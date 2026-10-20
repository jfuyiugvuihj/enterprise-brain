/**
 * R198 · 排队轮询：只有「终止性判定」才停表，停的那一下要说人话
 *
 * 病灶（改前取证，ChatPanel.vue 行号取本件基点 e6d9ae6）：
 *   :830  const QUEUE_POLL_MS = 3000                       —— 实测定时间隔 3 秒
 *   :831  const QUEUE_SETTLED = ['done','cancelled','failed','expired'] —— 只有这四枚状态会 stop()
 *   :944  if (QUEUE_SETTLED.includes(read.status)) stop()  —— 停表只看「状态收敛」
 *   :945-947 catch (err) { queueFaults[key] = err }        —— 拿到错误只记 fault，【不停表】
 *   :957  entry.timer = setInterval(tick, QUEUE_POLL_MS)   —— 于是 404 / 403 那一轮每 3 秒再打一枪
 *   :891-901 queueFaceOf：只有【从来没有成功读数】时才画 queuePollFailedFace（:896）；
 *            只要此前读到过一次 queued，:900 就永远画那张「排队中，前面还有 N 人」。
 * 也就是说：一枚失效页签 = 1200 发/小时被后端拒绝的读数 + 屏上永远停在「排队中」。
 *
 * 环境仍是 node（仓库没有 jsdom / @vue/test-utils，也不 npm i）。手法沿用 r171 / r197：
 *   取真身 —— 直接把 ChatPanel 编译产物里那份 setup 挂进一枚宿主组件，用 vue 公开的
 *             createRenderer + 内存虚拟节点跑【真客户端生命周期】，所以 onMounted →
 *             restoreQueuedTurns → watchQueueTurn → setInterval 全是产品自己走的；
 *   换掉的 —— 只有网络层（vi.mock lib/http）与「元素怎么落地」那一层渲染器；
 *   时钟 —— vi.useFakeTimers()，一格 3 秒，不真等。
 * 屏上那一句话取两道证：queueFaceOf()（面板真正喂给 <QueueFace :face> 的那枚值）+ 真 QueueFace
 * 组件渲染出的 HTML。停表成功与否取证于「状态请求还发不发」，那是这件事唯一的物理表现。
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

import ChatPanel from '../ChatPanel.vue'
import QueueFace from '../QueueFace.vue'
import { TOKEN_KEY } from '../../lib/http'
import { http } from '../../lib/http'
import { normalizeError } from '../../lib/errcodes'
import { queuePollFailedFace } from '../../lib/provenance'
import { activeId, messages } from '../../lib/sessions'

const source = f => readFileSync(new URL(`../${f}`, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const panel = source('ChatPanel.vue')

const QUEUE_MS = 3000
const REQUEST_ID = 'req-a'
const SSR_CONTEXT_KEY = Symbol.for('v-scx')

// ==================== 网络层脚本 ====================

function axiosStatusError(status, detail) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    config: { url: `/queue/status/${REQUEST_ID}` },
    response: { status, data: detail === undefined ? {} : { detail } },
  })
}
/** 传输层真断网：axios 给的是 code=ERR_NETWORK + 有 request 无 response。 */
const networkError = () => Object.assign(new Error('Network Error'), {
  isAxiosError: true, code: 'ERR_NETWORK', request: {}, config: { url: `/queue/status/${REQUEST_ID}` },
})
/** axios 超时：lib/errcodes.js:464 认 ECONNABORTED / ETIMEDOUT 这一族。 */
const timeoutError = () => Object.assign(new Error('timeout of 30000ms exceeded'), {
  isAxiosError: true, code: 'ECONNABORTED', request: {}, config: { url: `/queue/status/${REQUEST_ID}` },
})

const statusOk = (over = {}) => ({ data: { status: 'queued', request_id: REQUEST_ID, position: 3, ...over } })

/** 逐发应答 /queue/status；名单用尽后重复最后一发（瞬断一族要连打多久都有话说）。 */
function pollScript(...replies) {
  let at = 0
  return async (url) => {
    const target = String(url)
    if (target.startsWith('/queue/status')) {
      const reply = replies[Math.min(at, replies.length - 1)]
      at += 1
      if (reply instanceof Error) throw reply
      return reply
    }
    if (target === '/queue/stats') return { data: { queue_length: 1, processing: 0 } }
    if (target === '/health/details') return { data: { problems: [] } }
    return { data: {} }
  }
}

