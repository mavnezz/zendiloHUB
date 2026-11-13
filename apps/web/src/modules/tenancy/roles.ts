import { computed, reactive } from 'vue'
import { i18n } from '@/core/i18n/i18n'
import { isBuiltin, tenancyApi, type Role, type Roles, type TenantRole } from './api'
import { useTenants } from './tenants'

const state = reactive<{ byTenant: Record<string, Roles> }>({ byTenant: {} })

/** Names a role: built-in roles are translated, own roles have their name. */
export function roleLabel(role: TenantRole, roles: readonly Role[] = [], fallbackName?: string | null): string {
  if (isBuiltin(role)) {
    return i18n.global.t(`tenant.roles.${role}`)
  }
  return roles.find((each) => each.id === role)?.name ?? fallbackName ?? i18n.global.t('tenant.roles.custom')
}

/** The roles of the current organization, loaded once and shared (team, invitations, roles page). */
export function useRoles() {
  const tenants = useTenants()
  const data = computed(() => {
    const tenant = tenants.current.value
    return tenant ? state.byTenant[tenant.id] : undefined
  })
  const all = computed(() => data.value?.roles ?? [])

  return {
    data,
    all,

    async load(force = false): Promise<void> {
      const tenant = tenants.current.value
      if (!tenant || (state.byTenant[tenant.id] && !force)) {
        return
      }
      state.byTenant[tenant.id] = await tenancyApi.roles(tenant.id)
    },

    label(role: TenantRole, fallbackName?: string | null): string {
      return roleLabel(role, all.value, fallbackName)
    },

    /** The roles the caller may hand out: none that may do more than they may. */
    assignable(): Role[] {
      const own = new Set(tenants.current.value?.permissions ?? [])
      return all.value.filter((role) => role.permissions.every((permission) => own.has(permission)))
    },

    /** Whether the caller may change a member with this role (not someone who may do more). */
    governs(role: TenantRole): boolean {
      const own = new Set(tenants.current.value?.permissions ?? [])
      const found = all.value.find((each) => each.id === role)
      return found ? found.permissions.every((permission) => own.has(permission)) : false
    },
  }
}

/** For tests. */
export function resetRoles(): void {
  state.byTenant = {}
}
