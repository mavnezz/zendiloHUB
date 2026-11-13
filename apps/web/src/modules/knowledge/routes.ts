import type { RouteRecordRaw } from 'vue-router'

/** Inside an organization (below /t/:tenantId); everyone sees the text modules, `knowledge.manage` changes them. */
export const knowledgeRoutes: RouteRecordRaw[] = [
  { path: 'text-modules', name: 'textModules', component: () => import('./views/TextModulesView.vue') },
]
