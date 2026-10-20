/**
 * R519 · 队列道回来的那一格（`data_filename`），屏侧到底读不读得到
 *
 * 病灶（本单基点 97724c5 现取，不是推断）：服务端这一格在队列道上早就出到线上了——
 *   deploy/queue_worker.py:711 / :757 / deploy/queue_worker.py:921 三处把 `dataset_files` 递给 `chat.build_queue_terminal`
 *   → app/api/v1/chat.py:2296 `attach_terminal_data_filename` 落进终态载荷
 *   → app/api/v1/chat.py:5029-5031 `queue_terminal_readout` 只在载荷里那一格非空时把它写进回执
 *   → GET /queue/status/{request_id} 的返回体顶层就摆着 `data_filename`。
 * 而屏侧那一头只接了两条腿：`adoptServerDataRead`（ChatPanel.vue）读的是
 * `result.state.terminalDataFilename`，而那枚键由 lib/sessions.js 的 createStreamReducer 写
 * （canonical `request.completed` 与 legacy `done` 两支）。排队那一轮在 `queued` 回执之后
 * 就离开了那条 SSE 流，此后正文与读数全从轮询面回来（watchQueueTurn 只抄 status / position /
 * failure / result / approval 五枚），所以这一格走到屏上就断了：队列道那一轮永远不画那一句。
 * 本单接上它：新增一枚屏侧读者 adoptQueueDataRead，读同一格、写同一落点，serverDataOf 不必认腿。
 *
 * 三态照旧，队列这扇面只到场两态（这是后端口径，不是本单挑的）：
 *   报名字  回执里有非空字符串 → 屏上报那一个名字（甲1）
 *   不画    整格缺席（R504 之前的旧行、那一轮零枚或多枚）→ 一个字都不写（甲2）
 *   「说不准」在队列面上没有对应物：投影件 `and data_filename` 已经把空串挡在门外，
 *           所以本件收到空串同样不写（甲3）—— 写出去就是把「后端没说话」说成「后端说了说不清」
 *   先到者胜（甲4），非空优先于「说不准」（甲5）—— 与 r512 乙组同一套优先级，两枚同源不许互相改口
 *
 * 🔴 反证怎么算红：
 *   刀一 摘掉 watchQueueTurn 里那一行调用 ⇒ 甲1 乙1 乙2 当场红（队列道退回「屏上读不到」）；
 *   刀二 把守卫放宽成「非 undefined 就抄」⇒ 甲2 甲3 红（缺席被洗成一句话）；
 *   刀三 拿 msg.dataFilename（发依据）填这一格 ⇒ 甲6 红（两名故意不同名，任何回落都当场露）；
 *   刀四 顺手把这一格塞进排队脸的输入 `read` ⇒ 丁1 红（键名册多一枚，queueFace 的输入被扩宽）；
 *   刀五 把三态里任何一张脸改了措辞 ⇒ 丁2 红（serverDataOf 本单一字未动）；
 *   刀六 在生产码里再加一枚读者却不登记 ⇒ 丙1 名册红（谁读这一格，这张表必须跟着改口）。
 *
 * 手法沿用 r198 / r268 / r415：本仓没有 jsdom，也不 npm i。面板走 createRenderer + 内存虚拟
 * 节点跑【真客户端生命周期】，所以 onMounted → restoreQueuedTurns → watchQueueTurn → tick
 * 全是产品自己走的那条路，测试只换网络层与时钟；落盘那一格读的是真 localStorage 里的 JSON。
 */
import { readdirSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
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
import { activeId, messages, resetSessions } from '../../lib/sessions'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const panel = read('../ChatPanel.vue')
const lib = read('../../lib/sessions.js')
const chatPy = read('../../../../app/api/v1/chat.py')
const SRC = fileURLToPath(new URL('../../', import.meta.url))
const QUEUE_MS = 3000
const REQUEST_ID = 'req-r519'
const SESSION = 'r519-session'
const SSR_CONTEXT_KEY = Symbol.for('v-scx')
/** 两名故意不同名：任何「拿发依据冒充用表读数」的实现都会在这一格当场红。 */
const SENT = '报销明细表.csv'
const SERVER = 'sales.xlsx'
/** 屏上那一句的三张脸（措辞出自 serverDataOf，本单一字未动，丁2 钉的就是它）。 */
const NAMED = `这一轮算数用的表：${SERVER}`
const UNSURE = '这一轮说不准是哪张表'
const READ_KEY = 'serverDataFilename'
const BARE_CODE = /[一-鿿][^<>]*\b[a-z][a-z0-9]*(_[a-z0-9]+)+/

/* --------------------------------------------------------------- 回执形状 */

/** 队列这扇读面真交回来的形状：终态读数在顶层，`data_filename` 只在非空时才在（chat.py:5029-5031）。 */
const readoutReply = (cell = 'given') => {
  const body = { status: 'done', request_id: REQUEST_ID, result: '各区域最高 120 万。', terminal_state: 'answered' }
  if (cell === 'given') body.data_filename = SERVER
  else if (cell === 'empty') body.data_filename = ''
  else if (cell === 'other') body.data_filename = 'inventory.xlsx'
  return { data: body }
}

const queuedTurn = (over = {}) => ({
  role: 'assistant', content: '', steps: [], mid: 'r519-a',
  queue: { requestId: REQUEST_ID, status: 'queued' },
  ...over,
})

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
    if (target === '/queue/stats') return { data: { queue_length: 0, processing: 0 } }
    if (target === '/health/details') return { data: { problems: [] } }
    return { data: {} }
  }
}

