/**
 * R168 · 判据② + 判据④ —— 这一屏按得动，且说得出「成了没成 / 回哪儿去」
 *
 * 手法与本族另一枚（artifact-list.test.js）一致：node + @vue/server-renderer，无 jsdom。
 * 三条腿：
 *   ① 真状态：mock 只贴在网络层（http.get / authedFetch），consumeSseStream 用【真身】——
 *      所以喂进去的是一条真 SSE 字节流（new Response(ReadableStream)），界面自己从事件里读出
 *      terminal / error_code / awaiting_hitl，不是在测试里手填一个「成功」字。
 *   ② 真产物：读回的状态交回组件 ssrRender 画整屏，按钮在不在、disabled 在不在、
 *      「这一笔没有可回看的对话」那句话在不在，都由真 HTML 说话。
 *   ③ 会话 store 也是真身（lib/sessions.js 的 sessions / activeId / messages）：判据④
 *      要钉的是「切过去的是那一份、且没有多出一份」，只有动真 store 才作数。
 *
 * 反证乙（把无权渲染成空列表）打红的是 r168-hitl-pending.test.js，两把反证逐条记录在工单交付里。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'

// 只换网络层：errorDetail / errorCodeOf / consumeSseStream / sessions 全部保持真身。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn() }, authedFetch: vi.fn() }
})

import { authedFetch, http } from '../../lib/http'
import { activeId, messages, sessions } from '../../lib/sessions'
import ApprovalPanel from '../ApprovalPanel.vue'
import HitlPendingPanel, {
  APPROVE_PATH,
  PENDING_PATH,
  canReplayTurn,
  chatAnchor,
  decisionView,
} from '../hitl/HitlPendingPanel.vue'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const source = name => read(`../${name}`)

async function mountBindings(component) {
  let bindings = null
  const Probe = {
    name: 'R168DecisionProbe',
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
const codeText = html => html.replace(/<!--[\s\S]*?-->/g, ' ').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()

function pendingRow(overrides) {
  return Object.assign({
    session_id: 'sess-1',
    owner_user_id: 'u-1',
    parked_steps: ['chart'],
    labels: ['📈 生成图表'],
    status: 'awaiting',
    created_at: '2026-09-23T09:12:44.123456+08:00',
    expires_at: '2026-09-23T09:42:44.123456+08:00',
    request_id: 'req-9f2c',
    trace_id: 'tr-1',
    task_id: 'tk-1',
  }, overrides || {})
}

const pendingPage = (items, extra) => Object.assign({ items, count: items.length, limit: 50, offset: 0, has_more: false }, extra || {})

/** canonical 事件帧：形状照 chat.py 的 canonical_sse_event（sequence 递增，否则被读取器当迟到帧丢掉）。 */
let seq = 0
function canonical(event, data, status) {
  seq += 1
  return `event: ${event}\ndata: ${JSON.stringify({ request_id: 'req-9f2c', trace_id: 'tr-1', task_id: 'tk-1', sequence: seq, status: status || 'completed', data })}\n\n`
}
const legacy = (event, payload) => `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`

/** 一条真 SSE 响应：交给真的 consumeSseStream 解析，不 mock 解析器。 */
function sseResponse(chunks, status = 200) {
  const bytes = new TextEncoder().encode(chunks.join(''))
  const body = new ReadableStream({ start(controller) { controller.enqueue(bytes); controller.close() } })
  return new Response(body, { status, headers: { 'Content-Type': 'text/event-stream' } })
}

const completedStream = (data = {}) => sseResponse([
  canonical('request.started', { session_id: 'sess-1' }, 'running'),
  canonical('request.completed', Object.assign({ session_id: 'sess-1', worker_count: 1, elapsed: 1.2, answer_length: 40, awaiting_hitl: false, awaiting_steps: [] }, data)),
  legacy('done', { type: 'done' }),
])

