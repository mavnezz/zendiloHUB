import type { RouteRecordRaw } from 'vue-router'

/** Inside an organization (below /t/:tenantId). */
export const ticketRoutes: RouteRecordRaw[] = [
  { path: 'tickets', name: 'tickets', component: () => import('./views/TicketsView.vue') },
  { path: 'tickets/new', name: 'newTicket', component: () => import('./views/NewTicketView.vue') },
  { path: 'tickets/:ticketId', name: 'ticket', component: () => import('./views/TicketView.vue') },
  {
    path: 'ticket-fields',
    name: 'ticketFields',
    component: () => import('./views/TicketFieldsView.vue'),
    meta: { permission: 'queues.manage' },
  },
  {
    path: 'ticket-numbers',
    name: 'ticketNumbers',
    component: () => import('./views/TicketNumbersView.vue'),
    meta: { permission: 'tenant.manage' },
  },
]
