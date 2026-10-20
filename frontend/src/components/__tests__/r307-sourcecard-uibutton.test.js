/**
 * R307 守卫钉 · V2 前端面 · SourceCard.vue 的三枚裸按钮接进 ./ui 的 UiButton
 *
 * 判据（工单 R307）：
 *   ② 三枚真接原语 —— 不许靠「把按钮删了」蒙过归零：出口（打开原文）、两枚动作（采纳/驳回）、
 *      禁用态、点亮态、v-if 权限闸，一枚都不许掉；
 *   ③ 棘轮跟着收小 —— r288 那件的 per-file 数与合计只准往小改，改大当场红。
 *
 * 三条腿（沿用本仓口径：node 环境，无 jsdom / @vue/test-utils，也不 npm i）：
 *   ① 源码腿 = 逐枚扫 <UiButton 开标签（引号感知，手法与 r278 判据⑤同一套），
 *      每枚都带齐 @click / type / variant，两枚动作另带 :disabled 与 :aria-pressed；
 *   ② 真产物腿 = renderToString 走 vite 编好的那份 ssrRender，断言屏上仍是三枚真 <button>，
 *      且 data-testid 没被原语自己的 "ui-button" 顶掉；
 *   ③ 真点击腿 = vue 公开的 createRenderer + 内存虚拟节点跑真实补丁周期。夹具必须把 UiButton
 *      注册进 components —— 少这一枚，模板里的 <UiButton> 会退成一枚解析不到的桩，
 *      绿的是桩件而不是原语（本件特意盯着 class 里有没有 ui-button--*，就是为了不当这种假绿）。
 *
 * 反证怎么算红（本单实跑，跑完按字节还原并复验 sha256）：
 *   · 把任一枚改回裸 <button> ⇒ 甲1 + 丙4 同时红，r288 乙组那三条也一起红；
 *   · 摘掉 :disabled ⇒ 甲4 红，乙3「sending 期间按不动」跟着红；
 *   · 摘掉「打开原文」的 @click ⇒ 甲3 与乙2 一起红（preview 收不到那一行）；
 *   · 删掉采纳/驳回那一段 ⇒ 甲2 数到两枚当场红；
 *   · 把 r288 里 SourceCard 的格位改回 3 或把合计改回 20 ⇒ 丙1 与丙2 红。
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, createSSRApp, getCurrentInstance, h, nextTick } from 'vue'
import { renderToString } from '@vue/server-renderer'

// 只换网络层：feedback.js 的状态机、provenance.js 的模型、SourceCard 的模板与 UiButton 全走真身。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }
})

import { FEEDBACK_PATH, SIGNAL_ACCEPTED, SIGNAL_REJECTED, feedbackAriaLabel } from '../../lib/feedback'
import { http } from '../../lib/http'
import { sourcesFace } from '../../lib/provenance'
import SourceCard from '../SourceCard.vue'
import { UiButton } from '../ui'
import { countNativeButtons, scanNativeButtons, stripComments } from './r288-native-button-scan.js'

const TESTS_DIR = dirname(fileURLToPath(import.meta.url))
const SRC_ROOT = join(TESTS_DIR, '..', '..')
const readSrc = rel => readFileSync(join(SRC_ROOT, rel), 'utf8').replace(/\r\n/g, '\n')

const card = readSrc(join('components', 'SourceCard.vue'))
const ratchetFile = readSrc(join('components', '__tests__', 'r288-native-buttons.test.js'))

const NAME = '差旅费报销制度-2026.pdf'
const OTHER = '采购管理办法.docx'
const rowOf = (over = {}) => ({
  filename: NAME,
  sourceId: 'doc-travel',
  chunkIndex: 4,
  score: 0.412,
  scoreType: 'rerank',
  versionId: '7',
  classification: '2',
  department: '销售部',
  excerpt: '',
  ...over,
})
const faceOf = (rows, hidden = 0) => sourcesFace({ rows, hitCount: rows.length + hidden, hiddenCount: hidden, scopeReasonCode: 'department_scope' })
const receipt = (signal, over = {}) => ({
  data: { status: 'ok', filename: NAME, signal, accepted_count: 4, rejected_count: 1, ...over },
})

// ==================== 量具一：逐枚扫 <UiButton 开标签（源码腿） ====================

/** 取每个 <UiButton 的开标签本体；引号里的 > 不算收尾（与 r278 判据⑤同一条走法）。 */
function primitiveTags(text) {
  const items = []
  const re = /<UiButton\b/g
  let match = null
  while ((match = re.exec(text))) {
    const open = match.index
    let i = open + '<UiButton'.length
    let quote = null
    while (i < text.length) {
      const ch = text[i]
      if (quote) { if (ch === quote) quote = null } else if (ch === '"' || ch === "'") quote = ch
      else if (ch === '>') break
      i += 1
    }
    const attrs = text.slice(open + '<UiButton'.length, i).replace(/\s+/g, ' ').trim()
    items.push({
      line: text.slice(0, open).split('\n').length,
      attrs,
      testid: (/data-testid="([^"]+)"/.exec(attrs) || [, ''])[1],
      click: /@click|v-on:click/.test(attrs),
    })
  }
  return items
}

