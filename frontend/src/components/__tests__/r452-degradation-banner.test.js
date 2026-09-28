/**
 * R452 · G07 残格「全站降级横幅」的反证钉（判据①②③④⑤⑥ · 全部走 SSR 真 HTML）
 *
 * 病灶（总控现读 @7532652）：逐族降级那张脸早就长出并且在册 —— lib/health.js:214 computeFace、
 * :241 runtimeFaces、:65-66 读只读名单、:284 degraded；可消费点只有对话那一屏（ChatPanel.vue:242
 * import、:778 runtimeFaceList → 屏上 :1830-1832）。App.vue 一侧 runtimeFaces 零命中 ⇒ 员工切到
 * 总览 / 喂料 / 告警 / 审批任何一屏，「这台机器没配检索模型」「推理没走加速设备」「某几格跑在只读
 * 保护下」一个字都看不见：答案质量崩了没有一句解释。本单把它升成登录后整站常驻的一枚横幅。
 *
 * 取证口径按缺口清单 §10.3：判「上屏」一律从 renderToString 的真产物里抠，不拿裸 rg 命中数当判据。
 *
 * 六组断言，缺一组都不算收口：
 *   甲 三态分开（判据①）：正常 / 降级（权重那一格单独一档）/ 读数取不到，三张脸各自在位、两两不
 *      冒充；正常态整段不渲染 ⇒ 屏上连类名都数不到一枚（判据①那句「不许留占位高度」）。
 *   乙 一发都不许多打（判据②）：进工作台那一发是唯一读取点；切遍每一屏不重发；静置 1.5 秒不重发；
 *      再登录一次吃的是 lib/health.js 那份 60 秒缓存 —— 仍然一发；壳层没有 setInterval、读取点恰
 *      一枚；横幅不往屏上多长一枚控件。
 *   丙 逐族出话（判据⑥第三把刀的形状）：face 节点枚数 == runtimeFaces() 当场推导的那一枚数（不手抄），
 *      每一族的族名与那一句「下一步」逐字在屏上 —— 把几族并成一句泛话，当场红。
 *   丁 屏上零技术注脚（判据③，手法照 r267）：源码路径 / HTTP 方法与路由 / /api/ / 后端裸码名，
 *      在可见正文与整段渲染产物里逐条 0 命中；取不到读数那一张脸同样扫一遍。
 *   戊 不新造第二把尺（工单那句「用已有的那把脸」）：App.vue 剥掉注释之后不复算 problems、不碰后端
 *      那几枚键名，对 lib/health.js 只留一枚 import，请的既有工具一枚不多一枚不少。
 *   己 零外部请求（判据⑤第二道天花板）：App.vue 与 theme.css 里 googleapis / gstatic / unpkg /
 *      cdnjs / jsdelivr 一枚都不许有；非 SVG 命名空间的 http 字面量也不许多出来一枚。
 *
 * 三把反证刀都在 App.vue 上真摘一次守卫、只跑本件（红数见回执，不写「应该会红」）：
 *   刀一 摘掉横幅（模板那一段不再渲染）；
 *   刀二 把「读数取不到」画成正常（unknown 那一档当 ready 处理）；
 *   刀三 把逐族脸并成一句泛话（只留标题，不画 face 列表）。
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it, vi } from 'vitest'
import { createSSRApp, reactive } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { routeLocationKey, routerKey } from 'vue-router'

// 一发网络请求都不许真起：健康读数由本件逐种形状喂进去（手法与 r267 / r307b 同一套）。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { ...actual.http, get: vi.fn(), post: vi.fn(), delete: vi.fn() } }
})

import App from '../../App.vue'
import { http, ROLE_KEY, TOKEN_KEY, USER_KEY } from '../../lib/http'
import { fetchRuntimeHealth, MODEL_STATE_TEXT, resetRuntimeHealthCache, runtimeFaces } from '../../lib/health.js'
import { navigation, screenRouteIds } from '../../router'
import { countNativeButtons, stripComments } from './r288-native-button-scan.js'

const HEALTH_PATH = '/health/details'
const SRC_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const readSrc = rel => readFileSync(join(SRC_ROOT, rel), 'utf8').replace(/\r\n/g, '\n')
const appSource = readSrc('App.vue')
const appCode = stripComments(appSource)
const themeSource = readSrc(join('assets', 'theme.css'))

/* ---------------------------------------------------------------- 读数样本 */

