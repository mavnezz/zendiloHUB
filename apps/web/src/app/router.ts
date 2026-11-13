import { watch } from 'vue'
import { createRouter, createWebHistory, type Router, type RouterHistory } from 'vue-router'
import { installGuard, LOGIN_ROUTE } from '@/core/router/guard'
import { identityRoutes } from '@/modules/identity/routes'
import { installLocaleSync, useSession } from '@/modules/identity/session'
import type { Permission } from '@/modules/tenancy/api'
import { accessRoutes } from '@/modules/access/routes'
import { channelRoutes } from '@/modules/channels/routes'
import { customerRoutes } from '@/modules/customers/routes'
import { ticketRoutes } from '@/modules/tickets/routes'
import { complianceAdminRoutes, complianceRoutes } from '@/modules/compliance/routes'
import { tenancyRoutes, tenantRoutes } from '@/modules/tenancy/routes'
import { takePendingInvitation, useTenants } from '@/modules/tenancy/tenants'

export function createAppRouter(history: RouterHistory = createWebHistory()): Router {
  const session = useSession()
  const tenants = useTenants()

  const router = createRouter({
    history,
    routes: [
      {
        path: '/',
        name: 'start',
        // Logged in: the organization the user worked in last, or the onboarding to create one.
        beforeEnter: async () => {
          if (!session.authenticated.value) {
            return { name: LOGIN_ROUTE }
          }
          const invitation = takePendingInvitation()
          if (invitation) {
            return { name: 'invitation', query: { token: invitation } }
          }
          await tenants.load()
          const tenant = tenants.preferred()
          return tenant ? { name: 'overview', params: { tenantId: tenant.id } } : { name: 'onboarding' }
        },
        component: () => import('./NotFoundView.vue'),
      },
      {
        path: '/t/:tenantId',
        component: () => import('./TenantLayout.vue'),
        meta: { requiresAuth: true },
        beforeEnter: async (to) => {
          const tenantId = String(to.params.tenantId)
          await tenants.load()
          if (!tenants.usable(tenantId)) {
            return { name: 'start' }
          }
          tenants.select(tenantId)
          return true
        },
        children: [
          { path: '', redirect: { name: 'overview' } },
          { path: 'overview', name: 'overview', component: () => import('./OverviewView.vue') },
          ...ticketRoutes,
          ...customerRoutes,
          ...channelRoutes,
          ...tenantRoutes,
          ...accessRoutes,
          ...complianceRoutes,
        ],
      },
      {
        path: '/',
        component: () => import('./PlainLayout.vue'),
        children: [
          ...identityRoutes,
          ...tenancyRoutes,
          {
            path: 'account',
            name: 'account',
            component: () => import('./AccountPage.vue'),
            meta: { requiresAuth: true },
          },
          {
            path: 'admin',
            component: () => import('./AdminLayout.vue'),
            meta: { requiresAdmin: true },
            children: [
              { path: '', redirect: { name: 'admin-tenants' } },
              {
                path: 'tenants',
                name: 'admin-tenants',
                component: () => import('@/modules/tenancy/views/AdminTenantsView.vue'),
              },
              { path: 'users', name: 'admin-users', component: () => import('./admin/UsersPage.vue') },
              ...complianceAdminRoutes,
            ],
          },
          { path: 'imprint', name: 'imprint', component: () => import('./LegalView.vue'), props: { page: 'imprint' } },
          { path: 'privacy', name: 'privacy', component: () => import('./LegalView.vue'), props: { page: 'privacy' } },
          { path: 'terms', name: 'terms', component: () => import('./LegalView.vue'), props: { page: 'terms' } },
          { path: ':pathMatch(.*)*', name: 'not-found', component: () => import('./NotFoundView.vue') },
        ],
      },
    ],
    scrollBehavior: (_to, _from, saved) => saved ?? { top: 0 },
  })

  installGuard(router, session)
  // After the organization is selected (beforeEnter): pages the role may not see lead to the dashboard.
  router.beforeResolve((to) => {
    const permission = to.meta.permission as Permission | undefined
    if (permission && to.params.tenantId && !tenants.can(permission)) {
      return { name: 'overview', params: { tenantId: to.params.tenantId } }
    }
    return true
  })
  installLocaleSync()
  // Another account must not see the previous one's organizations.
  watch(
    () => session.user.value?.id ?? null,
    () => tenants.reset(),
  )
  return router
}
