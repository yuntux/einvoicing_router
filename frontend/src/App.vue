<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { authStatus, ensureAuthStatus, loginUrl, logout } from './api/auth'
import { formatDateTimeFr } from './utils/date'

const route = useRoute()

const navItems = [
  { to: '/invoices', label: 'Factures', icon: 'invoice', adminOnly: false },
  { to: '/routing-rules', label: 'Règles de routage', icon: 'route', adminOnly: false },
  { to: '/failed-routings', label: 'Échecs de routage', icon: 'alert', adminOnly: false },
  { to: '/directory', label: 'Annuaires', icon: 'directory', adminOnly: false },
] as const

// Regroupées sous "Paramétrage" (toutes admin-only, § 5.1) plutôt qu'au premier
// niveau du menu.
const settingsSubItems = [
  { to: '/companies', label: 'Entreprises' },
  { to: '/target-applications', label: 'Applications cibles' },
  { to: '/settings', label: 'Configuration' },
  { to: '/users', label: 'Gestion des accès' },
] as const

const tracesSubItems = [
  { to: '/traces/flow-traces', label: 'Traces techniques' },
  { to: '/traces/technical-logs', label: 'Journal des traitements' },
  { to: '/traces/audit-logs', label: "Journal d'audit" },
] as const

// § 5.1 : les pages Entreprises, Applications cibles, Configuration, Gestion des
// accès et Traces & journaux (3 sous-pages) sont réservées aux admins — masquées
// pour un utilisateur restreint plutôt que visibles avec un 403 au clic. Hors
// authentification (`oidc_mode === 'disabled'`) : aucune notion de rôle, tout reste
// visible (comportement des lots 0-6 inchangé, cf. `require_admin`).
const isAdmin = computed(
  () => !authStatus.value || authStatus.value.oidc_mode === 'disabled' || authStatus.value.user?.role === 'admin',
)
const visibleNavItems = computed(() => navItems.filter((item) => !item.adminOnly || isAdmin.value))

const isInSettingsGroup = (path: string) => settingsSubItems.some((item) => path.startsWith(item.to))

const tracesOpen = ref(route.path.startsWith('/traces'))
const settingsOpen = ref(isInSettingsGroup(route.path))
watch(
  () => route.path,
  (path) => {
    if (path.startsWith('/traces')) tracesOpen.value = true
    if (isInSettingsGroup(path)) settingsOpen.value = true
  },
)

const showShell = computed(() => !route.meta.public)

async function doLogout() {
  await logout()
  await ensureAuthStatus()
}

onMounted(ensureAuthStatus)
</script>

<template>
  <div v-if="showShell" class="app-shell">
    <aside class="sidebar">
      <div class="sidebar-brand">
        <span class="sidebar-brand-mark">R</span>
        <span class="sidebar-brand-name">einvoicing Router</span>
      </div>

      <nav class="sidebar-nav">
        <RouterLink v-for="item in visibleNavItems" :key="item.to" :to="item.to" class="nav-link">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path v-if="item.icon === 'invoice'" d="M7 3h8l4 4v14H7z" />
            <path v-if="item.icon === 'invoice'" d="M10 9h6M10 13h6M10 17h4" />
            <path v-if="item.icon === 'route'" d="M5 19c3 0 3-14 6-14s3 14 6 14" />
            <circle v-if="item.icon === 'route'" cx="5" cy="19" r="1.5" />
            <circle v-if="item.icon === 'route'" cx="17" cy="19" r="1.5" />
            <path v-if="item.icon === 'alert'" d="M12 3 2 20h20z" />
            <path v-if="item.icon === 'alert'" d="M12 10v4M12 17h.01" />
            <path v-if="item.icon === 'directory'" d="M6 3h11a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" />
            <path v-if="item.icon === 'directory'" d="M8 3v18M12 8h4M12 12h4" />
          </svg>
          {{ item.label }}
        </RouterLink>

        <template v-if="isAdmin">
          <button
            type="button"
            class="nav-link nav-group-toggle"
            :class="{ 'router-link-active': isInSettingsGroup(route.path) }"
            data-testid="nav-settings-toggle"
            @click="settingsOpen = !settingsOpen"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path
                d="M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 2h-4l-.5 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 22h4l.5-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2Z"
              />
            </svg>
            Paramétrage
            <svg class="nav-group-chevron" :class="{ 'nav-group-chevron-open': settingsOpen }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 6l6 6-6 6" />
            </svg>
          </button>
          <div v-if="settingsOpen" class="nav-subgroup">
            <RouterLink
              v-for="item in settingsSubItems"
              :key="item.to"
              :to="item.to"
              class="nav-link nav-sublink"
            >
              {{ item.label }}
            </RouterLink>
          </div>

          <button
            type="button"
            class="nav-link nav-group-toggle"
            :class="{ 'router-link-active': route.path.startsWith('/traces') }"
            data-testid="nav-traces-toggle"
            @click="tracesOpen = !tracesOpen"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 5h16M4 12h16M4 19h10" />
            </svg>
            Traces &amp; journaux
            <svg class="nav-group-chevron" :class="{ 'nav-group-chevron-open': tracesOpen }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 6l6 6-6 6" />
            </svg>
          </button>
          <div v-if="tracesOpen" class="nav-subgroup">
            <RouterLink
              v-for="item in tracesSubItems"
              :key="item.to"
              :to="item.to"
              class="nav-link nav-sublink"
            >
              {{ item.label }}
            </RouterLink>
          </div>
        </template>
      </nav>

      <div v-if="authStatus && authStatus.oidc_mode !== 'disabled'" class="sidebar-footer" data-testid="auth-status">
        <template v-if="authStatus.authenticated">
          <div class="sidebar-user">
            <strong>{{ authStatus.user?.name }}</strong>
            <button
              type="button"
              class="sidebar-icon-button"
              title="Se déconnecter"
              aria-label="Se déconnecter"
              data-testid="logout-button"
              @click="doLogout"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <path d="M16 17l5-5-5-5" />
                <path d="M21 12H9" />
              </svg>
            </button>
          </div>
          <div
            v-if="authStatus.user?.previous_login_at"
            class="sidebar-last-login"
            data-testid="sidebar-last-login"
          >
            Dernière connexion : {{ formatDateTimeFr(authStatus.user.previous_login_at) }}
          </div>
        </template>
        <template v-else>
          <a :href="loginUrl(route.fullPath)" data-testid="login-link">Se connecter</a>
        </template>
      </div>
    </aside>

    <div class="main-area">
      <RouterView />
    </div>
  </div>

  <div v-else class="standalone-shell">
    <RouterView />
  </div>
</template>
