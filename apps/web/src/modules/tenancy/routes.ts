import type { RouteRecordRaw } from 'vue-router'

/** Outside an organization (plain layout). */
export const tenancyRoutes: RouteRecordRaw[] = [
  {
    path: 'onboarding',
    name: 'onboarding',
    component: () => import('./views/OnboardingView.vue'),
    meta: { requiresAuth: true },
  },
  { path: 'invitations', name: 'invitation', component: () => import('./views/InvitationView.vue') },
]

/** Inside an organization (below /t/:tenantId, with the sidebar). */
export const tenantRoutes: RouteRecordRaw[] = [
  { path: 'team', name: 'team', component: () => import('./views/TeamView.vue'), meta: { permission: 'members.view' } },
  { path: 'roles', name: 'roles', component: () => import('./views/RolesView.vue') },
  {
    path: 'settings',
    name: 'settings',
    component: () => import('./views/TenantSettingsView.vue'),
    meta: { permission: 'tenant.manage' },
  },
  {
    path: 'api-keys',
    name: 'apiKeys',
    component: () => import('./views/ApiKeysView.vue'),
    meta: { permission: 'integrations.manage' },
  },
]