const statusCalls = () => http.get.mock.calls.filter(call => String(call[0]).startsWith('/queue/status')).length
const allCalls = () => http.get.mock.calls.length

// ==================== 无 DOM 的真生命周期 ====================

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

/** 内存 localStorage 替身（node 没有）：面板与 lib/sessions 只用到这几个方法。 */
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

let mounted = null

const settle = async () => {
  await nextTick()
  await vi.advanceTimersByTimeAsync(0)
  await nextTick()
}

/** 挂上一枚「已经排上队」的轮次：这一轮没正文，所以面板有理由一直盯状态。 */
function queuedTurn(mid = 'r198-turn-a') {
  return { role: 'assistant', content: '', steps: [], mid, queue: { requestId: REQUEST_ID, status: 'queued' } }
}

async function mountPanel(turns, replies) {
  installStorage({ [TOKEN_KEY]: 'jwt-live' })
  activeId.value = 'r198-session'
  messages.value = turns
  http.get.mockImplementation(pollScript(...replies))
  let instance = null
  const errors = []
  const pushed = []
  const app = createApp({
    __name: 'R198ChatPanelHost',
    setup: ChatPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div', { id: 'r198-host' })
    },
  })
  app.config.warnHandler = () => {}
  app.config.errorHandler = err => errors.push(err)
  app.provide(SSR_CONTEXT_KEY, {})
  app.provide(routeLocationKey, reactive({ name: 'chat', path: '/chat', query: {}, params: {}, meta: {}, fullPath: '/chat', hash: '' }))
  app.provide(routerKey, {
    push: target => { pushed.push(target); return Promise.resolve() },
    replace: target => { pushed.push(target); return Promise.resolve() },
  })
  app.mount(node('#root'))
  mounted = { app, errors, pushed, state: instance.setupState }
  await settle()
  return mounted
}

/** 这一轮此刻的脸：面板喂给 <QueueFace :face> 的就是这枚值，一个字都不另算。 */
const faceOfTurn = (turn, index = 0) => mounted.state.queueFaceOf(turn, index)

afterEach(() => {
  mounted?.app.unmount()
  mounted = null
  vi.useRealTimers()
  http.get.mockReset()
})

beforeEach(() => {
  vi.useFakeTimers()
  messages.value = []
  activeId.value = ''
})

describe('甲 · 判据① 病灶复现：终止性判定必须叫停（改前逐枚红）', () => {
  it('甲1 404 resource_not_found 之后不许再发第二发状态请求', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [axiosStatusError(404, 'resource_not_found')])
    expect(statusCalls(), '挂载当轮应当恰好打一发状态请求').toBe(1)
    await vi.advanceTimersByTimeAsync(QUEUE_MS)
    expect(statusCalls(), 'R198 判据②：404 resource_not_found 是终止性判定，第 2 发不许再发生').toBe(1)
  })

  it('甲2 停表是永久的：连推 60 秒（20 个周期）也不许复活', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [axiosStatusError(404, 'resource_not_found')])
    const stopped = allCalls()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(allCalls(), `停表之后这一轮总共只许发 ${stopped} 发（含 /queue/stats），实际 ${allCalls()} 发`).toBe(stopped)
  })

  it('甲3 403 permission_denied 同样叫停', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [axiosStatusError(403, 'permission_denied')])
    expect(statusCalls(), '挂载当轮打一发').toBe(1)
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
    expect(statusCalls(), 'R198 判据②：403 permission_denied 之后不许继续轮').toBe(1)
  })

  it('甲4 401 authentication_required 叫停，且不许自己造登录失效通路', async () => {
    const turn = queuedTurn()
    const { pushed, errors } = await mountPanel([turn], [axiosStatusError(401, 'authentication_required')])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
    expect(statusCalls(), 'R198 判据②：401 之后不许继续轮').toBe(1)
    // 既有通路只有一条：lib/http.js 的响应拦截器 -> handleUnauthorized -> App.vue 订阅。
    // 面板这一层既不许自己清会话，也不许自己换屏（那会变成第二套跳转/提示）。
    expect(globalThis.localStorage.getItem(TOKEN_KEY), '面板不许自己清会话：令牌仍在原处').toBe('jwt-live')
    expect(pushed, '面板不许自己跳登录页').toEqual([])
    expect(errors, '组件生命周期内不许抛错').toEqual([])
  })

  it('甲5 先读到过 queued、随后 404：屏上不许永远停在「排队中」', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [statusOk(), axiosStatusError(404, 'resource_not_found')])
    expect(faceOfTurn(turn).headline, '第一发读成功了：此刻说位次是对的').toContain('前面还有 2 人')
    await vi.advanceTimersByTimeAsync(QUEUE_MS)
    const face = faceOfTurn(turn)
    expect(face.headline, 'R198 判据③：叫停之后这一轮不许还写着「排队中」').not.toMatch(/前面还有 \d+ 人/)
    expect(face.headline).not.toMatch(/转入后台排队/)
    expect(face.ahead, '停表那一轮不许再报位次').toBeNull()
  })
})

