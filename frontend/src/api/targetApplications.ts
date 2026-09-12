export type RoutingMethod = 'mail' | 'afnor_api'

export interface TargetApplicationOAuth {
  app_type: 'confidential' | 'public'
  redirect_urls: string | null
  preferred_conversion_format: string | null
  webhook_url: string | null
}

export interface TargetApplication {
  id: number
  name: string
  routing_method: RoutingMethod
  company_id: number
  oauth_application_id: number | null
  oauth_application: TargetApplicationOAuth | null
  parameters: Record<string, unknown>
  is_active: boolean
}

export interface TargetApplicationUpdate {
  name: string
  parameters: Record<string, unknown>
}

export interface TargetApplicationCreated extends TargetApplication {
  oauth_client_id: string | null
  oauth_client_secret: string | null
}

export interface TargetApplicationCreate {
  name: string
  routing_method: RoutingMethod
  company_id: number
  parameters: Record<string, unknown>
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function listTargetApplications(): Promise<TargetApplication[]> {
  const response = await fetch(`${API_BASE}/api/ihm/target-applications`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to list target applications: ${response.status}`)
  return response.json()
}

export async function createTargetApplication(
  payload: TargetApplicationCreate,
): Promise<TargetApplicationCreated> {
  const response = await fetch(`${API_BASE}/api/ihm/target-applications`, {
    credentials: 'include',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(`Failed to create target application: ${response.status}`)
  return response.json()
}

export async function updateTargetApplication(
  id: number,
  payload: TargetApplicationUpdate,
): Promise<TargetApplication> {
  const response = await fetch(`${API_BASE}/api/ihm/target-applications/${id}`, {
    credentials: 'include',
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(`Failed to update target application: ${response.status}`)
  return response.json()
}

export async function setTargetApplicationActive(
  id: number,
  isActive: boolean,
): Promise<TargetApplication> {
  const response = await fetch(`${API_BASE}/api/ihm/target-applications/${id}/status`, {
    credentials: 'include',
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_active: isActive }),
  })
  if (!response.ok) throw new Error(`Failed to update target application status: ${response.status}`)
  return response.json()
}
