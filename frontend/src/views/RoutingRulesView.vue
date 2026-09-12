<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { listCompanyLookups, type CompanyLookup } from '../api/companies'
import { createPartner, listPartners, type Partner } from '../api/partners'
import { listTargetApplicationLookups, type TargetApplicationLookup } from '../api/targetApplications'
import { listRoutingRules, setRoutingRuleActive, type RoutingRule } from '../api/routingRules'
import { useErrorMessage } from '../composables/useErrorMessage'

const partners = ref<Partner[]>([])
const targetApplications = ref<TargetApplicationLookup[]>([])
const rules = ref<RoutingRule[]>([])
const companies = ref<CompanyLookup[]>([])

// Formulaire "nouveau fournisseur"
const newPartnerSiren = ref('')
const newPartnerName = ref('')

const { error, guard } = useErrorMessage()
const pendingCells = ref(new Set<string>())

function cellKey(partnerId: number, targetId: number): string {
  return `${partnerId}:${targetId}`
}

function isChecked(partnerId: number, targetId: number): boolean {
  return rules.value.some(
    (r) => r.partner_directory_id === partnerId && r.target_application_id === targetId,
  )
}

function partnerHasNoRule(partnerId: number): boolean {
  return !rules.value.some((r) => r.partner_directory_id === partnerId)
}

function recipientLabel(target: TargetApplicationLookup): string {
  if (target.company_id == null) return '—'
  const company = companies.value.find((c) => c.id === target.company_id)
  return company ? company.name : '—'
}

// Filtres (§ 8.3), un par colonne du tableau : le fournisseur (colonne statique) et
// le nom d'application cible (colonnes dynamiques) — filtrage local, la matrice est
// déjà entièrement chargée en mémoire.
const filterPartner = ref('')
const filterTargetApplication = ref('')

const columns = computed(() =>
  [...targetApplications.value]
    .filter((t) => t.name.toLowerCase().includes(filterTargetApplication.value.toLowerCase()))
    .sort((a, b) => (a.name < b.name ? -1 : 1)),
)

const rows = computed(() =>
  [...partners.value]
    .filter((p) => {
      const needle = filterPartner.value.toLowerCase()
      return p.siren.toLowerCase().includes(needle) || p.name.toLowerCase().includes(needle)
    })
    .sort((a, b) => (a.siren < b.siren ? -1 : 1)),
)

async function refresh() {
  ;[partners.value, targetApplications.value, rules.value, companies.value] = await Promise.all([
    listPartners(),
    listTargetApplicationLookups(),
    listRoutingRules(),
    listCompanyLookups(),
  ])
}

async function submitPartner() {
  await guard(async () => {
    await createPartner({ siren: newPartnerSiren.value, name: newPartnerName.value })
    newPartnerSiren.value = ''
    newPartnerName.value = ''
    await refresh()
  })
}

async function toggleCell(
  partnerId: number,
  targetId: number,
  checked: boolean,
  rerouteExisting: boolean,
) {
  const key = cellKey(partnerId, targetId)
  pendingCells.value.add(key)
  await guard(async () => {
    await setRoutingRuleActive(partnerId, targetId, checked, rerouteExisting)
    await refresh()
  })
  pendingCells.value.delete(key)
}

// La case étant liée en lecture seule (:checked="isChecked(...)"), le navigateur
// a déjà visuellement basculé la case au moment de @change — si l'utilisateur
// annule dans le popin, on doit donc restaurer nous-mêmes l'état visuel de
// l'input (sinon il resterait décoché/coché à tort jusqu'au prochain refresh).
interface PendingConfirm {
  partnerId: number
  targetId: number
  checked: boolean
  input: HTMLInputElement
  partnerLabel: string
  targetLabel: string
  rerouteExisting: boolean
}

const pendingConfirm = ref<PendingConfirm | null>(null)

function requestToggle(
  event: Event,
  partnerId: number,
  targetId: number,
  partnerLabel: string,
  targetLabel: string,
) {
  const input = event.target as HTMLInputElement
  pendingConfirm.value = {
    partnerId,
    targetId,
    checked: input.checked,
    input,
    partnerLabel,
    targetLabel,
    rerouteExisting: true,
  }
}

function confirmToggle() {
  const pending = pendingConfirm.value
  if (!pending) return
  pendingConfirm.value = null
  toggleCell(pending.partnerId, pending.targetId, pending.checked, pending.rerouteExisting)
}

function cancelToggle() {
  const pending = pendingConfirm.value
  if (!pending) return
  pending.input.checked = !pending.checked
  pendingConfirm.value = null
}

onMounted(() => guard(refresh))
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
      <h2>Filtres</h2>
      <input
        v-model="filterPartner"
        placeholder="Fournisseur (SIREN ou raison sociale)"
        data-testid="routing-rules-filter-partner"
      />
      <input
        v-model="filterTargetApplication"
        placeholder="Application cible"
        data-testid="routing-rules-filter-target-application"
      />
    </section>

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
            <tr
              v-for="partner in rows"
              :key="partner.id"
              :class="{ 'row-danger': partnerHasNoRule(partner.id) }"
              :data-testid="`routing-rule-row-${partner.id}`"
            >
              <td>{{ partner.siren }} — {{ partner.name }}</td>
              <td v-for="target in columns" :key="target.id" style="text-align: center">
                <input
                  type="checkbox"
                  :checked="isChecked(partner.id, target.id)"
                  :disabled="pendingCells.has(cellKey(partner.id, target.id))"
                  :data-testid="`routing-rule-checkbox-${partner.id}-${target.id}`"
                  @change="
                    requestToggle(
                      $event,
                      partner.id,
                      target.id,
                      `${partner.siren} — ${partner.name}`,
                      target.name,
                    )
                  "
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

    <ConfirmDialog
      :open="pendingConfirm !== null"
      :title="pendingConfirm?.checked ? 'Activer la règle de routage ?' : 'Désactiver la règle de routage ?'"
      :message="
        pendingConfirm
          ? `${pendingConfirm.checked ? 'Router' : 'Ne plus router'} les factures de ${pendingConfirm.partnerLabel} vers ${pendingConfirm.targetLabel} ?`
          : ''
      "
      :detail="
        pendingConfirm && !pendingConfirm.checked
          ? `Seules les prochaines factures reçues ne seront plus routées vers ce canal ; les factures déjà routées ne sont pas affectées.`
          : ''
      "
      :danger="pendingConfirm ? !pendingConfirm.checked : false"
      @confirm="confirmToggle"
      @cancel="cancelToggle"
    >
      <fieldset v-if="pendingConfirm?.checked" class="reroute-choice" data-testid="reroute-choice">
        <label>
          <input
            type="radio"
            :value="true"
            v-model="pendingConfirm.rerouteExisting"
            data-testid="reroute-choice-existing"
          />
          Envoyer toutes les factures déjà reçues de ce fournisseur qui ne sont pas encore routées vers ce canal
        </label>
        <label>
          <input
            type="radio"
            :value="false"
            v-model="pendingConfirm.rerouteExisting"
            data-testid="reroute-choice-future-only"
          />
          Envoyer uniquement les futures factures reçues pour ce fournisseur
        </label>
      </fieldset>
    </ConfirmDialog>
  </main>
</template>

<style scoped>
.reroute-choice {
  border: none;
  padding: 0;
  margin: 10px 0 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.reroute-choice label {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 0.9em;
}
</style>