const READY = { status: 'ok', problems: [], model: { name: 'qwen3:4b', source: 'ollama' }, storage: {} }
const DOWN = { status: 'down', problems: ['model_not_available'], model: { name: '', source: '' }, storage: {} }
const TWO_FAMILIES = {
  status: 'degraded',
  problems: ['embedding_model_missing', 'queue_unavailable'],
  model: { name: 'qwen3:4b', source: 'ollama' },
  storage: {},
}
// 六族一起坏：检索模型 / 队列 / 账号库 / 只读 / 依赖 / 没走加速。逐族出话那一组用的就是这份。
const WIDE = {
  status: 'degraded',
  problems: [
    'embedding_model_missing',
    'queue_unavailable',
    'users_store_not_persistent',
    'knowledge_graph_read_only',
    'postgres_unavailable',
  ],
  model: {
    name: 'qwen3:4b', source: 'ollama', inference_compute: 'cpu',
    inference_compute_detail: 'torch 落在 CPU', inference_compute_error_code: 'cuda_not_available',
    inference_compute_age_seconds: 126,
  },
  storage: { read_only_protected: ['knowledge_graph'] },
}

/* ------------------------------------------------------------------ 挂壳层 */

/** node 环境没有 window / localStorage：内存替身（手法与 r169 / r278 / r307b 同一套）。 */
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

const tick = () => new Promise(resolve => setTimeout(resolve, 0))
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))

function wrap(app, route) {
  app.provide(routeLocationKey, route)
  app.provide(routerKey, { push() {}, replace() {}, currentRoute: { value: route } })
  app.component('RouterView', { ssrRender: () => {} })
  return app
}

/**
 * 起一次真壳层：跑真 App.setup()，并由 checkAuth() 进工作台 —— 横幅那一发读取就在这里发生。
 * outcome：value 直接给读数 / fail 读不到（服务不应答）/ hold 那一发还压着没回来（settle 放行）。
 * render() 再渲一次同一份界面态：SSR 不跑 onMounted，读数落没落地全由这里自己推。
 */
async function boot(health, outcome = 'value') {
  resetRuntimeHealthCache()
  http.get.mockReset()
  const paths = []
  let release = null
  const held = new Promise(resolve => { release = resolve })
  http.get.mockImplementation(async (url) => {
    paths.push(url)
    if (outcome === 'fail') throw new Error('这台机器上的服务此刻不应答')
    if (outcome === 'hold') await held
    return { data: health }
  })
  const store = installDomStubs({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'staff' })
  const route = reactive({
    name: 'overview', path: '/overview', query: {}, params: {},
    meta: { title: '总览', screen: true }, fullPath: '/overview', hash: '', matched: [],
  })
  let bindings = null
  const Host = {
    name: 'R452BannerProbe',
    setup(props, ctx) {
      bindings = App.setup({}, ctx)
      bindings.checkAuth()
      return () => null
    },
  }
  await renderToString(wrap(createSSRApp(Host), route))
  const settle = async () => {
    if (outcome === 'hold') release(health)
    for (let round = 0; round < 3; round += 1) await Promise.resolve()
    await tick()
  }
  const render = async () => renderToString(wrap(createSSRApp({ ...App, setup: () => bindings }), route))
  return { bindings, route, render, settle, paths, store }
}

const visibleText = html => html
  .replace(/<!--[\s\S]*?-->/g, ' ')
  .replace(/<[^>]+>/g, ' ')
  .replace(/\s+/g, ' ')
  .trim()

/** 横幅在不在屏上：拿真产物里的 data-testid 说话，不看源码串。 */
const hasBanner = html => html.includes('data-testid="degradation-banner"')
const faceNodes = html => (html.match(/data-testid="degradation-banner-face"/g) || []).length

/** 从真产物里抠出横幅那一段：从它自己那枚 testid 起，到面板位之前止（前面的模板注释不进这一段）。 */
const bannerRegion = (html) => {
  const from = html.indexOf('data-testid="degradation-banner"')
  if (from < 0) return ''
  const to = html.indexOf('data-testid="panel-slot"', from)
  return html.slice(from, to < 0 ? html.length : to)
}
/* -------------------------------------------------------------------- 甲 */

