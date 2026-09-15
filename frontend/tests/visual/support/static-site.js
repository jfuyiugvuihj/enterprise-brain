import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * 从磁盘直接喂 dist 产物，不起 HTTP 服务器（对齐 docs/reference/capture.cjs）。
 * 同时模拟客户内网：远程字体域名一律 abort；/api/** 一律 401。
 */

const HERE = path.dirname(fileURLToPath(import.meta.url))
export const DIST_DIR = path.resolve(HERE, '../../../dist')
export const INDEX_HTML = path.join(DIST_DIR, 'index.html')

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.ttf': 'font/ttf',
  '.map': 'application/json',
}

/** 客户内网拿不到的域名：V1 自托管字体之前，这里必须一直是 abort 状态 */
export const BLOCKED_HOSTS = /fonts\.googleapis\.com|fonts\.gstatic\.com|cdn\.jsdelivr\.net|unpkg\.com/g

/** 三种后端错误形状之①②，用于断言界面不会弹 [object Object] */
export const UNAUTHENTICATED = {
  stringCode: { status: 401, body: '{"detail":"authentication_required"}' },
  envelope: {
    status: 401,
    body: '{"detail":{"code":"authentication_required","message":"请先登录","retryable":false,"details":{}}}',
  },
}

export function distReady() {
  return fs.existsSync(INDEX_HTML)
}

/**
 * @param {import('@playwright/test').BrowserContext} context
 * @param {{ apiReply?: { status: number, body: string }, entry?: string }} options
 */
export async function hostDistFromDisk(context, options = {}) {
  const { apiReply = UNAUTHENTICATED.stringCode, entry = 'index.html' } = options

  await context.route('**/*', async (route) => {
    const url = new URL(route.request().url())

    if (BLOCKED_HOSTS.test(url.hostname)) {
      BLOCKED_HOSTS.lastIndex = 0
      await route.abort('failed')
      return
    }

    if (url.pathname.startsWith('/api/')) {
      await route.fulfill({ status: apiReply.status, contentType: 'application/json', body: apiReply.body })
      return
    }

    const relative = decodeURIComponent(url.pathname).replace(/^\/+/, '') || entry
    const target = path.resolve(DIST_DIR, relative)
    if (!target.startsWith(DIST_DIR) || !fs.existsSync(target) || !fs.statSync(target).isFile()) {
      // SPA 深链回落到 index.html，其余给 404，避免把缺文件伪装成空页面
      if (relative.includes('.')) {
        await route.fulfill({ status: 404, contentType: 'text/plain', body: 'not found' })
        return
      }
      await route.fulfill({ status: 200, contentType: MIME['.html'], body: fs.readFileSync(INDEX_HTML) })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: MIME[path.extname(target).toLowerCase()] || 'application/octet-stream',
      body: fs.readFileSync(target),
    })
  })
}

/** 关动效：除了 reducedMotion 档位，再把 transition/animation 压成 0，保证像素稳定 */
export async function freezeMotion(page) {
  await page.addStyleTag({
    content: [
      '*, *::before, *::after {',
      '  transition: none !important;',
      '  animation: none !important;',
      '  scroll-behavior: auto !important;',
      '}',
    ].join('\n'),
  })
}

/** 记录页面级异常与请求异常，供断言「不崩、不空白」 */
export function collectPageErrors(page) {
  const errors = []
  page.on('pageerror', (error) => errors.push(`pageerror: ${String(error.message).slice(0, 200)}`))
  page.on('requestfailed', (request) => {
    const url = request.url()
    if (BLOCKED_HOSTS.test(url)) {
      BLOCKED_HOSTS.lastIndex = 0
      return
    }
    errors.push(`requestfailed: ${url}`)
  })
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(`console: ${message.text().slice(0, 200)}`)
  })
  return errors
}
