/**
 * R282 · queueFace 欠 cancel_requested 的那一张脸（员工按了中断，界面不许说「系统执行失败」）
 *
 * 病灶（改前取证取的是本单基点 ec42480 上真跑出来的结果，不是推断）：
 *   lib/provenance.js:349 queueFace 逐格判 queued / processing / done / cancelled / expired /
 *     awaiting_approval，唯独没有 cancel_requested 那一格，于是它落到 :416 那格 failed 兜底：
 *     「这一轮在后台执行失败，没有产出答案」（tone=danger）。同文件 :250 的状态清单注释里
 *     明明写着 cancel_requested 在后端存在 —— 只有分支没做。
 *   契约 docs/api/contract-v1.md:611-613：cancel_requested 是【非终态】，cancel() 在任务离开
 *     pending 列表之后按下，标记写进台账、由握着任务的 worker 下一次检查落成 cancelled；
 *     从这里起它只会落 cancelled，永远不会变成 done。写点 app/common/reliable_queue.py:478-486，
 *     读数出口 app/api/v1/chat.py:4361-4368（status 原样交回，failure 那一格恒带）。
 *   为什么这不是纸面缺陷：调用点 ChatPanel.vue:1317 交出去的是【落盘读数 msg.queue】那一格，
 *     而 R268 在 :1310 加的守卫前置条件是 read && —— 读数表为空时整条守卫直接绕过。乙组复现的
 *     就是这一格，手法与 r268 甲组第 3 条同一份（restoreQueuedTurns 只在 onMounted 跑一次，
 *     换进 messages 的轮次不会自己长出读数）。
 *
 * 三把反证刀各自咬什么（摘掉修复必红，逐枚在交工报告里贴 AssertionError 原文）：
 *   刀① provenance.js 退回本单基点那一版（新分支不存在）⇒ 甲1 甲2 甲3 甲4 甲5 乙1 乙2 丙1 丁2 红；
 *   刀② 把 cancel_requested 并进 cancelled 那一格 ⇒ 甲1（并格）与甲2（说了「已取消」）红；
 *   刀③ 把新分支挪到 failed 兜底【之后】⇒ 甲1 甲4 乙1 乙2 红（顺序钉，与 r260 那枚同族）。
 *
 * 手法沿用本仓既有那一份：没有 jsdom / @vue/test-utils，也不 npm i。面板那半走 createRenderer
 * + 内存虚拟节点跑真客户端生命周期，网络层 vi.mock lib/http，时钟是假的，一格 3 秒不真等。
 */
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, getCurrentInstance, h, nextTick, reactive, unref } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { routeLocationKey, routerKey } from 'vue-router'

vi.mock('../http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() }, authedFetch: vi.fn() }
})

import ChatPanel from '../../components/ChatPanel.vue'
import QueueFace from '../../components/QueueFace.vue'
import { TOKEN_KEY, authedFetch, http } from '../http'
import { queueFace } from '../provenance'
import { activeId, messages } from '../sessions'

