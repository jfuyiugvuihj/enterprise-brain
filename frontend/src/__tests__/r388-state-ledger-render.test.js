/**
 * R388 判据③ · 「状态这一格没答」上屏之后，屏上到底写着什么（纯函数级 + renderToString 级）
 *
 * 这一枚文件验的是最后一格：后端把「问不出」与「没读过」分开了，屏幕有没有跟着分开。
 * 三条纪律照 R385（它已被总控验收，本单沿用同一套取证姿势，一格都不许软）：
 *   ① 主断言一律从 renderToString 出来的那段字符串上取，不只验 view 对象（R375 半证那一格）；
 *   ② 键名与词表全部从后端真源现读再比，本文件一枚都不手抄（读法见下面 backendKeys / stateWords）；
 *   ③ 不许 skip：任何一枚真源读不到一律抛错让测试红，读空了下面几枚钉就白写。
 *
 * 与 r385-ledger-render.test.js 的分工：那一枚管 sources 那三格（它跑的回执里根本没有
 * state_ledger 这一格，所以本单在它屏上零影响——那一枚今天仍逐字全绿就是这件事的证据）。
 * 本枚只管第四格：它不供数时屏上多那一句什么话，以及逐行那枚「未读」还画不画。
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
  LEDGER_CAUSES,
  LEDGER_LEGS,
  absenceCopy,
  absenceLines,
  ledgerCells,
  ledgerReasonCopy,
  readInboxPage,
  stateLedgerCell,
  stateLedgerCopy,
  stateWordsKnown,
} from '../components/NotificationBell.vue'

const bellSource = readFileSync(new URL('../components/NotificationBell.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const bellCode = bellSource
  .replace(/<!--[\s\S]*?-->/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/^[ \t]*\/\/.*$/gm, '')

/** 后端真源：本单交付时那些件还没并主干，所以读工作树（读的是生产者本人，不是派工词）。 */
function repoFile(relative) {
  const url = new URL('../../../' + relative, import.meta.url)
  let text
  try {
    text = readFileSync(url, 'utf8')
  } catch (cause) {
    throw new Error('读不到后端真源 ' + relative + '（' + cause.message + '）：判据的账不许降级。')
  }
  if (!text || !text.trim()) throw new Error(relative + ' 是空的，无法对账。')
  return text.replace(/\r\n/g, '\n')
}

const inboxPy = repoFile('app/notifications/inbox.py')
const contractsPy = repoFile('app/notifications/contracts.py')
const contractMd = repoFile('docs/api/contract-v1.md')

/** inbox.py 里 state_ledger 那一格交回的那几枚线上传输键：成对读出来，不抄清单。 */
function backendStateKeys() {
  const start = inboxPy.indexOf("'state_ledger': {")
  if (start < 0) throw new Error('inbox.py 里找不到 state_ledger 那一格：后端没交它，本枚钉就白写')
  // 从那一格自己的花括号之后起读：键名清单里不许混进它本体的名字
  const body = inboxPy.slice(start + ("'state_ledger': {").length, inboxPy.indexOf('},', start))
  const keys = [...body.matchAll(/'([a-z_]+)':/g)].map(match => match[1])
  if (keys.length < 4) throw new Error('state_ledger 那一格只扫出 ' + keys.length + ' 枚键：' + JSON.stringify(keys))
  return keys
}

/** 后端那三枚状态词与那一格的线上传输名：屏上一个都不许出现（判据②的靶子）。 */
function stateWords() {
  const words = [...contractsPy.matchAll(/^STATE_([A-Z_]+) = '([a-z_]+)'$/gm)].map(match => match[2])
  if (words.length < 3) throw new Error('contracts.py 里扫不出那三枚状态词：' + JSON.stringify(words))
  return words
}

const WIRE_KEYS = backendStateKeys()
const STATE_WORDS = stateWords()
const TICK = String.fromCharCode(96)

