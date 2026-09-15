import { nextTick, shallowRef } from 'vue'
import { http } from './http'

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
        default:
          // 尚未认识的 canonical 事件（例如以后新增的 message.delta）：丢弃且不崩。
          if (!state.unknownEvents.includes(event)) state.unknownEvents.push(event)
          return { action: 'ignored' }
      }
    }

    if (!LEGACY_EVENTS.has(event)) {
      if (!state.unknownEvents.includes(event || '(anonymous)')) state.unknownEvents.push(event || '(anonymous)')
      return { action: 'ignored' }
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
        return { action: 'text' }
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
      case 'heartbeat':
      case 'queued':
      default:
        // heartbeat/queued 只表示还活着；default 保证任何新事件名都不会让前端崩。
        return { action: 'ignored' }
    }
  }
}

export function friendlyErrorText(state, fallback = '本轮回答未能完成') {
  const codes = {
    no_answer_produced: '本轮未产出任何结论（no_answer_produced），请重试或补充数据范围。',
    task_timeout: '请求超过系统处理时限（task_timeout）。',
    internal_error: '服务内部错误（internal_error）。',
    authorization_unavailable: '当前账号缺少部门授权范围（authorization_unavailable），请换带部门的账号或联系管理员。',
    authentication_required: '登录状态已失效（authentication_required），请重新登录。',
  }
  if (state.errorText) return `[错误] ${state.errorText}`
  if (state.errorCode && codes[state.errorCode]) return `[错误] ${codes[state.errorCode]}`
  if (state.errorCode) return `[错误] ${state.errorCode}`
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
    let detail = `HTTP ${response.status}`
    try {
      const payload = await response.clone().json()
      detail = payload?.detail || detail
    } catch (_) { /* 非 JSON 错误体 */ }
    return { ok: false, status: response.status, state, error: detail, stopped: 'http_error' }
  }
  if (!response.body) {
    return { ok: false, status: response.status, state, error: '服务未返回可读取的回答流', stopped: 'no_body' }
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

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
