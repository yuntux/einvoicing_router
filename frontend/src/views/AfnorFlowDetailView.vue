<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { afnorFlowDownloadUrl, getAfnorFlowContent, getInvoice, type AfnorFlow } from '../api/invoices'
import { getLifecycleCatalog, listLifecycleEvents, type StatusCatalogEntry } from '../api/lifecycle'
import { useErrorMessage } from '../composables/useErrorMessage'
import { formatDateTimeFr } from '../utils/date'

const props = defineProps<{ id: string; flowId: string }>()
const router = useRouter()
const { error, guard } = useErrorMessage()

const invoiceNumber = ref('')
const flow = ref<AfnorFlow | null>(null)
const eventDatetime = ref<string | null>(null)
const statusInfo = ref<StatusCatalogEntry | null>(null)
const rawContent = ref('')

function goToList() {
  router.push({ name: 'invoices' })
}

function goToInvoice() {
  router.push({ name: 'invoice-detail', params: { id: props.id } })
}

// Échappe le XML pour un affichage HTML sûr (les chevrons des balises doivent
// s'afficher tels quels, jamais être interprétés) puis met en gras le contenu
// textuel de chaque balise, jamais les balises elles-mêmes ni les espaces/retours
// à la ligne purement indentatifs entre elles.
function escapeHtml(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

const formattedXml = computed(() => {
  return rawContent.value
    .split(/(<[^>]+>)/g)
    .map((part) => {
      if (part === '') return ''
      if (/^<[^>]+>$/.test(part) || part.trim() === '') return escapeHtml(part)
      return `<strong>${escapeHtml(part)}</strong>`
    })
    .join('')
})

onMounted(async () => {
  const invoiceId = Number(props.id)
  const flowId = Number(props.flowId)

  await guard(async () => {
    const [invoice, events, catalog, content] = await Promise.all([
      getInvoice(invoiceId),
      listLifecycleEvents(invoiceId),
      getLifecycleCatalog(),
      getAfnorFlowContent(invoiceId, flowId),
    ])
    invoiceNumber.value = invoice.invoice_number
    flow.value = invoice.afnor_flows.find((f) => f.id === flowId) ?? null
    const event = events.find((ev) => ev.afnor_flow?.id === flowId)
    eventDatetime.value = event?.event_datetime ?? null
    statusInfo.value = catalog.statuses.find((s) => s.key === event?.status) ?? null
    rawContent.value = content
  })
})
</script>

<template>
  <main class="stack">
    <p v-if="error" role="alert">{{ error }}</p>

    <header class="page-header">
      <nav class="breadcrumb">
        <button type="button" class="back-link" data-testid="afnor-flow-back-to-list" @click="goToList">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M15 6l-6 6 6 6" />
          </svg>
          Retour à la liste des factures
        </button>
        <svg class="breadcrumb-sep" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 6l6 6-6 6" />
        </svg>
        <button type="button" class="breadcrumb-link" data-testid="afnor-flow-back-to-invoice" @click="goToInvoice">
          Retour à la facture {{ invoiceNumber }}
        </button>
      </nav>
      <h1>Flux CDAR {{ flow?.direction === 'in' ? 'reçu' : 'transmis' }}</h1>
    </header>

    <section v-if="flow" class="card">
      <div class="modal-stats" data-testid="afnor-flow-metadata">
        <div class="modal-stat-card">
          <span class="modal-stat-label">Identifiant</span>
          <span class="modal-stat-value">{{ flow.flow_id ?? '—' }}</span>
        </div>
        <div class="modal-stat-card">
          <span class="modal-stat-label">Horodatage</span>
          <span class="modal-stat-value">{{ eventDatetime ? formatDateTimeFr(eventDatetime) : '—' }}</span>
        </div>
        <div class="modal-stat-card">
          <span class="modal-stat-label">Code</span>
          <span class="modal-stat-value">{{ statusInfo?.cdar_code ?? '—' }}</span>
        </div>
        <div class="modal-stat-card">
          <span class="modal-stat-label">Message</span>
          <span class="modal-stat-value">{{ statusInfo?.label ?? '—' }}</span>
        </div>
      </div>
    </section>

    <section class="card">
      <div class="xml-viewer-header">
        <h3>Contenu brut</h3>
        <a
          v-if="flow?.has_file"
          :href="afnorFlowDownloadUrl(Number(id), flow.id)"
          class="btn btn-accent xml-download-btn"
          data-testid="afnor-flow-download"
        >
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M8 2v8m0 0l-3-3m3 3l3-3M2.5 12.5h11" />
          </svg>
          Télécharger le XML
        </a>
      </div>
      <pre class="xml-viewer" data-testid="afnor-flow-content" v-html="formattedXml"></pre>
    </section>
  </main>
</template>