/** 一格源账：默认「这本账在答，且确实没有」。 */
const cell = (overrides = {}) => ({
  included: true, reason_code: 'ok', candidates: 0, scanned: 0, truncated: false, ...overrides,
})

/** 后端 state_ledger 那一格：默认「答上了，一条都没数不清」。 */
const stateCell = (overrides = {}) => ({
  included: true, reason_code: 'ok', unknown_total: 0, unknown_returned: 0, ...overrides,
})

const ALL_ANSWERING = { approval: cell(), alert: cell(), document: cell() }
const STATE_SILENT = { included: false, reason_code: 'storage_unavailable', unknown_total: 2, unknown_returned: 2 }

function inboxPayload(sources, overrides = {}) {
  return {
    notifications: [],
    state: 'all',
    limit: 100,
    offset: 0,
    returned: 0,
    has_more: false,
    total: 2,
    unread_total: 0,
    unread_returned: 0,
    is_exact: true,
    sources: sources === undefined ? {} : sources,
    ...overrides,
  }
}

/** 后端在生产无库那一格真交回来的那一行：state 是 null，不是 unread。 */
function unknownRow(id) {
  return {
    id, source_type: id.split(':')[0], source_id: id.split(':')[1].split('#')[0],
    title: '标题 ' + id, detail: '正文 ' + id, created_at: '2026-09-27T09:00:00+08:00',
    state: null, reference: {},
  }
}

function row(id, state = 'unread') {
  return { ...unknownRow(id), state }
}

