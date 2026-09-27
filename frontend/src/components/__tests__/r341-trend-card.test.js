/**
 * R341 · 「数据趋势」这一格的真渲染钉
 *
 * 判据①的那句话就是这一枚件的主轴：trend 真回数据之后，「服务端还没有回传…」一个字都不许
 * 留在屏上；反过来，读不到 / 没权限 / 那几期真的零新增是三张脸，谁也不许顶替谁，更不许
 * 谁被画成 0。手法沿用 r267 那两枚件：环境 node + @vue/server-renderer（仓里没有 jsdom），
 * 只 mock 网络层那一枚 axios 实例，先真跑取数，再把同一份 bindings 渲染成真 HTML。
 *
 * 关于取数时机：趋势这一发不并进 loadDashboard —— 那三条 GET 的计数钉（R267①／R274③）
 * 量的是「四个数字只从聚合来、告警那一发只在有权限时发」，与这一格无关。这一格与口径卡
 * 同一族：onMounted 自己取，失败只换自己的脸，重试只补自己这一格。SSR 不触发 onMounted，
 * 所以既有件那一腿一律停在「还没取过数」那张脸上，本件用 bindings.loadTrend() 显式驱动。
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
import {
  COUNT_PLACEHOLDER,
  SUMMARY_PATH,
  TREND_ALERTS_DENIED_NOTE,
  TREND_DENIED_TITLE,
  TREND_INVALID_TITLE,
  TREND_MALFORMED_TITLE,
  TREND_PATH,
  TREND_STORAGE_TITLE,
  TREND_ZERO_NOTE,
} from '../../lib/dashboard'

const source = name => readFileSync(new URL(name, import.meta.url), 'utf8').replace(/\r?\n/g, '\n')
const panelSource = () => source('../../components/DashboardPanel.vue')
const libSource = () => source('../../lib/dashboard.js')

const SUMMARY = {
  generated_for: 'finance-manager',
  pending_approvals: 3,
  documents: 5,
  datasets: 12,
  alerts: { total: 137, unread: 40 },
}

function point(bucket, documents, ready, datasets, alerts, alertsOpen) {
  const row = { bucket, start: `${bucket}-01`, documents, documents_ready: ready, datasets }
  if (alerts !== null) {
    row.alerts = alerts
    row.alertsOpen = undefined
    row.alerts_open = alertsOpen
  }
  return row
}

/** 有告警读权那一档：两个月 + 一周的样本，数字与 SUMMARY 故意对不平。 */
function adminTrend(overrides = {}) {
  return {
    generated_for: 'finance-manager',
    period: 'month',
    buckets: 2,
    time_zone: 'Asia/Shanghai',
    // 五枚数字两两不同：任何一格被别的字段顶掉（含「已解析并入总数」那一类合并），逐格对序立刻红。
    series: [point('2026-08', 2, 1, 3, 4, 0), point('2026-09', 6, 4, 1, 2, 2)],
    ...overrides,
  }
}

function staffTrend() {
  const series = adminTrend().series.map(row => {
    const copy = { ...row }
    delete copy.alerts
    delete copy.alerts_open
    return copy
  })
  return { ...adminTrend(), series }
}

function zeroTrend() {
  const series = [point('2026-08', 0, 0, 0, 0, 0), point('2026-09', 0, 0, 0, 0, 0)]
  return { ...adminTrend(), series }
}

function axiosError(status, detail) {
  return { response: { status, data: { detail } } }
}

function stubRoutes({ trend = { status: 200, data: adminTrend() }, summary = SUMMARY } = {}) {
  http.get.mockImplementation(async (url) => {
    if (url === SUMMARY_PATH) return { status: 200, data: summary }
    if (url === '/documents/catalog') return { status: 200, data: { documents: [] } }
    if (url === '/alerts') return { status: 200, data: { alerts: [] } }
    if (url === TREND_PATH) {
      if (trend instanceof Error) throw trend
      if (trend.status !== 200) throw axiosError(trend.status, trend.detail)
      return trend
    }
    throw new Error(`不该被请求的路径：${url}`)
  })
  http.post.mockImplementation(async (url) => {
    if (url === '/semantics/match') return { status: 200, data: { context: null } }
    throw new Error(`不该被请求的路径：${url}`)
  })
}

