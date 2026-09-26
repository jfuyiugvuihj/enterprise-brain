/**
 * R277 · 前端块 B「自查归真」的钉：G09 部门格归真 · 部门被拒那张脸 · G13/G18 屏面干净
 *
 * 派工词与本件的对应关系（判据①②之一④⑤，逐条有钉，摘钉即红）：
 *   ① 换一个非市场部的 staff 账号进这一屏，屏上不许再出现「没有权限做审批预审」。
 *      做法＝部门格默认只可能是「登录账号自己的部门」或「空着由服务端补」（后端
 *      app/common/authorization.py::verify_department_self_report 放行这两条）。
 *      🔴 R237 定的「挂载即自动预审」是行为契约，本件反过来钉住【归真没有把它绕掉】：
 *      部门空着也照样真发那一发（①-3）。
 *   ②之一 部门被拒那一发画的是字典那句人话（R270 的出口），不再一律顶「没有权限」；
 *      同时钉住真无权限那张脸【没被顺手洗掉】——两枚钉一起，改回任何一边都红。
 *   ④ 屏面上再无源码路径与路由名（G13 那两处），面板头不写死数字与演示常量（G18）。
 *   ⑤ 部门类的句子一律出自字典，界面不替后端挑因由（app/agents/tools.py 把 policy 的
 *      department_scope_denied 折成 department_scope_required，同一枚码两种因由）。
 *
 * 手法沿用本件姊妹件 r237：本仓没有 jsdom 也不 npm i，用 createRenderer + 内存虚拟节点
 * 跑真客户端生命周期（onMounted 那一发预审是真发的），再把 SFC 编译出的 ssrRender 套在
 * 活 setupState 上出屏 —— 于是「格子里是什么」与「发出去的是什么」都是产品代码的结果。
 */
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, getCurrentInstance, h, nextTick, reactive } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { routeLocationKey, routerKey } from 'vue-router'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() }, authedFetch: vi.fn() }
})

import ApprovalPanel from '../ApprovalPanel.vue'
import { DEPARTMENT_KEY, http } from '../../lib/http'

