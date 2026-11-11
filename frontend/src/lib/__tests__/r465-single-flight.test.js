/**
 * R465 · 判据①② · GET /health/details 的在飞去重（single-flight）
 *
 * 病灶（本单基点 d824b10 现读 frontend/src/lib/health.js:31-41）：那枚模块只有私有 cached /
 * cachedAt 两格，讲的是「落地之后有没有货」，没有一格讲「此刻有没有一发在路上」。于是两处界面几乎
 * 同时伸手时，第二格查缓存查到的只是「没有」，只能自己再发一发 —— R458 丙5 把这枚数实量成 2 发。
 *
 * 量具（口径照在册那枚 r458-site-health-single-read）：
 *   拦在 lib/http 那枚 axios 实例的 get 上（vi.mock 换掉），也就是真 fetchRuntimeHealth 真要发请求
 *   时必走的那一格；paths 是唯一账本，读数 = 过滤那枚地址。不拦在组件上，也不拦在 lib/health.js 上。
 *   时钟用真的：本件钉的是「同一 tick 内两处伸手」，靠的是微任务先后，不是等出来的量；holdOpen()
 *   把那一发摁在路上，release 之前谁也拿不到读数 —— 「还在路上」是被造出来的。
 *   两处伸手是夹具（shellReach / panelReach），复刻 App.vue:63-65 与 ChatPanel.vue:795-808 各自那一腿
 *   的真实形状：同一 tick、都不穿透、各自把读数收进自己的格子。丁1 先证明这两处单独跑都真发得出去，
 *   否则上面每一个「1」都可能是一枚都没发的空账。
 *   真组件端到端那一腿在册件 r458 丙5 上（本单不许动它）：它钉的是「残留窗口今天就是 2」，本单一落地
 *   它就该读成 1 —— 那枚红是闭单的证据，红数记在交回里。
 *
 * 两把反证刀（🔴 一律造在临时目录的副本上，绝不原地改被跟踪文件 —— 事故 #71 的入规）：
 *   刀一 摘掉 single-flight（删掉 fetchRuntimeHealth 里那一句 if (inFlight) return inFlight）
 *     ⇒ 甲1 那格并发伸手当场回到 2 发。
 *   刀二 把失败也写进缓存（catch 里不作废 cached，只把 cachedAt 盖成当下）
 *     ⇒ 乙3 那格「失败后下一枚伸手允许重发」消失，且第三枚伸手拿到一份过期的「就绪」假读数。
 *   副本先过一遍成功腿（blade() 里那一句），免得拿「模块根本没加载」冒充反证。
 */
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { ...actual.http, get: vi.fn() } }
})

import { http } from '../../lib/http'
import {
  EMBEDDING_MODEL_MISSING,
  MODEL_STATE_TEXT,
  fetchRuntimeHealth,
  modelState,
  resetRuntimeHealthCache,
  runtimeFaces,
  runtimeHealthReadInFlight,
} from '../../lib/health.js'

const HEALTH = '/health/details'
const READY_BODY = { status: 'ok', problems: [], model: { name: 'qwen3:4b', source: 'ollama' }, storage: {} }
const DEGRADED_BODY = {
  status: 'degraded',
  problems: [EMBEDDING_MODEL_MISSING],
  model: { name: 'qwen3:4b', source: 'ollama' },
  storage: {},
}
const COMPUTE_BODY = {
  status: 'degraded',
  problems: [],
  model: {
    name: 'qwen3:4b',
    source: 'ollama',
    inference_compute: 'cpu',
    inference_compute_error_code: 'cuda_unavailable',
    inference_compute_age_seconds: 12,
  },
  storage: {},
}

/* ------------------------------------------------------------------- 假后端 */

let paths = []
let hold = null
let failure = null
let body = READY_BODY

const settle = async (rounds = 6) => {
  for (let round = 0; round < rounds; round += 1) await new Promise(done => { setTimeout(done, 0) })
}
const healthCount = () => paths.filter(path => path === HEALTH).length

function installBackend() {
  paths = []
  hold = null
  failure = null
  body = READY_BODY
  http.get.mockImplementation(async (url) => {
    const target = String(url)
    paths.push(target)
    if (target === HEALTH) {
      if (hold) await hold
      if (failure) throw failure
    }
    return { data: body }
  })
}

