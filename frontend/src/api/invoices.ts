import { API_BASE, apiFetch } from './http'

export interface InvoiceRouting {
  id: number
  target_application_id: number
  transfer_status: string
  attempt_count: number
  next_attempt_at: string | null
}

export interface Invoice {
  id: number
  company_id: number
  partner_directory_id: number | null
  emitter_siren: string
  emitter_siret: string | null
  invoice_number: string
  invoice_date: string
  due_date: string | null
  invoice_type: string
  lifecycle_status: string | null
  file_path: string
  certified_platform_flow_id: string
  amount_total: number | null
  amount_excl_tax: number | null
  currency: string | null
  syntax: string | null
  processing_rule: string | null
  received_at: string
  last_download_at: string | null
  last_download_by: string | null
  // Enveloppe de transport du flux AFNOR d'origine (schéma officiel "AFNOR Flow
  // Service") — distincte des champs métier ci-dessus, extraits du fichier facture.
  flow_profile: string | null
  processing_rule_source: string | null
  tracking_id: string | null
  flow_direction: string | null
  flow_type: string | null
  flow_name: string | null
  ack_status: string | null
  ack_details: string | null
  // Statut de routage par application cible (§ 4.7/§ 8.3) — un badge par
  // application de l'entreprise dans la liste des factures.
  routings: InvoiceRouting[]
}

export interface AfnorFlow {
  id: number
  flow_id: string | null
  direction: string
  flow_type: string
  syntax: string
  processing_rule: string | null
  state: string
  has_file: boolean
}

export interface InvoiceDetail extends Invoice {
  emitter_name: string | null
  last_download_at: string | null
  last_download_by: string | null
  afnor_flows: AfnorFlow[]
}

export interface InvoiceFilters {
  company_id?: number
  emitter_siren?: string
  emitter_name?: string
  invoice_number?: string
  syntax?: string
  processing_rule?: string
  invoice_date_from?: string
  invoice_date_to?: string
  amount_excl_tax_min?: number
  amount_excl_tax_max?: number
  vat_amount_min?: number
  vat_amount_max?: number
  amount_total_min?: number
  amount_total_max?: number
  downloaded?: boolean
}

export function listInvoices(filters: InvoiceFilters = {}): Promise<Invoice[]> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  return apiFetch(`/api/ihm/invoices?${params.toString()}`, {}, 'Failed to list invoices')
}

export function getInvoice(id: number): Promise<InvoiceDetail> {
  return apiFetch(`/api/ihm/invoices/${id}`, {}, 'Failed to get invoice')
}

export function invoiceDownloadUrl(id: number): string {
  return `${API_BASE}/api/ihm/invoices/${id}/download`
}

export function afnorFlowDownloadUrl(invoiceId: number, flowId: number): string {
  return `${API_BASE}/api/ihm/invoices/${invoiceId}/afnor-flows/${flowId}/download`
}
