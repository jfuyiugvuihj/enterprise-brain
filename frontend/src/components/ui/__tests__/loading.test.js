/**
 * V5 单测 · UiLoadingState（B-6 ②，B 叶子线）
 *
 * 环境仍是 node + @vue/server-renderer（不 npm i jsdom）。骨架屏的「不转圈」「动效可关」
 * 两条都是文档钉的口径（视觉文档 §8.4 第 5 条 + theme.css:95 的「动效只用于状态反馈」），
 * 所以这里既查 SSR 结构，也静态查 CSS 机制：颜色全走 token、尺度全走 var()、
 * prefers-reduced-motion 下必须把 animation 关掉。像素证据留给 A 接线后的 tests/visual。
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import UiLoadingState from '../UiLoadingState.vue'
import * as primitives from '../index.js'

const HERE = dirname(fileURLToPath(import.meta.url))
const cssOf = (name) => readFileSync(join(HERE, '..', name + '.css'), 'utf8')

const render = (props = {}, slots) => {
  const Host = defineComponent({
    render() {
      return h(UiLoadingState, props, slots)
    },
  })
  return renderToString(h(Host))
}

/**
 * 按「顶格选择器 + { 」取规则体，与 states.test.js:154 同一约定：本目录 CSS 一律顶格书写，
 * 逐行精确匹配，找不到就是红，不许静默跳过。多选择器组只有最后一行带 { ，
 * 所以共享声明（.bar, .block {）用 .ui-loading-state__block 这个名字去取。
 */
function ruleBodies(css, selector) {
  const lines = css.split(String.fromCharCode(10))
  const openLine = selector + ' {'
  const bodies = []
  for (let i = 0; i < lines.length; i += 1) {
    if (lines[i].trim() !== openLine) continue
    let body = ''
    for (let j = i + 1; j < lines.length && lines[j].trim().charAt(0) !== '}'; j += 1) {
      body += lines[j].trim() + ' '
    }
    bodies.push(body)
  }
  if (!bodies.length) {
    throw new Error('找不到顶格选择器 ' + selector + '：断言对象不存在就是红，不许改成跳过')
  }
  return bodies
}

describe('UiLoadingState 结构与语义', () => {
  it('默认档：role=status + aria-busy + 三根骨架条 + 一句人话', async () => {
    const html = await render()
    expect(html).toContain('role="status"')
    expect(html).toContain('aria-busy="true"')
    expect(html).toContain('data-testid="ui-loading-state"')
    expect(html).toContain('正在加载')
    expect(html).toContain('ui-loading-state__bars')
    expect((html.match(/data-testid="ui-loading-row"/g) || []).length).toBe(3)
    expect(html).not.toContain('role="alert"')
  })

  it('rows 钳在 0..12：给 0 只剩文案，负数/NaN/超大都不许失控', async () => {
    expect(await render({ rows: 0 })).not.toContain('ui-loading-state__bars')
    expect(await render({ rows: -5 })).not.toContain('ui-loading-state__bars')
    expect(await render({ rows: Number.NaN })).not.toContain('ui-loading-state__bars')
    const huge = await render({ rows: 99 })
    expect((huge.match(/data-testid="ui-loading-row"/g) || []).length).toBe(12)
  })

  it('尺寸档：sm/lg 落到类名上，未知值退回 md 而不是什么都不渲染', async () => {
    expect(await render({ size: 'sm' })).toContain('ui-loading-state--sm')
    expect(await render({ size: 'lg' })).toContain('ui-loading-state--lg')
    const bogus = await render({ size: 'enormous' })
    expect(bogus).toContain('ui-loading-state--md')
    expect(bogus).not.toContain('ui-loading-state--enormous')
  })

  it('block 档给预览/图表区：只有一块占位，不再叠骨架条', async () => {
    const html = await render({ variant: 'block' })
    expect(html).toContain('ui-loading-state--block')
    expect(html).toContain('data-testid="ui-loading-block"')
    expect(html).not.toContain('ui-loading-state__bars')
  })

  it('文案槽可以整体替换，正文槽追加在后面', async () => {
    const html = await render({ label: '不该出现' }, { label: () => h('b', '正在取图'), default: () => h('i', '预计 3 秒') })
    expect(html).toContain('正在取图')
    expect(html).toContain('预计 3 秒')
    expect(html).not.toContain('不该出现')
  })

  it('dense 档只改类名，不引入新色相', async () => {
    expect(await render({ dense: true })).toContain('ui-loading-state--dense')
  })

  it('导出面挂好了，A 不用猜路径', () => {
    expect(primitives.UiLoadingState).toBeDefined()
    expect(primitives.UiLoadingState.name).toBe('UiLoadingState')
  })
})

