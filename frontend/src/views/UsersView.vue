<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { type Company, listCompanies } from '../api/companies'
import { type AppUser, createUser, listUsers, updateUserAccess } from '../api/users'
import { useErrorMessage } from '../composables/useErrorMessage'
import { formatDateTimeFr } from '../utils/date'

const users = ref<AppUser[]>([])
const companies = ref<Company[]>([])
const { error, guard } = useErrorMessage()
const { error: createError, guard: guardCreate } = useErrorMessage()

const newUserEmail = ref('')
const newUserName = ref('')

// Édition en place : rôle + entreprises cochées + actif/inactif par utilisateur.
const editedRole = ref<Record<number, string>>({})
const editedCompanyIds = ref<Record<number, Set<number>>>({})
const editedIsActive = ref<Record<number, boolean>>({})

async function refresh() {
  users.value = await listUsers()
  companies.value = await listCompanies()
  for (const user of users.value) {
    editedRole.value[user.id] = user.role
    editedCompanyIds.value[user.id] = new Set(user.company_ids)
    editedIsActive.value[user.id] = user.is_active
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
  await guard(async () => {
    await updateUserAccess(userId, {
      role: editedRole.value[userId],
      company_ids: [...editedCompanyIds.value[userId]],
      is_active: editedIsActive.value[userId],
    })
    await refresh()
  })
}

async function submitNewUser() {
  await guardCreate(async () => {
    await createUser({ email: newUserEmail.value, name: newUserName.value || undefined })
    newUserEmail.value = ''
    newUserName.value = ''
    await refresh()
  })
}

onMounted(() => guard(refresh))
</script>

<template>
  <main class="stack">
    <header class="page-header">
      <h1>Gestion des accès</h1>
      <p>Pré-provisionnement des comptes, périmètre entreprises et activation/désactivation.</p>
    </header>

    <section class="card">
      <h2>Pré-provisionner un compte</h2>
      <p class="card-hint">
        Crée un compte à l'avance, par email — son titulaire pourra se connecter dès que son
        adresse email correspondra à un compte existant ici (aucune connexion n'est acceptée pour
        un email inconnu, sauf le tout premier compte du routeur).
      </p>
      <form @submit.prevent="submitNewUser">
        <input
          v-model="newUserEmail"
          type="email"
          required
          placeholder="email@exemple.com"
          data-testid="new-user-email-input"
        />
        <input v-model="newUserName" type="text" placeholder="Nom (optionnel)" data-testid="new-user-name-input" />
        <button type="submit" class="btn-secondary" data-testid="new-user-submit-button">Ajouter</button>
      </form>
      <p v-if="createError" role="alert">{{ createError }}</p>
    </section>

    <p v-if="error" role="alert">{{ error }}</p>

    <section class="card">
      <table data-testid="users-table">
        <thead>
          <tr>
            <th>Utilisateur</th>
            <th>Statut connexion</th>
            <th>Rôle</th>
            <th>Périmètre entreprises</th>
            <th>Actif</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id" :data-testid="`user-row-${user.id}`">
            <td>{{ user.name ?? '(jamais connecté)' }} ({{ user.email }})</td>
            <td :data-testid="`user-login-status-${user.id}`">
              <span class="badge" :class="user.has_logged_in ? 'badge-success' : 'badge-warning'">
                {{
                  user.has_logged_in
                    ? `Connecté le ${formatDateTimeFr(user.last_login_at)}`
                    : 'En attente de première connexion'
                }}
              </span>
            </td>
            <td>
              <select v-model="editedRole[user.id]" :data-testid="`user-role-select-${user.id}`">
                <option value="user">Utilisateur restreint</option>
                <option value="admin">Administrateur</option>
              </select>
            </td>
            <td>
              <span v-if="editedRole[user.id] === 'admin'" :data-testid="`user-companies-all-${user.id}`">
                Toutes les entreprises
              </span>
              <div v-else class="cluster">
                <label v-for="company in companies" :key="company.id">
                  <input
                    type="checkbox"
                    :checked="editedCompanyIds[user.id]?.has(company.id)"
                    :data-testid="`user-company-checkbox-${user.id}-${company.id}`"
                    @change="toggleCompany(user.id, company.id)"
                  />
                  {{ company.name }}
                </label>
              </div>
            </td>
            <td>
              <input
                type="checkbox"
                v-model="editedIsActive[user.id]"
                :data-testid="`user-active-checkbox-${user.id}`"
              />
            </td>
            <td>
              <button
                type="button"
                class="btn-secondary btn-sm"
                :data-testid="`user-save-button-${user.id}`"
                @click="saveAccess(user.id)"
              >
                Enregistrer
              </button>
            </td>
          </tr>
          <tr v-if="users.length === 0">
            <td colspan="6" class="entity-list-empty">Aucun utilisateur pré-provisionné.</td>
          </tr>
        </tbody>
      </table>
    </section>
  </main>
</template>
