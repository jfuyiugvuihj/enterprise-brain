/**
 * R399 · 「运行留痕」这一屏的唯一取数点与判脸点
 *
 * V2 那条硬要求（docs/version-roadmap-and-next-week-plan-2026-09-22.md:264「管理员可以查看
 * 一次运行的关键 Trace」）欠的不是后端：两条读腿早就在树，屏上零脸（开工现读：
 * git grep -n traces -- frontend/src 零命中）。本文件把它们接上，一个端点都不新增。
 *
 * 三枚读腿与它们的闸口（取证 = 基点 49489c3 现读）：
 *   事件回放  app/api/v1/observability.py:600  GET /traces/{trace_id}；:603 过 ACTION_AUDIT；
 *             :630 那一格在「记到的事件为零」时答 404 resource_not_found 而不是 200 空数组
 *             —— 所以「这一条运行没留下痕迹」是服务端说出来的话，前端不许替它说，也不许把
 *             自己那一次问不出翻译成这句。回包里的计数（:640 / :641 / :642）原样读，不重算。
 *   运行清单  app/api/v1/observability.py:684  GET /stage-latency，不带 trace_id 时 :714 把
 *             scope 写成 process：这一格答的是「这台服务进程今天的分段账」。清单不来自前端数
 *             样本，而来自服务端自己折好的 coverage.per_request（app/common/stage_timing.py:674
 *             逐枚运行一条账，:685 的 coverage.requests 就是它的枚数）；这里只读它，顺序也照
 *             它给的那串键，不重排、不排序。
 *   分段耗时  同一条出口带 trace_id 时走 app/api/v1/observability.py:710（scope 写成 trace），
 *             数由 :655 那一格从已记录的事件里折出来 —— 它不重跑请求，昨天的运行也读得回来。
 *   开关      进程账本自己带一枚 enabled（app/common/stage_timing.py:956，读的是 :755 那个环境
 *             变量）：它是 false 时这一格叫「不供数」，绝不叫「今天没有运行」。
 *   闸口      app/common/permissions.py:15（admin）与 :16（auditor）名下有 audit:read，
 *             :13（staff）与 :14（manager）没有 ⇒ 员工打这三枚出口拿回来的是 403，不是空列表。
 *
 * 三条不变量（逐枚有钉：src/lib/__tests__/r399-traces-contract.test.js）：
 *  ① 数只从服务端来：屏上每一个数字都是回包里那一格的读数。前端不数事件、不加和、不算百分位、
 *     不排序；唯一的加工是把浮点收成可读位数（格式化），以及把 true / false 说成中文（对账文案）。
 *  ② 三张脸两两不等：真没有（空态）／不供数（关着、读不出形状、坏了）／不向你开放（403），
 *     另加 401 与「还没点选」。任何一张都不许塌进另一张，尤其不许把「问不出」画成 0。
 *  ③ 词表是封闭的：事件名与分段名都对照后端字面量（对账钉直接读 app/** 的源码），词表外的值
 *     只说「未登记」，既不回显后端原串，也不猜一个中文 —— 与 lib/users.js::userRoleLabel 同一口径。
 */
import { faceOf, failureRetryable, formatStamp, listRows, UNRECORDED } from './alerts'
import { errorCodeLabel, errorCodeOf, errorText } from './errcodes'
import { errorDetail, http, PERMISSION_DENIED } from './http'

/**
 * 「未记录」这一句全仓只有一份（lib/alerts.js:213）：本模块 re-export 给屏壳用，
 * 组件里不许再抄第二枚字面量 —— 抄一份就是哪天改口径会漏改一处的开始。
 */
export { UNRECORDED } from './alerts'

// ==================== 出口地址（全站只此一处） ====================

/** 分段账本与运行清单共用这一条出口：app/api/v1/observability.py:684。 */
export const STAGE_LATENCY_PATH = '/stage-latency'
/** 一次运行的事件回放：app/api/v1/observability.py:600。 */
export const TRACE_EVENTS_PREFIX = '/traces/'

/** 服务端给这两格各自盖的名章：app/api/v1/observability.py:714 与 :710 的字面量。 */
export const SCOPE_PROCESS = 'process'
export const SCOPE_TRACE = 'trace'

