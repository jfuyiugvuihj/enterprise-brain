/**
 * R247 · 审批预审这一屏的两件事：重复挂载不许重打知识库 / 失败那张脸必须诚实
 *
 * 判据原文（§98.2）：ApprovalPanel 的 onMounted(submitCheck) 每次挂载都真发一发预审，
 * 而那一发在背后是 resolve_standard_from_knowledge_base 的一次知识库检索 —— 员工在面板间
 * 来回切（Vue 反复 unmount/mount）时，切一次就打一次。靶是【重复挂载】与【失败那张脸】，
 * 不是「要不要自动查」：字面量 onMounted(submitCheck) 必须原样留着（panel-states.test.js:221
 * 那枚现状钉锁的就是「挂载会发请求」这件事本身），本件一个字都没动它。
 *
 * 环境同 r237-r40-standard-auto.test.js：node + createRenderer 内存虚拟节点
 * （本仓没有 jsdom / @vue/test-utils，也不许 npm i）。与 r247 唯一的手法差是：
 * 这里要在【同一枚 app】里把面板拆掉再装回去 —— 一次页面会话里的两次挂载，
 * 显式生命周期跑两次 onMounted，那一发预审到底发没发，取证在【请求桩的调用次数】上。
 *
 * 三枚反证钉各自咬什么（摘掉守卫必红，逐枚写在名字里）：
 *   甲 复用被摘掉 ⇒ 第二次挂载又打知识库 ⇒ precheckCalls 从 1 变 2 就红；
 *   乙 force 那一腿被摘掉（按钮回到 submitCheck / 缓存不认 force）⇒ 点「重新自查」不再重发
 *      或取数时间不刷新 ⇒ 调用次数或 09:06 那一句就红；
 *   丙 后端 503 被画回「等待分析」（或画成通用失败那张脸）⇒ 那四个字重新上屏就红。
 */
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, getCurrentInstance, h, nextTick, reactive, ref } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { routeLocationKey, routerKey } from 'vue-router'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() }, authedFetch: vi.fn() }
})

import ApprovalPanel from '../ApprovalPanel.vue'
import { http } from '../../lib/http'
import { errorCodeOf } from '../../lib/errcodes'

