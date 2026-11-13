import { http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type AuditEntry = Schemas['AuditEntryResponse']
export type AuditPage = Schemas['AuditPageResponse']

export const complianceApi = {
  tenantLog: (tenantId: string, query: { offset?: number; limit?: number }) =>
    http.get<AuditPage>(`/tenants/${tenantId}/audit-log`, query),
  platformLog: (query: { tenant_id?: string; offset?: number; limit?: number }) =>
    http.get<AuditPage>('/admin/audit-log', query),
}
