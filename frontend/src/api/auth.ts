import { ref } from 'vue'

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

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function getCurrentUserStatus(): Promise<CurrentUserStatus> {
  const response = await fetch(`${API_BASE}/api/ihm/auth/me`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to get current user: ${response.status}`)
  return response.json()
}

export function loginUrl(next?: string): string {
  const base = `${API_BASE}/api/ihm/auth/login`
  return next ? `${base}?next=${encodeURIComponent(next)}` : base
}

export async function logout(): Promise<void> {
  const response = await fetch(`${API_BASE}/api/ihm/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to logout: ${response.status}`)
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
