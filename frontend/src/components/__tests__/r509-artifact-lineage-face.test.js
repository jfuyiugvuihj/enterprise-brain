/**
 * R509 · 来源那一格的两张脸（前端判据①的第二形）
 *
 * 后端今天有两枚可空列（migrations/0017：session_id / request_id）：登记过就带上键，没登记就
 * 整格缺席。屏上必须跟着长两张脸，而且**谁也不许顶替谁**：
 *   lineage    -> 「来自 问答 <原值> · 请求 <原值>」，值逐字来自行里那两枚键；
 *   unrecorded -> 「这一条没有登记它是哪一次产生的」，不是「—」、不是 0、不是空串、
 *                 也不是拿创建时间或 owner 猜的一轮。
 * 真渲染那两形在 r503 同名件里跑（它带着 http/artifacts 的 mock 与 setup 夹具，本件不另起第二套），
 * 本件判的是纯函数、模板分支与三把反证刀——刀全落在内存里的源码影子，盘上一字不改。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../../lib/http', () => ({
  http: { get: vi.fn(), delete: vi.fn() },
  errorDetail: vi.fn(() => ''),
  isPermissionDenied: vi.fn(() => false),
}))
vi.mock('../../lib/artifacts', () => ({ fetchArtifactBlob: vi.fn() }))

import { LINEAGE_UNRECORDED_TEXT, lineageView, mapArtifactRow } from '../ArtifactList.vue'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const componentSource = () => read('../../components/ArtifactList.vue')

const FACE_KEYS = ['face', 'text', 'title'].sort()

function apiRow(overrides = {}) {
  return {
    artifact_id: 'a1',
    artifact_type: 'chart',
    filename: '销售额趋势.png',
    content_url: '/api/v1/artifacts/a1/content',
    download_url: '/api/v1/artifacts/a1/download',
    expires_at: null,
    created_at: '2026-09-29T03:12:44.123456+00:00',
    owner_id: 'keeper',
    department_ids: ['finance'],
    classification: 'internal',
    visibility: 'private',
    source_version_id: null,
    ...overrides,
  }
}

/** 从模板里把来源那一格整段摘出来（找不到就红，不给刀空转的机会）。 */
function lineageCell(text) {
  const start = text.indexOf('class="artifact-source"')
  expect(start, '模板里那一格来源不见了').toBeGreaterThan(-1)
  return text.slice(text.lastIndexOf('<span', start), text.indexOf('</span>', start) + 7)
}

describe('R509 · lineageView 的两张脸', () => {
  it('两枚键都有：报得出是哪一次问答、哪一笔请求，且原值一字不改', () => {
    const view = lineageView({ sessionId: 'sess-42', requestId: 'req-42' })
    expect(view.face).toBe('lineage')
    expect(view.text).toContain('问答 sess-42')
    expect(view.text).toContain('请求 req-42')
    expect(Object.keys(view).sort()).toEqual(FACE_KEYS)
  })

  it('只登记了一枚：说得清登记了哪一枚，另一枚不许编', () => {
    const onlyRequest = lineageView({ sessionId: '', requestId: 'req-7' })
    expect(onlyRequest.face).toBe('lineage')
    expect(onlyRequest.text).toContain('请求 req-7')
    expect(onlyRequest.text).not.toContain('问答')
    const onlySession = lineageView({ sessionId: 'sess-7', requestId: '' })
    expect(onlySession.text).toContain('问答 sess-7')
    expect(onlySession.text).not.toContain('请求')
  })

  it('一枚都没有：走 unrecorded 那张脸，正文是一句人话而不是占位符', () => {
    for (const row of [{}, { sessionId: '', requestId: '' }, { sessionId: '   ', requestId: '' }]) {
      const view = lineageView(row)
      expect(view.face).toBe('unrecorded')
      expect(view.text).toBe(LINEAGE_UNRECORDED_TEXT)
      expect(view.text).not.toMatch(/^[\s—-]*$/)
      expect(view.text).not.toBe('0')
    }
  })

  it('映射层：行里没有那两枚键就整格不搬，face 落在 unrecorded', () => {
    const plain = mapArtifactRow(apiRow())
    expect(plain.sessionId).toBe('')
    expect(plain.lineage.face).toBe('unrecorded')
    const lined = mapArtifactRow(apiRow({ session_id: 'sess-1', request_id: 'req-1' }))
    expect(lined.lineage.face).toBe('lineage')
    expect(lined.lineage.text).toContain('sess-1')
  })
})

