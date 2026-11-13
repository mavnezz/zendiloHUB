import { toast } from 'vue-sonner'
import { errorText } from './i18n/i18n'

export const notify = {
  success(message: string): void {
    toast.success(message)
  },
  error(error: unknown): void {
    toast.error(errorText(error))
  },
}
