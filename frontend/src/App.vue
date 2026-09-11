<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { authStatus, ensureAuthStatus, loginUrl, logout } from './api/auth'

const route = useRoute()

async function doLogout() {
  await logout()
  await ensureAuthStatus()
}

onMounted(ensureAuthStatus)
</script>

<template>
  <nav>
    <RouterLink to="/invoices">Factures</RouterLink> |
    <RouterLink to="/companies">Entreprises</RouterLink> |
    <RouterLink to="/target-applications">Applications cibles</RouterLink> |
    <RouterLink to="/routing-rules">Règles de routage</RouterLink> |
    <RouterLink to="/failed-routings">Échecs de routage</RouterLink> |
    <RouterLink to="/settings">Configuration</RouterLink> |
    <RouterLink to="/users">Gestion des accès</RouterLink>

    <span v-if="authStatus && authStatus.oidc_mode !== 'disabled'" data-testid="auth-status">
      <template v-if="authStatus.authenticated">
        | Connecté : {{ authStatus.user?.name }}
        <button type="button" data-testid="logout-button" @click="doLogout">Se déconnecter</button>
      </template>
      <template v-else>
        | <a :href="loginUrl(route.fullPath)" data-testid="login-link">Se connecter</a>
      </template>
    </span>
  </nav>
  <RouterView />
</template>
