<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { lifecycleEventAttachmentDownloadUrl, listLifecycleEvents, type LifecycleEvent } from '../api/lifecycle'
import StatusBadge from './StatusBadge.vue'

const props = defineProps<{ invoiceId: number }>()

const events = ref<LifecycleEvent[]>([])

async function refreshEvents() {
  events.value = await listLifecycleEvents(props.invoiceId)
}

defineExpose({ refreshEvents })

onMounted(refreshEvents)
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
            <RouterLink
              v-if="ev.afnor_flow?.has_file"
              :to="{ name: 'invoice-afnor-flow', params: { id: invoiceId, flowId: ev.afnor_flow.id } }"
              :data-testid="`afnor-flow-download-${ev.afnor_flow.id}`"
            >
              Voir le CDAR {{ ev.direction === 'in' ? 'reçu' : 'transmis' }}
            </RouterLink>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>
