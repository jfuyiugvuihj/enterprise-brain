/**
 * R14-A1 · 总览四个数字的服务端聚合客户端（GET /dashboard/summary）
 *
 * 为什么要这一层：总览页原先在浏览器里数行——文档数 = 文档目录回来的数组长度、数据表 =
 * 数据文件列表的数组长度、审批数 = 前端演示洞察里 filter 之后的长度。列表一旦被分页截断，
 * 数字就静默变小而且「看起来是对的」，这正是 R14 要消灭的那类错法。四个数字现在只有一条
 * 来源：服务端按登录者可见范围算出来的聚合。本模块是它在前端的唯一入口。
 *
 * 三条契约，和后端 app/api/v1/dashboard.py 的模块说明一一对应，改任何一条都要两边一起改：
 *   一、告警键整个缺席 = 这个账号没有告警读取权限，**不等于**「0 条告警」。这里用
 *       hasOwnProperty 分辨「缺席」，不用 ?? 0、|| 0、数组长度把缺字段折成数字：那会在
 *       界面上点亮一盏假健康绿灯，顺带绕过 R1（staff 读告警必 403）。
 *   二、HITL 账本缺失时整个响应该端点自己定的那个 503，不会给「三个能算的数 + 一个缺的数」。
 *       所以前端也只有「整块报错」一条路，不拿上一轮的旧数字装作加载成功。
 *   三、每个数字都是「按你的可见范围」算出来的答案，界面必须把这句口径摆在数字旁边，
 *       否则部门主管会把它读成全公司总数。
 */
import { errorDetail, http, isPermissionDenied } from './http'
import { errorCodeOf } from './errcodes'

/** 只读聚合端点：无 body、不接 rows。POST /dashboard 那条自备 rows 的老路不是总览数据源。 */
export const SUMMARY_PATH = '/dashboard/summary'
const SUMMARY_TIMEOUT_MS = 15000

/** 三面失败标题各不相同：看标题就知道该找管理员开权限、找运维查存储，还是直接再点一次重试。 */
export const SUMMARY_DENIED_TITLE = '没有权限查看经营总览'
export const SUMMARY_STORAGE_TITLE = '存储服务还没就绪，总览数字取不到'
export const SUMMARY_FAILED_TITLE = '经营总览没加载出来'
export const SUMMARY_MALFORMED_TITLE = '总览聚合返回的内容读不出数字'

const SUMMARY_FAILED_MESSAGE = '经营总览暂时读不到数字，请重新加载；一直读不到的话请联系管理员。'
const SUMMARY_MALFORMED_MESSAGE = '聚合响应里缺少总览需要的计数字段，已按失败处理，不会用旧数字或 0 顶上。'
const SUMMARY_STORAGE_MESSAGE = '服务需要的存储还没有就绪，总览这次拿不到真实数字，请联系管理员确认迁移与数据库状态。'

/** 数字取不到时的占位：宁可画一道横杠，也不画一个像真的一样的 0。 */
export const COUNT_PLACEHOLDER = '—'

/** 告警位的三张脸：没权限、读不出来、真数到了。缺席与 0 绝不能共用一张脸。 */
export const ALERT_STATE_DENIED = 'denied'
export const ALERT_STATE_UNREADABLE = 'unreadable'
export const ALERT_STATE_COUNTED = 'counted'

export const ALERTS_DENIED_NOTE = '无权限查看告警'
export const ALERTS_UNREADABLE_NOTE = '告警计数读不出来'

/**
 * 文档卡那一句副文案（R274 · X-3）。
 *
 * 这一句原先是写死的：只要文档数大于 0 就报「都解析完了」那类好消息。可「目录里有 N 篇」
 * 与「N 篇都解析完了」是两件事，一篇都没解析完时那句好话照样成立——R267 把面板里行级的解析
 * 状态归了真，漏的就是 lib 这一层。现在这句话只从聚合回执里的「已解析篇数」来（前端读作
 * documents_ready），四种走法四种说法，谁也不许顶替谁：
 *   一篇都没有      -> 「还没有文档」
 *   回执没带这个数  -> 「已解析篇数未记录」（线上今天就是这一张脸）
 *   两数相等        -> 「全部已解析」
 *   还有没解析完的  -> 「N 篇还没解析完」
 * 已解析篇数比总数还大是一次坏掉的回执，不是一句好消息，所以那一档只说「对不上」。
 * 🚫 后端补上这一数之前，这一格不许换成另一句写死的好话：宁可说没记录。
 */
export const DOCUMENTS_EMPTY_NOTE = '还没有文档'
export const DOCUMENTS_UNRECORDED_NOTE = '已解析篇数未记录'
export const DOCUMENTS_ALL_READY_NOTE = '全部已解析'
export const DOCUMENTS_MISMATCH_NOTE = '已解析篇数与总数对不上'

