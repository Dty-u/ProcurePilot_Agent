<script setup lang="ts">
import type { ThreadSummary } from '@/types'

defineProps<{ threads: ThreadSummary[]; currentThreadId?: string }>()
defineEmits<{ select: [threadId: string]; create: [] }>()
</script>

<template>
  <aside class="thread-list">
    <div class="brand">
      <span class="brand-mark">P</span>
      <div><strong>ProcurePilot</strong><small>采购 Agent 工作台</small></div>
    </div>
    <button class="new-chat" type="button" @click="$emit('create')">+ 新建会话</button>
    <p class="section-label">最近会话</p>
    <button
      v-for="thread in threads"
      :key="thread.thread_id"
      class="thread-item"
      :class="{ active: thread.thread_id === currentThreadId }"
      type="button"
      @click="$emit('select', thread.thread_id)"
    >
      <strong>{{ thread.thread_id }}</strong
      ><small>{{ thread.message_count }} 条消息</small>
    </button>
    <p v-if="!threads.length" class="empty">还没有可回放的会话。</p>
  </aside>
</template>
