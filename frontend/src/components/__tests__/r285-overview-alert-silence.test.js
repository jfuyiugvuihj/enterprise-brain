/**
 * R285 · X-2 的反证钉：没有告警读取权的账号进总览，不再白打那一发必 403 的 GET /alerts
 *
 * 病灶链（本件现场复取，出处逐个点名）：
 *   一、DashboardPanel 的 loadRiskRows() 原先无条件 fetchAlerts()，只看列表回来什么。
 *   二、后端 app/api/v1/dashboard.py:137-139 只在 _alert_counts() 没返回 None 时才写 alerts 键，
 *       而它判的就是 GET /alerts 那同一条 _require_alert_management（dashboard.py:90 与
 *       alerts.py:925）；staff 与 auditor 的角色集里没有 alerts:manage（permissions.py:13/:16）。
 *   三、合起来：这一屏从聚合里读到「alerts 键缺席」的那一刻，就已经知道那一发必然 403。
 *
 * 本件钉四件事，方向各不相同：
 *   ① 没读权 ⇒ 那一发一次都不发，写请求与告警请求一个都不许多（判据①，改的是前端行为）。
 *   ② 不发不等于沉默：这一格必须画第三态「不向你开放」，不许掉回「当前没有异常线索」。
 *   ③ 有读权那一发照发、真行照上屏 —— 这单不许把有权限的人那一格弄没。
 *   ④ 没权限／401／真读失败／真空列表 四张脸两两不许共用（G4，与 R271 在告警屏的形状同一族）。
 *
 * 手法沿用 r267 / r274：node + @vue/server-renderer（仓里没有 jsdom），只 mock 网络层那一个
 * axios 实例，跑组件自己的加载，再把同一份 bindings 渲染成真 HTML。
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
import { SUMMARY_PATH, canReadAlerts, COUNT_PLACEHOLDER } from '../../lib/dashboard'
import { ALERTS_EMPTY_DESCRIPTION, alertsNotOpenView, fetchAlerts, readFailureView } from '../../lib/alerts'

const source = name => readFileSync(new URL(name, import.meta.url), 'utf8').replace(/\r?\n/g, '\n')
const panelSource = () => source('../../components/DashboardPanel.vue')

/** 这一屏那三张脸的标题：钉「两两不等」要拿它们互相比，字面量留在测试里是证据不是实现。 */
const RISK_DENIED_TITLE = '这个账号看不到告警账本'
const RISK_FAILED_TITLE = '异常与风险没加载出来'
const EMPTY_TITLE = '当前没有异常线索'
const RISK_ARGS = { deniedTitle: RISK_DENIED_TITLE, failedTitle: RISK_FAILED_TITLE }

const ADMIN_ROWS = [
  { id: 11, rule_id: 2, message: '华东区差旅费本月已超阈值', created_at: '2026-09-25T10:12:00+08:00' },
  { id: 10, rule_id: 4, message: '研发费用环比波动超过设定值', created_at: '2026-09-24T18:40:00+08:00' },
]

function summaryBody(overrides = {}) {
  return Object.assign({
    generated_for: 'admin',
    pending_approvals: 3,
    documents: 5,
    datasets: 12,
    alerts: { total: 137, unread: 40 },
  }, overrides)
}

/** staff 那份：后端整个省掉 alerts 键（连 null 都不给），这才是「没读权」的真形状。 */
function summaryBodyWithoutAlerts() {
  const body = summaryBody()
  delete body.alerts
  return body
}

function axiosError(status, detail) {
  return { response: { status, data: { detail } } }
}

/**
 * 路由桩。alerts 给 'absent' 时那一发根本不该被调用：桩直接抛，调用即红。
 * POST 这一腿只收 /semantics/match，别的路径抛错 —— 面板把它吞进 catch 也没用，
 * 下面的 posts 清单会把它揪出来。
 */
function stubRoutes({ summary = summaryBody(), catalogRows = [{ filename: '制度汇编.pdf', parse_status: 'ready', index_status: 'indexed' }], alerts = { status: 200, data: { alerts: ADMIN_ROWS } } } = {}) {
  http.get.mockImplementation(async (url) => {
    if (url === SUMMARY_PATH) return { status: 200, data: summary }
    if (url === '/documents/catalog') return { status: 200, data: { documents: catalogRows } }
    if (url === '/alerts') {
      if (alerts === 'absent') throw new Error('不该被请求的路径：/alerts（这一屏没有告警读权，这一发不该发）')
      if (alerts.status !== 200) throw axiosError(alerts.status, alerts.detail)
      return alerts
    }
    throw new Error('不该被请求的路径：' + url)
  })
  http.post.mockImplementation(async (url) => {
    if (url === '/semantics/match') return { status: 200, data: { context: null, definition_source: null, provenance: null } }
    throw new Error('不该被请求的路径：' + url)
  })
}