/** 把那一发摁在路上：release 之前它既不落地也不失败。 */
function holdOpen() {
  let done = null
  hold = new Promise(resolve => { done = resolve })
  return { release: () => { hold = null; done() } }
}

/* --------------------------------------------------------- 两处伸手的夹具 */

/** 壳层 App.vue:63-65：进工作台那一刻 await 一枚非穿透读数，取到取不到都算「试过了」。 */
function shellReach() {
  const box = { tried: false, health: null }
  fetchRuntimeHealth().then((read) => {
    box.tried = true
    box.health = read
  })
  return box
}

/** 面板 ChatPanel.vue:795-808：挂载那一刻同样一枚非穿透读数，落进自己那枚格子。 */
function panelReach() {
  const box = { value: null }
  fetchRuntimeHealth().then((read) => { box.value = read })
  return box
}

beforeEach(() => {
  installBackend()
  resetRuntimeHealthCache()
})

afterEach(() => {
  http.get.mockReset()
  resetRuntimeHealthCache()
})

/* ---------------------------------------------------- 甲 · 判据① 并发伸手 */

describe('R465 甲 · 判据①：并发伸手只发一发', () => {
  it('甲1 壳层那一发还在路上时面板也伸手：打到 /health/details 的请求数 = 1（R458 丙5 那 2 发在此闭掉）', async () => {
    const gate = holdOpen()
    const shell = shellReach()
    const panel = panelReach()
    await settle(1)
    expect(healthCount(), '两处伸手打出了两发：single-flight 没接上').toBe(1)
    expect(runtimeHealthReadInFlight(), '在飞槽位是空的：上面那个「1」可能是一枚都没发的空账').toBeTruthy()
    gate.release()
    await settle()
    expect(healthCount(), '放行之后又补了一发').toBe(1)
    expect(shell.health, '壳层没拿到落地读数').not.toBeNull()
    expect(panel.value, '等待方没拿到同一份读数').not.toBeNull()
    expect(panel.value === shell.health, '两处界面吃的不是同一份读数：同一发被解析了两遍').toBe(true)
    expect(runtimeHealthReadInFlight(), '落地后槽位没清：界面此后一次也问不到新读数').toBeNull()
  })

  it('甲2 三处伸手（壳层 + 两枚面板实例）挤在同一刻：仍然只有一发在路上', async () => {
    const gate = holdOpen()
    const shell = shellReach()
    const first = panelReach()
    const second = panelReach()
    await settle(1)
    expect(healthCount(), '三处伸手打出了多于一发：柜台前又站了三个人').toBe(1)
    gate.release()
    await settle()
    expect(healthCount(), '放行之后补发了').toBe(1)
    expect(first.value === second.value && second.value === shell.health, '三处没共用同一份读数').toBe(true)
  })

  it('甲3 force 伸手落在在飞那一发上也不另开第二枪：在飞槽位排在那 60 秒之前', async () => {
    const gate = holdOpen()
    const panel = panelReach()
    const pressed = fetchRuntimeHealth({ force: true })
    await settle(1)
    expect(healthCount(), '在飞时 force 又开一枪：同一时刻两发在路上').toBe(1)
    gate.release()
    const forced = await pressed
    await settle()
    expect(forced, '伸手那一位没等到读数').not.toBeNull()
    expect(panel.value === forced, '伸手与在飞那一位没吃到同一份读数').toBe(true)
  })
})

/* ------------------------------------------------ 乙 · 判据② 失败不污染缓存 */

