<script setup>
/**
 * R150 · 出处卡片（业主计划 v2 §5 第一张脸；销 R41 判据③「引用条可点回原文」的欠账）。
 *
 * 模型来自 lib/provenance.js::sourcesFace，本组件【不做判断】：几种读法、哪两句必须分开，
 * 都在纯函数里，所以 node 环境能直接单测措辞，这里只负责把它画出来。
 * 「另有 N 处命中未展示」与「本轮没有检索到可用文档」是两个独立节点（不是拼在同一句里），
 * 客户追问「到底是没查到还是不给我看」时，屏上这两句长得就不一样。
 */
import { classificationLabel, formatDayStamp, scoreLabel } from '../lib/provenance.js'

defineProps({
  face: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['preview'])

/** 命中句/生效日期今天不在 sources 行里（后端那一格还没抄），读取位先留好：出现就上屏。 */
const hitSentence = row => (typeof row?.excerpt === 'string' ? row.excerpt.trim() : '')
const effectiveMoment = row => formatDayStamp(row?.effectiveDate)
</script>

<template>
  <section
    v-if="face"
    class="source-card"
    :class="`source-card--${face.tone}`"
    data-testid="source-card"
    :data-kind="face.kind"
    role="group"
    aria-label="本轮回答的出处"
  >
    <p class="source-headline" data-testid="source-headline">{{ face.headline }}</p>
    <!-- 单独一行：它回答的是「资料在不在」，与上一行的「有几条能看」不是一回事 -->
    <p v-if="face.hiddenLine" class="source-hidden" data-testid="source-hidden-line">{{ face.hiddenLine }}</p>
    <p v-if="face.reason" class="source-reason" data-testid="source-reason">{{ face.reason }}</p>

    <ul v-if="face.searchable" class="source-list" data-testid="source-list">
      <li v-for="(row, index) in face.rows" :key="row.sourceId || `${row.filename}-${index}`" class="source-row">
        <button
          type="button"
          class="source-open"
          data-testid="source-open"
          :aria-label="`打开原文：${row.filename}`"
          @click="emit('preview', row)"
        >{{ row.filename }}</button>
        <span v-if="row.chunkIndex !== null" class="source-meta" data-testid="source-chunk">第 {{ row.chunkIndex + 1 }} 段</span>
        <span v-if="scoreLabel(row)" class="source-meta" data-testid="source-score">{{ scoreLabel(row) }}</span>
        <span v-if="classificationLabel(row.classification)" class="source-meta" data-testid="source-classification">{{ classificationLabel(row.classification) }}</span>
        <span v-if="row.department" class="source-meta" data-testid="source-department">{{ row.department }}</span>
        <span v-if="row.versionId" class="source-meta" data-testid="source-version">版本 {{ row.versionId }}</span>
        <span v-if="effectiveMoment(row)" class="source-meta" data-testid="source-effective">生效 {{ effectiveMoment(row) }}</span>
        <p v-if="hitSentence(row)" class="source-excerpt" data-testid="source-excerpt">{{ hitSentence(row) }}</p>
      </li>
    </ul>

    <p v-if="face.diagnostics && face.diagnostics.length" class="source-diagnostics" data-testid="source-diagnostics">
      {{ face.diagnostics.join('；') }}
    </p>
  </section>
</template>

<style scoped>
.source-card {
  margin: 0 0 var(--s-2);
  padding: var(--s-2) var(--s-3);
  border: 1px solid var(--border-1);
  border-radius: var(--r-md);
  background: var(--surface-1);
}

.source-card--warn {
  border-color: color-mix(in srgb, var(--warning) 45%, var(--border-1));
}

.source-card--danger {
  border-color: color-mix(in srgb, var(--danger) 45%, var(--border-1));
}

.source-card--ok {
  border-color: color-mix(in srgb, var(--success) 35%, var(--border-1));
}

.source-headline {
  margin: 0;
  font-size: var(--t-sm);
  color: var(--text-1);
}

.source-hidden {
  margin: var(--s-1) 0 0;
  font-size: var(--t-sm);
  color: var(--warning);
}

.source-reason {
  margin: var(--s-1) 0 0;
  font-size: var(--t-xs);
  color: var(--text-3);
}

.source-list {
  margin: var(--s-2) 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}

.source-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--s-1) var(--s-2);
}

.source-open {
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  font-size: var(--t-sm);
  color: var(--accent);
  text-decoration: underline;
  cursor: pointer;
}

.source-open:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.source-meta {
  font-size: var(--t-xs);
  color: var(--text-3);
}

.source-excerpt {
  flex: 1 1 100%;
  margin: 0;
  font-size: var(--t-xs);
  color: var(--text-2);
}

.source-diagnostics {
  margin: var(--s-1) 0 0;
  font-size: var(--t-xs);
  color: var(--warning);
}
</style>