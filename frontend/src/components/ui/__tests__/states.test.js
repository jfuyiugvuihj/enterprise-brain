/**
 * V5 单测 · 面板状态原语（B 叶子线）
 *
 * 环境是 node + @vue/server-renderer（本仓库 devDependencies 里没有 jsdom / @vue/test-utils，
 * 叶子线也不许 npm i），所以断言分两类，各管各的事：
 *   ① 结构与语义：SSR 出来的 HTML 直接查 role / data-testid / 类名 / 某个块到底渲染没有。
 *   ② 「长文案换行不溢出」：这是 CSS 机制，node 里量不了像素。这里静态断言机制挂在了正确的
 *      选择器上、并且没有用裁切（text-overflow / nowrap）糊过去；真正的像素证据由
 *      tests/visual/ui-states.spec.js 用 Chromium 在五档视口下量出来。
 * 事件（action / retry）在 SSR 里不触发，覆盖留给 A 线接线后的 e2e（不假装验过）。
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import UiEmptyState from '../UiEmptyState.vue'
import UiErrorState from '../UiErrorState.vue'
import * as primitives from '../index.js'
import { LONG_URL, LONG_ZH, FIXTURE_CLASSES, STATE_TESTIDS } from '../../../../tests/visual/support/state-fixtures.js'

const HERE = dirname(fileURLToPath(import.meta.url))
const render = (component, props = {}, slots) => {
  const Host = defineComponent({
    render() {
      return h(component, props, slots)
    },
  })
  return renderToString(h(Host))
}

describe('UiEmptyState', () => {
  it('不给任何操作就只有一句话：说明位与操作区都不渲染', async () => {
    const html = await render(UiEmptyState)
    expect(html).toContain('ui-empty-state__title')
    expect(html).toContain('暂无数据')
    expect(html).not.toContain('ui-empty-state__desc')
    expect(html).not.toContain('ui-empty-state__actions')
  })

  it('空态是「结果」不是「打断」：role=status 且测试位固定', async () => {
    const html = await render(UiEmptyState, { title: '今天没有需要你确认的高风险动作' })
    expect(html).toContain('role="status"')
    expect(html).toContain('data-testid="ui-empty-state"')
    expect(html).toContain('今天没有需要你确认的高风险动作')
    expect(html).not.toContain('role="alert"')
  })

  it('actionLabel 出主操作；未知变体退回 primary，dense 把按钮降到 sm', async () => {
    const plain = await render(UiEmptyState, { actionLabel: '查看已归档' })
    expect(plain).toContain('data-testid="ui-empty-action"')
    expect(plain).toContain('ui-button--primary')
    expect(plain).toContain('查看已归档')

    const bogus = await render(UiEmptyState, { actionLabel: '查看已归档', actionVariant: 'rainbow' })
    expect(bogus).toContain('ui-button--primary')

    const dense = await render(UiEmptyState, { actionLabel: '查看已归档', dense: true })
    expect(dense).toContain('ui-empty-state--dense')
    expect(dense).toContain('ui-button--sm')
  })

  it('actions 插槽整体接管操作区，不再叠一个默认按钮', async () => {
    const html = await render(UiEmptyState, { actionLabel: '不该出现' }, { actions: () => h('button', { type: 'button' }, '去登记一条') })
    expect(html).toContain('去登记一条')
    expect(html).toContain('ui-empty-state__actions')
    expect(html).not.toContain('ui-empty-action')
    expect(html).not.toContain('不该出现')
  })

  it('description 插槽覆盖 prop；默认插槽落在正文区内', async () => {
    const propOnly = await render(UiEmptyState, { description: '上传第一份文档后这里就会有内容' })
    expect(propOnly).toContain('ui-empty-state__desc')
    expect(propOnly).toContain('上传第一份文档后这里就会有内容')

    const slotted = await render(
      UiEmptyState,
      { description: '这条 prop 该被插槽顶掉' },
      { description: () => h('em', '说明插槽'), default: () => h('span', '正文插槽') },
    )
    expect(slotted).toContain('<em>说明插槽</em>')
    expect(slotted).toContain('正文插槽')
    expect(slotted).toContain('ui-empty-state__body')
    expect(slotted).not.toContain('这条 prop 该被插槽顶掉')
  })})

describe('UiErrorState', () => {
  it('默认可重试：重试按钮带固定测试位，失败必须打断读屏', async () => {
    const html = await render(UiErrorState, { description: '关系列表加载失败' })
    expect(html).toContain('role="alert"')
    expect(html).toContain('data-testid="ui-error-state"')
    expect(html).toContain('data-testid="ui-error-retry"')
    expect(html).toContain('重试')
    expect(html).toContain('关系列表加载失败')
  })

  it('retryable=false 时整条操作区消失：权限类失败不给只会再失败一次的按钮', async () => {
    const html = await render(UiErrorState, { title: '没有权限查看本部门数据', retryable: false })
    expect(html).toContain('没有权限查看本部门数据')
    expect(html).not.toContain('ui-error-state__actions')
    expect(html).not.toContain('data-testid="ui-error-retry"')
  })

  it('只有标题：不渲染说明位，也不渲染错误码小字', async () => {
    const html = await render(UiErrorState, { title: '这一步没有完成' })
    expect(html).toContain('ui-error-state__title')
    expect(html).not.toContain('ui-error-state__desc')
    expect(html).not.toContain('ui-error-state__code')
  })

  it('未知码走等宽小字位，与正文分开', async () => {
    const html = await render(UiErrorState, { codeLabel: '错误码：weird_code_from_backend' })
    expect(html).toContain('ui-error-state__code')
    expect(html).toContain('错误码：weird_code_from_backend')
  })

  it('busy 时重试按钮置忙，挡住重复点击', async () => {
    const html = await render(UiErrorState, { busy: true })
    expect(html).toContain('ui-button--busy')
    expect(html).toContain('aria-busy="true"')
    expect(html).toContain('disabled')
  })

  it('retryText 与 actions 插槽两条腿都能定制操作区', async () => {
    const text = await render(UiErrorState, { retryText: '重新加载' })
    expect(text).toContain('重新加载')

    const slotted = await render(UiErrorState, { retryable: true }, { actions: () => h('button', { type: 'button' }, '联系管理员') })
    expect(slotted).toContain('联系管理员')
    expect(slotted).not.toContain('data-testid="ui-error-retry"')
  })

  it('dense 档只缩间距，不换语义', async () => {
    const html = await render(UiErrorState, { dense: true })
    expect(html).toContain('ui-error-state--dense')
    expect(html).toContain('ui-button--sm')
    expect(html).toContain('role="alert"')
  })
})

const cssOf = (name) => readFileSync(join(HERE, '..', name + '.css'), 'utf8')

/** 组件名 → 类名词根：显式映射。UiEmptyState 的词根是 ui-empty-state，不是推导出来的 ui-emptystate */
const STEMS = { UiEmptyState: 'ui-empty-state', UiErrorState: 'ui-error-state' }
/** 空态没有错误码小字位，别照抄失败态的选择器清单 */
const PARTS = { UiEmptyState: ['title', 'desc'], UiErrorState: ['title', 'desc', 'code'] }

