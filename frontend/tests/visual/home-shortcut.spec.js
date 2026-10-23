import { test, expect } from '@playwright/test'
import { distReady, hostDistFromDisk } from './support/static-site.js'

test('手机登录页可找到桌面快捷方式入口，安装资料含应用图标', async ({ page }) => {
  test.skip(!distReady(), '先构建 frontend/dist')
  await page.setViewportSize({ width: 377, height: 812 })
  await hostDistFromDisk(page.context())
  await page.goto('http://enterprise-brain.test/')

  const addButton = page.getByRole('button', { name: '添加到手机桌面' })
  await expect(addButton).toBeVisible()
  await addButton.click()
  await expect(page.getByRole('dialog', { name: '添加到手机桌面' })).toBeVisible()
  await expect(page.getByRole('dialog')).toContainText('浏览器')

  const manifestHref = await page.locator('link[rel="manifest"]').getAttribute('href')
  expect(manifestHref).toBeTruthy()
  const manifest = await page.evaluate(async (href) => (await fetch(href)).json(), manifestHref)
  expect(manifest.name).toBe('企业智脑')
  expect(manifest.display).toBe('standalone')
  expect(manifest.icons.map((icon) => icon.sizes)).toEqual(expect.arrayContaining(['192x192', '512x512']))
  const iconsAvailable = await page.evaluate(async (icons) => Promise.all(icons.map(async (icon) => (await fetch(icon.src)).ok)), manifest.icons)
  expect(iconsAvailable).toEqual([true, true])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})
