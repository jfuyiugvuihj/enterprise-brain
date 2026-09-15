/**
 * 错误码字典（V5 / F7 叶子线产出）
 *
 * 后端错误体三种形状并存（工单 D-2），本模块统一成 { code, message, retryable }：
 *   形状 1 字符串稳定码   err.response.data.detail === "unsupported_file"
 *   形状 2 ErrorEnvelope  err.response.data.detail === { code, message, retryable, details }
 *                         来源 app/api/v1/observability.py 全部、chat.py::_document_index_error
 *   形状 3 FastAPI 422    err.response.data.detail === [{ loc, msg, type }, ...]
 *
 * 码名蓝本：app/agents/contracts.py::ErrorEnvelope.code（封闭枚举 16 码）
 * 追加 data.py 系列 7 码。线上出现的其它历史字符串走 LEGACY_ALIASES 归一，不自造码名。
 */

/** 蓝本 16 码 + data.py 7 码。文案面向业务同学，不出现接口路径与技术元数据。 */
export const ERROR_CODES = {
  authentication_required: { message: '登录状态已失效，请重新登录后再试。', retryable: false },
  permission_denied: { message: '当前账号没有这项权限，请联系管理员开通。', retryable: false },
  authorization_unavailable: { message: '暂时无法确认你的数据权限，请稍后重试。', retryable: true },
  resource_not_found: { message: '要找的内容不存在或已被移除。', retryable: false },
  validation_error: { message: '提交的内容有不合规之处，请检查后重试。', retryable: false },
  conflict: { message: '这条记录已被他人更新，请刷新后重试。', retryable: false },
  rate_limited: { message: '操作太频繁了，请稍等一会儿再试。', retryable: true },
  queue_unavailable: { message: '后台任务暂时排不上队，请稍后重试。', retryable: true },
  model_unavailable: { message: '分析模型当前不可用，请稍后重试或联系管理员。', retryable: true },
  retrieval_unavailable: { message: '知识库检索暂不可用，回答可能缺少资料依据。', retryable: true },
  task_timeout: { message: '这次分析耗时过长已中断，请缩小范围后重试。', retryable: true },
  task_cancelled: { message: '已按你的要求中止本次操作。', retryable: false },
  unsupported_file: { message: '这个文件类型系统暂不支持，请换一种格式再传。', retryable: false },
  parse_failed: { message: '文件内容没能解析成功，请检查文件是否损坏或受保护。', retryable: false },
  index_publish_failed: { message: '文件已收到，但没能进入知识库，请稍后重试。', retryable: true },
  internal_error: { message: '系统内部出现异常，请稍后重试。', retryable: false },

  invalid_filename: { message: '文件名不合法，请重命名后再试。', retryable: false },
  unsupported_chart_type: { message: '这种图表类型暂不支持，请换一种图表。', retryable: false },
  unsupported_export_format: { message: '这种导出格式暂不支持，请换一种格式。', retryable: false },
  department_scope_required: { message: '请先选择部门范围，再生成这项结果。', retryable: false },
  dataset_filename_conflict: { message: '已存在同名数据文件，请重命名或先删除旧的。', retryable: false },
  dataset_preview_failed: { message: '数据文件预览没能打开，请稍后重试。', retryable: true },
  chart_generation_failed: { message: '图表没能生成，请稍后重试。', retryable: true },
}

/**
 * 后端实际会返回、但不在封闭枚举里的历史码 → 归一到枚举码。
 * 每条都有出处（app/api/v1 实测命中行），message 可按语境覆盖。
 */
