/**
 * R268 · 判据⑥ · G07 反证钉：降级不是只有一张红脸，也不许再报绿
 *
 * 病灶（改前取证，行号取本单基点 1142c27）：
 *   lib/health.js:57  problems.includes(model_not_available) ? 'down' : 'ready'
 *                     —— 整份文件只认一枚码，其余降级一律落进 'ready'；
 *   app/common/monitoring.py:146 已经交出 embedding_model_missing、:133 交出 queue_unavailable、
 *                     :131 交出 *_read_only，前端一码不读。
 *   于是后端明明报着「检索模型没就绪 / 队列连不上 / 存储只读」，顶栏照样是绿点加「本地模型就绪」。
 *
 * 反证怎么算红：把 modelState 改回那一句三元，下面甲组全部红；把一族文案并成同一句，
 * 乙组「两两不同」红；把不认识的那一格改成闭嘴，丙组红；面板那一格接线拆掉，丁组红。
 *
 * 🔴 判据③点名「不许用一条红文案兜三格」，所以这里的硬断言是句子两两不同，不是枚数。
 * 手法沿用仓库既有口径（node + @vue/server-renderer，没有 jsdom 也不 npm i）：
 * 只把网络层 lib/http 换成假实现，lib/health.js 与面板的 setup 全部真身。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() }, authedFetch: vi.fn() }
})

import { http } from '../../lib/http'
import ChatPanel from '../ChatPanel.vue'
import {
  EMBEDDING_MODEL_MISSING,
  MODEL_NOT_AVAILABLE,
  MODEL_STATE_TEXT,
  QUEUE_UNAVAILABLE,
  USERS_STORE_NOT_PERSISTENT,
  computeFace,
  dependencyFaces,
  modelState,
  modelStatusText,
  problemFamily,
  readOnlyFace,
  resetRuntimeHealthCache,
  runtimeFaces,
} from '../../lib/health.js'

const source = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const panel = source('../ChatPanel.vue')

/** V6 闸门同一条口径：给人看的句子里不许夹 snake_case 裸码名。 */
const BARE_CODE = /[\u4e00-\u9fff][^<>]*\b[a-z][a-z0-9]*(_[a-z0-9]+)+/

const health = (problems, over = {}) => ({
  status: problems.length ? 'degraded' : 'ok',
  problems,
  modelName: 'qwen2.5:14b',
  modelSource: 'configured',
  ...over,
})

const voicesOf = (read) => runtimeFaces(read).map(face => `${face.headline}${face.detail}`)

// ==================== 面板真身：setup 绑定 + 真 fetchRuntimeHealth ====================

function installDomStubs() {
  const store = new Map()
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
}

/** 借宿主实例跑面板真 setup()，拿回未解包的原始绑定（同 r169 手法）。 */
async function mountPanel() {
  let bindings = null
  const Probe = defineComponent({
    name: 'R268HealthProbe',
    setup(props, ctx) {
      bindings = ChatPanel.setup({}, ctx)
      return () => null
    },
  })
  await renderToString(h(Probe))
  expect(bindings, '面板应暴露可调用的 setup()').toBeTruthy()
  return bindings
}

beforeEach(() => {
  resetRuntimeHealthCache()
  http.get.mockReset()
  http.post.mockReset()
})

