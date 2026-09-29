/**
 * R510 · 终态帧其余四枚键的屏侧脸：session_id／worker_count／elapsed／answer_length
 *
 * 病（改前取证）：后端今天在两枚终态出口都交出这四枚（app/api/v1/chat.py 的 /ask 与
 * /approve 各自的 request.completed，丁3 现读点名），lib 侧自 R501 起也整份交回
 * （result.state.terminalRead.data），而 ChatPanel.vue 一行未动 —— 屏上只有
 * data_filename 那一格（server-data-readout）。四枚读数到了界面却上不了屏，
 * 员工问「这一轮跑了几个工因／花了多久／答案多长」，屏上无话。
 *
 * 🔴 本件钉的是三形分开，一枚键一套：
 *   给了    后端交了这一格 ⇒ 报那一枚值；0 也是值（甲5），不许当成「没读到」
 *   空值    后端交了这一格但交回来的是空串 ⇒ 明说「它开了口，没给内容」（甲3）
 *   缺席    这一格压根没来 ⇒ 整条不出现（甲2／乙2／丙3）
 * 空值与缺席并脸＝替没说话的后端宣布它说了空话；把缺席补造成值＝说假话；四枚揉成一句
 * ＝没法说清哪一枚缺席。这三条就是甲4、甲7、乙4、丙2 各自咬住的东西。
 *
 * 反证怎么算红：把缺席那一支写成「空值」句 → 甲2/乙2/丙3 红；把四枚并成一句
 * → 甲7/丁2 红；让缺席回落到 activeId／msg.content.length → 丙2/丁4 红。
 *
 * 挂具与 r415 同一套（本仓没有 jsdom）：甲组直接给消息对象、SSR 出真 HTML 断屏上那句话；
 * 乙组跑真 send() 验「lib → 面板」那一格交接；丙组把 consumeSseStream 接回真实现，
 * 验【线上到屏上】整条腿；丁组钉两边键名逐字一致与「面板不当第三套判断」。
 */
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, getCurrentInstance, h, nextTick, reactive } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { routeLocationKey, routerKey } from 'vue-router'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() }, authedFetch: vi.fn() }
})

vi.mock('../../lib/sessions', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, consumeSseStream: vi.fn() }
})

import ChatPanel from '../ChatPanel.vue'
import { TOKEN_KEY, authedFetch, http } from '../../lib/http'
import { activeId, consumeSseStream, messages, resetSessions } from '../../lib/sessions'

// ==================== 四枚键：一枚一张脸，逐枚点名 data-testid ====================

const FACES = {
  session_id: 'terminal-session-readout',
  worker_count: 'terminal-worker-readout',
  elapsed: 'terminal-elapsed-readout',
  answer_length: 'terminal-answer-readout',
}
const KEYS = Object.keys(FACES)

const textOf = (html, testid) => [...html.matchAll(new RegExp(`data-testid="${testid}"[^>]*>([^<]*)<`, 'g'))].map(m => m[1])
const faceOf = (html, key) => textOf(html, FACES[key])

const render = () => renderToString(h({ render: () => h(ChatPanel) }))

/** 一轮问答：read 就是终态帧交回的那几枚键（undefined ＝ 这一帧压根没交）。 */
function turnWith(read) {
  const msg = { role: 'assistant', content: '最高 120 万。', steps: [], mid: 'a2' }
  if (typeof read !== 'undefined') msg.terminalReadData = read
  return [{ role: 'user', content: '各区域最高销售额', mid: 'a1' }, msg]
}

const GIVEN = { session_id: 'srv-9', worker_count: 3, elapsed: 12.4, answer_length: 2048 }
const GIVEN_TEXT = {
  session_id: '这一轮后端报的会话号：srv-9',
  worker_count: '这一轮后端报的分析工因数：3 枚',
  elapsed: '这一轮后端报的耗时：12.4 秒',
  answer_length: '这一轮后端报的答案长度：2048 个字符',
}
const EMPTY_TEXT = '后端这一格交回的是空值（它开了口，但没给内容）'

