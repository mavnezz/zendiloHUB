/** Stands in for EventSource: tests emit the server's events by hand. */
export class FakeEventSource {
  static instances: FakeEventSource[] = []
  readonly listeners = new Map<string, ((event: MessageEvent<string>) => void)[]>()
  closed = false

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this)
  }

  static last(): FakeEventSource {
    const source = FakeEventSource.instances.at(-1)
    if (!source) {
      throw new Error('No event source was opened')
    }
    return source
  }

  addEventListener(type: string, listener: (event: MessageEvent<string>) => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener])
  }

  emit(type: string, data: unknown): void {
    for (const listener of this.listeners.get(type) ?? []) {
      listener(new MessageEvent(type, { data: JSON.stringify(data) }))
    }
  }

  close(): void {
    this.closed = true
  }
}
