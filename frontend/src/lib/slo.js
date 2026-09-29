/**
 * R505 · 「三档目标账」这一屏唯一的取数点与判脸点
 *
 * 病（开工现取，基点 85572c1）：GET /api/v1/slo 在前端零消费者 —— 三枚只读出口里它的读数最不像
 * 「屏」（它交的全是欠账），所以界面上一个接它的地方都没有（rg -nF "/slo" frontend/src 除 </slot>
 * 那种误命中外 0 枚生产命中）。出口早就在树：app/api/v1/observability.py:1145 那条 GET，
 * 读数体是同文件 :1056 的 slo_readout()。本层把它接上，一枚端点都不新增、一格字段都不新造。
 *
 * 🔴 这一屏存在的全部意义是判据 A：不许把「没量过」画成达成。三格机制在源码里就写着，本层只转达：
 *   ① 样本闸不是查询参数。MIN_SLO_SAMPLES（app/api/v1/observability.py:742）由 slo_readout 的
 *      min_samples 形参默认值带出，:1060 那句注释给的理由是「调用方可以调低的下限不算下限」；
 *      所以这一屏连 limit 都不发，屏上印的那枚数是回包里的 sample_floor，不是界面给的。
 *   ② 欠样本时百分位是 null 而不是 0。:1018 与 :1019 在 status 不是 measured 时把 p50_ms /
 *      p95_ms 写成 None —— :749 那段注释说得很直白：骨架对没见过的分布答 0，而一枚 0 毫秒的 P95
 *      是这一模块能造出的最像真的假 SLO。所以屏上读 null 一律画「未记录」，一枚 0 都不许出现。
 *   ③ 目标值整格待填。SLO_TARGET_PENDING（:747）= awaiting_real_samples，:744 那句写明「写死一个
 *      800 毫秒就是编数据」。屏上每一档的目标那一格只有这一句人话，没有数字。
 *
 * blockers 逐条挂出来（判据 A 的后半）：_slo_not_measurable（:1034）在 :1050-1052 交出 [{code, detail}]，
 * code 用后端原名（lane_attribution_absent 那一族属乙半未清），本层一枚都不改名、一枚都不合并；
 * 中文只在词表里给它配一句「这是什么」，词表外的值只说「未登记的判定」，不猜。
 *
 * 三条不变量（钉在 src/lib/__tests__/r505-slo-contract.test.js）：
 *  ① 数只从服务端来：n / required_samples / shortfall / observed_requests / 两枚百分位全是回包读数，
 *     本层不数、不加、不算百分位；唯一的加工是格式化与查词表。
 *  ② 三张失败脸分开留名（判据 D）：403 不向你开放 / 503 存储不可用 / 500 读回失败，另加 401 与
 *     「回包读不出形状」，各一张，不许塌成一句「加载失败」。
 *  ③ 词表封闭：status / target_status / measured_from 三本词表都对照后端字面量，表外只认不下。
 */
import { UNRECORDED, faceOf } from './alerts'
import { errorCodeLabel, errorCodeOf, errorText } from './errcodes'
import { PERMISSION_DENIED, errorDetail, http } from './http'
import { countText, durationText, traceStageLabel } from './traces'

/** 这一屏唯一的一条读腿：app/api/v1/observability.py:1145 那条 GET。 */
export const SLO_PATH = '/slo'

// ==================== 脸谱（判据 D：三张失败脸两两不等） ====================

export const SLO_FACE_LOADING = 'loading'
export const SLO_FACE_READY = 'ready'
export const SLO_FACE_UNAUTHORIZED = 'unauthorized'
export const SLO_FACE_DENIED = 'denied'
export const SLO_FACE_STORAGE = 'storage'
export const SLO_FACE_MALFORMED = 'malformed'
export const SLO_FACE_FAILED = 'failed'

export const SLO_FACES = [
  SLO_FACE_LOADING, SLO_FACE_READY, SLO_FACE_UNAUTHORIZED, SLO_FACE_DENIED,
  SLO_FACE_STORAGE, SLO_FACE_MALFORMED, SLO_FACE_FAILED,
]

/** 后端在册的那枚存储码：app/api/v1/observability.py 没有 503 的文档形状，故只认码不认状态机。 */
export const SLO_STORAGE_CODE = 'storage_unavailable'

export const SLO_LOADING_TEXT = '正在读这份三档目标账'
export const SLO_TITLES = {
  [SLO_FACE_LOADING]: '正在读这份目标账',
  [SLO_FACE_READY]: '',
  [SLO_FACE_UNAUTHORIZED]: '这份目标账要重新登录才读得到',
  [SLO_FACE_DENIED]: '这份目标账不向你开放',
  [SLO_FACE_STORAGE]: '读数落不在这台机器上：存储不可用',
  [SLO_FACE_MALFORMED]: '这份目标账的回包读不出形状',
  [SLO_FACE_FAILED]: '这份目标账没读回来',
}