const DOCUMENTS_COUNTED_HINT = '按你有权查看的文档目录计数，不是全租户文档总数。'
const DOCUMENTS_UNRECORDED_HINT = '文档篇数与「其中已解析多少篇」是两件事：这份聚合回执只回了前者，'
  + '所以这一格不说已解析，只说没记录。等后端把已解析篇数一起回传，这里自己换说法。'
const DOCUMENTS_READY_HINT = '已解析篇数与文档总数同一口径，都按你当前的可见范围计算。'
const DOCUMENTS_MISMATCH_HINT = '回执里已解析的篇数比文档总数还大，这两个数不可能同时成立，所以这一格不下结论。'

const hasOwn = (target, key) => Object.prototype.hasOwnProperty.call(target, key)

/** 非负整数才算读出来的数；null / 字符串 / 负数 / 小数一律判「没数」，不静默降级成 0。 */
function countOf(value) {
  if (value === null || value === undefined || value === '') return null
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric < 0) return null
  return Math.trunc(numeric)
}

/**
 * 响应是否成功。axios 的错误走 reject，但 2xx 之外仍有 resolve 的形状（改过 validateStatus
 * 的调用、或别的 transport），所以取完数还得自己认一次状态：先看 fetch 风格的 ok，再看状态码。
 */
export function responseOk(response) {
  if (!response || typeof response !== 'object') return false
  if (typeof response.ok === 'boolean') return response.ok
  const status = Number(response.status ?? 200) || 0
  return status >= 200 && status < 300
}

/**
 * 从聚合响应里读告警计数。
 *
 * 判据只有一条：**键在不在**。后端在无权限时把整个字段省掉（连 null 都不给），所以缺席就是
 * 没权限，画成 0 就是假健康；给了键但形状读不出数，那是第三种脸（契约坏了），既不算 0 也不算没权限。
 */
export function readAlertFace(payload) {
  if (!payload || typeof payload !== 'object' || !hasOwn(payload, 'alerts')) {
    return { state: ALERT_STATE_DENIED, total: null, unread: null }
  }
  const raw = payload.alerts
  const total = countOf(raw?.total)
  const unread = countOf(raw?.unread)
  if (total === null || unread === null) {
    return { state: ALERT_STATE_UNREADABLE, total: null, unread: null }
  }
  return { state: ALERT_STATE_COUNTED, total, unread }
}

/** 告警位要画上屏的三件事：数字、副文案、口径提示。缺席与读不出来都只给横杠。 */
export function alertTileView(face) {
  const state = face && typeof face === 'object' ? face.state : ALERT_STATE_UNREADABLE
  if (state === ALERT_STATE_DENIED) {
    return {
      state,
      value: COUNT_PLACEHOLDER,
      note: ALERTS_DENIED_NOTE,
      hint: '这一项没有数字，是服务端按权限把告警计数省略了，不代表当前没有告警。',
    }
  }
  if (state === ALERT_STATE_COUNTED) {
    return {
      state,
      value: formatSummaryCount(face.total),
      note: face.unread ? `未读 ${face.unread} 条` : '暂无未读',
      hint: '告警总数按你有权读取的告警范围统计，与告警列表那一页的长度无关。',
    }
  }
  return {
    state: ALERT_STATE_UNREADABLE,
    value: COUNT_PLACEHOLDER,
    note: ALERTS_UNREADABLE_NOTE,
    hint: '聚合响应里的告警字段不是可读数字，已拒绝按 0 显示，请重新加载。',
  }
}

/**
 * 这一屏有没有告警读取权（R285 · X-2）。判据与告警数字位用的是同一枚事实：聚合回执里
 * alerts 键在不在。
 *
 * 后端 app/api/v1/dashboard.py:137-139 只在 _alert_counts() 没返回 None 时才写这一键，而它判的
 * 正是 GET /alerts 那同一条权限门（dashboard.py:90 与 alerts.py:925 都走 _require_alert_management），
 * staff 与 auditor 的角色集里没有 alerts:manage（app/common/permissions.py:13/:16）。
 * 于是键缺席 ⇒ 那一发 GET /alerts 每次必 403：前端不发它就是，这一条改的是前端行为，
 * 不是后端的权限口径 —— staff 不管告警是产品定的。
 *
 * 🚫 「还不知道」不许当成「没权限」：聚合还没落地（metrics 为 null）时返回 true 让那一发照发。
 * 键在但形状读不出（ALERT_STATE_UNREADABLE）同样返回 true —— 有这一键说明权限门过了，
 * 坏的是那一枚计数，不是这个账号的权利。
 */
export function canReadAlerts(metrics) {
  const face = metrics && typeof metrics === 'object' ? metrics.alerts : null
  if (!face || typeof face !== 'object') return true
  return face.state !== ALERT_STATE_DENIED
}

