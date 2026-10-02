/**
 * R399 判据①②③ · 「运行留痕」上屏之后的真 HTML 证据（本单四把刀有两把钉在这里）
 *
 * 手法沿用 r316 / r341 / r385 / r388（环境仍是 node + @vue/server-renderer：本仓没有 jsdom /
 * @vue/test-utils，也不许 npm i）：只 mock 网络层那一枚 axios 实例，先真跑三枚读腿，再把同一份
 * bindings 渲染成真 HTML。于是这里量的是屏上真的画出了什么，不是源码里长得像那么回事的字符串 ——
 * 主断言一律从 renderToString 出来的那段字符串上取（R375 半证那一格）。
 *
 * 判据③ 的三张脸在这里各交一段人话（回执③ 那三段就是从下面 visibleText 现取的，不是抄代码注释）：
 *   ① 这一条 Trace 真的没有    ⇒ absent：句子说「服务端答了：这个编号下一条事件都没记到」；
 *   ② 服务端拒答 / 读不出形状  ⇒ off / malformed / failed：各说各话，屏上一个 0 都不画；
 *   ③ 权限不够（staff 打管理员出口）⇒ denied：说「不向你开放」，并指出去哪申请，不并成「没有数据」。
 *
 * 四把反证刀（判据⑦）与本文件的对应关系，逐枚在影子副本里真注入过、跑完按字节复原：
 *   刀1 把「读不出」洗成空列表     → 乙组：off / malformed / failed / empty 四张脸两两不等，当场红；
 *   刀2 前端自己按事件重算一遍计数 → 甲组：events_total 与数组长度故意不同，屏上必须念服务端那两枚；
 *   刀3 403 渲染成「没有数据」     → 丙组：denied 那一句与 empty / failed 两句互斥，且不给重试按钮；
 *   刀4 把 trace_id 变成裸手输框   → 戊组：全场零枚 <input>，取号只有「清单里点」与「地址里带」。
 *
 * SSR 不跑 onMounted：下面 screenAt 里手工补的那两行，逐字对应屏壳 onMounted 那两行
 * （loadRoster()；picked 有值就 loadDetail(picked)）。屏壳级接线本身由 routes.test.js 与
 * r399-trace-screen.test.js 那两枚钉着，本枚只管「接上之后屏上画出了什么」。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createMemoryHistory } from 'vue-router'

vi.mock('../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }
})

import { http } from '../lib/http'
import { createAppRouter } from '../router/index.js'
import TracePanel from '../components/TracePanel.vue'
import {
  LEDGER_ABSENT_TITLE,
  LEDGER_EMPTY_TITLE,
  RUNS_DENIED_TITLE,
  RUNS_EMPTY_TITLE,
  RUNS_FAILED_TITLE,
  RUNS_MALFORMED_TITLE,
  RUNS_OFF_TITLE,
  RUNS_UNAUTHORIZED_TITLE,
  STAGE_LATENCY_PATH,
  TRACE_ABSENT_TITLE,
  TRACE_DENIED_TITLE,
  TRACE_EVENTS_PREFIX,
  TRACE_FAILED_TITLE,
  TRACE_MALFORMED_TITLE,
  TRACE_UNAUTHORIZED_TITLE,
} from '../lib/traces'

// ==================== 后端回包的形状（逐枚照那两枚出口交回的结构，不掺演示值） ====================

/** coverage.per_request 里的一条账：app/common/stage_timing.py:674 开格，六枚键在 app/common/stage_timing.py:675-:680。 */
function runEntry(overrides = {}) {
  return {
    segment_sum_ms: 912.5,
    end_to_end_ms: 950.25,
    gap_ms: 37.75,
    coverage_error_pct: 3.9724,
    unresolved_overlap_pairs: 0,
    within_one_percent: false,
    ...overrides,
  }
}

/** GET /stage-latency 不带编号（:714 把 scope 写成 process）。 */
function processReport(perRequest, overrides = {}) {
  const ids = Object.keys(perRequest)
  return {
    schema: 'r51.stage-latency/1',
    scope: 'process',
    enabled: true,
    sample_count: ids.length * 3,
    missing_stages: [],
    stages: {},
    coverage: { requests: ids.length, within_one_percent: null, worst_coverage_error_pct: null, per_request: perRequest },
    ...overrides,
  }
}

