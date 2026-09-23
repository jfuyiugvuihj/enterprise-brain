/**
 * R197 判据①④ · 出处卡那把「已记下」的锁，不许跟着 filename 跨轮走
 *
 * 病灶（R195 交回的一格边界）：ChatPanel.vue:1212 那枚消息循环按【下标】挂 key，
 * 而 SourceCard 的 marks 是按【filename】存在【实例】里的（SourceCard.vue:53）。
 * 切会话时 messages[i] 整份被换掉而下标没变 ⇒ 卡片实例复用 ⇒ 上一轮那笔「已记下」
 * 原封不动跟到新会话那一轮：员工看到的是「这一轮我也点过了？」，这一轮他什么都没点。
 * 同屏的 CacheFace（:1258）已经是正确写法：:key="`cache-${turnKey(msg, i)}`"。
 *
 * 环境仍是 node（仓库没有 jsdom / @vue/test-utils，也不 npm i）。SSR 每次渲染都新建实例，
 * 「实例复用」这件事在 renderToString 里根本看不见，所以这一族换两条腿，各管各的事：
 *   甲 机制腿：vue 公开的 createRenderer + 一枚内存虚拟节点，跑【真实补丁周期】；
 *      组件用真 SourceCard、真 lib/feedback 状态机、真 sourcesFace 模型，
 *      被换掉的只有网络层（vi.mock lib/http）与「元素怎么落地」那一层渲染器。
 *      甲1/甲2 是对照组：同一枚组件，强制不挂 key 就锁跨轮、强制挂按轮 key 就不跨轮
 *      —— 这一条与 ChatPanel 无关，它先把「病确实是由按位复用引起的」钉死。
 *   乙 接线腿：乙1~乙4 用的 key 值是从 ChatPanel.vue 源码里【现抠】出来的表达式算的，
 *      不是测试手捏的：改前抠到「没有 :key」⇒ 复用 ⇒ 红；改后抠到按轮表达式 ⇒ 绿。
 *      丙段再把「必须走 turnKey」「外层 :key="i" 不许动」钉在源码上。
 *
 * 两处诚实交代（不假装验过自己验不了的）：
 *   1) turnKey 住在 <script setup> 里不外露，本单也不许新造一份，所以测试按 :835 那两行
 *      原文镜像了一枚求值器；丙4 那枚钉子盯着原文，谁改 turnKey 谁就得同时来改镜子。
 *      镜子只负责把源码里那枚表达式算成一个值，它不当第二套判断。
 *   2) 机制腿的宿主是测试自搭的最小消息循环（外层 :key="i" + 内层一张卡），它证的是
 *      「按下标复用实例 ⇒ 实例里的锁跨轮活着」这条机制在真组件上成立，不证 ChatPanel 的
 *      DOM 层级；接线由乙腿（抠产品源码的 :key）与丙段源码钉负责。
 *   3) node 环境下 vite 把 SFC 编成【只有 ssrRender】的产物，客户端挂载需要一枚 render，
 *      所以夹具把产品自己那份模板原文（同一个 SourceCard.vue 的 <template>）过一遍 vue
 *      的运行时编译器补上这一枚；setup / props / emits / 状态机 / 措辞全用产品真身，
 *      这一步只换「模板怎么落地」，不换「谁存态、谁说话」。编译器不在位时当场报错，不静默退化。
 *      （运行时编译出的 render 形如 function(_ctx,_cache){with(_ctx){...}}，而 <script setup>
 *      的绑定被 __isScriptSetup 挡在公共代理之外，所以 _ctx 由夹具给一枚读真绑定的作用域。）
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, getCurrentInstance, h, nextTick, shallowRef } from 'vue'

// 只换网络层：feedback.js 的状态机与措辞、provenance.js 的模型、SourceCard 的模板全走真身。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }
})

import { http } from '../../lib/http'
import { sourcesFace } from '../../lib/provenance'
import SourceCard from '../SourceCard.vue'

const source = name => readFileSync(new URL(`../${name}`, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const panel = source('ChatPanel.vue')

/**
 * 产品组件的客户端版本：模板原文取自产品 .vue，compile 出来的是真 render。
 * vite 的 SSR 包装层会在 setup 里登记 ssrContext.modules（Symbol.for('v-scx')），
 * 客户端挂载没有真 ssrContext，所以由夹具补一枚空的 provide，让那层登记落空不炸。
 */
