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
}

export interface InvoiceRouting {
  id: number
  target_application_id: number
  transfer_status: string
  attempt_count: number
  next_attempt_at: string | null
}

export interface InvoiceDetail extends Invoice {
  routings: InvoiceRouting[]
  emitter_name: string | null
  last_download_at: string | null
  last_download_by: string | null
}

export interface InvoiceFilters {
  company_id?: number
  emitter_siren?: string
  invoice_number?: string
  currency?: string
  syntax?: string
  processing_rule?: string
  invoice_date_from?: string
  invoice_date_to?: string
}

export interface SimulateInvoicePayload {
  company_id: number
  emitter_siren: string
  emitter_siret?: string | null
  invoice_number: string
  invoice_date: string
  due_date?: string | null
  amount_total?: number | null
  amount_excl_tax?: number | null
  currency?: string
  syntax?: string
  processing_rule?: string
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

export async function simulateInvoiceReception(payload: SimulateInvoicePayload): Promise<Invoice> {
  const response = await fetch(`${API_BASE}/api/ihm/invoices/simulate`, {
    credentials: 'include',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(`Failed to simulate invoice: ${response.status}`)
  return response.json()
}