/** 一条已记录的事件（:645 _bounded_events 那一格的字段）。 */
function eventRow(overrides = {}) {
  return {
    sequence: '0001',
    timestamp: '2026-09-27T09:00:00.123456+08:00',
    event_type: 'request.started',
    status: 'running',
    stage: 'classify',
    ...overrides,
  }
}

/** GET /traces/{trace_id}：:638-642 那三枚计数由服务端算好。 */
function traceResponse(rows, overrides = {}) {
  return {
    trace_id: 'run-0a1b',
    event_count: rows.length,
    events_total: rows.length,
    truncated: false,
    events: rows,
    limits: { max_events: 200, applied_limit: 200, requested_limit: null, clamped: false },
    ...overrides,
  }
}

/** GET /stage-latency?trace_id=（:710 把 scope 写成 trace；数由 :655 那一格折出来）。 */
function traceStageReport(overrides = {}) {
  return {
    schema: 'r51.stage-latency/1',
    scope: 'trace',
    trace_id: 'run-0a1b',
    sample_count: 2,
    missing_stages: ['reflect'],
    stage_total_ms: 900,
    stages: {
      classify: { count: 1, total_ms: 12.5, share_pct: 1.3889, p50_ms: 12.5, p95_ms: 12.5 },
      retrieve: { count: 1, total_ms: 887.5, share_pct: 98.6111, p50_ms: 887.5, p95_ms: 887.5 },
    },
    ...overrides,
  }
}

const failWith = (status, detail) => ({ __error: { isAxiosError: true, status, response: { status, data: { detail } } } })

// ==================== 装屏 ====================

/** 在途请求登记册：屏壳的 watch 会自己补发读腿，只靠微任务数轮次会漏等。 */
let pending = []

/** 只认这三条地址：任何别的路径或别的动词都是本单越界（判据②「零新增端点」）。 */
function stubReads({ roster, events, ledger } = {}) {
  const answerFor = path => {
    if (path === 'roster') return settle(roster, '清单那一发没安排回包')
    if (path === 'events') return settle(events, '事件那一发没安排回包')
    return settle(ledger, '分段账那一发没安排回包')
  }
  function settle(answer, why) {
    if (answer === undefined) throw new Error(why)
    if (answer && answer.__error) throw answer.__error
    return { status: 200, data: answer }
  }
  http.get.mockImplementation((url, config) => {
    let slot
    if (url === STAGE_LATENCY_PATH) {
      const traceId = config && config.params && config.params.trace_id
      slot = traceId ? 'ledger' : 'roster'
    } else if (typeof url === 'string' && url.startsWith(TRACE_EVENTS_PREFIX)) {
      expect(url, '本件只投喂 run-0a1b 这一枚编号').toBe(TRACE_EVENTS_PREFIX + 'run-0a1b')
      slot = 'events'
    } else {
      throw new Error('不该被请求的路径：' + String(url))
    }
    const job = Promise.resolve().then(() => answerFor(slot))
    pending.push(job)
    return job
  })
  for (const verb of ['post', 'put', 'delete']) {
    http[verb].mockImplementation(async url => { throw new Error('这一屏不许发写请求：' + verb.toUpperCase() + ' ' + url) })
  }
}

async function mountedPanel(location = '/traces') {
  const router = createAppRouter({ history: createMemoryHistory() })
  await router.push(location)
  await router.isReady()
  let bindings = null
  const Host = {
    name: 'R399Probe',
    setup(props, ctx) {
      bindings = { ...TracePanel.setup({}, ctx), __router: router }
      return () => null
    },
  }
  await renderToString(createSSRApp(Host).use(router))
  expect(bindings, '屏壳没交出 setup() 绑定').toBeTruthy()
  return bindings
}

const render = bindings => renderToString(h({ ...TracePanel, setup: () => bindings }))

const visibleText = html => html
  .replace(/<!--[\s\S]*?-->/g, ' ')
  .replace(/<[^>]+>/g, ' ')
  .replace(/\s+/g, ' ')
  .trim()

