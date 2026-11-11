/**
 * R174 判据② · 「可回看」由后端决定，不由这台浏览器决定
 *
 * 要补的病（R168 交工时具名申报的三格之一）：旧口径判的是本机 localStorage 里的会话历史，
 * 于是员工把待办链接发给同事，同事换台机器打开就说「这一笔没有可回看的对话」—— 那句是假话，
 * 正文明明好好待在服务端。改完之后：能不能回看 = 后端还留着这一条会话吗。
 *
 * 三条腿（沿用 r168 的口径）：
 *   ① 真面板：mock 只贴在 http.get 上，跑组件自己的 refreshReplayBasis() / openTurn() /
 *      replayFromBackend()，读回它自己算出的判定 —— 判定不是在测试里手填的。
 *   ② 真产物：把状态交回组件 ssrRender 出整屏 HTML，哪一行给了跳转、屏上说了哪一句，HTML 说话。
 *   ③ 纯函数：replayVerdicts 的四格与句子两两不同，钉在它自己身上（SSR 不跑点击）。
 * 全程离线：http.get 是进程内假实现，一个 socket 都不开。
 *
 * 反证①（本单要求实测红→绿，跑完即还原）：把「向后端取正文 / 取名单」那一腿摘掉 ——
 *   G2「后端有、本机翻不到」与 G5「点下去之后正文真的回来了」两枚当场红。
 * 另一处锚在源码钉 G7：删掉 onMounted 里那一枪，或者把 openTurn 里的 replayFromBackend 摘掉，红。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn() }, authedFetch: vi.fn() }
})

import { http } from '../../lib/http'
import { activeId, messages, sessions } from '../../lib/sessions'
import HitlPendingPanel, {
  DENIED_TITLE,
  DENIED_WHERE,
  EMPTY_DESCRIPTION,
  EMPTY_TITLE,
  READ_FAILED_TITLE,
  REPLAY_READ_FAILED,
  REPLAY_BASIS_LOCAL_NOTE,
  STORAGE_DESCRIPTION,
  STORAGE_TITLE,
  canReplayTurn,
  replayVerdicts,
} from '../hitl/HitlPendingPanel.vue'
import HitlPendingRow, { REPLAY_LOCAL_ONLY, REPLAY_NONE } from '../hitl/HitlPendingRow.vue'

const source = f => readFileSync(new URL(`../${f}`, import.meta.url), 'utf8').replace(/\r\n/g, '\n')

async function mountBindings(component) {
  let bindings = null
  const Probe = {
    name: 'R174ReplayProbe',
    setup(props, ctx) {
      bindings = component.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Probe))
  expect(bindings, '组件应暴露可调用的 setup()').toBeTruthy()
  return bindings
}

const renderState = (component, bindings) => renderToString(h({ ...component, setup: () => bindings }))
const text = html => html.replace(/<!--[\s\S]*?-->/g, ' ').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()

function pendingRow(over) {
  return Object.assign({
    sessionId: 'sess-1',
    requestId: 'req-9f2c',
    steps: ['chart'],
    labels: ['📈 生成图表'],
    createdAt: '刚刚',
    expiresAt: '半小时后',
  }, over || {})
}

/** 按 URL 分路的假后端：账本 / 会话名单 / 单条正文，三格各回各的。 */
function route(payloads) {
  http.get.mockImplementation(async url => {
    const hit = payloads[url]
    if (hit instanceof Error) throw hit
    if (hit === undefined) return { data: {} }
    return { data: hit }
  })
}

const ledger = (...rows) => ({ items: rows.map(row => ({
  session_id: row.sessionId,
  owner_user_id: 'u-1',
  parked_steps: row.steps,
  labels: row.labels,
  status: 'awaiting',
  created_at: '2026-09-23T09:12:44+08:00',
  expires_at: '2026-09-23T09:42:44+08:00',
  request_id: row.requestId,
  trace_id: 'tr-1',
  task_id: 'tk-1',
})), count: rows.length, limit: 50, offset: 0, has_more: false })

const list = (...ids) => ({ sessions: ids.map(id => ({ id, title: '会话' })) })

beforeEach(() => {
  http.get.mockReset()
  sessions.value = []
  activeId.value = ''
  messages.value = []
})

