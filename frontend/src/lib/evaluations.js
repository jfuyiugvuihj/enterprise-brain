/**
 * R505 · 「评测报告」这一屏唯一的取数点与判脸点
 *
 * 病（开工现取，基点 85572c1）：GET /api/v1/evaluations 在前端零消费者（rg -nF "/evaluations"
 * frontend/src 除 </slot> 那种误命中外 0 枚生产命中）。出口早就在树：
 * app/api/v1/observability.py:1159 那条 GET。它交的是「这台机器上存着哪些评测报告、
 * 评测集在哪儿、以及为什么这一屏不能跑分」，本层原样转达，一格都不加。
 *
 * 🔴 这一屏存在的全部意义是判据 B：不许做成能触发跑分的样子。
 *   ① 载荷自己就写着这件事：execution.runs_on_request 恒为 false（observability.py:1181），
 *      reason（:1182-1185）说的是「评测要把整条检索与模型栈按每一题跑一遍，不该塞进一发只读的管理
 *      请求」，command_template（:1186，值出自 :64 那枚常量）是给人在命令行上敲的那一句。
 *      屏上把这三样如实端出来：只读、可选中复制、零枚「立即运行」按钮 —— 摆一枚按下去什么都不会
 *      发生的按钮，就是 R32 明令禁的假控件。
 *   ② reports 为空时后端答的是 status = no_reports（:1173 那一格按 summaries 是否为空分档）：
 *      这一屏走空态脸，说「这台机器上一份评测报告都还没有」，绝不画一枚 0 分。
 *   ③ 报告读不读得出来是报告自己的事：status 有三档（ok / unreadable / too_large，:447 与 :457、
 *      :465 写出来的字面量），unreadable 那一行屏上就写「这份文件读不出指标」，metrics 空对象
 *      不当成「指标都是零」。
 *
 * 三条不变量（钉在 src/lib/__tests__/r505-evaluations-contract.test.js）：
 *  ① 数只从服务端来：case_count、reports_total、metrics 里那些比值与延迟，全是回包读数；
 *     本层不平均、不加权、不排名，唯一的加工是格式化与查词表。
 *  ② 三张失败脸分开留名（判据 D）：403 / 503 / 500 各一张，另加 401 与「回包读不出形状」。
 *     这一屏的 403 与另两屏不同源：它过的是 admin 角色加 evaluation:read 那道闸
 *     （observability.py:1162 走 _require_admin），不是审计那一项。
 *  ③ 词表封闭：报告的 status、source、套件的 exists 都对照后端字面量，表外只说「未登记」。
 */
import { UNRECORDED, faceOf, formatStamp } from './alerts'
import { errorCodeLabel, errorCodeOf, errorText } from './errcodes'
import { PERMISSION_DENIED, errorDetail, http } from './http'
import { countText } from './traces'

/** 这一屏唯一的一条读腿：app/api/v1/observability.py:1159 那条 GET。 */
export const EVALUATIONS_PATH = '/evaluations'

// ==================== 脸谱（判据 D：三张失败脸两两不等） ====================

export const EVAL_FACE_LOADING = 'loading'
export const EVAL_FACE_READY = 'ready'
export const EVAL_FACE_EMPTY = 'empty'
export const EVAL_FACE_UNAUTHORIZED = 'unauthorized'
export const EVAL_FACE_DENIED = 'denied'
export const EVAL_FACE_STORAGE = 'storage'
export const EVAL_FACE_MALFORMED = 'malformed'
export const EVAL_FACE_FAILED = 'failed'

export const EVAL_FACES = [
  EVAL_FACE_LOADING, EVAL_FACE_READY, EVAL_FACE_EMPTY, EVAL_FACE_UNAUTHORIZED,
  EVAL_FACE_DENIED, EVAL_FACE_STORAGE, EVAL_FACE_MALFORMED, EVAL_FACE_FAILED,
]

/** 后端 :1173 那一分档：没有报告不是错误，是它老实交代的状态。 */
export const EVAL_STATUS_NO_REPORTS = 'no_reports'
export const EVAL_STATUS_REPORTS = 'reports_available'

export const EVALUATIONS_STORAGE_CODE = 'storage_unavailable'

