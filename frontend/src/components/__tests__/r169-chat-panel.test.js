/**
 * R169 · V1 前端主链路验收矩阵 —— 问答那一行（发问 / 看到来源 / 看到档位读数 / 取消 / 报告确认门）
 *
 * 这枚文件是**验收件**，不是修复件：产品代码一个字没改，它只回答「§5.2 E 组说的『问答可操作』
 * 今天到底有没有证据」。结论分三态写进回执，这里只放跑得起来的那两态。
 *
 * 既存 659 枚在这一行的落点（逐枚点过名，见回执矩阵）：
 *   看到来源   = components/__tests__/r150-chat-panel.test.js · G1 那一组（6 枚）
 *   看到读数   = components/__tests__/r141-lane-picker.test.js · P1/P3/P4（档位四态 + 请求体带 lane 的源码级）
 *   帧读成事实 = lib/r150-event-claims.test.js · B/C（真 reducer + 真 consumeSseStream，但**不经过面板**）
 * 而「发问」与「取消」这两格，659 枚里**没有任何一枚**调用过 ChatPanel 的 send / requestCancel /
 * confirmCancel / approve —— P4 那半钉的是源码文本（"SSR 不跑点击"是它自己写的理由）。
 * 本文件补的就是这一段：把面板自己的 setup() 跑起来，喂自造的真 SSE 字节，断言它做了什么。
 *
 * 三条腿（沿用仓库既有口径，不新发明）：
 *   ① 真逻辑：借宿主组件的实例上下文调编译产物的 setup() 拿回真绑定，网络层换成进程内假实现，
 *      流交给真 consumeSseStream 解析。node 里没有 window / localStorage，所以这两样给最小替身。
 *   ② 真产物：SSR 出 HTML —— 「待确认那张卡本来就画得出来」。
 *   ③ 源码形状：一次性收尾与落盘这类「跑一次看不到」的接线，钉在源码上（不假装跑过）。
 * 🔴 一条都不置灰、不挂待办、不放宽任何既存断言：补不了的写在回执里，不留在测试里。
 */
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { renderToString } from '@vue/server-renderer'

// 只换网络出口：errorDetail / 归码 / 流层全部保持真身，判据才不会被 mock 顺带改掉。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, authedFetch: vi.fn() }
})
vi.mock('../../lib/health.js', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, fetchRuntimeHealth: vi.fn(async () => null) }
})

import { authedFetch } from '../../lib/http'
import ChatPanel from '../ChatPanel.vue'
import { activeId, hitl, loading, messages } from '../../lib/sessions'

/** 面板的 setup 在挂载期会读 window / 写 localStorage（node 环境两样都没有），给最小替身。 */
function installDomStubs() {
  const store = new Map()
  globalThis.window = globalThis.window || { addEventListener() {}, removeEventListener() {} }
  globalThis.document = globalThis.document || { addEventListener() {}, removeEventListener() {}, visibilityState: 'visible' }
  globalThis.localStorage = {
    getItem: key => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: key => store.delete(key),
    clear: () => store.clear(),
    key: index => [...store.keys()][index] ?? null,
    get length() { return store.size },
  }
}

/**
 * 跑真面板的 setup() 拿回绑定（同 artifact-list.test.js 的手法）。
 * @returns {Promise<Record<string, any>>} 原始绑定，ref 不解包
 */
async function mountPanel() {
  let bindings = null
  const Probe = defineComponent({
    name: 'R169PanelProbe',
    setup(props, ctx) {
      bindings = ChatPanel.setup({}, ctx)
      return () => null
    },
  })
  await renderToString(h(Probe))
  expect(bindings, '面板应暴露可调用的 setup()').toBeTruthy()
  return bindings
}

/** 后端一帧真形状：event 名 + data 信封（sequence 是乱序闸门要读的）。 */
function sseFrame(event, data, sequence) {
  return `event: ${event}\ndata: ${JSON.stringify(sequence === undefined ? data : { ...data, sequence })}\n\n`
}

function sseText(text) {
  return sseFrame('text', { content: text })
}

/** 真 Response 形状的假应答：头三枚档位读数 + 一条 SSE 字节流。 */
function sseResponse(frames, { status = 200, headers = {} } = {}) {
  const bytes = frames.map(frame => new TextEncoder().encode(frame))
  let index = 0
  const headersMap = new Map(Object.entries(headers))
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: name => headersMap.get(String(name).toLowerCase()) ?? null },
    clone() { return this },
    async json() { return null },
    body: { getReader() { return { async read() { return index < bytes.length ? { done: false, value: bytes[index++] } : { done: true } } } } },
  }
}

