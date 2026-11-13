import { vi } from 'vitest'
import { toast } from 'vue-sonner'

/** Records the toasts a test triggers (the Toaster itself is only mounted by App.vue). */
export function spyToasts() {
  const success = vi.spyOn(toast, 'success').mockReturnValue(1)
  const error = vi.spyOn(toast, 'error').mockReturnValue(2)
  return {
    success: () => success.mock.calls.map((call) => call[0] as string),
    error: () => error.mock.calls.map((call) => call[0] as string),
  }
}
