/**
 * R385 判据②④⑦ · 缺席台账在真 HTML 上画得出什么（挂载 / renderToString 级）
 *
 * 为什么这一枚文件必须存在：R375 那一单因为「只验到 view 对象、没验到 DOM」被记了半证，
 * 本单判据⑦点名不许再犯。所以这里的每一条主断言都从 renderToString 出来的那段字符串上取，
 * 包括那句人话本身——交回里给的原句是从下面 rendered() 的返回值里截的，不是从源码抄的。
 *
 * 环境仍是 node + @vue/server-renderer（仓里没有 jsdom / @vue/test-utils，也不许 npm i），
 * 三条腿各管各的，不假装验过自己验不了的：
 *   ① 真状态：把 lib/http 那枚共享实例换成 mock，跑组件真 setup() 与真 refresh()；
 *   ② 真产物：同一份绑定交回组件自带的 ssrRender 出真 HTML；
 *   ③ 源码形状：只有「布局不遮正文」这一条量不到（node 里没有排版引擎），
 *      就退而钉它的形状：那条新块不带 position，且它在面板里排在正文之前。
 *      这一条在交回里按「半证」报，不算 DOM 证。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'

vi.mock('../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn() } }
})

import { http } from '../lib/http'
import NotificationBell, {
  EMPTY_TITLE,
  LEDGER_CAUSES,
  LEDGER_LEGS,
  absenceLines,
  bellAriaLabel,
  ledgerCells,
  ledgerSums,
  readInboxPage,
} from '../components/NotificationBell.vue'
import { ERROR_CODES } from '../lib/errcodes'

const bellSource = readFileSync(new URL('../components/NotificationBell.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const stripComments = (text) => text
  .replace(/<!--[\s\S]*?-->/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/^[ \t]*\/\/.*$/gm, '')
const bellCode = stripComments(bellSource)

/** 一格账本：默认「这本账在答，且确实没有」。 */
const cell = (overrides = {}) => ({
  included: true, reason_code: 'ok', candidates: 0, scanned: 0, truncated: false, ...overrides,
})

/** 一份收件箱响应：计数账固定，只有台账那一台在三条腿之间变。 */
function inboxPayload(sources, overrides = {}) {
  return {
    notifications: [],
    state: 'all',
    limit: 100,
    offset: 0,
    returned: 0,
    has_more: false,
    total: 3,
    unread_total: 3,
    unread_returned: 0,
    is_exact: true,
    sources: sources === undefined ? {} : sources,
    ...overrides,
  }
}

const ALL_ANSWERING = { approval: cell(), alert: cell(), document: cell() }
const APPROVAL_SILENT = {
  approval: cell({ included: false, reason_code: 'storage_unavailable' }),
  alert: cell(),
  document: cell(),
}

function row(id, state = 'unread') {
  return {
    id, source_type: id.split(':')[0], source_id: id.split(':')[1],
    title: '标题 ' + id, detail: '正文 ' + id, created_at: '2026-09-27T09:00:00+08:00',
    state, reference: {},
  }
}

/** 跑真 setup()：借最小宿主组件把实例上下文递进去（onMounted 挂在真实例上，SSR 不触发）。 */
async function mountBindings() {
  let bindings = null
  const Probe = {
    name: 'R385Probe',
    setup(props, ctx) {
      bindings = NotificationBell.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Probe))
  expect(bindings, '组件应交出可调用的 setup() 绑定').toBeTruthy()
  return bindings
}

const renderState = bindings => renderToString(h({ ...NotificationBell, setup: () => bindings }))

/** 真读一次 + 真渲染一次，面板展开。交回 { bindings, html }。 */
async function renderInbox(payload, open = true) {
  http.get.mockResolvedValue({ data: payload })
  const bindings = await mountBindings()
  await bindings.refresh()
  bindings.open.value = open
  return { bindings, html: await renderState(bindings) }
}

/** 面板里那一段缺席块的可见文字（剥标签，只留人读得到的那几句）。 */
function ledgerTextOf(html) {
  const block = /<ul[^>]*data-testid="notification-ledger"[^>]*>([\s\S]*?)<\/ul>/.exec(html)
  if (!block) return null
  return block[1].replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
}

