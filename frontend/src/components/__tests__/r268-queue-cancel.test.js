/**
 * R268 · 判据⑥ · G06 反证钉：排队中那一轮真的能一键取消，而取消之后说的是事实
 *
 * 病灶（改前取证，行号取本单基点 1142c27）：
 *   app/api/v1/chat.py:4380  POST /queue/{request_id}/cancel 早就在（200 回
 *       {cancelled, request_id, status}，401/403/404/503 各回一枚码），前端 0 个消费者；
 *   QueueFace.vue:38-56  只有 retry 与 action 两枚钮 —— 排上队之后员工只能干等；
 *   ChatPanel.vue:896-900 取消落定之后仍然画着最后一次读到的「排队中，前面还有 N 人」。
 *   输入框旁边那枚「中断本次回答」走的是 /ask/{session_id}/cancel（另一条腿，只管正在往屏上
 *   显示的那一轮），拿它当排队取消就是判据①点名的张冠李戴。
 *
 * 反证怎么算红：
 *   摘掉那枚按钮（或把 cancellable 写死 false）→ 甲组红；
 *   把取消改成借 /ask/{id}/cancel 那条腿 → 乙组第 3 条红；
 *   回执不读 status 就宣布「已取消」→ 乙组第 2 条红（cancel_requested 那一格会说谎）；
 *   取消成功后不停表 → 乙组第 4 条红；
 *   失败时把 404 / 403 / 503 并成一句「取消失败」→ 丙组红。
 *
 * 手法沿用 r198 / r260：createRenderer + 内存虚拟节点跑【真客户端生命周期】，所以
 * onMounted → restoreQueuedTurns → watchQueueTurn → setInterval 全是产品自己走的；
 * 换掉的只有网络层与「元素怎么落地」那一层。时钟是假的，一格 3 秒，不真等。
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
import { TOKEN_KEY, authedFetch, http } from '../../lib/http'
import { activeId, messages } from '../../lib/sessions'

const panel = readFileSync(new URL('../ChatPanel.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const QUEUE_MS = 3000
const REQUEST_ID = 'req-a'
const CANCEL_PATH = `/queue/${REQUEST_ID}/cancel`
const SSR_CONTEXT_KEY = Symbol.for('v-scx')
/** 屏上那句人话里不许夹 snake_case 裸码名（V6 闸门同一条口径）。 */
const BARE_CODE = /[\u4e00-\u9fff][^<>]*\b[a-z][a-z0-9]*(_[a-z0-9]+)+/

function axiosStatusError(status, detail) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    config: { url: CANCEL_PATH },
    response: { status, data: { detail } },
  })
}

const statusOk = (over = {}) => ({ data: { status: 'queued', request_id: REQUEST_ID, position: 3, ...over } })

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

const queuedTurn = (over = {}) => ({
  role: 'assistant', content: '', steps: [], mid: 'r268-turn-a',
  queue: { requestId: REQUEST_ID, status: 'queued' },
  ...over,
})

