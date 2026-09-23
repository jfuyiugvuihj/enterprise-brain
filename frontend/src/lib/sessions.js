import { nextTick, shallowRef } from 'vue'
import { http } from './http'
import { formatError } from './errcodes'
// normalizeError 另起一行 import 而不是并进上面那行：lib/sessions-error-text.test.js:22 把
// "import { formatError } from './errcodes'" 整行字面量钉住了，那是别人已并树的断言，本单
// 不放宽也不删。字典仍然只有 errcodes 这一本，取码通道仍然只有一条，只是多认一个入口函数。
// 入队失败的错误体是 {code, message} 对象（chat.py::_enqueue_ask_turn 的 503），老写法
// `payload?.detail || detail` 会把整个对象塞进模板字面量，界面渲染成 [object Object]。
import { normalizeError } from './errcodes'

// 会话状态放在模块级 shallowRef，面板卸载也不会丢：切走再回来还是同一份会话。
// 等 V3 上了 router，这份 store 直接交给路由上下文接管。
export const SESSIONS_KEY = 'eb_sessions_v2'
const MESSAGE_KEY_PREFIX = 'eb_msg_'
const MESSAGE_KEY = id => `${MESSAGE_KEY_PREFIX}${id}`

export const sessions = shallowRef([])
export const activeId = shallowRef('')
export const messages = shallowRef([])
export const activeDataFilename = shallowRef('')
export const loading = shallowRef(false)
export const hitl = shallowRef(null)
export const scrollOffset = shallowRef(0)

let controller = null
let flushTimer = null

export function genId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function readNumber(value, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

export function titleOf(list) {
  const first = (list || []).find(m => m.role === 'user')
  return first ? String(first.content || '').slice(0, 30) : ''
}

export function persist() {
  const slim = sessions.value.map(s => {
    try {
      localStorage.setItem(MESSAGE_KEY(s.id), JSON.stringify(s.messages || []))
    } catch (_) { /* 配额满时保留内存态 */ }
    const { messages: _drop, ...rest } = s
    return rest
  })
  try {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify({ activeId: activeId.value, sessions: slim }))
  } catch (_) { /* 同上 */ }
}

export function flush() {
  if (flushTimer) return
  flushTimer = setTimeout(() => {
    flushTimer = null
    persist()
  }, 800)
}

export function syncActive() {
  if (!activeId.value) return
  const entry = {
    id: activeId.value,
    title: titleOf(messages.value),
    msgCount: messages.value.filter(m => m.role === 'user').length,
    updatedAt: Date.now(),
    dataFilename: activeDataFilename.value,
    messages: [...messages.value],
  }
  const existing = sessions.value.find(s => s.id === activeId.value)
  if (existing) Object.assign(existing, entry)
  else sessions.value = [entry, ...sessions.value]
  persist()
}

export function ensureSession() {
  if (!activeId.value) activeId.value = genId()
  if (!sessions.value.find(s => s.id === activeId.value)) {
    sessions.value = [{
      id: activeId.value,
      title: titleOf(messages.value),
      msgCount: 0,
      updatedAt: Date.now(),
      dataFilename: activeDataFilename.value,
      messages: [...messages.value],
    }, ...sessions.value]
  }
}

export function loadSessions() {
  let raw = null
  try {
    raw = localStorage.getItem(SESSIONS_KEY)
  } catch (_) { return '' }
  if (!raw) return ''
  try {
    const data = JSON.parse(raw)
    sessions.value = (data.sessions || []).map(s => {
      let msgs = []
      try {
        const mr = localStorage.getItem(MESSAGE_KEY(s.id))
        if (mr) msgs = JSON.parse(mr) || []
      } catch (_) { msgs = [] }
      return { ...s, messages: msgs }
    })
    return data.activeId || ''
  } catch (_) {
    return ''
  }
}

/** 本机 store 里这一条会话的消息正文；没有这一条就返回 null（不新建，判据④那条老规矩）。 */
export function localMessagesOf(id) {
  const sessionId = textOf(id)
  if (!sessionId) return null
  // 正被这一屏用着的那一份以 messages.value 为准：流式进行中的正文还没落盘，
  // 从 sessions 里读到的是上一轮的副本，拿它定位会把最新一轮当成链接那一轮。
  if (sessionId === activeId.value) return messages.value
  const entry = sessions.value.find(s => String(s.id) === sessionId)
  return entry ? entry.messages || [] : null
}