const SSR_CONTEXT_KEY = Symbol.for('v-scx')
const hasOwn = (obj, key) => Object.prototype.hasOwnProperty.call(obj || {}, key)

/**
 * 渲染期读值的作用域：只有真绑定（setup 返回的那本，含 marks）与 props 才归它管。
 * has 必须按名单答，不能一律 true —— 运行时编译出的函数靠作用域链拿闭包里的 _Vue，
 * 全答 true 会把 _Vue 也吞进这枚代理（实跑过一次：Cannot destructure ... of '_Vue'）。
 */
function renderScope(instance) {
  const empty = {}
  const { setupState, props } = instance
  const names = new Set([...Object.keys(setupState || {}), ...Object.keys(props || {})])
  return new Proxy(empty, {
    has: (_target, key) => typeof key === 'string' && names.has(key),
    get: (_target, key) => {
      if (typeof key !== 'string') return undefined
      if (setupState && hasOwn(setupState, key)) return setupState[key]
      if (props && hasOwn(props, key)) return props[key]
      return instance.proxy[key]
    },
  })
}

function clientCard() {
  if (typeof compile !== 'function') {
    throw new Error('R197 夹具：解析到的 vue 构建里没有运行时编译器（compile），本族的机制腿跑不了，请人工核对，不要静默跳过')
  }
  const template = /<template>([\s\S]*)<\/template>/.exec(source('SourceCard.vue'))
  if (!template) throw new Error('R197 夹具：SourceCard.vue 里取不到 <template>')
  const compiled = compile(template[1])
  return {
    __name: 'R197ClientSourceCard',
    props: SourceCard.props,
    emits: SourceCard.emits,
    setup: SourceCard.setup,
    render(_ctx, _cache) {
      // 用 getCurrentInstance() 而不是 this.$：后者会往 stderr 里塞一枚
      // "Property '$' was accessed via 'this'" 的警告，别人的日志不该替夹具背这个。
      return compiled(renderScope(getCurrentInstance()), _cache)
    },
  }
}

const ClientSourceCard = clientCard()

const NAME = '差旅费报销制度-2026.pdf'
const LOCK_HEADLINE = '这处出处已记下「有用」。'

// ==================== 产品源码里那枚 :key ====================

/** 面板里这一枚自闭合元素的属性原文（正则字面量，不拼字符串，免得转义走形）。 */
function attrsOf(component) {
  const tags = /<([A-Z]\w+)\b([\s\S]*?)\/>/g
  let match = tags.exec(panel)
  while (match) {
    if (match[1] === component) return match[2]
    match = tags.exec(panel)
  }
  throw new Error(`R197 夹具：ChatPanel.vue 里找不到自闭合的 <${component}> 元素`)
}

/** 这一枚元素挂的 :key 原文；没挂就是 null（没挂正是本单要修的形）。 */
function keyExprOf(component) {
  const key = /:key="([^"]*)"/.exec(attrsOf(component))
  return key ? key[1] : null
}

/**
 * ChatPanel.vue:835 turnKey 的镜像（见文件头交代 1）。规则只两条：
 * msg.mid 是非空字符串就用它，否则用「会话 id + 下标」。
 */
function mirrorTurnKey(activeId, msg, index) {
  if (msg && typeof msg.mid === 'string' && msg.mid) return `m${msg.mid}`
  return `${activeId}#${index}`
}

/** 插值片段的取值：只认面板里真用得上的那几种形，认不下就当场报错，绝不猜。 */
function partValue(inner, ctx) {
  const text = inner.trim()
  if (text === 'turnKey(msg, i)') return mirrorTurnKey(ctx.activeId, ctx.msg, ctx.index)
  if (text === 'i' || text === 'index') return String(ctx.index)
  if (text === 'Math.random()') return String(Math.random())
  if (text === 'Date.now()') return String(Date.now())
  throw new Error(`R197 夹具：认不下 :key 里的表达式片段 —— ${inner}`)
}