const failedStream = code => sseResponse([
  canonical('request.started', { session_id: 'sess-1' }, 'running'),
  canonical('request.failed', { session_id: 'sess-1', error_code: code, worker_count: 0 }, 'failed'),
  legacy('done', { type: 'done' }),
])

const cancelledStream = () => sseResponse([
  canonical('request.started', { session_id: 'sess-1' }, 'running'),
  canonical('request.cancelled', { session_id: 'sess-1' }, 'cancelled'),
  legacy('cancelled', { type: 'cancelled', session_id: 'sess-1' }),
])

/** 批准之后图又停在下一个 HITL 节点：legacy hitl 排在收尾事件之前，读取器当场就停（chat.py:2462）。 */
const parkedAgainStream = () => sseResponse([
  canonical('request.started', { session_id: 'sess-1' }, 'running'),
  legacy('hitl', { type: 'hitl', pending: ['export'], labels: ['📋 导出报告'] }),
  canonical('request.completed', { session_id: 'sess-1', awaiting_hitl: true, awaiting_steps: ['export'] }),
])

const jsonError = (status, detail) => new Response(JSON.stringify({ detail }), { status, headers: { 'Content-Type': 'application/json' } })

const rowOf = bindings => bindings.rows.value[0]
const decideBody = index => JSON.parse(authedFetch.mock.calls[index][1].body)
const outcomeText = html => (html.match(/data-testid="hitl-outcome"[\s\S]*?<\/p>/) || [''])[0]

beforeEach(() => {
  vi.clearAllMocks()
  seq = 0
  sessions.value = []
  activeId.value = ''
  messages.value = []
  http.get.mockResolvedValue({ data: pendingPage([]) })
})

// ==================== 判据② · 批准与驳回都按得动，成功与失败的话不同 ====================

