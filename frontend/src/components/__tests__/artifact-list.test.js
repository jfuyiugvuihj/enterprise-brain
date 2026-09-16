/**
 * W2 · 分析产物列表（ArtifactList）与两处删除入口的判据单测
 *
 * 环境是 node + @vue/server-renderer（仓库里没有 jsdom / @vue/test-utils，也不许 npm i），
 * 所以断言分三条腿，各管各的事，不假装验过自己验不了的：
 *   ① 真逻辑：把 lib/http 与 lib/artifacts 换成假实现后，直接调组件自己的 setup() 取回真实
 *      绑定。SSR 不跑 onMounted，列表请求不会自己发出去，所以「加载中 / 无权限 / 空 / 有数据 /
 *      两步删除 / 失败文案」全是跑组件真代码得到的状态，而不是在测试里照抄一遍模板。
 *   ② 真产物：四张脸最终都交给 UiLoadingState / UiErrorState / UiEmptyState 渲染，role、
 *      aria-busy、重试按钮在不在，由 renderToString 出的真 HTML 说话。
 *   ③ 源码形状：分支顺序（进行 -> 失败 -> 空 -> 列表）、「打开」只吃 blob: 地址、
 *      不许出现 window.confirm 这类「渲染一次看不到」的判据，钉在源码上。
 *
 * 错误码字面量（permission_denied 等）在本文件里是「输入」而不是「输出」：
 * 判据是喂真码进真 errorDetail / isPermissionDenied（这两个不 mock），再断言界面拿到的
 * 句子已经没有人话之外的码名。__tests__ 目录不在裸码扫描范围内。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'

// 只换网络层与取字节层：errorDetail / isPermissionDenied 保持真身，判据才不会被 mock 顺带改掉。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), delete: vi.fn() } }
})

vi.mock('../../lib/artifacts', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, fetchArtifactBlob: vi.fn() }
})

import { errorDetail, http, isPermissionDenied } from '../../lib/http'
import { fetchArtifactBlob } from '../../lib/artifacts'
import ArtifactList, {
  ARTIFACT_PAGE_SIZE,
  advanceDelete,
  artifactExpiryText,
  artifactTypeLabel,
  deleteButtonLabel,
  deleteErrorView,
  formatArtifactTime,
  isOpenableImage,
  isPendingDelete,
  listErrorView,
  listFace,
  mapArtifactRow,
  openButtonLabel,
  openErrorView,
  openTargetUrl,
} from '../ArtifactList.vue'
import DataPanel from '../DataPanel.vue'
import { UiEmptyState, UiErrorState, UiLoadingState } from '../ui'

const source = (name) => readFileSync(new URL('../' + name, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const render = (component) => renderToString(h({ render: () => h(component) }))

/**
 * 跑真组件的 setup()：借一个最小宿主组件把实例上下文递进去，
 * 这样 onBeforeUnmount 之类挂在真实例上，不会有「脱离实例调用」的噪声。
 * 返回的是编译产物里的原始绑定对象，ref 不解包，所以测试一律写 .value。
 */
async function mountBindings(component) {
  let bindings = null
  const Probe = {
    name: 'W2Probe',
    setup(props, ctx) {
      bindings = component.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Probe))
  expect(bindings, '组件应暴露可调用的 setup()').toBeTruthy()
  return bindings
}

/** 后端 R2 的一行真形状（app/api/v1/artifacts.py 的 public_payload + filename/created_at）。 */
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

function apiPage(rows, extra) {
  return Object.assign({
    artifacts: rows,
    total: rows.length,
    returned: rows.length,
    limit: ARTIFACT_PAGE_SIZE,
    offset: 0,
    has_more: false,
    artifact_type: null,
  }, extra || {})
}

/** 403 / 404 / 500 的三种真形状：axios 的 { response: { status, data: { detail } } }。 */
function httpError(status, code) {
  return { response: { status, data: { detail: code } }, message: 'Request failed' }
}

// 后端码名不许出现在给人看的句子里（B-5 ②：码走独立通道，不进正文）。
const SNAKE = /[a-z][a-z0-9]*_[a-z0-9_]+/

beforeEach(() => {
  vi.clearAllMocks()
  http.get.mockResolvedValue({ data: apiPage([]) })
  http.delete.mockResolvedValue({ data: { status: 'ok' } })
  fetchArtifactBlob.mockResolvedValue({
    objectUrl: 'blob:preview-1',
    mediaType: 'image/png',
    size: 128,
    revoke() {},
  })
})