/**
 * 把源码里抠出来的 :key 表达式算成一个值。
 * `a-${turnKey(msg, i)}` 这类模板串按片段代入；裸 i 取序号；没挂 key 返回 undefined。
 */
function keyFromExpr(expr, ctx) {
  if (expr === null || expr === undefined) return undefined
  const raw = expr.trim()
  const template = /^`([\s\S]*)`$/.exec(raw)
  if (template) return template[1].replace(/\$\{([\s\S]*?)\}/g, (_, inner) => partValue(inner, ctx))
  if (raw === 'i' || raw === 'index') return String(ctx.index)
  if (raw === 'Math.random()' || raw === 'Date.now()') return partValue(raw, ctx)
  throw new Error(`R197 夹具：认不下 :key 形状 —— ${raw}`)
}

// ==================== 无 DOM 的真补丁周期 ====================

function vnodeNode(tag) {
  return { tag, props: {}, children: [], parent: null, text: '' }
}

const harness = { staticNodes: 0 }

function parentOf(node) {
  return node.parent || null
}

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
    harness.staticNodes += 1
    const node = Object.assign(vnodeNode('#static'), { text: content })
    nodeOps.insert(node, parent, anchor)
    return [node, node]
  },
  querySelector: () => null,
  setScopeId: (el, id) => { el.props[id] = '' },
}

const { createApp } = createRenderer(nodeOps)

function collect(node, testid, out = []) {
  if (node.props && node.props['data-testid'] === testid) out.push(node)
  ;(node.children || []).forEach(child => collect(child, testid, out))
  return out
}
const onScreen = (root, testid) => collect(root, testid)
const textOf = node => (node ? String(node.text || '') + (node.children || []).map(textOf).join('') : '')

/** 一枚按钮此刻按不按得动、亮没亮。 */
function markButton(root, testid) {
  const hits = onScreen(root, testid)
  expect(hits.length, `屏上应有且只有一枚 ${testid}，实测 ${hits.length} 枚`).toBe(1)
  return { disabled: hits[0].props.disabled === true, pressed: hits[0].props['aria-pressed'] === true }
}
const lockText = root => onScreen(root, 'source-feedback-state').map(node => textOf(node)).join(' ')

/**
 * 最小消息循环：外层就是面板那一枚 :key="i"（本单不许动它），内层一张真 SourceCard，
 * 挂的 key 由调用方给定 —— 从产品源码抠来的（乙段）或对照组强制的（甲段）。
 */
async function mountLoop({ turns, activeId, expr }) {
  const root = vnodeNode('#root')
  const list = shallowRef(turns)
  const session = shallowRef(activeId)
  const Host = {
    __name: 'R197Host',
    setup() {
      return () => list.value.map((msg, i) => {
        const face = sourcesFace(msg.sources)
        const key = keyFromExpr(expr, { msg, index: i, activeId: session.value })
        return h('div', { key: i, class: 'msg-row' }, [
          h('div', { class: 'face-stack' }, face ? [h(ClientSourceCard, { face, key })] : []),
        ])
      })
    },
  }
  const app = createApp(Host)
  app.provide(SSR_CONTEXT_KEY, {})
  app.mount(root)
  await nextTick()
  return {
    root,
    /** 切会话 = restoreActive() 那样整份换掉 messages.value（sessions.js:814）。 */
    async switchTo(nextTurns, nextActiveId) {
      list.value = nextTurns
      session.value = nextActiveId
      await nextTick()
      await nextTick()
    },
    /** 真人点法：从渲染产物里找出那枚按钮（一行两枚时点第一行），按模板绑的 handler 打一次。 */
    async click(testid = 'source-feedback-accept', which = 0) {
      const hits = onScreen(root, testid)
      expect(hits.length, `点之前屏上应有 ${testid}`).toBeGreaterThan(0)
      await hits[which].props.onClick({})
      await nextTick()
      await nextTick()
    },
  }
}

// ==================== 场景数据（真模型，不手捏 face） ====================