describe('R452 甲 · 三态分开：正常 / 降级 / 读数取不到（判据①）', () => {
  it('正常态：横幅一枚字都不画，也不留占位 —— 屏上连 runtime-banner 这个类名都数不到一枚', async () => {
    const shell = await boot(READY)
    await shell.settle()
    const html = await shell.render()
    expect(html.includes('runtime-banner'), '正常态还留着横幅的壳（哪怕是空壳）').toBe(false)
    expect(shell.bindings.bannerShows.value, '正常态 bannerShows 就该是假').toBe(false)
    expect(shell.paths.filter(path => path === HEALTH_PATH), '正常态也多打了一发').toHaveLength(1)
  })

  it('降级态：横幅在位，顶句就是那把尺的 modelStatusText，降级那一档自己写在类名上', async () => {
    const shell = await boot(TWO_FAMILIES)
    await shell.settle()
    const html = await shell.render()
    expect(hasBanner(html), '降级态没把横幅画出来（刀一那个形状）').toBe(true)
    expect(/class="[^"]*runtime-banner--degraded[^"]*"/.test(html), '降级那一档没自成一张脸').toBe(true)
    expect(visibleText(html)).toContain('本机服务降级（2 格）')
  })

  it('读数取不到：第三张脸自己说话，既不画成正常、也不画成降级（刀二的形状）', async () => {
    const shell = await boot(null, 'fail')
    await shell.settle()
    const html = await shell.render()
    const text = visibleText(html)
    expect(hasBanner(html), '读数取不到时横幅干脆不画 = 把「不知道」画成了「一切如常」').toBe(true)
    expect(/class="[^"]*runtime-banner--unknown[^"]*"/.test(html), '取不到那一档没自成一张脸').toBe(true)
    expect(text).toContain('此刻取不到')
    expect(text).not.toContain(MODEL_STATE_TEXT.ready, '取不到被画成了「本地模型就绪」')
    expect(text).not.toContain('本机服务降级', '取不到被画成了降级：界面并不知道降级的是哪一族')
  })

  it('读数还没回来：那一刻既不画正常也不画降级；放行之后才把降级那几张脸画出来', async () => {
    const shell = await boot(TWO_FAMILIES, 'hold')
    const pending = await shell.render()
    expect(hasBanner(pending), '一发还没回来的那一刻就画横幅：画的是想象中的读数').toBe(false)
    await shell.settle()
    expect(hasBanner(await shell.render()), '放行之后横幅没跟上：那一发读到的东西没人说').toBe(true)
  })

  it('权重那一格单独一档：顶句吃 MODEL_STATE_TEXT.down 现成的词，壳层不自造第二句', async () => {
    const shell = await boot(DOWN)
    await shell.settle()
    const text = visibleText(await shell.render())
    expect(text).toContain(MODEL_STATE_TEXT.down)
    expect(text).not.toContain(MODEL_STATE_TEXT.ready)
  })

  it('三态两两不冒充：ready 无横幅，degraded 与 unknown 各占一档、两句不同', async () => {
    const ready = await boot(READY)
    await ready.settle()
    const degraded = await boot(TWO_FAMILIES)
    await degraded.settle()
    const unknown = await boot(null, 'fail')
    await unknown.settle()
    expect(hasBanner(await ready.render())).toBe(false)
    const degradedHtml = await degraded.render()
    const unknownHtml = await unknown.render()
    expect(hasBanner(degradedHtml)).toBe(true)
    expect(hasBanner(unknownHtml)).toBe(true)
    expect(visibleText(unknownHtml)).not.toBe(visibleText(degradedHtml))
  })
})

/* -------------------------------------------------------------------- 乙 */

