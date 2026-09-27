/**
 * R333 判据①③④⑤⑥⑦⑧ · 顶栏那枚铃铛（components/NotificationBell.vue）
 *
 * 环境仍是 node + @vue/server-renderer（仓库里没有 jsdom / @vue/test-utils，也不许 npm i），
 * 三条腿各管各的，不假装验过自己验不了的（手法与 r168 / r278 同一套）：
 *   ① 真状态：把 lib/http 那枚 axios 实例换成 mock，跑组件自己真 setup() 与真 refresh()/markOne()，
 *      读回它自己算出的 face 与 badge —— 脸不是在测试里照抄一遍常量。
 *   ② 真产物：把同一份绑定交回组件自带的 ssrRender 出真 HTML，role / aria-label / 徽标数字由真 HTML 说话。
 *      「503 被画成没有通知」这一类缺陷会在 HTML 上当场红，而不只是红在正则上。
 *   ③ 源码形状：本地副本、第二本账、新开请求层这类「渲染一次看不到」的东西钉在剥掉注释的源码上。
 *
 * 焦点与键盘这一格诚实交代：node 里没有真 DOM，所以钉的是组件【真的那条焦点与按键路径】——
 * 往 bellEl / panelEl 里塞一枚带 focus() 的假元素，调组件自己的 openPanel/closePanel/onKeydown，
 * 断言那枚假元素的 focus 被谁调用过；Enter/Space 不需要自证，触发件渲染出的是真 <button>
 * （原生即可激活），这一条由甲6 与 r288 的棘轮共同看着。
 *
 * 四把反证里与这一件相关的三把（本单实跑，跑完原样还原，数字在交回里）：
 *   · 把徽标改成页内条数 → 甲2 红（'42' 变 '3'，读屏那句也一起红）；
 *   · 把 503 当空态 → 乙1 红（那一格会画成 ui-empty-state）；
 *   · 把 changed=false 也计入未读下降 → 丙2 红（第 N 次点同一枚，屏上的数掉了一格）。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, h, nextTick, reactive } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { routeLocationKey, routerKey } from 'vue-router'

// 只换网络层：errorDetail / errorCodeOf / 词典句子保持真身，判据③才不是自证。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn() } }
})

import { http } from '../../lib/http'
import { ERROR_CODES } from '../../lib/errcodes'
import NotificationBell, {
  EMPTY_DESCRIPTION,
  EMPTY_TITLE,
  closeKeyAction,
  focusTarget,
  inboxFace,
} from '../NotificationBell.vue'
import { MAX_IDS_PER_CALL } from '../../lib/notifications'
import App from '../../App.vue'

const stripComments = (text) => text
  .replace(/<!--[\s\S]*?-->/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/^[ \t]*\/\/.*$/gm, '')
const bellSource = readFileSync(new URL('../NotificationBell.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const bellCode = stripComments(bellSource)
const appSource = readFileSync(new URL('../../App.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const appCode = stripComments(appSource)

function inboxPage(overrides = {}) {
  return {
    notifications: [],
    state: 'all',
    limit: 100,
    offset: 0,
    returned: 0,
    has_more: false,
    total: 3,
    unread_total: 3,
    unread_returned: 3,
    is_exact: true,
    sources: {},
    ...overrides,
  }
}

function row(id, state = 'unread') {
  return {
    id,
    source_type: id.split(':')[0],
    source_id: id.split(':')[1],
    title: '标题 ' + id,
    detail: '正文 ' + id,
    created_at: '2026-09-26T09:00:00+08:00',
    state,
    reference: {},
  }
}

function receipt(ids, changed = ids) {
  const set = new Set(Array.isArray(changed) ? changed : [changed])
  return {
    action: 'read',
    requested: ids.length,
    changed: ids.filter(id => set.has(id)).length,
    results: ids.map(id => ({ id, state: 'read', changed: set.has(id), reason: 'applied' })),
  }
}

function axiosError(status, detail) {
  return { isAxiosError: true, message: 'Request failed with status code ' + status, response: { status, data: { detail } } }
}

function networkError() {
  return { isAxiosError: true, code: 'ERR_NETWORK', message: 'Network Error', request: {}, response: undefined }
}

/** 跑真 setup()：借最小宿主组件把实例上下文递进去（onMounted 挂在真实例上，SSR 不触发）。 */
async function mountBindings() {
  let bindings = null
  const Probe = {
    name: 'R333Probe',
    setup(props, ctx) {
      bindings = NotificationBell.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Probe))
  expect(bindings, '组件应交出可调用的 setup() 绑定').toBeTruthy()
  return bindings
}