const wired = primitiveTags(stripComments(card))
const TAGS = ['source-feedback-accept', 'source-feedback-reject', 'source-open']
const oneTag = testid => {
  const hits = wired.filter(item => item.testid === testid)
  expect(hits.length, `模板里带 data-testid="${testid}" 的 <UiButton> 应恰好一枚，实测 ${hits.length} 枚`).toBe(1)
  return hits[0]
}

// ==================== 量具二：SSR 真产物 ====================

const ssrCard = async (rows, hidden = 0) => renderToString(createSSRApp(SourceCard, { face: faceOf(rows, hidden) }))
const buttonTags = html => (html.match(/<button[\s\S]*?<\/button>/g) || []).map(tag => ({
  testid: (/data-testid="([^"]+)"/.exec(tag) || [, ''])[1],
  text: tag.replace(/<[\s\S]*?>/g, ' ').replace(/\s+/g, ' ').trim(),
  disabled: /\bdisabled\b/.test(tag.split('>')[0]),
  pressed: /aria-pressed="true"/.test(tag.split('>')[0]),
}))
const cardButtons = html => TAGS.map(testid => buttonTags(html).find(item => item.testid === testid) || null)

// ==================== 量具三：无 DOM 的真补丁周期（真点击腿） ====================

const SSR_CONTEXT_KEY = Symbol.for('v-scx')
const hasOwn = (obj, key) => Object.prototype.hasOwnProperty.call(obj || {}, key)

function vnodeNode(tag) {
  return { tag, props: {}, children: [], parent: null, text: '' }
}
function parentOf(node) { return node.parent || null }
function detach(node) {
  const siblings = parentOf(node) ? parentOf(node).children : null
  const at = siblings ? siblings.indexOf(node) : -1
  if (at >= 0) siblings.splice(at, 1)
  node.parent = null
}

const nodeOps = {
  createElement: tag => vnodeNode(tag),
  createText: text => Object.assign(vnodeNode('#text'), { text }),
  createComment: text => Object.assign(vnodeNode('#comment'), { text }),
  setText: (node, text) => { node.text = text },
  setElementText: (el, text) => { el.children.length = 0; el.text = text },
  parentNode: node => parentOf(node),
  nextSibling(node) {
    const siblings = parentOf(node) ? parentOf(node).children : null
    if (!siblings) return null
    return siblings[siblings.indexOf(node) + 1] || null
  },
  insert(node, parent, anchor) {
    detach(node)
    const at = anchor ? parent.children.indexOf(anchor) : -1
    if (at < 0) parent.children.push(node)
    else parent.children.splice(at, 0, node)
    node.parent = parent
  },
  remove: node => detach(node),
  patchProp: (el, key, prev, next) => {
    if (next === null || next === undefined) delete el.props[key]
    else el.props[key] = next
  },
  cloneNode: node => Object.assign(vnodeNode(node.tag), { props: { ...node.props }, text: node.text }),
  insertStaticContent(content, parent, anchor) {
    const node = Object.assign(vnodeNode('#static'), { text: content })
    nodeOps.insert(node, parent, anchor)
    return [node, node]
  },
  querySelector: () => null,
  setScopeId: (el, id) => { el.props[id] = '' },
}

const { createApp } = createRenderer(nodeOps)