describe('甲 · 三张脸分得开（反证：改回只认一枚码 ⇒ 本组全红）', () => {
  const cases = [
    ['检索模型缺失', health([EMBEDDING_MODEL_MISSING]), 'embedding'],
    ['队列连不上', health([QUEUE_UNAVAILABLE]), 'queue'],
    ['存储只读', health(['memories_read_only']), 'readOnly'],
  ]

  it.each(cases)('%s：读数在位时画得出那一格自己的脸', (_name, read, kind) => {
    const faces = runtimeFaces(read)
    expect(faces.map(face => face.kind), '一格只画一族，不许顺手替别格说话').toEqual([kind])
    expect(faces[0].headline.length).toBeGreaterThan(6)
    expect(faces[0].detail).toContain('管理员')
  })

  it('三格三句话两两不同：不许一条红文案兜三格', () => {
    const voices = cases.map(([, read]) => voicesOf(read)[0])
    expect(voices).toHaveLength(3)
    expect(new Set(voices).size, '三格并成同一句就是判据③点名的假话').toBe(3)
    for (const voice of voices) expect(voice).not.toMatch(BARE_CODE)
  })

  it('三格同时不对劲：三张脸、顶栏说得出几格，一句都不并', () => {
    const read = health([EMBEDDING_MODEL_MISSING, QUEUE_UNAVAILABLE, 'users_read_only'])
    const faces = runtimeFaces(read)
    expect(faces.map(face => face.kind).sort()).toEqual(['embedding', 'queue', 'readOnly'])
    expect(new Set(voicesOf(read)).size).toBe(3)
    expect(modelState(read)).toBe('degraded')
    expect(modelStatusText(read)).toContain('3 格')
  })

  it('降级一律不许落 ready：顶栏那句里不许出现「就绪」', () => {
    for (const [, read] of cases) {
      expect(modelState(read), `${read.problems[0]} 那一格不许报绿`).toBe('degraded')
      const text = modelStatusText(read)
      expect(text).not.toBe(MODEL_STATE_TEXT.ready)
      expect(text.startsWith(MODEL_STATE_TEXT.degraded), '顶栏那句得自己说清是降级').toBe(true)
      expect(text, '降级那句不许混进「就绪」二字').not.toContain('就绪')
    }
  })

  it('权重缺失仍是 down，且那一格不在 runtimeFaces 里重复画（同屏两句重复话）', () => {
    const read = health([MODEL_NOT_AVAILABLE])
    expect(modelState(read)).toBe('down')
    expect(modelStatusText(read)).toBe(MODEL_STATE_TEXT.down)
    expect(runtimeFaces(read)).toEqual([])
  })

  it('读不到就是读不到：一张脸都不画，也不报绿', () => {
    for (const bad of [null, undefined, {}, { problems: null }, { problems: 'x' }]) {
      expect(runtimeFaces(bad)).toEqual([])
      expect(modelState(bad)).toBe('unknown')
    }
    expect(modelStatusText(null)).toBe(MODEL_STATE_TEXT.unknown)
  })
})

describe('乙 · 认得出的每一族（反证：句子并格或名字丢失 ⇒ 本组红）', () => {
  it('码 → 族：一枚码只归一族', () => {
    expect(problemFamily(MODEL_NOT_AVAILABLE)).toBe('model')
    expect(problemFamily(EMBEDDING_MODEL_MISSING)).toBe('embedding')
    expect(problemFamily(QUEUE_UNAVAILABLE)).toBe('queue')
    expect(problemFamily(USERS_STORE_NOT_PERSISTENT)).toBe('store')
    expect(problemFamily('user_profiles_read_only')).toBe('readOnly')
    expect(problemFamily('postgres_unavailable')).toBe('dependency')
    expect(problemFamily('brand_new_fault')).toBe('other')
    expect(problemFamily('')).toBe('other')
  })

  it('三枚依赖各是一张脸，名字用人话说，裸码名一个都不上屏', () => {
    const faces = dependencyFaces([
      'postgres_unavailable', 'redis_not_configured', 'ollama_degraded',
    ])
    expect(faces).toHaveLength(3)
    expect(new Set(faces.map(face => `${face.headline}${face.detail}`)).size).toBe(3)
    expect(faces.map(face => face.label)).toEqual([
      '主数据库连不上', '队列与缓存服务没配置', '本机模型服务应答降级',
    ])
    for (const face of faces) expect(`${face.headline}${face.detail}`).not.toMatch(BARE_CODE)
  })

  it('只读那一格念得出受影响的格子（后端名单说了算，前端不重算判定）', () => {
    const face = readOnlyFace(['memories_read_only', 'knowledge_graph_read_only'])
    expect(face.kind).toBe('readOnly')
    expect(face.headline).toContain('长期记忆')
    expect(face.headline).toContain('知识图谱')
    expect(face.detail).toContain('重启就可能丢')
    expect(readOnlyFace([]).label).toBe('只读保护')
  })

  it('算力那一格：只有后端真记了降级码才有脸，unknown 不许说成故障', () => {
    expect(computeFace(null)).toBe(null)
    expect(computeFace({ problems: [] })).toBe(null)
    expect(computeFace({ problems: [], computeKind: 'unknown', computeErrorCode: '' })).toBe(null)
    const cpu = computeFace({
      problems: [], computeKind: 'cpu', computeErrorCode: 'model_unavailable', computeAgeSeconds: 42,
    })
    expect(cpu.kind).toBe('compute')
    expect(cpu.headline).toContain('CPU')
    expect(modelState({ problems: [], computeKind: 'cpu', computeErrorCode: 'model_unavailable' }))
      .toBe('degraded')
  })
})