async function settleEverything() {
  for (let round = 0; round < 8; round += 1) {
    const jobs = pending.splice(0, pending.length)
    // 那一发导航（router.replace）也是异步的：路由没落地就说明编号没写回地址，
    // 所以这里既等在途的读腿，也等一次宏任务让 router 走完它自己的 promise 链。
    const idle = jobs.length === 0
    if (idle) await new Promise(resolve => setTimeout(resolve, 0))
    else await Promise.allSettled(jobs)
    for (let i = 0; i < 8; i += 1) await Promise.resolve()
    if (idle && round > 0) return
  }
}

/** 一屏一张脸：装好回包、真取一次数、把屏渲染出来。 */
async function screenAt({ roster, events, ledger, location, picked } = {}) {
  pending = []
  stubReads({ roster, events, ledger })
  const bindings = await mountedPanel(location)
  // 屏壳 onMounted 那两行，SSR 不跑，这里逐字补上：
  bindings.loadRoster()
  if (bindings.picked.value) bindings.loadDetail(bindings.picked.value)
  if (picked && picked !== bindings.picked.value) {
    // 屏上点选那一条路：直接调那枚下拉的事件处理器 —— 它在屏壳里是 @update:model-value 的唯一接线，
    // 「换成这一枚选中 / 落回地址 / 补读那两发」三件事全在那一个函数里，本枚不代跑第二套接线。
    bindings.adoptRun(picked)
  }
  await settleEverything()
  return { bindings, html: await render(bindings) }
}

/** 某一格的句子只在那一格出现：三格并成一句含糊话，这一条就抓不到。 */
function textOfCell(html, testId) {
  const open = new RegExp('<section[^>]*data-testid="' + testId + '"[^>]*>').exec(html)
  expect(open, '屏上没有 ' + testId + ' 这一格，量具失灵了').toBeTruthy()
  const rest = html.slice(open.index + open[0].length)
  const close = rest.indexOf('</section>')
  expect(close, testId + ' 那一格没有闭合，量具失灵了').toBeGreaterThan(-1)
  return visibleText(rest.slice(0, close))
}

function faceOfCell(html, testId) {
  const match = new RegExp('<section[^>]*data-testid="' + testId + '"[^>]*data-face="([^"]*)"').exec(html)
  expect(match, testId + ' 那一格没带 data-face').toBeTruthy()
  return match[1]
}

const requested = () => http.get.mock.calls.map(call => (call[1] && call[1].params && call[1].params.trace_id ? STAGE_LATENCY_PATH + '?trace_id' : call[0]))

const ROSTER_TWO = processReport({ 'run-0a1b': runEntry(), 'run-9f8e': runEntry({ within_one_percent: true, coverage_error_pct: 0.42 }) })
const EVENTS_TWO = traceResponse([eventRow(), eventRow({ sequence: '0002', event_type: 'tool_call.finished', status: 'completed' })])
const LEDGER_TWO = traceStageReport()

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
  http.put.mockReset()
  http.delete.mockReset()
  pending = []
})

// ================= 甲 · 判据②：屏上的数就是回包里那一格的数 =================

