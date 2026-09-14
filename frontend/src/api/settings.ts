import { apiFetch } from './http'

export interface RouterSettings {
  technical_log_retention_days: number
  smtp_host: string | null
  smtp_port: number
  smtp_username: string | null
  smtp_use_tls: boolean
  smtp_from_address: string | null
  ihm_ip_allowlist: string | null
  afnor_api_ip_allowlist: string | null
}

export interface RouterSettingsUpdate {
  technical_log_retention_days?: number | null
  smtp_host?: string | null
  smtp_port?: number | null
  smtp_username?: string | null
  smtp_password?: string | null
  smtp_use_tls?: boolean | null
  smtp_from_address?: string | null
  ihm_ip_allowlist?: string | null
  afnor_api_ip_allowlist?: string | null
}

export interface SmtpOverrides {
  smtp_host?: string | null
  smtp_port?: number | null
  smtp_username?: string | null
  smtp_password?: string | null
  smtp_use_tls?: boolean | null
  smtp_from_address?: string | null
}

export interface SmtpTestResult {
  ok: boolean
  error: string | null
}

export interface BillingManagerContact {
  id: number
  email: string
}

export function getRouterSettings(): Promise<RouterSettings> {
  return apiFetch('/api/ihm/settings', {}, 'Failed to get router settings')
}

export function updateRouterSettings(payload: RouterSettingsUpdate): Promise<RouterSettings> {
  return apiFetch('/api/ihm/settings', { method: 'PUT', json: payload }, 'Failed to update router settings')
}

/** Aller-retour réseau réel (connexion + STARTTLS + authentification), sans envoi —
 * un champ omis retombe sur la valeur déjà enregistrée (utile pour tester avant
 * d'enregistrer, notamment le mot de passe, jamais renvoyé par `getRouterSettings`). */
export function testSmtpConnection(overrides: SmtpOverrides): Promise<SmtpTestResult> {
  return apiFetch(
    '/api/ihm/settings/smtp/test-connection',
    { method: 'POST', json: overrides },
    'Failed to test SMTP connection',
  )
}

export function sendSmtpTestEmail(overrides: SmtpOverrides, toAddress: string): Promise<SmtpTestResult> {
  return apiFetch(
    '/api/ihm/settings/smtp/send-test-email',
    { method: 'POST', json: { ...overrides, to_address: toAddress } },
    'Failed to send SMTP test email',
  )
}

export function listBillingManagerContacts(): Promise<BillingManagerContact[]> {
  return apiFetch(
    '/api/ihm/settings/billing-manager-contacts',
    {},
    'Failed to list billing manager contacts',
  )
}

export function createBillingManagerContact(email: string): Promise<BillingManagerContact> {
  return apiFetch(
    '/api/ihm/settings/billing-manager-contacts',
    { method: 'POST', json: { email } },
    'Failed to create billing manager contact',
  )
}

export function deleteBillingManagerContact(id: number): Promise<void> {
  return apiFetch(
    `/api/ihm/settings/billing-manager-contacts/${id}`,
    { method: 'DELETE' },
    'Failed to delete billing manager contact',
  )
}
