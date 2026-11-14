import { afterEach, beforeEach, vi } from 'vitest'
import { http } from '@/core/api/http'
import { setLocale } from '@/core/i18n/i18n'
import { useInstance } from '@/core/instance'
import { useSession } from '@/modules/identity/session'
import { resetFollowedQueues } from '@/modules/notifications/followed'
import { resetRoles } from '@/modules/tenancy/roles'
import { resetAssistant } from '@/modules/tickets/assistant'
import { resetDirectory } from '@/modules/tickets/directory'
import { useTenants } from '@/modules/tenancy/tenants'
import { unmountAll } from './mount'

class NoopResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

beforeEach(() => {
  localStorage.clear()
  // Tests assert English texts unless they switch the language themselves.
  setLocale('en')
  if (!('ResizeObserver' in globalThis)) {
    vi.stubGlobal('ResizeObserver', NoopResizeObserver)
  }
})

afterEach(() => {
  unmountAll()
  http.onUnauthenticated(null)
  useSession().reset()
  useTenants().reset()
  useInstance().reset()
  resetRoles()
  resetDirectory()
  resetAssistant()
  resetFollowedQueues()
})
