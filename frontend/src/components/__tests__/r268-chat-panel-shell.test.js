/**
 * R268 · 判据⑥ · G15 / G20 / G17 反证钉：删会话两步、按钮接原语、屏名与路由名同源
 *
 * 三格一屏，各自的病灶（行号取本单基点 1142c27）：
 *   G15  ChatPanel.vue:448  删一条会话用的是浏览器原生 confirm —— 全站只剩两枚之一，与仓里
 *        已经有的那套两步内联确认（ArtifactList.vue:141 advanceDelete，DataPanel.vue:10 就是这么
 *        import 的）并存两套词汇。本件把这一格接到【那一套】上，不新建第三套。
 *   G20  ChatPanel.vue 里 10 枚裸 <button>（UiButton / UiDialog 原语早在树上），控件各写各的
 *        焦点、忙碌、禁用与色值 —— 接原语，视觉沿用既有那几枚类。
 *   G17  路由那一屏叫「问一句」（frontend/src/router/index.js:87 meta.title），页内标题自己写着另一个名字。
 *        🔴 router 不在本单写域（块 F 持有），这里只把【页内】统一到 meta.title 那一处真源。
 *
 * 反证怎么算红：把 deleteSession 改回 `if (!confirm(...)) return` → 甲组第 1、2、3 条全红；
 * 把任意一枚按钮退回裸 <button> → 乙组第 1 条红；把页内屏名改回原来那句 → 丙组两条都红。
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

import UiButton from '../ui/UiButton.vue'
import ChatPanel from '../ChatPanel.vue'
import { routes } from '../../router/index.js'
import { TOKEN_KEY, http } from '../../lib/http'
import { SESSIONS_KEY, activeId, messages, resetSessions, sessions } from '../../lib/sessions'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const panel = read('../ChatPanel.vue')
const queueFace = read('../QueueFace.vue')
const SSR_CONTEXT_KEY = Symbol.for('v-scx')
const SCREEN_NAME = '问一句'

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

function row(id, title, extra = {}) {
  return {
    id, title, msgCount: 2, updatedAt: Date.now(), dataFilename: '',
    messages: [{ role: 'user', content: title, mid: `${id}-u` }, { role: 'assistant', content: '答', mid: `${id}-a` }],
    ...extra,
  }
}

async function mountPanel(rows) {
  installStorage({ [TOKEN_KEY]: 'jwt-live' })
  http.get.mockImplementation(async (url) => {
    if (String(url) === '/health/details') return { data: { problems: [] } }
    return { data: {} }
  })
  http.delete.mockResolvedValue({ status: 200, data: {} })
  activeId.value = rows[0].id
  sessions.value = rows
  messages.value = [...rows[0].messages]
  let instance = null
  const errors = []
  const app = createApp({
    __name: 'R268ShellHost',
    setup: ChatPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div', { id: 'r268-shell-host' })
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

const ids = () => sessions.value.map(item => item.id)

const deleteCalls = () => http.delete.mock.calls.map(call => String(call[0]))

beforeEach(() => {
  vi.useFakeTimers()
  resetSessions()
  messages.value = []
  sessions.value = []
  activeId.value = ''
})

afterEach(() => {
  mounted?.app.unmount()
  mounted = null
  vi.useRealTimers()
  http.get.mockReset()
  http.post.mockReset()
  http.delete.mockReset()
})

describe('甲 · G15 删一条会话是两步，而且用的是仓里已有的那一套状态机', () => {
  it('这一屏不再出现浏览器原生 confirm（全站只剩两枚之一，本单收掉一枚）', () => {
    expect(panel).not.toMatch(/[^a-zA-Z]confirm\s*\(/)
    expect(panel).not.toContain('window.confirm')
    expect(panel).toMatch(/import \{[\s\S]{0,200}?advanceDelete[\s\S]{0,200}?\} from '\.\/ArtifactList\.vue'/)
  })

  it('第一次点击只把这一行改成确认文案，一个请求都不发', async () => {
    await mountPanel([row('keep-me', '留着这条'), row('drop-me', '删掉这条')])
    expect(mounted.state.sessionDeleteLabel('drop-me')).toBe('✕')
    await mounted.state.deleteSession('drop-me')
    await settle()
    expect(http.delete).not.toHaveBeenCalled()
    expect(ids()).toContain('drop-me')
    expect(mounted.state.sessionDeleteLabel('drop-me'), '待确认那一行说的是确认文案').toBe('确认删除？')
  })

  it('同一行第二次点击才真删：本机那份与服务端那份都去掉', async () => {
    await mountPanel([row('keep-me', '留着这条'), row('drop-me', '删掉这条')])
    await mounted.state.deleteSession('drop-me')
    await settle()
    await mounted.state.deleteSession('drop-me')
    await settle()
    expect(deleteCalls()).toEqual(['/sessions/drop-me'])
    expect(ids()).toEqual(['keep-me'])
    expect(localStorage.getItem('eb_msg_drop-me')).toBe(null)
    expect(mounted.state.pendingSessionDelete).toBe('')
  })

  it('换一行点只把「待确认」挪过去：一次错位的点击删不掉没点过的会话', async () => {
    await mountPanel([row('a', 'A 条'), row('b', 'B 条'), row('c', 'C 条')])
    await mounted.state.deleteSession('a')
    await settle()
    expect(mounted.state.sessionDeleteLabel('a')).toBe('确认删除？')
    await mounted.state.deleteSession('b')
    await settle()
    expect(http.delete).not.toHaveBeenCalled()
    expect(mounted.state.sessionDeleteLabel('a'), '待确认挪走了，A 那条就不该被顺手删掉').toBe('✕')
    expect(mounted.state.sessionDeleteLabel('b')).toBe('确认删除？')
    await mounted.state.deleteSession('b')
    await settle()
    expect(deleteCalls()).toEqual(['/sessions/b'])
    expect(ids()).toEqual(['a', 'c'])
  })

  it('本机删掉了而服务端没删掉：两句话分开说，并给出那件还能做的事', async () => {
    await mountPanel([row('keep-me', '留着这条'), row('drop-me', '删掉这条')])
    http.delete.mockRejectedValue(Object.assign(new Error('Request failed with status code 403'), {
      isAxiosError: true, config: { url: '/sessions/drop-me' },
      response: { status: 403, data: { detail: 'permission_denied' } },
    }))
    await mounted.state.deleteSession('drop-me')
    await settle()
    await mounted.state.deleteSession('drop-me')
    await settle()
    expect(ids(), '本机那一份该拿掉').not.toContain('drop-me')
    const note = mounted.state.streamNote
    expect(note).toContain('会话未能从服务端删除')
    expect(note).toContain('当前账号没有这项权限，请联系管理员开通。')
    expect(note).toContain('从服务器取回')
    expect(note).not.toContain('请稍后再试')
  })

  it('待确认那一行改口的是钮上的字：面板把这句话绑给了原语，不是只活在函数里', async () => {
    await mountPanel([row('keep-me', '留着这条'), row('drop-me', '删掉这条')])
    // 面板模板上那一格绑的就是这枚函数（两处：title 与钮上的字），本件不另起第三套画法
    expect(panel).toMatch(/:title="sessionDeleteLabel\(s\.id\)"/)
    expect(panel).toMatch(/>\{\{ sessionDeleteLabel\(s\.id\) \}\}<\/UiButton>/)
    const sidebar = await renderToString(h({ render: () => h(ChatPanel) }))
    expect(sidebar.match(/data-testid="session-del"/g), '每一行一枚，不多不少').toHaveLength(2)
    // 真发一枚原语：SSR 出来的字就是发给浏览器的那一句
    const idle = await renderToString(h(UiButton, { class: 'session-del', label: mounted.state.sessionDeleteLabel('drop-me') }))
    expect(idle).toContain('✕')
    await mounted.state.deleteSession('drop-me')
    await settle()
    const armed = await renderToString(h(UiButton, { class: 'session-del', label: mounted.state.sessionDeleteLabel('drop-me') }))
    expect(armed).toContain('确认删除？')
    expect(armed).not.toContain('✕')
    const untouched = await renderToString(h(UiButton, { class: 'session-del', label: mounted.state.sessionDeleteLabel('keep-me') }))
    expect(untouched, '没点过的那一行不许跟着改口').toContain('✕')
  })
})

describe('乙 · G20 这一屏的按钮一律接原语，控件不再各写各的一套', () => {
  it('对话页两件件里裸 <button> 归零，且都从 ./ui 引进原语', () => {
    expect(panel).not.toMatch(/<button\b/)
    expect(queueFace).not.toMatch(/<button\b/)
    expect(panel).toMatch(/import \{[^}]*UiButton[^}]*\} from '\.\/ui'/)
    expect(queueFace).toMatch(/import UiButton from '\.\/ui\/UiButton\.vue'/)
  })

  it('每一枚动作都还在（一枚都不许在接线时弄丢），且都带着自己的 testid', () => {
    const required = [
      'sidebar-toggle', 'new-session', 'session-pull', 'session-del', 'deep-link-retry',
      'hitl-approve-chat', 'hitl-reject', 'chat-data-table-reload', 'chat-cancel-confirm-yes',
      'chat-cancel-confirm-no', 'chat-cancel', 'chat-send',
      // R458（判据②）：员工伸手才发的「再看一次」那一枚，连同枚数一起进账。
      'runtime-recheck-button',
    ]
    for (const testId of required) {
      expect(panel, `接线时把 ${testId} 这枚控件弄丢了`).toMatch(
        new RegExp(`<UiButton[\\s\\S]{0,320}?data-testid="${testId}"`),
      )
    }
    // R458：12 → 13，加的就是上面那枚 runtime-recheck-button。这一格钉的是【恰好】而不是上限：
    // 丢一枚、多一枚、新控件不带 testid，都照样红。
    expect(panel.match(/<UiButton\b/g)).toHaveLength(13)
  })

  it('HITL 那两枚的既有形状没被洗掉：块 C 读的就是这一行源码字面量', () => {
    expect(panel).toMatch(/class="hitl-btn approve"/)
    expect(panel).toMatch(/@action="openApprovalTurn"/)
    expect(queueFace).toMatch(/class="queue-retry"/)
  })
})

describe('丙 · G17 页内屏名与路由名同源（router 一行未动）', () => {
  it('路由那一格就叫这一句：页内文案向它对齐', () => {
    const chat = routes.find(route => String(route.name) === 'chat')
    expect(chat.meta.title).toBe(SCREEN_NAME)
  })

  it('屏上画出来的那一句与 meta.title 逐字相等', async () => {
    const html = await renderToString(h({ render: () => h(ChatPanel) }))
    const match = /data-testid="chat-screen-name"[^>]*>([^<]*)</.exec(html)
    expect(match, '这一屏把页级屏名弄丢了').toBeTruthy()
    expect(match[1].trim()).toBe(routes.find(route => String(route.name) === 'chat').meta.title)
  })

  it('旧叫法在这一件里一个字都不留（转出项：导航与面包屑由块 F 复核）', () => {
    expect(panel).not.toContain('智能问答')
    expect(panel).toMatch(/data-testid="chat-screen-name"/)
  })
})