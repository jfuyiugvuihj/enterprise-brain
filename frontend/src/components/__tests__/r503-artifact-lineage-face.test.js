/**
 * R503 · 成果回读链缺两把键：前端这一格的取证钉 + 三把反证刀
 *
 * R509 改口（2026-09-29）：后端给 artifacts 补了两枚可空列 session_id / request_id
 * （migrations/0017），列表行登记过就带这两枚键、没登记就整格缺席。⇒ 「组件里出现这两枚名字」
 * 从「假接入」改判成「只许从行里读、只许这一处读」，本件三条门的牙一枚没少：
 *   P1 视图模型字段全集仍然精确等式（名单同形加三项：sessionId / requestId / lineage）；
 *   P2 那一格时间位的正文仍然只许是时间与有效期（新那一格是另一个 span，探针照旧）；
 *   P3 仍然没有落盘列的那几枚生成键与会话出口照样禁；两枚有列的键换上一把更狠的尺
 *       —— probeLineageOnlyFromTheRow：名字只许在 mapArtifactRow 读行的那两行里出现，
 *          并且 face 必须由这两枚值决定，谁都不许拿 owner / created_at 顶。
 *
 * 现读 @092fb34 的事实（与 tests/test_r503_artifact_lineage_keys.py 同一批凭据）：
 *   一、GET /api/v1/artifacts 的列表行只有 12 枚字段（app/api/v1/artifacts.py:151-165），
 *       里面没有 session_id，也没有 request_id；migrations/0001 的 artifacts 表也没有这两列。
 *   二、所以「这张图是哪一次问答、哪一次计算产生的」今天在前端**无处可画**。
 *       判据③要的「点得回那一次问答」不是少一段模板，是少一枚落盘键 —— 本件因此不改生产码，
 *       只把「不许假接入」这三道门先钉上：
 *         P1 视图模型字段全集精确（多一枚来源键就先红）；
 *         P2 屏上那一格的正文只许是后端真给的时间与有效期（孤立「—」/「0」冒充来源 = 红）；
 *         P3 组件与 lib/artifacts.js 里不许出现会话出口或生成键名（半接线 = 红）。
 *
 * 环境仍是 node + @vue/server-renderer（仓库没有 jsdom / @vue/test-utils，也不许 npm i）。
 * 三把刀全落在**内存里的源码影子副本**（文本替换 + 探针），盘上那两枚文件一个字都不改；
 * 每把刀先把锚点数一遍，锚点不唯一或找不到就判定这把刀空转。对照 = 真源码跑同一套探针，必须全绿。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), delete: vi.fn() } }
})
vi.mock('../../lib/artifacts', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, fetchArtifactBlob: vi.fn() }
})

import { http } from '../../lib/http'
import ArtifactList, { LINEAGE_UNRECORDED_TEXT, mapArtifactRow } from '../ArtifactList.vue'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const componentSource = () => read('../../components/ArtifactList.vue')
const artifactLibSource = () => read('../../lib/artifacts.js')

/** 视图模型今天合法的字段全集（现取 ArtifactList.vue 的 mapArtifactRow；R509 同形加三枚）。 */
const VIEW_KEYS = [
  'artifactId',
  'filename',
  'typeRaw',
  'typeLabel',
  'contentUrl',
  'downloadUrl',
  'createdAt',
  'expiryText',
  'sessionId',
  'requestId',
  'lineage',
].sort()

/** 仍然没有落盘列的生成键，加上会话出口：一出现就是假接入（R509 之后这半条判据一字未改）。 */
const FORBIDDEN = /calculation_run_id|agent_run_id|trace_id|\/sessions\//

/** 0017 已有列的两枚键：只许在「读行」那两行里出现，别处出现＝第二份拼装或拿别人冒充。 */
const BACKED = /session_id|request_id/g
const BACKED_ONCE = /session_id|request_id/
const BACKED_READ_LINES = [
  "sessionId: String(source.session_id || ''),",
  "requestId: String(source.request_id || ''),",
]

/** 模板里那一格「时间/有效期」的正文：只许是后端真给的这两条腿。 */
const META_ANCHOR = '<span class="artifact-meta">'
const MAPPER_ANCHOR = '    expiryText: artifactExpiryText(source.expires_at),'

function templateOf(text) {
  const from = text.indexOf('<template>')
  const to = text.lastIndexOf('</template>')
  expect(from, '组件里找不到模板').toBeGreaterThan(-1)
  return text.slice(from, to)
}

