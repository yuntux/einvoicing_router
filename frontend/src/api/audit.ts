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

export interface FlowTraceFilters {
  created_from?: string
  created_to?: string
  direction?: string
  afnor_api_version?: string
  http_status?: number
  correlation_id?: string
}

export interface TechnicalLogFilters {
  created_from?: string
  created_to?: string
  log_type?: string
  origin?: string
  company_id?: number
  status?: string
  new_count?: number
  updated_count?: number
  details?: string
}

export interface AuditLogFilters {
  created_from?: string
  created_to?: string
  user_email?: string
  action?: string
  target?: string
  ip_address?: string
}

function toQueryString(filters: object): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  return params.toString()
}

export function listFlowTraces(filters: FlowTraceFilters = {}): Promise<FlowTrace[]> {
  return apiFetch(`/api/ihm/audit/flow-traces?${toQueryString(filters)}`, {}, 'Failed to list flow traces')
}

export function listTechnicalLogs(filters: TechnicalLogFilters = {}): Promise<TechnicalLog[]> {
  return apiFetch(
    `/api/ihm/audit/technical-logs?${toQueryString(filters)}`,
    {},
    'Failed to list technical logs',
  )
}

export function listAuditLogs(filters: AuditLogFilters = {}): Promise<AuditLogEntry[]> {
  return apiFetch(`/api/ihm/audit/audit-logs?${toQueryString(filters)}`, {}, 'Failed to list audit logs')
}
