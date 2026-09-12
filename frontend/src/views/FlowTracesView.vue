<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listFlowTraces, type FlowTrace } from '../api/audit'

const flowTraces = ref<FlowTrace[]>([])
const error = ref('')

const openFlowTraceId = ref<number | null>(null)

function toggleFlowTrace(id: number) {
  openFlowTraceId.value = openFlowTraceId.value === id ? null : id
}

async function refresh() {
  try {
    flowTraces.value = await listFlowTraces()
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(refresh)
</script>

<template>
  <main class="stack">
    <header class="page-header">
      <h1>Traces techniques (API AFNOR)</h1>
      <p>Requêtes/réponses HTTP brutes de chaque appel API AFNOR (NF1).</p>
    </header>

    <p v-if="error" role="alert">{{ error }}</p>

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
