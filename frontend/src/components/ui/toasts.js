/**
 * UiToast 的全局队列（模块级单例）。
 *
 * F7 的 7 处 `{{ error }}` 插值位改造后只需 `notifyError(err)`：
 * normalizeError 负责三种错误形状，这里负责展示、超时与可报告小字。
 */
import { computed, reactive, readonly } from 'vue'
import { errorCodeLabel, normalizeError } from '../../lib/errcodes.js'

const MAX_VISIBLE = 4
const DEFAULT_TIMEOUT = 6000

let sequence = 0

const state = reactive({
  toasts: [],
})

function inBrowser() {
  return typeof window !== 'undefined' && typeof window.document !== 'undefined'
}

export function pushToast(toast) {
  const message = typeof toast === 'string' ? { message: toast } : { ...(toast || {}) }
  const entry = {
    id: ++sequence,
    tone: message.tone || 'info',
    message: String(message.message || '').trim() || '操作没有完成，请稍后重试。',
    codeLabel: message.codeLabel || '',
    retryable: Boolean(message.retryable),
    timeout: Number.isFinite(message.timeout) ? message.timeout : DEFAULT_TIMEOUT,
  }
  state.toasts.push(entry)
  while (state.toasts.length > MAX_VISIBLE) state.toasts.shift()
  if (entry.timeout > 0 && inBrowser()) {
    window.setTimeout(() => dismissToast(entry.id), entry.timeout)
  }
  return entry.id
}

export function dismissToast(id) {
  const index = state.toasts.findIndex((toast) => toast.id === id)
  if (index >= 0) state.toasts.splice(index, 1)
}

export function clearToasts() {
  state.toasts.splice(0, state.toasts.length)
}

/** 任何 catch 块里的一行接入：自动过 normalizeError */
export function notifyError(err, fallbackMessage = '') {
  const result = normalizeError(err)
  return pushToast({
    tone: 'danger',
    message: result.message || fallbackMessage || '操作没有完成，请稍后重试。',
    codeLabel: errorCodeLabel(result),
    retryable: result.retryable,
  })
}

export function notifySuccess(message) {
  return pushToast({ tone: 'success', message })
}

export function useToasts() {
  return {
    toasts: readonly(state).toasts,
    count: computed(() => state.toasts.length),
    push: pushToast,
    dismiss: dismissToast,
    clear: clearToasts,
    notifyError,
    notifySuccess,
  }
}