async function mountedPanel(options = {}, install = null) {
  if (install) install()
  else stubRoutes(options)
  let bindings = null
  const Host = {
    name: 'R341Probe',
    setup(props, ctx) {
      bindings = DashboardPanel.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Host))
  await bindings.loadDashboard()
  return bindings
}

async function panelHtml(bindings) {
  return renderToString(h({ ...DashboardPanel, setup: () => bindings }))
}

/** 可控延迟：token 闸门只有「回包能迟到」才测得出来。 */
function deferredTrend() {
  const queue = []
  const install = () => http.get.mockImplementation((url, config) => {
    if (url === TREND_PATH) {
      let settle = null
      const promise = new Promise((resolve, reject) => { settle = { resolve, reject } })
      queue.push({ settle, params: config.params })
      return promise
    }
    if (url === SUMMARY_PATH) return Promise.resolve({ status: 200, data: SUMMARY })
    if (url === '/documents/catalog') return Promise.resolve({ status: 200, data: { documents: [] } })
    if (url === '/alerts') return Promise.resolve({ status: 200, data: { alerts: [] } })
    if (url === '/semantics/match') return Promise.resolve({ status: 200, data: { context: null } })
    return Promise.reject(new Error(`不该被请求的路径：${url}`))
  })
  return { queue, install }
}

/** 表里逐格读数：这一屏只有趋势这一张表，所以这串就是趋势的那几格。 */
const trendCells = html => [...html.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)]
  .map(match => match[1].replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim())

const visibleText = html => html
  .replace(/<!--[\s\S]*?-->/g, ' ')
  .replace(/<[^>]+>/g, ' ')
  .replace(/\s+/g, ' ')
  .trim()

const flush = async () => {
  for (let i = 0; i < 8; i += 1) await Promise.resolve()
  await new Promise(resolve => setTimeout(resolve, 0))
}

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
})

describe('R341① · 那句假话必须死', () => {
  it('源码里那两句「服务端还没回传 / 等聚合补上」整枚消失，永不许抄回来', () => {
    // 文案现在住在 lib 里，钉子就得同时扫两枚文件：只扫面板等于给假话留了个新家。
    for (const s of [panelSource(), libSource()]) {
      expect(s).not.toMatch(/服务端还没有回传|还没提供按期间汇总|等经营趋势的聚合补上|这里才会长出数字/)
      expect(s).not.toMatch(/data-unwired="trend"/)
    }
  })

  it('trend 真回数据：空态那一句与它的 testid 一起从屏上消失，数字上屏', async () => {
    const bindings = await mountedPanel({})
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    expect(html).not.toContain('data-testid="dashboard-trend-empty"')
    expect(html).not.toContain('服务端还没有回传')
    expect(html).not.toContain('还没有可信的来源')
    expect(html).toContain('data-testid="dashboard-trend-ready"')
    expect(html).toContain('2026 年 9 月')
    expect(html).toContain('data-testid="dashboard-trend-documents"')
    expect(bindings.trendView.value.rows).toHaveLength(2)
  })

  it('数字上了屏，那块「演示数据」诚实牌自己收掉（它只在这一格还没有服务端数字时挂着）', async () => {
    const bindings = await mountedPanel({})
    expect(await panelHtml(bindings)).toContain('data-testid="dashboard-demo-flag"')
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    expect(html).not.toContain('data-testid="dashboard-demo-flag"')
    expect(html).not.toContain('演示数据')
  })

  it('还没取过数那一档仍然在位：说的是「没取到就不画线」，不再替服务端说谎', async () => {
    const bindings = await mountedPanel({})
    const html = await panelHtml(bindings)
    const from = html.indexOf('data-testid="dashboard-trend-empty"')
    expect(from).toBeGreaterThan(-1)
    const block = html.slice(from, html.indexOf('</p>', from))
    expect(block).toContain('不画线')
    expect(block).not.toMatch(/一切正常|没有异常|已就绪|还没有回传/)
  })
})

