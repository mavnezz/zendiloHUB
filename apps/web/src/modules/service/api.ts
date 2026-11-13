import { http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type ServiceSetup = Schemas['SetupResponse']
export type Calendar = Schemas['CalendarResponse']
export type CalendarRequest = Schemas['CalendarRequest']
export type Policy = Schemas['PolicyResponse']
export type PolicyRequest = Schemas['PolicyRequest']
export type TicketClock = Schemas['ClockResponse']
export type Weekday = 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun'

export const WEEKDAYS: readonly Weekday[] = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

const base = (tenantId: string) => `/tenants/${tenantId}`

/** Service levels: business hours, response and solution times. */
export const serviceApi = {
  setup: (tenantId: string) => http.get<ServiceSetup>(`${base(tenantId)}/service-levels`),
  createCalendar: (tenantId: string, body: CalendarRequest) =>
    http.post<Calendar>(`${base(tenantId)}/service-calendars`, body),
  updateCalendar: (tenantId: string, id: string, body: CalendarRequest) =>
    http.patch<Calendar>(`${base(tenantId)}/service-calendars/${id}`, body),
  deleteCalendar: (tenantId: string, id: string) => http.delete<void>(`${base(tenantId)}/service-calendars/${id}`),
  createPolicy: (tenantId: string, body: PolicyRequest) =>
    http.post<Policy>(`${base(tenantId)}/service-policies`, body),
  updatePolicy: (tenantId: string, id: string, body: PolicyRequest) =>
    http.patch<Policy>(`${base(tenantId)}/service-policies/${id}`, body),
  deletePolicy: (tenantId: string, id: string) => http.delete<void>(`${base(tenantId)}/service-policies/${id}`),
  clock: (tenantId: string, ticketId: string) =>
    http.get<TicketClock | null>(`${base(tenantId)}/tickets/${ticketId}/service-level`),
  escalations: (tenantId: string) => http.get<TicketClock[]>(`${base(tenantId)}/escalations`),
}
