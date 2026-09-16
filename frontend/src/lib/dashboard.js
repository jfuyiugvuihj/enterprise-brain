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
      delta: metrics.documents ? '已解析入库' : '还没有文档',
      hint: '按你有权查看的文档目录计数，不是全租户文档总数。',
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
