/**
 * R467 判据② · 上传那一屏必须把「不点密级会怎样」说成人话，而且屏上一个技术串都不许有
 *
 * 现状（现读自 9c21490）：R313 已经把密级选择框放上屏（`document-classification-select`），
 * 默认档旁边只写着「（默认）」，说明句是「这一发按 密级 1 级 上传 · 部门由服务端按你的账号判定」
 * —— 员工读不出**不选会怎样**。而 H13 已由业主裁定为甲：未标注＝1 级＝这一维不设门槛、全公司都读得到。
 * 于是这一格从「省一句文案」变成了「客户知情与否」：本件钉的就是这句话必须上屏。
 *
 * 本单一枚新控件都不造：档位词汇仍是全站唯一那份 `classificationLabel`（`lib/provenance.js`），
 * 选择框、testid、发出去的 FormData 都归 r313 那本件管，本件只判**屏上读到的字**。
 *
 * 四组断言：
 *   甲 「不选就是默认档 密级 N 级：不设密级门槛，全公司的人都读得到」必须真印在渲染产物上，
 *      N 与 DEFAULT_UPLOAD_CLASSIFICATION、与后端 `Form(n)` 同一枚数（同源，不抄快照）；
 *      选了非默认档时，「这一发带的档」与「不选会落的档」必须同时在场、各说各的，不许混成一枚。
 *   乙 可见文本零技术串：`classification` / `Form(` / `key=1` 这类形状 0 命中（DOM 属性里的
 *      testid 是机器名，允许；员工眼睛读到的那一段不允许）—— 判的是 r267 同一族口径。
 *   丙 与 r313 现有断言逐条对齐：那本件里对屏上文案的 `toContain` 字面量必须仍在场（不许为了
 *      配合本单把它改宽），且今天的渲染产物逐条满足它们。
 *   丁 反证：甲乙用的**就是同一枚谓词函数**，把 R467 之前的那句原话与一枚带 `classification=1`
 *      的句子喂进去，谓词必须判 false —— 摘掉交付就当场红的证据，不是另一把平行尺。
 *
 * 手法沿用 r313 / r288 / r338：本仓没有 jsdom、也不 npm i。createRenderer + 内存虚拟节点挂
 * DocPanel 自己编译出的 setup，再把 SFC 那份 ssrRender 套在活 setupState 上出 HTML。
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

import DocPanel, { DEFAULT_UPLOAD_CLASSIFICATION } from '../DocPanel.vue'
import { http } from '../../lib/http'

// ==================== 无 DOM 的真生命周期 + 真模板 ====================

function vnode(tag) {
  return { tag, props: {}, children: [], parent: null, text: '' }
}

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
    const parent = target.parent
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

function mountPanel() {
  http.get.mockImplementation(async url => (
    String(url).endsWith('/documents/catalog')
      ? { data: { documents: [{ filename: '制度汇编.pdf', owner_id: 'u-1', size_bytes: 2048, parse_status: 'ready', index_status: 'indexed' }] } }
      : { data: {} }
  ))
  let instance = null
  const app = createApp({
    __name: 'R467PlainWordsHost',
    props: DocPanel.props,
    setup: DocPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div')
    },
  }, {})
  app.config.warnHandler = () => {}
  app.provide(SSR_CONTEXT_KEY, {})
  app.mount(vnode('#root'))
  live = { app, state: instance.setupState }
  return live.state
}

const stripComments = html => html.replace(/<!--[\s\S]*?-->/g, '')
const stripTags = html => html.replace(/<[^>]*>/g, '')
const plainText = html => stripTags(stripComments(html))
const render = () => renderToString(h({
  __name: 'R467PlainWordsFace',
  setup: () => live.state,
  ssrRender: DocPanel.ssrRender,
}))
const screen = async () => plainText(await render())
const settle = async () => { await nextTick(); await nextTick() }

// ==================== 判据用的那两枚谓词（丁组反证用的就是它们本身）====================

/** 「不选会怎样」必须一起说清：落到哪一档 + 那一档意味着什么。 */
const DEFAULT_CLAUSE = /不选就是默认档 密级 (\d+) 级：不设密级门槛，全公司的人都读得到/
const CHOSEN_CLAUSE = /这一发按 密级 (\d+) 级 上传/
const DEPARTMENT_CAVEAT = '部门由服务端按你的账号判定'
const plainWordsSaidClearly = text => DEFAULT_CLAUSE.test(text) && CHOSEN_CLAUSE.test(text)

/** 技术串的形状：员工屏幕上一个都不许有（r267 那族口径的同一条尺，键=值 / 源码符号 / 路由）。 */
const TECH_PATTERNS = [
  /classification/i,
  /\bForm\(/,
  /[A-Za-z_][A-Za-z0-9_]*\s*=\s*\d/,
  /\.py\b/,
  /\/api\/v\d/,
  /DEFAULT_UPLOAD_CLASSIFICATION/,
]
const techViolations = text => TECH_PATTERNS.filter(pattern => pattern.test(text)).map(String)

const BACKEND_CHAT = () => readFileSync(new URL('../../../../app/api/v1/chat.py', import.meta.url), 'utf8')
const R313_FILE = () => readFileSync(new URL('./r313-upload-classification.test.js', import.meta.url), 'utf8')

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
  live = null
})

// ==================== 甲 · 「不选会怎样」真上屏 ====================