/** 把同一份绑定交回组件自己的 ssrRender，渲染整块真 HTML。 */
const renderState = bindings => renderToString(h({ ...NotificationBell, setup: () => bindings }))

/** 带 focus() 的假元素：node 里没有 DOM，但组件那条「焦点交回触发件」的路径是真的。 */
const focusSpy = (name = 'node') => ({
  name,
  focuses: 0,
  focus() { this.focuses += 1 },
  $el: null,
})

beforeEach(() => {
  vi.clearAllMocks()
  http.get.mockResolvedValue({ data: inboxPage() })
  http.post.mockImplementation(async (_path, postData) => ({ data: receipt(postData.ids, postData.ids) }))
})

// ==================== 甲 · 判据⑥ 三张脸齐 + 判据① 徽标口径 ====================

describe('R333 判据⑥ · 加载 / 真空 / 失败三张脸互不冒充', () => {
  it('脸只有四条取值，且失败排在「空」之前（读不到永远不许说成没有）', () => {
    const faces = [
      inboxFace({ loading: true, rowCount: 3 }),
      inboxFace({ rowCount: 0 }),
      inboxFace({ rowCount: 2 }),
      inboxFace({ failure: { face: 'storage' }, rowCount: 0 }),
    ]
    expect(faces).toEqual(['loading', 'empty', 'list', 'storage'])
    expect(new Set(faces).size).toBe(4)
    expect(inboxFace({ loading: true, failure: { face: 'error' }, rowCount: 9 })).toBe('loading')
    expect(inboxFace({ failure: { face: 'error' }, rowCount: 1 })).toBe('error')
  })

  it('一次都没读过的时候画的是「正在读取」，不是「现在没有要看的通知」', async () => {
    const bindings = await mountBindings()
    expect(bindings.loading.value, '初值必须就是在读：没读过一次不配宣布空').toBe(true)
    // 三张脸住在面板里：先把面板展开，再问它此刻画的是哪一张（收起时的脸在丁组另有一枚钉）。
    bindings.open.value = true
    const html = await renderState(bindings)
    expect(html).toContain('data-testid="ui-loading-state"')
    expect(html).toContain('正在读取通知')
    expect(html).not.toContain('data-testid="ui-empty-state"')
    expect(html).not.toContain(EMPTY_TITLE)
  })

  it('200 且后端说没有 ⇒ 空态（role=status），并明说这是查询结果而不是坏了', async () => {
    http.get.mockResolvedValue({ data: inboxPage({ total: 0, unread_total: 0 }) })
    const bindings = await mountBindings()
    await bindings.refresh()
    expect(bindings.face.value).toBe('empty')
    bindings.open.value = true
    const html = await renderState(bindings)
    expect(html).toContain('data-testid="ui-empty-state"')
    expect(html).toContain(EMPTY_TITLE)
    expect(html).toContain(EMPTY_DESCRIPTION)
    expect(html).not.toContain('data-testid="ui-error-state"')
  })

  it('有行 ⇒ 列表：一行就是后端那一枚，屏上的行数与响应的行数一枚不差', async () => {
    http.get.mockResolvedValue({ data: inboxPage({ notifications: [row('alert:1'), row('approval:2'), row('document:a.md#v1')] }) })
    const bindings = await mountBindings()
    await bindings.refresh()
    expect(bindings.face.value).toBe('list')
    bindings.open.value = true
    const html = await renderState(bindings)
    expect((html.match(/data-testid="notification-row"/g) || []).length).toBe(3)
    expect(html).toContain('标题 alert:1')
    expect(html).not.toContain('data-testid="ui-empty-state"')
  })

  // 反证甲5：把触发件换成裸 <button> —— r288 的棘轮与这一条一起红。
  it('触发件是 components/ui 的 UiButton 原语：屏上是真 <button> 且带 ui-button 档位类，本件源码零枚裸开标签', async () => {
    const bindings = await mountBindings()
    const html = await renderState(bindings)
    const trigger = /<button[^>]*data-testid="notification-trigger"[^>]*>/.exec(html)
    expect(trigger, '顶栏这枚铃铛没渲染出真 button').toBeTruthy()
    expect(trigger[0]).toContain('ui-button')
    expect(trigger[0]).toContain('type="button"')
    expect(bellCode.match(/<button(?=[\s/>])/gi) || [], '本件里长出了裸 button 开标签').toHaveLength(0)
    expect(bellCode).toMatch(/<UiButton/)
  })
})

