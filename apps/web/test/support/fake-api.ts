import { http } from '@/core/api/http'

export interface FakeRequest {
  method: string
  path: string
  /** The last value of every parameter; `params` has repeated ones. */
  query: Record<string, string>
  params: URLSearchParams
  body: unknown
}

export interface FakeResponse {
  status?: number
  body?: unknown
}

type Responder = FakeResponse | ((request: FakeRequest) => FakeResponse | Promise<FakeResponse>)

interface Route {
  method: string
  path: string | RegExp
  responder: Responder
}

/** Answers API requests from registered routes; the last matching route wins. */
export class FakeApi {
  readonly requests: FakeRequest[] = []
  readonly #routes: Route[] = []

  constructor() {
    http.useFetch(this.fetch)
  }

  on(method: string, path: string | RegExp, responder: Responder): this {
    this.#routes.push({ method, path, responder })
    return this
  }

  /** JSON body with status 200. */
  json(method: string, path: string | RegExp, body: unknown, status = 200): this {
    return this.on(method, path, { status, body })
  }

  error(method: string, path: string | RegExp, status: number, error: string, message = error): this {
    return this.on(method, path, { status, body: { error, message } })
  }

  calls(method: string, path: string | RegExp): FakeRequest[] {
    return this.requests.filter((request) => request.method === method && matches(path, request.path))
  }

  last(method: string, path: string | RegExp): FakeRequest | undefined {
    return this.calls(method, path).at(-1)
  }

  readonly fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(input instanceof Request ? input.url : input.toString(), 'http://zendilohub.test')
    const request: FakeRequest = {
      method: init?.method ?? 'GET',
      path: url.pathname.replace(/^\/api\/v1/, ''),
      query: Object.fromEntries(url.searchParams),
      params: url.searchParams,
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : init?.body,
    }
    this.requests.push(request)
    const route = [...this.#routes]
      .reverse()
      .find((candidate) => candidate.method === request.method && matches(candidate.path, request.path))
    if (!route) {
      return new Response(
        JSON.stringify({ error: 'not_mocked', message: `${request.method} ${request.path} is not mocked` }),
        {
          status: 404,
          headers: { 'content-type': 'application/json' },
        },
      )
    }
    const response = typeof route.responder === 'function' ? await route.responder(request) : route.responder
    const status = response.status ?? 200
    return new Response(status === 204 || response.body === undefined ? null : JSON.stringify(response.body), {
      status,
      headers: { 'content-type': 'application/json' },
    })
  }) as typeof fetch
}

function matches(pattern: string | RegExp, path: string): boolean {
  return typeof pattern === 'string' ? pattern === path : pattern.test(path)
}
