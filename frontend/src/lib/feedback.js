/**
 * R195 · 出处卡片那两枚动作的唯一判定与措辞点（R46 前端半张）。
 *
 * 契约只有一枚出口：app/api/v1/feedback.py 的 POST /feedback/document。它【只认两枚键】
 * ——filename（上界 512 个字符，与 migrations/0011 那条 CHECK 同值）与 signal
 * （只有 accepted 与 rejected 两值），多一个键整条拒；200 回来的那五格见
 * docs/api/contract-v1.md 的 Document Activity Feedback 一节。本模块因此不长第三格：
 * 请求体由 feedbackRequestBody 一处组装，返回的是一个只含两枚键的字面对象，
 * 问题原文、答案文本、命中句都没有装进去的位置（判据④）。
 *
 * 撤回这一族【刻意不做】：取证 app/api/v1/feedback.py 全文只有两枚路由
 * （POST 与 GET /feedback/document），没有任何 DELETE / 复位出口；那张表的写法是
 * ON CONFLICT DO UPDATE 累加计数，落下去的数只能变大。既没有可走的门，也不许把一枚
 * 反向信号当成撤回发出去——那会把「有人觉得没用」凭空记成「有人觉得有用」，
 * 排序读到的先验就此变成假账。所以两枚动作是一次性的：记上了就锁住，界面如实这么说。
 *
 * 形状沿用 lib/provenance.js 与 lib/alerts.js：判定与措辞住在这里，组件只画，
 * node 环境能直接单测；发请求走 lib/http.js 那一个 axios 实例（Bearer 由它的拦截器加）。
 */
import { errorCodeOf } from './errcodes'
import { errorDetail, http } from './http'

/** 唯一路径。挂在 /api/v1 之下（app/main.py 把 feedback 路由注册进 v1 组）。 */
export const FEEDBACK_PATH = '/feedback/document'

/** 后端 DocumentFeedback.signal 的全部取值，一字不多（feedback.py 里那枚 Literal）。 */
export const SIGNAL_ACCEPTED = 'accepted'
export const SIGNAL_REJECTED = 'rejected'
export const SIGNALS = [SIGNAL_ACCEPTED, SIGNAL_REJECTED]

/** 界面上的说法：像人话，且两枚各自只表达一件事。 */
export const SIGNAL_LABELS = {
  [SIGNAL_ACCEPTED]: '有用',
  [SIGNAL_REJECTED]: '没用',
}

/** 请求体允许出现的键，顺序也钉住：多一格或少一格都说明契约变了。 */
export const FEEDBACK_BODY_KEYS = ['filename', 'signal']

/** filename 的硬上界，与后端 MAX_FILENAME_CHARS 与 0011 的 CHECK 同值。 */
export const MAX_FILENAME_CHARS = 512

/** 一次评价的状态机。五个态，记上与没确认那两支都没有回头路。 */
export const PHASE_IDLE = 'idle'
export const PHASE_SENDING = 'sending'
export const PHASE_RECORDED = 'recorded'
export const PHASE_FAILED = 'failed'
export const PHASE_UNCERTAIN = 'uncertain'

const PHASES = [PHASE_IDLE, PHASE_SENDING, PHASE_RECORDED, PHASE_FAILED, PHASE_UNCERTAIN]

/** 失败脸的档位：每一档话不同，共同的底线是绝不说「已记录」。 */
export const FACE_OFFLINE = 'offline'
export const FACE_TIMEOUT = 'timeout'
export const FACE_UNAUTHORIZED = 'unauthorized'
export const FACE_DENIED = 'denied'
export const FACE_MISSING = 'missing'
export const FACE_BODY_REFUSED = 'body_refused'
export const FACE_STORAGE = 'storage'
export const FACE_UNKNOWN = 'unknown'
export const FACE_UNCONFIRMED = 'unconfirmed'
export const FACE_TOO_LONG = 'too_long'
export const FACE_NO_FILENAME = 'no_filename'

const text = value => (typeof value === 'string' ? value.trim() : '')
const isSignal = value => SIGNALS.indexOf(text(value)) >= 0

/** 这一处出处的记账对象：后端按文件名计数，所以态也按文件名存。 */
export function rowFilename(row) {
  return text(row && typeof row === 'object' ? row.filename : '')
}

