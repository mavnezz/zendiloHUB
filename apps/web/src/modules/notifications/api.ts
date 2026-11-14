import { http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type Notification = Schemas['NotificationResponse']
export type NotificationInbox = Schemas['InboxResponse']
export type FollowedQueue = Schemas['FollowedQueueModel']
export type FollowMode = NonNullable<FollowedQueue['mode']>

const base = (tenantId: string) => `/tenants/${tenantId}`

export const notificationsApi = {
  list: (tenantId: string, unread = false) =>
    http.get<NotificationInbox>(`${base(tenantId)}/notifications`, { unread: unread || undefined }),
  read: (tenantId: string, ids?: string[]) =>
    http.post<NotificationInbox>(`${base(tenantId)}/notifications/read`, ids ? { ids } : {}),
  settings: (tenantId: string) => http.get<Schemas['SettingsBody']>(`${base(tenantId)}/me/notification-settings`),
  saveSettings: (tenantId: string, email: boolean) =>
    http.put<Schemas['SettingsBody']>(`${base(tenantId)}/me/notification-settings`, { email }),
  followed: (tenantId: string) => http.get<Schemas['FollowedQueuesBody']>(`${base(tenantId)}/notifications/queues`),
  follow: (tenantId: string, queues: FollowedQueue[]) =>
    http.put<Schemas['FollowedQueuesBody']>(`${base(tenantId)}/notifications/queues`, { queues }),
}
