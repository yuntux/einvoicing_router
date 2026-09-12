export interface RoutingRule {
  id: number
  partner_directory_id: number
  target_application_id: number
  start_date: string
  end_date: string | null
  active: boolean
}

export interface RoutingRuleCreate {
  partner_directory_id: number
  target_application_id: number
  start_date: string
  end_date?: string | null
  active?: boolean
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function listRoutingRules(): Promise<RoutingRule[]> {
  const response = await fetch(`${API_BASE}/api/ihm/routing-rules`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to list routing rules: ${response.status}`)
  return response.json()
}

export async function createRoutingRule(payload: RoutingRuleCreate): Promise<RoutingRule> {
  const response = await fetch(`${API_BASE}/api/ihm/routing-rules`, {
    credentials: 'include',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(`Failed to create routing rule: ${response.status}`)
  return response.json()
}

export async function upsertRoutingRule(
  partnerDirectoryId: number,
  targetApplicationId: number,
  payload: { start_date: string; end_date: string | null },
): Promise<RoutingRule> {
  const response = await fetch(
    `${API_BASE}/api/ihm/routing-rules/${partnerDirectoryId}/${targetApplicationId}`,
    {
      credentials: 'include',
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )
  if (!response.ok) throw new Error(`Failed to save routing rule: ${response.status}`)
  return response.json()
}
