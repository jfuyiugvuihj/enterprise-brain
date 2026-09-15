/**
 * UiUpload 的选取校验纯函数：扩展名 / MIME / 体积 / 单多文件。
 * 拒绝原因只使用 lib/errcodes.js 里已有的码名，不自造。
 */

/** `.pdf,.doc|application/pdf` → { extensions: ['pdf'], mimetypes: ['application/pdf'] } */
export function parseAccept(accept) {
  const tokens = String(accept || '')
    .split(',')
    .map((token) => token.trim().toLowerCase())
    .filter(Boolean)
  const extensions = []
  const mimetypes = []
  tokens.forEach((token) => {
    if (token.startsWith('.')) extensions.push(token.slice(1))
    else if (token.includes('/')) mimetypes.push(token)
    else extensions.push(token)
  })
  return { extensions, mimetypes }
}

function extensionOf(name) {
  const text = String(name || '')
  const dot = text.lastIndexOf('.')
  if (dot < 0 || dot === text.length - 1) return ''
  return text.slice(dot + 1).toLowerCase()
}

function mimetypeMatches(fileType, pattern) {
  const type = String(fileType || '').toLowerCase()
  if (!type || !pattern) return false
  if (pattern === type) return true
  if (pattern.endsWith('/*')) return type.startsWith(pattern.slice(0, -1))
  return false
}

/** 单个文件是否通过 accept；accept 为空即不限制 */
export function isAcceptable(file, accept) {
  const { extensions, mimetypes } = parseAccept(accept)
  if (!extensions.length && !mimetypes.length) return true
  if (extensions.includes(extensionOf(file?.name))) return true
  return mimetypes.some((pattern) => mimetypeMatches(file?.type, pattern))
}

export function formatBytes(bytes, unit = 'KB') {
  const value = Number(bytes)
  if (!Number.isFinite(value) || value < 0) return ''
  const base = unit === 'MB' ? 1024 * 1024 : 1024
  const digits = value / base >= 10 ? 0 : 1
  return `${(value / base).toFixed(digits)} ${unit}`
}

/**
 * 一次选取的批量校验。
 * @param {File[]|FileList} files
 * @param {{ accept?: string, multiple?: boolean, maxSizeMb?: number }} rules
 * @returns {{ accepted: unknown[], rejected: Array<{ file: unknown, code: string }> }}
 */
export function validateFiles(files, rules = {}) {
  const list = Array.isArray(files) ? files : Array.from(files || [])
  const { accept = '', multiple = true, maxSizeMb = 0 } = rules
  const accepted = []
  const rejected = []
  list.forEach((file) => {
    if (!multiple && accepted.length >= 1) {
      rejected.push({ file, code: 'validation_error' })
      return
    }
    if (!isAcceptable(file, accept)) {
      rejected.push({ file, code: 'unsupported_file' })
      return
    }
    const limit = Number(maxSizeMb) > 0 ? Number(maxSizeMb) * 1024 * 1024 : 0
    if (limit && Number(file?.size || 0) > limit) {
      rejected.push({ file, code: 'upload_too_large' })
    } else {
      accepted.push(file)
    }
  })
  return { accepted, rejected }
}
