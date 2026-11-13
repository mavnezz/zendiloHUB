import { http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type TextModule = Schemas['TextModuleResponse']
export type TextModuleRequest = Schemas['TextModuleRequest']

const base = (tenantId: string) => `/tenants/${tenantId}`

/** Text modules: typed as `::keyword` while writing. */
export const knowledgeApi = {
  textModules: (tenantId: string, queueId?: string) =>
    http.get<TextModule[]>(`${base(tenantId)}/text-modules`, { queue_id: queueId }),
  create: (tenantId: string, body: TextModuleRequest) => http.post<TextModule>(`${base(tenantId)}/text-modules`, body),
  update: (tenantId: string, id: string, body: TextModuleRequest) =>
    http.patch<TextModule>(`${base(tenantId)}/text-modules/${id}`, body),
  remove: (tenantId: string, id: string) => http.delete<void>(`${base(tenantId)}/text-modules/${id}`),
}

/** Fills the placeholders a text module may use from what the composer knows. */
export function fill(body: string, values: Record<string, string>): string {
  return body.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (whole, name: string) => values[name] ?? whole)
}
