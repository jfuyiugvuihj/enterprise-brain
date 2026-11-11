/**
 * R458 · 判据④ · 「再看一次」这一格上屏零技术注脚（手法照 r267 / r452）
 *
 * 口径照在册那两枚件：判「上屏」一律从 renderToString 的真产物里抠，不拿裸 rg 命中数当判据；
 * 注释不算正文（模板注释里写着源码路径是本仓记录事实的地方，它不上员工的眼），
 * 但【连属性一起扫】整段渲染产物 —— 把注脚挪进 <p title="..."> 里也照样红。
 * 覆盖三张脸：读到且没变 / 读到且变了 / 这一刻读不到。
 *
 * 乙组是判据④点名的「正向自证」：同一把尺先在伪造的注脚上逐条认得出，再看它认不出真产物 ——
 * 没有这一条，上面那些 0 命中全是空转。
 */
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { routeLocationKey, routerKey } from 'vue-router'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { ...actual.http, get: vi.fn(), post: vi.fn(), delete: vi.fn() } }
})

import ChatPanel from '../ChatPanel.vue'
import { http, TOKEN_KEY } from '../../lib/http'
import { fetchRuntimeHealth, resetRuntimeHealthCache } from '../../lib/health.js'

const readyBody = { status: 'ok', problems: [], model: { name: 'qwen3:4b', source: 'ollama' }, storage: {} }
const degradedBody = {
  status: 'degraded',
  problems: ['embedding_model_missing', 'users_store_not_persistent'],
  model: { name: 'qwen3:4b', source: 'ollama' },
  storage: {},
}

/** 员工读到的字里不许出现的东西：源码路径、方法与路由、后端裸码名、这把尺自己的函数名。 */
const VISIBLE_PATTERNS = [
  /src\/[A-Za-z0-9_./-]+\.(js|vue|ts)/,
  /\bGET \/[a-z]/,
  /\bPOST \/[a-z]/,
  /\/api\//,
  /health\/details/,
  /fetchRuntimeHealth|refreshRuntimeHealth|recheckRuntimeHealth|healthSignature|runtimeFaces|modelState|modelStatusText/,
  /\b[a-z]+_[a-z_]+\b/,
  /\b(read_only|read-?only|inference|embedding|onMounted|computed|localStorage|axios)\b/i,
]
/** 渲染产物（连属性一起）：data-testid / data-kind 这类机器名允许，文件名、方法与路由不许。 */
const DOM_PATTERNS = [
  /src\/[A-Za-z0-9_./-]+\.(js|vue|ts)/,
  /\bGET \/[a-z]/,
  /\bPOST \/[a-z]/,
  /\/api\//,
  /health\/details/,
  /read_only_protected|inference_compute|embedding_model_missing|model_not_available/,
  /users_store_not_persistent|queue_unavailable|postgres_unavailable|knowledge_graph_read_only/,
]

let body = readyBody
let failure = null

beforeEach(() => {
  body = readyBody
  failure = null
  resetRuntimeHealthCache()
  http.get.mockImplementation(async (url) => {
    if (String(url) === '/health/details') {
      if (failure) throw failure
      return { data: body }
    }
    return { data: {} }
  })
  http.post.mockImplementation(async () => ({ data: {} }))
  http.delete.mockImplementation(async () => ({ data: {} }))
})

afterEach(() => {
  http.get.mockReset()
  resetRuntimeHealthCache()
})

const visibleText = html => html
  .replace(/<!--[\s\S]*?-->/g, ' ')
  .replace(/<[^>]+>/g, ' ')
  .replace(/\s+/g, ' ')
  .trim()

/**
 * 起一次真面板：跑它自己的 setup()，SSR 渲一次拿真产物。
 * onMounted 在 SSR 里不跑，所以「壳层那一发」由这里自己请真 fetchRuntimeHealth 打，
 * 再把读数交给面板的绑定 —— 与 r267 / r452 的 loadedHtml 同一口径。
 */
