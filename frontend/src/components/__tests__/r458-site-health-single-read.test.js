/**
 * R458 · 判据③ + 判据① · 全站 GET /health/details 的发数计数器
 *
 * 病灶（本单基点 09c968f 现读，行号自己 rg 的）：全站两处读数点。
 *   · 壳层 App.vue 的 readRuntimeHealth → fetchRuntimeHealth()，R452 已收成「进工作台恰好一发」；
 *   · 面板 ChatPanel.vue 挂载期那一句写的是 fetchRuntimeHealth({ force: true })，force 穿的正是
 *     lib/health.js 那 60 秒缓存 ⇒ 员工一进对话屏，同一个人站在柜台前问两遍同一件事。
 * 本件钉的是收完之后：任意「登录 → 进工作台 → 切遍每一屏 → 静置」序列里这一发 <= 1，
 * 只有员工伸手按「再看一次」那一刻才允许出现第 2 发。
 *
 * 计数器的拦截点与时钟（为什么它拦得住第 2 发）：
 *   拦在 lib/http 那枚 axios 实例的 get 上（vi.mock 换掉），也就是【真 fetchRuntimeHealth 真要发
 *   请求时必走的那一格】—— 不拦在组件上，也不拦在 lib/health.js 上。面板无论用不用 force、
 *   无论被挂几枚实例，底层真发了就一定在 paths 里多一枚；paths 是唯一账本，读数 = 过滤那枚地址。
 *   时钟是 vi.useFakeTimers()（连 Date.now 一起冻）：「静置 1.5 秒」与「60 秒缓存」都是推出来的
 *   量，不靠真等，也不受本机负载影响。
 *   生命周期是真的：本仓 vitest 把 SFC 模板编成 ssrRender（node 环境，无 jsdom），所以「真挂载」
 *   一律走在册手法 —— r268-session-pull 的 createRenderer + 宿主 setup：跑的是 ChatPanel 自己的
 *   setup() 与它自己的 onMounted / onUnmounted，桩树上没有一枚 setTimeout 是假的。
 *   两把空转自证钉在下面：丙3 把「改前那种 force 穿透」摆进同一把尺，当场数出第 2 发；
 *   乙1 先证明壳层那一发真的打出去了。任一失效，上面那些数字都是空话。
 *
 * 一句话口径（丙5 把它量成读数，不是注释）：判据③那条「<= 1」钉的是【已落地的读数】这一格；
 * 壳层那一发还在路上时面板就挂上来，全站会打出第 2 发 —— 两发都不穿透缓存，代价是一枚本地 GET。
 * 闭它要在 lib/health.js 里加一枚 in-flight 读数（本单写域之外），丙5 现取的那个数记在回执。
 *
 * 反证怎么造（🔴 一律造在临时副本里，绝不原地改被跟踪文件 —— 事故 #71 的入规）：
 *   源码腿一律走 panelSource()，它认环境变量 R458_PANEL：把 ChatPanel.vue 复制到临时目录、改那份
 *   副本、带着变量重跑本件就是摘守卫；不落变量时读的是树里那一枚，一个字都不改。红数记在回执。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, getCurrentInstance, h, nextTick, reactive, unref } from 'vue'
import { createMemoryHistory } from 'vue-router'
import { routeLocationKey, routerKey } from 'vue-router'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { ...actual.http, get: vi.fn(), post: vi.fn(), delete: vi.fn() } }
})

import App from '../../App.vue'
import ChatPanel from '../ChatPanel.vue'
import { http, ROLE_KEY, TOKEN_KEY, USER_KEY } from '../../lib/http'
import { fetchRuntimeHealth, resetRuntimeHealthCache } from '../../lib/health.js'
import { createAppRouter, screenRouteIds } from '../../router'
import { stripComments } from './r288-native-button-scan.js'

const HEALTH = '/health/details'
const SRC_ROOT = resolve(import.meta.dirname, '..', '..')

/** 源码腿的取材点：默认读树里那枚被跟踪文件；R458_PANEL 指向临时副本时读副本（见文件头）。 */
function panelSource() {
  const from = process.env.R458_PANEL
  const text = from
    ? readFileSync(resolve(from), 'utf8')
    : readFileSync(new URL('../ChatPanel.vue', import.meta.url), 'utf8')
  return text.replace(/\r\n/g, '\n')
}
const appSource = readFileSync(new URL('../../App.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')

const READY = { status: 'ok', problems: [], model: { name: 'qwen3:4b', source: 'ollama' }, storage: {} }
const DEGRADED = {
  status: 'degraded',
  problems: ['embedding_model_missing'],
  model: { name: 'qwen3:4b', source: 'ollama' },
  storage: {},
}

/* ------------------------------------------------------------------ 假后端 */

let paths = []

function installBackend(read, { hold = false, keepLedger = false } = {}) {
  if (!keepLedger) paths = []
  let release = null
  const gate = new Promise((done) => { release = done })
  http.get.mockImplementation(async (url) => {
    const target = String(url)
    paths.push(target)
    if (target === HEALTH && hold) await gate
    return { data: read }
  })
  http.post.mockImplementation(async () => ({ data: {} }))
  http.delete.mockImplementation(async () => ({ data: {} }))
  return { release: () => release() }
}

const healthCount = () => paths.filter(path => path === HEALTH).length

/* --------------------------------------------------- 无 DOM 的真生命周期（在册手法） */

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
    if (target.parent) {
      parentDetach(target)
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

function parentDetach(target) {
  target.parent.children.splice(target.parent.children.indexOf(target), 1)
  target.parent = null
}

const { createApp } = createRenderer(nodeOps)

// 本仓 vitest 把 SFC 编成 ssrRender（node 环境），编译后的 setup() 里有一句 ssrContext.modules.add ——
// 所以宿主必须供上那枚 SSR 上下文，r268-session-pull / r452 挂真组件走的就是这一格（不是新发明）。
const SSR_CONTEXT_KEY = Symbol.for('v-scx')

function installDomStubs(seed = {}) {
  const store = new Map(Object.entries(seed))
  globalThis.document = {
    visibilityState: 'visible',
    activeElement: null,
    title: '',
    addEventListener: () => {},
    removeEventListener: () => {},
    createElement: tag => node(tag),
    createTextNode: text => Object.assign(node('#text'), { text }),
    body: node('body'),
    documentElement: node('html'),
  }
  globalThis.window = {
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => true,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    confirm: () => true,
    alert: () => {},
    open: () => null,
    location: { href: 'http://localhost/overview', origin: 'http://localhost' },
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

const SESSION_SEED = { [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'staff' }

/**
 * 壳层真挂载：宿主用 App 自己的 setup()，挂上真 router（memory history），
 * App 的 onMounted → checkAuth → enterWorkspace → readRuntimeHealth 一整串真跑。
 * 切屏改的是那一枚 reactive route（与 r452 同一条道），横幅与面板读的都是同一份状态。
 */
async function bootShell(read, options = {}) {
  const { hold = false, keepLedger = false, freshCache = true } = options
  if (freshCache) resetRuntimeHealthCache()
  const gate = installBackend(read, { hold, keepLedger })
  installDomStubs(SESSION_SEED)
  const route = reactive({
    name: 'overview', path: '/overview', query: {}, params: {},
    meta: { title: '总览', screen: true }, fullPath: '/overview', hash: '', matched: [],
  })
  const errors = []
  let instance = null
  const app = createApp({
    __name: 'R458ShellHost',
    setup: App.setup,
    render() {
      instance = getCurrentInstance()
      return h('div', { id: 'r458-shell' })
    },
  })
  app.config.warnHandler = () => {}
  app.config.errorHandler = err => errors.push(err)
  app.provide(SSR_CONTEXT_KEY, {})
  app.provide(routeLocationKey, route)
  app.provide(routerKey, { push: () => Promise.resolve(), replace: () => Promise.resolve(), currentRoute: route })
  app.mount(node('#root'))
  await flush()
  const state = instance.setupState
  return {
    app, state, route, errors, gate,
    health: healthCount,
    goto: async (name) => {
      route.name = name
      route.path = '/' + name
      await flush()
    },
    unmount: () => app.unmount(),
  }
}

/** 面板真挂载：跑 ChatPanel 自己的 setup() 与它自己的 onMounted / onUnmounted。 */
async function mountPanel(name = 'chat') {
  const route = reactive({
    name, path: '/' + name, query: {}, params: {},
    meta: { title: '问一句', screen: true }, fullPath: '/' + name, hash: '', matched: [],
  })
  const errors = []
  let instance = null
  const app = createApp({
    __name: 'R458PanelHost',
    setup: ChatPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div', { id: 'r458-panel' })
    },
  })
  app.config.warnHandler = () => {}
  app.config.errorHandler = err => errors.push(err)
  app.provide(SSR_CONTEXT_KEY, {})
  app.provide(routeLocationKey, route)
  app.provide(routerKey, { push: () => Promise.resolve(), replace: () => Promise.resolve(), currentRoute: route })
  app.mount(node('#root'))
  await flush()
  return { app, errors, state: instance.setupState, unmount: () => app.unmount() }
}

// 每一枚用例跑在冻住的时钟上：「静置」与「60 秒缓存」都是推出来的量，不是等出来的量。
beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  http.get.mockReset()
  http.post.mockReset()
  http.delete.mockReset()
})

/* ------------------------------------------------------------------ 甲 · 普查 */

const srcFiles = (() => {
  const out = []
  const walk = (dir) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry)
      if (statSync(full).isDirectory()) {
        if (entry === '__tests__' || entry === 'node_modules') continue
        walk(full)
      } else if (/\.(vue|js)$/.test(entry)) out.push(full)
    }
  }
  walk(SRC_ROOT)
  return out
})()