/** meta 段的纯文本：剥掉插值与标签，只看屏上真的会出现的字。 */
function metaText(tpl) {
  const start = tpl.indexOf(META_ANCHOR)
  expect(start, '模板里找不到那一格时间位').toBeGreaterThan(-1)
  const block = tpl.slice(start, tpl.indexOf('</span>', start))
  return block
    .replace(/<[^>]*>/g, ' ')
    .replace(/\{\{[^}]*\}\}/g, ' ')
    .replace(/[·]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

// --------------------------------------------------------------------------- 探针（刀与真件共用）

function probeMapperFieldSet(text) {
  const from = text.indexOf('export function mapArtifactRow')
  expect(from, '找不到 mapArtifactRow').toBeGreaterThan(-1)
  const body = text.slice(from, text.indexOf('\n}', from))
  const keys = [...body.matchAll(/^\s{4}(\w+):/gm)].map(match => match[1])
  expect(
    keys.slice().sort(),
    `视图模型字段全集漂了：${JSON.stringify(keys.slice().sort())}`,
  ).toEqual(VIEW_KEYS)
  return keys
}

/** 两枚有列的键只许从后端行里读，且只在这一处读；face 必须由它们决定。 */
function probeLineageOnlyFromTheRow(text) {
  const code = stripComments(text)
  const hits = code.match(BACKED) || []
  expect(
    hits.length,
    `生成键的名字在组件里被拼了 ${hits.length} 次，只许读行那两行：${JSON.stringify(hits)}`,
  ).toBe(BACKED_READ_LINES.length)
  for (const line of BACKED_READ_LINES) {
    expect(code.split(line).length - 1, `读行那一行漂了：${line}`).toBe(1)
  }
  expect(code, '来源那一格改用了别的身份顶替血缘列').not.toMatch(/lineageView\([^)]*(owner|created|source_id)/)
}

function stripComments(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter(line => !/^\s*\/\//.test(line))
    .join('\n')
}

function probeNoFabricatedLineage(text) {
  const code = stripComments(text)
  expect(code, '没有落盘来源的生成键或会话出口进了组件代码').not.toMatch(FORBIDDEN)
  const meta = metaText(templateOf(code))
  expect(meta, `那一格时间位里出现了冒充来源的残字：${JSON.stringify(meta)}`).toBe('')
}

// --------------------------------------------------------------------------- 判据①的读数：屏上到底有什么

function apiRow(overrides = {}) {
  return {
    artifact_id: 'a1',
    artifact_type: 'chart',
    filename: '销售额趋势.png',
    content_url: '/api/v1/artifacts/a1/content',
    download_url: '/api/v1/artifacts/a1/download',
    expires_at: null,
    created_at: '2026-09-16T03:12:44.123456+00:00',
    owner_id: 'keeper',
    department_ids: ['finance'],
    classification: 'internal',
    visibility: 'private',
    source_version_id: null,
    ...overrides,
  }
}

async function mountedRows(rows) {
  http.get.mockResolvedValue({
    data: { artifacts: rows, total: rows.length, returned: rows.length, limit: 20, offset: 0, has_more: false, artifact_type: null },
  })
  let bindings = null
  const Host = {
    name: 'R503Probe',
    setup(props, ctx) {
      bindings = ArtifactList.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Host))
  await bindings.loadArtifacts()
  return renderToString(h({ ...ArtifactList, setup: () => bindings }))
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('R503 · 后端行的两把键今天不存在，视图模型也不许多造一枚', () => {
  it('P1 真行映射出来的字段全集就是 VIEW_KEYS 那 11 枚，一枚不多（R509 同形加三项）', () => {
    expect(Object.keys(mapArtifactRow(apiRow())).sort()).toEqual(VIEW_KEYS)
  })

  it('P1 没有落盘列的生成键绝不搬进视图模型；有列的两枚照原样搬', () => {
    const forged = apiRow({ calculation_run_id: 'calc-fake', agent_run_id: 'run-fake', trace_id: 'trace-fake' })
    const view = mapArtifactRow(forged)
    expect(Object.keys(view).sort()).toEqual(VIEW_KEYS)
    expect(JSON.stringify(view)).not.toMatch(/calc-fake|run-fake|trace-fake/)

    const backed = mapArtifactRow(apiRow({ session_id: 'sess-1', request_id: 'req-1' }))
    expect(backed.sessionId).toBe('sess-1')
    expect(backed.requestId).toBe('req-1')
    expect(backed.lineage.face).toBe('lineage')
  })

  it('P1 反向钉：行里没有这两枚键，face 必须是 unrecorded，且不许留下空壳', () => {
    const plain = mapArtifactRow(apiRow())
    expect(plain.sessionId).toBe('')
    expect(plain.requestId).toBe('')
    expect(plain.lineage.face).toBe('unrecorded')
    expect(plain.lineage.text).toBe(LINEAGE_UNRECORDED_TEXT)
    expect(plain.lineage.text).not.toBe('')
  })

  it('P2 真渲染一行：屏上只有类型 / 文件名 / 时间，没有任何冒充来源的残字', async () => {
    const html = await mountedRows([apiRow()])
    expect(html).toContain('销售额趋势.png')
    expect(html).toContain('2026-09-16 03:12')
    expect(html).not.toMatch(/sess-fake|req-fake/)
    expect(html).not.toMatch(/\/sessions\//)
    expect(html).not.toMatch(/artifact-meta[^>]*>\s*[—-]\s*</)
    expect(html).not.toMatch(/artifact-meta[^>]*>\s*0\s*</)
  })

  it('P3 组件与取字节层里没有无列的生成键、也没有会话出口（半接线当场红）', () => {
    probeMapperFieldSet(componentSource())
    probeNoFabricatedLineage(componentSource())
    probeLineageOnlyFromTheRow(componentSource())
    expect(FORBIDDEN.test(artifactLibSource()), 'lib/artifacts.js 里出现了生成键或会话出口').toBe(false)
    expect(BACKED_ONCE.test(artifactLibSource()), 'lib/artifacts.js 里出现了生成键').toBe(false)
  })
})

/**
 * R509 落地后补的两形真渲染：同一枚夹具（mountedRows 走 setup + server-renderer），
 * 有血缘与没登记必须长成两张脸。判据①的第一形只有在这里才看得见，纯函数那一半在
 * r509-artifact-lineage-face.test.js。
 */
describe('R509 · 真渲染：来源那一格的两张脸', () => {
  it('有血缘：屏上报得出是哪一次问答、哪一笔请求，走 lineage 那张脸', async () => {
    const html = await mountedRows([apiRow({ session_id: 'sess-42', request_id: 'req-42' })])
    expect(html).toContain('问答 sess-42')
    expect(html).toContain('请求 req-42')
    expect(html).toContain('artifact-source--lineage')
    expect(html).not.toContain('artifact-source--unrecorded')
    expect(html).not.toContain('这一条没有登记它是哪一次产生的')
  })

  it('没血缘（存量行的形状）：明说没登记，且与上一形不是同一张脸', async () => {
    const plain = await mountedRows([apiRow()])
    expect(plain).toContain('artifact-source--unrecorded')
    expect(plain).toContain('这一条没有登记它是哪一次产生的')
    expect(plain).not.toContain('artifact-source--lineage')

    const lined = await mountedRows([apiRow({ session_id: 'sess-42', request_id: 'req-42' })])
    expect(plain).not.toBe(lined)
    expect(plain).not.toMatch(/artifact-source[^>]*>\s*[—-]\s*</)
  })
})

describe('R503 · 对照与三把反证刀（内存影子，盘上零改动）', () => {
  it('对照：真源码两枚探针全绿', () => {
    probeMapperFieldSet(componentSource())
    probeNoFabricatedLineage(componentSource())
  })

  const blade = (name, anchor, replacement) => {
    const text = componentSource()
    const hits = text.split(anchor).length - 1
    expect(hits, `${name}：锚点不唯一或找不到，这把刀会空转`).toBe(1)
    return text.replace(anchor, replacement)
  }

  it('刀①：把「—」塞进那一格时间位冒充来源 —— 必须红且点名', () => {
    const crippled = blade(
      'K1',
      META_ANCHOR,
      META_ANCHOR + '\n              — 本次会话 ',
    )
    expect(() => probeNoFabricatedLineage(crippled)).toThrow(/冒充来源/)
  })

  it('刀②：给 mapArtifactRow 加一枚来源字段（后端根本没交回）—— 必须红且点名', () => {
    const crippled = blade(
      'K2',
      MAPPER_ANCHOR,
      MAPPER_ANCHOR + '\n    sourceText: String(source.session_id || "—"),',
    )
    expect(() => probeMapperFieldSet(crippled)).toThrow(/字段全集漂了/)
    expect(() => probeLineageOnlyFromTheRow(crippled)).toThrow(/生成键的名字在组件里被拼了/)
  })

  it('刀③：手搓一个假的「点得回那一次问答」链接 —— 必须红且点名', () => {
    const crippled = blade(
      'K3',
      META_ANCHOR,
      META_ANCHOR + '\n              <a href="/sessions/sess-fake">回到那一次问答</a> ',
    )
    expect(() => probeNoFabricatedLineage(crippled)).toThrow(/生成键|会话出口/)
  })
})