/** 403 之后必须指出下一步去哪（与 lib/traces.js 同一口径）：重新登录不会让这项权限出现。 */
export const SLO_DENIED_WHERE =
  '这一屏读的出口过的是审计那一项权限，它只登记在管理员与审计人员名下；员工与部门负责人账号打进来'
  + '拿回的就是这一发 403。请让企业管理员在账号权限里核对这一项，再回到这一页重新读取——'
  + '重新登录本身不会让这项权限出现，界面上也没有一处能把样本闸调低。'

// ==================== 封闭词表（表外只认不下，不替后端答） ====================

/** 判定三档：measured 是唯一「真量到了」的一档，其余两档屏上都不许出现百分位数字。 */
export const SLO_STATUS_MEASURED = 'measured'
export const SLO_STATUS_INSUFFICIENT = 'insufficient_samples'
export const SLO_STATUS_NOT_MEASURABLE = 'not_measurable'

export const SLO_STATUS_LABELS = {
  [SLO_STATUS_MEASURED]: '量到了：样本够了，百分位出自服务端那一格',
  [SLO_STATUS_INSUFFICIENT]: '欠样本：读数不足以出百分位，所以这里没有数字',
  [SLO_STATUS_NOT_MEASURABLE]: '不可测：今天没有任何一段程序在产生这一格的样本',
}
export const SLO_STATUS_UNKNOWN = '未登记的判定'

/** 目标值那一格今天只可能是这一句；写数字是乙半的活，不是界面的活。 */
export const SLO_TARGET_PENDING = 'awaiting_real_samples'
export const SLO_TARGET_LABELS = {
  [SLO_TARGET_PENDING]: '目标值待填：还没有人往这一格写过数字',
}
export const SLO_TARGET_UNKNOWN = '未登记的目标状态'

/** 这一格的分布从哪儿来；no_measurement_piece 说的是代码，不是「流量还不够」。 */
export const SLO_SOURCE_LABELS = {
  stage_ledger: '来自进程内的分段账本',
  persisted_trace_events: '来自已落盘的运行事件',
  no_measurement_piece: '没有测量件：再多流量也填不上这一格',
}
export const SLO_SOURCE_UNKNOWN = '未登记的出处'

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

export function sloStatusLabel(status) {
  const key = textOf(status)
  return SLO_STATUS_LABELS[key] || SLO_STATUS_UNKNOWN
}

export function sloTargetLabel(status) {
  const key = textOf(status)
  return SLO_TARGET_LABELS[key] || SLO_TARGET_UNKNOWN
}

export function sloSourceLabel(source) {
  const key = textOf(source)
  return SLO_SOURCE_LABELS[key] || SLO_SOURCE_UNKNOWN
}

// ==================== 读数（回包里的每一格 -> 屏上的每一格） ====================

/**
 * 一枚数字格 -> 屏上的一行。🔴 判据 A 的两格硬规矩都在这枚函数里：
 *  · p50 / p95 是 null 就说「未记录」，绝不因为「0 也是个数」而画 0；
 *  · shortfall 与 required_samples 原样转达，本层不重算「还欠几枚」（那是服务端折好的那一格）。
 */
export function sloNumberView(slot) {
  const source = isRecord(slot) ? slot : {}
  const status = textOf(source.status)
  return {
    key: '',
    label: textOf(source.label),
    population: textOf(source.population),
    measuredFrom: textOf(source.measured_from),
    sourceText: sloSourceLabel(source.measured_from),
    status,
    statusText: sloStatusLabel(status),
    statusRaw: status,
    samples: countText(source.n, '条样本'),
    requiredSamples: countText(source.required_samples, '条'),
    shortfall: countText(source.shortfall, '条'),
    p50Text: durationText(source.p50_ms),
    p95Text: durationText(source.p95_ms),
    targetText: sloTargetLabel(source.target_status),
    targetRaw: textOf(source.target_status),
    /** 目标那一格有数字吗？有就一票否决地画出来（今天永远走不到这一支，画出来就是假话）。 */
    hasTarget: source.target !== null && source.target !== undefined && source.target !== '',
    reason: textOf(source.reason),
    percentileSource: textOf(source.percentile_source),
    blockers: sloBlockerViews(source.blockers),
  }
}

/** blockers 逐条挂出来：code 用后端原名（判据 A 要求留原名），detail 原样转达，本层不合并。 */
export function sloBlockerViews(blockers) {
  if (!Array.isArray(blockers)) return []
  return blockers.map((item, index) => {
    const source = isRecord(item) ? item : {}
    return {
      id: 'blocker-' + index,
      codeName: textOf(source.code),
      detail: textOf(source.detail),
    }
  })
}

