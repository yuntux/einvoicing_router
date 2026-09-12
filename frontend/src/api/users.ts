import { ApiError, apiFetch } from './http'

export interface AppUser {
  id: number
  email: string
  name: string | null
  role: string
  company_ids: number[]
  is_active: boolean
  has_logged_in: boolean
  last_login_at: string | null
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

export function listUsers(): Promise<AppUser[]> {
  return apiFetch('/api/ihm/users', {}, 'Failed to list users')
}

export async function createUser(payload: UserCreate): Promise<AppUser> {
  try {
    return await apiFetch('/api/ihm/users', { method: 'POST', json: payload }, 'Failed to create user')
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      throw new Error('Un compte existe déjà pour cet email.')
    }
    throw err
  }
}

export function updateUserAccess(userId: number, payload: UserAccessUpdate): Promise<AppUser> {
  return apiFetch(
    `/api/ihm/users/${userId}/access`,
    { method: 'PUT', json: payload },
    'Failed to update user access',
  )
}
