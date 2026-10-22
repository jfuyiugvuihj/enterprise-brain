/**
 * R316 判据①②③⑥⑦ · 「账号与角色」屏壳的真渲染钉
 *
 * 手法沿用 r341/r314 那一套：环境仍是 node + @vue/server-renderer（仓里没有 jsdom），
 * 只 mock 网络层那一枚 axios 实例，先真跑取数，再把同一份 bindings 渲染成真 HTML。
 * 于是这里量的是屏上真的画出了什么，不是源码里长得像那么回事的字符串。
 *
 * 五把刀里属于本件的三把都钉在这个文件：
 *   ② 403 画成空列表 → 「五张脸两两不等」与「没权限那张」当场红；
 *   ④ 摘掉 token 闸门 → 「迟到的回包不许盖掉新读数」红；
 *   ⑥ 模板原语没在 <script setup> 里 import → 屏上画出的是 <uibutton> 未知标签，
 *      数不到 class="ui-button" 就红（R333 踩过的那一把）。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { errorText } from '../../lib/errcodes'
import {
  USER_COLUMNS,
  USERS_DENIED_TITLE,
  USERS_EMPTY_TITLE,
  USERS_PATH,
} from '../../lib/users'
import { countNativeButtons } from './r288-native-button-scan.js'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }
})

import { http } from '../../lib/http'
import AdminPanel from '../AdminPanel.vue'

const source = () => readFileSync(new URL('../AdminPanel.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')

function row(overrides = {}) {
  return { id: 7, username: 'baiye', role: 'admin', department: 'finance', created_at: '2026-09-01T10:00:00+08:00', ...overrides }
}

const ok = rows => ({ status: 200, data: { users: rows } })
const status = (code, detail) => ({ response: { status: code, data: { detail } }, status: code })

/** 只有一枚 GET 的路由表：任何别的动词或别的路径都是本单越界。 */
function stubGet(handler) {
  http.get.mockImplementation(async (url) => {
    if (url !== USERS_PATH) throw new Error(`不该被请求的路径：${url}`)
    const result = await handler(url)
    if (result instanceof Error) throw result
    if (result.status && result.response) throw result
    return result
  })
  for (const verb of ['post', 'put', 'delete']) {
    http[verb].mockImplementation(async (url) => { throw new Error(`这一屏不许发写请求：${verb.toUpperCase()} ${url}`) })
  }
}

async function mountedPanel() {
  let bindings = null
  const Host = {
    name: 'R316Probe',
    setup(props, ctx) {
      bindings = AdminPanel.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Host))
  return bindings
}

const render = bindings => renderToString(h({ ...AdminPanel, setup: () => bindings }))

const visibleText = html => html
  .replace(/<!--[\s\S]*?-->/g, ' ')
  .replace(/<[^>]+>/g, ' ')
  .replace(/\s+/g, ' ')
  .trim()

const cellTexts = html => [...html.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)]
  .map(match => match[1].replace(/<[^>]+>/g, '').replace(/<!--[\s\S]*?-->/g, '').replace(/\s+/g, ' ').trim())

const flush = async () => {
  for (let i = 0; i < 8; i += 1) await Promise.resolve()
  await new Promise(resolve => setTimeout(resolve, 0))
}

/** 可控延迟：token 闸门只有「回包能迟到」才测得出来。 */
function deferredQueue() {
  const queue = []
  http.get.mockImplementation((url) => {
    if (url !== USERS_PATH) return Promise.reject(new Error(`不该被请求的路径：${url}`))
    let settle = null
    const promise = new Promise((resolve, reject) => { settle = { resolve, reject } })
    queue.push({ settle, url })
    return promise
  })
  return { queue }
}

/** 一屏一张脸：把 handler 装好、真取一次数、把屏渲染出来。 */
async function faceOfRun(handler) {
  stubGet(handler)
  const bindings = await mountedPanel()
  await bindings.loadRoster()
  await flush()
  return { bindings, html: await render(bindings) }
}

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
  http.put.mockReset()
  http.delete.mockReset()
})