export function formatSummaryCount(value) {
  const numeric = countOf(value)
  return numeric === null ? COUNT_PLACEHOLDER : numeric.toLocaleString('zh-CN')
}

/**
 * 把聚合响应折成总览要的四个数。少一个数就整体判 null 走失败脸：
 * 「三个数 + 一个横杠」在部门主管眼里就是一次正常加载，那是比报错更坏的产物。
 */
export function parseSummaryPayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null
  const documents = countOf(payload.documents)
  const datasets = countOf(payload.datasets)
  const pendingApprovals = countOf(payload.pending_approvals)
  if (documents === null || datasets === null || pendingApprovals === null) return null
  return {
    generatedFor: typeof payload.generated_for === 'string' ? payload.generated_for : '',
    documents,
    // R274（X-3）：「其中已解析多少篇」。后端今天还没回这一数，缺席就是 null，不折成 0。
    documentsReady: countOf(payload.documents_ready),
    datasets,
    pendingApprovals,
    alerts: readAlertFace(payload),
  }
}

/**
 * 失败归脸：没权限 / 存储没就绪 / 就是读不到，三件事三句话。
 *
 * 句子仍出自 lib/errcodes.js 那本字典（这里只决定标题与「字典没话说时」的兜底场景文案）。
 * 503 单独一张脸的理由：这个端点的 503 只有一个来源——HITL 账本表还没建（后端把整块响应
 * 判成 503 而不是省字段），修它要跑迁移，不是再点一次重试。
 */
export function summaryErrorView(err) {
  const code = errorCodeOf(err)
  const status = Number(err?.response?.status ?? err?.status ?? 0) || 0
  const denied = isPermissionDenied(err)
  const storage = code === 'storage_unavailable' || status === 503
  return {
    ok: false,
    code,
    status: storage ? 503 : status,
    denied,
    storage,
    title: summaryTitleOf(storage, denied),
    description: errorDetail(err, storage ? SUMMARY_STORAGE_MESSAGE : SUMMARY_FAILED_MESSAGE),
  }
}

function summaryTitleOf(storage, denied) {
  if (denied) return SUMMARY_DENIED_TITLE
  return storage ? SUMMARY_STORAGE_TITLE : SUMMARY_FAILED_TITLE
}

function malformedSummaryView() {
  return {
    ok: false,
    code: '',
    status: 0,
    denied: false,
    storage: false,
    title: SUMMARY_MALFORMED_TITLE,
    description: SUMMARY_MALFORMED_MESSAGE,
  }
}

/**
 * 取一次总览聚合。返回形状只有两种：``{ ok: true, metrics }`` 或 ``summaryErrorView`` 那张脸。
 * 不抛错给面板——面板要在 catch 里同时处理四五个请求的话，失败归脸就会串味。
 */
export async function loadDashboardSummary() {
  let response
  try {
    response = await http.get(SUMMARY_PATH, { timeout: SUMMARY_TIMEOUT_MS })
  } catch (err) {
    return summaryErrorView(err)
  }
  if (!responseOk(response)) {
    return summaryErrorView({ response, status: response?.status })
  }
  const metrics = parseSummaryPayload(response.data)
  if (!metrics) return malformedSummaryView()
  return { ok: true, metrics }
}

/** 口径提示：数字旁边必须跟着这一句，否则它会被读成全租户总数。 */
export function summaryScopeNote(generatedFor) {
  const who = typeof generatedFor === 'string' ? generatedFor.trim() : ''
  if (who) return `四个数字由服务端按「${who}」当前的可见范围计算，不是全租户总数。`
  return '四个数字由服务端按你当前的可见范围计算，不是全租户总数。'
}

/**
 * 文档卡的副文案与口径提示：只从聚合结果里那两个数来，取值走法见上面那组常量的注释。
 */
export function documentsTileView(metrics) {
  const counted = countOf(metrics?.documents)
  if (counted === 0) return { delta: DOCUMENTS_EMPTY_NOTE, hint: DOCUMENTS_COUNTED_HINT }
  const ready = countOf(metrics?.documentsReady)
  // 总数或已解析篇数任意一枚取不出来，这句都只能是「未记录」：不许把读不出数说成「没有文档」。
  if (counted === null || ready === null) return { delta: DOCUMENTS_UNRECORDED_NOTE, hint: DOCUMENTS_UNRECORDED_HINT }
  if (ready > counted) return { delta: DOCUMENTS_MISMATCH_NOTE, hint: DOCUMENTS_MISMATCH_HINT }
  if (ready === counted) return { delta: DOCUMENTS_ALL_READY_NOTE, hint: DOCUMENTS_READY_HINT }
  return { delta: `${counted - ready} 篇还没解析完`, hint: DOCUMENTS_READY_HINT }
}