/** 渲染期读值的作用域：只认真绑定与 props（手法同 r197，全答 true 会把闭包里的 _Vue 也吞进来）。 */
function renderScope(instance) {
  const empty = {}
  const { setupState, props } = instance
  const names = new Set([...Object.keys(setupState || {}), ...Object.keys(props || {})])
  // $slots / $attrs / $props 这些 public 属性也要答 has：UiButton 的模板读 $slots.icon，
  // 漏了这一支，运行时编译出的 render 会在 with 块里找不到它们而抛 ReferenceError。
  // 名单以外的（含闭包里的 _Vue 与 _createElementVNode 等 helper）一律答 false，照 r197 的交代。
  const PUBLIC_KEYS = /^\$(slots|attrs|props|el|data|setupState|emit|options|refs|root|parent|nextTick)$/
  return new Proxy(empty, {
    has: (_target, key) => typeof key === 'string' && (names.has(key) || PUBLIC_KEYS.test(key)),
    get: (_target, key) => {
      if (typeof key !== 'string') return undefined
      if (setupState && hasOwn(setupState, key)) return setupState[key]
      if (props && hasOwn(props, key)) return props[key]
      return instance.proxy[key]
    },
  })
}

/**
 * node 环境里 vite 把 SFC 编成【只有 ssrRender】的产物，客户端挂载缺一枚 render；
 * 这里把产品自己那份模板原文（同一个 .vue 的 <template>）过一遍 vue 的运行时编译器补上。
 * setup / props / emits / 状态机 / 原语内部一律用产品真身，被换掉的只有「元素怎么落地」那层。
 */
function clientify(label, rel, sfc, extraComponents) {
  if (typeof compile !== 'function') {
    throw new Error('R307 夹具：解析到的 vue 构建里没有运行时编译器（compile），请人工核对，不要静默跳过')
  }
  const template = /<template>([\s\S]*)<\/template>/.exec(readSrc(rel))
  if (!template) throw new Error(`R307 夹具：${rel} 里取不到 <template>`)
  const compiled = compile(template[1])
  return {
    __name: label,
    props: sfc.props,
    emits: sfc.emits,
    components: { ...extraComponents },
    setup: sfc.setup,
    render(_ctx, _cache) {
      return compiled(renderScope(getCurrentInstance()), _cache)
    },
  }
}

/**
 * 客户端版 UiButton：本件的「真点击腿」要按的是原语渲染出的那枚 button，
 * 所以原语自己也得进这一层 —— 少这一枚，<UiButton> 要么退成解析不到的桩，
 * 要么报「missing template or render function」，两种都不是产品屏上的那一格。
 */
const ClientUiButton = clientify('R307ClientUiButton', join('components', 'ui', 'UiButton.vue'), UiButton)
/** 卡片也客户端化，并把上面那枚真原语注册进去（这就是本件与桩件假绿的分界）。 */
const ClientCard = clientify('R307ClientSourceCard', join('components', 'SourceCard.vue'), SourceCard, { UiButton: ClientUiButton })

function collect(node, testid, out = []) {
  if (node.props && node.props['data-testid'] === testid) out.push(node)
  ;(node.children || []).forEach(child => collect(child, testid, out))
  return out
}
const onScreen = (root, testid) => collect(root, testid)

async function mountCard(rows) {
  const root = vnodeNode('#root')
  const face = faceOf(rows)
  const previews = []
  const Host = {
    __name: 'R307Host',
    setup() {
      return () => h(ClientCard, { face, onPreview: row => previews.push({ ...row }) })
    },
  }
  const app = createApp(Host)
  app.provide(SSR_CONTEXT_KEY, {})
  app.mount(root)
  await nextTick()
  return { root, previews }
}