/** 剥掉注释后的代码体：像 window.open 这种词只许出现在说明里，不许出现在代码里。 */
const codeOnly = (name) => source(name)
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .split('\n')
  .filter((line) => !/^\s*\/\//.test(line))
  .join('\n')

/** 组件里 requestDelete 不 await 子调用，一轮宏任务即可把 mock 的 promise 排干。 */
const settle = () => new Promise((resolve) => { setTimeout(resolve, 0) })

describe('ArtifactList · 四态判定只有一条出口（进行 -> 失败 -> 空 -> 列表）', () => {
  it('加载中优先于一切：带着错误文案也说「在读」', () => {
    expect(listFace({ loading: true, errorText: '上一轮失败了', rowCount: 3 })).toBe('loading')
  })

  // 判据本体：失败必须先于「空」被否掉，否则读不到列表会被说成「你们还没有产物」。
  it('失败排在空之前', () => {
    expect(listFace({ loading: false, errorText: '读不到', rowCount: 0 })).toBe('error')
  })

  it('200 空数组才是空态', () => {
    expect(listFace({ loading: false, errorText: '', rowCount: 0 })).toBe('empty')
  })

  it('有行才走列表', () => {
    expect(listFace({ loading: false, errorText: '', rowCount: 1 })).toBe('list')
  })

  it('rowCount 缺失 / NaN 按空处理，不渲染半张列表', () => {
    expect(listFace({ loading: false, errorText: '', rowCount: undefined })).toBe('empty')
    expect(listFace({ loading: false, errorText: '', rowCount: NaN })).toBe('empty')
  })
})

describe('ArtifactList · 无权限与「坏了」各一句人话（正文不吃裸码）', () => {
  it('403：说没权限，且不给重试按钮', () => {
    const err = httpError(403, 'permission_denied')
    expect(isPermissionDenied(err)).toBe(true)
    const view = listErrorView({ denied: true, detail: errorDetail(err, '分析产物列表加载失败') })
    expect(view.title).toBe('没有权限查看分析产物')
    expect(view.retryable).toBe(false)
    expect(view.description).toContain('请联系管理员开通')
  })

  it('403 的裸码名不进正文（喂真 errorDetail，不喂假句子）', () => {
    const err = httpError(403, 'permission_denied')
    const view = listErrorView({ denied: true, detail: errorDetail(err, '分析产物列表加载失败') })
    expect([view.title, view.description].join(' ')).not.toMatch(SNAKE)
  })

  it('404：说没读到，并带上字典给的人话原因，允许重新加载', () => {
    const err = httpError(404, 'resource_not_found')
    expect(isPermissionDenied(err)).toBe(false)
    const detail = errorDetail(err, '分析产物列表加载失败')
    const view = listErrorView({ denied: false, detail })
    expect(view.title).toBe('分析产物没读到')
    expect(view.retryable).toBe(true)
    expect(view.description).toBe(detail)
    expect(view.description).not.toMatch(SNAKE)
  })

  it('字典没话可说时退回场景文案，而不是把 err.message 原样上屏', () => {
    const view = listErrorView({ denied: false, detail: '' })
    expect(view.description).toBe('分析产物列表加载失败，请稍后重试。')
  })

  it('打开失败同样分两张脸，且都不出现裸码', () => {
    const denied = openErrorView({ denied: true })
    const failed = openErrorView({ denied: false, detail: errorDetail(httpError(500, 'internal_error'), 'x') })
    expect(denied.title).toBe('没有权限打开这条产物')
    expect(denied.retryable).toBe(false)
    expect(failed.title).toBe('这条产物没能打开')
    expect(failed.retryable).toBe(true)
    for (const view of [denied, failed]) {
      expect([view.title, view.description].join(' ')).not.toMatch(SNAKE)
    }
  })

  // retryable 恒 false：失败卡上放一个直接重发 DELETE 的按钮，等于把两步确认压成一步。
  it('删除失败两张脸都不给重试，主语可换成数据文件', () => {
    const denied = deleteErrorView({ denied: true })
    const failed = deleteErrorView({ denied: false, detail: errorDetail(httpError(500, 'internal_error'), 'x') })
    const file = deleteErrorView({ denied: true, subject: '这个数据文件' })
    expect([denied.retryable, failed.retryable, file.retryable]).toEqual([false, false, false])
    expect(denied.title).toBe('没有权限删除这条产物')
    expect(failed.title).toBe('这条产物没能删除')
    expect(file.title).toBe('没有权限删除这个数据文件')
    for (const view of [denied, failed, file]) {
      expect([view.title, view.description].join(' ')).not.toMatch(SNAKE)
    }
  })
})

describe('ArtifactList · 后端行 -> 视图模型（snake_case 只在这一处出现）', () => {
  it('一行真响应映射成视图字段，时间与类型都是给人看的形状', () => {
    const item = mapArtifactRow(apiRow())
    expect(item).toEqual({
      artifactId: 'a1',
      filename: '销售额趋势.png',
      typeRaw: 'chart',
      typeLabel: '图表',
      contentUrl: '/api/v1/artifacts/a1/content',
      downloadUrl: '/api/v1/artifacts/a1/download',
      createdAt: '2026-09-16 03:12',
      expiryText: '有效期至 2026-09-30',
    })
  })

  it('空行与缺字段不炸：文件名给通用说法，时间与有效期给空串', () => {
    expect(mapArtifactRow(null).filename).toBe('未命名产物')
    expect(mapArtifactRow({}).artifactId).toBe('')
    expect(mapArtifactRow({ created_at: '' }).createdAt).toBe('')
    expect(mapArtifactRow({ expires_at: null }).expiryText).toBe('')
  })

  it('UTC isoformat 串只截到分，不做时区换算', () => {
    expect(formatArtifactTime('2026-09-16T03:12:44.123456+00:00')).toBe('2026-09-16 03:12')
    expect(formatArtifactTime('2026-09-16 03:12:44')).toBe('2026-09-16 03:12')
    expect(formatArtifactTime('')).toBe('')
    expect(formatArtifactTime(undefined)).toBe('')
  })

  it('有效期只给到日：时刻级的过期提醒没有可操作余地', () => {
    expect(artifactExpiryText('2026-09-30T23:59:59+00:00')).toBe('有效期至 2026-09-30')
    expect(artifactExpiryText('')).toBe('')
  })

  // 未知类型宁可说「分析产物」，也不把后端原串画上屏（同裸码纪律）。
  it('类型标签：已登记的给中文，未知的给通用说法，绝不回显原串', () => {
    expect(artifactTypeLabel('chart')).toBe('图表')
    expect(artifactTypeLabel('report')).toBe('报告')
    expect(artifactTypeLabel('CHART')).toBe('图表')
    expect(artifactTypeLabel('sales_leaderboard')).toBe('分析产物')
    expect(artifactTypeLabel('')).toBe('分析产物')
    expect(artifactTypeLabel(undefined)).toBe('分析产物')
    expect(artifactTypeLabel('sales_leaderboard')).not.toMatch(SNAKE)
  })

  it('取字节的地址：content_url 优先，缺了才退 download_url，两个都没有就是空串', () => {
    expect(openTargetUrl({ contentUrl: '/api/v1/artifacts/a1/content', downloadUrl: '/d' })).toBe('/api/v1/artifacts/a1/content')
    expect(openTargetUrl({ contentUrl: '', downloadUrl: '/api/v1/artifacts/a1/download' })).toBe('/api/v1/artifacts/a1/download')
    expect(openTargetUrl({})).toBe('')
    expect(openTargetUrl(null)).toBe('')
  })
})

/**
 * 下面这一整块跑的是组件自己的代码：setup() 拿回来的就是编译产物里的真绑定，
 * 网络层与取字节层是假的，但「什么时候换成哪张脸」全部由组件判定，测试只读结果。
 */
describe('ArtifactList · 进行 / 失败 / 空 / 有数据四张脸各来一次', () => {
  it('请求在路上就是 loading，落地才换脸', async () => {
    let vm = await mountBindings(ArtifactList)
    let pending = vm.loadArtifacts()
    expect(vm.loading.value).toBe(true)
    expect(vm.face.value).toBe('loading')
    await pending
    expect(vm.face.value).toBe('empty')
  })

  it('列表只有一条取数路径：GET /artifacts 带 limit / offset，页大小不越后端上限', async () => {
    let vm = await mountBindings(ArtifactList)
    await vm.loadArtifacts()
    expect(http.get).toHaveBeenCalledTimes(1)
    let [url, config] = http.get.mock.calls[0]
    expect(url).toBe('/artifacts')
    expect(config.params.limit).toBe(ARTIFACT_PAGE_SIZE)
    expect(config.params.offset).toBe(0)
    expect(ARTIFACT_PAGE_SIZE).toBeGreaterThan(0)
    // 后端 app/api/v1/artifacts.py 的 MAX_LIST_LIMIT = 100：超了会被钳，别写个会被悄悄改掉的数
    expect(ARTIFACT_PAGE_SIZE).toBeLessThanOrEqual(100)
  })

  it('200 空列表 => 空态：没有错误，也没有「没权限」', async () => {
    let vm = await mountBindings(ArtifactList)
    await vm.loadArtifacts()
    expect(vm.face.value).toBe('empty')
    expect(vm.loadError.value).toBe('')
    expect(vm.loadDenied.value).toBe(false)
    expect(vm.listView.value.title).not.toBe('没有权限查看分析产物')
  })

  it('403 => 无权限态：与上一条唯一的变化是权限，脸也完全不同', async () => {
    http.get.mockRejectedValue(httpError(403, 'permission_denied'))
    let vm = await mountBindings(ArtifactList)
    await vm.loadArtifacts()
    expect(vm.face.value).toBe('error')
    expect(vm.loadDenied.value).toBe(true)
    expect(vm.listView.value.title).toBe('没有权限查看分析产物')
    expect(vm.listView.value.retryable).toBe(false)
    expect([vm.listView.value.title, vm.listView.value.description].join(' ')).not.toMatch(SNAKE)
  })

  it('刷新失败不许留着半截旧列表冒充结果', async () => {
    http.get.mockResolvedValue({ data: apiPage([apiRow()]) })
    let vm = await mountBindings(ArtifactList)
    await vm.loadArtifacts()
    expect(vm.rows.value).toHaveLength(1)
    http.get.mockRejectedValue(httpError(500, 'internal_error'))
    vm.reload()
    await settle()
    expect(vm.rows.value).toHaveLength(0)
    expect(vm.face.value).toBe('error')
    expect(vm.listView.value.retryable).toBe(true)
    expect(vm.listView.value.description).toContain('系统内部出现异常')
  })

  it('有数据 => 列表：文件名 / 类型 / 时间都来自后端行，总数与 has_more 各管各的', async () => {
    http.get.mockResolvedValue({
      data: apiPage([apiRow(), apiRow({ artifact_id: 'a2', artifact_type: 'report', filename: '月度经营报告.md' })], { total: 7, has_more: true }),
    })
    let vm = await mountBindings(ArtifactList)
    await vm.loadArtifacts()
    expect(vm.face.value).toBe('list')
    expect(vm.rows.value.map(row => row.filename)).toEqual(['销售额趋势.png', '月度经营报告.md'])
    expect(vm.rows.value.map(row => row.typeLabel)).toEqual(['图表', '报告'])
    expect(vm.rows.value[0].createdAt).toBe('2026-09-16 03:12')
    expect(vm.total.value).toBe(7)
    expect(vm.hasMore.value).toBe(true)
    expect(vm.offset.value).toBe(2)
  })

  it('读取更多用上一页落地的游标，且是追加不是替换', async () => {
    let page = apiPage([apiRow()], { total: 2, has_more: true })
    http.get.mockImplementation(() => Promise.resolve({ data: page }))
    let vm = await mountBindings(ArtifactList)
    await vm.loadArtifacts()
    page = apiPage([apiRow({ artifact_id: 'a9', filename: '第二页的图.png' })], { total: 2, has_more: false })
    await vm.loadArtifacts({ append: true })
    expect(http.get.mock.calls[1][1].params.offset).toBe(1)
    expect(vm.rows.value.map(row => row.artifactId)).toEqual(['a1', 'a9'])
    expect(vm.hasMore.value).toBe(false)
    expect(vm.offset.value).toBe(2)
  })

  it('下一页失败只说「后面的没读到」，已经拿到的行一条不丢', async () => {
    let calls = 0
    http.get.mockImplementation(() => {
      calls += 1
      if (calls === 1) return Promise.resolve({ data: apiPage([apiRow()], { total: 2, has_more: true }) })
      return Promise.reject(httpError(500, 'internal_error'))
    })
    let vm = await mountBindings(ArtifactList)
    await vm.loadArtifacts()
    await vm.loadArtifacts({ append: true })
    expect(vm.face.value).toBe('list')
    expect(vm.rows.value).toHaveLength(1)
    expect(vm.loadError.value).toBe('')
    expect(vm.moreError.value).not.toBe('')
    expect(vm.moreError.value).not.toMatch(SNAKE)
  })

  it('响应里没有 artifacts 数组也不炸，按空列表处理', async () => {
    http.get.mockResolvedValue({ data: { total: 0 } })
    let vm = await mountBindings(ArtifactList)
    await vm.loadArtifacts()
    expect(vm.rows.value).toEqual([])
    expect(vm.face.value).toBe('empty')
  })
})

/** 一行数据的现成现场：走完真列表加载，再把这一行交给测试。 */
async function vmWithRow(overrides) {
  http.get.mockResolvedValue({ data: apiPage([apiRow(overrides)]) })
  const vm = await mountBindings(ArtifactList)
  await vm.loadArtifacts()
  return vm
}

function blobHandle(overrides) {
  return Object.assign({ objectUrl: 'blob:preview-1', mediaType: 'image/png', size: 128, revoke() {} }, overrides)
}

describe('ArtifactList · 打开只从带 Bearer 的通道取字节（不许直链）', () => {
  it('图片产物：调 fetchArtifactBlob(content_url)，屏上绑的只有 blob: 地址', async () => {
    const vm = await vmWithRow()
    await vm.openArtifact(vm.rows.value[0])
    expect(fetchArtifactBlob).toHaveBeenCalledTimes(1)
    expect(fetchArtifactBlob).toHaveBeenCalledWith('/api/v1/artifacts/a1/content')
    expect(vm.previewId.value).toBe('a1')
    expect(vm.previewUrl.value).toBe('blob:preview-1')
    expect(vm.previewUrl.value).not.toContain('/api/v1/artifacts/')
    expect(openButtonLabel({ busy: false, previewing: true })).toBe('收起')
  })

  it('再点一次是收起，并且把 blob 地址释放掉（不给演示留一地内存）', async () => {
    let revoked = 0
    fetchArtifactBlob.mockResolvedValue(blobHandle({ revoke() { revoked += 1 } }))
    const vm = await vmWithRow()
    await vm.openArtifact(vm.rows.value[0])
    await vm.openArtifact(vm.rows.value[0])
    expect(revoked).toBe(1)
    expect(vm.previewId.value).toBe('')
    expect(vm.previewUrl.value).toBe('')
    expect(fetchArtifactBlob).toHaveBeenCalledTimes(1)
  })

  it('换一条产物时先释放上一条，屏幕上同时只有一个 blob', async () => {
    const urls = ['blob:one', 'blob:two']
    let revoked = []
    fetchArtifactBlob.mockImplementation(() => Promise.resolve(
      blobHandle({ objectUrl: urls.shift(), revoke() { revoked.push(1) } }),
    ))
    http.get.mockResolvedValue({ data: apiPage([apiRow({ artifact_id: 'a1' }), apiRow({ artifact_id: 'a2' })]) })
    const vm = await mountBindings(ArtifactList)
    await vm.loadArtifacts()
    await vm.openArtifact(vm.rows.value[0])
    await vm.openArtifact(vm.rows.value[1])
    expect(revoked).toHaveLength(1)
    expect(vm.previewId.value).toBe('a2')
    expect(vm.previewUrl.value).toBe('blob:two')
  })

  it('非图片产物走另存：落盘地址仍是 blob:，content_url 缺失才用 download_url', async () => {
    const saved = []
    globalThis.document = {
      createElement() {
        return {
          href: '',
          download: '',
          click() { saved.push({ href: this.href, download: this.download }) },
        }
      },
    }
    try {
      fetchArtifactBlob.mockResolvedValue(blobHandle({ objectUrl: 'blob:preview-2', mediaType: 'application/pdf' }))
      const vm = await vmWithRow({ artifact_type: 'report', filename: '月度经营报告.pdf', content_url: '' })
      await vm.openArtifact(vm.rows.value[0])
      expect(fetchArtifactBlob).toHaveBeenCalledWith('/api/v1/artifacts/a1/download')
      expect(saved).toEqual([{ href: 'blob:preview-2', download: '月度经营报告.pdf' }])
      expect(vm.previewId.value).toBe('')
    } finally {
      delete globalThis.document
    }
  })

  it('两个地址都没有：给「没有可打开的地址」并且不发任何裸请求', async () => {
    const vm = await vmWithRow({ content_url: '', download_url: '' })
    await vm.openArtifact(vm.rows.value[0])
    expect(fetchArtifactBlob).not.toHaveBeenCalled()
    expect(vm.actionError.value.title).toBe('这条产物没能打开')
    expect(vm.actionError.value.description).toBe('这条产物没有可打开的地址。')
    expect(vm.actionError.value.retryable).toBe(false)
  })

  it('取字节 403：无权限那张脸，不给重试', async () => {
    fetchArtifactBlob.mockRejectedValue(
      Object.assign(new Error('当前账号没有这项权限，请联系管理员开通。'), { status: 403, code: 'permission_denied' }),
    )
    const vm = await vmWithRow()
    await vm.openArtifact(vm.rows.value[0])
    expect(vm.actionError.value.title).toBe('没有权限打开这条产物')
    expect(vm.actionError.value.retryable).toBe(false)
    expect([vm.actionError.value.title, vm.actionError.value.description].join(' ')).not.toMatch(SNAKE)
    expect(vm.previewUrl.value).toBe('')
  })

  it('取字节超时：说坏了并允许再取一次，重试打的是同一条真通道', async () => {
    fetchArtifactBlob.mockRejectedValueOnce(
      Object.assign(new Error('连不上服务，请确认网络或稍后重试。'), { status: 0, code: 'network_error' }),
    )
    const vm = await vmWithRow()
    await vm.openArtifact(vm.rows.value[0])
    expect(vm.actionError.value.title).toBe('这条产物没能打开')
    expect(vm.actionError.value.retryable).toBe(true)
    vm.retryAction()
    await settle()
    expect(fetchArtifactBlob).toHaveBeenCalledTimes(2)
    expect(vm.actionError.value).toBe(null)
  })

  it('分类器判定「重试也没用」的失败（404 内容已被移除）不再配重试按钮', async () => {
    // retryable 由 lib/artifacts.js 的分类器带回来，组件只转述不自行发明：这里改一个字就能漂移。
    fetchArtifactBlob.mockRejectedValue(
      Object.assign(new Error('要找的内容不存在或已被移除。'), { status: 404, code: 'http_404', retryable: false }),
    )
    const vm = await vmWithRow()
    await vm.openArtifact(vm.rows.value[0])
    expect(vm.actionError.value.description).toBe('要找的内容不存在或已被移除。')
    expect(vm.actionError.value.retryable).toBe(false)
    expect([vm.actionError.value.title, vm.actionError.value.description].join(' ')).not.toMatch(SNAKE)
  })

  it('请求被取消是静默的：不该弹一张失败卡', async () => {
    fetchArtifactBlob.mockRejectedValue(Object.assign(new Error('取图已取消'), { code: 'aborted' }))
    const vm = await vmWithRow()
    await vm.openArtifact(vm.rows.value[0])
    expect(vm.actionError.value).toBe(null)
    expect(vm.previewId.value).toBe('')
  })
})


describe('ArtifactList · 删除是两步内联确认（不用 window.confirm）', () => {
  it('状态机：空目标 idle，第一次 arm，同目标第二次 execute，换目标只 re-arm', () => {
    expect(advanceDelete('', '')).toBe('idle')
    expect(advanceDelete('', 'a1')).toBe('arm')
    expect(advanceDelete('a1', 'a1')).toBe('execute')
    expect(advanceDelete('a2', 'a1')).toBe('arm')
    expect(isPendingDelete('a1', 'a1')).toBe(true)
    expect(isPendingDelete('a1', 'a2')).toBe(false)
    expect(isPendingDelete('a1', '')).toBe(false)
  })

  it('按钮三档文案：删除 / 确认删除？ / 删除中…，主语可换', () => {
    expect(deleteButtonLabel({ pending: false, busy: false, label: '删除' })).toBe('删除')
    expect(deleteButtonLabel({ pending: true, busy: false, label: '删除' })).toBe('确认删除？')
    expect(deleteButtonLabel({ pending: true, busy: true, label: '删除' })).toBe('删除中…')
    expect(deleteButtonLabel({ pending: false, busy: false, label: '删除所选数据文件' })).toBe('删除所选数据文件')
  })

  it('第一次点击只把按钮改成确认文案，一个 DELETE 都不发', async () => {
    const vm = await vmWithRow()
    vm.requestDelete(vm.rows.value[0])
    expect(http.delete).not.toHaveBeenCalled()
    expect(vm.pendingDelete.value).toBe('a1')
    expect(deleteButtonLabel({ pending: isPendingDelete(vm.pendingDelete.value, 'a1'), busy: false, label: '删除' })).toBe('确认删除？')
  })

  it('同一行第二次点击才真删，成功后这一行立刻消失', async () => {
    const vm = await vmWithRow()
    vm.requestDelete(vm.rows.value[0])
    vm.requestDelete(vm.rows.value[0])
    await settle()
    expect(http.delete).toHaveBeenCalledTimes(1)
    expect(http.delete).toHaveBeenCalledWith('/artifacts/a1')
    expect(vm.rows.value).toHaveLength(0)
    expect(vm.face.value).toBe('empty')
    expect(vm.deletingId.value).toBe('')
    expect(vm.actionError.value).toBe(null)
  })

  // 判据：一次错位点击不能删掉没确认过的那一行。
  it('先点 A 再点 B：只把待确认挪到 B，A 与 B 都还在', async () => {
    http.get.mockResolvedValue({ data: apiPage([apiRow({ artifact_id: 'a1' }), apiRow({ artifact_id: 'a2' })], { total: 2 }) })
    const vm = await mountBindings(ArtifactList)
    await vm.loadArtifacts()
    vm.requestDelete(vm.rows.value[0])
    vm.requestDelete(vm.rows.value[1])
    expect(http.delete).not.toHaveBeenCalled()
    expect(vm.pendingDelete.value).toBe('a2')
    expect(vm.rows.value).toHaveLength(2)
    vm.requestDelete(vm.rows.value[1])
    await settle()
    expect(http.delete).toHaveBeenCalledTimes(1)
    expect(http.delete).toHaveBeenCalledWith('/artifacts/a2')
    expect(vm.rows.value.map(row => row.artifactId)).toEqual(['a1'])
  })

  it('取消只清待确认；取消后再点仍然只是第一次点击', async () => {
    const vm = await vmWithRow()
    vm.requestDelete(vm.rows.value[0])
    vm.cancelDelete()
    expect(vm.pendingDelete.value).toBe('')
    vm.requestDelete(vm.rows.value[0])
    expect(http.delete).not.toHaveBeenCalled()
    expect(vm.pendingDelete.value).toBe('a1')
  })

  it('id 里的路径穿越与查询字符一律百分号编码，不拼坏请求路径', async () => {
    const id = '../../etc/passwd?x=1'
    const vm = await vmWithRow({ artifact_id: id })
    vm.requestDelete(vm.rows.value[0])
    vm.requestDelete(vm.rows.value[0])
    await settle()
    const url = http.delete.mock.calls[0][0]
    expect(url).toBe('/artifacts/' + encodeURIComponent(id))
    // 判据不是「点号消失」（encodeURIComponent 保留 . 且无所谓），而是 id 里再没有能改路径形状的字符
    expect(url.split('/')).toHaveLength(3)
    expect(url).not.toContain('?')
    expect(url).not.toContain('=')
    expect(url).toContain('%2F')
    expect(decodeURIComponent(url.slice('/artifacts/'.length))).toBe(id)
  })

  // 后端 newest-first：删掉一行会让后面每行下标前移，游标不跟着退就会整行漏掉一条。
  it('删除成功后总数与游标各退一格', async () => {
    http.get.mockResolvedValue({ data: apiPage([apiRow({ artifact_id: 'a1' }), apiRow({ artifact_id: 'a2' })], { total: 5, has_more: true }) })
    const vm = await mountBindings(ArtifactList)
    await vm.loadArtifacts()
    expect(vm.total.value).toBe(5)
    expect(vm.offset.value).toBe(2)
    vm.requestDelete(vm.rows.value[0])
    vm.requestDelete(vm.rows.value[0])
    await settle()
    expect(vm.total.value).toBe(4)
    expect(vm.offset.value).toBe(1)
    expect(vm.rows.value.map(row => row.artifactId)).toEqual(['a2'])
  })

  it('403 删除失败：无权限那张脸，行还在，且不给重试', async () => {
    http.delete.mockRejectedValue(httpError(403, 'permission_denied'))
    const vm = await vmWithRow()
    vm.requestDelete(vm.rows.value[0])
    vm.requestDelete(vm.rows.value[0])
    await settle()
    expect(vm.rows.value).toHaveLength(1)
    expect(vm.face.value).toBe('list')
    expect(vm.actionError.value.title).toBe('没有权限删除这条产物')
    expect(vm.actionError.value.retryable).toBe(false)
    expect([vm.actionError.value.title, vm.actionError.value.description].join(' ')).not.toMatch(SNAKE)
  })

  it('500 删除失败：说清原因也不给重试（失败卡上的重试等于把两步确认压成一步）', async () => {
    http.delete.mockRejectedValue(httpError(500, 'internal_error'))
    const vm = await vmWithRow()
    vm.requestDelete(vm.rows.value[0])
    vm.requestDelete(vm.rows.value[0])
    await settle()
    expect(vm.actionError.value.title).toBe('这条产物没能删除')
    expect(vm.actionError.value.retryable).toBe(false)
    expect(vm.actionError.value.description).toContain('系统内部出现异常')
    expect(vm.rows.value).toHaveLength(1)
  })

  it('删除进行中不受理第二次点击，不发重复 DELETE', async () => {
    let release
    http.delete.mockImplementation(() => new Promise((resolve) => { release = resolve }))
    const vm = await vmWithRow()
    vm.requestDelete(vm.rows.value[0])
    vm.requestDelete(vm.rows.value[0])
    vm.requestDelete(vm.rows.value[0])
    expect(http.delete).toHaveBeenCalledTimes(1)
    release({ data: { status: 'ok' } })
    await settle()
    expect(vm.deletingId.value).toBe('')
    expect(vm.rows.value).toHaveLength(0)
  })

  it('删掉正在预览的那条时，blob 地址一起释放', async () => {
    let revoked = 0
    fetchArtifactBlob.mockResolvedValue(blobHandle({ revoke() { revoked += 1 } }))
    const vm = await vmWithRow()
    await vm.openArtifact(vm.rows.value[0])
    vm.requestDelete(vm.rows.value[0])
    vm.requestDelete(vm.rows.value[0])
    await settle()
    expect(revoked).toBe(1)
    expect(vm.previewId.value).toBe('')
    expect(vm.previewUrl.value).toBe('')
  })
})


/** 数据文件列表 + 预览两条读路径；删掉之后列表会再读一次，所以 files 是可变的。 */
function mockFileList(state) {
  http.get.mockImplementation((url) => {
    if (url === '/data-files') return Promise.resolve({ data: { files: state.files } })
    const name = decodeURIComponent(url.split('/')[2])
    return Promise.resolve({
      data: {
        filename: name,
        profile: { columns: [{ name: '月份', missing_count: 0 }] },
        columns: ['月份'],
        rows: [{ 月份: '2026-01' }],
        truncated: false,
      },
    })
  })
}

function fileEntry(filename) {
  return { filename, extension: filename.endsWith('.csv') ? '.csv' : '.xlsx', size_label: '12 KB', modified_at: '2026-09-16T03:12:44' }
}

async function dataPanelWith(filename) {
  const state = { files: filename ? [fileEntry(filename)] : [] }
  mockFileList(state)
  const dp = await mountBindings(DataPanel)
  await dp.loadDataFiles()
  return { dp, state }
}

describe('DataPanel · 删除所选数据文件（W2-2：与产物侧共用同一个两步状态机）', () => {
  it('只对当前选中的那一个发 DELETE，走的是两步确认', async () => {
    const { dp } = await dataPanelWith('sales.csv')
    expect(dp.dataFile.value).toBe('sales.csv')
    dp.requestFileDelete()
    expect(http.delete).not.toHaveBeenCalled()
    expect(deleteButtonLabel({
      pending: isPendingDelete(dp.pendingFileDelete.value, dp.dataFile.value),
      busy: false,
      label: '删除所选数据文件',
    })).toBe('确认删除？')
    dp.requestFileDelete()
    await settle()
    expect(http.delete).toHaveBeenCalledTimes(1)
    expect(http.delete).toHaveBeenCalledWith('/data-files/sales.csv')
  })

  it('删成功之后不留残影：画像与表清空，列表重载', async () => {
    const { dp, state } = await dataPanelWith('sales.csv')
    expect(dp.profile.value).toBeTruthy()
    expect(dp.tableRows.value).toHaveLength(1)
    state.files = []
    dp.requestFileDelete()
    dp.requestFileDelete()
    await settle()
    expect(dp.profile.value).toBe(null)
    expect(dp.tableColumns.value).toEqual([])
    expect(dp.tableRows.value).toEqual([])
    expect(dp.tableTruncated.value).toBe(false)
    expect(dp.dataFile.value).toBe('')
    expect(dp.pendingFileDelete.value).toBe('')
    expect(http.get.mock.calls.filter(call => call[0] === '/data-files')).toHaveLength(2)
    expect(dp.dataFiles.value).toEqual([])
    expect(dp.fileDeleteError.value).toBe('')
  })

  it('文件名里的空格 / 中文 / 括号一律百分号编码', async () => {
    const name = '销售额 2026(副本).xlsx'
    const { dp } = await dataPanelWith(name)
    expect(dp.dataFile.value).toBe(name)
    dp.requestFileDelete()
    dp.requestFileDelete()
    await settle()
    const url = http.delete.mock.calls[0][0]
    expect(url).toBe('/data-files/' + encodeURIComponent(name))
    expect(url.split('/')).toHaveLength(3)
    expect(decodeURIComponent(url.slice('/data-files/'.length))).toBe(name)
  })

  it('没选中文件时按钮不受理任何请求（idle 分支）', async () => {
    const { dp } = await dataPanelWith(null)
    expect(dp.dataFile.value).toBe('')
    dp.requestFileDelete()
    dp.requestFileDelete()
    await settle()
    expect(http.delete).not.toHaveBeenCalled()
    expect(isPendingDelete(dp.pendingFileDelete.value, dp.dataFile.value)).toBe(false)
  })

  it('取消只撤待确认，不删任何东西', async () => {
    const { dp } = await dataPanelWith('sales.csv')
    dp.requestFileDelete()
    dp.cancelFileDelete()
    expect(dp.pendingFileDelete.value).toBe('')
    dp.requestFileDelete()
    expect(http.delete).not.toHaveBeenCalled()
  })

  it('403：别人的数据集是「没权限」，文件与预览一条都不许被偷偷清掉', async () => {
    const { dp } = await dataPanelWith('sales.csv')
    http.delete.mockRejectedValue(httpError(403, 'permission_denied'))
    dp.requestFileDelete()
    dp.requestFileDelete()
    await settle()
    expect(dp.fileDeleteDenied.value).toBe(true)
    expect(dp.fileDeleteView.value.title).toBe('没有权限删除这个数据文件')
    expect(dp.fileDeleteView.value.retryable).toBe(false)
    expect([dp.fileDeleteView.value.title, dp.fileDeleteView.value.description].join(' ')).not.toMatch(SNAKE)
    expect(dp.dataFile.value).toBe('sales.csv')
    expect(dp.profile.value).toBeTruthy()
    expect(dp.tableRows.value).toHaveLength(1)
    // 失败之后仍要重新走两步：待确认已清空，不会出现「再点一下顺手删掉」
    expect(dp.pendingFileDelete.value).toBe('')
  })

  it('500：说清没删成，也不给重试按钮，列表不重载', async () => {
    const { dp } = await dataPanelWith('sales.csv')
    http.delete.mockRejectedValue(httpError(500, 'internal_error'))
    dp.requestFileDelete()
    dp.requestFileDelete()
    await settle()
    expect(dp.fileDeleteDenied.value).toBe(false)
    expect(dp.fileDeleteView.value.title).toBe('这个数据文件没能删除')
    expect(dp.fileDeleteView.value.description).toContain('系统内部出现异常')
    expect(dp.fileDeleteView.value.retryable).toBe(false)
    expect(dp.profile.value).toBeTruthy()
    expect(http.get.mock.calls.filter(call => call[0] === '/data-files')).toHaveLength(1)
  })

  it('删除进行中忽略第二次点击', async () => {
    let release
    const { dp } = await dataPanelWith('sales.csv')
    http.delete.mockImplementation(() => new Promise((resolve) => { release = resolve }))
    dp.requestFileDelete()
    dp.requestFileDelete()
    dp.requestFileDelete()
    expect(http.delete).toHaveBeenCalledTimes(1)
    release({ data: { status: 'ok' } })
    await settle()
    expect(dp.deletingFile.value).toBe(false)
  })

  it('SSR 首屏同时给出「数据文件」与「分析产物」两块空态，两块都不是错误态', async () => {
    const html = await render(DataPanel)
    expect(html.match(/data-testid="ui-empty-state"/g)).toHaveLength(2)
    expect(html).toContain('暂无数据文件')
    expect(html).toContain('暂无分析产物')
    expect(html).not.toContain('data-testid="ui-error-state"')
  })
})

describe('四张脸的真产物：role 与重试按钮由原语长出来', () => {
  it('SSR 首屏（还没发过请求）是空态，不是错误态也不是进行态', async () => {
    const html = await render(ArtifactList)
    expect(html).toContain('data-testid="artifact-list"')
    expect(html).toContain('暂无分析产物')
    expect(html).toContain('data-testid="ui-empty-state"')
    expect(html).not.toContain('data-testid="ui-error-state"')
    expect(html).not.toContain('data-testid="ui-loading-state"')
  })

  it('空态 role=status：没有产物不是失败，不该打断读屏', async () => {
    const html = await renderToString(h(UiEmptyState, { title: '暂无分析产物', dense: true }))
    expect(html).toMatch(/<div class="ui-empty-state[^"]*" role="status"/)
    expect(html).not.toContain('role="alert"')
  })

  it('无权限那张卡：role=alert 且不配重试按钮', async () => {
    const view = listErrorView({ denied: true, detail: errorDetail(httpError(403, 'permission_denied'), '分析产物列表加载失败') })
    const html = await renderToString(h(UiErrorState, { title: view.title, description: view.description, retryable: view.retryable, dense: true }))
    expect(html).toContain('role="alert"')
    expect(html).toContain('没有权限查看分析产物')
    expect(html).not.toContain('data-testid="ui-error-retry"')
  })

  it('普通失败那张卡：给「重新加载」', async () => {
    const view = listErrorView({ denied: false, detail: errorDetail(httpError(500, 'internal_error'), 'x') })
    const html = await renderToString(h(UiErrorState, { title: view.title, description: view.description, retryable: view.retryable, retryText: '重新加载', dense: true }))
    expect(html).toContain('data-testid="ui-error-retry"')
    expect(html).toContain('重新加载')
  })

  it('进行态那张脸：role=status + aria-busy，文案只说在做什么', async () => {
    const html = await renderToString(h(UiLoadingState, { label: '正在读取分析产物...', dense: true }))
    expect(html).toMatch(/<div class="ui-loading-state[^"]*" role="status" aria-busy="true"/)
    expect(html).toContain('正在读取分析产物...')
  })
})


describe('ArtifactList · 源码形状：一次渲染看不到的三条判据', () => {
  const s = source('ArtifactList.vue')
  const code = codeOnly('ArtifactList.vue')
  // 模板里还有嵌套 <template v-else> / <template v-if>，尾界只能从最后一个 </template> 量起
  const tpl = s.slice(s.indexOf('<template>'), s.lastIndexOf('</template>'))

  // 顺序即语义：进行 -> 失败 -> 空 -> 列表，写反就等于把「读不到」说成「没有」。
  it('模板里四张脸按 v-if / v-else-if 串成一条互斥链', () => {
    const at = (needle) => {
      const i = tpl.indexOf(needle)
      expect(i, needle).toBeGreaterThan(-1)
      return i
    }
    const loading = at(`<UiLoadingState v-if="face === 'loading'"`)
    const error = at(`v-else-if="face === 'error'"`)
    const empty = at(`v-else-if="face === 'empty'"`)
    const list = at('data-testid="artifact-items"')
    expect(loading).toBeLessThan(error)
    expect(error).toBeLessThan(empty)
    expect(empty).toBeLessThan(list)
    expect(tpl.match(/<UiLoadingState/g)).toHaveLength(1)
    expect(tpl.match(/<UiEmptyState/g)).toHaveLength(1)
  })

  // 判据 ②：产物地址只从带 Bearer 的通道走，屏上出现的地址只有 blob:。
  it('产物地址不进 img / href / window.open，只有 blob: 地址上屏', () => {
    expect(tpl).toContain('<img :src="previewUrl"')
    expect(tpl).not.toContain('contentUrl')
    expect(tpl).not.toContain('downloadUrl')
    expect(code).toContain('fetchArtifactBlob(target)')
    expect(code).not.toContain('window.open')
    expect(code).not.toMatch(/<img[^>]*:src="item/)
    expect(code).not.toMatch(/:href="[^"]*[Uu]rl/)
  })

  it('删除请求的 URL 由 encodeURIComponent 生成，且没有第二套手搓确认框', () => {
    expect(code).toContain("http.delete('/artifacts/' + encodeURIComponent(item.artifactId))")
    expect(code).not.toMatch(/[^a-zA-Z]confirm\s*\(/)
    expect(code).not.toContain('window.confirm')
  })

  it('两步确认在模板里只有一处出口：待确认那一行才换文案并露出取消', () => {
    expect(tpl).toContain(':label="deleteButtonLabel({ pending: isPendingDelete(pendingDelete, item.artifactId)')
    expect(tpl).toContain('v-if="isPendingDelete(pendingDelete, item.artifactId)"')
    expect(tpl).toContain('data-testid="artifact-delete-cancel"')
    expect(tpl.match(/data-testid="artifact-delete"/g)).toHaveLength(1)
  })

  it('未知类型不回显原串：屏上只有中文标签，原始值只进 data 属性', () => {
    expect(tpl).toContain('{{ item.typeLabel }}')
    expect(tpl).toContain(':data-artifact-type="item.typeRaw"')
    expect(tpl).not.toContain('artifact_type')
    expect(tpl).not.toContain('artifact_id')
  })

  it('正文不出现裸码名：模板里没有 snake_case 字面量', () => {
    const mustaches = tpl.match(/\{\{[^}]*\}\}/g) || []
    expect(mustaches.length).toBeGreaterThan(0)
    for (const slot of mustaches) {
      expect(slot).not.toMatch(SNAKE)
    }
  })

  it('分页参数只有一个来源，页大小不写第二份', () => {
    expect(code).toMatch(/params: \{ limit: ARTIFACT_PAGE_SIZE, offset: requestOffset/)
    expect(code.match(/ARTIFACT_PAGE_SIZE/g)).toHaveLength(2)
  })

  it('样式零裸色值：只借 var(--*) 令牌与 theme.css 既有类', () => {
    const styleBlock = s.slice(s.indexOf('<style scoped>'), s.indexOf('</style>'))
    expect(styleBlock).not.toMatch(/#[0-9a-fA-F]{3,8}/)
    expect(styleBlock).not.toMatch(/rgba?\(/)
    expect(styleBlock).toContain('var(--danger)')
    expect(tpl).toContain('class="section-head"')
    expect(tpl).toContain('class="chip"')
  })

  it('按钮一律用 UiButton 原语，不手搓裸 button', () => {
    expect(tpl).not.toMatch(/<button/)
    expect(tpl.match(/<UiButton/g).length).toBeGreaterThanOrEqual(4)
  })
})

describe('DataPanel · 挂载位置与删除入口（源码形状）', () => {
  const s = source('DataPanel.vue')
  const code = codeOnly('DataPanel.vue')

  it('分析产物区挂在「数据文件」那一整段之后，且不在段内', () => {
    const filesSection = s.indexOf('<section class="data-files-section">')
    const filesEnd = s.indexOf('</section>', filesSection)
    const mounted = s.indexOf('<ArtifactList />')
    expect(filesSection).toBeGreaterThan(-1)
    expect(mounted).toBeGreaterThan(filesEnd)
    expect(s.slice(mounted, s.indexOf('<UiErrorState', mounted))).not.toContain('</section>')
  })

  it('两处删除共用同一份两步状态机，DataPanel 不自己再写一遍', () => {
    expect(s).toContain("from './ArtifactList.vue'")
    expect(s).toContain('import ArtifactList, { advanceDelete, deleteButtonLabel, deleteErrorView, isPendingDelete }')
    expect(code).toContain('advanceDelete(pendingFileDelete.value, dataFile.value)')
    expect(code).not.toMatch(/function advanceDelete/)
    expect(code).not.toMatch(/pendingFileDelete\.value\s*[=!]==?/)
    expect(s).not.toContain('确认删除')
  })

  it('删除只打当前选中的那一个文件，URL 走 encodeURIComponent', () => {
    expect(code).toContain("http.delete('/data-files/' + encodeURIComponent(filename))")
    expect(code).toContain('if (!filename || deletingFile.value) return')
    expect(code).toContain('if (!dataFile.value || deletingFile.value) return')
  })

  it('删除入口只在选中文件（有画像）时出现，且不出现裸 confirm(', () => {
    const at = s.indexOf('data-testid="data-file-delete"')
    expect(at).toBeGreaterThan(-1)
    expect(s.indexOf('<div v-if="profile"')).toBeLessThan(at)
    expect(code).not.toMatch(/[^a-zA-Z]confirm\s*\(/)
  })

  it('删除失败那张卡走 UiErrorState，标题吃 fileDeleteView，且不配重试', () => {
    const at = s.indexOf('v-if="fileDeleteError"')
    expect(at).toBeGreaterThan(-1)
    const block = s.slice(s.lastIndexOf('<UiErrorState', at), s.indexOf('/>', at))
    expect(block).toContain(':title="fileDeleteView.title"')
    expect(block).toContain(':description="fileDeleteView.description"')
    expect(block).toContain(':retryable="false"')
    expect(block).toContain('data-testid="data-file-delete-error"')
  })

  it('新增的删除样式只借语义令牌，一个裸色值都不写', () => {
    const ruleStart = s.indexOf('.data-action-btn--danger {')
    const rule = s.slice(ruleStart, s.indexOf('.col-missing.ok', ruleStart))
    expect(rule.length).toBeGreaterThan(0)
    expect(rule).not.toMatch(/#[0-9a-fA-F]{3,8}/)
    expect(rule).not.toMatch(/rgba?\(/)
    expect(rule).toContain('var(--danger)')
    expect(rule).toContain('var(--border-2)')
  })

  it('文件列表原有的三张脸没被这次改动挪位', () => {
    const loadingAt = s.indexOf('<UiLoadingState v-if="filesLoading"')
    const errorAt = s.indexOf('v-else-if="filesError"')
    const emptyAt = s.indexOf('v-else-if="!dataFiles.length"')
    expect(loadingAt).toBeGreaterThan(-1)
    expect(loadingAt).toBeLessThan(errorAt)
    expect(errorAt).toBeLessThan(emptyAt)
  })
})