describe('R465 乙 · 判据②：在飞失败不许污染缓存', () => {
  it('乙1 那一发失败：等待方拿到 null，那把尺落 unknown，一枚都不许落 ready', async () => {
    const gate = holdOpen()
    const shell = shellReach()
    const panel = panelReach()
    await settle(1)
    failure = new Error('这台机器上的服务此刻不应答')
    gate.release()
    await settle()
    expect(shell.health, '失败那一路给出了读数').toBeNull()
    expect(panel.value, '等待方拿到了假读数').toBeNull()
    expect(modelState(panel.value), '读不到被画成了健康').toBe('unknown')
    expect(MODEL_STATE_TEXT[modelState(panel.value)], '文案落回了「本地模型就绪」').not.toBe(MODEL_STATE_TEXT.ready)
    expect(MODEL_STATE_TEXT[modelState(panel.value)]).toBe('模型状态未知')
  })

  it('乙2 失败之后槽位清空：不许泄漏成「永远在飞」', async () => {
    const gate = holdOpen()
    const pending = fetchRuntimeHealth()
    await settle(1)
    failure = new Error('不应答')
    gate.release()
    await expect(pending).resolves.toBeNull()
    expect(runtimeHealthReadInFlight(), '失败没清槽位：后来的人一次也发不出去').toBeNull()
  })

  it('乙3 失败之后下一枚伸手真的重发（失败留着缓存，这条就是红的）', async () => {
    failure = new Error('不应答')
    await expect(fetchRuntimeHealth()).resolves.toBeNull()
    expect(healthCount(), '失败那腿自己就没发出去').toBe(1)
    failure = null
    body = READY_BODY
    const read = await fetchRuntimeHealth()
    expect(healthCount(), '失败之后第二枚伸手没重发：那份缓存被失败污染了').toBe(2)
    expect(modelState(read), '重发之后读不到真读数').toBe('ready')
  })

  it('乙4 对照腿：成功落地之后 60 秒内一枚都不重发（乙3 那个 2 是「失败作废缓存」换来的）', async () => {
    const first = await fetchRuntimeHealth()
    expect(healthCount()).toBe(1)
    const again = await fetchRuntimeHealth()
    expect(healthCount(), '成功之后还重发：那 60 秒缓存被改坏了').toBe(1)
    expect(again === first, '缓存里那份读数没被复用：两次各自解析了一遍').toBe(true)
  })
})

/* -------------------------------------- 丙 · 三条老规矩 + R268 第四条未退 */

describe('R465 丙 · 老规矩没因为加单飞而退', () => {
  it('丙1 老规矩 1 + 3：载荷形状不对时并发伸手各自拿到 null，一枚都不抛，且只发一发', async () => {
    body = 'not-an-object'
    const first = fetchRuntimeHealth()
    const second = fetchRuntimeHealth()
    await expect(first).resolves.toBeNull()
    await expect(second).resolves.toBeNull()
    expect(healthCount(), '形状不对时并发伸手打出了两发').toBe(1)
    expect(runtimeHealthReadInFlight(), '形状不对那一腿没清槽位').toBeNull()
    expect(() => modelState(null)).not.toThrow()
    expect(modelState(null)).toBe('unknown')
  })

  it('丙2 第四条未退：共用同一发的两处界面都拿到 degraded，既不并入 down 更不是 ready', async () => {
    body = DEGRADED_BODY
    const shell = shellReach()
    const panel = panelReach()
    await settle()
    expect(healthCount(), '降级读数也被打出了两发').toBe(1)
    expect(modelState(panel.value), '别的格子坏被并成了权重缺失那一句').not.toBe('down')
    expect(modelState(shell.health)).toBe('degraded')
    expect(modelState(panel.value)).toBe('degraded')
    expect(runtimeFaces(panel.value).map(face => face.kind)).toEqual(['embedding'])
  })

  it('丙3 算力那一格仍自成一档：problems 空但记了降级码 ⇒ degraded（单飞没把它抹平）', async () => {
    body = COMPUTE_BODY
    const read = await fetchRuntimeHealth()
    expect(modelState(read)).toBe('degraded')
    expect(runtimeFaces(read).map(face => face.kind)).toEqual(['compute'])
  })
})

/* ------------------------------------------------------ 丁 · 量具不空转 */

describe('R465 丁 · 夹具与读数都不是摆设', () => {
  it('丁1 每一处伸手单独跑都真发得出那一发（甲组每一个「1」的先决条件）', async () => {
    const shell = shellReach()
    await settle()
    expect(healthCount(), '壳层那处伸手根本不发请求：甲组是在数零个人').toBe(1)
    expect(shell.health).not.toBeNull()
    resetRuntimeHealthCache()
    paths = []
    const panel = panelReach()
    await settle()
    expect(healthCount(), '面板那处伸手根本不发请求：甲组那个「共用」是空转').toBe(1)
    expect(panel.value).not.toBeNull()
  })

  it('丁2 在飞读数是真的：伸手前 null、在路上非 null、落地后回到 null', async () => {
    expect(runtimeHealthReadInFlight()).toBeNull()
    const gate = holdOpen()
    const pending = fetchRuntimeHealth()
    expect(runtimeHealthReadInFlight(), '请求已经出门却在飞槽位上看不见：那枚读数是个摆设').toBeTruthy()
    gate.release()
    await pending
    expect(runtimeHealthReadInFlight()).toBeNull()
  })
})

