import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { clearDisplayHistory, listThreads } from '@/services/api'
import { useChatStore } from '../chat'

vi.mock('@/services/api', () => ({
  clearDisplayHistory: vi.fn(),
  getThread: vi.fn(),
  listThreads: vi.fn(),
  streamChat: vi.fn(),
  streamResume: vi.fn(),
}))

describe('chat store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(listThreads).mockResolvedValue([])
  })

  it('clears only the visible history and resets the active workbench state', async () => {
    const store = useChatStore()
    store.currentThreadId = 'thread-1'
    store.messages = [
      {
        thread_id: 'thread-1',
        message_id: 'msg-1',
        role: 'assistant',
        content: '报价已找到',
        occurred_at: '2026-09-18T00:00:00Z',
        source: 'api',
      },
    ]

    await store.clearCurrentDisplayHistory()

    expect(clearDisplayHistory).toHaveBeenCalledWith('thread-1')
    expect(store.currentThreadId).toBeUndefined()
    expect(store.messages).toEqual([])
  })
})
