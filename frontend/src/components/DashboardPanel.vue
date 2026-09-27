<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../lib/api'
import {
  canReadAlerts,
  documentsFailureView,
  loadDashboardSummary,
  loadDashboardTrend,
  SUMMARY_DENIED_TITLE,
  SUMMARY_FAILED_TITLE,
  summaryScopeNote,
  summaryTiles,
  TREND_BUCKET_OPTIONS,
  TREND_DEFAULT_BUCKETS,
  TREND_DEFAULT_PERIOD,
  TREND_FACE_LOADING,
  trendBlankView,
  trendFailureFace,
  trendHasNumbers,
} from '../lib/dashboard'
import { errorDetail, isPermissionDenied } from '../lib/http'
import { alertsNotOpenView, ALERTS_EMPTY_DESCRIPTION, fetchAlerts, mapAlertRow, readFailureView, shapeFailureView } from '../lib/alerts'
import { UiButton, UiEmptyState, UiErrorState, UiLoadingState, UiSelect } from './ui'

// R267：这一屏的输入全部来自服务端。
//   一、不再向 /dashboard 自备 rows：那条算法端点算的是客户端送上来的数，自造的 rows 送进去
//       只会把假话换成「服务端算出来的假话」。四个数字只读服务端那条总览聚合回执。
//   二、「数据趋势」读服务端 R332 那条按期间汇总的序列：取到就摆数字，取不到就说取不到，
//       那几期真的零新增就摆一串服务端说出来的 0 —— 三张脸谁也不许顶替谁，也不画假线。
//   三、「异常与风险」读服务端告警账本，行本身不做二次加工，也不按等级自己造优先级。
const emit = defineEmits(['goto'])
const loading = ref(true)
const error = ref('')
const errorTitle = ref('')
// 驾驶舱整体取不到 vs 取到了但没权限，是两件事；证据卡自己也可能单独失败（R1c）。
const denied = ref(false)
const evidenceError = ref('')
const evidenceDenied = ref(false)
// 异常卡失败脸与空态脸各自独立：没权限、结构坏了、真没有记录，是三句话，
// 谁也不许顶替谁，更不许因为这一格读不到就把整屏拖进错误态。
const alertRows = ref([])
const alertFailure = ref(null)
// R14-A1：总览四个数字的唯一来源。null 是「还没拿到」，拿到之后也不会再退回去数列表的行。
const summary = ref(null)
const metricQuery = ref('住宿费标准')
const metricContext = ref(null)
// 口径的出处与核对状态读服务端回执顶层那两个字段（G02）：
// 「每一篇都解析完了」「这条口径永远可信」这类写死的字串一律不许再出现在这一屏。
const metricEvidence = ref(null)
const metricQueried = ref(false)
const documents = ref([])
// R274（X-6）：文档目录那一发只归这一格的脸。它和整屏的 error 是两个变量——
// 改前它冒到 loadDashboard 的 catch，于是「最新文档没读到」会把四个数字和异常卡一起拖走。
const documentsFailure = ref(null)
// R341：「数据趋势」这一格的取数与脸全部自持。它不并进 loadDashboard 那三条 GET ——
// 那一腿的计数钉的是「四个数字只从聚合来、告警那一发只在有权限时发」，与这一格无关；
// 这一格失败也只换这一格的脸（R274 · X-6 同一条规矩），不把整屏拖进错误态。
const trendPeriod = ref(TREND_DEFAULT_PERIOD)
const trendBuckets = ref(TREND_DEFAULT_BUCKETS)
const trendView = ref(trendBlankView())
// token 闸门（沿用 R314 的手法）：切窗口、重新加载时迟到的回包一律丢掉，
// 上一份 series 不许挂在屏上冒充这一份的结果。
let trendToken = 0

