import { defineStore } from 'pinia'

import {
  clearDisplayHistory,
  getThread,
  listThreads,
  streamChat,
  streamResume,
} from '@/services/api'
import type {
  DisplayMessage,
  PendingInterrupt,
  ResumeDecision,
  ThreadSummary,
  ToolActivity,
} from '@/types'

export const useChatStore = defineStore('chat', {
  state: () => ({
    threads: [] as ThreadSummary[],
    messages: [] as DisplayMessage[],
    activities: [] as ToolActivity[],
    currentThreadId: undefined as string | undefined,
    pendingInterrupt: undefined as PendingInterrupt | undefined,
    isStreaming: false,
    error: '',
  }),
  actions: {
    async loadThreads() {
      this.threads = await listThreads()
    },
    async selectThread(threadId: string) {
      this.currentThreadId = threadId
      this.messages = await getThread(threadId)
      this.activities = []
      this.pendingInterrupt = undefined
      this.error = ''
    },
    startConversation() {
      this.currentThreadId = undefined
      this.messages = []
      this.activities = []
      this.pendingInterrupt = undefined
      this.error = ''
    },
    async send(message: string) {
      const content = message.trim()
      if (!content || this.isStreaming) return
      this.messages.push(localMessage(this.currentThreadId ?? 'pending', 'user', content))
      await this.consume(streamChat(content, this.currentThreadId))
      await this.loadThreads()
    },
    async submitSupplement(interruptId: string, supplement: string) {
      if (!this.currentThreadId || !supplement.trim()) return
      await this.consume(
        streamResume(this.currentThreadId, interruptId, { kind: 'supplement', supplement }),
      )
      await this.loadThreads()
    },
    async submitDecision({ interruptId, decision }: ResumeDecision) {
      if (!this.currentThreadId) return
      await this.consume(
        streamResume(this.currentThreadId, interruptId, { kind: 'decision', decision }),
      )
      await this.loadThreads()
    },
    async clearCurrentDisplayHistory() {
      if (!this.currentThreadId) return
      await clearDisplayHistory(this.currentThreadId)
      this.startConversation()
      await this.loadThreads()
    },
    async consume(
      events: AsyncIterable<{ event: string; payload: Record<string, unknown>; threadId?: string }>,
    ) {
      this.isStreaming = true
      this.error = ''
      this.activities = []
      let assistant: DisplayMessage | undefined
      try {
        for await (const event of events) {
          const threadId = event.threadId ?? this.currentThreadId ?? 'pending'
          if (threadId !== 'pending') {
            this.currentThreadId = threadId
            this.messages.forEach((message) => {
              if (message.thread_id === 'pending') message.thread_id = threadId
            })
          }
          if (event.event === 'token') {
            if (!assistant) {
              assistant = localMessage(threadId, 'assistant', '')
              this.messages.push(assistant)
            }
            assistant.content += stringValue(event.payload.text) ?? ''
          }
          this.captureToolActivity(event.event, event.payload)
          if (event.event === 'interrupt') this.pendingInterrupt = toInterrupt(event.payload)
          if (event.event === 'done' && event.payload.ok === false) {
            this.error = 'Agent 执行未完成，请检查后端日志后重试。'
          }
        }
      } catch (error) {
        this.error = error instanceof Error ? error.message : '网络请求失败。'
      } finally {
        this.isStreaming = false
      }
    },
    captureToolActivity(event: string, payload: Record<string, unknown>) {
      const id =
        stringValue(payload.tool_call_id) ?? stringValue(payload.tool_name) ?? crypto.randomUUID()
      const name = stringValue(payload.tool_name) ?? '采购工具'
      if (event === 'tool_start') this.activities.push({ id, name, status: 'running' })
      if (event === 'tool_args' || event === 'tool_result') {
        const activity = this.activities.find((item) => item.id === id)
        if (activity) activity.detail = stringValue(payload.args) ?? stringValue(payload.content)
      }
      if (event === 'tool_end') {
        const activity = this.activities.find((item) => item.id === id)
        if (activity) activity.status = payload.status === 'success' ? 'success' : 'failed'
      }
    },
  },
})

function localMessage(
  threadId: string,
  role: DisplayMessage['role'],
  content: string,
): DisplayMessage {
  return {
    thread_id: threadId,
    message_id: `local-${crypto.randomUUID()}`,
    role,
    content,
    occurred_at: new Date().toISOString(),
    source: 'web',
  }
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined
}

function toInterrupt(payload: Record<string, unknown>): PendingInterrupt {
  const values = Array.isArray(payload.interrupts) ? payload.interrupts : []
  const first = values[0] as Record<string, unknown> | undefined
  const value = first && typeof first.value === 'object' && first.value ? first.value : first
  const details = value as Record<string, unknown> | undefined
  const kind = details?.kind === 'order_info_request' ? 'supplement' : 'decision'
  return {
    interruptId: stringValue(first?.id) ?? stringValue(details?.interrupt_id) ?? '',
    kind,
    summary: JSON.stringify(details?.confirmed_summary ?? details ?? '等待人工处理'),
  }
}
