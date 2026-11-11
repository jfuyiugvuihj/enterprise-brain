/**
 * R260 · 队列道第九枚读数（awaiting_approval）在前端的三件事：停表 / 说对话 / 给一件能点的东西
 *
 * 病灶（改前取证，取的是本件基点 c70548a 上真跑出来的结果，不是推断）：
 *   :852  const QUEUE_SETTLED = [done, cancelled, failed, expired, dead] —— 没有 awaiting_approval；
 *   :1073 if (QUEUE_SETTLED.includes(read.status)) stop() —— 于是挂起那一轮的计时器永不停，
 *         每 3 秒继续打一枪，一直到 :1058 那枚 300 秒看门狗到点才收表；
 *   屏上那 300 秒说的是 lib/provenance.js 的 queueFace 最后那格兜底的原话：
 *     「这一轮在后台执行失败，没有产出答案」（tone=danger）—— 后端没失败，是人还没拍板；
 *   到点之后又换成「这一轮前台已盯到上限：已转后台，稍后可查回」—— 那一轮不会自己好。
 *   两句话都是假话，且没有一件能点的东西。取证脚本与输出见树根 _r260_evidence_prefix.txt。
 *
 * 契约原文：docs/api/contract-v1.md 的 Long Task Status 一节 —— awaiting_approval 对【轮询】
 * 是终态、对【这一轮】不是终态（POST /api/v1/approve 能把它再推动，客户端不必重发问题），
 * 且 result 恒为 null（挂起文案改走 approval.notice）。
 *
 * 手法照 r198 / r202 / r221：环境是 node（本仓没有 jsdom / @vue/test-utils，也不许 npm i），把
 * ChatPanel 编译产物里那份真 setup 挂进宿主组件，用 createRenderer + 内存虚拟节点跑真生命周期，
 * 所以 onMounted -> restoreQueuedTurns -> watchQueueTurn -> setInterval 全是产品自己走的；
 * 换掉的只有网络层（vi.mock lib/http）与元素落地那一层。时钟用 vi.useFakeTimers()，不真等。
 *
 * 三把反证刀各自咬什么（摘掉修复必红，逐枚写在名字里）：
 *   刀① 把停表名单里那枚摘掉 ⇒ 甲1 红，红在「一直轮询到看门狗到点」那一格（计数），不是红在字符串比对；
 *   刀② 把能点的入口摘掉（provenance 不再给 action，或模板不再绑 @action）⇒ 丙1 丙2 丙3 一起红；
 *   刀③ 把 result:null 当成正文（改掉 :1072 那行的守卫，或把 notice 投喂进 applyQueuedAnswer）⇒ 丁1 丁4 红。
 */
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, getCurrentInstance, h, nextTick, reactive, unref } from 'vue'
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
import { queueFace } from '../../lib/provenance'
// R458（判据①）：面板挂载期那一发不再穿透 lib/health.js 的 60 秒缓存，于是「本文件里第几次挂载
// 才发得出健康读数」变成缓存状态的事。己1 那本端点账要的是【每一枚挂载都真打过自家端点】，所以这里
// 像 r268-runtime-faces / chat-model-status 一样每枚用例清一次缓存，把它显式化 —— 账目一字未改。
import { resetRuntimeHealthCache } from '../../lib/health.js'
import { activeId, messages } from '../../lib/sessions'

