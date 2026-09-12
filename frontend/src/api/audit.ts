import { apiFetch } from './http'

export interface FlowTrace {
  id: number
  correlation_id: string
  direction: string
  afnor_api_version: string
  request: unknown
  response: unknown
  request_headers: Record<string, string> | null
  response_headers: Record<string, string> | null
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

export function listFlowTraces(): Promise<FlowTrace[]> {
  return apiFetch('/api/ihm/audit/flow-traces', {}, 'Failed to list flow traces')
}

export function listTechnicalLogs(): Promise<TechnicalLog[]> {
  return apiFetch('/api/ihm/audit/technical-logs', {}, 'Failed to list technical logs')
}

export function listAuditLogs(): Promise<AuditLogEntry[]> {
  return apiFetch('/api/ihm/audit/audit-logs', {}, 'Failed to list audit logs')
}
