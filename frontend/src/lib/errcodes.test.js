import { describe, expect, it } from 'vitest'
import {
  ERROR_CODES,
  FALLBACK_MESSAGE,
  LEGACY_ALIASES,
  errorCodeLabel,
  errorText,
  formatError,
  isRetryable,
  normalizeError,
} from './errcodes.js'

/** app/agents/contracts.py::ErrorEnvelope.code 的封闭枚举 16 码 */
const BLUEPRINT = [
  'authentication_required',
  'permission_denied',
  'authorization_unavailable',
  'resource_not_found',
  'validation_error',
  'conflict',
  'rate_limited',
  'queue_unavailable',
  'model_unavailable',
  'retrieval_unavailable',
  'task_timeout',
  'task_cancelled',
  'unsupported_file',
  'parse_failed',
  'index_publish_failed',
  'internal_error',
]

/** data.py 系列 7 码 */
const DATA_CODES = [
  'invalid_filename',
  'unsupported_chart_type',
  'unsupported_export_format',
  'department_scope_required',
  'dataset_filename_conflict',
  'dataset_preview_failed',
  'chart_generation_failed',
]

const axiosError = (status, detail) => ({
  isAxiosError: true,
  message: `Request failed with status code ${status}`,
  response: { status, data: detail === undefined ? {} : { detail } },
})

