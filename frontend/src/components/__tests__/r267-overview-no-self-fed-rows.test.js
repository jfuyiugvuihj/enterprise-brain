/**
 * R267 · 块 A 判据①② 的反证钉
 *
 * 钉的是两件事，方向都是「改回假数据就必须红」：
 *   ① 这一屏不再把自己造的 rows 送给后端：取数只剩三条 GET，POST 只准留给指标口径查询。
 *   ② 金额折线没有真数据就不画（连装饰用的假趋势形状也不算数据）；「异常与风险」接真账，
 *      而「没权限 / 结构坏了 / 真没有记录」是三张脸，谁也不许顶替谁。
 *
 * 手法沿用 dashboard-summary.test.js：环境是 node + @vue/server-renderer（仓里没有 jsdom），
 * 只 mock 网络层那一个 axios 实例，先跑组件自己的加载，再把同一份 bindings 渲染成真 HTML。
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
import { SUMMARY_PATH } from '../../lib/dashboard'

const source = name => readFileSync(new URL(name, import.meta.url), 'utf8').replace(/\r?\n/g, '\n')
const panelSource = () => source('../../components/DashboardPanel.vue')

/** 后端 dashboard-demo.js 那三枚常量的全部数值与标题：它们再回到这一屏就是假话回来了。 */
const DEMO_FOOTPRINTS = [
  '18600', '9200', '14200', '7600', '4200', '5400',
  '18,600', '9,200', '14,200', '7,600', '4,200', '5,400',
  '市场部差旅费异常', '财务部报销波动', '行政部住宿费上升',
]

function summaryBody(overrides = {}) {
  return Object.assign({
    generated_for: 'finance-manager',
    pending_approvals: 3,
    documents: 5,
    datasets: 12,
    alerts: { total: 137, unread: 40 },
  }, overrides)
}

function axiosError(status, detail) {
  return { response: { status, data: { detail } } }
}

function stubRoutes({ summary = summaryBody(), catalogRows = [], alerts = { status: 200, data: { alerts: [] } }, context = null } = {}) {
  http.get.mockImplementation(async (url) => {
    if (url === SUMMARY_PATH) return { status: 200, data: summary }
    if (url === '/documents/catalog') return { status: 200, data: { documents: catalogRows } }
    if (url === '/alerts') {
      if (alerts.status !== 200) throw axiosError(alerts.status, alerts.detail)
      return alerts
    }
    throw new Error(`不该被请求的路径：${url}`)
  })
  http.post.mockImplementation(async (url) => {
    if (url === '/semantics/match') return { status: 200, data: context }
    throw new Error(`不该被请求的路径：${url}`)
  })
}

async function mountedPanel() {
  let bindings = null
  const Host = {
    name: 'R267Probe',
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

async function renderLoaded(bindings) {
  return renderToString(h({ ...DashboardPanel, setup: () => bindings }))
}

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
})

