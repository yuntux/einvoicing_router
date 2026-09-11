export interface Company {
  id: number
  siren: string
  name: string
}

export interface CompanyCreate {
  siren: string
  name: string
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function listCompanies(): Promise<Company[]> {
  const response = await fetch(`${API_BASE}/api/ihm/companies`)
  if (!response.ok) throw new Error(`Failed to list companies: ${response.status}`)
  return response.json()
}

export async function createCompany(payload: CompanyCreate): Promise<Company> {
  const response = await fetch(`${API_BASE}/api/ihm/companies`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(`Failed to create company: ${response.status}`)
  return response.json()
}
