import { onBeforeUnmount, ref } from 'vue'

/** The current time, updated every `intervalMs` (for durations that tick). */
export function useNow(intervalMs = 1000) {
  const now = ref(Date.now())
  const timer = setInterval(() => {
    now.value = Date.now()
  }, intervalMs)
  onBeforeUnmount(() => clearInterval(timer))
  return now
}
