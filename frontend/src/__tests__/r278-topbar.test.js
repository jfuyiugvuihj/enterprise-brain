/**
 * R278 · G16 · 顶栏无死控件（块 F 第一片，判据①②③⑤）
 *
 * 病灶（改前取证，行号取本单基点 951909b 的 frontend/src/App.vue）：
 *   :393 一枚 aria-label="搜索" 的 button 没有 @click；
 *   :396 一枚 aria-label="通知" class="bell" 的 button 没有 @click；
 *   :401 退出那枚只有内容「⌄」，没有可及名称。
 * 计划书 §11 那句「顶栏无死控件；退出按钮有可及名称」（docs/frontend-plan-2026-09-14.md:592）
 * 今天不成立。本件按判据收口：两枚假控件【摘掉】，退出补真名。
 *
 * 为什么是摘而不是接（这一段是本件的立场，不是含糊话）：
 *   ① 搜索：全站没有一枚全局检索端点。app/api 的 GET/POST 名单里只有 POST /retrieval/debug
 *      （管理侧可观测工具）与各屏自己的列表，判据明写「不许接半截、不许新起端点、不许改后端」。
 *   ② 通知：今天没有一句诚实的「条数」可摆。GET /hitl/pending 的 count 是一页过滤后的长度
 *      （契约 docs/api/contract-v1.md 的 HITL Pending Listing 一节明写不得当总数用），
 *      GET /dashboard/summary 那一格不向图复核、自己写着「可能高估」，而徽标要在人点开之前
 *      就有数——只能每屏挂载多发一次请求去猜。所以壳层不摆数，也不自己第二本账。
 *
 * 三条腿（沿用本仓口径：node 环境，无 jsdom / @vue/test-utils）：
 *   ① 真产物 = 跑真 App.vue 的 setup() 并以 App.ssrRender 出真 HTML，断言屏上那枚按钮叫什么；
 *   ② 真逻辑 = 直接调 setup() 交回的 logoutLabel 与 doLogout，不 grep 句子冒充行为；
 *   ③ 接线形状 = 挂一次真壳层，逐枚读【渲染出的】 <button> 节点，每枚都必须追到 onClick /
 *      type="submit" / disabled 之一（判据⑤要的「逐枚对照表」就是这张，摘掉任一枚 @click 当场红）。
 *      R307 第二棒改口：这条原来扫的是 App.vue 源码里的 <button 开标签。为什么换、四条各自
 *      原来盯的是什么，逐条写在下面量具那段注释里，没有一条换松。
 *
 * 反证（本单实跑，跑完还原）：
 *   摘掉退出的可及名称 → 丙组三条一起红；
 *   把「搜索」那枚原样摆回去 → 甲组（逐枚对照）与乙组（顶栏只剩一枚按钮）同时红；
 *   给顶栏加一句「N 条待办」式的总数口径 → 乙组那条红（本件没有丁组，原文写错了组名，顺手改对）。
 *
 * R307 第二棒（2026-09-26，App.vue 八枚接 UiButton）实跑反证，跑完按字节还原并复验 sha256：
 *   摘掉顶栏退出的 @click → 甲2（逐枚对照）与乙1（那一枚按不动）一起红（W6 复跑一遍，仍 3 红）；
 *   把 logout 的 ⌄ 换成别的字 → 丙组那两条画相断言红；
 *   把甲2 的「三者之一」改松成「有 class 就算活着」→ 摘掉 @click 之后仍然红（改口不降要求那把刀）。
 * 另外本件那三条「屏上是什么」的断言，除了挂载腿还另有一遍真浏览器对照：改前那份打包件
 * （App.vue 取 1dda05e）与本树那份各起一次 Chromium（1280×860，route 拦截喂 dist，零服务），
 * 逐枚读 getComputedStyle / getBoundingClientRect 并按元素盒裁图比像素：24/27 格 0 差，
 * 唯一有真差的一格是退出那枚的 hover 文字色（账记在 components/__tests__/r307b 戊组最后一条）。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, createSSRApp, defineComponent, getCurrentInstance, nextTick, reactive } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { routeLocationKey, routerKey } from 'vue-router'

// 顶栏不碰鉴权以外的东西：整件用例不发任何网络请求（真起了请求就是真新增外部调用）。
vi.mock('../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { ...actual.http, get: vi.fn(), post: vi.fn() } }
})

import App from '../App.vue'
import { navigation } from '../router'
import { UiButton } from '../components/ui'

const source = readFileSync(new URL('../App.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const TOKEN_KEY = 'eb_token'
const USER_KEY = 'eb_user'
const ROLE_KEY = 'eb_role'

/**
 * 注释里的「按钮」二字不是控件，注释里提到的端点名也不是调用点：量具一律先在去掉注释的文本
 * 上跑（模板注释 + JS 块注释 + 整行注释），否则本件自己写的说明会把钉子钉红。
 */
