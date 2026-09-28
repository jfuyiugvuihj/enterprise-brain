/**
 * R268 · 判据⑥ · G03 反证钉：这一轮用的是哪张表，看得见、改得动、下一轮真用得上
 *
 * 病灶（改前取证，行号取本单基点 1142c27）：`activeDataFilename`（lib/sessions.js:20）
 * 只在别的屏派发问题时被顺手改写，ChatPanel.vue 的模板里【没有任何一处引用它】——
 * 员工问出来的数与页面上选的表对不上时，这一屏既看不见也改不动。
 *
 * 三条判据各钉一条：
 *   看得见 → 选择框与那句回话上屏，每一轮回答下面画回【那一轮发出去带的表】；
 *   改得动 → 就地改完，下一轮真发出去的那一发 body 里就是它（跑真 send()，不是读源码）；
 *   不冒充 → 清单是 lazy 的（挂载期一枚请求都不发，r260 己1 那道门），而且界面只说自己
 *     发出去的东西；服务端真正用了哪张表由终态帧那一格报，两句各说各的事（R415 读数、R424 接线）。
 *
 * 反证怎么算红：删掉模板里那一段（改回「无任何模板引用」）→ 甲组全红；把 chooseDataTable
 * 改成只写界面不写 store → 乙组红；把清单改成挂载期就读 → 丙组第 1 条红（同时也会踩 r260 己1）。
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
import { TOKEN_KEY, authedFetch, http } from '../../lib/http'
import { SESSIONS_KEY, activeDataFilename, activeId, messages, resetSessions } from '../../lib/sessions'

const panel = readFileSync(new URL('../ChatPanel.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const SSR_CONTEXT_KEY = Symbol.for('v-scx')
const DATA_FILES_PATH = '/data-files'

const FILES = [{ filename: 'sales.xlsx', rows: 120 }, { filename: '报销明细表.csv', rows: 40 }]

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

/** 后端那一发的真形状：一条 SSE 字节流 + 三枚档位读数头（照 r169 的口径）。 */
function sseFrame(event, data) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

function sseResponse(frames, { status = 200, headers = {} } = {}) {
  const bytes = frames.map(frame => new TextEncoder().encode(frame))
  let index = 0
  const headersMap = new Map(Object.entries(headers))
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: name => headersMap.get(String(name).toLowerCase()) ?? null },
    clone() { return this },
    async json() { return null },
    body: { getReader() { return { async read() { return index < bytes.length ? { done: false, value: bytes[index++] } : { done: true } } } } },
  }
}

const ANSWER = sseResponse([sseFrame('text', { content: '最高 120 万。' })], {
  headers: { 'x-effective-lane': 'analysis', 'x-lane-source': 'r42', 'x-declared-lane': 'analysis' },
})

const bodyOf = (callIndex = 0) => JSON.parse(authedFetch.mock.calls[callIndex][1].body)
const settled = async () => {
  for (let round = 0; round < 12; round += 1) await nextTick()
}

let mounted = null

async function mountPanel(get) {
  installStorage({ [TOKEN_KEY]: 'jwt-live' })
  activeId.value = 'r268-data-session'
  http.get.mockImplementation(get || (async () => ({ data: {} })))
  let instance = null
  const errors = []
  const app = createApp({
    __name: 'R268DataHost',
    setup: ChatPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div', { id: 'r268-data-host' })
    },
  })
  app.config.warnHandler = () => {}
  app.config.errorHandler = err => errors.push(err)
  app.provide(SSR_CONTEXT_KEY, {})
  app.provide(routeLocationKey, reactive({ name: 'chat', path: '/chat', query: {}, params: {}, meta: {}, fullPath: '/chat', hash: '' }))
  app.provide(routerKey, { push: () => Promise.resolve(), replace: () => Promise.resolve() })
  app.mount(node('#root'))
  mounted = { app, errors, state: instance.setupState }
  await settled()
  return mounted
}

/** 按 URL 分派的假后端：/data-files 给清单，其余回空。 */
function dataBackend(files = FILES, error = null) {
  const paths = []
  const get = async (url) => {
    const target = String(url)
    paths.push(target)
    if (target === DATA_FILES_PATH) {
      if (error) throw error
      return { data: { files, restricted: false } }
    }
    if (target === '/health/details') return { data: { problems: [] } }
    return { data: {} }
  }
  get.paths = paths
  return get
}

