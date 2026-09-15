import { http } from './http'

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

function readBlobError(blob) {
  // A 4xx/5xx body is JSON, but responseType:'blob' hands it back as a Blob.
  return blob.text().then(text => {
    try {
      const parsed = JSON.parse(text)
      return parsed?.detail || parsed?.error_code || text.slice(0, 120) || ''
    } catch (_) {
      return ''
    }
  }).catch(() => '')
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
      const detail = await readBlobError(blob)
      const error = new Error(detail || `取图失败（HTTP ${status}）`)
      error.status = status
      error.code = detail || `http_${status}`
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