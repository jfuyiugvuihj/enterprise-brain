/**
 * R202 · 停表名单漏的那一枚：403 authorization_unavailable
 *
 * 病灶（改前取证，本件基点 4dcbd30）：
 *   ChatPanel.vue:840-844 QUEUE_POLL_STOPPERS 只有三格（404 resource_not_found /
 *     403 permission_denied / 401 authentication_required），而 :851 的匹配是
 *     item.status === status && item.code === code 双条件；
 *   app/api/v1/chat.py::_authorize_queue_task 实际有五枚拒绝出口（:750 401 / :753 404 /
 *     :759 与 :763 两枚 403 authorization_unavailable / :765 403 permission_denied），
 *     其中 :759（任务载荷读不出 JSON）与 :763（载荷里没有 principal.user_id）这一族
 *     永远匹配不上名单 ⇒ 一枚再也读不回来的任务，页签照样每 3 秒打一枪，
 *     后端 R194 起的审计台账每笔拒绝记一行——正是 R198 要治的那笔噪声，只漏了入口这一格。
 *
 * 环境仍是 node（仓库没有 jsdom / @vue/test-utils，也不 npm i）。手法沿用 r171 / r197 / r198：
 *   取真身 —— 把 ChatPanel 编译产物里那份 setup 挂进一枚宿主组件，用 vue 公开的
 *             createRenderer + 内存虚拟节点跑真客户端生命周期，于是 onMounted →
 *             restoreQueuedTurns → watchQueueTurn → setInterval 全是产品自己走的路；
 *   换掉的 —— 只有网络层（vi.mock lib/http）与「元素怎么落地」那一层渲染器；
 *   时钟 —— vi.useFakeTimers()，一格 3 秒，不真等。
 * 取证口径：停没停表只看「状态请求还发不发」，那是这件事唯一的物理表现；
 * 屏上那一句话取两道证 —— queueFaceOf()（面板喂给 <QueueFace :face> 的那枚值）+ 真组件渲染的 HTML。
 * 判据③「脸要带归属」在这里可机器验证：正文必须等于 errcodes 字典里 authorization_unavailable
 * 那一格的原文（唯一真相源），既不许是 done-no-result 那句「后端说这一轮跑完了」——
 * 后端从没说过这一轮跑完过，复用到语义就是假话——也不许留着「每 3 秒再读一次」。
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
import { activeId, messages } from '../../lib/sessions'

const source = f => readFileSync(new URL(`../${f}`, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const panel = source('ChatPanel.vue')

const QUEUE_MS = 3000
const REQUEST_ID = 'req-r202-a'
const SSR_CONTEXT_KEY = Symbol.for('v-scx')
// chat.py:759 与 :763 两枚出口回的是同一个 detail，界面认的是「status + code」这一格
const AUTHZ = 'authorization_unavailable'

// ==================== 网络层脚本 ====================

function httpError(status, detail) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    config: { url: `/queue/status/${REQUEST_ID}` },
    response: { status, data: detail === undefined ? {} : { detail } },
  })
}
/** 形状 2（ErrorEnvelope）：同一枚判定在野外的另一种身体，判据不许因为形状而分叉。 */
const authzEnvelopeError = () => httpError(403, {
  code: AUTHZ, message: '暂时确认不了你的数据权限范围。', retryable: true,
})
/** 传输层真断网：axios 给的是 code=ERR_NETWORK + 有 request 无 response。 */
const networkError = () => Object.assign(new Error('Network Error'), {
  isAxiosError: true, code: 'ERR_NETWORK', request: {}, config: { url: `/queue/status/${REQUEST_ID}` },
})
/** axios 超时：lib/errcodes.js 认 ECONNABORTED / ETIMEDOUT 这一族。 */
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
const statsCalls = () => http.get.mock.calls.filter(call => String(call[0]) === '/queue/stats').length
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
function queuedTurn(mid = 'r202-turn-a') {
  return { role: 'assistant', content: '', steps: [], mid, queue: { requestId: REQUEST_ID, status: 'queued' } }
}

