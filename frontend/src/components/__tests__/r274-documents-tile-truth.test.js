/**
 * R274 · X-3 的反证钉：文档卡那句副文案只跟着服务端真值走
 *
 * 病灶在 frontend/src/lib/dashboard.js：`delta: metrics.documents ? '已解析入库' : '还没有文档'`。
 * 「目录里有 N 篇」与「N 篇都解析完了」是两件事——账本里躺着一篇解析失败的文档时，这句好话
 * 照样上屏。R267 把面板里行级的解析状态归了真，漏的就是 lib 这一层。
 *
 * 两组走法各钉一张脸，🔴 谁也不许被并成一句万能空态：
 *   ① 组钉「这一格缺席，或缺回来的值读不出数」那一张脸。R411 起它的口径是契约违约脸：
 *      R284 起 /summary 无条件带这一数（app/api/v1/dashboard.py 的 payload 字面量里就是
 *      "documents_ready": documents_ready 这一行，它上方注释原文 "this key is never
 *      conditional"），一份合契约的回执根本走不到这一档。旧稿把这一张写成线上今天的样子，
 *      还替服务端许过一次愿，两头都不成立——本件这六行的口径由 R411 改口，一枚断言都不动。
 *      这一张脸必须留着：摘掉它，一份缺列的回执就会被画成「全部已解析」。
 *   ③ 组钉回执带上这一数之后的三档读数（两数相等 / 还有没解析完的 / 两数对不上）：线上
 *      今天真正画到屏上的那几张脸都在这里。
 *
 * 手法沿用 dashboard-summary.test.js：node + @vue/server-renderer，只 mock 网络层那一个
 * axios 实例，先跑组件自己的加载，再把真 bindings 渲染成真 HTML——断言打在屏幕文本上。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn() } }
})

import { http } from '../../lib/http'
import DashboardPanel from '../DashboardPanel.vue'
import {
  DOCUMENTS_ALL_READY_NOTE,
  DOCUMENTS_EMPTY_NOTE,
  DOCUMENTS_MISMATCH_NOTE,
  DOCUMENTS_UNRECORDED_NOTE,
  SUMMARY_PATH,
  documentsTileView,
  parseSummaryPayload,
  summaryTiles,
} from '../../lib/dashboard'

/** 改前那一屏写死的好话：它回到任何一处渲染产物里，本件立刻红。 */
const OLD_LIE = '已解析入库'

/** 违约形状：一份不带解析进度这一格的聚合回执（R284 起服务端不会这样回，见头两组）。 */
function summaryBody(overrides = {}) {
  return Object.assign({
    generated_for: 'boss',
    pending_approvals: 3,
    documents: 5,
    datasets: 12,
    alerts: { total: 0, unread: 0 },
  }, overrides)
}

/** 走真解析链：聚合回执 -> 四个数字里的文档卡。 */
function documentsTile(payload) {
  const metrics = parseSummaryPayload(payload)
  expect(metrics, '这份聚合回执本身就该读不出数').toBeTruthy()
  return summaryTiles(metrics).find(item => item.id === 'documents')
}

/** 从真 HTML 里取一张数字卡的副文案，就是 <em> 那一行。 */
function tileNote(html, id) {
  const start = html.indexOf('data-testid="dashboard-kpi-' + id + '"')
  expect(start, '渲染里找不到数字卡 ' + id).toBeGreaterThan(-1)
  const block = html.slice(start, html.indexOf('</button>', start))
  // SSR 会给每个标签补 scoped 样式标记，所以标签名后面不能直接跟 >。
  const match = /<em[^>]*>([^<]*)<\/em>/.exec(block)
  expect(match, '这张卡没有副文案').toBeTruthy()
  return match[1]
}

/** 从真 HTML 里取一张数字卡的口径提示，就是 :title 那一串（挂在 DashboardPanel.vue 的卡头上）。 */
function tileHint(html, id) {
  const mark = html.indexOf('data-testid="dashboard-kpi-' + id + '"')
  expect(mark, '渲染里找不到数字卡 ' + id).toBeGreaterThan(-1)
  // title 排在 data-testid 之后，所以截取必须从开标签起算，不能从 testid 起算。
  const block = html.slice(html.lastIndexOf('<', mark), html.indexOf('</button>', mark))
  const match = /title="([^"]*)"/.exec(block)
  expect(match, '这张卡没有口径提示').toBeTruthy()
  return match[1]
}

async function renderWith(options = {}) {
  const summary = options.summary || summaryBody()
  const catalogRows = options.catalogRows || []
  http.get.mockImplementation(async (url) => {
    if (url === SUMMARY_PATH) return { status: 200, data: summary }
    if (url === '/documents/catalog') return { status: 200, data: { documents: catalogRows } }
    if (url === '/alerts') return { status: 200, data: { alerts: [] } }
    throw new Error('不该被请求的路径：' + url)
  })
  http.post.mockImplementation(async (url) => {
    if (url === '/semantics/match') {
      return { status: 200, data: { context: null, definition_source: null, provenance: null } }
    }
    throw new Error('不该被请求的路径：' + url)
  })
  let bindings = null
  const Host = {
    name: 'R274TileProbe',
    setup(props, ctx) {
      bindings = DashboardPanel.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Host))
  await bindings.loadDashboard()
  await bindings.lookupMetric()
  return renderToString(h({ ...DashboardPanel, setup: () => bindings }))
}

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
})