/** 整屏可见文字（判据②拿它证明状态名一个都没上屏）。 */
function visibleText(html) {
  return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ')
}

/**
 * 把「台账那一段」从渲染结果里整体擦掉：缺席块本体 + 读屏句子里并进去的那半截。
 * 丙组拿它做减法对平——擦掉之后必须与全供数那一屏逐字节相等，
 * 差一个字符就说明台账伸进了计数账的地盘（判据④）。
 */
function stripLedger(html) {
  return html
    .replace(/<ul[^>]*data-testid="notification-ledger"[\s\S]*?<\/ul>/g, '<!---->')
    .replace(/(aria-label|title)="([^"]*)"/g, (match, attr, value) => attr + '="' + value.split('；')[0] + '"')
}

beforeEach(() => {
  vi.clearAllMocks()
})

// ==================== 甲 · 判据⑦：那句话说得出，而且只在真缺席时说 ====================

describe('R385 甲 · 判据⑦：缺席句在真 HTML 上画得出', () => {
  it('审批那一格不供数 ⇒ 面板里画得出那句人话，原文逐字取自渲染结果', async () => {
    const { html } = await renderInbox(inboxPayload(APPROVAL_SILENT))
    const text = ledgerTextOf(html)
    expect(text, '屏上根本没有这一段').toBeTruthy()
    expect(text).toContain('审批账本这次没答上来')
    expect(text).toContain('它要的数据表在这台机器上还没准备好')
    expect(text).toContain('不代表那一类事情真的没有')
    expect((html.match(/data-testid="notification-ledger-item"/g) || [])).toHaveLength(1)
  })

  it('三格都在答 ⇒ 面板一个字符都不许多（与「压根没有 sources 这一格」逐字节相等）', async () => {
    const answering = await renderInbox(inboxPayload(ALL_ANSWERING))
    const missing = await renderInbox(inboxPayload(undefined))
    expect(answering.html).toBe(missing.html)
    expect(answering.html).not.toContain('没答上来')
    expect(answering.html).not.toContain('notification-ledger')
    expect(answering.html).not.toContain('系统正常')
  })

  it('「账本在答、确实没有」与「这一格不供数」是两张脸：同一枚 0 条未读，两屏不同字', async () => {
    const clean = await renderInbox(inboxPayload({ approval: cell(), alert: cell(), document: cell() }, { total: 0, unread_total: 0, unread_returned: 0 }))
    const silent = await renderInbox(inboxPayload(APPROVAL_SILENT, { total: 0, unread_total: 0, unread_returned: 0 }))
    expect(clean.html).toContain(EMPTY_TITLE)
    expect(ledgerTextOf(clean.html)).toBe(null)
    expect(silent.html).toContain(EMPTY_TITLE)
    expect(ledgerTextOf(silent.html)).toContain('审批账本')
    expect(silent.html.length).toBeGreaterThan(clean.html.length)
  })

  it('两格同时不供数 ⇒ 两句话都在，各占一行，不并成一句含糊话', async () => {
    const { html } = await renderInbox(inboxPayload({
      approval: cell({ included: false, reason_code: 'storage_unavailable' }),
      alert: cell({ included: false, reason_code: 'permission_denied' }),
      document: cell(),
    }))
    const text = ledgerTextOf(html)
    expect((html.match(/data-testid="notification-ledger-item"/g) || [])).toHaveLength(2)
    expect(text).toContain('审批账本')
    expect(text).toContain('告警账本')
    expect(text).toContain('这个账号没有看它的权限')
    expect(text.split('这次没答上来')).toHaveLength(3)
  })

  it('读失败那一档不画缺席句：读不到时台账未知，不是「有一格没答」，也不留「系统正常」', async () => {
    http.get.mockRejectedValue({ isAxiosError: true, message: 'Network Error', request: {}, response: undefined })
    const bindings = await mountBindings()
    await bindings.refresh()
    bindings.open.value = true
    const html = await renderState(bindings)
    expect(html).not.toContain('notification-ledger')
    expect(bindings.absence.value).toEqual([])
    expect(bindings.ledger.value).toBe(null)
  })

  it('未读列表照常画：缺席块不吞行，也不替那一格编条目', async () => {
    const { html } = await renderInbox(inboxPayload(APPROVAL_SILENT, {
      notifications: [row('alert:11'), row('document:a.md#v1')], total: 2, unread_total: 2, unread_returned: 2, returned: 2,
    }))
    expect((html.match(/data-testid="notification-row"/g) || [])).toHaveLength(2)
    expect(ledgerTextOf(html)).toContain('审批账本')
  })
})

