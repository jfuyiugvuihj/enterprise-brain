/**
 * R399 判据②③ · 「运行留痕」那三枚读腿的对账钉与归脸钉
 *
 * 两件分开验的事，各自有出处：
 *  甲 对账：本模块的词表与字段名，是不是后端此刻真发的那一套。读的是 `git show HEAD:app/**`
 *    而不是工作树（手法逐字照 r316-users-contract.test.js:50-59 —— 工作树会被这一单的改动污染，
 *    而本单一枚后端文件都不改，HEAD 就是那一份真源）。
 *  乙-戊 归脸与算术：空态 / 不供数 / 没权限三张脸两两不等，屏上没有一个前端数出来的数。
 *
 * 四把反证刀里，本件管三把的形状：①「读不出」被洗成空列表、②前端自己按事件重算计数、
 * ④编号变成手输框。真 HTML 那三把在 src/__tests__/r399-trace-render.test.js，屏壳形状在
 * src/components/__tests__/r399-trace-screen.test.js。
 */
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../lib/http', async importOriginal => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn() } }
})

import { errorText } from '../errcodes'
import { http } from '../http'
import {
  LEDGER_ABSENT_MESSAGE,
  LEDGER_ABSENT_TITLE,
  LEDGER_CLOSED_TEXT,
  LEDGER_DENIED_TITLE,
  LEDGER_EMPTY_MESSAGE,
  LEDGER_FAILED_TITLE,
  LEDGER_IDLE_TITLE,
  LEDGER_EMPTY_TITLE,
  LEDGER_LOADING_TEXT,
  LEDGER_MALFORMED_MESSAGE,
  LEDGER_MALFORMED_TITLE,
  LEDGER_UNCLOSED_TEXT,
  LEDGER_UNAUTHORIZED_TITLE,
  LEDGER_VERDICT_PENDING_TEXT,
  RUN_BACKEND_FIELDS,
  RUNS_DENIED_TITLE,
  RUNS_EMPTY_MESSAGE,
  RUNS_EMPTY_TITLE,
  RUNS_FACE_DENIED,
  RUNS_FACE_EMPTY,
  RUNS_FACE_FAILED,
  RUNS_FACE_LOADING,
  RUNS_FACE_MALFORMED,
  RUNS_FACE_OFF,
  RUNS_FACE_READY,
  RUNS_FACE_UNAUTHORIZED,
  RUNS_FAILED_TITLE,
  RUNS_LOADING_TEXT,
  RUNS_MALFORMED_MESSAGE,
  RUNS_MALFORMED_TITLE,
  RUNS_OFF_MESSAGE,
  RUNS_OFF_TITLE,
  RUNS_UNAUTHORIZED_TITLE,
  STAGE_LATENCY_PATH,
  TRACE_ABSENT_MESSAGE,
  TRACE_ABSENT_TITLE,
  TRACE_DENIED_TITLE,
  TRACE_EVENTS_PREFIX,
  TRACE_EVENT_LABELS,
  TRACE_EVENT_UNKNOWN,
  TRACE_FACES,
  TRACE_FACE_ABSENT,
  TRACE_FACE_IDLE,
  TRACE_FAILED_TITLE,
  TRACE_IDLE_MESSAGE,
  TRACE_IDLE_TITLE,
  TRACE_LOADING_TEXT,
  TRACE_MALFORMED_MESSAGE,
  TRACE_MALFORMED_TITLE,
  TRACE_STAGE_LABELS,
  TRACE_STAGE_UNKNOWN,
  TRACE_STATUS_LABELS,
  TRACE_STATUS_UNKNOWN,
  TRACE_UNAUTHORIZED_TITLE,
  UNRECORDED_ALIAS,
  cellKind,
  countText,
  durationText,
  eventCountNote,
  isAbsentError,
  ledgerBlankView,
  ledgerIdleView,
  ledgerViewFromResponse,
  loadRunRoster,
  loadTraceEvents,
  loadTraceLedger,
  mapRunRow,
  mapStageRow,
  mapTraceEvent,
  missingStageNote,
  percentText,
  runsBlankView,
  runsViewFromReport,
  traceBlankView,
  traceEventsPath,
  traceIdleView,
  traceReadFailureView,
  traceStageLabel,
  traceStatusLabel,
  traceViewFromResponse,
  UNRECORDED,
  verdictText,
} from '../traces'

