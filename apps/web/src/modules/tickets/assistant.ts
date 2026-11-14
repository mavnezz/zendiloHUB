import { ref, type Ref } from 'vue'
import { ticketsApi } from './api'

const enabled = ref<boolean | null>(null)
let loading: Promise<void> | null = null

/** Whether the server has the AI assistant (asked once per page load). */
export function useAssistant(tenantId: string): Ref<boolean | null> {
  if (enabled.value === null && !loading) {
    loading = ticketsApi
      .assistant(tenantId)
      .then((answer) => {
        enabled.value = answer.enabled
      })
      .catch(() => {
        enabled.value = false
      })
  }
  return enabled
}

/** For tests: forget the answer. */
export function resetAssistant(): void {
  enabled.value = null
  loading = null
}
