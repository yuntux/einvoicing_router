export interface StatusCatalogEntry {
  key: string
  label: string
  cdar_code: string
  mdt88_code: string | null
  manual_side: 'purchase' | 'sale' | null
  requires_detail: boolean
  requires_confirmation: boolean
}

export interface LifecycleCatalog {
  statuses: StatusCatalogEntry[]
  reasons: Record<string, string>
  actions: Record<string, string>
}

export interface LifecycleEventDetail {
  reason: string | null
  action: string | null
  comment: string | null
}

export interface LifecycleEventPayment {
  id: number
  amount: number
  currency: string
  payment_date: string
}

export interface LifecycleEventAttachment {
  id: number
  filename: string
  has_file: boolean
}

export interface LifecycleEvent {
  id: number
  invoice_id: number
  event_datetime: string
  status: string
  direction: string
  amount: number | null
  currency: string | null
  details: LifecycleEventDetail[]
  payments: LifecycleEventPayment[]
  attachments: LifecycleEventAttachment[]
}

export interface CreateLifecycleEventPayload {
  status: string
  reason?: string | null
  action?: string | null
  comment?: string | null
  confirmed?: boolean
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function getLifecycleCatalog(): Promise<LifecycleCatalog> {
  const response = await fetch(`${API_BASE}/api/ihm/lifecycle-catalog`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to load lifecycle catalog: ${response.status}`)
  return response.json()
}

export async function listLifecycleEvents(invoiceId: number): Promise<LifecycleEvent[]> {
  const response = await fetch(`${API_BASE}/api/ihm/invoices/${invoiceId}/lifecycle-events`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to list lifecycle events: ${response.status}`)
  return response.json()
}

export function lifecycleEventAttachmentDownloadUrl(
  invoiceId: number,
  eventId: number,
  attachmentId: number,
): string {
  return `${API_BASE}/api/ihm/invoices/${invoiceId}/lifecycle-events/${eventId}/attachments/${attachmentId}/download`
}

export async function createLifecycleEvent(
  invoiceId: number,
  payload: CreateLifecycleEventPayload,
): Promise<LifecycleEvent> {
  const response = await fetch(`${API_BASE}/api/ihm/invoices/${invoiceId}/lifecycle-events`, {
    credentials: 'include',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `Failed to create lifecycle event: ${response.status}`)
  }
  return response.json()
}