// ==================== 乙 · 判据②：状态名一个都不许占人话位 ====================

describe('R385 乙 · 判据②：后端那一格的原话上不了屏', () => {
  const SILENT_ALL = {
    approval: cell({ included: false, reason_code: 'storage_unavailable' }),
    alert: cell({ included: false, reason_code: 'permission_denied' }),
    document: cell({ included: false, reason_code: 'principal_inactive' }),
  }

  it('三格一起不供数，屏上可见文字里一个下划线都没有（snake_case 全灭）', async () => {
    const { html } = await renderInbox(inboxPayload(SILENT_ALL))
    const text = ledgerTextOf(html)
    expect(text).toBeTruthy()
    expect(text).not.toMatch(/[A-Za-z_]/)
    for (const word of Object.keys(LEDGER_CAUSES)) expect(text).not.toContain(word)
    expect(visibleText(html)).not.toMatch(/storage_unavailable|permission_denied|principal_inactive/)
  })

  it('表里没登记的原因也说人话：新码来了也不把码端出去', async () => {
    const { html } = await renderInbox(inboxPayload({
      approval: cell({ included: false, reason_code: 'clearance_insufficient' }),
      alert: cell(),
      document: cell(),
    }))
    const text = ledgerTextOf(html)
    expect(text).toContain('它没说明原因')
    expect(text).not.toContain('clearance_insufficient')
  })

  it('第四枚源真的来了：说的是笼统话，不拿键名糊成人话', async () => {
    const { html } = await renderInbox(inboxPayload({
      ...ALL_ANSWERING, wiki: cell({ included: false, reason_code: 'storage_unavailable' }),
    }))
    const text = ledgerTextOf(html)
    expect(text).toContain('有一格账本')
    expect(text).not.toContain('wiki')
  })

  it('人话位上的句子全部出自本件那两张表，字典里一枚都没引用（判据③：出处只有一处）', () => {
    const messages = new Set(Object.values(ERROR_CODES).map(entry => entry.message))
    for (const copy of Object.values(LEDGER_LEGS)) expect(messages.has(copy)).toBe(false)
    for (const copy of Object.values(LEDGER_CAUSES)) expect(messages.has(copy)).toBe(false)
    expect(bellCode.match(/errorCodeLabel|formatError|errorText/g) || []).toHaveLength(0)
  })

  it('存储那一格与权限那一格说的是两句不同的话（两脸不许并成一脸）', async () => {
    const store = ledgerTextOf((await renderInbox(inboxPayload(APPROVAL_SILENT))).html)
    const denied = ledgerTextOf((await renderInbox(inboxPayload({
      approval: cell({ included: false, reason_code: 'permission_denied' }), alert: cell(), document: cell(),
    }))).html)
    expect(store).not.toBe(denied)
    expect(store).toContain('数据库迁移')
    expect(denied).toContain('企业管理员')
  })
})

// ==================== 丙 · 判据④：计数账不被台账污染（DOM 级） ====================