/**
 * 按「顶格选择器」取规则体：本目录 CSS 一律顶格书写，逐行精确匹配。
 * 不用正则推导选择器（上一版把 UiEmptyState 推成 ui-emptystate，断言对象压根不存在）；
 * 找不到就是红，不许静默跳过。
 */
const ruleBodies = (css, selector) => {
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

describe('两个状态原语的样式契约', () => {
  for (const name of Object.keys(STEMS)) {
    const stem = STEMS[name]

    it(name + '.css 不含裸色值、发光字与动效', () => {
      const css = cssOf(name)
      for (const banned of ['#', 'rgb(', 'rgba(', 'hsl(', 'hsla(', 'text-shadow', 'box-shadow', 'transition', 'animation', '@keyframes', '!important']) {
        expect(css, name + '.css 不该出现 ' + banned).not.toContain(banned)
      }
    })

    it(name + '.css 里每条取色声明都挂在 token 上', () => {
      const lines = cssOf(name).split(String.fromCharCode(10))
      let checked = 0
      for (const line of lines) {
        const decl = line.trim()
        if (!/^(color|background|border|border-left|border-color):/.test(decl)) continue
        expect(decl, '取色声明必须走 var()：' + decl).toContain('var(')
        checked += 1
      }
      // 下限只用来抓「解析器被打崩 → 一条没扫到」，不是钉死条数：空态 7 条、失败态 8 条
      expect(checked, '一个取色声明都没扫到，说明解析器被打崩了，这条断言在空转').toBeGreaterThanOrEqual(6)
    })

    it(name + ' 的长文案靠换行解决，不靠裁切', () => {
      const css = cssOf(name)
      for (const banned of ['text-overflow', 'white-space: nowrap', 'overflow: hidden']) {
        expect(css, name + '.css 用 ' + banned + ' 是把长文案藏起来，不是换掉').not.toContain(banned)
      }
      for (const part of PARTS[name]) {
        const selector = '.' + stem + '__' + part
        const bodies = ruleBodies(css, selector).join(' ')
        expect(bodies, selector + ' 必须允许任意位置断行').toContain('overflow-wrap: anywhere')
      }
      const body = ruleBodies(css, '.' + stem + '__body').join(' ')
      expect(body, 'flex 子项没有 min-width: 0 就收缩不了，一长串会撑破面板').toContain('min-width: 0')
      expect(body, '正文没有限宽，宽面板里一行能拉出两三百字').toContain('max-width: 56ch')
    })
  }
})

describe('视觉 fixture 与组件产物的耦合', () => {
  it('手抄 markup 里每个类名与 testid 都真实存在于 SSR 产物', async () => {
    const html =
      (await render(UiErrorState, { description: LONG_URL, codeLabel: '错误码：weird_code_from_backend' })) +
      (await render(UiEmptyState, { title: LONG_ZH, dense: true, actionLabel: '去登记一条' }))
    for (const cls of FIXTURE_CLASSES) {
      expect(html, 'fixture 用了 ' + cls + '，组件产物里没有——两份已经各漂各的').toContain(cls)
    }
    for (const testid of Object.values(STATE_TESTIDS)) {
      expect(html, 'fixture 用了 data-testid=' + testid + '，组件产物里没有').toContain(testid)
    }
  })

  it('类名清单自己不空转：两个词根的骨架类都在册', () => {
    for (const stem of Object.values(STEMS)) {
      for (const cls of [stem, stem + '__mark', stem + '__body', stem + '__actions']) {
        expect(FIXTURE_CLASSES, 'fixture 清单漏了 ' + cls).toContain(cls)
      }
    }
    expect(FIXTURE_CLASSES.length, '清单被人剪短＝覆盖率下降').toBeGreaterThanOrEqual(19)
  })
})

describe('导出面', () => {
  it('两个新原语从 barrel 暴露，A 线不必猜路径', () => {
    expect(primitives.UiEmptyState).toBeTruthy()
    expect(primitives.UiErrorState).toBeTruthy()
    expect(primitives.UiEmptyState.name).toBe('UiEmptyState')
    expect(primitives.UiErrorState.name).toBe('UiErrorState')
  })

  it('失败态要用的三个错误函数都在同一个出口上', () => {
    expect(typeof primitives.normalizeError).toBe('function')
    expect(typeof primitives.errorCodeLabel).toBe('function')
    expect(typeof primitives.isRetryable).toBe('function')
  })
})
