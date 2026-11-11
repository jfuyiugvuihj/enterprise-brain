/**
 * R348 · 文档预览那一格第一次「按这篇问服务端」，且两把尺子不许并存成两套口径
 *
 * 病：R314 每开一篇预览就无参数全量拉 GET /knowledge-graph/relations，再在浏览器里逐行筛。
 * 那笔代价的理由（后端只筛主体、这篇出现在客体位的关系问不到）已经被 R344 补的 `document`
 * 腿拆掉了：现在服务端按任一端命中，把全库拉回浏览器再筛就是白付的代价。
 *
 * 三条口径，逐条对上工单判据：
 *   ① 上到线上的参数值是本篇登记名的**原文**，只过 encodeURIComponent（判据①）。去空白与折叠
 *      大小写是服务端 document_identity_key 的活 —— 前端先归一再发，同一篇文档就两把尺子并存。
 *   ② 客户端那道整名判定留着当 belt（判据③ 选乙），所以本件必须证明两把尺子**逐条同判**。
 *      样本一律现读 R344 那枚成对样本表（tests/test_r344_document_identity_normalization.py），
 *      本件不自编样本：自编一套就是第三把尺子，而那正是要防的东西。选乙不选甲的理由写在回执里。
 *   ③ 服务端筛过之后「交回 0 行」与「这一格读失败」仍是两张不同的脸（判据④）：0 行说的是这篇
 *      没登记过关联，读失败说的是这台服务器没答上来。不许因为「后端会筛」就并成一支。
 *
 * 三类证据（本仓没有 jsdom，手法与 r314 / r343 同）：
 *   甲 真逻辑：URL 真造、store 真跑、两篇文档真抢跑、迟到回包真丢掉；
 *   乙 同判：同一批输入喂给两把尺子，27×27 行的 keep/drop 逐条比；
 *   丙 源码形状：读法枚数、过滤参数枚数、三枚 token 闸门 —— 这三件只有源码能钉。
 *
 * 反证（每把摘掉实现里哪一行会红，实测数字在工单回执里）：
 *   1 把 document= 换成只筛主体的 source_entity= → 丙组「参数恰一枚」与 r314 反证 3 一起红；
 *   2 前端先归一再发（encodeURIComponent 里再套一层归一）→ 甲组「原文上线」两枚红；
 *   3 两把尺子改其一（动前端 documentIdentityKey，或动 R344 表里那一列读数）→ 乙组红；
 *   4 把服务端筛过的 0 行画成读失败，或把读失败画成「没有关联」→ 丙组「三张脸」红；
 *   5 摘掉迟到回包闸门 → 甲组「换两篇」与丙组「反证 5」红；
 *   6 跳转腿另加一枚关系读法（或在调用点再拼一枚参数）→ 丙组「读法恰一枚」红。
 */
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { readFileSync } from 'node:fs'

// 只换网络层：本格不挂载组件（SSR 里这一腿根本不发请求），但这道闸门保证任何时候都不会真出网。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), request: vi.fn() } }
})

import {
  createRelatedDocsStore,
  documentIdentityKey,
  readDocumentRelations,
  relationsAboutDocument,
  relationsListingUrl,
} from '../DocumentPreviewModal.vue'

