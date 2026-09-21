<script setup>
/**
 * R150 · 排队那张脸（业主计划 v2 §5 第三张脸；后端早给了 event: queued 与两个只读端点）。
 *
 * 每一枚数字都点名它的读数来源：
 *   前面 N 人   GET /queue/status/{request_id} 的 position（1 起，减一才是「前面几个人」）
 *   队列现状    GET /queue/stats 的 queue_length / processing
 *   排不上队    入队那一步的 HTTP 失败（今天只有 queue_unavailable 这一枚真实读数）
 * position 取不到时界面说「读不到」，不补 0，也不按排队人数编一个「队列已满」。
 */
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

const emit = defineEmits(['retry'])
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
    <button
      v-if="face.retryable"
      type="button"
      class="queue-retry"
      data-testid="queue-retry"
      @click="emit('retry')"
    >按原文再问一次</button>
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