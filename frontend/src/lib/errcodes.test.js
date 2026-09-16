import { describe, expect, it } from 'vitest'
import {
  ERROR_CODES,
  FALLBACK_MESSAGE,
  FRONTEND_ONLY_CODES,
  LEGACY_ALIASES,
  PROSE_ALIASES,
  STATUS_CODES,
  errorCodeLabel,
  errorCodeOf,
  errorText,
  formatError,
  isRetryable,
  normalizeError,
} from './errcodes.js'

/** app/agents/contracts.py::ErrorEnvelope.code 的封闭枚举 17 码（含主树 fa35a04 追认的 account_unavailable） */
const BLUEPRINT = [
  'authentication_required',
  'permission_denied',
  'authorization_unavailable',
  // 派单 B-1：C 已把该码并入 contracts.py 的 ErrorEnvelope.code 闭枚举，故归蓝本而非前端自扩。
  'account_unavailable',
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
/** SSE 流内错误码：chat.py:1001 的 request.failed data.error_code，两份后端枚举都还没有它 */
const STREAM_CODES = ['no_answer_produced']

const ALL_CODES = [...BLUEPRINT, ...DATA_CODES, ...STREAM_CODES, ...FRONTEND_ONLY_CODES]

const ENUM = Object.keys(ERROR_CODES)

/** 硬不变量：.code 只能是枚举值或空串，中文散文/未知码一律赶去 rawCode */
const inEnum = (result, label) => {
  expect(typeof result.code, label).toBe('string')
  expect(result.code === '' || ENUM.includes(result.code), `${label} -> code=${result.code}`).toBe(true)
  expect(typeof result.message, label).toBe('string')
  expect(result.retryable, label).toBeTypeOf('boolean')
  expect(typeof result.rawCode, label).toBe('string')
}

const axiosError = (status, detail) => ({
  isAxiosError: true,
  message: `Request failed with status code ${status}`,
  response: { status, data: detail === undefined ? {} : { detail } },
})

describe('码表蓝本', () => {
  it('只收录 contracts.py 17 码 + data.py 7 码，一个不自扩', () => {
    expect(Object.keys(ERROR_CODES).sort()).toEqual([...BLUEPRINT, ...DATA_CODES, ...STREAM_CODES, ...FRONTEND_ONLY_CODES].sort())
  })

  it('前端自扩码绊线为空：account_unavailable 已被后端追认，不许留残名', () => {
    expect(FRONTEND_ONLY_CODES).toEqual([])
    expect(BLUEPRINT).toContain('account_unavailable')
  })

  it('每个码都有一句人话与明确的 retryable', () => {
    Object.entries(ERROR_CODES).forEach(([code, entry]) => {
      expect(entry.message, code).toBeTruthy()
      expect(entry.message, code).not.toMatch(/[{}]|https?:\/\/|\/api\//)
      expect(typeof entry.retryable, code).toBe('boolean')
    })
  })

  it('别名与散文表只指向枚举内的码名，不发明新码', () => {
    Object.entries(LEGACY_ALIASES).forEach(([legacy, alias]) => expect(BLUEPRINT.concat(DATA_CODES), legacy).toContain(alias.code))
    Object.entries(PROSE_ALIASES).forEach(([prose, entry]) => expect(ENUM, prose).toContain(entry.code))
  })

  it('穷举：每个枚举码 / 别名码 / 散文码喂进去都收敛到自己', () => {
    ALL_CODES.forEach((code) => {
      const result = normalizeError({ response: { data: { detail: code } } })
      inEnum(result, code)
      expect(result.code, code).toBe(code)
      expect(result.message, code).toBe(ERROR_CODES[code].message)
    })
    Object.entries(LEGACY_ALIASES).forEach(([legacy, alias]) => {
      const result = normalizeError({ response: { data: { detail: legacy } } })
      inEnum(result, legacy)
      expect(result.code, legacy).toBe(alias.code)
      expect(result.rawCode, legacy).toBe(legacy)
    })
    Object.entries(PROSE_ALIASES).forEach(([prose, entry]) => {
      const result = normalizeError({ response: { data: { detail: prose } } })
      inEnum(result, prose)
      expect(result.code, prose).toBe(entry.code)
      expect(result.rawCode, prose).toBe(prose)
      expect(result.message.includes(prose), prose).toBe(false)
    })
    Object.keys(STATUS_CODES).forEach((status) => {
      const result = normalizeError({ response: { status: Number(status), data: {} } })
      inEnum(result, `status ${status}`)
      expect(result.code, status).toBe(STATUS_CODES[status])
    })
  })
})

describe('散文码：鉴权中间件的中文 detail', () => {
  it('app/main.py:104/109 的 401「请先登录」归到 authentication_required', () => {
    const result = normalizeError(axiosError(401, '请先登录'))
    inEnum(result, '请先登录')
    expect(result.code).toBe('authentication_required')
    expect(result.rawCode).toBe('请先登录')
    expect(result.message).toBe(ERROR_CODES.authentication_required.message)
    expect(result.retryable).toBe(false)
  })

  it('app/main.py:113 的 403「账号不可用」不能糊成 permission_denied', () => {
    const result = normalizeError(axiosError(403, '账号不可用'))
    inEnum(result, '账号不可用')
    expect(result.code).toBe('account_unavailable')
    expect(result.message).toContain('停用')
    expect(result.retryable).toBe(false)
  })

  it('没有 HTTP 状态也能认：SSE 事件里只带 detail 原文的情况', () => {
    expect(normalizeError('请先登录').code).toBe('authentication_required')
    expect(normalizeError('账号不可用').code).toBe('account_unavailable')
  })

  it('带首尾空白或尾部句读仍然等值命中', () => {
    expect(normalizeError(axiosError(401, '  请先登录  ')).code).toBe('authentication_required')
    expect(normalizeError(axiosError(401, '请先登录。')).code).toBe('authentication_required')
    expect(normalizeError(axiosError(403, '账号不可用！')).code).toBe('account_unavailable')
  })

  it('近似但不等值的散文不许命中：宁可漏判也不把人踢下线', () => {
    for (const near of ['请先登录以继续本次导出', '请先登录后再试', '账号不可用，请重新登录', '请先登']) {
      const result = normalizeError({ response: { data: { detail: near } } })
      inEnum(result, near)
      expect(result.rawCode, near).toBe(near)
      expect(result.message, near).toBe(near)
    }
  })

  it('漏判时靠 HTTP 状态兜底，不靠猜中文', () => {
    const result = normalizeError(axiosError(401, '请先登录后再试'))
    expect(result.code).toBe('authentication_required')
    expect(result.message).toBe('请先登录后再试')
    const other = normalizeError(axiosError(403, '请先登录后再试'))
    expect(other.code).toBe('permission_denied')
    expect(other.message).toBe('请先登录后再试')
  })

  it('散文命中的已知码不追加「错误码：」小字', () => {
    expect(errorCodeLabel(axiosError(401, '请先登录'))).toBe('')
    expect(formatError(axiosError(403, '账号不可用'))).toBe(ERROR_CODES.account_unavailable.message)
  })
})

describe('形状 1：detail 是字符串稳定码', () => {
  it('命中字典时出字典句', () => {
    const result = normalizeError(axiosError(415, 'unsupported_file'))
    expect(result.code).toBe('unsupported_file')
    expect(result.rawCode).toBe('')
    expect(result.message).toBe('这个文件类型系统暂不支持，请换一种格式再传。')
    expect(result.retryable).toBe(false)
  })

  it('data.py 的部门范围缺失与同名冲突也走字典', () => {
    expect(normalizeError(axiosError(403, 'department_scope_required')).message).toBe('请先选择部门范围，再生成这项结果。')
    expect(normalizeError(axiosError(409, 'dataset_filename_conflict')).code).toBe('dataset_filename_conflict')
  })

  it('历史别名归一到枚举码，原码留在 rawCode', () => {
    const big = normalizeError(axiosError(413, 'upload_too_large'))
    expect(big.code).toBe('unsupported_file')
    expect(big.rawCode).toBe('upload_too_large')
    expect(big.message).toContain('文件太大')
    const idx = normalizeError(axiosError(500, 'document_index_failed'))
    expect(idx.code).toBe('index_publish_failed')
    expect(idx.retryable).toBe(true)
  })

  it('后端已写成人话的 detail 原样直出，只按状态补分类码', () => {
    const result = normalizeError(axiosError(401, '用户名或密码错误'))
    expect(result.message).toBe('用户名或密码错误')
    expect(result.code).toBe('authentication_required')
    expect(errorCodeLabel(result)).toBe('')
  })

  it('未知码走兜底句：code 留空、原码进 rawCode 并可报告', () => {
    const err = axiosError(500, 'brand_new_backend_code')
    const result = normalizeError(err)
    inEnum(result, 'brand_new_backend_code')
    expect(result.code).toBe('internal_error')
    expect(result.rawCode).toBe('brand_new_backend_code')
    expect(result.message).toBe(FALLBACK_MESSAGE)
    expect(errorCodeLabel(result)).toBe('错误码：brand_new_backend_code')
    expect(formatError(err)).toBe(`${FALLBACK_MESSAGE}（错误码：brand_new_backend_code）`)
  })

  it('未知码且状态也无法归类时 code 为空，但小字仍在', () => {
    const result = normalizeError({ response: { status: 418, data: { detail: 'teapot_code' } } })
    expect(result.code).toBe('')
    expect(result.rawCode).toBe('teapot_code')
    expect(errorCodeLabel(result)).toBe('错误码：teapot_code')
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

  it('envelope 的 code 里塞中文也不许污染 .code', () => {
    const result = normalizeError(envelope('请先登录', ''))
    inEnum(result, 'envelope 中文码')
    expect(result.code).toBe('authentication_required')
    expect(result.rawCode).toBe('请先登录')
  })

  it('未知 envelope 码走兜底句但保留原码', () => {
    const err = envelope('mystery_code', '')
    const result = normalizeError(err)
    expect(result.code).toBe('internal_error')
    expect(result.rawCode).toBe('mystery_code')
    expect(result.message).toBe(FALLBACK_MESSAGE)
    expect(formatError(err)).toContain('错误码：mystery_code')
  })

  it('chat.py::_document_index_error 的真实结构能直接吃', () => {
    const result = normalizeError({
      response: {
        status: 500,
        data: { detail: { code: 'index_publish_failed', message: '文件已收到，但没能进入知识库。', retryable: true, details: { filename: '制度.docx', stage: 'publish' } } },
      },
    })
    expect(result.code).toBe('index_publish_failed')
    expect(result.message).toBe('文件已收到，但没能进入知识库。')
    expect(result.retryable).toBe(true)
  })
})

describe('形状 3：FastAPI 422 校验数组', () => {
  it('缺字段时说清是哪个字段', () => {
    const result = normalizeError(axiosError(422, [{ loc: ['body', 'department'], msg: 'Field required', type: 'missing' }]))
    inEnum(result, '422 missing')
    expect(result.code).toBe('validation_error')
    expect(result.message).toBe('「department」为必填项，请补充后再提交。')
    expect(result.retryable).toBe(false)
    expect(errorCodeLabel(result)).toBe('')
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

describe('脏输入的不变量', () => {
  const dirt = [
    undefined, null, {}, '', '   ', 0, 123, true, [],
    '[object Object]', { detail: '[object Object]' },
    '<!DOCTYPE html><html><body>502 Bad Gateway</body></html>',
    { response: { status: 502, data: '<html><body>502 Bad Gateway</body></html>' } },
    { response: { status: 401, data: { detail: { code: null, message: null } } } },
    { response: { status: 401, data: { detail: { code: 123, message: 456 } } } },
    { response: { status: 401, data: { detail: [{ loc: null, msg: null }] } } },
    { response: { status: 401, data: { detail: { code: 'x'.repeat(600) } } } },
    { response: { status: 403, data: { detail: { code: 'PERMISSION_DENIED' } } } },
    { response: { status: 403, data: { detail: '权限不足: users:manage' } } },
    { response: { status: 404, data: { detail: '用户不存在' } } },
    { response: { status: 422, data: { detail: 'not an array but a string' } } },
    new Error('会话已过期'),
  ]

  it.each(dirt.map((input, index) => [index, input]))('第 %i 条脏输入：code 落在枚举内、message 是人话、retryable 是布尔', (_index, input) => {
    const result = normalizeError(input)
    inEnum(result, JSON.stringify(input))
    expect(result.message.length, JSON.stringify(input)).toBeGreaterThan(0)
    expect(result.message).not.toContain('[object Object]')
    expect(result.message).not.toMatch(/^<(!doctype|html)/i)
    expect(result.message).not.toMatch(/^Request failed with status code/)
  })

  it('大写/带空格的伪码不许进 code，但原样留在 rawCode 供排查', () => {
    const upper = normalizeError({ response: { status: 403, data: { detail: { code: 'PERMISSION_DENIED' } } } })
    expect(upper.code).toBe('permission_denied')
    expect(upper.rawCode).toBe('PERMISSION_DENIED')
  })

  it('只有状态码也能归类', () => {
    expect(normalizeError({ response: { status: 404, data: {} } }).code).toBe('resource_not_found')
    expect(normalizeError({ response: { status: 429, data: {} } }).message).toBe(ERROR_CODES.rate_limited.message)
    expect(normalizeError({ response: { status: 504, data: {} } }).code).toBe('task_timeout')
  })

  it('断网与超时区分开，且都提示可重试', () => {
    const offline = normalizeError({ code: 'ERR_NETWORK', request: {}, message: 'Network Error' })
    expect(offline.retryable).toBe(true)
    expect(offline.message).toContain('连不上服务')
    expect(offline.rawCode).toBe('ERR_NETWORK')
    const timeout = normalizeError({ code: 'ECONNABORTED', message: 'timeout of 30000ms exceeded' })
    expect(timeout.code).toBe('task_timeout')
  })

  it('喂 undefined / null / 空对象都不崩，给兜底句且无码', () => {
    ;[undefined, null, {}, ''].forEach((input) => {
      const result = normalizeError(input)
      expect(result.message).toBe(FALLBACK_MESSAGE)
      expect(result.code).toBe('')
      expect(result.rawCode).toBe('')
      expect(result.retryable).toBe(false)
    })
  })

  it('裸字符串码与 Error 实例也接得住', () => {
    expect(normalizeError('invalid_filename').message).toBe(ERROR_CODES.invalid_filename.message)
    expect(normalizeError(new Error('会话已过期')).message).toBe('会话已过期')
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
    expect(isRetryable(axiosError(403, '账号不可用'))).toBe(false)
  })

  it('errorText 认枚举码、别名与散文', () => {
    expect(errorText('chart_generation_failed')).toBe(ERROR_CODES.chart_generation_failed.message)
    expect(errorText('export_failed')).toContain('导出')
    expect(errorText('请先登录')).toBe(ERROR_CODES.authentication_required.message)
    expect(errorText('nope')).toBe(FALLBACK_MESSAGE)
  })

  it('formatError 对已知码不加噪声小字', () => {
    expect(formatError(axiosError(415, 'unsupported_file'))).toBe(ERROR_CODES.unsupported_file.message)
  })

  it('normalizeError 的产物可以直接喂 errorCodeLabel / formatError', () => {
    const result = normalizeError(axiosError(500, 'odd_code'))
    expect(errorCodeLabel(result)).toBe('错误码：odd_code')
    expect(formatError(result)).toBe(`${FALLBACK_MESSAGE}（错误码：odd_code）`)
  })
})

/**
 * 文案政策（B-5 ②）的字面量侧：后端/sessions.js 有句子把码名夹在正文里直出，
 * 这里断言 normalizeError 会摘掉码名再收口，且政策判据本身可机器验证。
 */
describe('文案政策②：正文夹带裸码名（B-5-2）', () => {
  const BARE = /\b[a-z][a-z0-9]*(_[a-z0-9]+)+\b/

  it('app/api/v1/chat.py:998 的原句认得出码，且吐出去掉码名的字典句', () => {
    const raw = '本轮未产出任何结论（error_code=no_answer_produced），请重试或补充数据范围。'
    const result = normalizeError(axiosError(200, raw))
    inEnum(result, 'chat.py:998')
    expect(result.code).toBe('no_answer_produced')
    expect(result.message).toBe(ERROR_CODES.no_answer_produced.message)
    expect(BARE.test(result.message)).toBe(false)
    expect(errorCodeLabel(result)).toBe('')
  })

  it('lib/sessions.js:376 的中文括号裸码同样收口到字典句', () => {
    const result = normalizeError(axiosError(200, '本轮未产出任何结论（no_answer_produced），请重试或补充数据范围。'))
    expect(result.code).toBe('no_answer_produced')
    expect(result.message).toBe(ERROR_CODES.no_answer_produced.message)
    expect(BARE.test(result.message)).toBe(false)
  })

  it('半角括号 + 英文标点混排也能摘干净', () => {
    const result = normalizeError(axiosError(504, '请求超过系统处理时限(task_timeout)。'))
    expect(result.code).toBe('task_timeout')
    expect(result.message).toBe(ERROR_CODES.task_timeout.message)
  })

  it('内嵌未知码：码名摘出进 rawCode，正文读得通，小字仍可报告', () => {
    const raw = '工作簿没能解析（error_code=workbook_lock_failed），请另存为 xlsx 再传一次。'
    const result = normalizeError(axiosError(400, raw))
    inEnum(result, 'workbook_lock_failed')
    expect(result.code).toBe('validation_error')
    expect(result.rawCode).toBe('workbook_lock_failed')
    expect(BARE.test(result.message)).toBe(false)
    expect(result.message).toContain('请另存为 xlsx 再传一次')
    expect(formatError(result)).toContain('错误码：workbook_lock_failed')
  })

  it('括号里是普通词时一口都不吃：宁可漏判也不改坏句子', () => {
    const result = normalizeError(axiosError(400, '字段（id）不能为空，请补齐后再提交。'))
    expect(result.code).toBe('validation_error')
    expect(result.message).toBe('字段（id）不能为空，请补齐后再提交。')
    expect(result.rawCode).toBe('字段（id）不能为空，请补齐后再提交。')
  })

  it('errorCodeOf 独立通道：只回枚举码或空串，永不回散文', () => {
    ALL_CODES.forEach((code) => {
      expect(errorCodeOf({ response: { status: 200, data: { detail: code } } }), code).toBe(code)
    })
    expect(errorCodeOf(axiosError(401, '请先登录'))).toBe('authentication_required')
    expect(errorCodeOf(axiosError(200, '本轮未产出任何结论（no_answer_produced），请重试或补充数据范围。'))).toBe('no_answer_produced')
    // 状态可归类时按状态给枚举码，状态也给不出时才回空串
    expect(errorCodeOf(axiosError(500, 'odd_new_code'))).toBe('internal_error')
    expect(errorCodeOf(axiosError(200, 'odd_new_code'))).toBe('')
    expect(errorCodeOf(axiosError(500, '完全看不懂的一句话'))).toBe('internal_error')
    expect(errorCodeOf(axiosError(200, '完全看不懂的一句话'))).toBe('')
    expect(errorCodeOf(undefined)).toBe('')
    Object.keys(ERROR_CODES).concat(Object.keys(LEGACY_ALIASES), Object.keys(PROSE_ALIASES)).forEach((input) => {
      const value = errorCodeOf({ response: { status: 200, data: { detail: input } } })
      expect(value === '' || ENUM.includes(value), input).toBe(true)
      expect(/[\u4e00-\u9fff]/.test(value), input).toBe(false)
    })
  })

  it('字典里的每一条用户可见文案自己先过政策：不含裸码名', () => {
    Object.entries(ERROR_CODES).forEach(([code, entry]) => {
      expect(BARE.test(entry.message), code).toBe(false)
    })
    Object.entries(LEGACY_ALIASES).forEach(([legacy, entry]) => {
      expect(BARE.test(entry.message), legacy).toBe(false)
    })
    Object.values(PROSE_ALIASES).forEach((entry) => {
      expect(BARE.test(entry.message || '')).toBe(false)
    })
    expect(BARE.test(FALLBACK_MESSAGE)).toBe(false)
  })
})
