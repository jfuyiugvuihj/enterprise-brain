/**
 * 错误码字典（V5 / F7 叶子线产出）
 *
 * 后端错误体三种形状并存（工单 D-2），本模块统一成 { code, message, retryable, rawCode }：
 *   形状 1 字符串稳定码   err.response.data.detail === "unsupported_file"
 *   形状 2 ErrorEnvelope  err.response.data.detail === { code, message, retryable, details }
 *                         来源 app/api/v1/observability.py 全部、chat.py::_document_index_error
 *   形状 3 FastAPI 422    err.response.data.detail === [{ loc, msg, type }, ...]
 *
 * 码名蓝本：app/agents/contracts.py::ErrorEnvelope.code（封闭枚举 17 码，含主树 fa35a04 追认的 account_unavailable）
 * 追加 data.py 系列 7 码；线上出现的其它历史码名走 LEGACY_ALIASES 归一。
 * 鉴权中间件返的是**中文散文**（app/main.py:104/109 的 401「请先登录」、
 * app/main.py:113 的 403「账号不可用」），那不是码，走 PROSE_ALIASES 按原文索引。
 *
 * 硬不变量：normalizeError() 的 .code 一定 ∈ Object.keys(ERROR_CODES) ∪ {''}。
 * 后端原样回来的码名/散文一律放进 .rawCode，只供排查与「错误码：xxx」小字使用。
 *
 * 文案政策（B-5 ②）：给人看的句子只说人话 + 下一步，不内嵌裸 snake_case 码名。
 * 码名走独立通道 errorCodeOf()，由界面放进 data-code / 「详情」折叠区；未知码才由
 * formatError() 在句尾附「错误码：xxx」小字。后端直出的句子若夹带码名，由 extractEmbeddedCode()
 * 在归类前摘掉，摘不干净的宁可走兜底句也不把码名留在正文里。
 */

/** 蓝本 17 码 + data.py 7 码 + 流式 1 码 = 25 个键，这 25 个就是 normalizeError().code 的全部合法取值。 */
export const ERROR_CODES = {
  authentication_required: { message: '登录状态已失效，请重新登录后再试。', retryable: false },
  permission_denied: { message: '当前账号没有这项权限，请联系管理员开通。', retryable: false },
  // 部门授权范围取不到。原 lib/sessions.js:379 那句把「换带部门的账号或联系管理员」说清了，
  // 这里收下这层语义，只把裸码名摘掉（文案政策：句子说人话，码名走 errorCodeOf 独立通道）。
  authorization_unavailable: {
    message: '暂时确认不了你的数据权限范围，请稍后重试；仍不行的话请换带部门授权的账号或联系管理员。',
    retryable: true,
  },
  // 账号被停用：既不是 permission_denied（不是权限不够，重新登录也没用），也不该退化成兜底句。
  account_unavailable: { message: '这个账号已被停用，请联系管理员恢复后再使用。', retryable: false },
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

  // 流式回答跑完既没正文也没待确认步骤。出处 app/api/v1/chat.py:997-1013（SSE request.failed 的 data.error_code）。
  // 原先只活在 lib/sessions.js:376 的私有字典里，句子内嵌了裸码名，这里按文案政策重写成纯人话 + 下一步。
  no_answer_produced: { message: '本轮未产出任何结论，请重试，或把数据范围缩小一点再问。', retryable: true },
}

/**
 * 前端自己加、后端契约里还没有的码 —— 必须是空数组。
 * 这是一条绊线：谁往 ERROR_CODES 里塞未追认的码名，就得在这里登记，单测随即转红，
 * 直到后端把它并入 contracts.py 的封闭枚举。account_unavailable 走过这条路
 * （前端先登记 → 主树 fa35a04 追认 → 摘掉标记），别再开新的。
 */
export const FRONTEND_ONLY_CODES = []

/**
 * 后端实测会发、但两份契约枚举（app/agents/contracts.py::ErrorEnvelope.code 与
 * app/agents/evidence.py::_ERROR_CODES）都还没登记的码名。与 FRONTEND_ONLY_CODES 不同：
 * 这张表里的每一个都能在 app/api/v1 下指到出处，前端没有凭空发明，只是契约欠账。
 * 由总控派 C 追认；追认一条就从这里删一条，单测会盯着名单与「枚举 − 蓝本」是否相等。
 */
