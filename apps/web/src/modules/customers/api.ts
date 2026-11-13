import { http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type Contact = Schemas['ContactResponse']
export type ContactPage = Schemas['ContactPageResponse']
export type ContactRequest = Schemas['ContactRequest']
export type Company = Schemas['CompanyResponse']
export type CompanyPage = Schemas['CompanyPageResponse']
export type CompanyRequest = Schemas['CompanyRequest']

const base = (tenantId: string) => `/tenants/${tenantId}`

/** Contacts (the people who write in) and their companies. */
export const customersApi = {
  contacts: (tenantId: string, query: { q?: string; company_id?: string; offset?: number; limit?: number } = {}) =>
    http.get<ContactPage>(`${base(tenantId)}/contacts`, query),
  contact: (tenantId: string, id: string) => http.get<Contact>(`${base(tenantId)}/contacts/${id}`),
  createContact: (tenantId: string, body: ContactRequest) => http.post<Contact>(`${base(tenantId)}/contacts`, body),
  updateContact: (tenantId: string, id: string, body: ContactRequest) =>
    http.patch<Contact>(`${base(tenantId)}/contacts/${id}`, body),
  deleteContact: (tenantId: string, id: string) => http.delete<void>(`${base(tenantId)}/contacts/${id}`),

  companies: (tenantId: string, query: { q?: string; offset?: number; limit?: number } = {}) =>
    http.get<CompanyPage>(`${base(tenantId)}/companies`, query),
  company: (tenantId: string, id: string) => http.get<Company>(`${base(tenantId)}/companies/${id}`),
  createCompany: (tenantId: string, body: CompanyRequest) => http.post<Company>(`${base(tenantId)}/companies`, body),
  updateCompany: (tenantId: string, id: string, body: CompanyRequest) =>
    http.patch<Company>(`${base(tenantId)}/companies/${id}`, body),
  deleteCompany: (tenantId: string, id: string) => http.delete<void>(`${base(tenantId)}/companies/${id}`),
}
