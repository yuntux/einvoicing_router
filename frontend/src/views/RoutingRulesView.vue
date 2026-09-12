<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { listCompanies, type Company } from '../api/companies'
import { createPartner, listPartners, type Partner } from '../api/partners'
import { listTargetApplications, type TargetApplication } from '../api/targetApplications'
import { listRoutingRules, setRoutingRuleActive, type RoutingRule } from '../api/routingRules'

const partners = ref<Partner[]>([])
const targetApplications = ref<TargetApplication[]>([])
const rules = ref<RoutingRule[]>([])
const companies = ref<Company[]>([])

// Formulaire "nouveau fournisseur"
const newPartnerSiren = ref('')
const newPartnerName = ref('')

const error = ref('')
const pendingCells = ref(new Set<string>())

function cellKey(partnerId: number, targetId: number): string {
  return `${partnerId}:${targetId}`
}

function isChecked(partnerId: number, targetId: number): boolean {
  return rules.value.some(
    (r) => r.partner_directory_id === partnerId && r.target_application_id === targetId,
  )
}

function recipientLabel(target: TargetApplication): string {
  if (target.company_id == null) return '—'
  const company = companies.value.find((c) => c.id === target.company_id)
  return company ? company.name : '—'
}

const columns = computed(() =>
  [...targetApplications.value].sort((a, b) => (a.name < b.name ? -1 : 1)),
)

const rows = computed(() => [...partners.value].sort((a, b) => (a.siren < b.siren ? -1 : 1)))

async function refresh() {
  ;[partners.value, targetApplications.value, rules.value, companies.value] = await Promise.all([
    listPartners(),
    listTargetApplications(),
    listRoutingRules(),
    listCompanies(),
  ])
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

async function toggleCell(partnerId: number, targetId: number, checked: boolean) {
  error.value = ''
  const key = cellKey(partnerId, targetId)
  pendingCells.value.add(key)
  try {
    await setRoutingRuleActive(partnerId, targetId, checked)
    await refresh()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    pendingCells.value.delete(key)
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
      <h2>Règles de routage</h2>
      <div style="overflow-x: auto">
        <table data-testid="routing-rules-list">
          <thead>
            <tr>
              <th>Fournisseur</th>
              <th v-for="target in columns" :key="target.id">
                {{ target.name }}
                <div class="entity-sub">{{ recipientLabel(target) }}</div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="partner in rows" :key="partner.id" :data-testid="`routing-rule-row-${partner.id}`">
              <td>{{ partner.siren }} — {{ partner.name }}</td>
              <td v-for="target in columns" :key="target.id" style="text-align: center">
                <input
                  type="checkbox"
                  :checked="isChecked(partner.id, target.id)"
                  :disabled="pendingCells.has(cellKey(partner.id, target.id))"
                  :data-testid="`routing-rule-checkbox-${partner.id}-${target.id}`"
                  @change="toggleCell(partner.id, target.id, ($event.target as HTMLInputElement).checked)"
                />
              </td>
            </tr>
            <tr v-if="rows.length === 0 || columns.length === 0">
              <td :colspan="columns.length + 1" class="entity-list-empty">
                Aucun fournisseur ou aucune application cible configurée.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>
</template>
