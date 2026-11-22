<script setup lang="ts">
import { ref } from 'vue'

import type { PendingInterrupt } from '@/types'

defineProps<{ interrupt: PendingInterrupt }>()

const supplement = ref('')
const emit = defineEmits<{ submit: [{ interruptId: string; supplement: string }] }>()

function submit(interruptId: string) {
  if (supplement.value.trim()) emit('submit', { interruptId, supplement: supplement.value })
}
</script>

<template>
  <section class="interrupt-card">
    <p class="eyebrow">需要补充信息</p>
    <h3>请补充订单所需内容</h3>
    <p class="summary">{{ interrupt.summary }}</p>
    <textarea v-model="supplement" rows="3" placeholder="例如：供应商编号为 S-1001" />
    <div class="card-actions">
      <button class="primary" type="button" @click="submit(interrupt.interruptId)">
        提交补充信息
      </button>
    </div>
  </section>
</template>
