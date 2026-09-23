/**
 * R171 · 「失效收尾」这一支在任何输入下都必须留下一句人话
 *
 * 本件要修的那一格（App.vue 的 onAuthEvent 收尾支）改前是这样：
 *   clearSession(); goToLogin(); loginError.value = event.message; showToast(event.message, ...)
 * event.message 缺失 / 空串 / 纯空白 / 非字符串时，人已经被从工作台踢回登录页，而错误条
 * v-if="loginError" 不亮、提示条内容为空——员工看到的是「莫名其妙被登出」。
 *
 * 🔴 顺手记一笔证伪（跟进单 §85 三 的原判据是错的）：原判据说「loginError.value = event.message
 * 为 undefined ⇒ 错误条不亮」，并把这件事算在 shipped 的 unauthorized 路径上。实测不是：
 * lib/http.js:95 的 unauthorized 与 :127 的 expiring 从 a07294fb（2026-09-15）起就一直带文案，
 * 全盘 src/** 也只有这两枚 emit。所以「不亮」只在 message 缺席/为空/非字符串时才成立，
 * 而那种输入今天没有任何发出方会发——本件按最窄口径钉成 App.vue 这一支自己的防御，
 * 不去 lib/http.js 补文案（那是发出方的事，也是禁改区）。
 *
 * 三条腿（沿用仓库既有口径，手法同 r169-login-screen.test.js）：① 真逻辑 = 跑 App.vue 真 setup()，
 * 只换 http.post 那一发出口，clearSession / hasSession / saveSession 走 lib/http 真身；
 * ② 真产物 = SSR 出的 HTML 里 data-testid="login-error" 与 data-testid="auth-toast" 两处印的字；
 * ③ 源码形状 = 「两处收的是同一句」这种一次渲染看不到的接线。
 * 🔴 一条都不置灰、不挂待办、不放宽任何既存断言；不 import 也不改写 R169 那枚文件。
 */
import { describe, expect, it, vi } from 'vitest'
import { createSSRApp, h, nextTick, reactive } from 'vue'
import { readFileSync } from 'node:fs'
import { renderToString } from '@vue/server-renderer'
import { routeLocationKey, routerKey } from 'vue-router'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { ...actual.http, post: vi.fn() } }
})

import { ROLE_KEY, TOKEN_KEY, USER_KEY } from '../../lib/http'
import App from '../../App.vue'

