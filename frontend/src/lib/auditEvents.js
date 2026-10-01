/**
 * R505 · 「审计事件」这一屏唯一的取数点与判脸点
 *
 * 病（开工现取，基点 85572c1）：GET /api/v1/audit/events 在前端零消费者（rg -nF "/audit/events"
 * frontend/src 除 </slot> 那种误命中外 0 枚生产命中）。出口早就在树：
 * app/api/v1/observability.py:1644 那条 GET，读的是 app/common/audit.py:584 那份进程内视图。
 *
 * 🔴 这一屏存在的全部意义是判据 C：不许把截断藏起来。回包把这件事拆成六格交出来，本层逐格转达：
 *   filters（:1211-1215 构造，空串那一档后端自己剔掉了）、event_count（:1228 这一页几枚）、
 *   events_total（:1229 过滤后共几枚）、recorded_total（:1230 过滤前全库几枚）、
 *   truncated（:1231 这一页装不下剩下的那些）、limits（:1233-1239 默认与上限与这次实际用的）。
 *   order = newest_first 是 :1232 写死的字面量，屏上原话印出来 —— 「先看最近这些」这件事不该由界面猜。
 *
 * 另两格要紧的：
 *  · 空结果分三种脸，谁都不许冒充谁：过滤条件把每一条都筛掉了（filters 非空、events_total 为 0）、
 *    这台服务一条都没记过（recorded_total 为 0）、这一页没有但更早还有（truncated 为真）。
 *  · 界面上绝不自己造过滤条件：后端把空串剔了，屏侧就把空串那一格整个不发出去（auditQuery 交回的
 *    params 里不许出现值为空串的键），否则「filters 里写着 username=""」就成了界面撒的谎。
 *
 * 三条不变量（钉在 src/lib/__tests__/r505-audit-events-contract.test.js）：
 *  ① 数只从服务端来：三枚计数与那枚 truncation 布尔全是回包读数，本层不数行、不长度、不比大小。
 *     行模型的每一格都按 app/common/audit.py:537-562 那一串键名取，取不到就是「未记录」。
 *  ② 三张失败脸分开留名（判据 D）：403 / 503 / 500 各一张，另加 401 与「回包读不出形状」。
 *  ③ 词表封闭：outcome 那一格对照后端字面量（"allowed" / "denied" / "success" / "failure"），
 *     表外只说「未登记的处置结果」并把原名留在诊断那一行 —— 审计屏把猜出来的中文当处置结果，
 *     比不翻译更坏。action 与 resource 是自由文本，原样端出来，不翻译也不截断。
 */
import { UNRECORDED, faceOf, formatStamp } from './alerts'
import { errorCodeLabel, errorCodeOf, errorText } from './errcodes'
import { PERMISSION_DENIED, errorDetail, http } from './http'
import { countText } from './traces'

/** 这一屏唯一的一条读腿：app/api/v1/observability.py:1644 那条 GET。 */
export const AUDIT_EVENTS_PATH = '/audit/events'

/** 后端写死的那一枚排序：observability.py:1232 的字面量，屏上原话印出来。 */
export const AUDIT_ORDER_NEWEST_FIRST = 'newest_first'
export const AUDIT_ORDER_TEXT = '从最近一条往回列（服务端给的就是这一档顺序）'
export const AUDIT_ORDER_UNKNOWN = '回执没交代排序'

// ==================== 脸谱（判据 D：三张失败脸两两不等） ====================

export const AUDIT_FACE_LOADING = 'loading'
export const AUDIT_FACE_READY = 'ready'
export const AUDIT_FACE_EMPTY_FILTERED = 'empty_filtered'
export const AUDIT_FACE_EMPTY_RECORDED = 'empty_recorded'
export const AUDIT_FACE_UNAUTHORIZED = 'unauthorized'
export const AUDIT_FACE_DENIED = 'denied'
export const AUDIT_FACE_STORAGE = 'storage'
export const AUDIT_FACE_MALFORMED = 'malformed'
export const AUDIT_FACE_FAILED = 'failed'

export const AUDIT_FACES = [
  AUDIT_FACE_LOADING, AUDIT_FACE_READY, AUDIT_FACE_EMPTY_FILTERED, AUDIT_FACE_EMPTY_RECORDED,
  AUDIT_FACE_UNAUTHORIZED, AUDIT_FACE_DENIED, AUDIT_FACE_STORAGE, AUDIT_FACE_MALFORMED,
  AUDIT_FACE_FAILED,
]

export const AUDIT_STORAGE_CODE = 'storage_unavailable'