function jsonResponse(payload, { status = 200 } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => null },
    clone() { return this },
    async json() { return payload },
    body: null,
  }
}

const LANE_HEADERS = {
  'x-effective-lane': 'qa',
  'x-lane-source': 'r42',
  'x-declared-lane': '',
}

function bodyOf(callIndex = 0) {
  const [, options] = authedFetch.mock.calls[callIndex]
  return JSON.parse(options.body)
}

async function settled() {
  for (let round = 0; round < 12; round += 1) await nextTick()
}

describe('R169 Q1 · 发问的守门（跑真 send()）', () => {
  it('空输入按发送一个请求都不发，也不留两只空气泡', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = []
    activeId.value = 'r169-q1'
    b.input.value = '   '
    await b.send('')
    await settled()
    expect(authedFetch).not.toHaveBeenCalled()
    expect(messages.value).toHaveLength(0)
    expect(loading.value).toBe(false)
  })

  it('上一轮还在答时再按发送直接回绝：不产生第二条流', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = []
    activeId.value = 'r169-q1b'
    b.input.value = '住宿费标准是多少？'
    loading.value = true
    await b.send('')
    await settled()
    expect(authedFetch).not.toHaveBeenCalled()
    expect(messages.value).toHaveLength(0)
    expect(b.input.value, '被回绝这一发不该把用户已经敲下的字吞掉').toBe('住宿费标准是多少？')
    loading.value = false
  })

  it('待确认动作还挂着时不许另起一轮（先把那张卡答了）', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = []
    activeId.value = 'r169-q1c'
    hitl.value = { pending: { action: 'export_report' }, labels: { 'export_report': '生成报告' }, interrupted: false }
    b.input.value = '再问一句'
    await b.send('')
    await settled()
    expect(authedFetch).not.toHaveBeenCalled()
    expect(b.noteTone.value, '这一格要给的是提示，不是静默失败').toBe('warn')
    expect(messages.value).toHaveLength(0)
    hitl.value = null
  })
})

describe('R169 Q2 · 发问真的上屏、真的带四格（跑真 send() + 真流层）', () => {
  it('一问一答：用户气泡立刻上屏、助手气泡先空着挂本轮 id', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = []
    activeId.value = 'r169-q2'
    authedFetch.mockResolvedValue(sseResponse([sseText('限额以内据实报销。')], { headers: LANE_HEADERS }))
    b.input.value = '住宿费标准是多少？'
    const running = b.send('')
    expect(messages.value.map(m => m.role), '请求还在路上时这两只气泡就该已经在屏上').toEqual(['user', 'assistant'])
    expect(messages.value[0].content).toBe('住宿费标准是多少？')
    expect(messages.value[1].content).toBe('')
    expect(messages.value[1].mid).toBeTruthy()
    await running
    await settled()
  })

  it('发出去带 message / session_id / data_filename / lane 四格，输入随即清空', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = []
    activeId.value = 'r169-q2b'
    authedFetch.mockResolvedValue(sseResponse([sseText('答完了。')], { headers: LANE_HEADERS }))
    b.input.value = '对比各列数据的最大最小值'
    b.selectedLane.value = 'analysis'
    await b.send('报销明细表.csv')
    await settled()
    expect(authedFetch.mock.calls[0][0]).toBe('/ask')
    expect(bodyOf(0)).toEqual({
      message: '对比各列数据的最大最小值',
      session_id: 'r169-q2b',
      data_filename: '报销明细表.csv',
      lane: 'analysis',
    })
    expect(b.input.value).toBe('')
    expect(loading.value).toBe(false)
  })

  it('真 SSE 帧的正文落到这一轮的气泡里，档位读数同步抄在消息对象上', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = []
    activeId.value = 'r169-q2c'
    authedFetch.mockResolvedValue(sseResponse(
      [sseText('第一段。'), sseText('第二段。'), sseFrame('done', {})],
      { headers: { ...LANE_HEADERS, 'x-effective-lane': 'analysis', 'x-declared-lane': 'analysis', 'x-lane-source': 'explicit' } },
    ))
    b.input.value = '做个趋势'
    b.selectedLane.value = 'analysis'
    await b.send('')
    await settled()
    const turn = messages.value[1]
    expect(turn.content).toContain('第一段。')
    expect(turn.content).toContain('第二段。')
    expect(turn.lane).toMatchObject({ lane: 'analysis', source: 'explicit', declared: 'analysis' })
    expect(b.laneFaceText(turn.lane)).toContain('你选的')
    expect(messages.value[0].content).toBe('做个趋势')
  })

  it('后端这一轮没回正文要说出口，不许留一只空气泡冒充成功', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = []
    activeId.value = 'r169-q2d'
    authedFetch.mockResolvedValue(sseResponse([sseFrame('done', {})]))
    b.input.value = '这句没人答'
    await b.send('')
    await settled()
    expect(messages.value[1].content).toBe('本轮没有返回内容。')
    expect(loading.value).toBe(false)
  })
})