async function loadedPanel(options) {
  stubRoutes(options)
  let bindings = null
  const Host = {
    name: 'R285Probe',
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

const gets = () => http.get.mock.calls.map(call => call[0]).sort()
const posts = () => http.post.mock.calls.map(call => call[0])

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
})

describe('R285① · 没有告警读权就不发那一发', () => {
  it('前提自证：这一份聚合确实读不出 alerts 键，canReadAlerts 才判没权限', async () => {
    const staff = summaryBodyWithoutAlerts()
    expect(Object.prototype.hasOwnProperty.call(staff, 'alerts')).toBe(false)
    const { bindings } = await loadedPanel({ summary: staff, alerts: 'absent' })
    expect(bindings.summary.value.alerts.state).toBe('denied')
    expect(canReadAlerts(bindings.summary.value)).toBe(false)
    expect(canReadAlerts({ alerts: { state: 'counted', total: 0, unread: 0 } })).toBe(true)
    // 「还不知道」与「形状坏了」都不许当成没权限：宁可白打一次，也不把有权限的人那一格弄没。
    expect(canReadAlerts(null)).toBe(true)
    expect(canReadAlerts({ alerts: { state: 'unreadable', total: null, unread: null } })).toBe(true)
  })

  it('staff 一次加载：GET 恰好两行且不含 /alerts，写请求只有指标口径那一发', async () => {
    const { bindings } = await loadedPanel({ summary: summaryBodyWithoutAlerts(), alerts: 'absent' })
    expect(gets()).toEqual(['/documents/catalog', SUMMARY_PATH].sort())
    expect(gets()).not.toContain('/alerts')
    expect(posts()).toEqual(['/semantics/match'])
    // 口径卡那一句没被吞成「查询失败」：POST 桩抛过的错在这里会以另一张脸出现。
    expect(bindings.evidenceError.value).toBe('')
    expect(bindings.error.value).toBe('')
  })

  it('重试那条腿也不放过：没读权时 loadRiskRows 再点一次照样不发', async () => {
    const { bindings } = await loadedPanel({ summary: summaryBodyWithoutAlerts(), alerts: 'absent' })
    const before = http.get.mock.calls.length
    await bindings.loadRiskRows()
    expect(http.get.mock.calls).toHaveLength(before)
    expect(bindings.alertFailure.value.face).toBe('denied')
  })
})

describe('R285② · 不发不等于沉默：第三态必须说话', () => {
  it('那一格画「不向你开放」，而且不给重试按钮', async () => {
    const { bindings, html } = await loadedPanel({ summary: summaryBodyWithoutAlerts(), alerts: 'absent' })
    expect(bindings.alertFailure.value).toMatchObject({ face: 'denied', title: RISK_DENIED_TITLE, codeLabel: '', retryable: false })
    expect(bindings.alertRows.value).toEqual([])
    expect(html).toContain('data-testid="ui-error-state"')
    expect(html).toContain(RISK_DENIED_TITLE)
    expect(html).toContain('员工账号默认没有这一项')
    expect(html).not.toContain('data-testid="ui-error-retry"')
  })

  it('把没权限说成「当前没有异常线索」就是假话：这句与空态那张脸一个字都不许重叠', async () => {
    const { html } = await loadedPanel({ summary: summaryBodyWithoutAlerts(), alerts: 'absent' })
    expect(html).not.toContain(EMPTY_TITLE)
    expect(html).not.toContain(ALERTS_EMPTY_DESCRIPTION)
  })

  it('句子出自字典层：这一张脸里不许出现后端码名，也不许新造裸句子', async () => {
    const view = alertsNotOpenView(RISK_ARGS)
    expect(view.description).not.toMatch(/permission_denied|[a-z]+_[a-z]+/)
    expect(view.description.startsWith('当前账号没有这项权限，请联系管理员开通。')).toBe(true)
    // 与 403 那张脸同源同句：同一件事在两处只说一遍，第二处不许自己另编一句。
    expect(view.description).toBe(readFailureView(axiosError(403, 'permission_denied'), RISK_ARGS).description)
    expect(view.title).toBe(readFailureView(axiosError(403, 'permission_denied'), RISK_ARGS).title)
  })

  it('告警数字位仍是「无权限查看告警」，不跟着这一格改成 0', async () => {
    const { html } = await loadedPanel({ summary: summaryBodyWithoutAlerts(), alerts: 'absent' })
    const tile = html.slice(html.indexOf('data-testid="dashboard-kpi-alerts"'))
    const block = tile.slice(0, tile.indexOf('</button>'))
    expect(block).toContain('>' + COUNT_PLACEHOLDER + '<')
    expect(block).toContain('无权限查看告警')
  })
})

