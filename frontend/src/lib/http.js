import axios from 'axios'

// 全站唯一的 HTTP 入口：一个 axios 实例、一个 token 来源、一条 401 处理路径。
// 需要流式读取的地方（SSE）走 authedFetch，但它取的是同一个 token。

export const API_BASE = '/api/v1'
export const TOKEN_KEY = 'eb_token'
export const USER_KEY = 'eb_user'
export const ROLE_KEY = 'eb_role'
export const DEPARTMENT_KEY = 'eb_department'
export const EXPIRES_KEY = 'eb_token_expires_at'
export const EXPIRY_REMINDER_MS = 5 * 60 * 1000

export const http = axios.create({ baseURL: API_BASE, timeout: 30000 })

let listener = null
let lastUnauthorizedAt = 0

function emit(event) {
  if (!listener) return
  try {
    listener(event)
  } catch (_) { /* 界面订阅者出错不能影响请求链 */ }
}

// App.vue 订阅这里，Toast 与回登录都由它统一呈现。
export function subscribeAuth(handler) {
  listener = handler
  return () => { listener = null }
}

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch (_) {
    return ''
  }
}

export function hasSession() {
  return !!getToken()
}

export function saveSession(payload = {}) {
  const token = payload.token || ''
  if (!token) return
  const expiresIn = Number(payload.expires_in ?? payload.expiresIn ?? 0)
  try {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, payload.username || '')
    localStorage.setItem(ROLE_KEY, payload.role || 'staff')
    localStorage.setItem(DEPARTMENT_KEY, payload.department || '')
    if (Number.isFinite(expiresIn) && expiresIn > 0) {
      localStorage.setItem(EXPIRES_KEY, String(Date.now() + expiresIn * 1000))
    } else {
      localStorage.removeItem(EXPIRES_KEY)
    }
  } catch (_) { /* 隐私模式下内存态仍然可用 */ }
}

export function clearSession() {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    localStorage.removeItem(ROLE_KEY)
    localStorage.removeItem(DEPARTMENT_KEY)
    localStorage.removeItem(EXPIRES_KEY)
  } catch (_) { /* 同上 */ }
}

export function msUntilExpiry() {
  let raw = null
  try {
    raw = localStorage.getItem(EXPIRES_KEY)
  } catch (_) {
    return Infinity
  }
  if (!raw) return Infinity // 服务端没给有效期就不猜
  const at = Number(raw)
  if (!Number.isFinite(at)) return Infinity
  return at - Date.now()
}

function isLoginRequest(target) {
  return String(target || '').includes('/login')
}

function handleUnauthorized() {
  if (!hasSession()) return
  const now = Date.now()
  if (now - lastUnauthorizedAt < 3000) return // 并发请求只提示一次
  lastUnauthorizedAt = now
  clearSession()
  emit({ type: 'unauthorized', message: '登录状态已失效，请重新登录。' })
}

http.interceptors.request.use(config => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  response => response,
  error => {
    const status = error?.response?.status
    if (status === 401 && !isLoginRequest(error?.config?.url)) handleUnauthorized()
    return Promise.reject(error)
  },
)

// 到期前提醒；真的过期了就与 401 走同一条收尾路径。
export function startExpiryWatch(intervalMs = 20000) {
  let reminded = false
  const tick = () => {
    const remaining = msUntilExpiry()
    if (remaining === Infinity) return
    if (remaining <= 0) {
      clearInterval(timer)
      handleUnauthorized()
      return
    }
    if (!reminded && remaining <= EXPIRY_REMINDER_MS) {
      reminded = true
      const minutes = Math.max(1, Math.round(remaining / 60000))
      emit({ type: 'expiring', message: `登录状态将在约 ${minutes} 分钟后过期，请提前重新登录。` })
    }
  }
  const timer = setInterval(tick, intervalMs)
  tick()
  return () => clearInterval(timer)
}

export async function authedFetch(path, { headers, ...options } = {}) {
  const merged = { ...(headers || {}) }
  const token = getToken()
  if (token) merged.Authorization = `Bearer ${token}`
  const url = String(path).startsWith('http') ? path : `${API_BASE}${path}`
  const response = await fetch(url, { ...options, headers: merged })
  if (response.status === 401 && !isLoginRequest(path)) handleUnauthorized()
  return response
}

// 错误文案只认服务端 detail / 稳定码，不再用问号占位串。
// TODO(B 线 / G2 合并后)：文案映射应由 lib/errcodes.js 提供，此处只留一条取原始 detail 的通道。
// 已知短板：responseType:'blob' 的错误体（文档/数据下载）读不到 detail，只能落回兜底文案；
// artifacts.js 里有 readBlobError() 的先例，是否通用化由总控定，A 线不动 errcodes.js。
/**
 * 从后端三种错误形状里只取「稳定码」本身，不做任何文案映射 ——
 * 文案映射表本体归 lib/errcodes.js（见上面那条 TODO 与 B-5），在这里多写一句人话都会撞车。
 * 用途只有一个：面板要判断「这一步该画哪张脸」。R1(c) 裁定 403 与空列表必须分开渲染，
 * 判据是 detail 等于 canonical 稳定码 permission_denied（app/common/policy.py:157-158 产出），
 * 不是 HTTP 状态码本身。
 * 形状 1 字符串码 / 形状 2 ErrorEnvelope / 形状 3 FastAPI 422 列表 / 无响应（断网）。
 */
export function errorCode(err) {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail.trim()
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const code = detail.error_code || detail.code
    if (code) return String(code).trim()
  }
  return ''
}

export const PERMISSION_DENIED = 'permission_denied'

/** true = 这一步是「没权限」，不是「没数据」，也不是「服务坏了」：给无权限卡，且不给重试按钮。 */
export function isPermissionDenied(err) {
  return errorCode(err) === PERMISSION_DENIED
}

export function errorDetail(err, fallback = '请求失败') {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail === 'object') {
    const code = detail.error_code || detail.code
    if (code) return String(code)
  }
  const message = err?.message
  if (typeof message === 'string' && message.trim() && !/^Request failed with status code \d+$/.test(message)) return message
  return fallback
}

export default http