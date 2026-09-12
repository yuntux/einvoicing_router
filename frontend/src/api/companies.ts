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

export function listCompanies(): Promise<Company[]> {
  return apiFetch('/api/ihm/companies', {}, 'Failed to list companies')
}

export function createCompany(payload: CompanyCreate): Promise<Company> {
  return apiFetch('/api/ihm/companies', { method: 'POST', json: payload }, 'Failed to create company')
}
