/**
 * R267 · 块 A 判据③（G02）的反证钉：三处写死的字串必须换成服务端字段
 *
 * 原病灶（缺口清单 §6 G02，锚 1142c27 的行号为 DashboardPanel.vue:281-282 与 :307）：
 *   一、每一篇文档都标着「知识库 · 已解析」，后端 parse_status / index_status 根本没人读；
 *   二、指标口径那一格永远显示「高可信」，而 /semantics/match 顶层就回着 definition_source
 *       与 provenance，context.warnings 里还带着「未与已上传制度文件核对」这句原话。
 * 方向同样是「改回假数据就必须红」：把写死字串放回去，或者让 parse_status=failed 的行
 * 仍然长出「已解析」那张脸，本件立刻红。🚫 用 CSS 藏起来不算修——断言全部打在 SSR 产物文本上。
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

const TABLE_WARNING = '定义来自指标定义表 metric_definitions，未与已上传制度文件核对'
const CODE_WARNING = '定义来自代码语义注册表，未与已上传制度文件核对'

function summaryBody() {
  return { generated_for: 'boss', pending_approvals: 0, documents: 3, datasets: 2, alerts: { total: 0, unread: 0 } }
}

function stubRoutes({ catalogRows = [], match = { context: null, definition_source: null, provenance: null } } = {}) {
  http.get.mockImplementation(async (url) => {
    if (url === SUMMARY_PATH) return { status: 200, data: summaryBody() }
    if (url === '/documents/catalog') return { status: 200, data: { documents: catalogRows } }
    if (url === '/alerts') return { status: 200, data: { alerts: [] } }
    throw new Error(`不该被请求的路径：${url}`)
  })
  http.post.mockImplementation(async (url) => {
    if (url === '/semantics/match') return { status: 200, data: match }
    throw new Error(`不该被请求的路径：${url}`)
  })
}

async function loadedPanel(options = {}) {
  stubRoutes(options)
  let bindings = null
  const Host = {
    name: 'R267StatusProbe',
    setup(props, ctx) {
      bindings = DashboardPanel.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Host))
  await bindings.loadDashboard()
  await bindings.lookupMetric()
  return { bindings, html: await renderToString(h({ ...DashboardPanel, setup: () => bindings })) }
}

/** 从真 HTML 里取「最新文档」那一行的两个状态格：解析档与索引档。 */
function docRows(html) {
  const marks = [...html.matchAll(/data-testid="dashboard-doc-row"/g)]
  return marks.map((mark, index) => {
    const start = mark.index
    const end = html.indexOf('data-testid="dashboard-doc-row"', start + 1)
    const block = html.slice(start, end === -1 ? html.indexOf('</section>', start) : end)
    return {
      parse: /data-testid="dashboard-doc-parse"[^>]*>([^<]*)</.exec(block)?.[1] ?? null,
      index: /data-testid="dashboard-doc-index"[^>]*>([^<]*)</.exec(block)?.[1] ?? null,
    }
  })
}

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
})

describe('R267③-a · 最新文档的解析与索引状态读后端字段', () => {
  it('源码形状：写死的「知识库 · 已解析」与行尾那个 <em>已解析</em> 都不许再出现', () => {
    const s = panelSource()
    expect(s).not.toContain('知识库 · 已解析')
    expect(s).not.toMatch(/<em>已解析<\/em>/)
    expect(s).toContain('parseStatusText(item)')
    expect(s).toContain('indexStatusText(item)')
  })

  // 这一屏只摆三行（原设计如此，「查看全部」在卡头上），所以第四档 failed 单独走下一枚用例。
  it('parse_status 的三档各归各的脸，一行一个样，不再一律「已解析」', async () => {
    const rows = [
      { filename: 'a.pdf', parse_status: 'ready' },
      { filename: 'b.pdf', parse_status: 'parsing' },
      { filename: 'c.pdf', parse_status: 'pending' },
    ]
    const { html } = await loadedPanel({ catalogRows: rows })
    expect(docRows(html).map(row => row.parse)).toEqual(['已解析', '正在解析', '排队待解析'])
  })

  it('反证钉：唯一一行解析失败时，状态格里不许出现「已解析」那张脸', async () => {
    const { html } = await loadedPanel({ catalogRows: [{ filename: 'x.pdf', parse_status: 'failed' }] })
    expect(docRows(html)[0].parse).toBe('解析失败')
    expect(html).not.toContain('>已解析<')
  })

  it('后端没回 parse_status 就是「解析状态未知」，不许替它挑一档', async () => {
    const { html } = await loadedPanel({ catalogRows: [{ filename: 'legacy.pdf' }] })
    expect(docRows(html)[0].parse).toBe('解析状态未知')
  })

  it('index_status 三档分明：键整个缺席是「未记录」，不许画成「未索引」', async () => {
    const rows = [
      { filename: 'i.pdf', parse_status: 'ready', index_status: 'indexed' },
      { filename: 'e.pdf', parse_status: 'ready', index_status: 'excluded' },
      { filename: 'u.pdf', parse_status: 'ready', index_status: 'unknown' },
    ]
    const { html } = await loadedPanel({ catalogRows: rows })
    expect(docRows(html).map(row => row.index)).toEqual(['已入检索索引', '未索引', '索引状态未知'])
    const { html: legacyHtml } = await loadedPanel({ catalogRows: [{ filename: 'old.pdf', parse_status: 'ready' }] })
    expect(docRows(legacyHtml)[0].index).toBe('索引状态未记录')
  })
})