describe('R333 判据① · 徽标的数字只可能来自后端全集未读', () => {
  // 反证甲2：把 badge 的出处改成 unread_returned / returned / rows.length —— 这一枚当场红。
  it('全集 42 条未读、这一页只画 3 行：徽标画 42，页内那两格在 HTML 上一处都不许成为口径', async () => {
    http.get.mockResolvedValue({ data: inboxPage({ unread_total: 42, total: 50, returned: 3, unread_returned: 3, notifications: [row('alert:1'), row('alert:2'), row('alert:3')] }) })
    const bindings = await mountBindings()
    await bindings.refresh()
    expect(bindings.badge.value).toBe('42')
    expect(bindings.unread.value).toBe(42)
    const html = await renderState(bindings)
    expect(html).toMatch(/data-testid="notification-badge"[^>]*>42</)
    expect(html).toContain('aria-label="通知，42 条未读通知"')
    expect(html).not.toMatch(/aria-label="[^"]*3 条未读/)
  })

  it('is_exact=false 时徽标与读屏一起改口说「至少」：下界不许冒充全数', async () => {
    http.get.mockResolvedValue({ data: inboxPage({ unread_total: 42, is_exact: false }) })
    const bindings = await mountBindings()
    await bindings.refresh()
    expect(bindings.badge.value).toBe('42+')
    const html = await renderState(bindings)
    expect(html).toContain('aria-label="通知，至少 42 条未读通知"')
  })

  it('未读为零：徽标不画数字，读屏念的是「没有未读通知」；这一格与「还没读到」不是同一句话', async () => {
    http.get.mockResolvedValue({ data: inboxPage({ unread_total: 0, total: 0 }) })
    const bindings = await mountBindings()
    await bindings.refresh()
    expect(bindings.badge.value).toBe('')
    const html = await renderState(bindings)
    expect(html).not.toContain('data-testid="notification-badge"')
    expect(html).toContain('aria-label="通知，没有未读通知"')
    expect(html).not.toContain('通知，未读数还没读出来')
  })

  it('可见的徽标数字对读屏是隐藏的：孤零零一个 3 不配上屏，可读表达只有 aria-label 那一处', async () => {
    http.get.mockResolvedValue({ data: inboxPage({ unread_total: 3 }) })
    const bindings = await mountBindings()
    await bindings.refresh()
    const html = await renderState(bindings)
    const badge = /<span[^>]*data-testid="notification-badge"[^>]*>([^<]*)<\/span>/.exec(html)
    expect(badge, '徽标那一格没渲染出来').toBeTruthy()
    expect(badge[0]).toContain('aria-hidden="true"')
    expect(badge[1]).toBe('3')
    expect(html).toContain('aria-label="通知，3 条未读通知"')
  })
})

// ==================== 乙 · 判据③ 失败要有脸，且不伪装成空 ====================

