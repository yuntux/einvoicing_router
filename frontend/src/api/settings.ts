export interface RouterSettings {
  technical_log_retention_days: number
  smtp_host: string | null
  smtp_port: number
  smtp_username: string | null
  smtp_use_tls: boolean
  smtp_from_address: string | null
}

export interface RouterSettingsUpdate {
  technical_log_retention_days?: number | null
  smtp_host?: string | null
  smtp_port?: number | null
  smtp_username?: string | null
  smtp_password?: string | null
  smtp_use_tls?: boolean | null
  smtp_from_address?: string | null
}

export interface BillingManagerContact {
  id: number
  email: string
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function getRouterSettings(): Promise<RouterSettings> {
  const response = await fetch(`${API_BASE}/api/ihm/settings`)
  if (!response.ok) throw new Error(`Failed to get router settings: ${response.status}`)
  return response.json()
}

export async function updateRouterSettings(
  payload: RouterSettingsUpdate,
): Promise<RouterSettings> {
  const response = await fetch(`${API_BASE}/api/ihm/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(`Failed to update router settings: ${response.status}`)
  return response.json()
}

export async function listBillingManagerContacts(): Promise<BillingManagerContact[]> {
  const response = await fetch(`${API_BASE}/api/ihm/settings/billing-manager-contacts`)
  if (!response.ok) throw new Error(`Failed to list billing manager contacts: ${response.status}`)
  return response.json()
}

export async function createBillingManagerContact(email: string): Promise<BillingManagerContact> {
  const response = await fetch(`${API_BASE}/api/ihm/settings/billing-manager-contacts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  if (!response.ok) throw new Error(`Failed to create billing manager contact: ${response.status}`)
  return response.json()
}

export async function deleteBillingManagerContact(id: number): Promise<void> {
  const response = await fetch(`${API_BASE}/api/ihm/settings/billing-manager-contacts/${id}`, {
    method: 'DELETE',
  })
  if (!response.ok) throw new Error(`Failed to delete billing manager contact: ${response.status}`)
}