/* ------------------------------------------------------------- 挂具（无 jsdom） */

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

function installStorage() {
  const store = new Map([[TOKEN_KEY, 'jwt-live']])
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

/** 挂上一轮「已经排上队、还没正文」的问答：面板因此自己盯上状态，回执由 pollScript 逐发放。 */
async function mountPanel(turns, replies) {
  installStorage()
  activeId.value = SESSION
  messages.value = turns
  http.get.mockImplementation(pollScript(...replies))
  let instance = null
  const errors = []
  const app = createApp({
    __name: 'R519Host',
    setup: ChatPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div', { id: 'r519-host' })
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

/** 屏上那一句此刻说什么：走的就是模板里 data-testid="server-data-readout" 绑的那枚函数。 */
const onScreen = (turn, index = 0) => mounted.state.serverDataOf(turn, index)

/** 另一枚尺：整座面板重新渲染出来的 HTML 里，那一句的文本（模板那一行不改动，甲乙共用）。 */
const renderNames = async () => {
  const html = await renderToString(h({ render: () => h(ChatPanel) }))
  return [...html.matchAll(/data-testid="server-data-readout"[^>]*>([^<]*)</g)].map(m => m[1])
}

beforeEach(() => {
  vi.useFakeTimers()
  resetSessions()
  messages.value = []
  activeId.value = ''
  http.get.mockReset()
  authedFetch.mockReset()
})

afterEach(() => {
  mounted?.app.unmount()
  mounted = null
  vi.useRealTimers()
})

/* ---------------------------------------------------------------- 甲 · 三态 */

describe('甲 · 队列回执那一格上屏：三态各有名字（走真轮询，不手填消息对象）', () => {
  it('甲1 回执带非空文件名 → 屏上报的就是那一个名字（改前这一格是断的：屏侧读不到）', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [readoutReply('given')])
    expect(onScreen(turn)).toBe(NAMED)
    expect(turn[READ_KEY], '读数没抄进消息对象：刷新一次就丢').toBe(SERVER)
    expect(mounted.errors, '生命周期内不许抛错').toEqual([])
  })

  it('甲2 整格缺席 → 那一句一个字都不画，也不凭空造一枚键（缺席≠空串）', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [readoutReply('absent')])
    expect(onScreen(turn), '后端没说话，屏上不许替它编一句').toBe('')
    expect(READ_KEY in turn, '不许把缺席写成一枚键').toBe(false)
    expect(await renderNames()).toEqual([])
  })

  it('甲3 队列这扇面压根不发空串，收到也当没说：写出去就是把「没说话」说成「说不清」', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [readoutReply('empty')])
    expect(onScreen(turn), '队列道没有「说不准」这一态，不许并脸').toBe('')
    expect(onScreen(turn)).not.toContain(UNSURE)
    expect(READ_KEY in turn).toBe(false)
  })

  it('甲4 这一轮先有过一枚名字（同步道先报的）→ 队列后到的一枚不改口', async () => {
    const turn = queuedTurn({ [READ_KEY]: SERVER })
    await mountPanel([turn], [readoutReply('other')])
    expect(onScreen(turn), '两枚同源，后到的不许给先到的改口').toBe(NAMED)
    expect(turn[READ_KEY]).toBe(SERVER)
  })

  it('甲5 先到的是「说不准」（空串）→ 队列那枚名字覆盖它：非空优先，与 r512 乙5 同一条尺', async () => {
    const turn = queuedTurn({ [READ_KEY]: '' })
    await mountPanel([turn], [readoutReply('given')])
    expect(onScreen(turn)).toBe(NAMED)
    expect(turn[READ_KEY]).toBe(SERVER)
  })

  it('甲6 不拿发依据填这一格：屏上那一句报的是服务端那一份，不是界面点的那一张', async () => {
    const turn = queuedTurn({ dataFilename: SENT, content: '' })
    messages.value = [{ role: 'user', content: '各区域最高销售额', mid: 'r519-q' }, turn]
    await mountPanel(messages.value, [readoutReply('given')])
    const line = onScreen(turn, 1)
    expect(line).toBe(NAMED)
    expect(line).not.toContain(SENT)
    expect(mounted.state.dataTableOf(turn), '发依据那一句照旧说它自己的事').toBe(`本轮发问带的表：${SENT}`)
  })

  it('甲7 挂起等人拍板那一轮同样接得住：回执 status 不是 done 也照抄（后端两枚状态都发这一格）', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [{ data: { status: 'awaiting_approval', request_id: REQUEST_ID, result: null, data_filename: SERVER } }])
    expect(onScreen(turn)).toBe(NAMED)
  })
})