describe('UiLoadingState.css 契约', () => {
  const css = () => cssOf('UiLoadingState')

  it('颜色全部来自 token，没有裸色值与发光', () => {
    const src = css()
    for (const banned of ['#', 'rgb(', 'rgba(', 'hsl(', 'hsla(', 'text-shadow', 'box-shadow', '!important', ':deep(']) {
      expect(src, 'UiLoadingState.css 不该出现 ' + banned).not.toContain(banned)
    }
    for (const line of src.split(String.fromCharCode(10))) {
      const decl = line.trim()
      if (!/^(color|background|background-color|background-image|border(?:-(?:top|right|bottom|left))?(?:-color)?):/.test(decl)) continue
      expect(decl, '取色声明必须挂 token：' + decl).toContain('var(')
    }
  })

  it('尺度属性一律走 var()，没有裸字号与裸间距', () => {
    for (const line of css().split(String.fromCharCode(10))) {
      const decl = line.trim()
      if (!/^(margin|padding|gap|row-gap|column-gap|font-size|border-radius)(-|:)/.test(decl)) continue
      const value = decl.slice(decl.indexOf(':') + 1).replace(/;$/, '').trim()
      const ok = value.includes('var(') || /^(?:0|auto|inherit|normal|0 0)$/.test(value)
      expect(ok, '这条尺度声明没走 token：' + decl).toBe(true)
    }
  })

  it('骨架是「扫动」不是「转圈」，且 reduced-motion 下关掉', () => {
    const src = css()
    expect(src).toContain('@keyframes ui-loading-sweep')
    expect(src).not.toMatch(/rotate\(/)
    expect(src).not.toMatch(/border-\w+-color:\s*transparent/)
    // 共享的扫动声明挂在 .bar, .block 这一组上，末行带 { ，按约定取 block 这个名字
    expect(ruleBodies(src, '.ui-loading-state__block').join(' ')).toContain('animation: ui-loading-sweep')
    expect(ruleBodies(src, '.ui-loading-state__bar').join(' ')).toContain('height: var(--s-3')
    expect(ruleBodies(src, '.ui-loading-state--sm .ui-loading-state__bar').join(' ')).toContain('height: var(--s-2')
    expect(ruleBodies(src, '.ui-loading-state--lg .ui-loading-state__bar').join(' ')).toContain('height: var(--s-4')
    const reduced = src.slice(src.indexOf('@media (prefers-reduced-motion: reduce)'))
    expect(reduced).toContain('animation: none')
    expect(reduced).toContain('.ui-loading-state__bar')
    expect(reduced).toContain('.ui-loading-state__block')
  })

  it('长文案靠换行解决，不靠裁切；flex 子项留 min-width', () => {
    const src = css()
    for (const banned of ['text-overflow', 'white-space: nowrap', 'overflow: hidden']) {
      expect(src, '用 ' + banned + ' 是把长文案藏起来，不是换掉').not.toContain(banned)
    }
    expect(ruleBodies(src, '.ui-loading-state').join(' ')).toContain('min-width: 0')
    const label = ruleBodies(src, '.ui-loading-state__label').join(' ')
    expect(label).toContain('overflow-wrap: anywhere')
    expect(label).toContain('max-width: 56ch')
  })
})