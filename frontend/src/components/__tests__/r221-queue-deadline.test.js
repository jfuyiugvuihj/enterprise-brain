/**
 * R221 · 队轮询的两半：后端第五枚终态 + 前台等待上限
 *
 * 病灶（改前取证，ChatPanel.vue 行号取本件基点 4e29141）：
 *   :840  const QUEUE_SETTLED = ['done','cancelled','failed','expired'] —— 漏了 dead；
 *   :1010 if (QUEUE_SETTLED.includes(read.status)) stop()                —— 于是一发落进
 *          dead 的轮次永远不停表（:1029 那一枚 setInterval 一直打到页签关掉）；
 *   :1029 整条看门狗没有 deadline —— R218 读数 frontend_watch_has_no_deadline=true，
 *         前端侧 setTimeout / clearTimeout / Deadline 字样实测为零，屏上永远停在最后一次
 *         读数那张「前面还有 N 人」的 Spinner 脸上。
 * 后端真会写 dead 的三处出处：app/common/reliable_queue.py:248-251（rpush(dead_key) +
 * set(status,"dead")）、deploy/queue_worker.py:206（按 dead 补会话历史）、
 * app/api/v1/chat.py:3961（既不是 done 也不是 queued 时把这一枚原样交回前端）。
 *
 * 手法照 r198 / r202：环境是 node（仓库没有 jsdom / @vue/test-utils，也不许 npm i），
 * 把 ChatPanel 编译产物里那份真 setup 挂进宿主组件，用 createRenderer + 内存虚拟节点跑
 * 真客户端生命周期，所以 onMounted -> restoreQueuedTurns -> watchQueueTurn -> setInterval
 * 全是产品自己走的；换掉的只有网络层（vi.mock lib/http）与元素落地那一层。时钟用
 * vi.useFakeTimers()，一格 3 秒，不真等，也不打任何真接口。
 *
 * 两格反证钉（判据④）：甲组钉「dead 会停表并出现人话终态」，乙组钉「轮询必然带
 * deadline，且到点只收表、不判失败」。把修复分别摘掉，红只许落在这两组自己身上。
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
import { queueFace, queuePollFailedFace } from '../../lib/provenance'
import { activeId, messages } from '../../lib/sessions'

const source = f => readFileSync(new URL(`../${f}`, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const panel = source('ChatPanel.vue')

const QUEUE_MS = 3000
const REQUEST_ID = 'req-r221'
const SSR_CONTEXT_KEY = Symbol.for('v-scx')

// deadline 从面板源码里抠出来钉，不在这儿抄一份数字：抄了就只是「界面恰好等于测试」，
// 真把上限删掉这枚钉子反而会跟着绿（教训 #46）。
const deadlineMs = Number((/const QUEUE_WAIT_DEADLINE_MS = (\d+)/.exec(panel) || [])[1] ?? NaN)
const pollMs = Number((/const QUEUE_POLL_MS = (\d+)/.exec(panel) || [])[1] ?? NaN)
const MAX_POLLS = deadlineMs / pollMs

/** 读数脚本：逐格应答，名单用尽后重复最后一发（瞬断一族要连打多久都有话说）。 */
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

/** 传输层真断网：axios 给的是 code=ERR_NETWORK + 有 request 无 response。 */
const networkError = () => Object.assign(new Error('Network Error'), {
  isAxiosError: true, code: 'ERR_NETWORK', request: {}, config: { url: `/queue/status/${REQUEST_ID}` },
})

const statusOk = (over = {}) => ({ data: { status: 'queued', request_id: REQUEST_ID, position: 3, ...over } })

/** 后端真交出来的那一枚终态读数：app/api/v1/chat.py:3961 兜底分支 + reliable_queue.failure()。 */
const DEAD_FAILURE = { attempts: 3, max_attempts: 3, last_error: 'internal_error' }
const deadReply = () => ({ data: { status: 'dead', request_id: REQUEST_ID, failure: DEAD_FAILURE } })

