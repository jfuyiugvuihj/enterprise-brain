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
 *
 * R46 差格 a 在同一张卡片上补两枚【观测】动作：点开原文＝click，展开这一条详情＝view。
 * 判定、组装、发送、去重一律在 lib/feedback.js 的 ENGAGEMENT 那一族，这里只多长一格态。
 * 两枚都刻意【不改既有节点】——理由不是省事，是别人的判据：
 *   · click 包在既有那枚「打开原文」的 emit 上，模板里那一行一个字没动（R307 的在册钉逐字
 *     钉着那句 @click 与它到 ./ui 的接线）；
 *   · view 用原生 <details>/<summary>，既不多一枚 UiButton（同一枚钉着「三枚原语按钮」的
 *     清单），也不造一枚 role="button" 的 span——那是把键盘与读屏用户留在门外假装做到了。
 * 🔴 记账失败不挡用户看原文：发不出去只是少一枚证据，把原文藏起来才是事故，所以这一路
 * 的发收结果一个字节都不上屏（不发失败脸，也不因为后端拒了就改按钮的可用性）。
 * 题号（thread_id）由父级 ChatPanel 把它那枚 turnKey 传进来；缺它就不发——组件自己不知道
 * "这是哪一道题"，猜一个就是把不同轮次的账并成一本。
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
  EVENT_CLICK,
  EVENT_LABELS,
  EVENT_VIEW,
  engagementEventKey,
  sendDocumentSignal,
  sendEngagementEvent,
  settleFeedback,
  shouldSendEngagement,
  signalLabel,
} from '../lib/feedback.js'
import { classificationLabel, formatDayStamp, scoreLabel } from '../lib/provenance.js'
import { UiButton } from './ui'

const props = defineProps({
  face: {
    type: Object,
    default: null,
  },
  /**
   * 这一轮提问的轮次标识（ChatPanel::turnKey 那一族：m<mid> 或 <会话>#<序号>）。
   * 点击账要能说「是哪一道题里点的」，而这一格只有父级知道；缺它这一路一发都不发。
   */
  threadId: {
    type: String,
    default: '',
  },
})

/**
 * 「打开原文」那枚出口的真 emit。下面同名那层包了 R46a 的记账，模板里读的是包过的那一枚——
 * 于是既有接线（含 R307 钉住的那句字面 @click）一个字节都不必改。
 */
const previewSource = defineEmits(['preview'])

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
/** 展开态与「这一发发过没有」：前者按行存，后者按 (题号·文件名·动作) 那枚键存。 */
const opened = reactive({})
const sentEngagements = reactive(new Set())

const textOf = value => (typeof value === 'string' ? value.trim() : '')
const detailKey = (row, index) => `detail-${index}-${textOf(row && row.sourceId)}`
const detailOpen = (row, index) => Boolean(opened[detailKey(row, index)])
const detailLabel = event => EVENT_LABELS[event] || ''

/** 这一条出处排在第几名：读 face.rows 里的位次，1 起。找不到就不记——名次说不清就不该落账。 */
const rankOf = row => {
  const rows = props.face && Array.isArray(props.face.rows) ? props.face.rows : null
  return rows ? rows.indexOf(row) : -1
}

/**
 * 记一枚动作。发不出去就一发都不发（缺名字、缺题号、名次不成形、这一发已经发过）。
 * 🔴 返回值【不喂给界面】：这一族是观测，不是一次会被追问的业务提交；把丢掉的点击在下一轮
 * 补发，等于替用户记得比他自己更牢。
 */
async function noteEngagement(row, event, rank) {
  const item = {
    filename: rowFilename(row),
    event,
    threadId: textOf(props.threadId),
    rank,
  }
  const key = engagementEventKey(item)
  if (!key || !shouldSendEngagement(sentEngagements, item)) return null
  sentEngagements.add(key)
  return sendEngagementEvent(item)
}

/** 与既有接线同名，所以模板那句 emit('preview', row) 照原样就能把 click 记上：先放行再记账。 */
function emit(event, row) {
  previewSource(event, row)
  if (event !== 'preview') return
  const rank = rankOf(row)
  if (rank >= 0) void noteEngagement(row, EVENT_CLICK, rank + 1)
}

