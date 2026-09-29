/**
 * R293 第二棒 · 判据①②③④ —— 「取消已登记」那一格落盘这条路的真路径凭据
 *
 * 病灶（第一棒留下的那一格）：员工按下「不排了」拿到【非终态】回执（后端那一格叫
 * cancel_requested）时，状态只进内存里的 queueReads，不落 msg.queue，于是刷新或换回这条会话时
 * queueReads 是空的，ChatPanel.vue:1441 那条守卫的前置 read && 整条跳过，:1449 就把落盘那一格
 * （还是 queued）原样交给 queueFace —— 屏幕把「已登记取消」改口画回「排队中」。
 * 第一棒补上了写点（ChatPanel.vue 里那一格 `msg.queue = { ...(msg.queue || {}), requestId, status: receipt.status }`，按符号点名不写行号——行号会漂、符号不会），本件钉的就是这条写点真的能办事。
 *
 * 为什么必须走真路径（而不是手搭一枚 historyTurn('cancel_requested')）：手搭就是把病灶当成
 * 前提写进夹具，写点摘掉也照样绿 —— 那正是第一棒被指出的假绿风险。本件全程没有手搭：
 *   真挂载面板 → 真打字 → 真点「发送」→ 真 SSE 帧 event: queued 长出 requestId →
 *   真点「新建会话」→ 真点回旧会话 → 真点「不排了」→ 真拿到非终态回执 →
 *   真看那一次回写；再卸载、只留盘，用盘上那一格重新挂载，看屏幕第二回说什么。
 *
 * 手法沿用 r198 / r260 / r268 那一套（createRenderer + 内存虚拟节点跑【真客户端生命周期】），
 * 外加两处必须说清的加码，都为了「屏幕」这两个字：
 *  ① 本仓 vitest 是 environment: 'node'，.vue 以 ssr 档位变换加载，组件身上只有 ssrRender
 *     没有 render（所以 r268 那句「真 QueueFace 上屏」只能 renderToString，拿不到能点的钮）。
 *     本件把磁盘上那份 <template> 用 vue 自带的 @vue/compiler-sfc 按【客户端档位】再编一遍挂回
 *     组件（零 npm i、零 lockfile 变更、零配置改动）。于是 r268 的 setup 壳换成了真模板，
 *     @cancel="cancelQueuedTurn(msg, i)" 这层接线本身也在被测范围内，点的是模板长出来的钮。
 *  ② <TransitionGroup> / <Transition> / <Teleport> 的动效与挂载点住在真 DOM 里
 *     （getBoundingClientRect / activeElement / document.body），虚拟节点树上无处安放，换成透传壳。
 *     换掉的只有「动效外壳」与「teleport 落点」：节点内容、key、v-for 全部来自真模板。
 * 🔴 壳必须是【有状态组件】不能是函数组件：函数组件不参与 updateSlots，父件重渲染时它不跟着
 *     重渲染，屏幕会永远停在第一帧。下面那条体质与本条都是本件踩过之后钉在这里的。
 * 🔴 本件现取到两格里体质（都不是夹具毛病：换上真 TransitionGroup 在同一棵树上同样如此）：
 *     一、lib/sessions.js 的 messages 是 shallowRef，send() 只 push，而编译出来的
 *         <TransitionGroup> slot 带 _: 1 /* STABLE *\/ → 面板重渲染不带着这一列重画，冷启动头
 *         一发问出去的那一轮画不到屏上。所以本件走产品自己那条「新建会话 → 点回旧会话」
 *         （switchSession 里 restoreActive 会整份重新赋值 messages）把这一轮换回屏上 —— 而
 *         「换回会话」本来就是病灶句子里点名的一半，一并进了实测范围。
 *     二、onMounted 里 restoreQueuedTurns() 排在 loadSessions() / restoreActive() 之前
 *         （ChatPanel.vue:868 对 :875-880）→ 刷新那一轮 messages 还是空的，这一轮没有重新盯表。
 *         所以丙2 钉的是「一枪读数都没打」：落盘那一格是屏幕唯一的依据。
 * 时钟是假的（一格 3 秒 = QUEUE_POLL_MS），网络层假在一处：lib/http 的 http / authedFetch。
 *
 * 反证怎么算红（四把，逐把现跑，跑完按字节还原复验 ChatPanel.vue sha256 前 16 = c34c7d925517e217）：
 *  刀一 摘掉写点里那一发 persist()        -> 只红 1 枚：甲3
 *  刀二 把落的 status 写死成 'cancelled'   -> 红 8 枚：甲3 乙2 丙1 丙2 丙3 丙4 丁2 丁3
 *        （乙1 / 乙4 / 丁1 仍绿：按下那一腿的脸与表都读 queueReads 那一格，不认盘上写的是什么）
 *  刀三 顺手把 stopQueueWatch() / syncActive() 加回这一格
 *        -> 只红 2 枚：乙4（表被停）+ 乙5（updatedAt 被顶到侧栏最前）—— 这一格的差别就是本单的全部意义
 *  刀四 面板取脸入口分叉出自持的第二份措辞  -> 红 4 枚：乙1 丙3 丁1 丁3
 *        （丁2 仍绿：刷新那一腿走 :1449 的 queueFace(msg.queue)，本来就没经过面板自持那一份）
 *  16 枚里 4 枚（甲1 甲2 甲4 乙3）四把刀都摘不红，是有意的分工：它们钉的是「路径真不真」
 *  （模板编不编得出来 / requestId 只来自真 queued 帧 / 走没走排队那条腿 / 登记后还给不给第二枚取消钮），
 *  与措辞、落盘无关，红不到它们不算漏。
 *
 * 一处诚实账（刀一之下丙组为什么不红 —— 现取，不是推测）：摘掉那一发 persist() 之后，按下当刻
 * writes 里一条 cancel_requested 都没有、盘上仍是 queued；但卸载之后再读盘已经是 cancel_requested。
 * 掩盖它的是这条通道：ChatPanel.vue:888 onUnmounted -> :745 flushScroll -> lib/sessions.js:153
 * rememberScroll -> :63 syncActive -> :76 persist —— syncActive 把内存里那整包 msg.queue 带上盘，
 * 而刀一只摘了写点的后半发（persist），前半发 msg.queue = ... 还在。真浏览器里 F5 走的是
 * visibilitychange / pagehide 那条同构通道，同样可能顺带落住 —— 但「顺带」不等于「当场」：进程被强杀、
 * 标签页崩溃、下一次落盘时机不来，盘上就永远停在 queued，而病灶句子里点名的正是刷新那一屏。
 * 所以刀一的判死钉是【按下这一发之内看盘】的甲3（点之前记 writes 水位，只在零推进的窗口里找那一格），
 * 不是重新挂载那几枚；写点这一发 persist() 要买的是「按下即落住」，不赌下一次。
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as Vue from 'vue'
import { createRenderer, nextTick, proxyRefs, reactive } from 'vue'
import { compileScript, compileTemplate, parse } from '@vue/compiler-sfc'
import { routeLocationKey, routerKey } from 'vue-router'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
    authedFetch: vi.fn(),
  }
})

import ChatPanel from '../ChatPanel.vue'
import { authedFetch, http } from '../../lib/http'
import { queueFace } from '../../lib/provenance'
import { SESSIONS_KEY, activeId, hitl, loading, messages, sessions } from '../../lib/sessions'

const REQUEST_ID = 'req-r293b'
const POLL_MS = 3000
const MESSAGE_KEY_PREFIX = 'eb_msg_'
const SSR_CONTEXT_KEY = Symbol.for('v-scx')
const QUESTION = '帮我看一下这季度毛利'

/** 两枚字面量一律从 lib 取，本件一个字都不抄：抄了就是用第二份措辞去测第一条腿。 */
const PENDING = queueFace({ status: 'cancel_requested' })
const QUEUED = queueFace({ status: 'queued', position: 2 })
/** 屏幕上那一句话 = 脸上两枚字段逐字连起来，与 faceAt() 读屏的拼法同构。 */
const voiceOf = face => `${face.headline}\n${face.detail || ''}`
const PENDING_VOICE = voiceOf(PENDING)
const QUEUED_VOICE = voiceOf(QUEUED)

