<script setup lang="ts">
import type { ToolActivity as Activity } from '@/types'

defineProps<{ activities: Activity[] }>()
</script>

<template>
  <aside class="tool-panel">
    <div class="panel-heading">
      <p class="eyebrow">运行过程</p>
      <h2>工具活动</h2>
    </div>
    <p v-if="!activities.length" class="empty">Agent 调用采购工具时，执行过程会显示在这里。</p>
    <ol v-else class="activity-list">
      <li v-for="activity in activities" :key="activity.id">
        <span class="status-dot" :class="activity.status" />
        <div>
          <strong>{{ activity.name }}</strong>
          <p>{{ activity.detail || (activity.status === 'running' ? '执行中…' : '已完成') }}</p>
        </div>
      </li>
    </ol>
  </aside>
</template>
