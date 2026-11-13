import { describe, expect, it, vi } from 'vitest'
import { toast } from 'vue-sonner'
import { ApiRequestError } from '@/core/api/http'
import { notify } from '@/core/notify'

describe('notify', () => {
  it('shows success messages and translated errors', () => {
    const success = vi.spyOn(toast, 'success').mockReturnValue(1)
    const error = vi.spyOn(toast, 'error').mockReturnValue(2)
    notify.success('Saved')
    notify.error(new ApiRequestError(403, 'forbidden', 'Forbidden'))
    expect(success).toHaveBeenCalledWith('Saved')
    expect(error).toHaveBeenCalledWith('You are not allowed to do this.')
  })
})
