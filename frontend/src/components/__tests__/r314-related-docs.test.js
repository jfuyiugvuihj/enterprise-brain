/**
 * R314 · 文档预览里的「依据 / 相关制度」那一格（图谱撤下一级入口之后的承接面）
 *
 * 病：计划书 docs/frontend-plan-2026-09-14.md 撤图谱一级入口时承诺「降为文档预览『依据 /
 * 相关制度』子视图」，而承接面一直没装上。结果 /graph 只剩一屏手输主体/关系/客体的表单，
 * 员工不会去手输 —— 图谱这条 V2 能力对普通员工等于没有。
 *
 * 三类证据，各自说清自己验的是什么（本仓没有 jsdom，仓库里既有的手法就是这三条）：
 *   甲 真逻辑：判据函数与 store 直接跑，五枚面（idle / loading / failed / empty / matched）
 *      每一次转场都真走一遍 —— 不需要 DOM 也能验的那部分，这里全都真验了；
 *   乙 真产物：SSR 首屏与关闭态的真字面，外加三面原语拿本格同一份 props 渲出的形状；
 *   丙 源码形状：分支表、取数读法、裸字段名、密级与部门不在界面重算 —— 这四件只有源码能钉，
 *      用例名里也写明它们是形状证据，不假装等价于跑过。
 *
 * 反证（每把摘掉实现里哪一行会红，见用例名与注释）：
 *   1 把读失败伪装成空 → 甲组「读失败那一发」与丙组分支表同时红；
 *   1b 失败那一支改画空态组件 → 丙组「反证 1b」红；
 *   2 认文档从整名改成「包含」→ 甲组「差一个字符就不挂」与「扩展名参与」两枚红；
 *   3 取数换成第二枚读法或第二枚过滤参数（含只筛主体的 source_entity= 旧腿）→ 丙组「反证 3」红；
 *   4 摘掉换文档的迟到回包闸门 → 甲组「迟到的回包丢掉」红；
 *   5 无权限与真坏了共用一张脸（denied 恒 false）→ 甲组「403 与真坏了是两张脸」红；
 *   6 英文眉标抄回屏头 → 丙组「GraphPanel 的英文眉标已清」红；
 *   7 回包形状不对当成空 → 甲组「回包形状不对」红；
 *   8 watch 改回「每次新建的数组」→ 丙组「只盯两枚真源」红。
 *   9 在界面按密级或部门把服务端的裁决重算一遍 → 丙组「密级与部门不在界面重算」红。
 */
import { describe, expect, it, vi } from 'vitest'
import { createSSRApp, h, ref } from 'vue'
import { readFileSync } from 'node:fs'
import { renderToString } from '@vue/server-renderer'

// 只换网络层：api 是 lib/http 那个唯一实例的别名，本格的取数必须真的经过它。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }
})

import { http } from '../../lib/http'
import DocumentPreviewModal, {
  createRelatedDocsStore,
  documentIdentityKey,
  readDocumentRelations,
  relationsAboutDocument,
  relationStatusWord,
} from '../DocumentPreviewModal.vue'
import UiEmptyState from '../ui/UiEmptyState.vue'
import UiErrorState from '../ui/UiErrorState.vue'
import UiLoadingState from '../ui/UiLoadingState.vue'

