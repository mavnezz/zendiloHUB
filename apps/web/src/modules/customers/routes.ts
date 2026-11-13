import type { RouteRecordRaw } from 'vue-router'

/** Inside an organization (below /t/:tenantId). */
export const customerRoutes: RouteRecordRaw[] = [
  {
    path: 'contacts',
    name: 'contacts',
    component: () => import('./views/ContactsView.vue'),
    meta: { permission: 'customers.view' },
  },
  {
    path: 'contacts/:contactId',
    name: 'contact',
    component: () => import('./views/ContactView.vue'),
    meta: { permission: 'customers.view' },
  },
  {
    path: 'companies',
    name: 'companies',
    component: () => import('./views/CompaniesView.vue'),
    meta: { permission: 'customers.view' },
  },
  {
    path: 'companies/:companyId',
    name: 'company',
    component: () => import('./views/CompanyView.vue'),
    meta: { permission: 'customers.view' },
  },
]