/** 把一枚运行编号拼成事件回放的请求路径；空编号不拼，调用方先问清楚再发。 */
export function traceEventsPath(traceId) {
  const raw = typeof traceId === 'string' ? traceId.trim() : ''
  if (!raw) return ''
  return TRACE_EVENTS_PREFIX + encodeURIComponent(raw)
}

// ==================== 脸谱 ====================

export const RUNS_FACE_LOADING = 'loading'
export const RUNS_FACE_READY = 'ready'
export const RUNS_FACE_EMPTY = 'empty'
export const RUNS_FACE_OFF = 'off'
export const RUNS_FACE_DENIED = 'denied'
export const RUNS_FACE_UNAUTHORIZED = 'unauthorized'
export const RUNS_FACE_MALFORMED = 'malformed'
export const RUNS_FACE_FAILED = 'failed'
/** 还没点选任何运行：这是「没问」，不是「服务端说没有」，所以它自己一张脸。 */
export const TRACE_FACE_IDLE = 'idle'
/** 服务端答了 404：这一条运行确实没记到事件。它自成一张脸，不与「问不出」共用一句。 */
export const TRACE_FACE_ABSENT = 'absent'

/** 归脸的尺只有一把：这九枚是本模块会交出的全部脸名，多一枚少一枚契约钉就红。 */
export const TRACE_FACES = [
  RUNS_FACE_LOADING, RUNS_FACE_READY, RUNS_FACE_EMPTY, RUNS_FACE_OFF,
  RUNS_FACE_DENIED, RUNS_FACE_UNAUTHORIZED, RUNS_FACE_MALFORMED, RUNS_FACE_FAILED,
  TRACE_FACE_IDLE, TRACE_FACE_ABSENT,
]

/** 这些脸要画失败卡（UiErrorState）；空态与「还没点选」不在其内 —— 那是两张不同的脸。 */
export const FAILURE_FACES = [RUNS_FACE_DENIED, RUNS_FACE_UNAUTHORIZED, RUNS_FACE_OFF, RUNS_FACE_MALFORMED, RUNS_FACE_FAILED]

/** 一句人话都不许重复：同一格里两枚码共用一句话，就是又把它们塌回了一张脸。 */
export const RUNS_LOADING_TEXT = '正在读这台服务记下的运行清单……'
export const RUNS_DENIED_TITLE = '这份运行清单不向你开放'
export const RUNS_UNAUTHORIZED_TITLE = '运行清单要重新登录才读得到'
export const RUNS_OFF_TITLE = '这台服务没在记运行清单'
export const RUNS_MALFORMED_TITLE = '运行清单的回包读不出形状'
export const RUNS_FAILED_TITLE = '运行清单没读到'
export const RUNS_EMPTY_TITLE = '这台服务今天还没记下运行'

export const RUNS_OFF_MESSAGE =
  '服务端答了这一格，并说自己没在记：这里画不出任何运行，是因为那本账关着，不是因为公司今天没有运行。'
export const RUNS_MALFORMED_MESSAGE =
  '服务端答了，但清单那一格不成形：屏上一枚运行都不画，也不替它补一个「零」。'
export const RUNS_EMPTY_MESSAGE =
  '账本在答，只是这一格里一枚运行都没有。等这台服务跑完一次问答，这里才会有第一行。'
export const RUNS_DENIED_WHERE =
  '这三格读的是服务端的运行账本，过的是审计那一项权限；员工与部门负责人账号默认不在它名下。'
  + '请让企业管理员在账号权限里放开审计读取，再回到这一屏重新加载；重新登录本身不会让这项权限出现。'

export const TRACE_IDLE_TITLE = '还没点选哪一次运行'
export const TRACE_IDLE_MESSAGE = '在上面那份清单里挑一枚运行，屏下两格才去读它留下的事件与分段耗时。'
export const TRACE_LOADING_TEXT = '正在读这一次运行留下的事件……'
export const TRACE_ABSENT_TITLE = '这一条运行没留下痕迹'
export const TRACE_ABSENT_MESSAGE =
  '服务端答了：这个编号下一条事件都没记到。它说的是「没记到」，不是「读失败」，也不是「这条运行没跑过」。'
