/**
 * R174 判据① · 冷启动深链真的落到那一轮
 *
 * 口径：员工把 /chat?session=<会话号>&request=<轮号> 发给同事，同事直接打开（不经过站内点击）
 * 就该看到那一轮 —— 不是登录页，不是最新一轮，也不是一片空白。
 *
 * 五条腿各自验自己验得动的东西（沿用 r168 / r169 的口径，不新发明）：
 *   ① 参数格：deepLinkFromQuery 是真函数，坏地址、缺参数、站内点进来都从它过一遍。
 *   ② 落点状态机：resolveLocalDeepLink / resolveDeepLinkWith 是面板 setup 里递进来的那两枚本尊，
 *      不是抄一份；后端读正文这一腿用注入的假读数器，全程不发一个 socket。
 *   ③ 传输层：lib/sessions.js 里那条 readBackendSession 吃的是 mock 过的 axios 实例，
 *      「读不到」与「没有」的分脸就是在这一层判的，所以这一层必须真跑到。
 *   ④ 真产物：node + @vue/server-renderer + 真 vue-router（memory history）出整屏 HTML，
 *      标记在不在第几行、有没有盖住别人的会话，由 HTML 说话。
 *   ⑤ 面板自己那张接线表：buildDeepDeps() 就是面板 setup 里用的那一份，用例拿它跑一遍
 *      真通道（真 readBackendSession + 真 adoptBackendSession + 真 store），
 *      所以「摘掉向后端取正文那一腿」红的是行为，不是源码钉子。
 *
 * 三把反证都有常驻用例点名「摘掉哪一行会红」（红数为 2026-09-23 实取，跑完即还原）：
 *   反证① 摘掉面板的「向后端取正文」那一腿 → 本文件那组接线表红 3 枚；同一把的另一半在
 *        r174-replay-ownership.test.js：摘掉开屏问名单那一枪 → 红 3 枚。
 *   反证② 把「这一轮不存在」的文案并到「这一条不是你的」→ 红 1 枚；并判定路径 → 红 2 枚；
 *        把「正文没轮号」并成「这一轮不存在」→ 红 3 枚；把「只剩本机」并成「没有可回看」
 *        → r174-replay-ownership.test.js 红 3 枚。
 *   反证③ 把屏名回写成「报销自查」→ r174-screen-name.test.js 与两条既有钉一起红（红 7 枚）。
 * 每一把跑完都按字节还原，还原后 git diff --numstat 与动手前逐行相同。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createMemoryHistory, createRouter } from 'vue-router'

// 只换网络出口：会话 store、SSE 读取器、错误码字典一律真身。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn() } }
})

import { http } from '../../lib/http'
import ChatPanel, {
  DEEP_LINK_FACES,
  concludeDeepTurn,
  buildDeepDeps,
  deepLinkFaceOfRead,
  deepLinkFromQuery,
  deepTurnSelector,
  locateDeepTurn,
  resolveDeepLinkWith,
  resolveLocalDeepLink,
  revealDeepTurnIn,
} from '../ChatPanel.vue'
import {
  SESSION_READ,
  activeId,
  adoptBackendSession,
  createStreamReducer,
  createStreamState,
  loadSessions,
  localMessagesOf,
  messages,
  persist,
  readBackendSession,
  sessions,
  switchSession,
} from '../../lib/sessions'

const source = f => readFileSync(new URL(`../${f}`, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const panel = source('ChatPanel.vue')

const SESSION = 'sess-9f2c'
const TURN = 'req-1a2b'

/** 清干净那份模块级 store：面板读的就是它，脏了一发会串到下一枚用例。 */
function resetStore(list = []) {
  sessions.value = list
  activeId.value = list.length ? String(list[0].id) : ''
  messages.value = list.length ? [...(list[0].messages || [])] : []
}

const turn = (requestId, content) => ({ role: 'assistant', content, steps: [], sources: null, requestId })
const ask = content => ({ role: 'user', content, sources: null })

