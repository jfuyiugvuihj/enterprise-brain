/**
 * R237 · R40 判据③ —— 前端不再出现 standard 硬编，且消失的方式是「标准由服务端 auto 出」
 *
 * 判据原文（跟进单 §21 表 L511）：「③ 不再出现前端 standard: 500 硬编」。
 * 禁改边界：不改审批动作的权限判定（本件一个字都没动鉴权：submitCheck 里那套
 * isPermissionDenied / denied / retryable="!denied" 原样保留，见丁组反向钉）。
 *
 * 改之前的磁盘事实（上一班在快照 866c2f3 上取证，本件在 a856593 上重新复现）：
 *   frontend/src/devFixtures/approval-demo.js:7 就是那枚 `standard: 500,`；它不只是显示常量 ——
 *   ApprovalPanel.vue 拿它播种表单、把 form.value 整个 POST 给 /approval/precheck，
 *   还在屏上自陈「预审参数（金额 680 / 标准 500 …）来自前端常量」。
 *   判据①②（不传部门也能出结论、传错部门被稳定码拒）由后端三件钉着
 *   （tests/test_approval_precheck_standard_source.py 等），本件一枚都不碰。
 *
 * 为什么「换成另一个名字」或「挪进另一枚常量文件」不算达标：
 *   甲1 把整棵 frontend/src 扫一遍（剥注释、跳过用例），任何 `standard` 后面跟数字都红；
 *   乙组跑真生命周期，取证【发出去的请求体】：不许带 standard 这个键，必须带 auto 口径；
 *   丙2 钉屏上那个数逐字等于响应里的 standard —— 换一个前端常量仍然会红；
 *   丁组反向钉：前端那枚 auto 字符串必须与 app/approval/assistant.py 里的
 *   STANDARD_SOURCE_AUTO 逐字相等（跨语言对表），谁把它改成别的拼写就红。
 *
 * 手法同 r198 / r202 / 本单姊妹件 r237-r49-index-face：本仓没有 jsdom 也不 npm i，
 * 用 createRenderer + 内存虚拟节点跑【真客户端生命周期】（onMounted 那一发预审是真发的），
 * 再把 SFC 自己编译出的 ssrRender 套在活 setupState 上出屏。
 */
import { readFileSync } from 'node:fs'
import { readdirSync } from 'node:fs'
import { dirname, join, relative, sep } from 'node:path'
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
import { http } from '../../lib/http'
import { demoForm } from '../../devFixtures/approval-demo'

const SRC_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const REPO_ROOT = join(SRC_ROOT, '..', '..')
const AUTO = 'auto_from_knowledge_base'

const read = abs => readFileSync(abs, 'utf8').replace(/\r\n/g, '\n')
const panelSource = () => read(join(SRC_ROOT, 'components', 'ApprovalPanel.vue'))
const stripComments = text => text
  .replace(/<!--[\s\S]*?-->/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .split('\n')
  .filter(line => !/^\s*\/\//.test(line))
  .join('\n')

// ==================== 甲1 的探测器：整棵 frontend/src 扫 standard 硬编 ====================

const collectSourceFiles = (dir, out = []) => {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === '__tests__' || entry.name === 'node_modules') continue
      collectSourceFiles(full, out)
    } else if (/\.(js|vue|css)$/.test(entry.name) && !/\.(test|spec)\.js$/.test(entry.name)) {
      out.push(full)
    }
  }
  return out
}

