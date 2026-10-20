/**
 * R268 · 判据⑥ · G04 反证钉：会话名单从服务端取回来，并与本机那份合并
 *
 * 病灶（改前取证，行号取本单基点 1142c27）：
 *   GET /sessions（app/api/v1/chat.py:3446）早就回 {id,title,updated_at,msg_count}，
 *   而左侧那一列会话只由 lib/sessions.js:93-113 的 loadSessions() 从 localStorage 组装 ——
 *   名单没有任何人读。于是换一台浏览器、或被退出登录洗一次本地态，员工问过的话就「不见了」，
 *   而后端那一条会话一直都在。这一格是接线题，不是新接口题（零后端改动）。
 * 🔴 App.vue:183-197 那一刀（退出整包清 localStorage）本单不改（块 F 独占），所以下面这一套
 *   只依赖服务端读数 + 内存 store：第 3 条用例直接在【本地态全空】的环境上取证。
 *
 * 反证怎么算红：把 mergeServerSessions 改回「只从 localStorage 组装」→ 甲组 3/4/5 红；
 * 把四种落不到并成一句 → 乙组最后两条红；点开正文取不到就切过去 → 乙组倒数第一条红；
 * 挂个 mount 期自动打 /sessions（那是会踩 r260 己1 那道门的另一种错）→ 甲组第 1 条红。
 *
 * 手法沿用 r198：createRenderer + 内存虚拟节点跑【真客户端生命周期】，网络层换成假实现。
 */
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, getCurrentInstance, h, nextTick, reactive } from 'vue'
import { routeLocationKey, routerKey } from 'vue-router'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() }, authedFetch: vi.fn() }
})

import ChatPanel from '../ChatPanel.vue'
import { TOKEN_KEY, http } from '../../lib/http'
import {
  SESSIONS_KEY,
  SESSION_READ,
  activeId,
  clearStoredSessions,
  loadSessions,
  messages,
  mergeServerSessions,
  pullBackendMessages,
  readBackendSessionList,
  resetSessions,
  serverSessionRow,
  sessionBodyMissing,
  sessionMoment,
  sessions,
} from '../../lib/sessions'

const panel = readFileSync(new URL('../ChatPanel.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const SSR_CONTEXT_KEY = Symbol.for('v-scx')

const SERVER_ROWS = [
  { id: 'srv-old', title: '上季度销售额', created_at: '2026-09-20T02:00:00+08:00', updated_at: '2026-09-20T02:00:00+08:00', msg_count: 4 },
  { id: 'srv-new', title: '差旅报销制度', created_at: '2026-09-24T09:00:00+08:00', updated_at: '2026-09-24T09:00:00+08:00', msg_count: 7 },
]

function axiosStatusError(status, detail) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    config: { url: '/sessions' },
    response: { status, data: { detail } },
  })
}