/**
 * 一档（问答 / 分析 / 报告）-> 屏上一张卡。
 * numbers 与 stage_numbers 都是「键就是后端那一格的名字」的映射，这里按回包给的键序读，不排序。
 */
export function sloTierViews(report) {
  const tiers = isRecord(report) ? report.tiers : null
  if (!Array.isArray(tiers)) return []
  /** 一个桶（numbers / stage_numbers）里各格交出的原始 blockers，原样收集，不先过一遍视图。 */
  const rawBlockers = bucket => Object.keys(bucket).flatMap(key => {
    const slot = isRecord(bucket[key]) ? bucket[key].blockers : null
    return Array.isArray(slot) ? slot : []
  })
  return tiers.map((tier, index) => {
    const source = isRecord(tier) ? tier : {}
    const numbers = isRecord(source.numbers) ? source.numbers : {}
    const stages = isRecord(source.stage_numbers) ? source.stage_numbers : {}
    return {
      id: textOf(source.lane) || 'tier-' + index,
      lane: textOf(source.lane),
      label: textOf(source.label),
      note: textOf(source.note),
      screenRoute: textOf(isRecord(source.screen) ? source.screen.route : ''),
      screenPath: textOf(isRecord(source.screen) ? source.screen.path : ''),
      screenSource: textOf(isRecord(source.screen) ? source.screen.source : ''),
      endpoints: Array.isArray(source.endpoints) ? source.endpoints.map(item => textOf(item)) : [],
      observedRequests: countText(source.observed_requests, '枚请求窗口'),
      numbers: Object.keys(numbers).map(key => ({ ...sloNumberView(numbers[key]), key })),
      stages: Object.keys(stages).map(key => ({
        ...sloNumberView(stages[key]),
        key,
        label: traceStageLabel(key),
      })),
      // 🔴 判据 A 的后半：这一档的障碍 = 这一档「每一枚目标格 + 每一枚分段格」交出的全部障碍，
      // 逐条挂出来、码名留后端原名。今天后端只在 numbers 那一路带 blockers（_slo_stat :1013-1031
      // 那一格没有），但那是回包的形状，不是界面少读一格的权利：分段明天挂上障碍，屏上就得跟着挂。
      blockerList: sloBlockerViews([...rawBlockers(numbers), ...rawBlockers(stages)]),
    }
  })
}

/**
 * 未归因那一池：它不是任何一档，也不能被当成一档来读（回包自己就这么写）。
 * 屏上画它，是为了让「这台进程今天真有一池数」与「三档各有多少」两件事不互相冒充。
 */
export function sloPoolView(report) {
  const pool = isRecord(report) ? report.unattributed_pool : null
  if (!isRecord(pool)) return null
  return {
    what: textOf(pool.what),
    blockers: sloBlockerViews(pool.blockers),
    endToEnd: sloNumberView(pool.end_to_end),
  }
}

/** 「三档」这个词在仓里撞在三枚枚举上，回包把三枚都交出来了 —— 屏上就逐枚说，不挑一枚当真理。 */
export function sloUnitsView(report) {
  const units = isRecord(report) ? report.units : null
  if (!isRecord(units)) return []
  return Object.keys(units).map(key => {
    const source = isRecord(units[key]) ? units[key] : {}
    const bridge = isRecord(source.bridge_from_product_lane) ? source.bridge_from_product_lane : null
    return {
      id: key,
      ownsTheName: textOf(source.owns_the_name),
      decidedBy: textOf(source.decided_by),
      members: Array.isArray(source.members) ? source.members.map(item => textOf(item)) : [],
      unitOfSlo: source.this_is_the_unit_of_the_slo === true,
      bridge: bridge ? Object.keys(bridge).map(from => from + ' → ' + textOf(bridge[from])) : [],
      bridgeNote: textOf(source.bridge_note),
    }
  })
}

/** 顶栏那一行：schema、样本闸、百分位出处、总体口径 —— 全部是回包原文，这里一个字都不改写。 */
export function sloHeadView(report) {
  const source = isRecord(report) ? report : {}
  return {
    schema: textOf(source.schema),
    sampleFloor: countText(source.sample_floor, '条'),
    targetText: sloTargetLabel(source.target_status),
    percentileSource: textOf(source.percentile_source),
    populationNote: textOf(source.sample_population_note),
    requestedBy: textOf(isRecord(source.requested_by) ? source.requested_by.username : ''),
    requestedRoles: (isRecord(source.requested_by) && Array.isArray(source.requested_by.roles)
      ? source.requested_by.roles.map(item => textOf(item)).filter(item => item)
      : []).join('、'),
    requestedSource: isRecord(source.requested_by) ? textOf(source.requested_by.auth_source) : '',
  }
}

