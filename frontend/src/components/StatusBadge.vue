<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ value: string | null | undefined; fallback?: string }>()

// Regroupement visuel indicatif des statuts (cycle de vie AFNOR § 4.2 et
// transfert de routage § 4.7) — n'affecte pas la valeur affichée, seulement sa couleur.
const TONE_BY_VALUE: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
  approved: 'success',
  completed: 'success',
  payment_received: 'success',
  sent: 'success',
  done: 'success',
  success: 'success',
  to_send: 'info',
  retrying: 'warning',
  partially_approved: 'warning',
  suspended: 'warning',
  dispute: 'warning',
  warning: 'warning',
  refused: 'danger',
  rejected: 'danger',
  failed: 'danger',
  failed_final: 'danger',
  routing_error: 'danger',
  cancelled: 'danger',
  unacceptable: 'danger',
  error: 'danger',
}

const tone = computed(() => (props.value ? TONE_BY_VALUE[props.value] : undefined))
const label = computed(() => props.value ?? props.fallback ?? '—')
</script>

<template>
  <span class="badge" :class="tone ? `badge-${tone}` : ''">{{ label }}</span>
</template>
