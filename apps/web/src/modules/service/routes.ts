import type { RouteRecordRaw } from 'vue-router'

/** Inside an organization (below /t/:tenantId); everyone sees the service levels, `service.manage` changes them. */
export const serviceRoutes: RouteRecordRaw[] = [
  { path: 'service-levels', name: 'serviceLevels', component: () => import('./views/ServiceLevelsView.vue') },
]
