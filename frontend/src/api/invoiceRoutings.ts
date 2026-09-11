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

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function listFailedRoutings(): Promise<FailedInvoiceRouting[]> {
  const response = await fetch(`${API_BASE}/api/ihm/invoice-routings/failed`)
  if (!response.ok) throw new Error(`Failed to list failed routings: ${response.status}`)
  return response.json()
}

export async function replayRoutings(routingIds: number[]): Promise<ReplayRoutingResult[]> {
  const response = await fetch(`${API_BASE}/api/ihm/invoice-routings/replay`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ routing_ids: routingIds }),
  })
  if (!response.ok) throw new Error(`Failed to replay routings: ${response.status}`)
  return response.json()
}

export async function runSendCycle(): Promise<void> {
  const response = await fetch(`${API_BASE}/api/ihm/invoice-routings/run-send-cycle`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error(`Failed to run send cycle: ${response.status}`)
}
