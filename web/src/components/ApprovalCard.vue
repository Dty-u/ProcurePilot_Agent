<script setup lang="ts">
import type { PendingInterrupt } from '@/types'

defineProps<{ interrupt: PendingInterrupt }>()

const emit = defineEmits<{
  decide: [{ interruptId: string; decision: 'approve' | 'reject' }]
}>()
</script>

<template>
  <section class="interrupt-card approval-card">
    <p class="eyebrow">需要人工审批</p>
    <h3>确认执行采购操作？</h3>
    <p class="summary">{{ interrupt.summary }}</p>
    <div class="card-actions">
      <button
        class="secondary"
        type="button"
        data-testid="reject"
        @click="emit('decide', { interruptId: interrupt.interruptId, decision: 'reject' })"
      >
        拒绝
      </button>
      <button
        class="primary"
        type="button"
        data-testid="approve"
        @click="emit('decide', { interruptId: interrupt.interruptId, decision: 'approve' })"
      >
        批准执行
      </button>
    </div>
  </section>
</template>