export function restoreActive(id) {
  const entry = sessions.value.find(s => s.id === id)
  messages.value = entry ? [...entry.messages] : []
  activeDataFilename.value = entry?.dataFilename || ''
  scrollOffset.value = readNumber(entry?.scrollTop)
}

export function newSession() {
  syncActive()
  activeId.value = genId()
  messages.value = []
  activeDataFilename.value = ''
  hitl.value = null
  scrollOffset.value = 0
  ensureSession()
  persist()
}

export function switchSession(id) {
  if (id === activeId.value) return
  rememberScroll()
  syncActive()
  activeId.value = id
  restoreActive(id)
  persist()
}

export function rememberScroll() {
  // 由面板在滚动、卸载或切页前写入，回来时按同一偏移恢复。
  const entry = sessions.value.find(s => s.id === activeId.value)
  if (!entry) return
  if (entry.scrollTop === scrollOffset.value) return // 值没变就别白落一次盘
  entry.scrollTop = scrollOffset.value
  syncActive()
}

// 会话正文按会话拆在 eb_msg_<id> 里，只清 SESSIONS_KEY 会留下一整包别人问过的话。
export function clearStoredSessions() {
  try {
    const keys = []
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index)
      if (key === SESSIONS_KEY || key?.startsWith(MESSAGE_KEY_PREFIX)) keys.push(key)
    }
    keys.forEach(key => localStorage.removeItem(key))
  } catch (_) { /* 隐私模式下没有本地态可清 */ }
}

// 换人使用的收口：上一位用户的会话不能出现在下一位用户的界面里。
// 登出与 401/过期都走 App.vue 的 goToLogin()，那条链只有一处出口，所以这里只被调用一次。
export function resetSessions() {
  // 先断流：不中止的话，在跑的回答会继续往 messages 里追加，等于清完又漏回去。
  abortStream()
  if (flushTimer) {
    clearTimeout(flushTimer)
    flushTimer = null
  }
  activeId.value = ''
  sessions.value = []
  messages.value = []
  activeDataFilename.value = ''
  hitl.value = null
  scrollOffset.value = 0
  loading.value = false
  clearStoredSessions()
}

export async function removeSession(id) {
  const wasActive = id === activeId.value
  sessions.value = sessions.value.filter(s => s.id !== id)
  try { localStorage.removeItem(MESSAGE_KEY(id)) } catch (_) { /* 已不存在 */ }
  if (!sessions.value.length) newSession()
  else if (wasActive) {
    activeId.value = sessions.value[0].id
    restoreActive(activeId.value)
  }
  persist()
  // 后端删除结果必须显式判定，不能只吞异常。
  const response = await http.delete(`/sessions/${id}`)
  return response.status >= 200 && response.status < 300
}

export function beginStream() {
  controller = new AbortController()
  loading.value = true
  return controller.signal
}

export function endStream() {
  controller = null
  loading.value = false
}

export function abortStream() {
  controller?.abort()
  controller = null
}

export function isStreaming() {
  return !!controller
}

export async function scrollTo(el, behavior = 'smooth') {
  await nextTick()
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior })
}

// ==================== 流式事件协议 ====================
// canonical envelope（event 名带点、data 里有 request_id/sequence/status）优先采信；
// 旧的 status/text/step/hitl/error/done/heartbeat 只作为正文兜底；
// 其余一律丢弃且不崩，未知事件名走 default 分支。

export const CANONICAL_PREFIXES = ['request.']
export const LEGACY_EVENTS = new Set(['status', 'text', 'step', 'hitl', 'error', 'cancelled', 'done', 'heartbeat', 'queued'])

/**
 * 后端 SSE 事件名的【唯一认领表】（R150 判据① 的根因面）。
 *
 * 为什么要有这张表：R41 交出的 `sources` 事件被 isCanonicalEvent() 判成 canonical 之后落进
 * 下面的 default，塞进 state.unknownEvents 就再没有第二行代码读过它（全仓零读取方），于是
 * 「后端早就把这些字段吐到线上了」在界面上等于没有 —— R41 判据③ 的引用条至今没销账，就是
 * 这么销掉的。
 *
 * 口径：后端每一枚事件名都必须在这里有一句交代。render＝画进界面；note＝只进过程提示条；
 * terminal＝收尾信号；silent＝【显式选择不画】（heartbeat 只表示连接还活着，不是漏接）。
 * 新增一种后端事件而这里没登记 → src/lib/r150-event-claims.test.js 直接读
 * app/api/v1/chat.py 的出口枚举名字，当场红。不靠自觉，也不抄第二份清单。
 */