/** 一份按 URL 分派的假后端：/sessions 名单、/sessions/{id} 正文、其余回空。 */
function backend({ list = SERVER_ROWS, listError = null, body = null, bodyError = null } = {}) {
  const paths = []
  const get = vi.fn(async (url) => {
    const target = String(url)
    paths.push(target.startsWith('/sessions/') ? '/sessions/{id}' : target)
    if (target === '/sessions') {
      if (listError) throw listError
      return { data: Array.isArray(list) ? { sessions: list } : list }
    }
    if (target.startsWith('/sessions/')) {
      if (bodyError) throw bodyError
      return { data: body }
    }
    if (target === '/health/details') return { data: { problems: [] } }
    if (target === '/queue/stats') return { data: { queue_length: 0, processing: 0 } }
    return { data: {} }
  })
  return { get, paths }
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

let store = null

function installStorage(seed = {}) {
  store = new Map(Object.entries(seed))
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

async function mountPanel(get) {
  installStorage({ [TOKEN_KEY]: 'jwt-live' })
  http.get.mockImplementation(get)
  let instance = null
  const errors = []
  const app = createApp({
    __name: 'R268SessionHost',
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

beforeEach(() => {
  vi.useFakeTimers()
  resetSessions()
  clearStoredSessions()
  messages_reset()
})

function messages_reset() {
  activeId.value = ''
  sessions.value = []
}

afterEach(() => {
  mounted?.app.unmount()
  mounted = null
  vi.useRealTimers()
  http.get.mockReset()
})

describe('甲 · lib/sessions.js 那一格：读得到、并得进、盖不掉本机那一份', () => {
  it('名单一次都不读：挂载期与空转期都没有打 /sessions（伸手才发是这一格的前提）', async () => {
    const api = backend()
    await mountPanel(api.get)
    await vi.advanceTimersByTimeAsync(30_000)
    await settle()
    expect(api.paths, '面板常驻，挂载期自动读名单会变成每进一次页面多一枪').not.toContain('/sessions')
  })

  it('readBackendSessionList 真发 GET /sessions，并把后端那三枚字段原样收进来', async () => {
    const api = backend()
    http.get.mockImplementation(api.get)
    const read = await readBackendSessionList()
    expect(api.paths).toEqual(['/sessions'])
    expect(read.outcome).toBe(SESSION_READ.found)
    expect(read.rows.map(row => [row.id, row.title, row.msgCount])).toEqual([
      ['srv-old', '上季度销售额', 4],
      ['srv-new', '差旅报销制度', 7],
    ])
    expect(read.rows[0].bodyFetched).toBe(false)
  })

  it('换浏览器＝本地态全空：点一次取回，历史三条回到列表并落了盘', () => {
    const summary = mergeServerSessions(SERVER_ROWS.map(serverSessionRow).filter(Boolean))
    expect(summary).toMatchObject({ serverRows: 2, added: 2 })
    expect(sessions.value.map(item => item.title)).toEqual(['差旅报销制度', '上季度销售额'])
    expect(sessions.value[0].msgCount).toBe(7)
    const persisted = JSON.parse(localStorage.getItem(SESSIONS_KEY)).sessions
    expect(persisted.map(item => item.id)).toEqual(['srv-new', 'srv-old'])
  })

  it('并集不是覆盖：本机有正文的那一条不被服务端空壳洗掉', () => {
    sessions.value = [{
      id: 'srv-old', title: '我自己起的名字', msgCount: 12, updatedAt: 1758000000000,
      messages: [{ role: 'user', content: '本机已经写着的一问' }],
    }]
    const summary = mergeServerSessions(SERVER_ROWS.map(serverSessionRow))
    expect(summary.added, '本机已有同一 id，不该再算新增').toBe(1)
    expect(summary.total).toBe(2)
    const kept = sessions.value.find(item => item.id === 'srv-old')
    expect(kept.title, '本机自己起的名字不能被后端默认标题顶掉').toBe('我自己起的名字')
    expect(kept.msgCount, '本机有正文就问本机有几问').toBe(12)
    expect(kept.messages).toHaveLength(1)
  })

  it('排序认得两种时间形状：本机毫秒与后端 ISO 串排在一起', () => {
    sessions.value = [{ id: 'local', title: '本机', updatedAt: Date.parse('2026-09-21T00:00:00+08:00'), messages: [] }]
    mergeServerSessions(SERVER_ROWS.map(serverSessionRow))
    expect(sessions.value.map(item => item.id)).toEqual(['srv-new', 'local', 'srv-old'])
    expect(sessionMoment('不是时间')).toBe(0)
  })

  it('loadSessions 仍然读得回合并后的那份：取回不是只活在内存里', () => {
    mergeServerSessions(SERVER_ROWS.map(serverSessionRow))
    sessions.value = []
    loadSessions()
    expect(sessions.value.map(item => item.id)).toEqual(['srv-new', 'srv-old'])
    expect(sessions.value[0].title).toBe('差旅报销制度')
  })
})

describe('乙 · 面板接线：那枚按钮真办事，四种落不到各说各的一句话', () => {
  it('点「从服务器取回」只发一枪，并把并入几枚说在屏上', async () => {
    const api = backend()
    await mountPanel(api.get)
    await mounted.state.pullServerSessions()
    await settle()
    expect(api.paths.filter(path => path === '/sessions')).toHaveLength(1)
    expect(sessions.value.filter(item => item.fromServer).map(item => item.id)).toEqual(['srv-new', 'srv-old'])
    const face = mounted.state.serverPullFace(mounted.state.serverPull)
    expect(face.text).toContain('读到 2 条')
    expect(face.text).toContain('新并入 2 条')
    expect(mounted.state.sessionBodyMissing('srv-new'), '正文要点开才取，界面要说得出这一格').toBe(true)
  })

  it('后端回空名单：说的是「服务器上确实没有」，不是「没读到」', async () => {
    const api = backend({ list: [] })
    await mountPanel(api.get)
    await mounted.state.pullServerSessions()
    await settle()
    const text = mounted.state.serverPullFace(mounted.state.serverPull).text
    expect(text).toContain('没有可取回的会话')
    expect(text).toContain('不是「没读到」')
  })

  it('连不上／没权限／形状不对：三格三句话两两不同，且列表一个字都不动', async () => {
    const cases = [
      [axiosStatusError(503, { code: 'queue_unavailable', message: 'down' }), '这一次没读到'],
      [axiosStatusError(403, 'permission_denied'), '没取回来'],
      [null, '形状不是界面认的那一种'],
    ]
    const voices = []
    for (const [error, expectPhrase] of cases) {
      const api = backend({ list: error ? [] : 'not-a-list', listError: error })
      await mountPanel(api.get)
      const before = sessions.value.length
      await mounted.state.pullServerSessions()
      await settle()
      const text = mounted.state.serverPullFace(mounted.state.serverPull).text
      voices.push(text)
      expect(text).toContain(expectPhrase)
      expect(sessions.value.length, '落不到就别动列表').toBe(before)
    }
    expect(new Set(voices).size).toBe(3)
  })

  it('点开一条只有名单没有正文的会话：先把正文取回来再切，屏上不是一句空话', async () => {
    const api = backend({ body: { messages: [{ role: 'user', content: '后端那份正文' }] } })
    await mountPanel(api.get)
    mergeServerSessions(SERVER_ROWS.map(serverSessionRow))
    activeId.value = 'local-current'
    await mounted.state.openSession('srv-new')
    await settle()
    expect(api.paths).toContain('/sessions/{id}')
    expect(activeId.value, '正文到手才允许切过去').toBe('srv-new')
    expect(messages.value.map(item => item.content)).toEqual(['后端那份正文'])
    expect(mounted.state.sessionBodyFault).toBe(null)
    expect(sessions.value.find(item => item.id === 'srv-new').bodyFetched).toBe(true)
  })

  it('正文那一格落 404／403 各说一句，两句不同，也不切换', async () => {
    const voices = []
    for (const error of [axiosStatusError(404, 'resource_not_found'), axiosStatusError(403, 'permission_denied')]) {
      const api = backend({ bodyError: error })
      await mountPanel(api.get)
      mergeServerSessions(SERVER_ROWS.map(serverSessionRow))
      activeId.value = 'local-current'
      await mounted.state.openSession('srv-old')
      await settle()
      const fault = mounted.state.sessionBodyFault
      expect(fault.id).toBe('srv-old')
      voices.push(fault.text)
      expect(fault.text).toContain('正文')
      expect(activeId.value).toBe('local-current')
      expect(sessions.value.find(item => item.id === 'srv-old').bodyFetched, '没取回来就不算取回来').toBe(false)
    }
    expect(new Set(voices).size).toBe(2)
  })

  it('本机就有的那一条照旧直接切：这一格不该给老路子加一枪', async () => {
    const api = backend()
    await mountPanel(api.get)
    sessions.value = [{ id: 'mine', title: '本机这条', updatedAt: Date.now(), messages: [{ role: 'user', content: '一问' }] }]
    activeId.value = 'other'
    await mounted.state.openSession('mine')
    await settle()
    expect(api.paths).not.toContain('/sessions/{id}')
    expect(activeId.value).toBe('mine')
  })

  it('pullBackendMessages 只交回同一份 store，不另开第二份消息表', async () => {
    const api = backend({ body: { messages: [{ role: 'user', content: '后端正文', request_id: 'req-x' }] } })
    http.get.mockImplementation(api.get)
    mergeServerSessions([{ id: 'srv-new', title: '差旅报销制度', msg_count: 1, updated_at: '2026-09-24T09:00:00+08:00' }])
    activeId.value = 'srv-new'
    const read = await pullBackendMessages('srv-new')
    expect(read.outcome).toBe(SESSION_READ.found)
    expect(sessions.value).toHaveLength(1)
    expect(sessions.value[0].messages.map(item => item.content)).toEqual(['后端正文'])
    expect(sessionBodyMissing('srv-new')).toBe(false)
  })
})

describe('丙 · 接线形状与那一刀的关系（本单不改 App.vue）', () => {
  it('侧栏那枚按钮与那句回话都画得出来，且不新开第二份消息表', () => {
    expect(panel).toMatch(/data-testid="session-pull"/)
    expect(panel).toContain('从服务器取回')
    expect(panel).toMatch(/@click="pullServerSessions"/)
    expect(panel).toMatch(/data-testid="session-pull-face"/)
    expect(panel).toMatch(/data-testid="session-body-fault"/)
    expect(panel).toMatch(/@click="openSession\(s\.id\)"/)
  })

  it('面板侧不 import 服务端名单的第二套读法：名单与正文都只走 lib/sessions 那一份', () => {
    expect(panel).toMatch(/import \{[\s\S]{0,400}?mergeServerSessions[\s\S]{0,200}?\} from '\.\.\/lib\/sessions'/)
    expect(panel).not.toMatch(/http\.get\('\/sessions'\)/)
    expect(panel.match(/mergeServerSessions/g)).toHaveLength(2)
  })

  it('合并这件事不依赖退出时那一刀：本地态一行都没有也建得出列表', () => {
    installStorage({})
    globalThis.localStorage.clear()
    expect(localStorage.getItem(SESSIONS_KEY)).toBe(null)
    expect(mergeServerSessions(SERVER_ROWS)).toMatchObject({ serverRows: 2, added: 2, total: 2 })
    expect(JSON.parse(localStorage.getItem(SESSIONS_KEY)).sessions).toHaveLength(2)
  })
})