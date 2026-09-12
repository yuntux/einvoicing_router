<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  listFailedRoutings,
  replayRoutings,
  runSendCycle,
  type FailedInvoiceRouting,
  type FailedRoutingFilters,
} from '../api/invoiceRoutings'
import StatusBadge from '../components/StatusBadge.vue'
import { useErrorMessage } from '../composables/useErrorMessage'

const routings = ref<FailedInvoiceRouting[]>([])
const selected = ref<Set<number>>(new Set())
const { error, guard } = useErrorMessage()
const message = ref('')

// Filtres (§ 8.3), dans le même ordre que les colonnes du tableau ci-dessous.
const filterInvoiceNumber = ref('')
const filterEmitterSiren = ref('')
const filterTargetApplicationName = ref('')
const filterTransferStatus = ref('')
const filterAttemptCount = ref('')

async function refresh() {
  const filters: FailedRoutingFilters = {}
  if (filterInvoiceNumber.value) filters.invoice_number = filterInvoiceNumber.value
  if (filterEmitterSiren.value) filters.emitter_siren = filterEmitterSiren.value
  if (filterTargetApplicationName.value) filters.target_application_name = filterTargetApplicationName.value
  if (filterTransferStatus.value) filters.transfer_status = filterTransferStatus.value
  if (filterAttemptCount.value) filters.attempt_count = Number(filterAttemptCount.value)
  routings.value = await listFailedRoutings(filters)
  selected.value = new Set()
}

onMounted(() => guard(refresh))

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
  message.value = ''
  await guard(async () => {
    await runSendCycle()
    await refresh()
  })
}

async function replaySelected() {
  message.value = ''
  await guard(async () => {
    const results = await replayRoutings([...selected.value])
    const successCount = results.filter((r) => r.success).length
    message.value = `${successCount}/${results.length} rejeu(x) réussi(s).`
    await refresh()
  })
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
      <h2>Filtres</h2>
      <form @submit.prevent="refresh">
        <input
          v-model="filterInvoiceNumber"
          placeholder="Facture"
          data-testid="failed-routing-filter-invoice-number"
        />
        <input
          v-model="filterEmitterSiren"
          placeholder="SIREN émetteur"
          data-testid="failed-routing-filter-emitter-siren"
        />
        <input
          v-model="filterTargetApplicationName"
          placeholder="Cible"
          data-testid="failed-routing-filter-target-application"
        />
        <select v-model="filterTransferStatus" data-testid="failed-routing-filter-status">
          <option value="">Tous les statuts</option>
          <option value="retrying">Nouvel essai prévu</option>
          <option value="failed_final">Échec définitif</option>
        </select>
        <input
          v-model="filterAttemptCount"
          type="number"
          placeholder="Tentatives"
          data-testid="failed-routing-filter-attempt-count"
        />
        <button type="submit" class="btn-secondary" data-testid="failed-routing-filter-submit-button">
          Filtrer
        </button>
      </form>
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