// 总览只摆最近几行；完整列表与处置在各自的屏里。
const RISK_ROW_LIMIT = 4
const RISK_DENIED_TITLE = '这个账号看不到告警账本'
const RISK_FAILED_TITLE = '异常与风险没加载出来'
const RISK_ROWS_NOTE = '这里只摆账本里最近的 4 条，完整列表在「异常与告警」。'
const EVIDENCE_HINT_IDLE = '输入一个指标词，看它的口径由谁登记、有没有和制度文件核对过。'
const EVIDENCE_HINT_NO_MATCH = '这个问题没有匹配到已登记的指标口径，所以这里没有出处可显示。'

const quickActions = [
  { id: 'docs', icon: 'M12 4v11M7 9l5-5 5 5M5 20h14', label: '上传文档' },
  { id: 'data', icon: 'M5 5h14v14H5zM8 16V9M12 16V7M16 16v-4', label: '数据分析' },
  { id: 'insights', icon: 'M12 3a4 4 0 0 0-2 7.46V13H8v2h2v2h4v-2h2v-2h-2v-2.54A4 4 0 0 0 12 3Z', label: '新建洞察' },
  { id: 'approval', icon: 'M6 4h12v16H6zM9 9h6M9 13h6M9 17h3M5 12l3 3 6-7', label: '发起审批' },
]

const scopeNote = computed(() => summaryScopeNote(summary.value?.generatedFor))
// 这一格有没有服务端回传的数字，决定上面那块诚实牌挂不挂；判据在 lib，面板不长第二处。
const trendReal = computed(() => trendHasNumbers(trendView.value))
const trendFailure = computed(() => trendFailureFace(trendView.value))
const trendLoading = computed(() => trendView.value.face === TREND_FACE_LOADING)
// 卡头那一句跟着真实状态走：取到了就说服务端回的那几期，没取到就只说这一格要什么数，
// 不替服务端预支一个窗口长度。
const trendHeadNote = computed(() => (trendReal.value
  ? `${trendView.value.windowLabel}的新增条目数，不是金额`
  : '按期间汇总的新增条目数，不是金额'))
// R14-A1：标签、数值、副文案与口径提示全部来自聚合响应，这里只补图标、配色与点击落点。
// 原先每张卡还自带一条画死的迷你折线与柱状装饰：那不是数据，是假的趋势暗示，一并删掉。
const tileLooks = {
  documents: { icon: 'M6 3h8l4 4v14H6zM14 3v5h5M9 13h6M9 17h6', tone: 'blue', target: 'docs' },
  datasets: { icon: 'M5 5h14v14H5zM8 16V9M12 16V7M16 16v-4', tone: 'cyan', target: 'data' },
  pendingApprovals: { icon: 'M12 3 19 7v6c0 4-3 6.5-7 8-4-1.5-7-4-7-8V7zM9 12l2 2 4-4', tone: 'green', target: 'approval' },
  alerts: { icon: 'M12 3a4 4 0 0 0-2 7.46V13H8v2h2v2h4v-2h2v-2h-2v-2.54A4 4 0 0 0 12 3Z', tone: 'violet', target: 'insights' },
}
const kpis = computed(() => summaryTiles(summary.value)
  .map(tile => ({ ...tileLooks[tile.id], ...tile })))

/** 后端状态键归一：只认那几个取值，认不下一律走「未知」那张脸，不替后端编一个取值。 */
function keyOf(value) {
  return typeof value === 'string' ? value.trim().toLowerCase() : ''
}

function textOf(value) {
  return typeof value === 'string' ? value.trim() : ''
}

// parse_status 的四档取值出自后端文档目录的 PARSE_STATUSES：pending / parsing / ready / failed。
// 一行都没解析成功就写着「已解析」，是这一屏原先第二严重的假话（G02）。
const PARSE_STATUS_TEXT = {
  pending: '排队待解析',
  parsing: '正在解析',
  ready: '已解析',
  failed: '解析失败',
}
const PARSE_STATUS_UNKNOWN_TEXT = '解析状态未知'

