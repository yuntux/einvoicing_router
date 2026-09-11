<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { type Company, listCompanies } from '../api/companies'
import { type AppUser, listUsers, updateUserAccess } from '../api/users'

const users = ref<AppUser[]>([])
const companies = ref<Company[]>([])
const error = ref('')

// Édition en place : rôle + entreprises cochées par utilisateur.
const editedRole = ref<Record<number, string>>({})
const editedCompanyIds = ref<Record<number, Set<number>>>({})

async function refresh() {
  users.value = await listUsers()
  companies.value = await listCompanies()
  for (const user of users.value) {
    editedRole.value[user.id] = user.role
    editedCompanyIds.value[user.id] = new Set(user.company_ids)
  }
}

function toggleCompany(userId: number, companyId: number) {
  const set = editedCompanyIds.value[userId]
  if (set.has(companyId)) {
    set.delete(companyId)
  } else {
    set.add(companyId)
  }
  editedCompanyIds.value = { ...editedCompanyIds.value, [userId]: set }
}

async function saveAccess(userId: number) {
  error.value = ''
  try {
    await updateUserAccess(userId, {
      role: editedRole.value[userId],
      company_ids: [...editedCompanyIds.value[userId]],
    })
    await refresh()
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(refresh)
</script>

<template>
  <main>
    <h1>Gestion des accès (§ NF4)</h1>
    <p v-if="error" role="alert">{{ error }}</p>

    <table data-testid="users-table">
      <thead>
        <tr>
          <th>Utilisateur</th>
          <th>Rôle</th>
          <th>Périmètre entreprises</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="user in users" :key="user.id" :data-testid="`user-row-${user.id}`">
          <td>{{ user.name }} ({{ user.email }})</td>
          <td>
            <select v-model="editedRole[user.id]" :data-testid="`user-role-select-${user.id}`">
              <option value="user">Utilisateur restreint</option>
              <option value="admin">Administrateur (toutes entreprises)</option>
            </select>
          </td>
          <td>
            <label v-for="company in companies" :key="company.id">
              <input
                type="checkbox"
                :checked="editedCompanyIds[user.id]?.has(company.id)"
                :data-testid="`user-company-checkbox-${user.id}-${company.id}`"
                @change="toggleCompany(user.id, company.id)"
              />
              {{ company.name }}
            </label>
          </td>
          <td>
            <button
              type="button"
              :data-testid="`user-save-button-${user.id}`"
              @click="saveAccess(user.id)"
            >
              Enregistrer
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </main>
</template>
