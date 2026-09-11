export interface SuperPDPCredentialsStatus {
  configured: boolean
  client_id: string | null
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function getSuperPDPCredentialsStatus(
  companyId: number,
): Promise<SuperPDPCredentialsStatus> {
  const response = await fetch(`${API_BASE}/api/ihm/companies/${companyId}/superpdp-credentials`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to get SuperPDP credentials status: ${response.status}`)
  return response.json()
}

export async function setSuperPDPCredentials(
  companyId: number,
  clientId: string,
  clientSecret: string,
): Promise<SuperPDPCredentialsStatus> {
  const response = await fetch(`${API_BASE}/api/ihm/companies/${companyId}/superpdp-credentials`, {
    credentials: 'include',
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }),
  })
  if (!response.ok) throw new Error(`Failed to set SuperPDP credentials: ${response.status}`)
  return response.json()
}