const MYSELF = '研发部'
const DEMO_DEPARTMENT = '市场部'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const panelSource = () => read('../../components/ApprovalPanel.vue')
const demoSource = () => read('../../devFixtures/approval-demo.js')
const stripComments = text => text
  .replace(/<!--[\s\S]*?-->/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .split('\n')
  .filter(line => !/^\s*\/\//.test(line))
  .join('\n')

// ==================== 探测器：部门被写回字面量 ⇒ 咬 ====================

/** department 后面跟一枚【非空】引号串 = 界面又替员工填了一个部门。空串放行（那是留给服务端补的那条路）。 */
const DEPARTMENT_LITERAL = /department\s*[:=]\s*['"`][^'"`\s][^'"`]*['"`]/g

const departmentLiteralHits = text => stripComments(text)
  .split('\n')
  .map((line, index) => [index + 1, line])
  .filter(([, line]) => { DEPARTMENT_LITERAL.lastIndex = 0; return DEPARTMENT_LITERAL.test(line) })
  .map(([line, text]) => line + ': ' + text.trim().slice(0, 90))

// ==================== 无 DOM 的真生命周期 + 真模板（同 r237） ====================

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

/** 内存 localStorage 替身（node 没有）；每次挂载换一份，免得上一枚测试的部门漏到下一枚。 */
function installStorage(seed = {}) {
  const store = new Map(Object.entries(seed))
  globalThis.window = globalThis.window || { addEventListener() {}, removeEventListener() {} }
  globalThis.document = globalThis.document || { visibilityState: 'visible', addEventListener() {}, removeEventListener() {} }
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

let live = null

const PENDING_EMPTY = {
  data: {
    items: [], count: 0, limit: 20, offset: 0, has_more: false,
    failed_turns: [], failed_turns_has_more: false,
  },
}

async function settle() {
  await nextTick()
  await nextTick()
  await nextTick()
}

/** 真挂一次这一屏：storedDepartment 就是登录响应里那枚部门（undefined = 账号压根没登记）。 */
async function mountPanel(reply, storedDepartment) {
  installStorage(storedDepartment === undefined ? {} : { [DEPARTMENT_KEY]: storedDepartment })
  http.get.mockResolvedValue(PENDING_EMPTY)
  http.post.mockImplementation(async () => reply)
  let instance = null
  const app = createApp({
    __name: 'R277ApprovalHost',
    setup: ApprovalPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div')
    },
  })
  app.config.warnHandler = () => {}
  app.provide(SSR_CONTEXT_KEY, {})
  app.provide(routeLocationKey, reactive({ name: 'approval', path: '/approval', query: {}, params: {}, meta: {}, fullPath: '/approval', hash: '' }))
  app.provide(routerKey, { push: () => Promise.resolve(), replace: () => Promise.resolve() })
  app.mount(node('#root'))
  await settle()
  live = { app, state: instance.setupState }
  return live.state
}

const screenHtml = async () => (await renderToString(h({
  __name: 'R277ApprovalFace',
  setup: () => live.state,
  ssrRender: ApprovalPanel.ssrRender,
}))).replace(/<!--[\s\S]*?-->/g, '')

/** 屏面上给人看的正文：剥掉标签，只留员工真会读到的字。 */
const visibleText = html => html.replace(/<[^>]*>/g, ' ')

const precheckCalls = () => http.post.mock.calls.filter(call => call[0] === '/approval/precheck')

/** 后端真发的两种形状：detail 是裸串 / detail 是 {code, message}（authorization.py 今天发后者）。 */
const wire403 = detail => Object.assign(new Error('Request failed with status code 403'), {
  isAxiosError: true,
  config: { url: '/approval/precheck' },
  response: { status: 403, data: { detail } },
})
const departmentDenied = () => wire403({
  code: 'department_override_denied',
  message: 'department must match the authenticated principal',
})
const degraded503 = () => Object.assign(new Error('Request failed with status code 503'), {
  isAxiosError: true,
  config: { url: '/approval/precheck' },
  response: { status: 503, data: { detail: { code: 'retrieval_unavailable', message: 'the policy standard could not be retrieved' } } },
})
const okReply = (over = {}) => ({
  data: {
    department: MYSELF, expense_type: '住宿费', amount: '5000', standard: '450.00', currency: 'CNY',
    excess_amount: '230.00', excess_ratio: '1.0444', risk_level: 'high', status: '需人工审批',
    approved: false, recommendation: '提交部门负责人及财务复核', evidence: [],
    standard_source: 'auto_from_knowledge_base', standard_evidence: [], matched_expense_type: '住宿费',
    requested_by: 'u-1', ...over,
  },
})

afterEach(() => {
  live?.app?.unmount()
  live = null
  http.get.mockReset()
  http.post.mockReset()
})

// ==================== 判据① · 部门格只可能是本人部门或空 ====================

describe('R277① · 部门那一格不再替员工填别人的部门', () => {
  it('①-0 探测器先自证会咬：写回一枚字面量部门必须被点名', () => {
    expect(departmentLiteralHits("const form = ref({ ...demoForm, department: '市场部' })")).toHaveLength(1)
    expect(departmentLiteralHits("payload.department = '研发部'")).toHaveLength(1)
    // 合法形状不误伤：从账号取、以及「留空由服务端补」那条路。
    expect(departmentLiteralHits('const form = ref({ ...demoForm, department: ownDepartment() })')).toEqual([])
    expect(departmentLiteralHits("department: ''")).toEqual([])
  })

  it('①-1 面板与演示常量里再无一枚字面量部门，也没有那个演示部门名', () => {
    expect(departmentLiteralHits(panelSource()), '部门只能来自登录账号').toEqual([])
    expect(departmentLiteralHits(demoSource())).toEqual([])
    for (const [name, text] of [['ApprovalPanel.vue', panelSource()], ['approval-demo.js', demoSource()]]) {
      expect(stripComments(text), name + ' 里又出现了那枚演示部门名').not.toContain(DEMO_DEPARTMENT)
    }
  })

  it('①-2 账号登记了部门（非市场部）⇒ 格子里是本人的部门，发出去的也是它', async () => {
    const state = await mountPanel(okReply(), MYSELF)
    expect(state.form.department).toBe(MYSELF)
    const body = precheckCalls()[0][1]
    expect(body.department).toBe(MYSELF)
    expect(await screenHtml()).toContain('value="' + MYSELF + '"')
  })

  it('①-3 🔴 归真不是靠取消自动预审：部门空着也照样真发那一发，且整屏只有这一发写请求', async () => {
    const state = await mountPanel(okReply())
    expect(state.form.department).toBe('')
    const calls = precheckCalls()
    expect(calls, '挂载即自动预审是 R237 的行为契约，不许用「不发了」躲开 G09').toHaveLength(1)
    expect(calls[0][1].department, '留空 = 交给服务端按账号补，界面不许猜一枚部门').toBe('')
    expect(http.post.mock.calls.map(call => String(call[0]))).toEqual(['/approval/precheck'])
    expect(await screenHtml()).not.toContain('value="' + DEMO_DEPARTMENT + '"')
  })
})

// ==================== 判据②之一 · 那张脸画的是真话，而旧脸没被洗掉 ====================

describe('R277②之一 · 部门被拒不顶「没有权限」，真无权限那张脸仍在', () => {
  it('②之一-1 后端真发的形状（信封带英文 message）：标题与句子说的都是部门这一格', async () => {
    await mountPanel(Promise.reject(departmentDenied()))
    const html = await screenHtml()
    expect(html).toContain('部门那一格填的不是你的部门')
    expect(html).toContain('请求里写的部门不是你这个账号所属的部门')
    expect(html).not.toContain('没有权限做审批预审')
    expect(html).not.toContain('预审没有跑完')
    expect(html, '后端英文原句不许当人话上屏').not.toContain('department must match')
  })

  it('②之一-2 真无权限那张脸没被洗掉：permission_denied 仍说没权限，仍不给重试', async () => {
    // 真无权限那一发今天走的也是裸串形状（app/api/v1/intelligence.py::_authorized 把 policy 的
    // reason_code 原样塞进 detail），所以这一枚桩照形状 1 打。
    await mountPanel(Promise.reject(wire403('permission_denied')))
    const html = await screenHtml()
    expect(html).toContain('没有权限做审批预审')
    expect(html).not.toContain('部门那一格填的不是你的部门')
    expect(html).toContain('当前账号没有这项权限')
    expect(html, '没权限那一发点重试不会变，这颗按钮不该在').not.toContain('重新预审')
  })

  it('②之一-3 降级仍是第三张脸：不与上面两张共用一句话', async () => {
    await mountPanel(Promise.reject(degraded503()))
    const html = await screenHtml()
    expect(html).toContain('知识库取不到报销标准')
    expect(html).not.toContain('部门那一格填的不是你的部门')
    expect(html).not.toContain('没有权限做审批预审')
  })
})

// ==================== 判据④ · G13 两处与 G18 头 ====================

describe('R277④ · 屏面上再无源码路径、路由名、英文装饰字与写死的演示数字', () => {
  it('④-1 首屏正文里找不到 src/ 路径与 HTTP 路由（G13 那两处）', async () => {
    await mountPanel(okReply(), MYSELF)
    const text = visibleText(await screenHtml())
    expect(text).not.toMatch(/src\/[A-Za-z0-9_./-]+/)
    expect(text).not.toMatch(/(GET|POST|PUT|PATCH|DELETE) \//)
    expect(text).not.toContain('/hitl/pending')
    expect(text, '人话句里不许夹裸码名').not.toMatch(/\b[a-z][a-z0-9]*_[a-z0-9]+\b/)
    // 反向自证这条扫描有正文可读：那句诚实话必须在屏上。
    expect(text).toContain('填的是你这个账号在系统里登记的部门')
    expect(text).toContain('演示数据')
  })

  it('④-2 面板头不再挂那枚英文装饰字（G18），屏名仍与 meta.title 同源', async () => {
    await mountPanel(okReply(), MYSELF)
    const html = await screenHtml()
    expect(html, '屏头那格若还挂着纯拉丁字母，就是员工读到半中半英（G18）').not.toMatch(/class="eyebrow"[^>]*>[A-Za-z .-]+<\//)
    expect(html).not.toMatch(/class="eyebrow"[^>]*>\s*Approval\s*</)
    expect(html).toContain('审批与待办')
  })

  it('④-3 🔴 反证钉：披露句里那两枚数是表单真值，不是写死的常量', async () => {
    const state = await mountPanel(okReply(), MYSELF)
    state.form.amount = 987654
    state.form.expense_type = '市内交通'
    const text = visibleText(await screenHtml())
    expect(text).toContain('987654')
    expect(text).toContain('市内交通')
    expect(text, '屏上那行「初始值是多少」还照着常量报，就是与表单各说各的').not.toContain('680')
  })

  it('④-4 归真后的 approval-demo.js 只剩自查计算器那两格输入，文件保留（F4 裁定）', () => {
    expect(existsSync(new URL('../../devFixtures/approval-demo.js', import.meta.url))).toBe(true)
    const source = demoSource()
    expect(source).toContain('上线前必须清空')
    expect(departmentLiteralHits(source)).toEqual([])
    const keys = /export const demoForm = \{([\s\S]*?)\n\}/.exec(source)
    expect(keys, 'demoForm 不再是纯字面量，甲3 那枚钉会先红').toBeTruthy()
    expect(keys[1].split('\n').map(line => line.trim()).filter(Boolean).map(line => line.split(':')[0]).sort())
      .toEqual(['amount', 'expense_type'])
  })
})

// ==================== 判据②之二 · 死控件清零：按钮的有无交给字典 ====================

describe('R277②之二 · 「重新预审」不再跟着 !denied 摆，改吃字典那枚 retryable', () => {
  it('②之二-1 部门被拒那一发：字典判不可重发 ⇒ 这颗按钮不许在（改回 !denied 即红）', async () => {
    // 这一枚就是 G20 要清的那一族：denied 为假（它不是没权限），于是旧写法照样把按钮摆了出来，
    // 而按下去发出去的是同一枚必被拒的请求。字典早就是 retryable:false（errcodes.js:236）。
    await mountPanel(Promise.reject(departmentDenied()))
    const html = await screenHtml()
    expect(html).toContain('部门那一格填的不是你的部门')
    expect(html, '原样重发必然再被拒，这颗按钮就是一次注定失败的邀请').not.toContain('重新预审')
    expect(html).not.toContain('ui-error-retry')
  })

  it('②之二-2 反向自证：字典判可重发那一发（知识库此刻取不到）按钮照旧在 ⇒ 不是把钮一律摘掉', async () => {
    await mountPanel(Promise.reject(degraded503()))
    const html = await screenHtml()
    expect(html).toContain('知识库取不到报销标准')
    expect(html, '降级是「此刻取不到，稍后再取」，这颗按钮是真有救的').toContain('重新预审')
  })

  it('②之二-3 🔴 源码形状钉：绑定与赋值两头都钉住，写回 !denied 或不问字典都红', () => {
    const s = panelSource()
    expect(s).toContain("failureRetryable.value = isRetryable(err)")
    expect(s).toMatch(/:retryable="failureRetryable"/)
    expect(s).not.toMatch(/:retryable="!denied"/)
  })
})