const withoutComments = (text) => text
  .replace(/<!--[\s\S]*?-->/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/^[ \t]*\/\/.*$/gm, '')
const code = withoutComments(source)

/**
 * ==================== R307 第二棒改口（2026-09-26）：量具从「源码正则」换成「渲染产物」 ====================
 *
 * 原来这把刀读的是 App.vue 的【源码文本】：拿 /<button\b/g 数开标签，再在属性串里找
 * @click / type="submit" / disabled。它盯的是「源码怎么写的」，不是「屏上是什么」。
 * 八枚裸 <button> 接进 ./components/ui 的 UiButton 之后，App.vue 源码里的 <button
 * 开标签归零，那四处就一起去砍一件已经不存在的事（而屏上那八枚控件一枚都没少，仍然是真 button）：
 *   :149 expected 7 to be greater than or equal to 8  —— 数的是整份 App.vue 的开标签；
 *   :169 expected [] to have a length of 1 but got +0 —— 数的是顶栏那一段的开标签；
 *   :193 expected 'class="workspace-tools" data-v-…' to match /class="logout-link"[^>]*>⌄<\/button>/
 *        —— 接原语之后 logout-link 是类名列表里的一项、⌄ 被包进插槽那一层，字面形状必然对不上；
 *   :215 AssertionError: 顶栏那枚退出没渲染出来: expected '' to be truthy
 *        —— 同一条字面正则找不到 <button class="logout-link"，于是「退出没渲染出来」自己把自己判红。
 *
 * 四条的【要求】一条不减，只换绑法，逐条交代：
 *   :149 原意「量具不是空的：侧栏那几项与顶栏那一枚控件都在」。现在挂一次真壳层、数屏上真的
 *        <button>，下限不再手挑一个数字，而是 navigation.length + 1 —— 侧栏每一项一枚，
 *        加顶栏那一枚退出。谁把路由表掏空、把控件删掉，或者把顶栏数出第二枚，这条一样红。
 *   :152 原意「屏上没有一枚按了没反应的按钮」。原来读属性串里有没有 @click 三个字；现在直接读
 *        那一枚渲染出的 button 节点挂没挂 onClick（type="submit" 那枚走表单提交，显式 disabled
 *        那枚按不动）。「写着 @click」与「真的挂着 onClick」是同一件事的两种画法，后者还顺手挡掉
 *        「串里写着 @click 但接的是 undefined」这一种假绿 —— 比原来更严，不是更松。
 *   :169 原意「顶栏只剩一枚控件，而且它就是退出」。现在从渲染出的 workspace-tools 往上认祖先，
 *        数它下面真的 <button>：恰好一枚、类名里仍有 logout-link、可及名称仍是退出那一句，
 *        并且真按一次 —— 会话被清、屏切回登录页。原来那三条子断言一条没少，只是
 *        「@click="doLogout"」从字符串比对换成了「按下之后 doLogout 真的发生」。
 *   :193 与 :215 原意「屏上画的就是那一个 ⌄，退出这一格没换成别的字形、也没被谁顶掉」。
 *        现在按类名找到那一枚 button 再读它的可见文本：不再要求 class 属性正好等于 logout-link
 *        （接原语之后那是类名列表的一项），也不再要求 ⌄ 紧贴着 </button>。
 *        找得到这一条比原来更硬：原来的 logoutOf 找不到时返回 ''，只让 :215 那枚 truthy 红；
 *        现在找不到当场点名是哪一枚类名。
 *
 * 为什么这里宁可自己起一棵真组件树：桩件不算数。上一棒已经证过一次 —— 夹具没注册 UiButton 时
 * 模板会退化成解析不到的桩，一跑就绿，绿的却是桩。所以本件的挂载腿注册的是产品真身那份
 * UiButton（连同它自己的模板与档位类名），少一枚就当场红。
 */

