import { computed, ref } from 'vue'
import { apiFetch, loginUrl } from './http'

export { loginUrl }

export interface CurrentUser {
  id: number
  email: string
  name: string
  role: string
  company_ids: number[]
  // Avant-dernière connexion (pas la connexion en cours) — cf. schemas/auth.py.
  previous_login_at: string | null
}

export interface CurrentUserStatus {
  oidc_mode: string
  authenticated: boolean
  user: CurrentUser | null
}

export function getCurrentUserStatus(): Promise<CurrentUserStatus> {
  return apiFetch('/api/ihm/auth/me', {}, 'Failed to get current user')
}

export async function logout(): Promise<void> {
  await apiFetch('/api/ihm/auth/logout', { method: 'POST' }, 'Failed to logout')
  authStatus.value = null
}

// État d'authentification partagé (App.vue pour l'affichage, router.ts pour la garde
// de navigation) — un seul appel à /auth/me par chargement de page plutôt qu'un par
// consommateur.
export const authStatus = ref<CurrentUserStatus | null>(null)
let pendingFetch: Promise<CurrentUserStatus> | null = null

export async function ensureAuthStatus(): Promise<CurrentUserStatus> {
  if (authStatus.value) return authStatus.value
  if (!pendingFetch) {
    pendingFetch = getCurrentUserStatus().finally(() => {
      pendingFetch = null
    })
  }
  authStatus.value = await pendingFetch
  return authStatus.value
}

// Rôle « lecture seule » (§ 5.1) : mêmes pages que « utilisateur restreint », mais
// aucune écriture — les vues avec des actions de modification l'utilisent pour
// masquer/désactiver ces actions (le backend les bloque de toute façon via
// `require_write`, cf. app/auth/session.py ; ce composable n'est qu'un confort IHM).
export const isReadOnly = computed(
  () => !!authStatus.value?.authenticated && authStatus.value.user?.role === 'readonly',
)
