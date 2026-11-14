import { http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type Webhook = Schemas['WebhookResponse']
export type WebhookRequest = Schemas['WebhookRequest']
export type WebhookEvent = WebhookRequest['events'][number]
export type WebhookDelivery = Schemas['WebhookDeliveryResponse']

export const WEBHOOK_EVENTS: readonly WebhookEvent[] = [
  'ticket.created',
  'ticket.changed',
  'message.added',
  'sla.breached',
]

const base = (tenantId: string) => `/tenants/${tenantId}/webhooks`

export const integrationsApi = {
  list: (tenantId: string) => http.get<Webhook[]>(base(tenantId)),
  create: (tenantId: string, body: WebhookRequest) => http.post<Webhook>(base(tenantId), body),
  update: (tenantId: string, id: string, body: WebhookRequest) => http.patch<Webhook>(`${base(tenantId)}/${id}`, body),
  remove: (tenantId: string, id: string) => http.delete<void>(`${base(tenantId)}/${id}`),
  test: (tenantId: string, id: string) => http.post<void>(`${base(tenantId)}/${id}/test`),
  deliveries: (tenantId: string, id: string) => http.get<WebhookDelivery[]>(`${base(tenantId)}/${id}/deliveries`),
}
