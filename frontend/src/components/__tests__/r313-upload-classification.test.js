/**
 * R313 · 格一 —— 上传时问一句密级，而且这一枚值真发得出去
 *
 * 病灶（行号在基点 217d542 现取）：DocPanel 的上传表单只有 form.append('file', file) 这一枚
 * append，而 POST /api/v1/upload 的签名（app/api/v1/chat.py:3932-3935）明写着
 * classification: int = Form(1) —— 也就是说**从来没有一个人被问过密级**，整库默认 1 级。
 *
 * 三条判据各自怎么钉：
 *   ① 表单给出选择并把值真发出去 —— 走真实的 uploadSingleFile，抓 http.post 收到的那一份
 *      FormData 本身（不是抓一个测试自己拼的对象）：键集合、值、顺序三样都判。
 *   ② 🔴 默认值 == 后端那个 Form(1) —— 不抄快照，去后端源码里把那一句现读出来对数：
 *      谁改了后端默认而界面没跟着改，这一枚当场红。同时钉「用户不动选择框 ⇒ 发出去的就是 1」，
 *      这一发的请求结果与今天逐字节相同（今天压根不发这一枚字段，FastAPI 用 Form 默认补 1）。
 *   ③ 🔴 前端一律不许发 department —— chat.py 的 docstring 写明了理由（检索按来问的人的部门匹配，
 *      客户端能挑就等于允许往别人的结果里投稿），所以 FormData 的键集合里一枚 department 都不许出现。
 *
 * 手法沿用 r237-r49 / r288：本仓没有 jsdom、也不 npm i。createRenderer + 内存虚拟节点挂 DocPanel
 * 自己编译出的 setup（onMounted → loadDocs 走产品那一遍），再把 SFC 那份 ssrRender 套在活
 * setupState 上出 HTML —— 判的是真模板产物，不是源码字符串。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, getCurrentInstance, h, nextTick } from 'vue'
import { renderToString } from '@vue/server-renderer'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() }, authedFetch: vi.fn() }
})

vi.mock('../../lib/artifacts', () => ({
  isArtifactRequest: src => Boolean(src) && String(src).startsWith('artifact:'),
  fetchArtifactBlob: () => new Promise(() => {}),
}))

import DocPanel, {
  DEFAULT_UPLOAD_CLASSIFICATION,
  UPLOAD_CLASSIFICATION_LEVELS,
  normalizeClassification,
} from '../DocPanel.vue'
import { http } from '../../lib/http'

// ==================== 无 DOM 的真生命周期 + 真模板 ====================

function vnode(tag) {
  return { tag, props: {}, children: [], parent: null, text: '' }
}
const parentOf = target => target.parent

const nodeOps = {
  createElement: tag => vnode(tag),
  createText: text => Object.assign(vnode('#text'), { text }),
  createComment: text => Object.assign(vnode('#comment'), { text }),
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
    const parent = parentOf(target)
    if (parent) {
      parent.children.splice(parent.children.indexOf(target), 1)
      target.parent = null
    }
  },
  patchProp: (el, key, _prev, next) => {
    if (next === null || next === undefined) delete el.props[key]
    else el.props[key] = next
  },
  cloneNode: original => Object.assign(vnode(original.tag), { props: { ...original.props }, text: original.text }),
  insertStaticContent: () => [vnode('#static'), vnode('#static')],
  querySelector: () => null,
  setScopeId: () => {},
}

const { createApp } = createRenderer(nodeOps)
const SSR_CONTEXT_KEY = Symbol.for('v-scx')
let live = null

function mountPanel(props = {}) {
  http.get.mockImplementation(async (url) => (
    String(url).endsWith('/documents/catalog')
      ? { data: { documents: [{ filename: '制度汇编.pdf', owner_id: 'u-1', size_bytes: 2048, parse_status: 'ready', index_status: 'indexed' }] } }
      : { data: {} }
  ))
  http.post.mockImplementation(async () => ({
    data: { status: 'ok', message: '已收录', filename: '制度汇编.pdf' },
  }))
  let instance = null
  const app = createApp({
    __name: 'R313ClassificationHost',
    props: DocPanel.props,
    setup: DocPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div')
    },
  }, props)
  app.config.warnHandler = () => {}
  app.provide(SSR_CONTEXT_KEY, {})
  app.mount(vnode('#root'))
  live = { app, state: instance.setupState }
  return live.state
}

// 模板注释不上屏（r288 同款剥法）：不先剥掉，注释里那句「用原生 <select>」会把 stripTags 的
// 正则带偏，测试读到的是注释而不是屏上的字。
const stripComments = html => html.replace(/<!--[\s\S]*?-->/g, '')
const stripTags = html => html.replace(/<[^>]*>/g, '')
const plainText = html => stripTags(stripComments(html))
const faceRender = name => renderToString(h({
  __name: name,
  setup: () => live.state,
  ssrRender: DocPanel.ssrRender,
}))
const screen = async () => plainText(await faceRender('R313ClassificationFace'))
const screenHtml = async () => faceRender('R313ClassificationHtml')

async function settle() {
  await nextTick()
  await nextTick()
}

/** 抓 http.post 实际收到的那一份 FormData：键与值按出现顺序列出来，判的是发出去的东西本身。 */
function postedForm(atCall = 0) {
  const call = http.post.mock.calls[atCall]
  expect(call, '这一发上传压根没发出去').toBeTruthy()
  const form = call[1]
  expect(form, '第二枚实参不是 FormData').toBeInstanceOf(FormData)
  return form
}
/** 真 File 才像今天这一屏实际递出去的东西：FormData 会把它原样存下，而不是收成 "[object Object]"。 */
const fileFixture = () => new File(['制度'], '制度汇编.pdf', { type: 'text/plain' })
const formKeys = form => [...form.keys()]
const formEntries = form => [...form.entries()].map(([key, value]) => [key, typeof value === 'string' ? value : '<file>'])

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
  live = null
})
/** 只挂一次、只读模板：判下拉每一档的文案出处，不走上传那条路。 */
async function screenHtmlOfChoices() {
  mountPanel()
  await settle()
  return screenHtml()
}
// ==================== 甲 · 档位与默认值：出处只有一份 ====================