const source = f => readFileSync(new URL(f, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const panel = source('../ChatPanel.vue')
const provenanceSrc = source('../../lib/provenance.js')
/** 剥掉注释再数出现次数：这一格钉的是代码里的出口，不是说明里提到的那扇门（同 r247 的手法）。 */
const codeOnly = text => text
  .replace(/<!--[\s\S]*?-->/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .split('\n')
  .filter(line => !/^\s*\/\//.test(line))
  .join('\n')
const panelCode = codeOnly(panel)

const QUEUE_MS = 3000
const REQUEST_ID = 'req-r260'
const SESSION_ID = 'sess-r260'
const SSR_CONTEXT_KEY = Symbol.for('v-scx')

// 上限从面板源码里抠，不在这儿抄一份数字（抄了就只是「界面恰好等于测试」，删掉上限反而跟着绿）。
const deadlineMs = Number((/const QUEUE_WAIT_DEADLINE_MS = (\d+)/.exec(panel) || [])[1] ?? NaN)
const pollMs = Number((/const QUEUE_POLL_MS = (\d+)/.exec(panel) || [])[1] ?? NaN)
const MAX_POLLS = deadlineMs / pollMs

/** 后端 R254 真交回来的那一格（键逐条照契约 Structured terminal readout 一节抄）。 */
const APPROVAL_HANDLE = {
  session_id: SESSION_ID,
  pending_steps: ['export'],
  labels: ['📋 导出报告'],
  notice: '本轮在「📋 导出报告」前等待你确认，确认后才会执行，目前尚未产出回答内容。',
  decide_method: 'POST',
  decide_path: '/api/v1/approve',
  decide_body: { session_id: SESSION_ID, approved: true },
  ledger_status: 'awaiting',
}

/** 台账那一格的四种形状：认识的读数 / 不认识的读数 / 空串 / 压根没给这一格。 */
const MISSING = '（后端没给这一格）'
function ledgerApproval(ledger) {
  if (ledger === MISSING) {
    const handle = { ...APPROVAL_HANDLE }
    delete handle.ledger_status
    return handle
  }
  return { ...APPROVAL_HANDLE, ledger_status: ledger }
}

const LEDGER_OPEN_CASES = ['awaiting', 'unavailable', 'quitting', '', MISSING]
const LEDGER_CLOSED_CASES = ['resumed', 'refused', 'abandoned', 'stale', 'failed', 'absent', 'no_session', 'owner_mismatch']
const LEDGER_ALL = [...LEDGER_OPEN_CASES, ...LEDGER_CLOSED_CASES]

const awaitingReply = (approval = APPROVAL_HANDLE) => ({
  data: {
    status: 'awaiting_approval',
    request_id: REQUEST_ID,
    result: null,
    failure: null,
    terminal_schema: 'queue-terminal-v1',
    terminal_state: 'awaiting_approval',
    answer_present: false,
    sources_present: false,
    sources: [],
    usage: null,
    approval,
    terminal_note: '',
  },
})

/** 读数脚本：只认这三枚端点；这一格顺手记下打过哪些地址，判据⑤用它对账。 */
const hitPaths = []
function pollScript(...replies) {
  let at = 0
  return async (url) => {
    const target = String(url)
    hitPaths.push(target.startsWith('/queue/status/') ? '/queue/status/{id}' : target)
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

const networkError = () => Object.assign(new Error('Network Error'), {
  isAxiosError: true, code: 'ERR_NETWORK', request: {}, config: { url: `/queue/status/${REQUEST_ID}` },
})

const statusOk = (over = {}) => ({ data: { status: 'queued', request_id: REQUEST_ID, position: 3, ...over } })

// ==================== 无 DOM 的真生命周期（同 r198 / r202 / r221）====================

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
const apps = []
const pushed = []

const settle = async () => {
  await nextTick()
  await vi.advanceTimersByTimeAsync(0)
  await nextTick()
}

function queuedTurn(mid = 'r260-turn-a') {
  return { role: 'assistant', content: '', steps: [], mid, queue: { requestId: REQUEST_ID, status: 'queued' } }
}

async function mountPanel(turns, replies) {
  installStorage({ [TOKEN_KEY]: 'jwt-live' })
  activeId.value = 'r260-session'
  messages.value = turns
  http.get.mockImplementation(pollScript(...replies))
  let instance = null
  const errors = []
  const app = createApp({
    __name: 'R260ChatPanelHost',
    setup: ChatPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div', { id: 'r260-host' })
    },
  })
  app.config.warnHandler = () => {}
  app.config.errorHandler = err => errors.push(err)
  app.provide(SSR_CONTEXT_KEY, {})
  app.provide(routeLocationKey, reactive({ name: 'chat', path: '/chat', query: {}, params: {}, meta: {}, fullPath: '/chat', hash: '' }))
  // 路由是本单那件「能点的东西」的落点，所以这里必须收账：push 了什么，一眼看得见。
  app.provide(routerKey, {
    push: to => { pushed.push(to); return Promise.resolve() },
    replace: to => { pushed.push(to); return Promise.resolve() },
  })
  app.mount(node('#root'))
  apps.push(app)
  mounted = { app, errors, state: instance.setupState }
  await settle()
  return mounted
}

/** 这一轮此刻的脸：面板喂给 <QueueFace :face> 的就是这枚值，一个字都不另算。 */
const faceOfTurn = (turn, index = 0) => mounted.state.queueFaceOf(turn, index)

afterEach(() => {
  // 一格里连挂多枚面板（乙组与丙组按台账读数逐枚过）时，【每一枚】都得卸载：
  // 只卸最后那一枚就会留下仍在打的 setInterval 与 queueWatches 那一份模块级名单，
  // 下一发的计数与脸就串到别人那一轮上去了（这一格本来就是这么查出来的）。
  apps.splice(0).forEach(app => app.unmount())
  mounted = null
  pushed.length = 0
  hitPaths.length = 0
  vi.useRealTimers()
  http.get.mockReset()
})

beforeEach(() => {
  vi.useFakeTimers()
  resetRuntimeHealthCache()
  messages.value = []
  activeId.value = ''
})

/** 这一轮此刻的排队读数（面板自己那份袋子，不另算一遍）。 */
const readOfTurn = (turn) => {
  const bag = unref(mounted.state.queueReads) || {}
  return bag[mounted.state.turnKey(turn, 0)] || null
}

/** 装上这一轮，读到 awaiting_approval 为止，返回 { turn, face }。 */
async function mountAwaiting(name, approval = APPROVAL_HANDLE) {
  const turn = queuedTurn(name)
  await mountPanel([turn], [awaitingReply(approval)])
  return { turn, face: faceOfTurn(turn) }
}

// ==================== 甲 · 判据①：停表 ====================

describe('甲 · 判据① awaiting_approval 必须停表（挂起对轮询是终态）', () => {
  it('甲0 形状守门：名单仍是那一枚数组字面量，新终态写在里面', () => {
    const list = /const QUEUE_SETTLED = \[([^\]]*)\]/.exec(panel)
    expect(list, 'R221 甲0 同一条形状钉：改成函数或 Set 会让那枚钉看不见漏了什么').toBeTruthy()
    for (const status of ['done', 'cancelled', 'failed', 'expired', 'dead', 'awaiting_approval']) {
      expect(list[1], `停表名单漏了 ${status}`).toContain(`'${status}'`)
    }
  })

  it('甲1 读到挂起之后不许再打第二发状态请求（刀①摘掉那枚 ⇒ 本格红在轮询计数）', async () => {
    const turn = queuedTurn('r260-awaiting-stop')
    await mountPanel([turn], [awaitingReply()])
    expect(statusCalls(), '挂载当轮应当恰好打一发状态请求').toBe(1)
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
    expect(statusCalls(), 'R260 判据①：第 2 发不许再打（改前每 3 秒继续打一枪）').toBe(1)
    expect(mounted.errors, '组件生命周期内不许抛错').toEqual([])
  })

  it(`甲1b 一路推到看门狗上限仍然只发过 1 发（改前正是这一格打满 ${MAX_POLLS} 发，红点在这里）`, async () => {
    const turn = queuedTurn('r260-awaiting-full-window')
    await mountPanel([turn], [awaitingReply()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * (MAX_POLLS + 2))
    expect(statusCalls(), '挂起这一轮从头到尾只许发一发；不停表就会一直轮询到看门狗到点').toBe(1)
  })

  it('甲2 停表是永久的：连推 60 秒（20 个周期）也不许复活', async () => {
    const turn = queuedTurn('r260-awaiting-frozen')
    await mountPanel([turn], [awaitingReply()])
    const frozen = allCalls()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(allCalls(), `落进挂起之后这一轮总共只许发 ${frozen} 发（含 /queue/stats），实际 ${allCalls()} 发`).toBe(frozen)
  })

  it('甲3 到点那张脸不许盖到挂起这一轮上：说的不是「已转后台，稍后可查回」', async () => {
    const turn = queuedTurn('r260-awaiting-not-wait-face')
    await mountPanel([turn], [awaitingReply()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * (MAX_POLLS + 2))
    const face = faceOfTurn(turn)
    expect(face.kind, '到点收表是一态，挂起待批准是另一态，不许并格').toBe('parked-approval')
    expect(face.kind, 'kind 里不许含 wait：那是到点收表那一态的识别口径（r221 乙3 / 乙6）').not.toMatch(/wait|background/)
    expect(`${face.headline}${face.detail}`, '这一轮不是「已转后台稍后查回」，它停着等人拍板').not.toMatch(/已转后台|稍后可查回/)
  })
})

// ==================== 乙 · 判据②：界面不许说错话 ====================

describe('乙 · 判据② 挂起那一轮的读数三句假话都不许说（三枚反面各钉一次）', () => {
  it('乙0 前提：这一格真读到挂起那张脸（否则下面三枚反面全是假绿）', async () => {
    const { face } = await mountAwaiting('r260-voice-precondition')
    expect(face, '读数必须存在，界面才有话可说').toBeTruthy()
    expect(face.kind).toBe('parked-approval')
    expect(face.headline.length, '句子非空：空串过不了下面任何一枚 not.toMatch').toBeGreaterThan(8)
    expect(face.detail.length).toBeGreaterThan(8)
  })

  it('乙1 反面①：任何一格台账读数都不许说「已完成」', async () => {
    for (const ledger of LEDGER_ALL) {
      const { face } = await mountAwaiting(`r260-voice-done-${String(ledger)}`, ledgerApproval(ledger))
      expect(`${face.headline}${face.detail}`, `台账读数 ${String(ledger)} 那一张脸说了「完成」那类话`).not.toMatch(/已完成|已经跑完|跑完了|办完|办妥|已就绪|生成了答案/)
      expect(face.tone, 'tone=ok 就是「这一轮成了」的另一张脸').not.toBe('ok')
    }
  })

  it('乙2 反面②：任何一格台账读数都不许说「失败」', async () => {
    for (const ledger of LEDGER_ALL) {
      const { face } = await mountAwaiting(`r260-voice-failed-${String(ledger)}`, ledgerApproval(ledger))
      expect(`${face.headline}${face.detail}`, `台账读数 ${String(ledger)} 那一张脸说了失败那类话——人还没拍板不是系统失败`).not.toMatch(/失败|没有产出答案|出错了|异常|报错/)
      expect(face.kind, '改前 awaiting_approval 直接落进 queueFace 最后的 failed 兜底').not.toBe('failed')
    }
  })

  it('乙3 反面③：任何一格都不许承诺「稍后会自己好」，而真相那句必须说出口', async () => {
    for (const ledger of LEDGER_ALL) {
      const { face } = await mountAwaiting(`r260-voice-selfheal-${String(ledger)}`, ledgerApproval(ledger))
      expect(`${face.headline}${face.detail}`, `台账读数 ${String(ledger)} 那一张脸许了「等一会儿它自己好」`).not.toMatch(/稍后|稍候|会自动|自己(就好|动|往下走)|再等一会儿|过一会儿/)
    }
    const { face } = await mountAwaiting('r260-voice-truth', ledgerApproval('awaiting'))
    expect(face.headline, '挂起这一轮的真相：不确认它就不会再动，这句必须写在脸上').toMatch(/不确认它就不会再动/)
  })

  it('乙4 措辞出自 lib/provenance 那一份口径：面板不另立第三套判断', async () => {
    const { turn, face } = await mountAwaiting('r260-voice-single-source')
    const read = readOfTurn(turn)
    expect(read, '前提：这一轮的读数在位').toBeTruthy()
    expect(face, '屏上那句必须就是 lib/provenance 对同一枚读数的原话').toEqual(queueFace(read))
    expect(face.headline + face.detail, '等的是哪一步要说得出，而且用的是后端给的标签').toContain(APPROVAL_HANDLE.labels[0])
  })

  it('乙5 真 QueueFace 上屏：挂起这一轮画出来的就是那句，且不夹裸码名', async () => {
    const { face } = await mountAwaiting('r260-voice-ssr')
    const html = await renderToString(h(QueueFace, { face, stats: null }))
    expect(html).toContain('data-testid="queue-face"')
    expect(html).toContain('这一轮停在等你确认的那一步')
    expect(html, '给人看的句子里不许夹 snake_case 码名（V6 闸门同一条口径）')
      .not.toMatch(/[\u4e00-\u9fff][^<>]*\b[a-z][a-z0-9]*(_[a-z0-9]+)+/)
  })
})

// ==================== 丙 · 判据③：给一件能点的东西（走既有那一屏，不开第二套批准路径）====================

describe('丙 · 判据③ 挂起这一轮能从聊天面板走到既有的待批准 UI', () => {
  it('丙1 脸上带着可点的入口：kind 与文案都在位（刀②摘掉 action ⇒ 本格红）', async () => {
    const { face } = await mountAwaiting('r260-action-shape', ledgerApproval('awaiting'))
    expect(face.action, '挂起这一轮必须给得出路，不能只留一句话').toBeTruthy()
    expect(face.action.kind, '入口只认这一枚语义：去既有的待批准那一屏').toBe('hitl-pending')
    expect(face.action.label.length, '按钮得有个能读懂的名字').toBeGreaterThan(3)
    expect(face.retryable, '不许顺手把「按原文再问一次」当作出路：批准不需要重发问题').toBe(false)
  })

  it('丙2 真 QueueFace 上屏：那枚按钮画得出来，不是 disabled 占位（刀②同红）', async () => {
    const { face } = await mountAwaiting('r260-action-ssr', ledgerApproval('awaiting'))
    const html = await renderToString(h(QueueFace, { face, stats: null }))
    expect(html).toContain('data-testid="queue-action"')
    expect(html).toContain(face.action.label)
    expect(html, '假控件是这仓点过名的病：不许画一枚点不动的按钮').not.toMatch(/disabled/)
  })

  it('丙3 点它 = 落到既有那一屏（router.push({ name: approval })），且只此一步', async () => {
    const { face } = await mountAwaiting('r260-action-push', ledgerApproval('awaiting'))
    expect(panelCode, '模板必须把 QueueFace 的 @action 接到那枚跳转上（接线没接上就是屏上有按钮、点了没反应）')
      .toMatch(/@action="openApprovalTurn"/)
    mounted.state.openApprovalTurn(face.action)
    await settle()
    expect(pushed, '落点只有一个：挂 HitlPendingPanel 的那一屏').toEqual([{ name: 'approval' }])
    expect(http.post, '前端不替后端把批准发出去：归属判定在服务端').not.toHaveBeenCalled()
  })

  it('丙4 不开第二套批准路径：/approve 与 /hitl/pending 在面板里一次都没出现', () => {
    expect(panelCode.match(/\/approve/g) || [], '聊天面板里唯一那处 /approve 是同步道那张卡的 approve()（既有通路），排队这一轮只做跳转')
      .toHaveLength(1)
    expect(panelCode, '挂起账本的读取口长在 HitlPendingPanel 那一屏，本面板不抄第二份').not.toContain('/hitl/pending')
    expect(panelCode.match(/authedFetch\(['"]\/approve/g) || [], '同步道那张卡那一处原样保留').toHaveLength(1)
  })

  it('丙5 台账说这一步已经闭合的那几枚：不给按钮，而且八句话各说各的（不许并格）', async () => {
    const details = []
    for (const ledger of LEDGER_CLOSED_CASES) {
      const { face } = await mountAwaiting(`r260-closed-${ledger}`, ledgerApproval(ledger))
      expect(face.action, `账上已经闭合的 ${ledger} 那一格，摆个批准按钮就是假控件`).toBeFalsy()
      expect(face.kind).toBe('approval-closed')
      expect(details, `${ledger} 这句话与前面某格一字不差，就是并格了`).not.toContain(face.detail)
      details.push(face.detail)
    }
    expect(details).toHaveLength(LEDGER_CLOSED_CASES.length)
  })

  it('丙6 还开着 / 读不出 / 不认识 / 后端没给：这四格仍然给得出入口，并各自认账', async () => {
    for (const ledger of LEDGER_OPEN_CASES) {
      const { face } = await mountAwaiting(`r260-open-${String(ledger)}`, ledgerApproval(ledger))
      expect(face.action, `${String(ledger)} 不等于「已经闭合」，不能把出路藏起来`).toBeTruthy()
      expect(face.kind).toBe('parked-approval')
    }
    const unknown = await mountAwaiting('r260-open-unknown', ledgerApproval('quitting'))
    expect(`${unknown.face.headline}${unknown.face.detail}`, '词表之外的读数必须明说不认识，不许静默并回上面任何一格')
      .toMatch(/还不认识/)
    const unread = await mountAwaiting('r260-open-unavailable', ledgerApproval('unavailable'))
    expect(`${unread.face.headline}${unread.face.detail}`, '读不出来不等于「没有」这一格已经被谁办完')
      .toMatch(/读不出来/)
  })
})

// ==================== 丁 · 判据④：result 为 null 不许被画成正文 ====================

describe('丁 · 判据④ result:null 的真实走法（现取，不猜）', () => {
  it('丁0 前提：后端这一格真给的是 result:null', () => {
    expect(awaitingReply().data.result, '契约：挂起那一轮 publish 的正文是 null').toBeNull()
  })

  it('丁1 这条回答的正文仍然是空串：一个字都没被写进去（刀③改守卫 ⇒ 本格红）', async () => {
    const turn = queuedTurn('r260-null-not-body')
    await mountPanel([turn], [awaitingReply()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 2)
    expect(messages.value[0].content, '停表不等于有答案：这一轮的正文还没产出').toBe('')
    expect(mounted.errors, '组件生命周期内不许抛错').toEqual([])
  })

  it('丁2 链路上那一格折成空串而不是字面值：屏上不会出现 null / undefined 两个词', async () => {
    const { turn, face } = await mountAwaiting('r260-null-render')
    const read = readOfTurn(turn)
    expect(read.result, 'ChatPanel 把非字符串的 result 折成空串，null 一路没有变成字符串').toBe('')
    expect(face.headline + face.detail, '读数说的话里不许夹 null/undefined').not.toMatch(/null|undefined/i)
    const html = await renderToString(h(QueueFace, { face, stats: null }))
    expect(html).not.toMatch(/>\s*(null|undefined)\s*</)
  })

  it('丁3 这一轮不许被标成「有答案但空白」：既不是 done，也不是 done-no-result', async () => {
    const { face } = await mountAwaiting('r260-not-marked-answer', ledgerApproval('awaiting'))
    expect(['done', 'done-no-result'], '借一个 done 宣布界面上有答案，正是 R254 在后端治掉的那件事')
      .not.toContain(face.kind)
    expect(face.ahead, '终态不报位次').toBeNull()
  })

  it('丁5 done 而 result 为 null（R254 那格 answer_present:false 的形状）：正文不写，脸说「没带回答案」', async () => {
    const turn = queuedTurn('r260-done-null')
    await mountPanel([turn], [{ data: { status: 'done', request_id: REQUEST_ID, result: null, answer_present: false } }])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 2)
    expect(messages.value[0].content, '一个 null 不该在正文那一格里留下任何字').toBe('')
    expect(faceOfTurn(turn).kind, '这一格的说法是「跑完了但没带回答案」，不是「有答案」').toBe('done-no-result')
  })

  it('丁4 挂起文案（approval.notice）不许顺着正文那条腿流进这条回答（刀③投喂 ⇒ 本格红）', async () => {

    const turn = queuedTurn('r260-notice-not-body')
    await mountPanel([turn], [awaitingReply()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 2)
    expect(messages.value[0].content.includes(APPROVAL_HANDLE.notice), '那 37 字是说明，不是正文').toBe(false)
    const read = readOfTurn(turn)
    expect(read.approval.decide_path, '把手原样带下来：下一单要做就地批准从这儿接，不必改契约')
      .toBe('/api/v1/approve')
    expect(read.approval.decide_method).toBe('POST')
    expect(read.approval.decide_body).toEqual({ session_id: SESSION_ID, approved: true })
  })
})

// ==================== 戊 · 判据⑥：既有语义一枚都不许退化 ====================

describe('戊 · 判据⑥ R198 / R202 / R221 那三族的语义一枚都不许被本单碰红', () => {
  it('戊1 到点那张脸的原话仍在位：盯满上限还是「已转后台，稍后可查回」', async () => {
    const turn = queuedTurn('r260-deadline-copy')
    await mountPanel([turn], [statusOk({ position: 3 })])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * (MAX_POLLS + 1))
    const face = faceOfTurn(turn)
    expect(face.kind).toMatch(/wait|background/)
    expect(face.headline, 'R221 判据②那句话是本单的反面：它只对「没读到」的轮次说，不许被推广到挂起').toContain('已转后台，稍后可查回')
  })

  it('戊2 queued 不是终态：到上限之前每一发都该打（新名单没顺手停掉排队中）', async () => {
    const turn = queuedTurn('r260-queued-still-polls')
    await mountPanel([turn], [statusOk()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 5)
    expect(statusCalls(), '排队中继续每 3 秒读一次').toBe(6)
    expect(faceOfTurn(turn).kind).toBe('queued')
  })

  it('戊3 done 带回 result 仍然把答案补进这条回答，并且照旧停表', async () => {
    const turn = queuedTurn('r260-done-still-answers')
    await mountPanel([turn], [{ data: { status: 'done', request_id: REQUEST_ID, result: '上季度毛利率 38.2%' } }])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
    expect(messages.value[0].content).toBe('上季度毛利率 38.2%')
    expect(statusCalls(), 'done 本来就是终态').toBe(1)
  })

  it('戊4 先读到 queued、第 2 发才挂起：停在这第 2 发，屏上不许还画着「排队中」', async () => {
    const turn = queuedTurn('r260-queued-then-awaiting')
    await mountPanel([turn], [statusOk(), awaitingReply()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
    expect(statusCalls(), '挂起是终态：第 3 发不许再打').toBe(2)
    expect(faceOfTurn(turn).kind).toBe('parked-approval')
    expect(faceOfTurn(turn).headline).not.toMatch(/排队|前面还有/)
  })

  it('戊5 瞬断不停表这条反向半条没被放宽：断了 5 个周期仍在轮，随后读到挂起才停', async () => {
    const turn = queuedTurn('r260-blip-then-awaiting')
    await mountPanel([turn], [networkError(), networkError(), networkError(), awaitingReply()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
    expect(statusCalls(), '网络错误不算终止性判定').toBe(4)
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
    expect(statusCalls(), '读到挂起才停表').toBe(4)
  })

  it('戊6 401 那一族照旧叫停：queuePollStopper 与停表名单是两件事，本单没混', async () => {
    const turn = queuedTurn('r260-401-still-stops')
    const denied = Object.assign(new Error('Request failed with status code 401'), {
      isAxiosError: true,
      config: { url: `/queue/status/${REQUEST_ID}` },
      response: { status: 401, data: { detail: 'authentication_required' } },
    })
    await mountPanel([turn], [denied])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 3)
    expect(statusCalls(), '终止性判定一发叫停').toBe(1)
    expect(faceOfTurn(turn).kind).toBe('unreadable-stopped')
  })
})

// ==================== 己 · 判据⑤：零外部请求 ====================

describe('己 · 判据⑤ 私有化底线：这一格新增的东西不许带来任何外部请求', () => {
  it('己1 挂起这一轮从头到尾只打过排队那两枚自家端点', async () => {
    const turn = queuedTurn('r260-only-own-endpoints')
    await mountPanel([turn], [awaitingReply()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 6)
    const unique = [...new Set(hitPaths)].sort()
    expect(unique.join(' '), '本单不许新增第三枚端点：批准走既有那一屏，那里自己读它自己的账本')
      .toBe('/health/details /queue/stats /queue/status/{id}')
  })

  it('己2 三个被改的文件里零绝对地址（构建产物再扫一遍 googleapis / gstatic，见交工报告）', () => {
    const touched = panel + provenanceSrc + source('../QueueFace.vue')
    expect(touched, '写死的外部域名 = 断网就坏，本仓不接受').not.toMatch(/https?:\/\//)
  })
})
