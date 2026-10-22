/**
 * R169 · V1 前端主链路验收矩阵 —— 数据与图表那两行（选文件 → 预览 → 统计 / 出图 → 下载）
 *
 * 既存 659 枚在这两行的落点（逐枚点过名，见回执矩阵）：
 *   文件列表三张脸    = components/__tests__/panel-states.test.js · DataPanel 那一组（7 枚，SSR + 源码形状）
 *   预览 403 不画空态  = 同上 · 「预览失败也不许画成空态」（它自己写明钉的是源码文本）
 *   两步删除          = components/__tests__/artifact-list.test.js · 「DataPanel · 删除所选数据文件」9 枚
 *                      +「DataPanel · 挂载位置与删除入口」7 枚（前一组跑真 setup，后一组钉源码）
 *   产物侧出图与另存   = 同上 · ArtifactList「打开只从带 Bearer 的通道取字节」那一组（跑真 setup）
 *   图表卡三张脸的顺序 = panel-states.test.js · ChartViewer 那一组（3 枚：顺序 + dense 真产物 + 字号等值）
 *   取消不画失败卡     = lib/artifacts.test.js 那一枚只钉到「源码里还留着 code 等于 aborted 这行」的文本
 * 没盖到的：选中一个文件之后**真发生了什么**（打哪条 URL、画像/表/截断标记落到哪、数字取自哪一格）、
 * 预览失败两张脸的**真产物**、以及对话内那张图表卡（ChartViewer）的出图 / 空态 / 失败 / 重试 /
 * 取消 / 换一张 / 下载链接。这几格本文件用真 setup 跑真代码补上。
 *
 * 三条腿同仓库既有口径：① 真逻辑（跑组件自己的 setup，网络层与取字节层换成进程内假实现）；
 * ② 真产物（能渲染出来的那一支交给 renderToString）；③ 源码形状（一次渲染看不到的接线钉文本）。
 * 🔴 一条都不置灰、不挂待办、不放宽任何既存断言：补不了的写在回执里，不留在测试里。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, reactive } from 'vue'
import { readFileSync } from 'node:fs'
import { renderToString } from '@vue/server-renderer'

// 只换网络层与取字节层：errorDetail / isPermissionDenied / isArtifactRequest 保持真身。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }
})
vi.mock('../../lib/artifacts', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, fetchArtifactBlob: vi.fn() }
})

import { http } from '../../lib/http'
import { fetchArtifactBlob } from '../../lib/artifacts'
import ChartViewer from '../ChartViewer.vue'
import DataPanel from '../DataPanel.vue'

const source = name => readFileSync(new URL('../' + name, import.meta.url), 'utf8').replace(/\r\n/g, '\n')

/** 跑真组件的 setup() 拿回绑定（同 artifact-list.test.js 的手法）。refs 不解包，一律写 .value。 */
async function mountBindings(component, props) {
  let bindings = null
  const Probe = defineComponent({
    name: 'R169DataProbe',
    setup(_props, ctx) {
      bindings = component.setup(props || {}, ctx)
      return () => null
    },
  })
  await renderToString(h(Probe))
  expect(bindings, '组件应暴露可调用的 setup()').toBeTruthy()
  return bindings
}

/** 让挂载期那条 watch（以及它后面的 await 链）跑到收尾。 */
async function settled() {
  for (let round = 0; round < 12; round += 1) await nextTick()
}

/** data.py 的预览真形状：profile 是画像，rows 只是样例行（两者不是一回事）。 */
function previewPayload(over = {}) {
  return Object.assign({
    filename: '报销明细表.csv',
    profile: {
      rows: 137,
      column_count: 6,
      columns: [
        { name: '金额', dtype: 'float64', missing: 3 },
        { name: '部门', dtype: 'object', missing: 0 },
      ],
    },
    columns: ['金额', '部门'],
    rows: [{ 金额: 1280.5, 部门: '销售部' }],
    truncated: true,
  }, over)
}