/* -------------------------------------------------- 戊 · 两把反证刀（真跑） */

const STUB_HTTP = [
  'export const state = { paths: [], hold: null, failure: null, body: null }',
  'export const http = {',
  '  async get(url) {',
  '    state.paths.push(String(url))',
  '    if (state.hold) await state.hold',
  '    if (state.failure) throw state.failure',
  '    return { data: state.body }',
  '  },',
  '}',
].join('\n')

const dirs = []

/**
 * 把树里那枚 health.js 复制进临时目录、按刀改造、配上替身 http，再动态加载。
 * 副本导的是 './http.js' —— 落点就是同目录那枚替身，账本在 stub.state.paths 上。
 */
async function blade(name, cut) {
  const at = mkdtempSync(join(tmpdir(), 'r465-blade-'))
  dirs.push(at)
  const real = readFileSync(new URL('../health.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
  const mutated = cut(real)
  expect(mutated, '刀没切进去：副本与树里那枚一模一样').not.toBe(real)
  writeFileSync(join(at, 'http.js'), STUB_HTTP, 'utf8')
  writeFileSync(join(at, name), mutated.replace(/\n/g, '\r\n'), 'utf8')
  const stub = await import(pathToFileURL(join(at, 'http.js')).href)
  const mod = await import(pathToFileURL(join(at, name)).href)
  stub.state.body = READY_BODY
  await expect(mod.fetchRuntimeHealth()).resolves.toMatchObject({ status: 'ok' })
  mod.resetRuntimeHealthCache()
  stub.state.paths = []
  stub.state.failure = null
  return { stub, mod, count: () => stub.state.paths.filter(path => path === HEALTH).length }
}

afterEach(() => {
  for (const at of dirs) rmSync(at, { recursive: true, force: true })
  dirs.length = 0
})

describe('R465 戊 · 两把反证刀现场读数', () => {
  it('戊1 刀一：摘掉 single-flight ⇒ 甲1 那格当场回到 2 发', async () => {
    const { stub, mod, count } = await blade('blade-one-no-single-flight.js', (source) => {
      const needle = '  if (inFlight) return inFlight\n'
      expect(source.includes(needle), '刀一落点找不到：health.js 里那一句被改了形状').toBe(true)
      return source.replace(needle, '')
    })
    let done = null
    stub.state.hold = new Promise(resolve => { done = resolve })
    const first = mod.fetchRuntimeHealth()
    const second = mod.fetchRuntimeHealth()
    await settle(1)
    expect(count(), '反证刀一没让并发伸手变回 2 发 ⇒ 甲组那条「一发」是量具空转出来的假绿').toBe(2)
    stub.state.hold = null
    done()
    await Promise.all([first, second])
    expect(mod.runtimeHealthReadInFlight(), '刀一只摘了守卫，槽位清理那一条不许跟着坏').toBeNull()
  })

  it('戊2 刀二：把失败也写进缓存 ⇒ 乙3 那格的重发消失，第三枚伸手拿到一份过期的「就绪」', async () => {
    const { stub, mod, count } = await blade('blade-two-failure-caches.js', (source) => {
      const needle = '    cached = null\n    cachedAt = 0\n    return null'
      expect(source.includes(needle), '刀二落点找不到：catch 那两行被改了形状').toBe(true)
      return source.replace(needle, '    cachedAt = now\n    return null')
    })
    const warm = await mod.fetchRuntimeHealth()
    expect(mod.modelState(warm), '刀二的对照腿没把缓存喂热').toBe('ready')
    expect(count()).toBe(1)
    stub.state.failure = new Error('这台机器上的服务此刻不应答')
    await expect(mod.fetchRuntimeHealth({ force: true })).resolves.toBeNull()
    expect(count(), '失败那腿没真打出去').toBe(2)
    stub.state.failure = null
    const after = await mod.fetchRuntimeHealth()
    expect(count(), '刀二之下第三枚伸手还是重发了：那把刀没切进缓存').toBe(2)
    expect(after, '刀二没把旧读数留在缓存里：反证造不出来').not.toBeNull()
    expect(mod.modelState(after), '刀二交回的是一份过期的「就绪」假话 —— 这正是判据②要杀的形状').toBe('ready')
  })
})
