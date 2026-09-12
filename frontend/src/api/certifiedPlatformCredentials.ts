import { apiFetch } from './http'

export interface CertifiedPlatformCredentialsStatus {
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

export function getCertifiedPlatformCredentialsStatus(companyId: number): Promise<CertifiedPlatformCredentialsStatus> {
  return apiFetch(
    `/api/ihm/companies/${companyId}/certified-platform-credentials`,
    {},
    'Failed to get certified platform credentials status',
  )
}

export function setCertifiedPlatformCredentials(
  companyId: number,
  clientId: string,
  clientSecret: string,
  platform: string | null,
): Promise<CertifiedPlatformCredentialsStatus> {
  return apiFetch(
    `/api/ihm/companies/${companyId}/certified-platform-credentials`,
    {
      method: 'PUT',
      json: { client_id: clientId, client_secret: clientSecret, platform: platform || null },
    },
    'Failed to set certified platform credentials',
  )
}