/* ------------------------------------------------------------ 客户端档位模板 */

const passthrough = {
  name: 'R293bShell',
  setup(_props, ctx) {
    return () => (ctx.slots && ctx.slots.default ? ctx.slots.default() : null)
  },
}
const NAMESPACE = { ...Vue, TransitionGroup: passthrough, Transition: passthrough, Teleport: passthrough }
const VIEWS = import.meta.glob('../**/*.vue', { eager: true })
const compileProblems = []

function attachClientTemplates() {
  for (const [rel, mod] of Object.entries(VIEWS)) {
    const component = mod && mod.default
    if (!component || component.__r293bAttached) continue
    const file = fileURLToPath(new URL(rel, import.meta.url))
    const source = readFileSync(file, 'utf8').replace(/\r\n/g, '\n')
    const { descriptor } = parse(source, { filename: file })
    if (!descriptor.template) continue
    const script = compileScript(descriptor, { id: 'r293b', inlineTemplate: false })
    const { code, errors } = compileTemplate({
      source: descriptor.template.content,
      filename: file,
      id: 'r293b',
      compilerOptions: { bindingMetadata: script.bindings, mode: 'function', prefixIdentifiers: true },
    })
    if (errors.length) {
      compileProblems.push(`${rel}: ${errors.map(err => String(err.message || err)).join('; ')}`)
      continue
    }
    const factory = new Function('Vue', code)(NAMESPACE)
    const baseSetup = component.setup
    component.setup = function setup(props, ctx) {
      const bindings = baseSetup(props, ctx)
      if (typeof bindings === 'function') return bindings
      // 模板里 $setup.x 要的是【解包之后】的读数，与 Vue 自己给 instance.setupState 那一份同构。
      // 直接递 bindings 进去，每个 ref 都是对象真值，整屏 v-if 会集体走错分支（本件踩过）。
      const state = proxyRefs(bindings)
      return function render(_ctx, _cache) {
        return factory.call(_ctx, _ctx, _cache, _ctx.$props, state, _ctx.$data, _ctx.$options)
      }
    }
    component.__r293bAttached = true
  }
}
attachClientTemplates()