const BACKEND_CHAT = () => readFileSync(new URL('../../../../app/api/v1/chat.py', import.meta.url), 'utf8')
const BACKEND_POLICY = () => readFileSync(new URL('../../../../app/common/policy.py', import.meta.url), 'utf8')
const BACKEND_RBAC = () => readFileSync(new URL('../../../../app/common/rbac.py', import.meta.url), 'utf8')

describe('R313 格一 甲 · 默认值与档位都钉在后端那一处，不是界面自己想的', () => {
  it('默认档 == 后端 POST /upload 的 Form(1)：从后端源码现读那一句对数', () => {
    const hit = /classification:\s*int\s*=\s*Form\((\d+)\)/.exec(BACKEND_CHAT())
    expect(hit, '后端签名里找不到 classification = Form(n)：这一枚同源钉该改法而不是被跳过').toBeTruthy()
    expect(DEFAULT_UPLOAD_CLASSIFICATION, '界面默认档与后端 Form 默认值不再相等：谁改了后端没改这里').toBe(Number(hit[1]))
    expect(DEFAULT_UPLOAD_CLASSIFICATION).toBe(1)
  })

  it('可选档位 == 「至少有一个角色的 clearance 读得到」的那些档，一档不多一档不少', () => {
    const block = /_CLASSIFICATION_LEVELS\s*=\s*\{([\s\S]*?)\}/.exec(BACKEND_POLICY())
    expect(block, '后端那枚名字→档位的表读不到了：先取证再动界面').toBeTruthy()
    const declared = new Set([...block[1].matchAll(/:\s*(\d+)/g)].map(m => Number(m[1])))
    // 档位名从 app/common/rbac.py 现读，不抄快照：谁给某个角色抬了 clearance，这一枚钉当场重算。
    const rbac = BACKEND_RBAC()
    const clearance = /ROLE_CLEARANCE\s*=\s*\{([^}]*)\}/.exec(rbac)
    expect(clearance, 'ROLE_CLEARANCE 读不到了：这一枚钉该改法而不是被跳过').toBeTruthy()
    const reachable = new Set([...clearance[1].matchAll(/:\s*(\d+)/g)].map(m => Number(m[1])))
    for (const level of UPLOAD_CLASSIFICATION_LEVELS) {
      expect(declared.has(level), '界面上出现了后端词表里没有的档位：' + level).toBe(true)
      expect(reachable.has(level), '这一档没有角色的 clearance 够得着，放上来＝可点的数据黑洞：' + level).toBe(true)
    }
    expect([...UPLOAD_CLASSIFICATION_LEVELS].sort((x, y) => x - y)).toEqual([...reachable].sort((x, y) => x - y))
  })

  it('第 4 档（core）今天不许出现在界面上，也不许发得出去：它超出全部角色的 clearance', () => {
    const block = /_CLASSIFICATION_LEVELS\s*=\s*\{([\s\S]*?)\}/.exec(BACKEND_POLICY())
    const declared = new Set([...block[1].matchAll(/:\s*(\d+)/g)].map(m => Number(m[1])))
    expect(declared.has(4), '后端词表若已改动，这一枚钉连同密级口径一起回业主重裁（H13/U5）').toBe(true)
    expect(UPLOAD_CLASSIFICATION_LEVELS).not.toContain(4)
    expect(normalizeClassification(4), '4 档必须退回默认档，不能发得出去').toBe(DEFAULT_UPLOAD_CLASSIFICATION)
  })

  it('归一那道门只放行名单里的整数，其余一律退回默认档（垃圾值不许写进 NOT NULL 列）', () => {
    for (const level of UPLOAD_CLASSIFICATION_LEVELS) {
      expect(normalizeClassification(level)).toBe(level)
      expect(normalizeClassification(String(level))).toBe(level)
    }
    for (const junk of [0, -1, 4, 5, 99, '99', '', ' ', null, undefined, NaN, {}, [], '1级', true]) {
      expect(normalizeClassification(junk), '这一枚值不该发得出去：' + String(junk)).toBe(DEFAULT_UPLOAD_CLASSIFICATION)
    }
  })

  it('档位文案不新造：下拉每一档说的就是 lib/provenance.js 的 classificationLabel', async () => {
    const { classificationLabel } = await import('../../lib/provenance')
    const html = await screenHtmlOfChoices()
    for (const level of UPLOAD_CLASSIFICATION_LEVELS) {
      // classificationLabel 吃字符串（provenance.js 的 textOf 只认 string），断言这边同一条口径。
      const label = classificationLabel(String(level))
      expect(label, '共享口径自己都没给出句子').toBeTruthy()
      expect(html, '屏上这一档没有用全站那一份说法：' + label).toContain(`>${label}`)
    }
    expect(plainText(html)).not.toMatch(/(绝密|机密|秘密|内部|公开)/)
  })
})