async function mountPanel(turns, replies) {
  installStorage({ [TOKEN_KEY]: 'jwt-live' })
  activeId.value = 'r202-session'
  messages.value = turns
  http.get.mockImplementation(pollScript(...replies))
  let instance = null
  const errors = []
  const pushed = []
  const app = createApp({
    __name: 'R202ChatPanelHost',
    setup: ChatPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div', { id: 'r202-host' })
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

describe('甲 · 判据① 病灶复现：403 authorization_unavailable 必须叫停（改前逐枚红）', () => {
  it('甲1 第 1 发领到这一族，第 2 发就不许再发', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [httpError(403, AUTHZ)])
    expect(statusCalls(), '挂载当轮应当恰好打一发状态请求').toBe(1)
    await vi.advanceTimersByTimeAsync(QUEUE_MS)
    expect(statusCalls(), 'R202 判据①：载荷读不出 JSON / 没登记 principal 的任务永远不会自己变好，'
      + '继续轮只是给后端审计台账多记一笔被拒').toBe(1)
  })

  it('甲2 停表是永久的：连推 120 秒（40 个周期）也不许复活', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [httpError(403, AUTHZ)])
    const frozen = allCalls()
    await vi.advanceTimersByTimeAsync(120_000)
    expect(allCalls(), `停表之后这一轮总共只许发 ${frozen} 发（含 /queue/stats），实际 ${allCalls()} 发`).toBe(frozen)
  })

  it('甲3 同一枚判定的形状 2（ErrorEnvelope）也叫停：停不停只看 status + code，不看身体', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [authzEnvelopeError()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
    expect(statusCalls(), 'chat.py 那两枚出口今天是形状 1，但同一枚 code 走信封回来时不许漏判').toBe(1)
  })

  it('甲4 先读到过 queued、第 2 发才被拒：停在这第 2 发，屏上不许还画着「排队中」', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [statusOk(), httpError(403, AUTHZ)])
    expect(statusCalls(), '第一发是成功读数，表当然还在走').toBe(1)
    await vi.advanceTimersByTimeAsync(QUEUE_MS)
    expect(statusCalls(), '第二发领到这一族 ⇒ 第 2 发就是最后一发').toBe(2)
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 4)
    expect(statusCalls(), '叫停之后 12 秒内一发都不许再有').toBe(2)
    const face = faceOfTurn(turn)
    expect(face.kind, '此前读到过 queued 更要走停表脸，否则屏幕上永远停在「前面还有 2 人」').not.toBe('queued')
    expect(face.ahead, '位次读数不再更新，画一个静止的数字就是骗人').toBeNull()
  })

  it('甲5 判据③ 停表脸带归属：话出自字典那一格，既不是 done-no-result 也不是瞬断脸', async () => {
    const error = httpError(403, AUTHZ)
    const turn = queuedTurn()
    await mountPanel([turn], [error])
    const face = faceOfTurn(turn)
    const dictionary = normalizeError(error)
    expect(face.kind, '停表是一枚独立状态，不许借「跑完了但没带回答案」那张脸（后端从没说这一轮跑完过）')
      .not.toBe('done-no-result')
    expect(face.kind).toMatch(/stop/)
    expect(face.headline).toMatch(/停止|不再/)
    expect(face.headline, '既然停了，句子里就不许再出现「跑完/完成」这类读数收敛的说法')
      .not.toMatch(/跑完|已完成/)
    expect(dictionary.code, '钉住前提：这一族归一后的 code 就是名单里那一格').toBe(AUTHZ)
    expect(face.detail, '归属：正文必须是 errcodes 字典里这一格的原文，面板不另造一句解释')
      .toContain(dictionary.message)
    expect(face.detail).toContain('数据权限范围')
    expect(face.detail, '表已经停了，这句就是假话（R198 判据③同一条规矩）').not.toMatch(/每 3 秒再读一次/)
    expect(face.detail).not.toMatch(/读数里没带回答案/)
    expect(face.codeLabel, '已知码不脏屏：「错误码：xxx」小字只有 errorCodeLabel 一个生产者').toBe('')
    expect(face.retryable, '重试与否听字典的，界面不许自造第二套判断').toBe(dictionary.retryable)
    expect(face.tone).toBe('warn')
  })

  it('甲6 真 QueueFace 上屏：这一族的脸画出来的就是那句归属话，且不夹裸码名', async () => {
    const error = httpError(403, AUTHZ)
    const turn = queuedTurn()
    await mountPanel([turn], [error])
    const face = faceOfTurn(turn)
    const html = await renderToString(h(QueueFace, { face, stats: null }))
    expect(html).toContain('data-testid="queue-face"')
    expect(html).toMatch(/data-kind="[\w-]*stop[\w-]*"/)
    expect(html).toContain('数据权限范围')
    expect(html, '字典判这一族可恢复，屏上就要给出那个出口（与三枚终止性判定不同的地方）')
      .toContain('data-testid="queue-retry"')
    expect(html, '给人看的句子里不许夹 snake_case 码名（V6 裸码闸门同一条口径）')
      .not.toMatch(/[\u4e00-\u9fff][^<>]*\b[a-z][a-z0-9]*(_[a-z0-9]+)+/)
  })
})