const relOf = file => file.slice(SRC_ROOT.length + 1).split('\\').join('/')
const codeOf = file => stripComments(readFileSync(file, 'utf8').replace(/\r\n/g, '\n'))
/** 剥注释之后的代码体（r267 / r278 同一口径：文档注释里写着那枚地址不算调用点）。 */
const codeFiles = srcFiles.map(file => [relOf(file), codeOf(file)])
const writersOf = needle => codeFiles.filter(([, code]) => code.includes(needle)).map(([rel]) => rel).sort()

describe('R458 甲 · 全站读取点普查（源码层，本件现取）', () => {
  it('甲1 把那枚地址写在代码里的只有 lib/health.js 一枚：面板与壳层都不自己写地址', () => {
    expect(writersOf(HEALTH), '又有人自己写那枚地址：多一处就多一发').toEqual(['lib/health.js'])
  })

  it('甲2 请这把尺上场的只有两枚文件：壳层与对话面板（lib/health.js 是定义那枚，不算消费方）', () => {
    const importer = /import \{[^}]*\bfetchRuntimeHealth\b[^}]*\} from '[^']*lib\/health\.js'/
    const consumers = codeFiles.filter(([, code]) => importer.test(code)).map(([rel]) => rel).sort()
    expect(consumers, '读取点长出了第三枚消费文件').toEqual(['App.vue', 'components/ChatPanel.vue'])
  })

  it('甲3 面板对这把尺的引用恰三枚；穿透缓存的字面量恰一枚，且伸手那一条只能走它', () => {
    const panel = stripComments(panelSource())
    // 三枚 = import 一枚 + 缓存复用那一条裸调一枚 + 穿透那一条一枚。
    expect((panel.match(/fetchRuntimeHealth/g) || []).length, '面板里对这把尺的引用枚数变了').toBe(3)
    expect((panel.match(/fetchRuntimeHealth\(\{\s*force:\s*true\s*\}\)/g) || []).length,
      '面板里穿透缓存的健康读数不止一枚').toBe(1)
    const refresh = /async function refreshRuntimeHealth\(\{ force = false \} = \{\}\) \{[\s\S]*?\n\}/.exec(panel)
    expect(refresh, '找不到 refreshRuntimeHealth：穿透那一枚不在它身上').toBeTruthy()
    expect(refresh[0]).toMatch(/fetchRuntimeHealth\(\{ force: true \}\)/)
    const recheck = /async function recheckRuntimeHealth\(\) \{[\s\S]*?\n\}/.exec(panel)
    expect(recheck, '找不到 recheckRuntimeHealth').toBeTruthy()
    expect(recheck[0], '伸手那一条绕过 refreshRuntimeHealth 自己发：全站就又是两个发口').toMatch(
      /await refreshRuntimeHealth\(\{ force: true \}\)/)
  })

  it('甲3b 面板的在飞去重住在模块顶层（<script> 那一段），不是 <script setup> 那种一枚实例一份的私货', () => {
    const panel = panelSource()
    // 按标签取段，不按「文中出现过 <script setup> 五个字」取段：本文件自己的说明注释里就写着这两个名字。
    // 段首按行首标签取（模块顶层那一段就在文件第 1 行，前面没有换行可当锚点）。
    const at = pattern => {
      const hit = pattern.exec(panel)
      return hit ? hit.index : -1
    }
    const plainFrom = at(/^<script>$/m)
    const setupFrom = at(/^<script setup>$/m)
    const plainTo = panel.indexOf('\n</script>', plainFrom)
    const setupTo = panel.indexOf('\n</script>', setupFrom)
    expect([plainFrom, plainTo, setupFrom, setupTo], '两段 script 的形状读不出来').not.toContain(-1)
    const plain = panel.slice(plainFrom, plainTo)
    const setupBlock = panel.slice(setupFrom, setupTo)
    expect(plain, 'panelRuntimeRead 不在模块顶层那一段：<script setup> 里每枚实例一份，去重就是假的')
      .toMatch(/let panelRuntimeRead = null/)
    expect(setupBlock, '<script setup> 里又声明了一枚同名变量（把模块级那枚遮掉了）').not.toMatch(/let panelRuntimeRead/)
    expect(setupBlock).toMatch(/if \(panelRuntimeRead\) return panelRuntimeRead/)
  })

  it('甲4 挂载那一段既不带 force、也照旧先叫 refreshRuntimeHealth（在册那枚件钉的形状一条没退）', () => {
    const panel = panelSource()
    expect(panel).toMatch(/onMounted\(\(\) => \{\s*refreshRuntimeHealth\(\)/)
    const mount = /onMounted\(\(\) => \{[\s\S]*?\n\}\)/.exec(stripComments(panel))[0]
    expect(mount, '挂载那一段还带着 force：那就是全站第二发').not.toMatch(/force/)
  })

  it('甲5 壳层这一发一枚未动：本单写域不含 App.vue（读的是现成事实，不是自我声明）', () => {
    const shell = stripComments(appSource)
    expect((shell.match(/fetchRuntimeHealth\(/g) || []).length, 'App.vue 里那发被改动了').toBe(1)
    expect(shell).toMatch(/healthRead\.value = \{ tried: true, health: await fetchRuntimeHealth\(\) \}/)
    expect((shell.match(/\bsetInterval\b/g) || []).length, '壳层长出了轮询').toBe(0)
  })
})

/* -------------------------------------------------------- 乙 · 判据③ 端到端发数 */

describe('R458 乙 · 判据③：登录 → 进工作台 → 切遍每一屏 → 静置，全站 <= 1 发', () => {
  let shell = null
  let panel = null
  afterEach(() => { panel?.unmount(); shell?.unmount(); panel = null; shell = null })

  it('乙1 进工作台那一发真的打出去了（量具不空转的自证）', async () => {
    shell = await bootShell(DEGRADED)
    expect(shell.errors).toEqual([])
    expect(healthCount(), '壳层进工作台没打那一发：后面每一条「<= 1」都成了零个人的空账').toBe(1)
    expect(unref(shell.state.bannerShows), '降级读数没让横幅说话：这一发读到的东西没人接').toBe(true)
  })

  it('乙2 对话屏真挂载（面板 onMounted 真跑），一枚都不重发', async () => {
    shell = await bootShell(DEGRADED)
    await shell.goto('chat')
    panel = await mountPanel()
    expect(panel.errors, '面板挂载期抛错：这一条成了空转').toEqual([])
    expect(unref(panel.state.runtimeFaceList).map(face => face.kind), '面板没吃到壳层那份读数').toEqual(['embedding'])
    expect(healthCount(), '面板挂载又发了一发：两处读数点没收成一处').toBe(1)
  })

  it('乙3 切遍每一屏：每一屏都真挂一次面板，仍然一发', async () => {
    shell = await bootShell(DEGRADED)
    expect(screenRouteIds.length, '路由表没读到屏名清单：量具空转').toBeGreaterThan(3)
    for (const name of screenRouteIds) {
      await shell.goto(name)
      panel?.unmount()
      panel = await mountPanel(name)
      expect(panel.errors).toEqual([])
    }
    panel?.unmount()
    panel = null
    expect(healthCount(), '切屏把健康读数重打了一遍').toBe(1)
  })

  it('乙4 静置 1.5 秒不发第二发（假时钟推的，不是真等）', async () => {
    shell = await bootShell(DEGRADED)
    panel = await mountPanel()
    await vi.advanceTimersByTimeAsync(1500)
    await flush()
    expect(healthCount(), '静置之中又打了一发：它开始自己转了').toBe(1)
  })

  it('乙5 退出再登录吃的还是那份 60 秒缓存：累计仍然一发（判据③那一格的账）', async () => {
    shell = await bootShell(DEGRADED)
    panel = await mountPanel()
    panel.unmount()
    panel = null
    shell.state.doLogout()
    await flush()
    shell.state.checkAuth()
    await flush()
    expect(healthCount(), '同一台机器 60 秒内重新登录又打了一发').toBe(1)
  })

  it('乙6 员工伸手那一刻才是第 2 发：走的是按钮上挂着的那一枚处理函数', async () => {
    shell = await bootShell(READY)
    panel = await mountPanel()
    expect(healthCount()).toBe(1)
    await panel.state.recheckRuntimeHealth()
    await flush()
    expect(healthCount(), '伸手那一发没打出去：那是一枚假控件').toBe(2)
  })

  it('乙7 伸手之后静置不发第 3 发（它不是一张会自己转的脸）', async () => {
    shell = await bootShell(READY)
    panel = await mountPanel()
    await panel.state.recheckRuntimeHealth()
    await flush()
    await vi.advanceTimersByTimeAsync(30_000)
    await flush()
    expect(healthCount(), '伸手之后它自己转起来了').toBe(2)
  })
})

/* -------------------------------------------- 丙 · 判据① 缓存复用与在飞去重 */

describe('R458 丙 · 判据①：面板挂载复用壳层那发读数，不绕缓存', () => {
  let panel = null
  let second = null
  let shell = null
  afterEach(() => { panel?.unmount(); second?.unmount(); shell?.unmount(); panel = null; second = null; shell = null })

  it('丙1 壳层那一发落地之后，面板再挂载一枚都不发（「复用」二字的落地形状）', async () => {
    resetRuntimeHealthCache()
    installBackend(READY)
    installDomStubs(SESSION_SEED)
    await fetchRuntimeHealth()
    expect(healthCount(), '夹具自己没打到一发：这一条成了空转').toBe(1)
    panel = await mountPanel()
    expect(panel.errors).toEqual([])
    expect(healthCount(), '面板挂载又发了一发').toBe(1)
  })

  it('丙2 一发还在路上的时候，第二枚面板共用它，不另开一枪', async () => {
    resetRuntimeHealthCache()
    installDomStubs(SESSION_SEED)
    const gate = installBackend(READY, { hold: true })
    panel = await mountPanel()
    panel = await mountPanel()
    const afterFirst = healthCount()
    expect(afterFirst, '第一枚面板挂载没打出发：这一条成了空转').toBe(1)
    second = await mountPanel()
    expect(healthCount(), '同一份读数在路上时又补一发 = 柜台前第三个人').toBe(afterFirst)
    gate.release()
    await flush()
    expect(healthCount()).toBe(1)
    expect(unref(second.state.modelStateValue), '共用的那一发落地后没把读数交给第二枚面板').toBe('ready')
  })

  it('丙3 正向对照：把改前那种 force 穿透摆进同一把尺，它当场数出第 2 发', async () => {
    resetRuntimeHealthCache()
    installBackend(READY)
    installDomStubs(SESSION_SEED)
    await fetchRuntimeHealth()
    expect(healthCount()).toBe(1)
    const BypassTwin = {
      name: 'R458BypassTwin',
      setup() {
        const holder = reactive({ value: '' })
        return () => h('div', { 'data-testid': 'r458-bypass-twin' }, String(holder.value))
      },
    }
    const app = createApp(BypassTwin)
    app.config.warnHandler = () => {}
    app.provide(SSR_CONTEXT_KEY, {})
    app.mount(node('#root'))
    await flush()
    await fetchRuntimeHealth({ force: true })
    expect(healthCount(), '这把尺认不出一次 force 穿透：上面所有「发数」断言都是空转').toBe(2)
    app.unmount()
  })

  it('丙4 冷缓存下面板挂载确实会打出一发（丙1 那个「一」是收住的结果，不是这条路没跑）', async () => {
    resetRuntimeHealthCache()
    installBackend(READY)
    installDomStubs(SESSION_SEED)
    panel = await mountPanel()
    expect(healthCount(), '冷缓存下面板一枚都没发：说明这条路整个没跑起来').toBe(1)
  })

  it('丙5 唯一的残留窗口钉成读数（不写注释）：壳层那一发还在路上时面板就挂上来，全站打出第 2 发', async () => {
    // 这一条不是「达标」，是把今天真欠的那一格量出来：lib/health.js 只有「缓存里有没有」这一把尺，
    // 没有「这一发在不在路上」的对外读数（模块级的 in-flight 只在本单的三枚面板实例之间生效，跨不到
    // 壳层那一发），而闭掉它要在 lib/health.js 里加一枚 peek —— 那在本单写域之外（派工词硬禁）。
    // 形状：两发都是非穿透的同一次读数（谁都没绕缓存），代价 1 枚本地 GET，只在人手比网络快时出现。
    resetRuntimeHealthCache()
    shell = await bootShell(READY, { hold: true })
    expect(healthCount(), '壳层那一发没在路上：这一条成了空转').toBe(1)
    panel = await mountPanel()
    expect(healthCount(), '面板跟着补了一发之上的第二发（残留窗口今天就是 2，别抄成 1）').toBe(2)
    shell.gate.release()
    await flush()
    expect(healthCount(), '放行之后又多发了一发').toBe(2)
    expect(unref(panel.state.modelStateValue), '两发落地后没把读数交出来').toBe('ready')
  })
})

/* --------------------------------------------------------- 丁 · 不新造第二把尺 */

describe('R458 丁 · 面板不复算健康：借的还是 lib/health.js 那两把尺', () => {
  it('丁1 面板剥注释后一枚后端键名都不碰（problems / 只读名单 / 算力码都不在这里）', () => {
    const panel = stripComments(panelSource())
    for (const token of ['problems', 'inference_compute', 'read_only_protected', '_read_only',
      'embedding_model_missing', 'model_not_available', 'queue_unavailable']) {
      expect(panel, '面板自己开始读后端键名了：' + token).not.toContain(token)
    }
  })

  it('丁2 判定只有两把尺：modelState / runtimeFaces 各一处 computed，签名那一格也只用它们', () => {
    const panel = stripComments(panelSource())
    expect((panel.match(/modelState\(/g) || []).length, 'modelState 用点变了').toBe(2)
    expect((panel.match(/runtimeFaces\(/g) || []).length, 'runtimeFaces 用点变了').toBe(2)
    expect(panel).toMatch(/const runtimeFaceList = computed\(\(\) => runtimeFaces\(runtimeHealth\.value\)\)/)
    const signature = /function healthSignature\(read\) \{[\s\S]*?\n\}/.exec(panel)
    expect(signature, 'healthSignature 不见了：「再看一次」靠什么分 same / changed').toBeTruthy()
    expect(signature[0]).toMatch(/modelState\(read\)/)
    expect(signature[0]).toMatch(/runtimeFaces\(read\)/)
  })

  it('丁3 伸手那一条不立第三套状态：本单这三枚函数里没有轮询，timer 只有一枚且成对清理', () => {
    const panel = stripComments(panelSource())
    // 面板里那枚在册 setInterval 是排队轮询（queueWatches），与本单无关，也不许被顺手改；
    // 本件要钉的是【健康读数这一族】三枚函数体内一枚都不许长出轮询。
    const healthFamily = /function sharedRuntimeHealth\(\) \{[\s\S]*?\n\}/.exec(panel)[0]
      + /async function refreshRuntimeHealth[\s\S]*?\n\}/.exec(panel)[0]
      + /async function recheckRuntimeHealth\(\) \{[\s\S]*?\n\}/.exec(panel)[0]
    expect(healthFamily.match(/\bsetInterval\b/g), '健康读数这一族长出了轮询').toBe(null)
    expect((panel.match(/\bsetInterval\b/g) || []).length, '面板整体 setInterval 枚数变了（在册那枚是排队轮询）').toBe(1)
    expect((panel.match(/setTimeout\(retireRecheckFace/g) || []).length).toBe(1)
    expect((panel.match(/clearTimeout\(recheckFaceTimer\)/g) || []).length, '清 timer 只有一处，摘掉它卸载就漏').toBe(1)
    // 四枚 = 定义一枚 + 三处调用（伸手前、退场时、卸载时），少一处就是漏清。
    expect((panel.match(/clearRecheckFaceTimer\(\)/g) || []).length, '收口这一枚函数的定义与调用点枚数变了').toBe(4)
    expect(/onUnmounted\(\(\) => \{[\s\S]*?clearRecheckFaceTimer\(\)[\s\S]*?\n\}\)/.test(panel),
      '卸载没把这枚 timer 收掉').toBe(true)
  })
})
