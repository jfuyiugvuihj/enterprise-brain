/**
 * R169 · V1 前端主链路验收矩阵 —— 登录那一行（含「账号失效」那一格）
 *
 * 为什么这一整块是本件新补：659 枚既存用例里**没有任何一枚**调用过 App.vue 的
 * doLogin / checkAuth / doLogout / onAuthEvent（点名可查：`git grep doLogin -- '*test.js'` 零命中）。
 * 登录在既存账上的证据只有三类，全都不是「这个动作能操作」：
 *   假数字不外泄 = components/__tests__/v7-fake-data.test.js · V7-5 那一组（3 枚，钉源码文本）
 *   屏名与导航   = router/__tests__/routes.test.js、src/__tests__/navigation.test.js（钉的是路由表派生）
 *   面板里的 401 = insight-alerts / panel-states（钉的是**别的屏**读到 401 之后画什么脸）
 * 归码那一层早就钉好了（lib/errcodes.test.js · 401「请先登录」与 403「账号不可用」两条各一枚），
 * 本文件因此不重复钉字典，只钉**界面拿到之后做了什么**：会话落没落、屏换没换、句子是哪一张脸。
 *
 * 三条腿（沿用仓库既有口径）：① 真逻辑 = 跑 App.vue 自己的 setup()，登录那一发换成进程内假实现，
 * localStorage 换内存替身，会话读写走 lib/http 真身；② 真产物 = 未登录首屏 SSR 出的 HTML；
 * ③ 源码形状 = 换屏这类一次渲染看不到的接线。🔴 一条都不置灰、不挂待办、不放宽任何既存断言。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, h, nextTick, reactive } from 'vue'
import { readFileSync } from 'node:fs'
import { renderToString } from '@vue/server-renderer'
import { routeLocationKey, routerKey } from 'vue-router'

// 只换登录那一发的出口：saveSession / clearSession / hasSession / errorDetail 全部保持真身，
// 「会话到底落没落盘」这一格才有意义。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { ...actual.http, post: vi.fn() } }
})

import { http, ROLE_KEY, TOKEN_KEY, USER_KEY } from '../../lib/http'
import App from '../../App.vue'

const REMEMBER_KEY = 'eb_remember_username'
const EXPIRES_KEY = 'eb_token_expires_at'
const source = readFileSync(new URL('../../App.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')

/** 内存替身：node 环境没有 window / localStorage（App 与 lib/sessions 只用到这几个方法）。 */
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

/** 路由用假对象直接 provide：登录这一行只读 route.name，而 replace 的落点要能对账。 */
function providesOf(route, pushed) {
  const fakeRouter = {
    replace: target => { pushed.push(target); return Promise.resolve() },
    push: target => { pushed.push(target); return Promise.resolve() },
  }
  return { route, fakeRouter }
}

/**
 * 跑真 App.vue 的 setup()（手法同 artifact-list.test.js：借宿主实例把上下文递进去）。
 * @param {Record<string, string>} seed 预置的 localStorage
 * @param {string} screenName 当前所在屏（route.name）
 */
async function mountApp(seed = {}, screenName = '') {
  const store = installDomStubs(seed)
  const pushed = []
  const route = reactive({ name: screenName, path: '/', query: {}, meta: {}, params: {}, fullPath: '/', hash: '' })
  const { fakeRouter } = providesOf(route, pushed)
  let bindings = null
  const Probe = defineComponent({
    name: 'R169LoginProbe',
    setup(props, ctx) {
      bindings = App.setup({}, ctx)
      return () => null
    },
  })
  const app = createSSRApp({ render: () => h(Probe) })
  app.provide(routeLocationKey, route)
  app.provide(routerKey, fakeRouter)
  await renderToString(app)
  expect(bindings, 'App.vue 应暴露可调用的 setup()').toBeTruthy()
  return { bindings, store, route, pushed }
}

/** 不带实例上下文的那一腿：只要 HTML，不要绑定。 */
async function renderLoginHtml() {
  installDomStubs()
  const route = reactive({ name: '', path: '/', query: {}, meta: {}, params: {}, fullPath: '/', hash: '' })
  const app = createSSRApp({ render: () => h(App) })
  app.provide(routeLocationKey, route)
  app.provide(routerKey, { replace() {}, push() {} })
  return renderToString(app)
}