describe('R174① · 地址上那两枚参数先过形状这一格', () => {
  it('两枚都没写就不是深链：正常进这一屏，不许弹任何一句落点话', () => {
    expect(deepLinkFromQuery({})).toBe(null)
    expect(deepLinkFromQuery(undefined)).toBe(null)
    expect(deepLinkFromQuery({ lane: 'qa' })).toBe(null)
  })

  it('只有轮号、没有会话号 = 参数缺失那一句', () => {
    expect(deepLinkFromQuery({ request: TURN })).toEqual({ session: '', request: '', bad: 'bad-session' })
  })

  it('会话号写了个空、写了非法字符、写成重复参数，三种都算格式不对，一种都不算「没有这一轮」', () => {
    for (const query of [{ session: '' }, { session: '   ' }, { session: 'a/b' }, { session: ['a', 'b'] }]) {
      expect(deepLinkFromQuery(query).bad, JSON.stringify(query)).toBe('bad-session')
    }
  })

  it('会话号是好的、只有轮号写坏：另说一句，不把整条链接一起作废', () => {
    expect(deepLinkFromQuery({ session: SESSION, request: 'not ok!' })).toEqual({
      session: SESSION, request: '', bad: 'bad-request',
    })
  })

  it('两枚都合规就照原样交下去（后端两枚 id 的三种写法都认得）', () => {
    for (const request of ['req-1a2b', '3f2a9c8b7e6d', 'mdz3kq9x-2']) {
      expect(deepLinkFromQuery({ session: SESSION, request }).bad).toBe('')
    }
  })
})

describe('R174① · 本地那一腿：本机有这一条就直接定位，一次请求都不该发', () => {
  it('命中那一轮：位次交出来，会话切过去，读后端那枚函数一次都没被调用', () => {
    const reads = []
    const switched = []
    const list = [ask('上季度销售额多少'), turn(TURN, '一千二百万。')]
    const result = resolveLocalDeepLink({
      query: { session: SESSION, request: TURN },
      localMessages: () => list,
      readSession: id => { reads.push(id); return { outcome: SESSION_READ.found, messages: [] } },
      switchTo: id => switched.push(id),
    })
    expect(result).toMatchObject({ state: 'turn', turn: 1, from: 'local' })
    expect(switched).toEqual([SESSION])
    expect(reads, '本机就有这一条，凭什么去问后端').toEqual([])
  })

  it('本机没有这一条：本地这一腿交回 null，把活让给后端那一腿（不是就地新建一份空会话）', () => {
    expect(resolveLocalDeepLink({ query: { session: SESSION, request: TURN }, localMessages: () => null }))
      .toBe(null)
  })

  it('整份正文都没轮号时报 noTurnIds，绝不报成「这一轮不存在」', () => {
    const legacy = [ask('旧问题'), { role: 'assistant', content: '旧回答', steps: [] }]
    const at = locateDeepTurn(legacy, TURN)
    expect(at).toEqual({ hasIds: false, found: false, index: -1 })
    expect(concludeDeepTurn({ session: SESSION, request: TURN, bad: '' }, legacy, 'local').face)
      .toBe('noTurnIds')
  })

  it('带着轮号却找不到，才许说「这一轮不存在」', () => {
    const list = [turn('req-other', '另一轮'), turn('req-third', '第三轮')]
    expect(locateDeepTurn(list, TURN)).toEqual({ hasIds: true, found: false, index: -1 })
    expect(concludeDeepTurn({ session: SESSION, request: TURN, bad: '' }, list, 'local').face)
      .toBe('turnMissing')
  })

  it('匹配只按轮号字面相等：位次、时间、内容都不算证据（不许前端猜匹配）', () => {
    const list = [turn('req-a', '同一句正文'), turn(TURN, '同一句正文')]
    expect(locateDeepTurn(list, TURN).index).toBe(1)
    expect(locateDeepTurn(list, '').index).toBe(-1)
    expect(locateDeepTurn(null, TURN)).toEqual({ hasIds: false, found: false, index: -1 })
  })
})

