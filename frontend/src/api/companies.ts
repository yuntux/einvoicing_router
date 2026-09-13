import { apiFetch } from './http'

export interface Company {
  id: number
  siren: string
  name: string
  certified_platform_directory_id: string | null
}

export interface CompanyCreate {
  siren: string
  name: string
}

export interface CompanyUpdate {
  certified_platform_directory_id: string | null
}

/** Référence minimale (id + nom), sans SIREN — accessible à tout utilisateur
 * authentifié, contrairement à `listCompanies` (page Entreprises, admin uniquement,
 * § 5.1). À utiliser pour un affichage croisé (ex. Règles de routage), jamais pour
 * la page Entreprises elle-même. */
export interface CompanyLookup {
  id: number
  name: string
}

export function listCompanies(): Promise<Company[]> {
  return apiFetch('/api/ihm/companies', {}, 'Failed to list companies')
}

export function listCompanyLookups(): Promise<CompanyLookup[]> {
  return apiFetch('/api/ihm/companies/lookup', {}, 'Failed to list companies')
}

export function createCompany(payload: CompanyCreate): Promise<Company> {
  return apiFetch('/api/ihm/companies', { method: 'POST', json: payload }, 'Failed to create company')
}

export function updateCompany(companyId: number, payload: CompanyUpdate): Promise<Company> {
  return apiFetch(
    `/api/ihm/companies/${companyId}`,
    { method: 'PUT', json: payload },
    'Failed to update company',
  )
}

export function runPollingCycle(): Promise<void> {
  return apiFetch('/api/ihm/companies/run-polling-cycle', { method: 'POST' }, 'Failed to run polling cycle')
}
