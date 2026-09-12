<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listFlowTraces, type FlowTrace, type FlowTraceFilters } from '../api/audit'
import { useErrorMessage } from '../composables/useErrorMessage'

const flowTraces = ref<FlowTrace[]>([])
const { error, guard } = useErrorMessage()

const openFlowTraceId = ref<number | null>(null)

function toggleFlowTrace(id: number) {
  openFlowTraceId.value = openFlowTraceId.value === id ? null : id
}

// Filtres (§ 8.3), dans le même ordre que les colonnes du tableau ci-dessous.
const filterDateFrom = ref('')
const filterDateTo = ref('')
const filterDirection = ref('')
const filterAfnorApiVersion = ref('')
const filterHttpStatus = ref('')
const filterCorrelationId = ref('')

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

  const filters: FlowTraceFilters = {}
  if (filterDateFrom.value) filters.created_from = filterDateFrom.value
  if (filterDateTo.value) filters.created_to = filterDateTo.value
  if (filterDirection.value) filters.direction = filterDirection.value
  if (filterAfnorApiVersion.value) filters.afnor_api_version = filterAfnorApiVersion.value
  if (filterHttpStatus.value) filters.http_status = Number(filterHttpStatus.value)
  if (filterCorrelationId.value) filters.correlation_id = filterCorrelationId.value
  await guard(async () => {
    flowTraces.value = await listFlowTraces(filters)
  })
}

onMounted(refresh)
</script>

<template>
  <main class="stack">
    <header class="page-header">
      <h1>Traces techniques (API AFNOR)</h1>
      <p>Requêtes/réponses HTTP brutes de chaque appel API AFNOR.</p>
    </header>

    <p v-if="error" role="alert">{{ error }}</p>

    <section class="card">
      <h2>Filtres</h2>
      <form @submit.prevent="refresh">
        <div class="field">
          <label for="ft-filter-date-from">Date</label>
          <div class="cluster">
            <input
              id="ft-filter-date-from"
              v-model="filterDateFrom"
              type="date"
              placeholder="Du"
              data-testid="flow-trace-filter-date-from"
            />
            <input
              v-model="filterDateTo"
              type="date"
              placeholder="Au"
              data-testid="flow-trace-filter-date-to"
            />
          </div>
        </div>
        <input
          v-model="filterDirection"
          placeholder="Sens"
          data-testid="flow-trace-filter-direction"
        />
        <input
          v-model="filterAfnorApiVersion"
          placeholder="Version API"
          data-testid="flow-trace-filter-afnor-api-version"
        />
        <input
          v-model="filterHttpStatus"
          type="number"
          placeholder="Statut HTTP"
          data-testid="flow-trace-filter-http-status"
        />
        <input
          v-model="filterCorrelationId"
          placeholder="Correlation ID"
          data-testid="flow-trace-filter-correlation-id"
        />
        <button type="submit" class="btn-secondary" data-testid="flow-trace-filter-submit-button">
          Filtrer
        </button>
      </form>
    </section>

    <section class="card">
      <table data-testid="flow-traces-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Sens</th>
            <th>Version API</th>
            <th>Statut HTTP</th>
            <th>Correlation ID</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="trace in flowTraces" :key="trace.id">
            <tr :data-testid="`flow-trace-row-${trace.id}`">
              <td>{{ trace.created_at }}</td>
              <td>{{ trace.direction }}</td>
              <td>{{ trace.afnor_api_version }}</td>
              <td>
                <span class="badge" :class="trace.http_status < 400 ? 'badge-success' : 'badge-danger'">
                  {{ trace.http_status }}
                </span>
              </td>
              <td><code>{{ trace.correlation_id }}</code></td>
              <td>
                <button
                  type="button"
                  class="btn-secondary btn-sm"
                  :data-testid="`flow-trace-toggle-${trace.id}`"
                  @click="toggleFlowTrace(trace.id)"
                >
                  {{ openFlowTraceId === trace.id ? 'Masquer' : 'Détail' }}
                </button>
              </td>
            </tr>
            <tr v-if="openFlowTraceId === trace.id">
              <td colspan="6">
                <div class="cluster" style="align-items: flex-start">
                  <div>
                    <strong>Requête</strong>
                    <pre class="json-preview">{{ JSON.stringify(trace.request, null, 2) }}</pre>
                  </div>
                  <div>
                    <strong>Réponse</strong>
                    <pre class="json-preview">{{ JSON.stringify(trace.response, null, 2) }}</pre>
                  </div>
                  <div>
                    <strong>En-têtes requête</strong>
                    <pre class="json-preview">{{ JSON.stringify(trace.request_headers, null, 2) }}</pre>
                  </div>
                  <div>
                    <strong>En-têtes réponse</strong>
                    <pre class="json-preview">{{ JSON.stringify(trace.response_headers, null, 2) }}</pre>
                  </div>
                </div>
              </td>
            </tr>
          </template>
          <tr v-if="flowTraces.length === 0">
            <td colspan="6" class="entity-list-empty">Aucune trace technique enregistrée.</td>
          </tr>
        </tbody>
      </table>
    </section>
  </main>
</template>