export const UNRATIFIED_CODES = [
  'invalid_filename', // app/api/v1/data.py:57
  'unsupported_chart_type', // app/api/v1/data.py:376
  'unsupported_export_format', // app/api/v1/data.py:412
  'department_scope_required', // app/api/v1/data.py:43
  'dataset_filename_conflict', // app/api/v1/data.py:172
  'dataset_preview_failed', // app/api/v1/data.py:217
  'chart_generation_failed', // app/api/v1/data.py:384
  'no_answer_produced', // app/api/v1/chat.py:1001
]

/**
 * 后端实际会返回、但不在封闭枚举里的**码名** → 归一到枚举码（按码名索引）。
 * 每条都有 app/api/v1 下的实测出处，不发明码名；message 可按语境覆盖。
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

  // 下面五条是 app/common/policy.py 的拒绝原因码，经 HTTPException(detail=decision.reason_code) 原样落到 403 body：
  // alerts.py:106 / artifacts.py:50 / chat.py:278,318,766,1708 / data.py:90,328,354 / intelligence.py:69。
  // 下载与预览走 responseType:blob，这些码读不出来就会被误判成「坏了」，所以必须有人话 + 下一步。
  principal_inactive: { code: 'account_unavailable', message: '这个账号已被停用，请联系管理员恢复后再使用。', retryable: false }, // policy.py:136
  department_scope_denied: { code: 'permission_denied', message: '这份资料属于其他部门的数据范围，当前账号看不到，请联系管理员授权。', retryable: false }, // policy.py:210
  clearance_insufficient: { code: 'permission_denied', message: '这份资料的安全等级高于你的可见级别，不能打开，请联系管理员。', retryable: false }, // policy.py:189
  resource_scope_missing: { code: 'authorization_unavailable', message: '这份资料没有登记所属部门或密级，系统判断不了你能不能看，请联系管理员补齐登记。', retryable: false }, // policy.py:181,207
  resource_scope_invalid: { code: 'authorization_unavailable', message: '这份资料登记的部门或密级格式有误，系统判断不了你能不能看，请联系管理员。', retryable: false }, // policy.py:187
}

/**
 * 鉴权中间件的**中文散文** → 枚举码（按 detail 原文索引，与 LEGACY_ALIASES 分开）。
 * 出处：app/main.py:104（缺 token / token 验不过）、app/main.py:109（token 指向的用户已不存在）
 *      均 401 {"detail":"请先登录"}；app/main.py:113（principal.status !== 'active'）
 *      403 {"detail":"账号不可用"}。白名单见 app/main.py:86-95。
 * 匹配规则刻意保守：**规范化后全等**才认，宁可漏判走兜底句。
 * 误判成 authentication_required 的代价是把正在干活的员工踢回登录页，比漏判重得多。
 */