/**
 * 四个数字的视图模型：标签、数字、副文案、口径提示，全部只从聚合结果里取。
 * 图标与配色留在面板里（那是视觉层的事），这里一行 DOM 都不碰。
 */
export function summaryTiles(metrics) {
  if (!metrics) return []
  const alerts = alertTileView(metrics.alerts)
  return [
    {
      id: 'documents',
      label: '文档总量',
      value: formatSummaryCount(metrics.documents),
      ...documentsTileView(metrics),
    },
    {
      id: 'datasets',
      label: '数据表',
      value: formatSummaryCount(metrics.datasets),
      delta: metrics.datasets ? '可分析' : '还没有数据文件',
      hint: '按你可以分析并打开的数据文件计数。',
    },
    {
      id: 'pendingApprovals',
      label: '待我审批',
      value: formatSummaryCount(metrics.pendingApprovals),
      delta: metrics.pendingApprovals ? '等你处理' : '暂无待办',
      hint: '挂起账本里属于你的待确认项，只看你名下开着的行。',
    },
    {
      id: 'alerts',
      label: '告警',
      value: alerts.value,
      delta: alerts.note,
      hint: alerts.hint,
      state: alerts.state,
    },
  ]
}

/**
 * 「最新文档」这一格自己的失败脸（R274 · X-6）。
 *
 * 为什么归脸要放在 lib：面板里再调一次 isPermissionDenied 就是第三处权限判定，
 * 而「这一格读不到」与「这一屏读不到」本来就是两件事（改前 catalog 一发失败会把整屏
 * 拖进错误脸，连本来能读的告警账本都不再发请求）。没权限与真坏了仍是两句话：
 * 前者不给重试按钮，后者给。
 */
export const DOCUMENTS_DENIED_TITLE = '这个账号看不到文档目录'
export const DOCUMENTS_FAILED_TITLE = '最新文档没加载出来'

const DOCUMENTS_DENIED_MESSAGE = '这个账号没有读取文档目录的权限，所以这一格没有行；上面四个数字与其余卡片不受影响。'
const DOCUMENTS_FAILED_MESSAGE = '文档目录这一发没有回来，所以这一格没有行；这不代表公司没有文档，也不影响上面四个数字。'

export function documentsFailureView(err) {
  const denied = isPermissionDenied(err)
  return {
    denied,
    title: denied ? DOCUMENTS_DENIED_TITLE : DOCUMENTS_FAILED_TITLE,
    description: errorDetail(err, denied ? DOCUMENTS_DENIED_MESSAGE : DOCUMENTS_FAILED_MESSAGE),
  }
}


/* ============================================================================
 * R341 · 「数据趋势」那一格的期间序列客户端（GET /dashboard/trend）
 *
 * R332 把这条路由交出来之后，这一屏就没有任何理由再替服务端说「还没回传」。这一层的
 * 三条规矩，与 app/api/v1/dashboard.py 的模块说明和 docs/api/contract-v1.md:2509 那一节
 * 一一对应，改任何一条都要两边一起改：
 *   一、数字只从这条路由来。前端不按 created_at 自己切期、不从 /summary 反推、也不把两本
 *       账混着加总；period 与 buckets 原样做成查询参数交给服务端，窗口长度不由前端截断。
 *   二、「读不到 / 没权限 / 那几期真的零新增」是三张不同的脸。告警那两列用 hasOwnProperty
 *       分辨缺席（docs/api/contract-v1.md:2616：整键缺席是权限，不是数字），不用 ?? 0 与
 *       || 0 —— 在无权限的账号上画一个 0，等于用一条不是告警列表的路由去读告警账本。
 *   三、回包形状读不出就是失败，不降级成空态。存储读不出时服务端整格失败、没有部分序列，
 *       参数不合法是另一张脸；两张脸都不新增错误码，只读 lib/errcodes.js 既有那本字典。
 *
 * 序列之和与那四个数字本来就不该相等：series 只覆盖窗口这几期新产生的行，聚合数的是全部
 * 可见行（docs/api/contract-v1.md:2600）。所以这一层没有任何「对平」断言，界面也不许出现。
 * ========================================================================== */

/** 期间序列端点：无 body、不接 rows，参数只走查询串。 */
export const TREND_PATH = '/dashboard/trend'
const TREND_TIMEOUT_MS = 15000

/** 参数域与服务端一致：period 只有两枚取值，buckets 是 1..60 的整数，默认 12。 */
export const TREND_PERIOD_MONTH = 'month'
export const TREND_PERIOD_WEEK = 'week'
export const TREND_PERIODS = [TREND_PERIOD_MONTH, TREND_PERIOD_WEEK]
export const TREND_DEFAULT_PERIOD = TREND_PERIOD_MONTH
export const TREND_DEFAULT_BUCKETS = 12
export const TREND_MIN_BUCKETS = 1
export const TREND_MAX_BUCKETS = 60