describe('R333 判据③ · 503 / 401 / 断网三张失败脸，各自一句人话', () => {
  // 反证乙1：把 503 当空态（画成「现在没有要看的通知」）——这一枚当场红。
  it('503 storage_unavailable 画失败态：role=alert、句子逐字出自词典，且一条空态的话都不许出现', async () => {
    http.get.mockRejectedValue(axiosError(503, 'storage_unavailable'))
    const bindings = await mountBindings()
    await bindings.refresh()
    expect(bindings.face.value).toBe('storage')
    expect(bindings.failure.value.description).toBe(ERROR_CODES.storage_unavailable.message)
    bindings.open.value = true
    const html = await renderState(bindings)
    expect(html).toContain('data-testid="ui-error-state"')
    expect(html).toContain(ERROR_CODES.storage_unavailable.message)
    expect(html).not.toContain('data-testid="ui-empty-state"')
    expect(html).not.toContain(EMPTY_TITLE)
    // 503 不给重试按钮：重试不会把迁移跑出来（判据③「下一步」要说得清）
    expect(html).not.toContain('data-testid="ui-error-retry"')
  })

  it('401 说「登录状态已失效」，与 503 与断网两两不同句，三发都各自归脸', async () => {
    const cases = [
      [axiosError(401, 'authentication_required'), 'unauthorized', '登录状态已失效'],
      [axiosError(503, 'storage_unavailable'), 'storage', ERROR_CODES.storage_unavailable.message],
      [networkError(), 'error', '连不上服务'],
    ]
    const seen = []
    for (const [err, face, needle] of cases) {
      http.get.mockRejectedValue(err)
      const bindings = await mountBindings()
      await bindings.refresh()
      expect(bindings.face.value, JSON.stringify(err.response?.status || err.code)).toBe(face)
      expect(bindings.failure.value.description).toContain(needle)
      bindings.open.value = true
      const html = await renderState(bindings)
      expect(html).toContain('data-testid="ui-error-state"')
      expect(html).not.toContain('data-testid="ui-empty-state"')
      seen.push(bindings.failure.value.title + '|' + bindings.failure.value.description)
    }
    expect(new Set(seen).size, '三档失败画出了同一张脸').toBe(3)
  })

  it('读失败时徽标下屏、旧数字不留着冒充这一次的读数，读屏那句换成「没能读出来」', async () => {
    http.get.mockResolvedValue({ data: inboxPage({ unread_total: 42 }) })
    const bindings = await mountBindings()
    await bindings.refresh()
    expect(bindings.badge.value).toBe('42')
    http.get.mockRejectedValue(networkError())
    await bindings.refresh()
    expect(bindings.unread.value).toBeNull()
    expect(bindings.badge.value).toBe('')
    const html = await renderState(bindings)
    expect(html).not.toContain('data-testid="notification-badge"')
    expect(html).toContain('aria-label="通知没能读出来，打开可以看到原因"')
    expect(html).toContain('class="notif__marker"')
    expect(html).not.toContain('>42<')
  })

  it('形状不合（后端没交回未读总数）也是失败态，绝不退成「没有未读通知」', async () => {
    http.get.mockResolvedValue({ data: { notifications: [], total: 0 } })
    const bindings = await mountBindings()
    await bindings.refresh()
    expect(bindings.face.value).toBe('error')
    bindings.open.value = true
    const html = await renderState(bindings)
    expect(html).toContain('data-testid="ui-error-state"')
    expect(html).not.toContain(EMPTY_TITLE)
    expect(html).not.toContain('没有未读通知')
  })
})

// ==================== 丙 · 判据④ 幂等 · 切批 · 回执可分辨 ====================