describe('R169 Q3 · 取消是两步，且四种结果四张脸（跑真 requestCancel / confirmCancel）', () => {
  it('第一下只进「确认」态：一个 cancel 请求都不发', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = []
    activeId.value = 'r169-q3'
    b.requestCancel()
    expect(b.cancelPhase.value).toBe('confirm')
    expect(authedFetch).not.toHaveBeenCalled()
  })

  it('确认态里再按第一下是空操作（不会跳过确认直接打后端）', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = []
    activeId.value = 'r169-q3b'
    b.requestCancel()
    b.requestCancel()
    expect(b.cancelPhase.value).toBe('confirm')
    expect(authedFetch).not.toHaveBeenCalled()
  })

  it('确认之后真的打这一轮的取消端点，并把「不再收后续内容」说出来', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = [{ role: 'assistant', content: '', mid: 'm1' }]
    activeId.value = 'r169-q3c'
    authedFetch.mockResolvedValue(jsonResponse({ cancelled: true }))
    await b.confirmCancel()
    await settled()
    expect(authedFetch.mock.calls[0][0]).toBe('/ask/r169-q3c/cancel')
    expect(authedFetch.mock.calls[0][1].method).toBe('POST')
    expect(b.streamNote.value).toContain('不再接收后续内容')
    expect(b.noteTone.value).toBe('info')
    expect(messages.value[0].content).toBe('本次回答已中断，未产出结论。')
    expect(loading.value).toBe(false)
    expect(b.cancelPhase.value).toBe('idle')
  })

  it('200 但 cancelled=false：这是「当前没有正在生成的内容」，不是「已中断」', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = [{ role: 'assistant', content: '已经有半截正文。', mid: 'm2' }]
    activeId.value = 'r169-q3d'
    authedFetch.mockResolvedValue(jsonResponse({ cancelled: false }))
    await b.confirmCancel()
    await settled()
    expect(b.streamNote.value).toBe('当前没有正在生成的内容。')
    expect(b.noteTone.value).toBe('warn')
    expect(messages.value[0].content, '没停掉任何东西就不该改口说这一轮被中断').toBe('已经有半截正文。')
  })

  it('200 但响应里没有 cancelled 这一格：只能承认「无法确认」，不替后端宣布停没停', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = [{ role: 'assistant', content: '半截正文。', mid: 'm3' }]
    activeId.value = 'r169-q3e'
    authedFetch.mockResolvedValue(jsonResponse({}))
    await b.confirmCancel()
    await settled()
    expect(b.streamNote.value).toContain('无法确认')
    expect(b.noteTone.value).toBe('warn')
    expect(b.streamNote.value).not.toContain('不再接收后续内容')
  })

  it('取消端点回 4xx：说「未被受理」并点名状态码，与前三张脸各不同句', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = [{ role: 'assistant', content: '半截正文。', mid: 'm4' }]
    activeId.value = 'r169-q3f'
    authedFetch.mockResolvedValue(jsonResponse({ detail: 'permission_denied' }, { status: 403 }))
    await b.confirmCancel()
    await settled()
    expect(b.streamNote.value).toBe('中断请求未被受理（HTTP 403）。')
    expect(b.noteTone.value).toBe('error')
  })

  it('取消请求压根没送达：说的是连接断了，不假装停下来了', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = [{ role: 'assistant', content: '半截正文。', mid: 'm5' }]
    activeId.value = 'r169-q3g'
    authedFetch.mockRejectedValue(new Error('连接已断开'))
    await b.confirmCancel()
    await settled()
    expect(b.streamNote.value).toContain('中断请求未能送达')
    expect(b.streamNote.value).toContain('连接已断开')
    expect(b.noteTone.value).toBe('error')
  })

  it('四张脸两两不同句（并成一句「出错了」就是这一格要抓的缺陷）', async () => {
    const notes = []
    for (const reply of [
      jsonResponse({ cancelled: true }),
      jsonResponse({ cancelled: false }),
      jsonResponse({}),
      jsonResponse({}, { status: 403 }),
    ]) {
      installDomStubs()
      const b = await mountPanel()
      messages.value = [{ role: 'assistant', content: '半截正文。', mid: 'm6' }]
      activeId.value = 'r169-q3h'
      authedFetch.mockResolvedValue(reply)
      await b.confirmCancel()
      await settled()
      notes.push(b.streamNote.value)
    }
    expect(new Set(notes).size).toBe(4)
    expect(notes.every(Boolean)).toBe(true)
  })

  it('后端自己宣布这一轮取消了：气泡说「本次回答已中断。」，与客户端主动停那句不是同一句', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = []
    activeId.value = 'r169-q3j'
    authedFetch.mockResolvedValue(sseResponse([sseFrame('cancelled', {})]))
    b.input.value = '这一轮被后端停了'
    await b.send('')
    await settled()
    expect(messages.value[1].content).toBe('本次回答已中断。')
    expect(b.streamNote.value, '后端自己停的，不该再补一句「不再接收后续内容」冒充用户按了停止').toBe('')
  })

  it('中断不等于拒绝：待确认那张卡留在屏上并标明已中断（R11 裁定）', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = [{ role: 'assistant', content: '', mid: 'm7' }]
    activeId.value = 'r169-q3i'
    hitl.value = { pending: { action: 'export_report' }, labels: { 'export_report': '生成报告' }, interrupted: false }
    authedFetch.mockResolvedValue(jsonResponse({ cancelled: true }))
    await b.confirmCancel()
    await settled()
    expect(hitl.value).toBeTruthy()
    expect(hitl.value.interrupted).toBe(true)
    expect(b.streamNote.value).toContain('待确认动作仍保留')
    hitl.value = null
  })
})

