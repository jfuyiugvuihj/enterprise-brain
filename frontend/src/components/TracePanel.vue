<!--
  R399 · 「运行留痕」屏壳：把三枚早就在树的后端读腿摆上一屏

  欠的那一格（docs/version-roadmap-and-next-week-plan-2026-09-22.md:264「管理员可以查看一次
  运行的关键 Trace」，:281「页面主要数据不依赖固定演示值」）不在后端：读腿全在树
  （app/api/v1/observability.py:600 与 :684），前端一个消费者都没有。这一枚壳接的就是那三枚，
  零新增端点、零新增字段、零取数逻辑 —— 判码、归脸、句子全在 src/lib/traces.js。

  三格各走各的脸，谁都不替谁说话（判据③）：
    甲 清单  GET /stage-latency（服务端那格 scope 写的是 process）：有哪几枚运行，读的是服务端
        自己折好的 coverage.per_request（app/common/stage_timing.py:674 与 :685），不是前端数样本。
    乙 事件  GET /traces/<编号>：「这一条真没有」是服务端那枚 404 说的（app/api/v1/observability.py:630），
        不是这里猜的；读失败、被关掉、回包读不出，各说各的话，一律不画 0。
    丙 分段  同一条出口带上编号时走 trace 腿（app/api/v1/observability.py:710）：数由已记录的字节
        折出来，它不重跑请求，所以昨天的运行也读得回来。

  入口形状（判据① 走的是甲案）：这一屏是一「屏」，但不占一级入口 —— 逐字照 R316 的 /admin 先例：
  primary:false 派生不出一级导航项，administratorOnly:true 让它只长进管理员那一份入口清单
  （router/index.js 的 administratorNavigation 就是 App.vue:448 侧栏那枚 v-for 的真源，加这一屏
  不改壳层一个字；这一条由 R309 复核在 §G11 里翻案并留了证据）。为什么不挂一级：这三枚出口过的是
  审计那一项权限（app/common/permissions.py:15 与 :16），员工与部门负责人账号打进来拿回来的是 403；
  给他们在侧栏摆一枚按下去只会说「不向你开放」的按钮，就是 R32 明令禁的假控件。

  编号从哪儿来（判据① 要交代的就是这一格）：只有两条路。① 从甲那一格里点 —— 那份清单是服务端给的；
  ② 从地址上带进来 —— /traces?trace=<编号> 是真落点，接的就是后端在
  app/api/v1/observability.py:579 自己写出来的那一格 replay_path 里的编号。屏上没有一处「手输编号」
  的框：把编号做成输入框当主路，等于拿一场
  人肉猜数游戏冒充查询闭环。本仓点过名的反面教材就是 GraphPanel 那几枚手输框：今天现读
  :85-88 四枚 <input> 仍在原位，09-26 复核（docs/handoff/2026-09-26-frontend-gap-recheck.md §G12:167
  与 §G18:230）指着它记的还是同一文件的英文眉标 —— 那半行眉标后来在 R314 并树（commit 40fe97c）里
  删掉了，手输框原样留着，所以这一格欠的东西今天还在。

  三条屏壳级纪律：
  ① 零统计量：屏上没有一个前端数出来的数。条数、合计、占比、百分位全部取自回包里那一格的读数；
     连「一共几条」这句话念的也是服务端那两枚 event_count 与 events_total（判据②，R332 / R341 口径）。
  ② 每一次取数领一枚号：重新加载与离开这一屏都把旧号作废，迟到的那一发既不上屏，也不把上一份清单
     挂在新读数的位置上（手法逐字照 R316 / R341，不发明第二套闸门）。
  ③ 三格各自独立归脸：乙问不出不拖累甲的清单，丙缺样本也不替乙说「没有」。三格一起不供数时屏上是
     三句不同的话，谁都不并成一句含糊话（先例：R385 的缺席台账、R388 的状态账读腿）。

  零新色值（本文件不带样式块，排版只用 theme.css 既有类）、零枚裸 <button> 开标签、动作全部走 ui
  原语且在 script setup 块内 import —— 反向钉在 src/components/__tests__/r399-trace-screen.test.js。
