/**
 * R458 · 判据② · 「再看一次」这一枚入口的行为钉
 *
 * 这一格要的形状（裁定原文）：入口落在既有的 runtime-faces 那一区，员工伸手才发请求、
 * 卸载清 timer、挂载期零请求 —— 纪律照本文件里 session-pull 那一族（serverPull :505 /
 * pullServerSessions :553 / 甲组「挂载期与空转期都没有打 /sessions」），不自创一套。
 * 🔴 它不许长在壳层：r307b 两枚（App.vue 里 <UiButton 恰 8 枚、渲染枚数 = navigation.length+2）
 * 与 r288（App.vue 裸 <button> 归零）一字未动，本件丙组第三条就是拿这三枚现成尺复量一遍。
 *
 * 三条腿：① 真产物（renderToString 出真 HTML，屏上那枚按钮叫什么、禁用没禁用都读渲染结果）；
 * ② 真逻辑（跑面板自己的 setup / onMounted / onUnmounted，网络层换成假实现，时钟冻住）；
 * ③ 源码形状（只钉会被行为推翻的那几格：区段顺序、timer 的成对收口）。
 */
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, getCurrentInstance, h, nextTick, reactive, unref } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { routeLocationKey, routerKey } from 'vue-router'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { ...actual.http, get: vi.fn(), post: vi.fn(), delete: vi.fn() } }
})

import ChatPanel from '../ChatPanel.vue'
import App from '../../App.vue'
import { http, TOKEN_KEY } from '../../lib/http'
import { fetchRuntimeHealth, resetRuntimeHealthCache } from '../../lib/health.js'
import { navigation } from '../../router'
import { countNativeButtons, stripComments } from './r288-native-button-scan.js'

const HEALTH = '/health/details'
const RECHECK_TEXT = '再看一次'
const HOLD_MS = 30_000