export const EVENT_CLAIMS = {
  // legacy 腿：chat.py 里直写帧与 sse_event() 的调用点
  status: 'note',
  text: 'render',
  step: 'render',
  hitl: 'render',
  error: 'render',
  cancelled: 'render',
  done: 'terminal',
  heartbeat: 'silent',
  queued: 'render',
  // canonical 信封：chat.py::canonical_sse_event 的调用点
  'request.started': 'silent',
  'request.completed': 'terminal',
  'request.failed': 'render',
  'request.cancelled': 'render',
  sources: 'render',
}

/** 名字不在这张表里＝前端还没认领；unknownEvents 的读取方与告警一律以它为准。 */
export function isClaimedEvent(event) {
  return Object.prototype.hasOwnProperty.call(EVENT_CLAIMS, String(event || ''))
}

function textOf(value) {
  return typeof value === 'string' ? value.trim() : ''
}

/**
 * canonical `sources` 事件的 data → 出处卡片的数据（chat.py:1547-1562 与 :2038-2053 两个出口）。
 *
 * 三枚计数各说各的事，一枚都不许合并：`sources` 是看得见的行，`hit_count` 是它们的条数，
 * `unauthorized_count` 是「检到了但这一条检索范围不给你看」的条数（chat.py:1558 同一口径）。
 * `scope_reason_code` 一格两用：正常时是可见范围的理由（app/rag/filters.py 的两枚 reason），
 * 取不到范围时后端把【错误码】塞进同一格（chat.py:294-305 的 except 分支）。这里只搬运不解释，
 * 「两种词汇必须分开说人话」归 lib/provenance.js。
 */
export function sourcesFromEnvelope(data) {
  const rows = Array.isArray(data?.sources) ? data.sources : []
  const counted = rows.map(sourceRowFromWire).filter(row => row.filename)
  const declared = Number(data?.hit_count)
  return {
    rows: counted,
    hitCount: Number.isFinite(declared) && declared >= 0 ? Math.trunc(declared) : counted.length,
    hiddenCount: Math.max(0, readNumber(data?.unauthorized_count, 0)),
    scopeReasonCode: textOf(data?.scope_reason_code),
  }
}

/**
 * 一行命中 → 卡片要用的字段。取不到的键【留空而不是造一个】：密级、版本、分都是后端给的。
 *
 * `excerpt`（命中句）今天不在这枚事件里：证据袋有它（app/agents/evidence.py:80），
 * 而 chat.py::_document_source_row 没把它抄进 sources 行 —— 那是后端那一格欠的账，本单
 * 只把读取位留好：它什么时候出现，什么时候上屏，不猜内容。
 */
function sourceRowFromWire(row) {
  const raw = row && typeof row === 'object' ? row : {}
  const score = Number(raw.score)
  const chunk = Number(raw.chunk_index)
  const version = Number(raw.document_version_id)
  const level = Number(raw.classification)
  return {
    filename: textOf(raw.source),
    sourceId: textOf(raw.source_id),
    chunkIndex: Number.isFinite(chunk) ? Math.trunc(chunk) : null,
    score: Number.isFinite(score) ? score : null,
    scoreType: textOf(raw.score_type),
    versionId: Number.isFinite(version) ? String(version) : textOf(raw.document_version_id),
    classification: Number.isFinite(level) ? String(level) : textOf(raw.classification),
    department: textOf(raw.department),
    excerpt: textOf(raw.excerpt) || textOf(raw.content),
    // 生效日期：chat.py::_document_source_row 今天没抄这一格，但真值在库里就有 ——
    // app/rag/indexing.py:102/361 的 version.published_at（574/640 写入，0002 迁移在册）。
    // 读取位按后端的命名法接住它，出现就上屏；一枚都没给就是空串，界面绝不自己补「今天」。
    effectiveDate: textOf(raw.effective_date) || textOf(raw.published_at) || textOf(raw.created_at),
    worker: textOf(raw.worker),
  }
}