-->
<script>
export default { name: 'TracePanel' }
</script>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  LEDGER_LOADING_TEXT,
  RUNS_FACE_LOADING,
  RUNS_LOADING_TEXT,
  TRACE_LOADING_TEXT,
  cellKind,
  countText,
  durationText,
  eventCountNote,
  ledgerBlankView,
  ledgerIdleView,
  loadRunRoster,
  loadTraceEvents,
  loadTraceLedger,
  missingStageNote,
  percentText,
  runSubjectText,
  runsBlankView,
  traceBlankView,
  traceIdleView,
  verdictText,
} from '../lib/traces'
import { UiButton, UiEmptyState, UiErrorState, UiLoadingState, UiSelect, UiTable } from './ui'

/**
 * 路由在这里是**可选**的（与 ChatPanel.vue:326 同一手法）：单测裸渲染这一屏时没有 router 上下文，
 * useRoute() 回 undefined，全部访问点走可选链，读不到就当地址没写编号 —— 而不是替它猜一枚。
 */
const route = useRoute()
const router = useRouter()

function traceIdFromAddress() {
  const raw = route?.query?.trace
  return typeof raw === 'string' ? raw.trim() : ''
}

/** 甲那一格：运行清单。 */
const roster = ref(runsBlankView())
/** 乙那一格：一条运行的事件回放。 */
const eventCell = ref(traceIdleView())
/** 丙那一格：同一条运行的分段账。 */
const ledgerCell = ref(ledgerIdleView())

const picked = ref(traceIdFromAddress())

let rosterToken = 0
let detailToken = 0

const rosterKind = computed(() => cellKind(roster.value))
const eventKind = computed(() => cellKind(eventCell.value))
const ledgerKind = computed(() => cellKind(ledgerCell.value))
const rosterLoading = computed(() => rosterKind.value === 'loading')
const runRows = computed(() => (rosterKind.value === 'ready' ? roster.value.rows : []))
const runOptions = computed(() => runRows.value.map(row => ({
  value: row.traceId,
  label: row.traceId + ' · 整条走完 ' + durationText(row.endToEndMs),
})))
const eventRows = computed(() => (eventKind.value === 'ready' ? eventCell.value.events : []))
const stageRows = computed(() => (ledgerKind.value === 'ready' ? ledgerCell.value.rows : []))
const subject = computed(() => runSubjectText(picked.value))
const eventNote = computed(() => eventCountNote(eventCell.value))
const ledgerNote = computed(() => missingStageNote(ledgerCell.value.missing))

/** 清单只认服务端给的那串键，这里不排序：一排序就成了「前端替服务端决定先看哪一枚」。 */
const runColumns = [
  { key: 'traceId', label: '运行编号', mono: true },
  { key: 'endToEndMs', label: '整条走完', formatter: value => durationText(value) },
  { key: 'segmentSumMs', label: '分段合计', formatter: value => durationText(value) },
  { key: 'gapMs', label: '没归进分段的差额', formatter: value => durationText(value) },
  { key: 'coverageErrorPct', label: '差额占比', formatter: value => percentText(value) },
  { key: 'closed', label: '两笔账对得平吗', formatter: value => verdictText(value) },
]

/** 事件回放：序号与时序都是服务端记下的那一枚，这里不补号也不重排。 */
const eventColumns = [
  { key: 'sequence', label: '第几步记下', formatter: value => (value ? value + ' 号' : '没编号') },
  { key: 'stampText', label: '时刻', formatter: value => value || '未记录' },
  { key: 'eventLabel', label: '事件' },
  { key: 'statusLabel', label: '状态' },
]

/** 分段账：次数、合计、占比、两个百分位全部原样取自服务端那一格。 */
const stageColumns = [
  { key: 'label', label: '哪一段' },
  { key: 'count', label: '记到几次', formatter: value => countText(value, '次') },
  { key: 'totalMs', label: '合计', formatter: value => durationText(value) },
  { key: 'sharePct', label: '占整条', formatter: value => percentText(value) },
  { key: 'p50Ms', label: '一半的样本在这儿', formatter: value => durationText(value) },
  { key: 'p95Ms', label: '九成五的样本在这儿', formatter: value => durationText(value) },
]