describe('R285③ · 有读权那一发照发：admin 那一格一个真数都不许多丢', () => {
  it('admin 一次加载：三条 GET 一条不少，/alerts 恰好一发，真行照常上屏', async () => {
    const { bindings, html } = await loadedPanel({ summary: summaryBody(), alerts: { status: 200, data: { alerts: ADMIN_ROWS } } })
    expect(gets()).toEqual(['/alerts', '/documents/catalog', SUMMARY_PATH].sort())
    expect(http.get.mock.calls.filter(call => call[0] === '/alerts')).toHaveLength(1)
    expect(bindings.alertFailure.value).toBe(null)
    expect(html).toContain('华东区差旅费本月已超阈值')
    expect(html).toContain('研发费用环比波动超过设定值')
    expect(html.match(/data-testid="dashboard-risk-row"/g)).toHaveLength(2)
    expect(html).not.toContain(RISK_DENIED_TITLE)
    expect(html).not.toContain(EMPTY_TITLE)
  })

  it('200 真空列表仍是空态：那一发发了、读了、真的没有，这句话才轮得到上屏', async () => {
    const { bindings, html } = await loadedPanel({ summary: summaryBody(), alerts: { status: 200, data: { alerts: [] } } })
    expect(gets()).toContain('/alerts')
    expect(bindings.alertFailure.value).toBe(null)
    expect(html).toContain(EMPTY_TITLE)
    expect(html).toContain(ALERTS_EMPTY_DESCRIPTION)
    expect(html).not.toContain(RISK_DENIED_TITLE)
  })

  it('有键却 403（权限中途被收）仍走读失败那张 denied 脸：这一发发了就不许改口成沉默', async () => {
    const { bindings, html } = await loadedPanel({ summary: summaryBody(), alerts: { status: 403, detail: 'permission_denied' } })
    expect(gets()).toContain('/alerts')
    expect(bindings.alertFailure.value.face).toBe('denied')
    expect(html).toContain(RISK_DENIED_TITLE)
    expect(html).not.toContain(EMPTY_TITLE)
  })
})

describe('R285④ · 四张脸两两不等（G4）', () => {
  const faces = async () => {
    const notOpen = alertsNotOpenView(RISK_ARGS)
    const unauthorized = readFailureView(axiosError(401, 'authentication_required'), RISK_ARGS)
    const broken = readFailureView(axiosError(500, 'internal_error'), RISK_ARGS)
    const empty = { face: 'empty', title: EMPTY_TITLE, description: ALERTS_EMPTY_DESCRIPTION }
    return [notOpen, unauthorized, broken, empty]
  }

  it('没权限／401／真读失败／真空列表：标题与正文两两都不许共用', async () => {
    const list = await faces()
    for (let i = 0; i < list.length; i += 1) {
      for (let j = i + 1; j < list.length; j += 1) {
        expect(list[i].title + '|' + list[i].description, '两张脸共用了一句话：' + i + ' 与 ' + j).not.toBe(list[j].title + '|' + list[j].description)
      }
    }
  })

  it('canReadAlerts 为 false 与「读了但失败」是两句话，两句都不给重试', async () => {
    const notOpen = alertsNotOpenView(RISK_ARGS)
    const broken = readFailureView(axiosError(500, 'internal_error'), RISK_ARGS)
    expect(notOpen.description).not.toBe(broken.description)
    expect(notOpen.retryable).toBe(false)
    expect(broken.retryable).toBe(false)
    expect(notOpen.face).toBe('denied')
    expect(broken.face).toBe('error')
  })

  it('取数出口还在：fetchAlerts 仍读 GET /alerts，这一屏只是没资格问，不是把问句也改了', async () => {
    http.get.mockResolvedValue({ status: 200, data: { alerts: [{ id: 1 }] } })
    expect(await fetchAlerts()).toHaveLength(1)
    expect(http.get).toHaveBeenCalledWith('/alerts')
  })
})

describe('R285⑤ · 源码形状：闸门只有一处，第三态不吃空态原语', () => {
  it('loadRiskRows 先问 canReadAlerts，权限判定在 lib，面板里不长第三处 isPermissionDenied', () => {
    const s = panelSource()
    expect(s).toMatch(/async function loadRiskRows\(\) \{[\s\S]*?if \(!canReadAlerts\(summary\.value\)\) \{[\s\S]*?alertsNotOpenView\(\{ deniedTitle: RISK_DENIED_TITLE \}\)[\s\S]*?\n  \}/)
    expect(s.match(/isPermissionDenied\(err\)/g)).toHaveLength(2)
  })

  it('第三态吃 UiErrorState，不吃第四枚 UiEmptyState：空态原语仍只有三处', () => {
    const s = panelSource()
    expect(s.match(/<UiEmptyState/g)).toHaveLength(3)
    expect(s).toMatch(/v-if="alertFailure"[\s\S]*?:retryable="alertFailure\.retryable"[\s\S]*?v-else-if="alertRows\.length"/)
  })
})