export const EVAL_LOADING_TEXT = '正在读这台机器上的评测报告'
export const EVAL_TITLES = {
  [EVAL_FACE_LOADING]: '正在读评测报告',
  [EVAL_FACE_READY]: '',
  [EVAL_FACE_EMPTY]: '这台机器上一份评测报告都还没有',
  [EVAL_FACE_UNAUTHORIZED]: '这些评测报告要重新登录才读得到',
  [EVAL_FACE_DENIED]: '这些评测报告不向你开放',
  [EVAL_FACE_STORAGE]: '报告落不到这台机器上：存储不可用',
  [EVAL_FACE_MALFORMED]: '这份评测回执读不出形状',
  [EVAL_FACE_FAILED]: '评测报告没读回来',
}
export const EVAL_EMPTY_DESCRIPTION =
  '这一屏只按服务端这一发的回执说话：它回的是 status = ' + EVAL_STATUS_NO_REPORTS +
  '，也就是评测报告目录里一份能读的都没有。这不是零分，也不是「评测一切正常」——' +
  '评测要有人在命令行上真跑一轮才会留下文件，这一屏不替它跑。'

/** 403 那句要说清是哪道闸：这一屏过的是管理员角色加评测读权，与审计那一项不是同一道。 */
export const EVAL_DENIED_WHERE =
  '这条出口先要系统管理员角色，再要评测读取这一项权限；员工、部门负责人与审计人员的账号打进来'
  + '拿回的都是这一发 403。请让企业管理员核对角色与这一项权限后再来读——'
  + '重新登录本身不会让这两样出现，界面上也没有一处能把评测跑起来。'

// ==================== 执行那一格（判据 B 的主证） ====================

/** runs_on_request 是三档判定：false 是本单写死的屏上原话，true 是「后端改主意了」，null 是没答。 */
export const EVAL_RUNS_NO = '服务端不会为这一发请求跑评测'
export const EVAL_RUNS_YES = '服务端说这一发请求会直接跑评测：这一屏的只读前提已经不成立了'
export const EVAL_RUNS_UNKNOWN = '回执里没回答这一发会不会跑评测'

export function evaluationExecutionView(execution) {
  const source = isRecord(execution) ? execution : {}
  const runs = typeof source.runs_on_request === 'boolean' ? source.runs_on_request : null
  return {
    runs,
    runsText: runs === null ? EVAL_RUNS_UNKNOWN : (runs ? EVAL_RUNS_YES : EVAL_RUNS_NO),
    reason: textOf(source.reason),
    commandTemplate: textOf(source.command_template),
    reportModule: textOf(source.report_module),
  }
}

// ==================== 封闭词表 ====================

/** 报告那一条自己能不能读出指标：三档都来自 observability.py 里写出的字面量。 */
export const EVAL_REPORT_STATUS_LABELS = {
  ok: '读得出指标',
  unreadable: '这份文件读不出指标：宁可不画，也不拿零冒充',
  too_large: '这份文件超过出口的上限，回执没去读它',
}
export const EVAL_REPORT_STATUS_UNKNOWN = '未登记的报告状态'

/** 这份报告是操作员要的还是镜像自带的（:395 那枚 _report_provenance 交的就是这件事）。 */
export const EVAL_REPORT_SOURCE_LABELS = {
  configured: '操作员配置的目录',
  shipped_default: '镜像自带的那一份',
}
export const EVAL_REPORT_SOURCE_UNKNOWN = '未登记的来源'

export function evalReportStatusLabel(status) {
  const key = textOf(status)
  return EVAL_REPORT_STATUS_LABELS[key] || EVAL_REPORT_STATUS_UNKNOWN
}

export function evalReportSourceLabel(source) {
  const key = textOf(source)
  return EVAL_REPORT_SOURCE_LABELS[key] || EVAL_REPORT_SOURCE_UNKNOWN
}