describe('R452 乙 · 一发都不许多打：一次读取、整站复用（判据②）', () => {
  it('进工作台恰好一发：打出去的路径只有健康读数那一格，别的路径一枚都没碰', async () => {
    const shell = await boot(WIDE)
    await shell.settle()
    await shell.render()
    expect(shell.paths, '壳层进工作台打了一发以上的请求').toEqual([HEALTH_PATH])
  })

  it('切遍每一屏都不重发：横幅在每一屏都在（整站常驻这一格）', async () => {
    const shell = await boot(WIDE)
    await shell.settle()
    expect(screenRouteIds.length, '路由表没读到屏名清单：量具空转').toBeGreaterThan(3)
    for (const screen of screenRouteIds) {
      shell.route.name = screen
      shell.route.path = '/' + screen
      const html = await shell.render()
      expect(hasBanner(html), screen + ' 这一屏看不见降级横幅：整站常驻又塌回单屏').toBe(true)
    }
    expect(shell.paths.filter(path => path === HEALTH_PATH), '切屏把健康读数重打了一遍').toHaveLength(1)
  })

  it('静置 1.5 秒不发第二发；壳层没有 setInterval，读取点恰一枚（挂载即轮询就是这个形状）', async () => {
    const shell = await boot(WIDE)
    await shell.settle()
    await wait(1500)
    expect(shell.paths.filter(path => path === HEALTH_PATH), '静置之中又打了一发：横幅开始自己转了').toHaveLength(1)
    expect(/\bsetInterval\b/.test(appCode), 'App.vue 里出现了 setInterval：挂载即轮询').toBe(false)
    expect((appCode.match(/\breadRuntimeHealth\b/g) || []).length, '读取点不止一处：定义一枚、调用点一枚').toBe(2)
  })

  it('再登录一次吃的是 lib/health.js 那份 60 秒缓存：仍然只有一发，横幅照旧在位', async () => {
    const shell = await boot(WIDE)
    await shell.settle()
    shell.bindings.doLogout()
    expect(hasBanner(await shell.render()), '退出之后横幅还在：登录门没管住这一格').toBe(false)
    shell.store.set(TOKEN_KEY, 'jwt-live')
    shell.store.set(USER_KEY, 'baiye')
    shell.store.set(ROLE_KEY, 'staff')
    shell.bindings.checkAuth()
    await shell.settle()
    expect(hasBanner(await shell.render()), '回访时横幅没画出来：缓存里那份读数没人说').toBe(true)
    expect(shell.paths.filter(path => path === HEALTH_PATH), '回访又打了一发：一次读取多处复用没成立').toHaveLength(1)
  })

  it('横幅不往屏上多长一枚控件：源码里裸 <button> 与 <UiButton 枚数都没变，渲染出的枚数仍是侧栏 + 顶栏那两枚', async () => {
    const shell = await boot(WIDE)
    await shell.settle()
    const html = await shell.render()
    expect(countNativeButtons(appSource), 'App.vue 又长出裸 <button>（r288 的棘轮）').toBe(0)
    expect((appSource.match(/<UiButton\b/g) || []).length, 'App.vue 里 <UiButton 枚数变了（r307b 钉的是八枚）').toBe(8)
    const banner = /<div[^>]*data-testid="degradation-banner"[\s\S]*?<\/section>/.exec(html)?.[0] || ''
    expect(banner.length, '横幅那一段抠不出来：这一组对照成了空转').toBeGreaterThan(0)
    expect(banner.match(/<button\b/g), '横幅里混进了按钮：本单没有伸手刷新的入口').toBe(null)
    expect((html.match(/<button\b/g) || []).length, '屏上的控件枚数变了：横幅偷偷长了第二枚按钮')
      .toBe(navigation.length + 2)
  })
})

/* -------------------------------------------------------------------- 丙 */

describe('R452 丙 · 逐族出话：一族一句，族名与下一步都在（判据⑥第三把刀）', () => {
  it('face 节点枚数 == runtimeFaces() 当场推导的枚数（不手抄数字）', async () => {
    const shell = await boot(WIDE)
    await shell.settle()
    const html = await shell.render()
    // 推导用的是尺子自己归一化过的那份读数（fetchRuntimeHealth 命中的是 60 秒缓存，不再发第二发）：
    // 拿后端原始 body 直接算会把算力那一格的键名读丢，量具自己先少一族。
    const derived = runtimeFaces(await fetchRuntimeHealth())
    expect(derived.length, '样本读数推不出多族脸：这份夹具本身坏了').toBeGreaterThanOrEqual(5)
    expect(faceNodes(html), '横幅把几族并成了少于推导枚数的一句话').toBe(derived.length)
    expect(shell.paths.filter(path => path === HEALTH_PATH), '量具自己多打了一发').toHaveLength(1)
  })

  it('每一族的族名（label）与那一句「下一步」（detail）逐字在屏上：丢了哪一族就点名叫哪一族', async () => {
    const shell = await boot(WIDE)
    await shell.settle()
    const text = visibleText(await shell.render())
    for (const face of runtimeFaces(await fetchRuntimeHealth())) {
      expect(text, '屏上丢了这一族的名字：' + face.label).toContain(face.label)
      expect(text, '屏上丢了这一族的下一步：' + face.label).toContain(face.detail)
    }
  })

  it('族与族两两不同句：逐族抠出来的那几句里，一句重复都没有', async () => {
    const shell = await boot(WIDE)
    await shell.settle()
    const html = await shell.render()
    const perFace = [...html.matchAll(/data-testid="degradation-banner-face"[\s\S]*?<\/li>/g)]
      .map(chunk => visibleText(chunk[0].replace(/data-testid="degradation-banner-face"/, ' ')))
    expect(perFace.length, 'face 节点抠不出来：逐族这一格无从对照').toBeGreaterThan(1)
    expect(new Set(perFace).size, '两族画成了同一句话').toBe(perFace.length)
  })

  it('只坏两格时说的就是这两格：别格一个字都不许搭车', async () => {
    const shell = await boot(TWO_FAMILIES)
    await shell.settle()
    const text = visibleText(await shell.render())
    expect(text).toContain('检索模型缺失')
    expect(text).toContain('队列服务连不上')
    expect(text, '只坏两格却被横幅说成了别的格').not.toContain('只读')
    expect(text).not.toContain('没走加速设备')
  })
})