function parseStatusText(row) {
  return PARSE_STATUS_TEXT[keyOf(row?.parse_status)] || PARSE_STATUS_UNKNOWN_TEXT
}

// index_status 是另一件事，而且契约允许整个键缺席（索引状态这一列落地之前入库的行根本没判过）。
// 缺席只能读成「没记录过」：画成「未索引」就是替后端做了一个它没做过的决定。
const INDEX_STATUS_TEXT = {
  indexed: '已入知识库索引',
  excluded: '未索引',
  unknown: '索引状态未知',
}
const INDEX_STATUS_UNRECORDED_TEXT = '索引状态未记录'

function indexStatusText(row) {
  return INDEX_STATUS_TEXT[keyOf(row?.index_status)] || INDEX_STATUS_UNRECORDED_TEXT
}

// 口径出处的两种取值：指标定义表的行、代码注册表的行。除此之外只说「未知」。
const DEFINITION_SOURCE_TEXT = {
  metric_definitions: '指标定义表',
  code_registry: '代码语义注册表',
}
const DEFINITION_SOURCE_UNKNOWN_TEXT = '出处未知'
const DEFINITION_UNKNOWN_VERDICT = '出处与核对状态未知'

const evidenceWarnings = computed(() => {
  const warnings = metricContext.value?.warnings
  return Array.isArray(warnings) ? warnings.filter(item => textOf(item)) : []
})
const evidenceWarningText = computed(() => evidenceWarnings.value.join('；'))
// 「已核对」要同时满足两件事：服务端说这条定义与制度文件核对过，且没有留下任何警告。
// 缺一就不给那颗绿标——绿在这里是「可以放心」的意思，不能白给。
const evidenceVerified = computed(() => metricEvidence.value?.provenance?.verified_against_documents === true
  && evidenceWarnings.value.length === 0)
const evidenceVerdictText = computed(() => {
  const evidence = metricEvidence.value
  // 出处和核对状态两样都没回：这既是「不知道」，也不许读成「没警告就是可信」。
  if (!evidence || (!evidence.definitionSource && !evidence.provenance)) return DEFINITION_UNKNOWN_VERDICT
  return evidenceWarnings.value.length ? '未与制度文件核对' : '核对状态未知'
})
const evidenceSourceText = computed(() => {
  const provenance = metricEvidence.value?.provenance
  const verifiedDocument = textOf(provenance?.verified_document)
  if (evidenceVerified.value && verifiedDocument) return `依据：${verifiedDocument}`
  const source = DEFINITION_SOURCE_TEXT[keyOf(metricEvidence.value?.definitionSource)]
  const file = textOf(metricContext.value?.source_file)
  if (!source) return file ? `${DEFINITION_SOURCE_UNKNOWN_TEXT} · ${file}` : DEFINITION_SOURCE_UNKNOWN_TEXT
  return file ? `出处：${source} · ${file}` : `出处：${source}`
})
const evidenceHintText = computed(() => (metricQueried.value ? EVIDENCE_HINT_NO_MATCH : EVIDENCE_HINT_IDLE))

function documentName(item) {
  return typeof item === 'string' ? item : item.filename
}

async function loadDashboard() {
  loading.value = true
  error.value = ''
  errorTitle.value = ''
  denied.value = false
  try {
    // 四个数字先落地：聚合取不到就整块报错，不拿列表长度补一个「看起来对」的数（R14）。
    const result = await loadDashboardSummary()
    if (!result.ok) {
      summary.value = null
      denied.value = result.denied
      errorTitle.value = result.title
      error.value = result.description
      return
    }
    summary.value = result.metrics
    await loadOverviewCards()
  } catch (err) {
    denied.value = isPermissionDenied(err)
    errorTitle.value = denied.value ? SUMMARY_DENIED_TITLE : SUMMARY_FAILED_TITLE
    error.value = errorDetail(err, '经营驾驶舱加载失败')
  } finally {
    loading.value = false
  }
}