/** 从渲染出的 HTML 里逐枚抠 <button>：属性串、类名列表、可见文本。注释与标签壳都不算内容。 */
function renderedButtons(html) {
  const items = []
  const re = /<button\b/g
  let match = null
  while ((match = re.exec(html))) {
    const open = match.index
    let i = open + '<button'.length
    let quote = null
    while (i < html.length) {
      const ch = html[i]
      if (quote) { if (ch === quote) quote = null } else if (ch === '"' || ch === "'") quote = ch
      else if (ch === '>') break
      i += 1
    }
    const close = html.indexOf('</button>', i)
    const attrs = html.slice(open + '<button'.length, i).replace(/\s+/g, ' ').trim()
    items.push({
      attrs,
      classes: ' ' + ((/class="([^"]*)"/.exec(attrs) || [, ''])[1]).trim() + ' ',
      testid: (/data-testid="([^"]*)"/.exec(attrs) || [, ''])[1],
      text: (close < 0 ? '' : html.slice(i + 1, close)).replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim(),
    })
  }
  return items
}
const hasClass = (item, name) => item.classes.includes(' ' + name + ' ')
const namedButtons = (items, name) => items.filter(item => hasClass(item, name))

// ==================== 挂载腿：无 DOM 的真补丁周期（手法与 r197 / r307 同一套） ====================

const SSR_CONTEXT_KEY = Symbol.for('v-scx')
const hasOwn = (obj, key) => Object.prototype.hasOwnProperty.call(obj || {}, key)
// 壳层的模板里有 v-model（登录那两个输入框与「记住我」），运行时编译器把 runtime-dom
// 那份真指令带了进来，它要在节点上挂 input/change 监听 —— 内存节点给一对空处理器即可，
// 本件不测输入框，测的是那八枚 button。
const vnodeNode = tag => ({
  tag, props: {}, children: [], parent: null, text: '',
  addEventListener() {}, removeEventListener() {}, hasAttribute: () => false, getRootNode: () => ({}),
})
const parentOf = node => node.parent || null

function detach(node) {
  const siblings = parentOf(node) ? parentOf(node).children : null
  const at = siblings ? siblings.indexOf(node) : -1
  if (at >= 0) siblings.splice(at, 1)
  node.parent = null
}

const nodeOps = {
  createElement: tag => vnodeNode(tag),
  createText: text => Object.assign(vnodeNode('#text'), { text }),
  createComment: text => Object.assign(vnodeNode('#comment'), { text }),
  setText: (node, text) => { node.text = text },
  setElementText: (el, text) => { el.children.length = 0; el.text = text },
  parentNode: node => parentOf(node),
  nextSibling(node) {
    const siblings = parentOf(node) ? parentOf(node).children : null
    if (!siblings) return null
    return siblings[siblings.indexOf(node) + 1] || null
  },
  insert(node, parent, anchor) {
    detach(node)
    const at = anchor ? parent.children.indexOf(anchor) : -1
    if (at < 0) parent.children.push(node)
    else parent.children.splice(at, 0, node)
    node.parent = parent
  },
  remove: node => detach(node),
  patchProp: (el, key, prev, next) => {
    if (next === null || next === undefined) delete el.props[key]
    else el.props[key] = next
  },
  cloneNode: node => Object.assign(vnodeNode(node.tag), { props: { ...node.props }, text: node.text }),
  insertStaticContent(content, parent, anchor) {
    const node = Object.assign(vnodeNode('#static'), { text: content })
    nodeOps.insert(node, parent, anchor)
    return [node, node]
  },
  querySelector: () => null,
  setScopeId: (el, id) => { el.props[id] = '' },
}

const { createApp } = createRenderer(nodeOps)

/** 渲染期读值的作用域：只认真绑定与 props；名单以外（含闭包里的 _Vue）一律答 false。 */
function renderScope(instance) {
  const empty = {}
  const { setupState, props } = instance
  const names = new Set([...Object.keys(setupState || {}), ...Object.keys(props || {})])
  const PUBLIC_KEYS = /^\$(slots|attrs|props|el|data|setupState|emit|options|refs|root|parent|nextTick)$/
  return new Proxy(empty, {
    has: (_target, key) => typeof key === 'string' && (names.has(key) || PUBLIC_KEYS.test(key)),
    get: (_target, key) => {
      if (typeof key !== 'string') return undefined
      if (setupState && hasOwn(setupState, key)) return setupState[key]
      if (props && hasOwn(props, key)) return props[key]
      return instance.proxy[key]
    },
  })
}

