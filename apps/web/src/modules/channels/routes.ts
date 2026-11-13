import type { RouteRecordRaw } from 'vue-router'

/** Inside an organization (below /t/:tenantId). */
export const channelRoutes: RouteRecordRaw[] = [
  {
    path: 'email-accounts',
    name: 'emailAccounts',
    component: () => import('./views/EmailAccountsView.vue'),
    meta: { permission: 'channels.manage' },
  },
  {
    path: 'queue-email',
    name: 'queueEmail',
    component: () => import('./views/QueueEmailView.vue'),
    meta: { permission: 'channels.manage' },
  },
  {
    path: 'text-templates',
    name: 'textTemplates',
    component: () => import('./views/TextTemplatesView.vue'),
    meta: { permission: 'channels.manage' },
  },
  {
    path: 'mail-filters',
    name: 'mailFilters',
    component: () => import('./views/MailFiltersView.vue'),
    meta: { permission: 'channels.manage' },
  },
  {
    path: 'failed-emails',
    name: 'failedEmails',
    component: () => import('./views/FailedEmailsView.vue'),
    meta: { permission: 'channels.manage' },
  },
  { path: 'my-signature', name: 'mySignature', component: () => import('./views/MySignatureView.vue') },
]