describe('R341①⑧ · 读不到 / 没权限 / 真零新增 是三张脸', () => {
  it('503 读不到：说「存储还没就绪」，不摆表、不画 0、不降级成空态或零新增', async () => {
    const bindings = await mountedPanel({ trend: { status: 503, detail: 'storage_unavailable' } })
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    expect(html).toContain(TREND_STORAGE_TITLE)
    expect(html).toContain('data-testid="dashboard-trend-failed"')
    expect(html).not.toContain('data-testid="dashboard-trend-table"')
    expect(html).not.toContain('data-testid="dashboard-trend-documents"')
    expect(html).not.toContain('data-testid="dashboard-trend-empty"')
    expect(html).not.toContain(TREND_ZERO_NOTE)
  })

  it('422 参数没被接受：与 503 各说各话，两张脸不许共用一句', async () => {
    const bindings = await mountedPanel({ trend: { status: 422, detail: 'validation_error' } })
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    expect(html).toContain(TREND_INVALID_TITLE)
    expect(html).not.toContain(TREND_STORAGE_TITLE)
  })

  it('回包形状坏了：算「读不出数」，不算空序列、不算零新增', async () => {
    const bindings = await mountedPanel({ trend: { status: 200, data: { period: 'month', buckets: 12, time_zone: 'Asia/Shanghai', series: [] } } })
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    expect(html).toContain(TREND_MALFORMED_TITLE)
    expect(html).not.toContain(TREND_ZERO_NOTE)
    expect(html).not.toContain('data-testid="dashboard-trend-empty"')
  })

  it('真·零新增：表格照摆、0 照画，但那一句说的是「确实没有新增」', async () => {
    const bindings = await mountedPanel({ trend: { status: 200, data: zeroTrend() } })
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    expect(html).toContain('data-testid="dashboard-trend-table"')
    expect(html).toContain(TREND_ZERO_NOTE)
    expect(html.match(/data-testid="dashboard-trend-row"/g)).toHaveLength(2)
    expect(html).not.toContain(TREND_STORAGE_TITLE)
    expect(html).not.toContain(TREND_MALFORMED_TITLE)
  })

  it('403 是没权限：不给重试按钮，也不说成「读不到」', async () => {
    const bindings = await mountedPanel({ trend: { status: 403, detail: 'permission_denied' } })
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    expect(html).toContain(TREND_DENIED_TITLE)
    expect(html).not.toContain('data-testid="ui-error-retry"')
  })

  it('一格读不到不许拖走整屏：四个数字照旧在位', async () => {
    const bindings = await mountedPanel({ trend: axiosError(500, 'internal_error') })
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    expect(bindings.error.value).toBe('')
    expect(html).toContain('data-testid="dashboard-kpi-documents"')
    expect(html).toContain('data-testid="dashboard-kpi-alerts"')
  })
})

describe('R341④ · 整键缺席不等于 0', () => {
  it('staff 那一档：告警两列整列不出现，另说一句「是不向你开放，不是 0 条告警」', async () => {
    const bindings = await mountedPanel({ trend: { status: 200, data: staffTrend() } })
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    expect(html).not.toContain('新增告警（条）')
    expect(html).not.toContain('其中未闭环（条）')
    expect(html).not.toContain('data-testid="dashboard-trend-alerts"')
    expect(html).not.toContain('data-testid="dashboard-trend-alerts-open"')
    expect(html).toContain(TREND_ALERTS_DENIED_NOTE)
    // 列数当场数一遍：没权限那一档只剩四枚列头、每行三格（两行 = 六格），告警那两格压根不存在。
    expect(html.match(/<th scope="col"/g)).toHaveLength(4)
    expect(html.match(/data-testid="dashboard-trend-row"/g)).toHaveLength(2)
    expect(html.match(/<td/g)).toHaveLength(6)
  })

  it('有告警读权那一档：两列在位并逐格画服务端给的数，未闭环那一列附一句不可回放', async () => {
    const bindings = await mountedPanel({})
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    expect(html).toContain('新增告警')
    expect(html).toContain('其中未闭环')
    expect(html.match(/data-testid="dashboard-trend-alerts"/g)).toHaveLength(2)
    expect(html).toContain('事后回看')
    expect(html).not.toContain(TREND_ALERTS_DENIED_NOTE)
  })

  it('读不出的告警数只画横杠，横杠仍是总览那一枚占位符', async () => {
    const broken = adminTrend()
    broken.series = broken.series.map(row => ({ ...row, alerts: 'many', alerts_open: null }))
    const bindings = await mountedPanel({ trend: { status: 200, data: broken } })
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    expect(html.match(new RegExp('>' + COUNT_PLACEHOLDER + '<', 'g')).length).toBeGreaterThanOrEqual(4)
    expect(html).not.toMatch(/data-testid="dashboard-trend-alerts">\s*0</)
  })
})

