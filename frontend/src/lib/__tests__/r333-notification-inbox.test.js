/**
 * R333 判据①②③④⑤ · 通知中心的读写出路（lib/notifications.js）
 *
 * 环境是 node（仓库里没有 jsdom / @vue/test-utils，也不许 npm i）：这一件全部打在【逻辑腿】上，
 * 网络层换成 mock，而 errorDetail / errorCodeOf / 词典句子保持真身 —— 否则「失败要有脸」
 * 会被 mock 顺带改掉，判据③就成了自证。
 *
 * 三条腿各管各的，不假装验过自己验不了的：
 *   ① 真调用形状：mock 只替换 axios 实例，断言的是【这一发请求长什么样】（路径、params、body）。
 *   ② 真归码真句子：503 / 401 / 断网三档喂真码进真 errcodes，再读回来的句子——不 grep 常量冒充。
 *   ③ 源码形状：判据②那条「不许新开请求层」只能钉在源码上（本层不 import axios、不写 fetch、
 *      不拼 /api/v1、不碰本地存储），因为运行时已经没有第二条路可走了。
 *
 * 与本件相关的反证（本单实跑过红→绿，逐枚数字在交回里）：
 *   · 把徽标改成页内条数 → 甲1 / 甲2 红（normalizeInbox 根本不往上交本页长度）；
 *   · 把 503 当空态 → 乙1 与戊1 红（未知抛形状错、503 有自己那张脸）；
 *   · 把 changed=false 也算进未读下降 → 丙3 红（回执说 0 枚变化就是 0，前端再减一次就是假话）；
 *   · 把「回执少一枚」放过去 → 丙5 红（不许收到几条算几条）。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// 只换网络层：errcodes 与 alerts 的真身留着，判据③的句子才真是从词典出来的。
vi.mock('../http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn() } }
})

import { http } from '../http'
import { ERROR_CODES } from '../errcodes'
import {
  ALL_FILTER,
  DENIED_WHERE,
  DISMISS_ACTION_PATH,
  INBOX_PAGE_LIMIT,
  INBOX_PATH,
  MAX_COLLECTION_PAGES,
  MAX_IDS_PER_CALL,
  READ_ACTION_PATH,
  READ_DENIED_TITLE,
  READ_FAILED_TITLE,
  STORAGE_TITLE,
  InboxShapeError,
  applyAction,
  bellLabel,
  badgeText,
  chunkIds,
  collectUnreadIds,
  dismissNotifications,
  markAllUnread,
  markRead,
  normalizeInbox,
  normalizeReceipt,
  readFailureViewOf,
  readInbox,
  shapeFailureViewOf,
} from '../notifications'

/** 注释里本来就写着「不 import axios、不写 fetch、不拼 /api/v1」，负例一律在剥掉注释的文本上跑。 */
const stripComments = (text) => text
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/^[ \t]*\/\/.*$/gm, '')
const source = readFileSync(new URL('../notifications.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const code = stripComments(source)

/** 契约 R299 那一响应的键，一枚不多一枚不少（本页两格与全集两格刻意给不同的数，反证就靠这对差值）。 */
function inboxPage(overrides = {}) {
  return {
    notifications: [],
    state: ALL_FILTER,
    limit: INBOX_PAGE_LIMIT,
    offset: 0,
    returned: 3,
    has_more: false,
    total: 50,
    unread_total: 42,
    unread_returned: 3,
    is_exact: true,
    sources: {},
    ...overrides,
  }
}

function row(id, state = 'unread') {
  return {
    id,
    source_type: id.split(':')[0],
    source_id: id.split(':')[1],
    title: '通知 ' + id,
    detail: '正文 ' + id,
    created_at: '2026-09-26T09:00:00+08:00',
    state,
    reference: {},
  }
}

/** 一次写的回执：results 逐枚带 state / changed / reason（后端 _apply 的形状）。 */
function receipt(ids, changed = ids) {
  const set = new Set(Array.isArray(changed) ? changed : [changed])
  return {
    action: 'read',
    requested: ids.length,
    changed: ids.filter(id => set.has(id)).length,
    results: ids.map(id => ({ id, state: 'read', changed: set.has(id), reason: 'applied' })),
  }
}

function axiosError(status, detail) {
  return { isAxiosError: true, message: 'Request failed with status code ' + status, response: { status, data: { detail } } }
}

function networkError() {
  return { isAxiosError: true, code: 'ERR_NETWORK', message: 'Network Error', request: {}, response: undefined }
}

const unreadIds = (count, from = 0) => Array.from({ length: count }, (_item, index) => 'alert:' + (index + 1 + from))

beforeEach(() => {
  vi.clearAllMocks()
  http.get.mockResolvedValue({ data: inboxPage() })
  // 默认回执：后端逐枚交回 results，这里按「请求了几枚就动了几个」回，形状先对上
  http.post.mockImplementation(async (_path, postData) => ({ data: receipt(postData.ids, postData.ids) }))
})

// ==================== 甲 · 判据①② · 数字只可能来自后端全集口径 ====================

describe('R333 判据① · 未读数由后端说话', () => {
  it('normalizeInbox 只交回全集那一格，本页两条长度就地丢掉（想拿页内条数当总数也没有原料）', () => {
    const inbox = normalizeInbox(inboxPage({
      unread_total: 42,
      total: 50,
      returned: 3,
      unread_returned: 3,
      notifications: [row('alert:1'), row('alert:2'), row('alert:3')],
    }))
    expect(inbox.unread).toBe(42)
    expect(inbox.total).toBe(50)
    expect(inbox.rows).toHaveLength(3)
    // 本页那两格不许存在：判据①的防线不是「组件别用错」，而是「这一层不递给它用错的机会」。
    expect(inbox).not.toHaveProperty('returned')
    expect(inbox).not.toHaveProperty('unreadReturned')
    expect(inbox).not.toHaveProperty('unread_returned')
    expect(JSON.stringify(Object.keys(inbox).sort())).toBe(JSON.stringify(['hasMore', 'isExact', 'limit', 'offset', 'rows', 'state', 'total', 'unread']))
  })

  it('翻到最后一页、或按未读过滤，徽标数字都不许跟着页变（总数与分页无关，与过滤无关）', () => {
    const first = normalizeInbox(inboxPage({ notifications: [row('alert:1')], returned: 1, unread_returned: 1 }))
    const last = normalizeInbox(inboxPage({ state: 'unread', offset: 40, limit: 20, notifications: [row('alert:2'), row('alert:3')], returned: 2, unread_returned: 2 }))
    expect([first.unread, last.unread]).toEqual([42, 42])
    expect(first.rows.length).not.toBe(last.rows.length)
    expect(badgeText(last.unread, { isExact: last.isExact })).toBe('42')
    expect(bellLabel(last.unread, { isExact: last.isExact })).toBe('通知，42 条未读通知')
  })

  it('is_exact=false 时说的是「至少」：两个总数只是下界，不许冒充正好', () => {
    const trimmed = normalizeInbox(inboxPage({ is_exact: false }))
    expect(trimmed.isExact).toBe(false)
    expect(badgeText(trimmed.unread, { isExact: trimmed.isExact })).toBe('42+')
    expect(bellLabel(trimmed.unread, { isExact: trimmed.isExact })).toBe('通知，至少 42 条未读通知')
    // 后端没给这一格也按不精确说话（fail-closed），而不是默认「精确」把下界说成全数。
    const missing = inboxPage()
    delete missing.is_exact
    expect(normalizeInbox(missing).isExact).toBe(false)
  })
})

describe('R333 判据② · 请求只走 lib/http.js 那一枚既有出口', () => {
  it('读一发：路径与 params 就是契约那三条查询参数，不拼前缀、不自己带 token', async () => {
    await readInbox({ state: ALL_FILTER, limit: INBOX_PAGE_LIMIT, offset: 0 })
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(http.get.mock.calls[0][0]).toBe(INBOX_PATH)
    expect(http.get.mock.calls[0][1]).toEqual({ params: { state: 'all', limit: 100, offset: 0 } })
  })

  it('写一发：body 只有 ids 那一格（收件人不从 body 读，多塞一枚都算越契约）', async () => {
    await markRead(['alert:701'])
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(http.post.mock.calls[0][0]).toBe(READ_ACTION_PATH)
    expect(http.post.mock.calls[0][1]).toEqual({ ids: ['alert:701'] })
    await dismissNotifications(['alert:702'])
    expect(http.post.mock.calls[1][0]).toBe(DISMISS_ACTION_PATH)
    expect(http.post.mock.calls[1][1]).toEqual({ ids: ['alert:702'] })
  })

  it('本层不 import axios、不写 fetch、不拼 /api/v1、不碰本地存储（判据②与⑤的源码腿）', () => {
    expect(code).not.toMatch(/axios/)
    expect(code).not.toMatch(/(^|[^.\w])fetch\s*\(/)
    expect(code).not.toMatch(/\/api\/v1/)
    expect(code).not.toMatch(/Authorization|Bearer|eb_token/)
    expect(code).not.toMatch(/localStorage|sessionStorage|indexedDB/)
    expect(code).toMatch(/from '\.\/http'/)
  })
})

// ==================== 乙 · 判据③ · 读不到不许伪装成「没有通知」 ====================

describe('R333 判据③ · 0 不许当未知用（反证：把缺失当 0 就红）', () => {
  it('未读总数那一格缺失 / 不是数 / 负数 ⇒ 抛形状错，而不是交回一个 0', () => {
    const cases = [{ unread_total: undefined }, { unread_total: null }, { unread_total: '42' }, { unread_total: -1 }, { unread_total: NaN }]
    cases.forEach((override) => {
      expect(() => normalizeInbox(inboxPage(override)), JSON.stringify(override.unread_total)).toThrow(InboxShapeError)
    })
    expect(() => normalizeInbox(inboxPage({ total: undefined }))).toThrow(InboxShapeError)
    expect(() => normalizeInbox(inboxPage({ notifications: undefined }))).toThrow(InboxShapeError)
    expect(() => normalizeInbox(undefined)).toThrow(InboxShapeError)
    expect(() => normalizeInbox([])).toThrow(InboxShapeError)
  })

  it('真空态与未读到是两张脸：0 说「没有未读」，未知说「还没读出来」，两句话不许互换', () => {
    const empty = normalizeInbox(inboxPage({ unread_total: 0, total: 0, returned: 0, unread_returned: 0 }))
    expect(empty.unread).toBe(0)
    expect(badgeText(0)).toBe('')
    expect(bellLabel(0)).toBe('通知，没有未读通知')
    expect(badgeText(null)).toBe('')
    expect(bellLabel(null)).toBe('通知，未读数还没读出来')
    expect(bellLabel(null)).not.toBe(bellLabel(0))
    expect(bellLabel(undefined, { failed: true })).toBe('通知没能读出来，打开可以看到原因')
  })

  it('读到的行只可能来自响应：字段照契约抄，没给标题那一枚不编内容', () => {
    const inbox = normalizeInbox(inboxPage({ notifications: [row('alert:701'), { id: 'document:a.md#v2', state: 'read' }] }))
    expect(inbox.rows[0]).toEqual({
      id: 'alert:701',
      sourceType: 'alert',
      sourceId: '701',
      title: '通知 alert:701',
      detail: '正文 alert:701',
      createdAt: '2026-09-26 09:00',
      state: 'unread',
      read: false,
    })
    expect(inbox.rows[1].title).toBe('（这一枚没给标题）')
    expect(inbox.rows[1].read).toBe(true)
    expect(inbox.rows[1].createdAt).toBe('')
  })
})

// ==================== 丙 · 判据④ · 幂等、切批、回执可分辨 ====================

describe('R333 判据④ · 一次动作超过 50 枚就切批，一枚都不许静默丢', () => {
  const manyIds = unreadIds(120)

  it('chunkIds：120 枚切成 50 / 50 / 20，摊平后与去重后的清单逐枚同序相等', () => {
    const batches = chunkIds(manyIds)
    expect(batches.map(batch => batch.length)).toEqual([50, 50, 20])
    expect(batches.every(batch => batch.length <= MAX_IDS_PER_CALL)).toBe(true)
    expect(batches.flat()).toEqual(manyIds)
  })

  it('重复 id 先收敛成一枚：同一枚点两次不该发两遍，也不该在批次里出现两次', () => {
    expect(chunkIds(['alert:1', 'alert:1', ' alert:2 ', '', null, 'alert:2']).flat()).toEqual(['alert:1', 'alert:2'])
  })

  it('120 枚真发出去是三发请求，每发都不超过后端上界，聚合后的 requested 是 120（不是 50）', async () => {
    const result = await applyAction(READ_ACTION_PATH, manyIds)
    expect(http.post).toHaveBeenCalledTimes(3)
    http.post.mock.calls.forEach(call => expect(call[1].ids.length).toBeLessThanOrEqual(MAX_IDS_PER_CALL))
    expect(result.requested).toBe(120)
    expect(result.changed).toBe(120)
    expect(result.batches).toBe(3)
  })

  it('第 N 次点同一枚：回执 changed=false 聚合出来仍是 0 枚变化，前端不替后端再记一遍', async () => {
    http.post.mockResolvedValue({ data: receipt(['alert:9'], []) })
    const again = await markRead(['alert:9'])
    expect(again.requested).toBe(1)
    expect(again.changed).toBe(0)
    expect(again.results[0].state).toBe('read')
    expect(again.results[0].changed).toBe(false)
  })

  it('对不上号与不属于你同一张脸：refused 数得出来，码名与理由都不上屏', () => {
    const payload = {
      action: 'dismiss',
      requested: 2,
      changed: 1,
      results: [
        { id: 'alert:701', state: 'dismissed', changed: true, reason: 'applied' },
        { id: 'approval:other', state: null, changed: false, reason: 'notification_not_addressable' },
      ],
    }
    const parsed = normalizeReceipt(payload, ['alert:701', 'approval:other'])
    expect(parsed).toMatchObject({ requested: 2, changed: 1, refused: 1 })
    expect(parsed.results[1].state).toBe('')
    expect(JSON.stringify(parsed)).not.toMatch(/notification_not_addressable/)
  })

  it('回执少交一枚就是形状错：不许「收到几条算几条」', () => {
    expect(() => normalizeReceipt(receipt(['alert:1', 'alert:2']), ['alert:1', 'alert:2', 'alert:3'])).toThrow(InboxShapeError)
    expect(() => normalizeReceipt({ action: 'read' }, ['alert:1'])).toThrow(InboxShapeError)
  })

  it('空清单一发都不发：后端对空 ids 回 422，这里不许自己制造一次失败', async () => {
    const result = await markRead([])
    expect(http.post).not.toHaveBeenCalled()
    expect(result).toMatchObject({ requested: 0, changed: 0, refused: 0 })
  })

  it('任何一批失败就不再发后面的批：半截成功不许说成全部完成', async () => {
    http.post.mockRejectedValue(axiosError(503, 'storage_unavailable'))
    await expect(applyAction(READ_ACTION_PATH, manyIds)).rejects.toBeTruthy()
    expect(http.post).toHaveBeenCalledTimes(1)
  })
})

// ==================== 丁 · 「全部标已读」的 id 从后端逐页来 ====================

describe('R333 判据④⑤ · 全部标已读收的是后端逐页交回的 id', () => {
  function pageOf(ids, hasMore, offset) {
    return inboxPage({
      state: 'unread',
      notifications: ids.map(id => row(id)),
      returned: ids.length,
      unread_returned: ids.length,
      has_more: hasMore,
      offset,
    })
  }

  it('两页 150 枚收齐才发写：读的 params 是 state=unread，页与页之间靠 offset 走', async () => {
    http.get
      .mockResolvedValueOnce({ data: pageOf(unreadIds(100), true, 0) })
      .mockResolvedValueOnce({ data: pageOf(unreadIds(50, 100), false, 100) })
    const result = await markAllUnread()
    expect(http.get.mock.calls.map(call => call[1].params)).toEqual([
      { state: 'unread', limit: INBOX_PAGE_LIMIT, offset: 0 },
      { state: 'unread', limit: INBOX_PAGE_LIMIT, offset: 100 },
    ])
    expect(result.requested).toBe(150)
    expect(http.post).toHaveBeenCalledTimes(3)
  })

  it('后端说还有更多却不给行 ⇒ 抛错，不能把「没收完」画成「已读完」', async () => {
    http.get.mockResolvedValue({ data: pageOf([], true, 0) })
    await expect(collectUnreadIds()).rejects.toBeInstanceOf(InboxShapeError)
    expect(http.post).not.toHaveBeenCalled()
  })

  it('翻页撞到自己那枚安全阀也抛错：宁可失败，不许报一个「全部已读」的假成功', async () => {
    http.get.mockResolvedValue({ data: pageOf(unreadIds(100), true, 0) })
    await expect(collectUnreadIds()).rejects.toBeInstanceOf(InboxShapeError)
    expect(http.get).toHaveBeenCalledTimes(MAX_COLLECTION_PAGES)
    expect(http.post).not.toHaveBeenCalled()
  })

  it('未读为零时一发写请求都不发：空清单不是失败，也不该发出去换一枚 422', async () => {
    http.get.mockResolvedValue({ data: pageOf([], false, 0) })
    const result = await markAllUnread()
    expect(result.requested).toBe(0)
    expect(http.post).not.toHaveBeenCalled()
  })
})

// ==================== 戊 · 判据③的三张失败脸 ====================

describe('R333 判据③ · 503 / 401 / 断网是三张不同的脸，句子一律出自词典', () => {
  it('503 表没就绪：有自己那张脸，句子逐字出自词典，且不挂重试（重试不会把迁移跑出来）', () => {
    const view = readFailureViewOf(axiosError(503, 'storage_unavailable'))
    expect(view.face).toBe('storage')
    expect(view.title).toBe(STORAGE_TITLE)
    expect(view.description).toBe(ERROR_CODES.storage_unavailable.message)
    expect(view.retryable).toBe(false)
  })

  it('401：念得出「登录状态已失效」，与 503、与断网两两不同句', () => {
    const view = readFailureViewOf(axiosError(401, 'authentication_required'))
    expect(view.face).toBe('unauthorized')
    expect(view.title).toBe('登录状态已失效')
    expect(view.description).toBe(ERROR_CODES.authentication_required.message)
    expect(view.retryable).toBe(false)
    expect(view.title).not.toBe(STORAGE_TITLE)
  })

  it('断网：归到「真坏了」那一档并给重新加载，句子说的是连不上而不是没有', () => {
    const view = readFailureViewOf(networkError())
    expect(view.face).toBe('error')
    expect(view.title).toBe(READ_FAILED_TITLE)
    expect(view.description).toContain('连不上服务')
    expect(view.retryable).toBe(true)
  })

  it('没权限那张脸是预留（本资源今天发不出 403），句子不许借用告警那一屏的说法', () => {
    const view = readFailureViewOf(axiosError(403, 'permission_denied'))
    expect(view.face).toBe('denied')
    expect(view.title).toBe(READ_DENIED_TITLE)
    expect(view.description).toContain(DENIED_WHERE)
    expect(view.description).not.toContain('告警')
    expect(view.retryable).toBe(false)
  })

  it('形状不合走另一条出口：没有错误对象可归码时按「坏了」说，绝不退成空态', () => {
    const view = shapeFailureViewOf()
    expect(view.face).toBe('error')
    expect(view.title).toBe(READ_FAILED_TITLE)
    expect(view.retryable).toBe(true)
    expect(readFailureViewOf(new Error('boom')).face).toBe('error')
  })

  it('句子绝不夹裸码名：四档脸的 description 里没有 snake_case（no-bare-code 之外的第二道自查）', () => {
    const cases = [
      axiosError(503, 'storage_unavailable'),
      axiosError(401, 'authentication_required'),
      axiosError(403, 'permission_denied'),
      networkError(),
    ]
    cases.forEach((err) => {
      const view = readFailureViewOf(err)
      expect(/[a-z][a-z0-9]*_[a-z0-9]+/.test(view.description), view.face + ' ⇒ ' + view.description).toBe(false)
    })
  })
})