describe('丙 · 认不出来的那一格也要开口（反证：改成闭嘴 ⇒ 本组红）', () => {
  it('后端新加一格时界面说「还不认识」，而不是继续报绿', () => {
    const read = health(['vector_index_rebuilding'])
    expect(modelState(read)).toBe('degraded')
    const faces = runtimeFaces(read)
    expect(faces).toHaveLength(1)
    expect(faces[0].kind).toBe('other')
    expect(faces[0].headline).toContain('还不认识')
    expect(faces[0].detail).toContain('报给运维')
  })

  it('两枚陌生码并成一行，但那一句报得出枚数：把两格说成一格也是假话', () => {
    const read = health(['memories_read_only', 'users_read_only', 'brand_new_a', 'brand_new_b'])
    const faces = runtimeFaces(read)
    expect(faces.map(face => face.kind)).toEqual(['readOnly', 'other'])
    expect(faces[1].headline).toContain('2 格')
    expect(new Set(voicesOf(read)).size, '留下的每一行都得是自己的那句话').toBe(2)
  })
})

describe('丁 · 面板接线：那一串脸真的由 /health/details 驱动（反证：拆掉 computed ⇒ 本组红）', () => {
  it('真 fetchRuntimeHealth 打到 /health/details，降级读数落到面板的那份名单上', async () => {
    installDomStubs()
    const b = await mountPanel()
    http.get.mockResolvedValue({ data: health([EMBEDDING_MODEL_MISSING, QUEUE_UNAVAILABLE]) })
    await b.refreshRuntimeHealth()
    expect(http.get).toHaveBeenCalledWith('/health/details', expect.any(Object))
    expect(b.runtimeHealth.value.problems).toEqual([EMBEDDING_MODEL_MISSING, QUEUE_UNAVAILABLE])
    expect(b.runtimeFaceList.value.map(face => face.kind)).toEqual(['embedding', 'queue'])
    expect(b.modelStateValue.value).toBe('degraded')
    expect(b.modelStateText.value).toContain('降级')
    expect(b.modelStateText.value).not.toContain('就绪')
  })

  it('健康接口一次没读到时界面画「状态未知」，绝不画「本地模型就绪」', async () => {
    const html = await renderToString(h({ render: () => h(ChatPanel) }))
    expect(html).toContain(MODEL_STATE_TEXT.unknown)
    expect(html).not.toContain(MODEL_STATE_TEXT.ready)
    expect(html, '没有读数就没有脸：一张降级脸都不许凭空画出来')
      .not.toContain('data-testid="runtime-face"')
  })

  it('每一族各画一行，逐行带着自己的 data-kind（不是一句笼统的红）', () => {
    expect(panel.match(/data-testid="runtime-faces"/g)).toHaveLength(1)
    expect(panel).toMatch(/v-if="runtimeFaceList\.length"/)
    expect(panel).toMatch(/v-for="face in runtimeFaceList"[\s\S]{0,200}?data-kind="face\.kind"/)
    expect(panel).toMatch(/const runtimeFaceList = computed\(\(\) => runtimeFaces\(runtimeHealth\.value\)\)/)
    expect(panel.match(/data-testid="model-degraded-notice"/g)).toHaveLength(1)
  })
})