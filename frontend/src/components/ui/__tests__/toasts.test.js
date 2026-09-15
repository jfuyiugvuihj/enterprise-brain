import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearToasts, dismissToast, notifyError, notifySuccess, pushToast, useToasts } from '../toasts.js'
import { ERROR_CODES } from '../../../lib/errcodes.js'

const { toasts } = useToasts()
const pending = []

afterEach(() => {
  clearToasts()
  pending.length = 0
  delete globalThis.window
})

function withWindow() {
  globalThis.window = {
    document: {},
    setTimeout: (fn) => {
      pending.push(fn)
      return pending.length
    },
  }
}

describe('toast 队列', () => {
  it('空队列里没有卡片，也不会凭空出现提示框', () => {
    expect(toasts.length).toBe(0)
  })

  it('字符串入参也能入队，默认 info 语气', () => {
    pushToast('已保存')
    expect(toasts.length).toBe(1)
    expect(toasts[0].message).toBe('已保存')
    expect(toasts[0].tone).toBe('info')
    expect(toasts[0].codeLabel).toBe('')
  })

  it('超过 4 条丢最旧的，避免刷屏', () => {
    ;['一', '二', '三', '四', '五'].forEach((message) => pushToast({ message, timeout: 0 }))
    expect(toasts.length).toBe(4)
    expect(toasts.map((toast) => toast.message)).toEqual(['二', '三', '四', '五'])
  })

  it('dismiss 按 id 摘除单条', () => {
    const id = pushToast({ message: '临时', timeout: 0 })
    pushToast({ message: '留下', timeout: 0 })
    dismissToast(id)
    expect(toasts.map((toast) => toast.message)).toEqual(['留下'])
  })

  it('timeout=0 即粘住，不注册定时器', () => {
    withWindow()
    pushToast({ message: '必须手动关', timeout: 0 })
    expect(pending.length).toBe(0)
    pushToast({ message: '会自动走', timeout: 6000 })
    expect(pending.length).toBe(1)
    pending[0]()
    // 自动消失的那条走了，粘住的那条留下
    expect(toasts.map((toast) => toast.message)).toEqual(['必须手动关'])
  })
})

describe('notifyError 承接三种错误形状', () => {
  it('形状 1 字符串码：出字典句，已知码不附错误码小字', () => {
    withWindow()
    notifyError({ response: { status: 415, data: { detail: 'unsupported_file' } } })
    expect(toasts[0]).toMatchObject({ tone: 'danger', message: ERROR_CODES.unsupported_file.message, codeLabel: '' })
    expect(toasts[0].retryable).toBe(false)
  })

  it('形状 2 ErrorEnvelope：不再弹 [object Object]', () => {
    withWindow()
    notifyError({ response: { status: 500, data: { detail: { code: 'index_publish_failed', message: '文件已收到，但没能进入知识库。', retryable: true, details: {} } } } })
    expect(toasts[0].message).toBe('文件已收到，但没能进入知识库。')
    expect(toasts[0].message).not.toContain('[object Object]')
    expect(toasts[0].retryable).toBe(true)
  })

  it('形状 3 422 数组：说清是哪个字段', () => {
    withWindow()
    notifyError({ response: { status: 422, data: { detail: [{ loc: ['body', 'department'], msg: 'Field required', type: 'missing' }] } } })
    expect(toasts[0].message).toBe('「department」为必填项，请补充后再提交。')
  })

  it('未知码把码名留在小字里，保留可报告性', () => {
    withWindow()
    notifyError({ response: { status: 500, data: { detail: 'odd_new_code' } } })
    expect(toasts[0].message).toBe('操作没有完成，请稍后重试。')
    expect(toasts[0].codeLabel).toBe('错误码：odd_new_code')
  })

  it('成功语气用于写回成功，不与错误混色', () => {
    withWindow()
    notifySuccess('已提交')
    expect(toasts[0]).toMatchObject({ tone: 'success', message: '已提交' })
  })

  it('空 message 时用兜底句，不产生空气泡', () => {
    withWindow()
    notifyError({ response: { status: 500, data: { detail: '' } } })
    expect(toasts[0].message.length).toBeGreaterThan(4)
    expect(vi.isMockFunction(setTimeout)).toBe(false)
  })
})