describe('R385 丙 · 判据④：徽标、未读数、翻页都不经台账', () => {
  const polluted = {
    approval: cell({ included: false, reason_code: 'storage_unavailable', candidates: 99, scanned: 97 }),
    alert: cell({ candidates: 3, scanned: 4 }),
    document: cell({ candidates: 5, scanned: 6 }),
  }

  it('缺席格自称 99 枚候选：徽标与读屏的前半句逐字不变，那个数在 HTML 上一处都不许出现', async () => {
    const clean = await renderInbox(inboxPayload(ALL_ANSWERING, { total: 3, unread_total: 3 }))
    const dirty = await renderInbox(inboxPayload(polluted, { total: 3, unread_total: 3 }))
    expect(dirty.bindings.badge.value).toBe('3')
    expect(dirty.bindings.badge.value).toBe(clean.bindings.badge.value)
    expect(dirty.bindings.summary.value).toBe(clean.bindings.summary.value)
    expect(dirty.bindings.unread.value).toBe(clean.bindings.unread.value)
    expect(dirty.bindings.ariaLabel.value.startsWith(clean.bindings.ariaLabel.value + '；')).toBe(true)
    expect(stripLedger(dirty.html)).toBe(stripLedger(clean.html))
    expect(dirty.html).not.toContain('99')
    expect(dirty.html).not.toContain('97')
  })

  it('台账自己的合计只算答上了的那两格，且这一枚数是算出来的（与手算逐枚相等）', async () => {
    const { bindings, html } = await renderInbox(inboxPayload(polluted))
    const cells = ledgerCells({ sources: polluted })
    const answered = cells.filter(item => item.included === true)
    const expected = answered.reduce((sum, item) => sum + item.candidates, 0)
    expect(expected).toBe(8)
    expect(bindings.ledger.value.candidates).toBe(expected)
    expect(bindings.ledger.value.candidates).not.toBe(cells.reduce((sum, item) => sum + item.candidates, 0))
    expect(/data-ledger-candidates="(\d+)"/.exec(html)[1]).toBe(String(expected))
    expect(ledgerSums(cells).scanned).toBe(answered.reduce((sum, item) => sum + item.scanned, 0))
  })

  it('翻页与未读清单不看台账：has_more 说的还是后端那一格', async () => {
    const { bindings } = await renderInbox(inboxPayload(APPROVAL_SILENT, { has_more: true }))
    expect(bindings.inbox.value.hasMore).toBe(true)
    expect(bindings.inbox.value.unread).toBe(3)
    expect(absenceLines(ledgerCells(inboxPayload(APPROVAL_SILENT)))).toHaveLength(1)
  })

  it('一次动作之后再读，台账跟着重算：不留上一轮的缺席句在屏上', async () => {
    const first = await renderInbox(inboxPayload(APPROVAL_SILENT))
    expect(ledgerTextOf(first.html)).toContain('审批账本')
    http.get.mockResolvedValue({ data: inboxPayload(ALL_ANSWERING) })
    await first.bindings.refresh()
    first.bindings.open.value = true
    expect(await renderState(first.bindings)).not.toContain('notification-ledger')
  })

  it('本件对未读数一枚算术都没做：unread 的任何一处出现都不带运算符，也没有第二处赋值', () => {
    expect(bellCode).not.toMatch(/unread[^\n]*[-+*/]/)
    expect(bellCode.match(/unread\.value\s*=/g) || []).toHaveLength(0)
    expect(bellCode.match(/inbox\.value\s*=/g) || []).toHaveLength(2)
  })
})

// ==================== 丁 · 判据⑦：位置、可达性与读屏那一句 ====================

