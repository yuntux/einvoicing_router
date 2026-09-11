export interface AppUser {
  id: number
  email: string
  name: string
  role: string
  company_ids: number[]
}

export interface UserAccessUpdate {
  role: string
  company_ids: number[]
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function listUsers(): Promise<AppUser[]> {
  const response = await fetch(`${API_BASE}/api/ihm/users`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to list users: ${response.status}`)
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
