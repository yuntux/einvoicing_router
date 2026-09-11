<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listCompanies, type Company } from '../api/companies'
import {
  getInvoice,
  listInvoices,
  simulateInvoiceReception,
  type Invoice,
  type InvoiceDetail,
  type InvoiceFilters,
} from '../api/invoices'
import LifecycleEventForm from '../components/LifecycleEventForm.vue'

const companies = ref<Company[]>([])
const invoices = ref<Invoice[]>([])
const selected = ref<InvoiceDetail | null>(null)
const error = ref('')

// Filtres (§ 8.3)
const filterEmitterSiren = ref('')
const filterInvoiceNumber = ref('')
const filterCurrency = ref('')

// Simulation de réception (remplace le cron réel jusqu'au lot 5/6)
const simCompanyId = ref<number | null>(null)
const simEmitterSiren = ref('')
const simInvoiceNumber = ref('')
const simInvoiceDate = ref('')
const simAmountTotal = ref('')

async function refreshCompanies() {
  companies.value = await listCompanies()
}

async function refreshInvoices() {
  const filters: InvoiceFilters = {}
  if (filterEmitterSiren.value) filters.emitter_siren = filterEmitterSiren.value
  if (filterInvoiceNumber.value) filters.invoice_number = filterInvoiceNumber.value
  if (filterCurrency.value) filters.currency = filterCurrency.value
  invoices.value = await listInvoices(filters)
}

async function selectInvoice(id: number) {
  selected.value = await getInvoice(id)
}

async function onLifecycleEventCreated() {
  if (selected.value) {
    selected.value = await getInvoice(selected.value.id)
  }
}

async function submitSimulation() {
  error.value = ''
  if (!simCompanyId.value) {
    error.value = 'Entreprise réceptrice requise'
    return
  }
  try {
    await simulateInvoiceReception({
      company_id: simCompanyId.value,
      emitter_siren: simEmitterSiren.value,
      invoice_number: simInvoiceNumber.value,
      invoice_date: simInvoiceDate.value,
      amount_total: simAmountTotal.value ? Number(simAmountTotal.value) : null,
    })
    simEmitterSiren.value = ''
    simInvoiceNumber.value = ''
    simInvoiceDate.value = ''
    simAmountTotal.value = ''
    await refreshInvoices()
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(async () => {
  await Promise.all([refreshCompanies(), refreshInvoices()])
})
</script>

<template>
  <main>
    <h1>Factures reçues</h1>

    <section>
      <h2>Simuler la réception d'une facture</h2>
      <p>
        Remplace temporairement le polling SuperPDP réel (§ 4.1), en attendant le lot 6.
      </p>
      <form @submit.prevent="submitSimulation">
        <select v-model="simCompanyId" data-testid="sim-company-select">
          <option :value="null" disabled>Entreprise réceptrice</option>
          <option v-for="c in companies" :key="c.id" :value="c.id">{{ c.siren }} — {{ c.name }}</option>
        </select>
        <input v-model="simEmitterSiren" placeholder="SIREN émetteur" maxlength="9" required data-testid="sim-emitter-siren-input" />
        <input v-model="simInvoiceNumber" placeholder="Numéro de facture" required data-testid="sim-invoice-number-input" />
        <input v-model="simInvoiceDate" type="date" required data-testid="sim-invoice-date-input" />
        <input v-model="simAmountTotal" type="number" step="0.01" placeholder="Montant TTC" data-testid="sim-amount-input" />
        <button type="submit" data-testid="sim-submit-button">Simuler la réception</button>
      </form>
    </section>

    <p v-if="error" role="alert">{{ error }}</p>

    <section>
      <h2>Filtres</h2>
      <form @submit.prevent="refreshInvoices">
        <input v-model="filterEmitterSiren" placeholder="SIREN émetteur" data-testid="filter-emitter-siren" />
        <input v-model="filterInvoiceNumber" placeholder="Numéro de facture" data-testid="filter-invoice-number" />
        <input v-model="filterCurrency" placeholder="Devise" data-testid="filter-currency" />
        <button type="submit" data-testid="filter-submit-button">Filtrer</button>
      </form>
    </section>

    <section>
      <table data-testid="invoices-table">
        <thead>
          <tr>
            <th>N° facture</th>
            <th>Émetteur</th>
            <th>Date</th>
            <th>Montant</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="invoice in invoices"
            :key="invoice.id"
            @click="selectInvoice(invoice.id)"
            style="cursor: pointer"
            :data-testid="`invoice-row-${invoice.invoice_number}`"
          >
            <td>{{ invoice.invoice_number }}</td>
            <td>{{ invoice.emitter_siren }}</td>
            <td>{{ invoice.invoice_date }}</td>
            <td>{{ invoice.amount_total }} {{ invoice.currency }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="selected" data-testid="invoice-detail">
      <h2>Facture {{ selected.invoice_number }}</h2>
      <p>Émetteur : {{ selected.emitter_siren }} ({{ selected.emitter_name ?? 'annuaire inconnu' }})</p>
      <p>Statut cycle de vie : {{ selected.lifecycle_status ?? '—' }}</p>
      <h3>Routage</h3>
      <ul v-if="selected.routings.length" data-testid="invoice-routings-list">
        <li v-for="routing in selected.routings" :key="routing.id">
          Application cible #{{ routing.target_application_id }} — {{ routing.transfer_status }}
        </li>
      </ul>
      <p v-else data-testid="invoice-no-routing">Aucune application cible routée.</p>

      <LifecycleEventForm :key="selected.id" :invoice-id="selected.id" @created="onLifecycleEventCreated" />
    </section>
  </main>
</template>