async function loadRoster() {
  const mine = ++rosterToken
  roster.value = runsBlankView(RUNS_FACE_LOADING)
  const next = await loadRunRoster()
  if (mine !== rosterToken) return
  roster.value = next
}

async function loadDetail(traceId) {
  const mine = ++detailToken
  if (!traceId) {
    eventCell.value = traceIdleView()
    ledgerCell.value = ledgerIdleView()
    return
  }
  eventCell.value = traceBlankView(RUNS_FACE_LOADING)
  ledgerCell.value = ledgerBlankView(RUNS_FACE_LOADING)
  // 同一枚编号各发一发，各归各的脸：乙问不出不拖累丙，丙缺样本也不替乙说「没有」。
  const ledgerJob = loadTraceLedger(traceId)
  const eventView = await loadTraceEvents(traceId)
  if (mine !== detailToken) return
  eventCell.value = eventView
  const ledgerView = await ledgerJob
  if (mine !== detailToken) return
  ledgerCell.value = ledgerView
}

// 地址是真相：从侧栏进来、从 ?trace=<编号> 深链进来、后退回上一枚运行，选中的都跟着地址走。
// 写法逐字照 ChatPanel.vue:333 那一枚 watch：地址里那一格是主，屏上选中的是影。
watch(() => route?.query?.trace, () => {
  const next = traceIdFromAddress()
  if (next === picked.value) return
  picked.value = next
  loadDetail(next)
})

/**
 * 「在清单里点中一枚运行」这一动作的全部后果：换成这一枚选中、把编号落回地址、读它那两格。
 * 落回地址是为了「把这枚编号转给别人也能打开」——地址里只多那一格 query，屏名与路径仍由
 * 路由表那一份真源给（routes.test.js 钉着 /traces 这一条记录不多不少）。
 *
 * 它是那枚下拉的 @update:model-value 处理器，不是 watch(picked)：点选是一次显式动作，
 * 摆成事件处理器，屏壳少一层间接，单测也能真调它（SSR 不刷 pre-flush watcher）。
 */
function adoptRun(traceId) {
  const next = typeof traceId === 'string' ? traceId.trim() : ''
  picked.value = next
  if (next && traceIdFromAddress() !== next) {
    router?.replace({ query: { ...route?.query, trace: next } })
  }
  loadDetail(next)
}

onMounted(() => {
  loadRoster()
  if (picked.value) loadDetail(picked.value)
})

onUnmounted(() => {
  // 离开这一屏就把两枚号都作废：迟到的回包不许画到别的屏上。
  rosterToken += 1
  detailToken += 1
})
</script>

