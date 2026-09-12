<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listTechnicalLogs, type TechnicalLog } from '../api/audit'
import StatusBadge from '../components/StatusBadge.vue'
import { useErrorMessage } from '../composables/useErrorMessage'

const technicalLogs = ref<TechnicalLog[]>([])
const { error, guard } = useErrorMessage()

async function refresh() {
  await guard(async () => {
    technicalLogs.value = await listTechnicalLogs()
  })
}

onMounted(refresh)
</script>

<template>
  <main class="stack">
    <header class="page-header">
      <h1>Journal des traitements</h1>
      <p>Résultat métier des traitements batch (ex. cycle de polling).</p>
    </header>

    <p v-if="error" role="alert">{{ error }}</p>

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
            <td>{{ log.company_id ?? '—' }}</td>
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
