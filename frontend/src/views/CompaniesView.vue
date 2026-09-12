<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { type Company, createCompany, listCompanies } from '../api/companies'
import {
  type AfnorPlatform,
  getSuperPDPCredentialsStatus,
  listAfnorPlatforms,
  setSuperPDPCredentials,
  type SuperPDPCredentialsStatus,
} from '../api/superpdpCredentials'

const companies = ref<Company[]>([])
const siren = ref('')
const name = ref('')
const error = ref('')
const credentialsSuccess = ref('')

const afnorPlatforms = ref<AfnorPlatform[]>([])
const credentialsStatus = reactive<Record<number, SuperPDPCredentialsStatus>>({})
const openCredentialsForm = ref<number | null>(null)
const credentialsClientId = ref('')
const credentialsClientSecret = ref('')
const credentialsPlatform = ref('')
const credentialsSubmitting = ref(false)

function platformLabel(key: string | null): string | null {
  if (!key) return null
  return afnorPlatforms.value.find((p) => p.key === key)?.label ?? key
}

async function refresh() {
  companies.value = await listCompanies()
  for (const company of companies.value) {
    credentialsStatus[company.id] = await getSuperPDPCredentialsStatus(company.id)
  }
}

async function submit() {
  error.value = ''
  try {
    await createCompany({ siren: siren.value, name: name.value })
    siren.value = ''
    name.value = ''
    await refresh()
  } catch (e) {
    error.value = (e as Error).message
  }
}

function toggleCredentialsForm(companyId: number) {
  openCredentialsForm.value = openCredentialsForm.value === companyId ? null : companyId
  credentialsClientId.value = ''
  credentialsClientSecret.value = ''
  credentialsPlatform.value = credentialsStatus[companyId]?.platform ?? ''
  error.value = ''
  credentialsSuccess.value = ''
}

async function submitCredentials(companyId: number) {
  error.value = ''
  credentialsSuccess.value = ''
  credentialsSubmitting.value = true
  try {
    credentialsStatus[companyId] = await setSuperPDPCredentials(
      companyId,
      credentialsClientId.value,
      credentialsClientSecret.value,
      credentialsPlatform.value,
    )
    credentialsSuccess.value = 'Test de connexion OK'
    openCredentialsForm.value = null
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    credentialsSubmitting.value = false
  }
}

onMounted(async () => {
  afnorPlatforms.value = await listAfnorPlatforms()
  await refresh()
})
</script>

<template>
  <main class="stack">
    <header class="page-header">
      <h1>Entreprises gérées</h1>
      <p>Les entreprises pour lesquelles le routeur récupère et route les factures.</p>
    </header>

    <section class="card">
      <h2>Ajouter une entreprise</h2>
      <form @submit.prevent="submit">
        <div class="field">
          <label for="siren-input">SIREN</label>
          <input id="siren-input" v-model="siren" placeholder="123456789" maxlength="9" required data-testid="siren-input" />
        </div>
        <div class="field">
          <label for="name-input">Raison sociale</label>
          <input id="name-input" v-model="name" placeholder="Raison sociale" required data-testid="name-input" />
        </div>
        <button type="submit" data-testid="submit-button">Ajouter</button>
      </form>
    </section>

    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="credentialsSuccess" role="status" data-testid="superpdp-credentials-test-success">
      {{ credentialsSuccess }}
    </p>

    <section class="card">
      <h2>Entreprises</h2>
      <table data-testid="companies-list">
        <thead>
          <tr>
            <th>SIREN</th>
            <th>Raison sociale</th>
            <th>Identifiants API AFNOR</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="company in companies" :key="company.id" :data-testid="`company-row-${company.id}`">
            <td>{{ company.siren }}</td>
            <td>{{ company.name }}</td>
            <td :data-testid="`superpdp-credentials-status-${company.id}`">
              <span class="badge" :class="credentialsStatus[company.id]?.configured ? 'badge-success' : 'badge-warning'">
                {{
                  credentialsStatus[company.id]?.configured
                    ? `Configurés (${credentialsStatus[company.id]?.client_id})`
                    : 'Non configurés'
                }}
              </span>
              <div v-if="platformLabel(credentialsStatus[company.id]?.platform ?? null)" class="entity-sub">
                Plateforme : {{ platformLabel(credentialsStatus[company.id]?.platform ?? null) }}
              </div>

              <form
                v-if="openCredentialsForm === company.id"
                class="cluster"
                @submit.prevent="submitCredentials(company.id)"
              >
                <input
                  v-model="credentialsClientId"
                  placeholder="Client ID API AFNOR"
                  required
                  data-testid="superpdp-client-id-input"
                />
                <input
                  v-model="credentialsClientSecret"
                  type="password"
                  placeholder="Client secret API AFNOR"
                  required
                  data-testid="superpdp-client-secret-input"
                />
                <select v-model="credentialsPlatform" data-testid="superpdp-platform-select">
                  <option value="">Plateforme par défaut du serveur</option>
                  <option v-for="p in afnorPlatforms" :key="p.key" :value="p.key">{{ p.label }}</option>
                </select>
                <button
                  type="submit"
                  class="btn-sm"
                  :disabled="credentialsSubmitting"
                  data-testid="superpdp-credentials-submit-button"
                >
                  {{ credentialsSubmitting ? 'Test de connexion…' : 'Enregistrer' }}
                </button>
              </form>
            </td>
            <td>
              <button
                type="button"
                class="btn-secondary btn-sm"
                :data-testid="`superpdp-credentials-toggle-${company.id}`"
                @click="toggleCredentialsForm(company.id)"
              >
                {{ credentialsStatus[company.id]?.configured ? 'Remplacer' : 'Configurer' }}
              </button>
            </td>
          </tr>
          <tr v-if="companies.length === 0">
            <td colspan="4" class="entity-list-empty">Aucune entreprise gérée pour le moment.</td>
          </tr>
        </tbody>
      </table>
    </section>
  </main>
</template>