describe('R333 判据④ · 重复点同一枚不报错，changed=false 时未读数不许再动', () => {
  /** 打开面板：真实路径（写完之后一律再读一次，屏上的数以再读为准）。 */
  async function openPanelWithRows(bindings, rowsData) {
    http.get.mockResolvedValue({ data: rowsData })
    await bindings.refresh()
    await bindings.openPanel()
    await nextTick()
  }

  // 反证丙2：让组件自己算 unread - changed —— 这一枚当场红（屏上的数会掉一格）。
  it('第 N 次点同一枚：后端回 changed=false，再读回来的未读还是 3，屏上的数一格都不许动', async () => {
    const page = inboxPage({ unread_total: 3, total: 3, returned: 1, unread_returned: 1, notifications: [row('alert:7')], is_exact: true })
    const bindings = await mountBindings()
    await openPanelWithRows(bindings, page)
    expect(bindings.badge.value).toBe('3')
    http.post.mockResolvedValue({ data: receipt(['alert:7'], []) })   // 结论没变：这一枚早就是已读
    http.get.mockResolvedValue({ data: inboxPage({ unread_total: 3, total: 3, notifications: [row('alert:7', 'read')] }) })
    const again = await bindings.markOne(bindings.rows.value[0], 'read')
    expect(again.changed).toBe(0)
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(http.post.mock.calls[0][1]).toEqual({ ids: ['alert:7'] })
    expect(bindings.unread.value, '第 N 次点同一枚，未读数被前端自己减了一格').toBe(3)
    const html = await renderState(bindings)
    expect(html).toMatch(/data-testid="notification-badge"[^>]*>3</)
  })

  it('第一次点：后端回 changed=true 且再读回来是 2，屏上的数就跟着后端走（不是钉死不动）', async () => {
    const bindings = await mountBindings()
    await openPanelWithRows(bindings, inboxPage({ unread_total: 3, total: 3, notifications: [row('alert:8')] }))
    http.post.mockResolvedValue({ data: receipt(['alert:8'], ['alert:8']) })
    http.get.mockResolvedValue({ data: inboxPage({ unread_total: 2, total: 3, notifications: [row('alert:8', 'read'), row('alert:9'), row('alert:10')] }) })
    const once = await bindings.markOne(bindings.rows.value[0], 'read')
    expect(once.changed).toBe(1)
    expect(bindings.badge.value).toBe('2')
    expect(once.results[0].state).toBe('read')
  })

  it('划掉走的是另一条出口：POST /notifications/dismiss，body 仍然只有 ids', async () => {
    const bindings = await mountBindings()
    await openPanelWithRows(bindings, inboxPage({ notifications: [row('alert:11')] }))
    await bindings.markOne(bindings.rows.value[0], 'dismiss')
    expect(http.post.mock.calls[0][0]).toBe('/notifications/dismiss')
    expect(http.post.mock.calls[0][1]).toEqual({ ids: ['alert:11'] })
  })

  it('一次动作 120 枚切成 ≤50 的三批发，一枚都不许静默丢', async () => {
    const manyIds = Array.from({ length: 120 }, (_item, index) => 'alert:' + (index + 1))
    const pages = [
      inboxPage({ unread_total: 120, total: 120, notifications: manyIds.slice(0, 100).map(id => row(id)), has_more: true }),
      inboxPage({ unread_total: 120, total: 120, notifications: manyIds.slice(100).map(id => row(id)), has_more: false }),
    ]
    const bindings = await mountBindings()
    let read = 0
    http.get.mockImplementation(async () => ({ data: pages[Math.min(read++, pages.length - 1)] }))
    const receiptAll = await bindings.markEverything()
    expect(read, '收未读清单要逐页读，一页都不许少').toBeGreaterThanOrEqual(3)
    expect(receiptAll.requested).toBe(120)
    const writes = http.post.mock.calls
    expect(writes.length).toBe(3)
    writes.forEach(call => expect(call[1].ids.length).toBeLessThanOrEqual(MAX_IDS_PER_CALL))
    expect(writes.map(call => call[1].ids.length)).toEqual([50, 50, 20])
    expect(writes.map(call => call[0])).toEqual(['/notifications/read', '/notifications/read', '/notifications/read'])
    expect(writes.map(call => call.length)).toEqual([2, 2, 2])
  })

  it('写失败的句子说的是「这次动作没能改成」，条数仍以重新读取为准，不许把半截成功画成完成', async () => {
    const bindings = await mountBindings()
    await openPanelWithRows(bindings, inboxPage({ notifications: [row('alert:12')] }))
    http.post.mockRejectedValue(axiosError(503, 'storage_unavailable'))
    const result = await bindings.markOne(bindings.rows.value[0], 'read')
    expect(result).toBeNull()
    expect(bindings.writeFailure.value.description).toBe(ERROR_CODES.storage_unavailable.message)
    const html = await renderState(bindings)
    expect(html).toContain('这次动作没能改成')
    expect(html).toContain('data-testid="notification-write-note"')
    expect(html).toContain(ERROR_CODES.storage_unavailable.message)
    // 句子没写完就承认没读到：徽标不能留下一枚「看起来像已经改好」的数字
    expect(http.get.mock.calls.length, '写完没有再读一次').toBeGreaterThan(1)
  })

  it('同一时刻只许一次动作在飞：连着点两次第二发根本发不出去（幂等之外的挡重复点击）', async () => {
    const bindings = await mountBindings()
    await openPanelWithRows(bindings, inboxPage({ notifications: [row('alert:13')] }))
    let release
    http.post.mockReturnValue(new Promise(resolve => { release = resolve }))
    const first = bindings.markOne(bindings.rows.value[0], 'read')
    const second = await bindings.markOne(bindings.rows.value[0], 'read')
    expect(second, '在飞的时候又发了一发写请求').toBeNull()
    expect(http.post).toHaveBeenCalledTimes(1)
    release({ data: receipt(['alert:13'], ['alert:13']) })
    await first
    expect(bindings.busy.value).toBe('')
  })
})

// ==================== 丁 · 判据⑦ 可达性 ====================

