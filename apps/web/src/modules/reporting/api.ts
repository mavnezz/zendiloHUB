import { http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type Report = Schemas['ReportResponse']
export type ReportGroup = Schemas['ReportGroupResponse']

export const reportingApi = {
  report: (tenantId: string, query: { start: string; end: string; timezone?: string; queue_id?: string }) =>
    http.get<Report>(`/tenants/${tenantId}/reports`, query),
}