describe('乙 · 判据② 另一半：瞬断、超时、5xx 一律不许停表（既存正确行为，一枚都不许削弱）', () => {
  it('乙1 网络错误连断 5 个周期仍然在轮，脸仍然是「这次没读到」', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [networkError()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 4)
    expect(statusCalls(), 'R198 判据②：瞬断不能杀死排队状态的显示，5 个周期应当仍有第 5 发').toBe(5)
    const face = faceOfTurn(turn)
    expect(face.kind, '瞬断那一轮仍是「读不到」，不是「停表」').toBe('unreadable')
    expect(face.detail, '瞬断脸必须继续说「每 3 秒再读一次」——此刻这句是真话').toMatch(/每 3 秒再读一次/)
  })

  it('乙2 axios 超时不许停表', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [timeoutError()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 2)
    expect(statusCalls(), 'R198 判据②：超时是瞬断，不许停表').toBe(3)
  })

  it('乙3 5xx 与后端故障码不许停表', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [
      axiosStatusError(503, { code: 'queue_unavailable', message: '排队系统当前不可用。' }),
      axiosStatusError(500, 'internal_error'),
    ])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
    expect(statusCalls(), 'R198 判据②：503 / 500 都要继续轮，等后端缓过来').toBe(4)
  })

  it('乙4 瞬断两次后读数回来：这一轮要活回「排队中」，不许留下停表痕', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [networkError(), networkError(), statusOk({ position: 2 })])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 2)
    const face = faceOfTurn(turn)
    expect(statusCalls()).toBe(3)
    expect(face.kind, '读数回来了就不许还挂着「读不到」').toBe('queued')
    expect(face.headline).toContain('前面还有 1 人')
    await vi.advanceTimersByTimeAsync(QUEUE_MS)
    expect(statusCalls(), '恢复之后仍在轮：一次成功读数不该把表停掉').toBe(4)
  })

  it('乙5 403 authorization_unavailable：R202 改判为必须叫停', async () => {
    // 本件交付时这一格钉的是「判据②名单外一律不停表」，同时把「要不要收进名单」交给总控
    // 裁定（交工报告「同形只报不动」）。总控在并树提交 7b0ae26 里裁定：同一族，收名单 = R202
    // 一行改动 + 改判乙5，出处 app/api/v1/chat.py 那两枚载荷拒绝出口（今天的行号 759 / 763，
    // 本件旧注释里的 714 / 718 已随 R179 的落账改动位移）。判据②的双条件没有放宽，
    // 反向那半由 r202-queue-poll-stop-authz.test.js 的乙组钉着：名单外的 403 照旧不许停表。
    const turn = queuedTurn()
    await mountPanel([turn], [axiosStatusError(403, 'authorization_unavailable')])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 2)
    expect(statusCalls(), 'R202 判据①：与 404 同形，第 1 发之后就不许再打一枪').toBe(1)
  })
})