<template>
  <div class="panel-shell" data-testid="trace-panel" :data-face="roster.face">
    <header class="panel-head">
      <div>
        <span class="eyebrow">服务端运行账本</span>
        <p>
          这一屏列的是这台服务记下的运行，以及点中一枚运行之后服务端为它交出的事件与分段耗时。
          屏上每一个数字都是回包里那一格的读数：这里不数事件、不加和、也不算百分位。
        </p>
      </div>
      <div>
        <UiButton
          size="sm"
          variant="ghost"
          :loading="rosterLoading"
          label="重新加载清单"
          data-testid="reload-runs"
          @click="loadRoster"
        />
      </div>
    </header>

    <!-- 甲 · 清单格：有哪几枚运行由服务端那一格说；这里只画它给的行。 -->
    <section class="panel-card" data-testid="runs-cell" :data-face="roster.face">
      <div class="section-head">
        <span class="eyebrow">这台服务记下的运行</span>
        <span class="demo-note">这份清单问的是服务进程今天记下的运行账本；它没列出的编号不等于没跑过。</span>
      </div>

      <UiLoadingState v-if="rosterKind === 'loading'" :label="RUNS_LOADING_TEXT" data-testid="runs-loading" />
      <UiErrorState
        v-else-if="rosterKind === 'failure'"
        :title="roster.title"
        :description="roster.description"
        :code-label="roster.codeLabel"
        :retryable="roster.retryable"
        data-testid="runs-failure"
        @retry="loadRoster"
      />
      <UiEmptyState
        v-else-if="rosterKind === 'empty'"
        :title="roster.title"
        :description="roster.description"
        data-testid="runs-empty"
      />
      <template v-else-if="rosterKind === 'ready'">
        <UiSelect
          :model-value="picked"
          label="点选一枚运行"
          :options="runOptions"
          placeholder="先从这份清单里挑一枚"
          data-testid="pick-run"
          @update:model-value="adoptRun"
        />
        <UiTable
          :columns="runColumns"
          :rows="runRows"
          row-key="traceId"
          aria-label="服务端记下的运行"
          data-testid="runs-table"
        />
      </template>
    </section>

    <!-- 乙 · 事件格：三张脸分开画 —— 还没点选 / 这一条真没有 / 问不出。 -->
    <section class="panel-card" data-testid="events-cell" :data-face="eventCell.face">
      <div class="section-head">
        <span class="eyebrow">这一次运行留下的事件</span>
        <span class="demo-note">编号 {{ subject }}</span>
      </div>

      <UiLoadingState v-if="eventKind === 'loading'" :label="TRACE_LOADING_TEXT" data-testid="events-loading" />
      <UiEmptyState
        v-else-if="eventKind === 'idle'"
        :title="eventCell.title"
        :description="eventCell.description"
        data-testid="events-idle"
      />
      <UiEmptyState
        v-else-if="eventKind === 'empty'"
        :title="eventCell.title"
        :description="eventCell.description"
        data-testid="events-absent"
      />
      <UiErrorState
        v-else-if="eventKind === 'failure'"
        :title="eventCell.title"
        :description="eventCell.description"
        :code-label="eventCell.codeLabel"
        :retryable="eventCell.retryable"
        data-testid="events-failure"
        @retry="loadDetail(picked)"
      />
      <template v-else>
        <p class="demo-note" data-testid="events-count">{{ eventNote }}</p>
        <UiTable
          :columns="eventColumns"
          :rows="eventRows"
          row-key="sequence"
          aria-label="一次运行的事件"
          data-testid="events-table"
        >
          <template #cell-eventLabel="{ value, row }">
            <span :data-event-type="row.eventRaw" :data-event-status="row.statusRaw">{{ value }}</span>
          </template>
        </UiTable>
      </template>
    </section>

    <!-- 丙 · 分段格：与乙同一枚编号，但各问各的、各归各的脸。 -->
    <section class="panel-card" data-testid="ledger-cell" :data-face="ledgerCell.face">
      <div class="section-head">
        <span class="eyebrow">这一次运行的分段耗时</span>
        <span class="demo-note">数从已记录的事件里折出来，不重跑这一次运行。</span>
      </div>

      <UiLoadingState v-if="ledgerKind === 'loading'" :label="LEDGER_LOADING_TEXT" data-testid="ledger-loading" />
      <UiEmptyState
        v-else-if="ledgerKind === 'idle'"
        :title="ledgerCell.title"
        :description="ledgerCell.description"
        data-testid="ledger-idle"
      />
      <UiEmptyState
        v-else-if="ledgerKind === 'empty'"
        :title="ledgerCell.title"
        :description="ledgerCell.description"
        data-testid="ledger-empty"
      />
      <UiErrorState
        v-else-if="ledgerKind === 'failure'"
        :title="ledgerCell.title"
        :description="ledgerCell.description"
        :code-label="ledgerCell.codeLabel"
        :retryable="ledgerCell.retryable"
        data-testid="ledger-failure"
        @retry="loadDetail(picked)"
      />
      <template v-else>
        <p v-if="ledgerNote" class="demo-note" data-testid="ledger-note">{{ ledgerNote }}</p>
        <UiTable
          :columns="stageColumns"
          :rows="stageRows"
          row-key="stageKey"
          aria-label="一次运行的分段账"
          data-testid="ledger-table"
        />
      </template>
    </section>
  </div>
</template>