const source = f => readFileSync(new URL(f, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const provenanceSrc = source('../provenance.js')
const panel = source('../../components/ChatPanel.vue')

const QUEUE_MS = 3000
const REQUEST_ID = 'req-r282'
const SSR_CONTEXT_KEY = Symbol.for('v-scx')
/** 屏上那句人话里不许夹 snake_case 裸码名（V6 闸门同一条口径）。 */
const BARE_CODE = /[一-鿿][^<>]*\b[a-z][a-z0-9]*(_[a-z0-9]+)+/
/** 契约 Long Task Status 的整份词表（docs/api/contract-v1.md:598），逐格枚举用。 */
const VOCABULARY = ['queued', 'processing', 'cancel_requested', 'done', 'cancelled', 'failed', 'dead', 'awaiting_approval', 'expired']
/** 还没落定的那一族（failed 与 dead 同住兜底那一格，是判据④裁过的，见丁组）。 */
const NOT_THE_FALLBACK = ['queued', 'processing', 'cancel_requested', 'done', 'cancelled', 'expired', 'awaiting_approval']

/** 后端在 cancel_requested 这一格真交出来的形状：position 只有 queued 那一支才有（chat.py:4373）。 */
const cancelRead = (over = {}) => ({
  status: 'cancel_requested',
  request_id: REQUEST_ID,
  position: null,
  failure: { attempts: 1, last_error: null, max_attempts: 3 },
  result: '',
  approval: null,
  ...over,
})

const faceOfStatus = (status) => queueFace(status === 'done'
  ? { status, result: '答案正文' }
  : cancelRead({ status }))

const statusOk = (over = {}) => ({ data: { status: 'queued', request_id: REQUEST_ID, position: 3, ...over } })
const cancelRequestedReply = () => ({ data: cancelRead() })

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

/** 一条随会话落过盘的历史轮：msg.queue 带着后端那一格状态，读数表里没有它的份。 */
const historyTurn = (status, mid = 'r282-history') => ({
  role: 'assistant', content: '', steps: [], mid,
  queue: { requestId: REQUEST_ID, status },
})

async function mountPanel(turns, replies) {
  installStorage({ [TOKEN_KEY]: 'jwt-live' })
  activeId.value = 'r282-session'
  messages.value = turns
  http.get.mockImplementation(pollScript(...(replies || [statusOk()])))
  let instance = null
  const errors = []
  const app = createApp({
    __name: 'R282QueueHost',
    setup: ChatPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div', { id: 'r282-host' })
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

/** 换进一条落盘的轮次：restoreQueuedTurns 只在 onMounted 跑过一次，它不会长出活读数。 */
const putHistory = (turn) => { messages.value = [turn] }

const faceOfTurn = (turn, index = 0) => mounted.state.queueFaceOf(turn, index)
const readOfTurn = (turn) => {
  const bag = unref(mounted.state.queueReads) || {}
  return bag[mounted.state.turnKey(turn, 0)] || null
}
const voice = (face) => `${face.headline}${face.detail}`

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

// ==================== 甲 · 判据①② 这一格有自己的一张脸，而且是过渡态 ====================

describe('甲 · 判据①② cancel_requested 单独一张脸：两头都不许站，形状是过渡态', () => {
  it('甲1 它不是 failed 兜底，也不是 cancelled：kind 单独一格（刀① 摘分支 / 刀② 并格都红在这里）', () => {
    const face = queueFace(cancelRead())
    expect(face.kind, '改前这一格直接落进 queueFace 最后的 failed 兜底（同 r260 乙2 的形状）').not.toBe('failed')
    expect(face.kind).toBe('cancel-requested')
    expect(face.kind, '并到 cancelled 那一格就是替后端宣布「已取消」').not.toBe('cancelled')
    expect(face.tone, 'tone=danger 就是「这一轮失败了」的另一张脸').not.toBe('danger')
  })

  it('甲2 词面只说「已登记 / 落定之前」，两句假话一个字都不许出现', () => {
    const face = queueFace(cancelRead())
    expect(face.headline).toContain('取消已登记')
    expect(face.detail).toContain('落定之前')
    expect(voice(face), '员工自己按了中断，界面反过来说系统坏了就是本单病灶')
      .not.toMatch(/失败|没有产出答案|出错了|异常|报错/)
    expect(voice(face), '回执还没落，界面不许替后端宣布结果').not.toMatch(/已取消|已经取消|取消成功/)
    expect(voice(face), '契约：这一格永远不会变成 done，也就不许许诺会有答案')
      .not.toMatch(/跑完会自动|稍后可查回|答案已补/)
  })

  it('甲3 过渡态的形状照 queued / processing 的既有惯例：tone=info、ahead=null', () => {
    const face = queueFace(cancelRead())
    expect(face.tone).toBe('info')
    expect(face.tone, '非终态这一族在本件里就是 info（queued / processing 同档）').toBe(queueFace({ status: 'processing' }).tone)
    expect(face.ahead, '任务已离开待发队列，后端只在 status === queued 那一支给 position（chat.py:4373）：没有位次读数就填 null，不补 0 也不编人数').toBe(null)
    expect(queueFace({ status: 'queued', position: null }).ahead, '与「位次读不到」那一格同一口径').toBe(face.ahead)
  })

  it('甲3b 不带动作按钮也不给 retry：重发同一轮不是「继续中断」', () => {
    const face = queueFace(cancelRead())
    expect(face.retryable, '写明 false：这一轮不必重发（照 awaitingApprovalFace 的写法）').toBe(false)
    expect(face.action ?? null, '不给任何动作入口：出路就在员工已经按下的那一枚上').toBe(null)
    expect(face.cancellable, 'lib 这一层不许顺手把「不排了」置真：这一轮已经不排了').toBeUndefined()
  })

  it('甲4 顺序钉（源码级）：新分支排在 failed 兜底【之前】（刀③ 挪到之后必红）', () => {
    const at = provenanceSrc.indexOf("if (status === 'cancel_requested') {")
    const fallback = provenanceSrc.indexOf("kind: 'failed',")
    expect(at, '新分支根本不在源码里 —— 刀① 的形状').toBeGreaterThan(-1)
    expect(fallback).toBeGreaterThan(-1)
    expect(at, '排在兜底之后就永远读不到：与 r260 给 awaiting_approval 立的顺序规矩同族').toBeLessThan(fallback)
  })

  it('甲5 九枚词表逐格枚举：这一格与别的任何一格都不重，兜底那句也不借', () => {
    const mine = faceOfStatus('cancel_requested').headline
    for (const other of VOCABULARY.filter(item => item !== 'cancel_requested')) {
      expect(faceOfStatus(other).headline, `${other} 那一格与 cancel_requested 说了同一句话`).not.toBe(mine)
    }
    expect(new Set(NOT_THE_FALLBACK.map(faceOfStatus).map(face => face.headline)).size,
      '还没落定的那一族两两不重（failed 与 dead 共用兜底那一格是判据④裁过的，见丁组）').toBe(NOT_THE_FALLBACK.length)
  })
})

// ==================== 乙 · 判据① 的屏幕半：落盘读数那一格真的画过错话 ====================

describe('乙 · 判据① 重新打开一条会话时这一格画的是哪句人话（病灶复现）', () => {
  it('乙0 前提守门：这一格走的确实是 msg.queue 那一支，否则下面全是假绿', async () => {
    await mountPanel([historyTurn('queued', 'r282-seed')])
    const turn = historyTurn('cancel_requested')
    putHistory(turn)
    expect(readOfTurn(turn), '没有活读数：queueFaceOf 才会把落盘那一格交给 queueFace（ChatPanel.vue:1317）').toBe(null)
    expect(faceOfTurn(turn), '落盘读数在位，界面才有话可说').toBeTruthy()
    expect(mounted.errors).toEqual([])
  })

  it('乙1 历史轮落着 cancel_requested：屏上不许是「后台执行失败」，要是「取消已登记」（刀① 刀③都红在这里）', async () => {
    await mountPanel([historyTurn('queued', 'r282-seed')])
    const turn = historyTurn('cancel_requested')
    putHistory(turn)
    const face = faceOfTurn(turn)
    expect(voice(face), '改前上屏的就是「这一轮在后台执行失败，没有产出答案」——本单病灶的屏幕半')
      .not.toMatch(/失败|没有产出答案/)
    expect(face.kind).toBe('cancel-requested')
    expect(face.headline).toContain('取消已登记')
  })

  it('乙2 真 QueueFace 上屏：data-kind 与那句话都在，三枚按钮一枚都不画', async () => {
    await mountPanel([historyTurn('queued', 'r282-seed')])
    const turn = historyTurn('cancel_requested')
    putHistory(turn)
    const face = faceOfTurn(turn)
    const html = await renderToString(h(QueueFace, { face, stats: null }))
    expect(html).toContain('data-testid="queue-face"')
    expect(html).toContain('data-kind="cancel-requested"')
    expect(html).toContain('取消已登记')
    expect(html).not.toContain('data-testid="queue-retry"')
    expect(html).not.toContain('data-testid="queue-action"')
    expect(html, '已经不排了的一轮再给一枚「不排了」就是假控件').not.toContain('data-testid="queue-cancel"')
    expect(html, '给人看的句子里不许夹 snake_case 码名').not.toMatch(BARE_CODE)
  })

  it('乙3 活读数那一支仍走面板既有守卫（:1310）：两条腿到达同一格，说的是同一句话', async () => {
    const turn = historyTurn('queued', 'r282-live')
    await mountPanel([turn], [cancelRequestedReply()])
    await vi.advanceTimersByTimeAsync(QUEUE_MS * 2)
    expect(readOfTurn(turn).status, '前提：这一轮读到的是 cancel_requested').toBe('cancel_requested')
    const face = faceOfTurn(turn)
    expect(face.kind, '有活读数时面板在 :1310 就拦下了（R268 那条守卫本单一个字没动）').toBe('cancel-requested')
    expect(voice(face)).toBe(voice(queueFace(cancelRead())))
  })
})

// ==================== 丙 · 判据①「同一件事全站一种说法」：措辞只剩一处出处 ====================
//
// 改口说明（R293 · 业主判定：面板那份本地措辞是第二个事实源，删）：
// R282 写下这一组时，面板里另存着一份 headline / detail / tone，所以它能做的极限是「抠出那段函数
// 体，钉它与 lib 那份逐字相等」。R293 把面板那一份删了、改为委派 lib，于是抠不到字面量：旧 :332-
// :334 那三条 toBeTruthy 会红，旧 :339-:341 那三条更危险——它们会变成 null === null 一路假绿过去。
// 这一组因此换成「面板不再持有自己的措辞」。三条都只变严，没有一条变宽：
//   旧组只在抠到字面量时比三枚字段（headline / detail / tone），kind / retryable / ahead / action
//   一枚都没比；新组拿整枚对象 toEqual，多一枚少一枚都红。
//   旧组对「面板另存一份措辞」只能在事后量距离；新组先把两句字面量判死在面板全文里，不给它漂完再
//   抓的机会，也堵掉「两份恰好同文所以逐字相等成立」这条旧钉根本抓不到的路。
//   取脸入口被删或被改名照旧红：委派不等于入口消失（r268 :387 拿的就是这个入口）。
//
// 顺手记一笔（R293）：乙组那三枚钉的前提是【落盘那一格里存着 cancel_requested】，R282 当时靠测试
// 自己手搭 historyTurn('cancel_requested') 才成立，面板没有任何一处写得出这一格。写点在 R293 补上
// （ChatPanel.vue:1506-1511）。🔴 总控并树时现取：`components/__tests__/r293-cancel-requested-persist.test.js` **还不存在**（Test-Path 为 False）⇒ 这一格今天只有写点、没有真路径凭据，由 **R293 第二棒**补，补上之前这句话不许被当成已验。

describe('丙 · 判据③ 措辞的唯一出处在 lib，面板一份都不许持有（自持措辞必红）', () => {
  const pendingBlock = /function queueCancelPendingFace\(\) \{([\s\S]*?)\n\}/.exec(panel)
  const pendingSrc = pendingBlock ? pendingBlock[1] : ''

  it('丙0 前提守门：面板仍持有这一格的取脸入口，而它只做委派（抠不出来本组就是假绿）', () => {
    expect(pendingBlock, '面板的 queueCancelPendingFace 被删或改了名：本组钉的就是空气').toBeTruthy()
    expect(pendingSrc.trim(), '函数体抠空了：入口还在，可核对的实现不在').toBeTruthy()
    expect(pendingSrc, '这一格必须委派给 lib/provenance.js:386 那一张脸，不许就地组词')
      .toMatch(/return queueFace\(\{ status: 'cancel_requested' \}\)/)
  })

  it('丙1 唯一出处：两句措辞在面板全文不存在，而面板取回的脸逐字等于 lib 那一张整枚', async () => {
    expect(panel, '「取消已登记」那一句只许住在 lib 一处').not.toMatch(/headline:\s*'取消已登记/)
    expect(panel, '收尾那一句只许住在 lib 一处').not.toMatch(/detail:\s*'取消标记已经写进队列/)
    expect(panel, 'lib 那句 detail 的正文只要在面板里再出现一份，就是第二个事实源')
      .not.toContain('后台正在收尾，落定之前它不会再回答任何东西')
    const turn = historyTurn('queued', 'r282-bing')
    await mountPanel([turn])
    expect(mounted.state.queueCancelPendingFace(), '面板这张脸必须就是 lib 那一张：字段一枚不多、一枚不少')
      .toEqual(queueFace(cancelRead()))
  })

  it('丙2 口径出处对得上：面板 :1447 / :1495 那两句写的就是这一格，用词一字不差地跟着走', () => {
    expect(panel, '契约口径：这一格只能说「已登记」').toMatch(/是 cancel_requested（任务已经离开待发队列、等 worker 收尾）只能说「已登记」/)
    expect(panel, '契约口径：落定之前表继续开着').toMatch(/落定之前那一格（cancel_requested）/)
    const face = queueFace(cancelRead())
    expect(face.headline, '「已登记」这三枚字必须上屏').toContain('已登记')
    expect(face.detail, '「落定之前」这一句必须上屏').toContain('落定之前')
  })
})

// ==================== 丁 · 判据④ dead 的结论钉（本单不给它加脸） ====================

describe('丁 · 判据④ dead 落在兜底那一格是真话：本单不加脸，加脸要先过这组钉', () => {
  it('丁1 dead 仍然是兜底那一格，而那句对它是真话（后端自己就叫它终态失败）', () => {
    const face = queueFace({ status: 'dead', failure: { attempts: 3, max_attempts: 3, last_error: 'task_timeout' } })
    expect(face.kind, 'dead 由 fail_or_retry 落盘（reliable_queue.py:460-462）：重试用完、或契约判定重试也不会变；本轮确实没产出答案').toBe('failed')
    expect(face.headline).toContain('没有产出答案')
    expect(face.detail, '兜底那句还带着尝试次数与归类后的原因，不是空泛一句「出错了」').toContain('3/3')
  })

  it('丁2 它与 cancel_requested 的分别不是一句话的事：dead 是终态、那一格是非终态', () => {
    const dead = queueFace({ status: 'dead' })
    const pending = queueFace(cancelRead())
    expect(dead.tone).toBe('danger')
    expect(pending.tone).not.toBe(dead.tone)
    expect(pending.headline).not.toBe(dead.headline)
    expect(pending.retryable, 'dead 那一格给不给 retry 是兜底既有的账，本单不改；过渡态一律不给').toBe(false)
  })
})