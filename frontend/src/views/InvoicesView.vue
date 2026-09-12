<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  afnorFlowDownloadUrl,
  getInvoice,
  invoiceDownloadUrl,
  listInvoices,
  type Invoice,
  type InvoiceDetail,
  type InvoiceFilters,
} from '../api/invoices'
import { listTargetApplicationLookups, type TargetApplicationLookup } from '../api/targetApplications'
import LifecycleEventForm from '../components/LifecycleEventForm.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useErrorMessage } from '../composables/useErrorMessage'

const invoices = ref<Invoice[]>([])
const selected = ref<InvoiceDetail | null>(null)
const targetApplications = ref<TargetApplicationLookup[]>([])
const { error, guard } = useErrorMessage()

// § 4.7/§ 8.3 : un badge par application cible de l'entreprise de la facture,
// coloré selon le statut de routage effectif (ou gris si cette application n'a pas
// à recevoir cette facture).
function companyTargetApplications(companyId: number): TargetApplicationLookup[] {
  return targetApplications.value.filter((t) => t.company_id === companyId)
}

const ROUTING_BADGE_CLASS: Record<string, string> = {
  sent: 'badge-success',
  to_send: 'badge-info',
  retrying: 'badge-warning',
  failed: 'badge-danger',
  failed_final: 'badge-danger',
}

function routingBadgeClass(invoice: Invoice, targetId: number): string {
  const routing = invoice.routings.find((r) => r.target_application_id === targetId)
  if (!routing) return ''
  return ROUTING_BADGE_CLASS[routing.transfer_status] ?? ''
}

function isUnrouted(invoice: Invoice): boolean {
  return invoice.routings.length === 0
}

const showRoutingLegend = ref(false)
const ROUTING_LEGEND = [
  { class: 'badge-success', label: 'Routée avec succès vers cette application' },
  { class: 'badge-info', label: "En attente du prochain cycle d'envoi" },
  { class: 'badge-warning', label: 'Échec, un nouvel essai est prévu' },
  { class: 'badge-danger', label: "Échec définitif, plus aucun essai prévu" },
  { class: '', label: "Cette application n'a pas à recevoir cette facture" },
] as const

// Filtres (§ 8.3) — dans le même ordre que les colonnes du tableau ci-dessous.
const filterInvoiceNumber = ref('')
const filterEmitterSiren = ref('')
const filterEmitterName = ref('')
const filterDateFrom = ref('')
const filterDateTo = ref('')
const filterAmountExclTaxMin = ref('')
const filterAmountExclTaxMax = ref('')
const filterVatAmountMin = ref('')
const filterVatAmountMax = ref('')
const filterAmountTotalMin = ref('')
const filterAmountTotalMax = ref('')
const filterDownloaded = ref<'' | 'true' | 'false'>('')

const rangeFilters = [
  { from: filterDateFrom, to: filterDateTo, label: 'Date' },
  { from: filterAmountExclTaxMin, to: filterAmountExclTaxMax, label: 'Montant HT' },
  { from: filterVatAmountMin, to: filterVatAmountMax, label: 'Montant TVA' },
  { from: filterAmountTotalMin, to: filterAmountTotalMax, label: 'Montant TTC' },
]

function rangeError(): string {
  for (const { from, to, label } of rangeFilters) {
    if (from.value && to.value && to.value < from.value) {
      return `${label} : la borne de fin doit être supérieure ou égale à la borne de début.`
    }
  }
  return ''
}

async function refreshInvoices() {
  const rangeErr = rangeError()
  if (rangeErr) {
    error.value = rangeErr
    return
  }

  const filters: InvoiceFilters = {}
  if (filterInvoiceNumber.value) filters.invoice_number = filterInvoiceNumber.value
  if (filterEmitterSiren.value) filters.emitter_siren = filterEmitterSiren.value
  if (filterEmitterName.value) filters.emitter_name = filterEmitterName.value
  if (filterDateFrom.value) filters.invoice_date_from = filterDateFrom.value
  if (filterDateTo.value) filters.invoice_date_to = filterDateTo.value
  if (filterAmountExclTaxMin.value) filters.amount_excl_tax_min = Number(filterAmountExclTaxMin.value)
  if (filterAmountExclTaxMax.value) filters.amount_excl_tax_max = Number(filterAmountExclTaxMax.value)
  if (filterVatAmountMin.value) filters.vat_amount_min = Number(filterVatAmountMin.value)
  if (filterVatAmountMax.value) filters.vat_amount_max = Number(filterVatAmountMax.value)
  if (filterAmountTotalMin.value) filters.amount_total_min = Number(filterAmountTotalMin.value)
  if (filterAmountTotalMax.value) filters.amount_total_max = Number(filterAmountTotalMax.value)
  if (filterDownloaded.value) filters.downloaded = filterDownloaded.value === 'true'
  await guard(async () => {
    invoices.value = await listInvoices(filters)
  })
}

async function selectInvoice(id: number) {
  selected.value = await getInvoice(id)
}