describe('R467 判据②甲 · 默认档旁边那句话把人话说全了', () => {
  it('默认态：不选落到哪一档 + 那一档意味着什么，两句都在渲染产物上', async () => {
    mountPanel()
    await settle()
    const text = await screen()
    expect(text).toMatch(DEFAULT_CLAUSE)
    expect(text).toMatch(CHOSEN_CLAUSE)
    expect(plainWordsSaidClearly(text), '交付被摘：屏上读不出「不选会怎样」').toBe(true)
  })

  it('🔴 那句里的默认档不是手抄的：与 DEFAULT_UPLOAD_CLASSIFICATION 与后端 Form(n) 同一枚数', async () => {
    mountPanel()
    await settle()
    const hit = /classification:\s*int\s*=\s*Form\((\d+)\)/.exec(BACKEND_CHAT())
    expect(hit, '后端签名里读不到 classification = Form(n)：这一枚同源钉该改法而不是被跳过').toBeTruthy()
    const stated = Number(DEFAULT_CLAUSE.exec(await screen())[1])
    expect(stated).toBe(DEFAULT_UPLOAD_CLASSIFICATION)
    expect(stated).toBe(Number(hit[1]))
  })

  it('选了非默认档：「这一发带的档」与「不选会落的档」同时在场且各说各的，不许混成一枚', async () => {
    const state = mountPanel()
    await settle()
    state.chooseClassification('3')
    await settle()
    const text = await screen()
    expect(CHOSEN_CLAUSE.exec(text)[1]).toBe('3')
    expect(DEFAULT_CLAUSE.exec(text)[1]).toBe(String(DEFAULT_UPLOAD_CLASSIFICATION))
    expect(plainWordsSaidClearly(text)).toBe(true)
    state.stopUploadPoll()
  })

  it('🔴 「全员可检索」这句不许单独站着：同一句必须带着部门那道闸', async () => {
    mountPanel()
    await settle()
    const text = await screen()
    expect(text).toContain(DEPARTMENT_CAVEAT)
    const sentence = text.split(/[：]/).find(part => part.includes('不设密级门槛'))
    expect(sentence, '「不设密级门槛」那一段不见了').toBeTruthy()
    expect(sentence).toContain(DEPARTMENT_CAVEAT)
  })
})

// ==================== 乙 · 屏上零技术串 ====================

describe('R467 判据②乙 · 员工读到的那一段里没有一枚技术串', () => {
  it('可见文本：classification / Form( / key=1 / .py / /api/vN 全部 0 命中', async () => {
    mountPanel()
    await settle()
    const text = await screen()
    expect(techViolations(text), '屏上出现技术串：' + techViolations(text).join(', ')).toEqual([])
  })

  it('机器名只许待在属性里：DOM 有 document-classification-select，可见文本里没有 classification', async () => {
    mountPanel()
    await settle()
    const html = await render()
    expect(html).toContain('data-testid="document-classification-select"')
    expect(techViolations(plainText(html))).toEqual([])
  })
})

// ==================== 丙 · 与 r313 的现有断言逐条对齐 ====================

describe('R467 判据②丙 · 没有把 r313 的断言改宽，也没有与它打架', () => {
  const REQUIRED = [
    '这一发的密级',
    '这一发按 密级 1 级 上传',
    DEPARTMENT_CAVEAT,
    '密级 1 级（默认）',
  ]

  it('r313 那本件里对屏上文案的每一枚字面量仍在场（不许为了配合本单放宽它）', () => {
    const r313 = R313_FILE()
    for (const phrase of REQUIRED) {
      expect(r313, 'r313 不再要求屏上有这句：' + phrase).toContain(phrase)
    }
  })

  it('今天的渲染产物逐条满足 r313 那四枚要求', async () => {
    mountPanel()
    await settle()
    const text = await screen()
    for (const phrase of REQUIRED) {
      expect(text, '屏上读不到 r313 要求的那句：' + phrase).toContain(phrase)
    }
  })
})

// ==================== 丁 · 反证：同一枚谓词必须咬住「摘掉交付」那两种形状 ====================

describe('R467 判据②丁 · 谓词有牙（摘掉交付就当场红，用的不是另一把尺）', () => {
  it('刀1：把说明句换回 R467 之前那句原话 ⇒ 甲组谓词判 false', () => {
    const beforeR467 = '这一发按 密级 1 级 上传 · ' + DEPARTMENT_CAVEAT
    expect(plainWordsSaidClearly(beforeR467), '屏上只写「默认」而不写「不选会怎样」时本钉必须红').toBe(false)
    const chosenOnly = '这一发按 密级 3 级 上传 · ' + DEPARTMENT_CAVEAT
    expect(plainWordsSaidClearly(chosenOnly)).toBe(false)
  })

  it('刀2：把默认档写成 classification=1 这种技术串 ⇒ 乙组谓词必须报出来', () => {
    const leaky = '这一发按 密级 1 级 上传 · 不选就是默认档 classification=1：不设密级门槛，全公司的人都读得到（部门由服务端按你的账号判定）'
    expect(techViolations(leaky), '技术串没被这枚尺抓到').toEqual(
      expect.arrayContaining(['/classification/i', String(/[A-Za-z_][A-Za-z0-9_]*\s*=\s*\d/)]))
    // 同一枚变异也得被甲组抓到：档位一旦写成键值对，「密级 N 级」那个人话形状就没了。
    expect(plainWordsSaidClearly(leaky), '甲组谓词同样不认这种写法').toBe(false)
  })

  it('两把刀都对今天的真产物成立：真产物绿、变异体红，同一枚函数', async () => {
    mountPanel()
    await settle()
    const text = await screen()
    expect(plainWordsSaidClearly(text)).toBe(true)
    expect(techViolations(text)).toEqual([])
  })
})