const source = path => readFileSync(new URL(path, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
/** 屏上真正被人读到的字：SSR 会把模板注释一起吐出来，这里剥掉标签与注释。 */
const screen = html => html.replace(/<!--[\s\S]*?-->/g, '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()

const MODAL = source('../DocumentPreviewModal.vue')
const GRAPH = source('../GraphPanel.vue')

const DOC = '差旅费报销制度.pdf'
const OTHER = '费用科目表.xlsx'
const THIRD = '员工手册.pdf'

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

/** 403 permission_denied 的真形状：与 errcodes 认的那枚信封同源。 */
const deniedError = { response: { status: 403, data: { detail: 'permission_denied' } }, message: 'Request failed with status code 403' }
const brokenError = { response: { status: 503, data: { detail: 'storage_read_only' } }, message: 'Request failed with status code 503' }

// 五枚面的字面：这里各写一次，用例拿它们比对分支归属（同一句话出现在两支上就是顶替）。
const IDLE_COPY = '还没有去查这篇文档的关联。'
const LOADING_COPY = '正在查这篇文档的关联...'
const FAILED_TITLE = '这篇文档的关联没查到'
const DENIED_TITLE = '这个账号看不到关联登记'
const EMPTY_TITLE = '登记的关联里，没有文档名与这篇相同的'

// ==================== 甲 · 认文档 ====================

describe('甲 · 认文档（判据②）：只认同名，认不出就明说认不出', () => {
  it('这篇在主体位、客体位、两端都是它：三种形状都认得出', () => {
    const asSubject = relationsAboutDocument(DOC, [row()])
    const asObject = relationsAboutDocument(DOC, [row({ source_entity: OTHER, target: DOC })])
    const bothEnds = relationsAboutDocument(DOC, [row({ target: DOC })])
    expect(asSubject.map(r => r.role)).toEqual(['source'])
    expect(asObject.map(r => r.role)).toEqual(['target'])
    expect(bothEnds.map(r => r.role)).toEqual(['both'])
    // 对端摊成人能读的样子：这篇自己那一头说「这篇文档」，另一头带上书名号
    expect(asSubject[0].leftName).toBe('这篇文档')
    expect(asSubject[0].rightName).toBe('《' + OTHER + '》')
    expect(asObject[0].leftName).toBe('《' + OTHER + '》')
    expect(asObject[0].rightName).toBe('这篇文档')
  })

  it('差一个字符就不挂：近似名、少扩展名、名字被包住都不算这篇的关联', () => {
    const lookAlikes = [
      '差旅费报销制度',
      '差旅费报销制度.pdfx',
      '新版差旅费报销制度.pdf',
      '差旅费报销制度 doc',
      THIRD,
    ]
    for (const name of lookAlikes) {
      // 两端都不是这篇：无论它长得多么像，一行都不许挂过来
      expect(relationsAboutDocument(DOC, [row({ source_entity: name, target: OTHER })]), name).toEqual([])
      expect(relationsAboutDocument(DOC, [row({ source_entity: OTHER, target: name })]), name).toEqual([])
    }
    // 反过来也一样：这篇是「差旅费报销制度」时，不许挂到 .pdf 那篇的关系上
    expect(relationsAboutDocument('差旅费报销制度', [row()])).toEqual([])
  })

  it('比对时空白与 ASCII 大小写不参与，扩展名参与：差一个字母就是另一篇', () => {
    expect(relationsAboutDocument(' ' + DOC + ' ', [row()])).toHaveLength(1)
    expect(relationsAboutDocument(DOC, [row({ source_entity: DOC.replace('.pdf', '.PDF') })])).toHaveLength(1)
    // 扩展名参与：登记成「费用科目表」的行不属于这篇「费用科目表.xlsx」
    expect(relationsAboutDocument(OTHER, [row({ source_entity: OTHER.replace('.xlsx', ''), target: THIRD })])).toEqual([])
    expect(relationsAboutDocument(OTHER + '（副本）', [row({ source_entity: OTHER, target: THIRD })])).toEqual([])
  })

  it('比对用的形状只此一枚：整名去空白再折叠大小写，扩展名不动', () => {
    expect(documentIdentityKey('  差旅费报销制度.PDF  ')).toBe(documentIdentityKey('差旅费报销制度.pdf'))
    expect(documentIdentityKey('费用科目表')).not.toBe(documentIdentityKey('费用科目表.xlsx'))
    expect(documentIdentityKey(null)).toBe('')
    expect(documentIdentityKey(undefined)).toBe('')
  })

  it('拿不到文档名就等于认不出：空串与未定义零行，不许把全库的行冒充成这篇的', () => {
    const rows = [row(), row({ relation_id: 'rel-2', target: THIRD })]
    for (const name of ['', '   ', null, undefined]) {
      expect(relationsAboutDocument(name, rows), JSON.stringify(name)).toEqual([])
    }
  })

  it('后端给的不是数组、行里有 null：不炸，也不凭空多出行', () => {
    for (const bad of [undefined, null, {}, 'relations', 42]) {
      expect(relationsAboutDocument(DOC, bad)).toEqual([])
    }
    expect(relationsAboutDocument(DOC, [null, undefined, 7, row()])).toHaveLength(1)
  })

  it('行只带本屏自己的字段：登记账号、依据、状态词、日期都在，且不含裸字段名', () => {
    const [first] = relationsAboutDocument(DOC, [row()])
    expect(first).toMatchObject({
      rowKey: 'rel-1',
      linkWord: '适用于',
      evidence: '2026 版制度汇编第 3 章',
      statusWord: '本人登记，还没核对',
      author: 'baiye',
      registeredOn: '2026-09-20',
    })
    expect(Object.keys(first).some(key => key.includes('_'))).toBe(false)
  })

  it('状态词只翻后端在册四枚；翻不出就原样带出那个字，不替它编级别', () => {
    expect(relationStatusWord('candidate')).toBe('本人登记，还没核对')
    expect(relationStatusWord('confirmed')).toBe('登记者已确认')
    expect(relationStatusWord('promoted')).toBe('已核实并提升为口径')
    expect(relationStatusWord('rejected')).toBe('已被驳回')
    expect(relationStatusWord('whatever_the_server_said')).toBe('whatever_the_server_said')
    expect(relationStatusWord('')).toBe('')
    expect(relationStatusWord(null)).toBe('')
  })

  it('登记时间只取日期那一段；不是日期形状就原样带出，不替后端格式化', () => {
    expect(relationsAboutDocument(DOC, [row({ created_at: '2026-09-20T10:00:00+08:00' })])[0].registeredOn).toBe('2026-09-20')
    expect(relationsAboutDocument(DOC, [row({ created_at: '昨天下午' })])[0].registeredOn).toBe('昨天下午')
    expect(relationsAboutDocument(DOC, [row({ created_at: '' })])[0].registeredOn).toBe('')
  })

  it('登记时漏填的格子明说漏填，不留空白让人猜', () => {
    const [onlySubject] = relationsAboutDocument(DOC, [row({ relation: '', source: '', owner_id: '', status: '' })])
    expect(onlySubject.linkWord).toBe('（登记时没填关系）')
    expect(onlySubject.evidence).toBe('')
    expect(onlySubject.statusWord).toBe('')
    // 对端整格没填也明说没填，而不是画一格空白
    const [noObject] = relationsAboutDocument(DOC, [row({ target: '  ' })])
    expect(noObject.rightName).toBe('（登记时没填文档名）')
  })
})

// ==================== 甲 · 五枚面互不顶替 ====================

describe('甲 · 面与面不互相顶替（判据③）：读失败绝不等于「没有关联」', () => {
  it('库里为空 / 有行但对不上名字：两支都是 empty，不是失败也不是 matched', async () => {
    expect((await readDocumentRelations(DOC, async () => [])).face).toBe('empty')
    const nothingMatched = await readDocumentRelations(DOC, async () => [row({ source_entity: THIRD, target: OTHER })])
    expect(nothingMatched.face).toBe('empty')
    expect(nothingMatched.rows).toEqual([])
  })

  it('对得上名字：matched，摆出来的就是交回来的那几行', async () => {
    const result = await readDocumentRelations(DOC, async () => [row(), row({ relation_id: 'rel-2' }), row({ source_entity: OTHER, target: DOC, relation_id: 'rel-3' })])
    expect(result.face).toBe('matched')
    expect(result.rows.map(r => r.rowKey)).toEqual(['rel-1', 'rel-2', 'rel-3'])
    expect(result.message).toBe('')
    expect(result.denied).toBe(false)
  })

  it('🔴 反证 1：读失败就是读失败，face 不是 empty、也不许被冒充成「没有关联」', async () => {
    const result = await readDocumentRelations(DOC, async () => { throw brokenError })
    expect(result.face).toBe('failed')
    expect(result.face).not.toBe('empty')
    expect(result.rows).toEqual([])
    expect(result.denied).toBe(false)
    // 说的话得是「没查到」，而不是「库里没有」
    expect(result.message).not.toBe('')
    expect(result.message).not.toContain(EMPTY_TITLE)
  })

  it('回包形状不对（没有那一格 / 不是数组）也算读失败，不算空', async () => {
    for (const payload of [undefined, {}, { relations: 'nope' }, null]) {
      const result = await readDocumentRelations(DOC, async () => payload?.relations)
      expect(result.face, JSON.stringify(payload)).toBe('failed')
      expect(result.message).toContain('关系列表返回的数据结构不对')
    }
  })

  it('🔴 反证 5：403 与真坏了是两张脸，无权限那一支不给重试的话也另说一句', async () => {
    const denied = await readDocumentRelations(DOC, async () => { throw deniedError })
    const broken = await readDocumentRelations(DOC, async () => { throw brokenError })
    expect(denied.face).toBe('failed')
    expect(denied.denied).toBe(true)
    expect(broken.denied).toBe(false)
    expect(denied.message).not.toBe(broken.message)
    // 无权限也不说成「没有关联」：它说的是这个账号看不到
    expect(denied.message).toContain('看不到')
    expect(denied.message).not.toContain(EMPTY_TITLE)
  })
})

describe('甲 · store 的转场：每一面都真走过一次', () => {
  /** 可控的取数口子：resolve/reject 由用例决定什么时候落地。 */
  function deferred() {
    let resolve = null
    let reject = null
    const promise = new Promise((res, rej) => { resolve = res; reject = rej })
    return { promise, resolve, reject }
  }

  it('初值必是 idle：还没发过请求之前，这一格一个字也不替员工下结论', () => {
    const store = createRelatedDocsStore({ ref, fetchRelations: async () => [] })
    expect(store.state.value.face).toBe('idle')
    expect(store.state.value.rows).toEqual([])
    expect(store.state.value.message).toBe('')
  })

  it('请求在飞的那一刻是 loading，而不是上一轮的结论', async () => {
    const gate = deferred()
    const store = createRelatedDocsStore({ ref, fetchRelations: () => gate.promise })
    const pending = store.load(DOC)
    expect(store.state.value.face).toBe('loading')
    gate.resolve([row()])
    await pending
    expect(store.state.value.face).toBe('matched')
  })

  it('🔴 反证 4：换了一篇文档，上一发的迟到回包丢掉，屏上不挂别人的关联', async () => {
    const first = deferred()
    const second = deferred()
    const queue = [() => first.promise, () => second.promise]
    const store = createRelatedDocsStore({ ref, fetchRelations: () => queue.shift()() })
    const pendingA = store.load(DOC)
    const pendingB = store.load(THIRD)
    expect(store.state.value.face).toBe('loading')
    second.resolve([row({ source_entity: THIRD, target: OTHER })])
    await pendingB
    expect(store.state.value.face).toBe('matched')
    expect(store.state.value.rows.map(r => r.rowKey)).toEqual(['rel-1'])
    first.resolve([row({ relation_id: 'stale', source_entity: DOC, target: OTHER })])
    await pendingA
    // 迟到的一发不许把「员工手册」这一屏换成差旅制度的行
    expect(store.state.value.rows.map(r => r.rowKey)).toEqual(['rel-1'])
  })

  it('关掉这一格就回到 idle：重开先说「还没查」，不把上一篇的行留着冒充', async () => {
    const store = createRelatedDocsStore({ ref, fetchRelations: async () => [row()] })
    await store.load(DOC)
    expect(store.state.value.face).toBe('matched')
    store.reset()
    expect(store.state.value.face).toBe('idle')
    expect(store.state.value.rows).toEqual([])
  })

  it('没有文档名就不开口，也一发请求都不发', async () => {
    const fetchRelations = vi.fn(async () => [row()])
    const store = createRelatedDocsStore({ ref, fetchRelations })
    await store.load('   ')
    expect(fetchRelations).not.toHaveBeenCalled()
    expect(store.state.value.face).toBe('idle')
  })

  it('取数抛错不会变成未处理的拒绝：store 落回 failed 那一面', async () => {
    const store = createRelatedDocsStore({ ref, fetchRelations: async () => { throw new Error('boom') } })
    await store.load(DOC)
    expect(store.state.value.face).toBe('failed')
  })
})

// ==================== 乙 · 真产物 ====================

async function renderModal(props) {
  const ctx = {}
  const app = createSSRApp({ render: () => h(DocumentPreviewModal, { open: true, filename: DOC, kind: 'text', ...props }) })
  const shell = await renderToString(app, ctx)
  const body = ctx.teleports?.body ?? ''
  return { shell, body, text: screen(body) }
}

describe('乙 · 真产物：SSR 首屏、关闭态与三面原语', () => {
  it('SSR 首屏（还没发过请求）：只说「还没有去查」，不提前说「没有关联」也不说「没查到」', async () => {
    const { body, text } = await renderModal({})
    expect(body).toContain('document-relations')
    expect(text).toContain('依据与相关制度')
    expect(text).toContain(IDLE_COPY)
    expect(text).not.toContain(EMPTY_TITLE)
    expect(text).not.toContain(FAILED_TITLE)
    expect(text).not.toContain(DENIED_TITLE)
    expect(text).not.toContain(LOADING_COPY)
  })

  it('SSR 首屏一发请求都不该打出去：这一格的读法只在真浏览器里跑', async () => {
    await renderModal({})
    expect(http.get).not.toHaveBeenCalled()
  })

  it('没打开的弹窗连这一格一起不进 DOM：一个字都不往 body 里写', async () => {
    const { body, text } = await renderModal({ open: false })
    expect(text).toBe('')
    expect(body).not.toContain('document-relations')
    expect(body).not.toContain('依据与相关制度')
  })

  it('三面原语拿本格同一份 props 渲出来：字面各不相同，失败是 alert、空与进行是 status', async () => {
    const failed = await renderToString(h(UiErrorState, { title: FAILED_TITLE, description: '服务暂时读不到登记', retryText: '重新加载', dense: true }))
    const denied = await renderToString(h(UiErrorState, { title: DENIED_TITLE, description: '当前账号看不到这些关联登记，请联系管理员开通。', retryable: false, dense: true }))
    const empty = await renderToString(h(UiEmptyState, { title: EMPTY_TITLE, description: '关联要有人一条条登记，登记过之后就会出现在这里。', dense: true }))
    const loading = await renderToString(h(UiLoadingState, { label: LOADING_COPY, rows: 2, size: 'sm', dense: true }))
    const failedText = screen(failed)
    const deniedText = screen(denied)
    const emptyText = screen(empty)
    const loadingText = screen(loading)
    expect(failedText).toContain(FAILED_TITLE)
    expect(deniedText).toContain(DENIED_TITLE)
    expect(emptyText).toContain(EMPTY_TITLE)
    expect(loadingText).toContain(LOADING_COPY)
    // 四张脸两两不等：任何一张都不许被另一张顶替
    const words = [failedText, deniedText, emptyText, loadingText, IDLE_COPY]
    for (let i = 0; i < words.length; i += 1) {
      for (let j = i + 1; j < words.length; j += 1) expect(words[i]).not.toBe(words[j])
    }
    expect(failed).toMatch(/role="alert"/)
    expect(denied).toMatch(/role="alert"/)
    expect(empty).toMatch(/role="status"/)
    expect(loading).toMatch(/role="status"/)
    // 无权限那张不给重试按钮，真坏了那张才给
    expect(denied).not.toContain('重新加载')
    expect(failed).toContain('重新加载')
  })
})

// ==================== 丙 · 分支表与读法（源码形状） ====================

const asideStart = MODAL.indexOf('<aside class="related-docs"')
const aside = MODAL.slice(asideStart, MODAL.indexOf('</aside>', asideStart))

/** 取某一枚面在自己分支里的正文（从这枚分支的开口到下一枚分支的开口）。 */
function branchCopy(face) {
  const openings = [
    ['loading', "v-if=\"relatedFace === 'loading'\""],
    ['idle', "v-else-if=\"relatedFace === 'idle'\""],
    ['failed', "v-else-if=\"relatedFace === 'failed'\""],
    ['empty', "v-else-if=\"relatedFace === 'empty'\""],
    ['matched', 'v-else class="related-docs-list"'],
  ]
  const index = openings.findIndex(([name]) => name === face)
  expect(index, '分支表里没有这一枚面：' + face).toBeGreaterThan(-1)
  const markerAt = aside.indexOf(openings[index][1])
  expect(markerAt, '分支表里找不到 ' + face + ' 的开口').toBeGreaterThan(-1)
  // 条件写在标签的第二行上：切片得从这枚标签的尖括号开始，否则组件名会被切成半截
  const start = aside.lastIndexOf('<', markerAt)
  const next = openings.slice(index + 1)
    .map(([, marker]) => aside.lastIndexOf('<', aside.indexOf(marker)))
    .filter(at => at > start)
  const end = next.length ? Math.min(...next) : aside.length
  return aside.slice(start, end)
}

describe('丙 · 分支表（判据③，源码形状）：五枚面各占一支、各说各的话', () => {
  it('五枚面按固定顺序排成一条互斥链，matched 是唯一的兜底支', () => {
    const marks = [
      "v-if=\"relatedFace === 'loading'\"",
      "v-else-if=\"relatedFace === 'idle'\"",
      "v-else-if=\"relatedFace === 'failed'\"",
      "v-else-if=\"relatedFace === 'empty'\"",
      'v-else class="related-docs-list"',
    ]
    const at = marks.map(mark => aside.indexOf(mark))
    at.forEach((position, i) => expect(position, '分支缺了 ' + marks[i]).toBeGreaterThan(-1))
    expect(at).toEqual([...at].sort((a, b) => a - b))
    expect(aside.match(/v-else/g)).toHaveLength(4)
  })

  it('每句话只住在自己那一支里：空态那句不许出现在失败支，反之也一样', () => {
    expect(branchCopy('idle')).toContain(IDLE_COPY)
    expect(branchCopy('loading')).toContain(LOADING_COPY)
    expect(branchCopy('failed')).toContain(FAILED_TITLE)
    expect(branchCopy('failed')).toContain(DENIED_TITLE)
    expect(branchCopy('empty')).toContain(EMPTY_TITLE)
    for (const face of ['loading', 'idle', 'empty', 'matched']) {
      const copy = branchCopy(face)
      expect(copy, face + ' 那一支被塞进了失败的话').not.toContain(FAILED_TITLE)
      expect(copy, face + ' 那一支被塞进了无权限的话').not.toContain(DENIED_TITLE)
    }
    const failedCopy = branchCopy('failed')
    expect(failedCopy, '读失败那一支画出了「没有关联」= 判据③那类假话').not.toContain(EMPTY_TITLE)
    expect(failedCopy, '读失败那一支画出了行列表').not.toContain('related-docs-item')
    expect(branchCopy('empty'), '空态那一支画出了行列表').not.toContain('related-docs-item')
  })

  it('🔴 反证 1b：失败支的标题按 denied 分叉，且不回落到空态组件', () => {
    const failedCopy = branchCopy('failed')
    expect(failedCopy).toContain('relatedDenied ?')
    expect(failedCopy).toContain('<UiErrorState')
    expect(failedCopy).not.toContain('<UiEmptyState')
    expect(failedCopy).toContain(':retryable="!relatedDenied"')
    expect(failedCopy).toContain('@retry="readRelatedDocs"')
    expect(branchCopy('empty')).toContain('<UiEmptyState')
    expect(branchCopy('empty')).not.toContain('<UiErrorState')
  })

  it('matched 支只读摊平后的字段，后端裸字段名一个都不上屏', () => {
    const matched = branchCopy('matched')
    for (const field of ['leftName', 'rightName', 'linkWord', 'evidence', 'statusWord', 'author', 'registeredOn']) {
      expect(matched, 'matched 支不再读 row.' + field + '：摊平后的字段与模板脱钩了').toContain('row.' + field)
    }
    expect(matched).not.toMatch(/row\.[a-z]+_[a-z_]+/)
    // 整块这一格（含文案与表达式）都不许出现后端裸字段名
    expect(aside).not.toMatch(/source_entity|relation_id|owner_id|created_at/)
    // 「这篇文档」那一头认得出自己：role 判据在模板里就是这两枚条件
    expect(matched).toContain("row.role !== 'target'")
    expect(matched).toContain("row.role !== 'source'")
  })

  it('屏头不许落英文装饰字（🔴 反证 6：G18 的账，GraphPanel 那行英文眉标也一并清了）', () => {
    expect(aside).toMatch(/<h4>依据与相关制度<\/h4>/)
    expect(aside).not.toMatch(/class="eyebrow"/)
    expect(aside).not.toMatch(/<[a-z]+[^>]*>[A-Za-z][A-Za-z .&-]*<\/[a-z]+>/)
    expect(GRAPH).not.toContain('Knowledge Graph')
    expect(GRAPH).not.toMatch(/class="eyebrow"/)
  })
})

describe('丙 · 取数与不重算（判据①④，源码形状）', () => {
  // 🔴 这枚钉原本写的是「不许带过滤参数」，理由写在注释里：后端那道主体过滤筛不到客体位，
  // 所以只能全量拉回浏览器里筛。R344 把服务端那腿补成任一端命中之后，理由当场没了，这两条
  // not.toMatch 反过来拦住正确的做法。R348 按判据②把它改口成形状判据 —— 不删、不 skip：
  // 读法仍只有一枚、只造得出一个 URL、过滤参数只许 document 一枚、旧腿不许回来。
  it('🔴 反证 3（R348 改口）：关系表读法全文件恰一枚，且只带 document 这一枚过滤参数', () => {
    expect(MODAL.match(/api\.get\(/g)).toHaveLength(1)
    // 唯一的取数出口：那一枚 get 只许把 URL 交给 relationsListingUrl 造，别处不许再拼一套
    expect(MODAL).toContain('api.get(relationsListingUrl(documentName))')
    expect(MODAL.match(/api\.get\([A-Za-z$_]/g)).toHaveLength(1)
    // 查询串只许在一处拼出来：调用点再串一枚 & 参数就是第二套口径
    expect(MODAL.match(/\/knowledge-graph\/relations\?/g)).toHaveLength(1)
    expect(MODAL).not.toMatch(/&(?:relation|source_entity)=/)
    const builder = MODAL.match(/export function relationsListingUrl\(name\) \{([\s\S]*?)\n\}/)
    expect(builder, '关系表的 URL 只许有 relationsListingUrl 这一枚出处').not.toBeNull()
    const url = builder[1].match(/`([^`]*)`/)
    expect(url, '那一枚读法的 URL 是个模板字面量').not.toBeNull()
    const [path, query] = url[1].split('?')
    expect(path).toBe('/knowledge-graph/relations')
    // 过滤参数恰一枚，而且只能是 document：第二枚就是第二套口径
    expect((query ?? '').split('&').filter(Boolean).map(pair => pair.split('=')[0])).toEqual(['document'])
    // 值只许过 encodeURIComponent：登记名原文上线，前端先归一再发就是两把尺子并存
    expect(url[1]).toBe("/knowledge-graph/relations?document=${encodeURIComponent(String(name ?? ''))}")
    // 🔴 旧腿不许回来：source_entity= 只筛主体，会漏掉本篇在客体位的关系，正是当初全量拉的理由
    expect(MODAL).not.toMatch(/source_entity=/)
    expect(MODAL).not.toMatch(/\bapi\.(post|put|delete|patch)\(/)
  })

  it('与 GraphPanel 同一把读法：同一个路径、同一句「不是数组就摆失败态」', () => {
    expect(GRAPH).toContain("api.get('/knowledge-graph/relations')")
    expect(MODAL).toContain('data?.relations')
    expect(GRAPH).toContain('data?.relations')
    expect(MODAL).toContain('Array.isArray(list)')
    expect(GRAPH).toContain('Array.isArray(list)')
  })

  it('密级与部门不在界面重算：本屏不读那几枚键，也不按它们筛行', () => {
    expect(MODAL).not.toMatch(/clearance|department|classification|visibility|principal/)
    const matcher = MODAL.slice(MODAL.indexOf('export function relationsAboutDocument'), MODAL.indexOf('const RELATED_DOCS_IDLE'))
    expect(matcher).not.toMatch(/clearance|department|classification|visibility/)
    expect(aside).not.toMatch(/密级|部门|可见范围/)
  })

  it('这一格不产出任何统计量与自造数字（判据⑤）', () => {
    expect(aside).not.toMatch(/共\s*\d|总览|统计|条关联|占比/)
    expect(screen(aside)).not.toMatch(/\\d+/)
  })

  it('零外部请求：不引 CDN、不引远程字体、不写绝对地址', () => {
    expect(MODAL).not.toMatch(/https?:\/\//)
    expect(MODAL).not.toMatch(/cdn\.|unpkg|jsdelivr|googleapis/)
  })

  it('只盯两枚真源：预览正文的 loading 一变不许再发一发关系表（源码形状）', () => {
    expect(MODAL).toContain('watch([() => props.open, () => props.filename]')
    // watch 一个每次新建的数组等于每次都算「变了」：预览的 loading / text 一换就重发，白白多打几发
    expect(MODAL).not.toMatch(/watch\(\s*\(\)\s*=>\s*\[/)
    // 叫这枚读法开口的只有三处：打开或换文档（watch）、挂载时已经开着、失败那张脸的重试按钮
    expect(MODAL.match(/relatedDocs\.load\(/g)).toHaveLength(3)
    expect(MODAL).not.toMatch(/watch\([^)]*props\.loading/)
  })

  it('样式只借既有 token：这一格的新样式块里没有一枚裸色值', () => {
    const style = MODAL.slice(MODAL.indexOf('<style'), MODAL.indexOf('</style>'))
    const from = style.indexOf('.related-docs {')
    expect(from).toBeGreaterThan(-1)
    const block = style.slice(from)
    expect(block).not.toMatch(/#[0-9a-fA-F]{3}/)
    expect(block).not.toMatch(/\brgba?\(|\bhsla?\(/)
  })
})
