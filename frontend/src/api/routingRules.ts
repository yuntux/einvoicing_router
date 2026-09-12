import { apiFetch } from './http'

export interface RoutingRule {
  id: number
  partner_directory_id: number
  target_application_id: number
}

export function listRoutingRules(): Promise<RoutingRule[]> {
  return apiFetch('/api/ihm/routing-rules', {}, 'Failed to list routing rules')
}

export function setRoutingRuleActive(
  partnerDirectoryId: number,
  targetApplicationId: number,
  active: boolean,
  rerouteExisting = true,
): Promise<RoutingRule | null> {
  return apiFetch(
    `/api/ihm/routing-rules/${partnerDirectoryId}/${targetApplicationId}`,
    { method: 'PUT', json: { active, reroute_existing: rerouteExisting } },
    'Failed to update routing rule',
  )
}
