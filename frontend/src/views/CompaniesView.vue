<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { type Company, createCompany, listCompanies } from '../api/companies'
import {
  getSuperPDPCredentialsStatus,
  setSuperPDPCredentials,
  type SuperPDPCredentialsStatus,
} from '../api/superpdpCredentials'

const companies = ref<Company[]>([])
const siren = ref('')
const name = ref('')
const error = ref('')

const credentialsStatus = reactive<Record<number, SuperPDPCredentialsStatus>>({})
const openCredentialsForm = ref<number | null>(null)
const credentialsClientId = ref('')
const credentialsClientSecret = ref('')

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
}

async function submitCredentials(companyId: number) {
  error.value = ''
  try {
    credentialsStatus[companyId] = await setSuperPDPCredentials(
      companyId,
      credentialsClientId.value,
      credentialsClientSecret.value,
    )
    openCredentialsForm.value = null
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(refresh)
</script>

<template>
  <main>
    <h1>Entreprises gérées</h1>

    <form @submit.prevent="submit">
      <input v-model="siren" placeholder="SIREN" maxlength="9" required data-testid="siren-input" />
      <input v-model="name" placeholder="Raison sociale" required data-testid="name-input" />
      <button type="submit" data-testid="submit-button">Ajouter</button>
    </form>
    <p v-if="error" role="alert">{{ error }}</p>

    <ul data-testid="companies-list">
      <li v-for="company in companies" :key="company.id" :data-testid="`company-row-${company.id}`">
        {{ company.siren }} — {{ company.name }}
        —
        <span :data-testid="`superpdp-credentials-status-${company.id}`">
          {{
            credentialsStatus[company.id]?.configured
              ? `Identifiants SuperPDP configurés (${credentialsStatus[company.id]?.client_id})`
              : 'Identifiants SuperPDP non configurés'
          }}
        </span>
        <button
          type="button"
          :data-testid="`superpdp-credentials-toggle-${company.id}`"
          @click="toggleCredentialsForm(company.id)"
        >
          {{ credentialsStatus[company.id]?.configured ? 'Remplacer' : 'Configurer' }}
        </button>

        <form
          v-if="openCredentialsForm === company.id"
          @submit.prevent="submitCredentials(company.id)"
        >
          <input
            v-model="credentialsClientId"
            placeholder="Client ID SuperPDP"
            required
            data-testid="superpdp-client-id-input"
          />
          <input
            v-model="credentialsClientSecret"
            type="password"
            placeholder="Client secret SuperPDP"
            required
            data-testid="superpdp-client-secret-input"
          />
          <button type="submit" data-testid="superpdp-credentials-submit-button">
            Enregistrer
          </button>
        </form>
      </li>
    </ul>
  </main>
</template>