// ==================== 无 DOM 的真生命周期（同 r198 / r202）====================

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

function queuedTurn(mid = 'r221-turn-a') {
  return { role: 'assistant', content: '', steps: [], mid, queue: { requestId: REQUEST_ID, status: 'queued' } }
}

async function mountPanel(turns, replies) {
  installStorage({ [TOKEN_KEY]: 'jwt-live' })
  activeId.value = 'r221-session'
  messages.value = turns
  http.get.mockImplementation(pollScript(...replies))
  let instance = null
  const errors = []
  const app = createApp({
    __name: 'R221ChatPanelHost',
    setup: ChatPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div', { id: 'r221-host' })
    },
  })
  app.config.warnHandler = () => {}
  app.config.errorHandler = err => errors.push(err)
  app.provide(SSR_CONTEXT_KEY, {})
  app.provide(routeLocationKey, reactive({ name: 'chat', path: '/chat', query: {}, params: {}, meta: {}, fullPath: '/chat', hash: '' }))
  app.provide(routerKey, { push: () => Promise.resolve(), replace: () => Promise.resolve() })
  app.mount(node('#root'))
  mounted = { app, errors, state: instance.setupState }
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

describe('甲 · 判据① dead 是后端真会交出来的终态：必须停表，且停的那一下说人话', () => {
  it('甲0 前提：停表名单逐枚点名，第五枚就是 dead', () => {
    const list = /const QUEUE_SETTLED = \[([^\]]*)\]/.exec(panel)
    expect(list, 'QUEUE_SETTLED 必须还是那一枚数组字面量（换成函数就没人看得见漏了什么）').toBeTruthy()
    for (const status of ['done', 'cancelled', 'failed', 'expired', 'dead']) {
      expect(list[1], `R221 判据①：停表名单漏了 '${status}'`).toContain(`'${status}'`)
    }
  })

  it('甲1 读到 dead 之后不许再发第二发状态请求（改前红：计时器永远不停）', async () => {
    const turn = queuedTurn('r221-dead-stop')
    await mountPanel([turn], [deadReply()])
    expect(statusCalls(), '挂载当轮应当恰好打一发状态请求').toBe(1)
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
    expect(statusCalls(), 'R221 判据①：dead 是终态，第 2 发不许再打').toBe(1)
    expect(mounted.errors, '组件生命周期内不许抛错').toEqual([])
  })

  it('甲2 dead 停表是永久的：连推 60 秒（20 个周期）也不许复活', async () => {
    const turn = queuedTurn('r221-dead-frozen')
    await mountPanel([turn], [deadReply()])
    const frozen = allCalls()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(allCalls(), `落进 dead 之后这一轮总共只许发 ${frozen} 发（含 /queue/stats），实际 ${allCalls()} 发`).toBe(frozen)
  })

  it('甲3 停的那一格是人话终态，不是永久 Spinner，且句子出自既有那一份口径', async () => {
    const turn = queuedTurn('r221-dead-face')
    await mountPanel([turn], [deadReply()])
    const face = faceOfTurn(turn)
    const dictionary = normalizeError({ detail: DEAD_FAILURE.last_error })
    expect(dictionary.message.length, '前提：字典里那句人话必须非空，否则 toContain 是假绿').toBeGreaterThan(4)
    expect(face, '屏上那句必须就是 lib/provenance 对同一枚读数的原话，面板不另立第三套判断')
      .toEqual(queueFace({ status: 'dead', position: null, failure: DEAD_FAILURE, result: '' }))
    expect(face.headline, '终态要说得出没产出答案').toContain('没有产出答案')
    expect(face.detail, '原因走 normalizeError 那一份口径').toContain(dictionary.message)
    expect(face.detail, '第几次尝试也要说得出').toContain('已尝试 3/3 次')
    expect(face.detail, '表都停了还写「每 3 秒再读一次」就是假话').not.toMatch(/每 3 秒再读一次/)
    expect(face.headline, '终态那一轮不许还挂着排队中的话').not.toMatch(/排队中|前面还有|正在后台生成/)
    expect(face.ahead, '终态不报位次').toBeNull()
  })

  it('甲4 真 QueueFace 上屏：dead 那一轮画出来的就是那句终态，且不夹裸码名', async () => {
    const turn = queuedTurn('r221-dead-ssr')
    await mountPanel([turn], [deadReply()])
    const html = await renderToString(h(QueueFace, { face: faceOfTurn(turn), stats: null }))
    expect(html).toContain('data-testid="queue-face"')
    expect(html).toContain('这一轮在后台执行失败，没有产出答案')
    expect(html).toContain('系统内部出现异常，请稍后重试。')
    expect(html, '给人看的句子里不许夹 snake_case 码名（V6 裸码闸门同一条口径）')
      .not.toMatch(/[\u4e00-\u9fff][^<>]*\b[a-z][a-z0-9]*(_[a-z0-9]+)+/)
  })

  // 一枚一格（不塞进同一格循环）：计数在 afterEach 复位，塞一格就会把上一发的账算进来。
  for (const status of ['done', 'cancelled', 'failed', 'expired']) {
    it(`甲5 原有那枚终态 '${status}' 不许被这格改动碰坏`, async () => {
      const turn = queuedTurn(`r221-settled-${status}`)
      await mountPanel([turn], [{ data: { status, request_id: REQUEST_ID } }])
      await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
      expect(statusCalls(), `QUEUE_SETTLED 原有的 ${status} 本来就该停表`).toBe(1)
    })
  }
})

