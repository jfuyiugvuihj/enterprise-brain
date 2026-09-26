/**
 * R278 · 判据④ · 退出那一刀清的是什么，找回历史的线索又在哪里
 *
 * 背景是两件事叠在一起，得判一次（不是判两回）：
 *   · R268 刚并树（90c15bb）：左侧会话名单不再只有本机那一份，点一次「从服务器取回」就打
 *     一次 GET /sessions 再并进来（lib/sessions.js:924 readBackendSessionList / :940 mergeServerSessions，
 *     挂载期一枚请求都不发）；
 *   · App.vue 的 doLogout（改前 :183-197）今天整包清 eb_*，只留「记住我」的账号名，
 *     而清之前还先走 goToLogin() -> resetSessions()（lib/sessions.js:176）把内存 store 与
 *     本机名单一起洗掉。
 * 于是这一格要回答的是：**清完库之后，那个「点一次取回」的入口还在不在？**
 *
 * 取证结论（本件实取，行号取基点 951909b）：在，而且它从来就没依赖本机那份名单。
 *   读名单 = GET /sessions（后端已按归属过滤，chat.py 的 list_sessions 用 is_owned_by 那道闸），
 *   并名单 = 往【内存 store】里并（mergeServerSessions 读本机有的那一行只为「有正文就不覆盖」，
 *   本机一行都没有时它照样建得出整张表）。取回的线索是「你这个账号在服务端的归属」，
 *   那是令牌后面的事；本机 localStorage 只是缓存，不是身份。
 *
 * 本件选的语义（判据④明写这一格总控没有标准答案，要的是取证后那一句真话）：
 *   【维持整包清】。改成「只清凭据不清名单」会把上一个人的会话标题与正文留在同一台机器的
 *   浏览器里，下一个人一登录就看得见——私有化部署里这是数据外泄，不是便利。
 *   这格既有两枚邻居钉本件一行不放宽：r169-login-screen.test.js 钉「退出全清、只留记住的账号名」，
 *   r268-session-pull.test.js 丙组第三条钉「本地态一行都没有也建得出列表」。本件在壳层这一侧
 *   补甲（清得干净）与乙（清完还取得回来）两枚，凑成同一句话的两半。
 *
 * 取证的路上撞到的一格真缺陷（不粉饰，本件当场收掉）：那段 eb_* 整包扫原先只挂在 doLogout 上，
 *   而 401/过期那条收尾走的是同一个 goToLogin、却没有这一刀。今天两者【恰好】等价，全站写得出的
 *   eb_* 只有七枚（eb_token/eb_user/eb_role/eb_department/eb_token_expires_at 由 clearSession 清，
 *   eb_sessions_v2/eb_msg_* 由 resetSessions -> clearStoredSessions 清，eb_remember_username 有意留下），
 *   两把扫帚加起来盖得住全部——拿掉整包扫这个变异在改前【测不出红】（本件实跑过：三枚文件全绿），
 *   这正是那条兜底的意思：它防的是以后有人新加一枚 eb_* 而忘了列入清空名单。下一次真加了，
 *   改前那台被踢下线的浏览器就会把上一位的态留给下一位。本件把那一刀【上收到 goToLogin】：
 *   doLogout 的净效果一行未变（r169 的「全清只留记住的账号名」、r171 的两张失效脸、r268 丙组那条，
 *   三枚邻居钉现跑全绿），「换人使用」从此只有一处口径，甲4 钉的就是这一句。
 *   哨兵：甲1 里另 seed 一枚今天没人写的 eb_scope_picker，专钉这最后一道兜底——摘掉那一刀就红。
 *
 * 反证（本单实跑，全部只改本件写域里的 App.vue，跑完原样还原；数字取当场原文）：
 *   丁 摘掉那段 eb_* 整包扫（＝「只清凭据不清名单」那种写法）→ 本文件 2 failed
 *       （甲1 红：哨兵键 eb_scope_picker 留下来；甲4 红：两条收尾的残留不再一样）；
 *   戊 拿掉 goToLogin 里的 resetSessions() → 本文件 1 failed（甲2 红：内存那一列还留着上一位的标题）；
 *       甲4 在这一发下仍绿——因为整包扫兜住了 localStorage 那一半，没兜住的正是内存那一半，
 *       这一格分得开，说明两枚钉的不是同一件事。
 *   🔴 乙组不做变异：它的对面（mergeServerSessions 退回只从本机 localStorage 组装）要改
 *   lib/sessions.js，那是本单禁域，也是 R268 已经自己跑过反证并钉住的一格
 *   （components/__tests__/r268-session-pull.test.js 丙组第三条：本地态一行都没有也建得出列表）。
 *   本件因此只在壳层这一侧做【能零越界跑成】的那一半：清得干净（甲）+ 清完还取得回来（乙）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, reactive } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { routeLocationKey, routerKey } from 'vue-router'

// 只换网络那一发：saveSession / clearSession / hasSession 全部走真身，「清没清干净」才有意义。
vi.mock('../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { ...actual.http, get: vi.fn(), post: vi.fn() } }
})

import App from '../App.vue'
import { DEPARTMENT_KEY, EXPIRES_KEY, ROLE_KEY, TOKEN_KEY, USER_KEY, http } from '../lib/http'
import {
  SESSIONS_KEY,
  SESSION_READ,
  activeId,
  clearStoredSessions,
  mergeServerSessions,
  pullBackendMessages,
  readBackendSessionList,
  resetSessions,
  sessionBodyMissing,
  sessions,
} from '../lib/sessions'

const REMEMBER_KEY = 'eb_remember_username'
const MESSAGE_KEY = id => `eb_msg_${id}`

const SERVER_ROWS = [
  { id: 'srv-old', title: '上季度销售额', created_at: '2026-09-20T02:00:00+08:00', updated_at: '2026-09-20T02:00:00+08:00', msg_count: 4 },
  { id: 'srv-new', title: '差旅报销制度', created_at: '2026-09-24T09:00:00+08:00', updated_at: '2026-09-24T09:00:00+08:00', msg_count: 7 },
]

/** 内存替身：node 环境没有 window / localStorage（手法同 r169 / r171）。 */
function installDomStubs(seed = {}) {
  const store = new Map(Object.entries(seed))
  globalThis.window = globalThis.window || { addEventListener() {}, removeEventListener() {} }
  globalThis.document = globalThis.document || { addEventListener() {}, removeEventListener() {}, visibilityState: 'visible' }
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

/** 跑真 App.vue 的 setup() 并进工作台（同一台「浏览器」上用过一阵的样子）。 */
async function loginAndUse(seed) {
  const store = installDomStubs(seed)
  const route = reactive({
    name: 'chat', path: '/chat', query: {}, params: {},
    meta: { title: '屏名', screen: true }, fullPath: '/chat', hash: '', matched: [],
  })
  let bindings = null
  const Host = defineComponent({
    name: 'R278LogoutHost',
    ssrRender: App.ssrRender,
    setup(props, ctx) {
      const given = App.setup({}, ctx)
      given.checkAuth()
      bindings = given
      return given
    },
  })
  const app = createSSRApp(Host)
  app.provide(routeLocationKey, route)
  app.provide(routerKey, { push() {}, replace() {}, currentRoute: { value: route } })
  app.component('RouterView', { ssrRender: () => {} })
  await renderToString(app)
  return { bindings, store }
}

/** 一份按 URL 分派的假后端：/sessions 回名单，/sessions/{id} 回正文。 */
function backend() {
  const paths = []
  const get = vi.fn(async (url) => {
    const target = String(url)
    paths.push(target)
    if (target === '/sessions') return { data: { sessions: SERVER_ROWS } }
    if (target.startsWith('/sessions/')) return { data: { messages: [{ role: 'user', content: '后端正文', created_at: '' }] } }
    return { data: {} }
  })
  return { get, paths }
}

// eb_scope_picker 今天没有任何代码会写它：它是哨兵，钉的是上收到 goToLogin 的那道兜底本身。
const SENTINEL_KEY = 'eb_scope_picker'

const liveSeed = () => ({
  [TOKEN_KEY]: 'jwt-live',
  [SENTINEL_KEY]: '市场部',
  [USER_KEY]: 'baiye',
  [ROLE_KEY]: 'staff',
  [DEPARTMENT_KEY]: '市场部',
  [EXPIRES_KEY]: String(Date.now() + 3600_000),
  [REMEMBER_KEY]: 'baiye',
  [SESSIONS_KEY]: JSON.stringify({ activeId: 's-1', sessions: [{ id: 's-1', title: '本机那份', messages: [] }] }),
  [MESSAGE_KEY('s-1')]: JSON.stringify([{ role: 'user', content: '上一位问过的话' }]),
})

beforeEach(() => {
  resetSessions()
  clearStoredSessions()
  http.get.mockReset()
})

afterEach(() => {
  http.get.mockReset()
})

describe('R278 判据④ 甲 · 退出今天清的是什么（钉住「整包清」这一枚语义）', () => {
  it('凭据与本机名单一起清空，一台浏览器上只留下「记住我」的账号名', async () => {
    const { bindings, store } = await loginAndUse(liveSeed())
    expect(bindings.isLoggedIn.value).toBe(true)
    bindings.doLogout()
    const left = [...store.keys()].filter(key => key.startsWith('eb_'))
    expect(left, `退出之后本地还留着：${left.join(', ')}`).toEqual([REMEMBER_KEY])
    expect(store.get(REMEMBER_KEY)).toBe('baiye')
    expect(bindings.username.value).toBe('')
    expect(bindings.userRole.value).toBe('staff')
    expect(bindings.isLoggedIn.value).toBe(false)
  })

  it('内存里那一列也不留：换人使用不能看见上一位的会话标题', async () => {
    const { bindings } = await loginAndUse(liveSeed())
    sessions.value = [{ id: 's-1', title: '本机那份', messages: [{ role: 'user', content: '上一位问过的话' }] }]
    activeId.value = 's-1'
    bindings.doLogout()
    expect(sessions.value).toEqual([])
    expect(activeId.value).toBe('')
    expect(localStorage.getItem(SESSIONS_KEY)).toBe(null)
  })

  it('会话正文按会话拆的那些键也一并清掉（只清名单会漏一整包别人问过的话）', async () => {
    const { bindings, store } = await loginAndUse(liveSeed())
    expect(store.has(MESSAGE_KEY('s-1'))).toBe(true)
    bindings.doLogout()
    expect(store.has(MESSAGE_KEY('s-1'))).toBe(false)
  })

  it('手动退出与 401 失效两条收尾的残留一模一样：不许有「只洗一条路」的第二种口径', async () => {
    const manual = await loginAndUse(liveSeed())
    manual.bindings.doLogout()
    const kicked = await loginAndUse(liveSeed())
    kicked.bindings.onAuthEvent({ type: 'unauthorized', message: '登录状态已失效，请重新登录。' })
    const survivors = store => [...store.keys()].filter(key => key.startsWith('eb_')).sort()
    expect(survivors(manual.store), '手动退出之后本机还留着东西').toEqual([REMEMBER_KEY])
    expect(survivors(kicked.store), '被踢下线之后本机还留着东西').toEqual([REMEMBER_KEY])
    expect(sessions.value).toEqual([])
  })
})

describe('R278 判据④ 乙 · 清完库，「点一次从服务端取回」这条路仍然真通', () => {
  it('本机一行都没有：名单照样读得回、并得进（不拿本机那份当前提）', async () => {
    const { bindings } = await loginAndUse(liveSeed())
    bindings.doLogout()
    const api = backend()
    http.get.mockImplementation(api.get)
    expect(localStorage.getItem(SESSIONS_KEY)).toBe(null)
    const read = await readBackendSessionList()
    expect(read.outcome).toBe(SESSION_READ.found)
    expect(read.rows.map(row => row.id)).toEqual(['srv-old', 'srv-new'])
    expect(mergeServerSessions(read.rows)).toMatchObject({ serverRows: 2, added: 2, refreshed: 0, total: 2 })
    expect(sessions.value.map(item => item.title)).toEqual(['差旅报销制度', '上季度销售额'])
    expect(api.paths).toEqual(['/sessions'])
  })

  it('并回来的那一行正文还欠着，点开才取——这一步同样不依赖本机那份', async () => {
    const { bindings } = await loginAndUse(liveSeed())
    bindings.doLogout()
    http.get.mockImplementation(backend().get)
    const read = await readBackendSessionList()
    mergeServerSessions(read.rows)
    expect(sessionBodyMissing('srv-new')).toBe(true)
    const pulled = await pullBackendMessages('srv-new')
    expect(pulled.outcome).toBe(SESSION_READ.found)
    expect(sessionBodyMissing('srv-new')).toBe(false)
    const row = sessions.value.find(item => item.id === 'srv-new')
    expect(row.messages.map(item => item.content)).toEqual(['后端正文'])
  })

  it('退出与取回之间没有第三件事：入口要的是登录态，不是本机旧名单', async () => {
    const { bindings } = await loginAndUse(liveSeed())
    bindings.doLogout()
    const api = backend()
    http.get.mockImplementation(api.get)
    const read = await readBackendSessionList()
    expect(read.outcome).toBe(SESSION_READ.found)
    // 只发了那一枪名单：没有为了「找回历史」多起的第二发，也没有拿本机 id 去问后端
    expect(api.paths).toEqual(['/sessions'])
  })
})
