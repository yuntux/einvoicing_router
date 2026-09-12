import { apiFetch } from './http'

export interface FailedInvoiceRouting {
  id: number
  invoice_id: number
  invoice_number: string
  emitter_siren: string
  target_application_id: number
  target_application_name: string
  transfer_status: string
  attempt_count: number
  next_attempt_at: string | null
}

export interface ReplayRoutingResult {
  routing_id: number
  success: boolean
}

export function listFailedRoutings(): Promise<FailedInvoiceRouting[]> {
  return apiFetch('/api/ihm/invoice-routings/failed', {}, 'Failed to list failed routings')
}

export function replayRoutings(routingIds: number[]): Promise<ReplayRoutingResult[]> {
  return apiFetch(
    '/api/ihm/invoice-routings/replay',
    { method: 'POST', json: { routing_ids: routingIds } },
    'Failed to replay routings',
  )
}

export function runSendCycle(): Promise<void> {
  return apiFetch('/api/ihm/invoice-routings/run-send-cycle', { method: 'POST' }, 'Failed to run send cycle')
}