const rowOf = sourceId => ({
  filename: NAME,
  sourceId,
  chunkIndex: 4,
  score: 0.412,
  scoreType: 'rerank',
  versionId: '7',
  classification: '2',
  department: '销售部',
  excerpt: '',
})
const turn = (mid, sourceId) => ({
  role: 'assistant',
  content: '限额以内据实报销。',
  steps: [],
  mid,
  sources: { rows: [rowOf(sourceId)], hitCount: 1, hiddenCount: 0, scopeReasonCode: 'department_scope' },
})
/** 会话甲的第 0 轮：员工在这里点过一次「有用」。 */
const turnA = () => turn('mid-aaa', 'doc-travel')
/** 切到会话乙之后的第 0 轮：同一份 filename，这一轮员工什么都还没点。 */
const turnB = () => turn('mid-bbb', 'doc-travel')
/** 按轮 key 的正确形状（CacheFace 那一形的出处卡版本，只给甲段对照组用）。 */
const PER_TURN = '`source-${turnKey(msg, i)}`'

const receipt = signal => ({ data: { status: 'ok', filename: NAME, signal, accepted_count: 4, rejected_count: 1 } })
const productKey = () => keyExprOf('SourceCard')

beforeEach(() => {
  vi.clearAllMocks()
  http.post.mockImplementation(async (_path, body) => receipt(body.signal))
})

// ==================== 甲 · 机制腿：对照组 ====================

describe('R197 甲 · 同一枚真 SourceCard，挂不挂按轮 key 的差别（机制对照）', () => {
  it('甲0 夹具自证：卡真画出来了、点一下真落定、锁真在屏上（不谎报夹具）', async () => {
    const loop = await mountLoop({ turns: [turnA()], activeId: 'sess-a', expr: null })
    expect(onScreen(loop.root, 'source-card')).toHaveLength(1)
    expect(harness.staticNodes, 'SourceCard 若出现静态提升，本夹具的遍历会看不全，需要改夹具').toBe(0)
    expect(markButton(loop.root, 'source-feedback-accept')).toEqual({ disabled: false, pressed: false })
    expect(markButton(loop.root, 'source-feedback-reject')).toEqual({ disabled: false, pressed: false })
    expect(lockText(loop.root)).toBe('')

    await loop.click()
    expect(markButton(loop.root, 'source-feedback-accept')).toEqual({ disabled: true, pressed: true })
    expect(markButton(loop.root, 'source-feedback-reject').disabled).toBe(true)
    expect(lockText(loop.root)).toContain(LOCK_HEADLINE)
    expect(http.post).toHaveBeenCalledTimes(1)
  })

  it('甲1 强制不挂 key（病灶形状）：切会话之后，同一份 filename 的锁跟着过来了', async () => {
    const loop = await mountLoop({ turns: [turnA()], activeId: 'sess-a', expr: null })
    await loop.click()
    expect(markButton(loop.root, 'source-feedback-accept').disabled).toBe(true)

    await loop.switchTo([turnB()], 'sess-b')
    // 这一条写的就是「病确实存在」：不挂 key 时锁跨轮活着，所以本单才要挂 key。
    expect(markButton(loop.root, 'source-feedback-accept').disabled,
      '不挂按轮 key 时锁应当跨轮继承（机制归因；这一枚变红说明复用机制要重新取证）').toBe(true)
    expect(lockText(loop.root)).toContain(LOCK_HEADLINE)
  })

  it('甲2 强制挂按轮 key（CacheFace 那一形）：同一枚组件，锁就不再跨轮', async () => {
    const loop = await mountLoop({ turns: [turnA()], activeId: 'sess-a', expr: PER_TURN })
    await loop.click()
    expect(markButton(loop.root, 'source-feedback-accept').disabled).toBe(true)

    await loop.switchTo([turnB()], 'sess-b')
    expect(markButton(loop.root, 'source-feedback-accept')).toEqual({ disabled: false, pressed: false })
    expect(markButton(loop.root, 'source-feedback-reject')).toEqual({ disabled: false, pressed: false })
    expect(lockText(loop.root)).not.toContain(LOCK_HEADLINE)
  })

  it('甲3 同一轮内重复渲染不许把锁弄丢（按轮 key 不许是按帧 key）', async () => {
    const loop = await mountLoop({ turns: [turnA()], activeId: 'sess-a', expr: PER_TURN })
    await loop.click()
    await loop.switchTo([turn('mid-aaa', 'doc-travel')], 'sess-a')
    expect(markButton(loop.root, 'source-feedback-accept')).toEqual({ disabled: true, pressed: true })
    expect(lockText(loop.root)).toContain(LOCK_HEADLINE)
  })
})