/** 文件名超出上界时后端必然拒收（422），与其吃了个闭门羹不如当场说清。 */
export function filenameTooLong(name) {
  return text(name).length > MAX_FILENAME_CHARS
}

function hasControlLine(name) {
  return /[\r\n\u0000]/.test(String(name))
}

/**
 * 这一行能不能评价：没名字、名字带换行、名字超出那一格的上界，三样都算不能。
 * 不能就不摆按钮，改成把原因先写在屏上（见 rowFeedbackBlocked）——摆一枚按了只会
 * 弹出一句「送不出去」的按钮，比不摆更坏，而静悄悄少两枚按钮是把话咽了。
 */
export function rowMarkable(row) {
  const name = rowFilename(row)
  return Boolean(name) && !hasControlLine(name) && !filenameTooLong(name)
}

/** 两枚值以外的 signal 一律不发：后端只会回 422，而那一发是白写的账。 */
export function signalLabel(signal) {
  return SIGNAL_LABELS[text(signal)] || ''
}

/**
 * 画不出按钮的那一行也要把原因说出口：出处卡片里连名字都没有的一行，
 * 静悄悄少两枚按钮＝员工今天想夸一句而找不到地方，与「本轮没检索到」同族的那张哑脸。
 */
export function rowFeedbackBlocked(row) {
  const name = rowFilename(row)
  if (!name) return refusalView('no_filename')
  if (hasControlLine(name)) return refusalView('bad_filename')
  if (filenameTooLong(name)) return refusalView('too_long')
  return null
}

export function initialFeedbackState() {
  return {
    phase: PHASE_IDLE,
    signal: '',
    view: null,
    acceptedCount: null,
    rejectedCount: null,
  }
}

function normalizeState(state) {
  const base = initialFeedbackState()
  if (!state || typeof state !== 'object') return base
  return {
    phase: PHASES.indexOf(state.phase) >= 0 ? state.phase : base.phase,
    signal: isSignal(state.signal) ? state.signal : base.signal,
    view: state.view && typeof state.view === 'object' ? state.view : null,
    acceptedCount: countOf(state.acceptedCount),
    rejectedCount: countOf(state.rejectedCount),
  }
}

/**
 * 按得动按不动，只由这一处判：
 *   idle / failed 可点——失败那一次后端没有入账，重试不是第二枚信号，是把同一枚补上；
 *   sending 按住——两枚互斥，别让一次点击抢出两笔相反的账；
 *   recorded / uncertain 按住——记上了改不了，没确认的那一笔也不许再点。
 */
export function canSendSignal(state) {
  const current = normalizeState(state)
  return current.phase === PHASE_IDLE || current.phase === PHASE_FAILED
}

/** 按下去：返回新的态（不原地改），不该发的时候返回 null，组件据此一动不动。 */
export function requestFeedback(state, signal) {
  const current = normalizeState(state)
  if (!canSendSignal(current)) return null
  if (!isSignal(signal)) return null
  return { ...current, phase: PHASE_SENDING, signal: text(signal), view: null }
}

/** 两枚按钮各自的画法：点亮只能等回执，sending 期间一枚都不许亮。 */
export function feedbackButtonProps(state, signal) {
  const current = normalizeState(state)
  const known = isSignal(signal)
  return {
    disabled: !canSendSignal(current) || !known,
    pressed: known && current.phase === PHASE_RECORDED && current.signal === text(signal),
    busy: known && current.phase === PHASE_SENDING,
  }
}

