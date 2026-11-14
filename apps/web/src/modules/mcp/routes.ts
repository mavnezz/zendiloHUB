import type { RouteRecordRaw } from 'vue-router'

/** Inside an organization (below /t/:tenantId); every member connects their own assistants. */
export const mcpRoutes: RouteRecordRaw[] = [
  { path: 'ai-assistants', name: 'aiAssistants', component: () => import('./views/AssistantsView.vue') },
]
