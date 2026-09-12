<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getInvoice,
  invoiceDownloadUrl,
  listInvoices,
  type Invoice,
  type InvoiceDetail,
  type InvoiceFilters,
} from '../api/invoices'
import { listCompanyLookups, type CompanyLookup } from '../api/companies'
import { listTargetApplicationLookups, type TargetApplicationLookup } from '../api/targetApplications'
import { isReadOnly } from '../api/auth'
import LifecycleEventForm from '../components/LifecycleEventForm.vue'
import LifecycleStatusForm from '../components/LifecycleStatusForm.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useErrorMessage } from '../composables/useErrorMessage'
import { formatDateFr, formatDateTimeFr } from '../utils/date'

const route = useRoute()
const router = useRouter()

const invoices = ref<Invoice[]>([])
const selected = ref<InvoiceDetail | null>(null)
const targetApplications = ref<TargetApplicationLookup[]>([])
const companies = ref<CompanyLookup[]>([])
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

// Libellés FR pour `transfer_status` (§ mêmes valeurs que ROUTING_BADGE_CLASS
// ci-dessus, StatusBadge ne fait qu'un code couleur, jamais de traduction) —
// utilisés dans la popin de détail (§ section "Routage"), où le statut brut de
// l'API ("to_send", "failed_final"...) serait incompréhensible tel quel.
const ROUTING_STATUS_LABEL: Record<string, string> = {
  sent: 'Envoyée avec succès',
  to_send: "En attente du prochain cycle d'envoi",
  retrying: 'Échec, nouvel essai prévu',
  failed: 'Échec',
  failed_final: 'Échec définitif',
}

function routingStatusLabel(status: string): string {
  return ROUTING_STATUS_LABEL[status] ?? status
}

