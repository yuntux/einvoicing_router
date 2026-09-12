<script lang="ts">
export interface TargetApplicationFieldsState {
  name: string
  fromAddress: string
  to: string
  cc: string
  bcc: string
  redirectUrls: string
  preferredConversionFormat: string
  appType: 'confidential' | 'public'
  webhookUrl: string
}

export function emptyTargetApplicationFieldsState(): TargetApplicationFieldsState {
  return {
    name: '',
    fromAddress: '',
    to: '',
    cc: '',
    bcc: '',
    redirectUrls: '',
    preferredConversionFormat: '',
    appType: 'confidential',
    webhookUrl: '',
  }
}
</script>

<script setup lang="ts">
import type { RoutingMethod } from '../api/targetApplications'

defineProps<{
  routingMethod: RoutingMethod
  idPrefix: string
  testIds: {
    from: string
    to: string
    cc: string
    bcc: string
    redirectUrls: string
    conversionFormat: string
    appType: string
    webhookUrl: string
  }
  /** Affiché en lecture seule dans le bloc OAuth, uniquement en édition d'une
   * application déjà créée (§ 4.9.2) — jamais en création, où l'application OAuth
   * n'existe pas encore. */
  oauthClientId?: string | null
}>()

const state = defineModel<TargetApplicationFieldsState>({ required: true })
</script>

<template>
  <div v-if="routingMethod === 'mail'" class="subsection">
    <div class="subsection-title">Destinataires</div>
    <div class="field">
      <label :for="`${idPrefix}-from`">De (facultatif)</label>
      <input
        :id="`${idPrefix}-from`"
        v-model="state.fromAddress"
        placeholder="Adresse d'expédition (par défaut : celle de la configuration SMTP)"
        :data-testid="testIds.from"
      />
    </div>
    <input v-model="state.to" placeholder="À (séparés par des virgules)" :data-testid="testIds.to" />
    <input v-model="state.cc" placeholder="CC" :data-testid="testIds.cc" />
    <input v-model="state.bcc" placeholder="CCI" :data-testid="testIds.bcc" />
  </div>

  <div v-else class="subsection">
    <div class="subsection-title">Application OAuth</div>
    <div v-if="oauthClientId" class="field">
      <label>Client ID</label>
      <code :data-testid="`${idPrefix}-client-id`">{{ oauthClientId }}</code>
    </div>
    <div class="field">
      <label :for="`${idPrefix}-redirect-urls`">URLs de redirection</label>
      <textarea
        :id="`${idPrefix}-redirect-urls`"
        v-model="state.redirectUrls"
        placeholder="URLs de redirection (une par ligne)"
        :data-testid="testIds.redirectUrls"
      />
    </div>
    <div class="field">
      <label :for="`${idPrefix}-conversion-format`">Format préféré de conversion</label>
      <select :id="`${idPrefix}-conversion-format`" v-model="state.preferredConversionFormat" :data-testid="testIds.conversionFormat">
        <option value="">Aucun (facultatif)</option>
        <option value="Factur-X">Factur-X</option>
        <option value="UBL">UBL</option>
        <option value="CII">CII</option>
      </select>
    </div>
    <div class="field">
      <label :for="`${idPrefix}-app-type`">Type d'application</label>
      <select :id="`${idPrefix}-app-type`" v-model="state.appType" :data-testid="testIds.appType">
        <option value="confidential">Confidentielle</option>
        <option value="public">Publique</option>
      </select>
    </div>
    <div class="field">
      <label :for="`${idPrefix}-webhook-url`">URL de webhook</label>
      <input
        :id="`${idPrefix}-webhook-url`"
        v-model="state.webhookUrl"
        placeholder="URL de webhook"
        :data-testid="testIds.webhookUrl"
      />
    </div>
  </div>
</template>
