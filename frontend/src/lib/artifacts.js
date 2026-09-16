import { http } from './http'
import { readBlobError } from './errcodes'

// Artifact bodies live behind authenticated routes (GET /api/v1/artifacts/{id}/content),
// so an <img src> cannot load them: the browser sends no Authorization header on image
// subresource requests. Every generated file is therefore pulled as a Blob through the
// shared axios instance (which attaches the Bearer token) and displayed from an object URL.

const API_PREFIX = '/api/v1'

export function resolveArtifactUrl(url) {
  if (!url || typeof url !== 'string') return ''
  const trimmed = url.trim()
  if (/^(blob:|data:)/i.test(trimmed)) return trimmed
  if (/^https?:\/\//i.test(trimmed)) return trimmed
  const path = trimmed.startsWith('/') ? trimmed : `/${trimmed}`
  return path.startsWith(API_PREFIX) ? path : `${API_PREFIX}${path}`
}

export function isArtifactRequest(url) {
  const resolved = resolveArtifactUrl(url)
  return !!resolved && !/^(blob:|data:)/i.test(resolved)
}

function createObjectUrl(blob) {
  if (typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') {
    throw new Error('当前浏览器不支持本地取图')
  }
  return URL.createObjectURL(blob)
}

export async function fetchArtifactBlob(url, { signal } = {}) {
  const target = resolveArtifactUrl(url)
  if (!target) {
    const error = new Error('缺少图表地址')
    error.code = 'missing_url'
    throw error
  }

  let response
  try {
    // baseURL:'' keeps /static/... and absolute URLs from being rewritten under /api/v1.
    response = await http.get(target, { baseURL: '', responseType: 'blob', timeout: 30000, signal })
  } catch (err) {
    const status = err?.response?.status
    const blob = err?.response?.data
    if (blob instanceof Blob && status) {
      // errcodes 的通用解析器接手（A-4-1）。私拷那份只回一个字符串，既不接 status，
      // 又会把后端原串（常常就是裸码名 permission_denied）当文案抛给界面；
      // 这里把 status 传进去，非 JSON / 空 body 也能按 HTTP 状态归类成一句人话。
      const result = await readBlobError(blob, status)
      const error = new Error(result.message)
      error.status = status
      error.code = result.code || `http_${status}`
      error.retryable = result.retryable
      throw error
    }
    if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') {
      const error = new Error('取图已取消')
      error.code = 'aborted'
      throw error
    }
    const error = new Error(err?.message || '取图失败')
    error.code = err?.code || 'network_error'
    throw error
  }

  if (!response || (response.status < 200 || response.status >= 300)) {
    const status = response?.status ?? 0
    const error = new Error(`取图失败（HTTP ${status}）`)
    error.status = status
    error.code = `http_${status}`
    throw error
  }

  const blob = response.data
  if (!blob || !blob.size) {
    const error = new Error('图表内容为空')
    error.code = 'empty_artifact'
    throw error
  }

  const objectUrl = createObjectUrl(blob)
  let revoked = false
  return {
    objectUrl,
    blob,
    mediaType: blob.type || 'image/png',
    size: blob.size,
    revoke() {
      if (revoked) return
      revoked = true
      try {
        URL.revokeObjectURL(objectUrl)
      } catch (_) { /* already released */ }
    },
  }
}