export const AUDIT_LOADING_TEXT = '正在读这台服务记下的审计事件'
export const AUDIT_TITLES = {
  [AUDIT_FACE_LOADING]: '正在读审计事件',
  [AUDIT_FACE_READY]: '',
  [AUDIT_FACE_EMPTY_FILTERED]: '这几枚过滤条件把每一条都筛掉了',
  [AUDIT_FACE_EMPTY_RECORDED]: '这台服务到今天一条审计事件都没记下',
  [AUDIT_FACE_UNAUTHORIZED]: '审计事件要重新登录才读得到',
  [AUDIT_FACE_DENIED]: '审计事件不向你开放',
  [AUDIT_FACE_STORAGE]: '审计账落不到这台机器上：存储不可用',
  [AUDIT_FACE_MALFORMED]: '审计事件的回执读不出形状',
  [AUDIT_FACE_FAILED]: '审计事件没读回来',
}

/** 三种「空」各自一张脸：把筛掉了画成没记过，就是审计屏最不能犯的一种谎。 */
export const AUDIT_EMPTY_FILTERED_DESCRIPTION =
  '服务端这一发回的事件清单是空的，但它同时告诉我们：过滤条件之前全库是有记录的。'
  + '也就是说这里说的不是「公司没发生过什么」，而是「按上面那几枚条件没筛中」。'
export const AUDIT_EMPTY_RECORDED_DESCRIPTION =
  '服务端说这台进程今天一条审计事件都没记下：这既不是过滤筛掉的，也不是读失败。'
  + '刚装好的机器上这是一种正常状态，别把它读成「审计功能坏了」，也别把它读成「没人动过系统」。'

export const AUDIT_DENIED_WHERE =
  '这一屏读的出口过的是审计那一项权限，它只登记在管理员与审计人员名下；员工与部门负责人账号打进来'
  + '拿回的就是这一发 403。请让企业管理员在账号权限里核对这一项，再回到这一页重新读取——'
  + '重新登录本身不会让这项权限出现，也不要在界面上猜一条事件到底存不存在。'

// ==================== 封闭词表 ====================

export const AUDIT_OUTCOME_LABELS = {
  allowed: '放行了',
  denied: '被拒了',
  success: '做成了',
  failure: '没做成',
}
export const AUDIT_OUTCOME_UNKNOWN = '未登记的处置结果'