export const PROSE_ALIASES = {
  请先登录: { code: 'authentication_required' },
  账号不可用: { code: 'account_unavailable' },
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

/** 夹带码名的三种野外形状：error_code=X（app/api/v1/chat.py:998）与括号里的 X（lib/sessions.js:376-380 那批） */
const EMBED_CODE = /error_code=([a-z][a-z0-9_]+)|（([a-z][a-z0-9_]+)）|[(]([a-z][a-z0-9_]+)[)]/g

/** 稳定码的形状：小写字母开头的 snake_case。中文散文一律不算码 */
function isCodeShape(value) {
  return typeof value === 'string' && CODE_PATTERN.test(value.trim())
}

function cleanText(value) {
  if (typeof value === 'string') {
    const text = value.trim()
    if (!text || text === '[object Object]' || text === '[object Array]') return ''
    // 网关/静态页会把整段 HTML 塞进 detail，不能当成人话抛给界面
    if (text.startsWith('<') || /<!doctype\s+html|<html/i.test(text)) return ''
    if (/^request failed with status code \d+$/i.test(text)) return ''
    return text.slice(0, 300)
  }
  if (typeof value === 'number') return String(value)
  return ''
}

/** 散文规范化：去首尾空白 + 去尾部句读，仅此而已（不做包含式模糊匹配） */
function normalizeProseKey(value) {
  return cleanText(value).replace(/[\s。．.！!？?；;：,，、]+$/g, '').trim()
}

/**
 * 后端有句子把码名直接夹在正文里，例如 app/api/v1/chat.py:998 写的
 * 「本轮未产出任何结论（error_code=no_answer_produced），请重试或补充数据范围。」
 * 这类串既不是码、也不在散文表里，必须先做保守摘除再归类：只动 error_code=X、（X）、(X)
 * 三种形状，且 X 必须含下划线并符合码名形态；纯小写单词（id、api 之类）一概不动 ——
 * 宁可漏判走兜底句，也不许把正常词吃掉。
 * @returns {{ code: string, text: string } | null} text 是摘掉码名、收拾完残标点之后的句子
 */
function extractEmbeddedCode(text) {
  if (!text) return null
  EMBED_CODE.lastIndex = 0
  let match = EMBED_CODE.exec(text)
  let code = ''
  while (match) {
    const token = match[1] || match[2] || match[3] || ''
    if (!code && token.includes('_') && isCodeShape(token)) code = token
    match = EMBED_CODE.exec(text)
  }
  if (!code) return null
  return { code, text: tidyProse(text.replace(EMBED_CODE, '')) }
}

/** 摘掉码名之后收拾残标点：先清空括号，再并重复标点，最后压多余空格，顺序不能反 */
function tidyProse(text) {
  return text
    .replace(/（[ ]*）|[(][ ]*[)]/g, '')
    .replace(/([，、；：])[，、；：]+/g, '$1')
    .replace(/。[，、；：]+/g, '。')
    .replace(/^[，、；：。.]+/, '')
    .replace(/[ ]{2,}/g, ' ')
    .trim()
}

function isEnumCode(code) {
  return Object.prototype.hasOwnProperty.call(ERROR_CODES, code)
}

/** 按原文查散文表 */
function resolveProse(token) {
  const key = normalizeProseKey(token)
  if (!key) return null
  const entry = PROSE_ALIASES[key]
  return entry ? { ...entry, matched: key } : null
}

/**
 * 唯一的收口处：任何分支产出的 code 都过这里，非枚举值一律降级为 ''。
 * @returns {{ code: string, rawCode: string, message: string, retryable: boolean }}
 */
function clampResult({ code = '', rawCode = '', message = '', retryable = false }) {
  const known = isEnumCode(code)
  return {
    code: known ? code : '',
    rawCode: cleanText(rawCode) || (known ? '' : cleanText(code)),
    message: cleanText(message) || FALLBACK_MESSAGE,
    retryable: Boolean(retryable),
  }
}

/**
 * 码名/散文 → { code, rawCode, message, retryable }。
 * 查不到即兜底句；枚举外的原样串只进 rawCode，绝不进 code。
 */
function resolveCode(raw, status) {
  const token = cleanText(raw)

  if (isEnumCode(token)) {
    return clampResult({ code: token, message: ERROR_CODES[token].message, retryable: ERROR_CODES[token].retryable })
  }

  const alias = token && isCodeShape(token) ? LEGACY_ALIASES[token] : null
  if (alias) {
    const target = ERROR_CODES[alias.code] || {}
    return clampResult({
      code: alias.code,
      rawCode: token,
      message: cleanText(alias.message) || target.message,
      retryable: typeof alias.retryable === 'boolean' ? alias.retryable : target.retryable,
    })
  }

  const prose = token && !isCodeShape(token) ? resolveProse(token) : null
  if (prose) {
    const target = ERROR_CODES[prose.code] || {}
    return clampResult({
      code: prose.code,
      rawCode: token,
      message: cleanText(prose.message) || target.message,
      retryable: typeof prose.retryable === 'boolean' ? prose.retryable : target.retryable,
    })
  }

  // 后端把码名夹在正文里直出的句子：先摘码名再归类，摘完认得就用字典句（唯一真相源），
  // 认不下就把摘干净的句子当人话、码名留进 rawCode 供「错误码：xxx」小字排查。
  const embedded = token && !isCodeShape(token) ? extractEmbeddedCode(token) : null
  if (embedded) {
    if (isEnumCode(embedded.code)) {
      const known = ERROR_CODES[embedded.code]
      return clampResult({ code: embedded.code, rawCode: embedded.code, message: known.message, retryable: known.retryable })
    }
    const fallbackStatus = STATUS_CODES[status]
    return clampResult({
      code: fallbackStatus || '',
      rawCode: embedded.code,
      message: embedded.text,
      retryable: Boolean(fallbackStatus && ERROR_CODES[fallbackStatus].retryable),
    })
  }

  const statusKey = STATUS_CODES[status]
  if (token && isCodeShape(token)) {
    // 未知稳定码：走兜底句，码名留在 rawCode（界面小字仍可按「错误码：xxx」报出来）
    return clampResult({
      code: statusKey || '',
      rawCode: token,
      message: FALLBACK_MESSAGE,
      retryable: Boolean(statusKey && ERROR_CODES[statusKey].retryable),
    })
  }
  if (statusKey) {
    // 有状态码可归类：散文原样就是人话，直接当 message 用（如 auth.py「用户名或密码错误」）
    return clampResult({
      code: statusKey,
      rawCode: token,
      message: token || ERROR_CODES[statusKey].message,
      retryable: Boolean(ERROR_CODES[statusKey].retryable),
    })
  }
  // 既不认识又没有状态码可归类：散文原样留着当人话，但没有码可报；未知码才回兜底句
  return clampResult({ code: '', rawCode: token, message: token && !isCodeShape(token) ? token : FALLBACK_MESSAGE, retryable: false })
}

/** 形状 2：ErrorEnvelope / 任意 { code, message, retryable } 对象，后端给的 message 优先级最高 */
function fromEnvelope(envelope, status) {
  // 后端在 SSE 与下载错误体里用的是 error_code，不是 code（chat.py:1013、artifacts 的 blob 体），两个都要认
  const wireCode = envelope.code ?? envelope.error_code
  const resolved = resolveCode(wireCode, status)
  const message = cleanText(envelope.message)
  return clampResult({
    code: resolved.code,
    rawCode: cleanText(wireCode) || resolved.rawCode,
    message: message || resolved.message,
    retryable: typeof envelope.retryable === 'boolean' ? envelope.retryable : resolved.retryable,
  })
}

/** 形状 3：FastAPI 422 数组，取第一个问题字段说人话 */
function fromValidation(items, status) {
  const first = items.find((item) => item && typeof item === 'object')
  if (!first) return clampResult({ code: 'validation_error', message: ERROR_CODES.validation_error.message })
  const trail = Array.isArray(first.loc) ? first.loc.filter((part) => part !== 'body' && part !== 'query' && part !== 'path') : []
  const field = cleanText(String(trail[trail.length - 1] ?? ''))
  const problem = cleanText(first.msg)
  const type = cleanText(first.type)
  let message = ERROR_CODES.validation_error.message
  if (field && type === 'missing') message = `「${field}」为必填项，请补充后再提交。`
  else if (field && problem) message = `「${field}」填写有误：${problem}`
  else if (field) message = `「${field}」填写有误，请检查后重试。`
  else if (problem) message = problem
  // 校验错误的人话里已经点名了字段，不再另塞 rawCode
  return clampResult({ code: STATUS_CODES[status] || 'validation_error', message })
}

/** 把任意入参收敛成 { detail } 形状；payload 为 null 表示什么都没有 */
function pickPayload(err) {
  if (err == null) return null
  if (typeof err === 'string' || typeof err === 'number') return { detail: err }
  if (typeof err !== 'object') return null
  if ('detail' in err && !err.response) return err
  // 裸 ErrorEnvelope 对象：小写稳定码 + message，且不带 axios 的 request/response 痕迹
  if (
    !err.response &&
    !err.request &&
    !err.isAxiosError &&
    isCodeShape(err.code) &&
    typeof err.message === 'string'
  ) {
    return { detail: err }
  }
  const data = err.response?.data ?? err.data ?? null
  if (data == null) return { detail: undefined }
  if (typeof data === 'string' || Array.isArray(data)) return { detail: data }
  if (typeof data === 'object') {
    if ('detail' in data) return data
    if ('error_code' in data && !('detail' in data)) return { detail: data }
    if ('code' in data || 'message' in data) return { detail: data }
    const topMessage = cleanText(data.message) || cleanText(data.error)
    if (topMessage) return { detail: topMessage }
  }
  return { detail: undefined }
}

function isNormalized(value) {
  return Boolean(
    value && typeof value === 'object' && !Array.isArray(value) &&
      typeof value.code === 'string' && typeof value.message === 'string' &&
      typeof value.retryable === 'boolean' && typeof value.rawCode === 'string',
  )
}

/** 传输层能确定的两类：超时与断网，用枚举码表达 */
function resolveTransport(err, status) {
  const transport = cleanText(err?.code)
  if (transport === 'ECONNABORTED' || transport === 'ETIMEDOUT') {
    return clampResult({ code: 'task_timeout', message: ERROR_CODES.task_timeout.message, retryable: true })
  }
  if (transport === 'ERR_NETWORK' || (err && err.request && !err.response)) {
    return clampResult({ code: '', rawCode: transport, message: '连不上服务，请确认网络或稍后重试。', retryable: true })
  }
  const message = cleanText(err?.message)
  if (message && !isCodeShape(message)) {
    // 人话直出 + 状态码归类，绝不把中文塞进 code
    const statusKey = STATUS_CODES[status]
    return clampResult({
      code: statusKey || '',
      rawCode: transport,
      message,
      retryable: Boolean(statusKey && ERROR_CODES[statusKey].retryable),
    })
  }
  if (message) return resolveCode(message, status)
  return resolveCode('', status)
}

/**
 * 统一入口：axios 错误、Error、裸字符串、ErrorEnvelope、中文散文都能喂。
 * @param {unknown} err
 * @returns {{ code: string, message: string, retryable: boolean, rawCode: string }}
 *   code 一定在 ERROR_CODES 里或为空串；后端原样回来的串放 rawCode。
 */
export function normalizeError(err) {
  const status = Number(err?.response?.status ?? err?.status ?? 0) || 0
  const payload = pickPayload(err)
  const detail = payload?.detail

  if (Array.isArray(detail)) {
    // 空数组：等于没有错误体，退到状态码归类，不把 axios 的英文原句抛给界面
    return detail.length ? fromValidation(detail, status) : resolveCode('', status)
  }
  if (detail && typeof detail === 'object') {
    return fromEnvelope(detail, status)
  }

  const text = cleanText(detail)
  if (text) return resolveCode(text, status)
  return resolveTransport(err, status)
}

/**
 * 可报告小字：只有「后端给了一个我们不认识的码」时才出现。
 * 已知码、别名码、中文散文都不加，免得把界面搞脏；未知码走兜底句 + 这条小字，
 * 保证还能贴给后端排查。
 */
function toResult(input) {
  return isNormalized(input) ? input : normalizeError(input)
}

/**
 * 独立通道：界面要展示/埋点码名时只准用它，拿到的一定是封闭枚举内的码名或空串。
 * 用法是塞进 data-code / 「详情」折叠区，或 console.debug；不许拼进给人看的句子。
 * 未知码与中文散文在这里都回空串（那些走 errorCodeLabel 的「错误码：xxx」小字）。
 */
export function errorCodeOf(errOrResult) {
  return toResult(errOrResult).code
}

export function errorCodeLabel(errOrResult) {
  const result = toResult(errOrResult)
  const raw = cleanText(result.rawCode)
  if (!raw || isMappedRaw(raw)) return ''
  return isCodeShape(raw) ? `错误码：${raw}` : ''
}

/** 这个原始串是否已经被某张表收编过 */
function isMappedRaw(raw) {
  if (isEnumCode(raw) || LEGACY_ALIASES[raw]) return true
  const prose = resolveProse(raw)
  return Boolean(prose)
}
/** 单条 `{{ error }}` 插值位的成品句：未知码在句尾保留码名 */
export function formatError(err) {
  const result = toResult(err)
  const label = errorCodeLabel(result)
  return label ? `${result.message}（${label}）` : result.message
}

/** 展示层据此决定是否挂「重试」按钮 */
export function isRetryable(err) {
  return Boolean(toResult(err).retryable)
}

/** 码表查询：已知码返回原文案，未知返回兜底句 */
export function errorText(code) {
  return resolveCode(cleanText(code), 0).message
}