/** axios 真错误形状：detail 是后端稳定码（B-5 之后不再是人话）。 */
function httpError(status, code) {
  return { response: { status, data: { detail: code } }, message: 'Request failed' }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('R169 D1 · 选文件这一腿真的会拉预览（跑真 loadDataFiles / selectDataFile）', () => {
  it('列表回来后自动选中第一个文件，并立刻打它的预览', async () => {
    http.get.mockImplementation(async (url) => {
      if (url === '/data-files') return { data: { files: [{ filename: '报销明细表.csv' }] } }
      if (url.includes('/preview')) return { data: previewPayload() }
      throw new Error('不该打这一条：' + url)
    })
    const b = await mountBindings(DataPanel)
    await b.loadDataFiles()
    expect(http.get.mock.calls.map(call => call[0])).toEqual(['/data-files', expect.stringContaining('/preview')])
    expect(b.dataFile.value).toBe('报销明细表.csv')
    expect(b.profile.value).toBeTruthy()
    expect(b.selectingFile.value).toBe(false)
  })

  it('文件名里的空格 / 中文 / 括号一律百分号编码，不拼坏路径', async () => {
    http.get.mockResolvedValue({ data: previewPayload({ filename: 'Q3 报销(终).csv' }) })
    const b = await mountBindings(DataPanel)
    await b.selectDataFile('Q3 报销(终).csv')
    expect(http.get.mock.calls[0][0]).toBe('/data-files/' + encodeURIComponent('Q3 报销(终).csv') + '/preview')
    expect(http.get.mock.calls[0][0]).not.toContain(' ')
  })

  it('一个文件都没有时画像位是空的：界面不拿空表冒充「统计过」', async () => {
    http.get.mockResolvedValue({ data: { files: [] } })
    const b = await mountBindings(DataPanel)
    await b.loadDataFiles()
    expect(b.dataFiles.value).toEqual([])
    expect(b.profile.value).toBe(null)
    expect(b.filesError.value).toBe('')
    expect(b.filesDenied.value).toBe(false)
    expect(http.get.mock.calls.filter(call => call[0].includes('/preview'))).toHaveLength(0)
  })
})

describe('R169 D2 · 预览与统计：屏上的数只从后端画像来（跑真 applyDataPreview）', () => {
  it('行数列数取画像里的数，不取样例行长度', async () => {
    const b = await mountBindings(DataPanel)
    b.applyDataPreview(previewPayload())
    expect(b.profile.value.rows).toBe(137)
    expect(b.profile.value.column_count).toBe(6)
    expect(b.tableRows.value).toHaveLength(1)
    expect(b.profile.value.rows).not.toBe(b.tableRows.value.length)
  })

  it('表头与样例行照后端给的原样交给表格原语，截断标记不自己推断', async () => {
    const b = await mountBindings(DataPanel)
    b.applyDataPreview(previewPayload({ truncated: false }))
    expect(b.tableColumns.value).toEqual(['金额', '部门'])
    expect(b.tableTruncated.value).toBe(false)
    b.applyDataPreview(previewPayload({ truncated: true }))
    expect(b.tableTruncated.value).toBe(true)
    b.applyDataPreview({ filename: 'x.csv' })
    expect(b.profile.value).toBe(null)
    expect(b.tableColumns.value).toEqual([])
    expect(b.tableTruncated.value).toBe(false)
  })

  it('逐列缺失值一格不少地带回来，后端没给的列不补 0', async () => {
    const b = await mountBindings(DataPanel)
    b.applyDataPreview(previewPayload({
      profile: { rows: 10, columns: [{ name: '金额', dtype: 'float64', missing: 3 }, { name: '备注', dtype: 'object' }] },
    }))
    expect(b.profile.value.columns[0].missing).toBe(3)
    expect('missing' in b.profile.value.columns[1]).toBe(false)
    expect(b.profile.value.columns[1].missing).toBeUndefined()
    // 这两枚读数的读取位在模板上：砍掉「数从画像来」这条判据就断在这里
    const dataPanel = source('DataPanel.vue')
    expect(dataPanel).toContain('{{ profile.rows }} 行')
    expect(dataPanel).toContain('{{ col.missing }} 缺失')
  })

  it('预览 403：这是「打不开」不是「没有数据」，且不给重试', async () => {
    http.get.mockRejectedValue(httpError(403, 'permission_denied'))
    const b = await mountBindings(DataPanel)
    await b.selectDataFile('别人的数据集.xlsx')
    expect(b.previewDenied.value).toBe(true)
    expect(b.previewError.value).toContain('不属于你的可见范围')
    expect(b.previewError.value).not.toContain('permission_denied')
    expect(b.profile.value).toBe(null)
    expect(source('DataPanel.vue')).toMatch(/:retryable="!previewDenied"/)
  })

  it('预览 5xx：另一张脸——句子与无权限不同源，重试位留着', async () => {
    http.get.mockRejectedValue(httpError(500, 'a_code_nobody_registered_yet'))
    const b = await mountBindings(DataPanel)
    await b.selectDataFile('坏掉的数据集.csv')
    expect(b.previewDenied.value).toBe(false)
    expect(b.previewError.value).toBe('数据文件预览失败')
  })

  it('同为 403 但码不是 permission_denied：不许顺手判成「没权限」', async () => {
    http.get.mockRejectedValue(httpError(403, 'department_scope_required'))
    const b = await mountBindings(DataPanel)
    await b.selectDataFile('部门范围没设.csv')
    expect(b.previewDenied.value).toBe(false)
    expect(b.previewError.value).toBeTruthy()
    expect(b.previewError.value).not.toContain('department_scope_required')
  })

  it('列表与预览各判一次权限：列表能看见不等于每个文件都打得开', async () => {
    http.get.mockImplementation(async (url) => {
      if (url === '/data-files') return { data: { files: [{ filename: '我的.csv' }, { filename: '他的.csv' }] } }
      throw httpError(403, 'permission_denied')
    })
    const b = await mountBindings(DataPanel)
    await b.loadDataFiles()
    expect(b.filesDenied.value, '列表 200 就画得好好的，别让预览的失败传染它').toBe(false)
    expect(b.dataFiles.value).toHaveLength(2)
    expect(b.previewDenied.value).toBe(true)
  })
})

describe('R169 C1 · 出图只从带 Bearer 的通道取字节（跑真 ChartViewer 的 load）', () => {
  const ARTIFACT = '/api/v1/artifacts/a1/content'

  it('有地址就真去取，屏上绑的只有本地地址，产物地址一个字节都不绑', async () => {
    fetchArtifactBlob.mockResolvedValue({ objectUrl: 'blob:chart-1', mediaType: 'image/png', size: 2048, revoke() {} })
    const b = await mountBindings(ChartViewer, reactive({ src: ARTIFACT, caption: '销售额趋势', downloadName: 'trend.png' }))
    expect(fetchArtifactBlob).toHaveBeenCalledWith(ARTIFACT)
    await settled()
    expect(b.loadState.value).toBe('ready')
    expect(b.objectUrl.value).toBe('blob:chart-1')
    expect(b.displayUrl.value).toBe('blob:chart-1')
    const viewer = source('ChartViewer.vue')
    // 两处 <img> 都只吃 displayUrl；直接 :src="src" 就是这一格要抓的缺陷（浏览器发子请求不带 Bearer）
    expect(viewer).toMatch(/<img :src="displayUrl"/)
    expect(viewer).not.toMatch(/<img[^>]*:src="src"/)
  })

  it('这一轮没有图：什么都不发，也不在屏上留一块破图占位', async () => {
    const b = await mountBindings(ChartViewer, reactive({ src: '', caption: '', downloadName: '' }))
    expect(b.loadState.value).toBe('idle')
    expect(fetchArtifactBlob).not.toHaveBeenCalled()
    expect(b.downloadUrl.value).toBe('')
    const html = await renderToString(h(ChartViewer, { src: '' }))
    expect(html).not.toContain('<img')
    expect(html).not.toContain('data:image')
  })

  it('已经是本地地址的（内联图）直接用，不再发一次请求', async () => {
    const b = await mountBindings(ChartViewer, reactive({ src: 'data:image/png;base64,AAA', caption: '', downloadName: '' }))
    await settled()
    expect(fetchArtifactBlob).not.toHaveBeenCalled()
    expect(b.loadState.value).toBe('ready')
    expect(b.objectUrl.value).toBe('data:image/png;base64,AAA')
  })

  it('换一张图先释放上一条：屏幕上同时只留一个本地地址', async () => {
    const revoked = []
    const props = reactive({ src: ARTIFACT, caption: '', downloadName: '' })
    fetchArtifactBlob.mockResolvedValue({ objectUrl: 'blob:chart-1', mediaType: 'image/png', size: 1, revoke: () => revoked.push('blob:chart-1') })
    const b = await mountBindings(ChartViewer, props)
    await settled()
    expect(b.objectUrl.value).toBe('blob:chart-1')
    fetchArtifactBlob.mockResolvedValue({ objectUrl: 'blob:chart-2', mediaType: 'image/png', size: 1, revoke: () => revoked.push('blob:chart-2') })
    // 换 src 那一腿的触发器是 watch（SSR 实例的作用域在渲染收尾时已停，这里直接调同一条 load()：
    // 它读的就是 props.src，与 watch 回调进的是同一个函数体。「props 变了自动重取」归真机/visual。
    props.src = '/api/v1/artifacts/a2/content'
    await b.load()
    await settled()
    expect(revoked).toContain('blob:chart-1')
    expect(b.objectUrl.value).toBe('blob:chart-2')
  })
})

describe('R169 C2 · 取图失败、空字节与被取消各一张脸（跑真 ChartViewer 的 load）', () => {
  it('取失败：说「未能显示」并留一条真的重试，重试打的是同一条通道', async () => {
    fetchArtifactBlob.mockRejectedValue(Object.assign(new Error('取图失败（HTTP 500）'), { code: 'http_500' }))
    const b = await mountBindings(ChartViewer, reactive({ src: '/api/v1/artifacts/bad/content', caption: '', downloadName: '' }))
    await settled()
    expect(b.loadState.value).toBe('error')
    expect(b.errorText.value).toBe('取图失败（HTTP 500）')
    expect(b.downloadUrl.value).toBe('')
    const failedCalls = fetchArtifactBlob.mock.calls.length
    fetchArtifactBlob.mockResolvedValue({ objectUrl: 'blob:ok-2', mediaType: 'image/png', size: 2, revoke() {} })
    await b.load()
    await settled()
    expect(b.loadState.value).toBe('ready')
    expect(fetchArtifactBlob.mock.calls.length).toBe(failedCalls + 1)
    const viewer = source('ChartViewer.vue')
    expect(viewer).toMatch(/@click="load"[^>]*>重新取图|重新取图/)
    expect(viewer).toContain('@click="load"')
  })

  it('请求是被取消的：不画失败卡（拿取消当错误会凭空多出一张红脸）', async () => {
    fetchArtifactBlob.mockRejectedValue(Object.assign(new Error('取图已取消'), { code: 'aborted' }))
    const b = await mountBindings(ChartViewer, reactive({ src: '/api/v1/artifacts/x/content', caption: '', downloadName: '' }))
    await settled()
    expect(b.loadState.value).not.toBe('error')
    expect(b.errorText.value).toBe('')
  })

  it('后端只回空字节：说「内容为空」这一格，不给一张破图', async () => {
    fetchArtifactBlob.mockRejectedValue(Object.assign(new Error('图表内容为空'), { code: 'empty_artifact' }))
    const b = await mountBindings(ChartViewer, reactive({ src: '/api/v1/artifacts/e/content', caption: '', downloadName: '' }))
    await settled()
    expect(b.loadState.value).toBe('error')
    expect(b.errorText.value).toBe('图表内容为空')
    expect(b.downloadUrl.value).toBe('')
  })
})

describe('R169 C3 · 下载：链接只指向已经取回的那份字节', () => {
  it('ready 之后下载的就是屏上那张图的本地副本，且两处入口都带文件名', async () => {
    fetchArtifactBlob.mockResolvedValue({ objectUrl: 'blob:dl-1', mediaType: 'image/png', size: 4096, revoke() {} })
    const b = await mountBindings(ChartViewer, reactive({ src: '/api/v1/artifacts/dl/content', caption: '趋势', downloadName: 'sales-trend.png' }))
    await settled()
    expect(b.downloadUrl.value).toBe('blob:dl-1')
    expect(b.downloadUrl.value).toBe(b.displayUrl.value)
    const viewer = source('ChartViewer.vue')
    const anchors = viewer.match(/<a [^>]*:href="downloadUrl"[^>]*>/g) || []
    expect(anchors.length, '两处下载入口（卡片与放大层）都得存在').toBeGreaterThan(1)
    for (const anchor of anchors) expect(anchor).toContain(':download="downloadName')
    // 反证锚：下载位一旦改成产物直链（浏览器自己发请求＝没有 Bearer），这一条红
    expect(viewer).not.toMatch(/<a[^>]*:href="src"/)
  })

  it('没取回来的时候没有下载地址：不给一条点了必失败的链接', async () => {
    const pending = new Promise(resolve => { fetchArtifactBlob.mockImplementation(resolve) })
    const b = await mountBindings(ChartViewer, reactive({ src: '/api/v1/artifacts/slow/content', caption: '', downloadName: 'slow.png' }))
    expect(fetchArtifactBlob).toHaveBeenCalledTimes(1)
    expect(b.downloadUrl.value).toBe('')
    fetchArtifactBlob.mockImplementation(async () => ({ objectUrl: 'blob:late', mediaType: 'image/png', size: 1, revoke() {} }))
    await b.load()
    await settled()
    expect(b.downloadUrl.value).toBe('blob:late')
    expect(pending).toBeTruthy()
  })
})
