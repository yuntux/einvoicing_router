export interface FlowTrace {
  id: number
  correlation_id: string
  direction: string
  afnor_api_version: string
  request: unknown
  response: unknown
  http_status: number
  created_at: string
}

export interface TechnicalLog {
  id: number
  log_type: string
  origin: string
  company_id: number | null
  status: string
  new_count: number
  updated_count: number
  details: string | null
  created_at: string
}

export interface AuditLogEntry {
  id: number
  user_id: number | null
  user_email: string | null
  action: string
  target: string
  ip_address: string | null
  created_at: string
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function listFlowTraces(): Promise<FlowTrace[]> {
  const response = await fetch(`${API_BASE}/api/ihm/audit/flow-traces`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to list flow traces: ${response.status}`)
  return response.json()
}

export async function listTechnicalLogs(): Promise<TechnicalLog[]> {
  const response = await fetch(`${API_BASE}/api/ihm/audit/technical-logs`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to list technical logs: ${response.status}`)
  return response.json()
}

export async function listAuditLogs(): Promise<AuditLogEntry[]> {
  const response = await fetch(`${API_BASE}/api/ihm/audit/audit-logs`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to list audit logs: ${response.status}`)
  return response.json()
}
