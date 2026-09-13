<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  getLifecycleCatalog,
  lifecycleEventAttachmentDownloadUrl,
  listLifecycleEvents,
  retryAfnorFlow,
  type LifecycleCatalog,
  type LifecycleEvent,
} from '../api/lifecycle'
import { useErrorMessage } from '../composables/useErrorMessage'
import { formatDateTimeFr } from '../utils/date'
import StatusBadge from './StatusBadge.vue'

const props = defineProps<{ invoiceId: number }>()

const events = ref<LifecycleEvent[]>([])
const catalog = ref<LifecycleCatalog | null>(null)
const { error, guard } = useErrorMessage()

const openRetryEditForm = ref<number | null>(null)
const retryReason = ref('')
const retryAction = ref('')
const retryComment = ref('')
const retrySubmitting = ref<number | null>(null)

async function refreshEvents() {
  events.value = await listLifecycleEvents(props.invoiceId)
}

defineExpose({ refreshEvents })

async function retry(event: LifecycleEvent) {
  if (!event.afnor_flow) return
  retrySubmitting.value = event.afnor_flow.id
  await guard(async () => {
    await retryAfnorFlow(props.invoiceId, event.afnor_flow!.id)
    await refreshEvents()
  })
  retrySubmitting.value = null
}

function toggleRetryEditForm(event: LifecycleEvent) {
  if (!event.afnor_flow) return
  const detail = event.details[0]
  openRetryEditForm.value = openRetryEditForm.value === event.afnor_flow.id ? null : event.afnor_flow.id
  retryReason.value = detail?.reason ?? ''
  retryAction.value = detail?.action ?? ''
  retryComment.value = detail?.comment ?? ''
  error.value = ''
}

async function submitRetryWithEdits(event: LifecycleEvent) {
  if (!event.afnor_flow) return
  retrySubmitting.value = event.afnor_flow.id
  await guard(async () => {
    await retryAfnorFlow(props.invoiceId, event.afnor_flow!.id, {
      reason: retryReason.value || null,
      action: retryAction.value || null,
      comment: retryComment.value || null,
    })
    openRetryEditForm.value = null
    await refreshEvents()
  })
  retrySubmitting.value = null
}

onMounted(async () => {
  catalog.value = await getLifecycleCatalog()
  await refreshEvents()
})
</script>

<template>
  <div class="stack">
    <div>
      <h4>Cycle de vie</h4>
      <p class="entity-sub" style="margin: -4px 0 8px">
        Chaque ligne fusionne le statut métier et son flux CDAR technique associé.
      </p>
      <ul v-if="events.length === 0" class="entity-list" data-testid="lifecycle-events-list">
        <li class="entity-list-empty">Aucun événement de cycle de vie.</li>
      </ul>
      <ul v-else class="timeline" data-testid="lifecycle-events-list">
        <li v-for="ev in events" :key="ev.id" class="timeline-item">
          <span class="timeline-dot" :class="ev.direction === 'in' ? 'timeline-dot-in' : 'timeline-dot-out'"></span>
          <div>
            <span class="cluster">
              <StatusBadge :value="ev.status" />
              <span
                class="badge"
                :class="ev.direction === 'in' ? 'badge-success' : 'badge-info'"
                :data-testid="`lifecycle-event-direction-${ev.id}`"
              >
                {{ ev.direction === 'in' ? 'Reçu de SuperPDP' : 'Saisi manuellement' }}
              </span>
              <StatusBadge v-if="ev.afnor_flow" :value="ev.afnor_flow.state" />
            </span>
            <p class="entity-sub" style="margin: 4px 0 0">
              <template v-if="ev.details.length && ev.details[0].reason">Motif : {{ ev.details[0].reason }} — </template>
              <template v-if="ev.amount != null">{{ ev.amount }} {{ ev.currency }} — </template>
              {{ formatDateTimeFr(ev.event_datetime) }}
            </p>
            <div v-if="ev.payments.length" class="entity-sub">
              Paiements :
              <span v-for="payment in ev.payments" :key="payment.id">
                {{ payment.amount }} {{ payment.currency }} le {{ payment.payment_date }}
              </span>
            </div>
            <div v-if="ev.attachments.length" class="cluster">
              <a
                v-for="attachment in ev.attachments"
                :key="attachment.id"
                :href="attachment.has_file ? lifecycleEventAttachmentDownloadUrl(invoiceId, ev.id, attachment.id) : undefined"
                :aria-disabled="!attachment.has_file"
              >
                {{ attachment.filename }}
              </a>
            </div>
            <RouterLink
              v-if="ev.afnor_flow?.has_file"
              :to="{ name: 'invoice-afnor-flow', params: { id: invoiceId, flowId: ev.afnor_flow.id } }"
              :data-testid="`afnor-flow-download-${ev.afnor_flow.id}`"
            >
              Voir le CDAR {{ ev.direction === 'in' ? 'reçu' : 'transmis' }}
            </RouterLink>

            <div v-if="ev.afnor_flow?.direction === 'out' && ev.afnor_flow.state === 'error'" class="stack" style="margin-top: 6px">
              <div class="cluster">
                <button
                  type="button"
                  class="btn-secondary btn-sm"
                  :disabled="retrySubmitting === ev.afnor_flow.id"
                  :data-testid="`afnor-flow-retry-${ev.afnor_flow.id}`"
                  @click="retry(ev)"
                >
                  {{ retrySubmitting === ev.afnor_flow.id ? 'Renvoi…' : 'Renvoyer' }}
                </button>
                <button
                  type="button"
                  class="btn-secondary btn-sm"
                  :data-testid="`afnor-flow-retry-edit-toggle-${ev.afnor_flow.id}`"
                  @click="toggleRetryEditForm(ev)"
                >
                  Modifier et renvoyer
                </button>
              </div>
              <form
                v-if="openRetryEditForm === ev.afnor_flow.id"
                class="cluster"
                @submit.prevent="submitRetryWithEdits(ev)"
              >
                <select v-model="retryReason" :data-testid="`afnor-flow-retry-reason-${ev.afnor_flow.id}`" required>
                  <option value="" disabled>Motif</option>
                  <option v-for="(label, code) in catalog?.reasons" :key="code" :value="code">{{ label }}</option>
                </select>
                <select v-model="retryAction" :data-testid="`afnor-flow-retry-action-${ev.afnor_flow.id}`">
                  <option value="">Action (facultatif)</option>
                  <option v-for="(label, code) in catalog?.actions" :key="code" :value="code">{{ label }}</option>
                </select>
                <textarea
                  v-model="retryComment"
                  placeholder="Commentaire"
                  :data-testid="`afnor-flow-retry-comment-${ev.afnor_flow.id}`"
                />
                <button
                  type="submit"
                  class="btn-sm"
                  :disabled="retrySubmitting === ev.afnor_flow.id"
                  :data-testid="`afnor-flow-retry-submit-${ev.afnor_flow.id}`"
                >
                  {{ retrySubmitting === ev.afnor_flow.id ? 'Renvoi…' : 'Enregistrer et renvoyer' }}
                </button>
              </form>
            </div>
          </div>
        </li>
      </ul>
      <p v-if="error" role="alert">{{ error }}</p>
    </div>
  </div>
</template>
