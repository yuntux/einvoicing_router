<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { isReadOnly } from '../api/auth'
import { afnorFlowDownloadUrl } from '../api/invoices'
import {
  createLifecycleEvent,
  getLifecycleCatalog,
  lifecycleEventAttachmentDownloadUrl,
  listLifecycleEvents,
  type LifecycleCatalog,
  type LifecycleEvent,
} from '../api/lifecycle'
import { useErrorMessage } from '../composables/useErrorMessage'
import StatusBadge from './StatusBadge.vue'

const props = defineProps<{ invoiceId: number }>()
const emit = defineEmits<{ created: [] }>()

const catalog = ref<LifecycleCatalog | null>(null)
const events = ref<LifecycleEvent[]>([])
const { error, guard } = useErrorMessage()

const status = ref('')
const reason = ref('')
const action = ref('')
const comment = ref('')
const confirmed = ref(false)

const purchaseStatuses = computed(() =>
  (catalog.value?.statuses ?? []).filter((s) => s.manual_side === 'purchase'),
)

const selectedStatusInfo = computed(() =>
  purchaseStatuses.value.find((s) => s.key === status.value) ?? null,
)

async function refreshEvents() {
  events.value = await listLifecycleEvents(props.invoiceId)
}

async function submit() {
  await guard(async () => {
    await createLifecycleEvent(props.invoiceId, {
      status: status.value,
      reason: reason.value || null,
      action: action.value || null,
      comment: comment.value || null,
      confirmed: confirmed.value,
    })
    status.value = ''
    reason.value = ''
    action.value = ''
    comment.value = ''
    confirmed.value = false
    await refreshEvents()
    emit('created')
  })
}

onMounted(async () => {
  catalog.value = await getLifecycleCatalog()
  await refreshEvents()
})
</script>

<template>
  <div class="stack">
    <div v-if="!isReadOnly">
      <h3>Enregistrer un statut de cycle de vie</h3>
      <form @submit.prevent="submit">
        <select v-model="status" data-testid="lifecycle-status-select" required>
          <option value="" disabled>Statut</option>
          <option v-for="s in purchaseStatuses" :key="s.key" :value="s.key">{{ s.label }}</option>
        </select>

        <template v-if="selectedStatusInfo?.requires_detail">
          <select v-model="reason" data-testid="lifecycle-reason-select" required>
            <option value="" disabled>Motif</option>
            <option v-for="(label, code) in catalog?.reasons" :key="code" :value="code">{{ label }}</option>
          </select>
          <select v-model="action" data-testid="lifecycle-action-select">
            <option value="">Action (facultatif)</option>
            <option v-for="(label, code) in catalog?.actions" :key="code" :value="code">{{ label }}</option>
          </select>
          <textarea v-model="comment" placeholder="Commentaire" data-testid="lifecycle-comment-input" />
        </template>

        <label v-if="selectedStatusInfo?.requires_confirmation">
          <input type="checkbox" v-model="confirmed" data-testid="lifecycle-confirm-checkbox" />
          Je confirme le refus de cette facture
        </label>

        <button type="submit" class="btn-secondary" data-testid="lifecycle-submit-button">Enregistrer</button>
      </form>
      <p v-if="error" role="alert">{{ error }}</p>
    </div>

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
              {{ ev.event_datetime }}
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
            <a
              v-if="ev.afnor_flow?.has_file"
              :href="afnorFlowDownloadUrl(invoiceId, ev.afnor_flow.id)"
              :data-testid="`afnor-flow-download-${ev.afnor_flow.id}`"
            >
              Voir le CDAR {{ ev.direction === 'in' ? 'reçu' : 'transmis' }}
            </a>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>
