#!/usr/bin/env node
/**
 * Serve the built frontend from frontend/dist and proxy API/static requests to the
 * latest backend. This is a local acceptance helper, not a production server.
 *
 *   npm --prefix frontend run build
 *   node scripts/serve_latest_frontend.mjs
 *
 * Environment:
 *   EB_API_TARGET     default http://127.0.0.1:18082
 *   EB_FRONTEND_PORT  default 18083
 *   EB_FRONTEND_HOST  default 0.0.0.0 (LAN reachable)
 */
import http from 'node:http'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dist = path.join(root, 'frontend', 'dist')
const apiTarget = new URL(process.env.EB_API_TARGET || 'http://127.0.0.1:18082')
const port = Number(process.env.EB_FRONTEND_PORT || 18083)
const host = process.env.EB_FRONTEND_HOST || '0.0.0.0'

const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.pdf': 'application/pdf',
}

try {
  await fs.access(path.join(dist, 'index.html'))
} catch {
  console.error('frontend/dist is missing. Run: npm --prefix frontend run build')
  process.exit(1)
}

function proxy(request, response) {
  const target = new URL(request.url, apiTarget)
  const upstream = http.request({
    hostname: target.hostname,
    port: target.port || 80,
    path: `${target.pathname}${target.search}`,
    method: request.method,
    headers: { ...request.headers, host: target.host },
  }, (reply) => {
    response.writeHead(reply.statusCode || 502, reply.headers)
    reply.pipe(response)
  })
  upstream.on('error', (error) => {
    if (!response.headersSent) response.writeHead(502, { 'Content-Type': 'text/plain; charset=utf-8' })
    response.end(`upstream unavailable: ${error.message}`)
  })
  request.pipe(upstream)
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url, `http://${request.headers.host || 'localhost'}`)
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/static/')) {
    proxy(request, response)
    return
  }
  try {
    let file = path.join(dist, decodeURIComponent(url.pathname) === '/' ? 'index.html' : decodeURIComponent(url.pathname))
    let body
    try {
      body = await fs.readFile(file)
    } catch {
      file = path.join(dist, 'index.html')
      body = await fs.readFile(file)
    }
    response.writeHead(200, {
      'Content-Type': mime[path.extname(file)] || 'application/octet-stream',
      'Cache-Control': 'no-store',
    })
    response.end(body)
  } catch (error) {
    response.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' })
    response.end(String(error))
  }
})

server.listen(port, host, () => {
  const localHost = host === '0.0.0.0' || host === '::' ? '127.0.0.1' : host
  console.log(`latest frontend: http://${localHost}:${port}/`)
  console.log(`bind address:   ${host}:${port}`)
  console.log(`api target:     ${apiTarget.href}`)
})
