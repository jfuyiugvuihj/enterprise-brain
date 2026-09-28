/**
 * R415 · 反证钉：「这一轮算数用的表」报的必须是服务端那一份，三态各有名字
 *
 * 病（改前取证，锚串在 ChatPanel.vue 的 dataTableOf）：这一屏只有一句 dataTableOf，读的是
 * `msg.dataFilename` —— 界面自己发出去的那一份。员工问「这轮这几个数是从哪张表算的」，屏上答
 * 的是「我刚才点的那张」。两件事在调用方没点名、或一轮算了多张时并不相同，那句就是假话。
 *
 * 三态（服务端那一格的口径来自 R414 `chat.py::terminal_data_filename`）：
 *   报名字  终态帧交来一枚非空文件名 → 报那枚文件名（甲1）
 *   说不准  交来空串（零枚＝没跑数据；多枚＝没点名于是可见数据集全算了）→ 说人话「说不准」，
 *           并且【不回落到发依据那一份】（甲2，甲2 同时是"不许拿请求值冒充"的反显钉）
 *   不画    终态帧没这一格（旧后端／比树落后的镜像／R414 未并树的今天）→ 整句不出现（甲3）
 * 🔴 选「不画」的两个理由写在 ChatPanel.vue 里 serverDataOf 的注释上，甲3 钉的是它的屏上形状。
 *
 * 甲组直接把三种值交给消息对象（SSR 出真 HTML，断的是屏上那句话的文本，不是函数返回值）；
 * 乙组跑真 send()，把「lib → 面板」那一格交接（result.state.terminalDataFilename）接出来验；
 * 丙组钉的是【线上到屏上那一整截】：lib 不做桩（只把 mocked 的 consumeSseStream 接回真实现）跑真 send()，
 * 终态帧带文件名 → 屏上报那一个名字；空串 → 说不准；整格缺席 → 那一行一枚字都不画；读数还须随会话落盘。
 * R415 交单时这一组钉的是反面（lib 的 request.completed 分支把 data 的其余键丢掉 ⇒ 屏上不许凭空报名字），
 * 并自陈为【会自己报红的断点标记】：接线那一格落地那天它自己红，该改口的是它 —— 现在它改了，甲组没动。
 * 丁组钉本单没碰请求方向：发出去的那一发 body 里 data_filename 照旧（与 r169/r268 同一件事）。
 *
 * 反证怎么算红：把 serverDataOf 里空串那一支改成交回请求值 → 甲2 红；把缺席那一支也写成句子
 * → 甲3 红；把「报名字」那支的文件名换成 msg.dataFilename → 甲1 红；把 adoptServerDataRead 的
 * 非字符串守卫删掉（undefined 也写）→ 乙2 红。
 *
 * 🔴 本单没有牙的那一格：第 2 格要求把 ChatPanel.vue 里 R268 那段「要说出服务端那一份，需要后端在终态
 * 读数里带 data_filename」改口成今天的事实 —— 那是注释，不是判据。把旧句原样抄回那一行，甲乙丙丁四组照样全绿
 * （影子树读数 10 passed，见 R415 回执牙检③）。所以这枚件里一枚断言都不押在注释上：注释说什么，得靠读代码
 * 的人与总控核，不靠这枚钉子冒充验过。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, getCurrentInstance, h, nextTick, reactive } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { routeLocationKey, routerKey } from 'vue-router'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() }, authedFetch: vi.fn() }
})

// 乙/丁要验的是「lib 把读数交给面板之后，屏上说什么」，所以把这一格交接单独接出来。
// 🔴 这枚桩不证明后端会交这一格：那件事的凭据是 R414 并树之后总控在真树上的复读，见 R415 回执未证清单。
vi.mock('../../lib/sessions', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, consumeSseStream: vi.fn() }
})

import ChatPanel from '../ChatPanel.vue'
import { TOKEN_KEY, authedFetch, http } from '../../lib/http'
import {
  activeDataFilename,
  activeId,
  consumeSseStream,
  messages,
  resetSessions,
} from '../../lib/sessions'

// ==================== 屏上那句话怎么取：只认元素文本，不认函数返回值 ====================

const textOf = (html, testid) => [...html.matchAll(new RegExp(`data-testid="${testid}"[^>]*>([^<]*)<`, 'g'))].map(m => m[1])
const serverReadout = html => textOf(html, 'server-data-readout')
const sentReadout = html => textOf(html, 'data-table-readout')

const render = () => renderToString(h({ render: () => h(ChatPanel) }))

/** 一轮问答：发出去带 SENT，服务端那一份是 server（undefined ＝终态帧没这一格）。 */
function turn({ sent, server }) {
  const msg = { role: 'assistant', content: '最高 120 万。', steps: [], mid: 'a2' }
  if (typeof sent !== 'undefined') msg.dataFilename = sent
  if (typeof server !== 'undefined') msg.serverDataFilename = server
  return [
    { role: 'user', content: '各区域最高销售额', mid: 'a1' },
    msg,
  ]
}