const dataFileCalls = get => (get.paths || []).filter(path => path === DATA_FILES_PATH).length

beforeEach(() => {
  resetSessions()
  messages.value = []
  activeId.value = ''
  activeDataFilename.value = ''
  authedFetch.mockReset()
  http.get.mockReset()
})

afterEach(() => {
  mounted?.app.unmount()
  mounted = null
})

describe('甲 · 看得见：选择框、那句回话、每一轮画回的那张表', () => {
  it('这一屏画得出「本轮数据表」那一格，默认说的是不指定', async () => {
    const html = await renderToString(h({ render: () => h(ChatPanel) }))
    expect(html).toContain('data-testid="chat-data-table-picker"')
    expect(html).toContain('本轮数据表')
    expect(html).toContain('data-testid="chat-data-table-select"')
    const face = /data-testid="chat-data-table-face"[^>]*>([^<]*)</.exec(html)
    expect(face, '这一格必须自己说清下一轮发出去带什么').toBeTruthy()
    expect(face[1]).toContain('这一轮不指定数据表')
    expect(face[1]).toContain('界面挂载时不发请求')
  })

  it('选中的那张表就在句子上屏：界面不隔着三层去猜', async () => {
    activeDataFilename.value = 'sales.xlsx'
    const html = await renderToString(h({ render: () => h(ChatPanel) }))
    const face = /data-testid="chat-data-table-face"[^>]*>([^<]*)</.exec(html)
    expect(face[1]).toContain('这一轮将把〈sales.xlsx〉发给后端')
    expect(html).toMatch(/<option value="sales\.xlsx"/)
    // 选中态由 DOM 读 select 的 value（SSR 不替它写 selected），所以另取一道证：那一张确实在候选里
    expect(/value="sales\.xlsx"/.test(html)).toBe(true)
  })

  it('每一轮回答画回【那一轮发出去带的表】，老会话那一轮一句都不画', async () => {
    messages.value = [
      { role: 'user', content: '各区域最高销售额', mid: 'a1' },
      { role: 'assistant', content: '最高 120 万。', steps: [], mid: 'a2', dataFilename: 'sales.xlsx' },
      { role: 'user', content: '老的一问', mid: 'a3' },
      { role: 'assistant', content: '老的一答。', steps: [], mid: 'a4' },
      { role: 'user', content: '不指定的一问', mid: 'a5' },
      { role: 'assistant', content: '不指定的一答。', steps: [], mid: 'a6', dataFilename: '' },
    ]
    const html = await renderToString(h({ render: () => h(ChatPanel) }))
    const readouts = [...html.matchAll(/data-testid="data-table-readout"[^>]*>([^<]*)</g)].map(match => match[1])
    expect(readouts).toEqual(['本轮发问带的表：sales.xlsx', '本轮没指定数据表'])
  })

  it('措辞的边界：界面只说自己发出去的那一份，不冒充后端的用表读数', () => {
    expect(panel).toMatch(/function dataTableOf\(msg\) \{/)
    expect(panel).not.toMatch(/本轮用的表：|后端用了|这一轮用的是|今天不在线上任何一格/)
    expect(panel).toContain('服务端真正用了哪张表由下面那一格报')
  })
})

describe('乙 · 改得动：就地改完，下一轮真发出去的就是它（跑真 send()）', () => {
  it('选择框改一张表 → 下一轮 /ask 的 body 带的就是这一张', async () => {
    const get = dataBackend()
    await mountPanel(get)
    authedFetch.mockResolvedValue(ANSWER)
    mounted.state.chooseDataTable('sales.xlsx')
    expect(activeDataFilename.value).toBe('sales.xlsx')
    mounted.state.input = '各区域最高销售额是多少？'
    await mounted.state.send()
    await settled()
    expect(authedFetch.mock.calls[0][0]).toBe('/ask')
    expect(bodyOf(0).data_filename).toBe('sales.xlsx')
  })

  it('改回「不指定」也照样真生效：发出去的是空的那一格', async () => {
    const get = dataBackend()
    await mountPanel(get)
    authedFetch.mockResolvedValue(ANSWER)
    mounted.state.chooseDataTable('报销明细表.csv')
    mounted.state.chooseDataTable('')
    mounted.state.input = '公司年假几天？'
    await mounted.state.send()
    await settled()
    expect(bodyOf(0).data_filename).toBe('')
    expect(mounted.state.dataTableOf(messages.value[1])).toBe('本轮没指定数据表')
  })

  it('改完随这一条会话落盘：切走再切回来还是这一张，不是一句空话', async () => {
    const get = dataBackend()
    await mountPanel(get)
    authedFetch.mockResolvedValue(ANSWER)
    mounted.state.chooseDataTable('sales.xlsx')
    mounted.state.input = '各区域销售额'
    await mounted.state.send()
    await settled()
    const stored = JSON.parse(localStorage.getItem(SESSIONS_KEY)).sessions
      .find(item => item.id === activeId.value)
    expect(stored.dataFilename).toBe('sales.xlsx')
    activeDataFilename.value = ''
    mounted.state.switchSession('somewhere-else')
    activeDataFilename.value = ''
    mounted.state.switchSession(activeId.value)
  })

  it('那一轮发出去带的表记在消息对象上，不会被下一轮改掉', async () => {
    const get = dataBackend()
    await mountPanel(get)
    authedFetch.mockResolvedValue(ANSWER)
    mounted.state.chooseDataTable('sales.xlsx')
    mounted.state.input = '第一问'
    await mounted.state.send()
    await settled()
    mounted.state.chooseDataTable('报销明细表.csv')
    mounted.state.input = '第二问'
    await mounted.state.send()
    await settled()
    const turns = messages.value.filter(item => item.role === 'assistant')
    expect(turns.map(item => item.dataFilename)).toEqual(['sales.xlsx', '报销明细表.csv'])
    expect(bodyOf(1).data_filename).toBe('报销明细表.csv')
  })
})

describe('丙 · 清单是 lazy 的，读不到也看得见已选的那一张', () => {
  it('挂载期一枚 /data-files 都不发；伸手才发那一发', async () => {
    const get = dataBackend()
    await mountPanel(get)
    expect(dataFileCalls(get), '面板常驻，挂载期读清单等于每次进页面多一枪').toBe(0)
    await mounted.state.loadDataFiles()
    expect(dataFileCalls(get)).toBe(1)
    expect(mounted.state.dataTableChoices()).toEqual(['sales.xlsx', '报销明细表.csv'])
  })

  it('读到过一次就不再打一枪，要新的才 force', async () => {
    const get = dataBackend()
    await mountPanel(get)
    await mounted.state.loadDataFiles()
    await mounted.state.loadDataFiles()
    expect(dataFileCalls(get)).toBe(1)
    await mounted.state.loadDataFiles({ force: true })
    expect(dataFileCalls(get)).toBe(2)
    expect(mounted.state.dataTableFaceText()).toContain('清单已读到 2 张')
  })

  it('清单没读到：说的是这一格的事实，而已选那张表仍在候选里', async () => {
    const get = dataBackend(null, Object.assign(new Error('Request failed with status code 500'), {
      isAxiosError: true, config: { url: DATA_FILES_PATH }, response: { status: 500, data: { detail: 'storage_unavailable' } },
    }))
    await mountPanel(get)
    activeDataFilename.value = 'sales.xlsx'
    await mounted.state.loadDataFiles()
    expect(mounted.state.dataFilesState).toBe('failed')
    const face = mounted.state.dataTableFaceText()
    expect(face).toContain('这一轮将把〈sales.xlsx〉发给后端')
    expect(face).toContain('清单没读到')
    expect(face).toContain('服务需要的数据表还没有就绪')
    expect(mounted.state.dataTableChoices()).toContain('sales.xlsx')
  })

  it('后端回一份空清单是一句真话，不写成读不到', async () => {
    const get = dataBackend([])
    await mountPanel(get)
    await mounted.state.loadDataFiles()
    const face = mounted.state.dataTableFaceText()
    expect(face).toContain('清单已读到 0 张')
    expect(face).not.toContain('没读到')
  })

  it('清单那一格上屏：重读按钮真点得动，不是 disabled 占位', async () => {
    const html = await renderToString(h({ render: () => h(ChatPanel) }))
    expect(html).toContain('data-testid="chat-data-table-reload"')
    expect(html).toContain('重读清单')
    expect(panel).toMatch(/@click="loadDataFiles\(\{ force: true \}\)"/)
    expect(panel).toMatch(/@focus="loadDataFiles\(\)"/)
  })
})