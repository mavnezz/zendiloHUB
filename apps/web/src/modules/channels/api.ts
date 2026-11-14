import { http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type EmailAccount = Schemas['AccountResponse']
export type AccountRequest = Schemas['AccountRequest']
export type ServerRequest = Schemas['ServerRequest']
export type Security = ServerRequest['security']
export type Probe = Schemas['ProbeResponse']
export type MailProvider = Schemas['ConnectStartRequest']['provider']
export type ConnectStart = Schemas['ConnectStartRequest']
export type TextTemplate = Schemas['TemplateResponse']
export type TemplateKind = TextTemplate['kind']
export type Templates = Schemas['TemplatesResponse']
export type QueueChannel = Schemas['QueueChannelResponse']
export type QueueChannelRequest = Schemas['QueueChannelRequest']
export type Personal = Schemas['PersonalResponse']
export type MailFilter = Schemas['FilterResponse']
export type FilterRequest = Schemas['FilterRequest']
export type Condition = Schemas['ConditionModel']
export type FilterField = Condition['field']
export type Operator = Condition['operator']
export type FailedEmail = Schemas['FailedEmailResponse']
export type Delivery = Schemas['DeliveryResponse']
export type FilterTest = Schemas['FilterTestResponse']

export const SECURITIES: readonly Security[] = ['ssl', 'starttls', 'none']
export const FILTER_FIELDS: readonly FilterField[] = ['from', 'to', 'cc', 'delivered_to', 'subject', 'body', 'header']
export const OPERATORS: readonly Operator[] = [
  'contains',
  'not_contains',
  'equals',
  'not_equals',
  'starts_with',
  'ends_with',
  'regex',
]

const base = (tenantId: string) => `/tenants/${tenantId}`

/** E-mail: accounts, signatures and salutations, how queues write, filters, failed mails and deliveries. */
export const channelsApi = {
  accounts: (tenantId: string) => http.get<EmailAccount[]>(`${base(tenantId)}/email-accounts`),
  createAccount: (tenantId: string, body: AccountRequest) =>
    http.post<EmailAccount>(`${base(tenantId)}/email-accounts`, body),
  updateAccount: (tenantId: string, id: string, body: AccountRequest) =>
    http.patch<EmailAccount>(`${base(tenantId)}/email-accounts/${id}`, body),
  deleteAccount: (tenantId: string, id: string) => http.delete<void>(`${base(tenantId)}/email-accounts/${id}`),
  testAccount: (tenantId: string, id: string) => http.post<Probe>(`${base(tenantId)}/email-accounts/${id}/test`),
  fetchNow: (tenantId: string, id: string) => http.post<void>(`${base(tenantId)}/email-accounts/${id}/fetch`),
  mailProviders: (tenantId: string) =>
    http.get<Schemas['MailProvidersResponse']>(`${base(tenantId)}/email-accounts/oauth-providers`),
  /** The provider's sign-in page; it sends the browser back to the e-mail account settings afterwards. */
  startConnect: (tenantId: string, body: ConnectStart) =>
    http.post<Schemas['ConnectStartResponse']>(`${base(tenantId)}/email-accounts/oauth`, body),

  templates: (tenantId: string) => http.get<Templates>(`${base(tenantId)}/text-templates`),
  createTemplate: (tenantId: string, body: Schemas['TemplateRequest']) =>
    http.post<TextTemplate>(`${base(tenantId)}/text-templates`, body),
  updateTemplate: (tenantId: string, id: string, body: Schemas['TemplateRequest']) =>
    http.patch<TextTemplate>(`${base(tenantId)}/text-templates/${id}`, body),
  deleteTemplate: (tenantId: string, id: string) => http.delete<void>(`${base(tenantId)}/text-templates/${id}`),

  queueChannels: (tenantId: string) => http.get<QueueChannel[]>(`${base(tenantId)}/queue-channels`),
  setQueueChannel: (tenantId: string, queueId: string, body: QueueChannelRequest) =>
    http.put<QueueChannel>(`${base(tenantId)}/queue-channels/${queueId}`, body),

  personal: (tenantId: string) => http.get<Personal>(`${base(tenantId)}/me/email-settings`),
  setPersonal: (tenantId: string, body: Schemas['PersonalRequest']) =>
    http.put<Personal>(`${base(tenantId)}/me/email-settings`, body),

  filters: (tenantId: string) => http.get<MailFilter[]>(`${base(tenantId)}/mail-filters`),
  createFilter: (tenantId: string, body: FilterRequest) =>
    http.post<MailFilter>(`${base(tenantId)}/mail-filters`, body),
  updateFilter: (tenantId: string, id: string, body: FilterRequest) =>
    http.patch<MailFilter>(`${base(tenantId)}/mail-filters/${id}`, body),
  deleteFilter: (tenantId: string, id: string) => http.delete<void>(`${base(tenantId)}/mail-filters/${id}`),
  /** The order of one scope: the rules of a mailbox, or (null) the filters for all mailboxes. */
  reorderFilters: (tenantId: string, ids: string[], accountId: string | null = null) =>
    http.put<MailFilter[]>(`${base(tenantId)}/mail-filters-order`, { filter_ids: ids, account_id: accountId }),
  /** Where an e-mail would go; changes nothing. */
  testFilters: (tenantId: string, raw: string, accountId: string | null) =>
    http.post<FilterTest>(`${base(tenantId)}/mail-filters/test`, { raw, account_id: accountId }),

  failed: (tenantId: string) => http.get<FailedEmail[]>(`${base(tenantId)}/failed-emails`),
  retryFailed: (tenantId: string, id: string) =>
    http.post<Schemas['RetryResponse']>(`${base(tenantId)}/failed-emails/${id}/retry`),
  deleteFailed: (tenantId: string, id: string) => http.delete<void>(`${base(tenantId)}/failed-emails/${id}`),

  deliveries: (tenantId: string, ticketId: string) =>
    http.get<Delivery[]>(`${base(tenantId)}/tickets/${ticketId}/deliveries`),
  resend: (tenantId: string, ticketId: string, messageId: string) =>
    http.post<void>(`${base(tenantId)}/tickets/${ticketId}/deliveries/${messageId}/resend`),
  replyDraft: (
    tenantId: string,
    queueId: string,
    query: { number?: number; subject?: string; customer_name?: string; customer_email?: string },
  ) => http.get<Schemas['DraftResponse']>(`${base(tenantId)}/queues/${queueId}/reply-draft`, query),
}