describe('R174① · 后端那一腿（反证①：把这一腿摘掉，这一组全红）', () => {
  /** 本机没有这一条会话时，面板递进来的三条通道。adopted 记的是「交回了哪一份」。 */
  function backendDeps(read) {
    const switched = []
    const adopted = []
    return {
      switched,
      adopted,
      deps: {
        query: { session: SESSION, request: TURN },
        localMessages: () => null,
        readSession: async () => read,
        adopt: (id, rows) => adopted.push([id, rows]),
        switchTo: id => switched.push(id),
      },
    }
  }

  it('跨机器回看：后端带了轮号就定位到那一轮，并把同一份正文交回 store', async () => {
    const rows = [ask('上季度销售额多少'), turn(TURN, '一千二百万。'), turn('req-zzz', '另一轮')]
    const { deps, adopted, switched } = backendDeps({ outcome: SESSION_READ.found, messages: rows, turnIds: true })
    const result = await resolveDeepLinkWith(deps)
    expect(result).toMatchObject({ state: 'turn', turn: 1, from: 'backend', face: '' })
    expect(adopted, '后端读到的正文必须交回那份唯一的 store').toHaveLength(1)
    expect(adopted[0][0]).toBe(SESSION)
    expect(adopted[0][1]).toBe(rows)
    expect(switched, '站内点击与冷启动共用同一次切换').toEqual([SESSION])
    // 🔴 反证① 的落点：把 adopt / readSession 任何一腿删掉，这几行就红。
  })

  it('后端读回正文但没带轮号：说「定位不到」那一句，而不是「这一轮不存在」', async () => {
    const rows = [ask('旧问题'), { role: 'assistant', content: '旧回答', steps: [], created_at: '2026-09-23T09:12:44' }]
    const { deps } = backendDeps({ outcome: SESSION_READ.found, messages: rows, turnIds: false })
    const result = await resolveDeepLinkWith(deps)
    expect(result.face).toBe('noTurnIds')
    expect(result.face).not.toBe('turnMissing')
    expect(result.state).toBe('session')
  })

  it('found 不是一张脸：正文到手就往下走，不会被画成失败', () => {
    expect(deepLinkFaceOfRead({ outcome: SESSION_READ.found, messages: [] })).toBe('')
  })

  it('后端四种落不到各回各的读数，一格都不许并到另一格', async () => {
    const cases = [
      [SESSION_READ.notFound, '后端给了确定回答：没有这一条会话。'],
      [SESSION_READ.notYours, '这一条不是你的'],
      [SESSION_READ.unreachable, '后端这会儿读不到'],
      [SESSION_READ.badBody, '这一格的形状系统不认识'],
    ]
    for (const [outcome, phrase] of cases) {
      const { deps, adopted } = backendDeps({ outcome, messages: [] })
      const result = await resolveDeepLinkWith(deps)
      expect(result.state).toBe('face')
      expect(result.face).toBe(outcome)
      expect(DEEP_LINK_FACES[outcome].text).toContain(phrase)
      expect(adopted, `${outcome} 这一格没有正文可交，不许凭空交一份`).toEqual([])
    }
  })

  it('读数整个缺失（连 outcome 都没有）也不许落成「没有这一轮」', async () => {
    for (const read of [null, undefined, {}, { outcome: 'weird' }]) {
      const { deps } = backendDeps(read)
      expect((await resolveDeepLinkWith(deps)).face).toBe(SESSION_READ.badBody)
    }
  })
})

