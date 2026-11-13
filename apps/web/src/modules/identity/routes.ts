import type { RouteRecordRaw } from 'vue-router'

/** Inside the app layout. */
export const identityRoutes: RouteRecordRaw[] = [
  // The guard opens it only while a self-hosted instance has no administrator.
  { path: 'setup', name: 'setup', component: () => import('./views/SetupView.vue') },
  { path: 'login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { guestOnly: true } },
  {
    path: 'register',
    name: 'register',
    component: () => import('./views/RegisterView.vue'),
    meta: { guestOnly: true },
  },
  { path: 'verify-email', name: 'verify-email', component: () => import('./views/VerifyEmailView.vue') },
  {
    path: 'forgot-password',
    name: 'forgot-password',
    component: () => import('./views/ForgotPasswordView.vue'),
    meta: { guestOnly: true },
  },
  { path: 'reset-password', name: 'reset-password', component: () => import('./views/ResetPasswordView.vue') },
]