const panelSource = () => readFileSync(new URL('../ChatPanel.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const appSource = readFileSync(new URL('../../App.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
/** 模板段（含模板注释）：区段顺序这件事只有模板能回答。 */
const template = () => {
  const source = panelSource()
  // 侧栏里还嵌着一段 <template v-if>，收尾要认最后一个 </template>：认第一个会把名单自己切掉。
  return source.slice(source.indexOf('<template>'), source.lastIndexOf('</template>'))
}

const readyBody = { status: 'ok', problems: [], model: { name: 'qwen3:4b', source: 'ollama' }, storage: {} }
const degradedBody = {
  status: 'degraded',
  problems: ['embedding_model_missing'],
  model: { name: 'qwen3:4b', source: 'ollama' },
  storage: {},
}

/* ---------------------------------------------------------------- 假后端与账本 */

let paths = []
let body = readyBody
let failure = null
let holdGate = null

function installBackend() {
  paths = []
  failure = null
  holdGate = null
  http.get.mockImplementation(async (url) => {
    const target = String(url)
    paths.push(target)
    if (target === HEALTH) {
      if (holdGate) await holdGate
      if (failure) throw failure
    }
    return { data: body }
  })
  http.post.mockImplementation(async () => ({ data: {} }))
  http.delete.mockImplementation(async () => ({ data: {} }))
}

const healthCount = () => paths.filter(path => path === HEALTH).length

/* ------------------------------------------------------------------- 生命周期腿 */

function node(tag) {
  return { tag, props: {}, children: [], parent: null, text: '' }
}

const nodeOps = {
  createElement: tag => node(tag),
  createText: text => Object.assign(node('#text'), { text }),
  createComment: text => Object.assign(node('#comment'), { text }),
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
    if (!target.parent) return
    target.parent.children.splice(target.parent.children.indexOf(target), 1)
    target.parent = null
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
const SSR_CONTEXT_KEY = Symbol.for('v-scx')

function installDomStubs() {
  const store = new Map(Object.entries({ [TOKEN_KEY]: 'jwt-live' }))
  globalThis.window = {
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => true,
    setTimeout,
    clearTimeout,
  }
  globalThis.document = {
    visibilityState: 'visible',
    addEventListener: () => {},
    removeEventListener: () => {},
    createElement: tag => node(tag),
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

const flush = async (rounds = 4) => {
  for (let round = 0; round < rounds; round += 1) {
    await nextTick()
    await vi.advanceTimersByTimeAsync(0)
  }
}

let mounted = null

/** 面板真挂载：跑它自己的 setup() 与它自己的 onMounted / onUnmounted（在册手法，同 r268）。 */
async function mountPanel() {
  installDomStubs()
  let instance = null
  const errors = []
  const app = createApp({
    __name: 'R458RecheckHost',
    setup: ChatPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div', { id: 'r458-host' })
    },
  })
  app.config.warnHandler = () => {}
  app.config.errorHandler = err => errors.push(err)
  app.provide(SSR_CONTEXT_KEY, {})
  app.provide(routeLocationKey, reactive({
    name: 'chat', path: '/chat', query: {}, params: {}, meta: {}, fullPath: '/chat', hash: '',
  }))
  app.provide(routerKey, { push: () => Promise.resolve(), replace: () => Promise.resolve() })
  app.mount(node('#root'))
  await flush()
  mounted = { app, errors, state: instance.setupState }
  return mounted
}

/** 把同一份 setup 绑定再渲一次真 HTML：SSR 不跑 onMounted，落地与否由这里自己推。 */
const renderHtml = () => renderToString(h({ ...ChatPanel, setup: () => mounted.state }))

/** 面板当前那一句「再看一次」的脸（从真产物里抠，不读函数返回值）。 */
/** 抠出带这枚 testid 的那个开标签全文：属性顺序由 Vue 决定，不由本件猜。 */
function openTagOf(html, testId) {
  const at = html.indexOf('data-testid="' + testId + '"')
  if (at < 0) return null
  const start = html.lastIndexOf('<', at)
  let quote = null
  for (let i = at; i < html.length; i += 1) {
    const ch = html[i]
    if (quote) { if (ch === quote) quote = null; continue }
    if (ch === '"' || ch === "'") quote = ch
    else if (ch === '>') return html.slice(start, i + 1)
  }
  return null
}

/** 从面板源码的模板里抠出「再看一次」那一段（含它自己的开标签，嵌套 div  counted）。 */
function recheckBlockSource() {
  const source = panelSource()
  const start = source.indexOf('<div class="runtime-recheck"')
  if (start < 0) return null
  const scan = /<div\b|<\/div>/g
  scan.lastIndex = start
  let depth = 0
  let hit = null
  while ((hit = scan.exec(source))) {
    depth += hit[0] === '</div>' ? -1 : 1
    if (depth === 0) return source.slice(start, scan.lastIndex)
  }
  return null
}

const faceLine = html => {
  const hit = /data-testid="runtime-recheck-face"[^>]*>([^<]*)</.exec(html)
  return hit ? hit[1].trim() : null
}
const recheckRegion = (html) => {
  const from = html.indexOf('data-testid="runtime-recheck"')
  if (from < 0) return ''
  const to = html.indexOf('data-testid="chat-messages"', from)
  return html.slice(from, to < 0 ? html.length : to)
}

/**
 * 面板挂载复用壳层那一发：先用真 fetchRuntimeHealth 把那份 60 秒缓存喂热（这就是壳层进工作台打的那
 * 一发），再清账本、再挂面板 —— 后面每一条数的都是「面板自己有没有另开一枪」。
 */
async function mountWithWarmCache(nextBody = readyBody) {
  body = nextBody
  resetRuntimeHealthCache()
  await fetchRuntimeHealth()
  paths = []
  return mountPanel()
}

beforeEach(() => {
  vi.useFakeTimers()
  installBackend()
})

afterEach(() => {
  mounted?.app.unmount()
  mounted = null
  vi.useRealTimers()
  http.get.mockReset()
  http.post.mockReset()
  http.delete.mockReset()
  resetRuntimeHealthCache()
})

/* --------------------------------------------------------------------- 甲 · 位置 */

describe('R458 甲 · 入口落在 runtime-faces 那一区', () => {
  it('甲1 区段顺序现取：降级名单之后、消息区之前，就贴着它说话', () => {
    const tpl = template()
    const faces = tpl.indexOf('data-testid="runtime-faces"')
    const recheck = tpl.indexOf('data-testid="runtime-recheck"')
    const messages = tpl.indexOf('data-testid="chat-messages"')
    expect(faces, '找不到降级名单那一段（testid 被改名或挪走）').toBeGreaterThan(-1)
    expect(recheck, '找不到「再看一次」那一段').toBeGreaterThan(-1)
    expect(recheck, '「再看一次」不在 runtime-faces 那一区').toBeGreaterThan(faces)
    if (messages > -1) expect(recheck, '「再看一次」跑到消息区后面去了').toBeLessThan(messages)
  })

  it('甲2 真产物里那枚按钮画得出来：testid、原生 type、屏幕上叫什么，都读渲染结果', async () => {
    const panel = await mountWithWarmCache()
    const html = await renderHtml()
    const open = openTagOf(html, 'runtime-recheck-button')
    expect(open, '渲染产物里没有那枚「再看一次」的按钮开标签').toBeTruthy()
    expect(open, '原语给的原生 type 没跟着上屏').toMatch(/type="button"/)
    expect(open, '那一枚按钮的可及名称不在渲染产物里').not.toMatch(/disabled/)
    const labeled = /data-testid="runtime-recheck-button"[\s\S]{0,240}?再看一次/.exec(html)
    expect(labeled, '钮上那句话没画上屏（假控件的另一种形状）').toBeTruthy()
    expect(panel.errors).toEqual([])
    // R278 那一族的病：画得出来、按下去什么都没发生。SSR 产物里看不见监听器，所以这条腿
    // 拿两枚现成的东西对账 —— 模板里那一段确实把 @click 绑给了这个名字，而这个名字确实是一枚函数。
    const block = recheckBlockSource()
    expect(block, '模板里抠不出「再看一次」那一段').toBeTruthy()
    expect(block, '那枚按钮没绑 @click：按下去什么都不发生（R278 摘掉的就是这种假控件）')
      .toMatch(/@click="recheckRuntimeHealth"/)
    expect(typeof panel.state.recheckRuntimeHealth, '@click 绑的是一个不存在的东西').toBe('function')
  })

  it('甲3 它长在面板不长在壳层：三枚在册棘轮一字未动（不放宽的自证）', () => {
    const shellCode = stripComments(appSource)
    expect(shellCode, 'App.vue 里出现了 runtime-recheck：这一枚不许长在壳层').not.toContain('runtime-recheck')
    expect((appSource.match(/<UiButton\b/g) || []).length, 'r307b 第一枚：App.vue 里 <UiButton 恰 8 枚').toBe(8)
    expect(countNativeButtons(appSource), 'r288 那枚：App.vue 裸 <button> 归零').toBe(0)
    // r307b 第二枚（屏上渲染枚数 = navigation.length + 2）数的是【壳层真挂载】那一面，本仓没有
    // jsdom / @vue/test-utils，那一枚由它自己的件在 App 那侧守着；本件证的是它的前提：这枚新控件
    // 落在面板，一枚都没往壳层去 —— 那条账的数因此一个字没动。
    expect(navigation.length, '侧栏屏数读不出来：这本账无从对照').toBeGreaterThan(3)
    expect(countNativeButtons(panelSource()), 'r288 那一族对面板的要求：裸 <button> 归零').toBe(0)
  })
})

/* --------------------------------------------------------------- 乙 · 伸手才发 */

describe('R458 乙 · 员工伸手才发请求', () => {
  it('乙1 挂载期一枚都不发，那行字也不预先画（v-if，不是画着藏着）', async () => {
    const panel = await mountWithWarmCache()
    await vi.advanceTimersByTimeAsync(60_000)
    await flush()
    expect(healthCount(), '挂载期或空转期打了健康读数：这一格又变成第二读取点').toBe(0)
    expect(unref(panel.state.runtimeRecheck).phase).toBe('idle')
    const html = await renderHtml()
    expect(html, 'idle 那一刻就把那行字画上了屏（v-show 的形状）').not.toContain('data-testid="runtime-recheck-face"')
    expect(html).toContain('data-testid="runtime-recheck"')
  })

  it('乙2 按下去那一刻：sending 那句先在屏上，读数回来后那句改口，且只发一发', async () => {
    const panel = await mountWithWarmCache()
    let release = null
    holdGate = new Promise((done) => { release = done })
    const pending = panel.state.recheckRuntimeHealth()
    await flush()
    expect(healthCount(), '伸手那一刻没发出去').toBe(1)
    expect(faceLine(await renderHtml()), 'sending 那一刻没说话').toContain('正在')
    holdGate = null
    body = degradedBody
    release()
    await pending
    await flush()
    const html = await renderHtml()
    expect(faceLine(html), '读数回来之后那行字没改口').toContain('降级')
    expect(healthCount()).toBe(1)
    expect(unref(panel.state.runtimeFaceList).map(face => face.kind)).toEqual(['embedding'])
  })

  it('乙3 sending 期间按不动第二枚：真 disabled + 再点一次多发零枚（假控件的另一种形状）', async () => {
    const panel = await mountWithWarmCache()
    let release = null
    holdGate = new Promise((done) => { release = done })
    const pending = panel.state.recheckRuntimeHealth()
    await flush()
    const html = await renderHtml()
    const sendingOpen = openTagOf(html, 'runtime-recheck-button')
    expect(sendingOpen, 'sending 期间抠不出那枚按钮的开标签').toBeTruthy()
    expect(sendingOpen, '那枚按钮在渲染产物里没被禁用：按下去就是第二发').toMatch(/disabled/)
    expect(sendingOpen, '忙碌那一档没给读屏留下 aria-busy').toMatch(/aria-busy="true"/)
    await panel.state.recheckRuntimeHealth()
    await flush()
    expect(healthCount(), 'sending 期间又补了一发').toBe(1)
    holdGate = null
    release()
    await pending
    await flush()
  })

  it('乙4 读不到那一句自己说话：既不画成就绪，也不画成降级', async () => {
    const panel = await mountWithWarmCache()
    failure = new Error('这台机器上的服务此刻不应答')
    await panel.state.recheckRuntimeHealth()
    await flush()
    const line = faceLine(await renderHtml())
    expect(line, '取不到那一句没上屏').toContain('没问到')
    expect(line).not.toContain('就绪')
    expect(line).not.toContain('降级')
  })

  it('乙5 三种落法三句话，两两不等：同一句红文案兜三格是判据点名的假话', async () => {
    const panel = await mountWithWarmCache()
    const said = new Set()
    await panel.state.recheckRuntimeHealth()
    await flush()
    said.add(faceLine(await renderHtml()))
    body = degradedBody
    await panel.state.recheckRuntimeHealth()
    await flush()
    said.add(faceLine(await renderHtml()))
    failure = new Error('不应答')
    await panel.state.recheckRuntimeHealth()
    await flush()
    said.add(faceLine(await renderHtml()))
    expect(said.has(null), '有一种落法一句话都没说').toBe(false)
    expect(said.size, '三种落法并成了同一句话').toBe(3)
  })

  it('乙6 按几次就发几发，一枚都不许多：伸手这一格不是扇出器', async () => {
    const panel = await mountWithWarmCache()
    for (let round = 0; round < 3; round += 1) {
      await panel.state.recheckRuntimeHealth()
      await flush()
    }
    expect(healthCount(), '三按打出多于三发：这里长出了扇出').toBe(3)
  })
})

/* ---------------------------------------------------------------- 丙 · timer 纪律 */

describe('R458 丙 · 卸载清 timer，且不靠它轮询', () => {
  it('丙1 伸手后立刻卸载：推进两倍 hold，零请求、零报错（尾巴收干净了）', async () => {
    const panel = await mountWithWarmCache()
    await panel.state.recheckRuntimeHealth()
    await flush()
    expect(healthCount()).toBe(1)
    // 先落地一句话，好让「退场调度」真的存在：没落地就没有 timer 可清，这一条就成了空转。
    expect(unref(panel.state.runtimeRecheck).phase, '对照腿自己没到 done：丙1 无从证明').toBe('done')
    panel.app.unmount()
    mounted = null
    await vi.advanceTimersByTimeAsync(HOLD_MS * 2)
    await flush()
    expect(healthCount(), '卸载之后那枚 timer 又醒过来发了请求').toBe(1)
    // 卸载之后状态必须停在 done：摘掉 onUnmounted 里那一句 clearRecheckFaceTimer()，
    // 这枚 timer 会在组件已经不在了的时刻把 phase 洗回 idle —— 这一条当场红（影子副本实跑，见回执）。
    expect(unref(panel.state.runtimeRecheck).phase, '卸载后 timer 还在替已经不在了的面板改状态').toBe('done')
  })

  it('丙2 正向对照：不卸载时推进同一格，那行字真的退场（证明这枚 timer 是活的）', async () => {
    const panel = await mountWithWarmCache()
    await panel.state.recheckRuntimeHealth()
    await flush()
    expect(faceLine(await renderHtml()), '对照腿自己就没说话：丙1 的「零」无从证明').toBeTruthy()
    await vi.advanceTimersByTimeAsync(HOLD_MS)
    await flush()
    expect(unref(panel.state.runtimeRecheck).phase, '那枚 timer 没把这一格收回 idle')
      .toBe('idle')
    expect(faceLine(await renderHtml()), '过期那句话还赖在屏上冒充当前状态').toBe(null)
  })

  it('丙3 挂载那一段不许调度这枚 timer：它是伸手之后才长出来的，不是每进一次页面就转起来', () => {
    const panel = stripComments(panelSource())
    const mount = /onMounted\(\(\) => \{[\s\S]*?\n\}\)/.exec(panel)[0]
    expect(mount, '挂载就给「再看一次」排了 timer').not.toMatch(/recheckFaceTimer/)
    expect(panel.match(/setTimeout\(retireRecheckFace/g), '退场调度不止一处').toHaveLength(1)
  })

  it('丙4 卸载那一段确实调用收口函数（摘掉它丙1 当场红）', () => {
    const panel = stripComments(panelSource())
    const unmount = /onUnmounted\(\(\) => \{[\s\S]*?\n\}\)/.exec(panel)[0]
    expect(unmount, 'onUnmounted 里没收口这一枚 timer').toMatch(/clearRecheckFaceTimer\(\)/)
  })
})