/** 后端拒发令牌时 axios 抛的真形状：detail 是后端原话（app/main.py 的鉴权腿就是中文散文）。 */
function httpError(status, detail) {
  return { response: { status, data: { detail } }, message: 'Request failed with status code ' + status }
}

function rejectedWith(err) {
  return async () => { throw err }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('R169 L1 · 还没有会话时亮的是登录页（SSR 真产物）', () => {
  it('首屏画登录页：账号、口令、提交三件套齐了，工作台一件都不在', async () => {
    const html = await renderLoginHtml()
    expect(html).toContain('data-testid="login-page"')
    expect(html).toContain('data-testid="login-username"')
    expect(html).toContain('data-testid="login-password"')
    expect(html).toContain('data-testid="login-submit"')
    expect(html).not.toContain('data-testid="workbench"')
    expect(html).not.toContain('data-testid="sidebar"')
  })

  it('一次都没试过就不亮错误条：登录失败那张脸只有一条出现路径', async () => {
    const html = await renderLoginHtml()
    expect(html).not.toContain('data-testid="login-error"')
    // 只此一条路径，且 role=alert（读屏要打断），并且表单不会被换成第二套提示样式
    expect(source).toMatch(/v-if="loginError"[\s\S]*?data-testid="login-error" role="alert"/)
    expect(source).toMatch(/@submit\.prevent="doLogin"/)
  })
})

describe('R169 L2 · 登录这一发真的走通了（跑真 doLogin / checkAuth）', () => {
  it('后端给了令牌：会话落盘、换屏、错误条清空', async () => {
    const { bindings: b, store } = await mountApp()
    http.post.mockResolvedValue({ data: { token: 'jwt-1', username: 'baiye', role: 'admin', department: '财务部', expires_in: 3600 } })
    b.loginUser.value = '  baiye  '
    b.loginPass.value = 'pw'
    b.loginError.value = '上一轮的旧话'
    await b.doLogin()
    await nextTick()
    expect(http.post.mock.calls[0][0]).toBe('/login')
    expect(http.post.mock.calls[0][1]).toEqual({ username: 'baiye', password: 'pw' })
    expect(store.get(TOKEN_KEY)).toBe('jwt-1')
    expect(store.get(USER_KEY)).toBe('baiye')
    expect(store.get(ROLE_KEY)).toBe('admin')
    expect(Number(store.get(EXPIRES_KEY))).toBeGreaterThan(Date.now())
    expect(b.isLoggedIn.value).toBe(true)
    expect(b.username.value).toBe('baiye')
    expect(b.userRole.value).toBe('admin')
    expect(b.loginError.value).toBe('')
    b.goToLogin() // 停掉到期看门表，不把定时器留给下一个用例
  })

  it('后端 200 但响应里没有令牌：不进工作台、不落会话、说得出缺什么', async () => {
    const { bindings: b, store } = await mountApp()
    http.post.mockResolvedValue({ data: { username: 'baiye' } })
    b.loginUser.value = 'baiye'
    b.loginPass.value = 'pw'
    await b.doLogin()
    expect(store.has(TOKEN_KEY)).toBe(false)
    expect(b.isLoggedIn.value).toBe(false)
    expect(b.loginError.value).toContain('缺少令牌')
  })

  it('带着有效会话打开：不重新输密码，直接续上用得着的身份', async () => {
    const { bindings: b } = await mountApp({ [TOKEN_KEY]: 'jwt-old', [USER_KEY]: 'baiye', [ROLE_KEY]: 'staff' })
    b.checkAuth()
    expect(b.isLoggedIn.value).toBe(true)
    expect(b.username.value).toBe('baiye')
    expect(b.userRole.value).toBe('staff')
    expect(http.post).not.toHaveBeenCalled()
    b.goToLogin()
  })

  it('只有「记住的账号名」不算登录：回填账号名，但仍停在登录页', async () => {
    const { bindings: b } = await mountApp({ [REMEMBER_KEY]: 'baiye' })
    b.checkAuth()
    expect(b.isLoggedIn.value).toBe(false)
    expect(b.loginUser.value).toBe('baiye')
    expect(b.rememberMe.value).toBe(true)
  })

  it('勾了记住我：账号名落盘，口令一个字节都不留', async () => {
    const { bindings: b, store } = await mountApp()
    http.post.mockResolvedValue({ data: { token: 'jwt-2', username: 'baiye', role: 'staff' } })
    b.loginUser.value = 'baiye'
    b.loginPass.value = 'secret-pw'
    b.rememberMe.value = true
    await b.doLogin()
    expect(store.get(REMEMBER_KEY)).toBe('baiye')
    expect([...store.keys()].filter(key => /password|secret/i.test(key))).toEqual([])
    b.goToLogin()
  })

  it('没勾记住我：账号名不落盘（公用机器上不能把上一个人名留给下一个）', async () => {
    const { bindings: b, store } = await mountApp()
    http.post.mockResolvedValue({ data: { token: 'jwt-3', username: 'baiye' } })
    b.loginUser.value = 'baiye'
    b.loginPass.value = 'pw'
    b.rememberMe.value = false
    await b.doLogin()
    expect(store.has(REMEMBER_KEY)).toBe(false)
    b.goToLogin()
  })
})

describe('R169 L3 · 后端拒发令牌时的几张脸（跑真 doLogin，互不混用）', () => {
  it('口令错（401）：停在登录页，后端那句原话上屏，会话不落', async () => {
    const { bindings: b, store } = await mountApp()
    http.post.mockImplementation(rejectedWith(httpError(401, '用户名或密码错误')))
    b.loginUser.value = 'baiye'
    b.loginPass.value = 'wrong'
    await b.doLogin()
    expect(b.isLoggedIn.value).toBe(false)
    expect(store.has(TOKEN_KEY)).toBe(false)
    expect(b.loginError.value).toBe('用户名或密码错误')
  })

  it('账号失效（403「账号不可用」）：说的是这账号被停用了，不是没权限、也不是服务坏了', async () => {
    const { bindings: b, store } = await mountApp()
    http.post.mockImplementation(rejectedWith(httpError(403, '账号不可用')))
    b.loginUser.value = 'baiye'
    b.loginPass.value = 'pw'
    await b.doLogin()
    expect(b.loginError.value).toContain('停用')
    expect(b.loginError.value).not.toContain('权限')
    expect(b.isLoggedIn.value).toBe(false)
    expect(store.has(TOKEN_KEY)).toBe(false)
  })

  it('这一发压根没送达：说的是服务不可用，不冒充前两张脸', async () => {
    const { bindings: b } = await mountApp()
    http.post.mockImplementation(rejectedWith({ message: '' }))
    b.loginUser.value = 'baiye'
    b.loginPass.value = 'pw'
    await b.doLogin()
    expect(b.loginError.value).toBe('登录服务暂时不可用')
    expect(b.isLoggedIn.value).toBe(false)
  })

  it('四张脸两两不同句，且都不把裸码名印上屏（并成一句「登录失败」就是这一格要抓的缺陷）', async () => {
    const faces = []
    for (const rejection of [
      httpError(401, '用户名或密码错误'),
      httpError(403, '账号不可用'),
      httpError(403, 'permission_denied'),
      { message: '' },
    ]) {
      const { bindings: b } = await mountApp()
      http.post.mockImplementation(rejectedWith(rejection))
      b.loginUser.value = 'baiye'
      b.loginPass.value = 'pw'
      await b.doLogin()
      faces.push(b.loginError.value)
    }
    expect(faces.every(Boolean)).toBe(true)
    expect(new Set(faces).size).toBe(4)
    expect(faces.join('')).not.toMatch(/account_unavailable|permission_denied|authentication_required/)
  })

  it('每试一次先清掉上一轮的错误条：不许留着旧话冒充本轮结果', async () => {
    const { bindings: b } = await mountApp()
    b.loginError.value = '上一次留下的旧话'
    http.post.mockImplementation(rejectedWith(httpError(401, '用户名或密码错误')))
    b.loginUser.value = 'baiye'
    await b.doLogin()
    expect(b.loginError.value).not.toBe('上一次留下的旧话')
  })
})

describe('R169 L4 · 用得正一半路失效时怎么收尾（跑真 onAuthEvent / doLogout）', () => {
  it('收到 unauthorized：清会话、回登录页、把话说在错误条与提示条两处', async () => {
    const { bindings: b, store, pushed } = await mountApp({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'staff' }, 'chat')
    b.checkAuth()
    expect(b.isLoggedIn.value).toBe(true)
    b.onAuthEvent({ type: 'unauthorized', message: '登录状态已失效，请重新登录。' })
    await nextTick()
    expect(store.has(TOKEN_KEY)).toBe(false)
    expect(b.isLoggedIn.value).toBe(false)
    expect(b.loginError.value).toBe('登录状态已失效，请重新登录。')
    expect(b.toast.value).toMatchObject({ tone: 'error', message: '登录状态已失效，请重新登录。' })
    expect(b.username.value).toBe('')
    expect(pushed).toEqual([{ name: 'overview' }])
    b.goToLogin()
  })

  it('收到 expiring：只提醒，会话与身份一起留着（快到期不等于已过期）', async () => {
    const { bindings: b, store, pushed } = await mountApp({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'staff' }, 'chat')
    b.checkAuth()
    pushed.length = 0
    b.onAuthEvent({ type: 'expiring', message: '登录状态将在约 3 分钟后过期，请提前重新登录。' })
    expect(b.isLoggedIn.value).toBe(true)
    expect(store.get(TOKEN_KEY)).toBe('jwt-live')
    expect(b.toast.value).toMatchObject({ tone: 'warn' })
    expect(b.loginError.value).toBe('')
    expect(pushed).toEqual([])
    b.goToLogin()
  })

  it('只认两枚事件：没有事件什么都不做，认不得的那一枚按失效收尾（宁多踢一次，不拿不可信令牌继续发请求）', async () => {
    const quiet = await mountApp({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye' }, 'chat')
    quiet.bindings.checkAuth()
    quiet.bindings.onAuthEvent(undefined)
    quiet.bindings.onAuthEvent(null)
    expect(quiet.bindings.isLoggedIn.value, '空事件不算失效').toBe(true)
    expect(quiet.store.get(TOKEN_KEY)).toBe('jwt-live')
    quiet.bindings.goToLogin()

    const unknown = await mountApp({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye' }, 'chat')
    unknown.bindings.checkAuth()
    unknown.bindings.onAuthEvent({ type: 'something_else' })
    expect(unknown.store.has(TOKEN_KEY), '来路不明的鉴权事件之后，本地令牌不许还留着').toBe(false)
    expect(unknown.bindings.isLoggedIn.value).toBe(false)
    unknown.bindings.goToLogin()
  })

  it('手动退出：会话与本地缓存全清，只留「记住的账号名」，口令与身份一起清空', async () => {
    const { bindings: b, store, pushed } = await mountApp({
      [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'admin', [REMEMBER_KEY]: 'baiye', eb_sessions_v2: '[]',
    }, 'chat')
    b.checkAuth()
    b.loginPass.value = 'still-here'
    b.doLogout()
    expect(store.has(TOKEN_KEY)).toBe(false)
    expect(store.has(USER_KEY)).toBe(false)
    expect(store.has(ROLE_KEY)).toBe(false)
    expect(store.has('eb_sessions_v2')).toBe(false)
    expect(store.get(REMEMBER_KEY)).toBe('baiye')
    expect(b.loginPass.value).toBe('')
    expect(b.isLoggedIn.value).toBe(false)
    expect(b.userRole.value, '退出之后不许还留着管理员身份').toBe('staff')
    expect(pushed).toEqual([{ name: 'overview' }])
  })

  it('已经在默认落点上退出就不换屏：replace 只在真需要挪的时候发生', async () => {
    const { bindings: b, pushed } = await mountApp({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye' }, 'overview')
    b.checkAuth()
    pushed.length = 0
    b.doLogout()
    expect(b.isLoggedIn.value).toBe(false)
    expect(pushed).toEqual([])
  })
})