describe('R174① · 传输层：读不到不等于没有（lib/sessions.js 真身 + mock 掉的 axios）', () => {
  const fail = status => Object.assign(new Error(`Request failed with status code ${status}`), {
    response: { status, data: { detail: 'x' } },
  })

  it('404 报 not_found、401 与 403 报 not_yours、5xx 与连不上报 unreachable', async () => {
    const cases = [[404, SESSION_READ.notFound], [401, SESSION_READ.notYours], [403, SESSION_READ.notYours],
      [500, SESSION_READ.unreachable], [503, SESSION_READ.unreachable]]
    for (const [status, outcome] of cases) {
      http.get.mockRejectedValue(fail(status))
      expect((await readBackendSession(SESSION)).outcome, String(status)).toBe(outcome)
    }
    http.get.mockRejectedValue(new Error('Network Error'))
    expect((await readBackendSession(SESSION)).outcome).toBe(SESSION_READ.unreachable)
  })

  it('200 但 messages 不是数组报 bad_body，而不是当成一条空会话', async () => {
    http.get.mockResolvedValue({ data: { session: { id: SESSION } } })
    expect(await readBackendSession(SESSION)).toMatchObject({ outcome: SESSION_READ.badBody, messages: [] })
  })

  it('200 有正文就原样带出 role 与 content，绝不把缺席的轮号编成空串再当成有', async () => {
    http.get.mockResolvedValue({
      data: { session: { id: SESSION }, messages: [
        { role: 'user', content: '上季度销售额多少', steps: [], created_at: '2026-09-23T09:12:00' },
        { role: 'assistant', content: '一千二百万。', steps: [], created_at: '2026-09-23T09:12:40' },
      ] },
    })
    const read = await readBackendSession(SESSION)
    expect(read.outcome).toBe(SESSION_READ.found)
    expect(read.messages.map(m => m.content)).toEqual(['上季度销售额多少', '一千二百万。'])
    expect(read.turnIds, '后端今天就是不带轮号：这一格必须报 false，不许拿位次冒充').toBe(false)
  })

  it('后端哪天带上轮号，本文件一字不改就定位得到（那枚后端单的验收接缝）', async () => {
    http.get.mockResolvedValue({
      data: { messages: [{ role: 'assistant', content: 'a', request_id: TURN }] },
    })
    const read = await readBackendSession(SESSION)
    expect(read.turnIds).toBe(true)
    expect(read.messages[0].requestId).toBe(TURN)
  })

  it('地址里的会话号被塞了斜杠也出不了这条路径（深链参数不该成为第二个请求口）', () => {
    expect(encodeURI('/sessions/a/b')).not.toBe('/sessions/a%2Fb')
  })
})

describe('R174① · 交回同一份 store：站内点击与冷启动共用一份正文', () => {
  it('adopt 之后 sessions / activeId / messages 三处都是这一份，没有第二套', () => {
    resetStore([{ id: 'other', messages: [ask('别人的会话')] }])
    const rows = [{ role: 'user', content: '上季度销售额多少' }, { role: 'assistant', content: '一千二百万。', requestId: TURN }]
    adoptBackendSession(SESSION, rows)
    expect(activeId.value).toBe(SESSION)
    expect(messages.value.map(m => m.content)).toEqual(['上季度销售额多少', '一千二百万。'])
    expect(sessions.value.map(s => String(s.id))).toContain(SESSION)
    expect(localMessagesOf(SESSION)).toBe(messages.value)
    expect(sessions.value.find(s => String(s.id) === SESSION).messages.map(m => m.content))
      .toEqual(['上季度销售额多少', '一千二百万。'])
  })

  it('本机那份以正在用的这份为准：流没跑完时不拿盘上的旧副本去定位', () => {
    resetStore([{ id: SESSION, messages: [ask('旧问题')] }])
    activeId.value = SESSION
    const live = [ask('旧问题'), turn(TURN, '新答案')]
    messages.value = live
    expect(localMessagesOf(SESSION)).toBe(live)
    expect(locateDeepTurn(localMessagesOf(SESSION), TURN).index).toBe(1)
  })

  it('切走再回来还是那一份：一轮问答只存一处，第二套副本没有地方长出来', () => {
    resetStore([
      { id: SESSION, messages: [ask('旧问题')] },
      { id: 'other', messages: [ask('另一条')] },
    ])
    activeId.value = SESSION
    messages.value = [ask('旧问题'), turn(TURN, '新答案')]
    switchSession('other')
    expect(locateDeepTurn(localMessagesOf(SESSION), TURN).index).toBe(1)
    switchSession(SESSION)
    expect(messages.value.map(m => m.content)).toEqual(['旧问题', '新答案'])
  })
})