/** 真人点法：从渲染产物里取出那枚按钮（多行同名时按序号取），按模板绑的 handler 打一次。 */
async function press(root, testid, which = 0) {
  const hits = onScreen(root, testid)
  expect(hits.length, `屏上第 ${which + 1} 枚之前应有 ${testid}，实测 ${hits.length} 枚`).toBeGreaterThan(which)
  expect(typeof hits[which].props.onClick, `${testid} 没挂上点击目标（模板里的 @click 掉了）`).toBe('function')
  const result = hits[which].props.onClick({})
  await nextTick()
  if (result && typeof result.then === 'function') await result
  await nextTick()
  return hits[0]
}
const stateOf = (root, testid) => {
  const hits = onScreen(root, testid)
  expect(hits.length, `屏上应有且只有一枚 ${testid}`).toBe(1)
  return {
    tag: hits[0].tag,
    cls: String(hits[0].props.class || ''),
    disabled: hits[0].props.disabled === true,
    pressed: hits[0].props['aria-pressed'] === true,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

// ==================== 甲 · 源码层：三枚真的接上了原语，且没少东西 ====================

describe('R307 甲 · 判据②③：SourceCard 的裸 <button> 归零，且是真接进 ./ui 的 UiButton', () => {
  it('现取裸 <button> = 0 枚（塞回一枚当场红）', () => {
    expect(countNativeButtons(card), 'SourceCard.vue 还剩裸按钮').toBe(0)
  })

  it('从 ./ui 引了 UiButton，并在模板里用了三枚，一一对上原先的三个出口', () => {
    expect(card).toMatch(/import\s*\{\s*UiButton\s*\}\s*from\s*'\.\/ui'/)
    expect(wired.map(item => item.testid).sort()).toEqual(TAGS.slice().sort())
  })

  it('逐枚对照：三枚都追得到 @click，也都声明了 type="button" 与 variant 档位', () => {
    const dead = wired.filter(item => !item.click)
    expect(dead.map(item => `:${item.line} ${item.attrs}`), '这些 UiButton 没有可追的点击目标').toEqual([])
    for (const item of wired) {
      expect(item.attrs, `:${item.line} 掉了 type`).toMatch(/type="button"/)
      expect(item.attrs, `:${item.line} 掉了 variant 档位`).toMatch(/variant="(ghost|secondary|primary|danger)"/)
    }
  })

  it('「打开原文」这枚出口没退化成静态文字：ghost 档 + 原文案 + 仍 emit preview', () => {
    const open = oneTag('source-open')
    expect(open.attrs).toMatch(/class="source-open"/)
    expect(open.attrs).toMatch(/variant="ghost"/)
    expect(open.attrs).toMatch(/:aria-label="`打开原文：\$\{row\.filename\}`"/)
    expect(open.attrs).toMatch(/@click="emit\('preview', row\)"/)
  })

  it('采纳/驳回两枚的禁用态与点亮态一枚都不许掉', () => {
    for (const [testid, signal, cls] of [
      ['source-feedback-accept', 'SIGNAL_ACCEPTED', 'source-mark--accept'],
      ['source-feedback-reject', 'SIGNAL_REJECTED', 'source-mark--reject'],
    ]) {
      const item = oneTag(testid)
      expect(item.attrs, `${testid} 的类名掉了（点亮态的 CSS 锚点）`).toMatch(new RegExp(`class="source-mark ${cls}"`))
      expect(item.attrs, `${testid} 掉了 :disabled`).toMatch(new RegExp(`:disabled="propsOf\\(row, ${signal}\\)\\.disabled"`))
      expect(item.attrs, `${testid} 掉了 :aria-pressed`).toMatch(new RegExp(`:aria-pressed="propsOf\\(row, ${signal}\\)\\.pressed"`))
      expect(item.attrs, `${testid} 掉了 :aria-label`).toMatch(new RegExp(`:aria-label="ariaOf\\(row, ${signal}\\)"`))
      expect(item.attrs, `${testid} 掉了 @click`).toMatch(new RegExp(`@click="markSignal\\(row, ${signal}\\)"`))
    }
  })

  it('不许靠「删掉带按钮的那一段」归零：权限闸与不可标记那行的脸都还在', () => {
    expect(card).toContain('v-if="rowMarkable(row)"')
    expect(card).toContain('data-testid="source-feedback-blocked"')
    expect(card).toContain('data-testid="source-feedback"')
    expect(card).toContain(':data-phase="markOf(row).phase"')
  })
})

// ==================== 乙 · 真产物：SSR 出来的仍是三枚真 button ====================

describe('R307 乙 · 判据②：接原语之后屏上的那一格没变', () => {
  it('三枚仍渲染成真 <button>，testid 落在按钮上而不是被原语自己的 "ui-button" 顶掉', async () => {
    const html = await ssrCard([rowOf()])
    for (const testid of TAGS) {
      expect(html, `屏上缺真 button：${testid}`).toMatch(new RegExp(`<button[^>]*data-testid="${testid}"[^>]*>`))
    }
    expect(html, 'data-testid 被原语自己的值顶掉了').not.toContain('data-testid="ui-button"')
  })

  it('可及名称与文字一个都没换：aria-label 全文 + 文件名 + 两枚信号标签', async () => {
    const html = await ssrCard([rowOf()])
    expect(html).toContain('aria-label="打开原文：' + NAME + '"')
    expect(html).toContain('aria-label="' + feedbackAriaLabel(SIGNAL_ACCEPTED, NAME) + '"')
    const [accept, reject, open] = cardButtons(html)
    expect(open.text).toBe(NAME)
    expect(accept.pressed).toBe(false)
    expect(reject.pressed).toBe(false)
    expect(accept.disabled).toBe(false)
    expect(reject.disabled).toBe(false)
  })

  it('不可标记的那一行不摆两枚动作（v-if 权限闸还活着），但仍把原因说出口', async () => {
    const html = await ssrCard([rowOf({ filename: '   ' })])
    const marks = buttonTags(html).filter(item => item.testid.startsWith('source-feedback-'))
    expect(marks, '这一行摆出了动作按钮，权限闸掉了').toEqual([])
    expect(html).toContain('data-testid="source-feedback-blocked"')
    expect(html).toContain('这一行没有可记录的出处名称')
  })

  it('真点击：点「打开原文」把【这一行】交给 preview 出口，且一发请求都不发', async () => {
    const { root, previews } = await mountCard([rowOf(), rowOf({ filename: OTHER, sourceId: 'doc-buy', chunkIndex: 1 })])
    expect(onScreen(root, 'source-open').length, '两行出处应有两枚打开原文').toBe(2)
    const node = await press(root, 'source-open', 0)
    expect(node.tag, '打开原文渲染出的不是真 button（原语没接上）').toBe('button')
    expect(previews).toHaveLength(1)
    expect(previews[0].sourceId).toBe('doc-travel')
    expect(previews[0].filename).toBe(NAME)
    expect(http.post).not.toHaveBeenCalled()
    await press(root, 'source-open', 1)
    expect(previews.map(item => item.sourceId), '第二枚点开的必须是第二行，不是第一行').toEqual(['doc-travel', 'doc-buy'])
  })

  it('真点击：点「采纳」走真请求体，sending 期间两枚都按不动，点亮只等真回执', async () => {
    let release = null
    http.post.mockImplementation(() => new Promise(resolve => { release = () => resolve(receipt(SIGNAL_ACCEPTED)) }))
    const { root } = await mountCard([rowOf()])
    const clicked = press(root, 'source-feedback-accept')
    await nextTick()
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(http.post.mock.calls[0][0]).toBe(FEEDBACK_PATH)
    expect(http.post.mock.calls[0][1]).toEqual({ filename: NAME, signal: 'accepted' })
    expect(stateOf(root, 'source-feedback-accept').disabled, 'sending 期间这枚还能按，就是双击记账').toBe(true)
    expect(stateOf(root, 'source-feedback-reject').disabled).toBe(true)
    expect(stateOf(root, 'source-feedback-accept').pressed, '回执没回来就亮了，是假话').toBe(false)
    release()
    await clicked
    await nextTick()
    expect(stateOf(root, 'source-feedback-accept').pressed, '真回执落定之后没亮').toBe(true)
    expect(stateOf(root, 'source-feedback-reject').pressed, '驳回那枚不该跟着亮').toBe(false)
  })

  it('真点击：渲染出的那枚 button 带着原语的档位类，不是解析不到的桩', async () => {
    const { root } = await mountCard([rowOf()])
    const open = stateOf(root, 'source-open')
    const accept = stateOf(root, 'source-feedback-accept')
    expect(open.tag).toBe('button')
    expect(open.cls, 'UiButton 没解析出原语类名（夹具退成桩件了）').toContain('ui-button--ghost')
    expect(open.cls).toContain('source-open')
    expect(accept.cls).toContain('ui-button--secondary')
    expect(accept.cls).toContain('source-mark--accept')
  })

  it('真点击：同一行点第二下不是撤回，也不再多发一笔账（后端没这枚出口）', async () => {
    http.post.mockImplementation(async () => receipt(SIGNAL_REJECTED))
    const { root } = await mountCard([rowOf()])
    await press(root, 'source-feedback-reject')
    expect(stateOf(root, 'source-feedback-reject').pressed).toBe(true)
    const before = http.post.mock.calls.length
    await press(root, 'source-feedback-reject').catch(() => {})
    expect(http.post.mock.calls.length, '记上之后再点一次就是第二笔账').toBe(before)
  })
})

// ==================== 丙 · 棘轮只减不增（钉的是 r288 里的数字本身） ====================

describe('R307 丙 · 判据③：r288 的棘轮数字改大就红', () => {
  const perFile = rel => {
    const m = new RegExp(`'${rel}':\\s*(\\d+)`).exec(ratchetFile)
    expect(m, `r288-native-buttons.test.js 里找不到 ${rel} 这一格（刀被人整段摘了）`).toBeTruthy()
    return Number(m[1])
  }
  const totalLimit = () => {
    const m = /const DEBT_TOTAL_RATCHET = (\d+)/.exec(ratchetFile)
    expect(m, 'r288-native-buttons.test.js 里找不到合计棘轮').toBeTruthy()
    return Number(m[1])
  }

  it('SourceCard.vue 这一格收在 0：改回 3 或任何大于 0 的数字当场红', () => {
    expect(perFile('components/SourceCard.vue'), 'SourceCard 的棘轮上限被改大了').toBeLessThanOrEqual(0)
  })

  it('合计收到 17（App.vue 8 + DashboardPanel 9）：改回 20 当场红', () => {
    expect(totalLimit(), '全仓裸按钮合计棘轮被改大了').toBeLessThanOrEqual(17)
    expect(perFile('App.vue'), 'App.vue 的棘轮被改大（本单没动它，见回执）').toBeLessThanOrEqual(8)
    expect(perFile('components/DashboardPanel.vue'), 'DashboardPanel 的棘轮被改大（归 R291/R293）').toBeLessThanOrEqual(9)
  })

  it('r288 那把刀没被摘：两处 toBeLessThanOrEqual 与量具引用都还在', () => {
    expect(ratchetFile).toContain('countNativeButtons')
    expect(ratchetFile).toContain('toBeLessThanOrEqual(limit)')
    expect(ratchetFile).toContain('DEBT_TOTAL_RATCHET)')
  })

  it('数字与真扫描对得上：全仓现取 <= 17，且 SourceCard 已不在欠账表里', () => {
    const rows = scanNativeButtons(SRC_ROOT)
    const total = rows.reduce((sum, row) => sum + row.count, 0)
    expect(total, '现取合计超出棘轮：\n' + rows.map(row => row.file + ' ' + row.count).join('\n')).toBeLessThanOrEqual(totalLimit())
    expect(rows.map(row => row.file), 'SourceCard.vue 还挂在欠账表里').not.toContain('components/SourceCard.vue')
  })
})

// ==================== 丁 · 接原语时补的基线复位（这三枚的脸本来不长这样） ====================

describe('R307 丁 · 判据②的画相账：原语基线不许把这三枚撑开或换皮', () => {
  it('三枚行内脸不吃原语的控件高：.source-open / .source-mark 复位 min-height: 0', () => {
    const rule = /.source-open,\s*\.source-mark\s*\{([^}]*)}/.exec(card)
    expect(rule, '找不到那一条基线复位规则').toBeTruthy()
    expect(rule[1]).toMatch(/min-height:\s*0/)
  })

  it('文件名那枚仍是带下划线的链接：下划线挪到了插槽里那一层', () => {
    expect(card).toMatch(/\.source-open__text\s*\{[^}]*text-decoration:\s*underline/)
    expect(card).toMatch(/<span class="source-open__text">\{\{ row\.filename \}\}<\/span>/)
  })

  it('hover 复位排在点亮态与灰态之前，谁也不盖谁', () => {
    const hoverAt = card.indexOf('.source-mark:hover')
    const pressedAt = card.indexOf(".source-mark--accept[aria-pressed='true']")
    const disabledAt = card.indexOf('.source-mark[disabled]')
    expect(hoverAt).toBeGreaterThan(-1)
    expect(hoverAt, 'hover 复位排到了点亮态之后，会把绿色压掉').toBeLessThan(pressedAt)
    expect(hoverAt).toBeLessThan(disabledAt)
  })

  it('本单新增的 CSS 一枚裸色值都不许添（只准 var(--*)）', () => {
    const style = /<style scoped>([\s\S]*)<\/style>/.exec(card)[1]
    expect(style).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(style).not.toMatch(/\brgba?\(/)
    expect(style).not.toMatch(/:\s*(white|black|red|blue|green|gray|grey)\b/)
  })
})
