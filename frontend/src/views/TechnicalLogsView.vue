<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listTechnicalLogs, type TechnicalLog, type TechnicalLogFilters } from '../api/audit'
import { listCompanies, type Company } from '../api/companies'
import StatusBadge from '../components/StatusBadge.vue'
import { useErrorMessage } from '../composables/useErrorMessage'

const technicalLogs = ref<TechnicalLog[]>([])
const companies = ref<Company[]>([])
const { error, guard } = useErrorMessage()

// Filtres (§ 8.3), dans le même ordre que les colonnes du tableau ci-dessous.
const filterDateFrom = ref('')
const filterDateTo = ref('')
const filterLogType = ref('')
const filterOrigin = ref('')
const filterCompanyId = ref('')
const filterStatus = ref('')
const filterNewCount = ref('')
const filterUpdatedCount = ref('')
const filterDetails = ref('')

function dateRangeError(): string {
  if (filterDateFrom.value && filterDateTo.value && filterDateTo.value < filterDateFrom.value) {
    return 'Date : la borne de fin doit être supérieure ou égale à la borne de début.'
  }
  return ''
}

async function refresh() {
  const rangeErr = dateRangeError()
  if (rangeErr) {
    error.value = rangeErr
    return
  }

  const filters: TechnicalLogFilters = {}
  if (filterDateFrom.value) filters.created_from = filterDateFrom.value
  if (filterDateTo.value) filters.created_to = filterDateTo.value
  if (filterLogType.value) filters.log_type = filterLogType.value
  if (filterOrigin.value) filters.origin = filterOrigin.value
  if (filterCompanyId.value) filters.company_id = Number(filterCompanyId.value)
  if (filterStatus.value) filters.status = filterStatus.value
  if (filterNewCount.value) filters.new_count = Number(filterNewCount.value)
  if (filterUpdatedCount.value) filters.updated_count = Number(filterUpdatedCount.value)
  if (filterDetails.value) filters.details = filterDetails.value
  await guard(async () => {
    technicalLogs.value = await listTechnicalLogs(filters)
  })
}

function companyName(companyId: number | null): string {
  if (companyId == null) return '—'
  return companies.value.find((c) => c.id === companyId)?.name ?? '—'
}

onMounted(async () => {
  await guard(async () => {
    companies.value = await listCompanies()
  })
  await refresh()
})
</script>

<template>
  <main class="stack">
    <header class="page-header">
      <h1>Journal des traitements</h1>
      <p>Résultat métier des traitements batch (ex. cycle de polling).</p>
    </header>

    <p v-if="error" role="alert">{{ error }}</p>

    <section class="card">
      <h2>Filtres</h2>
      <form @submit.prevent="refresh">
        <div class="field">
          <label for="tl-filter-date-from">Date</label>
          <div class="cluster">
            <input
              id="tl-filter-date-from"
              v-model="filterDateFrom"
              type="date"
              placeholder="Du"
              data-testid="technical-log-filter-date-from"
            />
            <input
              v-model="filterDateTo"
              type="date"
              placeholder="Au"
              data-testid="technical-log-filter-date-to"
            />
          </div>
        </div>
        <input
          v-model="filterLogType"
          placeholder="Type"
          data-testid="technical-log-filter-log-type"
        />
        <input
          v-model="filterOrigin"
          placeholder="Origine"
          data-testid="technical-log-filter-origin"
        />
        <select v-model="filterCompanyId" data-testid="technical-log-filter-company">
          <option value="">Toutes les entreprises</option>
          <option v-for="company in companies" :key="company.id" :value="company.id">
            {{ company.name }}
          </option>
        </select>
        <input
          v-model="filterStatus"
          placeholder="Statut"
          data-testid="technical-log-filter-status"
        />
        <input
          v-model="filterNewCount"
          type="number"
          placeholder="Nouvelles"
          data-testid="technical-log-filter-new-count"
        />
        <input
          v-model="filterUpdatedCount"
          type="number"
          placeholder="Mises à jour"
          data-testid="technical-log-filter-updated-count"
        />
        <input
          v-model="filterDetails"
          placeholder="Détails"
          data-testid="technical-log-filter-details"
        />
        <button type="submit" class="btn-secondary" data-testid="technical-log-filter-submit-button">
          Filtrer
        </button>
      </form>
    </section>

    <section class="card">
      <table data-testid="technical-logs-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Type</th>
            <th>Origine</th>
            <th>Entreprise</th>
            <th>Statut</th>
            <th>Nouvelles</th>
            <th>Mises à jour</th>
            <th>Détails</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="log in technicalLogs" :key="log.id" :data-testid="`technical-log-row-${log.id}`">
            <td>{{ log.created_at }}</td>
            <td>{{ log.log_type }}</td>
            <td>{{ log.origin }}</td>
            <td>{{ companyName(log.company_id) }}</td>
            <td><StatusBadge :value="log.status" /></td>
            <td>{{ log.new_count }}</td>
            <td>{{ log.updated_count }}</td>
            <td>{{ log.details ?? '—' }}</td>
          </tr>
          <tr v-if="technicalLogs.length === 0">
            <td colspan="8" class="entity-list-empty">Aucun traitement enregistré.</td>
          </tr>
        </tbody>
      </table>
    </section>
  </main>
</template>
