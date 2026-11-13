/** Stands in for XMLHttpRequest (uploads): answers every request with `FakeXhr.reply`. */
export class FakeXhr {
  static requests: FakeXhr[] = []
  static reply: { status: number; body: unknown } = { status: 200, body: {} }
  headers: Record<string, string> = {}
  method = ''
  url = ''
  status = 0
  responseText = ''
  body: unknown
  upload: { onprogress: ((event: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = {
    onprogress: null,
  }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null

  constructor() {
    FakeXhr.requests.push(this)
  }

  static get last(): FakeXhr {
    const request = FakeXhr.requests.at(-1)
    if (!request) {
      throw new Error('No request was sent')
    }
    return request
  }

  open(method: string, url: string): void {
    this.method = method
    this.url = url
  }

  setRequestHeader(name: string, value: string): void {
    this.headers[name] = value
  }

  send(body: unknown): void {
    this.body = body
    if (FakeXhr.reply.status) {
      queueMicrotask(() => this.respond(FakeXhr.reply.status, JSON.stringify(FakeXhr.reply.body)))
    }
  }

  respond(status: number, text: string): void {
    this.status = status
    this.responseText = text
    this.onload?.()
  }
}