describe('R399 甲 · 三格只画服务端给的读数', () => {
  it('清单两枚运行两行：行内每一格都念得出服务端那枚账', async () => {
    const { html } = await screenAt({ roster: ROSTER_TWO, events: EVENTS_TWO, ledger: LEDGER_TWO })
    expect(faceOfCell(html, 'runs-cell')).toBe('ready')
    const cells = textOfCell(html, 'runs-cell')
    // 3.9724 收成 3.97 是本仓唯一的加工（格式化），不是第二道算术：整数位与小数位都对得上原值。
    for (const value of ['950.25', '912.5', '37.75', '3.97', '对不平', '对得平']) {
      expect(cells, '服务端给的读数没上屏：' + value).toContain(value)
    }
    expect(html).toContain('data-testid="runs-table"')
    expect(cells).not.toContain('演示')
  })

  it('刀2 靶子：那一格念的是服务端给的 event_count 与 events_total，不是数组长度', async () => {
    const { html } = await screenAt({
      roster: ROSTER_TWO,
      events: traceResponse([eventRow(), eventRow({ sequence: '0002' })], { events_total: 7, event_count: 2, truncated: true }),
      ledger: LEDGER_TWO,
      picked: 'run-0a1b',
    })
    const cells = textOfCell(html, 'events-cell')
    expect(cells).toContain('一共记了 7 条')
    expect(cells).toContain('读出 2 条')
    expect(cells, '前端把 events.length 当成了全集').not.toMatch(/一共记了 2 条/)
    expect(cells).toContain('剩下的不在这屏上')
  })

  it('分段账那一格把 count / total / share / p50 / p95 原样画出来，缺段只念服务端点名的那一段', async () => {
    const { html } = await screenAt({ roster: ROSTER_TWO, events: EVENTS_TWO, ledger: LEDGER_TWO, picked: 'run-0a1b' })
    const cells = textOfCell(html, 'ledger-cell')
    for (const value of ['12.5', '887.5', '1.39', '98.61', '1 次', '检索本体']) {
      expect(cells, '分段账少画了服务端给的那一格：' + value).toContain(value)
    }
    expect(cells).toContain('复审')
    expect(cells, '服务端没点名的段也被这一格说成缺了').not.toContain('意图与路由决策：')
  })

  it('词表外的段名不猜中文：那一格说「未登记的分段」，也不把后端原串画上屏', async () => {
    const odd = traceStageReport({ missing_stages: [], stages: { telekinesis: { count: 1, total_ms: 5, share_pct: 100, p50_ms: 5, p95_ms: 5 } } })
    const { html } = await screenAt({ roster: ROSTER_TWO, events: EVENTS_TWO, ledger: odd, picked: 'run-0a1b' })
    const cells = textOfCell(html, 'ledger-cell')
    expect(cells).toContain('未登记的分段')
    expect(cells, '后端原串被当成中文标签画上屏').not.toContain('telekinesis')
  })
})

// ============ 乙 · 刀1：读不出与不供数，一张都不许塌成「没有」 ============

describe('R399 乙 · 刀1：off / malformed / failed / empty 四张脸两两不等', () => {
  const cases = [
    ['off', processReport({}, { enabled: false }), RUNS_OFF_TITLE],
    ['malformed', processReport({}, { scope: 'trace' }), RUNS_MALFORMED_TITLE],
    ['failed', failWith(500, 'internal_error'), RUNS_FAILED_TITLE],
    ['empty', processReport({}), RUNS_EMPTY_TITLE],
  ]

  it('每一枚各说各话：自己的标题在，别人的标题一枚都不在', async () => {
    const read = []
    for (const [face, answer, title] of cases) {
      const { html } = await screenAt({ roster: answer, events: EVENTS_TWO, ledger: LEDGER_TWO })
      read.push({ face, title, cells: textOfCell(html, 'runs-cell'), drawn: faceOfCell(html, 'runs-cell') })
    }
    expect(read.map(item => item.face)).toEqual(read.map(item => item.drawn))
    for (const own of read) {
      expect(own.cells, own.face + ' 那张脸没念出自己的句子：' + own.cells).toContain(own.title)
      for (const other of read) {
        if (other === own) continue
        expect(own.cells, own.face + ' 并成了 ' + other.face + ' 那句：' + own.cells).not.toContain(other.title)
      }
    }
    const titles = read.map(item => item.title)
    expect(new Set(titles).size, '四枚标题里有重复的，判据③ 塌了').toBe(4)
  })

  it('四张脸都不画数：屏上不出现一枚 0，也不出现表格', async () => {
    for (const [, answer] of cases) {
      const { html } = await screenAt({ roster: answer, events: EVENTS_TWO, ledger: LEDGER_TWO })
      const cells = textOfCell(html, 'runs-cell')
      expect(cells.replace(/[，。：；、]/g, ''), '这一格把「问不出」报成了读数').not.toMatch(/0/)
      expect(html).not.toContain('data-testid="runs-table"')
    }
  })

  it('分段账零样本：说「这一次运行没记到分段耗时」，不拿零毫秒冒充读数', async () => {
    const { html } = await screenAt({
      roster: ROSTER_TWO,
      events: EVENTS_TWO,
      ledger: traceStageReport({ sample_count: 0, stages: { classify: { count: 0, total_ms: 0, share_pct: 0, p50_ms: 0, p95_ms: 0 } } }),
      picked: 'run-0a1b',
    })
    expect(textOfCell(html, 'ledger-cell')).toContain(LEDGER_EMPTY_TITLE)
    expect(faceOfCell(html, 'ledger-cell')).toBe('empty')
    expect(html).not.toContain('data-testid="ledger-table"')
  })

  it('分段账那一格读不出形状：说「读不出形状」，不并成零样本那句', async () => {
    const { html } = await screenAt({ roster: ROSTER_TWO, events: EVENTS_TWO, ledger: traceStageReport({ scope: 'process' }), picked: 'run-0a1b' })
    const cells = textOfCell(html, 'ledger-cell')
    expect(cells).toContain('分段账的回包读不出形状')
    expect(cells).not.toContain(LEDGER_EMPTY_TITLE)
    expect(faceOfCell(html, 'ledger-cell')).toBe('malformed')
  })
})