async function probe({ press = false, nextBody = null, unreachable = false } = {}) {
  let bindings = null
  const Host = {
    name: 'R458NoteProbe',
    setup(props, ctx) {
      bindings = ChatPanel.setup({}, ctx)
      return () => null
    },
  }
  globalThis.window = globalThis.window || { addEventListener() {}, removeEventListener() {}, dispatchEvent: () => true }
  globalThis.document = globalThis.document || { visibilityState: 'visible', addEventListener() {}, removeEventListener() {} }
  globalThis.localStorage = globalThis.localStorage || {
    getItem: key => (key === TOKEN_KEY ? 'jwt-live' : null), setItem() {}, removeItem() {}, clear() {},
    key: () => null, length: 0,
  }
  await renderToString(h(Host))
  await bindings.refreshRuntimeHealth()
  if (press) {
    if (nextBody) body = nextBody
    if (unreachable) failure = new Error('这台机器上的服务此刻不应答')
    await bindings.recheckRuntimeHealth()
  }
  return renderToString(h({ ...ChatPanel, setup: () => bindings }))
}

/** 从真产物里抠出「再看一次」那一段：从它自己的 testid 起，到消息区之前。 */
function recheckRegion(html) {
  const from = html.indexOf('data-testid="runtime-recheck"')
  if (from < 0) return ''
  const to = html.indexOf('class="chat-messages"', from)
  return html.slice(from, to < 0 ? html.length : to)
}

describe('R458 甲 · 三张脸上屏零技术注脚（判据④）', () => {
  const cases = [
    ['读到且没变', { press: true }],
    ['读到且变了', { press: true, nextBody: degradedBody }],
    ['这一刻读不到', { press: true, unreachable: true }],
  ]

  it.each(cases)('%s：可见正文与整段渲染产物逐条 0 命中', async (_label, options) => {
    const html = await probe(options)
    const region = recheckRegion(html)
    expect(region.length, '那一段根本没上屏：注脚扫描成了空转').toBeGreaterThan(80)
    expect(region, '这一段里没画上那枚按钮').toContain('data-testid="runtime-recheck-button"')
    const text = visibleText(html)
    for (const pattern of VISIBLE_PATTERNS) {
      expect(text.match(pattern), '可见正文命中了 ' + pattern).toBe(null)
    }
    for (const pattern of DOM_PATTERNS) {
      expect(region.match(pattern), '渲染产物命中了 ' + pattern).toBe(null)
    }
  })

  it('那三句话都是人话：每句都带「再看一次」或「没问到」这种员工读得懂的动词', async () => {
    const same = visibleText(await probe({ press: true }))
    const changed = visibleText(await probe({ press: true, nextBody: degradedBody }))
    const missing = visibleText(await probe({ press: true, unreachable: true }))
    expect(same).toContain('再看一次')
    expect(changed).toContain('再看一次')
    expect(missing).toContain('没问到')
    expect(missing).not.toContain('就绪')
    expect(missing).not.toContain('降级')
  })
})

