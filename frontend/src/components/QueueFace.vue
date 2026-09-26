<script setup>
/**
 * R150 · 排队那张脸（业主计划 v2 §5 第三张脸；后端早给了 event: queued 与两个只读端点）。
 *
 * 每一枚数字都点名它的读数来源：
 *   前面 N 人   GET /queue/status/{request_id} 的 position（1 起，减一才是「前面几个人」）
 *   队列现状    GET /queue/stats 的 queue_length / processing
 *   排不上队    入队那一步的 HTTP 失败（今天只有 queue_unavailable 这一枚真实读数）
 * position 取不到时界面说「读不到」，不补 0，也不按排队人数编一个「队列已满」。
 *
 * R268 · G06：排队中那一轮今天多了一枚真能办事的「不排了」。本组件只画按钮、不打接口 ——
 * 取消这件事由面板发到 POST /queue/{request_id}/cancel，它的三条落点（已取消 / 取消已登记 /
 * 没取消成）也一律住在 ChatPanel.vue，与本组件既有的 retry / action 同一个分工。
 * 给不给这枚按钮由 face.cancellable 决定，而只有【这一轮还没落定】那两格才置真：对着已经
 * 落定的一轮、对着挂起等人拍板的一轮说「不排了」都是假话。
 * face.cancelling = 这一枚还在飞（按钮转忙），face.cancelRetry = 上一次没办成（换文案）。
 * G20 的接线半同时落在本组件：三枚按钮一律走 UiButton 原语，class 沿用既有那两枚，视觉不改。
 */
import UiButton from './ui/UiButton.vue'
defineProps({
  face: {
    type: Object,
    required: true,
  },
  stats: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['retry', 'action', 'cancel'])
</script>

<template>
  <p
    class="queue-face"
    :class="`queue-face--${face.tone}`"
    data-testid="queue-face"
    :data-kind="face.kind"
    :data-ahead="face.ahead === null ? 'unknown' : face.ahead"
    role="status"
    aria-live="polite"
  >
    <span class="queue-headline" data-testid="queue-headline">{{ face.headline }}</span>
    <span v-if="face.detail" class="queue-detail" data-testid="queue-detail">{{ face.detail }}</span>
    <span v-if="stats" class="queue-stats" data-testid="queue-stats">{{ stats.headline }}</span>
    <UiButton
      v-if="face.retryable"
      class="queue-retry"
      size="sm"
      data-testid="queue-retry"
      @click="emit('retry')"
    >按原文再问一次</UiButton>
    <!-- R260 · 挂起待批准那一轮给一件能点的东西：这一枚只做【去哪一屏】，
         批准本身仍由「审批与待办」那两枚既有组件（HitlPendingPanel / HitlPendingRow）
         发到 POST /approve —— 本组件不开第二套批准路径，也不在这里判归属（鉴权在服务端）。
         样式沿用上面那枚 pill：本单不涉视觉，零新增色值。 -->
    <UiButton
      v-if="face.action"
      class="queue-retry"
      size="sm"
      data-testid="queue-action"
      :data-action="face.action.kind"
      @click="emit('action', face.action)"
    >{{ face.action.label }}</UiButton>
    <!-- R268 · 「不排了」走的是排队那一头的取消端点（见本组件文档注释点名的那一条腿）。它与
         输入框旁边那枚「中断本次回答」不是同一条腿：一枚管还没开始跑的，一枚管
         正在往屏上显示的。两枚各说各的，这里不借那一枚，也不把两条腿并成同一句「已取消」。
         样式沿用上面那两枚 pill 与原语的 danger 档：本单零新增色值。 -->
    <UiButton
      v-if="face.cancellable"
      class="queue-retry"
      variant="danger"
      size="sm"
      :loading="Boolean(face.cancelling)"
      data-testid="queue-cancel"
      @click="emit('cancel')"
    >{{ face.cancelRetry ? '再试一次取消' : (face.cancelling ? '取消中…' : '不排了') }}</UiButton>
  </p>
</template>

<style scoped>
.queue-face {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--s-1) var(--s-2);
  margin: 0 0 var(--s-1);
  padding: var(--s-1) var(--s-2);
  border: 1px solid color-mix(in srgb, var(--accent) 40%, var(--border-1));
  border-radius: var(--r-sm);
  background: var(--surface-1);
  font-size: var(--t-xs);
  color: var(--text-2);
}

.queue-headline {
  color: var(--text-1);
}

.queue-detail,
.queue-stats {
  color: var(--text-3);
}

.queue-face--danger {
  border-color: color-mix(in srgb, var(--danger) 45%, var(--border-1));
}

.queue-face--danger .queue-headline {
  color: var(--danger);
}

.queue-face--warn {
  border-color: color-mix(in srgb, var(--warning) 45%, var(--border-1));
}

.queue-face--warn .queue-headline {
  color: var(--warning);
}

.queue-retry {
  padding: 0 var(--s-2);
  border: 1px solid var(--border-2);
  border-radius: var(--r-pill);
  background: var(--surface-2);
  font: inherit;
  font-size: var(--t-xs);
  color: var(--text-1);
  cursor: pointer;
}

.queue-retry:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
</style>