/* ------------------------------------------------------- 虚拟节点渲染器与假 DOM */

function makeNode(tag) {
  return {
    tag,
    props: {},
    children: [],
    parent: null,
    text: '',
    listeners: {},
    value: '',
    nodeType: 1,
    style: {},
    scrollTop: 0,
    scrollHeight: 0,
    clientHeight: 0,
    offsetTop: 0,
    offsetHeight: 0,
    offsetWidth: 0,
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn) },
    removeEventListener(type, fn) {
      const list = this.listeners[type]
      if (list) {
        const at = list.indexOf(fn)
        if (at >= 0) list.splice(at, 1)
      }
    },
    getBoundingClientRect: () => ({ top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 }),
    getRootNode() { return this },
    contains: () => false,
    focus() {},
    blur() {},
    scrollIntoView() {},
  }
}

const nodeOps = {
  createElement: tag => makeNode(tag),
  createText: text => Object.assign(makeNode('#text'), { text, nodeType: 3 }),
  createComment: text => Object.assign(makeNode('#comment'), { text, nodeType: 8 }),
  setText: (target, text) => { target.text = String(text) },
  setElementText: (el, text) => { el.children.length = 0; el.text = String(text) },
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
    if (key === 'value') el.value = next === null || next === undefined ? '' : String(next)
  },
  cloneNode: original => Object.assign(makeNode(original.tag), { props: { ...original.props }, text: original.text }),
  insertStaticContent: content => [
    Object.assign(makeNode('#static'), { text: content }),
    Object.assign(makeNode('#static'), { text: content }),
  ],
  querySelector: () => null,
  setScopeId: () => {},
}