/** 一次落定的读数（后端两枚计数）；认不下就是认不下，不补 0。 */
function countOf(value) {
  if (value === null || value === undefined || value === '') return null
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

function view(face, headline, detail, retryable) {
  return { kind: 'failed', face, headline, detail, retryable: Boolean(retryable) }
}

/**
 * 没读到确认回执（200 但形状不是契约那一枚）。这一支【不可重试】：
 * 服务端可能已经入账，再点一次就是两笔。所以它既不亮已完成，也不留第二下。
 */
function unconfirmedView() {
  return {
    kind: 'uncertain',
    face: FACE_UNCONFIRMED,
    headline: '这一下没读到确认回执',
    detail: '服务端回的是成功，但回执里没有我们认得的那几格，所以这里既不能替你确认记下，'
      + '也不宜再点一次——再点会多记一笔。',
    retryable: false,
  }
}

/** 本地就拒发的三种形状：请求根本没出去，也就没有任何一笔账被写过。 */
function refusalView(reason) {
  if (reason === 'too_long') {
    return view(FACE_TOO_LONG,
      '这份资料的名称太长，评价送不出去',
      '服务端记笔数的名称有长度上限，这一份超出了上限，所以请求没有发出去，也没有记上任何一笔。',
      false)
  }
  if (reason === 'no_filename') {
    return view(FACE_NO_FILENAME,
      '这一行没有可记录的出处名称',
      '后端按资料名记这笔评价，这一行连名字都没有，所以请求没有发出去。',
      false)
  }
  if (reason === 'bad_filename') {
    return view(FACE_NO_FILENAME,
      '这份资料的名称里有换行，评价送不出去',
      '后端不接受带换行的资料名，这一行的请求没有发出去，也没有记上任何一笔。',
      false)
  }
  return view(FACE_UNKNOWN,
    '这一枚评价值不认识，请求没有发出去',
    '后端只认「有用」与「没用」两枚值，别的一律不收；这一发没有送出去，也没有记上。',
    false)
}

/**
 * 失败那一张脸：档位不同、话不同，一条共同底线——每一句都写清「没有记上」。
 * 句子里的码名不进正文：走 lib/errcodes.js 的字典（no-bare-code 那道闸）。
 */
export function signalFailureView(err) {
  const code = errorCodeOf(err)
  const status = Number(err && err.response ? err.response.status : err && err.status) || 0
  const sentence = errorDetail(err, '服务端没有回话，这一笔评价没有记上。')

  if (code === 'authentication_required' || status === 401) {
    return view(FACE_UNAUTHORIZED, '评价没送出去：登录状态已经过期',
      '这一处出处没有记上。' + sentence + '重新登录后再点一次就可以。', false)
  }
  if (code === 'permission_denied' || status === 403) {
    return view(FACE_DENIED, '评价没送出去：这份资料你现在记不了',
      '这一处出处没有记上。' + sentence
        + '能不能给一份资料记评价，走的就是能不能看见它的同一道判定，不另开一条。', false)
  }
  if (code === 'resource_not_found' || status === 404) {
    return view(FACE_MISSING, '评价没送出去：资料库里没有这份文件',
      '这一处出处没有记上。' + sentence + '资料被移除或换过版本时会长这样，过一会儿再问一次未必能记上。', false)
  }
  if (code === 'validation_error' || status === 422) {
    return view(FACE_BODY_REFUSED, '评价没送出去：这次提交被服务端挡下',
      '这一处出处没有记上。' + sentence
        + '出口只认资料名与「有用 / 没用」两格，反复出现请把这一屏报给管理员。', false)
  }
  if (code === 'storage_unavailable' || code === 'model_unavailable') {
    return view(FACE_STORAGE, '评价没送出去：服务端的计数表没写成',
      '这一处出处没有记上。' + sentence, false)
  }
  if (code === 'task_timeout') {
    return view(FACE_TIMEOUT, '评价没送出去：这一等没有等到回音',
      '请求发出去了，但服务端没在时限内回话，所以这一处到底记没记上说不准；再点一次有可能多记一笔。', true)
  }
  if (!err || !err.response) {
    return view(FACE_OFFLINE, '评价没送出去：连不上服务端',
      '这一处出处没有等到回执。' + sentence + '要是这一笔其实已经到了，再点一次会多记一笔。', true)
  }
  return view(FACE_UNKNOWN, '评价没送出去：没读到确认',
    '这一处出处没有记上。' + sentence, true)
}

/**
 * 200 回执的认法：status 与 signal 两格都得对上号才敢点亮按钮。
 * 计数原样带回去但不画进卡片——那两个数是这份资料的全站累计，不是「你点了几次」，
 * 摆在个人评价旁边会被读成后者，那是另一句假话。
 */
export function receiptView(data, { filename = '', signal = '' } = {}) {
  const body = data && typeof data === 'object' ? data : null
  if (!body) return unconfirmedView()
  const sent = isSignal(signal) ? text(signal) : ''
  if (String(body.status || '') !== 'ok' || !sent || String(body.signal || '') !== sent) {
    return unconfirmedView()
  }
  const named = text(body.filename)
  if (named && text(filename) && named !== text(filename)) return unconfirmedView()
  return {
    kind: 'recorded',
    face: 'recorded',
    signal: sent,
    acceptedCount: countOf(body.accepted_count),
    rejectedCount: countOf(body.rejected_count),
  }
}

/** 落定：把发送结果折回状态机。失败一律把 signal 清空——没有任何一枚按钮该亮着。 */
export function settleFeedback(state, result) {
  const outcome = result && typeof result === 'object' ? result : unconfirmedView()
  if (outcome.kind === 'recorded') {
    return {
      ...initialFeedbackState(),
      phase: PHASE_RECORDED,
      signal: isSignal(outcome.signal) ? outcome.signal : '',
      acceptedCount: countOf(outcome.acceptedCount),
      rejectedCount: countOf(outcome.rejectedCount),
    }
  }
  return {
    ...initialFeedbackState(),
    phase: outcome.kind === 'uncertain' ? PHASE_UNCERTAIN : PHASE_FAILED,
    view: outcome,
  }
}

/**
 * 请求体的唯一组装点：只可能有两枚键。
 * 返回 null 的意思是这一发根本不该出门（缺名、超长、带换行、值不认识）。
 */
export function feedbackRequestBody(filename, signal) {
  const name = text(filename)
  if (!name || hasControlLine(name) || name.length > MAX_FILENAME_CHARS) return null
  if (!isSignal(signal)) return null
  return { filename: name, signal: text(signal) }
}

/**
 * 发一枚信号。永远走 lib/http.js 那一个实例（Bearer 由它的请求拦截器挂上），
 * 这里不写第二份网络出口；返回的是【视图】而不是抛异常，组件拿到的形状与后端真回执同构。
 */
export async function sendDocumentSignal(filename, signal, client = http) {
  const name = text(filename)
  if (!name || hasControlLine(name)) return refusalView(name ? 'unknown_signal' : 'no_filename')
  if (name.length > MAX_FILENAME_CHARS) return refusalView('too_long')
  if (!isSignal(signal)) return refusalView('unknown_signal')
  const body = feedbackRequestBody(name, signal)
  if (!body) return refusalView('no_filename')
  try {
    const response = await client.post(FEEDBACK_PATH, body)
    return receiptView(response && response.data, { filename: name, signal })
  } catch (err) {
    return signalFailureView(err)
  }
}

/**
 * 卡片那一行的说明句：没话说就留白，绝不在 idle 时预告「已记录」。
 * sending 那一句刻意不说完成——回执没回来之前按钮不亮，字也不亮。
 */
export function feedbackNotice(state) {
  const current = normalizeState(state)
  if (current.phase === PHASE_SENDING) {
    return { headline: '正在送出这处出处的评价…', detail: '', face: PHASE_SENDING }
  }
  if (current.phase === PHASE_RECORDED) {
    const label = signalLabel(current.signal)
    if (!label) return { headline: '', detail: '', face: PHASE_RECORDED }
    return {
      headline: '这处出处已记下「' + label + '」。',
      detail: '一处出处只记一次，记上就改不了：后端没有留撤回的门。',
      face: PHASE_RECORDED,
    }
  }
  if (current.phase === PHASE_FAILED || current.phase === PHASE_UNCERTAIN) {
    const settled = current.view || unconfirmedView()
    return {
      headline: settled.headline || '这处出处的评价没有记上。',
      detail: settled.detail || '',
      face: settled.face || FACE_UNKNOWN,
    }
  }
  return { headline: '', detail: '', face: PHASE_IDLE }
}

/** 按钮的人话全称：屏幕阅读器只读到一枚「有用」时，得知道它在说哪一份资料。 */
export function feedbackAriaLabel(signal, filename) {
  const label = signalLabel(signal)
  const name = text(filename)
  if (!label) return ''
  return '把这处出处『' + (name || '未具名资料') + '』标记为' + label
}

/** 两枚按钮那一组的名字：屏上读不出「采纳 / 驳回」这种内部词。 */
export const FEEDBACK_GROUP_LABEL = '这处出处对你有帮助吗'