describe('码表蓝本', () => {
  it('只收录 contracts.py 16 码 + data.py 7 码，不多不少', () => {
    expect(Object.keys(ERROR_CODES).sort()).toEqual([...BLUEPRINT, ...DATA_CODES].sort())
  })

  it('每个码都有一句人话与明确的 retryable', () => {
    Object.entries(ERROR_CODES).forEach(([code, entry]) => {
      expect(entry.message, code).toBeTruthy()
      expect(entry.message, code).not.toMatch(/[{}]|https?:\/\/|\/api\//)
      expect(typeof entry.retryable, code).toBe('boolean')
    })
  })

  it('别名只指向枚举内的码名，不发明新码', () => {
    Object.entries(LEGACY_ALIASES).forEach(([legacy, alias]) => {
      expect(BLUEPRINT, legacy).toContain(alias.code)
    })
  })
})

describe('形状 1：detail 是字符串稳定码', () => {
  it('命中字典时出字典句', () => {
    const result = normalizeError(axiosError(415, 'unsupported_file'))
    expect(result).toEqual({
      code: 'unsupported_file',
      message: '这个文件类型系统暂不支持，请换一种格式再传。',
      retryable: false,
    })
  })

  it('data.py 的部门范围缺失也走字典', () => {
    expect(normalizeError(axiosError(403, 'department_scope_required')).message).toBe('请先选择部门范围，再生成这项结果。')
    expect(normalizeError(axiosError(409, 'dataset_filename_conflict')).code).toBe('dataset_filename_conflict')
  })

  it('历史别名归一到枚举码，并保留语境文案', () => {
    const big = normalizeError(axiosError(413, 'upload_too_large'))
    expect(big.code).toBe('unsupported_file')
    expect(big.message).toContain('文件太大')
    expect(normalizeError(axiosError(500, 'document_index_failed')).code).toBe('index_publish_failed')
    expect(normalizeError(axiosError(500, 'document_index_failed')).retryable).toBe(true)
  })

  it('后端已写成人话的 detail 原样直出，只按状态补分类码', () => {
    const result = normalizeError(axiosError(401, '用户名或密码错误'))
    expect(result.message).toBe('用户名或密码错误')
    expect(result.code).toBe('authentication_required')
  })

  it('未知码走兜底句，并保留可报告小字', () => {
    const err = axiosError(500, 'brand_new_backend_code')
    const result = normalizeError(err)
    expect(result.message).toBe(FALLBACK_MESSAGE)
    expect(result.code).toBe('brand_new_backend_code')
    expect(errorCodeLabel(result)).toBe('错误码：brand_new_backend_code')
    expect(formatError(err)).toBe(`${FALLBACK_MESSAGE}（错误码：brand_new_backend_code）`)
  })
})

describe('形状 2：detail 是 ErrorEnvelope 对象', () => {
  const envelope = (code, message, retryable) => ({
    isAxiosError: true,
    response: { status: 500, data: { detail: { code, message, retryable, details: { filename: '预算.xlsx', stage: 'index' } } } },
  })

  it('不再弹 [object Object]，这是上传解析失败的真实回归', () => {
    const result = normalizeError(envelope('parse_failed', '工作簿受密码保护，无法读取。'))
    expect(result.message).toBe('工作簿受密码保护，无法读取。')
    expect(result.message).not.toContain('[object Object]')
    expect(result.code).toBe('parse_failed')
  })

  it('envelope 没带 message 时回落到字典句', () => {
    const result = normalizeError(envelope('index_publish_failed', ''))
    expect(result.message).toBe(ERROR_CODES.index_publish_failed.message)
    expect(result.retryable).toBe(true)
  })

  it('envelope 的 retryable 覆盖字典默认值', () => {
    expect(normalizeError(envelope('internal_error', '索引发布失败', true)).retryable).toBe(true)
    expect(normalizeError(envelope('internal_error', '索引发布失败')).retryable).toBe(false)
  })

  it('chat.py::_document_index_error 的真实结构能直接吃', () => {
    const result = normalizeError({
      response: {
        status: 500,
        data: { detail: { code: 'index_publish_failed', message: '文件已收到，但没能进入知识库。', retryable: true, details: { filename: '制度.docx', stage: 'publish' } } },
      },
    })
    expect(result).toEqual({ code: 'index_publish_failed', message: '文件已收到，但没能进入知识库。', retryable: true })
  })

  it('未知 envelope 码走兜底句但保留码名', () => {
    const err = envelope('mystery_code', '')
    expect(normalizeError(err).message).toBe(FALLBACK_MESSAGE)
    expect(formatError(err)).toContain('错误码：mystery_code')
  })
})

describe('形状 3：FastAPI 422 校验数组', () => {
  it('缺字段时说清是哪个字段', () => {
    const result = normalizeError(axiosError(422, [{ loc: ['body', 'department'], msg: 'Field required', type: 'missing' }]))
    expect(result.code).toBe('validation_error')
    expect(result.message).toBe('「department」为必填项，请补充后再提交。')
    expect(result.retryable).toBe(false)
  })

  it('类型不符时带上原始 msg', () => {
    const result = normalizeError(axiosError(422, [{ loc: ['body', 'rows', 0, 'threshold'], msg: 'Input should be a valid number', type: 'int_parsing' }]))
    expect(result.code).toBe('validation_error')
    expect(result.message).toContain('threshold')
  })

  it('空数组不退化成 axios 英文原句', () => {
    const result = normalizeError(axiosError(422, []))
    expect(result.code).toBe('validation_error')
    expect(result.message).toBe(ERROR_CODES.validation_error.message)
  })
})

describe('无错误体时的降级', () => {
  it('只有状态码也能归类', () => {
    expect(normalizeError({ response: { status: 404, data: {} } }).code).toBe('resource_not_found')
    expect(normalizeError({ response: { status: 429, data: {} } }).message).toBe(ERROR_CODES.rate_limited.message)
    expect(normalizeError({ response: { status: 504, data: {} } }).code).toBe('task_timeout')
  })

  it('断网与超时区分开，且都提示可重试', () => {
    const offline = normalizeError({ code: 'ERR_NETWORK', request: {}, message: 'Network Error' })
    expect(offline.retryable).toBe(true)
    expect(offline.message).toContain('连不上服务')
    const timeout = normalizeError({ code: 'ECONNABORTED', message: 'timeout of 30000ms exceeded' })
    expect(timeout.code).toBe('task_timeout')
  })

  it('喂 undefined / null / 空对象都不崩，给兜底句', () => {
    ;[undefined, null, {}, ''].forEach((input) => {
      const result = normalizeError(input)
      expect(result.message).toBe(FALLBACK_MESSAGE)
      expect(result.code).toBe('')
      expect(result.retryable).toBe(false)
    })
  })

  it('裸字符串码与 Error 实例也接得住', () => {
    expect(normalizeError('invalid_filename').message).toBe(ERROR_CODES.invalid_filename.message)
    expect(normalizeError(new Error('会话已过期')).message).toBe('会话已过期')
  })

  it('HTML 错误页不会被当成消息抛出去', () => {
    const result = normalizeError({ response: { status: 502, data: '<html><body>502 Bad Gateway</body></html>' } })
    expect(result.code).toBe('model_unavailable')
    expect(result.message).toBe(ERROR_CODES.model_unavailable.message)
  })

  it('message 有则优先，data.message 平铺也能识别', () => {
    const result = normalizeError({ response: { status: 400, data: { message: '导出列名不能为空' } } })
    expect(result.message).toBe('导出列名不能为空')
    expect(result.code).toBe('validation_error')
  })
})

describe('isRetryable / errorText / formatError', () => {
  it('只在可重试的码上为真', () => {
    expect(isRetryable(axiosError(429, 'rate_limited'))).toBe(true)
    expect(isRetryable(axiosError(403, 'permission_denied'))).toBe(false)
    expect(isRetryable(axiosError(401, 'authentication_required'))).toBe(false)
  })

  it('errorText 认枚举码也认别名', () => {
    expect(errorText('chart_generation_failed')).toBe(ERROR_CODES.chart_generation_failed.message)
    expect(errorText('export_failed')).toContain('导出')
    expect(errorText('nope')).toBe(FALLBACK_MESSAGE)
  })

  it('formatError 对已知码不加噪声小字', () => {
    const message = formatError(axiosError(415, 'unsupported_file'))
    expect(message).toBe(ERROR_CODES.supported_file?.message || ERROR_CODES.unsupported_file.message)
    expect(message).not.toContain('错误码：')
  })
})