// ==================== 乙 · 选择框真的在屏上，且默认就是不动它 ====================

describe('R313 格一 乙 · 上传前问那一句：选择框在屏上，默认档不改变今天的行为', () => {
  it('首屏就有一枚密级选择框，每一档都在，默认档标着「（默认）」', async () => {
    mountPanel()
    await settle()
    const html = await screenHtml()
    expect(html).toContain('data-testid="document-classification-select"')
    expect(html.match(/<option value="[1-4]"/g)).toHaveLength(UPLOAD_CLASSIFICATION_LEVELS.length)
    const text = stripTags(html)
    expect(text).toContain('这一发的密级')
    expect(text).toMatch(/密级 1 级（默认）/)
  })

  it('不碰它 ⇒ 界面自己说的是 1 级，state 里也是 1', async () => {
    const state = mountPanel()
    await settle()
    expect(state.uploadClassification).toBe(DEFAULT_UPLOAD_CLASSIFICATION)
    expect(await screen()).toContain('这一发按 密级 1 级 上传')
  })

  it('🔴 这一屏不发部门：屏上没有部门控件，说明句只把部门归给服务端', async () => {
    const state = mountPanel()
    await settle()
    const text = await screen()
    expect(text).toContain('部门由服务端按你的账号判定')
    expect(state.chooseClassification).toBeTypeOf('function')
  })
})