const read = () => readFileSync(new URL('../ApprovalPanel.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const codeOnly = text => text
  .replace(/<!--[\s\S]*?-->/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .split('\n')
  .filter(line => !/^\s*\/\//.test(line))
  .join('\n')

// ==================== 无 DOM 的真生命周期（同一枚 app 里可以拆了再装） ====================

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
const SSR_CONTEXT_KEY = Symbol.for('v-scx')

/** 内存 localStorage 替身（node 没有）：HitlPendingPanel 经 lib/sessions 要读它。 */
function installStorage() {
  const store = new Map()
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

const PENDING_EMPTY = {
  data: {
    items: [], count: 0, limit: 20, offset: 0, has_more: false,
    failed_turns: [], failed_turns_has_more: false,
  },
}

/** 服务端会回的那些形状（逐字段照抄 precheck_payload）：屏上那个标准只可能来自这里。 */
const precheckReply = (over = {}) => ({
  data: {
    department: '市场部',
    expense_type: '住宿费',
    amount: '680',
    standard: '450.00',
    currency: 'CNY',
    excess_amount: '230.00',
    excess_ratio: '1.0444',
    risk_level: 'high',
    status: '需人工审批',
    approved: false,
    recommendation: '提交部门负责人及财务复核',
    evidence: ['差旅费报销制度.pdf chunk=3'],
    standard_source: 'auto_from_knowledge_base',
    standard_evidence: ['差旅费报销制度.pdf chunk=3'],
    matched_expense_type: '住宿费',
    requested_by: 'u-1',
    ...over,
  },
})

/** 后端的两种失败形状：503 是「知识库取不到标准」（app/api/v1/intelligence.py），403 是没权限。 */
const httpError = (status, code) => Object.assign(
  new Error('Request failed with status code ' + status),
  {
    isAxiosError: true,
    config: { url: '/approval/precheck' },
    response: { status, data: { detail: { code, message: 'the policy standard could not be retrieved' } } },
  },
)
const networkError = () => Object.assign(new Error('Network Error'), {
  isAxiosError: true,
  code: 'ERR_NETWORK',
  config: { url: '/approval/precheck' },
})

let session = null

async function settle() {
  await nextTick()
  await nextTick()
  await nextTick()
}

/** 挂一次 /approval 那一屏：onMounted 自己发的那一发预审走的就是产品代码。 */
async function open(reply) {
  installStorage()
  http.get.mockResolvedValue(PENDING_EMPTY)
  http.post.mockImplementation(async () => reply)
  const instances = []
  const shown = ref(true)
  const Face = {
    __name: 'R247ApprovalFace',
    setup: ApprovalPanel.setup,
    render() {
      instances.push(getCurrentInstance())
      return h('div', { 'data-testid': 'approval-panel' })
    },
  }
  const app = createApp({
    __name: 'R247ApprovalHost',
    setup: () => ({ shown }),
    render() { return shown.value ? h(Face) : h('div') },
  })
  app.config.warnHandler = () => {}
  app.provide(SSR_CONTEXT_KEY, {})
  app.provide(routeLocationKey, reactive({ name: 'approval', path: '/approval', query: {}, params: {}, meta: {}, fullPath: '/approval', hash: '' }))
  app.provide(routerKey, { push: () => Promise.resolve(), replace: () => Promise.resolve() })
  app.mount(node('#root'))
  await settle()
  session = { app, instances, shown }
  return session
}

/** 员工切走再切回：同一枚 app 里把面板 unmount 掉再 mount 一次（Vue 的 v-if 语义）。 */
async function remount(s = session) {
  s.shown.value = false
  await nextTick()
  s.shown.value = true
  await settle()
  return s
}

const state = (s = session) => s.instances[s.instances.length - 1].setupState
const stripTagsOnly = html => html.replace(/<!--[\s\S]*?-->/g, '')
/** 屏上现在画着的那张脸：把活 setupState 套回 SFC 自己编译的 ssrRender。 */
const faceHtml = async (s = session) => stripTagsOnly(await renderToString(h({
  __name: 'R247ApprovalScreen',
  setup: () => state(s),
  ssrRender: ApprovalPanel.ssrRender,
})))
const precheckCalls = () => http.post.mock.calls.filter(call => call[0] === '/approval/precheck')
const byTestId = (html, id) => {
  const out = []
  const re = new RegExp('<(\\w+)([^>]*data-testid="' + id + '"[^>]*)>', 'g')
  let match
  while ((match = re.exec(html))) {
    const tag = match[1]
    const end = html.indexOf('</' + tag + '>', re.lastIndex)
    out.push({ tag, text: (end < 0 ? '' : html.slice(re.lastIndex, end)).replace(/<[^>]*>/g, '') })
  }
  return out
}

beforeEach(() => {
  vi.useFakeTimers({ now: new Date(2026, 8, 25, 9, 0, 0) })
})

afterEach(() => {
  session?.app?.unmount()
  session = null
  http.get.mockReset()
  http.post.mockReset()
  vi.useRealTimers()
})

// ==================== 判据①：重复挂载复用上次读数 ====================

describe('R247① · 切走再切回不许重打知识库（靶是重复挂载，不是要不要自动查）', () => {
  it('反证钉甲：同一枚 app 里拆掉再装回 ⇒ 预审只真发一次；复用一摘掉就红', async () => {
    await open(precheckReply())
    expect(precheckCalls()).toHaveLength(1)
    await remount()
    expect(precheckCalls(), '第二次挂载又去打了知识库：来回切一次就打一次检索').toHaveLength(1)
    const html = await faceHtml()
    expect(html).toContain('上次自查留下的读数')
    expect(html).toContain('切回这一屏没有重新问知识库')
    expect(html).toContain('取于 09:00')
    // 复用的是同一枚读数：屏上那个标准仍然逐字来自第一发的响应
    const cell = byTestId(html, 'approval-standard')
    expect(cell).toHaveLength(1)
    expect(cell[0].text).toBe('标准：450.00')
  })

  it('反证钉乙：显式「重新自查」必须真重发并刷新取数时间；force 那一腿摘掉就红', async () => {
    await open(precheckReply())
    await remount()
    expect(precheckCalls()).toHaveLength(1)
    // 本仓没有 jsdom，点不了真鼠标：接线钉在源码上（这一枚按钮绑的就是 submitCheck(true)），
    // 行为钉在同一句表达式上。把模板改回 @click="submitCheck" 或把 force 判据摘掉都会红。
    expect(read()).toMatch(/data-testid="run-approval"[^\n]*@click="submitCheck\(true\)"/)
    vi.setSystemTime(new Date(2026, 8, 25, 9, 6, 0))
    await state().submitCheck(true)
    await settle()
    expect(precheckCalls(), '点了「重新自查」却没重发：缓存把显式动作也吞了').toHaveLength(2)
    const html = await faceHtml()
    expect(html).toContain('取于 09:06')
    expect(html).toContain('刚查出来的读数')
    expect(precheckCalls()[1][1]).toMatchObject({ amount: 680, standard_source: 'auto_from_knowledge_base' })
  })

  it('复用只认同一组参数：改了金额那一发是新问题，不许端上次的读数', async () => {
    await open(precheckReply())
    const st = state()
    st.form.amount = 1234
    await st.submitCheck()
    await settle()
    expect(precheckCalls()).toHaveLength(2)
    expect(precheckCalls()[1][1].amount).toBe(1234)
  })

  it('失败不进缓存：两次挂载都取不到 ⇒ 仍然真发两次（没有读数可复用）', async () => {
    await open(Promise.reject(httpError(503, 'retrieval_unavailable')))
    expect(precheckCalls()).toHaveLength(1)
    await remount()
    expect(precheckCalls()).toHaveLength(2)
  })
})

// ==================== 判据②：失败那张脸必须诚实（四张脸分开） ====================

// R277 记账：这一屏今天有【第五张脸】——「部门那一格填的不是你的部门」（后端
// department_override_denied 经 R270 字典出口不再顶「没有权限」）。它由 r277-approval-selfcheck-truth
// 与 r237 丁2 钉着，本件的这四张脸一字未动：判据②要防的「失败冒充空态」与那张新脸是两件事。
describe('R247② · 成功 / 降级 / 错误 / 无权限四张脸两两不同，且都不说「等待分析」', () => {
  it('反证钉丙：桩一发 503（知识库取不到标准）⇒ 「等待分析」四个字不许再上屏', async () => {
    const err = httpError(503, 'retrieval_unavailable')
    // 先自证这枚桩打的就是后端那一发的形状，否则下面那张脸是白测的
    expect(errorCodeOf(err), '这枚桩没落进 canonical 码：降级那张脸根本不会被触发').toBe('retrieval_unavailable')
    await open(Promise.reject(err))
    const html = await faceHtml()
    expect(html).not.toContain('等待分析')
    expect(html).toContain('data-testid="ui-error-state"')
    expect(html).toContain('知识库取不到报销标准')
    expect(html).toContain('说不出超没超标')
    expect(html).toContain('是此刻取不到')
    // 降级仍然给重试：知识库恢复了这一点就变得了（与无权限那张脸相反）
    expect(html).toContain('重新预审')
  })

  it('真失败是另一张脸：网络断了说「预审没有跑完」，不与降级共用一句话', async () => {
    await open(Promise.reject(networkError()))
    const html = await faceHtml()
    expect(html).not.toContain('等待分析')
    expect(html).toContain('data-testid="ui-error-state"')
    expect(html).toContain('预审没有跑完')
    expect(html).not.toContain('知识库取不到报销标准')
    expect(html).toContain('重新预审')
  })

  it('无权限是第三张脸：说没权限，且不给「重新预审」那颗按钮', async () => {
    await open(Promise.reject(httpError(403, 'permission_denied')))
    const html = await faceHtml()
    expect(html).not.toContain('等待分析')
    expect(html).toContain('没有权限做审批预审')
    expect(html).not.toContain('重新预审')
    expect(html).not.toContain('知识库取不到报销标准')
  })

  it('成功那张脸自己说清数是从哪儿来的，缓存命中时不装作刚查的', async () => {
    await open(precheckReply())
    const first = await faceHtml()
    expect(first).toContain('刚查出来的读数')
    expect(first).toContain('服务端从知识库检索')
    expect(first).not.toContain('上次自查留下的读数')
    await remount()
    const second = await faceHtml()
    expect(second).toContain('上次自查留下的读数')
    expect(second).not.toContain('刚查出来的读数')
  })

  it('第四张脸仍是首屏那张空：SSR 首屏留着「等待分析」，失败时它一定不在', async () => {
    const html = await renderToString(h(ApprovalPanel))
    expect(stripTagsOnly(html)).toContain('等待分析')
    expect(html).toContain('data-testid="ui-empty-state"')
  })
})

// ==================== 判据④的两条硬约束（本件自己咬） ====================

describe('R247④ · 字面量与硬约束：现状钉不动、色值不新增、运行时零外网', () => {
  it('现状钉原样：onMounted(submitCheck) 还在，且这一屏仍只发一发请求', () => {
    expect(read()).toContain('onMounted(submitCheck)')
    const code = codeOnly(read())
    expect(code.match(/(api|http|axios)\.(get|post|put|patch|delete)\(/g)).toHaveLength(1)
    expect(code).toContain("api.post('/approval/precheck'")
  })

  it('组件里不许新增裸色值：这条 <style> 里裸 hex/rgba 的条数只准停在原有那一档', () => {
    const style = /<style scoped>([\s\S]*?)<\/style>/.exec(read())[1]
    const bare = style.match(/#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(/g) || []
    // 原有的一档欠账在 .recommendation 的 background（stylelint 棘轮 148 条里的同一条）；
    // 新增任何一枚裸色值都会把这条咬红。新色值的唯一去路是 src/assets/theme.css。
    expect(bare.length).toBeLessThanOrEqual(1)
  })

  it('运行时零外部请求：这一枚文件里不许出现任何 http(s) 资源、字体 CDN', () => {
    expect(read()).not.toMatch(/https?:\/\//)
    expect(read()).not.toMatch(/fonts\.googleapis|gstatic|cdn\./i)
  })
})
