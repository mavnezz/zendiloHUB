import type { RouteRecordRaw } from 'vue-router'

/** Inside an organization (below /t/:tenantId). */
export const accessRoutes: RouteRecordRaw[] = [
  {
    path: 'queues',
    name: 'queues',
    component: () => import('./views/QueuesView.vue'),
    meta: { permission: 'queues.manage' },
  },
  {
    path: 'groups',
    name: 'queueGroups',
    component: () => import('./views/GroupsView.vue'),
    meta: { permission: 'queues.manage' },
  },
  {
    path: 'queue-rights',
    name: 'queueRights',
    component: () => import('./views/QueueRightsView.vue'),
    meta: { permission: 'queues.manage' },
  },
]
