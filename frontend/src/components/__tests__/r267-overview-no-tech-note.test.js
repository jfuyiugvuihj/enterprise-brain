/**
 * R267 · 块 A 判据④（G13）的反证钉：屏幕正文里不许出现源码路径与 HTTP 路由
 *
 * 缺口清单 §4.2 的取证口径（锚 1142c27 的历史坐标，今日该行已不是这一句）：DashboardPanel.vue:175 那句 `.demo-note` 把
 * 「前端常量 src/devFixtures/dashboard-demo.js」和「GET /api/v1/dashboard/summary」
 * 直接印在了员工屏幕上。这条判据的修法只有两种许可：删掉技术细节，或挪进 `<details>`——
 * 但 `<details>` 的正文同样是 DOM 里的可见文本，所以本件的取证一律覆盖整段渲染产物，
 * 挪进去也照样红。🚫 反过来，「演示数据」这块诚实牌连同那一句人话必须留着：
 * 摘牌等于把「这一格还没接线」藏起来，与写假数据同罪。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn() } }
})

import { http } from '../../lib/http'
import DashboardPanel from '../DashboardPanel.vue'
import { SUMMARY_PATH } from '../../lib/dashboard'

const source = name => readFileSync(new URL(name, import.meta.url), 'utf8').replace(/\r?\n/g, '\n')
const panelSource = () => source('../../components/DashboardPanel.vue')

/** 屏幕正文取证：这些串一个都不许出现在员工读到的字里。 */
const VISIBLE_PATTERNS = [
  /src\/[A-Za-z0-9_./-]+\.js/,
  /\bGET \/[a-z]/,
  /\bPOST \/[a-z]/,
  /\/api\//,
  /devFixtures/,
  /dashboard-demo\.js/,
  /parse_status|index_status|definition_source|verified_against_documents/,
  /metric_definitions|code_registry/,
]
/** DOM 取证（连属性一起扫）：data-testid 这类机器名允许，文件名、方法与路由不允许。 */
const DOM_PATTERNS = [
  /src\/[A-Za-z0-9_./-]+\.js/,
  /\bGET \/[a-z]/,
  /\bPOST \/[a-z]/,
  /\/api\//,
  /devFixtures/,
  /dashboard-demo\.js/,
]

function visibleText(html) {
  return html
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

async function loadedHtml() {
  http.get.mockImplementation(async (url) => {
    if (url === SUMMARY_PATH) {
      return { status: 200, data: { generated_for: 'boss', pending_approvals: 1, documents: 2, datasets: 3 } }
    }
    if (url === '/documents/catalog') {
      return { status: 200, data: { documents: [{ filename: '差旅制度.pdf', parse_status: 'ready', index_status: 'indexed' }] } }
    }
    if (url === '/alerts') {
      return { status: 200, data: { alerts: [{ id: 3, message: '华东区差旅费超阈值', created_at: '2026-09-25T09:00:00+08:00' }] } }
    }
    throw new Error(`不该被请求的路径：${url}`)
  })
  http.post.mockImplementation(async (url) => {
    if (url === '/semantics/match') {
      return {
        status: 200,
        data: {
          context: { metric_name: '住宿费标准', definition: '每人每晚', source_file: '', warnings: ['定义来自代码语义注册表，未与已上传制度文件核对'] },
          definition_source: 'code_registry',
          provenance: { source: 'code_registry', verified_against_documents: false },
        },
      }
    }
    throw new Error(`不该被请求的路径：${url}`)
  })
  let bindings = null
  const Host = {
    name: 'R267NoteProbe',
    setup(props, ctx) {
      bindings = DashboardPanel.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Host))
  await bindings.loadDashboard()
  await bindings.lookupMetric()
  return renderToString(h({ ...DashboardPanel, setup: () => bindings }))
}

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
})

describe('R267④ · 屏幕上读不到源码路径与 HTTP 路由', () => {
  it('正文取证：每条技术串 0 命中（含属性与 <details> 在内的整段产物）', async () => {
    const html = await loadedHtml()
    const text = visibleText(html)
    for (const pattern of VISIBLE_PATTERNS) expect(text.match(pattern), `正文命中了 ${pattern}`).toBe(null)
    for (const pattern of DOM_PATTERNS) expect(html.match(pattern), `渲染产物命中了 ${pattern}`).toBe(null)
  })

  // 源码这一腿只钉「会被当成屏幕正文」的东西：模板里的文本节点与注释。
  // <script> 里的实现注释允许写路径（缺口清单 §4.2 数出来的 26 处就是这类，不上屏）。
  it('模板取证：文本节点与模板注释里都没有源码路径、路由与字段名', () => {
    const template = /<template>[\s\S]*<\/template>/.exec(panelSource())?.[0]
    expect(template, '面板应有 <template> 段').toBeTruthy()
    const body = template
      .replace(/<!--[\s\S]*?-->/g, ' ')
      .replace(/<[^>]+>/g, ' ')
    for (const pattern of [...VISIBLE_PATTERNS, /dashboard\/summary/, /\/dashboard/, /\/alerts/]) {
      expect(body.match(pattern), `模板正文命中 ${pattern}`).toBe(null)
    }
  })

  it('诚实牌没被摘：徽标在位、data-testid 在位、那句人话还是句人话', async () => {
    const html = await loadedHtml()
    const text = visibleText(html)
    expect(html).toContain('data-testid="dashboard-demo-flag"')
    expect(html).toContain('class="demo-flag"')
    expect(text).toContain('演示数据')
    const note = /class="demo-note"[^>]*>([^<]{30,})/.exec(html)
    expect(note, '徽标旁边那句说明不许缩成空话').not.toBe(null)
    expect(note[1]).toContain('数据趋势')
  })

  it('说明句只说「哪一格还没接线」，不顺手把其它卡片也打成假的', async () => {
    const html = await loadedHtml()
    const from = html.indexOf('data-testid="dashboard-demo-flag"')
    const block = html.slice(from, html.indexOf('</aside>', from))
    expect(block).toContain('不画线')
    expect(block).toContain('读自服务端')
    expect(block).not.toMatch(/都是假的|全部为演示|仅供参考/)
  })

  it('后端字段名与取值一律洗成中文：屏上出现的是「已解析」「代码语义注册表」这种说法', async () => {
    const text = visibleText(await loadedHtml())
    expect(text).toContain('已解析')
    expect(text).toContain('已入检索索引')
    expect(text).toContain('代码语义注册表')
    expect(text).not.toMatch(/pending|parsing|ready|failed|indexed|excluded/)
  })
})