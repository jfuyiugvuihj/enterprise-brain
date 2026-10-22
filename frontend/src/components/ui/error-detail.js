/*
 * R291 · 后端原文的渲染策略（UiErrorState 详情区唯一口径）
 *
 * 这一枚模块只回答一个问题：**这一发失败的后端原话，该不该画上屏、画哪一句**。
 * 数法只有一处：UiErrorState 用它，面板要自己拼详情区也用它，不许有第二份判断。
 *
 * 背景（判据②要修的那道缝）：lib/errcodes.js 从 R281 起就把后端信封 message 那一格
 * 原样收进 normalizeError() 的 rawMessage，那是**数据出口**。而渲染出口今天只有一条，
 * 且刻意不画它：errorCodeLabel() 的「错误码：xxx」小字只在字典收不下的码上出现，
 * 对人话位而言后端原文一个字都不上屏。R281 判据①明令不要把那条小字改成常开，
 * 所以补的是**第二条腿**：一处折叠的、等宽的、给人贴给运维的技术信息区。
 *
 * 三条口径，逐条都有出处：
 *   ① 只认 rawMessage 这一格。它是「后端在信封 message 里主动回了什么」，
 *      由 errcodes 清洗过（HTML、[object Object]、axios 英文原句都进不来）。
 *      本模块绝不回退去挖 response.data 的任意字段，也不拼 details 里的内部结构 ——
 *      那会把「后端选择说什么」换成「前端能翻到什么」，契约 docs/api/contract-v1.md:1222
 *      刚把「internal exception text is no longer streamed」记成一笔还掉的债。
 *   ② 原话与人话同字时不上屏。字典收不下的那一档（未知码 / 无码）后端那句仍占人话位
 *      （errcodes.js::fromEnvelope 的 claimed 分流），再画一遍就是同一句话开两个出口。
 *      于是详情区真正补上的，恰好是「字典有话说、后端原话被字典句顶掉」那一档 —— 也就是本单的症状。
 *   ③ 鉴权 / 越权 / 密级那一族一律不上屏（判据③）。契约口径：那一族的原文要么根本没有
 *      （鉴权门回的是裸码名，形状 1，rawMessage 恒空），要么是后端替前端内部人的说法
 *      （contract-v1.md:160 的示例 "resource access is not permitted"），而「按什么维度拒的」
 *      在现网有独立一套原因码（app/common/policy.py 那一族，见 LEGACY_ALIASES 逐枚位锚），
 *      行级那一层甚至刻意不说为什么（contract-v1.md:851-866：no_visible_rows 的 message 键是
 *      缺席而不是空，消费方「must not introduce permission, visibility or department wording
 *      of their own」）。把原话贴上去等于用未裁定的因由覆盖字典那张脸，所以这里选择沉默。
 *      沉默 = 不渲染这一块，不是渲染一句「后端没有提供原文」——前端编的第三种说法同样是第二真相。
 *
 * 名单取值全部来自 lib/errcodes.js 里真实在册的码名与原因码，不发明码名。
 */
import { normalizeError } from '../../lib/errcodes.js'

/** 鉴权 / 权限 / 可见性那一族的枚举码本尊：这一族的原话一律不上屏 */
const REFUSED_CODES = [
  'authentication_required',
  'permission_denied',
  'authorization_unavailable',
  'account_unavailable',
  'row_scope_denied',
  'no_visible_rows',
]

/**
 * 后端原因码：多半已被 LEGACY_ALIASES 折进上面某一格，但折完之后 code 就不是它自己了
 * （department_override_denied 折向 validation_error、clearance_insufficient 折向 permission_denied），
 * 所以按 rawCode 再判一次，免得「折到哪格」决定「漏不漏原文」。
 */
const REFUSED_RAW_CODES = [
  'principal_inactive',
  'department_scope_denied',
  'clearance_insufficient',
  'resource_scope_missing',
  'resource_scope_invalid',
  'department_override_denied',
  'row_scope_denied',
]

/** 鉴权面与越权面的 HTTP 状态：code 归不上类时（未知码）也要拦住 */
const REFUSED_STATUSES = [401, 403]

const GARBAGE = /^[[(<]?(?:object [A-Za-z]*|undefined|null|NaN)[\])]?$/

/** 只认字符串，其他形状一律「没有原文」—— 空串、undefined、[object Object] 都不配上屏 */
function asText(value) {
  if (typeof value !== 'string') return ''
  const text = value.trim()
  if (!text || GARBAGE.test(text)) return ''
  return text
}

/** 这一发带得来的 HTTP 状态（axios 的 response.status 与 artifacts.js 挂的 status 两种形状） */
function statusOf(source) {
  if (!source || typeof source !== 'object') return 0
  return Number(source.response?.status ?? source.status ?? 0) || 0
}

/**
 * 后端原话 + 归类结果。两条读法，取哪条由「输入是不是已经过字典」决定：
 *   带 rawMessage 字符串 ⇒ 它是 normalizeError 的产物，或 artifacts.js 重建过的 Error，
 *     两格现成，直接读。不复算 normalizeError：拿成品再跑一遍会把**字典那句人话**
 *     当成信封 message 收进 rawMessage（fromEnvelope 只看有没有 message 这一格），
 *     详情区就此变成人话的第二份拷贝 —— 那是假话。
 *   其余对象 ⇒ 还没过字典（裸 axios 错误），交给 normalizeError 走它自己的分流。
 */
function verdictOf(source) {
  if (source && typeof source === 'object' && typeof source.rawMessage === 'string') {
    return {
      raw: source.rawMessage,
      code: asText(source.code),
      rawCode: asText(source.rawCode),
    }
  }
  const result = normalizeError(source)
  return { raw: result.rawMessage, code: result.code, rawCode: result.rawCode }
}

function isRefused({ code, rawCode, status }) {
  if (REFUSED_STATUSES.includes(status)) return true
  if (REFUSED_CODES.includes(code)) return true
  return REFUSED_RAW_CODES.includes(rawCode)
}

/**
 * UiErrorState 详情区的内容：这一发该展示的后端原文，没有可展示的原文时回空串。
 *
 * @param {unknown} source catch 到的错误对象、axios 错误或 normalizeError 的产物
 * @param {{ shown?: string }} [options] 已经画上屏的那句人话（UiErrorState 的 description）：
 *   与原文同字时不再重复一遍（口径②）
 * @returns {string} 后端原话逐字，或空串
 */
export function rawDetailOf(source, { shown = '' } = {}) {
  const verdict = verdictOf(source)
  const raw = asText(verdict.raw)
  if (!raw) return ''
  if (isRefused({ code: verdict.code, rawCode: verdict.rawCode, status: statusOf(source) })) return ''
  const human = asText(shown)
  if (human && (human === raw || human.includes(raw))) return ''
  return raw
}
