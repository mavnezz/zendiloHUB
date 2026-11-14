import type { RouteRecordRaw } from 'vue-router'

/** Inside an organization (below /t/:tenantId). */
export const reportingRoutes: RouteRecordRaw[] = [
  {
    path: 'reports',
    name: 'reports',
    component: () => import('./views/ReportsView.vue'),
    meta: { permission: 'reports.view' },
  },
]
