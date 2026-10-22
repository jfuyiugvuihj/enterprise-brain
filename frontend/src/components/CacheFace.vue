<script setup>
/**
 * R150 · 缓存那张脸（业主计划 v2 §5 第二张脸；R35 交出的三枚字段今天才第一次上屏）。
 *
 * 三种读法必须分开，不许合并成一句「出错了」，也不许合并成一句「都一样」：
 *   live            实时算：后端这枚 text 帧压根没带 cached（chat.py 只有命中路径带）
 *   cached          命中缓存：时间与那句话都是后端给的（cache_note / cache_generated_at）
 *   cached-stale    命中缓存但来源已改版：版本时间出自 GET /documents/{filename}/versions
 *   cached-unknown  命中缓存且无从核对：这一轮没再交出来源清单，界面不猜「大概没改版」
 */
defineProps({
  face: {
    type: Object,
    required: true,
  },
})
</script>

<template>
  <p
    class="cache-face"
    :class="`cache-face--${face.tone}`"
    data-testid="cache-face"
    :data-kind="face.kind"
    role="status"
  >
    <span class="cache-headline" data-testid="cache-headline">{{ face.headline }}</span>
    <span v-if="face.detail" class="cache-detail" data-testid="cache-detail">{{ face.detail }}</span>
  </p>
</template>

<style scoped>
.cache-face {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-1) var(--s-2);
  margin: 0 0 var(--s-1);
  padding: var(--s-1) var(--s-2);
  border: 1px solid var(--border-1);
  border-radius: var(--r-sm);
  background: var(--surface-1);
  font-size: var(--t-xs);
  color: var(--text-2);
}

.cache-headline {
  color: var(--text-1);
}

.cache-detail {
  flex: 1 1 100%;
  color: var(--text-3);
}

.cache-face--warn {
  border-color: color-mix(in srgb, var(--warning) 45%, var(--border-1));
}

.cache-face--warn .cache-headline {
  color: var(--warning);
}

.cache-face--info .cache-headline {
  color: var(--accent);
}
</style>