export const TRACE_DENIED_TITLE = '这一次运行不向你开放'
export const TRACE_UNAUTHORIZED_TITLE = '这一次运行要重新登录才读得到'
export const TRACE_MALFORMED_TITLE = '这一次运行的回包读不出形状'
export const TRACE_MALFORMED_MESSAGE =
  '服务端答了，但事件那一格不成形：屏上一条都不画，也不把「读不出」写成「没有」。'
export const TRACE_FAILED_TITLE = '这一次运行没读到'

export const LEDGER_IDLE_TITLE = '这一次运行的分段账还没问'
export const LEDGER_LOADING_TEXT = '正在从已记录的事件里折出这一次运行的分段耗时……'
export const LEDGER_EMPTY_TITLE = '这一次运行没记到分段耗时'
export const LEDGER_EMPTY_MESSAGE =
  '这条运行留下了事件，但服务端说分段样本是零：这一格画不出耗时，也不拿零样本报成一串零毫秒。'
export const LEDGER_MALFORMED_MESSAGE =
  '服务端答了，但分段账那一格读不出形状：这一格一格都不画，也不拿空表冒充它在答。'
export const LEDGER_ABSENT_TITLE = '分段账这一格没读到记录'
export const LEDGER_ABSENT_MESSAGE =
  '服务端答了：这个编号下一条事件都没记到，分段账也就折不出来。这一格说的是「没读到记录」，不是「耗时是零」。'
export const LEDGER_DENIED_TITLE = '这一次运行的分段账不向你开放'
export const LEDGER_UNAUTHORIZED_TITLE = '分段账要重新登录才读得到'
export const LEDGER_MALFORMED_TITLE = '分段账的回包读不出形状'
export const LEDGER_FAILED_TITLE = '分段账没读到'

// ==================== 词表（对照后端字面量，词表外只说未登记） ====================

/**
 * coverage.per_request 每一条账的字段名：那一格开在 app/common/stage_timing.py:674，六枚键在 :675-:680。
 * 这一枚数组是账本不是注释：契约钉拿它逐枚对源码，后端改了名而这里没跟上就红。
 */
export const RUN_BACKEND_FIELDS = [
  'segment_sum_ms', 'end_to_end_ms', 'gap_ms',
  'coverage_error_pct', 'unresolved_overlap_pairs', 'within_one_percent',
]

/** 一条运行事件的字面量词表；出处是 app/** 里那些 event_type 字面量，由契约钉逐枚对账。 */
export const TRACE_EVENT_LABELS = {
  'request.started': '一次请求开始',
  'request.completed': '一次请求完成',
  'request.failed': '一次请求失败',
  'request.cancelled': '一次请求被取消',
  'step.started': '一步开始',
  'step.finished': '一步结束',
  'step.progress': '一步进展',
  'tool.completed': '工具产出折回',
  'tool_call.started': '一次工具调用开始',
  'tool_call.finished': '一次工具调用结束',
  'model.started': '一次模型往返开始',
  'model.finished': '一次模型往返结束',
  'retrieval.completed': '检索完成',
  'agent.result.recorded': '结果登记',
}
/** 词表外的事件名：说认不下，绝不照着猜一个中文，也不把后端原串画上屏。 */
export const TRACE_EVENT_UNKNOWN = '未登记的事件'

/** 分段名词表：封闭集合的出处是 app/common/stage_timing.py:48 那五枚。 */
export const TRACE_STAGE_LABELS = {
  classify: '意图与路由决策',
  rewrite: '多路查询改写',
  retrieve: '检索本体',
  generate: '作答与工具执行',
  reflect: '复审',
}
export const TRACE_STAGE_UNKNOWN = '未登记的分段'

/** 事件状态词表；词表外同样只说「未登记的状态」。 */
export const TRACE_STATUS_LABELS = {
  running: '在跑',
  completed: '完成',
  failed: '失败',
  cancelled: '取消',
  rejected: '被拒',
}
export const TRACE_STATUS_UNKNOWN = '未登记的状态'

/** 服务端那枚「分段合计与端到端是否差在一 percent 内」的三档说法：它没答就不替它答。 */
export const LEDGER_CLOSED_TEXT = '对得平'
export const LEDGER_UNCLOSED_TEXT = '对不平'
export const LEDGER_VERDICT_PENDING_TEXT = '服务端没给这一格的结论'