export const LEGACY_ALIASES = {
  upload_too_large: { code: 'unsupported_file', message: '文件太大，上传没有成功，请压缩或拆分后再传。' },
  document_parse_failed: { code: 'parse_failed' },
  document_index_failed: { code: 'index_publish_failed', retryable: true },
  document_preview_failed: { code: 'internal_error', message: '文件预览没能生成，请稍后重试。', retryable: true },
  unsupported_preview: { code: 'unsupported_file', message: '这种文件类型不支持在线预览，可下载后在本地打开。' },
  idempotency_key_required: { code: 'validation_error', message: '这次请求缺少重复提交标识，请重新提交。' },
  export_failed: { code: 'internal_error', message: '文件导出没能完成，请稍后重试。', retryable: true },
  storage_read_only: { code: 'internal_error', message: '当前存储处于只读状态，写入没有生效，请联系管理员。', retryable: true },
  relation_source_required: { code: 'validation_error', message: '请先选择关系的起始对象。' },
  invalid_agent_result: { code: 'internal_error', message: '分析结果格式异常，本次未采信，请重试。', retryable: true },
}

/** 拿不到 detail 时按 HTTP 状态兜底，取值全部落在封闭枚举内 */
export const STATUS_CODES = {
  400: 'validation_error',
  401: 'authentication_required',
  403: 'permission_denied',
  404: 'resource_not_found',
  409: 'conflict',
  413: 'unsupported_file',
  415: 'unsupported_file',
  422: 'validation_error',
  429: 'rate_limited',
  500: 'internal_error',
  502: 'model_unavailable',
  503: 'model_unavailable',
  504: 'task_timeout',
}

/** 完全无法归类时的兜底句；未知码由 formatError 在句尾附上「错误码：xxx」小字 */
export const FALLBACK_MESSAGE = '操作没有完成，请稍后重试。'

const CODE_PATTERN = /^[a-z][a-z0-9_]*$/

function isCodeShape(value) {
  return typeof value === 'string' && CODE_PATTERN.test(value.trim())
}

function cleanText(value) {
  if (typeof value === 'string') {
    const text = value.trim()
    if (!text || text === '[object Object]' || text === '[object Array]') return ''
    return text.slice(0, 300)
  }
  if (typeof value === 'number') return String(value)
  return ''
}

/** 码名（枚举码 / 历史别名 / 未知码）→ { code, message, retryable }，查不到即兜底句 */
function resolveCode(rawCode, fallbackStatus) {
  const code = cleanText(rawCode)
  if (ERROR_CODES[code]) return { code, message: ERROR_CODES[code].message, retryable: Boolean(ERROR_CODES[code].retryable) }
  const alias = LEGACY_ALIASES[code]
  if (alias) {
    const target = ERROR_CODES[alias.code] || {}
    return {
      code: alias.code,
      message: cleanText(alias.message) || target.message || FALLBACK_MESSAGE,
      retryable: typeof alias.retryable === 'boolean' ? alias.retryable : Boolean(target.retryable),
    }
  }
  if (code) return { code, message: FALLBACK_MESSAGE, retryable: Boolean(ERROR_CODES[STATUS_CODES[fallbackStatus]]?.retryable) }
  const statusKey = STATUS_CODES[fallbackStatus]
  if (statusKey) return { code: statusKey, message: ERROR_CODES[statusKey].message, retryable: Boolean(ERROR_CODES[statusKey].retryable) }
  return { code: '', message: FALLBACK_MESSAGE, retryable: false }
}

/** 形状 2：ErrorEnvelope，后端给的 message 优先级最高 */
function fromEnvelope(envelope, status) {
  const resolved = resolveCode(envelope.code, status)
  const message = cleanText(envelope.message)
  return {
    code: resolved.code,
    message: message || resolved.message,
    retryable: typeof envelope.retryable === 'boolean' ? envelope.retryable : resolved.retryable,
  }
}