// ==================== 丙 · 这一枚值真发得出去 ====================

describe('R313 格一 丙 · 抓 http.post 收到的那一份 FormData 本身', () => {
  it('用户不动选择框 ⇒ 发出去的就是 classification=1，与今天等价', async () => {
    const state = mountPanel()
    await settle()
    await state.uploadSingleFile(fileFixture())
    const form = postedForm(0)
    expect(formEntries(form)).toEqual([['file', '<file>'], ['classification', '1']])
    expect(form.get('classification')).toBe(String(DEFAULT_UPLOAD_CLASSIFICATION))
    state.stopUploadPoll()
  })

  it('表单里只有 file 与 classification 两枚键：🔴 department 一枚都不发', async () => {
    const state = mountPanel()
    await settle()
    for (const level of UPLOAD_CLASSIFICATION_LEVELS) {
      http.post.mockClear()
      state.chooseClassification(String(level))
      await state.uploadSingleFile(fileFixture())
      const form = postedForm(0)
      expect(formKeys(form), '键集合里多出来的东西都是越权面').toEqual(['file', 'classification'])
      expect(form.get('department')).toBeNull()
      expect(form.get('classification')).toBe(String(level))
    }
    state.stopUploadPoll()
  })

  it('选择框改到 3 级 ⇒ 下一发真带 3；回执那一行显示的也是发出去的这一档', async () => {
    const state = mountPanel()
    await settle()
    state.chooseClassification('3')
    await state.uploadFilesParallel([fileFixture()])
    expect(postedForm(0).get('classification')).toBe('3')
    const text = await screen()
    expect(text).toContain('密级 3 级')
    state.stopUploadPoll()
  })

  it('中途把下拉改回去，也不许改已在途那一发：出发时取的是一档快照', async () => {
    mountPanel()
    await settle()
    const state = live.state
    let release = null
    http.post.mockImplementation(() => new Promise(resolve => {
      release = () => resolve({ data: { status: 'ok', message: '已收录', filename: '制度汇编.pdf' } })
    }))
    const HIGHEST = String(Math.max(...UPLOAD_CLASSIFICATION_LEVELS))
    state.chooseClassification(HIGHEST)
    const flying = state.uploadFilesParallel([fileFixture()])
    await settle()
    state.chooseClassification('1')
    expect(release, '这一发没挂起，快照判据就没测到').toBeTruthy()
    release()
    await flying
    expect(postedForm(0).get('classification'), '已在途那一发被中途改的下拉污染了').toBe(HIGHEST)
    state.stopUploadPoll()
  })

  it('下拉被改成垃圾值（越界/空）⇒ 发出去的是默认档，不是一串垃圾', async () => {
    const state = mountPanel()
    await settle()
    state.chooseClassification('99')
    await state.uploadSingleFile(fileFixture())
    expect(postedForm(0).get('classification')).toBe('1')
    expect(state.uploadClassification, '屏上显示的那一档也得跟着归一，否则说的与发的两回事').toBe(1)
    state.chooseClassification('')
    http.post.mockClear()
    await state.uploadSingleFile(fileFixture())
    expect(postedForm(0).get('classification')).toBe('1')
    state.stopUploadPoll()
  })

  it('源码级反向钉：这一屏不 append department，也不 v-model 直连未归一的表单值', () => {
    const src = readFileSync(new URL('../DocPanel.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
    expect(src).not.toMatch(/append\(\s*['"]department['"]/)
    expect(src).toMatch(/form\.append\('classification', String\(item\.classification\)\)/)
    expect(src).toMatch(/item\.classification = normalizeClassification\(uploadClassification\.value\)/)
    // 队列那一条显示的是【发出去的那一档】，不是选择框现在的样子：两格各管一头。
    expect(src).toMatch(/classificationWords\(item\.classification\)/)
  })
})
