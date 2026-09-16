/**
 * A-3-2 · R1(c) 判据单测 + A-4-2 · 取码器收口
 *
 * 「403 无权限」与「空列表」必须走两条不同的渲染路径，这里钉住判据本身。
 * A-4-2 之后判据不再自带一套取码逻辑：全站只有 lib/errcodes.js 的 errorCodeOf() 一个取码器，
 * 本文件因此从"验我自己的解析"改成"验薄通道接对了 + 形状覆盖变宽了 + 漏码上屏的老洞补上了"。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { PERMISSION_DENIED, errorDetail, isPermissionDenied } from './http.js'

/** 造一个 axios 风格的错误对象，只填判据真正会读的字段 */
const httpError = (detail, status = 403) => ({
  response: { status, data: { detail } },
  message: 'Request failed with status code ' + status,
})

describe('A-4-2 · 全站只留一个取码器', () => {
  const http = readFileSync(new URL('./http.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
  const errcodes = readFileSync(new URL('./errcodes.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n')

  it('http.js 里不再有第二份取码逻辑，只 import errcodes', () => {
    expect(http).not.toMatch(/function errorCode\b/)
    expect(http).toContain("import { FALLBACK_MESSAGE, errorCodeOf, normalizeError } from './errcodes'")
    expect(http.match(/errorCodeOf\(/g)).toHaveLength(1)
  })

  it('errcodes.js 仍只有一个定义处（没有被我复制一份过去）', () => {
    expect(errcodes.match(/export function errorCodeOf/g)).toHaveLength(1)
  })

  it('G2 那条 TODO 已经兑现，注释里不再挂着"待 B 线"', () => {
    expect(http).not.toContain('TODO(B 线')
    expect(http).not.toMatch(/TODO.*errcodes/)
  })
})

describe('isPermissionDenied：判据只认 permission_denied', () => {
  it('形状 1 —— detail 是字符串稳定码', () => {
    expect(isPermissionDenied(httpError('permission_denied'))).toBe(true)
  })

  it('形状 2 —— ErrorEnvelope，code 与 error_code 两个字段名都认', () => {
    expect(isPermissionDenied(httpError({ code: PERMISSION_DENIED, message: 'x', retryable: false }))).toBe(true)
    expect(isPermissionDenied(httpError({ error_code: PERMISSION_DENIED, message: 'x' }))).toBe(true)
  })

  // 合并前这份判据读不到这两种形状（老 errorCode 只看 detail 是字符串/对象，列表与裸体都漏）。
  it('收口后新认得两种形状：422 校验列表、只有 data.error_code 的裸体', () => {
    expect(isPermissionDenied(httpError([{ loc: ['body', 'rows'], msg: 'field required', type: 'missing' }], 422))).toBe(false)
    expect(isPermissionDenied({ response: { status: 403, data: { error_code: 'permission_denied' } }, message: 'x' })).toBe(true)
  })

  // 空列表是 200 响应，不是错误对象：这条把「空列表永不进无权限分支」钉死。
  it('空列表不算无权限（该画空态）', () => {
    expect(isPermissionDenied({ response: { status: 200, data: { relations: [] } } })).toBe(false)
  })

  // 同为 403 但语义不同（policy.py:159-162 resource_scope_missing、chat.py:312）不能画成没权限。
  // 这些码已在字典/别名表里，所以走的是"码优先"，不会被状态兜底盖掉。
  it('同为 403 的其他已登记码不算无权限', () => {
    for (const code of ['resource_scope_missing', 'authorization_unavailable', 'account_unavailable', 'department_scope_required']) {
      expect(isPermissionDenied(httpError(code)), code).toBe(false)
    }
  })

  it('401 与 500 不算无权限', () => {
    expect(isPermissionDenied(httpError('authentication_required', 401))).toBe(false)
    expect(isPermissionDenied(httpError('internal_error', 500))).toBe(false)
  })

  it('undefined / 断网不算无权限（该画带重试的失败态）', () => {
    expect(isPermissionDenied(undefined)).toBe(false)
    expect(isPermissionDenied({ message: 'Network Error' })).toBe(false)
  })

  // 合并带来的唯一放宽：403 且码没登记（或没有响应体）时按 STATUS_CODES[403] 归类。
  // 记在这里是让它被看见，而不是被藏起来：这类情况以前画"加载失败+重试"，现在画"没权限"。
  it('放宽面只有两种：403 无响应体、403 带未登记码（已登记码不受影响）', () => {
    expect(isPermissionDenied({ response: { status: 403, data: {} }, message: 'x' })).toBe(true)
    expect(isPermissionDenied(httpError('a_code_nobody_registered_yet'))).toBe(true)
    expect(isPermissionDenied(httpError('a_code_nobody_registered_yet', 500))).toBe(false)
  })
})

describe('errorDetail：句子一律出自字典，本函数只管退回场景文案', () => {
  // 合并前这里会把形状 2 的码名原样 return，面板又直插进 UiErrorState 的 description，
  // 于是屏幕上出现 "permission_denied"。这是运行时漏码，静态扫描抓不到，只能这样钉。
  it('后端回裸码名时给人话句子，不再把码名当文案上屏', () => {
    const text = errorDetail(httpError('permission_denied'), '关系列表加载失败')
    expect(text).not.toContain('permission_denied')
    expect(text).toContain('权限')
  })

  it('后端 message 优先原样（信息量不降级）', () => {
    expect(errorDetail(httpError({ error_code: 'unsupported_file', message: '这个文件类型不支持' }, 400), '文档列表加载失败'))
      .toBe('这个文件类型不支持')
  })

  it('字典只剩通用兜底句时，退回调用方那句更具体的场景文案', () => {
    expect(errorDetail({ message: 'x' }, '文档列表加载失败')).toBe('文档列表加载失败')
  })

  // 放宽的另一处落点：403 且响应体为空时字典按 STATUS_CODES[403] 归类，
  // 于是这句不再是笼统的「关系列表加载失败」，而是说清是没权限。
  it('403 无响应体：出按状态归类的权限句，而不是笼统场景文案', () => {
    const text = errorDetail(httpError(''), '关系列表加载失败')
    expect(text).toContain('权限')
    expect(text).not.toBe('关系列表加载失败')
    expect(errorDetail(httpError('a_code_nobody_registered_yet', 500), '关系列表加载失败')).toBe('关系列表加载失败')
    expect(errorDetail(undefined, '图谱没加载出来')).toBe('图谱没加载出来')
  })

  it('axios 英文原句绝不上屏', () => {
    expect(errorDetail(httpError(''), 'x')).not.toMatch(/Request failed with status code/)
  })

  it('断网这类有人话 message 的错误，句子照旧直出', () => {
    expect(errorDetail(new Error('连不上服务'), 'x')).toBe('连不上服务')
  })
})