/*
 * R291 · 两枚站点的接线（总控批 A 案：ArtifactList.vue 的列表脸与操作脸）
 *
 * 这一件只管一件事：**从组件真实状态出发的最后一跳接上了，而且接的是错误对象本身**。
 * 与 artifact-list.test.js 的区别是刻意少一层 mock —— 本件不 mock lib/artifacts，
 * 只把网络层 lib/http 打成桩，于是操作脸（463 那一处）拿到的 Error 是
 * lib/artifacts.js 真身重建并 attachRawText 过的那一枚，不是测试手搓的相似物。
 *
 * 两枚站点各跑一次真流程：
 *   甲 394  v-else-if="face === 'error'"  ← loadArtifacts() 的 catch，错误来自 http.js 的 GET
 *   乙 463  v-if="actionError"            ← openArtifact() 的 catch，错误来自 lib/artifacts.js
 * 判据：屏上逐字出现后端回的那一句；没有原文（裸码名 / 压根没有错误对象 / 越权）时那张脸不变。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it, vi } from 'vitest'
import { h, toRaw } from 'vue'
import { renderToString } from '@vue/server-renderer'

const { httpGet, httpDelete } = vi.hoisted(() => ({ httpGet: vi.fn(), httpDelete: vi.fn() }))
// errorDetail / isPermissionDenied 保持真身（与 artifact-list.test.js 同一口径）：
// mock 掉它们等于让判据被桩改掉。lib/artifacts 不 mock —— 463 那发的真身要从那里出门。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: httpGet, delete: httpDelete } }
})

const ArtifactList = (await import('../ArtifactList.vue')).default
const { mapArtifactRow, openTargetUrl } = await import('../ArtifactList.vue')
const UiErrorState = (await import('../ui/UiErrorState.vue')).default

const LIST_URL = '/artifacts'
/** 后端在信封 message 那一格原样回的话：形状 2，字典有话说 ⇒ 人话位归中文，这一句今天没地方画 */
const BACKEND_ZH = '工作簿受密码保护，无法读取。'
const BACKEND_EXPIRY = 'artifact content is expired and was purged from the store'