describe('R316⑦ · 加载这一张脸先画上，进屏就只发那一枚 GET', () => {
  it('取数之前屏上是骨架不是空列表，也没有半句结论', async () => {
    stubGet(() => ok([row()]))
    const bindings = await mountedPanel()
    const html = await render(bindings)
    expect(html).toContain('data-testid="ui-loading-state"')
    expect(html).toContain('正在读取账号名册')
    expect(html).not.toContain('admin-users-rows')
    expect(html).not.toContain(USERS_EMPTY_TITLE)
    expect(http.get).not.toHaveBeenCalled()
  })

  it('onMounted 接的就是 loadRoster：SSR 不触发挂载钩子，所以这一条只能钉接线本身', () => {
    expect(source()).toMatch(/onMounted\(loadRoster\)/)
    expect(source()).toMatch(/onUnmounted\(invalidateRoster\)/)
  })

  it('挂载钩子跑起来后只发一枚 GET /users，一个写动词都没有', async () => {
    stubGet(() => ok([row()]))
    const bindings = await mountedPanel()
    await bindings.loadRoster()
    await flush()
    expect(http.get.mock.calls.map(call => call[0])).toEqual([USERS_PATH])
    expect(http.post).not.toHaveBeenCalled()
    expect(http.put).not.toHaveBeenCalled()
    expect(http.delete).not.toHaveBeenCalled()
  })
})

