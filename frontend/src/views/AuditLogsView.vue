<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listAuditLogs, type AuditLogEntry } from '../api/audit'

const auditLogs = ref<AuditLogEntry[]>([])
const error = ref('')

async function refresh() {
  try {
    auditLogs.value = await listAuditLogs()
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(refresh)
</script>

<template>
  <main class="stack">
    <header class="page-header">
      <h1>Journal d'audit</h1>
      <p>Actions utilisateur sur l'IHM (NF9).</p>
    </header>

    <p v-if="error" role="alert">{{ error }}</p>

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
