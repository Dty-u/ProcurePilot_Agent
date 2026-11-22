<script setup lang="ts">
import { onMounted, ref } from 'vue'

import ApprovalCard from '@/components/ApprovalCard.vue'
import SupplementCard from '@/components/SupplementCard.vue'
import ThreadList from '@/components/ThreadList.vue'
import ToolActivity from '@/components/ToolActivity.vue'
import { useChatStore } from '@/stores/chat'

const store = useChatStore()
const draft = ref('')

onMounted(async () => {
  try {
    await store.loadThreads()
  } catch (error) {
    store.error =
      error instanceof Error ? error.message : '无法加载会话历史，请确认后端服务已启动。'
  }
})

async function send() {
  const content = draft.value
  draft.value = ''
  await store.send(content)
}
</script>

<template>
  <main class="workbench">
    <ThreadList
      :threads="store.threads"
      :current-thread-id="store.currentThreadId"
      @create="store.startConversation()"
      @select="store.selectThread"
    />

    <section class="conversation">
      <header class="conversation-header">
        <div>
          <p class="eyebrow">采购协作助手</p>
          <h1>采购 Agent 工作台</h1>
        </div>
        <button
          v-if="store.currentThreadId"
          class="clear-history"
          type="button"
          @click="store.clearCurrentDisplayHistory()"
        >
          清除展示记录
        </button>
      </header>
      <p v-if="store.currentThreadId" class="history-notice">
        此操作仅清除前端回放消息，不会删除 Agent 状态或待处理审批。
      </p>
      <div class="messages" aria-live="polite">
        <div v-if="!store.messages.length" class="welcome">
          <span>✦</span>
          <h2>今天需要处理什么采购任务？</h2>
          <p>例如：比较 part-001 的有效报价，或准备创建采购订单。</p>
        </div>
        <article
          v-for="message in store.messages"
          :key="message.message_id"
          class="message"
          :class="message.role"
        >
          <span class="message-role">{{ message.role === 'user' ? '你' : 'Agent' }}</span>
          <p>{{ message.content }}</p>
        </article>
        <ApprovalCard
          v-if="store.pendingInterrupt?.kind === 'decision'"
          :interrupt="store.pendingInterrupt"
          @decide="store.submitDecision"
        />
        <SupplementCard
          v-if="store.pendingInterrupt?.kind === 'supplement'"
          :interrupt="store.pendingInterrupt"
          @submit="({ interruptId, supplement }) => store.submitSupplement(interruptId, supplement)"
        />
      </div>
      <p v-if="store.error" class="error">{{ store.error }}</p>
      <form class="composer" @submit.prevent="send">
        <textarea
          v-model="draft"
          :disabled="store.isStreaming"
          rows="3"
          placeholder="输入采购问题或订单请求…"
        />
        <button class="primary" :disabled="store.isStreaming || !draft.trim()" type="submit">
          {{ store.isStreaming ? '处理中…' : '发送' }}
        </button>
      </form>
    </section>

    <ToolActivity :activities="store.activities" />
  </main>
</template>