/* ------------------------------------------------------ 乙 · 落盘与刷新复原 */

describe('乙 · 抄进去的那一份随会话落盘，刷新之后还在（消息对象才是复原用的那一只袋子）', () => {
  it('乙1 真 localStorage 里那一轮带着这一格：不是只活在内存里的当场读数', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [readoutReply('given')])
    const raw = globalThis.localStorage.getItem(`eb_msg_${SESSION}`)
    expect(raw, 'syncActive → persist 没把这一轮写下去').toBeTruthy()
    const stored = JSON.parse(raw).find(item => item.mid === 'r519-a')
    expect(stored[READ_KEY], '落盘那一份没这一格：刷新就读不到了').toBe(SERVER)
  })

  it('乙2 换一枚全新面板实例（刷新）只靠消息对象复原，那一句照样上屏', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [readoutReply('given')])
    expect(await renderNames()).toEqual([NAMED])
  })

  it('乙3 对照：那一轮压根没读到 → 刷新之后仍然一句不画（本单不许把「历史里没有」画成「说不准」）', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [readoutReply('absent')])
    expect(await renderNames()).toEqual([])
  })
})

/* ------------------------------------------- 丙 · 逐跳坐标：谁读这一格，在册点名 */

describe('丙 · 这一路的接缝（坐标现读，不抄本纸）', () => {
  /** 生产码里真正「碰这一枚线上键」的行：剥注释，测试件不算读者。 */
  const productionReaderLines = () => {
    const hits = []
    const walk = (dir, rel) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = `${dir}/${entry.name}`
        const shown = rel ? `${rel}/${entry.name}` : entry.name
        if (entry.isDirectory()) {
          if (entry.name !== '__tests__') walk(full, shown)
          continue
        }
        if (!/\.(js|vue)$/.test(entry.name) || /\.test\.js$/.test(entry.name)) continue
        readFileSync(full, 'utf8').replace(/\r\n/g, '\n').split('\n').forEach((line, at) => {
          const trimmed = line.trim()
          if (!trimmed || /^(\/\/|\*|\/\*|<!--)/.test(trimmed)) return
          if (/data_filename/.test(trimmed)) hits.push(`${shown}:${at + 1}:${trimmed}`)
        })
      }
    }
    walk(SRC, '')
    return hits.sort()
  }

  it('丙1 读者名册逐枚相等：三枚读响应方向那一格，一枚写请求方向 —— 多一枚少一枚都红', () => {
    expect(productionReaderLines().map(line => line.split(':').slice(2).join(':')).sort()).toEqual([
      // 请求方向：发出去时带的那一张（不是本单的账，r169 / r268 钉着）
      'data_filename: dataFilename,',
      // 响应方向三枚：SSE 两支解码处 + 本单补的队列道那一只读者
      `const read = typeof readout?.data_filename === 'string' ? readout.data_filename : ''`,
      'if (typeof data.data_filename === \'string\') state.terminalDataFilename = data.data_filename',
      'if (typeof payload?.data_filename === \'string\' && payload.data_filename && !state.terminalDataFilename) state.terminalDataFilename = payload.data_filename',
    ].sort())
  })

  it('丙2 队列道那一枚读者只有一个调用点，而且就在 watchQueueTurn 里（不是别处顺手抄的）', () => {
    expect((panel.match(/function adoptQueueDataRead\(/g) || []).length, '定义处枚数').toBe(1)
    const watch = panel.slice(panel.indexOf('function watchQueueTurn'), panel.indexOf('function stopQueueWatch'))
    expect((watch.match(/adoptQueueDataRead\(key, status\.data\)/g) || []).length, '调用点必须在这扇轮询里，且只有一枚').toBe(1)
    expect((panel.match(/adoptServerDataRead\(turn, aiMsg, result\)/g) || []).length,
      'SSE 那两条腿（/ask 与 /approve）本单没并进来也没摘走').toBe(2)
  })

  it('丙3 接缝两侧键名逐字一致：面板读的就是投影件写出去的那一枚（漂一个字那一行永远不画）', () => {
    const publish = /readout\["data_filename"\] = data_filename/
    expect(chatPy, '后端投影件那一格换了写法：先取证再改口').toMatch(publish)
    expect(panel).toContain("readout?.data_filename")
    expect(panel).toContain('serverDataReads.value = storeBag(serverDataReads, key, read)')
  })

  it('丙4 投影件的门槛就是「非空」：本单的「空串也不写」跟着它，不是自己挑的', () => {
    const from = chatPy.indexOf('def queue_terminal_readout(')
    expect(from).toBeGreaterThan(-1)
    const body = chatPy.slice(from, chatPy.indexOf('\ndef ', from + 10))
    expect(body).toMatch(/if isinstance\(data_filename, str\) and data_filename:/)
    const attach = chatPy.slice(chatPy.indexOf('def attach_terminal_data_filename('))
    expect(attach.slice(0, attach.indexOf('\ndef '))).toContain('terminal_data_filename(list(dataset_files or []))')
  })

  it('丙5 队列工三处都把 dataset_files 递进终态构造点，收集只走在册那枚收集器', () => {
    const worker = read('../../../../deploy/queue_worker.py')
    expect((worker.match(/dataset_files=dataset_files,/g) || []).length, '三枚终态构造点少一枚，就是有一道回不来').toBe(3)
    expect((worker.match(/chat\._collect_dataset_filenames\(/g) || []).length).toBeGreaterThanOrEqual(1)
    expect((worker.match(/terminal_data_filename|attach_terminal_data_filename/g) || []).length,
      '队列工不许自己拼第二份文件名：取值只在 chat 那两枚在册件里').toBe(0)
  })

  it('丙6 SSE 那两支解码处仍在原位（本单没动 lib，也没为了变绿去动任何一枚钉）', () => {
    expect(lib).toContain("state.terminalDataFilename = data.data_filename")
    expect(lib).toContain('state.terminalDataFilename = payload.data_filename')
    expect((lib.match(/state\.terminalDataFilename = /g) || []).length, 'lib 里往这一枚键写值的解码处必须还是两枚：本单没在 lib 加第三枚').toBe(2)
  })
})