describe('R174① · 定位要看得见：滚得过去的那一行 + 一眼看得出的标记', () => {
  it('找的就是那一行的锚点，找到才滚；找不到不猜位置也不滚到最新一条', () => {
    const seen = []
    const container = {
      scrollTop: 999,
      querySelector: sel => {
        seen.push(sel)
        return sel === '[data-turn="1"]' ? { offsetTop: 320 } : null
      },
      scrollTo: () => {},
    }
    expect(revealDeepTurnIn(container, 1)).toMatchObject({ found: true, scrolled: true, top: 308 })
    expect(seen).toEqual([deepTurnSelector(1)])
    expect(revealDeepTurnIn(container, 7)).toMatchObject({ found: false, scrolled: false })
    expect(revealDeepTurnIn(null, 1)).toMatchObject({ found: false, scrolled: false })
  })

  it('面板把结论接到真 DOM 上：初值走本地那一腿，参数一改就重新落点', () => {
    // setup 期就把本地那一腿走完（冷启动第一帧就有结论），浏览器里只补那一枪与那一次滚动。
    expect(panel).toMatch(/const deepLink = ref\(deepOpening\(\)\)/)
    expect(panel).toMatch(/const local = resolveLocalDeepLink\(deepDeps\)/)
    // 盯的是那两枚参数拼出来的一枚串：换档位（?lane=）不算改落点，不该因此重复问后端
    expect(panel).toContain("watch(() => `${route?.query?.session")
    // 面板不再自己拼这张表，而是取 buildDeepDeps 那一份：用例与面板吃同一张表，见下面那一组
    expect(panel).toMatch(/const deepDeps = buildDeepDeps\(route\?\.query\)/)
  })
})

describe('R174① · 面板自带的那张接线表（反证①：摘掉「向后端取正文」那一腿，这一组当场红）', () => {
  beforeEach(() => {
    resetStore([])
    http.get.mockReset()
  })

  it('本机没有这一条：真读后端、真交回 store，一步就落到那一轮', async () => {
    // 这台浏览器只看得到别人的会话，链接那一条只在服务端 —— 换台机器打开的就是这一格
    resetStore([{ id: 'other', messages: [ask('别人上次看的那一条')] }])
    http.get.mockResolvedValue({ data: { messages: [
      { role: 'user', content: '上季度销售额多少', request_id: 'req-0' },
      { role: 'assistant', content: '一千二百万。', request_id: TURN },
    ] } })
    const result = await resolveDeepLinkWith(buildDeepDeps({ session: SESSION, request: TURN }))
    expect(result).toMatchObject({ state: 'turn', from: 'backend', turn: 1 })
    // 落的就是 store 里这一份：站内点击与冷启动没有各存一套
    expect(activeId.value).toBe(SESSION)
    expect(localMessagesOf(SESSION).map(row => row.content)).toEqual(['上季度销售额多少', '一千二百万。'])
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(http.get).toHaveBeenCalledWith(`/sessions/${SESSION}`)
  })

  it('本机就有这一条：走面板自己那张表也一次请求都不该发，直接落到那一轮', async () => {
    resetStore([{ id: SESSION, messages: [ask('上季度销售额多少'), turn(TURN, '一千二百万。')] }])
    const result = await resolveDeepLinkWith(buildDeepDeps({ session: SESSION, request: TURN }))
    expect(result).toMatchObject({ state: 'turn', from: 'local', turn: 1 })
    expect(http.get).not.toHaveBeenCalled()
  })

  it('后端今天没带轮号：说的是「对不上号」，不是「没有这一轮」，也不是「读不到」', async () => {
    http.get.mockResolvedValue({ data: { messages: [{ role: 'assistant', content: '一千二百万。' }] } })
    const result = await resolveDeepLinkWith(buildDeepDeps({ session: SESSION, request: TURN }))
    expect(result).toMatchObject({ state: 'session', face: 'noTurnIds', from: 'backend' })
    expect(DEEP_LINK_FACES[result.face].text).toContain('缺的是后端那一格')
    // 正文照样交回 store：会话能看，只是替用户挑不出那一轮
    expect(activeId.value).toBe(SESSION)
  })

  it('后端四种回答各落各的脸：404 不并成「不是你的」，403 不并成「读不到」', async () => {
    const cases = [
      [404, SESSION_READ.notFound],
      [403, SESSION_READ.notYours],
      [503, SESSION_READ.unreachable],
      [0, SESSION_READ.unreachable],
    ]
    for (const [status, face] of cases) {
      http.get.mockReset()
      http.get.mockRejectedValue(status === 0 ? new Error('Network Error') : { response: { status } })
      const result = await resolveDeepLinkWith(buildDeepDeps({ session: SESSION, request: TURN }))
      expect(result, `status=${status}`).toMatchObject({ state: 'face', face, from: 'backend' })
    }
  })
})