/** 形状 3：FastAPI 422 数组，取第一个问题字段说人话 */
function fromValidation(items, status) {
  const first = items.find((item) => item && typeof item === 'object')
  if (!first) return { code: 'validation_error', message: ERROR_CODES.validation_error.message, retryable: false }
  const trail = Array.isArray(first.loc) ? first.loc.filter((part) => part !== 'body' && part !== 'query' && part !== 'path') : []
  const field = cleanText(String(trail[trail.length - 1] ?? ''))
  const problem = cleanText(first.msg)
  const type = cleanText(first.type)
  let message = ERROR_CODES.validation_error.message
  if (field && type === 'missing') message = `「${field}」为必填项，请补充后再提交。`
  else if (field && problem) message = `「${field}」填写有误：${problem}`
  else if (field) message = `「${field}」填写有误，请检查后重试。`
  else if (problem) message = problem
  return { code: STATUS_CODES[status] || 'validation_error', message, retryable: false }
}
/** 把任意入参收敛成 { detail } 形状；payload 为 null 表示什么都没有 */
function pickPayload(err) {
  if (err == null) return null
  if (typeof err === 'string' || typeof err === 'number') return { detail: err }
  if (typeof err !== 'object') return null
  if ('detail' in err && !err.response) return err
  if ('code' in err && 'message' in err && !err.response) return { detail: err }
  const data = err.response?.data ?? err.data ?? null
  if (data == null) return { detail: undefined }
  if (typeof data === 'string' || Array.isArray(data)) return { detail: data }
  if (typeof data === 'object') {
    if ('detail' in data) return data
    if ('code' in data || 'message' in data) return { detail: data }
    const topMessage = cleanText(data.message) || cleanText(data.error)
    if (topMessage) return { detail: topMessage }
  }
  return { detail: undefined }
}

function isNormalized(value) {
  return Boolean(
    value && typeof value === 'object' && !Array.isArray(value) &&
      typeof value.code === 'string' && typeof value.message === 'string' && typeof value.retryable === 'boolean',
  )
}

/**
 * 统一入口：axios 错误、Error、裸字符串、ErrorEnvelope 都能喂。
 * @param {unknown} err
 * @returns {{ code: string, message: string, retryable: boolean }}
 */
export function normalizeError(err) {
  const status = Number(err?.response?.status ?? err?.status ?? 0) || 0
  const payload = pickPayload(err)
  const detail = payload?.detail

  if (Array.isArray(detail)) {
    if (detail.length) return fromValidation(detail, status)
  } else if (detail && typeof detail === 'object') {
    return fromEnvelope(detail, status)
  } else {
    const text = cleanText(detail)
    if (text) {
      if (isCodeShape(text)) return resolveCode(text, status)
      // 后端已写成人话（如 auth.py「用户名或密码错误」）：原文直出，状态码只补分类
      const statusKey = STATUS_CODES[status]
      return {
        code: statusKey || '',
        message: text,
        retryable: Boolean(statusKey && ERROR_CODES[statusKey]?.retryable),
      }
    }
  }

  // 到这里没有可用错误体：看传输层
  const transport = cleanText(err?.code)
  if (transport === 'ECONNABORTED' || transport === 'ETIMEDOUT') {
    return { code: 'task_timeout', message: ERROR_CODES.task_timeout.message, retryable: true }
  }
  if (transport === 'ERR_NETWORK' || (err && err.request && !err.response)) {
    return { code: '', message: '连不上服务，请确认网络或稍后重试。', retryable: true }
  }
  const message = cleanText(err?.message)
  if (message && !isCodeShape(message)) {
    const statusKey = STATUS_CODES[status]
    return { code: statusKey || '', message, retryable: Boolean(statusKey && ERROR_CODES[statusKey]?.retryable) }
  }
  if (message) return resolveCode(message, status)
  return resolveCode('', status)
}

/** 归一结果里的「错误码：xxx」可报告小字；字典内已知码返回空串，避免污染界面 */
export function errorCodeLabel(errOrResult) {
  const result = isNormalized(errOrResult) ? errOrResult : normalizeError(errOrResult)
  if (!result.code || ERROR_CODES[result.code]) return ''
  return `错误码：${result.code}`
}

/** 单条 `{{ error }}` 插值位的成品句：未知码在句尾保留码名 */
export function formatError(err) {
  const result = normalizeError(err)
  const label = errorCodeLabel(result)
  return label ? `${result.message}（${label}）` : result.message
}

/** 展示层据此决定是否挂「重试」按钮 */
export function isRetryable(err) {
  return Boolean(normalizeError(err).retryable)
}

/** 码表查询：已知码返回原文案，未知返回兜底句 */
export function errorText(code) {
  const resolved = resolveCode(cleanText(code), 0)
  return resolved.message
}