/**
 * node 环境里 vite 把 SFC 编成【只有 ssrRender】的产物，客户端挂载缺一枚 render：
 * 这里把产品自己那份模板原文过一遍 vue 的运行时编译器补上。setup / props / 模板全用真身，
 * 换掉的只有「元素怎么落地」那一层。编译器不在位当场报错，绝不静默退成桩件。
 */
function clientify(label, rel, sfc, extraComponents) {
  if (typeof compile !== 'function') {
    throw new Error('R278 夹具：解析到的 vue 构建里没有运行时编译器（compile），请人工核对，不要静默跳过')
  }
  const file = readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
  const template = /<template>([\s\S]*)<\/template>/.exec(file)
  if (!template) throw new Error('R278 夹具：' + rel + ' 里取不到 <template>')
  const compiled = compile(template[1])
  return {
    __name: label,
    props: sfc.props,
    emits: sfc.emits,
    components: { ...extraComponents },
    setup: sfc.setup,
    render(_ctx, _cache) {
      return compiled(renderScope(getCurrentInstance()), _cache)
    },
  }
}

/** 原语走真身：档位类名（ui-button--ghost 那一套）必须是它自己算出来的，不是夹具捏的。 */
const ClientUiButton = clientify('R278ClientUiButton', '../components/ui/UiButton.vue', UiButton)
/** 壳层的客户端版本：面板位（RouterView / KeepAlive）换成空桩 —— 本件看的是壳层，不是任何一屏。 */
const ClientApp = clientify('R278ClientApp', '../App.vue', App, {
  UiButton: ClientUiButton,
  RouterView: { __name: 'R278RouterViewStub', render: () => null },
  KeepAlive: { __name: 'R278KeepAliveStub', render: () => null },
  Transition: {
    __name: 'R278TransitionStub',
    render() {
      const [first] = this.$slots.default ? this.$slots.default() : []
      return first || null
    },
  },
})

const collectClass = node => ' ' + String(node.props.class || '').replace(/\s+/g, ' ').trim() + ' '
const hasNodeClass = (node, name) => collectClass(node).includes(' ' + name + ' ')

function walk(node, out = []) {
  out.push(node)
  ;(node.children || []).forEach(child => walk(child, out))
  return out
}

/** 屏上真的 button 节点（tag 就是 button，不是解析不到的桩）。 */
const buttonNodes = root => walk(root).filter(node => node.tag === 'button')
/** 某一枚容器节点【直接子树里】的 button：向上认祖先，别把整屏的控件算进这一段。 */
function buttonsUnder(root, className) {
  const box = walk(root).find(node => node.tag !== 'button' && hasNodeClass(node, className))
  expect(box, '挂载产物里找不到容器节点 ' + className).toBeTruthy()
  return buttonNodes(box)
}
/**
 * 挂一次真壳层：跑真 setup()（含 onMounted 里那一次 checkAuth），登录门由 seed 决定。
 * 返回渲染出的虚拟 DOM 根、屏上每一枚 button、以及 setup() 交回的那本绑定。
 */
async function mountShell(seed = {}, poke) {
  const store = installDomStubs(seed)
  const loggedIn = store.has(TOKEN_KEY)
  const route = reactive({
    name: loggedIn ? 'overview' : '', path: loggedIn ? '/overview' : '/', query: {}, params: {},
    meta: { title: '屏名', screen: true }, fullPath: loggedIn ? '/overview' : '/', hash: '', matched: [],
  })
  const replaced = []
  const root = vnodeNode('#root')
  const app = createApp(ClientApp)
  app.provide(SSR_CONTEXT_KEY, {})
  app.provide(routeLocationKey, route)
  app.provide(routerKey, {
    push() {},
    replace: to => replaced.push(to),
    currentRoute: { value: route },
  })
  app.mount(root)
  await nextTick()
  await nextTick()
  return { root, store, route, replaced, buttons: () => buttonNodes(root), poke, app }
}
/** 内存替身：node 环境没有 window / localStorage（手法同 r169 / r171）。 */
function installDomStubs(seed = {}) {
  const store = new Map(Object.entries(seed))
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
  return store
}

/**
 * 真渲染那一腿：跑真 setup() 并 checkAuth() 进工作台，再拿 App 自己的 ssrRender 出 HTML。
 * 面板位（RouterView）换成空桩——本件要看的是顶栏，不是任何一屏。
 */
