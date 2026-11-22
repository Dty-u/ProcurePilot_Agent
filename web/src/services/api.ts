import type { DisplayMessage, ThreadSummary } from '@/types'

import { parseSSE, type SSEEvent } from './sse'

const identityHeaders = {
  'X-User-ID': import.meta.env.VITE_DEV_USER_ID ?? 'buyer-demo',
  'X-User-Name': import.meta.env.VITE_DEV_USER_NAME ?? 'buyer-demo',
  'X-Roles': import.meta.env.VITE_DEV_ROLES ?? 'procurement_reader,order_reader,buyer',
}

export async function listThreads(): Promise<ThreadSummary[]> {
  const response = await fetch('/api/history', { headers: identityHeaders })
  return readJson<{ items: ThreadSummary[] }>(response).then((body) => body.items)
}

export async function getThread(threadId: string): Promise<DisplayMessage[]> {
  const response = await fetch(`/api/history/${encodeURIComponent(threadId)}`, {
    headers: identityHeaders,
  })
  return readJson<{ items: DisplayMessage[] }>(response).then((body) => body.items)
}

export async function clearDisplayHistory(threadId: string): Promise<void> {
  const response = await fetch(`/api/history/${encodeURIComponent(threadId)}`, {
    method: 'DELETE',
    headers: identityHeaders,
  })
  await readJson(response)
}

export function streamChat(message: string, threadId?: string): AsyncIterable<SSEEvent> {
  return postStream('/api/chat/stream', { message, ...(threadId ? { thread_id: threadId } : {}) })
}

export function streamResume(
  threadId: string,
  interruptId: string,
  resume: Record<string, string>,
): AsyncIterable<SSEEvent> {
  return postStream(`/api/chat/${encodeURIComponent(threadId)}/resume`, {
    interrupt_id: interruptId,
    resume,
  })
}

async function* postStream(path: string, body: Record<string, unknown>): AsyncGenerator<SSEEvent> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { ...identityHeaders, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok || !response.body) {
    throw new Error(await responseMessage(response))
  }
  const decoder = new TextDecoder()
  const chunks = {
    async *[Symbol.asyncIterator](): AsyncGenerator<string> {
      const reader = response.body?.getReader()
      if (!reader) return
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          yield decoder.decode(value, { stream: true })
        }
        const tail = decoder.decode()
        if (tail) yield tail
      } finally {
        reader.releaseLock()
      }
    },
  }
  yield* parseSSE(chunks)
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(await responseMessage(response))
  return (await response.json()) as T
}

async function responseMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    return typeof body.detail === 'string' ? body.detail : '请求未成功，请稍后重试。'
  } catch {
    return '请求未成功，请检查后端服务和开发身份配置。'
  }
}
