import type { RouteRecordRaw } from 'vue-router'

/** Inside an organization (below /t/:tenantId). */
export const automationRoutes: RouteRecordRaw[] = [
  {
    path: 'macros',
    name: 'macros',
    component: () => import('./views/RulesView.vue'),
    meta: { permission: 'automation.manage', kind: 'macro' },
  },
  {
    path: 'triggers',
    name: 'triggers',
    component: () => import('./views/RulesView.vue'),
    meta: { permission: 'automation.manage', kind: 'trigger' },
  },
  {
    path: 'scheduled-jobs',
    name: 'scheduledJobs',
    component: () => import('./views/RulesView.vue'),
    meta: { permission: 'automation.manage', kind: 'schedule' },
  },
]
