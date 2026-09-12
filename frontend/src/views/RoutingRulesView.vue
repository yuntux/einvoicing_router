<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { listCompanies, type Company } from '../api/companies'
import { createPartner, listPartners, type Partner } from '../api/partners'
import { listTargetApplications, type TargetApplication } from '../api/targetApplications'
import { listRoutingRules, upsertRoutingRule, type RoutingRule } from '../api/routingRules'

const partners = ref<Partner[]>([])
const targetApplications = ref<TargetApplication[]>([])
const rules = ref<RoutingRule[]>([])
const companies = ref<Company[]>([])

// Formulaire "nouveau fournisseur"
const newPartnerSiren = ref('')
const newPartnerName = ref('')

const error = ref('')

// Édition de la matrice fournisseur × application cible : une entrée par couple,
// pré-remplie depuis la règle existante le cas échéant, vide sinon (§ 4.3).
const edits = reactive<Record<string, { start_date: string; end_date: string }>>({})

function cellKey(partnerId: number, targetId: number): string {
  return `${partnerId}:${targetId}`
}

function initEdits() {
  for (const key of Object.keys(edits)) delete edits[key]
  for (const partner of partners.value) {
    for (const target of targetApplications.value) {
      const rule = rules.value.find(
        (r) => r.partner_directory_id === partner.id && r.target_application_id === target.id,
      )
      edits[cellKey(partner.id, target.id)] = {
        start_date: rule?.start_date ?? '',
        end_date: rule?.end_date ?? '',
      }
    }
  }
}

const rows = computed(() =>
  partners.value.flatMap((partner) =>
    targetApplications.value.map((target) => ({ partner, target })),
  ),
)

function recipientLabel(target: TargetApplication): string {
  if (target.company_id == null) return '—'
  const company = companies.value.find((c) => c.id === target.company_id)
  return company ? company.name : '—'
}

async function refresh() {
  ;[partners.value, targetApplications.value, rules.value, companies.value] = await Promise.all([
    listPartners(),
    listTargetApplications(),
    listRoutingRules(),
    listCompanies(),
  ])
  initEdits()
}

async function submitPartner() {
  error.value = ''
  try {
    await createPartner({ siren: newPartnerSiren.value, name: newPartnerName.value })
    newPartnerSiren.value = ''
    newPartnerName.value = ''
    await refresh()
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function saveCell(partnerId: number, targetId: number) {
  error.value = ''
  const cell = edits[cellKey(partnerId, targetId)]
  try {
    await upsertRoutingRule(partnerId, targetId, {
      start_date: cell.start_date || null,
      end_date: cell.end_date || null,
    })
    await refresh()
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(refresh)
</script>

<template>
  <main class="stack">
    <header class="page-header">
      <h1>Règles de routage</h1>
      <p>Routage des factures par émetteur (SIREN/SIRET) vers une ou plusieurs applications cibles.</p>
    </header>

    <section class="card">
      <h2>Ajouter un fournisseur</h2>
      <form @submit.prevent="submitPartner">
        <input v-model="newPartnerSiren" placeholder="SIREN" maxlength="9" required data-testid="partner-siren-input" />
        <input v-model="newPartnerName" placeholder="Raison sociale" required data-testid="partner-name-input" />
        <button type="submit" class="btn-secondary" data-testid="partner-submit-button">Ajouter un fournisseur</button>
      </form>
    </section>

    <p v-if="error" role="alert">{{ error }}</p>

    <section class="card">
      <h2>Règles existantes</h2>
      <table data-testid="routing-rules-list">
        <thead>
          <tr>
            <th>Fournisseur</th>
            <th>Application cible</th>
            <th>Destinataire</th>
            <th>Début</th>
            <th>Fin</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="cellKey(row.partner.id, row.target.id)"
            :data-testid="`routing-rule-row-${row.partner.id}-${row.target.id}`"
          >
            <td>{{ row.partner.siren }} — {{ row.partner.name }}</td>
            <td>{{ row.target.name }}</td>
            <td>{{ recipientLabel(row.target) }}</td>
            <td>
              <input
                v-model="edits[cellKey(row.partner.id, row.target.id)].start_date"
                type="date"
                :data-testid="`routing-rule-start-${row.partner.id}-${row.target.id}`"
              />
            </td>
            <td>
              <input
                v-model="edits[cellKey(row.partner.id, row.target.id)].end_date"
                type="date"
                :data-testid="`routing-rule-end-${row.partner.id}-${row.target.id}`"
              />
            </td>
            <td>
              <button
                type="button"
                class="btn-secondary btn-sm"
                :data-testid="`routing-rule-save-${row.partner.id}-${row.target.id}`"
                @click="saveCell(row.partner.id, row.target.id)"
              >
                Enregistrer
              </button>
            </td>
          </tr>
          <tr v-if="rows.length === 0">
            <td colspan="6" class="entity-list-empty">
              Aucun fournisseur ou aucune application cible configurée.
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </main>
</template>
