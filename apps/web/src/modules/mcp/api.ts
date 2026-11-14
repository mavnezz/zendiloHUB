import { http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type Connection = Schemas['ConnectionResponse']

const base = (tenantId: string) => `/tenants/${tenantId}/mcp-connections`

export const mcpApi = {
  list: (tenantId: string) => http.get<Connection[]>(base(tenantId)),
  connect: (tenantId: string, name: string) => http.post<Connection>(base(tenantId), { name }),
  disconnect: (tenantId: string, id: string) => http.delete<void>(`${base(tenantId)}/${id}`),
}