function targetApplicationName(targetId: number): string {
  return targetApplications.value.find((t) => t.id === targetId)?.name ?? `Application cible #${targetId}`
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
const filterCompanyId = ref('')
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
  if (filterCompanyId.value) filters.company_id = Number(filterCompanyId.value)
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

// Détail de facture routé (§ /invoices/:id, plutôt qu'une popin) : le clic sur une
// ligne pousse une vraie navigation — URL partageable, bouton précédent du
// navigateur fonctionnel nativement — au lieu de basculer un simple booléen local.
function openInvoice(id: number) {
  router.push({ name: 'invoice-detail', params: { id } })
}

function goBackToList() {
  router.push({ name: 'invoices' })
}

async function loadSelected(idParam: string | string[] | undefined) {
  if (!idParam) {
    selected.value = null
    downloadMenuOpen.value = false
    return
  }
  const id = Number(Array.isArray(idParam) ? idParam[0] : idParam)
  await guard(async () => {
    selected.value = await getInvoice(id)
  })
}

// Navigue entre /invoices et /invoices/:id (ou d'une facture à l'autre) sans
// remonter le composant — même `component:` sur les deux routes, § router.ts.
watch(() => route.params.id, (id) => loadSelected(id))

const downloadMenuOpen = ref(false)
const downloadControlRef = ref<HTMLElement | null>(null)

function onDocumentClick(event: MouseEvent) {
  if (downloadMenuOpen.value && !downloadControlRef.value?.contains(event.target as Node)) {
    downloadMenuOpen.value = false
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && selected.value) {
    goBackToList()
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
})

async function refreshSelected() {
  if (selected.value) {
    selected.value = await getInvoice(selected.value.id)
  }
}

function scheduleRefreshSelected() {
  setTimeout(refreshSelected, 500)
}

const lifecycleEventFormRef = ref<InstanceType<typeof LifecycleEventForm> | null>(null)

async function onLifecycleEventCreated() {
  if (selected.value) {
    selected.value = await getInvoice(selected.value.id)
  }
  await lifecycleEventFormRef.value?.refreshEvents()
}

onMounted(async () => {
  await guard(async () => {
    ;[targetApplications.value, companies.value] = await Promise.all([
      listTargetApplicationLookups(),
      listCompanyLookups(),
    ])
  })
  await refreshInvoices()
  // Chargement initial si l'URL pointe déjà sur une facture (lien direct/rechargement
  // de page) — les navigations suivantes passent par le `watch` ci-dessus.
  await loadSelected(route.params.id)
})
</script>

<template>
  <main class="stack">
    <p v-if="error" role="alert">{{ error }}</p>

    <template v-if="!selected">
    <header class="page-header">
      <h1>Factures reçues</h1>
      <p>Factures récupérées depuis l'API AFNOR et leur routage vers les applications cibles.</p>
    </header>

    <section class="card">
      <h2>Filtres</h2>
      <form @submit.prevent="refreshInvoices">
        <input v-model="filterInvoiceNumber" placeholder="Numéro de facture" data-testid="filter-invoice-number" />
        <input v-model="filterEmitterSiren" placeholder="SIREN émetteur" data-testid="filter-emitter-siren" />
        <input v-model="filterEmitterName" placeholder="Raison sociale émetteur" data-testid="filter-emitter-name" />

        <div class="field">
          <label for="filter-company-id">Destinataire</label>
          <select id="filter-company-id" v-model="filterCompanyId" data-testid="filter-company-id">
            <option value="">Toutes les entreprises</option>
            <option v-for="company in companies" :key="company.id" :value="company.id">
              {{ company.name }}
            </option>
          </select>
        </div>

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
            <th>Destinataire</th>
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
            @click="openInvoice(invoice.id)"
            :data-testid="`invoice-row-${invoice.invoice_number}`"
          >
            <td>{{ invoice.invoice_number }}</td>
            <td>
              {{ invoice.emitter_siren }}
              <div class="entity-sub">{{ invoice.emitter_name ?? 'annuaire inconnu' }}</div>
            </td>
            <td>
              {{ invoice.company_siren }}
              <div class="entity-sub">{{ invoice.company_name }}</div>
            </td>
            <td>{{ formatDateFr(invoice.invoice_date) }}</td>
            <td>{{ invoice.amount_excl_tax ?? '—' }} {{ invoice.currency }}</td>
            <td>{{ invoice.amount_tax ?? '—' }} {{ invoice.currency }}</td>
            <td>{{ invoice.amount_total ?? '—' }} {{ invoice.currency }}</td>
            <td :data-testid="`invoice-last-download-${invoice.invoice_number}`">
              <template v-if="invoice.last_download_at">
                {{ formatDateTimeFr(invoice.last_download_at) }} par
                {{ invoice.last_download_by ?? 'utilisateur non identifié' }}
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
            <td colspan="9" class="entity-list-empty">Aucune facture ne correspond aux filtres.</td>
          </tr>
        </tbody>
      </table>
    </section>
    </template>

    <template v-else>
      <header class="page-header">
        <nav class="breadcrumb">
          <button
            type="button"
            class="back-link"
            data-testid="invoice-detail-back"
            @click="goBackToList"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M15 6l-6 6 6 6" />
            </svg>
            Retour à la liste
          </button>
        </nav>
        <h1>Facture {{ selected.invoice_number }}</h1>
      </header>

      <section class="card" data-testid="invoice-detail">
        <div class="modal-stats">
          <div class="modal-stat-card">
            <span class="modal-stat-label">Émetteur</span>
            <span class="modal-stat-value">{{ selected.emitter_siren }}</span>
            <span class="entity-sub">{{ selected.emitter_name ?? 'annuaire inconnu' }}</span>
          </div>
          <div class="modal-stat-card">
            <span class="modal-stat-label">Destinataire</span>
            <span class="modal-stat-value">{{ selected.company_siren }}</span>
            <span class="entity-sub">{{ selected.company_name }}</span>
          </div>
          <div class="modal-stat-card">
            <span class="modal-stat-label">Date</span>
            <span class="modal-stat-value">{{ formatDateFr(selected.invoice_date) }}</span>
          </div>
          <div class="modal-stat-card">
            <span class="modal-stat-label">Statut cycle de vie</span>
            <span><StatusBadge :value="selected.lifecycle_status" /></span>
          </div>
          <div class="modal-stat-card">
            <span class="modal-stat-label">Montant HT</span>
            <span class="modal-stat-value">{{ selected.amount_excl_tax ?? '—' }} {{ selected.currency }}</span>
          </div>
          <div class="modal-stat-card">
            <span class="modal-stat-label">Montant TVA</span>
            <span class="modal-stat-value">{{ selected.amount_tax ?? '—' }} {{ selected.currency }}</span>
          </div>
          <div class="modal-stat-card">
            <span class="modal-stat-label">Montant TTC</span>
            <span class="modal-stat-value">{{ selected.amount_total ?? '—' }} {{ selected.currency }}</span>
          </div>
          <div class="modal-stat-card">
            <span class="modal-stat-label">Dernier téléchargement</span>
            <span data-testid="invoice-last-download">
              <template v-if="selected.last_download_at">
                {{ formatDateTimeFr(selected.last_download_at) }} par
                {{ selected.last_download_by ?? 'utilisateur non identifié' }}
              </template>
              <template v-else>jamais</template>
            </span>
          </div>
        </div>

        <div class="download-control-wrapper">
          <div ref="downloadControlRef" class="download-control">
            <div class="download-btn-group">
              <a
                :href="invoiceDownloadUrl(selected.id)"
                class="btn btn-accent download-btn-main"
                data-testid="invoice-download-link"
                @click="scheduleRefreshSelected"
              >
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M8 2v8m0 0l-3-3m3 3l3-3M2.5 12.5h11" />
                </svg>
                Télécharger la facture
              </a>
              <button
                type="button"
                class="download-btn-toggle"
                aria-label="Choisir le format de téléchargement"
                data-testid="invoice-download-format-toggle"
                @click="downloadMenuOpen = !downloadMenuOpen"
              >
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M4 6l4 4 4-4" />
                </svg>
              </button>
            </div>
            <div v-if="downloadMenuOpen" class="download-menu" data-testid="invoice-download-menu">
              <a
                :href="invoiceDownloadUrl(selected.id)"
                data-testid="invoice-download-format-original"
                @click="downloadMenuOpen = false; scheduleRefreshSelected()"
              >
                {{ selected.syntax ?? 'Format d’origine' }}
                <span class="entity-sub">(format de réception)</span>
              </a>
            </div>
          </div>
        </div>

        <div class="modal-columns">
          <div class="modal-column">
            <LifecycleEventForm ref="lifecycleEventFormRef" :key="selected.id" :invoice-id="selected.id" />
            <LifecycleStatusForm
              v-if="!isReadOnly"
              :invoice-id="selected.id"
              @created="onLifecycleEventCreated"
            />
          </div>

          <div class="modal-column">
            <h3>Enveloppe du flux AFNOR</h3>
            <div class="kv-columns" data-testid="invoice-flow-envelope">
              <div class="kv-list">
                <p>
                  <strong>Syntaxe :</strong> {{ selected.syntax ?? '—' }}
                  <span v-if="selected.flow_name" class="entity-sub">({{ selected.flow_name }})</span>
                </p>
                <p>
                  <strong>Règle de traitement :</strong> {{ selected.processing_rule ?? '—' }}
                  <span v-if="selected.processing_rule_source" class="entity-sub">
                    (Source : {{ selected.processing_rule_source }})
                  </span>
                </p>
                <p><strong>Profil :</strong> {{ selected.flow_profile ?? '—' }}</p>
              </div>
              <div class="kv-list">
                <p>
                  <strong>Direction / type :</strong> {{ selected.flow_direction ?? '—' }} / {{ selected.flow_type ?? '—' }}
                </p>
                <p>
                  <strong>Identifiant de suivi :</strong>
                  <code v-if="selected.tracking_id">{{ selected.tracking_id }}</code>
                  <template v-else>—</template>
                </p>
                <p>
                  <strong>Accusé de réception :</strong>
                  <StatusBadge :value="selected.ack_status" />
                  <span v-if="selected.ack_details" class="entity-sub">{{ selected.ack_details }}</span>
                </p>
              </div>
            </div>

            <h3>Routage</h3>
            <table v-if="selected.routings.length" data-testid="invoice-routings-list">
              <thead>
                <tr>
                  <th>Application cible</th>
                  <th>Statut de transfert</th>
                  <th>Tentatives</th>
                  <th>Prochain essai</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="routing in selected.routings" :key="routing.id">
                  <td>{{ targetApplicationName(routing.target_application_id) }}</td>
                  <td>
                    <span class="badge" :class="ROUTING_BADGE_CLASS[routing.transfer_status] ?? ''">
                      {{ routingStatusLabel(routing.transfer_status) }}
                    </span>
                  </td>
                  <td>{{ routing.attempt_count }}</td>
                  <td>{{ routing.next_attempt_at ? formatDateTimeFr(routing.next_attempt_at) : '—' }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="entity-list-empty" data-testid="invoice-no-routing">Aucune application cible routée.</p>
          </div>
        </div>
      </section>
    </template>
  </main>
</template>