async function mountBindings() {
  let bindings = null
  const Probe = {
    name: 'R388Probe',
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

async function renderInbox(payload, open = true) {
  http.get.mockResolvedValue({ data: payload })
  const bindings = await mountBindings()
  await bindings.refresh()
  bindings.open.value = open
  return { bindings, html: await renderState(bindings) }
}

function ledgerTextOf(html) {
  const block = /<ul[^>]*data-testid="notification-ledger"[^>]*>([\s\S]*?)<\/ul>/.exec(html)
  if (!block) return null
  return block[1].replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
}

function visibleText(html) {
  return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ')
}

const ledgerCountOf = html => (html.match(/data-testid="notification-ledger-item"/g) || []).length
const rowStateCountOf = html => (html.match(/class="notif__row-state"/g) || []).length
const rowCountOf = html => (html.match(/data-testid="notification-row"/g) || []).length

beforeEach(() => {
  vi.clearAllMocks()
})

// ================= 甲 · 读那一格：四枚键、两枚脸、句子只有一处出处 =================

describe('R388 甲 · 判据①②：那一格读得出来，两脸不并', () => {
  it('后端 state_ledger 交回的每一枚键，前端都真读了（逐枚反证：改了它读数必变）', () => {
    const before = JSON.stringify(stateLedgerCell({ state_ledger: stateCell() }))
    const probes = { included: false, reason_code: 'zzz_no_such', unknown_total: 7, unknown_returned: 9 }
    for (const key of WIRE_KEYS) {
      expect(Object.prototype.hasOwnProperty.call(probes, key), key + ' 是新生出来的键？').toBe(true)
      const after = JSON.stringify(stateLedgerCell({ state_ledger: stateCell({ [key]: probes[key] }) }))
      expect(after, key + ' 前端没读它：改了它，读出来的那一格一个字都没动').not.toBe(before)
    }
  })

  it('那一格整个缺席 = 还不知道，不是「没答」：一律 null，屏上一格字都不许多', () => {
    for (const payload of [
      {}, { state_ledger: null }, { state_ledger: false }, { state_ledger: 'ok' }, { state_ledger: [] },
    ]) {
      expect(stateLedgerCell(payload), JSON.stringify(payload)).toBe(null)
    }
    expect(stateLedgerCopy(null)).toBe('')
    expect(stateWordsKnown(null)).toBe(true)
  })

  it('included 只认严格 true：缺 / null / 字符串 / 数字一律算没答（fail-closed，与 isExact 同尺）', () => {
    for (const value of [undefined, null, 'true', 1, 0, false]) {
      const read = stateLedgerCell({ state_ledger: stateCell({ included: value }) })
      expect(read.included, JSON.stringify(value)).toBe(false)
      expect(stateWordsKnown(read)).toBe(false)
    }
  })

  it('答上了的那一格交回空句：一个字符都不许多，逐行「未读」照旧可画', () => {
    const read = stateLedgerCell({ state_ledger: stateCell() })
    expect(read.included).toBe(true)
    expect(stateLedgerCopy(read)).toBe('')
    expect(stateWordsKnown(read)).toBe(true)
  })

  it('屏上那一句与 sources 同一道闸、同一族句式：头逐字同，尾刻意不同', () => {
    const sample = absenceCopy({ sourceType: 'approval', included: false, reasonCode: 'storage_unavailable' })
    const legName = LEDGER_LEGS.approval
    const cause = ledgerReasonCopy('storage_unavailable')
    const head = sample.slice(legName.length, sample.indexOf(cause, legName.length))
    expect(head.length, '从源账那句里剥不出那一枚头，本枚钉就白写').toBeGreaterThan(1)
    const line = stateLedgerCopy(stateLedgerCell({ state_ledger: stateCell(STATE_SILENT) }))
    expect(line).toContain(head)
    expect(line).toContain(cause)
    const sourceTail = sample.slice(sample.indexOf(cause) + cause.length)
    expect(sourceTail.length, '剥不出源账那句的尾巴，本枚钉就白写').toBeGreaterThan(3)
    expect(line, '状态这一格丢的不是某一类事项，尾巴不许抄源账那一句').not.toContain(sourceTail)
  })

  it('那一句里没有一枚后端原话：状态名、键名、原因码一个都不许占人话位（判据②）', () => {
    const line = stateLedgerCopy(stateLedgerCell({ state_ledger: stateCell(STATE_SILENT) }))
    expect(line.length).toBeGreaterThan(10)
    expect(line).not.toMatch(/[A-Za-z_]/)
    for (const word of [...STATE_WORDS, ...WIRE_KEYS]) expect(line).not.toContain(word)
    for (const word of Object.keys(LEDGER_CAUSES)) expect(line).not.toContain(word)
  })

  it('表里没登记的原因也说人话：新码来了也不把码端出去', () => {
    const line = stateLedgerCopy(stateLedgerCell({ state_ledger: stateCell({ included: false, reason_code: 'clearance_insufficient' }) }))
    expect(line).toContain(ledgerReasonCopy('anything_new_next_week'))
    expect(line).not.toContain('clearance_insufficient')
  })
})

// ============ 乙 · 一次读取 = 一个请求：那一格是同一次问出来的，不是第二本账 ============

describe('R388 乙 · 判据④：状态那一格搭同一班车，不另起一本账', () => {
  it('读一次只发一个请求，且那一格与台账一起交回（缺席不是第二次问出来的）', async () => {
    http.get.mockResolvedValue({ data: inboxPayload(ALL_ANSWERING, { state_ledger: stateCell(STATE_SILENT) }) })
    const read = await readInboxPage()
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(read.absence).toHaveLength(1)
    expect(read.stateLedger).toEqual({
      included: false, reasonCode: 'storage_unavailable', unknownTotal: 2, unknownReturned: 2,
    })
  })

  it('旧后端（回执里根本没有那一格）⇒ 交回 null，屏上那串话与 R385 逐字同', async () => {
    const legacy = inboxPayload({ approval: cell({ included: false, reason_code: 'storage_unavailable' }) })
    delete legacy.state_ledger
    http.get.mockResolvedValue({ data: legacy })
    const read = await readInboxPage()
    expect(read.stateLedger).toBe(null)
    expect(read.absence).toEqual(absenceLines(ledgerCells(legacy)))
  })

  it('状态那一句排在三格源账之后：不重排、不补格、不并进别格', async () => {
    const payload = inboxPayload({
      approval: cell({ included: false, reason_code: 'storage_unavailable' }),
      alert: cell(),
      document: cell({ included: false, reason_code: 'permission_denied' }),
    }, { state_ledger: stateCell(STATE_SILENT) })
    http.get.mockResolvedValue({ data: payload })
    const read = await readInboxPage()
    expect(read.absence).toHaveLength(3)
    expect(read.absence[0]).toContain(LEDGER_LEGS.approval)
    expect(read.absence[1]).toContain(LEDGER_LEGS.document)
    expect(read.absence[2]).toBe(stateLedgerCopy(stateLedgerCell(payload)))
    expect(read.absence[2]).not.toContain(LEDGER_LEGS.approval)
  })
})

// ==================== 丙 · 真 HTML：员工看到的是「这一格没答上来」 ====================

describe('R388 丙 · 判据③⑦：那句话画得上屏，逐行那枚「未读」画不上屏', () => {
  it('状态这一格不供数 ⇒ 面板画得出那句人话，原文逐字取自渲染结果', async () => {
    const { html } = await renderInbox(inboxPayload(ALL_ANSWERING, {
      state_ledger: stateCell(STATE_SILENT),
      notifications: [unknownRow('approval:r388-1'), unknownRow('document:r388.pdf#v1')],
      total: 2, returned: 2,
    }))
    const text = ledgerTextOf(html)
    expect(text, '屏上根本没有这一段').toBeTruthy()
    expect(text).toContain('已读状态账本')
    expect(text).toContain('这次没答上来')
    expect(text).toContain('它要的数据表在这台机器上还没准备好')
    expect(text).toContain('不代表它们全都是新的')
    expect(rowCountOf(html), '条目被那一格问不出一起打死了').toBe(2)
  })

  it('同一屏里逐行那枚「未读」一枚都不画，而条目与动作都还在（判据③的正身）', async () => {
    const silent = await renderInbox(inboxPayload(ALL_ANSWERING, {
      state_ledger: stateCell(STATE_SILENT),
      notifications: [unknownRow('approval:r388-2'), unknownRow('document:r388.pdf#v1')],
      total: 2, returned: 2,
    }))
    expect(rowStateCountOf(silent.html)).toBe(0)
    expect(silent.html).not.toContain('未读</span>')
    expect(silent.html.match(/data-testid="notification-mark-read"/g) || []).toHaveLength(2)
    expect(silent.bindings.unread.value).toBe(0)
    expect(silent.bindings.ariaLabel.value).toContain('已读状态账本')
  })

  it('旧后端那一格缺席 ⇒ 逐行「未读」照画：本单不许反过来吃掉既有语义', async () => {
    const legacy = inboxPayload(ALL_ANSWERING, {
      notifications: [row('approval:r388-3'), row('document:r388.pdf#v1')],
      total: 2, returned: 2, unread_total: 2, unread_returned: 2,
    })
    delete legacy.state_ledger
    const { html } = await renderInbox(legacy)
    expect(rowStateCountOf(html)).toBe(2)
    expect(ledgerTextOf(html)).toBe(null)
  })

  it('状态答上了的那一屏，与「压根没有这一格」的旧屏逐字节相等：正常态零新增文案', async () => {
    const rows = [row('approval:r388-4'), row('document:r388.pdf#v1')]
    const answered = await renderInbox(inboxPayload(ALL_ANSWERING, {
      state_ledger: stateCell(), notifications: rows, total: 2, returned: 2, unread_total: 2, unread_returned: 2,
    }))
    const legacy = inboxPayload(ALL_ANSWERING, {
      notifications: rows, total: 2, returned: 2, unread_total: 2, unread_returned: 2,
    })
    delete legacy.state_ledger
    const old = await renderInbox(legacy)
    expect(answered.html).toBe(old.html)
    expect(answered.html).not.toContain('notification-ledger')
    expect(answered.html).not.toContain('这次没答上来')
  })

  it('四格一起不供数 ⇒ 四句话各占一行，不并成一句含糊话', async () => {
    const { html } = await renderInbox(inboxPayload({
      approval: cell({ included: false, reason_code: 'storage_unavailable' }),
      alert: cell({ included: false, reason_code: 'permission_denied' }),
      document: cell({ included: false, reason_code: 'principal_inactive' }),
    }, { state_ledger: stateCell(STATE_SILENT) }))
    const text = ledgerTextOf(html)
    expect(ledgerCountOf(html)).toBe(4)
    expect(text.split('这次没答上来')).toHaveLength(5)
    for (const leg of Object.keys(LEDGER_LEGS)) expect(text).toContain(LEDGER_LEGS[leg])
    expect(text).toContain('已读状态账本')
  })

  it('整屏可见文字里一枚后端原话都没有：状态名 / 键名 / 原因码全上不了屏', async () => {
    const { html } = await renderInbox(inboxPayload(ALL_ANSWERING, {
      state_ledger: stateCell(STATE_SILENT),
      notifications: [unknownRow('approval:r388-5')], total: 1, returned: 1,
    }))
    const text = visibleText(html)
    for (const word of [...STATE_WORDS, ...WIRE_KEYS, 'storage_unavailable']) {
      expect(text, word + ' 被直插到人话位上了').not.toContain(word)
    }
    expect(text).not.toMatch(/unknown|dismissed/i)
  })

  it('台账那块不新开 data-* ：两枚 unknown 计数只给机器读，不长第二本屏上的账', async () => {
    const { html } = await renderInbox(inboxPayload(ALL_ANSWERING, { state_ledger: stateCell(STATE_SILENT) }))
    const tag = /<ul[^>]*data-testid="notification-ledger"[^>]*>/.exec(html)[0]
    expect([...tag.matchAll(/data-([a-z-]+)=/g)].map(match => match[1]).sort())
      .toEqual(['ledger-candidates', 'ledger-silent', 'testid'])
    expect(tag).toContain('role="status"')
    expect(tag).not.toContain('role="alert"')
  })
})

// ==================== 丁 · 契约与实现同名：回执里有而契约没有的字段名一律算假话 ====================

describe('R388 丁 · 判据②：那一格在契约里有名字，且历史一字未动', () => {
  const heading = '## A read that cannot be answered must not be read as an empty ledger (2026-09-27, R388)'

  // 改口（2026-09-28 · 总控动手，R397 并树 c0c4bcd 之后）：这一格原来钉的是「本单那一节必须写在文末」，
  // 可契约是 append-only 的公共面——`## R397` 就是长在它之后的第一笔合法追加，那半句
  // 前提天生撑不过下一笔追加。它真正要挡的从来不是「后面有东西」，而是「有人把新的一节插进历史中间」。
  // 所以判据换成钉住它**前面**那一节是谁：插队在前必红，后来单往末尾追加不再撞这一格。
  // 追加处那枚空行照旧要，全文枚数照旧要——一条牙没卸，只是把「我是最后一节」换成「我的前身是谁」。
  const predecessor = '## R392 健康报不许替一张没在位的表背书（2026-09-27）'

  it('本单那一节全文恰一枚，且紧跟在它那一枚前身之后：插进历史必红，往末尾追加不算插队', () => {
    expect(contractMd.split(heading).length - 1, '本单那一节的枚数不对').toBe(1)
    const at = contractMd.indexOf(heading)
    expect(at, '本单那一节根本不在契约里').toBeGreaterThan(0)
    // 🔴 先在「我前面那段」里找，别拿 fromIndex 去排除自己：`lastIndexOf('\n## ', at - 1)`
    // 会把本单自己那一节找回来（那一枚 `\n` 正好在 at-1），我第一版就是这么红的。
    const before = contractMd.slice(0, at)
    const prev = before.lastIndexOf('\n## ')
    expect(prev, 'R388 那一节前面没有历史节了：它跑到文件开头去了').toBeGreaterThan(-1)
    expect(before.slice(prev + 1, before.indexOf('\n', prev + 1)),
      '有人把新的一节插进了 R388 与它的前身之间：那是改写历史，不是追加').toBe(predecessor)
    expect(contractMd.slice(0, at).endsWith('\n\n'), '追加处缺那枚空行：历史最后一行被顶掉了').toBe(true)
  })

  it('回执里那一格的每一枚键，在契约里都带反引号在册（名字现读自后端，不抄清单）', () => {
    const section = contractMd.slice(contractMd.indexOf(heading))
    for (const key of ['state_ledger', ...WIRE_KEYS]) {
      expect(section, key + ' 在契约里逐字没有名字').toContain(TICK + key + TICK)
    }
    expect(section).toContain('not a fourth state word')
  })

  it('组件里那一格的读数只有一处出处：本件没有第二份文案，也没有第二枚读者', () => {
    // 一处定义 + 一枚读者：多一枚读者就是第二本账，少一枚就是本件压根没读它
    expect(bellCode.match(/stateLedgerCell\(/g) || []).toHaveLength(2)
    expect(bellCode.match(/stateWordsKnown\(/g) || []).toHaveLength(2)
    expect(bellCode.match(/STATE_LEG_TAIL/g) || []).toHaveLength(2)
    expect(bellCode.match(/notif__row-state/g) || []).toHaveLength(2)
    expect(bellCode).not.toMatch(/unread[^\n]*[-+*/]/)
    expect(bellCode.match(/unread\.value\s*=/g) || []).toHaveLength(0)
    expect(bellCode.match(/inbox\.value\s*=/g) || []).toHaveLength(2)
  })
})

// ============ 戊 · 反证刀（屏上）：那两格反证必须真咬，不许是空转的 not.toContain ============

describe('R388 戊 · 判据④·刀丁（屏上）：直插原话与正常态多话都被同一把尺读出', () => {
  /** 假想的那一种写法：把后端原话直接端到人话位上（状态名 / 键名 / 原因码一起上屏）。 */
  const nakedSentence = '已读状态账本这次没答上来：storage_unavailable（unread / dismissed / unknown_total）'

  it('刀丁·屏上一：原话一旦直插人话位，同一把扫描尺当场读出（读不出=那枚 not.toContain 是空转）', async () => {
    const silent = await renderInbox(inboxPayload(ALL_ANSWERING, {
      state_ledger: stateCell(STATE_SILENT),
      notifications: [unknownRow('approval:r388-6'), unknownRow('document:r388.pdf#v1')],
      total: 2, returned: 2,
    }))
    const banned = [...STATE_WORDS, ...WIRE_KEYS, 'storage_unavailable']
    const honest = visibleText(silent.html)
    for (const word of banned) expect(honest, '正身那一屏本来就不该有 ' + word).not.toContain(word)
    silent.bindings.absence.value = [...silent.bindings.absence.value, nakedSentence]
    const naked = visibleText(await renderState(silent.bindings))
    const caught = banned.filter(word => naked.includes(word))
    expect(caught.length, '这把尺连插进人话位的原话都读不出来：它量不到任何东西').toBeGreaterThan(0)
    expect(naked).toContain('已读状态账本')
  })

  it('刀丁·屏上二：正常态一旦多长一句，那枚逐字节相等钉当场就断（零新增文案有牙）', async () => {
    const rows = [row('approval:r388-7'), row('document:r388.pdf#v1')]
    const answered = await renderInbox(inboxPayload(ALL_ANSWERING, {
      state_ledger: stateCell(), notifications: rows, total: 2, returned: 2, unread_total: 2, unread_returned: 2,
    }))
    const baseline = answered.html
    expect(baseline).not.toContain('这次没答上来')
    answered.bindings.absence.value = [...answered.bindings.absence.value, '已读状态账本正常']
    const grown = await renderState(answered.bindings)
    expect(grown, '多长一句而逐字节还相等：那枚 toBe 相等钉量不到东西').not.toBe(baseline)
    expect(grown.length, '多出来的那一句必须真的落到字节上').toBeGreaterThan(baseline.length)
    expect(grown).toContain('已读状态账本正常')
  })
})
