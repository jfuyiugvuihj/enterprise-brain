import { expect, test } from '@playwright/test'
import { collectPageErrors, distReady, freezeMotion, hostDistFromDisk, UNAUTHENTICATED } from './support/static-site.js'

/**
 * V6 / F3 未登录分支：/api/** 一律 401，两种后端错误形状都要走通。
 * 形状① 字符串稳定码、形状② ErrorEnvelope 对象——D-2 里把对象原样插值就是
 * 「[object Object] / 一屏 JSON」的来源。
 */

const SKIPPED = '缺 frontend/dist：先在 frontend 目录跑 npm run build（本用例不伪造通过）'

async function openLogin(page, apiReply) {
  test.skip(!distReady(), SKIPPED)
  await hostDistFromDisk(page.context(), { apiReply })
  await page.goto('http://enterprise-brain.test/', { waitUntil: 'load' })
  await freezeMotion(page)
}

async function submitLogin(page) {
  await page.getByTestId('login-username').fill('probe')
  await page.getByTestId('login-password').fill('probe-pass')
  await page.getByTestId('login-submit').click()
  await page.waitForLoadState('networkidle')
}

for (const [label, reply] of Object.entries({ '形状1-字符串码': UNAUTHENTICATED.stringCode, '形状2-ErrorEnvelope': UNAUTHENTICATED.envelope })) {
  test(`未登录喂 401（${label}）不崩、不白屏、不弹对象`, async ({ page }) => {
    const errors = collectPageErrors(page)
    await openLogin(page, reply)
    await submitLogin(page)

    const bodyText = await page.locator('body').innerText()
    expect(bodyText).not.toContain('[object Object]')
    expect(bodyText.trim().length, '页面不能空白板').toBeGreaterThan(0)
    await expect(page.getByTestId('login-page')).toBeVisible()
    expect(errors.filter((line) => line.startsWith('pageerror')), errors.join('\n')).toEqual([])
  })
}

test('401 的 ErrorEnvelope 必须经字典转成一句人话（F7 接线前预期失败）', async ({ page }) => {
  // 已知缺陷 D-2：面板把 err.response.data.detail 原样插值，Envelope 会渲染成 JSON。
  // A 线接上 lib/errcodes.js + UiToast 之后本用例会「意外通过」，
  // 那时请删掉 test.fail() 注解，让它变成硬闸门。
  test.fail()
  await openLogin(page, UNAUTHENTICATED.envelope)
  await submitLogin(page)
  const notice = page.getByTestId('login-error')
  await expect(notice).toBeVisible()
  const text = await notice.innerText()
  expect(text).not.toMatch(/\{|"code"|authentication_required/)
  expect(text.length).toBeGreaterThan(4)
})
