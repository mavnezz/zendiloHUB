import type { RouteRecordRaw } from 'vue-router'

/** Inside an organization (below /t/:tenantId): switching the portal on. */
export const portalSettingsRoutes: RouteRecordRaw[] = [
  {
    path: 'customer-portal',
    name: 'customerPortal',
    component: () => import('./views/PortalSettingsView.vue'),
    meta: { permission: 'tenant.manage' },
  },
]

/** Outside the app: where customers see and answer their tickets. */
export const portalRoutes: RouteRecordRaw[] = [
  { path: 'portal/:tenantId', name: 'portal', component: () => import('./views/PortalHomeView.vue') },
  { path: 'portal/:tenantId/verify', name: 'portalVerify', component: () => import('./views/PortalVerifyView.vue') },
  {
    path: 'portal/:tenantId/tickets/:ticketId',
    name: 'portalTicket',
    component: () => import('./views/PortalTicketView.vue'),
  },
]