describe('R174② · 判定表：四格各判各的，一句不许多、一句不许并', () => {
  const row = pendingRow()

  it('后端有这一条就给跳转，本机翻不给翻都无所谓', () => {
    const v = replayVerdicts([row], { known: true, ids: ['sess-1'] }, [])
    expect(v['sess-1']).toEqual({ canOpen: true, note: '', basis: 'backend' })
  })

  it('后端没有、只有这台浏览器留着：另说一句，不并进「没有可回看」', () => {
    const v = replayVerdicts([row], { known: true, ids: [] }, ['sess-1'])
    expect(v['sess-1']).toMatchObject({ canOpen: false, note: REPLAY_LOCAL_ONLY, basis: 'backend' })
  })

  it('后端与本机都没有：才是那句「这一笔没有可回看的对话」', () => {
    const v = replayVerdicts([row], { known: true, ids: ['other'] }, ['another'])
    expect(v['sess-1']).toMatchObject({ canOpen: false, note: REPLAY_NONE })
  })

  it('名单没读到不等于名单是空的：读不到时按本机判，并把标准如实记下来', () => {
    const v = replayVerdicts([row], { known: false, ids: [] }, ['sess-1'])
    expect(v['sess-1']).toMatchObject({ canOpen: true, basis: 'local' })
    expect(canReplayTurn(row, [])).toBe(false)
  })

  it('这一屏关于「回不回得去」的六句两两不同：判不到的三种各说各的，点下去没回来的又各自一句', () => {
    const notes = [
      REPLAY_NONE,
      REPLAY_LOCAL_ONLY,
      ...Object.values(REPLAY_READ_FAILED),
    ]
    expect(notes).toHaveLength(6)
    expect(new Set(notes).size, '有两格并成了同一句话').toBe(6)
    for (const a of notes) {
      for (const b of notes) if (a !== b) expect(a.includes(b), b.slice(0, 14)).toBe(false)
    }
  })
})