describe('R274① · 回执不带「已解析篇数」这一格（违约形状）：这一档只许说没记录', () => {
  it('账本里有解析失败的文档时，屏上不许出现「已解析入库」', async () => {
    const html = await renderWith({
      catalogRows: [
        { filename: 'a.pdf', parse_status: 'failed' },
        { filename: 'b.pdf', parse_status: 'ready' },
      ],
    })
    // 先证明那篇失败文档真的在屏上：不然上面那句 not.toContain 就是一句空话。
    expect(html).toContain('解析失败')
    expect(html).not.toContain(OLD_LIE)
    expect(tileNote(html, 'documents')).toBe(DOCUMENTS_UNRECORDED_NOTE)
  })

  it('纯函数：回执没这一数就是 null，不折成 0、也不折成「全部」', () => {
    expect(parseSummaryPayload(summaryBody()).documentsReady).toBe(null)
    expect(documentsTile(summaryBody()).delta).toBe(DOCUMENTS_UNRECORDED_NOTE)
    expect(documentsTile(summaryBody({ documents_ready: null })).delta).toBe(DOCUMENTS_UNRECORDED_NOTE)
    expect(documentsTile(summaryBody({ documents_ready: 'many' })).delta).toBe(DOCUMENTS_UNRECORDED_NOTE)
  })

  it('未记录那句下面跟着人话的口径说明，而且不把后端字段名画上屏', () => {
    const tile = documentsTile(summaryBody())
    expect(tile.hint.length).toBeGreaterThan(10)
    expect(tile.hint).toContain('只回了')
    expect(tile.delta + tile.hint).not.toMatch(/parse_status|index_status|documents_ready/)
  })

  it('一篇都没有：还是那句「还没有文档」，不借「未记录」装作读到了什么', () => {
    expect(documentsTile(summaryBody({ documents: 0 })).delta).toBe(DOCUMENTS_EMPTY_NOTE)
  })

  it('总数本身取不出来时也不许说「还没有文档」：读不出数不等于没有', () => {
    const tile = summaryTiles({ documents: null, documentsReady: null, alerts: null }).find(item => item.id === 'documents')
    expect(tile.delta).toBe(DOCUMENTS_UNRECORDED_NOTE)
    expect(tile.delta).not.toBe(DOCUMENTS_EMPTY_NOTE)
  })

  it('R411 · 屏上那一句 :title 逐字等于 lib 里那一串：口径提示没有一个字是面板自己加的', async () => {
    // 这一枚是 R411 乙组那几枚「屏上不许出现等待」的前提：纯函数读到的那一句确实就是渲染
    // 出去的那一句。没有它，只测 lib 等于给面板留了一个「自己再写一句」的新家。
    const html = await renderWith({})
    const metrics = parseSummaryPayload(summaryBody())
    expect(tileHint(html, 'documents')).toBe(documentsTileView(metrics).hint)
    expect(tileNote(html, 'documents')).toBe(documentsTileView(metrics).delta)
  })
})

describe('R274③ · 回执带上这一数（R284 起的常态）：同一处代码自己换脸（不许再写死）', () => {
  it('两数相等给「全部已解析」，没解析完报差额：两句都不是旧那句好话', () => {
    const all = documentsTile(summaryBody({ documents: 5, documents_ready: 5 }))
    const partial = documentsTile(summaryBody({ documents: 5, documents_ready: 3 }))
    expect(all.delta).toBe(DOCUMENTS_ALL_READY_NOTE)
    expect(partial.delta).toBe('2 篇还没解析完')
    expect(partial.hint).toBe(all.hint)
    for (const tile of [all, partial]) expect(tile.delta).not.toBe(OLD_LIE)
  })

  it('一篇都没解析完也要报差额，不许退化成「未记录」蒙过去', () => {
    expect(documentsTile(summaryBody({ documents: 5, documents_ready: 0 })).delta).toBe('5 篇还没解析完')
  })

  it('已解析比总数还大 = 一次坏掉的回执：只说对不上，不挑一句好听的', () => {
    const tile = documentsTile(summaryBody({ documents: 5, documents_ready: 7 }))
    expect(tile.delta).toBe(DOCUMENTS_MISMATCH_NOTE)
    expect(tile.hint).toContain('不可能同时成立')
  })

  it('真渲染走一遍「后端已补列」的形状：屏上换成正解的那句，旧那句仍 0 命中', async () => {
    const html = await renderWith({
      summary: summaryBody({ documents: 2, documents_ready: 2 }),
      catalogRows: [{ filename: 'a.pdf', parse_status: 'ready' }],
    })
    expect(tileNote(html, 'documents')).toBe(DOCUMENTS_ALL_READY_NOTE)
    expect(html).not.toContain(OLD_LIE)
  })
})