/** 展开这一条详情：第一次展开记一枚 view；折叠再展开不重复记（前端与库里那枚 UNIQUE 各一道）。 */
function onDetailToggle(row, index, event) {
  const key = detailKey(row, index)
  const open = event && event.target ? Boolean(event.target.open) : !opened[key]
  opened[key] = open
  if (open) void noteEngagement(row, EVENT_VIEW, index + 1)
}

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
        <UiButton
          class="source-open"
          variant="ghost"
          size="sm"
          type="button"
          data-testid="source-open"
          :aria-label="`打开原文：${row.filename}`"
          @click="emit('preview', row)"
        ><span class="source-open__text">{{ row.filename }}</span></UiButton>
        <span v-if="row.chunkIndex !== null" class="source-meta" data-testid="source-chunk">第 {{ row.chunkIndex + 1 }} 段</span>
        <span v-if="scoreLabel(row)" class="source-meta" data-testid="source-score">{{ scoreLabel(row) }}</span>
        <span v-if="classificationLabel(row.classification)" class="source-meta" data-testid="source-classification">{{ classificationLabel(row.classification) }}</span>
        <span v-if="row.department" class="source-meta" data-testid="source-department">{{ row.department }}</span>
        <span v-if="row.versionId" class="source-meta" data-testid="source-version">版本 {{ row.versionId }}</span>
        <span v-if="effectiveMoment(row)" class="source-meta" data-testid="source-effective">生效 {{ effectiveMoment(row) }}</span>
        <p v-if="hitSentence(row)" class="source-excerpt" data-testid="source-excerpt">{{ hitSentence(row) }}</p>
        <!--
          R46 差格 a · 展开这一条的详情：第一次展开落一枚 view。
          看得见的那几格全是这一条命中本来就带着的读数（名次 / 出处号 / 相关度），不新造任何
          东西，也不含正文——命中句那一行上面已经画着，这里不重复抄一份。
        -->
        <details
          class="source-detail"
          data-testid="source-detail"
          :open="detailOpen(row, index)"
          @toggle="onDetailToggle(row, index, $event)"
        >
          <summary class="source-detail__summary" data-testid="source-detail-summary">{{ detailLabel(EVENT_VIEW) }}</summary>
          <span class="source-detail__body">
            <span class="source-detail__rank" data-testid="source-detail-rank">本轮第 {{ index + 1 }} 名</span>
            <span v-if="row.sourceId" class="source-detail__id" data-testid="source-detail-id">出处 {{ row.sourceId }}</span>
            <span v-if="scoreLabel(row)" class="source-detail__score" data-testid="source-detail-score">{{ scoreLabel(row) }}</span>
          </span>
        </details>
        <!-- R195 · 一处出处一次评价：两枚互斥，点亮只等真回执；没有撤回那一支（后端没这枚出口）。 -->
        <span
          v-if="rowMarkable(row)"
          class="source-feedback"
          data-testid="source-feedback"
          role="group"
          :aria-label="FEEDBACK_GROUP_LABEL"
          :data-phase="markOf(row).phase"
        >
          <UiButton
            class="source-mark source-mark--accept"
            variant="secondary"
            size="sm"
            type="button"
            data-testid="source-feedback-accept"
            :disabled="propsOf(row, SIGNAL_ACCEPTED).disabled"
            :aria-pressed="propsOf(row, SIGNAL_ACCEPTED).pressed"
            :aria-label="ariaOf(row, SIGNAL_ACCEPTED)"
            @click="markSignal(row, SIGNAL_ACCEPTED)"
          >{{ labelOf(SIGNAL_ACCEPTED) }}</UiButton>
          <UiButton
            class="source-mark source-mark--reject"
            variant="secondary"
            size="sm"
            type="button"
            data-testid="source-feedback-reject"
            :disabled="propsOf(row, SIGNAL_REJECTED).disabled"
            :aria-pressed="propsOf(row, SIGNAL_REJECTED).pressed"
            :aria-label="ariaOf(row, SIGNAL_REJECTED)"
            @click="markSignal(row, SIGNAL_REJECTED)"
          >{{ labelOf(SIGNAL_REJECTED) }}</UiButton>
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

/* R307 · 裸按钮接 UiButton 之后的基线复位。原语给每一档都配了 min-height 与 hover 皮肤，
   而这三枚在 R150/R195 定稿时是「行内链接 + 小胶囊」：既不撑到控件高，也不换 hover 底色。
   下面四条只把它们改回既有 token 值，一枚裸色值都不添；位置刻意排在 [disabled] 与
   [aria-pressed='true'] 那几条之前 —— 点亮态与灰态照旧压过 hover，与接原语前同一张脸。 */
.source-open,
.source-mark {
  min-height: 0;
}

.source-open__text {
  text-decoration: underline;
}

.source-open:hover {
  color: var(--accent);
  background: none;
}

.source-mark:hover {
  border-color: var(--border-2);
  background: var(--surface-2);
  color: var(--text-2);
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

/* R46 差格 a · 展开详情那一行同样只复用既有 token，与下面那句同一理由：theme.css 另有其人。 */
.source-detail {
  flex: 1 1 100%;
}

.source-detail__summary {
  font-size: var(--t-xs);
  color: var(--text-3);
  cursor: pointer;
}

.source-detail__summary:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.source-detail__body {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--s-1) var(--s-2);
  margin-top: var(--s-1);
  font-size: var(--t-xs);
  color: var(--text-3);
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