const { createApp } = createRenderer(nodeOps)

let writes = []

function installStorage() {
  const store = new Map()
  // 面板要三枚弹窗成员在场，但它们一律写成 `alert: noop` 这种「值」的形状，不写成 `alert() {}`：
  // r288 那枚门钉（components/__tests__/r288-native-buttons.test.js 甲组第一钉）扫 src 下所有
  // .vue/.js 且不豁免 __tests__ 目录，字面一出现就多一发「原生弹窗调用点」——本件现取实测。
  const noop = () => {}
  globalThis.window = {
    addEventListener: noop, removeEventListener: noop,
    confirm: () => true, alert: noop, prompt: () => null, open: noop,
  }
  globalThis.document = {
    visibilityState: 'visible', activeElement: null,
    addEventListener() {}, removeEventListener() {},
  }
  globalThis.localStorage = {
    getItem: key => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => { store.set(key, String(value)); writes.push({ key, value: String(value) }) },
    removeItem: key => store.delete(key),
    clear: () => store.clear(),
    key: index => [...store.keys()][index] ?? null,
    get length() { return store.size },
  }
  globalThis.getComputedStyle = () => ({
    getPropertyValue: () => '0s',
    transitionDelay: '0s', transitionDuration: '0s',
    animationDelay: '0s', animationDuration: '0s', transitionProperty: 'all',
  })
  globalThis.requestAnimationFrame = callback => setTimeout(() => callback(Date.now()), 0)
  globalThis.cancelAnimationFrame = id => clearTimeout(id)
  // v-model 的 beforeUpdate 会拿 rootNode instanceof Document / ShadowRoot 判焦点：这两枚全局
  // 缺席时表达式直接 ReferenceError。给空壳 == 判不出实例 == 「这一枚没被聚焦」，与真浏览器里
  // 焦点不在输入框上时走的是同一条分支。
  globalThis.Document = class Document {}
  globalThis.ShadowRoot = class ShadowRoot {}
  return store
}

const diskKeys = () => Array.from({ length: localStorage.length }, (_, i) => localStorage.key(i))
const messageKeys = () => diskKeys().filter(key => key.startsWith(MESSAGE_KEY_PREFIX))
const diskTurns = key => {
  const target = key || messageKeys()[0]
  return target ? JSON.parse(localStorage.getItem(target)) : null
}
const diskQueues = () => (diskTurns() || []).map(turn => turn.queue).filter(Boolean)
const diskSessions = () => {
  const raw = localStorage.getItem(SESSIONS_KEY)
  return raw ? JSON.parse(raw).sessions : []
}
const diskQueueWith = status => diskQueues().find(entry => entry && entry.status === status)

let server = null

/** 一台假排队服务器：入队先回 queued，取消之后每一枪读到的都是回执那一格。 */
function makeServer() {
  const state = {
    receipt: 'cancel_requested',
    phase: 'queued',
    hang: false,
    calls: 0,
    delivered: 0,
    cancelCalls: [],
  }
  http.get.mockImplementation(url => {
    const target = String(url)
    if (target.startsWith('/queue/status')) {
      state.calls += 1
      if (state.hang) return new Promise(() => {})
      state.delivered += 1
      return Promise.resolve({
        data: { status: state.phase, request_id: REQUEST_ID, position: state.phase === 'queued' ? 2 : null },
      })
    }
    if (target === '/queue/stats') return Promise.resolve({ data: { queue_length: 1, processing: 0 } })
    return Promise.resolve({ data: { problems: [] } })
  })
  http.post.mockImplementation(url => {
    const target = String(url)
    if (target.endsWith('/cancel')) {
      state.cancelCalls.push(target)
      state.phase = state.receipt
      return Promise.resolve({ data: { cancelled: true, request_id: REQUEST_ID, status: state.receipt } })
    }
    return Promise.resolve({ data: {} })
  })
  return state
}

