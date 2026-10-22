import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'
import { collectPageErrors } from './support/static-site.js'
import { CONTROL_MARKUP, EMPTY_STATE_MARKUP, ERROR_STATE_MARKUP } from './support/state-fixtures.js'

/**
 * V6 · 面板状态原语「长文案换行不溢出」的像素证据（B 叶子线）
 *
 * 为什么单独一份 spec：states.test.js 跑在 node 环境里量不了像素，它在头注释里承诺了
 * 「像素证据由本文件量」，那就必须真有这么一条用例在 Chromium 里量，否则那句承诺就是假账。
 *
 * 在「原语还没接进任何面板」的前提下怎么拿到真实渲染：
 *   - 样式是真的：theme.css 的 :root 块 + UiButton/UiEmptyState/UiErrorState 三个 css 原样内联；
 *   - DOM 是手抄的等价 markup（support/state-fixtures.js），由 states.test.js 逐类名比对真实 SSR 产物；
 *   - 不起服务器、不 goto、不依赖 dist：setContent 直接喂，远程字体天然不被引用（见第一条断言）。
 *
 * 关键设计：同视口同容器宽度里放一个「抽掉换行机制」的对照组。组件不溢出 + 对照组必须溢出，
 * 两件事同时成立，才说明不溢出是 overflow-wrap / min-width:0 救的，而不是视口够宽造成的假绿。
 */

const HERE = path.dirname(fileURLToPath(import.meta.url))
const FRONTEND_ROOT = path.resolve(HERE, '..', '..')
const read = (relative) => fs.readFileSync(path.join(FRONTEND_ROOT, relative), 'utf8')

/** 只取 :root 块：theme.css 第 1 行是远程字体 @import，整份内联会把外网依赖带进内网用例 */
function rootBlock(css) {
  const start = css.indexOf(':root {')
  if (start < 0) throw new Error('theme.css 里找不到 :root 块：token 层形状变了，这里该红，不该 skip')
  const end = css.indexOf('\n}', start)
  if (end < 0) throw new Error(':root 块没有独行收口的右大括号：该升级解析器，而不是放宽断言')
  return css.slice(start, end + 2)
}

const TOKEN_CSS = rootBlock(read('src/assets/theme.css'))
const TOKEN_LINES = TOKEN_CSS.split('\n').filter((line) => line.trim().startsWith('--')).length

const SHELL_CSS = [
  'body { margin: 0; padding: var(--s-5); background: var(--surface-0); color: var(--text-1); font-family: var(--font-body); }',
  '.fx-stack { display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-5); }',
  '.fx-panel { width: 380px; }',
  '.fx-panel--wide { width: min(1200px, 100%); }',
  '.fx-control { width: 380px; overflow: hidden; padding: var(--s-2); border: 1px dashed var(--border-2); }',
  '.fx-control__text { margin: 0; overflow-wrap: normal; word-break: keep-all; font-size: var(--t-sm); }',
].join('\n')

const STYLE = [
  TOKEN_CSS,
  SHELL_CSS,
  read('src/components/ui/UiButton.css'),
  read('src/components/ui/UiEmptyState.css'),
  read('src/components/ui/UiErrorState.css'),
].join('\n')

const PAGE_HTML = [
  '<!doctype html>',
  '<html lang="zh-CN"><head><meta charset="utf-8"><style>' + STYLE + '</style></head><body>',
  '<div class="fx-stack">',
  '  <div class="fx-panel">' + ERROR_STATE_MARKUP + '</div>',
  '  <div class="fx-panel">' + EMPTY_STATE_MARKUP + '</div>',
  '  <div class="fx-panel">' + CONTROL_MARKUP + '</div>',
  '  <div class="fx-panel fx-panel--wide">' + ERROR_STATE_MARKUP + '</div>',
  '</div>',
  '</body></html>',
].join('\n')

test.beforeEach(async ({ page }) => {
  await page.setContent(PAGE_HTML, { waitUntil: 'load' })
  // 字体度量决定换行位置：等字体就绪再量，避免回退字体中途改变行宽
  await page.evaluate(() => (document.fonts ? document.fonts.ready : Promise.resolve()))
})

