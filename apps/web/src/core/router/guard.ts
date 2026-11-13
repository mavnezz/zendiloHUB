import type { ComputedRef } from 'vue'
import type { Router } from 'vue-router'
import { http } from '../api/http'
import { useInstance } from '../instance'

export interface SessionGate {
  authenticated: ComputedRef<boolean>
  isAdmin: ComputedRef<boolean>
  load(): Promise<void>
  expire(): void
}

export const LOGIN_ROUTE = 'login'
export const SETUP_ROUTE = 'setup'

/**
 * Sends a new self-hosted instance to the setup wizard, visitors to the login page (and back afterwards), keeps
 * users out of admin pages and away from the login.
 */
export function installGuard(router: Router, session: SessionGate): void {
  const instance = useInstance()
  router.beforeEach(async (to) => {
    try {
      await Promise.all([instance.load(), session.load()])
    } catch {
      // Server unreachable: pages that need it explain that themselves.
    }
    if (instance.setupOpen.value !== (to.name === SETUP_ROUTE)) {
      return instance.setupOpen.value ? { name: SETUP_ROUTE } : { name: 'start' }
    }
    const requiresAuth = to.matched.some((route) => route.meta.requiresAuth || route.meta.requiresAdmin)
    if (requiresAuth && !session.authenticated.value) {
      return { name: LOGIN_ROUTE, query: { redirect: to.fullPath } }
    }
    if (to.matched.some((route) => route.meta.requiresAdmin) && !session.isAdmin.value) {
      return { name: 'start' }
    }
    if (to.meta.guestOnly && session.authenticated.value) {
      return { name: 'start' }
    }
    return true
  })

  http.onUnauthenticated(() => {
    session.expire()
    const current = router.currentRoute.value
    if (current.matched.some((route) => route.meta.requiresAuth || route.meta.requiresAdmin)) {
      void router.push({ name: LOGIN_ROUTE, query: { redirect: current.fullPath } })
    }
  })
}

/** Only allow redirects within the app. */
export function safeRedirect(value: unknown): string {
  return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//') && !value.startsWith('/\\')
    ? value
    : '/'
}

declare module 'vue-router' {
  interface RouteMeta {
    /** Visitors are sent to the login page. */
    requiresAuth?: boolean
    /** Only for administrators. */
    requiresAdmin?: boolean
    /** Login and sign-up: logged-in users go to the start page. */
    guestOnly?: boolean
    /** Pages of an organization: only for roles with this permission. */
    permission?: string
  }
}