function sseStream(frames) {
  const encoder = new TextEncoder()
  let at = 0
  return {
    ok: true,
    status: 200,
    headers: { get: () => null },
    body: {
      getReader: () => ({
        read: async () => (at < frames.length ? { value: encoder.encode(frames[at++]), done: false } : { done: true }),
      }),
    },
  }
}

/* ------------------------------------------------------------------ 树上的读数 */

const walk = (n, out = []) => {
  out.push(n)
  for (const child of n.children) walk(child, out)
  return out
}
const textOf = n => {
  if (!n || n.tag === '#comment') return ''
  if (n.tag === '#text' || n.tag === '#static') return n.text
  if (n.children.length) return n.children.map(textOf).join('')
  return n.text
}
const find = (root, testId) => walk(root).filter(n => n.props && n.props['data-testid'] === testId)
const one = (root, testId) => (root ? find(root, testId)[0] || null : null)
const rows = root => walk(root).filter(n => n.props && n.props['data-turn'] !== undefined)
const sessionRows = root => walk(root).filter(n => String((n.props && n.props.class) || '').includes('session-item'))
const statusPolls = () => http.get.mock.calls.filter(call => String(call[0]).startsWith('/queue/status')).length

function faceAt(root) {
  const faces = find(root, 'queue-face')
  expect(faces.length, `屏幕上画了 ${faces.length} 张排队脸，读数没法归到一枚`).toBeLessThanOrEqual(1)
  const face = faces[0]
  if (!face) return null
  const headline = textOf(one(face, 'queue-headline'))
  const detail = textOf(one(face, 'queue-detail'))
  return {
    kind: face.props['data-kind'],
    ahead: face.props['data-ahead'],
    headline,
    detail,
    voice: `${headline}\n${detail}`,
    cancelLabel: textOf(one(face, 'queue-cancel')),
    cancel: Boolean(one(face, 'queue-cancel')),
    retry: Boolean(one(face, 'queue-retry')),
  }
}

/* ---------------------------------------------------------- 挂载与真路径操作 */

let panel = null

async function settle() {
  for (let round = 0; round < 4; round += 1) {
    await nextTick()
    await vi.advanceTimersByTimeAsync(0)
  }
  await nextTick()
}

/** 只清模块态，盘一行都不动 —— 这就是「刷新」在本夹具里的全部含义。 */
function wipeStoreState() {
  messages.value = []
  sessions.value = []
  activeId.value = ''
  loading.value = false
  hitl.value = null
}

function mountPanel() {
  const root = makeNode('root')
  const seen = { errors: [], warnings: [] }
  const app = createApp(ChatPanel)
  app.config.warnHandler = message => seen.warnings.push(String(message))
  app.config.errorHandler = err => seen.errors.push(String((err && err.message) || err))
  app.provide(SSR_CONTEXT_KEY, {})
  app.provide(routeLocationKey, reactive({
    name: 'chat', path: '/chat', query: {}, params: {}, meta: {}, fullPath: '/chat', hash: '',
  }))
  app.provide(routerKey, { push: () => Promise.resolve(), replace: () => Promise.resolve() })
  app.mount(root)
  panel = { root, app, ...seen }
  return panel
}

async function unmountPanel() {
  if (!panel) return
  await panel.app.unmount()
  panel = null
}

function click(el, what) {
  expect(el, `${what}没画到屏上，谈不到真点`).toBeTruthy()
  el.props.onClick({ target: el, currentTarget: el, preventDefault() {}, stopPropagation() {} })
}

