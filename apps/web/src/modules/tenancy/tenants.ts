import { computed, reactive } from 'vue'
import { tenancyApi, type OwnTenant, type Permission } from './api'

export const LAST_TENANT_KEY = 'zendilohub.tenant'

/** An invitation opened before logging in: after the login (or the confirmed sign-up), the app comes back to it. */
export const PENDING_INVITATION_KEY = 'zendilohub.pending-invitation'

export function rememberInvitation(token: string): void {
  localStorage.setItem(PENDING_INVITATION_KEY, token)
}

/** The remembered invitation, once. */
export function takePendingInvitation(): string | null {
  const token = localStorage.getItem(PENDING_INVITATION_KEY)
  localStorage.removeItem(PENDING_INVITATION_KEY)
  return token
}

const state = reactive<{ loaded: boolean; tenants: OwnTenant[]; currentId: string | null }>({
  loaded: false,
  tenants: [],
  currentId: null,
})

/** The caller's organizations and the one they work in. Shared by the whole app. */
export function useTenants() {
  const current = computed(() => state.tenants.find((tenant) => tenant.id === state.currentId) ?? null)

  return {
    tenants: computed(() => state.tenants),
    loaded: computed(() => state.loaded),
    current,

    async load(force = false): Promise<void> {
      if (state.loaded && !force) {
        return
      }
      state.tenants = await tenancyApi.list()
      state.loaded = true
    },

    /** The tenant the user worked in last time, else the first one they can use. */
    preferred(): OwnTenant | null {
      const usable = state.tenants.filter((tenant) => tenant.status === 'active')
      const last = localStorage.getItem(LAST_TENANT_KEY)
      return usable.find((tenant) => tenant.id === last) ?? usable[0] ?? null
    },

    /** True if the user can work in the tenant (a member, and it is active). */
    usable(tenantId: string): boolean {
      return state.tenants.some((tenant) => tenant.id === tenantId && tenant.status === 'active')
    },

    select(tenantId: string): void {
      state.currentId = tenantId
      localStorage.setItem(LAST_TENANT_KEY, tenantId)
    },

    /** After creating, joining or changing a tenant. */
    put(tenant: OwnTenant): void {
      const index = state.tenants.findIndex((each) => each.id === tenant.id)
      if (index === -1) {
        state.tenants = [...state.tenants, tenant].sort((a, b) => a.name.localeCompare(b.name))
      } else {
        state.tenants.splice(index, 1, tenant)
      }
    },

    /** After deleting or leaving a tenant. */
    forget(tenantId: string): void {
      state.tenants = state.tenants.filter((tenant) => tenant.id !== tenantId)
      if (state.currentId === tenantId) {
        state.currentId = null
      }
    },

    can(permission: Permission): boolean {
      return current.value?.permissions.includes(permission) ?? false
    },

    /** Forget everything (logout, tests). */
    reset(): void {
      state.loaded = false
      state.tenants = []
      state.currentId = null
    },
  }
}
