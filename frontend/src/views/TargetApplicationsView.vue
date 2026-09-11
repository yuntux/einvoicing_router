<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listCompanies, type Company } from '../api/companies'
import {
  createTargetApplication,
  listTargetApplications,
  type RoutingMethod,
  type TargetApplication,
  type TargetApplicationCreated,
} from '../api/targetApplications'

const targetApplications = ref<TargetApplication[]>([])
const companies = ref<Company[]>([])
const name = ref('')
const routingMethod = ref<RoutingMethod>('mail')
const companyId = ref<number | null>(null)

// Paramètres méthode "mail" (§ 4.9.1)
const to = ref('')
const cc = ref('')
const bcc = ref('')

// Paramètres méthode "afnor_api" (§ 4.9.2)
const redirectUrls = ref('')
const preferredConversionFormat = ref('')
const appType = ref<'confidential' | 'public'>('confidential')
const webhookUrl = ref('')

const error = ref('')
const createdCredentials = ref<TargetApplicationCreated | null>(null)

function splitList(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((v) => v.trim())
    .filter(Boolean)
}

async function refresh() {
  targetApplications.value = await listTargetApplications()
}

async function submit() {
  error.value = ''
  createdCredentials.value = null

  if (routingMethod.value === 'afnor_api' && !companyId.value) {
    error.value = "L'entreprise est requise pour la méthode afnor_api (§ 4.9.2)."
    return
  }

  const parameters =
    routingMethod.value === 'mail'
      ? { to: splitList(to.value), cc: splitList(cc.value), bcc: splitList(bcc.value) }
      : {
          redirect_urls: splitList(redirectUrls.value),
          preferred_conversion_format: preferredConversionFormat.value || null,
          app_type: appType.value,
          webhook_url: webhookUrl.value || null,
        }

  try {
    const created = await createTargetApplication({
      name: name.value,
      routing_method: routingMethod.value,
      company_id: companyId.value,
      parameters,
    })
    if (created.oauth_client_id && created.oauth_client_secret) {
      createdCredentials.value = created
    }
    name.value = ''
    companyId.value = null
    to.value = ''
    cc.value = ''
    bcc.value = ''
    redirectUrls.value = ''
    preferredConversionFormat.value = ''
    webhookUrl.value = ''
    await refresh()
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(async () => {
  await refresh()
  companies.value = await listCompanies()
})
</script>

<template>
  <main>
    <h1>Applications cibles</h1>

    <form @submit.prevent="submit">
      <input v-model="name" placeholder="Nom" required data-testid="ta-name-input" />
      <select v-model="routingMethod" data-testid="ta-method-select">
        <option value="mail">Routage mail</option>
        <option value="afnor_api">Mise à disposition via API AFNOR</option>
      </select>

      <select
        v-if="routingMethod === 'afnor_api'"
        v-model="companyId"
        data-testid="ta-company-select"
      >
        <option :value="null" disabled>Entreprise</option>
        <option v-for="company in companies" :key="company.id" :value="company.id">
          {{ company.name }}
        </option>
      </select>

      <fieldset v-if="routingMethod === 'mail'">
        <legend>Destinataires (§ 4.9.1)</legend>
        <input v-model="to" placeholder="À (séparés par des virgules)" data-testid="ta-to-input" />
        <input v-model="cc" placeholder="CC" data-testid="ta-cc-input" />
        <input v-model="bcc" placeholder="CCI" data-testid="ta-bcc-input" />
      </fieldset>

      <fieldset v-else>
        <legend>Application OAuth (§ 4.9.2)</legend>
        <input v-model="redirectUrls" placeholder="URLs de redirection" />
        <input v-model="preferredConversionFormat" placeholder="Format préféré de conversion" />
        <select v-model="appType">
          <option value="confidential">Confidentielle</option>
          <option value="public">Publique</option>
        </select>
        <input v-model="webhookUrl" placeholder="URL de webhook" />
      </fieldset>

      <button type="submit" data-testid="ta-submit-button">Ajouter</button>
    </form>
    <p v-if="error" role="alert">{{ error }}</p>

    <div v-if="createdCredentials" role="status" data-testid="ta-oauth-credentials">
      <p>
        <strong>Identifiants OAuth générés — à copier maintenant, le secret ne sera plus
        affiché ensuite.</strong>
      </p>
      <p>Client ID : <code data-testid="ta-oauth-client-id">{{ createdCredentials.oauth_client_id }}</code></p>
      <p>
        Client secret :
        <code data-testid="ta-oauth-client-secret">{{ createdCredentials.oauth_client_secret }}</code>
      </p>
    </div>

    <ul data-testid="target-applications-list">
      <li v-for="ta in targetApplications" :key="ta.id">
        {{ ta.name }} — {{ ta.routing_method }}
      </li>
    </ul>
  </main>
</template>