async function mountPanel(turns, replies) {
  installStorage({ [TOKEN_KEY]: 'jwt-live' })
  activeId.value = 'r268-session'
  messages.value = turns
  http.get.mockImplementation(pollScript(...(replies || [statusOk()])))
  http.post.mockResolvedValue({ data: { cancelled: true, request_id: REQUEST_ID, status: 'cancelled' } })
  let instance = null
  const errors = []
  const app = createApp({
    __name: 'R268QueueHost',
    setup: ChatPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div', { id: 'r268-host' })
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

const faceOfTurn = (turn, index = 0) => mounted.state.queueFaceOf(turn, index)
const cancelText = (face) => `${face.headline}${face.detail}`

beforeEach(() => {
  vi.useFakeTimers()
  messages.value = []
  activeId.value = ''
})

afterEach(() => {
  mounted?.app.unmount()
  mounted = null
  vi.useRealTimers()
  http.get.mockReset()
  http.post.mockReset()
  authedFetch.mockReset()
})

describe('甲 · 排队中那一轮点得动：按钮给得出、也只给还没落定的那一轮', () => {
  it('排队中 / 正在跑各给一枚「不排了」，还没读到位次时也不缺席', async () => {
    const turn = queuedTurn()
    await mountPanel([turn])
    const face = faceOfTurn(turn)
    expect(face.kind).toBe('queued')
    expect(face.cancellable, '判据①那一键：排着队就该有件能点的事').toBe(true)
    expect(face.cancelling).toBeUndefined()
  })

  it('真 QueueFace 上屏：那枚钮画得出来、不是 disabled 占位、文案不夹裸码名', async () => {
    const turn = queuedTurn()
    await mountPanel([turn])
    const html = await renderToString(h(QueueFace, { face: faceOfTurn(turn), stats: null }))
    expect(html).toContain('data-testid="queue-cancel"')
    expect(html).toContain('不排了')
    expect(html, '假控件是这仓点过名的病').not.toMatch(/disabled/)
    expect(html).not.toMatch(BARE_CODE)
  })

  it('已经落定的那一轮不许再给按钮：对着不会动的东西说「不排了」是假话', async () => {
    const turn = queuedTurn()
    await mountPanel([turn])
    for (const status of ['done', 'cancelled', 'failed', 'expired', 'dead']) {
      http.get.mockImplementation(pollScript(statusOk({ status, result: status === 'done' ? '答案' : '' })))
      mounted.state.stopQueueWatch(`m${turn.mid}`)
      messages.value = []
      const settled = queuedTurn({ mid: `m-${status}`, queue: { requestId: REQUEST_ID, status } })
      messages.value = [settled]
      const face = faceOfTurn(settled)
      expect(face.cancellable, `${status} 是落定态，不该给取消`).toBeFalsy()
    }
  })

  it('挂起等人拍板那一轮不给取消：那一格的出路是去审批那一屏（R260 的账）', async () => {
    await mountPanel([queuedTurn()])
    const parked = queuedTurn({
      mid: 'r268-await',
      queue: { requestId: REQUEST_ID, status: 'awaiting_approval', approval: { labels: ['导出报告'] } },
    })
    const face = mounted.state.queueFaceOf(parked, 7)
    expect(face.kind).toBe('parked-approval')
    expect(face.cancellable, '对着等人拍板的一轮说「不排了」是第二套出路').toBeFalsy()
  })
})

describe('乙 · 一键取消走的真就是 POST /queue/{request_id}/cancel', () => {
  it('点一次真发一发，且只发一发（在飞时再点不重复打）', async () => {
    const turn = queuedTurn()
    await mountPanel([turn])
    let release = null
    http.post.mockReturnValue(new Promise(resolve => { release = resolve }))
    const first = mounted.state.cancelQueuedTurn(turn, 0)
    await settle()
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(http.post.mock.calls[0][0]).toBe(CANCEL_PATH)
    const busy = faceOfTurn(turn)
    expect(busy.cancelling, '在飞时按钮要转忙，不是一枚还能点的钮').toBe(true)
    mounted.state.cancelQueuedTurn(turn, 0)
    await settle()
    expect(http.post).toHaveBeenCalledTimes(1)
    release({ data: { cancelled: true, request_id: REQUEST_ID, status: 'cancelled' } })
    await first
    await settle()
  })

  it('后端说 cancelled：脸改口成已取消、msg 上那一份也跟着落盘，刷新不会画回排队中', async () => {
    const turn = queuedTurn()
    await mountPanel([turn])
    await mounted.state.cancelQueuedTurn(turn, 0)
    await settle()
    const face = faceOfTurn(turn)
    expect(face.kind).toBe('cancelled')
    expect(cancelText(face)).toContain('已取消')
    expect(turn.queue.status).toBe('cancelled')
    expect(mounted.state.streamNote).toContain('已取消')
  })

  it('后端说 cancel_requested：只能说「已登记」，两头都不许站（既不说失败也不说已取消）', async () => {
    const turn = queuedTurn()
    await mountPanel([turn])
    http.post.mockResolvedValue({ data: { cancelled: true, request_id: REQUEST_ID, status: 'cancel_requested' } })
    await mounted.state.cancelQueuedTurn(turn, 0)
    await settle()
    const face = faceOfTurn(turn)
    expect(face.kind).toBe('cancel-requested')
    const voice = cancelText(face)
    expect(voice).toContain('取消已登记')
    expect(voice, '人刚按了取消，界面反过来说系统坏了就是判据①点名的那句假话')
      .not.toContain('这一轮在后台执行失败')
    expect(voice).not.toContain('已取消，')
    expect(mounted.state.streamNote).toContain('不会再产出答案')
  })

  it('取消落定之后表停了：不再每 3 秒打一枪被拒的读数', async () => {
    const turn = queuedTurn()
    await mountPanel([turn])
    await mounted.state.cancelQueuedTurn(turn, 0)
    await settle()
    const before = statusCalls()
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 4)
    await settle()
    expect(statusCalls(), '取消成功的这一轮不会再有新读数，继续打就是白打').toBe(before)
  })

  it('HTTP 200 但回执没那枚 true：界面不替后端宣布结果', async () => {
    const turn = queuedTurn()
    await mountPanel([turn])
    http.post.mockResolvedValue({ data: { cancelled: false, request_id: REQUEST_ID, status: 'queued' } })
    await mounted.state.cancelQueuedTurn(turn, 0)
    await settle()
    expect(mounted.state.streamNote).toContain('不替它宣布结果')
    expect(faceOfTurn(turn).kind, '没证据就不许改口成已取消').toBe('queued')
  })

  it('这一轮压根没有 request_id 时点不动，也不瞎发一发', async () => {
    const turn = queuedTurn({ queue: undefined })
    await mountPanel([turn])
    await mounted.state.cancelQueuedTurn(turn, 0)
    await settle()
    expect(http.post).not.toHaveBeenCalled()
  })
})

describe('丙 · 取消失败必须读服务端错误码并说人话（三格三句，不许并成一句）', () => {
  const cases = [
    ['404 找不着那一格', 404, 'resource_not_found', '要找的内容不存在或已被移除。'],
    ['403 权限不够', 403, 'permission_denied', '当前账号没有这项权限，请联系管理员开通。'],
    // 后端这一格 envelope 里那行 message 是给开发者看的英文正文（chat.py:4388 带 str(exc)）：
    // 判据①要的是「读码说人话」，所以脸上那句必须是字典那一句，不是那行英文。
    ['503 队列连不上', 503, { code: 'queue_unavailable', message: 'Unable to verify the Redis connection' }, '后台任务暂时排不上队，请稍后重试。'],
  ]

  it.each(cases)('%s：脸上那句就是字典那一句', async (_name, status, detail, expected) => {
    const turn = queuedTurn()
    await mountPanel([turn])
    http.post.mockRejectedValue(axiosStatusError(status, detail))
    await mounted.state.cancelQueuedTurn(turn, 0)
    await settle()
    const face = faceOfTurn(turn)
    expect(face.kind).toBe('cancel-failed')
    expect(cancelText(face)).toContain('这一轮没能取消')
    expect(cancelText(face)).toContain(expected)
    expect(cancelText(face), '字典句在前，后端那行英文正文不许原样念给员工听').not.toContain('Unable to verify')
    expect(cancelText(face)).not.toMatch(BARE_CODE)
    expect(mounted.state.streamNote).toContain(expected)
  })

  it('三格三句两两不同，且界面没有替后端宣布取消、也没有停表', async () => {
    const voices = []
    for (const [, status, detail] of cases) {
      const turn = queuedTurn({ mid: `deny-${status}` })
      await mountPanel([turn])
      http.post.mockRejectedValue(axiosStatusError(status, detail))
      await mounted.state.cancelQueuedTurn(turn, 0)
      await settle()
      const face = faceOfTurn(turn)
      voices.push(cancelText(face))
      expect(face.cancellable).toBe(true)
      expect(face.cancelRetry, '上一次没办成，按钮自己换文案，不另立第二枚控件').toBe(true)
      expect(face.kind).not.toBe('cancelled')
      const before = statusCalls()
      await vi.advanceTimersByTimeAsync(QUEUE_MS * 2)
      await settle()
      expect(statusCalls()).toBeGreaterThan(before)
    }
    expect(new Set(voices).size).toBe(3)
  })

  it('它走的是排队那条腿：借 /ask/{session_id}/cancel 那一枚就算红', async () => {
    const turn = queuedTurn()
    await mountPanel([turn])
    await mounted.state.cancelQueuedTurn(turn, 0)
    await settle()
    expect(http.post).toHaveBeenCalledWith(CANCEL_PATH)
    expect(authedFetch, '「中断本次回答」管的是正在显示的那一轮，不是这一枚按钮').not.toHaveBeenCalled()
    expect(panel).not.toMatch(/cancelQueuedTurn[\s\S]{0,600}?authedFetch\(`\/ask\//)
  })
})

describe('丁 · 接线形状：组件只画钮、面板只发请求，两处都不自造第二套判定', () => {
  it('QueueFace 自己不打接口，取消这件事一律由面板办', async () => {
    const face = { kind: 'queued', headline: '排队中', detail: '', tone: 'info', ahead: null, cancellable: true }
    await renderToString(h(QueueFace, { face, stats: null }))
    expect(http.post).not.toHaveBeenCalled()
    expect(panel).toMatch(/@cancel="cancelQueuedTurn\(msg, i\)"/)
    expect(panel).toMatch(/http\.post\(`\/queue\/\$\{encodeURIComponent\(requestId\)\}\/cancel`/)
  })

  it('取消那三张脸的形状齐备：kind / headline / detail / tone 一枚不缺', async () => {
    const turn = queuedTurn()
    await mountPanel([turn])
    const pending = mounted.state.queueCancelPendingFace()
    const failed = mounted.state.queueCancelFailedFace(axiosStatusError(403, 'permission_denied'))
    for (const face of [pending, failed]) {
      expect(typeof face.kind).toBe('string')
      expect(face.headline.length).toBeGreaterThan(4)
      expect(face.detail.length).toBeGreaterThan(10)
      expect(['info', 'warn', 'danger']).toContain(face.tone)
    }
    expect(pending.kind).not.toBe(failed.kind)
  })
})