const REPO_REF = 'HEAD'
/** git grep 的 pathspec 按进程当前目录解释，所以显式回到仓根再扫。 */
const REPO_ROOT = fileURLToPath(new URL('../../../..', import.meta.url))

function showAtRef(path) {
  let text
  try {
    text = execFileSync('git', ['show', REPO_REF + ':' + path], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
  } catch (cause) {
    throw new Error('读不到真源 ' + REPO_REF + ':' + path + '（git show 失败：' + cause.message + '）。对账不许降级成 skip。')
  }
  if (!text.trim()) throw new Error('git show ' + REPO_REF + ':' + path + ' 返回空内容，无法对账。')
  return text.replace(/\r\n/g, '\n')
}

const observability = () => showAtRef('app/api/v1/observability.py')
const stageTiming = () => showAtRef('app/common/stage_timing.py')

// ==================== 夹具：形状逐枚照后端回包写 ====================

const runEntry = (over = {}) => ({
  segment_sum_ms: 900.5,
  end_to_end_ms: 918.75,
  gap_ms: 18.25,
  coverage_error_pct: 1.9864,
  unresolved_overlap_pairs: 0,
  within_one_percent: false,
  ...over,
})

const rosterPayload = (perRequest = { 'trace-b': runEntry(), 'trace-a': runEntry({ within_one_percent: true }) }, over = {}) => ({
  schema: 'r51.stage-latency/1',
  sample_count: 12,
  scope: 'process',
  enabled: true,
  coverage: {
    requests: Object.keys(perRequest).length,
    within_one_percent: false,
    worst_coverage_error_pct: 1.9864,
    per_request: perRequest,
  },
  ...over,
})

const traceEvent = (over = {}) => ({
  trace_id: 'trace-a',
  request_id: 'req-1',
  task_id: 'task-1',
  sequence: 1,
  timestamp: '2026-09-27T10:00:00.123456+08:00',
  event_type: 'request.started',
  status: 'running',
  payload: { owner_id: 'u-1' },
  ...over,
})

const eventsPayload = (events = [traceEvent(), traceEvent({ sequence: 2, event_type: 'model.finished', status: 'completed' })], over = {}) => ({
  trace_id: 'trace-a',
  requested_by: { username: 'ops', role: 'admin' },
  event_count: events.length,
  events_total: events.length,
  truncated: false,
  first_sequence: 1,
  last_sequence: events.length,
  events,
  limits: { max_events: 200, applied_limit: 200, requested_limit: null, clamped: false },
  ...over,
})

const stageEntry = (over = {}) => ({
  count: 1,
  p50_ms: 12.5,
  p95_ms: 12.5,
  average_ms: 12.5,
  max_ms: 12.5,
  total_ms: 12.5,
  ledger_count: 1,
  excluded_count: 0,
  excluded_ms: 0,
  share_pct: 20,
  // 后端这一格自带一句含源码路径的描述（app/common/stage_timing.py:88 那张表）：本模块一个字都不读它。
  description: '意图/路由/拆题决策（含 supervisor 往返）',
  ...over,
})

const ledgerPayload = (over = {}) => ({
  schema: 'r51.stage-latency/1',
  sample_count: 3,
  scope: 'trace',
  trace_id: 'trace-a',
  stages: {
    classify: stageEntry(),
    rewrite: stageEntry({ count: 0, ledger_count: 0, total_ms: 0, share_pct: 0 }),
    retrieve: stageEntry({ count: 1, total_ms: 300.25, share_pct: 48.02 }),
    generate: stageEntry({ count: 2, total_ms: 300, share_pct: 47.98 }),
    reflect: stageEntry({ count: 0, ledger_count: 0, total_ms: 0, share_pct: 0 }),
  },
  missing_stages: ['rewrite', 'reflect'],
  ...over,
})

const httpError = (status, detail) => ({ response: { status, data: { detail } }, message: 'Request failed with status code ' + status })

afterEach(() => {
  vi.clearAllMocks()
})

// ==================== 甲 · 对账：词表与字段名是不是后端此刻真发的那一套 ====================

describe('R399 甲 · 对账（读 git show ' + REPO_REF + ':app/**）', () => {
  it('零新增端点：本模块用到的两条地址，就是 observability 在册的那两枚 GET', () => {
    const source = observability()
    const registered = new Set()
    for (const match of source.matchAll(/@router\.get\(\s*"([^"]+)"/g)) registered.add(match[1])
    for (const match of source.matchAll(/@router\.get\(\s*([A-Z_]+)/g)) {
      const literal = new RegExp(match[1] + ' = "([^"]+)"').exec(source)
      if (literal) registered.add(literal[1])
    }
    expect(registered, '/stage-latency 不在后端在册的 GET 里').toContain('/stage-latency')
    expect(registered, '/traces/{trace_id} 不在后端在册的 GET 里').toContain('/traces/{trace_id}')
    expect(STAGE_LATENCY_PATH).toBe('/stage-latency')
    // 本模块拼事件地址只用这一枚前缀，且全模块只出现一次，不留第二条拼法。
    expect(TRACE_EVENTS_PREFIX).toBe('/traces/')
    expect(traceEventsPath('trace-a')).toBe('/traces/trace-a')
  })

  it('分段名词表与 CANONICAL_STAGES 同集同序：后端加一段而这里没跟上就红', () => {
    const match = /CANONICAL_STAGES: tuple\[str, \.\.\.\] = \(([^)]*)\)/.exec(stageTiming())
    expect(match, '后端那五枚分段名换了写法，对账得先跟着改量具').toBeTruthy()
    const stages = [...match[1].matchAll(/"([^"]+)"/g)].map(item => item[1])
    expect(stages).toEqual(Object.keys(TRACE_STAGE_LABELS))
    for (const stage of stages) {
      expect(traceStageLabel(stage), stage + ' 的中文说法没登记').toBe(TRACE_STAGE_LABELS[stage])
    }
  })

  it('事件名字典与后端字面量双向闭合：多一枚、少一枚都红', () => {
    const listed = execFileSync('git', ['grep', '-h', '-o', '-E', '"(request|step|tool_call|tool|model|retrieval|agent)\\.[a-z_.]+"', REPO_REF, '--', 'app'], {
      cwd: REPO_ROOT,
      encoding: 'utf8',
      maxBuffer: 16 * 1024 * 1024,
    })
      .split('\n')
      .map(line => line.trim().replace(/"/g, ''))
      .filter(Boolean)
    const emitted = [...new Set(listed)].sort()
    expect(emitted.length, '扫到的事件名字面量为零，量具本身失灵了').toBeGreaterThan(0)
    expect(emitted).toEqual(Object.keys(TRACE_EVENT_LABELS).slice().sort())
  })

  it('清单行的字段账本对得上 stage_timing 里那枚 per_request 的键', () => {
    const block = /per_request\[trace_id\] = \{([\s\S]*?)\n {8}\}/.exec(stageTiming())
    expect(block, '后端 per_request 那一格换了形状').toBeTruthy()
    const keys = [...block[1].matchAll(/"([a-z_]+)":/g)].map(item => item[1])
    expect(keys.slice().sort()).toEqual(RUN_BACKEND_FIELDS.slice().sort())
  })

  it('分段格只挑要展示的字段：含源码路径的那句 description 一个字节都不进视图', () => {
    const row = mapStageRow('classify', stageEntry())
    expect(Object.keys(row)).toEqual(['stageKey', 'label', 'count', 'totalMs', 'sharePct', 'p50Ms', 'p95Ms'])
    expect(JSON.stringify(row)).not.toMatch(/\.py|app\//)
  })
})

// ==================== 乙 · 清单格：空 / 不供数 / 没权限 三张脸 ====================

describe('R399 乙 · 清单那一格', () => {
  it('服务端给了两枚运行：脸是 ready，行按它给的键序，一枚都不重排', () => {
    const view = runsViewFromReport(rosterPayload())
    expect(view.face).toBe(RUNS_FACE_READY)
    expect(view.rows.map(row => row.traceId)).toEqual(['trace-b', 'trace-a'])
    expect(cellKind(view)).toBe('ready')
  })

  it('coverage.requests 与它自己的清单对不上：这是读不出形状，不是「没有运行」', () => {
    const drifted = rosterPayload()
    drifted.coverage.requests = 7
    const view = runsViewFromReport(drifted)
    expect(view.face).toBe(RUNS_FACE_MALFORMED)
    expect(view.title).toBe(RUNS_MALFORMED_TITLE)
    expect(cellKind(view)).toBe('failure')
    expect(view.retryable).toBe(true)
  })

  it('enabled=false：说「这台服务没在记」，不说「今天没有运行」，也不给重试按钮', () => {
    const off = runsViewFromReport(rosterPayload({}, { enabled: false }))
    const empty = runsViewFromReport(rosterPayload({}))
    expect(off.face).toBe(RUNS_FACE_OFF)
    expect(off.title).toBe(RUNS_OFF_TITLE)
    expect(off.retryable).toBe(false)
    expect(empty.face).toBe(RUNS_FACE_EMPTY)
    expect(off.title).not.toBe(empty.title)
    expect(off.description).not.toBe(empty.description)
    expect(off.description).toContain('不是因为公司今天没有运行')
  })

  it('scope 不是 process：那是另一条腿的回答，本格不认，归读不出形状', () => {
    expect(runsViewFromReport(rosterPayload({}, { scope: 'trace' })).face).toBe(RUNS_FACE_MALFORMED)
    expect(runsViewFromReport({}).face).toBe(RUNS_FACE_MALFORMED)
    expect(runsViewFromReport(null).face).toBe(RUNS_FACE_MALFORMED)
  })

  it('真零行是空态：句子说「账本在答」，且不画任何一枚 0', () => {
    const view = runsViewFromReport(rosterPayload({}))
    expect(view.face).toBe(RUNS_FACE_EMPTY)
    expect(view.title).toBe(RUNS_EMPTY_TITLE)
    expect(view.description).toBe(RUNS_EMPTY_MESSAGE)
    expect(JSON.stringify(view)).not.toMatch(/"rows": \[\{/)
  })

  it('403 是没权限、401 是登录失效、500 是没读到：三张脸三句话，都不许退成空态', () => {
    const denied = traceReadFailureView(httpError(403, 'permission_denied'), {
      deniedTitle: RUNS_DENIED_TITLE,
      unauthorizedTitle: RUNS_UNAUTHORIZED_TITLE,
      failedTitle: RUNS_FAILED_TITLE,
    })
    const unauthorized = traceReadFailureView(httpError(401, 'authentication_required'), {
      deniedTitle: RUNS_DENIED_TITLE,
      unauthorizedTitle: RUNS_UNAUTHORIZED_TITLE,
      failedTitle: RUNS_FAILED_TITLE,
    })
    const failed = traceReadFailureView(httpError(500, 'internal_error'), {
      deniedTitle: RUNS_DENIED_TITLE,
      unauthorizedTitle: RUNS_UNAUTHORIZED_TITLE,
      failedTitle: RUNS_FAILED_TITLE,
    })
    expect([denied.face, unauthorized.face, failed.face]).toEqual([RUNS_FACE_DENIED, RUNS_FACE_UNAUTHORIZED, RUNS_FACE_FAILED])
    expect(denied.description).toContain(errorText('permission_denied'))
    expect(denied.retryable).toBe(false)
    expect(unauthorized.retryable).toBe(false)
    // internal_error 在字典里就写着不可重试：那一枚「重新加载」不能靠取数层自己判（R368 口径）。
    expect(failed.retryable).toBe(false)
    const offline = traceReadFailureView({ code: 'ECONNABORTED', message: 'timeout of 30000ms exceeded' }, {
      deniedTitle: RUNS_DENIED_TITLE,
      unauthorizedTitle: RUNS_UNAUTHORIZED_TITLE,
      failedTitle: RUNS_FAILED_TITLE,
    })
    expect(offline.face).toBe(RUNS_FACE_FAILED)
    // 字典没为这一枚码说话 → 再点一次是有意义的，这条不许做成「一律 false」的假绿。
    expect(offline.retryable).toBe(true)
    for (const view of [denied, unauthorized, failed]) {
      expect(cellKind(view)).toBe('failure')
      expect(view.face).not.toBe(RUNS_FACE_EMPTY)
    }
  })
})

// ==================== 丙 · 事件格与分段格：各问各的，各归各的 ====================

describe('R399 丙 · 乙丙两格各自归脸', () => {
  it('事件回放的 404 是「真没有」：absent 那张脸说的是没记到，不是读失败', () => {
    expect(isAbsentError(httpError(404, 'resource_not_found'))).toBe(true)
    const view = traceBlankView(RUNS_FACE_LOADING)
    expect(view.face).toBe(RUNS_FACE_LOADING)
    expect(cellKind(traceIdleView())).toBe('idle')
  })

  it('两格都没点选时的句子，与「服务端说没有」的句子不是一句', () => {
    expect(TRACE_IDLE_TITLE).not.toBe(TRACE_ABSENT_TITLE)
    expect(TRACE_IDLE_MESSAGE).not.toBe(TRACE_ABSENT_MESSAGE)
    expect(LEDGER_EMPTY_TITLE).not.toBe(TRACE_ABSENT_TITLE)
    expect(LEDGER_ABSENT_TITLE).not.toBe(TRACE_ABSENT_TITLE)
    expect(LEDGER_ABSENT_MESSAGE).not.toBe(TRACE_ABSENT_MESSAGE)
  })

  it('分段格的 404 说「这一格没读到记录」，并与零样本那张脸分开', () => {
    const absent = ledgerViewFromResponse({ ...ledgerPayload(), scope: 'nope' })
    expect(absent.face).toBe(RUNS_FACE_MALFORMED)
    const empty = ledgerViewFromResponse(ledgerPayload({ sample_count: 0 }))
    expect(empty.face).toBe(RUNS_FACE_EMPTY)
    expect(empty.title).toBe(LEDGER_EMPTY_TITLE)
    expect(empty.description).toBe(LEDGER_EMPTY_MESSAGE)
    expect(cellKind(empty)).toBe('empty')
    expect(cellKind(ledgerIdleView())).toBe('idle')
  })

  it('分段格读的是服务端那枚 sample_count，不自己数样本', () => {
    const view = ledgerViewFromResponse(ledgerPayload({ samples: [{ trace_id: 'x' }, { trace_id: 'x' }] }))
    expect(view.face).toBe(RUNS_FACE_READY)
    expect(view.rows).toHaveLength(5)
    expect(view.rows.map(row => row.stageKey)).toEqual(['classify', 'rewrite', 'retrieve', 'generate', 'reflect'])
    expect(view.rows[2]).toEqual(mapStageRow('retrieve', stageEntry({ count: 1, total_ms: 300.25, share_pct: 48.02 })))
    expect(view.rows.some(row => 'description' in row)).toBe(false)
  })

  it('缺段句只念服务端点名的那几段：它没点名就一个字都不多', () => {
    expect(missingStageNote(ledgerViewFromResponse(ledgerPayload()).missing)).toBe(
      '服务端说这几段没记到样本：多路查询改写、复审。这一格不替它编一段耗时。',
    )
    expect(missingStageNote([])).toBe('')
    expect(missingStageNote(undefined)).toBe('')
  })

  it('词表外的事件与分段：只说未登记，绝不回显后端原串', () => {
    const odd = mapTraceEvent(traceEvent({ event_type: 'quantum.leap', status: 'wobbled' }))
    expect(odd.eventLabel).toBe(TRACE_EVENT_UNKNOWN)
    expect(odd.statusLabel).toBe(TRACE_STATUS_UNKNOWN)
    expect(traceStageLabel('vectorize')).toBe(TRACE_STAGE_UNKNOWN)
    // 原串只在 data-* 那一条通道上活着（供排查与 e2e 取数），不进文案。
    const row = mapTraceEvent(traceEvent({ event_type: 'quantum.leap' }))
    expect(row.eventRaw).toBe('quantum.leap')
    expect(row.eventLabel).not.toContain('quantum')
  })
})

// ==================== 丁 · 零前端算术 ====================

describe('R399 丁 · 屏上没有一枚前端数出来的数', () => {
  it('行字段与服务端那几枚逐字节相等：不换算、不四舍五入、不补零', () => {
    const row = mapRunRow('trace-a', runEntry())
    expect(row.endToEndMs).toBe(918.75)
    expect(row.segmentSumMs).toBe(900.5)
    expect(row.gapMs).toBe(18.25)
    expect(row.coverageErrorPct).toBe(1.9864)
    expect(row.closed).toBe(false)
  })

  it('读不到的那一格留 null（渲染成未记录），不补一个像真的一样的 0', () => {
    const row = mapRunRow('trace-a', {})
    expect(Object.values(row).filter(value => value === 0)).toEqual([])
    expect(row.endToEndMs).toBeNull()
    expect(durationText(row.endToEndMs)).toBe(UNRECORDED)
    expect(durationText(null)).toBe(UNRECORDED)
    expect(percentText(null)).toBe(UNRECORDED)
    expect(countText(null)).toBe(UNRECORDED)
    expect(durationText(12.3456)).toBe('12.35 毫秒')
    expect(percentText(1.9864)).toBe('1.99%')
    expect(countText(7, '次')).toBe('7 次')
    expect(countText(7)).toBe('7 条')
  })

  it('within_one_percent 没答就说没答：那一档既不叫「对不平」，也不叫「对得平」', () => {
    expect(verdictText(true)).toBe(LEDGER_CLOSED_TEXT)
    expect(verdictText(false)).toBe(LEDGER_UNCLOSED_TEXT)
    expect(verdictText(null)).toBe(LEDGER_VERDICT_PENDING_TEXT)
    expect(verdictText(undefined)).toBe(LEDGER_VERDICT_PENDING_TEXT)
  })

  it('条数那句念的是服务端给的 event_count 与 events_total：前端不数 events', () => {
    const full = traceViewFromResponse(eventsPayload())
    expect(full.face).toBe(RUNS_FACE_READY)
    expect(eventCountNote(full)).toContain('记了 2 条')
    const page = traceViewFromResponse(eventsPayload([traceEvent(), traceEvent({ sequence: 2 })], { event_count: 2, events_total: 5, truncated: true }))
    expect(page.truncated).toBe(true)
    expect(eventCountNote(page)).toContain('这一屏按它给的上限读出 2 条')
    expect(eventCountNote(page)).toContain('一共记了 5 条')
    // 未就绪的那一格不产句子：宁缺不猜。
    expect(eventCountNote(runsBlankView())).toBe('')
  })

  it('计数与事件行对不上就是形状漂移：不挑一个自己算的数顶上', () => {
    expect(traceViewFromResponse(eventsPayload(undefined, { event_count: 9 })).face).toBe(RUNS_FACE_MALFORMED)
    expect(traceViewFromResponse(eventsPayload(undefined, { truncated: true })).face).toBe(RUNS_FACE_MALFORMED)
    expect(traceViewFromResponse({ events: [] }).face).toBe(RUNS_FACE_MALFORMED)
    expect(traceViewFromResponse(null).face).toBe(RUNS_FACE_MALFORMED)
  })

  it('事件行不补号也不重排：序号原样带过来', () => {
    const view = traceViewFromResponse(eventsPayload([
      traceEvent({ sequence: 7, event_type: 'step.finished', status: 'completed' }),
      traceEvent({ sequence: 3, event_type: 'step.started', status: 'running' }),
    ], { event_count: 2 }))
    expect(view.events.map(row => row.sequence)).toEqual(['7', '3'])
    expect(view.events[0].stampText).toBe('2026-09-27 10:00')
  })
})

// ==================== 戊 · 取数只发那一发 ====================

describe('R399 戊 · 三枚读腿各自只发一发', () => {
  it('清单那一发：GET /stage-latency，不带任何参数', async () => {
    http.get.mockResolvedValue({ data: rosterPayload() })
    const view = await loadRunRoster()
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(http.get.mock.calls[0][0]).toBe(STAGE_LATENCY_PATH)
    expect(http.get.mock.calls[0][1]).toBeUndefined()
    expect(view.face).toBe(RUNS_FACE_READY)
  })

  it('事件那一发：GET /traces/<编号>；编号为空就一发都不发，也不替服务端说「没有」', async () => {
    http.get.mockResolvedValue({ data: eventsPayload() })
    const view = await loadTraceEvents('trace-a')
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(http.get.mock.calls[0][0]).toBe('/traces/trace-a')
    expect(view.face).toBe(RUNS_FACE_READY)
    expect(view.traceId).toBe('trace-a')

    http.get.mockClear()
    const idle = await loadTraceEvents('   ')
    expect(http.get).not.toHaveBeenCalled()
    expect(idle.face).toBe(TRACE_FACE_IDLE)
    expect(idle.title).toBe(TRACE_IDLE_TITLE)
  })

  it('分段那一发：GET /stage-latency?trace_id=，与事件那一发各走各的出口形状', async () => {
    http.get.mockResolvedValue({ data: ledgerPayload() })
    const view = await loadTraceLedger('trace-a')
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(http.get.mock.calls[0][0]).toBe(STAGE_LATENCY_PATH)
    expect(http.get.mock.calls[0][1]).toEqual({ params: { trace_id: 'trace-a' } })
    expect(view.face).toBe(RUNS_FACE_READY)
  })

  it('404 / 403 / 500 从网络层回来时，各自落到各自那张脸', async () => {
    http.get.mockRejectedValue(httpError(404, 'resource_not_found'))
    expect((await loadTraceEvents('trace-a')).face).toBe(TRACE_FACE_ABSENT)
    expect((await loadTraceLedger('trace-a')).face).toBe(TRACE_FACE_ABSENT)
    expect((await loadRunRoster()).face).toBe(RUNS_FACE_FAILED)
    http.get.mockRejectedValue(httpError(403, 'permission_denied'))
    expect((await loadTraceEvents('trace-a')).title).toBe(TRACE_DENIED_TITLE)
    expect((await loadTraceLedger('trace-a')).title).toBe(LEDGER_DENIED_TITLE)
    expect((await loadRunRoster()).title).toBe(RUNS_DENIED_TITLE)
    http.get.mockRejectedValue(httpError(500, 'internal_error'))
    expect((await loadTraceEvents('trace-a')).face).toBe(RUNS_FACE_FAILED)
    http.get.mockResolvedValue({ data: { scope: 'process', enabled: true, coverage: { requests: 1, per_request: { a: runEntry() } } } })
    expect(traceEventsPath('trace 中文')).toBe(TRACE_EVENTS_PREFIX + encodeURIComponent('trace 中文'))
  })

  it('失败视图不带半行数据：读不出时屏上不可能同时出现一句「没读到」与半截清单', async () => {
    http.get.mockRejectedValue(httpError(500, 'internal_error'))
    const roster = await loadRunRoster()
    expect(roster.rows).toEqual([])
    const events = await loadTraceEvents('trace-a')
    expect(events.events).toEqual([])
    expect(events.eventCount).toBeNull()
    expect(events.eventsTotal).toBeNull()
    const ledger = await loadTraceLedger('trace-a')
    expect(ledger.rows).toEqual([])
    expect(ledger.missing).toEqual([])
  })
})

// ==================== 己 · 一句话只属于一张脸 ====================

describe('R399 己 · 三格的全部句子两两不等', () => {
  const titles = {
    runsDenied: RUNS_DENIED_TITLE,
    runsUnauthorized: RUNS_UNAUTHORIZED_TITLE,
    runsOff: RUNS_OFF_TITLE,
    runsMalformed: RUNS_MALFORMED_TITLE,
    runsFailed: RUNS_FAILED_TITLE,
    runsEmpty: RUNS_EMPTY_TITLE,
    traceIdle: TRACE_IDLE_TITLE,
    traceAbsent: TRACE_ABSENT_TITLE,
    traceDenied: TRACE_DENIED_TITLE,
    traceUnauthorized: TRACE_UNAUTHORIZED_TITLE,
    traceMalformed: TRACE_MALFORMED_TITLE,
    traceFailed: TRACE_FAILED_TITLE,
    ledgerAbsent: LEDGER_ABSENT_TITLE,
    ledgerDenied: LEDGER_DENIED_TITLE,
    ledgerUnauthorized: LEDGER_UNAUTHORIZED_TITLE,
    ledgerMalformed: LEDGER_MALFORMED_TITLE,
    ledgerEmpty: LEDGER_EMPTY_TITLE,
    ledgerFailed: LEDGER_FAILED_TITLE,
    ledgerIdle: LEDGER_IDLE_TITLE,
  }

  it('十九枚标题一枚都不重复（并成一句含糊话就是这里的红）', () => {
    const values = Object.values(titles)
    expect(new Set(values).size).toBe(values.length)
    for (const [name, value] of Object.entries(titles)) {
      expect(value, name + ' 是空句').toBeTruthy()
      expect(value, name + ' 上没有一句人话').toMatch(/[\u4e00-\u9fff]/)
      // 码名与字段名一个都不许混进标题（no-bare-code 那条屏侧纪律在这一格自己先守住）。
      expect(value, name + ' 里夹带了裸码名').not.toMatch(/[a-z][a-z0-9]*(_[a-z0-9]+)+/)
      expect(value, name + ' 里夹带了源码路径').not.toMatch(/\.py|app\/|GET \//)
    }
  })

  it('每一张脸都点名说自己那一格读的是什么，不互相顶名', () => {
    expect(RUNS_DENIED_TITLE + RUNS_UNAUTHORIZED_TITLE + RUNS_OFF_TITLE + RUNS_MALFORMED_TITLE + RUNS_FAILED_TITLE + RUNS_EMPTY_TITLE).toMatch(/清单/)
    expect(LEDGER_DENIED_TITLE + LEDGER_UNAUTHORIZED_TITLE + LEDGER_MALFORMED_TITLE + LEDGER_FAILED_TITLE + LEDGER_EMPTY_TITLE + LEDGER_ABSENT_TITLE).toMatch(/分段/)
  })

  it('本模块会交出的脸名是封闭集合，多一枚就红（面板按这张表分派画法）', () => {
    const faces = [
      runsBlankView().face,
      runsBlankView(RUNS_FACE_LOADING).face,
      runsViewFromReport(rosterPayload()).face,
      runsViewFromReport(rosterPayload({})).face,
      runsViewFromReport(rosterPayload({}, { enabled: false })).face,
      runsViewFromReport({}).face,
      traceIdleView().face,
      traceBlankView(RUNS_FACE_LOADING).face,
      traceViewFromResponse(eventsPayload()).face,
      ledgerIdleView().face,
      ledgerBlankView(RUNS_FACE_LOADING).face,
      ledgerViewFromResponse(ledgerPayload()).face,
      ledgerViewFromResponse(ledgerPayload({ sample_count: 0 })).face,
      ledgerViewFromResponse({}).face,
      traceReadFailureView(httpError(403, 'permission_denied'), { deniedTitle: 'a', unauthorizedTitle: 'b', failedTitle: 'c' }).face,
      traceReadFailureView(httpError(401, 'authentication_required'), { deniedTitle: 'a', unauthorizedTitle: 'b', failedTitle: 'c' }).face,
      traceReadFailureView(httpError(500, 'internal_error'), { deniedTitle: 'a', unauthorizedTitle: 'b', failedTitle: 'c' }).face,
    ]
    for (const face of faces) expect(TRACE_FACES, '多出来的一张脸：' + String(face)).toContain(face)
    expect(TRACE_FACES).toContain(RUNS_FACE_READY)
    expect(TRACE_FACES).toContain(TRACE_FACE_ABSENT)
    expect(cellKind({ face: 'invented-face' })).toBe('failure')
    expect(cellKind(undefined)).toBe('failure')
  })

  it('未记录那一句全仓只有一份：本模块引用 lib/alerts.js 的 UNRECORDED，不抄第二枚', () => {
    expect(UNRECORDED).toBe('未记录')
    expect(durationText(0)).toBe('0 毫秒')
    expect(durationText(null)).toBe(UNRECORDED)
  })
})