describe('R174② · 真面板：后端说了算（反证①的靶心）', () => {
  it('后端有、这台浏览器翻不到 —— 仍然给跳转（换机器打开链接的那一位看得见）', async () => {
    route({ '/hitl/pending': ledger(pendingRow()), '/sessions': list('sess-1') })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    expect(bindings.canOpen(bindings.rows.value[0]), '本机历史为空就判「不能回看」，就是本单要补的病')
      .toBe(false)
    await bindings.refreshReplayBasis()
    expect(bindings.canOpen(bindings.rows.value[0])).toBe(true)
    const html = await renderState(HitlPendingPanel, bindings)
    expect(html).toContain('data-testid="hitl-open"')
    expect(text(html)).not.toContain('这一笔没有可回看的对话')
    // 🔴 反证①：把 refreshReplayBasis 或 readBackendSessionIds 那一腿摘掉，上面三条红。
  })

  it('本机有、后端已经没有 —— 说的是「只在这台浏览器里」那一句，且不并进上一句', async () => {
    sessions.value = [{ id: 'sess-1', messages: [], msgCount: 1 }]
    route({ '/hitl/pending': ledger(pendingRow()), '/sessions': list() })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    await bindings.refreshReplayBasis()
    expect(bindings.canOpen(bindings.rows.value[0])).toBe(false)
    const html = await renderState(HitlPendingPanel, bindings)
    expect(text(html)).toContain('这一条只在这台浏览器里')
    expect(text(html)).not.toContain('后端说没有这一条会话，这台浏览器里也翻不到')
    expect(html).not.toContain('data-testid="hitl-open"')
  })

  it('名单没读到才换标准，而且这句必须由屏上说出来；没问过之前不许说「问不到」', async () => {
    route({ '/hitl/pending': ledger(pendingRow()) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    let html = await renderState(HitlPendingPanel, bindings)
    expect(html).not.toContain('data-testid="hitl-replay-basis"')
    await bindings.refreshReplayBasis()
    html = await renderState(HitlPendingPanel, bindings)
    expect(html).toContain('data-basis="local"')
    // 逐字比常量本身：模板里另抄一份、日后漂了，这一条就红
    expect(text(html)).toContain(REPLAY_BASIS_LOCAL_NOTE)
  })

  it('点下去之后正文真的回来了：交回那份唯一的 store，不各存一套', async () => {
    const body = [{ role: 'user', content: '上季度销售额多少' }, { role: 'assistant', content: '一千二百万。' }]
    route({
      '/hitl/pending': ledger(pendingRow()),
      '/sessions': list('sess-1'),
      '/sessions/sess-1': { session: { id: 'sess-1' }, messages: body },
    })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    await bindings.refreshReplayBasis()
    expect(await bindings.replayFromBackend(bindings.rows.value[0])).toBe(true)
    expect(activeId.value).toBe('sess-1')
    expect(messages.value.map(m => m.content)).toEqual(['上季度销售额多少', '一千二百万。'])
    expect(sessions.value.map(s => String(s.id))).toContain('sess-1')
    // 🔴 反证① 的第二靶心：把 readBackendSession / adoptBackendSession 那一腿摘掉，这四条红。
  })

  it('本机就有这一条时不许多发那一枪：openTurn 同步切过去就行', async () => {
    sessions.value = [
      { id: 'sess-1', messages: [{ role: 'user', content: '本地那句' }], msgCount: 1 },
      { id: 'sess-here', messages: [{ role: 'user', content: '此刻正看着的' }], msgCount: 1 },
    ]
    activeId.value = 'sess-here'
    route({ '/hitl/pending': ledger(pendingRow()), '/sessions': list('sess-1') })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    await bindings.refreshReplayBasis()
    http.get.mockClear()
    expect(bindings.openTurn(bindings.rows.value[0])).toBe(true)
    expect(http.get.mock.calls, '本机有这一条还去问后端，是多打的一枪').toEqual([])
    expect(activeId.value).toBe('sess-1')
    expect(messages.value.map(m => m.content)).toEqual(['本地那句'])
  })

  it('后端说没有这一条：单独一句，且不把这一笔从屏上抹掉', async () => {
    const gone = Object.assign(new Error('Request failed with status code 404'), { response: { status: 404 } })
    route({ '/hitl/pending': ledger(pendingRow()), '/sessions': list('sess-1'), '/sessions/sess-1': gone })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    await bindings.refreshReplayBasis()
    expect(await bindings.replayFromBackend(bindings.rows.value[0])).toBe(false)
    const html = await renderState(HitlPendingPanel, bindings)
    expect(html).toContain('data-testid="hitl-open-failure"')
    expect(text(html)).toContain(REPLAY_READ_FAILED.not_found)
    expect(bindings.rows.value).toHaveLength(1)
  })
})

describe('R174② · 接线与判据④的旧账', () => {
  it('开屏就问后端一次，判定的来源不再是本机历史', () => {
    const code = source('hitl/HitlPendingPanel.vue')
    expect(code).toMatch(/onMounted\(\(\) => \{[\s\S]*?refreshReplayBasis\(\)[\s\S]*?loadPending\(\)/)
    // 跳转这一腿必须真把 store 用上：只在面板里存一份私有正文，就是「各存一套」那个病
    expect(code).toMatch(/adoptBackendSession\(row\.sessionId, read\.messages\)/)
    expect(code).toMatch(/void replayFromBackend\(row\)/)
    expect(code).toMatch(/readBackendSessionIds\(\)/)
  })

  it('判定表是派生态，不写进行数据：行只可能来自后端那一页账本', () => {
    const code = source('hitl/HitlPendingPanel.vue')
    const assigns = (code.replace(/\/\*[\s\S]*?\*\//g, '').split('\n').filter(l => !/^\s*(\/\/|\*|\/\*\*?)/.test(l)).join('\n'))
      .match(/rows\.value = [^\n]*/g) || []
    expect(assigns).toEqual([
      'rows.value = []',
      'rows.value = append ? rows.value.concat(mapped) : mapped',
      'rows.value = []',
    ])
  })

  it('这一屏 14 句两两不同（判据④）：屏上原有的五张脸，与 R174 新添的九句，谁也不许顶谁', () => {
    // 原有的：无权那一格（标题＋那句补充）/ 空态那一格 / 账本没就绪 / 读失败标题
    // R174 新添的：名单没读到（换了标准必须说出口）/ 只剩本机 / 两头都没有 / 点下去正文没回来的四句
    const say = [
      DENIED_TITLE,
      DENIED_WHERE,
      EMPTY_TITLE,
      EMPTY_DESCRIPTION,
      STORAGE_TITLE,
      STORAGE_DESCRIPTION,
      READ_FAILED_TITLE,
      REPLAY_BASIS_LOCAL_NOTE,
      REPLAY_NONE,
      REPLAY_LOCAL_ONLY,
      ...Object.values(REPLAY_READ_FAILED),
    ]
    expect(say).toHaveLength(14)
    expect(new Set(say).size, '有两张脸并成了同一句话').toBe(say.length)
    for (const a of say) {
      for (const b of say) if (a !== b) expect(a.includes(b), `整句被并进了：${b.slice(0, 14)}`).toBe(false)
    }
    expect(Object.keys(REPLAY_READ_FAILED).sort()).toEqual(
      ['bad_body', 'not_found', 'not_yours', 'unreachable'],
    )
  })

  it('行组件不自己判「能不能回看」：判定只有一处，本组件只画带下来的结果', () => {
    const rowCode = source('hitl/HitlPendingRow.vue')
    expect(rowCode).not.toMatch(/localIds|localStorage|sessions\.value/)
    expect(rowCode).toMatch(/replay: \{ type: Object, default: null \}/)
  })
})
