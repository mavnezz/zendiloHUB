import { http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type Queue = Schemas['QueueResponse']
export type Group = Schemas['GroupResponse']
export type Grant = Schemas['GrantResponse']
export type RightsMatrix = Schemas['RightsMatrixResponse']
export type QueueRight = Queue['rights'][number]
export type RightsPreset = NonNullable<Grant['preset']>

/** The ready-made levels of the matrix, from least to most. */
export const PRESETS: readonly RightsPreset[] = ['read', 'contribute', 'work', 'full']

const base = (tenantId: string) => `/tenants/${tenantId}`

/** Queues, groups and what each group may do in each queue. */
export const accessApi = {
  /** The queues the caller may see, with their rights there. */
  queues: (tenantId: string) => http.get<Queue[]>(`${base(tenantId)}/queues`),
  createQueue: (tenantId: string, body: Schemas['QueueRequest']) => http.post<Queue>(`${base(tenantId)}/queues`, body),
  updateQueue: (tenantId: string, id: string, body: Schemas['QueueRequest']) =>
    http.patch<Queue>(`${base(tenantId)}/queues/${id}`, body),
  deleteQueue: (tenantId: string, id: string) => http.delete<void>(`${base(tenantId)}/queues/${id}`),

  groups: (tenantId: string) => http.get<Group[]>(`${base(tenantId)}/groups`),
  createGroup: (tenantId: string, body: Schemas['GroupRequest']) => http.post<Group>(`${base(tenantId)}/groups`, body),
  updateGroup: (tenantId: string, id: string, body: Schemas['GroupRequest']) =>
    http.patch<Group>(`${base(tenantId)}/groups/${id}`, body),
  setMembers: (tenantId: string, id: string, userIds: string[]) =>
    http.put<Group>(`${base(tenantId)}/groups/${id}/members`, { user_ids: userIds }),
  deleteGroup: (tenantId: string, id: string) => http.delete<void>(`${base(tenantId)}/groups/${id}`),

  matrix: (tenantId: string) => http.get<RightsMatrix>(`${base(tenantId)}/queue-rights`),
  /** No rights take the group's rights in the queue away. */
  setRights: (tenantId: string, groupId: string, queueId: string, rights: QueueRight[]) =>
    http.put<Grant>(`${base(tenantId)}/queue-rights`, { group_id: groupId, queue_id: queueId, rights }),
}