/** 界面上唯一合法的窗口档位：60 是服务端上限，前端不许自己造更高的密度。 */
export const TREND_BUCKET_OPTIONS = [
  { label: '近 6 期', value: 6 },
  { label: '近 12 期', value: TREND_DEFAULT_BUCKETS },
  { label: '近 24 期', value: 24 },
  { label: '近 60 期（服务端上限）', value: TREND_MAX_BUCKETS },
]

/**
 * 这一格的脸：never（还没取过数）、loading（正在取）、ready（数字在位），
 * 加 denied / storage / invalid / malformed / failed 五张各归各的失败脸。
 * 「那几期真的零新增」不是单独一枚脸而是 ready 上的 allZero —— 数字在位，只是服务端
 * 逐期说了 0，那是一句事实，与「读不到」绝不一样。
 */
export const TREND_FACE_NEVER = 'never'
export const TREND_FACE_LOADING = 'loading'
export const TREND_FACE_READY = 'ready'
export const TREND_FACE_DENIED = 'denied'
export const TREND_FACE_STORAGE = 'storage'
export const TREND_FACE_INVALID = 'invalid'
export const TREND_FACE_MALFORMED = 'malformed'
export const TREND_FACE_FAILED = 'failed'

/** 四面失败标题各不相同：看标题就知道该开权限、该修存储、该改参数，还是直接再点一次。 */
export const TREND_DENIED_TITLE = '这个账号看不到数据趋势'
export const TREND_STORAGE_TITLE = '存储服务还没就绪，趋势取不到'
export const TREND_INVALID_TITLE = '趋势的期间参数没有被接受'
export const TREND_MALFORMED_TITLE = '趋势回包读不出数'
export const TREND_FAILED_TITLE = '数据趋势没加载出来'

const TREND_DENIED_MESSAGE = '这个账号没有查看这条趋势的权限，所以这一格没有数字；再点一次也不会改变它。'
const TREND_STORAGE_MESSAGE = '服务需要的存储还没有就绪。三本账任意一本读不出，服务端就不回部分序列，所以这里也没有半成品可以画。'
const TREND_INVALID_MESSAGE = '请求的期间或期数没有被接受：服务端只认按月或按周，期数在 1 到 60 之间。这一格没有数字，这不代表那几期没有新增。'
const TREND_MALFORMED_MESSAGE = '回包里的期间序列读不出数，已按失败处理，不会用旧数字或 0 顶上。'
const TREND_FAILED_MESSAGE = '这一格暂时读不到按期间汇总的计数，请重新加载；一直读不到的话请联系管理员。'

/** never 与 loading 两张脸的正文：都在说「还没有数」，但都不许被读成「没有新增」。 */
export const TREND_NEVER_TEXT = '这一格还没有取过按期间汇总的计数：没取到就不画线，也不放一个像真的刻度。上面的按月、按周与窗口就是这一格的取数参数。'
export const TREND_LOADING_TEXT = '正在向服务端取按期间汇总的计数。'

/** 单位口径（R332 裁定①）：这一格只表条目数，不表钱。 */
export const TREND_UNIT_NOTE = '表里每一格都是「这一期新增了几条」：文档按条、数据集按个、告警按条，不是金额，这里也没有任何金额刻度。'

/** 条形只按同一列里最高的那一格等比缩短；全窗口都是 0 时每一根都收成零长。 */
export const TREND_BAR_NOTE = '条形长度按窗口里最高的新增文档条数等比缩短，只表条数，最高的那一格画满。'

/** 窗口口径：这一句是「为什么这张表加总不等于上面的文档数字」的唯一解释。 */
export const TREND_WINDOW_NOTE = '上面四个数字数的是全部可见行，这张表只数窗口这几期新产生的行：语料比窗口老的时候，两边本来就不该相等。'

/** 那几期真的什么都没有新增（服务端逐期回了 0），与「读不到」是两句话。 */
export const TREND_ZERO_NOTE = '窗口里每一期的新增都是服务端说出来的 0：这是「确实没有新增」，不是「读不到」，也不是「没有权限」。'

/** 告警两列的三张脸。整键缺席时两列一起不出现，而不是画 0，也不是画横杠冒充没权限。 */
export const TREND_ALERTS_DENIED_NOTE = '「新增告警」与「其中未闭环」这两列没有出现在这张表里：服务端按权限把这两列整个省掉了。这是「不向你开放」，不是「0 条告警」。'
export const TREND_ALERTS_UNREADABLE_NOTE = '告警那两列的键在位但读不出数，表里只画横杠，不按 0 画。'