describe('乙 · 判据② 双条件不许放宽：403 不是停表许可证', () => {
  it('乙1 403 account_unavailable（别名码 principal_inactive）不许停表', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [httpError(403, 'principal_inactive')])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 2)
    expect(normalizeError(httpError(403, 'principal_inactive')).code, '钉住前提：这一格归一到 account_unavailable')
      .toBe('account_unavailable')
    expect(statusCalls(), '只看 status 就会把名单外的 403 一起判死，这一族今天照旧轮').toBe(3)
  })

  it('乙2 403 信封里的 account_unavailable 同样不停表', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [httpError(403, { code: 'account_unavailable', message: '这个账号已被停用。', retryable: false })])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
    expect(statusCalls(), '名单是按 (status, code) 逐格登记的，不是按状态段').toBe(4)
  })

  it('乙3 名单每一格都必须同时写 status 与 code', () => {
    const from = panel.indexOf('const QUEUE_POLL_STOPPERS')
    expect(from, '名单必须还在面板里（R198 正解）').toBeGreaterThan(-1)
    const list = panel.slice(from, panel.indexOf('/** 这一发失败算不算'))
    expect((list.match(/status:/g) || []).length, '每一格都得写 status').toBeGreaterThan(0)
    expect((list.match(/code:/g) || []).length, '每一格都得写 code：一格都不许多不许少')
      .toBe((list.match(/status:/g) || []).length)
    for (const code of ['resource_not_found', 'permission_denied', 'authentication_required', AUTHZ]) {
      expect(list, `R202 判据②：名单漏了 ${code}`).toContain(code)
    }
    const matcher = panel.slice(panel.indexOf('function queuePollStopper'), panel.indexOf('let queueWatches'))
    expect(matcher).toMatch(/item\.status === status\s*&&\s*item\.code === code/)
    expect(matcher, '匹配函数不许退化成只看 status').not.toMatch(/if\s*\(!?code\)/)
  })
})