/**
 * 缓存那张脸的读数来自【legacy `text` 帧的 payload】（chat.py:1307-1316：只有命中路径才带
 * cached / cache_generated_at / cache_note，实时路径一枚都不带）。
 *
 * 未命中也记一格，但记的是「我当场看到的回答帧没带这三枚」，不是「后端报了未命中」：
 *   cached:false + observed:true = 这一轮亲眼看着它实时生成（界面那句「本轮实时生成」只认这个）
 *   整格缺失                     = 这一轮没被当场观察到（从 localStorage 复原的老消息）—— 界面不说这一态
 * 把「没带字段」直接推成「当时是实时算的」是拿缺席当证据：本单之前入库的老消息里，缓存命中的那几条
 * 同样没带过这三枚，那样推会把它们一一标错。
 */
export function cacheFromFrame(payload) {
  const hit = payload && typeof payload === 'object' && 'cached' in payload
  return {
    cached: hit ? payload.cached === true : false,
    generatedAt: hit ? textOf(payload.cache_generated_at) : '',
    note: hit ? textOf(payload.cache_note) : '',
    observed: true,
  }
}

/**
 * `event: queued` 的回执（chat.py:1171-1181）：request_id 是后面轮询 /queue/status 的唯一入口。
 *
 * 回执里另外两枚字段说明「这一轮为什么被转成后台任务」，前端今天【一枚都不读】：
 * R32 的假控件禁令把「档」这个词钉在服务端真分出轻重之前不许出现在前端任何一处源码里
 * （tests/test_r32_lane_contract.py 判据⑥，枚枚文件全文搜词，注释与测试件一起算），而那两枚
 * 字段的值本身就是档位名。这不等于不解释排队原因——chat.py 给的那格是英文码名，直插进句子
 * 还会撞上 V6 裸码闸门。等 nodes.py 与 orchestrator 真按档分流那天，连同这格读取一起评审。
 */
export function queueFromFrame(payload) {
  return {
    requestId: textOf(payload?.request_id),
    status: textOf(payload?.status) || 'queued',
  }
}

export function parseSseFrame(frame) {
  if (typeof frame !== 'string' || !frame.trim()) return null
  let event = ''
  const dataLines = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    // id: / retry: / 以 ":" 开头的注释行：按协议忽略
  }
  if (!event && !dataLines.length) return null
  let payload = null
  if (dataLines.length) {
    try {
      payload = JSON.parse(dataLines.join('\n'))
    } catch (_) {
      return { event, payload: null, invalid: true }
    }
  }
  return { event, payload }
}

export function isCanonicalEvent(event, payload) {
  if (typeof event === 'string' && CANONICAL_PREFIXES.some(prefix => event.startsWith(prefix))) return true
  return !!(payload && typeof payload === 'object'
    && 'request_id' in payload
    && typeof payload.sequence === 'number')
}

export function createStreamState() {
  return {
    lastSequence: 0,
    terminal: null,
    // R174 判据一：这一轮在后端的身份（canonical 信封上的 request_id）。读到才有值，
    // 读不到留空串 —— 空串是「这一轮没有可核对的轮号」，不是「轮号不存在」。
    requestId: '',
    errorCode: '',
    awaitingHitl: false,
    pendingSteps: [],
    segments: [],
    sawText: false,
    unknownEvents: [],
  }
}

function ensureSteps(msg) {
  if (!Array.isArray(msg.steps)) msg.steps = []
  return msg.steps
}

