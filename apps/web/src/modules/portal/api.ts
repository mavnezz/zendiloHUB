import { http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type PortalSettings = Schemas['PortalSettingsBody']
export type PortalTicket = Schemas['PortalTicketResponse']
export type PortalThread = Schemas['PortalThreadResponse']
export type PortalMessage = Schemas['PortalMessageResponse']
export type Visitor = Schemas['VisitorResponse']

const portal = (tenantId: string) => `/portal/${tenantId}`

/** The customer portal: its settings (for administrators) and what customers do there (no account, a link by mail). */
export const portalApi = {
  settings: (tenantId: string) => http.get<PortalSettings>(`/tenants/${tenantId}/portal-settings`),
  saveSettings: (tenantId: string, body: PortalSettings) =>
    http.put<PortalSettings>(`/tenants/${tenantId}/portal-settings`, body),

  requestLink: (tenantId: string, email: string) => http.post<void>(`${portal(tenantId)}/login`, { email }),
  verify: (tenantId: string, token: string) => http.post<Visitor>(`${portal(tenantId)}/verify`, { token }),
  logout: (tenantId: string) => http.post<void>(`${portal(tenantId)}/logout`),
  me: (tenantId: string) => http.get<Visitor>(`${portal(tenantId)}/me`),
  tickets: (tenantId: string) => http.get<PortalTicket[]>(`${portal(tenantId)}/tickets`),
  open: (tenantId: string, subject: string, body: string) =>
    http.post<PortalTicket>(`${portal(tenantId)}/tickets`, { subject, body }),
  thread: (tenantId: string, ticketId: string) => http.get<PortalThread>(`${portal(tenantId)}/tickets/${ticketId}`),
  answer: (tenantId: string, ticketId: string, body: string) =>
    http.post<PortalThread>(`${portal(tenantId)}/tickets/${ticketId}/messages`, { body }),
}
