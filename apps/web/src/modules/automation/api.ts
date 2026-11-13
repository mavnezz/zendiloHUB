import { http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type Rule = Schemas['RuleResponse']
export type RuleRequest = Schemas['RuleRequest']
export type RuleActions = Schemas['RuleActionsModel']
export type RuleCondition = Schemas['RuleConditionModel']
export type RuleSchedule = Schemas['RuleScheduleModel']
export type RuleKind = Rule['kind']
export type TriggerEvent = NonNullable<Rule['event']>
export type ConditionField = RuleCondition['field']
export type ConditionOperator = RuleCondition['operator']

export const RULE_PATHS: Record<RuleKind, string> = { macro: 'macros', trigger: 'triggers', schedule: 'scheduled-jobs' }
export const TRIGGER_EVENTS: readonly TriggerEvent[] = ['created', 'customer_replied', 'updated']
export const CONDITION_FIELDS: readonly ConditionField[] = [
  'subject',
  'customer_email',
  'queue_id',
  'state',
  'priority',
  'channel',
  'tags',
  'owner',
]
export const CONDITION_OPERATORS: readonly ConditionOperator[] = [
  'is',
  'is_not',
  'contains',
  'not_contains',
  'is_set',
  'is_not_set',
]

const base = (tenantId: string) => `/tenants/${tenantId}`

/** Macros, triggers and scheduled jobs. */
export const automationApi = {
  list: (tenantId: string, kind: RuleKind) => http.get<Rule[]>(`${base(tenantId)}/${RULE_PATHS[kind]}`),
  create: (tenantId: string, kind: RuleKind, body: RuleRequest) =>
    http.post<Rule>(`${base(tenantId)}/${RULE_PATHS[kind]}`, body),
  update: (tenantId: string, kind: RuleKind, id: string, body: RuleRequest) =>
    http.patch<Rule>(`${base(tenantId)}/${RULE_PATHS[kind]}/${id}`, body),
  remove: (tenantId: string, kind: RuleKind, id: string) =>
    http.delete<void>(`${base(tenantId)}/${RULE_PATHS[kind]}/${id}`),
}