const source = readFileSync(new URL('../../App.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')

/** lib/http.js:95 shipped 的那句原话：本件钉「它不许被自家兜底话覆盖」，不是钉 App 自己写了什么。 */
const SERVER_SENTENCE = '登录状态已失效，请重新登录。'
/** 英文稳定码一律不许上屏（判据 §三）。 */
const CODE_WORDS = ['unauthorized', 'permission_denied', 'authentication_required', 'expiring']
/** 只有空白分隔的「文案」不算话。 */
const BLANKS = ['', '   ', '\t ', '\n']
/** 非字符串文案：上屏就成了「undefined」「null」「NaN」「[object Object]」这种字面。 */
const NON_STRINGS = [undefined, null, 123, NaN, {}, []]
const LITERALS = ['undefined', 'null', 'NaN', '[object', '123']

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

const SEED = { [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'staff' }

function routeOf(screenName) {
  return reactive({ name: screenName, path: '/' + screenName, query: {}, meta: {}, params: {}, fullPath: '/' + screenName, hash: '' })
}

function routerOf(pushed) {
  return {
    replace: target => { pushed.push(target); return Promise.resolve() },
    push: target => { pushed.push(target); return Promise.resolve() },
  }
}

/** 只取绑定、不画模板的那一腿（用在「还留在工作台」的三处既存语义上）。 */
async function mountApp(seed = {}, screenName = 'chat') {
  const store = installDomStubs(seed)
  const pushed = []
  const route = routeOf(screenName)
  let bindings = null
  const Probe = {
    name: 'R171AuthEventProbe',
    setup(props, ctx) {
      bindings = App.setup({}, ctx)
      return () => null
    },
  }
  const app = createSSRApp({ render: () => h(Probe) })
  app.provide(routeLocationKey, route)
  app.provide(routerKey, routerOf(pushed))
  await renderToString(app)
  expect(bindings, 'App.vue 应暴露可调用的 setup()').toBeTruthy()
  return { bindings, store, pushed }
}

/**
 * 同一份绑定画成真模板的那一腿：Probe 复用 App.ssrRender，所以 setup 里跑完 onAuthEvent 之后，
 * SSR 出来的 HTML 就是员工此刻看到的屏——错误条亮没亮、上面印的是哪几个字，全在 html 里对账。
 */
async function renderApp({ seed = SEED, screenName = 'chat', drive } = {}) {
  const store = installDomStubs(seed)
  const pushed = []
  const route = routeOf(screenName)
  let bindings = null
  const Probe = {
    name: 'R171AuthEventScreen',
    setup(props, ctx) {
      bindings = App.setup({}, ctx)
      bindings.checkAuth()
      drive?.(bindings)
      return bindings
    },
    ssrRender: App.ssrRender,
  }
  const app = createSSRApp({ render: () => h(Probe) })
  app.provide(routeLocationKey, route)
  app.provide(routerKey, routerOf(pushed))
  app.component('RouterView', { render: () => null }) // 工作台区没挂（v-if 已关），只补一句解析声明
  const html = await renderToString(app)
  return { bindings, html, store, pushed }
}

/** 失效收尾那一发：带进事件、带回绑定 / 会话盘 / 换屏记录 / 真产物 HTML。 */
function fire(event, options = {}) {
  return renderApp({ ...options, drive: b => b.onAuthEvent(event) })
}

/** 屏上那两处字：错误条（data-testid="login-error"）与提示条（data-testid="auth-toast"）。 */
function errorBarText(html) {
  return html.match(/data-testid="login-error"[\s\S]*?<span[^>]*>([^<]*)<\/span>/)?.[1] ?? null
}
function toastText(html) {
  return html.match(/class="auth-toast-text"[^>]*>([^<]*)</)?.[1] ?? null
}
function screenWords(html) {
  return [errorBarText(html) ?? '', toastText(html) ?? '']
}

/** 每一枚都要过的地板：两处都有话、两句话是同一句、且没把码名与字面量漏上屏。 */
function expectBothPlacesSaidSomething(html, pushed) {
  const [bar, toast] = screenWords(html)
  expect(bar, '错误条上必须有一句非空的话').toBeTruthy()
  expect(toast, '提示条上必须有一句非空的话').toBeTruthy()
  expect(toast, '错误条与提示条两处收的应当是同一句').toBe(bar)
  for (const word of CODE_WORDS) {
    expect(bar + toast, '屏上不许出现英文稳定码 ' + word).not.toContain(word)
  }
  for (const literal of LITERALS) {
    expect(bar + toast, '屏上不许出现字面量 ' + literal).not.toContain(literal)
  }
  expect(bar.trim(), '只有空白不算一句人话').not.toBe('')
  expect(pushed, '失效收尾要把人挪回登录落点').toEqual([{ name: 'overview' }])
}

describe('R171 A · 带了原话的失效事件：原话原样上屏，不许被兜底话覆盖', () => {
  it('unauthorized 带 lib/http.js 那句原话：错误条与提示条两处都还是那句原话', async () => {
    const { bindings: b, html, store, pushed } = await fire({ type: 'unauthorized', message: SERVER_SENTENCE })
    expect(b.loginError.value).toBe(SERVER_SENTENCE)
    expect(b.toast.value).toMatchObject({ tone: 'error', message: SERVER_SENTENCE })
    expect(store.has(TOKEN_KEY)).toBe(false)
    expect(b.isLoggedIn.value).toBe(false)
    expectBothPlacesSaidSomething(html, pushed)
    expect(errorBarText(html)).toBe(SERVER_SENTENCE)
    expect(toastText(html)).toBe(SERVER_SENTENCE)
  })

  it('unauthorized 带别的真原因（后端换文案 / 未来带场景句子）：照样原样上屏，不许换成自家话', async () => {
    const reason = '这台机器上的登录票据已经过期。'
    const { bindings: b, html, pushed } = await fire({ type: 'unauthorized', message: reason })
    expect(b.loginError.value).toBe(reason)
    expect(b.toast.value.message).toBe(reason)
    expectBothPlacesSaidSomething(html, pushed)
    expect(errorBarText(html)).toBe(reason)
  })
})

describe('R171 B · 没把话说齐的失效事件：这一支自己必须补一句', () => {
  it('unauthorized 少带 message：被踢回登录页，且错误条真的亮起来、两处同一句非空', async () => {
    const { bindings: b, html, store, pushed } = await fire({ type: 'unauthorized' })
    expect(store.has(TOKEN_KEY), '令牌不许留着').toBe(false)
    expect(b.isLoggedIn.value).toBe(false)
    expect(html).toContain('data-testid="login-error"') // 改前这一格 v-if 不亮
    expect(html).toContain('data-testid="auth-toast"')
    expectBothPlacesSaidSomething(html, pushed)
  })

  it.each(BLANKS)('unauthorized 带空白类文案 %j：不许亮一条空错误条', async message => {
    const { bindings: b, html, pushed } = await fire({ type: 'unauthorized', message })
    expect(html).toContain('data-testid="login-error"')
    expectBothPlacesSaidSomething(html, pushed)
    expect(b.loginError.value).toBe(b.toast.value.message)
  })

  it.each(NON_STRINGS)('unauthorized 带非字符串文案 %p：字面量不许印上屏', async message => {
    const { bindings: b, html, pushed } = await fire({ type: 'unauthorized', message })
    expect(html).toContain('data-testid="login-error"')
    expectBothPlacesSaidSomething(html, pushed)
    expect(typeof b.loginError.value).toBe('string')
  })
})

describe('R171 C · 认不得的鉴权事件：另一张脸，同样必须有话说', () => {
  it('未知 type：被踢，且必然有一句非空、且不是 unauthorized 那句', async () => {
    const { bindings: b, html, store, pushed } = await fire({ type: 'something_else' })
    expect(store.has(TOKEN_KEY), '来路不明的鉴权事件之后，本地令牌不许还留着').toBe(false)
    expect(b.isLoggedIn.value).toBe(false)
    expectBothPlacesSaidSomething(html, pushed)
    expect(b.loginError.value, '未知事件不许复用真失效那句糊过去').not.toBe(SERVER_SENTENCE)
    expect(b.toast.value.tone).toBe('error')
  })

  it.each([{ type: 'permission_denied' }, { type: 'authentication_required' }, { type: '' }, {}])(
    '认不得的形状 %j：就算它带了 message 也只说「无法识别」那一张脸，裸码名零上屏',
    async event => {
      const { bindings: b, html, pushed } = await fire({ ...event, message: 'unauthorized' })
      expectBothPlacesSaidSomething(html, pushed)
      expect(errorBarText(html)).toBe(b.loginError.value)
      expect(b.loginError.value).toBe(b.toast.value.message)
      const expired = await fire({ type: 'unauthorized' })
      expect(b.loginError.value, '认不得的事件不许复用真失效那张脸').not.toBe(expired.bindings.loginError.value)
    },
  )

  it('两张脸各说一句：话面不同，真失效说「失效」，来路不明说「无法识别」', async () => {
    const expired = await fire({ type: 'unauthorized' })
    const unknown = await fire({ type: 'something_else' })
    const expiredText = expired.bindings.loginError.value
    const unknownText = unknown.bindings.loginError.value
    expect(unknownText, '两种脸必须两句话').not.toBe(expiredText)
    expect(expiredText).toContain('失效')
    expect(unknownText).toContain('无法识别')
    expect(expiredText).not.toContain('无法识别')
    expect(unknownText).not.toContain('失效')
    expectBothPlacesSaidSomething(expired.html, expired.pushed)
    expectBothPlacesSaidSomething(unknown.html, unknown.pushed)
  })
})

describe('R171 D · 三处既存语义不退化（R169 钉过的三条）', () => {
  it('没有事件仍然什么都不做：会话、身份、错误条一起原样留着', async () => {
    const { bindings: b, store } = await mountApp(SEED)
    b.checkAuth()
    b.onAuthEvent(undefined)
    b.onAuthEvent(null)
    expect(b.isLoggedIn.value).toBe(true)
    expect(store.get(TOKEN_KEY)).toBe('jwt-live')
    expect(b.loginError.value).toBe('')
    b.goToLogin()
  })

  it('expiring 仍然只提醒：不动会话与身份，也不亮错误条', async () => {
    const { bindings: b, store, pushed } = await mountApp(SEED)
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

  it('未知 type 仍然按失效收尾：清会话、换屏、身份一起清空（宁可多踢一次）', async () => {
    const { bindings: b, store, pushed } = await mountApp(SEED)
    b.checkAuth()
    b.onAuthEvent({ type: 'something_else' })
    await nextTick()
    expect(store.has(TOKEN_KEY)).toBe(false)
    expect(store.has(USER_KEY)).toBe(false)
    expect(store.has(ROLE_KEY)).toBe(false)
    expect(b.isLoggedIn.value).toBe(false)
    expect(b.username.value).toBe('')
    expect(pushed).toEqual([{ name: 'overview' }])
  })
})

describe('R171 E · 源码形状：错误条与提示条只有一条句子来源', () => {
  it('收尾支两处都从同一个 message 变量取话，不再裸赋 event.message', () => {
    expect(source).toMatch(/loginError\.value = message\n[ ]*showToast\(message, 'error'/)
    expect(source).not.toMatch(/loginError\.value = event\.message/)
    expect(source).not.toMatch(/showToast\(event\.message, 'error'/)
    // 兜底那一步是本件的全部：少了它，B 与 C 两组当场红。
    expect(source).toMatch(/readableMessage\(event\.message\)[\s\S]{0,120}AUTH_EXPIRED_MESSAGE[\s\S]{0,80}AUTH_EVENT_UNKNOWN_MESSAGE/)
  })
})
