export type RoutingMethod = 'mail' | 'afnor_api'

export interface TargetApplication {
  id: number
  name: string
  routing_method: RoutingMethod
  company_id: number | null
  parameters: Record<string, unknown>
}

export interface TargetApplicationCreate {
  name: string
  routing_method: RoutingMethod
  company_id?: number | null
  parameters: Record<string, unknown>
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function listTargetApplications(): Promise<TargetApplication[]> {
  const response = await fetch(`${API_BASE}/api/ihm/target-applications`)
  if (!response.ok) throw new Error(`Failed to list target applications: ${response.status}`)
  return response.json()
}

export async function createTargetApplication(
  payload: TargetApplicationCreate,
): Promise<TargetApplication> {
  const response = await fetch(`${API_BASE}/api/ihm/target-applications`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(`Failed to create target application: ${response.status}`)
  return response.json()
}