// ============ 丙 · 判据③：真没有 / 问不出 / 没权限，三张脸分开 ============

describe('R399 丙 · 刀3：403 是没权限，404 是真没有，401 是登录失效', () => {
  it('服务端答 404：事件那一格说「没留下痕迹」，并明说它不是读失败', async () => {
    const gone = failWith(404, 'resource_not_found')
    const { html } = await screenAt({ roster: ROSTER_TWO, events: gone, ledger: gone, picked: 'run-0a1b' })
    const cells = textOfCell(html, 'events-cell')
    expect(cells).toContain(TRACE_ABSENT_TITLE)
    expect(cells).toContain('没记到')
    expect(cells).not.toContain(TRACE_FAILED_TITLE)
    expect(cells).not.toContain(TRACE_MALFORMED_TITLE)
    expect(cells).not.toContain(TRACE_DENIED_TITLE)
    expect(faceOfCell(html, 'events-cell')).toBe('absent')
    // 同一枚编号、同一个 404，分段那一格说的是自己那一格的话，不抄事件那句。
    const ledgerCells = textOfCell(html, 'ledger-cell')
    expect(ledgerCells).toContain(LEDGER_ABSENT_TITLE)
    expect(ledgerCells).not.toContain(TRACE_ABSENT_TITLE)
  })

  it('刀3 靶子：403 说「不向你开放」并指出去哪申请，一句都不并成「没有数据」', async () => {
    const denied = failWith(403, 'permission_denied')
    const { html } = await screenAt({ roster: denied, events: denied, ledger: denied, picked: 'run-0a1b' })
    const cells = textOfCell(html, 'runs-cell')
    expect(cells).toContain(RUNS_DENIED_TITLE)
    expect(cells).toContain('审计')
    expect(cells).toContain('企业管理员')
    expect(cells).not.toContain(RUNS_EMPTY_TITLE)
    expect(cells).not.toContain(RUNS_FAILED_TITLE)
    expect(cells).not.toContain(RUNS_UNAUTHORIZED_TITLE)
    expect(faceOfCell(html, 'runs-cell')).toBe('denied')
    // 没权限不给重试：那一枚按钮按下去只会再来一次 403，是 R32 明令禁的假控件。
    expect(html).not.toContain('data-testid="ui-error-retry"')
    // 三格各说各的没权限，不是同一句被复制三遍。
    expect(textOfCell(html, 'events-cell')).toContain(TRACE_DENIED_TITLE)
    expect(textOfCell(html, 'ledger-cell')).toContain('这一次运行的分段账不向你开放')
  })

  it('401 是登录失效：既不说没权限，也不说没数据', async () => {
    const { html } = await screenAt({ roster: failWith(401, 'authentication_required'), events: EVENTS_TWO, ledger: LEDGER_TWO })
    const cells = textOfCell(html, 'runs-cell')
    expect(cells).toContain(RUNS_UNAUTHORIZED_TITLE)
    expect(cells).not.toContain(RUNS_DENIED_TITLE)
    expect(cells).not.toContain(RUNS_EMPTY_TITLE)
    expect(faceOfCell(html, 'runs-cell')).toBe('unauthorized')
  })

  it('还没点选：屏上是「还没点选」，不替服务端说「没有」，也不发第二发', async () => {
    const { html } = await screenAt({ roster: ROSTER_TWO, events: EVENTS_TWO, ledger: LEDGER_TWO })
    expect(faceOfCell(html, 'events-cell')).toBe('idle')
    expect(faceOfCell(html, 'ledger-cell')).toBe('idle')
    const cells = textOfCell(html, 'events-cell')
    expect(cells).toContain('还没点选哪一次运行')
    expect(cells).not.toContain(TRACE_ABSENT_TITLE)
    expect(requested()).toEqual([STAGE_LATENCY_PATH])
  })

  it('乙问不出不拖累甲：清单照旧两行，事件那一格自己说一句', async () => {
    const { html } = await screenAt({ roster: ROSTER_TWO, events: failWith(500, 'internal_error'), ledger: LEDGER_TWO, picked: 'run-0a1b' })
    expect(faceOfCell(html, 'runs-cell')).toBe('ready')
    expect(html).toContain('data-testid="runs-table"')
    expect(textOfCell(html, 'events-cell')).toContain(TRACE_FAILED_TITLE)
    expect(faceOfCell(html, 'ledger-cell')).toBe('ready')
  })
})