describe('R316① · 屏上那一列一列，逐格来自后端真给的键', () => {
  it('表头逐字就是 USER_COLUMNS 的 label，一列不多一列不少', async () => {
    const { html } = await faceOfRun(() => ok([row()]))
    const headers = [...html.matchAll(/<th[^>]*>[\s\S]*?<span>([^<]*)<\/span>[\s\S]*?<\/th>/g)].map(match => match[1])
    expect(headers.length, '表头一枚都没数到，量具失灵了').toBeGreaterThan(0)
    expect(headers).toEqual(USER_COLUMNS.map(column => column.label))
  })

  it('一行回包画五格：编号、账号、角色人话、部门、创建时间各就各位', async () => {
    const { html } = await faceOfRun(() => ok([row()]))
    expect(html).toContain('data-testid="admin-users-rows"')
    expect(cellTexts(html)).toEqual(['7', 'baiye', '系统管理员', 'finance', '2026-09-01 10:00'])
  })

  it('内存表那一腿 created_at 是空串：屏上说的是「未记录」，不是 0、也不是今天', async () => {
    const { html } = await faceOfRun(() => ok([row({ created_at: '', department: '' })]))
    expect(cellTexts(html)).toEqual(['7', 'baiye', '系统管理员', '未登记归属部门', '未记录'])
  })

  it('①拿假数据冒充后端没给的列：那一格一帧都上不了屏（mapUserRow 白名单被摘掉就红）', async () => {
    const planted = row({ last_login: '2026-09-27 09:00', status: 'active', email: 'baiye@example.com', is_active: true })
    const { html } = await faceOfRun(() => ok([planted]))
    const text = visibleText(html)
    for (const value of ['2026-09-27 09:00', 'active', 'baiye@example.com', '最近登录', '邮箱']) {
      expect(text, `后端从没给过的「${value}」上屏了`).not.toContain(value)
    }
    expect(cellTexts(html)).toHaveLength(USER_COLUMNS.length)
  })

  it('词表外的角色不猜：那一格说「无法识别的角色」', async () => {
    const { html } = await faceOfRun(() => ok([row({ role: 'superuser' })]))
    expect(cellTexts(html)[2]).toBe('无法识别的角色')
  })
})
describe('R316② · 五张脸两两不等，没有一张塌成「没有用户」', () => {
  it('staff 拿到 403：画的是「这一屏不向你开放」，句子出自 errcodes 词典，而且不给重试', async () => {
    const { html } = await faceOfRun(() => status(403, 'permission_denied'))
    expect(html).toContain('data-testid="admin-users-failure"')
    expect(html).toContain('data-testid="ui-error-state"')
    expect(html).toContain(USERS_DENIED_TITLE)
    expect(html).toContain(errorText('permission_denied'))
    // 空态那张脸一帧都不许同时出现
    expect(html).not.toContain('data-testid="admin-users-empty"')
    expect(html).not.toContain('data-testid="ui-empty-state"')
    expect(visibleText(html)).not.toContain(USERS_EMPTY_TITLE)
    // 权限不在重试身上，字典那句「请联系管理员开通」才是下一步
    expect(html).not.toContain('data-testid="ui-error-retry"')
  })

  it('后端把 reason code 括在散文里那一枚真实形状，画的仍是同一张没权限脸', async () => {
    const { html } = await faceOfRun(() => status(403, '权限不足: users:manage (permission_denied)'))
    expect(html).toContain(USERS_DENIED_TITLE)
    expect(html).not.toContain(USERS_EMPTY_TITLE)
    expect(html).not.toMatch(/permission_denied/)
  })

  it('401 是「登录状态已失效」，与 403 与空态都不同名同句', async () => {
    const { html } = await faceOfRun(() => status(401, 'authentication_required'))
    expect(html).toContain('登录状态已失效')
    expect(html).not.toContain(USERS_DENIED_TITLE)
    expect(html).not.toContain(USERS_EMPTY_TITLE)
    expect(html).toContain(errorText('authentication_required'))
  })

  it('503 是「存储还没就绪」：不摆表、不画空态，也不说成没权限', async () => {
    const { html } = await faceOfRun(() => status(503, 'storage_unavailable'))
    expect(html).toContain('账号存储还没就绪，名册取不到')
    expect(html).not.toContain(USERS_DENIED_TITLE)
    expect(html).not.toContain(USERS_EMPTY_TITLE)
    expect(html).not.toContain('data-testid="admin-users-rows"')
  })

  it('200 但回包读不出行是「形状不对」那张，绝不与「真零行」共用一句', async () => {
    for (const payload of [{}, { users: null }, { users: 'baiye' }]) {
      const { html } = await faceOfRun(() => ({ status: 200, data: payload }))
      expect(html).toContain('账号名册的回包读不出行')
      expect(html).not.toContain(USERS_EMPTY_TITLE)
      expect(html).not.toContain('data-testid="admin-users-empty"')
      expect(html).toContain('data-testid="ui-error-retry"')
    }
  })

  it('200 真零行才画空态，而那句话说的是回包，不替后端解释、也不说成没权限', async () => {
    const { html } = await faceOfRun(() => ok([]))
    expect(html).toContain('data-testid="admin-users-empty"')
    expect(html).toContain(USERS_EMPTY_TITLE)
    expect(html).toContain('这一发回包里没有行')
    expect(html).not.toContain(USERS_DENIED_TITLE)
    expect(html).not.toContain(errorText('permission_denied'))
    expect(html).not.toContain('data-testid="admin-users-rows"')
  })

  it('五张脸各渲染一遍，HTML 两两不等（任何一张被并成另一张，这条当场红）', async () => {
    const shots = []
    for (const handler of [
      () => status(403, 'permission_denied'),
      () => status(401, 'authentication_required'),
      () => status(503, 'storage_unavailable'),
      () => ({ status: 200, data: {} }),
      () => ok([]),
    ]) {
      const { html } = await faceOfRun(handler)
      shots.push(visibleText(html).replace(/正在读取账号名册/g, '').trim())
    }
    expect(new Set(shots).size, '两张脸被画成了同一句').toBe(5)
  })

  it('连不上服务（归不出码）也不许退成空列表：那是「没加载出来」那一张', async () => {
    const { html } = await faceOfRun(() => new Error('Network Error'))
    expect(html).toContain('账号名册没加载出来')
    expect(html).not.toContain(USERS_EMPTY_TITLE)
    expect(html).toContain('data-testid="ui-error-retry"')
  })
})