// ==================== 归脸 ====================

export function sloBlankView(face = SLO_FACE_LOADING) {
  const loading = face === SLO_FACE_LOADING
  return {
    face: loading ? SLO_FACE_LOADING : SLO_FACE_FAILED,
    title: loading ? '' : SLO_TITLES[SLO_FACE_FAILED],
    description: loading ? SLO_LOADING_TEXT : '',
    codeLabel: '',
    report: null,
    tiers: [],
    units: [],
    pool: null,
    head: sloHeadView(null),
  }
}

/** 200 那一发：读不出 tiers 就是 malformed，不许当成「三档都是零」。 */
export function sloViewFromResponse(payload) {
  if (!isRecord(payload) || !Array.isArray(payload.tiers)) {
    return {
      face: SLO_FACE_MALFORMED,
      title: SLO_TITLES[SLO_FACE_MALFORMED],
      description: '回包里读不到档位清单那一格：这一屏宁可什么都不画，也不拿一份空对象冒充三档。',
      codeLabel: '',
      report: null,
      tiers: [],
      units: [],
      pool: null,
      head: sloHeadView(null),
    }
  }
  return {
    face: SLO_FACE_READY,
    title: '',
    description: '',
    codeLabel: '',
    report: payload,
    tiers: sloTierViews(payload),
    units: sloUnitsView(payload),
    pool: sloPoolView(payload),
    head: sloHeadView(payload),
  }
}

/**
 * 失败腿：判据只走 errorCodeOf 与 HTTP status 两枚出处（复用 lib/alerts.js::faceOf 那把全仓唯一的尺），
 * 本模块一枚码都不新增；句子仍归 lib/errcodes.js 那本字典。
 */
export function sloViewFromError(err) {
  const status = Number(err && err.response ? err.response.status : err && err.status) || 0
  const code = errorCodeOf(err)
  const face = faceOf({ failed: true, code })
  const label = errorCodeLabel(err)
  const message = errorDetail(err, '')
  const base = {
    face: SLO_FACE_FAILED,
    title: SLO_TITLES[SLO_FACE_FAILED],
    description: message || SLO_TITLES[SLO_FACE_FAILED],
    codeLabel: label,
    report: null,
    tiers: [],
    units: [],
    pool: null,
    head: sloHeadView(null),
  }
  if (face === 'unauthorized' || status === 401) {
    return { ...base, face: SLO_FACE_UNAUTHORIZED, title: SLO_TITLES[SLO_FACE_UNAUTHORIZED] }
  }
  if (face === 'denied' || status === 403 || code === PERMISSION_DENIED) {
    return {
      ...base,
      face: SLO_FACE_DENIED,
      title: SLO_TITLES[SLO_FACE_DENIED],
      description: errorDetail(err, errorText(PERMISSION_DENIED)) + SLO_DENIED_WHERE,
    }
  }
  if (status === 503 || code === SLO_STORAGE_CODE) {
    return {
      ...base,
      face: SLO_FACE_STORAGE,
      title: SLO_TITLES[SLO_FACE_STORAGE],
      description: message || errorText(SLO_STORAGE_CODE),
    }
  }
  return base
}

/** 面板只认 face：这张表给它标题、句子、码名与「该不该给重试」。 */
export function sloFaceView(view) {
  const face = isRecord(view) ? view.face : ''
  return {
    face,
    title: SLO_TITLES[face] || SLO_TITLES[SLO_FACE_FAILED],
    description: (view && view.description) || '',
    codeLabel: (view && view.codeLabel) || '',
    // 该不该给「重试」只由这一枚名单判：读回一次不会让权限长出来，也不会把坏掉的存储修好。
    retryable: SLO_RETRYABLE_FACES.includes(face),
  }
}

/** 只有这两张脸值得再来一次：没权限要改权限、存储不可用要修存储，重放同一发都不改变结果。 */
export const SLO_RETRYABLE_FACES = [SLO_FACE_FAILED, SLO_FACE_MALFORMED]

/** 这一屏唯一的读腿：不带任何查询参数（样本闸不是查询参数，判据 A 的①）。 */
export async function loadSlo() {
  try {
    const response = await http.get(SLO_PATH)
    return sloViewFromResponse(response && response.data)
  } catch (err) {
    return sloViewFromError(err)
  }
}

/** 这一档今天到底有没有一枚可读的百分位：屏上「有数」那一格的唯一判据（不是本层造的判定）。 */
export function sloHasReadableNumber(slot) {
  const view = sloNumberView(slot)
  return view.status === SLO_STATUS_MEASURED && (view.p50Text !== UNRECORDED || view.p95Text !== UNRECORDED)
}

export { UNRECORDED }
