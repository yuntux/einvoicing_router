export interface RoutingRule {
  id: number
  partner_directory_id: number
  target_application_id: number
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function listRoutingRules(): Promise<RoutingRule[]> {
  const response = await fetch(`${API_BASE}/api/ihm/routing-rules`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to list routing rules: ${response.status}`)
  return response.json()
}

export async function setRoutingRuleActive(
  partnerDirectoryId: number,
  targetApplicationId: number,
  active: boolean,
): Promise<RoutingRule | null> {
  const response = await fetch(
    `${API_BASE}/api/ihm/routing-rules/${partnerDirectoryId}/${targetApplicationId}`,
    {
      credentials: 'include',
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active }),
    },
  )
  if (!response.ok) throw new Error(`Failed to update routing rule: ${response.status}`)
  return response.json()
}
