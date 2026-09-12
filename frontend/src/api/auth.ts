import { ref } from 'vue'
import { API_BASE, apiFetch } from './http'

export interface CurrentUser {
  id: number
  email: string
  name: string
  role: string
  company_ids: number[]
}

export interface CurrentUserStatus {
  oidc_mode: string
  authenticated: boolean
  user: CurrentUser | null
}

export function getCurrentUserStatus(): Promise<CurrentUserStatus> {
  return apiFetch('/api/ihm/auth/me', {}, 'Failed to get current user')
}

export function loginUrl(next?: string): string {
  const base = `${API_BASE}/api/ihm/auth/login`
  return next ? `${base}?next=${encodeURIComponent(next)}` : base
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