// 列表回来什么就摆什么：行本身只用于展示，不参与任何数字——页长一截断就静默变小的那种数是错的。
async function loadOverviewCards() {
  await loadDocumentRows()
  await loadRiskRows()
}

/**
 * 「最新文档」的取数：失败就地换脸，不冒泡（R274 · X-6）。
 *
 * 改前这一发 500 会把整屏拖进错误态，而且因为异常卡在它后面，连告警账本都不再发请求；
 * 现在四个数字、异常卡、口径卡各自照旧，只有这一格说「没加载出来」。
 * 🚫 这一格不许因为「反正列表空着也是空着」回落成空态：读不到与没有是两句话。
 */
async function loadDocumentRows() {
  documentsFailure.value = null
  try {
    const docsResponse = await api.get('/documents/catalog')
    documents.value = docsResponse.data.documents || []
  } catch (err) {
    documents.value = []
    documentsFailure.value = documentsFailureView(err)
  }
}

/**
 * 告警账本按登录者可见范围回传，且已按 id 倒序（最新在前）：这里只截前四行，不重排。
 *
 * R285（X-2）：这一发只在「这个账号确实读得到告警」时发。聚合回执把 alerts 键整个省掉就是
 * 没有告警读取权（判据在 lib/dashboard.js 的 canReadAlerts，与告警数字位同一枚），而
 * GET /alerts 过同一条权限门，于是那一发每次必 403 —— 白打。不发的那一格照旧说话：
 * 🚫 不许让它掉回下面的空态，「这一屏不给这个账号看」与「当前没有异常线索」是两句话。
 */
async function loadRiskRows() {
  alertFailure.value = null
  if (!canReadAlerts(summary.value)) {
    alertRows.value = []
    alertFailure.value = alertsNotOpenView({ deniedTitle: RISK_DENIED_TITLE })
    return
  }
  try {
    const rows = await fetchAlerts()
    if (!rows) {
      alertRows.value = []
      alertFailure.value = shapeFailureView(RISK_FAILED_TITLE)
      return
    }
    alertRows.value = rows.slice(0, RISK_ROW_LIMIT).map(mapAlertRow)
  } catch (err) {
    alertRows.value = []
    alertFailure.value = readFailureView(err, { deniedTitle: RISK_DENIED_TITLE, failedTitle: RISK_FAILED_TITLE })
  }
}

/**
 * 期间序列的取数：参数原样交给服务端，窗口长度不由前端截断；每一发都先把屏清成 loading，
 * 于是「正在取下一份」与「上一份的结果」不可能同时在屏上。
 */
async function loadTrend() {
  const mine = ++trendToken
  trendView.value = trendBlankView(TREND_FACE_LOADING)
  const next = await loadDashboardTrend({ period: trendPeriod.value, buckets: trendBuckets.value })
  if (mine !== trendToken) return
  trendView.value = next
}

function setTrendPeriod(period) {
  if (period === trendPeriod.value) return
  trendPeriod.value = period
  loadTrend()
}

function setTrendBuckets(value) {
  const count = Number(value)
  if (count === trendBuckets.value) return
  // 越界的档位不夹、不猜：交给 lib 那一层的参数守门，它会给「参数没有被接受」那张脸。
  trendBuckets.value = Number.isNaN(count) ? value : count
  loadTrend()
}

async function lookupMetric() {
  // 这个 catch 原先把错误整个吞掉，于是「查失败了」和「还没查」都长成
  // 「查询指标口径后显示证据」那一句空话——R1(c) 要拆的就是这种同脸。
  evidenceError.value = ''
  evidenceDenied.value = false
  metricQueried.value = true
  try {
    const response = await api.post('/semantics/match', { question: metricQuery.value })
    const payload = response.data && typeof response.data === 'object' ? response.data : {}
    metricContext.value = payload.context || null
    metricEvidence.value = {
      definitionSource: typeof payload.definition_source === 'string' ? payload.definition_source : null,
      provenance: payload.provenance && typeof payload.provenance === 'object' ? payload.provenance : null,
    }
  } catch (err) {
    metricContext.value = null
    metricEvidence.value = null
    evidenceDenied.value = isPermissionDenied(err)
    evidenceError.value = evidenceDenied.value
      ? '当前账号没有查询指标口径的权限，请联系管理员开通。'
      : errorDetail(err, '指标口径查询失败')
  }
}