describe('R333 判据⑦ · 键盘可达、Enter/Space 可开、Esc 可关、焦点回得到位', () => {
  it('铃铛有可及名称，且带 aria-expanded / aria-controls / aria-haspopup：读屏念得出这一格是什么', async () => {
    const bindings = await mountBindings()
    const html = await renderState(bindings)
    const trigger = /<button[^>]*data-testid="notification-trigger"[^>]*>/.exec(html)
    expect(trigger).toBeTruthy()
    expect(trigger[0]).toContain('aria-label="通知，未读数还没读出来"')
    expect(trigger[0]).toContain('aria-expanded="false"')
    expect(trigger[0]).toContain('aria-controls="notification-panel"')
    expect(trigger[0]).toContain('aria-haspopup="dialog"')
    expect(bindings.face.value).toBe('loading')
  })

  it('按一次就开：面板渲染出 role=dialog，aria-expanded 跟着翻成 true，焦点落进面板', async () => {
    const bindings = await mountBindings()
    const panel = focusSpy('panel')
    bindings.panelEl.value = panel
    await bindings.togglePanel()
    await nextTick()
    expect(bindings.open.value).toBe(true)
    const html = await renderState(bindings)
    expect(html).toContain('data-testid="notification-panel"')
    expect(html).toMatch(/role="dialog"/)
    const trigger = /<button[^>]*data-testid="notification-trigger"[^>]*>/.exec(await renderState(bindings))
    expect(trigger[0]).toContain('aria-expanded="true"')
    expect(panel.focuses, '打开面板没把焦点放进去').toBe(1)
  })

  it('关闭后焦点回到触发件：那枚假元素的 focus 真的被调用过一次', async () => {
    const bindings = await mountBindings()
    const bell = focusSpy('bell')
    bindings.panelEl.value = focusSpy('panel')
    bindings.bellEl.value = bell
    await bindings.openPanel()
    await nextTick()
    expect(bindings.open.value).toBe(true)
    bindings.closePanel()
    expect(bindings.open.value).toBe(false)
    expect(bell.focuses, '关闭后没把焦点交回触发件').toBe(1)
  })

  it('Esc 才关：Tab 与其它键不许抢；输入框里的 Esc 留给「清空输入」那一层语义', async () => {
    expect(closeKeyAction({ key: 'Escape', target: { tagName: 'DIV' } })).toBe(true)
    expect(closeKeyAction({ key: 'Tab', target: { tagName: 'DIV' } })).toBe(false)
    expect(closeKeyAction({ key: 'Enter', target: { tagName: 'BUTTON' } })).toBe(false)
    expect(closeKeyAction({ key: ' ', target: { tagName: 'BUTTON' } })).toBe(false)
    expect(closeKeyAction({ key: 'Escape', target: { tagName: 'INPUT' } })).toBe(false)
    expect(closeKeyAction(null)).toBe(false)
    // 双向都钉：不是 Esc 的键一律不许关面板、也不许 preventDefault（Tab 还要留着走焦点环），
    // 只有 Esc 才关并吃掉那一次默认行为。只测「Esc 能关」是软的：把条件摘成「任何键都关」它照样绿。
    const bindings = await mountBindings()
    bindings.panelEl.value = focusSpy('panel')
    bindings.bellEl.value = focusSpy('bell')
    await bindings.openPanel()
    await nextTick()
    let prevented = 0
    const key = name => ({ key: name, target: { tagName: 'DIV' }, preventDefault: () => { prevented += 1 } })
    await bindings.onKeydown(key('Tab'))
    await bindings.onKeydown(key('Enter'))
    await bindings.onKeydown(key('a'))
    expect(bindings.open.value, '这三枚键里有一枚把面板关了：只有 Esc 配关它').toBe(true)
    expect(prevented, '不是 Esc 就不许 preventDefault').toBe(0)
    await bindings.onKeydown(key('Escape'))
    expect(bindings.open.value).toBe(false)
    expect(prevented).toBe(1)
    const html = await renderState(bindings)
    expect(html).not.toContain('data-testid="notification-panel"')
  })

  it('焦点落点这枚函数不误伤：没有可聚焦目标就什么都不做，绝不猜一个别的选择器', () => {
    const spy = focusSpy('x')
    expect(focusTarget(spy)).toBe(true)
    expect(focusTarget({ $el: spy })).toBe(true)
    expect(spy.focuses).toBe(2)
    expect(focusTarget(null)).toBe(false)
    expect(focusTarget({ focus: 'not-a-function' })).toBe(false)
  })

  it('触发件的点击绑定只有一处，且接的是 togglePanel（判据⑦的可开 = 真接了行为，不是死控件）', () => {
    const triggers = bellCode.match(/<UiButton[\s\S]*?data-testid="notification-trigger"[\s\S]*?>/g) || []
    expect(triggers).toHaveLength(1)
    expect(triggers[0]).toMatch(/@click="togglePanel"/)
    expect(triggers[0]).toMatch(/@keydown="onKeydown"/)
  })
})

// ==================== 戊 · 判据⑤ 不开第二本账 ====================

