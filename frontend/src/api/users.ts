export interface AppUser {
  id: number
  email: string
  name: string | null
  role: string
  company_ids: number[]
  is_active: boolean
  has_logged_in: boolean
}

export interface UserCreate {
  email: string
  name?: string
}

export interface UserAccessUpdate {
  role: string
  company_ids: number[]
  is_active: boolean
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function listUsers(): Promise<AppUser[]> {
  const response = await fetch(`${API_BASE}/api/ihm/users`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to list users: ${response.status}`)
  return response.json()
}

export async function createUser(payload: UserCreate): Promise<AppUser> {
  const response = await fetch(`${API_BASE}/api/ihm/users`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    if (response.status === 409) throw new Error('Un compte existe déjà pour cet email.')
    throw new Error(`Failed to create user: ${response.status}`)
  }
  return response.json()
}

export async function updateUserAccess(
  userId: number,
  payload: UserAccessUpdate,
): Promise<AppUser> {
  const response = await fetch(`${API_BASE}/api/ihm/users/${userId}/access`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(`Failed to update user access: ${response.status}`)
  return response.json()
}
