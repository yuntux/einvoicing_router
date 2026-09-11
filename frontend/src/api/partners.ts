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

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function listPartners(): Promise<Partner[]> {
  const response = await fetch(`${API_BASE}/api/ihm/partners`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to list partners: ${response.status}`)
  return response.json()
}

export async function createPartner(payload: PartnerCreate): Promise<Partner> {
  const response = await fetch(`${API_BASE}/api/ihm/partners`, {
    credentials: 'include',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(`Failed to create partner: ${response.status}`)
  return response.json()
}