const source = path => readFileSync(new URL(path, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const MODAL = source('../DocumentPreviewModal.vue')
const R344_TABLES = source('../../../../tests/test_r344_document_identity_normalization.py')

const DOC = '差旅费报销制度.pdf'
const OTHER = '费用科目表.xlsx'
const THIRD = '员工手册.pdf'

const EMPTY_TITLE = '登记的关联里，没有文档名与这篇相同的'
const brokenError = { response: { status: 503, data: { detail: 'storage_read_only' } }, message: 'Request failed with status code 503' }

/** 后端一行关系的形状（app/knowledge_graph/service.py::Relation.to_dict 的子集）。 */
function row(extra = {}) {
  return {
    relation_id: 'rel-1',
    source_entity: DOC,
    relation: '适用于',
    target: OTHER,
    source: '2026 版制度汇编第 3 章',
    owner_id: 'baiye',
    status: 'candidate',
    created_at: '2026-09-20T10:00:00+08:00',
    ...extra,
  }
}

/**
 * 现读 R344 的样本表：按行取 Python 源码里的字符串字面量，再交给 JSON.parse 解 \uXXXX 转义。
 * 表改名、表被削平，这里当场抛错而不是静默少验几枚 —— 那枚表是两把尺子共同的凭据。
 */
function pythonTable(blockName) {
  const start = R344_TABLES.indexOf(blockName + ' = [')
  if (start < 0) throw new Error('R344 的样本表找不到：' + blockName)
  const end = R344_TABLES.indexOf('\n]', start)
  const rows = R344_TABLES.slice(start, end)
    .split('\n')
    .filter(line => /^\s*\(/.test(line))
    .map(line => (line.match(/"(?:[^"\\]|\\.)*"/g) ?? []).map(literal => JSON.parse(literal)))
    .filter(cells => cells.length >= 2)
  if (!rows.length) throw new Error('R344 的样本表扫出零行：' + blockName)
  return rows
}

const PAIRED = pythonTable('PAIRED_SAMPLES')
const SAME_PAIRS = pythonTable('SAME_DOCUMENT_PAIRS')
const DIFFERENT_PAIRS = pythonTable('DIFFERENT_DOCUMENT_PAIRS')

/** 那一枚 URL 上线的参数值：拆出 query、判枚数、decode 回原文。 */
function sentParam(url) {
  const [, query] = url.split('?')
  expect(query, url).toBeDefined()
  const pairs = query.split('&')
  expect(pairs, '过滤参数只许一枚：' + url).toHaveLength(1)
  expect(pairs[0].startsWith('document='), url).toBe(true)
  return decodeURIComponent(pairs[0].slice('document='.length))
}

// ==================== 甲 · 登记名原文上线 ====================

describe('甲 · 参数值是登记名原文（判据①：归一是服务端的活）', () => {
  it('URL 只有那一枚路径与那一枚参数，decode 回来与原文逐字相同', () => {
    for (const raw of [DOC, '  员工手册.PDF  ', '差旅管理办法\u3000PDF', '\ufeff员工手册.pdf', 'STAFF Handbook', '员工\u200b手册']) {
      const url = relationsListingUrl(raw)
      expect(url.split('?')[0], url).toBe('/knowledge-graph/relations')
      expect(sentParam(url), JSON.stringify(raw)).toBe(raw)
    }
  })

  it('🔴 反证 2：原文里的空白、大小写、BOM、零宽字符一律原样上线，不许先归一', () => {
    // 编码形状照既有惯例：encodeURIComponent，空格成 %20，扩展名的大小写原样带上
    expect(relationsListingUrl('Travel Rules .PDF')).toBe('/knowledge-graph/relations?document=Travel%20Rules%20.PDF')
    for (const raw of [' 差旅管理办法.PDF ', '\ufeff员工手册.pdf', '员工\u3000手册', '员工\t手册.pdf', 'Straße.pdf', '\u0130.pdf']) {
      const sent = sentParam(relationsListingUrl(raw))
      expect(sent, JSON.stringify(raw)).toBe(raw)
      // 上线的不是归一后的键：首尾空白、扩展名大小写、BOM、全角空格都还在原处
      expect(sent, JSON.stringify(raw)).not.toBe(documentIdentityKey(raw))
    }
  })

  it('🔴 store 递给取数腿的就是本篇登记名：每开一篇只发一发，两篇就是两发（判据①⑤）', async () => {
    const seen = []
    const store = createRelatedDocsStore({ ref, fetchRelations: async name => { seen.push(name); return [] } })
    await store.load('  差旅管理办法.PDF  ')
    // 这一腿只有既有的那枚 trim；大小写、扩展名、内部空白都不许在发出去之前被抹掉
    expect(seen).toEqual(['差旅管理办法.PDF'])
    expect(sentParam(relationsListingUrl(seen[0]))).toBe('差旅管理办法.PDF')
    expect(seen[0]).not.toBe(documentIdentityKey('差旅管理办法.PDF'))
    await store.load(THIRD)
    expect(seen).toEqual(['差旅管理办法.PDF', THIRD])
    expect(store.state.value.face).toBe('empty')
  })

  it('readDocumentRelations 一个字都不改名字：递给取数腿的就是它收到的那一串', async () => {
    const seen = []
    await readDocumentRelations('员工\u3000手册.PDF', async name => { seen.push(name); return [] })
    expect(seen).toEqual(['员工\u3000手册.PDF'])
  })

  it('没有文档名就一发都不发：?document= 空值在服务端是「谁都不匹配」，不许拿它当「不过滤」', async () => {
    const fetchRelations = vi.fn(async () => [])
    const store = createRelatedDocsStore({ ref, fetchRelations })
    await store.load('   ')
    expect(fetchRelations).not.toHaveBeenCalled()
    expect(store.state.value.face).toBe('idle')
  })
})

// ==================== 乙 · 两把尺子逐条同判 ====================

describe('乙 · 客户端那道 belt 与服务端那把尺子逐条同判（判据③ 选乙）', () => {
  it('样本现读 R344：27 行成对读数、6 对同篇、6 对不同篇，一行都不许缺', () => {
    expect(PAIRED.length).toBeGreaterThanOrEqual(27)
    expect(SAME_PAIRS).toHaveLength(6)
    expect(DIFFERENT_PAIRS).toHaveLength(6)
  })

  it('🔴 反证 3（其一）：成对样本逐条喂给前端那把尺子，读数与表里那一列一字不差', () => {
    for (const [raw, expectedKey] of PAIRED) {
      expect(documentIdentityKey(raw), JSON.stringify(raw)).toBe(expectedKey)
    }
  })

  it('🔴 反证 3（其二）：同篇与不同篇两组配对，前端逐条同判（近似名永不挂上、写法差异永远一篇）', () => {
    for (const [left, right, why] of SAME_PAIRS) {
      expect(documentIdentityKey(left), why).toBe(documentIdentityKey(right))
    }
    for (const [left, right, why] of DIFFERENT_PAIRS) {
      expect(documentIdentityKey(left), why).not.toBe(documentIdentityKey(right))
    }
  })

  it('同一批名字铺成 27×27 行关系表：服务端按表里的读数裁出的行，与客户端留下的行逐条同判', () => {
    const names = PAIRED.map(([raw]) => raw)
    /** 服务端那把尺子的读数 = R344 表里那一列（它自己的件钉着 service.py 必须复现这张表）。 */
    const serverKey = new Map(PAIRED)
    for (const doc of names) {
      const rows = names.map((subject, index) => row({
        relation_id: 'srv-' + index,
        source_entity: subject,
        target: names[(index + 1) % names.length],
      }))
      const docKey = serverKey.get(doc)
      const expected = rows
        .filter(item => {
          // 空身份键匹配不到任何一篇：与服务端 _names_document 里 document_key 为空同一条规矩
          if (!docKey) return false
          return serverKey.get(item.source_entity) === docKey || serverKey.get(item.target) === docKey
        })
        .map(item => item.relation_id)
      const actual = relationsAboutDocument(doc, rows).map(item => item.rowKey)
      expect(actual, '两把尺子不同判：' + JSON.stringify(doc)).toEqual(expected)
    }
  })

  it('belt 不许把服务端裁过的行改口成「没有关联」：命中客体那一篇留得下，服务端回 0 行才空', async () => {
    const rows = [row({ source_entity: THIRD, target: DOC })]
    const hit = await readDocumentRelations(DOC, async () => rows)
    expect(hit.face).toBe('matched')
    expect(hit.rows.map(item => item.role)).toEqual(['target'])
    const hitOtherEnd = await readDocumentRelations(THIRD, async () => rows)
    expect(hitOtherEnd.face).toBe('matched')
    expect(hitOtherEnd.rows.map(item => item.role)).toEqual(['source'])
    const none = await readDocumentRelations(DOC, async () => [])
    expect(none.face).toBe('empty')
    expect(none.rows).toEqual([])
  })
})

// ==================== 丙 · 源码形状 ====================

describe('丙 · 读法枚数、面与闸门（判据④⑤，源码形状）', () => {
  const reader = MODAL.slice(MODAL.indexOf('export async function readDocumentRelations'), MODAL.indexOf('export function createRelatedDocsStore'))

  it('🔴 反证 1：参数只许 document 一枚 —— 换成 source_entity= 当场红', () => {
    expect(MODAL.match(/api\.get\(/g)).toHaveLength(1)
    const builder = MODAL.match(/export function relationsListingUrl\(name\) \{([\s\S]*?)\n\}/)
    expect(builder, 'URL 只许 relationsListingUrl 一枚出处').not.toBeNull()
    const url = builder[1].match(/`([^`]*)`/)
    expect(url, '那一枚读法的 URL 是个模板字面量').not.toBeNull()
    const [path, query] = url[1].split('?')
    expect(path).toBe('/knowledge-graph/relations')
    expect((query ?? '').split('&').filter(Boolean).map(pair => pair.split('=')[0])).toEqual(['document'])
    expect(MODAL).not.toMatch(/source_entity=/)
    expect(MODAL).not.toMatch(/&(?:relation|source-entity)=/)
  })

  it('🔴 反证 6：两条腿共用同一枚读法，全文件只造得出一个 URL', () => {
    expect(MODAL.match(/relationsListingUrl\(/g)).toHaveLength(2)
    expect(MODAL.match(/\/knowledge-graph\/relations\?/g)).toHaveLength(1)
    expect(MODAL).toContain('api.get(relationsListingUrl(documentName))')
    // 三条腿（watch / onMounted / readRelatedDocs）都汇进 relatedDocs.load 这一枚漏斗
    expect(MODAL.match(/relatedDocs\.load\(/g)).toHaveLength(3)
    const jump = MODAL.slice(MODAL.indexOf('function openRelatedDocument'), MODAL.indexOf('/** 回到父组件打开的那一篇'))
    expect(jump).toContain('readRelatedDocs()')
    expect(MODAL).not.toMatch(/api\.get\([^)]*\?/)
  })

  it('🔴 反证 4：服务端筛过之后 0 行仍是 empty，不是读失败；读失败也不许冒充「没有关联」', async () => {
    const empty = await readDocumentRelations(DOC, async () => [])
    expect(empty.face).toBe('empty')
    expect(empty.rows).toEqual([])
    expect(empty.message).toBe('')
    expect(empty.denied).toBe(false)
    const shape = await readDocumentRelations(DOC, async () => ({ relations: 'not a list' }))
    expect(shape.face).toBe('failed')
    expect(shape.message).toContain('关系列表返回的数据结构不对')
    const boom = await readDocumentRelations(DOC, async () => { throw brokenError })
    expect(boom.face).toBe('failed')
    expect(boom.message).not.toContain(EMPTY_TITLE)
    // 判据只认「是不是数组」，不认「有没有长度」：把 0 行并进失败那一支就是这一行被改了
    expect(reader).toContain('if (!Array.isArray(list)) {')
    expect(reader).not.toMatch(/!list\.length|list\.length === 0|list\.length > 0/)
  })

  it('🔴 反证 5：摘掉迟到回包闸门就红 —— 两篇文档抢跑，屏上只留最新那一篇的行', async () => {
    const seen = []
    const release = []
    const gate = index => new Promise(resolve => { release[index] = resolve })
    const store = createRelatedDocsStore({ ref, fetchRelations: async name => { seen.push(name); return gate(seen.length - 1) } })
    const first = store.load(DOC)
    const second = store.load(THIRD)
    expect(store.state.value.face).toBe('loading')
    expect(seen).toEqual([DOC, THIRD])
    release[1]([row({ relation_id: 'fresh', source_entity: THIRD, target: OTHER })])
    await second
    expect(store.state.value.rows.map(item => item.rowKey)).toEqual(['fresh'])
    release[0]([row({ relation_id: 'stale', source_entity: DOC, target: OTHER })])
    await first
    expect(store.state.value.face).toBe('matched')
    expect(store.state.value.rows.map(item => item.rowKey)).toEqual(['fresh'])
    // 三枚 token 闸门（关联腿 / 跳转腿 / 名单腿）一枚不许松
    expect(MODAL.match(/if \(mine !== token\) return/g)).toHaveLength(3)
  })
})
