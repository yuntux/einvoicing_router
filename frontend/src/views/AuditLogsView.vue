<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listAuditLogs, type AuditLogEntry, type AuditLogFilters } from '../api/audit'
import { useErrorMessage } from '../composables/useErrorMessage'

const auditLogs = ref<AuditLogEntry[]>([])
const { error, guard } = useErrorMessage()

// Filtres (§ 8.3), dans le même ordre que les colonnes du tableau ci-dessous.
const filterDateFrom = ref('')
const filterDateTo = ref('')
const filterUserEmail = ref('')
const filterAction = ref('')
const filterTarget = ref('')
const filterIpAddress = ref('')

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

  const filters: AuditLogFilters = {}
  if (filterDateFrom.value) filters.created_from = filterDateFrom.value
  if (filterDateTo.value) filters.created_to = filterDateTo.value
  if (filterUserEmail.value) filters.user_email = filterUserEmail.value
  if (filterAction.value) filters.action = filterAction.value
  if (filterTarget.value) filters.target = filterTarget.value
  if (filterIpAddress.value) filters.ip_address = filterIpAddress.value
  await guard(async () => {
    auditLogs.value = await listAuditLogs(filters)
  })
}

onMounted(refresh)
</script>

<template>
  <main class="stack">
    <header class="page-header">
      <h1>Journal d'audit</h1>
      <p>Actions utilisateur sur l'IHM.</p>
    </header>

    <p v-if="error" role="alert">{{ error }}</p>

    <section class="card">
      <h2>Filtres</h2>
      <form @submit.prevent="refresh">
        <div class="field">
          <label for="al-filter-date-from">Date</label>
          <div class="cluster">
            <input
              id="al-filter-date-from"
              v-model="filterDateFrom"
              type="date"
              placeholder="Du"
              data-testid="audit-log-filter-date-from"
            />
            <input
              v-model="filterDateTo"
              type="date"
              placeholder="Au"
              data-testid="audit-log-filter-date-to"
            />
          </div>
        </div>
        <input
          v-model="filterUserEmail"
          placeholder="Utilisateur"
          data-testid="audit-log-filter-user-email"
        />
        <input
          v-model="filterAction"
          placeholder="Action"
          data-testid="audit-log-filter-action"
        />
        <input
          v-model="filterTarget"
          placeholder="Cible"
          data-testid="audit-log-filter-target"
        />
        <input
          v-model="filterIpAddress"
          placeholder="Adresse IP"
          data-testid="audit-log-filter-ip-address"
        />
        <button type="submit" class="btn-secondary" data-testid="audit-log-filter-submit-button">
          Filtrer
        </button>
      </form>
    </section>

    <section class="card">
      <table data-testid="audit-logs-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Utilisateur</th>
            <th>Action</th>
            <th>Cible</th>
            <th>Adresse IP</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="log in auditLogs" :key="log.id" :data-testid="`audit-log-row-${log.id}`">
            <td>{{ log.created_at }}</td>
            <td>{{ log.user_email ?? 'non identifié' }}</td>
            <td>{{ log.action }}</td>
            <td>{{ log.target }}</td>
            <td>{{ log.ip_address ?? '—' }}</td>
          </tr>
          <tr v-if="auditLogs.length === 0">
            <td colspan="5" class="entity-list-empty">Aucune action enregistrée.</td>
          </tr>
        </tbody>
      </table>
    </section>
  </main>
</template>