/* -------------------------------------------------------------------- 丁 */

const VISIBLE_PATTERNS = [
  /src\/[A-Za-z0-9_./-]+\.js/,
  /\bGET \/[a-z]/,
  /\bPOST \/[a-z]/,
  /\/api\//,
  /devFixtures/,
  /runtimeFaces|modelState|fetchRuntimeHealth/,
  /\b[a-z]+_[a-z_]+\b/,
]
const DOM_PATTERNS = [
  /src\/[A-Za-z0-9_./-]+\.js/,
  /\bGET \/[a-z]/,
  /\bPOST \/[a-z]/,
  /\/api\//,
  /devFixtures/,
  /read_only_protected|inference_compute|embedding_model_missing|model_not_available/,
  /users_store_not_persistent|queue_unavailable|postgres_unavailable|knowledge_graph_read_only/,
]

describe('R452 丁 · 屏上零技术注脚（判据③ · 手法照 r267）', () => {
  const cases = [['六族全坏', WIDE, 'value'], ['权重不在', DOWN, 'value'], ['读数取不到', null, 'fail']]
  it.each(cases)('%s：可见正文与整段渲染产物逐条 0 命中', async (_label, health, outcome) => {
    const shell = await boot(health, outcome)
    await shell.settle()
    const html = await shell.render()
    expect(hasBanner(html), '这一格根本没上屏：注脚扫描成了空转').toBe(true)
    const text = visibleText(html)
    for (const pattern of VISIBLE_PATTERNS) {
      expect(text.match(pattern), '可见正文命中了 ' + pattern).toBe(null)
    }
    // DOM 这一腿只扫横幅自己那一段（连属性一起）：壳层里 R333 / R148 那几段在册模板注释带着源码路径，
    // 它们既不上屏也不是本单写的。口径照 r267「注释不算正文」，整页扫会把别人的账算成本单的红。
    const region = bannerRegion(html)
    expect(region.length, '横幅那一段抠不出来：DOM 扫描成了空转').toBeGreaterThan(80)
    for (const pattern of DOM_PATTERNS) {
      expect(region.match(pattern), '横幅的渲染产物命中了 ' + pattern).toBe(null)
    }
  })

  it('正向自证：这一组量具不是空转 —— 同样的扫描能在夹具里认出注脚', () => {
    const forged = '这台机器 <strong>embedding_model_missing</strong> 见 src/lib/health.js 与 GET /api/v1/health/details'
    expect(visibleText(forged).match(/\b[a-z]+_[a-z_]+\b/), '量具认不出裸码名').toBeTruthy()
    expect(visibleText(forged).match(/src\/[A-Za-z0-9_./-]+\.js/), '量具认不出源码路径').toBeTruthy()
    expect(forged.match(/\/api\//), '量具认不出路由').toBeTruthy()
    expect(forged.match(/\bGET \/[a-z]/), '量具认不出方法与路由').toBeTruthy()
    expect(bannerRegion('<p>x</p><div data-testid="degradation-banner"><b>坏</b></div><i data-testid="panel-slot">').length, '抠段量具自己空转').toBeGreaterThan(20)
  })
})

/* -------------------------------------------------------------------- 戊 */

describe('R452 戊 · 不新造第二把尺（工单正文那一句）', () => {
  it('对 lib/health.js 的 import 恰一枚，请的就是既有那四枚工具，一枚不多一枚不少', () => {
    const imports = appCode.match(/import \{[^}]*\} from '\.\/lib\/health\.js'/g) || []
    expect(imports, 'App.vue 里对 health.js 的 import 不是一枚').toHaveLength(1)
    const names = imports[0]
      .replace(/^import \{/, '')
      .replace(/\} from.*$/, '')
      .split(',')
      .map(name => name.trim())
      .filter(Boolean)
    expect(names.sort(), '壳层请的工具换了人：要么是新造的尺，要么是没人用的死接线').toEqual([
      'fetchRuntimeHealth', 'modelState', 'modelStatusText', 'runtimeFaces',
    ])
  })

  it('壳层不复算：problems / 后端那几枚键名 / 只读后缀，剥注释后一枚都不在 App.vue 里', () => {
    for (const token of ['problems', 'inference_compute', 'read_only_protected', '_read_only',
      'embedding_model_missing', 'model_not_available']) {
      expect(appCode, 'App.vue 自己开始读后端键名了：' + token).not.toContain(token)
    }
  })

  it('三态的尺只有一把：bannerKind 直接吃 modelState()，壳层不写第二套判定式', () => {
    expect(appCode, 'bannerKind 不再吃 modelState()：这里长出了第二把尺')
      .toMatch(/bannerKind = computed\(\(\) =>[^\n]*modelState\(healthRead\.value\.health\)/)
  })
})

/* -------------------------------------------------------------------- 己 */

describe('R452 己 · 运行时零外部请求（判据⑤第二道天花板）', () => {
  it('App.vue 与 theme.css 的代码体里一枚外部主机都不许有（googleapis / gstatic / unpkg / cdnjs / jsdelivr）', () => {
    const external = /googleapis|gstatic|unpkg\.com|cdnjs|jsdelivr|cdn\./i
    for (const [label, text] of [['App.vue', stripComments(appSource)], ['theme.css', stripComments(themeSource)]]) {
      expect(text.match(external), label + ' 出现了外部主机引用').toBe(null)
    }
  })

  it('正向自证：外部主机那把尺不是空转 —— 一句远程字体 @import 当场认得出', () => {
    const external = /googleapis|gstatic|unpkg\.com|cdnjs|jsdelivr|cdn\./i
    const forged = "/* 记录：fonts.googleapis.com 已删 */\n@import url('https://fonts.googleapis.com/css2?family=Manrope');"
    expect(stripComments(forged).match(external), '量具认不出远程字体引用（注释剥过头了？）').toBeTruthy()
    // 反向一格：同一句作为注释存在时，剥注释之后它就不该再被这把尺认出（那是记录，不是引用）。
    expect(stripComments('/* 记录：fonts.googleapis.com 已删 */').match(external), '注释里的那句记录被当成了引用').toBe(null)
  })

  it('非 SVG 命名空间的 http 字面量一枚都不许多出来（data: 里那一条是内联 SVG 的命名空间）', () => {
    const urls = text => (text.match(/https?:\/\/[^\s"'`)]+/g) || []).filter(url => !url.startsWith('http://www.w3.org/2000/svg'))
    expect(urls(appSource), 'App.vue 里多了要出本机才能取的东西：' + urls(appSource).join(', ')).toEqual([])
    expect(urls(themeSource), 'theme.css 里多了要出本机才能取的东西：' + urls(themeSource).join(', ')).toEqual([])
  })

  it('横幅那一段样式一枚裸色值都没添（新色值只准在 theme.css 落地）', () => {
    const style = /<style scoped>([\s\S]*)<\/style>/.exec(appSource)?.[1] || ''
    const mark = style.indexOf('R452 · 全站降级横幅')
    expect(mark, '找不到横幅那一段样式的起点注释').toBeGreaterThan(-1)
    const block = style.slice(mark).replace(/\/\*[\s\S]*?\*\//g, '')
    expect(block.match(/#[0-9a-fA-F]{3,8}\b/), '横幅样式里出现井号色值').toBe(null)
    expect(block.match(/\brgba?\(/), '横幅样式里出现 rgb 系函数').toBe(null)
    expect((block.match(/var\(--[^)]*\)/g) || []).length, '这一段没全走 token').toBeGreaterThan(8)
  })
})