// 整屏重取：四个数字那一腿与这一格各自取各自的数，趋势这一发排在聚合成功之后 ——
// 聚合都读不到时整屏是错误脸，那一格本来也不在屏上。
async function reloadScreen() {
  await loadDashboard()
  if (!error.value) await loadTrend()
}

onMounted(async () => {
  await loadDashboard()
  await lookupMetric()
  await loadTrend()
})
</script>

<template>
  <div class="dashboard-panel reference-dashboard" data-testid="dashboard-panel">
    <UiLoadingState v-if="loading" label="正在加载经营数据" />
    <UiErrorState
      v-else-if="error"
      :title="errorTitle"
      :description="error"
      :retryable="!denied"
      retry-text="重新加载"
      :busy="loading"
      @retry="reloadScreen"
    />

    <template v-else>
      <!-- 诚实牌：这一屏还有哪一格不是真数据，就用这一句说给员工听；实现细节不上屏（G13）。 -->
      <!-- 诚实牌只在这一格还没有服务端数字时挂着：R332 已经把按期间汇总的序列交出来了，
           再写「服务端还没提供」就是替服务端说谎；数字一上屏，这块牌自己收掉。 -->
      <aside v-if="!trendReal" class="demo-flag-row" data-testid="dashboard-demo-flag">
        <span class="demo-flag">演示数据</span>
        <span class="demo-note">「数据趋势」这一格此刻还没有服务端回传的数字：没有数字就不画线、也不放金额刻度。上面四个数字、下面的异常行、文档行与口径出处都读自服务端，按登录者可见范围计算。</span>
      </aside>

      <section class="kpi-grid" data-testid="dashboard-kpis" aria-describedby="dashboard-scope-note">
        <button
          v-for="item in kpis"
          :key="item.id"
          type="button"
          :class="['reference-kpi', `tone-${item.tone}`]"
          :data-testid="`dashboard-kpi-${item.id}`"
          :data-alert-state="item.state"
          :data-target="item.target"
          :title="item.hint"
          @click="emit('goto', item.target)"
        >
          <span class="kpi-icon">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="item.icon" /></svg>
          </span>
          <span class="kpi-copy">
            <small>{{ item.label }}</small>
            <strong>{{ item.value }}</strong>
            <em>{{ item.delta }}</em>
          </span>
        </button>
      </section>
      <p id="dashboard-scope-note" class="demo-note kpi-scope" data-testid="dashboard-scope-note">{{ scopeNote }}</p>

      <section class="dashboard-main-grid">
        <article class="reference-card trend-card" data-testid="dashboard-trend-card">
          <header class="reference-card-head">
            <div>
              <h2>数据趋势</h2>
              <p>{{ trendHeadNote }}</p>
            </div>
            <UiButton size="sm" variant="ghost" label="去上传数据 ›" @click="emit('goto', 'data')" />
          </header>
          <div class="trend-window-tools" data-testid="dashboard-trend-tools">
            <UiButton
              size="sm"
              variant="ghost"
              label="按月"
              :aria-pressed="trendPeriod === 'month' ? 'true' : 'false'"
              @click="setTrendPeriod('month')"
            />
            <UiButton
              size="sm"
              variant="ghost"
              label="按周"
              :aria-pressed="trendPeriod === 'week' ? 'true' : 'false'"
              @click="setTrendPeriod('week')"
            />
            <UiSelect
              size="sm"
              :block="false"
              label="窗口"
              :model-value="trendBuckets"
              :options="TREND_BUCKET_OPTIONS"
              @change="setTrendBuckets"
            />
          </div>
          <UiLoadingState v-if="trendLoading" :label="trendView.text" size="sm" :rows="2" dense />
          <div v-else-if="trendFailure" class="trend-failure" data-testid="dashboard-trend-failed">
            <UiErrorState
              :title="trendView.title"
              :description="trendView.description"
              :retryable="trendView.retryable"
              retry-text="重新加载"
              dense
              @retry="loadTrend"
            />
          </div>
          <p v-else-if="!trendReal" class="demo-note" data-testid="dashboard-trend-empty">{{ trendView.text }}</p>
          <div v-else class="trend-body" data-testid="dashboard-trend-ready">
            <div class="trend-scroll">
              <table class="trend-table" data-testid="dashboard-trend-table">
                <caption class="trend-caption">
                  新增条目数 · {{ trendView.windowLabel }} · 服务端自报时区 {{ trendView.timeZone }}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">期间</th>
                    <th scope="col">新增文档（条）</th>
                    <th scope="col">其中已解析（条）</th>
                    <th scope="col">新增数据集（个）</th>
                    <th v-if="trendView.alertsColumn" scope="col">新增告警（条）</th>
                    <th v-if="trendView.alertsColumn" scope="col">其中未闭环（条）</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in trendView.rows" :key="row.bucket" data-testid="dashboard-trend-row">
                    <th scope="row">{{ row.label }}</th>
                    <td class="trend-cell-count">
                      <span class="trend-bar" aria-hidden="true"><i :style="{ width: row.documentsWidth }"></i></span>
                      <b data-testid="dashboard-trend-documents">{{ row.documents }}</b>
                    </td>
                    <td class="trend-cell-count" data-testid="dashboard-trend-ready-count">{{ row.documentsReady }}</td>
                    <td class="trend-cell-count" data-testid="dashboard-trend-datasets">{{ row.datasets }}</td>
                    <td v-if="trendView.alertsColumn" class="trend-cell-count" data-testid="dashboard-trend-alerts">{{ row.alerts }}</td>
                    <td v-if="trendView.alertsColumn" class="trend-cell-count" data-testid="dashboard-trend-alerts-open">{{ row.alertsOpen }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="demo-note trend-alerts-note" data-testid="dashboard-trend-alerts-note">{{ trendView.alertsNote }}</p>
            <ul class="trend-notes" data-testid="dashboard-trend-notes">
              <li v-for="(note, index) in trendView.notes" :key="index">{{ note }}</li>
            </ul>
          </div>
        </article>

        <article class="reference-card risk-card" data-testid="dashboard-risk-card">
          <header class="reference-card-head">
            <div><h2>异常与风险</h2><p>服务端告警账本里最近的记录</p></div>
            <button type="button" @click="emit('goto', 'insights')">查看全部 ›</button>
          </header>
          <UiErrorState
            v-if="alertFailure"
            :title="alertFailure.title"
            :description="alertFailure.description"
            :code-label="alertFailure.codeLabel"
            :retryable="alertFailure.retryable"
            retry-text="重新加载"
            dense
            @retry="loadRiskRows"
          />
          <div v-else-if="alertRows.length" class="risk-list">
            <button
              v-for="(item, index) in alertRows"
              :key="item.id || `row-${index}`"
              type="button"
              class="risk-item"
              data-testid="dashboard-risk-row"
              @click="emit('goto', 'insights')"
            >
              <span class="risk-icon">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="m12 4 8 4v5c0 3.8-2.6 6.4-8 8-5.4-1.6-8-4.2-8-8V8zM12 9v4M12 16v.01" />
                </svg>
              </span>
              <span class="risk-copy"><strong>{{ item.message }}</strong></span>
              <span class="risk-time">{{ item.createdAt }}</span>
            </button>
            <p class="demo-note">{{ RISK_ROWS_NOTE }}</p>
          </div>
          <UiEmptyState v-else title="当前没有异常线索" :description="ALERTS_EMPTY_DESCRIPTION" dense />
        </article>
      </section>

      <section class="dashboard-bottom-grid">
        <article class="reference-card list-card">
          <header class="reference-card-head">
            <h2>最新文档</h2>
            <button type="button" @click="emit('goto', 'docs')">查看全部 ›</button>
          </header>
          <UiErrorState
            v-if="documentsFailure"
            :title="documentsFailure.title"
            :description="documentsFailure.description"
            :retryable="!documentsFailure.denied"
            retry-text="重新加载"
            dense
            @retry="loadDocumentRows"
          />
          <div v-else-if="documents.length" class="reference-list">
            <button v-for="item in documents.slice(0, 3)" :key="documentName(item)" type="button" class="reference-list-row" data-testid="dashboard-doc-row" @click="emit('goto', 'docs')">
              <span class="row-icon">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6zM14 3v5h5M9 13h6M9 17h6" /></svg>
              </span>
              <span>
                <strong>{{ documentName(item) }}</strong>
                <small data-testid="dashboard-doc-index">{{ indexStatusText(item) }}</small>
              </span>
              <span class="chip" data-testid="dashboard-doc-parse">{{ parseStatusText(item) }}</span>
            </button>
          </div>
          <UiEmptyState v-else title="上传制度或业务文档后显示在这里" dense />
        </article>

        <article class="reference-card list-card evidence-card">
          <header class="reference-card-head">
            <h2>知识证据</h2>
            <button type="button" @click="emit('goto', 'chat')">查看全部 ›</button>
          </header>
          <UiErrorState
            v-if="evidenceError"
            :title="evidenceDenied ? '没有权限查询指标口径' : '指标口径没查到'"
            :description="evidenceError"
            :retryable="!evidenceDenied"
            retry-text="重新查询"
            dense
            @retry="lookupMetric"
          />
          <div v-else-if="metricContext" class="evidence-main" data-testid="dashboard-evidence">
            <span class="row-icon">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6zM14 3v5h5M9 13h6M9 17h6" /></svg>
            </span>
            <div>
              <strong>{{ metricContext.metric_name }}</strong>
              <small data-testid="dashboard-evidence-source">{{ evidenceSourceText }}</small>
            </div>
            <b v-if="evidenceVerified" data-testid="dashboard-evidence-verified">已按制度核对</b>
            <span v-else class="demo-note" data-testid="dashboard-evidence-unverified" :title="evidenceWarningText || evidenceVerdictText">{{ evidenceVerdictText }}</span>
          </div>
          <UiEmptyState v-else title="查询指标口径后显示证据" :description="evidenceHintText" dense />
          <div class="evidence-query">
            <input v-model="metricQuery" placeholder="查询指标口径" @keyup.enter="lookupMetric" />
            <button type="button" @click="lookupMetric">查询</button>
          </div>
        </article>

        <article class="reference-card quick-card">
          <header class="reference-card-head"><h2>快速操作</h2></header>
          <div class="quick-grid">
            <button v-for="item in quickActions" :key="item.id" type="button" @click="emit('goto', item.id)">
              <span>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="item.icon" /></svg>
              </span>{{ item.label }}
            </button>
          </div>
        </article>
      </section>
    </template>
  </div>
</template>

<style scoped>
/* 口径提示贴在数字下面：只看数字的人也要看得见它是按谁的范围算出来的。 */
.kpi-scope {
  margin-top: -8px;
}

/* 告警位没有数字（没权限 / 读不出来）时，副文案不许借用「一切正常」的那盏绿灯。 */
.reference-kpi[data-alert-state='denied'] .kpi-copy em,
.reference-kpi[data-alert-state='unreadable'] .kpi-copy em {
  color: var(--ink-soft);
}
</style>