describe('R385 丁 · 判据⑦：位置不遮正文 + 读屏说得出', () => {
  it('缺席块排在正文之前（面板 grid 里占一行，把清单往下推，不是浮层）', async () => {
    const { html } = await renderInbox(inboxPayload(APPROVAL_SILENT, {
      notifications: [row('alert:21')], total: 1, unread_total: 1, unread_returned: 1, returned: 1,
    }))
    const ledger = html.indexOf('data-testid="notification-ledger"')
    const list = html.indexOf('data-testid="notification-list"')
    expect(ledger).toBeGreaterThan(-1)
    expect(list).toBeGreaterThan(-1)
    expect(ledger, '缺席块压到正文之后去了').toBeLessThan(list)
  })

  it('它是 status 不是 alert：只说一句话，不抢读屏、不弹、不挂红', async () => {
    const { html } = await renderInbox(inboxPayload(APPROVAL_SILENT))
    const tag = /<ul[^>]*data-testid="notification-ledger"[^>]*>/.exec(html)[0]
    expect(tag).toContain('role="status"')
    expect(tag).not.toContain('role="alert"')
    expect(tag).toContain('notif__ledger')
    expect(tag).not.toMatch(/danger|error/)
  })

  // 反证刀4 的靶子：只在 view 对象里对、屏上其实看不见，就是 R375 被记半证的那一格。
  it('画出来的那一句必须是摆得上屏的：不带 hidden / style / display:none，也不靠藏起来活', async () => {
    const { html } = await renderInbox(inboxPayload(APPROVAL_SILENT))
    const tag = /<ul[^>]*data-testid="notification-ledger"[^>]*>/.exec(html)[0]
    expect(tag, '缺席块被挂上了隐藏属性：view 对象对，屏上看不见').not.toMatch(/\bhidden\b|style=/)
    const rules = [...bellCode.matchAll(/\.notif__ledger[\w-]*\s*\{[^}]*\}/g)].map(match => match[0])
    for (const rule of rules) {
      expect(rule).not.toMatch(/display:\s*none/)
      expect(rule).not.toMatch(/visibility:\s*hidden/)
      expect(rule).not.toMatch(/opacity:\s*0\b/)
    }
    // 它在展开的面板里，而面板本身也得是可见的：整块 HTML 里那一句话不能只活在注释里。
    const outside = html.replace(/<!--[\s\S]*?-->/g, '')
    expect(outside).toContain('审批账本这次没答上来')
  })

  it('那条新块的样式里没有 position，也不开一枚新色值（判据⑤：只借既有 token）', () => {
    const rules = [...bellCode.matchAll(/\.notif__ledger[\w-]*\s*\{[^}]*\}/g)].map(match => match[0])
    expect(rules.length, '本件里没有 .notif__ledger 这条规则').toBeGreaterThan(1)
    for (const rule of rules) {
      expect(rule).not.toMatch(/position/)
      expect(rule).not.toMatch(/#[0-9a-fA-F]{3}/)
      expect(rule).not.toMatch(/rgba?\(|hsla?\(/)
      expect(rule).not.toMatch(/:\s*(red|blue|green|white|black|gray|grey|navy|teal)\b/)
    }
    expect(bellCode.slice(bellCode.indexOf('<style'))).not.toMatch(/--ledger[a-z0-9-]*:/)
  })

  it('读屏那一句：正常态逐字等于旧句，缺席态逐字并上同一串人话（不是第二份文案）', async () => {
    const clean = await renderInbox(inboxPayload(ALL_ANSWERING), false)
    expect(clean.bindings.ariaLabel.value).toBe('通知，3 条未读通知')
    expect(clean.bindings.ariaLabel.value).toBe(bellAriaLabel('通知，3 条未读通知', []))
    const dirty = await renderInbox(inboxPayload(APPROVAL_SILENT), false)
    const line = absenceLines(ledgerCells({ sources: APPROVAL_SILENT }))[0]
    expect(dirty.bindings.ariaLabel.value).toBe('通知，3 条未读通知；' + line)
    const rendered = /aria-label="([^"]*)"/.exec(await renderState(dirty.bindings))
    expect(rendered[1]).toContain('审批账本这次没答上来')
  })

  it('角色差异不写死：组件源码里没有任何角色名，两脸的差别全来自响应那一格', () => {
    expect(bellCode).not.toMatch(/\b(staff|administrator|admin_role|manager)\b/)
    expect(bellCode).not.toMatch(/administratorOnly|canManageAlerts|hasPermission/)
  })

  it('一次读取只发一个请求：读一次 = 一次 http.get，台账不是第二次问出来的', async () => {
    http.get.mockResolvedValue({ data: inboxPayload(APPROVAL_SILENT) })
    const read = await readInboxPage()
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(read.absence).toHaveLength(1)
    expect(read.page.unread).toBe(3)
    expect(http.get.mock.calls[0][1]).toEqual({ params: { state: 'all', limit: 100, offset: 0 } })
  })
})
