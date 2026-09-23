/**
 * R168 · 判据① + 判据③ —— 挂起待办那一屏的「脸」与「行」
 *
 * 环境仍是 node + @vue/server-renderer（仓库里没有 jsdom / @vue/test-utils，也不许 npm i），
 * 所以三条腿各管各的，不假装验过自己验不了的：
 *   ① 真状态：把 lib/http 的 axios 实例换成 mock，跑组件自己的 setup() 与真的 loadPending()，
 *      读回它自己算出的 face 与 failure —— 脸不是在测试里照抄一遍常量。
 *   ② 真产物：拿到的状态交回组件自带的 ssrRender 渲染整屏，role / 文案 / 行数为零由真 HTML 说话。
 *      「403 被画成暂无待办」这种缺陷会在 HTML 上当场红，而不只是红在正则上。
 *   ③ 源码形状：假数据、演示常量这类「渲染一次看不到」的东西钉在源码上。
 *
 * permission_denied / storage_unavailable 等码名在本文件里是【输入】而不是【输出】：
 * 判据是喂真码进真 errorCodeOf / errorDetail（这两个不 mock），再断言上屏的句子已无人话之外的码名。
 *
 * 两把反证（本单要求实测红→绿，见工单交付说明）：
 *   反证甲「把空态改成假数据」→ 打红 describe「判据③ · 行只可能来自响应」全体（本文件 9–12 枚）。
 *   反证乙「把无权渲染成空列表」→ 打红 it「403 无权限不许渲染成『暂无待办』」。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'

// 只换网络层：errorDetail / errorCodeOf 保持真身，判据才不会被 mock 顺带改掉。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn() }, authedFetch: vi.fn() }
})

import { http } from '../../lib/http'
import { sessions } from '../../lib/sessions'
import { rowFace, rowLabels, stepLabel } from '../hitl/HitlPendingRow.vue'
import HitlPendingPanel, {
  DENIED_WHERE,
  DENIED_TITLE,
  EMPTY_DESCRIPTION,
  EMPTY_TITLE,
  PENDING_PAGE_SIZE,
  PENDING_PATH,
  READ_FAILED_TITLE,
  STORAGE_DESCRIPTION,
  STORAGE_TITLE,
  mapPendingRow,
  pendingFace,
  pendingFailureView,
  pendingShapeFailure,
} from '../hitl/HitlPendingPanel.vue'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const source = name => read(`../${name}`)
const render = component => renderToString(h({ render: () => h(component) }))

/** 跑真组件的 setup()：借最小宿主组件把实例上下文递进去，onMounted 挂在真实例上（SSR 不触发）。 */
async function mountBindings(component) {
  let bindings = null
  const Probe = {
    name: 'R168Probe',
    setup(props, ctx) {
      bindings = component.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Probe))
  expect(bindings, '组件应暴露可调用的 setup()').toBeTruthy()
  return bindings
}

/** 把同一份绑定交回组件自己的 ssrRender，渲染整屏真 HTML。 */
const renderState = (component, bindings) => renderToString(h({ ...component, setup: () => bindings }))

/** 后端账本一行的真形状（chat.py::hitl_pending 的 items 元素，字段一个不多一个不少）。 */
function pendingRow(overrides) {
  return Object.assign({
    session_id: 'sess-1',
    owner_user_id: 'u-1',
    parked_steps: ['chart'],
    labels: ['📈 生成图表'],
    status: 'awaiting',
    created_at: '2026-09-23T09:12:44.123456+08:00',
    expires_at: '2026-09-23T09:42:44.123456+08:00',
    request_id: 'req-9f2c',
    trace_id: 'tr-1',
    task_id: 'tk-1',
  }, overrides || {})
}

/** 外层信封：count 是过滤后的长度（契约明写不得当总数用），has_more 说的是账本还有行。 */
function pendingPage(items, extra) {
  return Object.assign({
    items,
    count: items.length,
    limit: PENDING_PAGE_SIZE,
    offset: 0,
    has_more: false,
  }, extra || {})
}

/** axios 错误的真形状：{ response: { status, data: { detail } } }。 */
function httpError(status, code) {
  return { response: { status, data: code === undefined ? undefined : { detail: code } }, message: 'Request failed with status code ' + status }
}

const countRows = html => (html.match(/data-testid="hitl-row"/g) || []).length

beforeEach(() => {
  vi.clearAllMocks()
  sessions.value = []
  http.get.mockResolvedValue({ data: pendingPage([]) })
})

// ==================== 判据① · 空态 / 挂起 / 无权三态互不相同 ====================