describe('乙 · 判据② 看门狗带显式 deadline：到点只收表，绝不判失败', () => {
  it('乙0 前提：上限是一枚正数，且落在「瞬断不至于撞上、回执还查得回」那一段', () => {
    expect(Number.isFinite(deadlineMs) && deadlineMs > 0, 'deadline 必须是正数毫秒').toBe(true)
    expect(Number.isFinite(MAX_POLLS) && MAX_POLLS >= 20, `上限只够打 ${MAX_POLLS} 发，就是拿 deadline 当失败判定用`).toBe(true)
    expect(deadlineMs, '必须短于后端回执保留期 1800 秒，否则「稍后可查回」是假话').toBeLessThan(1_800_000)
  })

  it('乙1 没有 deadline 的轮询不存在：收表判定必须写在同一枚时钟的那一发之前', () => {
    const watch = panel.slice(panel.indexOf('function watchQueueTurn'), panel.indexOf('function stopQueueWatches'))
    expect(watch.length, '取到的是真实代码块').toBeGreaterThan(100)
    expect(watch, 'R221 判据②：看门狗必须带显式 deadline').toContain('QUEUE_WAIT_MAX_POLLS')
    expect(watch).toMatch(/entry\.polls > QUEUE_WAIT_MAX_POLLS/)
    expect(watch, '不许为 deadline 另起第二套计时器（r198 丁4 同一条规矩）').not.toMatch(/setTimeout/)
  })

  it('乙2 读数永远是 queued：盯满上限必须收表，此后一枪都不许再打', async () => {
    const turn = queuedTurn('r221-deadline-plain')
    await mountPanel([turn], [statusOk()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * (MAX_POLLS + 1))
    expect(statusCalls(), '到点之前每一发都该打，到点那一发只收表').toBe(MAX_POLLS)
    const frozen = allCalls()
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 20)
    expect(allCalls(), `收表之后连推 60 秒一枪都不许再有（基线 ${frozen} 发）`).toBe(frozen)
    expect(mounted.errors, '组件生命周期内不许抛错').toEqual([])
  })

  it('乙3 到点那一格的脸：说「已转后台，稍后可查回」，一个字都不许判失败', async () => {
    const turn = queuedTurn('r221-deadline-face')
    await mountPanel([turn], [statusOk({ position: 3 })])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * (MAX_POLLS + 1))
    const face = faceOfTurn(turn)
    expect(face.kind, '到点是新的一态，不许借 failed / unreadable-stopped 说话').toMatch(/wait|background/)
    expect(['failed', 'unreadable', 'unreadable-stopped'], '到点不是失败判定，也不是「读不回来」').not.toContain(face.kind)
    expect(face.headline).toContain('已转后台')
    expect(face.headline).toContain('稍后可查回')
    expect(`${face.headline}${face.detail}`, '语义红线：到点=停止前台等待，不是判定任务失败')
      .not.toMatch(/失败|没有产出答案|再也读不回来|已终止/)
    expect(face.detail, '表停了不许再说还在每 3 秒读').not.toMatch(/每 3 秒再读一次/)
    expect(`${face.headline}${face.detail}`, '也不许继续报旧位次').not.toMatch(/前面还有 \d+ 人/)
    expect(face.ahead).toBeNull()
    expect(messages.value[0].content, '收表不许往这条回答里编一个答案').toBe('')
    expect(Object.keys(face).sort(), '复用现成 face 形状，不另起一套字段')
      .toEqual(Object.keys(queuePollFailedFace(networkError())).sort())
  })

  it('乙4 到点之前不提前收表：瞬断连打到第 N-1 发仍然在轮，脸仍是「这次没读到」', async () => {
    const turn = queuedTurn('r221-blip')
    await mountPanel([turn], [networkError()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * (MAX_POLLS - 2))
    expect(statusCalls(), `反向半条：瞬断连打 ${MAX_POLLS - 1} 发也不许提前停表`).toBe(MAX_POLLS - 1)
    const face = faceOfTurn(turn)
    expect(face.kind, '没到点之前仍是「读不到」').toBe('unreadable')
    expect(face.detail).toMatch(/每 3 秒再读一次/)
  })

  it('乙5 瞬断打到上限：收的是前台这张表，收完仍然一个字不判失败', async () => {
    const turn = queuedTurn('r221-blip-full')
    await mountPanel([turn], [networkError()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * (MAX_POLLS - 2))
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 4)
    expect(statusCalls(), '打到上限照样收表：瞬断不能提前收表，不等于永远不收表').toBe(MAX_POLLS)
    const face = faceOfTurn(turn)
    expect(face.kind).toMatch(/wait|background/)
    expect(`${face.headline}${face.detail}`, '读不到不等于失败，这条到点上也不许翻成失败判定')
      .not.toMatch(/失败|没有产出答案|再也读不回来/)
    expect(face.retryable, '界面不自造重试按钮：再问一次会新起一轮，这一轮的结果可能仍在路上').toBe(false)
  })

  it('乙6 真 QueueFace 上屏：到点那张脸画出来的就是那句，且不夹裸码名', async () => {
    const turn = queuedTurn('r221-deadline-ssr')
    await mountPanel([turn], [statusOk()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * (MAX_POLLS + 1))
    const html = await renderToString(h(QueueFace, { face: faceOfTurn(turn), stats: null }))
    expect(html).toContain('data-testid="queue-face"')
    expect(html).toContain('已转后台，稍后可查回')
    expect(html).toMatch(/data-kind="[\w-]*(wait|background)/)
    expect(html).not.toMatch(/[\u4e00-\u9fff][^<>]*\b[a-z][a-z0-9]*(_[a-z0-9]+)+/)
  })

  it('乙7 「稍后可查回」是真通路：重新盯上会清掉到点痕并接着轮', async () => {
    const turn = queuedTurn('r221-rearm')
    await mountPanel([turn], [statusOk()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * (MAX_POLLS + 1))
    expect(faceOfTurn(turn).kind).toMatch(/wait|background/)
    mounted.state.restoreQueuedTurns()
    await settle()
    expect(faceOfTurn(turn).kind, '重新盯上之后到点痕必须清掉，否则那张脸会盖住新读数').toBe('queued')
    const before = statusCalls()
    await vi.advanceTimersByTimeAsync(QUEUE_MS)
    expect(statusCalls(), '重新起一轮前台等待：表得接着走').toBe(before + 1)
  })
})
