import type { RouteRecordRaw } from 'vue-router'

/** Inside an organization (below /t/:tenantId). */
export const integrationRoutes: RouteRecordRaw[] = [
  {
    path: 'webhooks',
    name: 'webhooks',
    component: () => import('./views/WebhooksView.vue'),
    meta: { permission: 'integrations.manage' },
  },
]