// ==================== 乙/丙/丁 用的挂具（与 r268 同一套：本仓没有 jsdom） ====================

const SSR_CONTEXT_KEY = Symbol.for('v-scx')

function node(tag) {
  return { tag, props: {}, children: [], parent: null, text: '' }
}

const nodeOps = {
  createElement: tag => node(tag),
  createText: text => Object.assign(node('#text'), { text }),
  createComment: text => Object.assign(node('#comment'), { text }),
  setText: (target, text) => { target.text = text },
  setElementText: (el, text) => { el.children.length = 0; el.text = text },
  parentNode: target => target.parent || null,
  nextSibling(target) {
    const parent = target.parent
    if (!parent) return null
    return parent.children[parent.children.indexOf(target) + 1] || null
  },
  insert(target, parent, anchor) {
    if (target.parent) {
      const from = target.parent.children.indexOf(target)
      if (from >= 0) target.parent.children.splice(from, 1)
    }
    target.parent = parent
    const at = anchor ? parent.children.indexOf(anchor) : -1
    if (at < 0) parent.children.push(target)
    else parent.children.splice(at, 0, target)
  },
  remove(target) {
    if (target.parent) {
      target.parent.children.splice(target.parent.children.indexOf(target), 1)
      target.parent = null
    }
  },
  patchProp: (el, key, _prev, next) => {
    if (next === null || next === undefined) delete el.props[key]
    else el.props[key] = next
  },
  cloneNode: original => Object.assign(node(original.tag), { props: { ...original.props }, text: original.text }),
  insertStaticContent: () => [node('#static'), node('#static')],
  querySelector: () => null,
  setScopeId: () => {},
}

const { createApp } = createRenderer(nodeOps)

function installStorage(seed = {}) {
  const store = new Map(Object.entries(seed))
  globalThis.window = globalThis.window || { addEventListener() {}, removeEventListener() {} }
  globalThis.document = globalThis.document || {
    visibilityState: 'visible', addEventListener() {}, removeEventListener() {},
  }
  globalThis.localStorage = {
    getItem: key => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: key => store.delete(key),
    clear: () => store.clear(),
    key: index => [...store.keys()][index] ?? null,
    get length() { return store.size },
  }
  return store
}

const settled = async () => {
  for (let round = 0; round < 12; round += 1) await nextTick()
}

let mounted = null

async function mountPanel() {
  installStorage({ [TOKEN_KEY]: 'jwt-live' })
  activeId.value = 'r415-session'
  http.get.mockImplementation(async () => ({ data: {} }))
  let instance = null
  const errors = []
  const app = createApp({
    __name: 'R415Host',
    setup: ChatPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div', { id: 'r415-host' })
    },
  })
  app.config.warnHandler = () => {}
  app.config.errorHandler = err => errors.push(err)
  app.provide(SSR_CONTEXT_KEY, {})
  app.provide(routeLocationKey, reactive({ name: 'chat', path: '/chat', query: {}, params: {}, meta: {}, fullPath: '/chat', hash: '' }))
  app.provide(routerKey, { push: () => Promise.resolve(), replace: () => Promise.resolve() })
  app.mount(node('#root'))
  mounted = { app, errors, state: instance.setupState }
  await settled()
  return mounted
}

/** 真 SSE 帧形状（丙组喂真读取器用）。 */
function sseFrame(event, data) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

function sseResponse(frames) {
  const bytes = frames.map(frame => new TextEncoder().encode(frame))
  let index = 0
  return {
    ok: true,
    status: 200,
    headers: { get: () => null },
    clone() { return this },
    async json() { return null },
    body: { getReader() { return { async read() { return index < bytes.length ? { done: false, value: bytes[index++] } : { done: true } } } } },
  }
}

/** 一枚带服务端读数的终态帧：形状逐字照 R414 交回来的那一格。 */
const terminalFrameWithRead = sseFrame('request.completed', {
  request_id: 'req-1',
  sequence: 2,
  data: { session_id: 'r415-session', data_filename: 'sales.xlsx', worker_count: 1 },
})

// 响应形状够 send() 用：读头与读体都不许抛。
const STREAM_RESPONSE = sseResponse([terminalFrameWithRead])

const bodyOf = (callIndex = 0) => JSON.parse(authedFetch.mock.calls[callIndex][1].body)

beforeEach(() => {
  resetSessions()
  messages.value = []
  activeId.value = ''
  activeDataFilename.value = ''
  authedFetch.mockReset()
  http.get.mockReset()
  consumeSseStream.mockReset()
})

