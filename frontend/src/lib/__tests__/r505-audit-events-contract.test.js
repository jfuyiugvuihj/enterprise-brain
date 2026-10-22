/**
 * R505 判据 C + D · 「审计事件」那枚取数模块（src/lib/auditEvents.js）的对账钉与归脸钉
 *
 * 判据 C 只有一句话：不许把截断藏起来。回包把这件事拆成六格（filters / event_count /
 * events_total / recorded_total / truncated / limits）外加一枚 order，本层逐格转达：
 *  ① 三枚计数各说各的话，本层一枚都不重算 —— 喂进去互相矛盾的三枚数，屏上就照实是那样三枚；
 *  ② 界面上绝不自己造过滤条件：空串那一格整个不发（后端 :1211-1215 剔空不是界面跟着塞的理由）；
 *  ③ 「空」有三种脸，谁都不许冒充谁：筛掉了 / 没记过 / 回执自己打脸。
 * 判据 D：403 / 503 / 500 各一张，另加 401 与形状脸。
 *
 * 字段一律对账 `git show HEAD:app/**`（同 r399 / r505-slo / r505-evaluations 的手法）：
 * 本单一枚后端文件都不改，HEAD 就是那一份真源。真 HTML 在
 * src/components/__tests__/r505-audit-events-screen.test.js。
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../lib/http', async importOriginal => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn() } }
})

import { UNRECORDED } from '../alerts'
import { errorText } from '../errcodes'
import { http, PERMISSION_DENIED } from '../http'
import {
  AUDIT_EMPTY_FILTERED_DESCRIPTION,
  AUDIT_EMPTY_RECORDED_DESCRIPTION,
  AUDIT_EVENTS_PATH,
  AUDIT_FACES,
  AUDIT_FACE_DENIED,
  AUDIT_FACE_EMPTY_FILTERED,
  AUDIT_FACE_EMPTY_RECORDED,
  AUDIT_FACE_FAILED,
  AUDIT_FACE_MALFORMED,
  AUDIT_FACE_READY,
  AUDIT_FACE_STORAGE,
  AUDIT_FACE_UNAUTHORIZED,
  AUDIT_FILTER_FIELDS,
  AUDIT_LOADING_TEXT,
  AUDIT_ORDER_NEWEST_FIRST,
  AUDIT_ORDER_TEXT,
  AUDIT_ORDER_UNKNOWN,
  AUDIT_OUTCOME_LABELS,
  AUDIT_OUTCOME_UNKNOWN,
  AUDIT_RETRYABLE_FACES,
  AUDIT_STORAGE_CODE,
  AUDIT_TITLES,
  auditBlankView,
  auditBoolText,
  auditCountsView,
  auditEventRow,
  auditFaceView,
  auditFilterPairs,
  auditFiltersNote,
  auditLimitsView,
  auditOutcomeLabel,
  auditQuery,
  auditViewFromError,
  auditViewFromResponse,
  loadAuditEvents,
} from '../auditEvents'

const REPO_REF = 'HEAD'
const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const MODULE_SOURCE = read('../auditEvents.js')
const REPO_ROOT = fileURLToPath(new URL('../../../..', import.meta.url))

function gitShow(path) {
  try {
    const text = execFileSync('git', ['show', REPO_REF + ':' + path], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
    if (!text.trim()) throw new Error('内容为空')
    return text
  } catch (cause) {
    throw new Error('读不到真源 ' + REPO_REF + ':' + path + '（git show 失败：' + cause.message + '）。对账不许降级成 skip。')
  }
}
const observability = () => gitShow('app/api/v1/observability.py')
const auditModule = () => gitShow('app/common/audit.py')

/** 那条出口自己写出来的响应键（:1223-1239 那一段 return）。 */
function responseKeys() {
  const body = /return \{\r?\n((?:.*\r?\n)*?) {4}\}/.exec(handlerBody())
  expect(body, '读不到那条出口的 return').toBeTruthy()
  return [...body[1].matchAll(/"([a-z_]+)":/g)].map(match => match[1])
}
function handlerBody() {
  const match = /async def read_audit_events\([\s\S]*?\n\n\n/.exec(observability())
  expect(match, '读不到 read_audit_events 那一条出口').toBeTruthy()
  return match[0]
}
/** 一条审计事件真带的键名（app/common/audit.py 里那枚 event 字典）。 */
function eventKeys() {
  const body = /event: dict\[str, Any\] = \{([\s\S]*?)\n {4}\}/.exec(auditModule())
  expect(body, '读不到那枚 event 字典').toBeTruthy()
  return [...body[1].matchAll(/"([a-z_]+)":/g)].map(match => match[1])
}
/** 全仓 record_audit(principal, action, "outcome", …) 真正写出去的处置词。 */
function backendOutcomeWords() {
  const text = execFileSync('git', ['grep', '-h', '-A3', '-E', 'record_audit\\(', REPO_REF, '--', 'app'], {
    encoding: 'utf8', cwd: REPO_ROOT, maxBuffer: 32 * 1024 * 1024,
  })
  const words = [...text.matchAll(/record_audit\(\s*[^,\n]+,\s*[^,\n]+,\s*"([a-z_]+)"/g)].map(match => match[1])
  expect(words.length, '一条 record_audit 调用都没抓到：对账的尺子本身过期').toBeGreaterThan(3)
  return [...new Set(words)].sort()
}

const EVENT = {
  event_id: 'aud-9f2c', timestamp: '2026-09-29T02:03:04.512+00:00', created_at: '2026-09-29T02:03:04+00:00',
  username: 'lishan', role: 'manager', owner_id: 'u-7', auth_source: 'local', actor_clearance: 2,
  actor_departments: ['研发部', '平台组'], action: 'document:upload', resource: 'doc-31',
  outcome: 'denied', reason: 'clearance_insufficient', request_id: 'req-77',
  resource_scope: { department: '研发部' }, resource_scope_source: 'principal',
  policy_version: 'v3', policy_version_source: 'default', before_summary: null, after_summary: null,
  retention_days: 180, expires_at: '2027-03-28T00:00:00+00:00', persisted: true, storage_mode: 'pg',
}
const REPORT = {
  requested_by: { username: 'root', roles: ['admin'], auth_source: 'local' },
  source: 'app.common.audit.get_audit_events', filters: {}, events: [EVENT],
  event_count: 1, events_total: 1, recorded_total: 12, truncated: false, order: 'newest_first',
  limits: { default_limit: 100, max_limit: 200, applied_limit: 100, requested_limit: null, clamped: false },
}
const REFUSALS = {
  unauthorized: { response: { status: 401, data: { detail: { code: 'authentication_required', message: 'A valid principal is required.', details: {} } } } },
  denied: { response: { status: 403, data: { detail: { code: 'permission_denied', message: 'audit:read is not permitted for this principal.', details: { reason_code: 'clearance_insufficient' } } } } },
  storage: { response: { status: 503, data: { detail: { code: 'storage_unavailable', message: 'audit trail is not readable', details: {} } } } },
  failed: { response: { status: 500, data: { detail: { code: 'internal_error', message: 'audit read blew up', details: {} } } } },
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('R505 甲 · 对账（读 git show ' + REPO_REF + ':app/**）', () => {
  it('出口地址就是那条装饰器；本模块只有一处地址字面量', () => {
    const match = /@router\.get\("([^"]+)", responses=_ERROR_RESPONSES\)\nasync def read_audit_events\(/.exec(observability())
    expect(match, '后端没有这条 GET /audit/events 了：对账的尺子本身过期').toBeTruthy()
    expect(AUDIT_EVENTS_PATH).toBe(match[1])
    expect(MODULE_SOURCE.split("'" + AUDIT_EVENTS_PATH + "'").length - 1).toBe(1)
  })

  it('那一屏读的每一个顶层键名都真在那条出口的 return 里，一枚不多一枚不少', () => {
    const keys = responseKeys()
    expect(keys).toEqual(expect.arrayContaining(['requested_by', 'source', 'filters', 'events', 'event_count', 'events_total', 'recorded_total', 'truncated', 'order', 'limits']))
    for (const key of ['requested_by', 'source', 'filters', 'events', 'event_count', 'events_total', 'recorded_total', 'truncated', 'order', 'limits']) {
      expect(keys, '那条出口不交这一格：' + key).toContain(key)
    }
    for (const key of ['default_limit', 'max_limit', 'applied_limit', 'requested_limit', 'clamped']) {
      expect(handlerBody(), 'limits 里没这一格：' + key).toContain('"' + key + '"')
    }
  })

  it('行模型逐格对得上那枚 event 字典；名册里没有单数 department 这一列', () => {
    const keys = eventKeys()
    const consumed = ['event_id', 'timestamp', 'created_at', 'username', 'role', 'action', 'resource', 'outcome', 'reason', 'request_id', 'actor_departments', 'storage_mode', 'persisted']
    for (const key of consumed) {
      expect(keys, '屏上读了后端没交的一格：' + key).toContain(key)
    }
    // 复数那一格才是真名：把 department 当审计列 = 屏上多出一列界面自己造的归属。
    expect(keys).not.toContain('department')
    expect(auditEventRow(EVENT).actorDepartments).toBe('研发部、平台组')
    expect('department' in auditEventRow(EVENT)).toBe(false)
  })

  it('处置词表逐字对齐 record_audit 真写出去的那四枚，表外只认不下', () => {
    expect(Object.keys(AUDIT_OUTCOME_LABELS).sort()).toEqual(backendOutcomeWords())
    expect(auditOutcomeLabel('maybe_allowed_but_we_hope_not')).toBe(AUDIT_OUTCOME_UNKNOWN)
    expect(auditOutcomeLabel('')).toBe(AUDIT_OUTCOME_UNKNOWN)
    expect(auditOutcomeLabel(null)).toBe(AUDIT_OUTCOME_UNKNOWN)
    // 表外那一格的原名不许丢：审计屏把猜出来的中文当处置结果，比不翻译更坏。
    expect(auditEventRow({ ...EVENT, outcome: 'maybe_allowed_but_we_hope_not' }).outcomeRaw).toBe('maybe_allowed_but_we_hope_not')
  })

  it('order 那一格写死是 newest_first：别的值与缺席各自说一句自己那句', () => {
    expect(handlerBody()).toContain('"order": "newest_first"')
    expect(AUDIT_ORDER_NEWEST_FIRST).toBe('newest_first')
    expect(auditCountsView({ ...REPORT, order: 'oldest_first' }).orderText).toBe(AUDIT_ORDER_UNKNOWN)
    expect(auditCountsView({ ...REPORT, order: 'oldest_first' }).order).toBe('oldest_first')
    expect(auditCountsView({ ...REPORT, order: undefined }).orderText).toBe(AUDIT_ORDER_UNKNOWN)
    expect(auditCountsView(REPORT).orderText).toBe(AUDIT_ORDER_TEXT)
  })

  it('这一屏只有读腿：对 http 的调用只有 http.get 一枚，也不许有 fetch/XHR', () => {
    expect(MODULE_SOURCE.match(/http\.[A-Za-z_$][\w$]*\s*\(/g), '审计屏长出了写腿').toEqual(['http.get('])
    expect(MODULE_SOURCE).not.toMatch(/\b(?:fetch|axios|XMLHttpRequest)\s*\(/)
  })
})

describe('R505 判据 C 之① · 空条件一枚都不许是界面自己造的', () => {
  it('空串、只有空白、缺席的格子整枚不发；发出去的那几枚值非空', () => {
    expect(auditQuery()).toBeUndefined()
    expect(auditQuery({})).toBeUndefined()
    for (const blank of ['', '   ', '\t\n', null, undefined]) {
      expect(auditQuery({ username: blank, action: blank, outcome: blank }), JSON.stringify(blank)).toBeUndefined()
    }
    expect(auditQuery({ username: ' lishan ', action: '' })).toEqual({ username: 'lishan' })
    expect(Object.values(auditQuery({ username: 'a', outcome: 'denied' }))).toEqual(['a', 'denied'])
  })

  it('界面能发的过滤格就是那条出口的形参，一枚不许多一枚不许少', () => {
    const params = /\(\s*request: Request,\s*([\s\S]*?)\)\s*->\s*dict/.exec(handlerBody())
    expect(params, '读不到那条出口的形参').toBeTruthy()
    const names = [...params[1].matchAll(/^\s*(\w+):/gm)].map(match => match[1])
    expect(names).toEqual(['username', 'action', 'outcome', 'limit'])
    expect(AUDIT_FILTER_FIELDS).toEqual(names.slice(0, 3))
  })

  it('limit 那一格：写了才发，只取整数；非数字整枚不发而不是发一枚 NaN', () => {
    expect(auditQuery({ limit: '50' })).toEqual({ limit: 50 })
    expect(auditQuery({ limit: 50.9 })).toEqual({ limit: 50 })
    expect(auditQuery({ limit: 'abc' })).toBeUndefined()
    expect(auditQuery({ limit: '' })).toBeUndefined()
    expect(auditQuery({ limit: null })).toBeUndefined()
  })

  it('filters 只读回执 echo 的那几格，一个都不补；那一句「带没带条件」由回执说', () => {
    expect(auditFilterPairs(undefined)).toEqual([])
    expect(auditFilterPairs('username')).toEqual([])
    expect(auditFilterPairs({ username: 'lishan' })).toEqual([{ key: 'username', value: 'lishan' }])
    // 幂等：壳把 counts.filters（已配好的名册）再递回来时不许读成「没有条件」——
    // 那会让屏上同时列出条件又说没收过，正是判据 C 要治的自相矛盾。
    const pairs = auditFilterPairs({ username: 'lishan', outcome: 'denied' })
    expect(auditFilterPairs(pairs)).toEqual(pairs)
    expect(auditFiltersNote(pairs)).toBe(auditFiltersNote({ username: 'lishan', outcome: 'denied' }))
    expect(auditFilterPairs([{ key: '', value: 'x' }, 'nope', null])).toEqual([])
    expect(auditFiltersNote([{ key: 'username', value: 'lishan' }])).toContain('真正用上')
    expect(auditFiltersNote({ username: 'lishan' })).toContain('真正用上')
    expect(auditFiltersNote({})).toContain('没有收到任何过滤条件')
    expect(auditFiltersNote({})).not.toBe(auditFiltersNote({ username: 'x' }))
  })

  it('读腿：条件全空时第二个实参就是 undefined，屏侧不塞一枚空 params 冒充「筛过一次」', async () => {
    http.get.mockResolvedValue({ data: REPORT })
    await loadAuditEvents({ username: '', action: '', outcome: '', limit: '' })
    expect(http.get.mock.calls[0]).toEqual([AUDIT_EVENTS_PATH, undefined])
    await loadAuditEvents({ username: 'lishan', action: '  ', outcome: '', limit: 5 })
    expect(http.get.mock.calls[1]).toEqual([AUDIT_EVENTS_PATH, { params: { username: 'lishan', limit: 5 } }])
  })
})

describe('R505 判据 C 之② · 三枚计数与那枚截断逐格如实，本层不重算', () => {
  it('喂进三枚互不相同的数，屏上就是那三枚：没有一枚是数行数数出来的', () => {
    const counts = auditCountsView({ ...REPORT, event_count: 3, events_total: 900, recorded_total: 5_000 })
    expect([counts.eventCount, counts.eventsTotal, counts.recordedTotal]).toEqual(['3 条', '900 条', '5000 条'])
    expect(counts.eventCount).not.toBe(counts.eventsTotal)
    expect(counts.eventsTotal).not.toBe(counts.recordedTotal)
  })

  it('缺席的计数说「未记录」，不补零：0 与「没这一格」在审计屏上是两件事', () => {
    const counts = auditCountsView({})
    expect(counts.eventCount).toBe(UNRECORDED)
    expect(counts.eventsTotal).toBe(UNRECORDED)
    expect(counts.recordedTotal).toBe(UNRECORDED)
    expect(counts.truncated).toBeNull()
    expect(counts.truncatedText).toBe(UNRECORDED)
    expect(counts.filters).toEqual([])
  })

  it('truncated=true 说「这一页装不下」，false 说「这一页就是全部」，两句话不许同义', () => {
    const yes = auditCountsView({ ...REPORT, truncated: true }).truncatedText
    const no = auditCountsView({ ...REPORT, truncated: false }).truncatedText
    expect(yes).not.toBe(no)
    expect(yes).toContain('这一页装不下')
    expect(no).toContain('全部')
  })

  it('limits 五格分开说，含「这一发没带 limit」那一句', () => {
    const limits = auditLimitsView(REPORT.limits)
    expect(limits.defaultLimit).toBe('100 条')
    expect(limits.maxLimit).toBe('200 条')
    expect(limits.appliedLimit).toBe('100 条')
    expect(limits.requestedLimit).toBe('这一发没带 limit')
    expect(limits.clamped).toBe(false)
    expect(limits.clampedText).toBe('没夹')
    const clamped = auditLimitsView({ default_limit: 100, max_limit: 200, applied_limit: 200, requested_limit: 9_000, clamped: true })
    expect(clamped.requestedLimit).toBe('9000 条')
    expect(clamped.clampedText).toBe('被后端夹过')
    expect(auditLimitsView(null).maxLimit).toBe(UNRECORDED)
  })

  it('布尔三档：true / false / 回执没答 —— 审计屏不替后端答第三档', () => {
    expect(auditBoolText(true, '甲', '乙')).toBe('甲')
    expect(auditBoolText(false, '甲', '乙')).toBe('乙')
    for (const notABoolean of ['true', 1, 0, null, undefined]) {
      expect(auditBoolText(notABoolean, '甲', '乙'), JSON.stringify(notABoolean)).toBe(UNRECORDED)
    }
  })
})

describe('R505 判据 C 之③ · 三种「空」各自一张脸，谁都不许冒充谁', () => {
  it('筛掉了 ≠ 没记过：两句话两枚标题，各自点名自己是哪一种', () => {
    const filtered = auditViewFromResponse({ ...REPORT, events: [], event_count: 0, events_total: 0, recorded_total: 12, filters: { username: 'nobody' } })
    const never = auditViewFromResponse({ ...REPORT, events: [], event_count: 0, events_total: 0, recorded_total: 0, filters: {} })
    expect(filtered.face).toBe(AUDIT_FACE_EMPTY_FILTERED)
    expect(never.face).toBe(AUDIT_FACE_EMPTY_RECORDED)
    expect(filtered.title).toBe(AUDIT_TITLES[AUDIT_FACE_EMPTY_FILTERED])
    expect(filtered.description).toBe(AUDIT_EMPTY_FILTERED_DESCRIPTION)
    expect(never.description).toBe(AUDIT_EMPTY_RECORDED_DESCRIPTION)
    expect(filtered.title).not.toBe(never.title)
    expect(filtered.description).not.toBe(never.description)
  })

  it('回执自己打脸（全库有记录、没带条件却交回空清单）走形状脸，不许被并进前两种空', () => {
    const view = auditViewFromResponse({ ...REPORT, events: [], event_count: 0, recorded_total: 12, filters: {} })
    expect(view.face).toBe(AUDIT_FACE_MALFORMED)
    expect(view.description).toContain('打脸')
  })

  it('有事件就是正常脸：标题留空，让账自己说话', () => {
    const view = auditViewFromResponse(REPORT)
    expect(view.face).toBe(AUDIT_FACE_READY)
    expect(view.title).toBe('')
    expect(view.rows).toHaveLength(1)
    expect(view.rows[0].outcomeText).toBe(AUDIT_OUTCOME_LABELS.denied)
    expect(view.rows[0].stampText).toBe('2026-09-29 02:03')
    expect(view.rows[0].persistedText).toBe('这条已经落盘')
  })

  it('读不出 events / 计数就是形状脸，不许滑成「没有事件」', () => {
    for (const payload of [undefined, null, {}, { events: [] }, { events: [], event_count: 0 }, { events: 'nope', event_count: 0, recorded_total: 1 }]) {
      expect(auditViewFromResponse(payload).face, JSON.stringify(payload)).toBe(AUDIT_FACE_MALFORMED)
    }
  })

  it('一条事件读不到 event_id 时行键退回可寻址占位，用户名那格仍说「未记录」', () => {
    const row = auditEventRow({})
    expect(row.id).toBe('audit-row-unaddressable')
    expect(row.username).toBe('')
    expect(row.persisted).toBeNull()
    expect(row.persistedText).toBe(UNRECORDED)
  })
})

describe('R505 判据 D · 三张失败脸分开留名', () => {
  const failureFaces = [AUDIT_FACE_UNAUTHORIZED, AUDIT_FACE_DENIED, AUDIT_FACE_STORAGE, AUDIT_FACE_FAILED, AUDIT_FACE_MALFORMED]

  it('九张脸九格名册定长，五张失败/空脸标题两两不等', () => {
    expect(AUDIT_FACES).toEqual(['loading', 'ready', 'empty_filtered', 'empty_recorded', 'unauthorized', 'denied', 'storage', 'malformed', 'failed'])
    const titles = failureFaces.map(face => AUDIT_TITLES[face])
    expect(new Set(titles).size).toBe(5)
    titles.forEach(title => expect(title).toBeTruthy())
    expect(AUDIT_TITLES[AUDIT_FACE_READY]).toBe('')
    expect(auditBlankView().description).toBe(AUDIT_LOADING_TEXT)
    // 点名要哪张脸就得是哪张脸：把形状脸折成 failed，判据 D 就少一张（本单真踩过这一格）。
    expect(auditBlankView(AUDIT_FACE_MALFORMED).face).toBe(AUDIT_FACE_MALFORMED)
    expect(auditBlankView(AUDIT_FACE_MALFORMED).title).toBe(AUDIT_TITLES[AUDIT_FACE_MALFORMED])
    expect(auditBlankView('not_a_face_at_all').face).toBe(AUDIT_FACE_FAILED)
    expect(auditViewFromResponse({}).face).toBe(AUDIT_FACE_MALFORMED)
  })

  it('403 / 503 / 500 各落各的脸，两两不等；401 与形状脸也不同名', () => {
    const three = [REFUSALS.denied, REFUSALS.storage, REFUSALS.failed].map(auditViewFromError)
    expect(three.map(view => view.face)).toEqual([AUDIT_FACE_DENIED, AUDIT_FACE_STORAGE, AUDIT_FACE_FAILED])
    expect(new Set(three.map(view => view.title)).size).toBe(3)
    expect(auditViewFromError(REFUSALS.unauthorized).face).toBe(AUDIT_FACE_UNAUTHORIZED)
  })

  it('503 认状态码也认码名：后端只回一枚裸码、没带状态码时也得落在存储那一格上', () => {
    expect(auditViewFromError({ response: { data: { detail: { code: AUDIT_STORAGE_CODE, message: 'nope' } } } }).face).toBe(AUDIT_FACE_STORAGE)
    expect(auditViewFromError({ response: { data: { detail: { code: PERMISSION_DENIED, message: 'nope' } } } }).face).toBe(AUDIT_FACE_DENIED)
  })

  it('403 那句出自全仓唯一的字典，后面接「下一步去哪」，并且不许出现「没有事件」那种说法', () => {
    const view = auditViewFromError(REFUSALS.denied)
    expect(view.description.startsWith(errorText(PERMISSION_DENIED))).toBe(true)
    expect(view.description).toContain('重新登录')
    expect(view.description).not.toContain('一条审计事件都没记下')
    expect(view.rows).toEqual([])
    expect(view.counts.recordedTotal).toBe(UNRECORDED)
  })

  it('只有 failed / malformed 值得再按一次；权限与存储要人先动手', () => {
    for (const face of [AUDIT_FACE_DENIED, AUDIT_FACE_STORAGE, AUDIT_FACE_UNAUTHORIZED, AUDIT_FACE_EMPTY_FILTERED, AUDIT_FACE_EMPTY_RECORDED]) {
      expect(auditFaceView({ face }).retryable, face).toBe(false)
    }
    expect(AUDIT_RETRYABLE_FACES).toEqual([AUDIT_FACE_FAILED, AUDIT_FACE_MALFORMED])
    expect(auditFaceView(null).face).toBe('')
    expect(auditFaceView({ face: 'who_knows' }).title).toBe(AUDIT_TITLES[AUDIT_FACE_FAILED])
  })

  it('读腿把失败也变成一次归脸：不抛出', async () => {
    http.get.mockRejectedValue(REFUSALS.failed)
    await expect(loadAuditEvents({ username: 'lishan' })).resolves.toMatchObject({ face: AUDIT_FACE_FAILED })
  })
})
