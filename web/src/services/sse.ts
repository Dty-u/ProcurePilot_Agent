export interface SSEEvent {
  event: string
  payload: Record<string, unknown>
  threadId?: string
}

export async function* parseSSE(chunks: AsyncIterable<string>): AsyncGenerator<SSEEvent> {
  let buffer = ''

  for await (const chunk of chunks) {
    buffer += chunk
    let separatorIndex = buffer.indexOf('\n\n')
    while (separatorIndex >= 0) {
      const frame = buffer.slice(0, separatorIndex)
      buffer = buffer.slice(separatorIndex + 2)
      const parsed = parseFrame(frame)
      if (parsed) {
        yield parsed
      }
      separatorIndex = buffer.indexOf('\n\n')
    }
  }

  const parsed = parseFrame(buffer)
  if (parsed) {
    yield parsed
  }
}

function parseFrame(frame: string): SSEEvent | null {
  const event = frame
    .split('\n')
    .find((line) => line.startsWith('event:'))
    ?.slice('event:'.length)
    .trim()
  const data = frame
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice('data:'.length).trim())
    .join('\n')

  if (!event || !data) {
    return null
  }
  try {
    const decoded: unknown = JSON.parse(data)
    if (!isEnvelope(decoded)) {
      return null
    }
    return {
      event,
      payload: decoded.payload,
      ...(typeof decoded.thread_id === 'string' ? { threadId: decoded.thread_id } : {}),
    }
  } catch {
    return null
  }
}

function isEnvelope(value: unknown): value is {
  payload: Record<string, unknown>
  thread_id?: string
} {
  return (
    typeof value === 'object' &&
    value !== null &&
    'payload' in value &&
    typeof value.payload === 'object' &&
    value.payload !== null
  )
}