afterEach(() => {
  mounted?.app.unmount()
  mounted = null
})

describe('甲 · 三态各有名字（断的是屏上那句话的文本）', () => {
  it('报名字：终态帧交来一枚文件名，这一句报的就是它 —— 不是界面发出去的那一张', async () => {
    // 故意让两份不同名：任何"回落到请求值"的实现都会在这一枚当场红。
    messages.value = turn({ sent: '报销明细表.csv', server: 'sales.xlsx' })
    const html = await render()
    expect(serverReadout(html)).toEqual(['这一轮算数用的表：sales.xlsx'])
    expect(sentReadout(html)).toEqual(['本轮发问带的表：报销明细表.csv'])
  })

  it('说不准：交来空串就说不准，一个字都不许从发依据里借', async () => {
    messages.value = turn({ sent: '报销明细表.csv', server: '' })
    const html = await render()
    const lines = serverReadout(html)
    expect(lines).toHaveLength(1)
    expect(lines[0]).toContain('说不准')
    expect(lines[0]).toContain('没跑数据')
    expect(lines[0]).toContain('不止一份')
    // 🔴 本仓的假绿形状就在这两行：空串那一格不是"用了一份空文件"，更不是刚才点的那一张。
    expect(lines[0]).not.toContain('报销明细表.csv')
    expect(lines[0]).not.toContain('sales.xlsx')
    expect(sentReadout(html)).toEqual(['本轮发问带的表：报销明细表.csv'])
  })

  it('不画：终态帧没这一格就整句不出现，而发依据那一句照旧在（缺席不等于空串）', async () => {
    messages.value = turn({ sent: '报销明细表.csv' })
    const html = await render()
    expect(serverReadout(html)).toEqual([])
    expect(html).not.toContain('data-testid="server-data-readout"')
    expect(sentReadout(html)).toEqual(['本轮发问带的表：报销明细表.csv'])
  })

  it('三态两两不并格：两种有句子的说法彼此不同，第三种一句都没有', async () => {
    const named = serverReadout(await (async () => { messages.value = turn({ sent: '', server: 'sales.xlsx' }); return render() })())
    const unsure = serverReadout(await (async () => { messages.value = turn({ sent: '', server: '' }); return render() })())
    const silent = serverReadout(await (async () => { messages.value = turn({ sent: '' }); return render() })())
    expect(named).toHaveLength(1)
    expect(unsure).toHaveLength(1)
    expect(silent).toEqual([])
    expect(named[0]).not.toBe(unsure[0])
  })

  it('只说在助手那一侧：员工自己那句话不配拥有这一格', async () => {
    messages.value = [{ role: 'user', content: '各区域最高销售额', mid: 'a1', serverDataFilename: 'sales.xlsx' }]
    expect(serverReadout(await render())).toEqual([])
  })
})

describe('乙 · 流结束之后把读数抄进这一轮（接缝验法：交过来就得报名字）', () => {
  it('lib 交来一枚文件名 → 屏上出现那一句，而且随消息落盘可复原', async () => {
    consumeSseStream.mockResolvedValue({ ok: true, status: 200, stopped: 'done', state: { terminal: 'completed', terminalDataFilename: 'sales.xlsx' } })
    authedFetch.mockResolvedValue(STREAM_RESPONSE)
    const panel0 = await mountPanel()
    panel0.state.input = '各区域最高销售额是多少？'
    await panel0.state.send('报销明细表.csv')
    await settled()
    const html = await render()
    expect(serverReadout(html)).toEqual(['这一轮算数用的表：sales.xlsx'])
    const aiMsg = messages.value.filter(item => item.role === 'assistant').pop()
    expect(aiMsg.serverDataFilename).toBe('sales.xlsx')
    expect(aiMsg.dataFilename, '发依据没被读数顶掉：两句各说各的事').toBe('报销明细表.csv')
  })

  it('lib 什么都没交（今天的真实形状）→ 屏上一句都不许多，也不许回显请求值', async () => {
    consumeSseStream.mockResolvedValue({ ok: true, status: 200, stopped: 'done', state: { terminal: 'completed' } })
    authedFetch.mockResolvedValue(STREAM_RESPONSE)
    const panel0 = await mountPanel()
    panel0.state.input = '各区域最高销售额是多少？'
    await panel0.state.send('报销明细表.csv')
    await settled()
    const html = await render()
    expect(serverReadout(html)).toEqual([])
    expect(sentReadout(html)).toEqual(['本轮发问带的表：报销明细表.csv'])
  })

  it('lib 交来空串 → 屏上说不准，且不等于上面两态里的任何一句', async () => {
    consumeSseStream.mockResolvedValue({ ok: true, status: 200, stopped: 'done', state: { terminal: 'completed', terminalDataFilename: '' } })
    authedFetch.mockResolvedValue(STREAM_RESPONSE)
    const panel0 = await mountPanel()
    panel0.state.input = '把可见的数据都算一遍'
    await panel0.state.send('')
    await settled()
    const lines = serverReadout(await render())
    expect(lines).toHaveLength(1)
    expect(lines[0]).toContain('说不准')
    expect(sentReadout(await render())).toEqual(['本轮没指定数据表'])
  })
})