/** 真打字 + 真点发送：这一轮的 requestId 只可能来自真 SSE 帧。 */
async function sendQuestion(text = QUESTION) {
  const input = one(panel.root, 'chat-input')
  const send = one(panel.root, 'chat-send')
  expect(input, '屏幕连输入框都没画出来：模板没按客户端档位编').toBeTruthy()
  expect(send, '「发送」这一枚钮没画出来就谈不上真路径').toBeTruthy()
  input.value = text
  input.props.value = text
  ;(input.listeners.input || []).forEach(fn => fn({
    target: input, currentTarget: input, preventDefault() {}, stopPropagation() {},
  }))
  await settle()
  click(send, '「发送」')
  await settle()
}

/**
 * 换回这一条会话：产品自己那条路（点「新建会话」再点回旧会话）。两个理由见文件头体质一：
 * 冷启动 push 进 shallowRef 的这一轮换不回屏上，而「换回会话」正是病灶句子点名的一半。
 */
async function returnToThisSession(sessionTitle) {
  const before = sessions.value.length
  click(one(panel.root, 'new-session'), '「新建会话」')
  await settle()
  expect(sessions.value.length, '新建会话没把上一条留在名单里').toBeGreaterThan(before)
  const row = sessionRows(panel.root).find(entry => textOf(entry).includes(sessionTitle))
  click(row, '侧栏里那一条会话')
  await vi.advanceTimersByTimeAsync(POLL_MS)
  await settle()
}

/** 甲组前奏：挂载 → 真发问 → 换回会话 → 屏上确实是「排队中」且有一枚能点的「不排了」。 */
async function queuedTurnOnScreen() {
  mountPanel()
  await settle()
  await sendQuestion()
  const turn = messages.value[messages.value.length - 1]
  expect(turn.role).toBe('assistant')
  expect(turn.queue, 'requestId 没从真 queued 帧里长出来').toEqual({ requestId: REQUEST_ID, status: 'queued' })
  await returnToThisSession(QUESTION)
  const face = faceAt(panel.root)
  expect(face, '换回会话之后屏上没有排队脸').toBeTruthy()
  expect(face.kind).toBe('queued')
  expect(face.voice).toBe(QUEUED_VOICE)
  expect(face.cancelLabel).toBe('不排了')
  return face
}

async function pressCancel() {
  const button = one(panel.root, 'queue-cancel')
  expect(button, '排队中那一轮没画出「不排了」，就没有真路径可走').toBeTruthy()
  const watermark = writes.length
  click(button, '「不排了」')
  await settle()
  return watermark
}

/** 卸载 → 只清模块态 → 重新挂载（读数一枪不打，见 makeServer().hang）。 */
async function pressThenReload() {
  await queuedTurnOnScreen()
  const pressedVoice = faceAt(panel.root).voice
  await pressCancel()
  const afterPressVoice = faceAt(panel.root).voice
  await unmountPanel()
  writes = []
  wipeStoreState()
  server.hang = true
  server.calls = 0
  server.delivered = 0
  const second = mountPanel()
  await settle()
  return { second, pressedVoice, afterPressVoice, refreshedVoice: faceAt(second.root).voice }
}

beforeEach(() => {
  vi.useFakeTimers()
  writes = []
  installStorage()
  wipeStoreState()
  server = makeServer()
  authedFetch.mockReset()
  authedFetch.mockResolvedValue(
    sseStream([`event: queued\ndata: ${JSON.stringify({ request_id: REQUEST_ID })}\n\n`]),
  )
})

afterEach(async () => {
  await unmountPanel()
  vi.useRealTimers()
  http.get.mockReset()
  http.post.mockReset()
})

/* ------------------------------------------------------------------ 甲：真路径 */

