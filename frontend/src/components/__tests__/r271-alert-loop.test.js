/**
 * R271 · 块 C「告警闭环」：三件动作就地做完，处理人与处理时间必须留在屏上
 * （判据 ① 就地处置＋刷新可见、③ 四张读脸与六张处置脸互不顶替、④ G18 不写死数字、⑤ 反证钉）
 *
 * 环境仍然只有 node + @vue/server-renderer（仓里没有 jsdom / @vue/test-utils，也不许 npm i），
 * 所以这一件能证的事到「真 setup() 绑定 + 组件自己 ssrRender 出来的 HTML」这一层为止：
 *   · 真取数：只换 lib/http 那一枚 axios 实例，errorDetail / errorCodeOf 保持真身；
 *   · 真状态机：makeServer 是一枚会自己记账的假服务端，按后端 app/api/v1/alerts.py
 *     :326-339 的合法跳转、:342-346 的写列、:145-146 的请求体形状、:548-556 的拒绝码办事。
 *     面板说什么，取决于它到底写没写进去、重读回没读回来 —— 屏上那一版不是测试替它铺好的；
 *   · 真上屏：断言读的是 HTML，不是内部状态。摘掉「处理人 / 时间」那两格，本件当场红。
 * 没有 DOM 就点不了真按钮：下面凡「点击」一律直接调组件自己的处理函数，
 * 而「按钮点不动」回到 HTML 上的 disabled / aria-busy 去读。这一层的边界写在交回里。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'

// 只换网络层：判脸的 errorDetail / errorCodeOf 走真身，mock 改不动它们。
vi.mock('../../lib/http', async importOriginal => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }
})

import { http } from '../../lib/http'
import {
  ALERTS_EMPTY_TITLE,
  ALERTS_PATH,
  ALERT_ACTION_NOTES,
  ALERT_STATUS_UNKNOWN,
  DISPOSED_BUT_UNREADABLE,
  DISPOSAL_FAILURE_TITLES,
  INVALID_ID_FAILURE,
  PERMISSION_WHERE,
  RULES_PATH,
  UNATTRIBUTED_DEPARTMENT,
  UNRECORDED,
} from '../../lib/alerts'
import InsightPanel from '../InsightPanel.vue'

const source = name => readFileSync(new URL('../' + name, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const libSource = name => readFileSync(new URL('../../lib/' + name, import.meta.url), 'utf8').replace(/\r\n/g, '\n')

/** 后端码名不许出现在给人看的句子里（与 insight-alerts.test.js 同一条口径）。 */
const SNAKE = /[a-z][a-z0-9]*_[a-z0-9_]+/

/** 假服务端盖处理时间用的那一对值：屏上必须出现格式化后的 STAMP，而不是前端自己算的现在。 */
const ACTOR = 'zhangli'
const STAMP_RAW = '2026-09-26T14:03:07+08:00'
const STAMP = '2026-09-26 14:03'