/* ---------------------------------------------------- 丁 · 本单没扩宽别的东西 */

describe('丁 · 反证钉：接这一格没顺手改宽任何别人的账', () => {
  it('丁1 排队脸的输入 `read` 键名册一字未扩（本单没把第六枚塞进 queueFace 的嘴里）', () => {
    const watch = panel.slice(panel.indexOf('function watchQueueTurn'), panel.indexOf('function stopQueueWatches'))
    const from = watch.indexOf('const read = {')
    expect(from, '轮询里那枚取数对象找不到了：本钉就成了空转').toBeGreaterThan(-1)
    const block = watch.slice(from, watch.indexOf('\n      }', from))
    const keys = [...block.matchAll(/^ {8}([a-z_]+):/gm)].map(m => m[1])
    expect(keys, '排队轮询抄下来的键名册变了：queueFace 的输入被谁扩了').toEqual(['status', 'position', 'failure', 'result', 'approval'])
  })

  it('丁2 serverDataOf 三张脸措辞原文在位，且没长出第四张', () => {
    const from = panel.indexOf('function serverDataOf(')
    const body = panel.slice(from, panel.indexOf('\n}', from))
    expect(body).toContain(`if (read === null) return ''`)
    expect(body).toContain(UNSURE)
    expect(body).toContain('这一轮算数用的表：')
    expect((body.match(/return/g) || []).length, '三态之外没许第四支').toBe(4)
  })

  it('丁3 屏上那一句人话不夹裸码名（V6 闸门同一条口径）', async () => {
    const turn = queuedTurn()
    await mountPanel([turn], [readoutReply('given')])
    expect(onScreen(turn)).not.toMatch(BARE_CODE)
  })

  it('丁4 没引入第二套时钟：轮询仍只有那一枚 setInterval，tick 里也不许长 setTimeout', () => {
    expect(panel.match(/setInterval\(tick, QUEUE_POLL_MS\)/g)).toHaveLength(1)
    const watch = panel.slice(panel.indexOf('function watchQueueTurn'), panel.indexOf('function stopQueueWatches'))
    expect(watch, '本单只加了一枚取数，没加定时器').not.toMatch(/setTimeout/)
  })

  it('丁5 那一句仍只挂在助手那一侧，员工自己那句话不配拥有它', async () => {
    const ask = { role: 'user', content: '各区域最高销售额', mid: 'r519-q' }
    const turn = queuedTurn()
    messages.value = [ask, turn]
    await mountPanel(messages.value, [readoutReply('given')])
    expect(onScreen(ask, 0), '员工那句话不画这一格').toBe('')
    expect(onScreen(turn, 1)).toBe(NAMED)
  })
})
