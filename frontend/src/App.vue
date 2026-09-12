<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { authStatus, ensureAuthStatus, loginUrl, logout } from './api/auth'

const route = useRoute()

const navItems = [
  { to: '/invoices', label: 'Factures', icon: 'invoice' },
  { to: '/companies', label: 'Entreprises', icon: 'building' },
  { to: '/target-applications', label: 'Applications cibles', icon: 'target' },
  { to: '/routing-rules', label: 'Règles de routage', icon: 'route' },
  { to: '/failed-routings', label: 'Échecs de routage', icon: 'alert' },
  { to: '/settings', label: 'Configuration', icon: 'gear' },
  { to: '/users', label: 'Gestion des accès', icon: 'users' },
] as const

const tracesSubItems = [
  { to: '/traces/flow-traces', label: 'Traces techniques' },
  { to: '/traces/technical-logs', label: 'Journal des traitements' },
  { to: '/traces/audit-logs', label: "Journal d'audit" },
] as const

const tracesOpen = ref(route.path.startsWith('/traces'))
watch(
  () => route.path,
  (path) => {
    if (path.startsWith('/traces')) tracesOpen.value = true
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
        <span class="sidebar-brand-name">Routeur de factures</span>
      </div>

      <nav class="sidebar-nav">
        <RouterLink v-for="item in navItems" :key="item.to" :to="item.to" class="nav-link">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path v-if="item.icon === 'invoice'" d="M7 3h8l4 4v14H7z" />
            <path v-if="item.icon === 'invoice'" d="M10 9h6M10 13h6M10 17h4" />
            <path v-if="item.icon === 'building'" d="M4 21V6l8-3 8 3v15" />
            <path v-if="item.icon === 'building'" d="M9 21v-6h6v6M9 10h.01M15 10h.01M9 14h.01M15 14h.01" />
            <circle v-if="item.icon === 'target'" cx="12" cy="12" r="8" />
            <circle v-if="item.icon === 'target'" cx="12" cy="12" r="3" />
            <path v-if="item.icon === 'route'" d="M5 19c3 0 3-14 6-14s3 14 6 14" />
            <circle v-if="item.icon === 'route'" cx="5" cy="19" r="1.5" />
            <circle v-if="item.icon === 'route'" cx="17" cy="19" r="1.5" />
            <path v-if="item.icon === 'alert'" d="M12 3 2 20h20z" />
            <path v-if="item.icon === 'alert'" d="M12 10v4M12 17h.01" />
            <circle v-if="item.icon === 'gear'" cx="12" cy="12" r="3" />
            <path
              v-if="item.icon === 'gear'"
              d="M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 2h-4l-.5 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 22h4l.5-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2Z"
            />
            <circle v-if="item.icon === 'users'" cx="9" cy="8" r="3.2" />
            <path v-if="item.icon === 'users'" d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" />
            <circle v-if="item.icon === 'users'" cx="17.5" cy="9" r="2.6" />
            <path v-if="item.icon === 'users'" d="M15.5 20c.2-2.6 1.6-4.6 3.6-5.4 1.8.6 3 2.1 3 5.4" />
          </svg>
          {{ item.label }}
        </RouterLink>

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