describe('R341⑤ · 参数照后端走', () => {
  it('按月按周切换与窗口档位都只经查询参数交给服务端', async () => {
    const bindings = await mountedPanel({})
    await bindings.loadTrend()
    bindings.setTrendPeriod('week')
    expect(http.get.mock.calls.filter(call => call[0] === TREND_PATH).map(call => call[1].params))
      .toEqual([{ period: 'month', buckets: 12 }, { period: 'week', buckets: 12 }])
    bindings.setTrendBuckets(60)
    expect(http.get.mock.calls.filter(call => call[0] === TREND_PATH).map(call => call[1].params))
      .toEqual([{ period: 'month', buckets: 12 }, { period: 'week', buckets: 12 }, { period: 'week', buckets: 60 }])
  })

  it('前端不截窗口、不造密度：表里就是服务端回的那几期，一行不多一行不少', async () => {
    const bindings = await mountedPanel({})
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    expect(html.match(/data-testid="dashboard-trend-row"/g)).toHaveLength(2)
    expect(panelSource()).toMatch(/v-for="row in trendView\.rows"/)
    expect(panelSource()).not.toMatch(/trendView\.rows\.slice|\.rows\.filter/)
  })

  it('越界的档位不夹也不猜：不发那一发请求，直接说参数没有被接受', async () => {
    const bindings = await mountedPanel({})
    await bindings.loadTrend()
    const before = http.get.mock.calls.filter(call => call[0] === TREND_PATH).length
    bindings.setTrendBuckets(61)
    await flush()
    expect(http.get.mock.calls.filter(call => call[0] === TREND_PATH)).toHaveLength(before)
    const html = await panelHtml(bindings)
    expect(html).toContain('趋势的期间参数没有被接受')
    expect(html).not.toContain('data-testid="dashboard-trend-table"')
  })

  it('这一发只在取趋势时打：loadDashboard 那三条 GET 一格都没多', async () => {
    const bindings = await mountedPanel({})
    expect(http.get.mock.calls.map(call => call[0]).sort()).toEqual(['/alerts', '/documents/catalog', SUMMARY_PATH].sort())
    await bindings.loadTrend()
    expect(http.get.mock.calls.map(call => call[0])).toContain(TREND_PATH)
  })
})

describe('R341⑥ · 不留旧数字（token 闸门）', () => {
  it('切 period 的第一瞬就收掉上一份 series：进行态里一格旧数都不许挂着', async () => {
    const { queue, install } = deferredTrend()
    const bindings = await mountedPanel({}, install)
    const first = bindings.loadTrend()
    queue[0].settle.resolve({ status: 200, data: adminTrend() })
    await first
    expect(await panelHtml(bindings)).toContain('2026 年 9 月')
    bindings.setTrendPeriod('week')
    const html = await panelHtml(bindings)
    expect(html).not.toContain('data-testid="dashboard-trend-row"')
    expect(html).not.toContain('2026 年 9 月')
    expect(html).toContain('正在向服务端取按期间汇总的计数')
    queue[1].settle.resolve({ status: 200, data: adminTrend({ period: 'week', buckets: 1, series: [point('2026-W39', 1, 1, 0, 0, 0)] }) })
    await flush()
    expect(await panelHtml(bindings)).toContain('2026 年第 39 周')
  })

  it('迟到的回包一律丢掉：先发的月序列不得盖掉后到的周序列', async () => {
    const { queue, install } = deferredTrend()
    const bindings = await mountedPanel({}, install)
    const stale = bindings.loadTrend()
    bindings.setTrendPeriod('week')
    await flush()
    queue[1].settle.resolve({ status: 200, data: adminTrend({ period: 'week', buckets: 1, series: [point('2026-W40', 3, 3, 0, 0, 0)] }) })
    await flush()
    queue[0].settle.resolve({ status: 200, data: adminTrend() })
    await stale
    await flush()
    const html = await panelHtml(bindings)
    expect(html).toContain('2026 年第 40 周')
    expect(html).not.toContain('2026 年 9 月')
    expect(bindings.trendView.value.period).toBe('week')
  })
})