// ============ 戊 · 刀4：编号只有「清单里点」与「地址里带」两条来路 ============

describe('R399 戊 · 刀4：屏上没有手输编号的框', () => {
  it('唯一的取号控件是清单里点出来的下拉：全场零枚 <input>、零枚 <textarea>', async () => {
    const { html } = await screenAt({ roster: ROSTER_TWO, events: EVENTS_TWO, ledger: LEDGER_TWO })
    expect(html, '清单那一格没画出那枚下拉').toContain('data-testid="pick-run"')
    expect(html).toContain('data-testid="ui-select-trigger"')
    expect(html).toContain('role="combobox"')
    expect(html, '屏上出现了可手输的文本框').not.toMatch(/<input\b/)
    expect(html).not.toMatch(/<textarea\b/)
    // 候选就是服务端清单里那两枚编号，前端不补号也不排号（顺序 = 它给的那串键）。
    const options = visibleText(html)
    expect(options.indexOf('run-0a1b')).toBeLessThan(options.indexOf('run-9f8e'))
  })

  it('点中一枚：读腿只补那两发，编号写回地址', async () => {
    const { bindings } = await screenAt({ roster: ROSTER_TWO, events: EVENTS_TWO, ledger: LEDGER_TWO })
    http.get.mockClear()
    bindings.adoptRun('run-0a1b')
    await settleEverything()
    expect(requested()).toEqual([STAGE_LATENCY_PATH + '?trace_id', TRACE_EVENTS_PREFIX + 'run-0a1b'])
    expect(bindings.__router.currentRoute.value.query.trace, '编号没写回地址：这一屏转不出去').toBe('run-0a1b')
    const html = await render(bindings)
    expect(textOfCell(html, 'events-cell')).toContain('run-0a1b')
    expect(faceOfCell(html, 'events-cell')).toBe('ready')
  })

  it('深链 /traces?trace=<编号> 直接进：一进来就两格齐读，地址是主', async () => {
    const { bindings, html } = await screenAt({ roster: ROSTER_TWO, events: EVENTS_TWO, ledger: LEDGER_TWO, location: '/traces?trace=run-0a1b' })
    expect(bindings.picked.value).toBe('run-0a1b')
    expect(requested()).toEqual([STAGE_LATENCY_PATH, STAGE_LATENCY_PATH + '?trace_id', TRACE_EVENTS_PREFIX + 'run-0a1b'])
    expect(faceOfCell(html, 'events-cell')).toBe('ready')
    expect(faceOfCell(html, 'ledger-cell')).toBe('ready')
    expect(http.post).not.toHaveBeenCalled()
    expect(http.put).not.toHaveBeenCalled()
    expect(http.delete).not.toHaveBeenCalled()
  })
})
