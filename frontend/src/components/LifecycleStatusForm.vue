<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { createLifecycleEvent, getLifecycleCatalog, type LifecycleCatalog } from '../api/lifecycle'
import { useErrorMessage } from '../composables/useErrorMessage'

const props = defineProps<{ invoiceId: number }>()
const emit = defineEmits<{ created: [] }>()

const catalog = ref<LifecycleCatalog | null>(null)
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
    emit('created')
  })
}

onMounted(async () => {
  catalog.value = await getLifecycleCatalog()
})
</script>

<template>
  <div>
    <form class="cluster lifecycle-quick-form" @submit.prevent="submit">
      <select
        v-model="status"
        class="lifecycle-status-select-wide"
        data-testid="lifecycle-status-select"
        required
      >
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
</template>
