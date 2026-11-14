import { computed, reactive } from 'vue'
import { useTenants } from '@/modules/tenancy/tenants'
import { notificationsApi, type FollowedQueue, type FollowMode } from './api'

const state = reactive<{ byTenant: Record<string, FollowedQueue[]> }>({ byTenant: {} })

/** The queues the caller follows (they hear about new tickets there), loaded once per organization and shared. */
export function useFollowedQueues() {
  const tenants = useTenants()
  const tenantId = computed(() => tenants.current.value?.id)
  const queues = computed(() => (tenantId.value ? (state.byTenant[tenantId.value] ?? []) : []))

  return {
    queues,
    loaded: computed(() => !!tenantId.value && tenantId.value in state.byTenant),

    async load(force = false): Promise<void> {
      const id = tenantId.value
      if (!id || (id in state.byTenant && !force)) {
        return
      }
      state.byTenant[id] = (await notificationsApi.followed(id)).queues
    },

    modeOf(queueId: string): FollowMode | null {
      return queues.value.find((each) => each.queue_id === queueId)?.mode ?? null
    },

    /** Follows the queue in this mode, or stops following it (null). */
    async set(queueId: string, mode: FollowMode | null): Promise<void> {
      const id = tenantId.value!
      const others = queues.value.filter((each) => each.queue_id !== queueId)
      const wanted = mode ? [...others, { queue_id: queueId, mode }] : others
      state.byTenant[id] = (await notificationsApi.follow(id, wanted)).queues
    },
  }
}

/** For tests. */
export function resetFollowedQueues(): void {
  state.byTenant = {}
}