/** 文字实际绘制范围用 Range 量：block 盒子的宽度不随内容溢出而变长，只看盒子会漏判 */
const MEASURE = () => {
  const probe = (selector) => {
    const el = document.querySelector(selector)
    if (!el) return null
    const box = el.getBoundingClientRect()
    const range = document.createRange()
    range.selectNodeContents(el)
    const painted = range.getBoundingClientRect()
    const style = getComputedStyle(el)
    const size = parseFloat(style.fontSize)
    let linePx
    if (style.lineHeight && style.lineHeight.indexOf('px') >= 0) linePx = parseFloat(style.lineHeight)
    else if (style.lineHeight && style.lineHeight !== 'normal') linePx = size * parseFloat(style.lineHeight)
    else linePx = size * 1.2
    return {
      paintedRight: painted.right,
      boxRight: box.right,
      boxWidth: box.width,
      boxHeight: box.height,
      lines: box.height / linePx,
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    }
  }
  const wideBody = probe('.fx-panel--wide .ui-error-state__body')
  const widePanel = probe('.fx-panel--wide')
  return {
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    desc: probe('.ui-error-state__desc'),
    emptyTitle: probe('.ui-empty-state__title'),
    control: probe('.fx-control__text'),
    wideBodyWidth: wideBody ? wideBody.boxWidth : null,
    widePanelWidth: widePanel ? widePanel.boxWidth : null,
  }
}

test('内联的是真 token 层，且整页不引任何远程资源', async ({ page }) => {
  const errors = collectPageErrors(page)
  expect(TOKEN_LINES, ':root 只抽出几行，说明解析形状变了').toBeGreaterThanOrEqual(70)
  expect(STYLE).toContain('--surface-0')
  expect(STYLE).toContain('--danger')
  expect(STYLE).not.toContain('@import')
  expect(STYLE).not.toContain('@font-face')
  expect(PAGE_HTML).not.toContain('https://fonts')
  expect(errors, errors.join('\n')).toEqual([])
})

test('不可断行的长串在窄面板里被迫换行，而不是顶穿状态块', async ({ page }) => {
  const m = await page.evaluate(MEASURE)
  expect(m.desc, '失败态说明文案没渲染出来，用例就成了空跑').not.toBeNull()
  expect(m.emptyTitle, '空态标题没渲染出来，用例就成了空跑').not.toBeNull()
  expect(m.control, '对照组没渲染出来，就无法证明这条用例有检测力').not.toBeNull()

  // ① 组件：文字绘制范围不越过自己的盒子（+2 容差吸收亚像素）
  expect(m.desc.paintedRight, '后端回来的长串顶穿了失败态盒子').toBeLessThanOrEqual(m.desc.boxRight + 2)
  expect(m.emptyTitle.paintedRight, '长中文顶穿了空态标题盒子').toBeLessThanOrEqual(m.emptyTitle.boxRight + 2)

  // ② 组件：确实被迫换成多行，而不是靠裁切 / overflow: hidden 装成「没溢出」
  expect(m.desc.lines, '139 字符不可断行长串居然还是单行').toBeGreaterThanOrEqual(2)
  expect(m.emptyTitle.lines, '88 字无标点中文居然还是单行').toBeGreaterThanOrEqual(2)

  // ③ 对照组：同视口同容器，抽掉 overflow-wrap 就必须溢出；不溢出说明 ①② 是假绿
  expect(m.control.paintedRight, '对照组都没溢出：这条用例量不出任何东西').toBeGreaterThan(m.control.boxRight + 2)
  // 溢出证据取两段：文字绘制范围越过盒子，且段落自身 scrollWidth 大于 clientWidth。
  // （取 <p> 而不是外层 overflow:hidden 壳：Chromium 对后者只报 1px 差，量不出真实溢出）
  expect(m.control.scrollWidth, '对照组段落没被撑出滚动宽度').toBeGreaterThan(m.control.clientWidth + 1)

  // ④ 整页不该出现横向滚动条
  expect(m.scrollWidth - m.innerWidth, '页面被撑出横向滚动条').toBeLessThanOrEqual(1)
})

test('宽面板里正文列仍受测量宽度约束，不跟着容器拉成通栏', async ({ page }) => {
  const m = await page.evaluate(MEASURE)
  expect(m.wideBodyWidth, '宽面板里的失败态实例没渲染').not.toBeNull()
  expect(m.widePanelWidth, '宽面板容器没渲染').not.toBeNull()
  // 通栏一行上百汉字读不下去（视觉文档 §6 可读行长），正文列必须明显窄于容器
  expect(m.wideBodyWidth, '正文列宽度低于 120px，测量宽度被算成了怪值').toBeGreaterThanOrEqual(120)
  expect(m.wideBodyWidth, '正文列跟着容器拉成通栏了').toBeLessThanOrEqual(m.widePanelWidth - 100)
})

test('状态原语样例整页截图基线（不入库，缺失时显式 skip）', async ({ page }, testInfo) => {
  const bootstrapping = process.env.EB_MAKE_BASELINES === '1'
  const baselineDir = path.join(HERE, '__snapshots__', path.basename(testInfo.file, '.js') + '-' + testInfo.project.name)
  test.skip(!bootstrapping && !fs.existsSync(baselineDir), '基线截图不入库：跑 npx playwright test --update-snapshots 生成本地基线')
  await expect(page).toHaveScreenshot({ fullPage: false })
})
