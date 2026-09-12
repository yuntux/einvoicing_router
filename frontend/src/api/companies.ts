import { apiFetch } from './http'

export interface Company {
  id: number
  siren: string
  name: string
}

export interface CompanyCreate {
  siren: string
  name: string
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
