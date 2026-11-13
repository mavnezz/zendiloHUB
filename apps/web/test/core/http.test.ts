import { describe, expect, it, vi } from 'vitest'
import { ApiRequestError, buildUrl, HttpClient } from '@/core/api/http'

function client(response: () => Response | Promise<Response>) {
  const fetch = vi.fn(async () => response())
  const http = new HttpClient()
  http.useFetch(fetch)
  return { http, fetch }
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })

describe('buildUrl', () => {
  it('prefixes the API and drops empty query values', () => {
    expect(buildUrl('/jobs', { page: 0, q: 'a*', type: '', cursor: undefined, x: null, flag: false })).toBe(
      '/api/v1/jobs?page=0&q=a*&flag=false',
    )
    expect(buildUrl('/users')).toBe('/api/v1/users')
  })

  it('repeats parameters with several values', () => {
    expect(buildUrl('/calls', { outcome: ['busy', 'no_answer', null], limit: 50 })).toBe(
      '/api/v1/calls?outcome=busy&outcome=no_answer&limit=50',
    )
    expect(buildUrl('/calls', { outcome: [] })).toBe('/api/v1/calls')
  })
})

describe('HttpClient', () => {
  it('sends JSON and parses JSON answers', async () => {
    const { http, fetch } = client(() => json(200, { ok: true }))
    await expect(http.post('/things', { name: 'a' })).resolves.toEqual({ ok: true })
    expect(fetch).toHaveBeenCalledWith('/api/v1/things', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'content-type': 'application/json', accept: 'application/json' },
      body: '{"name":"a"}',
    })
  })

  it.each(['get', 'put', 'patch', 'delete'] as const)('supports %s', async (method) => {
    const { http, fetch } = client(() => new Response(null, { status: 204 }))
    await expect(
      method === 'get' || method === 'delete' ? http[method]('/x') : http[method]('/x', {}),
    ).resolves.toBeUndefined()
    expect((fetch.mock.calls[0] as unknown[])[1]).toMatchObject({ method: method.toUpperCase() })
  })

  it('uploads form data and lets the browser set the content type', async () => {
    const { http, fetch } = client(() => json(201, { id: 'i1' }))
    const form = new FormData()
    form.append('file', new File(['PNG'], 'logo.png'))
    await expect(http.upload('/batches/b1/images', form)).resolves.toEqual({ id: 'i1' })
    expect(fetch).toHaveBeenCalledWith('/api/v1/batches/b1/images', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { accept: 'application/json' },
      body: form,
    })
  })

  it('turns API errors into ApiRequestError', async () => {
    const { http } = client(() => json(409, { error: 'email_taken', message: 'Taken' }))
    const error = await http.get('/users').catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiRequestError)
    expect(error).toMatchObject({ status: 409, code: 'email_taken', message: 'Taken', params: {}, details: [] })
  })

  it('keeps the parameters and details of API errors', async () => {
    const body = {
      error: 'output_too_large',
      message: 'Too large',
      params: { width: 13000, max_width: 12000 },
      details: [{ field: 'dpi', message: 'too small', type: 'value_error' }],
    }
    const { http } = client(() => json(413, body))
    await expect(http.post('/batches', {})).rejects.toMatchObject({ params: body.params, details: body.details })
  })

  it('handles error answers that are not API errors', async () => {
    const { http } = client(() => new Response('<html>Bad gateway</html>', { status: 502 }))
    await expect(http.get('/x')).rejects.toMatchObject({ status: 502, code: 'http_error' })
    const other = client(() => json(500, { oops: true }))
    await expect(other.http.get('/x')).rejects.toMatchObject({ status: 500, code: 'http_error' })
  })

  it('reports network failures', async () => {
    const { http } = client(() => {
      throw new TypeError('Failed to fetch')
    })
    await expect(http.get('/x')).rejects.toMatchObject({
      status: 0,
      code: 'network_error',
      message: expect.stringContaining('Failed to fetch'),
    })
  })

  it('notifies about expired sessions, except for auth endpoints', async () => {
    const { http } = client(() => json(401, { error: 'unauthenticated', message: 'Login required' }))
    const handler = vi.fn()
    http.onUnauthenticated(handler)
    await expect(http.get('/users')).rejects.toBeInstanceOf(ApiRequestError)
    await expect(http.post('/auth/login', {})).rejects.toBeInstanceOf(ApiRequestError)
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('uses the global fetch by default', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(200, [1]))
    await expect(new HttpClient().get('/x')).resolves.toEqual([1])
    expect(spy).toHaveBeenCalled()
  })
})

describe('HttpClient.delete', () => {
  it('passes query parameters', async () => {
    const requests: string[] = []
    const client = new HttpClient()
    client.useFetch(async (input: RequestInfo | URL) => {
      requests.push(input instanceof Request ? input.url : input.toString())
      return new Response(null, { status: 204 })
    })
    await client.delete('/presets/p1', { force: 'yes' })
    expect(requests).toEqual(['/api/v1/presets/p1?force=yes'])
  })
})
