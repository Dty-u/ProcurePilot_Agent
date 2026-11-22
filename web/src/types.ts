export interface ThreadSummary {
  thread_id: string
  last_message_at: string
  message_count: number
}

export interface DisplayMessage {
  thread_id: string
  message_id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  occurred_at: string
  source: string
}

export interface ToolActivity {
  id: string
  name: string
  status: 'running' | 'success' | 'failed'
  detail?: string
}

export interface PendingInterrupt {
  interruptId: string
  kind: 'supplement' | 'decision'
  summary: string
}

export interface ResumeDecision {
  interruptId: string
  decision: 'approve' | 'reject'
}