describe('R267③-b · 指标口径那一格不再永远「高可信」', () => {
  it('源码形状：「高可信」整枚消失，出处与核对状态一律来自回执字段', () => {
    const s = panelSource()
    expect(s).not.toContain('高可信')
    expect(s).toContain('definition_source')
    expect(s).toContain('verified_against_documents')
    expect(s).toContain('warnings')
  })

  it('代码注册表的口径：绿标不出现，屏上写「未与制度文件核对」与真出处', async () => {
    const { html } = await loadedPanel({
      match: {
        context: { metric_name: '住宿费标准', definition: '每人每晚限额', source_file: '', warnings: [CODE_WARNING] },
        definition_source: 'code_registry',
        provenance: { source: 'code_registry', verified_against_documents: false, warnings: [CODE_WARNING] },
      },
    })
    expect(html).toContain('住宿费标准')
    expect(html).toContain('出处：代码语义注册表')
    expect(html).toContain('未与制度文件核对')
    expect(html).not.toContain('已按制度核对')
    expect(html).not.toContain('高可信')
    expect(html).toContain('data-testid="dashboard-evidence-unverified"')
  })

  it('指标定义表且真核对过的口径才配那颗绿标，并把依据文件一起摆出来', async () => {
    const { html } = await loadedPanel({
      match: {
        context: { metric_name: '差旅费', definition: '含市内交通', source_file: '差旅制度.md', warnings: [] },
        definition_source: 'metric_definitions',
        provenance: {
          source: 'metric_definitions',
          verified_against_documents: true,
          verified_document: '差旅制度.md',
          warnings: [],
        },
      },
    })
    expect(html).toContain('data-testid="dashboard-evidence-verified"')
    expect(html).toContain('已按制度核对')
    expect(html).toContain('依据：差旅制度.md')
    expect(html).not.toContain('未与制度文件核对')
  })

  it('服务端既没说出处也没说核对状态：只许回答「未知」，不许顺手挑一句好听的', async () => {
    const { html } = await loadedPanel({
      match: {
        context: { metric_name: '物料费', definition: '生产领用', source_file: '', warnings: [] },
        definition_source: null,
        provenance: null,
      },
    })
    expect(html).toContain('出处未知')
    expect(html).toContain('出处与核对状态未知')
    expect(html).not.toContain('已按制度核对')
  })

  it('认不出的 definition_source 一律「出处未知」，不翻译成一个看着像的名字', async () => {
    const { html } = await loadedPanel({
      match: {
        context: { metric_name: '外包费', definition: '口径待补', source_file: '', warnings: [TABLE_WARNING] },
        definition_source: 'spreadsheet_tab',
        provenance: { source: 'spreadsheet_tab', verified_against_documents: false, warnings: [TABLE_WARNING] },
      },
    })
    expect(html).toContain('出处未知')
    expect(html).toContain('未与制度文件核对')
  })

  it('查过但没匹配到口径：说的是「没匹配到」，不再挂着那句「查询后显示证据」装没查过', async () => {
    const { html } = await loadedPanel({ match: { context: null, definition_source: null, provenance: null } })
    expect(html).toContain('这个问题没有匹配到已登记的指标口径')
    expect(html).toContain('查询指标口径后显示证据')
  })
})