describe('R509 · 模板那一格：两张脸不并成一格', () => {
  it('两张脸各有各的 class 与 testid，且都由 face 派生', () => {
    const cell = lineageCell(componentSource())
    expect(cell).toContain("item.lineage.face")
    expect(cell).toContain('artifact-source--')
    expect(cell).toContain('data-testid="artifact-lineage"')
    expect(cell).not.toMatch(/String\.fromCharCode/)
  })

  it('那一格没有借创建时间、owner 或访问者身份冒充来源', () => {
    const code = componentSource().replace(/\/\*[\s\S]*?\*\//g, '').split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n')
    const from = code.indexOf('export function lineageView')
    const body = code.slice(from, code.indexOf('\n}', from))
    expect(body).not.toMatch(/created|owner|user_id|principal/)
  })
})

function probeFaceBranch(text) {
  const cell = lineageCell(text)
  expect(cell, '来源那一格不再按 face 分支：两张脸并成一格了').toContain('item.lineage.face')
  expect(cell, '两张脸共用一个类名，屏上分不出来').toContain("'artifact-source--' + item.lineage.face")
}

function probeHonestUnrecordedText(text) {
  const match = /export const LINEAGE_UNRECORDED_TEXT = '([^']*)'/.exec(text)
  expect(match, '找不到「没登记」那句原话').not.toBeNull()
  const value = match[1]
  expect(
    value.trim() === '' || /^[\s\u2014\u2013-]+$/.test(value),
    `占位符冒充了一句人话：${JSON.stringify(value)}`,
  ).toBe(false)
  expect(value).toContain('没有登记')
}

function probeLineageViewUsesOnlyLineage(text) {
  const from = text.indexOf('export function lineageView')
  expect(from, '找不到 lineageView').toBeGreaterThan(-1)
  const body = text.slice(from, text.indexOf('\n}', from))
  expect(body, '来源那一格改用了别的身份顶替血缘列').not.toMatch(/created|owner|principal|user_id/)
  expect(body, '两张脸的 face 不再由血缘键决定').toMatch(/face: 'unrecorded'/)
}

describe('R509 · 对照与三把反证刀（内存影子，盘上零改动）', () => {
  const source = componentSource()

  it('对照：真源码三枚探针全绿', () => {
    probeFaceBranch(source)
    probeHonestUnrecordedText(source)
    probeLineageViewUsesOnlyLineage(source)
  })

  const blade = (anchor, replacement) => {
    expect(source.split(anchor).length - 1, '锚点不唯一或找不到，这把刀会空转').toBe(1)
    return source.replace(anchor, replacement)
  }

  it('刀①：抹掉 face 分支（两张脸并成一格）—— 必须红且点名', () => {
    const crippled = blade(
      "              :class=\"'artifact-source--' + item.lineage.face\"\n",
      '',
    )
    expect(() => probeFaceBranch(crippled)).toThrow(/两张脸|face 分支/)
  })

  it('刀②：把「没登记」那句换成一个破折号 —— 必须红且点名', () => {
    const crippled = blade(
      "export const LINEAGE_UNRECORDED_TEXT = '这一条没有登记它是哪一次产生的'",
      "export const LINEAGE_UNRECORDED_TEXT = '\u2014'",
    )
    expect(() => probeHonestUnrecordedText(crippled)).toThrow(/占位符|没有登记/)
  })

  it('刀③：没登记就拿创建时间凑一轮 —— 必须红且点名', () => {
    const crippled = blade(
      "    return { face: 'unrecorded', text: LINEAGE_UNRECORDED_TEXT, title: LINEAGE_UNRECORDED_TEXT }",
      "    return { face: 'lineage', text: '来自 ' + row.createdAt, title: row.createdAt }",
    )
    expect(() => probeLineageViewUsesOnlyLineage(crippled)).toThrow(/顶替|face 不再由血缘键决定/)
  })
})
