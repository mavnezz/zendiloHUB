import { computed, reactive } from 'vue'
import { http } from './api/http'
import type { Schemas } from './api/types'

export type InstanceStatus = Schemas['SetupStatusResponse']

const state = reactive<{ loaded: boolean; status: InstanceStatus }>({
  loaded: false,
  status: { open: false, self_hosted: false },
})

/**
 * What kind of instance this is: self-hosted (one organization, invited people only) or SaaS, and whether the setup
 * wizard is still open. Asked once per page load; the answer only changes when the wizard is done.
 */
export function useInstance() {
  return {
    setupOpen: computed(() => state.status.open),
    selfHosted: computed(() => state.status.self_hosted),

    async load(): Promise<void> {
      if (state.loaded) {
        return
      }
      state.status = await http.get<InstanceStatus>('/setup')
      state.loaded = true
    },

    /** The wizard made the administrator and the organization. */
    setUp(): void {
      state.status = { ...state.status, open: false }
    },

    /** Forget everything, as after a reload (tests). */
    reset(): void {
      state.loaded = false
      state.status = { open: false, self_hosted: false }
    },
  }
}
