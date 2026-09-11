<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { type Company, createCompany, listCompanies } from '../api/companies'

const companies = ref<Company[]>([])
const siren = ref('')
const name = ref('')
const error = ref('')

async function refresh() {
  companies.value = await listCompanies()
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
      <li v-for="company in companies" :key="company.id">
        {{ company.siren }} — {{ company.name }}
      </li>
    </ul>
  </main>
</template>