async function renderWorkspace(seed) {
  const store = installDomStubs(seed)
  const route = reactive({
    name: 'overview', path: '/overview', query: {}, params: {},
    meta: { title: '屏名', screen: true }, fullPath: '/overview', hash: '', matched: [],
  })
  let bindings = null
  const Host = defineComponent({
    name: 'R278TopbarHost',
    ssrRender: App.ssrRender,
    setup(props, ctx) {
      const given = App.setup({}, ctx)
      given.checkAuth()
      bindings = given
      return given
    },
  })
  const app = createSSRApp(Host)
  app.provide(routeLocationKey, route)
  app.provide(routerKey, { push() {}, replace() {}, currentRoute: { value: route } })
  app.component('RouterView', { ssrRender: () => {} })
  const html = await renderToString(app)
  const from = html.indexOf('class="workspace-tools"')
  const topbar = from < 0 ? '' : html.slice(from, html.indexOf('</header>', from))
  return { html, topbar, bindings, store }
}

describe('R278 判据⑤ · 逐枚对照：App.vue 里没有一枚按了没反应的按钮', () => {
  it('挂载量具本身不是空的：侧栏每一项 + 顶栏那一枚退出，屏上都是真的 <button>', async () => {
    const { root, buttons } = await mountShell({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'staff' })
    const onScreen = buttons()
    // 下限取 navigation.length + 1，不手挑数字：这一屏该有侧栏每一项一枚，再加顶栏那枚退出。
    expect(onScreen.length, '屏上真的 button 比路由表还少，量具或控件坏了一枚').toBeGreaterThanOrEqual(navigation.length + 1)
    // 量具不误伤：非 button 的容器节点一枚都不许算进来（顶栏的 identity 是 span）。
    expect(walk(root).filter(node => node.tag === 'span' && hasNodeClass(node, 'identity')).length, 'identity 那一段该是 span').toBe(1)
    expect(onScreen.every(node => node.tag === 'button'), '屏上每一枚都必须是真 button').toBe(true)
  })

  it('每一枚都追得到 @click / type="submit" / 显式 disabled 三者之一（读渲染节点，不读源码串）', async () => {
    const workspace = await mountShell({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'staff' })
    const login = await mountShell({})
    const onScreen = [...workspace.buttons(), ...login.buttons()]
    // 空集就是假绿：两屏都得真数到控件（工作台 navigation 每项一枚 + 顶栏一枚，登录屏至少三枚），
    // 下面这条 filter 才有「逐枚」的意义。
    expect(onScreen.length, '两屏合计渲染出的 button 少到无法逐枚对照').toBeGreaterThanOrEqual(navigation.length + 4)
    const dead = onScreen.filter(node => !(typeof node.props.onClick === 'function' || node.props.type === 'submit' || node.props.disabled === true))
    expect(dead.map(node => node.tag + ' ' + String(node.props.class || '')), '这些按钮没有任何可追的行为').toEqual([])
  })

  it('改造前那两枚假控件（搜索、通知）不在源码里了', () => {
    expect(code).not.toMatch(/aria-label="搜索"/)
    expect(code).not.toMatch(/aria-label="通知"/)
    expect(code).not.toMatch(/class="bell"/)
  })
})

