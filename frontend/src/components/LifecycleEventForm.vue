<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  createLifecycleEvent,
  getLifecycleCatalog,
  listLifecycleEvents,
  type LifecycleCatalog,
  type LifecycleEvent,
} from '../api/lifecycle'

const props = defineProps<{ invoiceId: number }>()
const emit = defineEmits<{ created: [] }>()

const catalog = ref<LifecycleCatalog | null>(null)
const events = ref<LifecycleEvent[]>([])
const error = ref('')

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
  error.value = ''
  try {
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
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(async () => {
  catalog.value = await getLifecycleCatalog()
  await refreshEvents()
})
</script>

<template>
  <div>
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

      <button type="submit" data-testid="lifecycle-submit-button">Enregistrer</button>
    </form>
    <p v-if="error" role="alert">{{ error }}</p>

    <h4>Historique</h4>
    <ul data-testid="lifecycle-events-list">
      <li v-for="ev in events" :key="ev.id">
        {{ ev.status }}
        <span v-if="ev.details.length && ev.details[0].reason">— {{ ev.details[0].reason }}</span>
      </li>
    </ul>
  </div>
</template>
