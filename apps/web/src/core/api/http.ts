export const API_BASE = '/api/v1'

export type ErrorParams = Record<string, string | number>

/** The body of every error answer of the API. */
export interface ApiErrorBody {
  error: string
  message: string
  params?: ErrorParams
  details?: { field: string; message: string; type: string }[]
}

/** An error answer of the API (`{ error, message }`) or a network failure (status 0). */
export class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly params: ErrorParams = {},
    readonly details: ApiErrorBody['details'] = [],
  ) {
    super(message)
    this.name = 'ApiRequestError'
  }
}

export type QueryValue = string | number | boolean | null | undefined
/** An array repeats the parameter (`?outcome=busy&outcome=no_answer`). */
export type Query = Record<string, QueryValue | readonly QueryValue[]>

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export function buildUrl(path: string, query: Query = {}): string {
  const params = new URLSearchParams()
  for (const [name, entry] of Object.entries(query)) {
    for (const value of Array.isArray(entry) ? entry : [entry]) {
      if (value !== undefined && value !== null && value !== '') {
        params.append(name, String(value))
      }
    }
  }
  const search = params.toString()
  const separator = path.includes('?') ? '&' : '?'
  return `${API_BASE}${path}${search ? `${separator}${search}` : ''}`
}

/** JSON client for the zendiloHUB API; the session travels in an HTTP-only cookie. */
export class HttpClient {
  #fetch: typeof fetch = (...args) => globalThis.fetch(...args)
  #onUnauthenticated: (() => void) | null = null

  useFetch(implementation: typeof fetch): void {
    this.#fetch = implementation
  }

  /** Called when a request outside /auth fails with 401, e.g. after the session expired. */
  onUnauthenticated(handler: (() => void) | null): void {
    this.#onUnauthenticated = handler
  }

  get<T>(path: string, query?: Query): Promise<T> {
    return this.request<T>('GET', path, undefined, query)
  }

  post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>('POST', path, body)
  }

  put<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>('PUT', path, body)
  }

  patch<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>('PATCH', path, body)
  }

  delete<T>(path: string, query?: Query): Promise<T> {
    return this.request<T>('DELETE', path, undefined, query)
  }

  /** Uploads form data (e.g. a file) as multipart/form-data. */
  upload<T>(path: string, form: FormData): Promise<T> {
    return this.request<T>('POST', path, form)
  }

  async request<T>(method: Method, path: string, body?: unknown, query?: Query): Promise<T> {
    let response: Response
    try {
      response = await this.#fetch(buildUrl(path, query), {
        method,
        credentials: 'same-origin',
        // The browser sets the multipart boundary for form data itself.
        headers:
          body === undefined || body instanceof FormData
            ? { accept: 'application/json' }
            : { 'content-type': 'application/json', accept: 'application/json' },
        body: body === undefined || body instanceof FormData ? body : JSON.stringify(body),
      })
    } catch (error) {
      throw new ApiRequestError(0, 'network_error', `The server is not reachable (${(error as Error).message})`)
    }

    if (response.status === 401 && !path.startsWith('/auth/')) {
      this.#onUnauthenticated?.()
    }
    if (!response.ok) {
      throw await toError(response)
    }
    // 204 and 202 (accepted, e.g. "fetch now") come without a body.
    const text = response.status === 204 ? '' : await response.text()
    return (text ? JSON.parse(text) : undefined) as T
  }
}

async function toError(response: Response): Promise<ApiRequestError> {
  try {
    const body = (await response.json()) as Partial<ApiErrorBody>
    if (typeof body.error === 'string' && typeof body.message === 'string') {
      return new ApiRequestError(response.status, body.error, body.message, body.params, body.details)
    }
  } catch {
    // Not JSON, e.g. a proxy error page.
  }
  return new ApiRequestError(response.status, 'http_error', `Request failed with status ${response.status}`)
}

export const http = new HttpClient()