describe('甲 · 真路径：真挂载 → 真发一轮 → 真点「不排了」，非终态那一格当场落盘', () => {
  it('甲1 屏幕是真模板画出来的，客户端编译一处没红', async () => {
    mountPanel()
    await settle()
    expect(compileProblems, `客户端档位编译失败：${compileProblems.join(' | ')}`).toEqual([])
    expect(String(ChatPanel.__file).replace(/\\/g, '/')).toMatch(/src\/components\/ChatPanel\.vue$/)
    expect(panel.errors, `挂载报错：${panel.errors.join(' | ')}`).toEqual([])
    expect(messages.value).toHaveLength(0)
    expect(one(panel.root, 'chat-input')).toBeTruthy()
    expect(one(panel.root, 'chat-send')).toBeTruthy()
    expect(faceAt(panel.root), '冷启动不该有排队脸').toBe(null)
  })

  it('甲2 requestId 只来自真 queued 帧，换回会话时屏上先说「排队中」', async () => {
    await queuedTurnOnScreen()
    expect(messages.value[messages.value.length - 1].queue.status).toBe('queued')
    expect(rows(panel.root).length, '这一轮压根没画到屏上').toBeGreaterThanOrEqual(2)
  })

  it('甲3 按下这一发之内盘上真回写过一次，带的就是 cancel_requested', async () => {
    await queuedTurnOnScreen()
    const sessionId = activeId.value
    const watermark = await pressCancel()
    const landed = writes.slice(watermark).filter(entry => entry.key === `${MESSAGE_KEY_PREFIX}${sessionId}`)
    expect(landed.length, '按下之后一次回写都没有：写点里那一发 persist() 是空的').toBeGreaterThan(0)
    expect(
      landed.some(entry => JSON.parse(entry.value).some(turn => turn.queue && turn.queue.status === 'cancel_requested')),
      '回写发生了，但盘上那一份不是 cancel_requested',
    ).toBe(true)
  })

  it('甲4 走的确实是排队那条腿，且只发一发', async () => {
    await queuedTurnOnScreen()
    await pressCancel()
    expect(server.cancelCalls).toEqual([`/queue/${REQUEST_ID}/cancel`])
  })
})

/* ------------------------------------------ 乙：落的必须是后端给的那一枚非终态 */

describe('乙 · 落的是后端那一枚非终态：不冒充终态、不停表、不顶侧栏', () => {
  it('乙1 屏幕说「取消已登记」，两头都不站', async () => {
    await queuedTurnOnScreen()
    await pressCancel()
    const face = faceAt(panel.root)
    expect(face.kind).toBe('cancel-requested')
    expect(face.voice).toBe(PENDING_VOICE)
    expect(face.voice).not.toContain('已取消，')
    expect(face.voice).not.toContain('这一轮在后台执行失败')
    expect(face.retry, '还没落定的一轮不该给重试钮').toBe(false)
  })

  it('乙2 消息对象上那一份：requestId 原样，status 是 cancel_requested 而不是 cancelled', async () => {
    await queuedTurnOnScreen()
    const turn = messages.value[messages.value.length - 1]
    await pressCancel()
    expect(turn.queue.requestId).toBe(REQUEST_ID)
    expect(turn.queue.status).toBe('cancel_requested')
    expect(diskQueueWith('cancelled'), '盘上不该有还没发生的终态').toBe(undefined)
  })

  it('乙3 登记之后不再给第二次「不排了」：这一格的出路只有等它落定', async () => {
    await queuedTurnOnScreen()
    await pressCancel()
    expect(faceAt(panel.root).cancel, '非终态那一格又长出一枚取消钮').toBe(false)
  })

  it('乙4 表继续开着：登记之后仍然每 3 秒读一次状态（没有顺手停表）', async () => {
    await queuedTurnOnScreen()
    await pressCancel()
    const before = statusPolls()
    await vi.advanceTimersByTimeAsync(POLL_MS * 2)
    await settle()
    expect(statusPolls() - before, '刚登记就停表：这一轮的落定再也没人读').toBeGreaterThanOrEqual(2)
    expect(faceAt(panel.root).kind).toBe('cancel-requested')
  })

  it('乙5 侧栏没被这一发顶到最前：updatedAt 仍是按下之前的读数（没有顺手 syncActive）', async () => {
    await queuedTurnOnScreen()
    const sessionId = activeId.value
    const before = diskSessions().find(entry => entry.id === sessionId).updatedAt
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await settle()
    await pressCancel()
    const after = diskSessions().find(entry => entry.id === sessionId).updatedAt
    expect(after, '顺手 syncActive：没落定的一轮把这条会话顶到了侧栏最前').toBe(before)
  })
})

