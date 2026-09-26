/**
 * R278 · G16 · 顶栏无死控件（块 F 第一片，判据①②③⑤）
 *
 * 病灶（改前取证，行号取本单基点 951909b 的 frontend/src/App.vue）：
 *   :393 一枚 aria-label="搜索" 的 button 没有 @click；
 *   :396 一枚 aria-label="通知" class="bell" 的 button 没有 @click；
 *   :401 退出那枚只有内容「⌄」，没有可及名称。
 * 计划书 §11 那句「顶栏无死控件；退出按钮有可及名称」（docs/frontend-plan-2026-09-14.md:592）
 * 今天不成立。本件按判据收口：两枚假控件【摘掉】，退出补真名。
 *
 * 为什么是摘而不是接（这一段是本件的立场，不是含糊话）：
 *   ① 搜索：全站没有一枚全局检索端点。app/api 的 GET/POST 名单里只有 POST /retrieval/debug
 *      （管理侧可观测工具）与各屏自己的列表，判据明写「不许接半截、不许新起端点、不许改后端」。
 *   ② 通知：今天没有一句诚实的「条数」可摆。GET /hitl/pending 的 count 是一页过滤后的长度
 *      （契约 docs/api/contract-v1.md 的 HITL Pending Listing 一节明写不得当总数用），
 *      GET /dashboard/summary 那一格不向图复核、自己写着「可能高估」，而徽标要在人点开之前
 *      就有数——只能每屏挂载多发一次请求去猜。所以壳层不摆数，也不自己第二本账。
 *
 * 三条腿（沿用本仓口径：node 环境，无 jsdom / @vue/test-utils）：
 *   ① 真产物 = 跑真 App.vue 的 setup() 并以 App.ssrRender 出真 HTML，断言屏上那枚按钮叫什么；
 *   ② 真逻辑 = 直接调 setup() 交回的 logoutLabel 与 doLogout，不 grep 句子冒充行为；
 *   ③ 接线形状 = 逐枚扫 <button 开标签，每枚都必须追到 @click / type="submit" / disabled 之一
 *      （判据⑤要的「逐枚对照表」就是这张，摘掉任一枚 @click 当场红）。
 *
 * 反证（本单实跑，跑完还原）：
 *   摘掉退出的可及名称 → 丙组三条一起红；
 *   把「搜索」那枚原样摆回去 → 甲组（逐枚对照）与乙组（顶栏只剩一枚按钮）同时红；
 *   给顶栏加一句「N 条待办」式的总数口径 → 丁组红。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, reactive } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { routeLocationKey, routerKey } from 'vue-router'

// 顶栏不碰鉴权以外的东西：整件用例不发任何网络请求（真起了请求就是真新增外部调用）。
vi.mock('../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { ...actual.http, get: vi.fn(), post: vi.fn() } }
})

import App from '../App.vue'

const source = readFileSync(new URL('../App.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const TOKEN_KEY = 'eb_token'
const USER_KEY = 'eb_user'
const ROLE_KEY = 'eb_role'

/**
 * 注释里的「按钮」二字不是控件，注释里提到的端点名也不是调用点：量具一律先在去掉注释的文本
 * 上跑（模板注释 + JS 块注释 + 整行注释），否则本件自己写的说明会把钉子钉红。
 */
const withoutComments = (text) => text
  .replace(/<!--[\s\S]*?-->/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/^[ \t]*\/\/.*$/gm, '')
const code = withoutComments(source)

/**
 * 判据⑤的量具：逐枚取 <button 的开标签本体（引号里的 > 不算收尾），
 * 再按三种「活着」的画法各判一次。返回的表就是交回里那张对照表。
 */
function buttonInventory(text) {
  const items = []
  const re = /<button\b/g
  let match = null
  while ((match = re.exec(text))) {
    const open = match.index
    let i = open + '<button'.length
    let quote = null
    while (i < text.length) {
      const ch = text[i]
      if (quote) { if (ch === quote) quote = null } else if (ch === '"' || ch === "'") quote = ch
      else if (ch === '>') break
      i += 1
    }
    const attrs = text.slice(open + '<button'.length, i).replace(/\s+/g, ' ').trim()
    items.push({
      line: text.slice(0, open).split('\n').length,
      attrs,
      click: /@click|v-on:click/.test(attrs),
      submit: /type="submit"/.test(attrs),
      disabled: /(?<![:\w-])(?:disabled|:disabled|disabled=)/.test(attrs),
    })
  }
  return items
}

const inventory = buttonInventory(code)

/** 顶栏那一行（workspace-tools 到 header 收尾）：本件判据只管这里。 */
function topbarBlock(text) {
  const from = text.indexOf('class="workspace-tools"')
  expect(from, 'App.vue 里找不到顶栏那一行').toBeGreaterThan(-1)
  const to = text.indexOf('</header>', from)
  expect(to, '顶栏那一行没有收尾的 header').toBeGreaterThan(from)
  return text.slice(from, to)
}

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