describe('R278 判据①② · 顶栏这一行的形状', () => {
  it('顶栏只剩一枚按钮，而且它就是退出（挂到真节点上，再真按一次）', async () => {
    const { root, store, buttons } = await mountShell({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'staff' })
    const tools = buttonsUnder(root, 'workspace-tools')
    expect(tools, '顶栏那一段不是恰好一枚按钮').toHaveLength(1)
    expect(hasNodeClass(tools[0], 'logout-link'), '顶栏那一枚不是退出').toBe(true)
    expect(String(tools[0].props['aria-label']), '顶栏那一枚念不出「退出登录」').toContain('退出登录')
    expect(typeof tools[0].props.onClick, '顶栏那一枚按不动（原意就是 @click="doLogout"）').toBe('function')
    // 「@click="doLogout"」的等价物：真按一次 —— 令牌从 localStorage 走掉，顶栏那一枚也跟着下屏。
    tools[0].props.onClick({})
    await nextTick()
    await nextTick()
    expect(store.has(TOKEN_KEY), '按了退出，令牌还留在本地').toBe(false)
    expect(buttons().some(node => hasNodeClass(node, 'logout-link')), '按了退出，顶栏那枚还钉在屏上').toBe(false)
    expect(walk(root).some(node => hasNodeClass(node, 'login-v2')), '按了退回去的得是登录页').toBe(true)
  })

  it('壳层不自己读挂起账本，也不摆任何「N 条」总数口径', async () => {
    // 去掉注释之后仍然一个字都不提那两条端点：顶栏没有第二本账，也没有为它新起的请求
    expect(code).not.toMatch(/hitl/i)
    expect(code).not.toMatch(/\/pending/)
    expect(code).not.toMatch(/dashboard/)
    expect(code).not.toMatch(/http\.get\(|authedFetch\(/)
    // 「N 条」这种总数口径一枚都不许出现在顶栏那一段里
    const { topbar } = await renderWorkspace({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'staff' })
    expect(topbar).not.toMatch(/\d+\s*(?:条|个|枚)/)
    expect(topbar).not.toMatch(/(?:待办|待审批|等你拍板)/)
  })
})

describe('R278 判据③ · 退出的可及名称（真渲染，不是 grep 句子）', () => {
  it('有账号时念得出「退出登录（当前账号 …）」，鼠标悬停也看得见同一句', async () => {
    const { topbar } = await renderWorkspace({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'staff' })
    expect(topbar).toContain('aria-label="退出登录（当前账号 baiye）"')
    expect(topbar).toContain('title="退出登录（当前账号 baiye）"')
    // 画相不变：屏上仍是那一个记号，本件只补名称，不改行为也不换字形。
    // 改口（R307 第二棒）：原来这条比的是 class 属性正好等于 logout-link、⌄ 紧贴 </button>；
    // 接原语之后 logout-link 是类名列表的一项、⌄ 被包在插槽那一层里，所以换成「按类名找到
    // 那一枚 button，再读它真正画出来的可见文本」—— 要看的还是那一个记号在不在屏上。
    const logout = namedButtons(renderedButtons(topbar), 'logout-link')
    expect(logout, '顶栏那枚退出没渲染出来（按类名找也找不到）').toHaveLength(1)
    expect(logout[0].text, '退出那一格画的还是不是 ⌄').toBe('⌄')
  })

  it('账号名取不到时只说「退出登录」，不许留一对空括号冒充有名字', async () => {
    const { topbar } = await renderWorkspace({ [TOKEN_KEY]: 'jwt-live' })
    expect(topbar).toContain('aria-label="退出登录"')
    expect(topbar).not.toContain('当前账号 ）')
    expect(topbar).not.toMatch(/aria-label="[^"]*\(\)/)
  })

  it('同一句名称是派生的：logoutLabel 跟着 username 走，不在模板里抄第二份', async () => {
    const { bindings, topbar } = await renderWorkspace({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'zhangsan', [ROLE_KEY]: 'admin' })
    expect(bindings.logoutLabel.value).toBe('退出登录（当前账号 zhangsan）')
    expect(topbar).toContain('aria-label="退出登录（当前账号 zhangsan）"')
    bindings.username.value = 'lisi'
    expect(bindings.logoutLabel.value).toBe('退出登录（当前账号 lisi）')
  })

  it('管理员与员工念出来是同一句：角色不在这枚名称里充数', async () => {
    // 改口（R307 第二棒）：原来那条正则把整段 <button …>…</button> 抠出来逐字比，找不到时
    // 返回 '' 只让 truthy 那一枚红。现在按类名找：找不到当场点名，比得更硬。
    // 比较对象从「整段标签」换成「属性串 + 可见文本」两格 —— 接原语后中间多了一层插槽
    // span，逐字比整段会平白比出那两层壳；名称、类名、type、title 与那一个记号该一样的照样一样。
    const logoutOf = html => {
      const hits = namedButtons(renderedButtons(html), 'logout-link')
      expect(hits, '顶栏那枚退出没渲染出来（按类名找也找不到）').toHaveLength(1)
      return hits[0]
    }
    const staff = await renderWorkspace({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'staff' })
    const admin = await renderWorkspace({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'admin' })
    const asStaff = logoutOf(staff.topbar)
    const asAdmin = logoutOf(admin.topbar)
    expect(asStaff.attrs, '员工与管理员那枚退出不一样').toBe(asAdmin.attrs)
    expect(asStaff.text, '员工与管理员那枚退出的画相不一样').toBe(asAdmin.text)
    expect(asAdmin.attrs).toContain('aria-label="退出登录（当前账号 baiye）"')
  })
})