// ==================== 乙 · 接线腿：key 从产品源码现抠 ====================

describe('R197 乙 · ChatPanel 给出处卡挂的必须是按轮的 key', () => {
  it('乙1 切会话：上一轮点过「有用」，新一轮同一份 filename 不该 disabled、不该显示「已记下」', async () => {
    const loop = await mountLoop({ turns: [turnA()], activeId: 'sess-a', expr: productKey() })
    await loop.click()
    expect(markButton(loop.root, 'source-feedback-accept').disabled).toBe(true)

    await loop.switchTo([turnB()], 'sess-b')
    const accept = markButton(loop.root, 'source-feedback-accept')
    expect(accept.disabled, '新一轮这一行员工什么都没点，按钮不该是灰的（锁被上一轮继承了）').toBe(false)
    expect(accept.pressed, '新一轮不许点亮任何一枚').toBe(false)
    expect(lockText(loop.root), '新一轮不许说「已记下」').not.toContain(LOCK_HEADLINE)
    expect(markButton(loop.root, 'source-feedback-reject')).toEqual({ disabled: false, pressed: false })
  })

  it('乙2 没有 mid 的那一轮（turnKey 的退路分支）：换会话也不许继承上一轮的锁', async () => {
    const noMid = base => {
      const msg = base()
      delete msg.mid
      return msg
    }
    const loop = await mountLoop({ turns: [noMid(turnA)], activeId: 'sess-a', expr: productKey() })
    await loop.click()
    expect(markButton(loop.root, 'source-feedback-accept').disabled).toBe(true)

    await loop.switchTo([noMid(turnB)], 'sess-b')
    expect(markButton(loop.root, 'source-feedback-accept').disabled,
      '退路键是「会话 + 下标」，换了会话就不该还是同一枚键').toBe(false)
    expect(lockText(loop.root)).not.toContain(LOCK_HEADLINE)
  })

  it('乙3 同一轮两行同一份 filename：两行共用一笔账（R195 的口径不许被本单改坏）', async () => {
    const twice = {
      role: 'assistant',
      content: '限额以内据实报销。',
      steps: [],
      mid: 'mid-aaa',
      sources: { rows: [rowOf('doc-travel'), rowOf('doc-travel-2')], hitCount: 2, hiddenCount: 0, scopeReasonCode: '' },
    }
    const loop = await mountLoop({ turns: [twice], activeId: 'sess-a', expr: productKey() })
    expect(onScreen(loop.root, 'source-feedback-accept')).toHaveLength(2)
    await loop.click()
    const locked = onScreen(loop.root, 'source-feedback-accept').map(node => node.props.disabled === true)
    expect(locked, '同一份资料命中两段时两行共用同一笔评价').toEqual([true, true])
  })

  it('乙4 同一轮流式追加之后再看一眼：那一把锁还在（挡按帧/随机 key）', async () => {
    const loop = await mountLoop({ turns: [turnA()], activeId: 'sess-a', expr: productKey() })
    await loop.click()
    // 这一轮还在长：正文追加一帧，卡片必须原地更新，不许被换一张新的（换了就是锁丢了）。
    const grown = Object.assign(turnA(), { content: '限额以内据实报销。超出部分由本人承担。' })
    await loop.switchTo([grown], 'sess-a')
    expect(markButton(loop.root, 'source-feedback-accept')).toEqual({ disabled: true, pressed: true })
    expect(lockText(loop.root)).toContain(LOCK_HEADLINE)
    expect(http.post).toHaveBeenCalledTimes(1)
  })
})

// ==================== 丙 · 源码钉 ====================

