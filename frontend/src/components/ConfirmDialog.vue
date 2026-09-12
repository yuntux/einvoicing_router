<script setup lang="ts">
defineProps<{
  open: boolean
  title: string
  message: string
  detail?: string
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
}>()

const emit = defineEmits<{ confirm: []; cancel: [] }>()
</script>

<template>
  <div v-if="open" class="confirm-overlay" @click.self="emit('cancel')">
    <div class="confirm-dialog card" role="alertdialog" aria-modal="true" data-testid="confirm-dialog">
      <h3>{{ title }}</h3>
      <p>{{ message }}</p>
      <p v-if="detail" class="confirm-detail">{{ detail }}</p>
      <slot />
      <div class="cluster confirm-actions">
        <button type="button" class="btn-secondary" data-testid="confirm-dialog-cancel" @click="emit('cancel')">
          {{ cancelLabel ?? 'Annuler' }}
        </button>
        <button
          type="button"
          :class="danger ? 'btn-danger' : ''"
          data-testid="confirm-dialog-confirm"
          @click="emit('confirm')"
        >
          {{ confirmLabel ?? 'Confirmer' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.confirm-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.confirm-dialog {
  max-width: 360px;
  margin: 0;
}

.confirm-actions {
  justify-content: flex-end;
  margin-top: 10px;
}

.confirm-detail {
  color: var(--color-text-muted, #666);
  font-size: 0.9em;
}
</style>
