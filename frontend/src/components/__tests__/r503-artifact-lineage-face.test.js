/**
 * R503 · 成果回读链缺两把键：前端这一格的取证钉 + 三把反证刀
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
import ArtifactList, { mapArtifactRow } from '../ArtifactList.vue'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const componentSource = () => read('../../components/ArtifactList.vue')
const artifactLibSource = () => read('../../lib/artifacts.js')

/** 视图模型今天合法的字段全集（现取 ArtifactList.vue:70-82 的 mapArtifactRow）。 */
const VIEW_KEYS = [
  'artifactId',
  'filename',
  'typeRaw',
  'typeLabel',
  'contentUrl',
  'downloadUrl',
  'createdAt',
  'expiryText',
].sort()

/** 这几枚名字一旦出现在组件或取字节层里，就说明有人在没有落盘来源的情况下接了「生成键」。 */
const FORBIDDEN = /session_id|request_id|calculation_run_id|agent_run_id|trace_id|\/sessions\//

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

function probeNoFabricatedLineage(text) {
  const code = text
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter(line => !/^\s*\/\//.test(line))
    .join('\n')
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
  it('P1 真行映射出来的字段全集就是那 8 枚，一枚不多', () => {
    expect(Object.keys(mapArtifactRow(apiRow())).sort()).toEqual(VIEW_KEYS)
  })

  it('P1 喂一行假装有 session_id / request_id 的响应，视图模型一枚都不搬', () => {
    const forged = apiRow({ session_id: 'sess-fake', request_id: 'req-fake', calculation_run_id: 'calc-fake' })
    const view = mapArtifactRow(forged)
    expect(Object.keys(view).sort()).toEqual(VIEW_KEYS)
    expect(Object.values(view).join(' ')).not.toMatch(/sess-fake|req-fake|calc-fake/)
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

  it('P3 组件与取字节层里没有生成键、也没有会话出口（半接线当场红）', () => {
    probeMapperFieldSet(componentSource())
    probeNoFabricatedLineage(componentSource())
    expect(FORBIDDEN.test(artifactLibSource()), 'lib/artifacts.js 里出现了生成键或会话出口').toBe(false)
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
    expect(() => probeNoFabricatedLineage(crippled)).toThrow(/生成键/)
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