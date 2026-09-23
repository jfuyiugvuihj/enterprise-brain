<script setup>
/**
 * R150 · 出处卡片（业主计划 v2 §5 第一张脸；销 R41 判据③「引用条可点回原文」的欠账）。
 *
 * 模型来自 lib/provenance.js::sourcesFace，本组件【不做判断】：几种读法、哪两句必须分开，
 * 都在纯函数里，所以 node 环境能直接单测措辞，这里只负责把它画出来。
 * 「另有 N 处命中未展示」与「本轮没有检索到可用文档」是两个独立节点（不是拼在同一句里），
 * 客户追问「到底是没查到还是不给我看」时，屏上这两句长得就不一样。
 *
 * R195 在这一族的每一行上补两枚动作（采纳 / 驳回）：员工看完回答终于有一个地方能把
 * 「这条真帮到我」说出口。判定、措辞、发请求一律在 lib/feedback.js，本组件只存态与画；
 * 那两句空话节点（另有 N 处未展示 / 本轮没检索到可用文档）一行按钮都不摆。
 */
import { reactive } from 'vue'
import {
  FEEDBACK_GROUP_LABEL,
  SIGNAL_ACCEPTED,
  SIGNAL_REJECTED,
  feedbackAriaLabel,
  feedbackButtonProps,
  feedbackNotice,
  initialFeedbackState,
  requestFeedback,
  rowFeedbackBlocked,
  rowFilename,
  rowMarkable,
  sendDocumentSignal,
  settleFeedback,
  signalLabel,
} from '../lib/feedback.js'
import { classificationLabel, formatDayStamp, scoreLabel } from '../lib/provenance.js'

defineProps({
  face: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['preview'])

/**
 * 评价态按【文件名】存：后端计数就是一文件一格（document_activity_signals 以 filename 为键），
 * 同一份资料命中两段时两行共用同一笔评价，免得一个人对同一份文件点出两笔账。
 * 五个态谁能点、点亮哪一枚、那句说明怎么讲，全部问 lib/feedback.js，这里不加一层判断。
 */
const marks = reactive({})

const markOf = row => marks[rowFilename(row)] || initialFeedbackState()
const noticeOf = row => feedbackNotice(markOf(row))
const propsOf = (row, signal) => feedbackButtonProps(markOf(row), signal)
const ariaOf = (row, signal) => feedbackAriaLabel(signal, rowFilename(row))
const labelOf = signal => signalLabel(signal)
const blockedOf = row => rowFeedbackBlocked(row)

/**
 * 点一下：发不出去时 requestFeedback 给的是 null，这里就一发都不发。
 * 后端没有撤回的出口，所以记上之后的第二次点击不是撤回，也不许当成反向信号再发一枚。
 */
async function markSignal(row, signal) {
  const key = rowFilename(row)
  const next = requestFeedback(markOf(row), signal)
  if (!key || !next) return null
  marks[key] = next
  marks[key] = settleFeedback(next, await sendDocumentSignal(key, signal))
  return marks[key]
}

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
        <!-- R195 · 一处出处一次评价：两枚互斥，点亮只等真回执；没有撤回那一支（后端没这枚出口）。 -->
        <span
          v-if="rowMarkable(row)"
          class="source-feedback"
          data-testid="source-feedback"
          role="group"
          :aria-label="FEEDBACK_GROUP_LABEL"
          :data-phase="markOf(row).phase"
        >
          <button
            type="button"
            class="source-mark source-mark--accept"
            data-testid="source-feedback-accept"
            :disabled="propsOf(row, SIGNAL_ACCEPTED).disabled"
            :aria-pressed="propsOf(row, SIGNAL_ACCEPTED).pressed"
            :aria-label="ariaOf(row, SIGNAL_ACCEPTED)"
            @click="markSignal(row, SIGNAL_ACCEPTED)"
          >{{ labelOf(SIGNAL_ACCEPTED) }}</button>
          <button
            type="button"
            class="source-mark source-mark--reject"
            data-testid="source-feedback-reject"
            :disabled="propsOf(row, SIGNAL_REJECTED).disabled"
            :aria-pressed="propsOf(row, SIGNAL_REJECTED).pressed"
            :aria-label="ariaOf(row, SIGNAL_REJECTED)"
            @click="markSignal(row, SIGNAL_REJECTED)"
          >{{ labelOf(SIGNAL_REJECTED) }}</button>
          <span v-if="noticeOf(row).headline" class="source-feedback-state" data-testid="source-feedback-state">{{ noticeOf(row).headline }}</span>
          <span v-if="noticeOf(row).detail" class="source-feedback-detail" data-testid="source-feedback-detail">{{ noticeOf(row).detail }}</span>
        </span>
        <span v-else class="source-feedback source-feedback--blocked" data-testid="source-feedback-blocked" data-phase="blocked">
          <span class="source-feedback-state" data-testid="source-feedback-state">{{ blockedOf(row).headline }}</span>
          <span v-if="blockedOf(row).detail" class="source-feedback-detail" data-testid="source-feedback-detail">{{ blockedOf(row).detail }}</span>
        </span>
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

/* R195 · 两枚动作只复用既有 token：theme.css 另有其人正在动，这里一律不新增色值 */
.source-feedback {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--s-1) var(--s-2);
  flex: 1 1 100%;
}

.source-mark {
  padding: 0 var(--s-2);
  border: 1px solid var(--border-2);
  border-radius: var(--r-pill);
  background: var(--surface-2);
  font: inherit;
  font-size: var(--t-xs);
  color: var(--text-2);
  cursor: pointer;
}

.source-mark[disabled] {
  color: var(--text-3);
  cursor: default;
}

.source-mark--accept[aria-pressed='true'] {
  border-color: color-mix(in srgb, var(--success) 55%, var(--border-1));
  color: var(--success);
}

.source-mark--reject[aria-pressed='true'] {
  border-color: color-mix(in srgb, var(--danger) 45%, var(--border-1));
  color: var(--danger);
}

.source-mark:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.source-feedback-state {
  font-size: var(--t-xs);
  color: var(--text-2);
}

.source-feedback-detail {
  flex: 1 1 100%;
  font-size: var(--t-xs);
  color: var(--text-3);
}

.source-feedback[data-phase='recorded'] .source-feedback-state {
  color: var(--success);
}

.source-feedback[data-phase='failed'] .source-feedback-state,
.source-feedback[data-phase='uncertain'] .source-feedback-state,
.source-feedback--blocked .source-feedback-state {
  color: var(--warning);
}
</style>