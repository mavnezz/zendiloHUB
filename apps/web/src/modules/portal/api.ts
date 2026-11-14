import { buildUrl, http } from '@/core/api/http'
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
  open: (tenantId: string, subject: string, body: string, files: File[] = []) =>
    http.upload<PortalTicket>(`${portal(tenantId)}/tickets`, form({ subject, body }, files)),
  thread: (tenantId: string, ticketId: string) => http.get<PortalThread>(`${portal(tenantId)}/tickets/${ticketId}`),
  answer: (tenantId: string, ticketId: string, body: string, files: File[] = []) =>
    http.upload<PortalThread>(`${portal(tenantId)}/tickets/${ticketId}/messages`, form({ body }, files)),
  fileUrl: (tenantId: string, ticketId: string, fileId: string) =>
    buildUrl(`${portal(tenantId)}/tickets/${ticketId}/attachments/${fileId}`),
}

/** Customers send text and files as a form (multipart). */
function form(fields: Record<string, string>, files: File[]): FormData {
  const data = new FormData()
  for (const [name, value] of Object.entries(fields)) {
    data.append(name, value)
  }
  for (const file of files) {
    data.append('files', file)
  }
  return data
}