describe('R333 判据⑤ · 通知是那三本账的投影，这里不开第二本账', () => {
  it('本件不碰任何本地存储：没有 localStorage / sessionStorage / indexedDB，也没有自己那份未读副本', () => {
    expect(bellCode).not.toMatch(/localStorage|sessionStorage|indexedDB|document\.cookie/)
    expect(bellCode).not.toMatch(/watch\(.*unread.*setItem/)
  })

  it('本件不复制那三本账的任何清单：不 import alerts / insight / hitl / dashboard 的数据层，也不发它们的请求', () => {
    expect(bellCode).not.toMatch(/from '\.\.\/lib\/(alerts|insight|sessions|provenance|dashboard|health|feedback)'/)
    expect(bellCode).not.toMatch(/components\/hitl/)
    expect(bellCode).not.toMatch(/\/alerts|\/hitl|\/pending|\/dashboard|\/insight/)
    expect(bellCode).not.toMatch(/axios|(^|[^.\w])fetch\s*\(|\/api\/v1/)
  })

  it('列表只可能来自响应：没有任何写死的演示行，也没有第二处给 rows 赋值的地方', () => {
    expect(bellCode).not.toMatch(/devFixtures|fixtures|MOCK|DEMO_/)
    const assigns = bellCode.match(/rows\.value\s*=/g) || []
    expect(assigns, 'rows 的赋值口不止两处（要么来自响应、要么清空）').toHaveLength(2)
    expect(bellCode.match(/inbox\.value\s*=/g) || []).toHaveLength(2)
  })

 it('未读数没有第二处来源：组件里不许对unread做任何算术，也不许把本页长度当总数', () => {
    expect(bellCode).not.toMatch(/unread[^\n]*[-+]/)
   expect(bellCode).not.toMatch(/unread\.value\s*[-+*/]/)
    expect(bellCode).not.toMatch(/unread\s*=\s*unread/)
    expect(bellCode).not.toMatch(/receipt\.changed/)
    expect(bellCode).not.toMatch(/length.*\|\|.*unread|unread.*\|\|.*length/)
  })

  it('壳层只多了一枚挂载点：App.vue 仍然自己不发通知请求、不读台账、不出现第二处通知字样', () => {
    expect(appCode).toMatch(/<NotificationBell \/>/)
    expect(appCode).toMatch(/from '\.\/components\/NotificationBell\.vue'/)
    expect(appCode).not.toMatch(/notifications|\/notifications/)
    expect(appCode).not.toMatch(/http\.get\(|authedFetch\(|localStorage\.(get|set)Item\('notif/)
    expect(appCode.match(/<UiButton/g) || []).toHaveLength(8)
  })
})

// ==================== 己 · 判据⑧ 搜索那一格没被顺手动 ====================

describe('R333 判据⑧ · 只接通知那一枚，搜索那一格仍然空着', () => {
  it('顶栏与铃铛里都没有「搜索」那一格，也没有任何全局检索端点被接上', () => {
    expect(bellCode).not.toMatch(/搜索|检索/)
    expect(appCode).not.toMatch(/aria-label="搜索"/)
    expect(bellCode).not.toMatch(/retrieval\/debug|\/search|searchQuery/)
  })

  it('摘掉那枚旧控件的理由里，只有「通知」那一半被 R299 推翻：搜索那一半一字未动地留在账上', () => {
    // App.vue 顶部那段 R278 说明仍然写着搜索没有诚实出处；本件只补通知那一格。
    expect(appSource).toMatch(/全站没有一枚「全局检索」端点可用/)
    expect(appSource).toMatch(/徽标要在人点开之前就有数/)
  })
})

// ==================== 庚 · 真壳层的顶栏那一段：今天恰好两枚按钮 ====================

/**
 * 这一组为什么要在本件再数一遍：r278 的挂载腿用的是运行时 compile()（夹具的注册表里没有
 * NotificationBell，会打一句 Failed to resolve component），那一腿数到的枚数今天不含铃铛。
 * 本组走的是 App 自己那份 ssrRender（脚本绑定在位，铃铛真能画出来），数的就是屏上的真产物。
 * 「两枚」是这一单故意钉住的新常态：再加第三枚，必须先有诚实出处，再显式改本组这一枚钉。
 */

/** node 环境没有 window / localStorage：内存替身，手法与 r278 / r307b 同一套。 */
function shellStubs(seed) {
  const store = new Map(Object.entries(seed))
  globalThis.window = globalThis.window || { addEventListener() {}, removeEventListener() {} }
  globalThis.document = globalThis.document || { addEventListener() {}, removeEventListener() {}, visibilityState: 'visible' }
  globalThis.localStorage = {
    getItem: key => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: key => store.delete(key),
    clear: () => store.clear(),
  }
  return store
}

/** 跑真 App.vue 的 setup() 与它自己那份 ssrRender，抠出顶栏 .workspace-tools 那一段真 HTML。 */
async function renderTopbar(seed) {
  shellStubs(seed)
  const route = reactive({
    name: 'overview', path: '/overview', query: {}, params: {},
    meta: { title: '屏名', screen: true }, fullPath: '/overview', hash: '', matched: [],
  })
  const Host = defineComponent({
    name: 'R333ShellHost',
    ssrRender: App.ssrRender,
    setup(props, ctx) {
      const bindings = App.setup({}, ctx)
      bindings.checkAuth()
      return bindings
    },
  })
  const app = createSSRApp(Host)
  app.provide(routeLocationKey, route)
  app.provide(routerKey, { push() {}, replace() {}, currentRoute: { value: route } })
  app.component('RouterView', { ssrRender: () => {} })
  const html = await renderToString(app)
  const from = html.indexOf('class="workspace-tools"')
  expect(from, '渲染产物里找不到顶栏那一段，壳层坏了，下面数的都不算数').toBeGreaterThan(-1)
  const end = html.indexOf('</header>', from)
  expect(end, '顶栏那一段没有收尾，切出来的区间不可信').toBeGreaterThan(from)
  // SSR 会把模板里的注释原样上屏（R278/R333 那两段账就写在这一段里），先剥掉再数：
  // 本组要钉的是「这一段里有哪些控件」，不是「注释里提没提过搜索」。
  return html.slice(from, end).replace(/<!--[\s\S]*?-->/g, '')
}

const STAFF_SEED = { eb_token: 'jwt-live', eb_user: 'baiye', eb_role: 'staff' }
/** 逐枚抠出这一段里的 <button>：属性串 + 可见文本，别拿整屏的控件凑数。 */
function topbarButtons(html) {
  const items = []
  const re = /<button\b/g
  let match = null
  while ((match = re.exec(html))) {
    const open = match.index
    let at = open + '<button'.length
    let quote = null
    while (at < html.length) {
      const ch = html[at]
      if (quote) { if (ch === quote) quote = null } else if (ch === '"' || ch === "'") quote = ch
      else if (ch === '>') break
      at += 1
    }
    const close = html.indexOf('</button>', at)
    items.push({
      attrs: html.slice(open + '<button'.length, at).replace(/\s+/g, ' ').trim(),
      text: (close < 0 ? '' : html.slice(at + 1, close)).replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim(),
    })
  }
  return items
}

describe('R333 庚 · 真壳层（App 自己那份 ssrRender）：顶栏那一段恰好退出 + 铃铛两枚', () => {
  it('两枚都是真 <button>，都出自 UiButton，一枚不多一枚不少', async () => {
    const topbar = await renderTopbar(STAFF_SEED)
    const buttons = topbarButtons(topbar)
    expect(buttons, '顶栏那一段的枚数不是「退出 + 铃铛」两枚了：要加第三枚，先给它一句诚实出处，再来改本组这一枚钉').toHaveLength(2)
    buttons.forEach(item => {
      expect(item.attrs, '这一枚不是 UiButton 画的：' + item.attrs).toContain('ui-button')
      expect(/ui-button--(primary|secondary|ghost|danger)/.test(item.attrs), '档位类没算出来：' + item.attrs).toBe(true)
    })
    expect(/class="[^"]*notif__bell[^"]*"/.test(buttons[0].attrs), '第一枚不是铃铛：' + buttons[0].attrs).toBe(true)
    expect(/class="[^"]*logout-link[^"]*"/.test(buttons[1].attrs), '第二枚不是退出：' + buttons[1].attrs).toBe(true)
  })

  it('铃铛在顶栏里画的是「还没读出来」那一张脸：SSR 阶段一个数字都不许凭空摆（0 与未知不是 3）', async () => {
    const topbar = await renderTopbar(STAFF_SEED)
    expect(topbar).toMatch(/aria-label="通知，未读数还没读出来"/)
    expect(topbar).not.toMatch(/notif__badge/)
    expect(topbar).not.toMatch(/\d+\s*条/)
  })

  it('退出那一枚的既有语义没被顶栏新客挤掉：同一句名称仍在 aria-label 与 title 两处', async () => {
    const topbar = await renderTopbar(STAFF_SEED)
    expect(topbar).toContain('aria-label="退出登录（当前账号 baiye）"')
    expect(topbar).toContain('title="退出登录（当前账号 baiye）"')
    expect(topbar).toContain('⌄')
  })

  it('这一段里没有「搜索」，也没有第二处通知字样（判据⑧在真产物上再数一遍）', async () => {
    const topbar = await renderTopbar(STAFF_SEED)
    expect(topbar).not.toMatch(/搜索|检索/)
    expect((topbar.match(/notif__bell/g) || []).length, '顶栏里长出了第二枚铃铛').toBe(1)
  })
})