/** 未闭环那一列不可回放：它是本次请求时刻的处置状态画在过往的创建期上，不是当时的快照。 */
export const TREND_ALERTS_OPEN_NOTE = '「其中未闭环」按这次请求时刻的处置状态计算：同一个月份事后回看可能对不上，它不是当时那条记录的快照。'

/** 已解析那一列沿用总览那笔已声明的偏差，两列不许在图上被合并成一个数。 */
export const TREND_READY_NOTE = '「其中已解析」与上面文档卡同一口径，迁移前登记的历史行一律算「还没解析完」，所以这一列只会偏保守。'

/**
 * 参数原样交给服务端。非法值不发那一发请求 —— 前端没有权力替服务端猜一个合法值，
 * 也不许把 61 期悄悄夹成 60 期：那是把用户要问的窗口换成另一个窗口。
 */
/** 「没有期间」那一格的口径（R342）：数只从服务端搬，这一层一个都不自己算。 */
const TREND_UNDATED_BOOKS = [
  ['documents', '文档', '条'],
  ['datasets', '数据集', '个'],
  ['alerts', '告警', '条'],
]

/** 服务端一格都没报缺时间：这一句与「那几期真的零新增」是两句话。 */
export const TREND_UNDATED_CLEAR_NOTE = '服务端没有报出「没有时间」的行：窗口里每一行的期间都读得出来。'

const TREND_UNDATED_TAIL = '条没有时间，未计入上面任何一期：那是「那一格没有记录」，不是「这一期没有新增」。'

/**
 * 把 undated 三本账折成一句人话。只搬运：这里不出现任何加减，也不拿总览的数字减一遍
 * （R333/R341 同一条纪律：浏览器里多一本账，就是同一个问题多一个答案）。
 */
export function trendUndatedNote(undated) {
  if (!undated || typeof undated !== 'object' || Array.isArray(undated)) return ''
  const parts = TREND_UNDATED_BOOKS
    .map(([key, label, unit]) => [label, unit, countOf(undated[key])])
    .filter(([, , value]) => value !== null && value > 0)
    .map(([label, unit, value]) => `${formatSummaryCount(value)} ${unit}${label}`)
  return parts.length ? `另有 ${parts.join('、')}${TREND_UNDATED_TAIL}` : TREND_UNDATED_CLEAR_NOTE
}

export const TREND_UNDATED_KEYS = TREND_UNDATED_BOOKS.map(([key]) => key)

export function trendRequestParams({ period = TREND_DEFAULT_PERIOD, buckets = TREND_DEFAULT_BUCKETS } = {}) {
  if (!TREND_PERIODS.includes(period)) return null
  const raw = typeof buckets === 'number' || typeof buckets === 'string' ? String(buckets).trim() : ''
  const count = Number(raw)
  if (!raw || !Number.isInteger(count) || count < TREND_MIN_BUCKETS || count > TREND_MAX_BUCKETS) return null
  return { period, buckets: count }
}

/** 月份读成「2026 年 9 月」，ISO 周读成「2026 年第 40 周」；读不成中文就逐字显示服务端给的标签，不替它编一个日期。 */
export function trendBucketLabel(period, bucket) {
  const raw = typeof bucket === 'string' ? bucket.trim() : ''
  if (!raw) return ''
  const month = /^(\d{4})-(\d{1,2})$/.exec(raw)
  if (period === TREND_PERIOD_MONTH && month) return `${month[1]} 年 ${Number(month[2])} 月`
  const week = /^(\d{4})-W(\d{1,2})$/i.exec(raw)
  if (period === TREND_PERIOD_WEEK && week) return `${week[1]} 年第 ${Number(week[2])} 周`
  return raw
}

/**
 * 一列的权限脸：没有一枚桶带这个键 = 没权限（整列不出现）；每枚桶都带但读不出数，
 * 或只有部分桶带（服务端自相矛盾）= 读不出（画横杠）。两种都不许折成 0。
 */
function trendColumnFace(series, key) {
  const owned = series.filter(point => hasOwn(point, key))
  if (owned.length === 0) return ALERT_STATE_DENIED
  if (owned.length !== series.length) return ALERT_STATE_UNREADABLE
  return series.some(point => countOf(point[key]) === null) ? ALERT_STATE_UNREADABLE : ALERT_STATE_COUNTED
}

/** 这一列上屏的单元格：没权限时面板整列不渲染；读不出给横杠；数到了给千分位。 */
function trendColumnCell(face, value) {
  if (face === ALERT_STATE_DENIED) return null
  if (face === ALERT_STATE_UNREADABLE) return COUNT_PLACEHOLDER
  return formatSummaryCount(value)
}

/** 条形宽度：与那一格的数等比。max 为 0（全窗口零新增）时每根都收成零长，不画一根假装有的。 */
function trendBarWidth(value, max) {
  if (!(max > 0)) return '0%'
  const ratio = Math.max(0, Math.min(1, value / max)) * 100
  return `${ratio.toFixed(1)}%`
}

