import { buildUrl, http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type Ticket = Schemas['TicketResponse']
export type TicketDetail = Schemas['TicketDetailResponse']
export type TicketPage = Schemas['TicketPageResponse']
export type TicketCounts = Schemas['TicketCountsResponse']
export type TicketMessage = Schemas['MessageResponse']
export type Attachment = Schemas['AttachmentResponse']
export type HistoryEntry = Schemas['HistoryEntryResponse']
export type TimeEntry = Schemas['TimeEntryResponse']
export type CreateTicketRequest = Schemas['CreateTicketRequest']
export type TicketChanges = Schemas['TicketChangesRequest']
export type MessageRequest = Schemas['MessageRequest']
export type BulkRequest = Schemas['BulkRequest']
export type CustomerCard = NonNullable<Ticket['customer']>
export type TicketState = Ticket['state']
export type SettableState = NonNullable<TicketChanges['state']>
export type Priority = Ticket['priority']
export type LinkKind = Schemas['LinkRequest']['kind']
export type FirstMessage = NonNullable<CreateTicketRequest['first']>
export type TicketView = 'mine' | 'unassigned' | 'due' | 'escalated' | 'open' | 'watching' | 'closed' | 'all'
export type TicketSort = 'updated' | 'created' | 'priority' | 'number' | 'pending'

export const VIEWS: readonly TicketView[] = [
  'mine',
  'unassigned',
  'due',
  'escalated',
  'open',
  'watching',
  'closed',
  'all',
]
export type TicketField = Schemas['FieldResponse']
export type ChecklistItem = Schemas['ChecklistItemResponse']
export type Viewer = Schemas['ViewerResponse']
export type AssistTask = Schemas['AssistTask']
export const SETTABLE_STATES: readonly SettableState[] = ['new', 'open', 'pending_reminder', 'pending_close', 'closed']
export const PENDING_STATES: readonly TicketState[] = ['pending_reminder', 'pending_close']
export const PRIORITIES: readonly Priority[] = ['low', 'normal', 'high', 'urgent']
export const LINK_KINDS: readonly LinkKind[] = ['related', 'parent', 'child']

export interface TicketQuery {
  view?: TicketView
  queue_id?: string
  state?: TicketState
  priority?: Priority
  owner_id?: string
  customer_id?: string
  company_id?: string
  ids?: string[]
  tag?: string
  q?: string
  sort?: TicketSort
  descending?: boolean
  offset?: number
  limit?: number
}

const base = (tenantId: string) => `/tenants/${tenantId}`
const one = (tenantId: string, id: string) => `${base(tenantId)}/tickets/${id}`

/** Tickets: what the caller may do with each is in its `rights` (their groups' rights in its queue). */
export const ticketsApi = {
  list: (tenantId: string, query: TicketQuery = {}) => http.get<TicketPage>(`${base(tenantId)}/tickets`, { ...query }),
  counts: (tenantId: string) => http.get<TicketCounts>(`${base(tenantId)}/tickets/counts`),
  create: (tenantId: string, body: CreateTicketRequest) => http.post<TicketDetail>(`${base(tenantId)}/tickets`, body),
  get: (tenantId: string, id: string) => http.get<TicketDetail>(one(tenantId, id)),
  byNumber: (tenantId: string, number: number) => http.get<Ticket>(`${base(tenantId)}/tickets/by-number/${number}`),
  update: (tenantId: string, id: string, body: TicketChanges) => http.patch<TicketDetail>(one(tenantId, id), body),
  remove: (tenantId: string, id: string) => http.delete<void>(one(tenantId, id)),
  bulk: (tenantId: string, body: BulkRequest) =>
    http.post<Schemas['BulkResponse']>(`${base(tenantId)}/tickets/bulk`, body),

  messages: (tenantId: string, id: string) => http.get<TicketMessage[]>(`${one(tenantId, id)}/messages`),
  addMessage: (tenantId: string, id: string, body: MessageRequest) =>
    http.post<TicketMessage>(`${one(tenantId, id)}/messages`, body),
  /** A file for the message being written; its id goes into `attachment_ids`. */
  upload: (tenantId: string, id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.upload<Attachment>(`${one(tenantId, id)}/attachments`, form)
  },
  discard: (tenantId: string, id: string, attachmentId: string) =>
    http.delete<void>(`${one(tenantId, id)}/attachments/${attachmentId}`),
  /** The address of a file, for links and image previews. */
  attachmentUrl: (tenantId: string, id: string, attachmentId: string) =>
    buildUrl(`${one(tenantId, id)}/attachments/${attachmentId}`),
  history: (tenantId: string, id: string) => http.get<HistoryEntry[]>(`${one(tenantId, id)}/history`),
  time: (tenantId: string, id: string) => http.get<TimeEntry[]>(`${one(tenantId, id)}/time`),
  recordTime: (tenantId: string, id: string, minutes: number) =>
    http.post<TimeEntry>(`${one(tenantId, id)}/time`, { minutes }),

  watch: (tenantId: string, id: string) => http.put<void>(`${one(tenantId, id)}/watch`),
  unwatch: (tenantId: string, id: string) => http.delete<void>(`${one(tenantId, id)}/watch`),
  link: (tenantId: string, id: string, number: number, kind: LinkKind) =>
    http.post<TicketDetail>(`${one(tenantId, id)}/links`, { number, kind }),
  unlink: (tenantId: string, id: string, otherId: string) => http.delete<void>(`${one(tenantId, id)}/links/${otherId}`),
  merge: (tenantId: string, id: string, number: number) =>
    http.post<TicketDetail>(`${one(tenantId, id)}/merge`, { number }),
  split: (tenantId: string, id: string, messageId: string, subject?: string) =>
    http.post<TicketDetail>(`${one(tenantId, id)}/split`, { message_id: messageId, subject }),

  assignees: (tenantId: string, queueId: string) => http.get<string[]>(`${base(tenantId)}/queues/${queueId}/assignees`),

  fields: (tenantId: string) => http.get<TicketField[]>(`${base(tenantId)}/ticket-fields`),
  createField: (tenantId: string, body: Schemas['FieldRequest']) =>
    http.post<TicketField>(`${base(tenantId)}/ticket-fields`, body),
  updateField: (tenantId: string, id: string, body: Schemas['FieldRequest']) =>
    http.patch<TicketField>(`${base(tenantId)}/ticket-fields/${id}`, body),
  deleteField: (tenantId: string, id: string) => http.delete<void>(`${base(tenantId)}/ticket-fields/${id}`),

  checklist: (tenantId: string, id: string) => http.get<ChecklistItem[]>(`${one(tenantId, id)}/checklist`),
  addChecklistItem: (tenantId: string, id: string, text: string) =>
    http.post<ChecklistItem>(`${one(tenantId, id)}/checklist`, { text }),
  changeChecklistItem: (tenantId: string, id: string, itemId: string, body: { text?: string; done?: boolean }) =>
    http.patch<ChecklistItem>(`${one(tenantId, id)}/checklist/${itemId}`, body),
  deleteChecklistItem: (tenantId: string, id: string, itemId: string) =>
    http.delete<void>(`${one(tenantId, id)}/checklist/${itemId}`),

  presence: (tenantId: string, id: string, writing: boolean) =>
    http.put<Viewer[]>(`${one(tenantId, id)}/presence`, { writing }),

  /** Tickets about the same thing (words of the subject). */
  similar: (tenantId: string, id: string) => http.get<TicketPage>(`${one(tenantId, id)}/similar`),
  /** Whether the AI assistant is set up on this server. */
  assistant: (tenantId: string) => http.get<Schemas['AssistantResponse']>(`${base(tenantId)}/assistant`),
  /** A summary or a draft reply by the AI assistant; nothing is saved. */
  assist: (tenantId: string, id: string, task: AssistTask) =>
    http.post<Schemas['AssistResponse']>(`${one(tenantId, id)}/assist`, { task }),
}

/** `2026-11-13T09:00` (a datetime-local input) → an ISO date with the browser's offset. */
export function fromLocalInput(value: string): string | null {
  if (!value) {
    return null
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

/** An ISO date → the value of a datetime-local input, in the browser's time zone. */
export function toLocalInput(value: string | null | undefined): string {
  if (!value) {
    return ''
  }
  const date = new Date(value)
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}
