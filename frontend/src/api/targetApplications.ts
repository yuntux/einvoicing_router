import { apiFetch } from './http'

export type RoutingMethod = 'mail' | 'afnor_api'

export interface TargetApplicationOAuth {
  client_id: string
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

/** Référence minimale (id + nom + entreprise), sans paramètres ni infos OAuth —
 * accessible à tout utilisateur authentifié, contrairement à
 * `listTargetApplications` (page Applications cibles, admin uniquement, § 5.1). À
 * utiliser pour un affichage croisé (ex. Règles de routage), jamais pour la page
 * Applications cibles elle-même. */
export interface TargetApplicationLookup {
  id: number
  name: string
  company_id: number
}

export function listTargetApplications(): Promise<TargetApplication[]> {
  return apiFetch('/api/ihm/target-applications', {}, 'Failed to list target applications')
}

export function listTargetApplicationLookups(): Promise<TargetApplicationLookup[]> {
  return apiFetch('/api/ihm/target-applications/lookup', {}, 'Failed to list target applications')
}

export function createTargetApplication(
  payload: TargetApplicationCreate,
): Promise<TargetApplicationCreated> {
  return apiFetch(
    '/api/ihm/target-applications',
    { method: 'POST', json: payload },
    'Failed to create target application',
  )
}

export function updateTargetApplication(
  id: number,
  payload: TargetApplicationUpdate,
): Promise<TargetApplication> {
  return apiFetch(
    `/api/ihm/target-applications/${id}`,
    { method: 'PUT', json: payload },
    'Failed to update target application',
  )
}

export function setTargetApplicationActive(id: number, isActive: boolean): Promise<TargetApplication> {
  return apiFetch(
    `/api/ihm/target-applications/${id}/status`,
    { method: 'PUT', json: { is_active: isActive } },
    'Failed to update target application status',
  )
}