/**
 * 一枚桶：三本核心账（文档、其中已解析、数据集）任意一枚读不出数，或者已解析比总数还大，
 * 就是整份回包读不出 —— 宁可报错，也不摆一行缺数的「期间」，更不补一个 0。
 */
function trendPointRow(period, point) {
  if (!point || typeof point !== 'object' || Array.isArray(point)) return null
  const bucket = typeof point.bucket === 'string' ? point.bucket.trim() : ''
  if (!bucket) return null
  const documents = countOf(point.documents)
  const documentsReady = countOf(point.documents_ready)
  const datasets = countOf(point.datasets)
  if (documents === null || documentsReady === null || datasets === null) return null
  if (documentsReady > documents) return null
  return { bucket, label: trendBucketLabel(period, bucket), documents, documentsReady, datasets }
}

/**
 * 把回包折成视图模型。任何一条不成立都返回 null（面板据此画「读不出数」那张脸）：
 * 序列不是数组、长度与 buckets 自相矛盾、时区没有自报、period 不是服务端认的那两枚取值。
 * 时区与窗口一律用回包里那几枚字段，前端不自己截日历、也不猜今天是哪一期。
 */
export function parseTrendPayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null
  const series = payload.series
  if (!Array.isArray(series) || series.length === 0) return null
  if (!TREND_PERIODS.includes(payload.period)) return null
  const buckets = countOf(payload.buckets)
  if (buckets === null || buckets !== series.length) return null
  const timeZone = typeof payload.time_zone === 'string' ? payload.time_zone.trim() : ''
  if (!timeZone) return null

  const rows = []
  for (const point of series) {
    const row = trendPointRow(payload.period, point)
    if (!row) return null
    rows.push(row)
  }

  // R342 · 「没有期间」那一格：整块缺席、三本核心账读不出数，都是回包坏了，不降级成 0。
  const undated = payload.undated
  if (!undated || typeof undated !== 'object' || Array.isArray(undated)) return null
  const undatedCounts = {}
  for (const key of ['documents', 'documents_ready', 'datasets']) {
    const value = countOf(undated[key])
    if (!hasOwn(undated, key) || value === null) return null
    undatedCounts[key] = value
  }
  const undatedAlerts = ['alerts', 'alerts_open'].filter(key => hasOwn(undated, key))
  for (const key of undatedAlerts) undatedCounts[key] = countOf(undated[key])

  const alertsFace = trendColumnFace(series, 'alerts')
  const openFace = trendColumnFace(series, 'alerts_open')
  const columnState = alertsFace === openFace ? alertsFace : ALERT_STATE_UNREADABLE
  const max = rows.reduce((top, row) => Math.max(top, row.documents), 0)
  const cells = rows.map(row => ({
    ...row,
    documentsWidth: trendBarWidth(row.documents, max),
    alerts: trendColumnCell(columnState, null),
    alertsOpen: trendColumnCell(columnState, null),
  }))
  if (columnState === ALERT_STATE_COUNTED) {
    series.forEach((point, index) => {
      cells[index].alerts = formatSummaryCount(countOf(point.alerts))
      cells[index].alertsOpen = formatSummaryCount(countOf(point.alerts_open))
    })
  }

  const allZero = rows.every(row => row.documents === 0 && row.documentsReady === 0 && row.datasets === 0)
  // 桶里带告警列，undated 就得带满两枚；桶里不带（没权限），undated 也不许带——多出来就是把告警账本递出去了。
  if (columnState === ALERT_STATE_DENIED ? undatedAlerts.length !== 0 : undatedAlerts.length !== 2) return null

  const notes = [TREND_UNIT_NOTE, TREND_BAR_NOTE, TREND_READY_NOTE, TREND_WINDOW_NOTE]
  notes.push(`窗口按服务端自报的时区 ${timeZone} 截日历，不是协调世界时。`)
  if (allZero) notes.push(TREND_ZERO_NOTE)
  // 告警那两列的脸单说一句、单独一格：整列缺席是权限，不许和口径提示混成一段小字。
  const alertsNote = columnState === ALERT_STATE_DENIED
    ? TREND_ALERTS_DENIED_NOTE
    : columnState === ALERT_STATE_UNREADABLE ? TREND_ALERTS_UNREADABLE_NOTE : TREND_ALERTS_OPEN_NOTE

  return {
    face: TREND_FACE_READY,
    generatedFor: typeof payload.generated_for === 'string' ? payload.generated_for : '',
    period: payload.period,
    buckets,
    timeZone,
    rows: cells,
    alertsState: columnState,
    alertsColumn: columnState !== ALERT_STATE_DENIED,
    alertsNote,
    undated: undatedCounts,
    undatedNote: trendUndatedNote(undated),
    allZero,
    windowLabel: payload.period === TREND_PERIOD_WEEK ? `最近 ${buckets} 周` : `最近 ${buckets} 个月`,
    notes,
  }
}

