/**
 * R274 · X-6 的反证钉：文档目录那一发失败只许换「最新文档」这一格的脸
 *
 * 原病灶（改前即如此）：loadOverviewCards 里直接 await api.get('/documents/catalog')，
 * 一发 500 就冒到 loadDashboard 的 catch，整屏换成错误脸；更糟的是异常卡的取数排在其后，
 * 于是「文档目录读不到」还会顺带吞掉告警账本那一发请求——一格的事拖走一屏。
 *
 * 这一件钉三个方向：① 失败只归这一格；② 其余卡各自的既有脸一张不许变；
 * ③ 重试只补这一格，不重播整屏。🚫 告警卡的失败归脸（lib/alerts.js）不在本件范围内，
 * 这里只钉它「不许被牵连」：catalog 坏了的时候，异常卡该是空态就还是空态。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn() } }
})

import { http } from '../../lib/http'
import DashboardPanel from '../DashboardPanel.vue'
import { DOCUMENTS_DENIED_TITLE, DOCUMENTS_FAILED_TITLE, SUMMARY_PATH } from '../../lib/dashboard'

const source = name => readFileSync(new URL(name, import.meta.url), 'utf8').replace(/\r?\n/g, '\n')
const panelSource = () => source('../../components/DashboardPanel.vue')

const SUMMARY = {
  generated_for: 'boss',
  pending_approvals: 3,
  documents: 5,
  datasets: 12,
  alerts: { total: 0, unread: 0 },
}
const CATALOG_ROWS = [{ filename: '制度汇编.pdf', parse_status: 'ready', index_status: 'indexed' }]
const EMPTY_DOCS_COPY = '上传制度或业务文档后显示在这里'

function axiosError(status, detail) {
  return { response: { status, data: { detail } } }
}

// summary 可覆盖：R285 起「三条 GET」这枚计数是有前提的，没告警读权那半份要拿一份不带
// alerts 键的聚合来数（app/api/v1/dashboard.py:137-139 那一格只在有权限时才出）。
function stubRoutes({ summary = SUMMARY, catalog = { status: 200, data: { documents: CATALOG_ROWS } }, alerts = { status: 200, data: { alerts: [] } } } = {}) {
  http.get.mockImplementation(async (url) => {
    if (url === SUMMARY_PATH) return { status: 200, data: summary }
    if (url === '/documents/catalog') {
      if (catalog.status !== 200) throw axiosError(catalog.status, catalog.detail)
      return catalog
    }
    if (url === '/alerts') {
      // 'absent' = 这一发压根不该出现（R285 那半份）：抛的是「不该被请求」，不是 403 归脸。
      if (alerts === 'absent') throw new Error('不该被请求的路径：/alerts（这一屏没有告警读权）')
      if (alerts.status !== 200) throw axiosError(alerts.status, alerts.detail)
      return alerts
    }
    throw new Error('不该被请求的路径：' + url)
  })
  http.post.mockImplementation(async (url) => {
    if (url === '/semantics/match') {
      return { status: 200, data: { context: null, definition_source: null, provenance: null } }
    }
    throw new Error('不该被请求的路径：' + url)
  })
}

async function loadedPanel(options) {
  stubRoutes(options)
  let bindings = null
  const Host = {
    name: 'R274CatalogProbe',
    setup(props, ctx) {
      bindings = DashboardPanel.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Host))
  await bindings.loadDashboard()
  await bindings.lookupMetric()
  return { bindings, html: await renderToString(h({ ...DashboardPanel, setup: () => bindings })) }
}

const requestedUrls = () => http.get.mock.calls.map(call => call[0])

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
})

describe('R274③ · catalog 500：只有「最新文档」换脸', () => {
  it('整屏不进错误态，四张数字卡与另外三格的既有脸一张不少', async () => {
    const { bindings, html } = await loadedPanel({ catalog: { status: 500, detail: 'internal_error' } })
    expect(bindings.error.value).toBe('')
    // 整屏错误脸与内容分支是 v-if / v-else 两路：诚实牌只在「没进错误态」那一支渲染。
    expect(html).toContain('data-testid="dashboard-demo-flag"')
    for (const id of ['documents', 'datasets', 'pendingApprovals', 'alerts']) {
      expect(html).toContain('data-testid="dashboard-kpi-' + id + '"')
    }
    // 这一格长出新脸
    expect(html).toContain(DOCUMENTS_FAILED_TITLE)
    expect(html).toContain('data-testid="ui-error-state"')
    expect(html).not.toContain(EMPTY_DOCS_COPY)
    // 其余三格各自的旧脸不许被顶替：趋势空态、异常空态、口径空态
    expect(html).toContain('不画线')
    expect(html).toContain('当前没有异常线索')
    expect(html).toContain('查询指标口径后显示证据')
    expect(html).not.toContain('异常与风险没加载出来')
    expect(html).not.toContain(DOCUMENTS_DENIED_TITLE)
  })

  // 计数改成有前提的条件式（R285 · X-2），等号一个都没放宽：有告警读权这一发照发，
  // catalog 坏了也不许吞掉它；没读权那一发本来就不该发，这一格换成「不向你开放」那张脸。
  it('catalog 坏了不许再吞掉告警那一发请求：有告警读权时一次加载照旧只打三条 GET', async () => {
    expect(Object.prototype.hasOwnProperty.call(SUMMARY, 'alerts')).toBe(true)
    const { bindings } = await loadedPanel({ catalog: { status: 500, detail: 'internal_error' } })
    expect(bindings.documents.value).toEqual([])
    expect(bindings.documentsFailure.value.denied).toBe(false)
    expect([...requestedUrls()].sort()).toEqual(['/alerts', '/documents/catalog', SUMMARY_PATH].sort())
  })

  it('换成没告警读权那半份：catalog 坏了仍是两行 GET，/alerts 一发都不许有', async () => {
    const staff = { ...SUMMARY }
    delete staff.alerts
    const { bindings } = await loadedPanel({ summary: staff, catalog: { status: 500, detail: 'internal_error' }, alerts: 'absent' })
    expect([...requestedUrls()].sort()).toEqual(['/documents/catalog', SUMMARY_PATH].sort())
    // 不发 ≠ 沉默：这一格说「不向你开放」，而不是「当前没有异常线索」。
    expect(bindings.alertFailure.value.face).toBe('denied')
    expect(bindings.documentsFailure.value.denied).toBe(false)
  })
})

describe('R274③ · catalog 403：是没权限，不是没有文档，也不给重试按钮', () => {
  it('换的是「没权限」那张脸，而且仍然只换这一格', async () => {
    const { bindings, html } = await loadedPanel({ catalog: { status: 403, detail: 'permission_denied' } })
    expect(bindings.error.value).toBe('')
    expect(bindings.documentsFailure.value.denied).toBe(true)
    expect(html).toContain(DOCUMENTS_DENIED_TITLE)
    expect(html).not.toContain(DOCUMENTS_FAILED_TITLE)
    expect(html).not.toContain('data-testid="ui-error-retry"')
    expect(html).toContain('data-testid="ui-error-state"')
    expect(html).toContain('当前没有异常线索')
  })

  it('把没权限画成空态就是假话：这一格读不到与「没有文档」是两句话', async () => {
    const { html } = await loadedPanel({ catalog: { status: 403, detail: 'permission_denied' } })
    expect(html).not.toContain(EMPTY_DOCS_COPY)
  })
})

describe('R274③ · 重试只补这一格', () => {
  it('再点一次成功后列表回来、失败脸收掉，而且不重播整屏那三条请求', async () => {
    const { bindings } = await loadedPanel({ catalog: { status: 500, detail: 'internal_error' } })
    expect(bindings.documentsFailure.value).toBeTruthy()
    const before = requestedUrls().length
    stubRoutes({})
    await bindings.loadDocumentRows()
    const after = requestedUrls().slice(before)
    expect(after).toEqual(['/documents/catalog'])
    expect(bindings.documentsFailure.value).toBe(null)
    expect(bindings.documents.value).toHaveLength(1)
    const html = await renderToString(h({ ...DashboardPanel, setup: () => bindings }))
    expect(html).toContain('制度汇编.pdf')
    expect(html).not.toContain(DOCUMENTS_FAILED_TITLE)
  })
})

describe('R274③ · 源码形状：失败就地归脸，不冒泡', () => {
  it('loadDocumentRows 自己 catch，并把 catalog 的取数从 loadOverviewCards 里搬走', () => {
    const s = panelSource()
    expect(s).toMatch(/async function loadDocumentRows\(\) \{[\s\S]*?api\.get\('\/documents\/catalog'\)[\s\S]*?\} catch \(err\) \{[\s\S]*?documentsFailure\.value = documentsFailureView\(err\)/)
    expect(s).toMatch(/async function loadOverviewCards\(\) \{\s*\n\s*await loadDocumentRows\(\)/)
    expect(s).toMatch(/v-if="documentsFailure"[\s\S]*?v-else-if="documents\.length"/)
    // 权限判定仍然只有两处：这一格的脸归在 lib，面板里不许再长第三处。
    expect(s.match(/isPermissionDenied\(err\)/g)).toHaveLength(2)
  })
})
