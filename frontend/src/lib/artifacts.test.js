/**
 * A-4-1 · artifacts.js 的错误体解析改吃 lib/errcodes.js 之后，行为必须"为零或变好"
 *
 * 对照基准是删掉的那份私拷：它只回一个字符串、不接 status，并且把后端原串
 * （常常就是裸码名）直接当文案抛给界面。这里逐形状比对新旧差异。
 * 环境是 node（无 jsdom），Blob 用 node 全局，URL.createObjectURL 手工桩。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { httpGet } = vi.hoisted(() => ({ httpGet: vi.fn() }))
vi.mock('./http', () => ({ http: { get: httpGet } }))

const { fetchArtifactBlob } = await import('./artifacts.js')

const failWith = (status, body) => {
  httpGet.mockRejectedValue({ response: { status, data: body instanceof Blob ? body : new Blob([body], { type: 'application/json' }) } })
}
const reject = () => httpGet.mockRejectedValue({ name: 'CanceledError', code: 'ERR_CANCELED' })
const grab = async () => {
  try {
    await fetchArtifactBlob('/static/x.png')
  } catch (e) {
    return e
  }
  throw new Error('这条用例本来就该抛出错误')
}
const BARE_CODE = /\b[a-z][a-z0-9]*(_[a-z0-9]+)+\b/

describe('artifacts · 取图失败的说法统一由字典负责', () => {
  // 花括号是必需的：箭头函数把 Mock（可调用对象）当返回值交出去，Vitest 5 会把它
  // 当成 teardown 再调一次，于是凭空多出一个没人 await 的 rejected promise。
  beforeEach(() => {
    httpGet.mockReset()
  })

  it('私拷已删，改从 errcodes 引（全站只留一份 blob 错误解析）', () => {
    const s = readFileSync(new URL('./artifacts.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
    expect(s).toContain("import { readBlobError } from './errcodes'")
    expect(s).not.toMatch(/function readBlobError/)
    expect(s.match(/readBlobError\(/g)).toHaveLength(1)
  })

  it('status 真的传进了通用函数（私拷的老签名接不到它）', () => {
    const s = readFileSync(new URL('./artifacts.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
    expect(s).toContain('readBlobError(blob, status)')
  })

  // 形状①：detail 是裸稳定码。老实现 = 把 "permission_denied" 当句子画到占位卡上。
  it('403 + permission_denied：出字典句而不是码名，code/status/retryable 三样都在', async () => {
    failWith(403, '{"detail":"permission_denied"}')
    const err = await grab()
    expect(err.code).toBe('permission_denied')
    expect(err.status).toBe(403)
    expect(err.retryable).toBe(false)
    expect(err.message).not.toContain('permission_denied')
    expect(err.message).toMatch(/权限/)
    expect(BARE_CODE.test(err.message)).toBe(false)
  })

  // 形状②：ErrorEnvelope（下载与 SSE 错误体用的是 error_code）
  it('400 + ErrorEnvelope：认 error_code 这个字段名，后端 message 优先', async () => {
    failWith(400, '{"detail":{"error_code":"unsupported_file","message":"这个文件类型不支持","retryable":false}}')
    const err = await grab()
    expect(err.code).toBe('unsupported_file')
    expect(err.status).toBe(400)
    expect(err.message).toBe('这个文件类型不支持')
  })

  // 形状③：非 JSON。私拷会把正文前 120 字当 detail 返回，nginx 页面就此上屏。
  it('502 + 网关 HTML：不把 HTML 当人话，按状态归类；老实现会截 120 字直出', async () => {
    httpGet.mockRejectedValue({ response: { status: 502, data: new Blob(['<html><body>502 Bad Gateway</body></html>'], { type: 'text/html' }) } })
    const err = await grab()
    expect(err.message).not.toContain('502 Bad Gateway')
    expect(err.message).not.toContain('<html')
    expect(err.status).toBe(502)
    expect(BARE_CODE.test(err.message)).toBe(false)
  })

  // 形状④：空 body。私拷回空串，只能落到 "取图失败（HTTP 404）" 这种半人话。
  it('404 + 空 body：仍然是一句人话且留着状态', async () => {
    failWith(404, '')
    const err = await grab()
    expect(err.status).toBe(404)
    expect(err.message.length).toBeGreaterThan(0)
    expect(err.message).not.toMatch(/^取图失败（HTTP/)
    expect(BARE_CODE.test(err.message)).toBe(false)
  })

  it('取消这条路没被碰：ChartViewer.vue:56 还要靠 code==="aborted" 少画一张失败卡', async () => {
    reject()
    const err = await grab()
    expect(err.code).toBe('aborted')
    expect(err.message).toBe('取图已取消')
  })

  it('成功路没被碰：回 objectUrl + 幂等 revoke', async () => {
    const created = []
    const revoked = []
    globalThis.URL.createObjectURL = blob => { created.push(blob.size); return 'blob:mock-1' }
    globalThis.URL.revokeObjectURL = url => revoked.push(url)
    httpGet.mockResolvedValue({ status: 200, data: new Blob(['png-bytes'], { type: 'image/png' }) })
    const handle = await fetchArtifactBlob('/static/ok.png')
    expect(handle.objectUrl).toBe('blob:mock-1')
    expect(handle.mediaType).toBe('image/png')
    handle.revoke()
    handle.revoke()
    expect(created).toEqual([9])
    expect(revoked).toEqual(['blob:mock-1'])
  })
})