function textOf(value) {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

function numberOrNull(value) {
  const raw = typeof value === 'string' ? value.trim() : value
  if (raw === '' || raw === null || raw === undefined) return null
  const num = typeof raw === 'number' ? raw : Number(raw)
  return Number.isFinite(num) ? num : null
}

function boolOrNull(value) {
  return typeof value === 'boolean' ? value : null
}

function isRecord(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

/** 词表查名：与 users.js::userRoleLabel 同一口径，词表外只说认不下。 */
export function traceEventLabel(eventType) {
  const key = textOf(eventType)
  return TRACE_EVENT_LABELS[key] || TRACE_EVENT_UNKNOWN
}

export function traceStageLabel(stage) {
  const key = textOf(stage)
  return TRACE_STAGE_LABELS[key] || TRACE_STAGE_UNKNOWN
}

export function traceStatusLabel(status) {
  const key = textOf(status)
  return TRACE_STATUS_LABELS[key] || TRACE_STATUS_UNKNOWN
}

/** 毫秒数只收成可读位数：这是格式化，不是第二道算术，屏上那个数仍是服务端给的那一枚。 */
export function durationText(value) {
  const num = numberOrNull(value)
  if (num === null) return UNRECORDED
  return String(Math.round(num * 100) / 100) + ' 毫秒'
}

export function percentText(value) {
  const num = numberOrNull(value)
  if (num === null) return UNRECORDED
  return String(Math.round(num * 100) / 100) + '%'
}

export function countText(value, unit = '条') {
  const num = numberOrNull(value)
  if (num === null) return UNRECORDED
  return String(num) + ' ' + unit
}

/** 三档判定：true / false / 服务端没答。第三档存在的全部意义就是「不许替它答」。 */
export function verdictText(value) {
  const verdict = boolOrNull(value)
  if (verdict === null) return LEDGER_VERDICT_PENDING_TEXT
  return verdict ? LEDGER_CLOSED_TEXT : LEDGER_UNCLOSED_TEXT
}

/** 这一格该画什么：读表只此一处，模板不许再判一遍码。 */
export function cellKind(view) {
  const face = isRecord(view) ? view.face : ''
  if (face === RUNS_FACE_LOADING) return 'loading'
  if (face === TRACE_FACE_IDLE) return 'idle'
  if (face === RUNS_FACE_EMPTY || face === TRACE_FACE_ABSENT) return 'empty'
  if (face === RUNS_FACE_READY) return 'ready'
  return 'failure'
}

// ==================== 行模型（后端行 -> 视图行，只此一处） ====================

/**
 * coverage.per_request 的一条账 -> 屏上一行。字段一概按 RUN_BACKEND_FIELDS 那几枚取，
 * 取不到留 null（渲染成「未记录」），绝不留 0 —— 0 是一条读数，null 是没读数。
 */
export function mapRunRow(traceId, entry) {
  const source = isRecord(entry) ? entry : {}
  return {
    traceId: textOf(traceId),
    endToEndMs: numberOrNull(source.end_to_end_ms),
    segmentSumMs: numberOrNull(source.segment_sum_ms),
    gapMs: numberOrNull(source.gap_ms),
    coverageErrorPct: numberOrNull(source.coverage_error_pct),
    closed: boolOrNull(source.within_one_percent),
  }
}

/** 一条已记录的事件 -> 屏上一行。序号与时序原样带走，这里不排序、不补号、不数条。 */
export function mapTraceEvent(event) {
  const source = isRecord(event) ? event : {}
  return {
    sequence: textOf(source.sequence),
    stampText: formatStamp(source.timestamp),
    eventLabel: traceEventLabel(source.event_type),
    statusLabel: traceStatusLabel(source.status),
    eventRaw: textOf(source.event_type),
    statusRaw: textOf(source.status),
  }
}

/** stages 那一格里的一段 -> 屏上一行；数字全部原样取自服务端，这里只挑要展示的格。 */
export function mapStageRow(stageKey, entry) {
  const source = isRecord(entry) ? entry : {}
  return {
    stageKey: textOf(stageKey),
    label: traceStageLabel(stageKey),
    count: numberOrNull(source.count),
    totalMs: numberOrNull(source.total_ms),
    sharePct: numberOrNull(source.share_pct),
    p50Ms: numberOrNull(source.p50_ms),
    p95Ms: numberOrNull(source.p95_ms),
  }
}

// ==================== 归脸（句子仍出自 lib/errcodes.js 那本字典） ====================

/**
 * 读取失败 -> 一格的视图。判据只认 errorCodeOf 与 HTTP status 两枚出处（复用
 * lib/alerts.js::faceOf 那把全仓唯一的尺），本模块一枚码都不新增；没权限那句额外并上
 * 「下一步去哪」，与 lib/users.js::usersErrorView 同族写法，不是第二套权限判定。
 */
export function traceReadFailureView(err, { deniedTitle, unauthorizedTitle, failedTitle }) {
  const code = errorCodeOf(err)
  const face = faceOf({ failed: true, code })
  const label = errorCodeLabel(err)
  if (face === 'unauthorized') {
    return {
      face: RUNS_FACE_UNAUTHORIZED,
      title: unauthorizedTitle,
      description: errorDetail(err, errorText(code)),
      codeLabel: '',
      retryable: false,
    }
  }
  if (face === 'denied') {
    return {
      face: RUNS_FACE_DENIED,
      title: deniedTitle,
      description: errorDetail(err, errorText(PERMISSION_DENIED)) + RUNS_DENIED_WHERE,
      codeLabel: label,
      retryable: false,
    }
  }
  return {
    face: RUNS_FACE_FAILED,
    title: failedTitle,
    description: errorDetail(err, failedTitle),
    codeLabel: label,
    retryable: failureRetryable(err),
  }
}

/** 404 归给「真没有」那张脸：这一格由服务端答，前端只是接住它。 */
export function isAbsentError(err) {
  return errorCodeOf(err) === 'resource_not_found'
}

export function runsBlankView(face = RUNS_FACE_LOADING) {
  const loading = face === RUNS_FACE_LOADING
  return {
    face: loading ? RUNS_FACE_LOADING : RUNS_FACE_FAILED,
    title: '',
    description: loading ? RUNS_LOADING_TEXT : '',
    codeLabel: '',
    rows: [],
    retryable: false,
  }
}

export function runsOffView() {
  return {
    face: RUNS_FACE_OFF,
    title: RUNS_OFF_TITLE,
    description: RUNS_OFF_MESSAGE,
    codeLabel: '',
    rows: [],
    retryable: false,
  }
}

export function runsMalformedView() {
  return {
    face: RUNS_FACE_MALFORMED,
    title: RUNS_MALFORMED_TITLE,
    description: RUNS_MALFORMED_MESSAGE,
    codeLabel: '',
    rows: [],
    retryable: true,
  }
}

/**
 * 进程账本的回包 -> 清单那一格。每一步都只读服务端给的那一格；任何一处对不上都归
 * 「读不出形状」，绝不退成空态 —— 空态是服务端亲口说「有这本账，里面是零枚」。
 */
export function runsViewFromReport(report) {
  if (!isRecord(report)) return runsMalformedView()
  if (report.scope !== SCOPE_PROCESS) return runsMalformedView()
  if (typeof report.enabled !== 'boolean') return runsMalformedView()
  if (!report.enabled) return runsOffView()
  const coverage = isRecord(report.coverage) ? report.coverage : null
  if (!coverage) return runsMalformedView()
  const ledger = isRecord(coverage.per_request) ? coverage.per_request : null
  if (!ledger) return runsMalformedView()
  const ids = Object.keys(ledger)
  const requests = numberOrNull(coverage.requests)
  // 服务端自己的枚数与它自己的清单对不上：这是形状漂移，不是「没有运行」。
  if (requests === null || requests !== ids.length) return runsMalformedView()
  if (!ids.length) {
    return {
      face: RUNS_FACE_EMPTY,
      title: RUNS_EMPTY_TITLE,
      description: RUNS_EMPTY_MESSAGE,
      codeLabel: '',
      rows: [],
      retryable: false,
    }
  }
  return {
    face: RUNS_FACE_READY,
    title: '',
    description: '',
    codeLabel: '',
    rows: ids.map(id => mapRunRow(id, ledger[id])),
    retryable: false,
  }
}

export function traceIdleView() {
  return {
    face: TRACE_FACE_IDLE,
    title: TRACE_IDLE_TITLE,
    description: TRACE_IDLE_MESSAGE,
    codeLabel: '',
    events: [],
    eventCount: null,
    eventsTotal: null,
    truncated: null,
    retryable: false,
  }
}

export function traceBlankView(face = RUNS_FACE_LOADING) {
  const loading = face === RUNS_FACE_LOADING
  return {
    ...traceIdleView(),
    face: loading ? RUNS_FACE_LOADING : RUNS_FACE_FAILED,
    title: '',
    description: loading ? TRACE_LOADING_TEXT : '',
  }
}

export function traceAbsentView() {
  return {
    ...traceIdleView(),
    face: TRACE_FACE_ABSENT,
    title: TRACE_ABSENT_TITLE,
    description: TRACE_ABSENT_MESSAGE,
  }
}

export function traceMalformedView() {
  return {
    ...traceIdleView(),
    face: RUNS_FACE_MALFORMED,
    title: TRACE_MALFORMED_TITLE,
    description: TRACE_MALFORMED_MESSAGE,
    retryable: true,
  }
}

/**
 * 事件回放的回包 -> 那一格。app/api/v1/observability.py:638-652 那几枚计数原样读；
 * 它们与事件行对不上时归「读不出形状」，不挑一个自己算出来的数顶上（判据①）。
 */
export function traceViewFromResponse(data) {
  const events = listRows(data, 'events')
  if (!events) return traceMalformedView()
  const eventCount = numberOrNull(data.event_count)
  const eventsTotal = numberOrNull(data.events_total)
  const truncated = boolOrNull(data.truncated)
  if (eventCount === null || eventsTotal === null || truncated === null) return traceMalformedView()
  const serverSaysTruncated = eventsTotal > eventCount
  if (eventCount !== events.length || truncated !== serverSaysTruncated) return traceMalformedView()
  return {
    face: RUNS_FACE_READY,
    title: '',
    description: '',
    codeLabel: '',
    traceId: textOf(data.trace_id),
    events: events.map(mapTraceEvent),
    eventCount,
    eventsTotal,
    truncated,
    retryable: false,
  }
}

export function ledgerIdleView() {
  return {
    face: TRACE_FACE_IDLE,
    title: LEDGER_IDLE_TITLE,
    description: TRACE_IDLE_MESSAGE,
    codeLabel: '',
    rows: [],
    missing: [],
    retryable: false,
  }
}

export function ledgerBlankView(face = RUNS_FACE_LOADING) {
  const loading = face === RUNS_FACE_LOADING
  return {
    ...ledgerIdleView(),
    face: loading ? RUNS_FACE_LOADING : RUNS_FACE_FAILED,
    title: '',
    description: loading ? LEDGER_LOADING_TEXT : '',
  }
}

export function ledgerEmptyView() {
  return {
    ...ledgerIdleView(),
    face: RUNS_FACE_EMPTY,
    title: LEDGER_EMPTY_TITLE,
    description: LEDGER_EMPTY_MESSAGE,
  }
}

export function ledgerMalformedView() {
  return {
    ...ledgerIdleView(),
    face: RUNS_FACE_MALFORMED,
    title: LEDGER_MALFORMED_TITLE,
    description: LEDGER_MALFORMED_MESSAGE,
    retryable: true,
  }
}

/**
 * 单条运行的分段账 -> 那一格。零样本与否只看服务端那枚 sample_count
 * （app/common/stage_timing.py:699），前端不数样本；缺哪几段也照它自己说的
 * missing_stages（:702）念，不替它补一段名字。
 */
export function ledgerViewFromResponse(data) {
  if (!isRecord(data)) return ledgerMalformedView()
  if (data.scope !== SCOPE_TRACE) return ledgerMalformedView()
  const sampleCount = numberOrNull(data.sample_count)
  if (sampleCount === null || sampleCount < 0) return ledgerMalformedView()
  const stages = isRecord(data.stages) ? data.stages : null
  if (!stages || !Object.keys(stages).length) return ledgerMalformedView()
  const missing = Array.isArray(data.missing_stages) ? data.missing_stages.map(key => traceStageLabel(key)) : []
  if (!sampleCount) return { ...ledgerEmptyView(), missing }
  return {
    face: RUNS_FACE_READY,
    title: '',
    description: '',
    codeLabel: '',
    rows: Object.keys(stages).map(key => mapStageRow(key, stages[key])),
    missing,
    retryable: false,
  }
}

// ==================== 三枚读腿（面板只调它们） ====================

/** 清单那一格：GET /stage-latency（scope=process）。 */
export async function loadRunRoster() {
  try {
    const response = await http.get(STAGE_LATENCY_PATH)
    return runsViewFromReport(response && response.data)
  } catch (err) {
    // 失败视图带着空行而不是没有行：面板按 face 分派，这里少一枚键就会让它读到 undefined。
    return { ...traceReadFailureView(err, {
      deniedTitle: RUNS_DENIED_TITLE,
      unauthorizedTitle: RUNS_UNAUTHORIZED_TITLE,
      failedTitle: RUNS_FAILED_TITLE,
    }), rows: [] }
  }
}

/** 事件那一格：GET /traces/{trace_id}。空编号不发请求，也不替服务端答「没有」。 */
export async function loadTraceEvents(traceId) {
  if (!traceEventsPath(traceId)) return traceIdleView()
  try {
    const response = await http.get(traceEventsPath(traceId))
    const view = traceViewFromResponse(response && response.data)
    if (view.face !== RUNS_FACE_READY) return view
    return { ...view, traceId: textOf(traceId) || view.traceId }
  } catch (err) {
    if (isAbsentError(err)) return traceAbsentView()
    const view = traceReadFailureView(err, {
      deniedTitle: TRACE_DENIED_TITLE,
      unauthorizedTitle: TRACE_UNAUTHORIZED_TITLE,
      failedTitle: TRACE_FAILED_TITLE,
    })
    return { ...view, events: [], eventCount: null, eventsTotal: null, truncated: null }
  }
}

/** 分段账那一格：GET /stage-latency?trace_id=。它与事件那一格各自归脸，谁都不替谁说话。 */
export async function loadTraceLedger(traceId) {
  const raw = typeof traceId === 'string' ? traceId.trim() : ''
  if (!raw) return ledgerIdleView()
  try {
    const response = await http.get(STAGE_LATENCY_PATH, { params: { trace_id: raw } })
    return ledgerViewFromResponse(response && response.data)
  } catch (err) {
    if (isAbsentError(err)) {
      return { ...ledgerIdleView(), face: TRACE_FACE_ABSENT, title: LEDGER_ABSENT_TITLE, description: LEDGER_ABSENT_MESSAGE }
    }
    const view = traceReadFailureView(err, {
      deniedTitle: LEDGER_DENIED_TITLE,
      unauthorizedTitle: LEDGER_UNAUTHORIZED_TITLE,
      failedTitle: LEDGER_FAILED_TITLE,
    })
    return { ...view, rows: [], missing: [] }
  }
}

/**
 * 事件那一格的计数句：两个数都是服务端给的读数（app/api/v1/observability.py:640 与 :641），
 * 这里只做中文连接；「没读全」与「问不出」是两句话，谁都不许顶替谁。
 */
export function eventCountNote(view) {
  if (!isRecord(view) || view.face !== RUNS_FACE_READY) return ''
  const total = countText(view.eventsTotal)
  const read = countText(view.eventCount)
  if (view.truncated === true) {
    return '服务端说这一条运行一共记了 ' + total + '，这一屏按它给的上限读出 ' + read + '，剩下的不在这屏上。'
  }
  return '服务端说这一条运行记了 ' + total + '，这一屏读出的 ' + read + ' 就是它交回来的那些。'
}

/** 分段账那一格的缺段句：缺哪几段由服务端那枚 missing_stages 说，这里只把它们念成中文。 */
export function missingStageNote(missing) {
  const names = (Array.isArray(missing) ? missing : []).filter(Boolean)
  if (!names.length) return ''
  return '服务端说这几段没记到样本：' + names.join('、') + '。这一格不替它编一段耗时。'
}

/** 顶栏那一行要说得出「这一格问的是哪一枚运行」：编号是数据，可以上屏，但不是字段名。 */
export function runSubjectText(traceId) {
  return textOf(traceId) || '未点选'
}
