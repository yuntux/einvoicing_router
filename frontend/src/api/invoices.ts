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
  superpdp_flow_id: string
  amount_total: number | null
  amount_excl_tax: number | null
  currency: string | null
  syntax: string | null
  processing_rule: string | null
  received_at: string
  last_download_at: string | null
  last_download_by: string | null
}

export interface InvoiceRouting {
  id: number
  target_application_id: number
  transfer_status: string
  attempt_count: number
  next_attempt_at: string | null
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
  routings: InvoiceRouting[]
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

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function listInvoices(filters: InvoiceFilters = {}): Promise<Invoice[]> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const response = await fetch(`${API_BASE}/api/ihm/invoices?${params.toString()}`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to list invoices: ${response.status}`)
  return response.json()
}

export async function getInvoice(id: number): Promise<InvoiceDetail> {
  const response = await fetch(`${API_BASE}/api/ihm/invoices/${id}`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to get invoice: ${response.status}`)
  return response.json()
}

export function invoiceDownloadUrl(id: number): string {
  return `${API_BASE}/api/ihm/invoices/${id}/download`
}

export function afnorFlowDownloadUrl(invoiceId: number, flowId: number): string {
  return `${API_BASE}/api/ihm/invoices/${invoiceId}/afnor-flows/${flowId}/download`
}
