<script>
/**
 * HitlPendingRow —— 挂起待办的一行（R168）
 *
 * 这一屏判据②④的"手"都在这枚文件上：批准、驳回、以及跳回产生它的那一轮对话。
 * 它自己是哑的：不发请求、不解释流式响应，只把行数据与父组件算好的结果反馈画出来，
 * 再往上抛三个意图（decide / open）。判定语义全在 HitlPendingPanel.vue 的纯函数里，
 * 一屏两套口径是这仓反复犯过的病（跟进单 §71），这里不再开第三份。
 *
 * 三条写死的规矩：
 *   ① 动作名只从后端来。挂起的步骤名与中文标签都是账本里的值（labels / parked_steps），
 *      后端没给标签时才按步骤名补一份中文，绝不自己发明第三个动作名。
 *   ② 跳不过去就明写，而且为什么跳不过去要分得清（R174 判据②把这道门的判据从本机换成了后端）：
 *      能不能回看由「后端还留着这一条会话吗」说了算，不再由这台浏览器的历史记录说了算 ——
 *      员工把链接发给同事，同事那台机器本来就没有这段历史，按旧口径那条链接就废了。
 *      于是行上两句各说各的事，一格都不许并：REPLAY_NONE（后端与本机都没有）与
 *      REPLAY_LOCAL_ONLY（只有这台浏览器还留着）。两句都由父组件挑，本组件只画挑中的那一句；
 *      一句都不给时兜底走 REPLAY_NONE —— 宁缺不静，绝不放一个点不动的按钮，
 *      也绝不"点开发现是份空会话"（lib/sessions.js 的 switchSession 拿不到那一条时会就地
 *      新建一份同名空会话，那是伪造历史，canOpen 就是把这道门）。
 *   ③ 结果反馈原样上屏。父组件给的是 decisionView() 的成品，face 决定这一行是"办完了"
 *      还是"没办成"，本组件不粉饰：失败就是失败，不写"已完成"。
 *
 * 视觉：只借 theme.css 既有类（.chip）与 var(--*) 令牌，零裸色值；按钮一律 UiButton。
 */
export default { name: 'HitlPendingRow' }

/**
 * parked_steps 的全部取值来自 app/agents/orchestrator.py 的 _HITL_PARKED（chart / export）。
 * 这两条只是"后端没带标签时"的兜底说法，正常路径上 labels 就是后端给的那份。
 */
export const STEP_LABELS = {
  chart: '生成图表',
  export: '导出报告',
}

/** 未知步骤给通用说法，绝不把后端原串画上屏（与 ArtifactList 的类型标签同一口径）。 */
export function stepLabel(step) {
  const key = typeof step === 'string' ? step.trim().toLowerCase() : ''
  return STEP_LABELS[key] || '需要确认的一步'
}

/** 后端 labels 优先；缺了才按步骤名补，两条都没有就是空数组（行上什么动作名也不画）。 */
export function rowLabels(row) {
  const given = Array.isArray(row && row.labels) ? row.labels.filter(Boolean).map(String) : []
  if (given.length) return given
  const steps = Array.isArray(row && row.steps) ? row.steps : []
  return steps.map(stepLabel)
}

/**
 * 这一行的脸：忙碌 > 结果反馈 > 常态。
 * 排这个顺序是因为反馈一旦落地就该盖住按钮状态，让"我刚才那一下成了没成"是屏上最响的一句话。
 */
export function rowFace({ busy = false, outcome = null } = {}) {
  if (busy) return 'busy'
  if (outcome) return outcome.face || 'unknown'
  return 'idle'
}

/** 长 id 屏上只留前 8 位供人对账，完整值在 data-request / data-session 属性里。 */
export function shortId(value) {
  const raw = String(value == null ? '' : value).trim()
  return raw ? raw.slice(0, 8) : ''
}

/** 后端没有这一条、这台浏览器也翻不到：真没有可回看的东西。 */
export const REPLAY_NONE = '这一笔没有可回看的对话：后端说没有这一条会话，这台浏览器里也翻不到，'
  + '所以这一行不给跳转，也不会替你新开一份。'

/** 后端没有、只有这台浏览器还留着：与上面那句不是一回事，单独一句（判据②原话「别并格」）。 */
export const REPLAY_LOCAL_ONLY = '这一条只在这台浏览器里：后端已经没有这一条会话了。换台机器、换个浏览器打开同一串链接就回不去，'
  + '所以这一行仍然不给跳转 —— 要落的那一份正文已经不在了。'
</script>