describe('R197 丙 · 键的形状钉在 ChatPanel.vue 上', () => {
  it('丙1 抠出来的 key 表达式：不同轮必须给不同键', () => {
    const expr = productKey()
    const a = keyFromExpr(expr, { msg: turn('mid-aaa', 'x'), index: 0, activeId: 'sess-a' })
    const b = keyFromExpr(expr, { msg: turn('mid-bbb', 'x'), index: 0, activeId: 'sess-b' })
    expect(a, '没挂 :key 就是按位复用，本单要修的就是这一格').toBeDefined()
    expect(a).not.toBe(b)
  })

  it('丙2 同一轮重复求值必须给同一枚键（挡 Math.random / 时间戳那类退化）', () => {
    const expr = productKey()
    const ctx = { msg: turn('mid-aaa', 'x'), index: 0, activeId: 'sess-a' }
    expect(keyFromExpr(expr, ctx)).toBe(keyFromExpr(expr, ctx))
  })

  it('丙3 必须走既有 turnKey(msg, i)，不许新造一枚 key 函数', () => {
    const expr = productKey() || ''
    expect(expr).toContain('turnKey(msg, i)')
    const calls = expr.match(/[A-Za-z_$][\w$]*\(/g) || []
    expect(calls, '这枚 key 里只许出现 turnKey 一次调用').toEqual(['turnKey('])
  })

  it('丙4 镜子有凭据：turnKey 原文仍是「有 mid 用 mid，否则会话 + 下标」两行', () => {
    const body = /function turnKey\(msg, index\) \{([\s\S]*?)\n\}/.exec(panel)?.[1]
    if (!body) throw new Error('R197 夹具：ChatPanel.vue 里找不到 turnKey')
    expect(body).toContain("typeof msg.mid === 'string' && msg.mid")
    expect(body).toContain('return `m${msg.mid}`')
    expect(body).toContain('return `${activeId.value}#${index}`')
    expect(mirrorTurnKey('sess-a', { mid: 'm1' }, 0)).toBe('mm1')
    expect(mirrorTurnKey('sess-a', {}, 3)).toBe('sess-a#3')
  })

  it('丙5 夹具自检：镜子把同屏 CacheFace 那枚已知的按轮 key 算成 cache-<轮键>', () => {
    const expr = keyExprOf('CacheFace')
    expect(expr).toBe('`cache-${turnKey(msg, i)}`')
    expect(keyFromExpr(expr, { msg: turn('mid-aaa', 'x'), index: 0, activeId: 'sess-a' })).toBe('cache-mmid-aaa')
  })

  it('丙6 外层消息循环的 :key="i" 一字未动（本单不扩大爆炸半径）', () => {
    const outer = /<div v-for="\(msg, i\) in messages" :key="([^"]*)"/.exec(panel)
    if (!outer) throw new Error('R197 夹具：外层消息循环的形状变了，请人工核对（r174 那族也依赖它）')
    expect(outer[1]).toBe('i')
    expect(panel.match(/v-for="\(msg, i\) in messages"/g)).toHaveLength(1)
  })
})

// ==================== 丁 · 判据⑤ 同形名单（本单只读不动） ====================

describe('R197 丁 · 同形下标 key 名单（读数钉：谁改了形就得重新核账）', () => {
  const countOf = re => (panel.match(re) || []).length

  it('丁1 面板里按下标挂 key 的位置就是名单这四枚，一枚不多一枚不少', () => {
    expect([
      countOf(/:key="i"/g), // 外层消息循环（授权范围外，本单不动）
      countOf(/:key="ci"/g), // ChartViewer
      countOf(/:key="si"/g), // msg.steps
      countOf(/:key="li"/g), // hitl.labels
    ]).toEqual([1, 1, 1, 1])
  })

  it('丁2 出处卡不许留第二枚挂载点，也不许再有无 key 的挂法', () => {
    expect(panel.match(/<SourceCard/g)).toHaveLength(1)
    expect(keyExprOf('SourceCard'), '出处卡必须挂一枚 key（乙腿四条行为用例的前提）').toBeTruthy()
  })
})