describe('R267① · 这一屏不再把自造 rows 送给后端', () => {
  it('源码形状：自备 rows 那条腿、三枚演示常量、算法端点的回执字段一起消失', () => {
    const s = panelSource()
    expect(s).not.toMatch(/api\.post\(['"]\/dashboard['"]/)
    expect(s).not.toMatch(/rows:\s/)
    expect(s).not.toMatch(/insights:\s/)
    expect(s).not.toMatch(/demoRows|demoInsights|demoTrendShape/)
    expect(s).not.toMatch(/devFixtures/)
    expect(s).not.toMatch(/departments/)
  })

  it('真跑一次加载：只打三条 GET，POST 只可能是指标口径查询', async () => {
    stubRoutes()
    const bindings = await mountedPanel()
    await bindings.lookupMetric()
    const gets = http.get.mock.calls.map(call => call[0]).sort()
    expect(gets).toEqual(['/alerts', '/documents/catalog', SUMMARY_PATH].sort())
    const posts = http.post.mock.calls.map(call => call[0])
    expect(posts).toEqual(['/semantics/match'])
    expect(bindings.error.value).toBe('')
  })

  it('四个数字仍只从聚合来：文档列表回来 1 行，数字位照旧画 5', async () => {
    stubRoutes({ catalogRows: [{ filename: '制度汇编.pdf', parse_status: 'ready' }] })
    const bindings = await mountedPanel()
    expect(bindings.documents.value).toHaveLength(1)
    expect(bindings.summary.value.documents).toBe(5)
    const html = await renderLoaded(bindings)
    expect(html).toContain('>5</strong>')
  })
})

describe('R267② · 没有真数据就不画线，异常卡接真账', () => {
  it('趋势卡是空态：没有折线、没有圆点、没有金额刻度，也没有画死的迷你趋势装饰', async () => {
    stubRoutes()
    const html = await renderLoaded(await mountedPanel())
    expect(html).toContain('data-testid="dashboard-trend-card"')
    expect(html).toContain('data-testid="dashboard-trend-empty"')
    for (const shape of ['<polyline', '<circle', 'chart-y-axis', 'chart-x-axis', 'kpi-spark', 'kpi-bars']) {
      expect(html).not.toContain(shape)
    }
    for (const fake of DEMO_FOOTPRINTS) expect(html).not.toContain(fake)
  })

  it('空态那句人话说的是「没有来源」，不是「一切正常」', async () => {
    stubRoutes()
    const html = await renderLoaded(await mountedPanel())
    const from = html.indexOf('data-testid="dashboard-trend-empty"')
    const block = html.slice(from, html.indexOf('</p>', from))
    expect(block).toContain('不画线')
    expect(block).not.toMatch(/一切正常|没有异常|已就绪/)
  })

  it('异常与风险摆的是服务端账本行：消息与时间是真回传，不是常量', async () => {
    stubRoutes({
      alerts: {
        status: 200,
        data: {
          alerts: [
            { id: 7, rule_id: 2, message: '华东区差旅费本月已超阈值', ai_analysis: '', created_at: '2026-09-25T10:12:00+08:00' },
            { id: 6, rule_id: 4, message: '研发费用环比波动超过设定值', ai_analysis: '', created_at: '2026-09-24T18:40:00+08:00' },
          ],
        },
      },
    })
    const html = await renderLoaded(await mountedPanel())
    expect(html).toContain('华东区差旅费本月已超阈值')
    expect(html).toContain('研发费用环比波动超过设定值')
    expect(html).toContain('2026-09-25 10:12')
    expect(html.match(/data-testid="dashboard-risk-row"/g)).toHaveLength(2)
  })

  it('账本只回 4 行，第 5 行不许挤进来，也不许数列表长度当告警数', async () => {
    const rows = Array.from({ length: 6 }, (_, index) => ({ id: index, message: `账本记录 ${index}`, created_at: '' }))
    stubRoutes({ alerts: { status: 200, data: { alerts: rows } } })
    const bindings = await mountedPanel()
    const html = await renderLoaded(bindings)
    expect(bindings.alertRows.value).toHaveLength(4)
    expect(html.match(/data-testid="dashboard-risk-row"/g)).toHaveLength(4)
    const alertTile = html.slice(html.indexOf('data-testid="dashboard-kpi-alerts"'))
    expect(alertTile.slice(0, alertTile.indexOf('</button>'))).toContain('>137<')
  })

  it('403 是一张独立的失败脸：不降级成空态，也不给重试按钮', async () => {
    stubRoutes({ alerts: { status: 403, detail: 'permission_denied' } })
    const bindings = await mountedPanel()
    const html = await renderLoaded(bindings)
    expect(bindings.alertFailure.value.face).toBe('denied')
    expect(html).toContain('这个账号看不到告警账本')
    expect(html).not.toContain('当前没有异常线索')
    expect(html).not.toContain('data-testid="ui-error-retry"')
  })

  it('200 空数组才是空态：那句「当前没有异常线索」只有这一种走法', async () => {
    stubRoutes({ alerts: { status: 200, data: { alerts: [] } } })
    const bindings = await mountedPanel()
    const html = await renderLoaded(bindings)
    expect(bindings.alertFailure.value).toBe(null)
    expect(html).toContain('当前没有异常线索')
    expect(html).not.toContain('这个账号看不到告警账本')
  })

  it('这一格读不到不许把整屏拖进错误态：四个数字照旧在位', async () => {
    stubRoutes({ alerts: { status: 500, detail: 'internal_error' } })
    const bindings = await mountedPanel()
    const html = await renderLoaded(bindings)
    expect(bindings.error.value).toBe('')
    expect(html).toContain('异常与风险没加载出来')
    expect(html).toContain('data-testid="dashboard-kpi-documents"')
    expect(html).toContain('data-testid="dashboard-kpi-datasets"')
  })
})