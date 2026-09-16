/**
 * W6 · 总览四个数字改读 R14-A1 服务端聚合（GET /api/v1/dashboard/summary）
 *
 * 环境仍是 node + @vue/server-renderer（仓库没有 jsdom / @vue/test-utils，也不许 npm i），
 * 所以断言分三条腿，各管各的事：
 *   ① 纯函数：lib/dashboard.js 的读形状、告警分脸、失败归脸，直接喂真 payload / 真错误体。
 *   ② 真组件 + 真 DOM：只 mock 网络层（lib/http 的那一个 axios 实例），先跑组件自己的
 *      loadDashboard() 取回真 bindings，再把同一份 bindings 当作 setup 结果渲染一次真 HTML。
 *      SSR 不跑 onMounted，所以「有数字的那张脸」必须这样喂出来，而不是在测试里手搓模板。
 *      错误句一律走真 errorDetail / isPermissionDenied（这两个不 mock），判据才不会被 mock 顺带改掉。
 *   ③ 源码形状：四个数字不许再从列表长度来；告警那条路径不许出现 ?? 0 / || 0 / .length。
 *
 * 契约对照（tests/test_dashboard_summary.py 是后端那一侧的同一份）：
 *   无告警权限时 alerts 键整个缺席 -> 界面画「无权限查看告警」，不画 0；
 *   告警总数按表算（137）、列表页长只有 100 -> 界面画 137；
 *   缺账本 -> 整个响应 503 storage_unavailable -> 文案与「就是读不到」分开两句。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'

// 只换网络层：面板（经 lib/api 别名）与 lib/dashboard 取的是同一个 http 对象。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn() } }
})

import { http } from '../../lib/http'
import DashboardPanel from '../DashboardPanel.vue'
import {
  ALERT_STATE_COUNTED,
  ALERT_STATE_DENIED,
  ALERT_STATE_UNREADABLE,
  COUNT_PLACEHOLDER,
  SUMMARY_DENIED_TITLE,
  SUMMARY_FAILED_TITLE,
  SUMMARY_MALFORMED_TITLE,
  SUMMARY_PATH,
  SUMMARY_STORAGE_TITLE,
  alertTileView,
  formatSummaryCount,
  loadDashboardSummary,
  parseSummaryPayload,
  readAlertFace,
  responseOk,
  summaryErrorView,
  summaryScopeNote,
  summaryTiles,
} from '../../lib/dashboard'

const source = (name) => readFileSync(new URL(name, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const panelSource = () => source('../../components/DashboardPanel.vue')
const libSource = () => source('../../lib/dashboard.js')

/** 后端 R14-A1 的 200 真形状：字段名与 app/api/v1/dashboard.py 一一对应。 */
function summaryBody(overrides = {}) {
  return Object.assign({
    generated_for: 'finance-manager',
    pending_approvals: 3,
    documents: 5,
    datasets: 12,
    alerts: { total: 137, unread: 40 },
  }, overrides)
}

/** 无告警权限：后端把整个键省掉，不是给 0，也不是给 null。 */
function summaryBodyWithoutAlerts() {
  const body = summaryBody()
  delete body.alerts
  return body
}

function axiosError(status, detail) {
  return { response: { status, data: detail === undefined ? {} : { detail } } }
}

function networkError() {
  return Object.assign(new Error('Network Error'), { code: 'ERR_NETWORK' })
}

function stubRoutes({ summary, catalogRows = [], card }) {
  http.get.mockImplementation(async (url) => {
    if (url === SUMMARY_PATH) return { status: 200, data: summary }
    if (url === '/documents/catalog') return { status: 200, data: { documents: catalogRows } }
    throw new Error(`不该被请求的路径：${url}`)
  })
  http.post.mockImplementation(async (url) => {
    if (url === '/dashboard') return { status: 200, data: card || { metrics: {}, departments: {}, insights: [] } }
    throw new Error(`不该被请求的路径：${url}`)
  })
}

/** 跑真组件的 setup()，再显式触发一次真加载，返回原始绑定（ref 不解包，一律 .value）。 */
async function mountedPanel() {
  let bindings = null
  const Host = {
    name: 'W6Probe',
    setup(props, ctx) {
      bindings = DashboardPanel.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Host))
  expect(bindings, '组件应暴露可调用的 setup()').toBeTruthy()
  await bindings.loadDashboard()
  return bindings
}

/** 把上面那份真绑定再交给真模板渲染一次：拿到带真数字的 HTML。 */
async function renderLoaded(bindings) {
  return renderToString(h({ ...DashboardPanel, setup: () => bindings }))
}