/**
 * 失败归脸：没权限 / 存储没就绪 / 参数没被接受 / 就是读不到，四句话四张脸。
 * 句子仍出自 lib/errcodes.js 那本字典（这里只决定标题与「字典没话说时」的场景文案），
 * 判据走 errorCodeOf 那枚独立通道 —— 本模块一个码都不新增。
 */
export function trendErrorView(err) {
  const code = errorCodeOf(err)
  const status = Number(err?.response?.status ?? err?.status ?? 0) || 0
  const denied = isPermissionDenied(err)
  const storage = code === 'storage_unavailable' || status === 503
  const invalid = code === 'validation_error' || status === 422
  const face = denied ? TREND_FACE_DENIED : storage ? TREND_FACE_STORAGE : invalid ? TREND_FACE_INVALID : TREND_FACE_FAILED
  const title = denied
    ? TREND_DENIED_TITLE
    : storage
      ? TREND_STORAGE_TITLE
      : invalid
        ? TREND_INVALID_TITLE
        : TREND_FAILED_TITLE
  const fallback = denied
    ? TREND_DENIED_MESSAGE
    : storage
      ? TREND_STORAGE_MESSAGE
      : invalid
        ? TREND_INVALID_MESSAGE
        : TREND_FAILED_MESSAGE
  return {
    face,
    code,
    status: storage ? 503 : invalid ? 422 : status,
    denied,
    storage,
    invalid,
    retryable: !denied,
    title,
    description: errorDetail(err, fallback),
    rows: [],
    notes: [],
    alertsNote: '',
    undatedNote: '',
  }
}

function malformedTrendView() {
  return {
    face: TREND_FACE_MALFORMED,
    code: '',
    status: 0,
    denied: false,
    storage: false,
    invalid: false,
    retryable: true,
    title: TREND_MALFORMED_TITLE,
    description: TREND_MALFORMED_MESSAGE,
    rows: [],
    notes: [],
    alertsNote: '',
    undatedNote: '',
  }
}

/** 参数不合法这一腿没有那一发请求可归脸：现场造一份 422 的形状，句子用本模块那句人话。 */
function invalidTrendView() {
  const view = trendErrorView({ response: { status: 422, data: { detail: 'validation_error' } } })
  return { ...view, description: TREND_INVALID_MESSAGE }
}

/**
 * 还没有数时的两张脸（never / loading）。面板把它当 ref 起点，也把它当清空目标：
 * 每一次重新取数都从这里起步，上一份 series 不许挂在屏上冒充这一份的结果。
 */
export function trendBlankView(face = TREND_FACE_NEVER) {
  const text = face === TREND_FACE_LOADING ? TREND_LOADING_TEXT : TREND_NEVER_TEXT
  return {
    face: face === TREND_FACE_LOADING ? TREND_FACE_LOADING : TREND_FACE_NEVER,
    title: '',
    description: '',
    text,
    rows: [],
    notes: [],
    alertsNote: '',
    undatedNote: '',
  }
}

/** 屏上有没有服务端回传的数字：这一块判据只写一次，诚实牌与表格共用它。 */
export function trendHasNumbers(view) {
  return Boolean(view) && view.face === TREND_FACE_READY
}

/**
 * 这张脸是不是「读不到」那五张之一，是就把脸名回给面板，不是就回空串。
 * 面板里再写一遍 if/else 就是第三处权限判定（R285 的教训），所以归脸留在这里。
 */
export function trendFailureFace(view) {
  const face = view && typeof view === 'object' ? view.face : ''
  return [TREND_FACE_DENIED, TREND_FACE_STORAGE, TREND_FACE_INVALID, TREND_FACE_MALFORMED, TREND_FACE_FAILED].includes(face) ? face : ''
}

/**
 * 取一次期间序列。返回形状只有两种：parseTrendPayload 那张 ready 视图，或一张失败脸。
 * 与 loadDashboardSummary 同一规矩：不抛错给面板 —— 一格的事不许拖走一屏。
 */
export async function loadDashboardTrend({ period = TREND_DEFAULT_PERIOD, buckets = TREND_DEFAULT_BUCKETS } = {}) {
  const params = trendRequestParams({ period, buckets })
  if (!params) return invalidTrendView()
  let response
  try {
    response = await http.get(TREND_PATH, { params, timeout: TREND_TIMEOUT_MS })
  } catch (err) {
    return trendErrorView(err)
  }
  if (!responseOk(response)) {
    return trendErrorView({ response, status: response?.status })
  }
  const parsed = parseTrendPayload(response.data)
  if (!parsed) return malformedTrendView()
  return parsed
}