/** 剥掉块注释 / HTML 注释 / 行注释后的代码体：历史说明只许留在注释里。 */
function codeOnly(text) {
  return text
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter(line => !/^\s*\/\//.test(line))
    .join('\n')
}

/** 只留屏上真正给人读的正文：剥注释与标签。 */
function visibleText(html) {
  return html.replace(/<!--[\s\S]*?-->/g, ' ').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
}

/** axios 的真形状：{ response: { status, data: { detail } } }。 */
function httpError(status, code) {
  return { response: { status, data: { detail: code } }, message: 'Request failed with status code ' + status }
}

/** 后端一行真发的 15 列（列集由 r271-alert-contract.test.js 现读后端钉住），默认是一格 open 空账。 */
function rawRow(overrides) {
  return Object.assign({
    id: 7,
    rule_id: 3,
    message: '差旅费合计 12800 大于阈值 8000',
    ai_analysis: '集中在 9 月，环比上升明显。',
    department: '市场部',
    read: false,
    status: 'open',
    acknowledged_by: '',
    acknowledged_at: '',
    closed_by: '',
    closed_at: '',
    assignee: '',
    assigned_by: '',
    assigned_at: '',
    created_at: '2026-09-26T09:12:44+08:00',
  }, overrides || {})
}
/**
 * 一枚会自己记账的「服务端」。它只干后端干的事：判合法跳转、写列、按归属回读，
 * 面板画成什么样由它的账本决定。opts 是几枚可控缺口，用来钉「不许替后端补数据」：
 *   failReadsAfter  第 N 次之后 GET /alerts 一律 500：钉「写成却读不回来」那张降级脸
 *   writePolicy     echo_only = 回成功、回执里有行，可账本上什么都没写：钉「没有被记上」
 *   echo            drop_actor = 交回的行没有处理人；no_row = 压根不交回 alert 这一枚
 *   hang            POST 挂在半空：用在飞那一张屏（三枚动作一起熄）
 *   assignable      转派白名单：不在册的用户名一律 400 validation_error（后端四格合一）
 *   failPost        按需注入拒绝码，判据③ 的六张脸由它喂出来
 */
function makeServer(rows, opts) {
  const options = opts || {}
  const server = { rows: rows.map(row => ({ ...row })), alertsReads: 0, posts: [], pending: [] }
  http.get.mockImplementation(async url => {
    if (url === ALERTS_PATH) {
      server.alertsReads += 1
      if (options.failReadsAfter !== undefined && server.alertsReads > options.failReadsAfter) {
        throw httpError(500, 'internal_error')
      }
      return { data: { alerts: server.rows.map(row => ({ ...row })) } }
    }
    if (url === RULES_PATH) return { data: { rules: options.rules === undefined ? [] : options.rules } }
    throw new Error('未预期的 GET 路径：' + url)
  })
  http.post.mockImplementation(async (url, body) => {
    const hit = /^\/alerts\/([^/]+)\/(ack|close|assign)$/.exec(url)
    if (!hit) throw new Error('未预期的 POST 路径：' + url)
    server.posts.push({ url, body })
    if (options.failPost) {
      const err = options.failPost(url, body)
      if (err) throw err
    }
    if (options.hang) await new Promise(resolve => server.pending.push(resolve))
    const row = server.rows.find(item => String(item.id) === decodeURIComponent(hit[1]))
    if (!row) throw httpError(404, 'resource_not_found')
    const action = hit[2]
    const legalFrom = action === 'ack' ? ['open'] : ['open', 'acknowledged']
    if (legalFrom.indexOf(row.status) < 0) throw httpError(409, 'conflict')
    const echo = { ...row }
    const writes = options.writePolicy !== 'echo_only'
    if (action === 'assign') {
      // 后端 AlertAssignCreate 只有一枚 assignee：多带一格就是 400（客户端不许代填人与时）
      const keys = Object.keys(body && typeof body === 'object' ? body : {})
      if (keys.length !== 1 || keys[0] !== 'assignee') throw httpError(400, 'validation_error')
      const target = typeof body.assignee === 'string' ? body.assignee.trim() : ''
      if (!target || (options.assignable && options.assignable.indexOf(target) < 0)) {
        throw httpError(400, 'validation_error')
      }
      if (writes) { row.assignee = target; row.assigned_by = ACTOR; row.assigned_at = STAMP_RAW }
      echo.assignee = target; echo.assigned_by = ACTOR; echo.assigned_at = STAMP_RAW
    } else {
      // ack / close 两枚 handler 没有请求体：多发一格，本件当场红
      if (body !== undefined) throw new Error(action + ' 后端不收请求体，前端多发了：' + JSON.stringify(body))
      if (action === 'ack') {
        if (writes) { row.status = 'acknowledged'; row.acknowledged_by = ACTOR; row.acknowledged_at = STAMP_RAW }
        echo.status = 'acknowledged'; echo.acknowledged_by = ACTOR; echo.acknowledged_at = STAMP_RAW
      } else {
        if (writes) { row.status = 'closed'; row.closed_by = ACTOR; row.closed_at = STAMP_RAW }
        echo.status = 'closed'; echo.closed_by = ACTOR; echo.closed_at = STAMP_RAW
      }
    }
    if (options.echo === 'no_row') return { data: {} }
    if (options.echo === 'drop_actor') {
      echo.acknowledged_by = ''; echo.closed_by = ''; echo.assigned_by = ''
    }
    return { data: { alert: echo } }
  })
  server.release = () => {
    const waiters = server.pending.splice(0)
    waiters.forEach(done => done())
  }
  return server
}

/** 跑真组件的 setup() 取回真绑定；ref 不解包，一律写 .value。 */
async function mountBindings(component) {
  let bindings = null
  const Probe = {
    name: 'R271Probe',
    setup(props, ctx) {
      bindings = component.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Probe))
  expect(bindings, '组件应暴露可调用的 setup()').toBeTruthy()
  return bindings
}

/** 同一份绑定交回组件自己的 ssrRender 渲染整屏（vitest 下产出的是 ssrRender，没有 render）。 */
const renderState = bindings => renderToString(h({ ...InsightPanel, setup: () => bindings }))

/** 装好服务端并走完首屏读取：返回服务端账本、真绑定、当前这一行的视图模型取法。 */
async function openPanel(serverRows, opts) {
  const server = makeServer(serverRows || [rawRow()], opts)
  const bindings = await mountBindings(InsightPanel)
  await bindings.loadAll()
  return { server, bindings, html: () => renderState(bindings) }
}

/** askCloseAlert / confirmAssign 这些同步入口后面的 Promise 链只能靠让宏任务转圈来收。 */
async function settled(times) {
  for (let i = 0; i < (times || 10); i += 1) await new Promise(resolve => setTimeout(resolve, 0))
}

/** 屏上那三行台账：一行一句「谁 · 什么时候」，顺序固定是 确认 / 关闭 / 指派。 */
function ledgerLines(html) {
  return (html.match(/data-testid="alert-ledger-line"[\s\S]*?<\/p>/g) || []).map(visibleText)
}

/** alerts 这一张卡自己的 HTML：判「列表有没有退成空态」只能看它，不能被规则卡的空态连坐。 */
function alertsCard(html) {
  const start = html.indexOf('data-testid="alerts-card"')
  if (start < 0) return ''
  const end = html.indexOf('</section>', start)
  return html.slice(start, end < 0 ? html.length : end)
}

/** 回执条 / 失败条自己的那一段 HTML（截到本卡收尾），判「上屏」而不是判内部状态对象。 */
function actionStrip(html, testId) {
  const start = html.indexOf('data-testid="' + testId + '"')
  if (start < 0) return ''
  const end = html.indexOf('</section>', start)
  return html.slice(start, end < 0 ? html.length : end)
}

/** 按钮在屏上到底点不点得动：读 SSR 出来的 disabled，不是读 canDispose() 的返回值。 */
function buttonTag(html, testId) {
  const tags = html.match(/<button[^>]*>/g) || []
  return tags.find(tag => tag.includes('data-testid="' + testId + '"')) || ''
}

beforeEach(() => {
  vi.clearAllMocks()
  http.delete.mockResolvedValue({ data: { status: 'ok' } })
})
describe('R271 判据① · 确认：就地做完，处理人与处理时间留在屏上', () => {
  it('确认发出 POST /alerts/{id}/ack 且不带请求体，写完必须再按 GET /alerts 重读一次', async () => {
    const { server, bindings } = await openPanel()
    await bindings.runDisposal(bindings.alerts.value[0], 'ack')
    expect(server.posts.map(item => item.url)).toEqual(['/alerts/7/ack'])
    expect(server.posts[0].body).toBeUndefined()
    // 一次处置 = 一发 POST + 一次重读；首屏已经读过一次，所以这里是 2。
    expect(server.alertsReads).toBe(2)
    expect(bindings.alerts.value[0].status).toBe('acknowledged')
    expect(bindings.actionFailure.value).toBe(null)
  })

  it('确认之后的台账第一行真把「谁 · 几点」画上屏，回执只作补充', async () => {
    const { bindings, html } = await openPanel()
    await bindings.runDisposal(bindings.alerts.value[0], 'ack')
    const page = await html()
    const lines = ledgerLines(page)
    expect(lines).toHaveLength(3)
    expect(page).toMatch(/data-recorded="yes"[\s\S]*?data-testid="alert-ledger-line"/)
    expect(lines[0]).toContain('确认')
    expect(lines[0]).toContain(ACTOR)
    expect(lines[0]).toContain(STAMP)
    expect(lines[1]).toContain(UNRECORDED)
    expect(lines[2]).toContain(UNRECORDED)
    expect(visibleText(page)).toContain('已确认，待处理')
    const strip = actionStrip(page, 'alert-action-receipt')
    expect(visibleText(strip)).toContain('确认已经记到台账上')
    expect(visibleText(strip)).toContain(ACTOR)
    expect(bindings.actionReceipt.value.kind).toBe('done')
  })

  it('后端只回「成功」不回行：屏上的人与时间仍来自重读，不是回执缓存', async () => {
    const { server, bindings, html } = await openPanel(null, { echo: 'no_row' })
    await bindings.runDisposal(bindings.alerts.value[0], 'ack')
    expect(server.alertsReads).toBe(2)
    const page = await html()
    expect(ledgerLines(page)[0]).toContain(ACTOR)
    expect(ledgerLines(page)[0]).toContain(STAMP)
    expect(bindings.actionReceipt.value.kind).toBe('done')
  })

  it('回执把处理人抹掉：以重读回来的那一版为准，屏上不跟着变空', async () => {
    const { bindings, html } = await openPanel(null, { echo: 'drop_actor' })
    await bindings.runDisposal(bindings.alerts.value[0], 'ack')
    const page = await html()
    expect(ledgerLines(page)[0]).toContain(ACTOR)
    expect(bindings.alerts.value[0].ledger[0].who).toBe(ACTOR)
  })

  it('刷新＝重新打开这一页：谁处理过、几点处理过，还在服务端交回的那一格里', async () => {
    const first = await openPanel()
    await first.bindings.runDisposal(first.bindings.alerts.value[0], 'ack')
    expect(first.server.rows[0].acknowledged_by).toBe(ACTOR)
    // 换一枚全新的组件实例（等价于离开这一页再回来），账本还是同一份。
    const reopened = await openPanel(first.server.rows)
    const page = await reopened.html()
    expect(visibleText(page)).toContain('已确认，待处理')
    expect(ledgerLines(page)[0]).toContain(ACTOR)
    expect(ledgerLines(page)[0]).toContain(STAMP)
    expect(reopened.bindings.actionReceipt.value).toBe(null)
  })

  it('一笔写在飞时这一行三枚动作一起熄：HTML 上是真 disabled，不是话术', async () => {
    const { server, bindings, html } = await openPanel(null, { hang: true })
    const flying = bindings.runDisposal(bindings.alerts.value[0], 'ack')
    await settled(2)
    const row = bindings.alerts.value[0]
    expect(bindings.disposing.value).toBe('ack:7')
    expect([bindings.canDispose('ack', row), bindings.canDispose('close', row), bindings.canDispose('assign', row)])
      .toEqual([false, false, false])
    const page = await html()
    expect(buttonTag(page, 'alert-ack')).toMatch(/\bdisabled\b/)
    expect(buttonTag(page, 'alert-ack')).toContain('aria-busy="true"')
    expect(buttonTag(page, 'alert-close')).toMatch(/\bdisabled\b/)
    expect(buttonTag(page, 'alert-assign')).toMatch(/\bdisabled\b/)
    server.release()
    await flying
    expect(server.posts).toHaveLength(1)
    expect(bindings.disposing.value).toBe('')
  })
})

describe('R271 判据① · 关闭：两下才发，发完这一条到此为止', () => {
  it('第一下只把「确认关闭？」点亮在这一行，一个请求都不发', async () => {
    const { server, bindings } = await openPanel()
    const row = bindings.alerts.value[0]
    bindings.askCloseAlert(row)
    expect(server.posts).toHaveLength(0)
    expect(bindings.closeLabel(row)).toBe('确认关闭？')
    expect(bindings.closeLabel(bindings.alerts.value[0])).toBe('确认关闭？')
  })

  it('第二下发 POST /alerts/{id}/close 且不带请求体，之后三枚动作全不再点亮', async () => {
    const { server, bindings, html } = await openPanel()
    bindings.askCloseAlert(bindings.alerts.value[0])
    bindings.askCloseAlert(bindings.alerts.value[0])
    await settled()
    expect(server.posts.map(item => item.url)).toEqual(['/alerts/7/close'])
    expect(server.posts[0].body).toBeUndefined()
    const page = await html()
    const text = visibleText(page)
    expect(text).toContain('已关闭')
    expect(text).toContain('已关闭是终态')
    expect(ledgerLines(page)[1]).toContain(ACTOR)
    expect(ledgerLines(page)[1]).toContain(STAMP)
    for (const testId of ['alert-ack', 'alert-close', 'alert-assign']) {
      expect(buttonTag(page, testId)).toMatch(/\bdisabled\b/)
    }
  })

  it('错位点击不顶替：两行时第二行的一下不会关掉第一行', async () => {
    const rows = [rawRow({ id: 7 }), rawRow({ id: 8 })]
    const { server, bindings } = await openPanel(rows)
    const [a, b] = bindings.alerts.value
    bindings.askCloseAlert(a)
    bindings.askCloseAlert(b)
    await settled()
    expect(server.posts).toHaveLength(0)
    expect(bindings.pendingCloseId.value).toBe('8')
    expect(bindings.closeLabel(a)).toBe('关闭')
    expect(bindings.closeLabel(b)).toBe('确认关闭？')
  })

  it('三枚按钮的 :title 写明后果，关闭那句必须说「不等于问题已被修好」', async () => {
    const { bindings, html } = await openPanel()
    const page = await html()
    expect(buttonTag(page, 'alert-ack')).toContain(ALERT_ACTION_NOTES.ack)
    expect(buttonTag(page, 'alert-close')).toContain('关闭是终态')
    expect(buttonTag(page, 'alert-close')).toContain('关闭不等于问题已被修好')
    expect(buttonTag(page, 'alert-assign')).toContain('指派只换「现在归谁」，不改处置状态')
    expect(bindings.rowActionNote(bindings.alerts.value[0])).toBe('')
  })
})

describe('R271 判据① · 指派：只换「现在归谁」，不改处置状态', () => {
  it('草稿空着就点发送：一个请求都不发，屏上说清要填登录用户名', async () => {
    const { server, bindings, html } = await openPanel()
    const row = bindings.alerts.value[0]
    bindings.openAssign(row)
    bindings.confirmAssign(row)
    await settled()
    expect(server.posts).toHaveLength(0)
    expect(bindings.assignErrors.value['7']).toContain('请填写要派给谁')
    const page = await html()
    expect(page).toContain('data-testid="assign-form"')
    expect(visibleText(page)).toContain('请填写要派给谁')
  })

  it('请求体只有一枚 assignee（草稿去空格），派出的人与被派的人一起上屏', async () => {
    const { server, bindings, html } = await openPanel(null, { assignable: ['linan', 'wangqiang'] })
    const row = bindings.alerts.value[0]
    bindings.openAssign(row)
    bindings.setAssignDraft(row, '  wangqiang  ')
    bindings.confirmAssign(row)
    await settled()
    expect(server.posts).toHaveLength(1)
    expect(server.posts[0].url).toBe('/alerts/7/assign')
    expect(server.posts[0].body).toEqual({ assignee: 'wangqiang' })
    const page = await html()
    expect(visibleText(page)).toContain('派给 wangqiang')
    expect(ledgerLines(page)[2]).toContain(ACTOR)
    expect(ledgerLines(page)[2]).toContain(STAMP)
    expect(visibleText(page)).toContain('还没人处理')
    expect(visibleText(page)).not.toContain('已确认，待处理')
    expect(bindings.actionReceipt.value.kind).toBe('done')
    expect(bindings.actionReceipt.value.title).toBe('指派已经记到台账上')
  })

  it('转派成功后草稿与展开框一起收：屏上不留一个已经发出去的用户名', async () => {
    const { bindings } = await openPanel(null, { assignable: ['wangqiang'] })
    const row = bindings.alerts.value[0]
    bindings.openAssign(row)
    bindings.setAssignDraft(row, 'wangqiang')
    bindings.confirmAssign(row)
    await settled()
    expect(bindings.assignOpen.value).toBe('')
    expect(bindings.assignDrafts.value['7']).toBe('')
  })

  it('派给后端不认的人 -> 「转派没有成立」：四格合一，绝不猜是哪一格没过', async () => {
    const { server, bindings, html } = await openPanel(null, { assignable: ['linan', 'wangqiang'] })
    const row = bindings.alerts.value[0]
    bindings.openAssign(row)
    bindings.setAssignDraft(row, 'meiyouzhegeRen')
    bindings.confirmAssign(row)
    await settled()
    expect(server.posts).toHaveLength(1)
    expect(bindings.actionFailure.value.face).toBe('rejected')
    expect(bindings.actionFailure.value.title).toBe(DISPOSAL_FAILURE_TITLES.rejected)
    const page = await html()
    const strip = visibleText(actionStrip(page, 'alert-action-failure'))
    expect(strip).toContain('转派没有成立')
    expect(strip).toContain('查无此人、账号停用、没有这项权限、看不到这一条')
    expect(bindings.alerts.value[0].ledger[2].who).toBe(UNRECORDED)
    expect(bindings.alerts.value[0].ledger[2].to).toBe(UNRECORDED)
  })
})
/** 判据③：喂真码进真 handler 链，读回来的脸由组件自己算。 */
const FAILURE_SPECS = [
  { name: 'unauthorized', status: 401, code: 'authentication_required', action: 'ack' },
  { name: 'denied', status: 403, code: 'permission_denied', action: 'ack' },
  { name: 'notFound', status: 404, code: 'resource_not_found', action: 'ack' },
  { name: 'conflict', status: 409, code: 'conflict', action: 'ack' },
  { name: 'rejected', status: 400, code: 'validation_error', action: 'assign', assignee: 'linan' },
  { name: 'error', status: 500, code: 'internal_error', action: 'ack' },
]

async function failureFace(spec, failTimes) {
  const rows = spec.action === 'assign' ? [rawRow({ assignee: '', assigned_by: '', assigned_at: '' })] : [rawRow()]
  // failTimes 只给「再试一次」那一枚用例用：第一发必被拒、第二发放行，才看得出重试真把动作重发了一次。
  let remaining = failTimes === undefined ? Infinity : failTimes
  const { server, bindings, html } = await openPanel(rows, {
    assignable: ['linan', 'wangqiang'],
    failPost: () => {
      if (remaining <= 0) return null
      remaining -= 1
      return httpError(spec.status, spec.code)
    },
  })
  const row = bindings.alerts.value[0]
  if (spec.action === 'assign') {
    bindings.openAssign(row)
    bindings.setAssignDraft(row, spec.assignee)
    bindings.confirmAssign(row)
  } else {
    await bindings.runDisposal(row, spec.action)
  }
  await settled()
  return { spec, server, bindings, page: await html() }
}

describe('R271 判据③ · 处置的六张脸互不顶替，且一张都不许退成读列表那几张', () => {
  it('六种真拒绝码走出六张不同的脸：face / 标题 / 屏上正文两两不等', async () => {
    const runs = []
    for (const spec of FAILURE_SPECS) runs.push(await failureFace(spec))
    expect(runs.map(item => item.spec.name)).toEqual(['unauthorized', 'denied', 'notFound', 'conflict', 'rejected', 'error'])
    for (const item of runs) {
      expect(item.bindings.actionFailure.value.face).toBe(item.spec.name)
      expect(item.bindings.actionFailure.value.title).toBe(DISPOSAL_FAILURE_TITLES[item.spec.name])
      expect(visibleText(item.page)).toContain(DISPOSAL_FAILURE_TITLES[item.spec.name])
    }
    for (const key of ['face', 'title']) {
      const values = runs.map(item => item.bindings.actionFailure.value[key])
      expect(new Set(values).size, key + ' 这一维不许有两张脸重合').toBe(FAILURE_SPECS.length)
    }
    const bodies = runs.map(item => visibleText(actionStrip(item.page, 'alert-action-failure')))
    expect(new Set(bodies).size).toBe(FAILURE_SPECS.length)
  })

  it('任何一张处置失败都不把列表退成空态、也不退成读失败', async () => {
    for (const spec of FAILURE_SPECS) {
      const item = await failureFace(spec)
      const card = alertsCard(item.page)
      expect(item.bindings.alertsFace.value, spec.name + ' 之后列表还得在').toBe('list')
      expect(card).toContain('data-testid="alert-rows"')
      expect(card).not.toContain('data-testid="ui-empty-state"')
      expect(visibleText(card)).not.toContain(ALERTS_EMPTY_TITLE)
      expect(visibleText(card)).toContain(rawRow().message)
      expect(card).toContain('data-testid="alert-action-failure"')
    }
  })

  it('没权限说的是「处置告警的权限」：绝不顺口说成看不到数据，也不给重试按钮', async () => {
    const item = await failureFace(FAILURE_SPECS[1])
    const strip = visibleText(actionStrip(item.page, 'alert-action-failure'))
    expect(strip).toContain('这个账号没有处置告警的权限')
    expect(item.page).not.toContain('这个账号没有查看告警的权限')
    expect(strip).toContain(PERMISSION_WHERE)
    expect(item.page).not.toContain('data-testid="ui-error-retry"')
    expect(item.bindings.actionFailure.value.retryable).toBe(false)
  })

  it('登录失效不给重试、真坏了才给：两件事不是一张脸', async () => {
    const lost = await failureFace(FAILURE_SPECS[0])
    expect(visibleText(actionStrip(lost.page, 'alert-action-failure'))).toContain('登录状态已失效')
    expect(lost.page).not.toContain('data-testid="ui-error-retry"')
    const broken = await failureFace(FAILURE_SPECS[5], 1)
    expect(broken.bindings.actionFailure.value.retryable).toBe(true)
    expect(broken.page).toContain('data-testid="ui-error-retry"')
    // 再试一次真把同一枚动作重发出去，而不是只擦掉那条红字。
    await broken.bindings.retryDisposal()
    await settled()
    expect(broken.server.posts.map(post => post.url)).toEqual(['/alerts/7/ack', '/alerts/7/ack'])
    expect(broken.bindings.actionFailure.value).toBe(null)
    expect(broken.bindings.actionReceipt.value.kind).toBe('done')
  })

  it('404 与 409 会说「屏上这一版不作数」并顺手重读；403 不重读', async () => {
    const gone = await failureFace(FAILURE_SPECS[2])
    expect(gone.server.alertsReads).toBe(2)
    expect(gone.bindings.actionFailure.value.reload).toBe(true)
    const moved = await failureFace(FAILURE_SPECS[3])
    expect(moved.server.alertsReads).toBe(2)
    expect(moved.bindings.actionFailure.value.reload).toBe(true)
    const denied = await failureFace(FAILURE_SPECS[1])
    expect(denied.server.alertsReads).toBe(1)
    expect(denied.bindings.actionFailure.value.reload).toBe(false)
  })

  it('把 ack 打回的 400 不许冒充「转派没有成立」', async () => {
    const item = await failureFace({ status: 400, code: 'validation_error', action: 'ack', name: 'error' })
    expect(item.bindings.actionFailure.value.face).toBe('error')
    expect(item.bindings.actionFailure.value.title).toBe(DISPOSAL_FAILURE_TITLES.error)
  })

  it('六张脸都不许漏出后端码名，而且都得点名说的是哪一条', async () => {
    for (const spec of FAILURE_SPECS) {
      const item = await failureFace(spec)
      const strip = visibleText(actionStrip(item.page, 'alert-action-failure'))
      expect(strip).not.toMatch(SNAKE)
      expect(strip).toContain('说的是这一条（编号 7）：' + rawRow().message)
    }
  })
})

describe('R271 判据①② · 写成却读不回来、回成功却没记账：都是降级，不是成功也不是空', () => {
  it('处置写成了但列表重读失败 -> 降级那张脸，既不宣布记上了也不画成空账', async () => {
    const { server, bindings, html } = await openPanel(null, { failReadsAfter: 1 })
    await bindings.runDisposal(bindings.alerts.value[0], 'ack')
    expect(server.alertsReads).toBe(2)
    expect(bindings.alertsFace.value).toBe('error')
    expect(bindings.actionReceipt.value.kind).toBe('degraded')
    expect(bindings.actionReceipt.value.title).toBe(DISPOSED_BUT_UNREADABLE.title)
    const page = await html()
    const strip = visibleText(actionStrip(page, 'alert-action-receipt'))
    expect(strip).toContain(DISPOSED_BUT_UNREADABLE.title)
    expect(strip).not.toContain('已经记到台账上')
    expect(page).not.toContain(ALERTS_EMPTY_TITLE)
    expect(bindings.actionFailure.value).toBe(null)
  })

  it('后端回成功却没写进账 -> 明说「没有被记上」，屏上一个处理人都不许出现', async () => {
    const { server, bindings, html } = await openPanel(null, { writePolicy: 'echo_only' })
    await bindings.runDisposal(bindings.alerts.value[0], 'ack')
    expect(server.rows[0].acknowledged_by).toBe('')
    expect(server.rows[0].status).toBe('open')
    expect(bindings.actionReceipt.value.kind).toBe('degraded')
    expect(bindings.actionReceipt.value.title).toContain('没有被记上')
    const page = await html()
    expect(visibleText(page)).not.toContain(ACTOR)
    expect(ledgerLines(page)[0]).toContain(UNRECORDED)
  })

  it('一条处置都没做的空账：三行都写「未记录」，一格都不许空着冒充', async () => {
    const { html } = await openPanel()
    const page = await html()
    const lines = ledgerLines(page)
    expect(lines).toHaveLength(3)
    for (const line of lines) {
      expect(line).toContain(UNRECORDED)
      expect(page).toContain('data-recorded="no"')
    }
    expect(page).not.toMatch(/class="ledger-who"><\/span>/)
  })

  it('后端已处置的行逐列上屏：谁确认、谁关闭、谁派的、派给谁、分别是几点', async () => {
    const rows = [rawRow({
      status: 'acknowledged',
      acknowledged_by: 'linan',
      acknowledged_at: '2026-09-25T08:01:00+08:00',
      closed_by: 'wangqiang',
      closed_at: '2026-09-25T18:22:00+08:00',
      assignee: 'chenjie',
      assigned_by: 'zhaomin',
      assigned_at: '2026-09-25T09:09:00+08:00',
    })]
    const { bindings, html } = await openPanel(rows)
    const page = await html()
    const lines = ledgerLines(page)
    expect(lines[0]).toContain('linan')
    expect(lines[0]).toContain('2026-09-25 08:01')
    expect(lines[1]).toContain('wangqiang')
    expect(lines[1]).toContain('2026-09-25 18:22')
    expect(lines[2]).toContain('zhaomin')
    expect(lines[2]).toContain('派给 chenjie')
    expect(lines[2]).toContain('2026-09-25 09:09')
    expect(bindings.alerts.value[0].handled).toBe(true)
  })
})
describe('R271 判据② · 取不到的列走「未记录」，认不下的值不猜', () => {
  it('词表外的处置状态：三枚动作全不点亮，屏上说「认不下就不猜」，原词不上屏', async () => {
    const { server, bindings, html } = await openPanel([rawRow({ status: 'snoozed' })])
    const row = bindings.alerts.value[0]
    expect(row.statusKnown).toBe(false)
    expect(row.status).toBe('')
    expect(row.actions).toEqual([])
    const page = await html()
    expect(visibleText(page)).toContain(ALERT_STATUS_UNKNOWN)
    expect(visibleText(page)).toContain('认不下就不猜')
    expect(page).not.toContain('snoozed')
    for (const testId of ['alert-ack', 'alert-close', 'alert-assign']) {
      expect(buttonTag(page, testId)).toMatch(/\bdisabled\b/)
    }
    await bindings.runDisposal(row, 'ack')
    expect(server.posts).toHaveLength(0)
  })

  it('编号读不出来的那一行：动作发不出去，但这跟「没有权限」是两件事', async () => {
    const { server, bindings, html } = await openPanel([rawRow({ id: '' })])
    const row = bindings.alerts.value[0]
    expect(row.addressable).toBe(false)
    const page = await html()
    expect(visibleText(page)).toContain('这一行没有可用的编号')
    expect(visibleText(page)).not.toContain('没有权限')
    for (const testId of ['alert-ack', 'alert-close', 'alert-assign']) {
      expect(buttonTag(page, testId)).toMatch(/\bdisabled\b/)
    }
    await bindings.runDisposal(row, 'ack')
    expect(server.posts).toHaveLength(0)
  })

  it('编号非数字：真按一次按钮也不发请求，回执说的是「没有可用的编号」', async () => {
    const { server, bindings } = await openPanel([rawRow({ id: 'not-a-number' })])
    const row = bindings.alerts.value[0]
    await bindings.runDisposal(row, 'ack')
    expect(server.posts).toHaveLength(0)
    expect(bindings.actionFailure.value.face).toBe('invalidId')
    expect(bindings.actionFailure.value.title).toBe(INVALID_ID_FAILURE.title)
    expect(server.alertsReads).toBe(2)
  })

  it('department 空串是后端在册的真值：屏上说「未登记归属部门」，不摆空白', async () => {
    const { bindings, html } = await openPanel([rawRow({ department: '' })])
    expect(bindings.alerts.value[0].departmentText).toBe(UNATTRIBUTED_DEPARTMENT)
    const page = await html()
    expect(visibleText(page)).toContain(UNATTRIBUTED_DEPARTMENT)
    expect(page).toContain('data-testid="alert-status-line"')
  })
})

describe('R271 判据④ · G18：面板头的数字只能来自服务端', () => {
  it('这一页没有前端自己盖的时钟：面板与取数层都不出现 new Date / Date.now', () => {
    for (const text of [codeOnly(source('InsightPanel.vue')), codeOnly(libSource('alerts.js'))]) {
      expect(text).not.toMatch(/new\s+Date\s*\(/)
      expect(text).not.toMatch(/Date\.now\s*\(/)
      expect(text).not.toMatch(/toISOString\s*\(/)
    }
  })

  it('计数格只有一处产出：读回来几行就写几，不许有第二本账', () => {
    const body = /function countText\([\s\S]*?\n}/.exec(codeOnly(source('InsightPanel.vue')))
    expect(body, 'countText 应该还是那唯一一枚计数出口').toBeTruthy()
    expect(body[0]).toMatch(/return String\(rows\.length\)/)
    expect(body[0]).not.toMatch(/\[['"]\d+['"]/)
  })

  it('首屏两格都是「正在读取」；读到 2 条告警 1 条规则就变成 2 与 1', async () => {
    const cold = await renderToString(h({ render: () => h(InsightPanel) }))
    expect(visibleText(cold)).toContain('正在读取')
    const fresh = await mountBindings(InsightPanel)
    expect(fresh.summary.value.map(item => item.value)).toEqual(['正在读取', '正在读取'])
    const rules = [{ id: 3, name: '差旅费上限', metric: '差旅费', op: 'gt', threshold: 8000, enabled: true }]
    const { bindings, html } = await openPanel([rawRow({ id: 7 }), rawRow({ id: 8, status: 'closed' })], { rules })
    expect(bindings.summary.value.map(item => item.value)).toEqual(['2', '1'])
    const page = await html()
    expect((page.match(/class="record-item"/g) || []).length).toBe(2)
    expect((page.match(/data-testid="alert-ledger"[\s>]*/g) || []).length).toBe(2)
  })

  it('源码里不出现 demo / 示例 / 假，面板头也不留英文 Alerts 占位', () => {
    const text = source('InsightPanel.vue')
    expect(text).not.toMatch(/demo|示例|假/)
    expect(text).not.toMatch(/class="eyebrow"[^>]*>\s*Alerts\s*</)
    expect(text).toMatch(/class="eyebrow">服务端告警账本</)
  })

  it('无权限这一张脸上，处置三动作与巡检一起熄：读不到就不许写', async () => {
    makeServer([], {})
    http.get.mockImplementation(async url => {
      if (url === ALERTS_PATH || url === RULES_PATH) throw httpError(403, 'permission_denied')
      throw new Error('未预期的 GET 路径：' + url)
    })
    const bindings = await mountBindings(InsightPanel)
    await bindings.loadAll()
    expect(bindings.denied.value).toBe(true)
    expect(bindings.canManage.value).toBe(false)
    expect(bindings.canDispose('ack', { id: '7', addressable: true, statusKnown: true, actions: ['ack'] })).toBe(false)
    const page = await renderState(bindings)
    expect(visibleText(page)).toContain('这个账号没有查看告警的权限')
    expect(buttonTag(page, 'run-alert-check')).toMatch(/\bdisabled\b/)
  })
})