export function createStreamReducer(msg, state) {
  return function reduce(parsed) {
    if (!parsed) return { action: 'ignored' }
    if (parsed.invalid) return { action: 'ignored' }
    const { event, payload } = parsed

    if (isCanonicalEvent(event, payload)) {
      const sequence = Number(payload?.sequence)
      if (Number.isFinite(sequence)) {
        if (sequence <= state.lastSequence) return { action: 'ignored' }
        state.lastSequence = sequence
      }
      // 轮号后端早就随每一枚 canonical 信封发出（app/api/v1/chat.py::canonical_sse_event 的
      // request_id），本文件此前只用 sequence 做乱序闸门，从没把它抄进消息里。于是这一轮
      // 落盘之后就没了身份，深链在本地也无从定位。这里补的是「第一次有人读后端早已发出的
      // 字段」，与 R150 读 sources / cached 同一手法：读到才记，读不到不写。
      const requestId = textOf(payload.request_id)
      if (requestId) {
        state.requestId = requestId
        if (!msg.requestId) msg.requestId = requestId
      }
      const data = payload?.data || {}
      switch (event) {
        case 'request.started':
          return { action: 'ignored' }
        case 'request.completed':
          state.terminal = state.terminal || 'completed'
          state.awaitingHitl = !!data.awaiting_hitl
          state.pendingSteps = Array.isArray(data.awaiting_steps) ? data.awaiting_steps : []
          return { action: 'terminal' }
        case 'request.failed':
          state.terminal = state.terminal || 'failed'
          if (data.error_code) state.errorCode = String(data.error_code)
          return { action: 'failed' }
        case 'request.cancelled':
          state.terminal = state.terminal || 'cancelled'
          return { action: 'cancelled' }
        case 'sources':
          // R41 判据③ 欠的账在这一格：出处事件不是「认不得的 canonical 事件」，它是正经载荷。
          // 顺序也在这儿吃 canonical 的 sequence 闸门：迟到的、重放的 sources 不会覆盖新一轮。
          msg.sources = sourcesFromEnvelope(data)
          return { action: 'sources', sources: msg.sources }
        default:
          // 走到这里＝后端新增了一种 canonical 事件、而本文件还没认领它（认领表见 EVENT_CLAIMS）。
          // 不崩是底线，但绝不静默：记名 → consumeSseStream 告警 → 界面画一句系统自陈 → 用例红。
          if (!state.unknownEvents.includes(event)) state.unknownEvents.push(event)
          return { action: 'unknown', event }
      }
    }

    if (!LEGACY_EVENTS.has(event)) {
      const name = event || '(anonymous)'
      if (!state.unknownEvents.includes(name)) state.unknownEvents.push(name)
      // 不带 event: 名的帧、以及 LEGACY_EVENTS 没登记过的新名字，走的是同一条「未认领」通道。
      // 只记名不往外报，等于没人会去读它 —— sources 就是这么在界面上消失了两年（R41 判据③）。
      return { action: 'unknown', event: name }
    }

    switch (event) {
      case 'text': {
        const chunk = typeof payload?.content === 'string' ? payload.content : ''
        if (!chunk) return { action: 'ignored' }
        if (msg._correcting) {
          msg.content = chunk
          msg._correcting = false
          state.segments = [chunk]
        } else if (state.segments.includes(chunk)) {
          return { action: 'ignored' }
        } else {
          const covering = state.segments.find(seg => chunk.includes(seg) && chunk !== seg)
          if (covering) msg.content = chunk
          else msg.content = `${msg.content || ''}${chunk}`
          state.segments = covering ? [chunk] : [...state.segments, chunk]
        }
        state.sawText = true
        // 缓存那三枚字段就骑在这一枚 text 帧上（chat.py:1315 的 payload 展开），没有第二条通道：
        // 读到就记。没读到【不写 msg.cache】—— 不许把「后端没带」记成 cached:false 那种它没报的读数。
        // 只有真正把正文续上的那一帧才走到这里（空帧与重复帧都在上面 return 了）：
        // 所以这一格记的是「亲眼见过一枚实时回答帧」，不是「这帧碰巧没带 cached」。
        const cache = cacheFromFrame(payload)
        msg.cache = cache
        // 把读数一起带出去：store 的 messages 是 shallowRef，光往消息对象上塞属性，
        // 面板不会重渲染。缓存那张脸要能当场出现，就得有一条能触发的通道。
        return { action: 'text', cache }
      }
      case 'step': {
        const steps = ensureSteps(msg)
        const running = payload?.status === 'running'
        const existing = steps.find(s => s.tool === payload?.tool && s.status === 'running')
        if (existing && !running) {
          existing.status = 'done'
          existing.elapsed = payload?.elapsed ?? null
        } else if (running) {
          if (msg.content) msg._correcting = true
          steps.push({ tool: payload?.tool, label: payload?.label, status: 'running', elapsed: null })
        } else if (payload?.tool) {
          steps.push({ tool: payload.tool, label: payload?.label, status: payload?.status || 'done', elapsed: payload?.elapsed ?? null })
        }
        return { action: 'step' }
      }
      case 'hitl':
        return { action: 'hitl', hitl: { pending: payload?.pending || [], labels: payload?.labels || [] } }
      case 'status': {
        const note = typeof payload?.content === 'string' ? payload.content : ''
        if (note) state.statusNote = note
        return { action: 'ignored' }
      }
      case 'error': {
        const detail = typeof payload?.content === 'string' ? payload.content : ''
        if (detail && !state.errorText) state.errorText = detail
        state.terminal = state.terminal || 'failed'
        return { action: 'failed' }
      }
      case 'cancelled':
        state.terminal = state.terminal || 'cancelled'
        return { action: 'cancelled' }
      case 'done':
        if (!state.terminal) state.terminal = 'completed'
        return { action: 'terminal' }
      case 'queued': {
        // 排队那张脸的起点。回执只给 request_id，位次与结果必须另读 /queue/status/{id}（判据④）。
        msg.queue = queueFromFrame(payload)
        return { action: 'queued', queue: msg.queue }
      }
      case 'heartbeat':
        // 【显式选择不画】：它只表示连接还活着，画出来是噪声。认领表里它是 silent，不是漏接。
        return { action: 'ignored' }
      default:
        // 走到这里＝名字在 LEGACY_EVENTS 里但本文件没给 case：这是自己漏接，不是后端新事件。
        if (!state.unknownEvents.includes(event || '(anonymous)')) state.unknownEvents.push(event || '(anonymous)')
        return { action: 'unknown', event: event || '(anonymous)' }
    }
  }
}