/**
 * 真渲染那一腿：跑真 setup() 并 checkAuth() 进工作台，再拿 App 自己的 ssrRender 出 HTML。
 * 面板位（RouterView）换成空桩——本件要看的是顶栏，不是任何一屏。
 */
async function renderWorkspace(seed) {
  const store = installDomStubs(seed)
  const route = reactive({
    name: 'overview', path: '/overview', query: {}, params: {},
    meta: { title: '屏名', screen: true }, fullPath: '/overview', hash: '', matched: [],
  })
  let bindings = null
  const Host = defineComponent({
    name: 'R278TopbarHost',
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
  const html = await renderToString(app)
  const from = html.indexOf('class="workspace-tools"')
  const topbar = from < 0 ? '' : html.slice(from, html.indexOf('</header>', from))
  return { html, topbar, bindings, store }
}

describe('R278 判据⑤ · 逐枚对照：App.vue 里没有一枚按了没反应的按钮', () => {
  it('扫描本身不是空的：真扫到了八枚 button（少一枚就是量具坏了）', () => {
    expect(inventory.length).toBeGreaterThanOrEqual(8)
  })

  it('每一枚都追得到 @click / type="submit" / 显式 disabled 三者之一', () => {
    const dead = inventory.filter(item => !(item.click || item.submit || item.disabled))
    expect(dead.map(item => `:${item.line} ${item.attrs}`), '这些按钮没有任何可追的行为').toEqual([])
  })

  it('改造前那两枚假控件（搜索、通知）不在源码里了', () => {
    expect(code).not.toMatch(/aria-label="搜索"/)
    expect(code).not.toMatch(/aria-label="通知"/)
    expect(code).not.toMatch(/class="bell"/)
  })
})

describe('R278 判据①② · 顶栏这一行的形状', () => {
  const block = topbarBlock(code)

  it('顶栏只剩一枚按钮，而且它就是退出', () => {
    const tools = buttonInventory(block)
    expect(tools).toHaveLength(1)
    expect(tools[0].click).toBe(true)
    expect(tools[0].attrs).toMatch(/@click="doLogout"/)
  })

  it('壳层不自己读挂起账本，也不摆任何「N 条」总数口径', async () => {
    // 去掉注释之后仍然一个字都不提那两条端点：顶栏没有第二本账，也没有为它新起的请求
    expect(code).not.toMatch(/hitl/i)
    expect(code).not.toMatch(/\/pending/)
    expect(code).not.toMatch(/dashboard/)
    expect(code).not.toMatch(/http\.get\(|authedFetch\(/)
    // 「N 条」这种总数口径一枚都不许出现在顶栏那一段里
    const { topbar } = await renderWorkspace({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'staff' })
    expect(topbar).not.toMatch(/\d+\s*(?:条|个|枚)/)
    expect(topbar).not.toMatch(/(?:待办|待审批|等你拍板)/)
  })
})

describe('R278 判据③ · 退出的可及名称（真渲染，不是 grep 句子）', () => {
  it('有账号时念得出「退出登录（当前账号 …）」，鼠标悬停也看得见同一句', async () => {
    const { topbar } = await renderWorkspace({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'staff' })
    expect(topbar).toContain('aria-label="退出登录（当前账号 baiye）"')
    expect(topbar).toContain('title="退出登录（当前账号 baiye）"')
    // 画相不变：屏上仍是那一个记号，本件只补名称，不改行为也不换字形
    expect(topbar).toMatch(/class="logout-link"[^>]*>⌄<\/button>/)
  })

  it('账号名取不到时只说「退出登录」，不许留一对空括号冒充有名字', async () => {
    const { topbar } = await renderWorkspace({ [TOKEN_KEY]: 'jwt-live' })
    expect(topbar).toContain('aria-label="退出登录"')
    expect(topbar).not.toContain('当前账号 ）')
    expect(topbar).not.toMatch(/aria-label="[^"]*\(\)/)
  })

  it('同一句名称是派生的：logoutLabel 跟着 username 走，不在模板里抄第二份', async () => {
    const { bindings, topbar } = await renderWorkspace({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'zhangsan', [ROLE_KEY]: 'admin' })
    expect(bindings.logoutLabel.value).toBe('退出登录（当前账号 zhangsan）')
    expect(topbar).toContain('aria-label="退出登录（当前账号 zhangsan）"')
    bindings.username.value = 'lisi'
    expect(bindings.logoutLabel.value).toBe('退出登录（当前账号 lisi）')
  })

  it('管理员与员工念出来是同一句：角色不在这枚名称里充数', async () => {
    const logoutOf = html => (/<button class="logout-link"[\s\S]*?<\/button>/.exec(html) || [''])[0]
    const staff = await renderWorkspace({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'staff' })
    const admin = await renderWorkspace({ [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'admin' })
    expect(logoutOf(staff.topbar), '顶栏那枚退出没渲染出来').toBeTruthy()
    expect(logoutOf(staff.topbar)).toBe(logoutOf(admin.topbar))
    expect(logoutOf(admin.topbar)).toContain('aria-label="退出登录（当前账号 baiye）"')
  })
})