/* ------------------------------------------------ 丙：两段式重新挂载（刷新） */

describe('丙 · 卸载之后只用盘上那一格重新挂载：屏幕不许改口画回「排队中」', () => {
  it('丙1 第二次挂载读的还是 cancel-requested，不是 queued', async () => {
    const { second } = await pressThenReload()
    const face = faceAt(second.root)
    expect(face, '重新挂载之后屏幕上连脸都没有了').toBeTruthy()
    expect(face.kind).toBe('cancel-requested')
    expect(face.headline).toBe(PENDING.headline)
    expect(face.voice).not.toContain('前面还有')
  })

  it('丙2 说话的就是盘上那一格：重新挂载一枪读数都没打', async () => {
    const { second } = await pressThenReload()
    // 体质二（本件现取）：onMounted 里 restoreQueuedTurns() 排在 loadSessions()/restoreActive()
    // 之前，刷新那一轮 messages 还是空的 → 这一轮没有重新盯表。落盘那一格因此是屏幕唯一的依据。
    expect(server.calls, '刷新之后又打了一枪状态：这一枚就不是落盘腿').toBe(0)
    expect(server.delivered).toBe(0)
    expect(rows(second.root).length, '重新挂载没把这一轮画到屏上').toBeGreaterThanOrEqual(2)
    expect(faceAt(second.root).kind).toBe('cancel-requested')
  })

  it('丙3 两腿同脸：按下那一发（内存读数）/ 刷新那一发（落盘读数）逐字相同', async () => {
    const { pressedVoice, afterPressVoice, refreshedVoice } = await pressThenReload()
    expect(pressedVoice, '换回会话时屏上说的还是排队中那一句').toBe(QUEUED_VOICE)
    expect(afterPressVoice).toBe(PENDING_VOICE)
    expect(refreshedVoice).toBe(afterPressVoice)
    expect(refreshedVoice, '屏幕说的不是 lib 那一张脸').toBe(PENDING_VOICE)
    expect(refreshedVoice.length, '短到不像同一句话').toBeGreaterThan(30)
  })

  it('丙4 盘上那一格到重新挂载之后仍然是非终态', async () => {
    await pressThenReload()
    expect(diskQueueWith('cancel_requested'), '盘上找不到非终态那一格').toBeTruthy()
    expect(diskQueueWith('cancelled'), '盘上出现了还没发生的终态').toBe(undefined)
  })
})

/* ------------------------------------------------ 丁：两条腿必须走到同一张脸 */

describe('丁 · 两条腿走到的是 lib 那一张脸，措辞不分叉', () => {
  it('丁1 按下那一发（内存读数腿）渲染的措辞 === lib 那张脸，逐字', async () => {
    await queuedTurnOnScreen()
    await pressCancel()
    const face = faceAt(panel.root)
    expect([face.headline, face.detail]).toEqual([PENDING.headline, PENDING.detail])
  })

  it('丁2 刷新那一发（落盘读数腿）渲染的措辞 === 同一张脸，逐字', async () => {
    const { second } = await pressThenReload()
    const face = faceAt(second.root)
    expect([face.headline, face.detail]).toEqual([PENDING.headline, PENDING.detail])
  })

  it('丁3 两条腿彼此逐字相同（面板不再自持第二份措辞）', async () => {
    const { pressedVoice, afterPressVoice, refreshedVoice } = await pressThenReload()
    expect(refreshedVoice).toBe(afterPressVoice)
    expect(refreshedVoice).not.toBe(pressedVoice)
    expect(refreshedVoice).toBe(PENDING_VOICE)
  })
})