export function auditOutcomeLabel(outcome) {
  const key = textOf(outcome)
  return AUDIT_OUTCOME_LABELS[key] || AUDIT_OUTCOME_UNKNOWN
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

export function auditBoolText(value, yes, no) {
  if (typeof value === 'boolean') return value ? yes : no
  return UNRECORDED
}

// ==================== 过滤条件（判据 C 的第一格） ====================

/** 界面能发出去的四格，逐枚对应 observability.py:1201-1204 那四个形参。 */
export const AUDIT_FILTER_FIELDS = ['username', 'action', 'outcome']

/**
 * 查询参数构造器：空串与只含空白的格子整枚不发。
 * 后端 :1211-1215 也会剔空，但那不是界面可以跟着塞的理由 —— 塞进去的那一枚空条件会让回执的
 * filters 读起来像「操作员筛过一次并留下了这一格」，而它其实是界面自己造的。
 */
export function auditQuery(form = {}) {
  const params = {}
  for (const field of AUDIT_FILTER_FIELDS) {
    const raw = form[field]
    const value = typeof raw === 'string' ? raw.trim() : ''
    if (value) params[field] = value
  }
  const limit = numberOrNull(form.limit)
  if (limit !== null) params.limit = Math.trunc(limit)
  return Object.keys(params).length ? params : undefined
}

/**
 * 后端 echo 回来的 filters（:1226）：只读它给的键，一个都不补。
 * 两种形状都收：回执里那一枚原始对象，以及本模块已经配好的那一份名册（counts.filters）。
 * 屏壳要「列条件」与「说那句话」用的是同一份读数，就得让同一枚归一化函数幂等地接得住自己的产物。
 * 旧写法只认原始对象：壳把 counts.filters（数组）递进来时被折成 []，于是屏上同时列出两枚条件、
 * 又说「服务端这一发没有收到任何过滤条件」—— 判据 C 要治的正是这一种自相矛盾。
 */
export function auditFilterPairs(filters) {
  if (Array.isArray(filters)) {
    return filters
      .filter(pair => isRecord(pair) && textOf(pair.key))
      .map(pair => ({ key: textOf(pair.key), value: textOf(pair.value) }))
  }
  if (!isRecord(filters)) return []
  return Object.keys(filters).map(key => ({ key, value: textOf(filters[key]) }))
}

/** 「这一发到底带没带过滤条件」这句话由回执说，不由表单说。 */
export function auditFiltersNote(filters) {
  return auditFilterPairs(filters).length
    ? '上面这几枚条件就是服务端这一发真正用上的过滤（回执里给的，空的条件后端不会留下）'
    : '服务端这一发没有收到任何过滤条件：下面列的是全库最近的那些事件'
}

// ==================== 行模型（键名逐枚对 app/common/audit.py:537-562） ====================

/** 一条事件 -> 屏上一行。取不到的格留「未记录」，不留空串、更不留 0。 */
export function auditEventRow(event) {
  const source = isRecord(event) ? event : {}
  return {
    id: textOf(source.event_id) || 'audit-row-unaddressable',
    eventId: textOf(source.event_id),
    stampText: formatStamp(source.timestamp || source.created_at),
    username: textOf(source.username),
    role: textOf(source.role),
    action: textOf(source.action),
    resource: textOf(source.resource),
    outcomeRaw: textOf(source.outcome),
    outcomeText: auditOutcomeLabel(source.outcome),
    reason: textOf(source.reason),
    requestId: textOf(source.request_id),
    // 名册里没有 department 这一列（app/common/audit.py:537-562 交的是 actor_departments，复数）
    actorDepartments: (Array.isArray(source.actor_departments)
      ? source.actor_departments.map(item => textOf(item)).filter(item => item)
      : []).join('、'),
    storageMode: textOf(source.storage_mode),
    persistedText: auditBoolText(source.persisted, '这条已经落盘', '这条只在进程里'),
    persisted: typeof source.persisted === 'boolean' ? source.persisted : null,
  }
}

/** 分页与上限那一格：默认几枚、最多几枚、这次给了几枚、请求过几枚、有没有被夹。 */
export function auditLimitsView(limits) {
  const source = isRecord(limits) ? limits : {}
  return {
    defaultLimit: countText(source.default_limit, '条'),
    maxLimit: countText(source.max_limit, '条'),
    appliedLimit: countText(source.applied_limit, '条'),
    requestedLimit: source.requested_limit === null || source.requested_limit === undefined
      ? '这一发没带 limit'
      : countText(source.requested_limit, '条'),
    clampedText: auditBoolText(source.clamped, '被后端夹过', '没夹'),
    clamped: typeof source.clamped === 'boolean' ? source.clamped : null,
  }
}

/** 三枚计数 + 那一枚 truncated：判据 C 要求逐格如实，这里一格都不合并。 */
export function auditCountsView(report) {
  const source = isRecord(report) ? report : {}
  const truncated = typeof source.truncated === 'boolean' ? source.truncated : null
  const order = textOf(source.order)
  return {
    eventCount: countText(source.event_count, '条'),
    eventsTotal: countText(source.events_total, '条'),
    recordedTotal: countText(source.recorded_total, '条'),
    truncated,
    truncatedText: truncated === null
      ? UNRECORDED
      : (truncated
        ? '这一页装不下：按同一枚条件还能筛出更早的事件，它们没在这份清单里'
        : '这一页就是按这一发条件筛出来的全部事件'),
    order,
    orderText: order === AUDIT_ORDER_NEWEST_FIRST ? AUDIT_ORDER_TEXT : AUDIT_ORDER_UNKNOWN,
    source: textOf(source.source),
    requestedBy: textOf(isRecord(source.requested_by) ? source.requested_by.username : ''),
    filters: auditFilterPairs(source.filters),
  }
}

// ==================== 归脸 ====================

export function auditBlankView(face = AUDIT_FACE_LOADING) {
  // 点名要哪张脸就给哪张脸：旧写法把「表内但不等于 loading」的请求一律折成 failed ——
  // 于是判据 C 要的「读不出形状」那一格会悄悄变成「读回失败」，两张脸塌成一张（判据 D 同病）。
  const known = AUDIT_FACES.includes(face) ? face : AUDIT_FACE_FAILED
  const loading = known === AUDIT_FACE_LOADING
  return {
    face: known,
    title: loading ? '' : AUDIT_TITLES[known],
    description: loading ? AUDIT_LOADING_TEXT : '',
    codeLabel: '',
    rows: [],
    counts: auditCountsView(null),
    limits: auditLimitsView(null),
  }
}

/**
 * 200 那一发：先分两种「空」，再把有事件当正常脸画。
 * events 与 counts 读不出来就是 malformed —— 「读不出形状」不许滑进空态，那是两回事。
 */
export function auditViewFromResponse(payload) {
  // 回执整枚缺席（204 / 空 body / 一层壳没套对）也是一次「读不出形状」，不是 TypeError：
  // 这一层先把非对象折成空对象，下面三枚计数各自会照实答「读不到」。
  const source = isRecord(payload) ? payload : {}
  const rows = source.events
  const recorded = numberOrNull(source.recorded_total)
  if (!Array.isArray(rows) || numberOrNull(source.event_count) === null || recorded === null) {
    return {
      ...auditBlankView(AUDIT_FACE_MALFORMED),
      title: AUDIT_TITLES[AUDIT_FACE_MALFORMED],
      description: '回执里读不到事件清单或那一格计数：这一屏宁可什么都不画，也不拿一份空数组当「没有事件」。',
    }
  }
  const counts = auditCountsView(source)
  const filtered = counts.filters.length > 0
  const empty = rows.length === 0
  // 空清单有两句不同的话要说，还有一句是「这一发回执自己就矛盾」——第三种情况不许被并进前两句。
  if (empty && recorded !== null && recorded > 0 && !filtered) {
    return {
      ...auditBlankView(AUDIT_FACE_MALFORMED),
      title: AUDIT_TITLES[AUDIT_FACE_MALFORMED],
      description: '回执说全库是有记录的，却又在没带过滤条件的情况下交回一张空清单：'
        + '这两格互相打脸，屏上不替它挑一种说法，请连同下面那三枚计数一起报给运维。',
    }
  }
  const face = empty
    ? (filtered && recorded !== null && recorded > 0 ? AUDIT_FACE_EMPTY_FILTERED : AUDIT_FACE_EMPTY_RECORDED)
    : AUDIT_FACE_READY
  return {
    face,
    title: empty ? AUDIT_TITLES[face] : '',
    description: empty
      ? (face === AUDIT_FACE_EMPTY_FILTERED ? AUDIT_EMPTY_FILTERED_DESCRIPTION : AUDIT_EMPTY_RECORDED_DESCRIPTION)
      : '',
    codeLabel: '',
    rows: rows.map(auditEventRow),
    counts,
    limits: auditLimitsView(source.limits),
  }
}

/** 失败腿：判据只走 errorCodeOf 与 HTTP status 两枚出处，本模块一枚码都不新增。 */
export function auditViewFromError(err) {
  const status = Number(err && err.response ? err.response.status : err && err.status) || 0
  const code = errorCodeOf(err)
  const face = faceOf({ failed: true, code })
  const message = errorDetail(err, '')
  const shell = view => ({
    face: view,
    title: AUDIT_TITLES[view],
    description: message,
    codeLabel: errorCodeLabel(err),
    rows: [],
    counts: auditCountsView(null),
    limits: auditLimitsView(null),
  })
  if (face === 'unauthorized' || status === 401) return shell(AUDIT_FACE_UNAUTHORIZED)
  if (face === 'denied' || status === 403 || code === PERMISSION_DENIED) {
    return {
      ...shell(AUDIT_FACE_DENIED),
      description: errorDetail(err, errorText(PERMISSION_DENIED)) + AUDIT_DENIED_WHERE,
    }
  }
  if (status === 503 || code === AUDIT_STORAGE_CODE) {
    return { ...shell(AUDIT_FACE_STORAGE), description: message || errorText(AUDIT_STORAGE_CODE) }
  }
  return shell(AUDIT_FACE_FAILED)
}

/** 只有这两张脸值得再来一次：权限要人去改，存储要人去修，重放同一发都不改变结果。 */
export const AUDIT_RETRYABLE_FACES = [AUDIT_FACE_FAILED, AUDIT_FACE_MALFORMED]

export function auditFaceView(view) {
  const face = isRecord(view) ? view.face : ''
  return {
    face,
    title: AUDIT_TITLES[face] || AUDIT_TITLES[AUDIT_FACE_FAILED],
    description: (view && view.description) || '',
    codeLabel: (view && view.codeLabel) || '',
    retryable: AUDIT_RETRYABLE_FACES.includes(face),
  }
}

/** 这一屏唯一的读腿：条件全空时一枚查询参数都不带（判据 C 的那句「屏侧别自己造空条件」）。 */
export async function loadAuditEvents(form = {}) {
  const params = auditQuery(form)
  const config = params ? { params } : undefined
  try {
    const response = await http.get(AUDIT_EVENTS_PATH, config)
    return auditViewFromResponse(response && response.data)
  } catch (err) {
    return auditViewFromError(err)
  }
}