describe('R168 判据① · pendingFace 只有一条出口，读失败永远排在小空表之前', () => {
  it('四张脸的取值互不相同', () => {
    const faces = [
      pendingFace({ loading: true, rowCount: 3 }),
      pendingFace({ rowCount: 0 }),
      pendingFace({ rowCount: 2 }),
      pendingFace({ failure: { face: 'denied' } }),
    ]
    expect(faces).toEqual(['loading', 'empty', 'list', 'denied'])
    expect(new Set(faces).size).toBe(4)
  })

  it('loading 优先于一切：还没读过账本就不许替账本宣布它没有内容', () => {
    expect(pendingFace({ loading: true, failure: { face: 'error' }, rowCount: 9 })).toBe('loading')
  })

  // 这条是判据①的命门：failure 一旦排到 rowCount 之后，服务坏了就说成「你没有待办」。
  it('失败排在 rowCount 之前：带着一行数据失败也不给 list / empty', () => {
    expect(pendingFace({ failure: { face: 'error' }, rowCount: 1 })).toBe('error')
    expect(pendingFace({ failure: { face: 'denied' }, rowCount: 0 })).toBe('denied')
    expect(pendingFace({ failure: { face: 'denied' }, rowCount: 0 })).not.toBe('empty')
  })
})

describe('R168 判据① · 四种响应画出四张不复制的脸（真 loadPending + 真 HTML）', () => {
  it('200 空数组 -> 空态（role=status，明说「确实没有挂着的事」）', async () => {
    http.get.mockResolvedValue({ data: pendingPage([]) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    expect(bindings.face.value).toBe('empty')
    const html = await renderState(HitlPendingPanel, bindings)
    expect(html).toContain('data-testid="ui-empty-state"')
    expect(html).toMatch(/<div class="ui-empty-state[^"]*" role="status"/)
    expect(html).toContain(EMPTY_TITLE)
    // 空态不许同时是失败态，也不许有一行数据。
    expect(html).not.toContain('data-testid="ui-error-state"')
    expect(countRows(html)).toBe(0)
  })

  it('SSR 首屏（还没发过请求）是 loading，不是空态也不是列表', async () => {
    const html = await render(HitlPendingPanel)
    expect(html).toContain('data-testid="ui-loading-state"')
    expect(html).not.toContain(EMPTY_TITLE)
    expect(countRows(html)).toBe(0)
    // 首屏也不许有任何按钮：这一屏的按钮只长在真行上。
    expect(html).not.toContain('<button')
  })

  // 反证乙的靶子：把 403 渲染成空列表 / 「暂无待办」，这一枚当场红。
  it('403 无权限不许渲染成「暂无待办」', async () => {
    http.get.mockRejectedValue(httpError(403, 'permission_denied'))
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    expect(bindings.face.value).toBe('denied')
    const html = await renderState(HitlPendingPanel, bindings)
    expect(html).toContain('data-testid="ui-error-state"')
    expect(html).toMatch(/<div class="ui-error-state[^"]*" role="alert"/)
    expect(html).toContain(DENIED_TITLE)
    expect(html).toContain(DENIED_WHERE)
    // 无权与空是两张脸：无权这一屏上不许出现空态那句话、那个 role，也不许出现「暂无待办」。
    expect(html).not.toContain(EMPTY_TITLE)
    expect(html).not.toContain(EMPTY_DESCRIPTION)
    expect(html).not.toContain('ui-empty-state')
    expect(html).not.toMatch(/暂无待办|没有等你拍板/)
  })

  it('无权不给重试按钮：权限不是重试能试出来的', async () => {
    http.get.mockRejectedValue(httpError(403, 'permission_denied'))
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    expect(pendingFailureView(httpError(403, 'permission_denied')).retryable).toBe(false)
    const html = await renderState(HitlPendingPanel, bindings)
    expect(html).not.toContain('data-testid="ui-error-retry"')
  })

  it('401 未登录 / 503 账本没就绪 / 500 真坏了：三张失败脸两两不同', async () => {
    const unauthorized = pendingFailureView(httpError(401, undefined))
    const storage = pendingFailureView({ response: { status: 503, data: { detail: 'storage_unavailable' } }, message: 'Request failed' })
    const broken = pendingFailureView(httpError(500, 'internal_error'))
    expect([unauthorized.face, storage.face, broken.face]).toEqual(['unauthorized', 'storage', 'error'])
    expect(new Set([unauthorized.title, storage.title, broken.title]).size).toBe(3)
    expect(storage.title).toBe(STORAGE_TITLE)
    expect(storage.retryable).toBe(false)
    expect(broken.retryable).toBe(true)
    // 「表没建」要说得让人能去修：句子指迁移，不给一个空转的重试按钮。
    expect(STORAGE_DESCRIPTION).toMatch('迁移')

    http.get.mockRejectedValue({ response: { status: 503, data: { detail: 'storage_unavailable' } }, message: 'Request failed' })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    expect(bindings.face.value).toBe('storage')
    const html = await renderState(HitlPendingPanel, bindings)
    expect(html).toContain(STORAGE_TITLE)
    expect(html).not.toContain(EMPTY_TITLE)
  })

  it('码名一律走独立通道，给人看的句子与描述里没有裸码', async () => {
    const view = pendingFailureView({ response: { status: 403, data: { detail: { code: 'permission_denied', message: '没有权限' } } }, message: 'Request failed' })
    const SNAKE = /[a-z][a-z0-9]*_[a-z0-9_]+/
    expect(SNAKE.test(view.title)).toBe(false)
    expect(SNAKE.test(view.description)).toBe(false)
    // 唯一容许出现码名的位置是 codeLabel 那格，且必须带「错误码」字样。
    if (view.codeLabel) expect(view.codeLabel).toMatch(/^错误码：/)
  })

  it('这一屏只发一条请求，打的就是挂起账本，分页参数按后端默认档', async () => {
    http.get.mockResolvedValue({ data: pendingPage([pendingRow()]) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    expect(http.get.mock.calls.map(call => call[0])).toEqual([PENDING_PATH])
    expect(http.get.mock.calls[0][1]).toEqual({ params: { limit: PENDING_PAGE_SIZE, offset: 0 } })
    expect(PENDING_PATH).toBe('/hitl/pending')
  })

  it('items 不是数组（后端坏了）算坏了，不算空的', async () => {
    http.get.mockResolvedValue({ data: { count: 0, limit: PENDING_PAGE_SIZE, offset: 0, has_more: false } })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    expect(bindings.face.value).toBe('error')
    expect(pendingShapeFailure().face).toBe('error')
    const html = await renderState(HitlPendingPanel, bindings)
    expect(html).toContain(READ_FAILED_TITLE)
    expect(html).not.toContain(EMPTY_TITLE)
  })
})

// ==================== 判据③ · 🔴 一条假行都不许有（位阶最高） ====================

describe('R168 判据③ · 行只可能来自响应（反证甲的靶子）', () => {
  it('mapPendingRow 逐字段照契约搬，不发明后端没给的东西', () => {
    const mapped = mapPendingRow(pendingRow())
    expect(mapped).toEqual({
      sessionId: 'sess-1',
      requestId: 'req-9f2c',
      traceId: 'tr-1',
      taskId: 'tk-1',
      steps: ['chart'],
      labels: ['📈 生成图表'],
      status: 'awaiting',
      createdAt: '2026-09-23 09:12',
      expiresAt: '2026-09-23 09:42',
    })
  })

  // 标签只有一份字典，长在行组件里：后端给了就照用，没给才按步骤名补，未知值不回显后端原串。
  it('动作名只有一个来源：后端 labels 优先，缺了才补中文，未知步骤不回显原串', () => {
    const withLabels = mapPendingRow(pendingRow({ labels: ['📈 生成图表'], parked_steps: ['chart'] }))
    expect(rowLabels(withLabels)).toEqual(['📈 生成图表'])
    expect(rowLabels(mapPendingRow(pendingRow({ labels: [], parked_steps: ['export'] })))).toEqual(['导出报告'])
    expect(rowLabels(mapPendingRow(pendingRow({ labels: [], parked_steps: ['something_new'] })))).toEqual(['需要确认的一步'])
    expect(rowLabels(mapPendingRow(pendingRow({ labels: [], parked_steps: null })))).toEqual([])
    expect(stepLabel('CHART ')).toBe('生成图表')
    expect(rowFace({})).toBe('idle')
    expect(rowFace({ busy: true })).toBe('busy')
    expect(rowFace({ outcome: { face: 'failed' } })).toBe('failed')
  })

  // 后端复核不过的行会被就地排除：游标必须按「消费掉多少行账本」推进，否则同一笔会列两次。
  it('翻页游标按 limit 推进，不把被复核掉的行再读一遍', async () => {
    const first = []
    for (let n = 0; n < 3; n += 1) first.push(pendingRow({ session_id: 'sess-' + n }))
    http.get.mockResolvedValue({ data: pendingPage(first, { has_more: true }) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    http.get.mockResolvedValue({ data: pendingPage([pendingRow({ session_id: 'sess-3' })]) })
    await bindings.loadMore()
    expect(http.get.mock.calls.map(call => call[1].params.offset)).toEqual([0, PENDING_PAGE_SIZE])
    expect(bindings.rows.value.map(row => row.sessionId)).toEqual(['sess-0', 'sess-1', 'sess-2', 'sess-3'])
    const html = await renderState(HitlPendingPanel, bindings)
    expect(html.match(/data-testid="hitl-row"/g)).toHaveLength(4)
  })

  // 反证甲第一把：谁把空态换成演示行，这一枚先红。
  it('200 空数组就是零行：屏上不出现任何一行待办，也不出现任何 id', async () => {
    http.get.mockResolvedValue({ data: pendingPage([]) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    expect(bindings.rows.value).toEqual([])
    const html = await renderState(HitlPendingPanel, bindings)
    expect(countRows(html)).toBe(0)
    expect(html).not.toContain('sess-1')
    expect(html).not.toContain('data-session=')
  })

  // 反证甲第二把：拿本地历史会话冒充待办 —— 这才是最像"真数据"的假数据。
  it('本地存着三份历史会话也不许被当成待办列出来', async () => {
    sessions.value = [
      { id: 'sess-old-a', messages: [] },
      { id: 'sess-old-b', messages: [] },
      { id: 'sess-old-c', messages: [] },
    ]
    http.get.mockResolvedValue({ data: pendingPage([]) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    expect(bindings.rows.value).toEqual([])
    const html = await renderState(HitlPendingPanel, bindings)
    expect(countRows(html)).toBe(0)
    expect(html).not.toContain('sess-old-a')
  })

  it('读失败时 rows 被清空：失败脸下面不留半张待办表', async () => {
    http.get.mockResolvedValue({ data: pendingPage([pendingRow(), pendingRow({ session_id: 'sess-2' })]) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    expect(countRows(await renderState(HitlPendingPanel, bindings))).toBe(2)

    http.get.mockRejectedValue(httpError(500, 'internal_error'))
    await bindings.loadPending()
    expect(bindings.rows.value).toEqual([])
    const html = await renderState(HitlPendingPanel, bindings)
    expect(countRows(html)).toBe(0)
    expect(html).not.toContain('sess-1')
  })

  it('真有二笔才画二行，行数只可能来自 items', async () => {
    http.get.mockResolvedValue({ data: pendingPage([pendingRow(), pendingRow({ session_id: 'sess-2', parked_steps: ['export'], labels: ['📋 导出报告'] })]) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    const html = await renderState(HitlPendingPanel, bindings)
    expect(countRows(html)).toBe(2)
    expect(html).toContain('sess-1')
    expect(html).toContain('📋 导出报告')
  })

  /** 剥注释后的代码体：说明文字里叙述「不用演示常量」不算使用，只有代码里出现才算。 */
  const codeOnly = name => source(name)
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter(line => !/^\s*(\/\/|\*|\/\*\*?)/.test(line))
    .join('\n')

  it('源码钉：这一屏不引用演示常量，也没有任何写死的行', () => {
    for (const file of ['hitl/HitlPendingPanel.vue', 'hitl/HitlPendingRow.vue']) {
      const s = codeOnly(file)
      expect(s).not.toMatch(/devFixtures|fixtures|DEMO|demoRow/)
      expect(s).not.toMatch(/items\.value\s*=\s*\[\s*\{/)
      expect(s).not.toMatch(/rows\.value\s*=\s*\[\s*\{/)
    }
    // rows 的每一次赋值都要点名：只可能是「空数组」或「本次响应 items 映射出来的行」，没有第三条路。
    const code = codeOnly('hitl/HitlPendingPanel.vue')
    const assigns = code.match(/rows\.value = [^\n]*/g) || []
    expect(assigns).toEqual([
      'rows.value = []',
      'rows.value = append ? rows.value.concat(mapped) : mapped',
      'rows.value = []',
    ])
    // mapped 也只有一条来源：items.map(mapPendingRow)。这里不承认任何第二份行来源。
    expect(code).toContain('const mapped = items.map(mapPendingRow)')
    expect(code.match(/const mapped = /g)).toHaveLength(1)
  })

  it('不摆「待审批 N 条」那种无处可取的数字', async () => {
    http.get.mockResolvedValue({ data: pendingPage([pendingRow()], { count: 1, has_more: true }) })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    const text = (await renderState(HitlPendingPanel, bindings)).replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ')
    expect(text).not.toMatch(/待审批\s*\d+/)
    expect(text).not.toMatch(/审批\s*\d+\s*条/)
    expect(text).not.toMatch(/待办\s*\d+\s*(条|笔)/)
    // has_more 说的是「账本还有行」，这一屏如实这么说。
    expect(text).toContain('账本里还有更早的挂起')
  })
})