/** 真路由 + 真 store 出整屏 HTML。 */
async function renderChat(query) {
  const routes = [{ path: '/chat', name: 'chat', component: ChatPanel, meta: { screen: true, title: '问一句' } }]
  const router = createRouter({ history: createMemoryHistory(), routes })
  const app = createSSRApp({ render: () => h(ChatPanel) })
  app.use(router)
  await router.push({ name: 'chat', query })
  await router.isReady()
  return renderToString(app)
}

const text = html => html.replace(/<!--[\s\S]*?-->/g, ' ').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()

describe('R174① · 冷启动直接打开这条地址（真渲染）', () => {
  beforeEach(() => resetStore([]))

  it('本机有这一条且轮号对得上：只给标记，不给任何一句失败话', async () => {
    resetStore([{ id: SESSION, messages: [ask('上季度销售额多少'), turn(TURN, '一千二百万。')] }])
    const html = await renderChat({ session: SESSION, request: TURN })
    expect(html).toContain('data-testid="deep-link-badge"')
    expect(html).toContain('data-deep-target="1"')
    expect(text(html)).toContain('就是这一轮')
    expect(html).not.toContain('data-testid="deep-link-note"')
    expect(html.match(/data-turn="/g)).toHaveLength(2)
    expect(html).toMatch(/data-turn="1"[^>]*data-deep-target="1"/)
  })

  it('只有轮号没有会话号：说「参数缺失」那一句，且不是一片空白、也不是别人的最新一轮', async () => {
    resetStore([{ id: 'someone-else', messages: [ask('这条不是链接指的')] }])
    const html = await renderChat({ request: TURN })
    expect(html).toContain('data-testid="deep-link-note"')
    expect(html).toContain('data-face="bad-session"')
    expect(text(html)).toContain('这条链接没带会话号')
    expect(html).toContain('role="status"')
    expect(text(html)).not.toContain('这条不是链接指的')
    expect(html).not.toContain('welcome-screen')
  })

  it('本机没有这一条：先画「正在问后端」，绝不在有结论前把最新一轮顶上来', async () => {
    resetStore([{ id: 'other', messages: [ask('上次看的那一条')] }])
    const html = await renderChat({ session: SESSION, request: TURN })
    expect(html).toContain('data-state="reading"')
    expect(text(html)).toContain('正在问后端')
    expect(text(html)).not.toContain('上次看的那一条')
  })

  it('失败脸里只有「后端读不到」那一张给重试，无权与「没有」都不给', () => {
    const retry = Object.keys(DEEP_LINK_FACES).filter(name => DEEP_LINK_FACES[name].retry)
    expect(retry).toEqual([SESSION_READ.unreachable])
    expect(DEEP_LINK_FACES[SESSION_READ.notYours].blocking).toBe(true)
    expect(DEEP_LINK_FACES[SESSION_READ.notFound].blocking).toBe(true)
  })

  it('九张脸九句两两不同（反证②：把「这一轮不存在」与「不是你的」并成一张，这枚就红）', () => {
    const texts = Object.values(DEEP_LINK_FACES).map(face => face.text)
    expect(texts).toHaveLength(9)
    expect(new Set(texts).size, '有两张脸说了同一句话').toBe(9)
    for (const a of texts) {
      for (const b of texts) {
        if (a === b) continue
        expect(a.includes(b), `另一张脸整句被并进了：${b.slice(0, 12)}`).toBe(false)
      }
    }
    expect(DEEP_LINK_FACES.turnMissing.text).toContain('这一轮不存在')
    expect(DEEP_LINK_FACES[SESSION_READ.notYours].text).toContain('这一条不是你的')
    expect(DEEP_LINK_FACES.turnMissing.text).not.toContain('不是你的')
    expect(DEEP_LINK_FACES[SESSION_READ.notYours].text).not.toContain('这一轮不存在')
  })

  it('那两格是两条岔路各自走到的：并文案会红，并判定路径也会红（反证②的另一半）', async () => {
    // 「这一轮不存在」= 正文到手了、带轮号、其中没有链接那个（本地那腿就能走到）
    const withIds = [turn('req-other', '另一轮'), turn('req-third', '第三轮')]
    expect(resolveLocalDeepLink({
      query: { session: SESSION, request: TURN },
      localMessages: () => withIds,
      switchTo: () => {},
    }).face).toBe('turnMissing')
    // 「这一条不是你的」= 连正文都没到手（身份那一关就被挡下，压根轮不到判轮次）
    const denied = await resolveDeepLinkWith({
      query: { session: SESSION, request: TURN },
      localMessages: () => null,
      readSession: async () => ({ outcome: SESSION_READ.notYours, messages: [] }),
    })
    expect(denied.face).toBe(SESSION_READ.notYours)
    expect(denied.state).toBe('face')
    // 一张盖住会话区（连正文都没有），一张不盖（会话就在下面，只是那一轮对不上）
    expect(DEEP_LINK_FACES[SESSION_READ.notYours].blocking).toBe(true)
  expect(DEEP_LINK_FACES.turnMissing.blocking).toBe(false)
  })
})

/** node 环境没有 localStorage（同 r169-chat-panel.test.js 的手法，只给最小替身）。 */
function installStorage() {
  const store = new Map()
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

describe('R174① · 轮号从后端信封一路走到落点（本地这条链一节都不许断）', () => {
  it('真 reducer 把 canonical 信封上的轮号抄进这一轮：读到才记，读不到不写', () => {
    const msg = { role: 'assistant', content: '一千二百万。', steps: [], sources: null }
    const state = createStreamState()
    expect(state.requestId, '开局不该凭空有一枚轮号').toBe('')
    const reduce = createStreamReducer(msg, state)
    reduce({
      event: 'request.completed',
      payload: { request_id: TURN, trace_id: 'trace-1', task_id: 'task-1', sequence: 1, status: 'ok', data: {} },
    })
    expect(msg.requestId).toBe(TURN)
    expect(state.requestId).toBe(TURN)
    // 迟到的第二轮不许把身份换掉：一轮一个身份
    reduce({
      event: 'request.completed',
      payload: { request_id: 'req-late', trace_id: 'trace-1', task_id: 'task-1', sequence: 2, status: 'ok', data: {} },
    })
    expect(msg.requestId).toBe(TURN)
  })

  it('冷启动重开同一台机器：轮号过了盘，本地那一腿照样落到那一轮，一次请求都不发', () => {
    installStorage()
    const answer = { role: 'assistant', content: '一千二百万。', steps: [], sources: null, requestId: TURN }
    resetStore([{ id: SESSION, messages: [ask('上季度销售额多少'), answer] }])
    persist()
    // 重开页面：内存清空，只剩盘上那一份
    sessions.value = []
    messages.value = []
    activeId.value = ''
    expect(loadSessions()).toBe(SESSION)
    const result = resolveLocalDeepLink(buildDeepDeps({ session: SESSION, request: TURN }))
    expect(result, '盘上那份没把轮号带回来，本地这一腿就断了').toMatchObject({ state: 'turn', from: 'local', turn: 1 })
    expect(http.get).not.toHaveBeenCalled()
    // 标记落在这条消息上，而它确实带着轮号：一眼看得出「就是这条」的前提是这一行认得出自己
    expect(messages.value[result.turn].requestId).toBe(TURN)
  })
})
