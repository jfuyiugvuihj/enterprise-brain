/**
 * A-3-2 · R1(c) 判据单测
 *
 * 「403 无权限」与「空列表」必须走两条不同的渲染路径，这里钉住判据本身：
 * 判据是 detail 里的 canonical 稳定码 permission_denied（app/common/policy.py:157-158），
 * 不是 HTTP 状态码，也不是文案里有没有「权限」两个字。
 * 本文件只验判断，不验文案映射（映射表本体在 lib/errcodes.js，B-5 在做，A 线不抢）。
 */
import { describe, expect, it } from 'vitest'
import { PERMISSION_DENIED, errorCode, errorDetail, isPermissionDenied } from './http.js'

/** 造一个 axios 风格的错误对象，只填 errorCode/isPermissionDenied 真正会读的字段 */
const httpError = (detail, status = 403) => ({
  response: { status, data: { detail } },
  message: 'Request failed with status code ' + status,
})

describe('errorCode：后端三种错误形状都取得到稳定码', () => {
  it('形状 1 —— detail 是字符串稳定码', () => {
    expect(errorCode(httpError('permission_denied'))).toBe('permission_denied')
  })

  it('形状 2 —— detail 是 ErrorEnvelope，取 code / error_code', () => {
    expect(errorCode(httpError({ code: 'permission_denied', message: 'x', retryable: false }))).toBe('permission_denied')
    expect(errorCode(httpError({ error_code: 'dataset_preview_failed' }))).toBe('dataset_preview_failed')
  })

  it('形状 3 —— FastAPI 422 的 detail 是列表，取不到码就交空串，不崩', () => {
    expect(errorCode(httpError([{ loc: ['body', 'rows'], msg: 'field required', type: 'missing' }], 422))).toBe('')
  })

  it('断网 / 无响应 / 压根不是错误对象都交空串', () => {
    expect(errorCode({ message: 'Network Error' })).toBe('')
    expect(errorCode(undefined)).toBe('')
    expect(errorCode(new Error('boom'))).toBe('')
  })
})

describe('isPermissionDenied：无权限这条判据只认 permission_denied', () => {
  it('字符串码与 Envelope 码都算无权限', () => {
    expect(isPermissionDenied(httpError('permission_denied'))).toBe(true)
    expect(isPermissionDenied(httpError({ code: PERMISSION_DENIED, message: 'x' }))).toBe(true)
  })

  // 200 + 空数组不是错误，它该画空态；这条把「空列表永远不进无权限分支」钉死。
  it('空列表不是错误对象，判据为 false（该画空态）', () => {
    const emptyListResponse = { response: { status: 200, data: { relations: [] } } }
    expect(isPermissionDenied(emptyListResponse)).toBe(false)
    expect(errorCode(emptyListResponse)).toBe('')
  })

  // 同为 403 但原因不是 permission_denied（policy.py:159-162 的 resource_scope_missing、
  // chat.py:312 的 authorization_unavailable）不能画成「没权限」：那是暂时性的，该给重试。
  it('同为 403 的其他 reason code 不算无权限', () => {
    expect(isPermissionDenied(httpError('resource_scope_missing'))).toBe(false)
    expect(isPermissionDenied(httpError('authorization_unavailable'))).toBe(false)
    expect(isPermissionDenied(httpError('account_unavailable'))).toBe(false)
  })

  it('401 与 500 不算无权限', () => {
    expect(isPermissionDenied(httpError('authentication_required', 401))).toBe(false)
    expect(isPermissionDenied(httpError('internal_error', 500))).toBe(false)
  })

  it('undefined / 断网不算无权限（该画带重试的失败态）', () => {
    expect(isPermissionDenied(undefined)).toBe(false)
    expect(isPermissionDenied({ message: 'Network Error' })).toBe(false)
  })

  it('permission_denied 仍原样进 detail，说明判据没有顺手改掉文案通道', () => {
    expect(errorDetail(httpError('permission_denied'), '关系列表加载失败')).toBe('permission_denied')
    expect(errorDetail(httpError(''), '关系列表加载失败')).toBe('关系列表加载失败')
  })
})