describe('R168 判据② · 这一屏上批准与驳回都是活的', () => {
  it('真行上每枚按钮都在：idle 可点、忙碌时只按住这一笔的两个决定', async () => {
    sessions.value = [{ id: 'sess-1', title: '把上季度销售额画成图', messages: [], msgCount: 0 }]
    http.get.mockResolvedValue({ data: pendingPage([pendingRow()]) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()

    /** 枚一枚数按钮：取它自己的 data-testid 与开标签上的 disabled，不整屏扫字符串。 */
    const buttons = async () => {
      const html = await renderState(HitlPendingPanel, bindings)
      return (html.match(/<button[\s\S]*?<\/button>/g) || []).map(tag => ({
        testid: (/data-testid=\"([^\"]+)\"/.exec(tag) || [, ''])[1],
        pressed: /\bdisabled\b/.test(tag.split('>')[0]),
      }))
    }

    const idle = await buttons()
    expect(idle.map(item => item.testid).sort()).toEqual(['hitl-approve', 'hitl-open', 'hitl-reject', 'hitl-reload'])
    expect(idle.filter(item => item.pressed)).toEqual([])

    bindings.busyId.value = 'sess-1'
    const busy = await buttons()
    // 一次点击只该按住这一笔的两个决定：刷新与回看是别的动作，不跟着变灰。
    expect(busy.filter(item => item.pressed).map(item => item.testid).sort()).toEqual(['hitl-approve', 'hitl-reject'])
  })

  it('点下去打的就是 /approve，body 恰为 { session_id, approved }，一个字段不多', async () => {
    http.get.mockResolvedValue({ data: pendingPage([pendingRow()]) })
    authedFetch.mockResolvedValue(completedStream())
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    await bindings.decide({ row: rowOf(bindings), approved: true })
    expect(authedFetch.mock.calls).toHaveLength(1)
    expect(authedFetch.mock.calls[0][0]).toBe(APPROVE_PATH)
    expect(APPROVE_PATH).toBe('/approve')
    expect(authedFetch.mock.calls[0][1].method).toBe('POST')
    expect(decideBody(0)).toEqual({ session_id: 'sess-1', approved: true })

    await bindings.decide({ row: rowOf(bindings), approved: false })
    expect(decideBody(1)).toEqual({ session_id: 'sess-1', approved: false })
  })

  it('批准成功与批准失败回的话不同：一个说放行，一个说没生效', async () => {
    http.get.mockResolvedValue({ data: pendingPage([pendingRow()]) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()

    authedFetch.mockResolvedValue(completedStream())
    const okView = await bindings.decide({ row: rowOf(bindings), approved: true })
    http.get.mockResolvedValue({ data: pendingPage([pendingRow()]) })

    authedFetch.mockResolvedValue(failedStream('no_answer_produced'))
    const failView = await bindings.decide({ row: rowOf(bindings), approved: true })

    expect(okView.face).toBe('ok')
    expect(failView.face).toBe('failed')
    expect(okView.title).not.toBe(failView.title)
    expect(okView.description).not.toBe(failView.description)
    expect(okView.title).toBe('已批准，这一步已放行')
    expect(failView.title).toBe('批准没有生效')
  })

  // R123 甲案：批准失败要倒扣 —— 不许出现任何一种「已经办妥」的说法。
  it('批准失败的话里不许出现「已完成 / 已放行 / 已批准 / 办完」', async () => {
    authedFetch.mockResolvedValue(failedStream('no_answer_produced'))
    const view = decisionView({ approved: true, ok: true, status: 200, terminal: 'failed', errorCode: 'no_answer_produced' })
    const text = view.title + view.description
    expect(text).not.toMatch(/已完成|已放行|已批准|已办完|办妥了|成功/)
    expect(text).toMatch('没有生效')
    expect(text).toMatch('重新读取')
    // 后端在报失败之前先闭合了账面，所以这句话必须把「账面 vs 实际」分开说，不能只说一半。
    expect(text).toMatch('不等于这一步真跑完了')
  })

  it('失败要倒扣：行不消失、不重读账本；成功才重读', async () => {
    http.get.mockResolvedValue({ data: pendingPage([pendingRow()]) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    expect(http.get.mock.calls).toHaveLength(1)

    authedFetch.mockResolvedValue(failedStream('task_timeout'))
    await bindings.decide({ row: rowOf(bindings), approved: true })
    expect(http.get.mock.calls).toHaveLength(1) // 没去重读：一次刷新不该把失败洗成「没有待办」
    expect(bindings.rows.value).toHaveLength(1)
    const html = await renderState(HitlPendingPanel, bindings)
    expect(html).toContain('data-face="failed"')
    expect(outcomeText(html)).toMatch('没有生效')

    authedFetch.mockResolvedValue(completedStream())
    http.get.mockResolvedValue({ data: pendingPage([]) })
    await bindings.decide({ row: rowOf(bindings), approved: true })
    expect(http.get.mock.calls.map(call => call[0])).toEqual([PENDING_PATH, PENDING_PATH])
    expect(bindings.rows.value).toEqual([])
    const after = await renderState(HitlPendingPanel, bindings)
    expect(codeText(after)).toContain('现在没有等你拍板的事')
    // 办完之后反馈该随那一行一起退场，不许留成屏上一句无主的「已批准」。
    expect(outcomeText(after)).toBe('')
  })

  it('驳回成功的话与批准成功不同，且如实说这一步不会执行', async () => {
    const approved = decisionView({ approved: true, ok: true, terminal: 'completed' })
    const rejected = decisionView({ approved: false, ok: true, terminal: 'completed' })
    expect(rejected.title).toBe('已驳回，这一步不会执行')
    expect(rejected.title).not.toBe(approved.title)
    expect(rejected.description).toMatch('确实没有执行')
    expect(rejected.face).toBe('ok')
  })

  it('中断既不算驳回也不算批准：脸是 unknown', async () => {
    http.get.mockResolvedValue({ data: pendingPage([pendingRow()]) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    authedFetch.mockResolvedValue(cancelledStream())
    const view = await bindings.decide({ row: rowOf(bindings), approved: true })
    expect(view.face).toBe('unknown')
    expect(view.description).toMatch('既不算驳回')
    expect(view.description).toMatch('不能断定')
    expect(http.get.mock.calls).toHaveLength(1)
  })

  it('又停下来问下一件事：算批准成功，并说清新挂起就在下面', async () => {
    http.get.mockResolvedValue({ data: pendingPage([pendingRow()]) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    authedFetch.mockResolvedValue(parkedAgainStream())
    http.get.mockResolvedValue({ data: pendingPage([pendingRow({ parked_steps: ['export'], labels: ['📋 导出报告'] })]) })
    const view = await bindings.decide({ row: rowOf(bindings), approved: true })
    expect(view.face).toBe('ok')
    expect(view.title).toMatch('下一件事')
    expect(http.get.mock.calls).toHaveLength(2)
    expect(bindings.rows.value[0].labels).toEqual(['📋 导出报告'])
  })

  it('服务端直接回 403：说「没有送出去」，不写失败已确认', async () => {
    http.get.mockResolvedValue({ data: pendingPage([pendingRow()]) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    authedFetch.mockResolvedValue(jsonError(403, 'permission_denied'))
    const view = await bindings.decide({ row: rowOf(bindings), approved: true })
    expect(view.face).toBe('failed')
    expect(view.title).toBe('批准没有送出去')
    expect(view.description).toMatch('HTTP 403')
    expect(view.description).toMatch('当前账号没有这项权限')
    expect(view.description).not.toMatch(/permission_denied/) // 码名只走 codeLabel 那条独立通道
  })

  it('断网：结果未知，既不写成功也不写「确实没执行」', async () => {
    http.get.mockResolvedValue({ data: pendingPage([pendingRow()]) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    authedFetch.mockRejectedValue(new Error('fetch failed'))
    const view = await bindings.decide({ row: rowOf(bindings), approved: false })
    expect(view.face).toBe('unknown')
    expect(view.title).toBe('驳回没能送到服务，结果未知')
    expect(http.get.mock.calls).toHaveLength(1)
    expect(bindings.rows.value).toHaveLength(1)
  })

  it('六种结局的话两两不同（没有哪两种可以互换）', () => {
    const views = [
      decisionView({ approved: true, ok: true, terminal: 'completed' }),
      decisionView({ approved: false, ok: true, terminal: 'completed' }),
      decisionView({ approved: true, ok: true, terminal: 'completed', awaitingHitl: true }),
      decisionView({ approved: true, ok: true, terminal: 'failed', errorCode: 'no_answer_produced' }),
      decisionView({ approved: true, ok: true, terminal: 'cancelled' }),
      decisionView({ approved: true, ok: false, status: 500, errorMessage: '服务坏了' }),
    ]
    const texts = views.map(view => view.title + '|' + view.description)
    expect(new Set(texts).size).toBe(6)
    expect(new Set(views.map(view => view.face)).size).toBe(3)
  })
})

// ==================== 判据④ · 跳回产生它的那一轮，且不新开一份 ====================

describe('R168 判据④ · 待办行回到那一轮对话', () => {
  it('本地有那一份会话：切过去，一份新的都不许多', async () => {
    sessions.value = [
      { id: 'sess-1', messages: [{ role: 'user', content: '把上季度销售额画成图' }], msgCount: 1 },
      { id: 'sess-2', messages: [], msgCount: 0 },
    ]
    activeId.value = 'sess-2'
    http.get.mockResolvedValue({ data: pendingPage([pendingRow()]) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()

    const html = await renderState(HitlPendingPanel, bindings)
    expect(html).toContain('data-testid="hitl-open"')
    expect(html).not.toContain('这一笔没有可回看的对话')

    expect(bindings.openTurn(rowOf(bindings))).toBe(true)
    expect(activeId.value).toBe('sess-1')
    expect(sessions.value).toHaveLength(2)
    expect(messages.value.map(m => m.content)).toEqual(['把上季度销售额画成图'])
  })

  it('本地没有那一份：明写「这一笔没有可回看的对话」，不给按钮、不新开一份', async () => {
    sessions.value = [{ id: 'sess-other', messages: [], msgCount: 0 }]
    activeId.value = 'sess-other'
    http.get.mockResolvedValue({ data: pendingPage([pendingRow({ session_id: 'sess-ghost' })]) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()

    const html = await renderState(HitlPendingPanel, bindings)
    expect(html).toContain('data-testid="hitl-no-turn"')
    expect(codeText(html)).toContain('这一笔没有可回看的对话')
    expect(html).not.toContain('data-testid="hitl-open"')

    expect(bindings.openTurn(rowOf(bindings))).toBe(false)
    expect(activeId.value).toBe('sess-other')
    expect(sessions.value).toHaveLength(1) // 关键：switchSession 没机会伪造一份新会话
    expect(canReplayTurn(rowOf(bindings), ['sess-1'])).toBe(false)
  })

  it('两行并存时各说各的：能跳的给按钮，不能跳的给那句话', async () => {
    sessions.value = [{ id: 'sess-1', messages: [], msgCount: 0 }]
    http.get.mockResolvedValue({ data: pendingPage([pendingRow(), pendingRow({ session_id: 'sess-ghost' })]) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    const html = await renderState(HitlPendingPanel, bindings)
    expect(html.match(/data-testid="hitl-open"/g)).toHaveLength(1)
    expect(html.match(/data-testid="hitl-no-turn"/g)).toHaveLength(1)
    expect(html.match(/data-testid="hitl-row"/g)).toHaveLength(2)
  })

  it('深链落在对话屏，带上这一笔的两个编号；编号缺席也不编一个出来', () => {
    expect(chatAnchor({ sessionId: 'sess-1', requestId: 'req-9f2c' })).toEqual({
      name: 'chat',
      query: { session: 'sess-1', request: 'req-9f2c' },
    })
    expect(chatAnchor({ sessionId: 'sess-1', requestId: '' })).toEqual({ name: 'chat', query: { session: 'sess-1' } })
    // 深链只是把用户送回那一轮：它不发问答、不新建会话，也不带任何会被后端当新轮次的字段。
    const anchor = JSON.stringify(chatAnchor({ sessionId: 'sess-1', requestId: 'req-9f2c' }))
    expect(anchor).not.toMatch(/ask|query_text|question|newSession/i)
  })
})

// ==================== 一屏成形：真组件挂在 /approval 那一屏上 ====================

describe('R168 · 这一屏真的挂上了那一块（真产物 + 源码形状）', () => {
  it('ApprovalPanel 的 SSR 产物里就有「挂起待办」那块，且它自己不新增请求', async () => {
    const html = await renderToString(h({ render: () => h(ApprovalPanel) }))
    expect(html).toContain('data-testid="hitl-pending"')
    expect(codeText(html)).toContain('挂起待办')
    const code = source('ApprovalPanel.vue')
      .replace(/<!--[\s\S]*?-->/g, '')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .split('\n')
      .filter(line => !/^\s*\/\//.test(line))
      .join('\n')
    expect(code.match(/(api|http|axios)\.(get|post|put|patch|delete)\(/g)).toHaveLength(1)
    // 屏上「读的是哪两条端点」是可以写在说明里的；判据钉的是这一枚文件自己不动网络层。
    expect(code).not.toMatch(/authedFetch\(|http\.get\(|http\.post\(/)
  })

  it('当年那两句假话已经从屏上摘掉', () => {
    const s = source('ApprovalPanel.vue')
    expect(s).not.toMatch(/端点尚未实现/)
    expect(s).not.toMatch(/要等后端的工单模型建起来/)
    // 而「演示数据」那块牌只圈自查计算器：上方那一屏读的是真账本，不许被一并标成演示。
    expect(s).toMatch(/上方那一屏挂起待办读的是服务端真账本/)
  })
})