describe('丙 · 判据③ 停的那一下要说人话', () => {
  it('丙1 停表脸说得出「不再查询」，句子出自 errcodes 字典（同源措辞）', async () => {
    const error = axiosStatusError(404, 'resource_not_found')
    const turn = queuedTurn()
    await mountPanel([turn], [error])
    const face = faceOfTurn(turn)
    expect(face.headline, '停表那一轮必须说一句明确的话').toMatch(/停止|不再/)
    expect(face.headline).toMatch(/排队|这一轮/)
    expect(face.detail, '正文必须是字典里那句人话（normalizeError 唯一生产者）').toContain(normalizeError(error).message)
    expect(face.retryable, '三枚终止性判定都不可重试，字典说了算，界面不自造重试按钮').toBe(false)
  })

  it('丙2 停表脸与既有失败脸同一形状，但 kind 必须是新态', async () => {
    const error = axiosStatusError(403, 'permission_denied')
    const turn = queuedTurn()
    await mountPanel([turn], [error])
    const face = faceOfTurn(turn)
    expect(Object.keys(face).sort(), 'R198 判据③：复用现成 face 形状，不另起一套字段')
      .toEqual(Object.keys(queuePollFailedFace(error)).sort())
    expect(face.kind).not.toBe('unreadable')
    expect(face.kind).toMatch(/stop/)
  })

  it('丙3 停表那张脸不许再说「每 3 秒再读一次」，瞬断那张必须说', async () => {
    const stoppedTurn = queuedTurn('r198-stopped')
    await mountPanel([stoppedTurn], [axiosStatusError(401, 'authentication_required')])
    expect(faceOfTurn(stoppedTurn).detail, '停表之后这句就是假话').not.toMatch(/每 3 秒再读一次/)
    expect(faceOfTurn(stoppedTurn).detail, '401 那一轮要说的是登录失效那句（字典原文）')
      .toContain('登录状态已失效')
  })

  it('丙4 真 QueueFace 上屏：停表那一轮画出的就是那句话，且不带裸码名', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [axiosStatusError(403, 'permission_denied')])
    const face = faceOfTurn(turn)
    const html = await renderToString(h(QueueFace, { face, stats: null }))
    expect(html).toContain('data-testid="queue-face"')
    expect(html).toContain('当前账号没有这项权限')
    expect(html).toMatch(/data-kind="[\w-]*stop[\w-]*"/)
    expect(html, '给人看的句子里不许夹 snake_case 码名（V6 裸码闸门同一条口径）')
      .not.toMatch(/[\u4e00-\u9fff][^<>]*\b[a-z][a-z0-9]*(_[a-z0-9]+)+/)
  })

  it('丙5 新增这块零裸色：组件文件里不许出现 hex / rgba', async () => {
    const from = panel.indexOf('function queuePollStopper')
    expect(from, 'R198 正解：面板必须有一枚「终止性判定」的判据函数').toBeGreaterThan(-1)
    const block = panel.slice(from, panel.indexOf('function watchQueueTurn'))
    expect(block).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(block).not.toMatch(/rgba?\(/)
    expect(block).not.toMatch(/hsla?\(/)
  })
})

describe('丁 · 既存正确行为一枚都不许改坏', () => {
  for (const status of ['done', 'cancelled', 'failed', 'expired']) {
    it(`丁1 状态收敛 '${status}' 仍然叫停（QUEUE_SETTLED 原有语义）`, async () => {
      const turn = queuedTurn(`r198-${status}`)
      await mountPanel([turn], [{ data: { status, request_id: REQUEST_ID } }])
      await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
      expect(statusCalls(), `QUEUE_SETTLED 里的 ${status} 本来就该停表`).toBe(1)
    })
  }

  it('丁2 done 带回 result 仍然把答案补进这条回答', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [{ data: { status: 'done', result: '限额以内据实报销。' } }])
    expect(messages.value[0].content).toBe('限额以内据实报销。')
    await vi.advanceTimersByTimeAsync(QUEUE_MS)
    expect(statusCalls()).toBe(1)
  })

  it('丁3 卸载仍然停表：面板不在了就不许继续打接口', async () => {
    const turn = queuedTurn()
    const { app } = await mountPanel([turn], [networkError()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 2)
    const before = statusCalls()
    expect(before).toBe(3)
    app.unmount()
    mounted = null
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 10)
    expect(statusCalls(), '卸载之后计数必须冻住').toBe(before)
  })

  it('丁4 只有一枚 3 秒时钟：不许引入第二套 setTimeout 轮询', () => {
    expect(panel).toMatch(/const QUEUE_POLL_MS = 3000/)
    expect(panel.match(/setInterval\(tick, QUEUE_POLL_MS\)/g)).toHaveLength(1)
    const watch = panel.slice(panel.indexOf('function watchQueueTurn'), panel.indexOf('function stopQueueWatches'))
    expect(watch, '排队轮询只准用那一枚 setInterval 时钟').not.toMatch(/setTimeout/)
  })
})