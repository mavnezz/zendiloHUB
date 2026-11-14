import { http } from '@/core/api/http'
import type { Schemas } from '@/core/api/types'

export type TextModule = Schemas['TextModuleResponse']
export type TextModuleRequest = Schemas['TextModuleRequest']
export type Article = Schemas['ArticleResponse']
export type ArticleRequest = Schemas['ArticleRequest']
export type Library = Schemas['LibraryResponse']

const base = (tenantId: string) => `/tenants/${tenantId}`

/** Text modules: typed as `::keyword` while writing. */
export const knowledgeApi = {
  textModules: (tenantId: string, queueId?: string) =>
    http.get<TextModule[]>(`${base(tenantId)}/text-modules`, { queue_id: queueId }),
  create: (tenantId: string, body: TextModuleRequest) => http.post<TextModule>(`${base(tenantId)}/text-modules`, body),
  update: (tenantId: string, id: string, body: TextModuleRequest) =>
    http.patch<TextModule>(`${base(tenantId)}/text-modules/${id}`, body),
  remove: (tenantId: string, id: string) => http.delete<void>(`${base(tenantId)}/text-modules/${id}`),

  articles: (tenantId: string, query: { q?: string; category?: string } = {}) =>
    http.get<Library>(`${base(tenantId)}/articles`, query),
  createArticle: (tenantId: string, body: ArticleRequest) => http.post<Article>(`${base(tenantId)}/articles`, body),
  updateArticle: (tenantId: string, id: string, body: ArticleRequest) =>
    http.patch<Article>(`${base(tenantId)}/articles/${id}`, body),
  deleteArticle: (tenantId: string, id: string) => http.delete<void>(`${base(tenantId)}/articles/${id}`),

  /** The help center: public articles, no login. */
  helpCenter: (tenantId: string, query: { q?: string; category?: string } = {}) =>
    http.get<Library>(`/help/${tenantId}`, query),
  helpArticle: (tenantId: string, id: string) => http.get<Article>(`/help/${tenantId}/${id}`),
}

/** Fills the placeholders a text module may use from what the composer knows. */
export function fill(body: string, values: Record<string, string>): string {
  return body.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (whole, name: string) => values[name] ?? whole)
}
