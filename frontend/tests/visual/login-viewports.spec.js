import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'
import { collectPageErrors, distReady, freezeMotion, hostDistFromDisk } from './support/static-site.js'

/**
 * V6 五档视口回归：登录页在 1440 / 1920 / 3440 / 1280 / 768 下不拉伸、不溢出、不崩。
 * 磁盘直喂 dist，不起服务器；远程字体一律 abort（模拟客户内网）。
 */

const HERE = path.dirname(fileURLToPath(import.meta.url))
const READY = distReady()
const SKIPPED = '缺 frontend/dist：先在 frontend 目录跑 npm run build（本用例不伪造通过）'

test.beforeEach(async ({ page }, testInfo) => {
  test.skip(!READY, SKIPPED)
  await hostDistFromDisk(page.context())
  await page.goto('http://enterprise-brain.test/', { waitUntil: 'load' })
  await freezeMotion(page)
  await page.evaluate(() => (document.fonts ? document.fonts.ready : Promise.resolve()))
})

test('登录页在窄屏不出现横向溢出，登录卡完整落在视口内', async ({ page }) => {
  const errors = collectPageErrors(page)
  const viewportSize = page.viewportSize()
  const login = page.getByTestId('login-page')
  await expect(login).toBeVisible()

  const size = viewportSize || { width: 1440, height: 900 }
  const box = await page.getByTestId('login-panel').boundingBox()
  expect(box, '登录卡必须渲染出来').not.toBeNull()
  expect(box.x).toBeGreaterThanOrEqual(-1)
  expect(box.y).toBeGreaterThanOrEqual(-1)
  expect(box.x + box.width).toBeLessThanOrEqual(size.width + 1)
  expect(box.y + box.height).toBeLessThanOrEqual(size.height + 1)

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow, '横向滚动条说明有元素被撑出视口').toBeLessThanOrEqual(1)

  expect(errors, errors.join('\n')).toEqual([])
})

test('断掉远程字体域名后仍按自托管/系统字体渲染，不阻塞出字', async ({ page }) => {
  const errors = collectPageErrors(page)
  const remote = errors.filter((line) => /googleapis|gstatic/i.test(line))
  expect(remote, '内网环境不该指望远程字体域名成功').toEqual([])

  const family = await page.getByTestId('login-hero').evaluate((node) => getComputedStyle(node).fontFamily)
  expect(family).toBeTruthy()
  // 落到浏览器默认字体（serif/sans-serif 打头）说明 V1 自托管还没落地，这里只锁「有字可见」
  const visible = await page.getByTestId('login-hero').evaluate((node) => {
    const style = getComputedStyle(node)
    return { opacity: Number(style.opacity), text: node.innerText.trim().length }
  })
  expect(visible.opacity).toBeGreaterThan(0.9)
  expect(visible.text).toBeGreaterThan(0)
})

test('整页截图基线（不入库，缺失时显式 skip）', async ({ page }, testInfo) => {
  // 基线不入库：首次生成需要显式开关（Playwright 的 CLI 标记传不进 worker 的 argv）
  //   EB_MAKE_BASELINES=1 npx playwright test --update-snapshots
  const bootstrapping = process.env.EB_MAKE_BASELINES === '1'
  const baselineDir = path.join(HERE, '__snapshots__', `${path.basename(testInfo.file)}-${testInfo.project.name}`)
  test.skip(!bootstrapping && !fs.existsSync(baselineDir), '基线截图不入库：跑 npx playwright test --update-snapshots 生成本地基线')
  await expect(page).toHaveScreenshot({ fullPage: false })
})