describe('R458 乙 · 正向自证：这把尺认得出注脚（不是空转）', () => {
  const forged = '这台机器 <strong>embedding_model_missing</strong> 见 src/lib/health.js 与 GET /api/v1/health/details，读自 users_store_not_persistent'

  it('伪造那一句逐条都被认出来：认不出任何一条就说明甲组那些 0 命中是假的', () => {
    const text = visibleText(forged)
    expect(text.match(/src\/[A-Za-z0-9_./-]+\.(js|vue|ts)/), '量具认不出源码路径').toBeTruthy()
    expect(text.match(/\bGET \/[a-z]/), '量具认不出方法与路由').toBeTruthy()
    expect(text.match(/\/api\//), '量具认不出路由').toBeTruthy()
    expect(text.match(/health\/details/), '量具认不出那枚地址的字面量').toBeTruthy()
    expect(text.match(/\b[a-z]+_[a-z_]+\b/), '量具认不出后端裸码名').toBeTruthy()
    expect(forged.match(/users_store_not_persistent/), '连属性串都不扫的话这一条会漏').toBeTruthy()
  })

  it('抠段那把尺不是空转：一段真形状抠得出来，缺 testid 时抠不出来', () => {
    const shaped = '<div data-testid="runtime-recheck"><button>再看一次</button></div><div class="chat-messages">'
    expect(recheckRegion(shaped).length, '抠段量具自己抠不出真形状').toBeGreaterThan(20)
    expect(recheckRegion('<div class="chat-messages">').length).toBe(0)
    expect(recheckRegion('<div data-testid="runtime-recheck">没有收尾').length, '抠不到收尾时必须给整段而不是空串')
      .toBeGreaterThan(20)
  })

  it('反向一格：真产物里那句话自己必须在屏上（否则甲组扫的是一段不存在的东西）', async () => {
    const html = await probe({ press: true, nextBody: degradedBody })
    expect(html).toContain('data-testid="runtime-recheck-face"')
    expect(visibleText(recheckRegion(html))).toContain('降级')
    const before = await probe({ press: false })
    expect(before, '挂载期就把这行字画上了屏（应当是 v-if）').not.toContain('data-testid="runtime-recheck-face"')
  })
})

describe('R458 丙 · 注脚不进数据属性：那一格的属性只有人话档位', async () => {
  it('丙1 data-phase / data-tone 的取值是本仓既有那三档，不许把后端码名塞进属性里', async () => {
    const html = await probe({ press: true, unreachable: true })
    const region = recheckRegion(html)
    const values = [...region.matchAll(/data-(phase|tone)="([^"]*)"/g)].map(hit => hit[2])
    expect(values.length, '这一段连一档属性都没写出来：量具空转').toBeGreaterThan(0)
    for (const value of values) expect(value).toMatch(/^(idle|sending|done|failed|info|warn|success)$/)
  })

  it('丙2 面板里新增的这一段不复算后端判定：它只把 modelStatusText 那句话摆出来', async () => {
    const source = readFileSync(new URL('../ChatPanel.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
    const face = /function runtimeRecheckFace\(state\) \{[\s\S]*?\n\}/.exec(source)
    expect(face, '找不到那句脸的函数').toBeTruthy()
    expect(face[0]).toMatch(/modelStatusText\(runtimeHealth\.value\)/)
    expect(face[0], '这句脸自己开始读后端码名了').not.toMatch(/[a-z]+_[a-z_]+/)
  })

  it('丙3 缓存那本账没被面板抄第二份：读数这一族三枚函数里一枚时长判定都没有', () => {
    const source = readFileSync(new URL('../ChatPanel.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
    const family = [
      /function sharedRuntimeHealth\(\) \{[\s\S]*?\n\}/,
      /async function refreshRuntimeHealth\([\s\S]*?\n\}/,
      /async function recheckRuntimeHealth\(\) \{[\s\S]*?\n\}/,
    ].map(pattern => {
      const hit = pattern.exec(source)
      expect(hit, '读数这一族少了一枚函数：形状被改了').toBeTruthy()
      return hit[0]
    }).join('\n')
    // 60 秒这件事只有 lib/health.js 一处说；面板里那些 60000 是「几分钟前」的取整与 blob 回收，
    // 与本单无关（现取 :455-457 与 :1747），所以这一枚只扫本单那三枚函数。
    expect(family.match(/Date\.now\(|CACHE_MS|60_000|60000/g), '面板自己开始算缓存时长了：那是第二本 60 秒的账').toBe(null)
    expect((family.match(/\bsetTimeout\(/g) || []).length, '读数这一族的调度枚数变了（只许退场那一枚）').toBe(1)
    expect(family).toMatch(/setTimeout\(retireRecheckFace/)
  })
})