describe('R341②③⑧ · 数字只来自趋势回执、单位说人话、图形与数一致', () => {
  it('这一格只打趋势那一条路径：不碰聚合、不读文档列表反推', async () => {
    const bindings = await mountedPanel({})
    await bindings.loadTrend()
    const urls = http.get.mock.calls.map(call => call[0])
    expect(urls.filter(url => url === TREND_PATH)).toHaveLength(1)
    expect(urls.filter(url => url === SUMMARY_PATH)).toHaveLength(1)
    const s = panelSource()
    expect(s).not.toMatch(/created_at/)
    expect(s).not.toMatch(/new Date\(/)
  })

  it('窗口与聚合故意对不平：两个数各自上屏，屏上不出现「对平」那句假话', async () => {
    const bindings = await mountedPanel({})
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    expect(html).toContain('data-testid="dashboard-kpi-documents"')
    expect(html).toContain('>5<')
    expect(html).toContain('6')
    expect(html).toContain('两边本来就不该相等')
    expect(html).not.toMatch(/合计等于|与总览一致|与上方数字相符/)
  })

  it('文案与列标只表条目数，一枚金额符号都不许出现', async () => {
    const bindings = await mountedPanel({})
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    expect(html).toContain('新增条目数')
    expect(html).toContain('新增文档（条）')
    expect(html).toContain('新增数据集（个）')
    expect(visibleText(html)).not.toMatch(/[¥￥$]|万元|[0-9]\s*元/)
    expect(visibleText(html)).not.toMatch(/营业额|销售额|费用额|预算|GMV/)
    expect(visibleText(html)).toContain('没有任何金额刻度')
  })

  it('条形与那一格的数同序：最高那格画满、其余等比、零那格收成零长', async () => {
    const bindings = await mountedPanel({})
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    expect(html).toContain('width:100.0%')
    const low = html.match(/width:33\.3%/)
    expect(low).not.toBe(null)
    const zero = await panelHtml(await mountedPanelWith(zeroTrend()))
    expect(zero).toContain('width:0%')
    expect(zero).not.toContain('width:100.0%')
  })

  it('documents 与 documents_ready 分开两格画，不在图上被合并成一个数', async () => {
    const bindings = await mountedPanel({})
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    const row = html.slice(html.indexOf('2026 年 8 月'), html.indexOf('2026 年 9 月'))
    expect(row).toContain('>2<')
    expect(row).toContain('>1<')
    expect(row).toContain('width:33.3%')
    expect(html).toContain('其中已解析（条）')
  })

  it('一格只认一个字段：十格逐格对序，谁被别列顶掉当场红', async () => {
    const bindings = await mountedPanel({})
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    expect(trendCells(html)).toEqual(['2', '1', '3', '4', '0', '6', '4', '1', '2', '2'])
  })

  it('后端字段名一律洗成中文：屏上读不到 documents_ready 这种机器名', async () => {
    const bindings = await mountedPanel({})
    await bindings.loadTrend()
    const html = await panelHtml(bindings)
    const text = html.replace(/<[^>]+>/g, ' ')
    expect(text).not.toMatch(/documents_ready|alerts_open|created_at|time_zone|generated_for/)
  })

  async function mountedPanelWith(data) {
    const bindings = await mountedPanel({ trend: { status: 200, data } })
    await bindings.loadTrend()
    return bindings
  }
})