function isRecord(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

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

/** 布尔三档：是 / 否 / 回执没答。第三档存在的全部意义就是「不许替它答」。 */
export function evalBoolText(value, yes, no) {
  if (typeof value === 'boolean') return value ? yes : no
  return UNRECORDED
}

// ==================== 行模型 ====================

/**
 * 一栏指标：键名一律用后端那一格自己的名字（:419 的 _report_metrics 说得很清楚，
 * 派生出来的键名不在这抄第二份清单），屏上给的是「键名 + 原样读数」。
 * 数值只收成可读位数；非数值（点名的题号清单之类）转成文本原样端出来。
 */
export function evalMetricPairs(metrics) {
  if (!isRecord(metrics)) return []
  return Object.keys(metrics).map(key => {
    const raw = metrics[key]
    const num = numberOrNull(raw)
    return {
      key,
      valueText: num !== null ? String(Math.round(num * 10000) / 10000) : textOf(raw) || UNRECORDED,
      isList: Array.isArray(raw),
      listText: Array.isArray(raw) ? raw.map(item => textOf(item)).join('、') : '',
    }
  })
}

/** 一份报告 -> 屏上一行。size_bytes / modified_at / category_count 都是后端条件性交的格。 */
export function evalReportRow(row) {
  const source = isRecord(row) ? row : {}
  const metrics = evalMetricPairs(source.metrics)
  return {
    id: textOf(source.id) || textOf(source.path) || UNRECORDED,
    path: textOf(source.path),
    sourceRaw: textOf(source.source),
    sourceText: evalReportSourceLabel(source.source),
    statusRaw: textOf(source.status),
    statusText: evalReportStatusLabel(source.status),
    sizeText: countText(source.size_bytes, '字节'),
    modifiedText: formatStamp(source.modified_at),
    categoryText: countText(source.category_count, '类'),
    /** metrics 是空对象：这一格要说「这份文件没交出指标」，不能说「指标都是零」。 */
    hasMetrics: metrics.length > 0,
    metrics,
  }
}

/** 一套评测集 -> 屏上一行。exists=false 时 case_count 是零但那一零不等于「跑过且全错」。 */
export function evalSuiteRow(row) {
  const source = isRecord(row) ? row : {}
  return {
    id: textOf(source.id) || textOf(source.path) || UNRECORDED,
    path: textOf(source.path),
    exists: typeof source.exists === 'boolean' ? source.exists : null,
    existsText: evalBoolText(source.exists, '这台机器上有这份文件', '这台机器上没有这份文件'),
    caseCountText: countText(source.case_count, '题'),
    categories: Array.isArray(source.categories) ? source.categories.map(item => textOf(item)) : [],
    truncatedText: evalBoolText(source.truncated, '题号清单在这一发里被截过', '没截'),
    truncated: typeof source.truncated === 'boolean' ? source.truncated : null,
  }
}

/** 分页那一格：请求过几枚、实际给几枚、有没有被夹住、总数几枚 —— 四格分开说。 */
export function evalLimitsView(limits) {
  const source = isRecord(limits) ? limits : {}
  return {
    maxReports: countText(source.max_reports, '份'),
    appliedLimit: countText(source.applied_limit, '份'),
    requestedLimit: source.requested_limit === null || source.requested_limit === undefined
      ? '这一发没带 limit'
      : countText(source.requested_limit, '份'),
    clampedText: evalBoolText(source.clamped, '被后端夹过', '没夹'),
    clamped: typeof source.clamped === 'boolean' ? source.clamped : null,
  }
}

/** 顶栏那一行：状态、时间、总数与是否截断，全部原样转达。 */
export function evalHeadView(report) {
  const source = isRecord(report) ? report : {}
  return {
    status: textOf(source.status),
    generatedText: formatStamp(source.generated_at),
    reportsTotal: countText(source.reports_total, '份'),
    truncated: typeof source.truncated === 'boolean' ? source.truncated : null,
    truncatedText: evalBoolText(source.truncated,
      '这一发只交出前若干份，报告目录里还有更早的没列出',
      '这一发把回执认得的报告都列出来了'),
    requestedBy: textOf(isRecord(source.requested_by) ? source.requested_by.username : ''),
  }
}

/** 截断那句人话：这一屏不许把「没列全」藏成「就这些」。 */
export function evalTruncationNote(view) {
  const report = isRecord(view) ? view.report : null
  if (!isRecord(report)) return ''
  return view.head.truncatedText
}

// ==================== 归脸 ====================

export function evaluationsBlankView(face = EVAL_FACE_LOADING) {
  const loading = face === EVAL_FACE_LOADING
  return {
    face: loading ? EVAL_FACE_LOADING : EVAL_FACE_FAILED,
    title: loading ? '' : EVAL_TITLES[EVAL_FACE_FAILED],
    description: loading ? EVAL_LOADING_TEXT : '',
    codeLabel: '',
    report: null,
    rows: [],
    suites: [],
    execution: evaluationExecutionView(null),
    limits: evalLimitsView(null),
    head: evalHeadView(null),
  }
}

/** 200 那一发：reports 为空走空态脸（判据 B 的②），读不出 reports 数组才是 malformed。 */
export function evaluationsViewFromResponse(payload) {
  const rows = isRecord(payload) ? payload.reports : undefined
  const suites = isRecord(payload) ? payload.evaluation_sets : undefined
  if (!Array.isArray(rows) || !Array.isArray(suites)) {
    return {
      face: EVAL_FACE_MALFORMED,
      title: EVAL_TITLES[EVAL_FACE_MALFORMED],
      description: '回执里读不到报告清单或评测集清单：这一屏宁可什么都不画，也不拿一份空对象当「没有报告」。',
      codeLabel: '',
      report: null,
      rows: [],
      suites: [],
      execution: evaluationExecutionView(null),
      limits: evalLimitsView(null),
      head: evalHeadView(null),
    }
  }
  const head = evalHeadView(payload)
  const empty = rows.length === 0 || head.status === EVAL_STATUS_NO_REPORTS
  return {
    face: empty ? EVAL_FACE_EMPTY : EVAL_FACE_READY,
    title: empty ? EVAL_TITLES[EVAL_FACE_EMPTY] : '',
    description: empty ? EVAL_EMPTY_DESCRIPTION : '',
    codeLabel: '',
    report: payload,
    rows: rows.map(evalReportRow),
    suites: suites.map(evalSuiteRow),
    execution: evaluationExecutionView(payload.execution),
    limits: evalLimitsView(payload.limits),
    head,
  }
}

/**
 * 失败腿：判据只走 errorCodeOf 与 HTTP status 两枚出处（与 lib/profile.js 同一手法），
 * 本模块一枚码都不新增，句子仍归 lib/errcodes.js 那本字典。
 */
export function evaluationsViewFromError(err) {
  const status = Number(err && err.response ? err.response.status : err && err.status) || 0
  const code = errorCodeOf(err)
  const face = faceOf({ failed: true, code })
  const message = errorDetail(err, '')
  const shell = view => ({
    face: view,
    title: EVAL_TITLES[view],
    description: message,
    codeLabel: errorCodeLabel(err),
    report: null,
    rows: [],
    suites: [],
    execution: evaluationExecutionView(null),
    limits: evalLimitsView(null),
    head: evalHeadView(null),
  })
  if (face === 'unauthorized' || status === 401) return shell(EVAL_FACE_UNAUTHORIZED)
  if (face === 'denied' || status === 403 || code === PERMISSION_DENIED) {
    return {
      ...shell(EVAL_FACE_DENIED),
      description: errorDetail(err, errorText(PERMISSION_DENIED)) + EVAL_DENIED_WHERE,
    }
  }
  if (status === 503 || code === EVALUATIONS_STORAGE_CODE) {
    return { ...shell(EVAL_FACE_STORAGE), description: message || errorText(EVALUATIONS_STORAGE_CODE) }
  }
  return shell(EVAL_FACE_FAILED)
}

/** 只有这两张脸值得再来一次：权限、角色、存储都得有人先动手，重放同一发不改变结果。 */
export const EVAL_RETRYABLE_FACES = [EVAL_FACE_FAILED, EVAL_FACE_MALFORMED]

export function evaluationsFaceView(view) {
  const face = isRecord(view) ? view.face : ''
  return {
    face,
    title: EVAL_TITLES[face] || EVAL_TITLES[EVAL_FACE_FAILED],
    description: (view && view.description) || '',
    codeLabel: (view && view.codeLabel) || '',
    retryable: EVAL_RETRYABLE_FACES.includes(face),
  }
}

/**
 * 查询参数：只把「真的写了的那一格」发出去。
 * 🔴 空串与 NaN 一律不发 —— 后端 _clamped（observability.py:190）会把非法值折回默认，
 * 但界面上自己造一枚空参数等于替操作员宣称「我要的是默认那一档」。
 */
export function evaluationsParams(limit) {
  const num = numberOrNull(limit)
  if (num === null) return undefined
  return { limit: Math.trunc(num) }
}

/** 这一屏唯一的读腿。limit 不传就是没带这一格。 */
export async function loadEvaluations(limit) {
  const params = evaluationsParams(limit)
  const config = params ? { params } : undefined
  try {
    const response = await http.get(EVALUATIONS_PATH, config)
    return evaluationsViewFromResponse(response && response.data)
  } catch (err) {
    return evaluationsViewFromError(err)
  }
}
