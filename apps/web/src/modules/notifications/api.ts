import { http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type Notification = Schemas['NotificationResponse']
export type NotificationInbox = Schemas['InboxResponse']

const base = (tenantId: string) => `/tenants/${tenantId}`

export const notificationsApi = {
  list: (tenantId: string, unread = false) =>
    http.get<NotificationInbox>(`${base(tenantId)}/notifications`, { unread: unread || undefined }),
  read: (tenantId: string, ids?: string[]) =>
    http.post<NotificationInbox>(`${base(tenantId)}/notifications/read`, ids ? { ids } : {}),
  settings: (tenantId: string) => http.get<Schemas['SettingsBody']>(`${base(tenantId)}/me/notification-settings`),
  saveSettings: (tenantId: string, email: boolean) =>
    http.put<Schemas['SettingsBody']>(`${base(tenantId)}/me/notification-settings`, { email }),
}