/**
 * SSE 失败帧 → 界面上一句人话。字典在 lib/errcodes.js（A-4-3 收口，这里不再有第二份码表）。
 * 前缀 [错误] 保留：后端把失败也写成 "[错误] ..." 塞进同一条回答里
 * （app/api/v1/chat.py:729、:1101），气泡要跟它同一形状，也才对着上 tests/
 * test_legacy_chat_retrieval_scope.py:124 那条断言。
 * 未知码不再把码本身当句子直出：走字典兜底句 + formatError 的「错误码：xxx」诊断小字，
 * 与 UiErrorState 的 codeLabel 同一条通道；气泡里没有可折叠区，只能inline带出来。
 * 顺序从"后端文本优先"改成"机器字段优先"：errorText 是自由文本，会夹裸码名，
 * 现在也一律先过字典（摘码名、清 HTML 与 axios 英文原句、截 300 字）再上屏。
 */
export function friendlyErrorText(state, fallback = '本轮回答未能完成') {
  const code = String(state.errorCode || '').trim()
  if (code) return `[错误] ${formatError({ detail: code })}`
  const backendText = String(state.errorText || '').trim()
  if (backendText) return `[错误] ${formatError({ detail: backendText })}`
  return `[错误] ${fallback}`
}

export function splitSseFrames(buffer) {
  const frames = buffer.split(/\r?\n\r?\n/)
  return { rest: frames.pop() ?? '', frames }
}

