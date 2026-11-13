import type { RouteRecordRaw } from 'vue-router'

/** Inside an organization (below /t/:tenantId). */
export const complianceRoutes: RouteRecordRaw[] = [
  {
    path: 'audit-log',
    name: 'audit',
    component: () => import('./views/AuditLogView.vue'),
    meta: { permission: 'audit.view' },
  },
]

/** In the platform administration (below /admin). */
export const complianceAdminRoutes: RouteRecordRaw[] = [
  { path: 'audit-log', name: 'admin-audit', component: () => import('./views/AdminAuditLogView.vue') },
]
