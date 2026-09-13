import { API_BASE, apiFetch } from './http'

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

export interface LifecycleEventAfnorFlow {
  id: number
  flow_id: string | null
  direction: string
  flow_type: string
  syntax: string
  processing_rule: string | null
  state: string
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
  // Flux CDAR technique associé (§ 6.2) — fusionné dans l'affichage plutôt que
  // listé séparément (cf. maquette popin facture).
  afnor_flow: LifecycleEventAfnorFlow | null
}

export interface CreateLifecycleEventPayload {
  status: string
  reason?: string | null
  action?: string | null
  comment?: string | null
  confirmed?: boolean
}

export function getLifecycleCatalog(): Promise<LifecycleCatalog> {
  return apiFetch('/api/ihm/lifecycle-catalog', {}, 'Failed to load lifecycle catalog')
}

export function listLifecycleEvents(invoiceId: number): Promise<LifecycleEvent[]> {
  return apiFetch(`/api/ihm/invoices/${invoiceId}/lifecycle-events`, {}, 'Failed to list lifecycle events')
}

export function lifecycleEventAttachmentDownloadUrl(
  invoiceId: number,
  eventId: number,
  attachmentId: number,
): string {
  return `${API_BASE}/api/ihm/invoices/${invoiceId}/lifecycle-events/${eventId}/attachments/${attachmentId}/download`
}

export function createLifecycleEvent(
  invoiceId: number,
  payload: CreateLifecycleEventPayload,
): Promise<LifecycleEvent> {
  return apiFetch(
    `/api/ihm/invoices/${invoiceId}/lifecycle-events`,
    { method: 'POST', json: payload },
    'Failed to create lifecycle event',
  )
}

export interface RetryAfnorFlowPayload {
  reason?: string | null
  action?: string | null
  comment?: string | null
}

/** Renvoie un CDAR sortant resté en erreur — `overrides` absent : renvoi tel quel,
 * fourni : remplace motif/action/commentaire avant renvoi (§ fiche facture). */
export function retryAfnorFlow(
  invoiceId: number,
  flowId: number,
  overrides?: RetryAfnorFlowPayload,
): Promise<LifecycleEvent> {
  return apiFetch(
    `/api/ihm/invoices/${invoiceId}/afnor-flows/${flowId}/retry`,
    { method: 'POST', ...(overrides !== undefined && { json: overrides }) },
    'Failed to retry AFNOR flow',
  )
}