const grab = (block, tag) => {
  const match = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`).exec(block)
  return match ? match[1] : null
}

/** 从真 HTML 里取一张数字卡：标签 / 数值 / 副文案 / 卡片自身的属性串。 */
function tileOf(html, id) {
  const marker = `data-testid="dashboard-kpi-${id}"`
  const start = html.indexOf(marker)
  expect(start, `渲染里找不到数字卡 ${id}`).toBeGreaterThan(-1)
  const head = html.slice(html.lastIndexOf('<button', start), html.indexOf('>', start))
  const block = html.slice(start, html.indexOf('</button>', start))
  return { label: grab(block, 'small'), value: grab(block, 'strong'), note: grab(block, 'em'), attrs: head }
}

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
})

describe('W6-① alerts 键缺席是没权限，不是 0 条告警', () => {
  it('纯函数：省掉键 -> denied；给 0 -> counted。两种脸不可能共用一个数', () => {
    const denied = readAlertFace(summaryBodyWithoutAlerts())
    const zero = readAlertFace(summaryBody({ alerts: { total: 0, unread: 0 } }))
    const counted = readAlertFace(summaryBody())
    expect(denied.state).toBe(ALERT_STATE_DENIED)
    expect(denied.total).toBe(null)
    expect(zero.state).toBe(ALERT_STATE_COUNTED)
    expect(zero.total).toBe(0)
    expect(counted.total).toBe(137)
  })

  it('没权限时数字位是占位横杠，副文案说「无权限查看告警」', () => {
    const tile = alertTileView(readAlertFace(summaryBodyWithoutAlerts()))
    expect(tile.value).toBe(COUNT_PLACEHOLDER)
    expect(tile.value).not.toBe('0')
    expect(tile.note).toBe('无权限查看告警')
    expect(tile.hint).toContain('不代表当前没有告警')
  })

  it('给了键但形状读不出来 -> 第三张脸：既不折成 0，也不谎称没权限', () => {
    expect(alertTileView(readAlertFace(summaryBody({ alerts: { total: null } }))).state).toBe(ALERT_STATE_UNREADABLE)
    expect(alertTileView(readAlertFace(summaryBody({ alerts: null }))).state).toBe(ALERT_STATE_UNREADABLE)
    const unreadable = alertTileView(readAlertFace(summaryBody({ alerts: 12 })))
    expect(unreadable.value).toBe(COUNT_PLACEHOLDER)
    expect(unreadable.note).not.toBe('无权限查看告警')
  })

  it('真渲染：告警卡画「无权限查看告警」，另外三个真实数字一个都不许跟着丢', async () => {
    stubRoutes({ summary: summaryBodyWithoutAlerts() })
    const html = await renderLoaded(await mountedPanel())
    const alerts = tileOf(html, 'alerts')
    expect(alerts.value).toBe('—')
    expect(alerts.note).toBe('无权限查看告警')
    expect(alerts.attrs).toContain('data-alert-state="denied"')
    expect(html).not.toContain('data-alert-state="counted"')
    expect(tileOf(html, 'documents').value).toBe('5')
    expect(tileOf(html, 'datasets').value).toBe('12')
    expect(tileOf(html, 'pendingApprovals').value).toBe('3')
  })

  it('对照组：服务端真给了 0 条告警时才画 0，且不出现「无权限」字样', async () => {
    stubRoutes({ summary: summaryBody({ alerts: { total: 0, unread: 0 } }) })
    const html = await renderLoaded(await mountedPanel())
    expect(tileOf(html, 'alerts').value).toBe('0')
    expect(tileOf(html, 'alerts').attrs).toContain('data-alert-state="counted"')
    expect(html).not.toContain('无权限查看告警')
  })

  it('没有数字的告警位不许借用「一切正常」那盏绿灯（样式判据）', () => {
    const s = panelSource()
    expect(s).toMatch(/\[data-alert-state='denied'\][\s\S]{0,120}color: var\(--ink-soft\)/)
  })
})

describe('W6-② 数字取聚合里的总数，不取列表页长', () => {
  it('137 条告警、列表只给 100 行：界面画 137', () => {
    const metrics = parseSummaryPayload(summaryBody({ alerts: { total: 137, unread: 40 } }))
    const listed = Array.from({ length: 100 }, (_, index) => ({ id: index }))
    const tile = summaryTiles(metrics).find(item => item.id === 'alerts')
    expect(listed).toHaveLength(100)
    expect(tile.value).toBe('137')
    expect(tile.value).not.toBe(String(listed.length))
    expect(tile.delta).toBe('未读 40 条')
  })

  it('真渲染：聚合说 5 篇文档，列表卡只回来 2 行，数字仍是 5', async () => {
    stubRoutes({
      summary: summaryBody(),
      catalogRows: [{ filename: '制度汇编.pdf' }, { filename: '差旅标准.docx' }],
    })
    const bindings = await mountedPanel()
    const html = await renderLoaded(bindings)
    expect(tileOf(html, 'documents').value).toBe('5')
    expect(html).toContain('制度汇编.pdf')
    expect(bindings.documents.value).toHaveLength(2)
  })

  it('数据表的数字不再靠拉列表：/data-files 与 /alerts 一次都不许被请求', async () => {
    stubRoutes({ summary: summaryBody() })
    const html = await renderLoaded(await mountedPanel())
    const urls = http.get.mock.calls.map(call => call[0])
    expect(urls).toContain(SUMMARY_PATH)
    expect(urls).not.toContain('/data-files')
    expect(urls).not.toContain('/alerts')
    expect(tileOf(html, 'datasets').value).toBe('12')
  })

  it('四张卡的数值与千分位都来自同一次聚合', () => {
    const metrics = parseSummaryPayload(summaryBody({ documents: 12345, datasets: 0, pending_approvals: 1, alerts: { total: 8, unread: 0 } }))
    const tiles = summaryTiles(metrics)
    expect(tiles.map(item => item.id)).toEqual(['documents', 'datasets', 'pendingApprovals', 'alerts'])
    expect(tiles.map(item => item.value)).toEqual(['12,345', '0', '1', '8'])
    expect(tiles.find(item => item.id === 'datasets').delta).toBe('还没有数据文件')
    expect(tiles.every(item => item.hint.length > 0)).toBe(true)
  })
})

describe('W6-③ 503 存储没就绪与「就是读不到」是两句话', () => {
  it('503 那张脸的标题与句子都不与通用失败共用', () => {
    const storage = summaryErrorView(axiosError(503, 'storage_unavailable'))
    const unreadable = summaryErrorView(networkError())
    expect(storage.storage).toBe(true)
    expect(storage.title).toBe(SUMMARY_STORAGE_TITLE)
    expect(storage.description).toContain('还没有就绪')
    expect(unreadable.title).toBe(SUMMARY_FAILED_TITLE)
    expect(unreadable.title).not.toBe(storage.title)
    expect(unreadable.description).not.toBe(storage.description)
  })

  it('没权限是第三句话，且句子只说人话不带裸码名', () => {
    const denied = summaryErrorView(axiosError(403, 'permission_denied'))
    expect(denied.denied).toBe(true)
    expect(denied.storage).toBe(false)
    expect(denied.title).toBe(SUMMARY_DENIED_TITLE)
    expect(denied.description).not.toMatch(/storage_unavailable|permission_denied/)
  })

  it('真渲染：503 与通用失败各画各的标题，两句都不把码名当人话上屏', async () => {
    http.get.mockRejectedValue(axiosError(503, 'storage_unavailable'))
    const storageHtml = await renderLoaded(await mountedPanel())
    http.get.mockRejectedValue(networkError())
    const failedHtml = await renderLoaded(await mountedPanel())
    expect(storageHtml).toContain(SUMMARY_STORAGE_TITLE)
    expect(failedHtml).toContain(SUMMARY_FAILED_TITLE)
    expect(failedHtml).not.toContain(SUMMARY_STORAGE_TITLE)
    for (const html of [storageHtml, failedHtml]) {
      expect(html).toContain('role="alert"')
      expect(html).toContain('data-testid="ui-error-retry"')
      expect(html).not.toMatch(/storage_unavailable|permission_denied|internal_error/)
    }
  })

  it('200 但 ok=false、或形状读不出数：按失败处理，不画半个总览', async () => {
    http.get.mockImplementation(async () => ({ ok: false, status: 200, data: summaryBody() }))
    const notOk = await mountedPanel()
    expect(notOk.error.value).toBeTruthy()
    expect(notOk.errorTitle.value).toBe(SUMMARY_FAILED_TITLE)
    expect(notOk.summary.value).toBe(null)

    http.get.mockImplementation(async (url) => (url === SUMMARY_PATH ? { status: 200, data: { documents: 3 } } : { status: 200, data: { documents: [] } }))
    const malformed = await mountedPanel()
    const malformedHtml = await renderLoaded(malformed)
    expect(malformed.errorTitle.value).toBe(SUMMARY_MALFORMED_TITLE)
    expect(malformedHtml).toContain(SUMMARY_MALFORMED_TITLE)
    expect(malformed.kpis.value).toEqual([])
    expect(malformedHtml).not.toContain('dashboard-kpi-documents')
  })
})

describe('W6-④ 取数走统一实例、检查 response.ok、失败可重试、口径写明白', () => {
  it('responseOk 认 fetch 风格的 ok，也认状态码区间', () => {
    expect(responseOk({ status: 200 })).toBe(true)
    expect(responseOk({ status: 204 })).toBe(true)
    expect(responseOk({ status: 500 })).toBe(false)
    expect(responseOk({ ok: false, status: 200 })).toBe(false)
    expect(responseOk({ ok: true, status: 200 })).toBe(true)
    expect(responseOk(null)).toBe(false)
    expect(responseOk(undefined)).toBe(false)
  })

  it('loadDashboardSummary 只经统一 axios 实例打这条路径，并且不抛错给面板', async () => {
    stubRoutes({ summary: summaryBody() })
    const result = await loadDashboardSummary()
    expect(SUMMARY_PATH).toBe('/dashboard/summary')
    expect(result.ok).toBe(true)
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(http.get.mock.calls[0][0]).toBe(SUMMARY_PATH)

    http.get.mockRejectedValue(axiosError(403, 'permission_denied'))
    await expect(loadDashboardSummary()).resolves.toMatchObject({ ok: false, denied: true })
  })

  it('错误态带重试按钮，重试再走一次同一批请求并把数字补回来', async () => {
    http.get.mockRejectedValue(axiosError(503, 'storage_unavailable'))
    const bindings = await mountedPanel()
    expect(bindings.error.value).toBeTruthy()
    stubRoutes({ summary: summaryBody() })
    await bindings.loadDashboard()
    expect(bindings.error.value).toBe('')
    expect(bindings.summary.value.documents).toBe(5)
    const urls = http.get.mock.calls.map(call => call[0])
    expect(urls.every(url => url === SUMMARY_PATH || url === '/documents/catalog')).toBe(true)
  })

  it('口径来源写在数字旁边，并如实带上服务端回显的登录者', () => {
    const note = summaryScopeNote('finance-manager')
    expect(note).toContain('可见范围')
    expect(note).toContain('finance-manager')
    expect(note).toContain('不是全租户总数')
    expect(summaryScopeNote('')).toContain('按你当前的可见范围')
    expect(summaryScopeNote(null)).toContain('按你当前的可见范围')
  })

  it('真渲染里能看到口径行，四张卡也各自标了落点', async () => {
    stubRoutes({ summary: summaryBodyWithoutAlerts() })
    const html = await renderLoaded(await mountedPanel())
    expect(html).toContain('data-testid="dashboard-scope-note"')
    expect(html).toContain('四个数字由服务端按「finance-manager」当前的可见范围计算')
    for (const target of ['docs', 'data', 'approval', 'insights']) {
      expect(html).toContain(`data-target="${target}"`)
    }
  })

  it('源码形状：四个数字只从聚合来，面板里不再自己数行', () => {
    const s = panelSource()
    expect(s).toContain('summaryTiles(summary.value)')
    expect(s).toContain('const summary = ref(null)')
    expect(s).not.toMatch(/value:[^\n]*\.length/)
    expect(s).not.toMatch(/documents\.value\.length|dataFiles\.value|approvalCount/)
    expect(s).not.toContain('const dataFiles = ref([])')
    expect(s).not.toMatch(/value:[^\n]*latestInsights/)
    expect(s).not.toMatch(/from 'axios'/)
  })

  it('源码形状：告警那条路径里没有把缺字段折成 0 的写法', () => {
    const s = libSource()
    const from = s.indexOf('export function readAlertFace')
    const to = s.indexOf('export function formatSummaryCount')
    expect(from).toBeGreaterThan(-1)
    expect(to).toBeGreaterThan(from)
    const block = s.slice(from, to)
    expect(block).toContain("hasOwn(payload, 'alerts')")
    expect(block).not.toMatch(/\?\? 0|\|\| 0|\.length/)
  })

  it('数值格式化：读不出来的数只给横杠，不给 0', () => {
    expect(formatSummaryCount(0)).toBe('0')
    expect(formatSummaryCount(null)).toBe(COUNT_PLACEHOLDER)
    expect(formatSummaryCount(undefined)).toBe(COUNT_PLACEHOLDER)
    expect(formatSummaryCount('12')).toBe('12')
    expect(formatSummaryCount(-3)).toBe(COUNT_PLACEHOLDER)
    expect(formatSummaryCount('abc')).toBe(COUNT_PLACEHOLDER)
  })
})