const source = () => readFileSync(new URL('../ArtifactList.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')

/** 借最小宿主把真 setup() 的绑定对象取回来（ref 不解包，一律 .value），与 artifact-list.test.js 同一手法 */
async function mountBindings(component) {
  let bindings = null
  const Probe = {
    name: 'R291Probe',
    setup(props, ctx) {
      bindings = component.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Probe))
  expect(bindings, '组件应暴露可调用的 setup()').toBeTruthy()
  return bindings
}

function apiRow(overrides) {
  return Object.assign({
    artifact_id: 'a1',
    artifact_type: 'chart',
    filename: '销售额趋势.png',
    content_url: '/api/v1/artifacts/a1/content',
    download_url: '/api/v1/artifacts/a1/download',
    expires_at: '2026-09-30T00:00:00+00:00',
    created_at: '2026-09-16T03:12:44.123456+00:00',
  }, overrides || {})
}

/** axios 形状的失败：JSON 错误体（列表与删除走这条），detail 给对象就是形状 2 */
const jsonError = (status, detail) => ({ response: { status, data: { detail } }, message: 'Request failed with status code ' + status })
/** 取字节的失败：responseType:'blob' 下错误体是 Blob，artifacts.js 靠这一格判定走通用解析器 */
const blobError = (status, body) => ({ response: { status, data: new Blob([body], { type: 'application/json' }) }, message: 'Request failed' })

const RAW_RE = /<p class="ui-error-state__detail-text"[^>]*>([^<]*)<\/p>/

/** 把某一处站点此刻真的往原语上递的那几枚 prop 原样复现一次（值全部来自组件真状态） */
const renderSite = props => renderToString(h(UiErrorState, props))

describe('甲 · 394 列表脸：错误对象存进 loadErrorSource，原话随真状态上屏', () => {
  it('这一发的 catch 把真错误对象留住，不是句子也不是复制品', async () => {
    const thrown = jsonError(400, { code: 'parse_failed', message: BACKEND_ZH })
    httpGet.mockRejectedValueOnce(thrown)
    const vm = await mountBindings(ArtifactList)
    await vm.loadArtifacts()
    expect(vm.face.value).toBe('error')
    // ref() 对普通对象做 toReactive（Error 实例不做），所以这一格取回的是真身的代理；
    // 断言用 toRaw 比对象本身，而不是退成 toEqual：代理会照样透出 rawMessage，但身份必须是同一枚。
    expect(toRaw(vm.loadErrorSource.value), '详情区没有可读的对象：错误对象没被留下来').toBe(thrown)
    expect(vm.loadError.value, '人话位上仍是字典那句，本单一个字没改').not.toContain(BACKEND_ZH)
  })

  it('模板里那一处确实把这一格递给了原语（props 复现与源码同一枚绑定）', () => {
    const s = source()
    const at = s.indexOf(`v-else-if="face === 'error'"`)
    expect(at).toBeGreaterThan(-1)
    const site = s.slice(at, s.indexOf('/>', at))
    expect(site).toContain(':raw-error="loadErrorSource"')
    expect(site).toContain(':description="listView.description"')
    expect(site.indexOf(':description="listView.description"')).toBeLessThan(site.indexOf(':raw-error="loadErrorSource"'))
  })

  it('SSR：394 那一处的屏上逐字出现后端原话', async () => {
    httpGet.mockRejectedValueOnce(jsonError(400, { code: 'parse_failed', message: BACKEND_ZH }))
    const vm = await mountBindings(ArtifactList)
    await vm.loadArtifacts()
    const view = vm.listView.value
    const html = await renderSite({
      title: view.title,
      description: view.description,
      rawError: vm.loadErrorSource.value,
      retryable: view.retryable,
    })
    expect(html).toContain(BACKEND_ZH)
    const hit = RAW_RE.exec(html)
    expect(hit, '详情区没长出来').not.toBeNull()
    expect(hit[1]).toBe(BACKEND_ZH)
    // 人话位没被顶掉：中文那句还在，两句话一处一个位
    expect(html).toContain('文件内容没能解析成功，请检查文件是否损坏或受保护。')
  })

  it('裸码名那一发（鉴权门的真形状）不产出原文：还是今天那张脸', async () => {
    httpGet.mockRejectedValueOnce(jsonError(500, 'internal_error'))
    const vm = await mountBindings(ArtifactList)
    await vm.loadArtifacts()
    const view = vm.listView.value
    const plain = await renderSite({ title: view.title, description: view.description, retryable: view.retryable })
    const wired = await renderSite({ title: view.title, description: view.description, retryable: view.retryable, rawError: vm.loadErrorSource.value })
    expect(wired).toBe(plain)
    expect(wired).not.toContain('ui-error-state__detail')
  })

  it('403 那一发（列表读不到最常见的那张脸）不显示后端原文', async () => {
    httpGet.mockRejectedValueOnce(jsonError(403, { code: 'permission_denied', message: BACKEND_EXPIRY }))
    const vm = await mountBindings(ArtifactList)
    await vm.loadArtifacts()
    expect(vm.loadDenied.value).toBe(true)
    const view = vm.listView.value
    const html = await renderSite({ title: view.title, description: view.description, rawError: vm.loadErrorSource.value, retryable: view.retryable })
    expect(html).not.toContain(BACKEND_EXPIRY)
    expect(html).not.toContain('ui-error-state__detail')
    expect(html).toContain('当前账号没有查看分析产物的权限，请联系管理员开通。')
  })
})

describe('乙 · 463 操作脸：错误对象是 lib/artifacts.js 真身重建的那一枚', () => {
  async function vmWithRow(overrides) {
    const vm = await mountBindings(ArtifactList)
    vm.rows.value = [mapArtifactRow(apiRow(overrides))]
    return vm
  }

  it('取字节的 catch 把 artifacts.js 那枚 Error 原样留下（rawMessage 是它带的，不是测试造的）', async () => {
    httpGet.mockImplementation(url => (url === LIST_URL ? Promise.reject(new Error('不该发列表请求')) : Promise.reject(blobError(400, JSON.stringify({ detail: { error_code: 'parse_failed', message: BACKEND_ZH } })))))
    const vm = await vmWithRow()
    await vm.openArtifact(vm.rows.value[0])
    const source_ = vm.actionErrorSource.value
    expect(source_, '操作脸没有错误对象可递：463 那一处接的是空').not.toBeNull()
    expect(source_ instanceof Error).toBe(true)
    // 出处取证：这枚 Error 是在 fetchArtifactBlob 的 catch 里 new 出来的，栈上就带着那个函数名 ——
    // 它不是组件自己造的相似物，也不可能是测试手搓的。
    expect(String(source_.stack), '这枚错误不是 lib/artifacts.js 重建的那一枚').toMatch(/attachRawText|fetchArtifactBlob/)
    expect(source_.rawMessage, 'lib/artifacts.js 的那两格没跟到消费口').toBe(BACKEND_ZH)
    expect(source_.rawCode).toBe('parse_failed')
    expect(source_.status).toBe(400)
    expect(vm.actionError.value.description).toBe('文件内容没能解析成功，请检查文件是否损坏或受保护。')
  })

  it('模板里那一处确实把这一格递给了原语', () => {
    const s = source()
    const at = s.indexOf('v-if="actionError"')
    expect(at).toBeGreaterThan(-1)
    const site = s.slice(at, s.indexOf('/>', at))
    expect(site).toContain(':raw-error="actionErrorSource"')
    expect(site).toContain(':description="actionView.description"')
  })

  it('SSR：463 那一处的屏上逐字出现后端原话', async () => {
    httpGet.mockRejectedValue(blobError(500, JSON.stringify({ detail: { code: 'internal_error', message: BACKEND_EXPIRY } })))
    const vm = await vmWithRow()
    await vm.openArtifact(vm.rows.value[0])
    const view = vm.actionView.value
    const html = await renderSite({
      title: view.title,
      description: view.description,
      rawError: vm.actionErrorSource.value,
      retryable: view.retryable,
    })
    expect(html).toContain(BACKEND_EXPIRY)
    const hit = RAW_RE.exec(html)
    expect(hit, '详情区没长出来').not.toBeNull()
    expect(hit[1]).toBe(BACKEND_EXPIRY)
    expect(html).toContain('系统内部出现异常，请稍后重试。')
  })

  it('密级那一发不显示原文：这一处接的是真身，拦住它的也是真身', async () => {
    httpGet.mockRejectedValue(blobError(403, JSON.stringify({ detail: { code: 'clearance_insufficient', message: 'clearance level 3 required for this artifact' } })))
    const vm = await vmWithRow()
    await vm.openArtifact(vm.rows.value[0])
    expect(vm.actionErrorSource.value.rawMessage).toBe('clearance level 3 required for this artifact')
    const view = vm.actionView.value
    const html = await renderSite({ title: view.title, description: view.description, rawError: vm.actionErrorSource.value, retryable: view.retryable })
    expect(html).not.toContain('clearance level 3 required')
    expect(html).not.toContain('ui-error-state__detail')
    // 这一处的人话由面板自己的 openErrorView 定（isPermissionDenied 走 denied 那一支），
    // 不是字典别名句：本单不碰这张脸，只钉「原文没混进来」。
    expect(html).toContain('当前账号没有查看这份内容的权限，请联系管理员开通。')
  })

  it('压根没有错误对象的那一发（没有可打开的地址）留 null：前端不替后端编一句话', async () => {
    const vm = await vmWithRow({ content_url: '', download_url: '' })
    await vm.openArtifact(vm.rows.value[0])
    expect(openTargetUrl(vm.rows.value[0])).toBe('')
    expect(httpGet).not.toHaveBeenCalled()
    expect(vm.actionErrorSource.value).toBe(null)
    const view = vm.actionView.value
    const plain = await renderSite({ title: view.title, description: view.description, retryable: view.retryable })
    const wired = await renderSite({ title: view.title, description: view.description, retryable: view.retryable, rawError: vm.actionErrorSource.value })
    expect(wired).toBe(plain)
    expect(wired).not.toContain('ui-error-state__detail')
    expect(wired).toContain('这条产物没有可打开的地址。')
  })

  it('两格同生同灭：重新取字节 / 刷新 / 换行待确认，都不会留下上一发的原文', async () => {
    httpGet.mockRejectedValue(blobError(500, JSON.stringify({ detail: { code: 'internal_error', message: BACKEND_EXPIRY } })))
    const vm = await vmWithRow()
    await vm.openArtifact(vm.rows.value[0])
    expect(vm.actionErrorSource.value).not.toBe(null)
    vm.actionError.value = null
    vm.actionErrorSource.value = null
    expect(vm.actionErrorSource.value).toBe(null)
    // retryAction 走的是同一条真通道，重发前那一格必须先清空（否则新脸挂旧原文）
    await vm.openArtifact(vm.rows.value[0])
    expect(vm.actionErrorSource.value).not.toBe(null)
    vm.reload()
    expect(vm.actionErrorSource.value).toBe(null)
    expect(vm.loadErrorSource.value).toBe(null)
  })
})
