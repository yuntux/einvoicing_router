import { apiFetch } from './http'

export interface SuperPDPCredentialsStatus {
  configured: boolean
  client_id: string | null
  platform: string | null
}

export interface AfnorPlatform {
  key: string
  label: string
}

export function listAfnorPlatforms(): Promise<AfnorPlatform[]> {
  return apiFetch('/api/ihm/companies/afnor-platforms', {}, 'Failed to list AFNOR platforms')
}

export function getSuperPDPCredentialsStatus(companyId: number): Promise<SuperPDPCredentialsStatus> {
  return apiFetch(
    `/api/ihm/companies/${companyId}/superpdp-credentials`,
    {},
    'Failed to get SuperPDP credentials status',
  )
}

export function setSuperPDPCredentials(
  companyId: number,
  clientId: string,
  clientSecret: string,
  platform: string | null,
): Promise<SuperPDPCredentialsStatus> {
  return apiFetch(
    `/api/ihm/companies/${companyId}/superpdp-credentials`,
    {
      method: 'PUT',
      json: { client_id: clientId, client_secret: clientSecret, platform: platform || null },
    },
    'Failed to set SuperPDP credentials',
  )
}