// ==================== 乙/丙 用的挂具（与 r415 同一套） ====================

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
  activeId.value = 'r510-local-session'
  http.get.mockImplementation(async () => ({ data: {} }))
  let instance = null
  const errors = []
  const app = createApp({
    __name: 'R510Host',
    setup: ChatPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div', { id: 'r510-host' })
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

const STREAM_RESPONSE = sseResponse([sseFrame('request.completed', { request_id: 'req-1', sequence: 1, data: GIVEN })])

const assistantMsg = () => messages.value.filter(item => item.role === 'assistant').pop()

beforeEach(() => {
  resetSessions()
  messages.value = []
  activeId.value = ''
  authedFetch.mockReset()
  http.get.mockReset()
  consumeSseStream.mockReset()
})

afterEach(() => {
  mounted?.app.unmount()
  mounted = null
})

describe('甲 · 三形各一张脸（断的是屏上那句话，一枚键一条 testid）', () => {
  it('给了：四枚各画一句，报的就是后端交回的那一枚值', async () => {
    messages.value = turnWith(GIVEN)
    const html = await render()
    for (const key of KEYS) expect(faceOf(html, key), key).toEqual([GIVEN_TEXT[key]])
  })

  it('缺席：整条不出现，四个 testid 一个都不许多出来', async () => {
    messages.value = turnWith(undefined)
    const html = await render()
    for (const key of KEYS) {
      expect(faceOf(html, key), key).toEqual([])
      expect(html, key).not.toContain(`data-testid="${FACES[key]}"`)
    }
  })

  it('给了空串：明说后端开了口没给内容，且不落进 0、不落进缺席', async () => {
    messages.value = turnWith({ session_id: '', worker_count: '', elapsed: '', answer_length: '' })
    const html = await render()
    for (const key of KEYS) {
      const lines = faceOf(html, key)
      expect(lines, key).toHaveLength(1)
      expect(lines[0], key).toContain(EMPTY_TEXT)
      expect(lines[0], key + '：空值不许画成 0').not.toMatch(/：0/)
    }
  })

  it.each(KEYS)('%s：给了／空值／缺席三形两两不并脸', async (key) => {
    messages.value = turnWith({ [key]: key === 'session_id' ? 'srv-9' : 7 })
    const given = faceOf(await render(), key)
    messages.value = turnWith({ [key]: '' })
    const empty = faceOf(await render(), key)
    messages.value = turnWith({})
    const silent = faceOf(await render(), key)
    expect(given).toHaveLength(1)
    expect(empty).toHaveLength(1)
    expect(silent).toEqual([])
    expect(given[0]).not.toBe(empty[0])
  })

  it('0 是值不是缺席：后端报 0 枚／0 秒／0 个字符，屏上就照实报 0', async () => {
    messages.value = turnWith({ session_id: 'srv-zero', worker_count: 0, elapsed: 0, answer_length: 0 })
    const html = await render()
    expect(faceOf(html, 'worker_count')).toEqual(['这一轮后端报的分析工因数：0 枚'])
    expect(faceOf(html, 'elapsed')).toEqual(['这一轮后端报的耗时：0 秒'])
    expect(faceOf(html, 'answer_length')).toEqual(['这一轮后端报的答案长度：0 个字符'])
  })

  it('只说在助手那一侧：员工自己那句话不配拥有这四格', async () => {
    messages.value = [{ role: 'user', content: '各区域最高销售额', mid: 'a1', terminalReadData: GIVEN }]
    const html = await render()
    for (const key of KEYS) expect(faceOf(html, key), key).toEqual([])
  })

  it('四枚各一张脸，不许揉成一句「本轮读数」：四条各含自己那一枚值，谁也不替谁背书', async () => {
    messages.value = turnWith(GIVEN)
    const html = await render()
    const lines = KEYS.map(key => faceOf(html, key))
    for (const one of lines) expect(one).toHaveLength(1)
    const said = lines.map(one => one[0])
    expect(new Set(said).size, '四句必须四样，并成一句就红').toBe(4)
    expect(html, '屏上不许出现一句「本轮读数」把它们糊在一起').not.toContain('本轮读数')
    for (let i = 0; i < KEYS.length; i += 1) {
      for (let j = 0; j < KEYS.length; j += 1) {
        if (i === j) continue
        expect(said[i], KEYS[i] + ' 那一句里不许出现 ' + KEYS[j] + ' 的值').not.toContain(String(GIVEN[KEYS[j]]))
      }
    }
  })

  it('部分到场：只交两枚时另两枚整格不画，有脸那两枚照说', async () => {
    messages.value = turnWith({ session_id: 'srv-partial', elapsed: 3.5 })
    const html = await render()
    expect(faceOf(html, 'session_id')).toEqual(['这一轮后端报的会话号：srv-partial'])
    expect(faceOf(html, 'elapsed')).toEqual(['这一轮后端报的耗时：3.5 秒'])
    expect(faceOf(html, 'worker_count')).toEqual([])
    expect(faceOf(html, 'answer_length')).toEqual([])
  })
})

describe('乙 · 流结束之后把整格读数抄进这一轮（lib → 面板那一格交接）', () => {
  it('lib 交来四枚 → 屏上四句都在，且随消息落盘', async () => {
    consumeSseStream.mockResolvedValue({ ok: true, status: 200, stopped: 'done', state: { terminal: 'completed', terminalRead: { event: 'request.completed', seen: KEYS, data: GIVEN } } })
    authedFetch.mockResolvedValue(STREAM_RESPONSE)
    const panel0 = await mountPanel()
    panel0.state.input = '各区域最高销售额是多少？'
    await panel0.state.send('报销明细表.csv')
    await settled()
    const html = await render()
    for (const key of KEYS) expect(faceOf(html, key), key).toEqual([GIVEN_TEXT[key]])
    expect(assistantMsg().terminalReadData).toEqual(GIVEN)
  })

  it('lib 连 terminalRead 都没交（缓存命中道／旧镜像今天的形状）→ 四句一枚都不画', async () => {
    consumeSseStream.mockResolvedValue({ ok: true, status: 200, stopped: 'done', state: { terminal: 'completed' } })
    authedFetch.mockResolvedValue(STREAM_RESPONSE)
    const panel0 = await mountPanel()
    panel0.state.input = '各区域最高销售额是多少？'
    await panel0.state.send('报销明细表.csv')
    await settled()
    const html = await render()
    for (const key of KEYS) expect(faceOf(html, key), key).toEqual([])
    expect('terminalReadData' in assistantMsg(), '后端没说话，消息对象里就不许多这一枚键').toBe(false)
  })

  it('只交两枚 → 另两枚整格不画，不许补空串也不许补 0', async () => {
    consumeSseStream.mockResolvedValue({ ok: true, status: 200, stopped: 'done', state: { terminal: 'completed', terminalRead: { event: 'request.completed', seen: ['session_id', 'elapsed'], data: { session_id: 'srv-two', elapsed: 2.5 } } } })
    authedFetch.mockResolvedValue(STREAM_RESPONSE)
    const panel0 = await mountPanel()
    panel0.state.input = '各区域最高销售额是多少？'
    await panel0.state.send('')
    await settled()
    const html = await render()
    expect(faceOf(html, 'session_id')).toEqual(['这一轮后端报的会话号：srv-two'])
    expect(faceOf(html, 'elapsed')).toEqual(['这一轮后端报的耗时：2.5 秒'])
    expect(faceOf(html, 'worker_count')).toEqual([])
    expect(faceOf(html, 'answer_length')).toEqual([])
    expect(assistantMsg().terminalReadData, '缺席的键不许被补进袋子').toEqual({ session_id: 'srv-two', elapsed: 2.5 })
  })

  it('给了空串与整格缺席同时在场 → 两种形状两张脸，一句都不许多', async () => {
    consumeSseStream.mockResolvedValue({ ok: true, status: 200, stopped: 'done', state: { terminal: 'completed', terminalRead: { event: 'request.completed', seen: ['session_id'], data: { session_id: '' } } } })
    authedFetch.mockResolvedValue(STREAM_RESPONSE)
    const panel0 = await mountPanel()
    panel0.state.input = '把可见的数据都算一遍'
    await panel0.state.send('')
    await settled()
    const html = await render()
    expect(faceOf(html, 'session_id')).toEqual(['这一轮后端报的会话号：' + EMPTY_TEXT])
    expect(faceOf(html, 'worker_count')).toEqual([])
  })

  it('键在而值是 undefined（后端没构造出来）→ 屏上无话可说，不与「交了空值」并脸', async () => {
    consumeSseStream.mockResolvedValue({ ok: true, status: 200, stopped: 'done', state: { terminal: 'completed', terminalRead: { event: 'request.completed', seen: ['worker_count'], data: { worker_count: undefined } } } })
    authedFetch.mockResolvedValue(STREAM_RESPONSE)
    const panel0 = await mountPanel()
    panel0.state.input = '各区域最高销售额是多少？'
    await panel0.state.send('')
    await settled()
    expect(faceOf(await render(), 'worker_count')).toEqual([])
  })
})

describe('丙 · 线上到屏上那一整截（lib 不做桩，真帧 → 真读取器 → 真 send()）', () => {
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
    return { aiMsg: assistantMsg(), real }
  }

  it('终态帧七枚键都交 → 屏上四句各取帧里那一份，data_filename 那一格不受影响', async () => {
    await realTurn(sseFrame('request.completed', {
      request_id: 'req-1', sequence: 2,
      data: { ...GIVEN, data_filename: 'sales.xlsx', awaiting_hitl: false, awaiting_steps: [] },
    }))
    const html = await render()
    for (const key of KEYS) expect(faceOf(html, key), key).toEqual([GIVEN_TEXT[key]])
    expect(textOf(html, 'server-data-readout')).toEqual(['这一轮算数用的表：sales.xlsx'])
  })

  it('🔴 帧里的读数与界面自己那几枚不同 → 屏上只能说帧里的，不许回显请求值/本地数', async () => {
    const { aiMsg } = await realTurn(sseFrame('request.completed', {
      request_id: 'req-1', sequence: 2,
      data: { session_id: 'srv-side-01', worker_count: 5, elapsed: 99.9, answer_length: 2048 },
    }))
    const html = await render()
    expect(faceOf(html, 'session_id'), '界面自己的会话号是 r510-local-session，不许冒充后端读数').toEqual(['这一轮后端报的会话号：srv-side-01'])
    expect(faceOf(html, 'worker_count')).toEqual(['这一轮后端报的分析工因数：5 枚'])
    expect(faceOf(html, 'elapsed')).toEqual(['这一轮后端报的耗时：99.9 秒'])
    expect(faceOf(html, 'answer_length'), '本地正文长度数得出，不许拿它当后端报的答案长度').toEqual(['这一轮后端报的答案长度：2048 个字符'])
    expect(aiMsg.content.length).not.toBe(2048)
    expect(activeId.value).toBe('r510-local-session')
  })

  it('终态帧不带这四枚（比树落后的镜像）→ 四句一枚都不画，也不许冒出一句「空值」', async () => {
    await realTurn(sseFrame('request.completed', {
      request_id: 'req-1', sequence: 2, data: { session: 'r510-local-session', data_filename: 'sales.xlsx' },
    }))
    const html = await render()
    for (const key of KEYS) expect(faceOf(html, key), key).toEqual([])
    expect(html).not.toContain(EMPTY_TEXT)
  })

  it('读数随会话落盘：刷新回来四句还在，复原的不是现猜的', async () => {
    const { real } = await realTurn(sseFrame('request.completed', {
      request_id: 'req-1', sequence: 2, data: GIVEN,
    }))
    real.sessions.value = []
    real.messages.value = []
    real.restoreActive(real.loadSessions())
    const aiMsg = assistantMsg()
    expect(aiMsg.terminalReadData, '随会话落盘的那一份没回来：刷新一次就读不到后端读数了').toEqual(GIVEN)
    const html = await render()
    for (const key of KEYS) expect(faceOf(html, key), key).toEqual([GIVEN_TEXT[key]])
  })
})

describe('丁 · 两边逐字对齐 + 面板不当第三套判断（源码级）', () => {
  const panel = () => readFileSync(new URL('../ChatPanel.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
  const lib = () => readFileSync(new URL('../../lib/sessions.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
  const chat = () => readFileSync(new URL('../../../../app/api/v1/chat.py', import.meta.url), 'utf8').replace(/\r\n/g, '\n')

  it('接缝的键名两边逐字一致：lib 交回的那一枚就是面板读的那一枚', () => {
    expect(panel(), '面板读的那一格名字漂了：这四句永远不画').toContain('result?.state?.terminalRead?.data')
    expect(lib()).toContain("state.terminalRead = { event: 'request.completed', seen: Object.keys(data), data: { ...data } }")
  })

  it('四枚各占一条 testid、各调自己那张脸：屏上不是一句合起来的读数', () => {
    const src = panel()
    const pairs = [
      ['terminal-session-readout', 'terminalSessionFace'],
      ['terminal-worker-readout', 'terminalWorkerFace'],
      ['terminal-elapsed-readout', 'terminalElapsedFace'],
      ['terminal-answer-readout', 'terminalAnswerFace'],
    ]
    for (const [testid, fn] of pairs) {
      expect(src, testid).toContain(`data-testid="${testid}"`)
      expect(src.split(fn + '(msg, i)').length - 1, fn + ' 应当 v-if 与插值各调一次').toBe(2)
    }
  })

  it('后端两枚终态出口今天确实交出这四枚键（屏侧这句话的全部依据）', () => {
    const src = chat()
    const exits = [...src.matchAll(/"request\.completed",/g)].length
    expect(exits, 'request.completed 的出口数变了：这一枚取证必须重新看').toBe(2)
    for (const match of src.matchAll(/"request\.completed",/g)) {
      const block = src.slice(match.index, match.index + 900)
      for (const key of KEYS) expect(block, '这一枚出口不再交 ' + key + '：屏上那一句就成了假话').toContain(`"${key}"`)
    }
  })

  it('读数的脸不读请求方向：函数体里不许出现 activeId／msg.content.length／发依据那几枚', () => {
    const src = panel()
    const from = src.indexOf('function terminalReadFace(')
    expect(from).toBeGreaterThan(0)
    const faceBody = src.slice(from, src.indexOf('\n}', from))
    for (const banned of ['activeId', 'content.length', 'dataFilename', 'serverDataFilename', 'Date.now']) {
      expect(faceBody, '回显了 ' + banned + '：那就是把界面自己的数冒充成后端读数').not.toContain(banned)
    }
  })

  it('缺席判据走 hasOwnProperty：不许把真值判断当缺席（0 与空串都会在这格翻车）', () => {
    const src = panel()
    expect(src).toContain('Object.prototype.hasOwnProperty.call(bag, key)')
    expect(src).toContain('Object.prototype.hasOwnProperty.call(data, key)')
  })
})