function vatAmount(invoice: Invoice): number | null {
  if (invoice.amount_total == null || invoice.amount_excl_tax == null) return null
  return invoice.amount_total - invoice.amount_excl_tax
}

async function refreshSelected() {
  if (selected.value) {
    selected.value = await getInvoice(selected.value.id)
  }
}

function scheduleRefreshSelected() {
  setTimeout(refreshSelected, 500)
}

async function onLifecycleEventCreated() {
  if (selected.value) {
    selected.value = await getInvoice(selected.value.id)
  }
}

onMounted(async () => {
  await guard(async () => {
    targetApplications.value = await listTargetApplicationLookups()
  })
  await refreshInvoices()
})
</script>

<template>
  <main class="stack">
    <header class="page-header">
      <h1>Factures reçues</h1>
      <p>Factures récupérées depuis l'API AFNOR et leur routage vers les applications cibles.</p>
    </header>

    <p v-if="error" role="alert">{{ error }}</p>

    <section class="card">
      <h2>Filtres</h2>
      <form @submit.prevent="refreshInvoices">
        <input v-model="filterInvoiceNumber" placeholder="Numéro de facture" data-testid="filter-invoice-number" />
        <input v-model="filterEmitterSiren" placeholder="SIREN émetteur" data-testid="filter-emitter-siren" />
        <input v-model="filterEmitterName" placeholder="Raison sociale émetteur" data-testid="filter-emitter-name" />

        <div class="field">
          <label for="filter-date-from">Date</label>
          <div class="cluster">
            <input
              id="filter-date-from"
              v-model="filterDateFrom"
              type="date"
              placeholder="Du"
              data-testid="filter-date-from"
            />
            <input
              v-model="filterDateTo"
              type="date"
              placeholder="Au"
              data-testid="filter-date-to"
            />
          </div>
        </div>

        <div class="field">
          <label for="filter-amount-excl-tax-min">Montant HT</label>
          <div class="cluster">
            <input
              id="filter-amount-excl-tax-min"
              v-model="filterAmountExclTaxMin"
              type="number"
              step="0.01"
              placeholder="Min"
              data-testid="filter-amount-excl-tax-min"
            />
            <input
              v-model="filterAmountExclTaxMax"
              type="number"
              step="0.01"
              placeholder="Max"
              data-testid="filter-amount-excl-tax-max"
            />
          </div>
        </div>

        <div class="field">
          <label for="filter-vat-amount-min">Montant TVA</label>
          <div class="cluster">
            <input
              id="filter-vat-amount-min"
              v-model="filterVatAmountMin"
              type="number"
              step="0.01"
              placeholder="Min"
              data-testid="filter-vat-amount-min"
            />
            <input
              v-model="filterVatAmountMax"
              type="number"
              step="0.01"
              placeholder="Max"
              data-testid="filter-vat-amount-max"
            />
          </div>
        </div>

        <div class="field">
          <label for="filter-amount-total-min">Montant TTC</label>
          <div class="cluster">
            <input
              id="filter-amount-total-min"
              v-model="filterAmountTotalMin"
              type="number"
              step="0.01"
              placeholder="Min"
              data-testid="filter-amount-total-min"
            />
            <input
              v-model="filterAmountTotalMax"
              type="number"
              step="0.01"
              placeholder="Max"
              data-testid="filter-amount-total-max"
            />
          </div>
        </div>

        <div class="field">
          <label for="filter-downloaded">Téléchargée</label>
          <select id="filter-downloaded" v-model="filterDownloaded" data-testid="filter-downloaded">
            <option value="">Toutes</option>
            <option value="true">Oui</option>
            <option value="false">Non</option>
          </select>
        </div>

        <button type="submit" class="btn-secondary" data-testid="filter-submit-button">Filtrer</button>
      </form>
    </section>

    <section class="card">
      <table data-testid="invoices-table">
        <thead>
          <tr>
            <th>N° facture</th>
            <th>Émetteur</th>
            <th>Date</th>
            <th>Montant HT</th>
            <th>Montant TVA</th>
            <th>Montant TTC</th>
            <th>Dernier téléchargement</th>
            <th style="position: relative">
              Routage
              <button
                type="button"
                class="legend-help-button"
                aria-label="Légende des couleurs de routage"
                data-testid="routing-legend-toggle"
                @click="showRoutingLegend = !showRoutingLegend"
              >
                ?
              </button>
              <div v-if="showRoutingLegend" class="legend-popover" data-testid="routing-legend-popover">
                <button
                  type="button"
                  class="legend-popover-close"
                  aria-label="Fermer"
                  @click="showRoutingLegend = false"
                >
                  ×
                </button>
                <ul>
                  <li v-for="item in ROUTING_LEGEND" :key="item.label">
                    <span class="badge" :class="item.class">&nbsp;</span>
                    {{ item.label }}
                  </li>
                </ul>
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="invoice in invoices"
            :key="invoice.id"
            class="row-clickable"
            @click="selectInvoice(invoice.id)"
            :data-testid="`invoice-row-${invoice.invoice_number}`"
          >
            <td>{{ invoice.invoice_number }}</td>
            <td>{{ invoice.emitter_siren }}</td>
            <td>{{ invoice.invoice_date }}</td>
            <td>{{ invoice.amount_excl_tax ?? '—' }} {{ invoice.currency }}</td>
            <td>{{ vatAmount(invoice) ?? '—' }} {{ invoice.currency }}</td>
            <td>{{ invoice.amount_total ?? '—' }} {{ invoice.currency }}</td>
            <td :data-testid="`invoice-last-download-${invoice.invoice_number}`">
              <template v-if="invoice.last_download_at">
                {{ invoice.last_download_at }} par {{ invoice.last_download_by ?? 'utilisateur non identifié' }}
              </template>
              <template v-else>jamais</template>
            </td>
            <td :data-testid="`invoice-routing-${invoice.invoice_number}`">
              <div class="cluster" style="gap: 4px">
                <span
                  v-for="target in companyTargetApplications(invoice.company_id)"
                  :key="target.id"
                  class="badge"
                  :class="routingBadgeClass(invoice, target.id)"
                  :data-testid="`invoice-routing-badge-${invoice.invoice_number}-${target.id}`"
                >
                  {{ target.name }}
                </span>
                <span
                  v-if="isUnrouted(invoice)"
                  style="color: var(--color-danger); font-weight: 600"
                  :data-testid="`invoice-unrouted-${invoice.invoice_number}`"
                >
                  Facture non routée
                </span>
              </div>
            </td>
          </tr>
          <tr v-if="invoices.length === 0">
            <td colspan="8" class="entity-list-empty">Aucune facture ne correspond aux filtres.</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="selected" class="card" data-testid="invoice-detail">
      <h2>Facture {{ selected.invoice_number }}</h2>
      <p>Émetteur : {{ selected.emitter_siren }} ({{ selected.emitter_name ?? 'annuaire inconnu' }})</p>
      <p class="cluster">Statut cycle de vie : <StatusBadge :value="selected.lifecycle_status" /></p>
      <p>
        <a
          :href="invoiceDownloadUrl(selected.id)"
          data-testid="invoice-download-link"
          @click="scheduleRefreshSelected"
        >
          Télécharger le fichier
        </a>
      </p>
      <p data-testid="invoice-last-download">
        Dernier téléchargement :
        <template v-if="selected.last_download_at">
          {{ selected.last_download_at }} par {{ selected.last_download_by ?? 'utilisateur non identifié' }}
        </template>
        <template v-else>jamais</template>
      </p>

      <h3>Enveloppe du flux AFNOR</h3>
      <ul class="entity-list" data-testid="invoice-flow-envelope">
        <li>Syntaxe : {{ selected.syntax ?? '—' }} <span class="entity-sub">({{ selected.flow_name ?? '—' }})</span></li>
        <li>Règle de traitement : {{ selected.processing_rule ?? '—' }} <span class="entity-sub">({{ selected.processing_rule_source ?? '—' }})</span></li>
        <li>Profil : {{ selected.flow_profile ?? '—' }}</li>
        <li>Direction / type : {{ selected.flow_direction ?? '—' }} / {{ selected.flow_type ?? '—' }}</li>
        <li>Identifiant de suivi (trackingId) : {{ selected.tracking_id ?? '—' }}</li>
        <li>
          Accusé de réception :
          <StatusBadge :value="selected.ack_status" />
          <span v-if="selected.ack_details" class="entity-sub">{{ selected.ack_details }}</span>
        </li>
      </ul>

      <h3>Routage</h3>
      <ul v-if="selected.routings.length" class="entity-list" data-testid="invoice-routings-list">
        <li v-for="routing in selected.routings" :key="routing.id">
          <span>Application cible #{{ routing.target_application_id }}</span>
          <StatusBadge :value="routing.transfer_status" />
        </li>
      </ul>
      <p v-else data-testid="invoice-no-routing">Aucune application cible routée.</p>

      <h3>Flux AFNOR</h3>
      <ul v-if="selected.afnor_flows.length" class="entity-list" data-testid="afnor-flows-list">
        <li v-for="flow in selected.afnor_flows" :key="flow.id">
          <div>
            <span class="entity-title">{{ flow.flow_type }} ({{ flow.direction }})</span>
            <span class="entity-sub">Syntaxe {{ flow.syntax }}<template v-if="flow.flow_id"> — {{ flow.flow_id }}</template></span>
          </div>
          <StatusBadge :value="flow.state" />
          <a
            v-if="flow.has_file"
            :href="afnorFlowDownloadUrl(selected.id, flow.id)"
            :data-testid="`afnor-flow-download-${flow.id}`"
          >
            Télécharger
          </a>
        </li>
      </ul>
      <p v-else data-testid="invoice-no-afnor-flow">Aucun flux AFNOR pour cette facture.</p>

      <LifecycleEventForm :key="selected.id" :invoice-id="selected.id" @created="onLifecycleEventCreated" />
    </section>
  </main>
</template>
