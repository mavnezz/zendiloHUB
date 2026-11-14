import type { RouteRecordRaw } from 'vue-router'

/** Inside an organization (below /t/:tenantId); everyone sees the text modules, `knowledge.manage` changes them. */
export const knowledgeRoutes: RouteRecordRaw[] = [
  { path: 'text-modules', name: 'textModules', component: () => import('./views/TextModulesView.vue') },
  { path: 'knowledge-base', name: 'knowledgeBase', component: () => import('./views/ArticlesView.vue') },
]

/** Outside the app: the public help center. */
export const helpCenterRoutes: RouteRecordRaw[] = [
  { path: 'help/:tenantId', name: 'helpCenter', component: () => import('./views/HelpCenterView.vue') },
  { path: 'help/:tenantId/:articleId', name: 'helpArticle', component: () => import('./views/HelpCenterView.vue') },
]