/** 硬编形状：标识符 standard（不带后缀，standard_source / standard_evidence 不算）后面跟数字。 */
const STANDARD_HARDCODE = /\bstandard\b\s*[:=]\s*['"]?-?\d/

const hardcodeHits = (text) => {
  const code = stripComments(text)
  const hits = []
  code.split('\n').forEach((line, index) => {
    if (STANDARD_HARDCODE.test(line)) hits.push(`${index + 1}: ${line.trim().slice(0, 90)}`)
  })
  return hits
}

const rel = full => relative(SRC_ROOT, full).split(sep).join('/')

// ==================== 无 DOM 的真生命周期 + 真模板 ====================

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

/** 真挂一次 /approval 那一屏：onMounted 自己发的那一发预审走的就是产品代码。 */
async function mountPanel(reply) {
  installStorage()
  http.get.mockResolvedValue(PENDING_EMPTY)
  http.post.mockImplementation(async () => reply)
  let instance = null
  const app = createApp({
    __name: 'R237ApprovalHost',
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

const screenHtml = async () => stripTagsOnly(await renderToString(h({
  __name: 'R237ApprovalFace',
  setup: () => live.state,
  ssrRender: ApprovalPanel.ssrRender,
})))
const stripTagsOnly = html => html.replace(/<!--[\s\S]*?-->/g, '')

const byTestId = (html, id) => {
  const out = []
  const re = new RegExp('<(\\w+)([^>]*data-testid="' + id + '"[^>]*)>', 'g')
  let match
  while ((match = re.exec(html))) {
    const tag = match[1]
    const attrs = match[2]
    const end = html.indexOf('</' + tag + '>', re.lastIndex)
    out.push({
      tag,
      attrs,
      text: (end < 0 ? '' : html.slice(re.lastIndex, end)).replace(/<[^>]*>/g, ''),
      attr: name => {
        const hit = new RegExp('(?:^|\\s)' + name + '="([^"]*)"').exec(attrs)
        return hit ? hit[1] : null
      },
    })
  }
  return out
}

afterEach(() => {
  live?.app?.unmount()
  live = null
  http.get.mockReset()
  http.post.mockReset()
})

// ==================== 服务端会回的那些形状（逐字段照抄 precheck_payload） ====================

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
    standard_source: AUTO,
    standard_evidence: ['差旅费报销制度.pdf chunk=3'],
    matched_expense_type: '住宿费',
    requested_by: 'u-1',
    ...over,
  },
})

describe('甲 · 硬编不许回来（探测器先自证会咬）', () => {
  it('甲1 探测器咬得住：把常量改回去的那一行必须被点名', () => {
    const mutant = 'export const demoForm = {\n  amount: 680,\n  standard: 500,\n}'
    expect(hardcodeHits(mutant)).toHaveLength(1)
    expect(hardcodeHits(mutant)[0]).toContain('standard: 500')
    // 换拼写也咬：赋值形状与带引号的数字都算硬编。
    expect(hardcodeHits('form.standard = 500')).toHaveLength(1)
    expect(hardcodeHits("standard: '500'")).toHaveLength(1)
    // 而合法的读响应形状不许误伤。
    expect(hardcodeHits('const label = () => result.value.standard')).toEqual([])
    expect(hardcodeHits('standard_source: STANDARD_SOURCE_AUTO')).toEqual([])
  })

  it('甲2 整棵 frontend/src 零命中：standard 硬编已经从源码里消失', () => {
    const files = collectSourceFiles(SRC_ROOT).sort()
    expect(files.length).toBeGreaterThanOrEqual(30)
    expect(files.map(rel)).toContain('devFixtures/approval-demo.js')
    for (const full of files) {
      expect(hardcodeHits(read(full)), rel(full) + ' 里又出现了 standard 硬编').toEqual([])
    }
  })

  it('甲3 演示常量本身没有 standard / evidence 这两格', () => {
    expect(Object.keys(demoForm)).toEqual(['amount', 'department', 'expense_type'])
    expect(demoForm).not.toHaveProperty('standard')
    expect(demoForm).not.toHaveProperty('evidence')
  })

  it('甲4 屏上那句自陈不再指向已删的常量', () => {
    const panel = panelSource()
    expect(panel).not.toMatch(/标准\s*500/)
    expect(panel).not.toMatch(/金额 680 \/ 标准/)
    expect(panel).toContain('由服务端从知识库检索')
  })
})

describe('乙 · 发出去的请求体：不带 standard，只报 auto 口径', () => {
  it('乙1 onMounted 那一发预审的 body 里没有 standard 键', async () => {
    await mountPanel(precheckReply())
    const calls = http.post.mock.calls.filter(call => call[0] === '/approval/precheck')
    expect(calls).toHaveLength(1)
    const body = calls[0][1]
    expect(Object.keys(body)).not.toContain('standard')
    expect(body.standard_source).toBe(AUTO)
    expect(body.amount).toBe(680)
    expect(body.expense_type).toBe('住宿费')
  })

  it('乙2 用户改了金额也不会有 standard 冒出来（重新自查那一发同样干净）', async () => {
    const state = await mountPanel(precheckReply())
    state.form.amount = 1234
    await state.submitCheck()
    await settle()
    const bodies = http.post.mock.calls.filter(call => call[0] === '/approval/precheck').map(call => call[1])
    expect(bodies).toHaveLength(2)
    for (const body of bodies) {
      expect(Object.keys(body)).not.toContain('standard')
      expect(body.standard_source).toBe(AUTO)
    }
    expect(bodies[1].amount).toBe(1234)
  })

  it('乙3 这一屏仍然只发预审这一发写请求：没有第二套结论、也没有工单端点', async () => {
    await mountPanel(precheckReply())
    const posts = http.post.mock.calls.map(call => String(call[0]))
    expect(posts).toEqual(['/approval/precheck'])
    const code = stripComments(panelSource())
    expect(code.match(/(api|http|axios)\.(get|post|put|patch|delete)\(/g)).toHaveLength(1)
  })
})

describe('丙 · 屏上那个标准只可能来自响应', () => {
  it('丙1 渲染出的标准逐字等于响应里的 standard', async () => {
    await mountPanel(precheckReply({ standard: '450.00' }))
    const html = await screenHtml()
    const cell = byTestId(html, 'approval-standard')
    expect(cell).toHaveLength(1)
    expect(cell[0].text).toBe('标准：450.00')
    // 450.00 这枚数在整棵 frontend/src 里一个字节都没有：它出现在屏上只可能是响应带回来的。
    const elsewhere = collectSourceFiles(SRC_ROOT).filter(full => read(full).includes('450.00'))
    expect(elsewhere.map(rel)).toEqual([])
  })

  it('丙2 服务端换一枚标准，屏上的数跟着换（不是钉死的常量）', async () => {
    await mountPanel(precheckReply({ standard: '720.50', excess_amount: '0.00', excess_ratio: '-0.0549' }))
    expect(byTestId(await screenHtml(), 'approval-standard')[0].text).toBe('标准：720.50')
  })

  it('丙3 标准出处走服务端那一份：屏上标口径，出处列成 chips', async () => {
    await mountPanel(precheckReply({ standard_evidence: ['差旅费报销制度.pdf chunk=3'] }))
    const html = await screenHtml()
    const line = byTestId(html, 'approval-standard-source')
    expect(line).toHaveLength(1)
    expect(line[0].attr('data-standard-source')).toBe(AUTO)
    expect(line[0].text).toContain('服务端从知识库检索')
    const chips = byTestId(html, 'approval-standard-evidence')
    expect(chips).toHaveLength(1)
    expect(chips[0].text).toContain('差旅费报销制度.pdf chunk=3')
  })

  it('丙4 知识库没给出标准：直说未给出，不拿 0 凑一个结论', async () => {
    await mountPanel(precheckReply({
      standard: null, excess_amount: null, excess_ratio: null,
      status: '无法确认', risk_level: 'unknown', standard_evidence: [],
      recommendation: '补充制度标准来源后重新预审',
    }))
    const html = await screenHtml()
    expect(byTestId(html, 'approval-standard')[0].text).toBe('标准：服务端未给出')
    expect(byTestId(html, 'approval-excess')[0].text).toBe('超出：算不出')
    // 关键反证：null 乘一百会算出一枚屏上从未有过的 0.0%，那才是假数字。
    expect(html).not.toMatch(/0\.0%/)
    expect(byTestId(html, 'approval-standard-evidence')).toHaveLength(0)
    expect(html).toContain('无法确认')
  })

  it('丙5 服务端没回口径：这一格不替它编出处', async () => {
    await mountPanel(precheckReply({ standard_source: 'explicit', standard_evidence: [] }))
    const html = await screenHtml()
    const line = byTestId(html, 'approval-standard-source')
    expect(line[0].text).toContain('不替它编出处')
    expect(line[0].attr('data-standard-source')).toBe('explicit')
    // 口径没回就不冒充知识库结论：那一格的标准也一并说「没回口径」。
    expect(byTestId(html, 'approval-standard')[0].text).toBe('标准：服务端没回取用口径')
    // 只钉那句【结论旁的口径句】：说明区的演示句在两种口径下都在，不算冒充。
    expect(html).not.toContain('上面的标准是服务端从知识库检索出来的那一个数')
  })
})

describe('丁 · 边界不许越：口径拼写对表后端，权限判定一字未动', () => {
  it('丁1 前端那枚 auto 字符串与 app/approval/assistant.py 逐字相等', () => {
    const backend = read(join(REPO_ROOT, 'app', 'approval', 'assistant.py'))
    const declared = /STANDARD_SOURCE_AUTO\s*=\s*"([^"]+)"/.exec(backend)
    expect(declared, '后端 STANDARD_SOURCE_AUTO 读不到了').toBeTruthy()
    expect(declared[1]).toBe(AUTO)
    // 界面里的那一枚也必须同一拼写，不许自造别名。
    expect(panelSource()).toContain(`const STANDARD_SOURCE_AUTO = '${AUTO}'`)
  })

  it('丁2 权限判定原样保留：403 仍走 isPermissionDenied，不给重试', async () => {
    const denied = Object.assign(new Error('Request failed with status code 403'), {
      isAxiosError: true,
      config: { url: '/approval/precheck' },
      response: { status: 403, data: { detail: 'department_override_denied' } },
    })
    await mountPanel(Promise.reject(denied))
    const html = await screenHtml()
    expect(html).toContain('没有权限做审批预审')
    expect(html).not.toContain('等待分析')
    const code = stripComments(panelSource())
    expect(code).toContain('isPermissionDenied(err)')
    expect(code).toMatch(/:retryable="!denied"/)
    expect(code).toContain('onMounted(submitCheck)')
  })

  it('丁3 演示这块仍挂牌：徽标与 data-demo 一处不少', async () => {
    await mountPanel(precheckReply())
    const html = await screenHtml()
    expect(html).toContain('data-demo="fixtures"')
    expect(html).toContain('演示数据')
    expect(html).toContain('上方那一屏挂起待办读的是服务端真账本')
  })

  it('丁4 自查那一格仍然不办理审批：整屏一个按钮', async () => {
    await mountPanel(precheckReply())
    const html = await screenHtml()
    const labels = [...html.matchAll(/<button[^>]*>([\s\S]*?)<\/button>/g)].map(m => m[1].replace(/<[^>]*>/g, '').trim())
    expect(labels).toEqual(['重新自查'])
  })
})