/**
 * 顶栏「本地模型」那块脸的真假判据（总控自办）。
 *
 * 起因是硬事实：演示机上 Ollama 的 model_count=0、/health/details 的 problems 里有
 * model_not_available，而顶栏照样是绿点 +「本地模型」——这属于计划里要点名杀的「假装健康」。
 *
 * 三条腿（照仓库现有做法，node + @vue/server-renderer，没有 jsdom 也不 npm i）：
 *   ① 真逻辑：只把 lib/http 的网络层换成假实现，fetchRuntimeHealth / modelState / modelStatusText
 *      跑的是真代码——成功解析、失败回落 null、60 秒缓存、带外 force 各钉一条。
 *   ② 三档语义：读不到健康接口 = unknown，**不许回落到 ready**（这条最容易写错，也最贵）。
 *   ③ 源码形状：SSR 不跑 onMounted，「未就绪提示条」要等一次真失败才出现，node 里打不到那一层，
 *      于是钉住渲染路径唯一、且明说答案是检索原文；像素覆盖归 tests/visual。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn() } }
})

import { http } from '../../lib/http'
import {
  MODEL_NOT_AVAILABLE,
  MODEL_STATE_TEXT,
  fetchRuntimeHealth,
  modelState,
  modelStatusText,
  resetRuntimeHealthCache,
} from '../../lib/health.js'

const source = (rel) => readFileSync(new URL(rel, import.meta.url), 'utf8')

const degraded = {
  status: 'degraded',
  problems: [MODEL_NOT_AVAILABLE],
  model: { name: 'qwen2.5:14b', source: 'configured' },
}
const healthy = { status: 'ok', problems: [], model: { name: 'qwen2.5:14b', source: 'detected' } }

beforeEach(() => {
  resetRuntimeHealthCache()
  http.get.mockReset()
})

describe('① 真逻辑：读健康接口', () => {
  it('degraded 载荷解析成 problems + 模型名', async () => {
    http.get.mockResolvedValue({ status: 200, data: degraded })
    const got = await fetchRuntimeHealth()
    expect(http.get).toHaveBeenCalledWith('/health/details', expect.any(Object))
    expect(got.problems).toEqual([MODEL_NOT_AVAILABLE])
    expect(got.modelName).toBe('qwen2.5:14b')
    expect(modelState(got)).toBe('down')
  })

  it('接口 500 / 抛异常一律返回 null,并把缓存一起作废（下次还会真读）', async () => {
    http.get.mockRejectedValue(new Error('boom'))
    await expect(fetchRuntimeHealth()).resolves.toBeNull()
    expect(modelState(null)).toBe('unknown')
    http.get.mockResolvedValue({ status: 200, data: healthy })
    await expect(fetchRuntimeHealth()).resolves.toMatchObject({ status: 'ok' })
  })

  it('60 秒内第二次调用不再打网络；force 才穿透', async () => {
    http.get.mockResolvedValue({ status: 200, data: healthy })
    await fetchRuntimeHealth()
    await fetchRuntimeHealth()
    expect(http.get).toHaveBeenCalledTimes(1)
    await fetchRuntimeHealth({ force: true })
    expect(http.get).toHaveBeenCalledTimes(2)
  })

  it('载荷形状不对（非对象 / problems 缺失）也回落到 null / unknown', async () => {
    http.get.mockResolvedValue({ status: 200, data: 'not-an-object' })
    await expect(fetchRuntimeHealth({ force: true })).resolves.toBeNull()
    expect(modelState({ status: 'ok' })).toBe('unknown')
  })
})

describe('② 三档语义：不确定不是坏消息,画成健康才是', () => {
  it('problems 含 model_not_available 才是 down,空数组才是 ready', () => {
    expect(modelState({ problems: [MODEL_NOT_AVAILABLE] })).toBe('down')
    expect(modelState({ problems: [] })).toBe('ready')
  })

  it('null / undefined / 形状缺失全部落 unknown,一个都不许落 ready,也不许抛', () => {
    for (const bad of [null, undefined, {}, { problems: null }, { problems: 'x' }, { status: 'ok' }]) {
      expect(() => modelState(bad)).not.toThrow()
      expect(modelState(bad)).toBe('unknown')
    }
  })

  it('未就绪与未知的文案里不许出现「就绪」二字', () => {
    // 「未就绪」里含着「就绪」四个字,所以判据只能钉在整句上:未就绪与未知都不等于就绪那句。
    expect(MODEL_STATE_TEXT.down).toContain('未就绪')
    expect(MODEL_STATE_TEXT.down).not.toBe(MODEL_STATE_TEXT.ready)
    expect(MODEL_STATE_TEXT.unknown).not.toContain('就绪')
    expect(modelStatusText({ problems: [MODEL_NOT_AVAILABLE] })).toBe(MODEL_STATE_TEXT.down)
    expect(modelStatusText(null)).toBe(MODEL_STATE_TEXT.unknown)
  })
})

describe('③ 源码形状：顶栏由状态驱动', () => {
  const panel = source('../ChatPanel.vue')

  it('写死的绿点类没有了,点和文案同源于 modelStateValue', () => {
    expect(panel).not.toMatch(/class="chat-dot online"/)
    expect(panel).toMatch(/:class="`chat-dot--\$\{modelStateValue\}`"[^>]*data-testid="model-dot"/)
    expect(panel).toMatch(/:class="`model-status--\$\{modelStateValue\}`"/)
    expect(panel).toMatch(/data-testid="model-status"/)
  })

  it('降级提示条只有一条出现路径:down,且明说答案是检索原文', () => {
    expect(panel.match(/data-testid="model-degraded-notice"/g)).toHaveLength(1)
    expect(panel).toMatch(/v-if="modelStateValue === 'down'"/)
    const notice = panel.split('data-testid="model-degraded-notice">')[1].split('</div>')[0]
    expect(notice).toContain('原文')
    expect(notice).toContain('模型')
  })

  it('挂载即拉一次健康度,不等用户动作', () => {
    expect(panel).toMatch(/onMounted\(\(\) => \{\s*refreshRuntimeHealth\(\)/)
  })

  it('状态色一律借 token,不许再把绿色写死进组件（色值棘轮只准降）', () => {
    const block = panel.slice(panel.indexOf('.chat-dot {'), panel.indexOf('.model-degraded-notice {') + 240)
    expect(block).not.toMatch(/#[0-9a-fA-F]{3,6}\b/)
    expect(block).not.toMatch(/rgba\(/)
    expect(block).toMatch(/var\(--green\)/)
    expect(block).toMatch(/var\(--amber\)/)
    expect(block).toMatch(/var\(--muted\)/)
  })
})
