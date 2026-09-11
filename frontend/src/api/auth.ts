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

export function loginUrl(): string {
  return `${API_BASE}/api/ihm/auth/login`
}

export async function logout(): Promise<void> {
  const response = await fetch(`${API_BASE}/api/ihm/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to logout: ${response.status}`)
}
