import { http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type User = Schemas['UserResponse']
export type Session = Schemas['SessionResponse']
export type UserPage = Schemas['UserPageResponse']
export type Role = User['role']

export const identityApi = {
  session: () => http.get<Session>('/auth/session'),
  /** The setup wizard of a self-hosted instance: the first administrator and the organization; logs in. */
  completeSetup: (body: Schemas['SetupRequest']) => http.post<Session>('/setup', body),
  register: (body: Schemas['RegisterRequest']) => http.post<void>('/auth/register', body),
  confirm: (token: string) => http.post<Session>('/auth/confirm', { token }),
  resendConfirmation: (body: Schemas['CredentialsRequest']) => http.post<void>('/auth/resend-confirmation', body),
  login: (body: Schemas['CredentialsRequest']) => http.post<Session>('/auth/login', body),
  logout: () => http.post<void>('/auth/logout'),
  forgotPassword: (email: string) => http.post<void>('/auth/forgot-password', { email }),
  resetPassword: (body: Schemas['ResetPasswordRequest']) => http.post<Session>('/auth/reset-password', body),

  updateAccount: (body: Schemas['UpdateAccountRequest']) => http.patch<User>('/account', body),
  changePassword: (body: Schemas['ChangePasswordRequest']) => http.post<void>('/account/password', body),
  deleteAccount: (password: string) => http.post<void>('/account/delete', { password }),

  users: ({ ids, ...query }: { q?: string; offset?: number; limit?: number; ids?: readonly string[] }) =>
    http.get<UserPage>(
      `/admin/users${ids?.length ? `?${ids.map((id) => `ids=${encodeURIComponent(id)}`).join('&')}` : ''}`,
      query,
    ),
  changeRole: (userId: string, role: Role) => http.patch<User>(`/admin/users/${userId}`, { role }),
  deleteUser: (userId: string) => http.delete<void>(`/admin/users/${userId}`),
}

/** Minimum password length, as the server checks it. */
export const PASSWORD_MIN_LENGTH = 10
