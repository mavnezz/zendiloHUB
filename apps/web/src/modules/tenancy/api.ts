import { http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type OwnTenant = Schemas['OwnTenantResponse']
export type Tenant = Schemas['TenantResponse']
export type Member = Schemas['MemberResponse']
export type Invitation = Schemas['InvitationResponse']
export type InvitationPreview = Schemas['InvitationPreviewResponse']
export type RoleMatrix = Schemas['RoleMatrixResponse']
export type AdminTenantPage = Schemas['AdminTenantPageResponse']
/** A person's role; API keys have none. */
export type TenantRole = NonNullable<OwnTenant['role']>
export type Permission = OwnTenant['permissions'][number]

export const TENANT_ROLES: readonly TenantRole[] = ['owner', 'admin', 'manager', 'agent']

export const tenancyApi = {
  list: () => http.get<OwnTenant[]>('/tenants'),
  create: (body: Schemas['CreateTenantRequest']) => http.post<OwnTenant>('/tenants', body),
  get: (tenantId: string) => http.get<OwnTenant>(`/tenants/${tenantId}`),
  update: (tenantId: string, body: Schemas['UpdateTenantRequest']) =>
    http.patch<OwnTenant>(`/tenants/${tenantId}`, body),
  delete: (tenantId: string) => http.delete<void>(`/tenants/${tenantId}`),

  members: (tenantId: string) => http.get<Member[]>(`/tenants/${tenantId}/members`),
  changeRole: (tenantId: string, userId: string, role: TenantRole) =>
    http.patch<Member>(`/tenants/${tenantId}/members/${userId}`, { role }),
  removeMember: (tenantId: string, userId: string) => http.delete<void>(`/tenants/${tenantId}/members/${userId}`),

  invitations: (tenantId: string) => http.get<Invitation[]>(`/tenants/${tenantId}/invitations`),
  invite: (tenantId: string, body: Schemas['InviteRequest']) =>
    http.post<Invitation>(`/tenants/${tenantId}/invitations`, body),
  revoke: (tenantId: string, invitationId: string) =>
    http.delete<void>(`/tenants/${tenantId}/invitations/${invitationId}`),
  previewInvitation: (token: string) => http.post<InvitationPreview>('/invitations/preview', { token }),
  acceptInvitation: (token: string) => http.post<OwnTenant>('/invitations/accept', { token }),

  roles: () => http.get<RoleMatrix>('/roles'),

  adminTenants: (query: { q?: string; offset?: number; limit?: number }) =>
    http.get<AdminTenantPage>('/admin/tenants', query),
  changeStatus: (tenantId: string, status: Tenant['status']) =>
    http.patch<Tenant>(`/admin/tenants/${tenantId}`, { status }),
}

export type ApiKey = Schemas['ApiKeyResponse']
export type ApiKeyRequest = Schemas['ApiKeyRequest']
export type CreatedApiKey = Schemas['CreatedApiKeyResponse']
export type ApiKeyPermission = ApiKeyRequest['permissions'][number]

/** What a key can be given, in the server's order (what needs a person or an owner is not among them). */
export const API_KEY_PERMISSIONS: readonly ApiKeyPermission[] = ['members.view', 'queues.manage', 'audit.view']
export const READ_PERMISSIONS = API_KEY_PERMISSIONS.filter((permission) => permission.endsWith('.view'))

/** The organization's API keys: other systems call its routes with `Authorization: Bearer zhk_…`. */
export const apiKeysApi = {
  list: (tenantId: string) => http.get<ApiKey[]>(`/tenants/${tenantId}/api-keys`),
  /** The key is in the answer this once. */
  create: (tenantId: string, body: ApiKeyRequest) => http.post<CreatedApiKey>(`/tenants/${tenantId}/api-keys`, body),
  /** Another name or other permissions; the key stays the same. */
  update: (tenantId: string, id: string, body: ApiKeyRequest) =>
    http.patch<ApiKey>(`/tenants/${tenantId}/api-keys/${id}`, body),
  remove: (tenantId: string, id: string) => http.delete<void>(`/tenants/${tenantId}/api-keys/${id}`),
}
