import { computed, reactive } from 'vue'
import { i18n } from '@/core/i18n/i18n'
import { accessApi, type Queue } from '@/modules/access/api'
import { tenancyApi, type Member } from '@/modules/tenancy/api'
import { useTenants } from '@/modules/tenancy/tenants'

interface Entry {
  queues: Queue[]
  members: Member[]
}

const state = reactive<{ byTenant: Record<string, Entry> }>({ byTenant: {} })

/**
 * The queues the caller may see and the members of the organization, to show names instead of ids in the tickets.
 * Loaded once per organization and shared.
 */
export function useDirectory() {
  const tenants = useTenants()
  const entry = computed(() => {
    const tenant = tenants.current.value
    return tenant ? state.byTenant[tenant.id] : undefined
  })

  return {
    queues: computed(() => entry.value?.queues ?? []),
    members: computed(() => entry.value?.members ?? []),

    async load(force = false): Promise<void> {
      const tenant = tenants.current.value
      if (!tenant || (state.byTenant[tenant.id] && !force)) {
        return
      }
      const [queues, members] = await Promise.all([
        accessApi.queues(tenant.id),
        tenants.can('members.view') ? tenancyApi.members(tenant.id).catch(() => []) : Promise.resolve([]),
      ])
      state.byTenant[tenant.id] = { queues, members }
    },

    queueName(id: string | null | undefined): string {
      return entry.value?.queues.find((queue) => queue.id === id)?.name ?? i18n.global.t('tickets.unknownQueue')
    },

    memberName(id: string | null | undefined): string {
      if (!id) {
        return i18n.global.t('tickets.nobody')
      }
      return entry.value?.members.find((member) => member.user_id === id)?.email ?? i18n.global.t('tickets.someone')
    },

    /** Queues where the caller may open tickets. */
    creatable: computed(() => (entry.value?.queues ?? []).filter((queue) => queue.rights.includes('create'))),
  }
}

/** For tests. */
export function resetDirectory(): void {
  state.byTenant = {}
}