describe('丙 · 判据④ 网络错误 / 超时 / 5xx 依旧不许停表（R198 那枚钉原位保留）', () => {
  it('丙1 真断网继续轮', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [networkError()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 2)
    expect(statusCalls(), 'R198 判据②：瞬断不能杀死排队状态显示').toBe(3)
    expect(faceOfTurn(turn).kind, '瞬断脸仍是 unreadable，不许被写成停表脸').toBe('unreadable')
  })

  it('丙2 axios 超时继续轮', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [timeoutError()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 2)
    expect(statusCalls()).toBe(3)
  })

  it('丙3 5xx 与后端故障码继续轮', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [
      httpError(503, { code: 'queue_unavailable', message: '排队系统当前不可用。' }),
      httpError(500, 'internal_error'),
    ])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
    expect(statusCalls(), '503 / 500 都要继续轮，等后端缓过来').toBe(4)
  })

  it('丙4 429 rate_limited 继续轮：被限流不等于这一轮读不回来', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [httpError(429, 'rate_limited')])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 2)
    expect(statusCalls(), '名单只收终止性判定，429 是「等一会儿再试」').toBe(3)
  })

  it('丙5 瞬断→读数回来→才被这一族叫停：停表判定与顺序无关', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [networkError(), statusOk({ position: 2 }), httpError(403, AUTHZ)])
    await vi.advanceTimersByTimeAsync(QUEUE_MS)
    expect(statusCalls()).toBe(2)
    expect(faceOfTurn(turn).kind, '读数回来那一轮必须活回「排队中」，不许留着上一次的痕').toBe('queued')
    await vi.advanceTimersByTimeAsync(QUEUE_MS)
    expect(statusCalls(), '第 3 发才领到终止性判定：停在这第 3 发').toBe(3)
    expect(statsCalls(), '全局等待人数那一笔也得跟着停：它打在同一个 tick 里').toBe(3)
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 5)
    expect(statusCalls()).toBe(3)
    expect(statsCalls()).toBe(3)
    expect(faceOfTurn(turn).kind).toMatch(/stop/)
  })
})

describe('丁 · R198 已有正确行为一枚都不许被这格改动碰坏', () => {
  for (const [status, detail] of [[404, 'resource_not_found'], [403, 'permission_denied'], [401, 'authentication_required']]) {
    it(`丁1 原有终止性判定 ${status} ${detail} 仍然一发叫停`, async () => {
      const turn = queuedTurn(`r202-${status}-${detail}`)
      await mountPanel([turn], [httpError(status, detail)])
      await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
      expect(statusCalls()).toBe(1)
      expect(faceOfTurn(turn).retryable, '这三枚按字典都是不可重试：不许因为加了一格就把它们改宽').toBe(false)
    })
  }

  for (const settled of ['done', 'cancelled', 'failed', 'expired']) {
    it(`丁2 状态收敛 '${settled}' 仍然叫停（QUEUE_SETTLED 原有语义）`, async () => {
      const turn = queuedTurn(`r202-${settled}`)
      await mountPanel([turn], [{ data: { status: settled, request_id: REQUEST_ID } }])
      await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
      expect(statusCalls()).toBe(1)
    })
  }

  it('丁3 卸载仍然停表：面板不在了就不许继续打接口', async () => {
    const turn = queuedTurn()
    const { app } = await mountPanel([turn], [statusOk()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 2)
    const before = statusCalls()
    expect(before).toBe(3)
    app.unmount()
    mounted = null
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 10)
    expect(statusCalls(), '卸载之后计数必须冻住').toBe(before)
  })

  it('丁4 只有一枚 3 秒时钟：这一格不许带出第二套轮询', () => {
    expect(panel).toMatch(/const QUEUE_POLL_MS = 3000/)
    expect(panel.match(/setInterval\(tick, QUEUE_POLL_MS\)/g)).toHaveLength(1)
  })

  it('丁5 组件这块零裸色：名单与停表脸里不许出现 hex / rgba / hsl', () => {
    const block = panel.slice(panel.indexOf('const QUEUE_POLL_STOPPERS'), panel.indexOf('function queuePollStoppedFace'))
    expect(block.length, '取到的是真实代码块').toBeGreaterThan(100)
    expect(block).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(block).not.toMatch(/rgba?\(/)
    expect(block).not.toMatch(/hsla?\(/)
  })
})