describe('R169 Q4 · 报告那一腿的确认门（SSR 真产物 + 跑真 approve()）', () => {
  it('待确认那张卡本来就画得出来：两张按钮 + 后端原话，没有第三枚假控件', async () => {
    hitl.value = {
      pending: { action: 'export_report' },
      labels: { export_report: '生成这份报告' },
      interrupted: false,
    }
    activeId.value = 'r169-hitl'
    messages.value = [{ role: 'assistant', content: '先问一句', mid: 'm8' }]
    const html = await renderToString(h(ChatPanel))
    expect(html).toContain('class="hitl-card"')
    expect(html).toContain('需要确认')
    expect(html).toContain('生成这份报告')
    expect(html).toContain('确认执行')
    expect(html).toContain('data-testid="hitl-reject"')
    // 这一屏只给两个决定：执行或拒绝。第三枚「稍后再说」之类的假控件一出现就该红。
    expect(html.match(/class="hitl-btn/g)).toHaveLength(2)
    hitl.value = null
  })

  it('点「确认」才发那一腿，请求里带的就是这一格决定', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = [{ role: 'assistant', content: '', mid: 'm9' }]
    activeId.value = 'r169-r2'
    hitl.value = { pending: { action: 'export_report' }, labels: {}, interrupted: false }
    authedFetch.mockResolvedValue(sseResponse([sseText('报告已生成。')]))
    await b.approve(true)
    await settled()
    expect(authedFetch.mock.calls[0][0]).toBe('/approve')
    expect(bodyOf(0)).toEqual({ session_id: 'r169-r2', approved: true })
    expect(hitl.value, '答完就把卡收掉，不留残影').toBe(null)
    expect(messages.value[0].content).toContain('报告已生成。')
    expect(loading.value).toBe(false)
  })

  it('点「拒绝」同样只发一次，且没有动作结果时界面自己说清被拒', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = [{ role: 'assistant', content: '', mid: 'm10' }]
    activeId.value = 'r169-r2b'
    hitl.value = { pending: { action: 'export_report' }, labels: {}, interrupted: false }
    authedFetch.mockResolvedValue(sseResponse([sseFrame('done', {})]))
    await b.approve(false)
    await settled()
    expect(bodyOf(0).approved).toBe(false)
    expect(messages.value[0].content).toBe('已拒绝该动作。')
  })

  it('确认结果没被受理（HTTP 4xx）：进气泡的那句与提示条那句各说各的', async () => {
    installDomStubs()
    const b = await mountPanel()
    messages.value = [{ role: 'assistant', content: '前半段。', mid: 'm11' }]
    activeId.value = 'r169-r2c'
    hitl.value = { pending: { action: 'export_report' }, labels: {}, interrupted: false }
    authedFetch.mockResolvedValue({ ok: false, status: 503, headers: { get: () => null }, clone() { return this }, async json() { return { detail: 'queue_unavailable' } }, body: null })
    await b.approve(true)
    await settled()
    expect(messages.value[0].content).toContain('[请求错误]')
    expect(b.streamNote.value).toContain('确认结果未被受理（HTTP 503）')
    expect(b.cancelPhase.value).toBe('idle')
  })
})
