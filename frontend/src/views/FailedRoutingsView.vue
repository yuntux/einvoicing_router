<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  listFailedRoutings,
  replayRoutings,
  runSendCycle,
  type FailedInvoiceRouting,
} from '../api/invoiceRoutings'
import StatusBadge from '../components/StatusBadge.vue'

const routings = ref<FailedInvoiceRouting[]>([])
const selected = ref<Set<number>>(new Set())
const error = ref('')
const message = ref('')

async function refresh() {
  routings.value = await listFailedRoutings()
  selected.value = new Set()
}

onMounted(refresh)

function toggle(id: number) {
  if (selected.value.has(id)) {
    selected.value.delete(id)
  } else {
    selected.value.add(id)
  }
  // Force la réactivité (Set muté en place).
  selected.value = new Set(selected.value)
}

function selectAllForInvoice(invoiceId: number) {
  const ids = routings.value.filter((r) => r.invoice_id === invoiceId).map((r) => r.id)
  selected.value = new Set([...selected.value, ...ids])
}

async function forceSendCycle() {
  error.value = ''
  message.value = ''
  try {
    await runSendCycle()
    await refresh()
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function replaySelected() {
  error.value = ''
  message.value = ''
  try {
    const results = await replayRoutings([...selected.value])
    const successCount = results.filter((r) => r.success).length
    message.value = `${successCount}/${results.length} rejeu(x) réussi(s).`
    await refresh()
  } catch (e) {
    error.value = (e as Error).message
  }
}
</script>

<template>
  <main class="stack">
    <header class="page-header">
      <h1>Échecs de routage</h1>
      <p>Suivi des envois en échec ou en retry, avec rejeu manuel unitaire ou en masse.</p>
    </header>

    <section class="card">
      <div class="cluster">
        <button type="button" class="btn-secondary" data-testid="force-send-cycle-button" @click="forceSendCycle">
          Forcer un cycle d'envoi
        </button>

        <button
          type="button"
          :disabled="selected.size === 0"
          data-testid="replay-selected-button"
          @click="replaySelected"
        >
          Rejouer la sélection ({{ selected.size }})
        </button>
      </div>

      <p v-if="message" role="status">{{ message }}</p>
      <p v-if="error" role="alert">{{ error }}</p>
    </section>

    <section class="card">
      <table data-testid="failed-routings-table">
        <thead>
          <tr>
            <th></th>
            <th>Facture</th>
            <th>Émetteur</th>
            <th>Cible</th>
            <th>Statut</th>
            <th>Tentatives</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="routing in routings" :key="routing.id" :data-testid="`failed-routing-row-${routing.id}`">
            <td>
              <input
                type="checkbox"
                :checked="selected.has(routing.id)"
                :data-testid="`failed-routing-checkbox-${routing.id}`"
                @change="toggle(routing.id)"
              />
            </td>
            <td>{{ routing.invoice_number }}</td>
            <td>{{ routing.emitter_siren }}</td>
            <td>{{ routing.target_application_name }}</td>
            <td><StatusBadge :value="routing.transfer_status" /></td>
            <td>{{ routing.attempt_count }}</td>
            <td>
              <button type="button" class="btn-secondary btn-sm" @click="selectAllForInvoice(routing.invoice_id)">
                Sélectionner toutes les cibles de cette facture
              </button>
            </td>
          </tr>
          <tr v-if="routings.length === 0">
            <td colspan="7" class="entity-list-empty">Aucun échec de routage en cours.</td>
          </tr>
        </tbody>
      </table>
    </section>
  </main>
</template>