// send() 与 approve() 共用同一个读取器：响应状态只在这里判一次，
// 事件语义只在这里解释一次，两处不会再各写一份解析器。
export async function consumeSseStream(response, msg, handlers = {}) {
  const state = createStreamState()
  const reduce = createStreamReducer(msg, state)
  const signal = handlers.signal
  let stopped = null

  if (!response) return { ok: false, status: 0, state, error: '服务未返回响应', stopped: 'no_response' }
  if (!response.ok) {
    let body = null
    try {
      body = await response.clone().json()
    } catch (_) { /* 非 JSON 错误体：仍要按状态码归类出一句人话 */ }
    // 后端在入队失败这一格给的是 {code, message} 对象（chat.py::_enqueue_ask_turn 的 503
    // detail=ErrorEnvelope）。老写法把整个对象塞进模板字面量，界面渲染成 [object Object]，
    // 于是「排队系统不可用」这句最该说清的话变成一串噪声。归一只走 errcodes 一个通道。
    const normalized = normalizeError({
      status: response.status,
      detail: body?.detail ?? (body && typeof body === 'object' ? body : undefined),
    })
    return {
      ok: false,
      status: response.status,
      state,
      error: normalized.message,
      errorCode: normalized.code,
      retryable: normalized.retryable,
      // 归一成品整体带出：面板要画「没能排上队」那张脸时，第二次 normalizeError 会把
      // 未知码那格的 rawCode 洗成空串（小字静默消失）。给它成品，就不存在两套口径。
      normalized,
      stopped: 'http_error',
    }
  }
  if (!response.body) {
    return { ok: false, status: response.status, state, error: '服务未返回可读取的回答流', stopped: 'no_body' }
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  // 本轮已经报过的未认领事件名：一条一名报一次，不把控制台与界面刷成噪声。
  const unseen = new Set()

  while (!stopped) {
    if (signal?.aborted) { stopped = 'aborted'; break }
    let chunk
    try {
      chunk = await reader.read()
    } catch (err) {
      if (err?.name === 'AbortError' || signal?.aborted) { stopped = 'aborted'; break }
      throw err
    }
    if (chunk?.done) break

    buffer += decoder.decode(chunk.value, { stream: true })
    const split = splitSseFrames(buffer)
    buffer = split.rest
    for (const frame of split.frames) {
      const result = reduce(parseSseFrame(frame))
      switch (result.action) {
        case 'hitl':
          handlers.onHitl?.(result.hitl)
          stopped = 'hitl'
          break
        case 'failed':
          handlers.onFailed?.(state)
          break
        case 'cancelled':
          stopped = 'cancelled'
          break
        case 'text':
          handlers.onText?.(state)
          // 缓存三枚字段骑在 text 帧上（chat.py:1315），没有独立事件；单独回报一次，
          // 不必等整轮跑完才画得出「实时算 / 命中缓存」那张脸。
          if (result.cache) handlers.onCache?.(result.cache, state)
          break
        case 'sources':
          handlers.onSources?.(result.sources, state)
          break
        case 'queued':
          handlers.onQueued?.(result.queue, state)
          break
        case 'unknown':
          // 界面没认领的后端事件：告警 + 回调各一次，一名一次。静默丢掉就是 sources 当年的死法。
          if (!unseen.has(result.event)) {
            unseen.add(result.event)
            console.warn(`[SSE] 界面未认领的事件：${result.event}`)
            handlers.onUnknownEvent?.(result.event, state)
          }
          break
        case 'terminal':
        case 'ignored':
        default:
          break
      }
      if (stopped) break
    }
    if (stopped && stopped !== 'hitl') {
      try { await reader.cancel() } catch (_) { /* 流已关闭 */ }
    }
    await handlers.onBatch?.(state)
  }

  return { ok: true, status: response.status, state, stopped: stopped || 'done' }
}

// ==================== R174 · 「那一轮」在后端到底有没有 ====================
//
// 为什么这两条读取住在本文件而不在面板里：判据①第 2 件的原话是「站内点击与冷启动两条路最终
// 必须落到同一份 store，不许各存一套」，而这份 store 的真源就是本文件（sessions / activeId /
// messages 三枚 shallowRef）。把网络出口放在面板里，就会出现「面板里有一份后端正文、store 里
// 有一份本地正文」的两套；所以这里只多两件事：向后端问一次，问到的交回同一份 store。
//
// 🔴 一件本单做不到、也坚决没猜的事（已具名报总控，见交付说明里的 B 单）：
// GET /sessions/{session_id} 的返回体是 { session, messages }，而 messages 里每一条只有
// role / content / steps / created_at —— 轮号在这一格里根本不存在：
//   app/api/v1/chat.py:1280 建 session_messages 表，没有这一列；
//   app/api/v1/chat.py:763   INSERT 的字段清单里没有它；
//   app/api/v1/chat.py:801   SELECT 出来的三枚字段里也没有它；
//   app/api/v1/chat.py:755   内存回退分支构造的字典同样只有那四枚。
// 缺的是后端的一个字段，不是前端的一段代码。所以这里【只按字面读 request_id 一枚】：后端哪天
// 带上，跨机器就自动定位得到，本文件一字不改；今天一枚都不带，就报 turnIds:false，
// 绝不拿 created_at 或消息位次去猜「哪一条才是那一轮」—— 那是伪造定位，比不定位更坏。

/** 会话正文端点，逐字对齐 app/api/v1/chat.py:2588 的 GET /sessions/{session_id}。 */
export const sessionPath = id => `/sessions/${encodeURIComponent(String(id == null ? '' : id))}`

/** 会话名单端点：后端已按归属过滤（chat.py::list_sessions 只留 is_owned_by 为真的那些）。 */
export const SESSIONS_LIST_PATH = '/sessions'

/**
 * 一次「后端有没有这一条」的读数。四种落不到各是一种，不许并格（判据①第 4 件）：
 *   found       200 且 messages 是数组 —— 正文到手了，能不能再定位到某一轮是另一件事
 *   notFound    404 resource_not_found —— 后端的口径是「读不到就像不存在」
 *   notYours    401 / 403 —— 身份对不上，与「没有」是两句话
 *   unreachable 连接失败与 5xx —— 这格永远不许被说成「没有」
 *   badBody     200 但 messages 不是数组 —— 后端换了形状，也不许当成空会话
 */
export const SESSION_READ = {
  found: 'found',
  notFound: 'not_found',
  notYours: 'not_yours',
  unreachable: 'unreachable',
  badBody: 'bad_body',
}

/** 深链参数允许的形状：后端两枚 id 都是十六进制族（uuid hex / req-<hex> / 本地 genId 的 base36）。 */
export const DEEP_LINK_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$/

/** 轮号在后端正文里的字面名字：与 canonical 信封、与 ?request= 带的是同一枚值，只认这一个。 */
const TURN_ID_KEY = 'request_id'

function statusCodeOf(err) {
  const status = Number(err?.response?.status ?? err?.status)
  return Number.isFinite(status) ? status : 0
}

function classifySessionReadError(err) {
  const status = statusCodeOf(err)
  if (status === 404) return SESSION_READ.notFound
  if (status === 401 || status === 403) return SESSION_READ.notYours
  // 0 = 连上了却没响应/超时/DNS，5xx = 服务坏了：这两种都是「读不到」，不是「没有」。
  if (status === 0 || status >= 500) return SESSION_READ.unreachable
  return SESSION_READ.badBody
}

/**
 * 后端 messages 行 → store 里的消息形状。
 *
 * 逐字带 role / content / steps / created_at 四枚（这就是后端给的全部），轮号只在
 * 后端真的带上 request_id 时才存在；带不上就不写这一格，并整份标记 turnIds:false ——
 * 面板据此说「这一轮定位不到，因为后端读到的正文里没有轮号」，而不是说「没有这一轮」。
 */
export function backendSessionMessages(payload) {
  const list = Array.isArray(payload?.messages) ? payload.messages : null
  if (!list) return { ok: false, messages: [], turnIds: false }
  let turnIds = false
  const messages = list.filter(item => item && typeof item === 'object').map((item, index) => {
    const requestId = textOf(item[TURN_ID_KEY])
    if (requestId) turnIds = true
    return {
      role: textOf(item.role),
      content: textOf(item.content),
      steps: Array.isArray(item.steps) ? item.steps : [],
      created_at: item.created_at == null ? '' : String(item.created_at),
      requestId,
      // mid 是面板给每一轮起的钥匙（sources / 缓存那些派生脸用它）；后端行没有本地 mid，
      // 就按位次补一枚，只当身份用，不当内容用。
      mid: `backend-${index}`,
    }
  })
  return { ok: true, messages, turnIds }
}

/** 向后端问一次「这一条会话你那儿有正文吗」，并把正文原样带回来。 */
export async function readBackendSession(id) {
  const sessionId = textOf(id)
  if (!sessionId) return { outcome: SESSION_READ.badBody, messages: [], turnIds: false }
  let response = null
  try {
    response = await http.get(sessionPath(sessionId))
  } catch (err) {
    return { outcome: classifySessionReadError(err), messages: [], turnIds: false }
  }
  const read = backendSessionMessages(response?.data)
  if (!read.ok) return { outcome: SESSION_READ.badBody, messages: [], turnIds: false }
  return { outcome: SESSION_READ.found, messages: read.messages, turnIds: read.turnIds }
}

/**
 * 「后端有没有这一条」的名单（判据②的读数）。
 * known:false 说的是「这份名单没读到」，与「名单是空的」是两句话 —— 后者才等于「后端没有」。
 */
export async function readBackendSessionIds() {
  let response = null
  try {
    response = await http.get(SESSIONS_LIST_PATH)
  } catch (err) {
    return { known: false, ids: [], failure: classifySessionReadError(err) }
  }
  const list = Array.isArray(response?.data?.sessions) ? response.data.sessions : null
  if (!list) return { known: false, ids: [], failure: SESSION_READ.badBody }
  return { known: true, ids: list.map(row => textOf(row?.id)).filter(Boolean), failure: '' }
}

/** 这台浏览器的 store 里有没有这一条会话（判据②要分的那两格，只用它做对照，不再当裁决）。 */
export function hasLocalSession(id) {
  const sessionId = textOf(id)
  return Boolean(sessionId) && sessions.value.some(item => String(item.id) === sessionId)
}

/**
 * 后端读到的正文交回【同一份】store：切过去、落盘、以后就当普通历史看。
 * 走的是既有的 syncActive()，不另开第二份消息表；也不顺手新建会话 —— 只有真读到正文才谈得上交回。
 */
export function adoptBackendSession(id, list = []) {
  const sessionId = textOf(id)
  if (!sessionId) return []
  messages.value = (Array.isArray(list) ? list : []).map(item => ({ ...item }))
  activeId.value = sessionId
  activeDataFilename.value = ''
  hitl.value = null
  scrollOffset.value = 0
  syncActive()
  return messages.value
}