describe('丙 · 线上到屏上那一整截（lib 不做桩，只把 consumeSseStream 接回真实现）', () => {
  it('终态帧带文件名 → 屏上报的就是那一个名字，而不是界面发出去的那一张', async () => {
    const { aiMsg } = await realTurn(terminalFrameWithRead)
    const html = await render()
    expect(serverReadout(html), '线上那一格到屏上这一句必须接得住').toEqual(['这一轮算数用的表：sales.xlsx'])
    expect(aiMsg.serverDataFilename).toBe('sales.xlsx')
    expect(aiMsg.dataFilename, '发依据与用表读数各说各的事，一句不替另一句背书').toBe('报销明细表.csv')
  })

  it('终态帧交空串 → 屏上说不准，一个字都不许从发依据里借', async () => {
    await realTurn(sseFrame('request.completed', {
      request_id: 'req-1', sequence: 2, data: { session_id: 'r415-session', data_filename: '' },
    }))
    const lines = serverReadout(await render())
    expect(lines).toHaveLength(1)
    expect(lines[0]).toContain('说不准')
    expect(lines[0], '空串那一格不是「刚才点的那一张」').not.toContain('报销明细表.csv')
  })

  it('终态帧整格缺席 → 那一行一枚字都不画；缺席也不许写成「说不准」', async () => {
    const { aiMsg } = await realTurn(sseFrame('request.completed', {
      request_id: 'req-1', sequence: 2, data: { session_id: 'r415-session' },
    }))
    expect(serverReadout(await render())).toEqual([])
    expect('serverDataFilename' in aiMsg, '后端没说话，界面也不许替它宣布「说不准」').toBe(false)
    expect(sentReadout(await render())).toEqual(['本轮发问带的表：报销明细表.csv'])
  })

  it('读数随会话落盘：刷新回来仍报同一个名字，复原的不是现猜的', async () => {
    const { real } = await realTurn(terminalFrameWithRead)
    // 真 send() 收尾自己就走 syncActive() + persist()，这里只模拟刷新：内存 store 清空，
    // 正文只剩 localStorage 那一枚 —— 复原得回来才算那一格真落了盘。
    real.sessions.value = []
    real.messages.value = []
    real.restoreActive(real.loadSessions())
    const aiMsg = real.messages.value.filter(item => item.role === 'assistant').pop()
    expect(aiMsg.serverDataFilename, '随会话落盘的那一份没回来：刷新一次就读不到服务端读数了').toBe('sales.xlsx')
    expect(serverReadout(await render())).toEqual(['这一轮算数用的表：sales.xlsx'])
  })

  // 挂具放在最后一枚用例之后：函数声明提到整个 describe 作用域，而 307/308 那两行的位置
  // 是台账按行号指着这枚断点标记的（跟进单写的是「R415 丙组 :308」），不许被本单挪走。
  /**
   * 真帧 → 真读取器 → 真 send()：线上到屏上的整条腿都不做桩。
   * 返回那一轮的 assistant 消息与真模块（落盘那一枚要拿真模块自己那一份 store 模拟刷新）。
   */
  async function realTurn(frame) {
    const real = await vi.importActual('../../lib/sessions.js')
    consumeSseStream.mockImplementation(
      (response, msg, handlers) => real.consumeSseStream(response, msg, handlers),
    )
    authedFetch.mockResolvedValue(sseResponse([frame]))
    const panel0 = await mountPanel()
    panel0.state.input = '各区域最高销售额是多少？'
    await panel0.state.send('报销明细表.csv')
    await settled()
    const aiMsg = messages.value.filter(item => item.role === 'assistant').pop()
    return { aiMsg, real }
  }
})

describe('丁 · 请求方向那一格没被本单碰', () => {
  it('发出去的那一发 body 里 data_filename 照旧是选择框那一份', async () => {
    consumeSseStream.mockResolvedValue({ ok: true, status: 200, stopped: 'done', state: { terminal: 'completed' } })
    authedFetch.mockResolvedValue(STREAM_RESPONSE)
    const panel0 = await mountPanel()
    panel0.state.chooseDataTable('报销明细表.csv')
    panel0.state.input = '各区域最高销售额是多少？'
    await panel0.state.send()
    await settled()
    expect(authedFetch.mock.calls[0][0]).toBe('/ask')
    expect(bodyOf(0).data_filename).toBe('报销明细表.csv')
  })
})
