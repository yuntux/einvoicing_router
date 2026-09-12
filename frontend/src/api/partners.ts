import { apiFetch } from './http'

export interface Partner {
  id: number
  siren: string
  siret: string | null
  name: string
}

export interface PartnerCreate {
  siren: string
  siret?: string | null
  name: string
}

export function listPartners(): Promise<Partner[]> {
  return apiFetch('/api/ihm/partners', {}, 'Failed to list partners')
}

export function createPartner(payload: PartnerCreate): Promise<Partner> {
  return apiFetch('/api/ihm/partners', { method: 'POST', json: payload }, 'Failed to create partner')
}