describe('R316③ · 零统计量', () => {
  it('屏上没有「共 N 人 / 占比 / 活跃」那一类句子，行多行少都不产数', async () => {
    const one = await faceOfRun(() => ok([row()]))
    const many = await faceOfRun(() => ok([row(), row({ id: 8, username: 'chen' }), row({ id: 9, username: 'zhao' })]))
    for (const { html } of [one, many]) {
      expect(visibleText(html)).not.toMatch(/共\s*\d+\s*(人|个|名)|账号总数|人数|占比|活跃|在岗/)
    }
    // 三行就是 3 枚 <tr> 与 3 x 5 格：行数只决定画多少行，不生出任何一个「前端算出来的数」。
    expect(many.html.match(/data-testid="ui-table-row"/g)).toHaveLength(3)
    expect(cellTexts(many.html)).toHaveLength(USER_COLUMNS.length * 3)
    expect(cellTexts(one.html)).toHaveLength(USER_COLUMNS.length)
  })

  it('屏壳不数 rows.length：读回来几行与这一屏说什么话无关', () => {
    expect(source()).not.toMatch(/rows\.value\.length|rows\.length/)
  })
})

describe('R316⑥ · 视觉与预算', () => {
  it('零枚裸 <button>，模板用的原语全部在 <script setup> 里 import（R333 踩过的那把刀）', async () => {
    const text = source()
    expect(countNativeButtons(text)).toBe(0)
    const setupBlock = /<script setup>([\s\S]*?)<\/script>/.exec(text)[1]
    for (const name of ['UiButton', 'UiTable', 'UiEmptyState', 'UiErrorState', 'UiLoadingState']) {
      expect(setupBlock, `${name} 没在 <script setup> 里 import`).toContain(name)
    }
    expect(setupBlock).toMatch(/import \{[^}]*\bUiButton\b[^}]*\} from '\.\/ui'/)
    const { html } = await faceOfRun(() => ok([row()]))
    expect(html).toContain('class="ui-button')
    expect(html).not.toMatch(/<uibutton|<uitable|<uierrorstate/i)
  })

  it('本件一枚新色值都不加：屏壳里没有 <style>，也没有 hex / rgba()，theme.css 一格未动', () => {
    const text = source()
    expect(text).not.toMatch(/<style/)
    expect(text).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(text).not.toMatch(/rgba?\(|hsla?\(/)
  })
})

describe('R316⑦ · token 闸门：上一份读数不许挂在屏上', () => {
  it('重新加载先把屏清回骨架，迟到的那一发不许盖掉新读数', async () => {
    const { queue } = deferredQueue()
    const bindings = await mountedPanel()

    const first = bindings.loadRoster()
    queue[0].settle.resolve(ok([row({ id: 1, username: 'old-guest' })]))
    await first
    await flush()
    expect(await render(bindings)).toContain('old-guest')

    const second = bindings.loadRoster()
    expect(await render(bindings)).toContain('data-testid="ui-loading-state"')
    expect(await render(bindings)).not.toContain('old-guest')

    queue[1].settle.resolve(ok([row({ id: 2, username: 'new-admin' })]))
    await second
    await flush()
    const html = await render(bindings)
    expect(html).toContain('new-admin')
    expect(html).not.toContain('old-guest')
  })

  it('先落地的是旧那一发也上不了屏（把闸门摘掉，这一条当场红）', async () => {
    const { queue } = deferredQueue()
    const bindings = await mountedPanel()
    const first = bindings.loadRoster()
    const second = bindings.loadRoster()

    queue[1].settle.resolve(ok([row({ id: 2, username: 'second-row' })]))
    await second
    await flush()
    queue[0].settle.resolve(ok([row({ id: 1, username: 'first-late' })]))
    await first
    await flush()

    const html = await render(bindings)
    expect(html).toContain('second-row')
    expect(html).not.toContain('first-late')
  })

  it('离开这一屏把号作废：迟到的回包既不上屏也不留下一份读数', async () => {
    const { queue } = deferredQueue()
    const bindings = await mountedPanel()
    const first = bindings.loadRoster()
    bindings.invalidateRoster()
    queue[0].settle.resolve(ok([row({ username: 'after-leave' })]))
    await first
    await flush()
    expect(await render(bindings)).not.toContain('after-leave')
  })
})