<script setup>
import { computed } from 'vue'
import { UiButton } from '../ui'
// rowLabels / rowFace / shortId 就长在上面的 <script> 块里：plugin-vue 会把两段合成同一个模块，
// 所以不必（也不该）再 import 一次自己的文件名 —— ArtifactList.vue 同此写法。

const props = defineProps({
  row: { type: Object, required: true },
  canOpen: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  outcome: { type: Object, default: null },
  // 父组件算好的那一格判定（{ canOpen, note, basis }）。判定住在面板里，本组件只画结果 ——
  // 一屏两套「能不能回看」的口径是这仓反复犯过的病，这里不再开第二份。
  replay: { type: Object, default: null },
})

const emit = defineEmits(['decide', 'open'])

const labels = computed(() => rowLabels(props.row))
const face = computed(() => rowFace({ busy: props.busy, outcome: props.outcome }))
const requestShort = computed(() => shortId(props.row.requestId))
// 为什么跳不过去，父组件判完带下来；没带就兜底走 REPLAY_NONE —— 宁可多说一句，也不静默。
const replayText = computed(() => String((props.replay && props.replay.note) || REPLAY_NONE))
const replayBasis = computed(() => String((props.replay && props.replay.basis) || 'local'))
</script>

<template>
  <article
    class="hitl-row"
    data-testid="hitl-row"
    :data-face="face"
    :data-session="row.sessionId"
    :data-request="row.requestId"
  >
    <div class="hitl-row__head">
      <strong class="hitl-row__title">等你拍板</strong>
      <span v-for="(label, index) in labels" :key="index" class="chip">{{ label }}</span>
    </div>

    <p class="hitl-row__meta">
      <span v-if="row.createdAt">挂起于 {{ row.createdAt }}</span>
      <span v-if="row.expiresAt">· 超过 {{ row.expiresAt }} 就不再算挂着</span>
      <span v-if="requestShort" class="hitl-row__trace">请求 #{{ requestShort }}</span>
    </p>

    <div class="hitl-row__actions">
      <UiButton
        variant="primary"
        size="sm"
        :loading="busy"
        label="批准执行"
        data-testid="hitl-approve"
        @click="emit('decide', { row, approved: true })"
      />
      <UiButton
        variant="secondary"
        size="sm"
        :loading="busy"
        label="驳回"
        data-testid="hitl-reject"
        @click="emit('decide', { row, approved: false })"
      />
      <UiButton
        v-if="canOpen"
        variant="ghost"
        size="sm"
        label="回到这一轮对话"
        data-testid="hitl-open"
        @click="emit('open', row)"
      />
    </div>

    <p v-if="!canOpen" class="hitl-row__noturn" data-testid="hitl-no-turn" :data-replay="replayBasis">
      {{ replayText }}
    </p>

    <p v-if="outcome" class="hitl-row__outcome" :data-face="outcome.face" data-testid="hitl-outcome">
      <strong>{{ outcome.title }}</strong>
      <span>{{ outcome.description }}</span>
      <small v-if="outcome.codeLabel" class="hitl-row__code" data-testid="hitl-outcome-code">{{ outcome.codeLabel }}</small>
    </p>
  </article>
</template>

<style scoped>
.hitl-row {
  display: grid;
  gap: var(--s-2);
  padding: var(--s-3);
  border: 1px solid var(--line);
  border-left: 3px solid var(--warning);
  border-radius: var(--r-md);
  background: var(--surface-2);
}

.hitl-row__head,
.hitl-row__meta,
.hitl-row__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
}

.hitl-row__title {
  color: var(--text);
  font-size: var(--t-sm);
  font-weight: 600;
}

.hitl-row__meta {
  color: var(--ink-soft);
  font-size: var(--t-xs);
}

.hitl-row__trace {
  color: var(--ink-faint);
  font-family: var(--font-mono);
  font-size: var(--t-xs);
}

.hitl-row__noturn {
  margin: 0;
  color: var(--muted);
  font-size: var(--t-xs);
  line-height: 1.6;
}

.hitl-row__outcome {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--s-2);
  margin: 0;
  padding: var(--s-2);
  border-radius: var(--r-sm);
  background: var(--surface-3);
  color: var(--text);
  font-size: var(--t-xs);
  line-height: 1.6;
}

.hitl-row__outcome[data-face='ok'] {
  border-left: 3px solid var(--success);
}

.hitl-row__outcome[data-face='failed'] {
  border-left: 3px solid var(--danger);
}

.hitl-row__outcome[data-face='unknown'] {
  border-left: 3px solid var(--warning);
}

.hitl-row__code {
  color: var(--ink-faint);
  font-family: var(--font-mono);
}
</style>
