/**
 * R191 判据② · 弹窗那一格真的装上（Bohr 交工第⑥格挂账）
 *
 * 病：R186 从面板侧把拒绝句喂进了弹窗已有的 error prop，剩下那一格它具名报了 ——
 * 「只裁掉一部分」那一支，弹窗打开仍只说「40 行预览」，而同一屏的面板说的是
 * 「全表 120 行中，当前账号可见的 40 行」。把一部分说成全部是 R163 归的 B 类假话，
 * 客户一开弹窗就抓到：两张脸说的是两件不同的事，而其中一张在撒谎。
 *
 * 装法：弹窗新增一枚 rowScope prop（后端 preview.row_scope 的原样载荷：rows_in /
 * rows_visible / code），句子与判据一起走 DocumentPreviewModal.vue 导出的
 * rowScopeVisibleNote()，面板的统计行与弹窗的预览行从此共用同一枚出处。
 *
 * 四条红线：
 *   ① 部分可见 ⇒ 弹窗报「全表 N 行中，当前账号可见的 M 行」，两个数一律来自后端；
 *   ② 真没有（code === '' 且两数皆 0）、全部可见、后端根本没挂这枚键 ⇒ 不插字，
 *      那一行的产物字节与本格装上之前逐字相同；
 *   ③ code === 'row_scope_denied' ⇒ 弹窗说的是后端原句（走已有的 error 通道，排在表格之前），
 *      这一格不许再补一句自己的；后端故意沉默的 no_visible_rows 那一支也不许替它编因由；
 *   ④ 🔴 不许前端数行：给弹窗一行数据、后端说可见 40 行，那一句话仍必须报 40 —— 界面手里
 *      有几行与这张表多大是两件事（R186 教训：读屏上说了什么一律先去标签与注释）。
 *
 * 本弹窗根节点是 <Teleport to="body">：SSR 的真产物在 ctx.teleports.body 那一格里，
 * renderToString 的主返回值只留两枚 teleport 标记（panel-states.test.js 钉着这件事），
 * 所以这里的每一枚断言都从缓冲区读，而不是从主返回值读 —— 读主返回值会静默拿到空串。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, h } from 'vue'
import { readFileSync } from 'node:fs'
import { renderToString } from '@vue/server-renderer'

// 只换网络层：面板走真的 loadDataFiles -> openDataFile -> applyDataPreview。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }
})
vi.mock('../../lib/artifacts', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, fetchArtifactBlob: vi.fn() }
})

import { http } from '../../lib/http'
import DataPanel from '../DataPanel.vue'
import DocumentPreviewModal, { rowScopeVisibleNote } from '../DocumentPreviewModal.vue'

const source = path => readFileSync(new URL(path, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
/** 屏上真正被人读到的那几个字：SSR 会把模板注释一起吐出来。 */
const screen = html => html.replace(/<!--[\s\S]*?-->/g, '').replace(/<[^>]*>/g, '')

const FILENAME = '销售明细.csv'
const COLUMNS = ['月份', '区域', '金额']
const ROW_SCOPE_DENIED = 'row_scope_denied'
const NO_VISIBLE_ROWS = 'no_visible_rows'
/** 后端 message 的原句形状（app/agents/tools.py 那一枚唯一翻译层）。 */
const DENIED_MESSAGE = '本表 3 行属于其他部门，都不在当前账号（部门「财务」）的可见范围内'
/** 无依据字样清单：与 r186 同源 —— 后端没说因由的那一支，界面不许发明因由。 */
const CAUSE_WORDS = ['权限', '可见范围', '部门', '标注', '密级', '不属于']
/** 两张脸共用那一句话的字面（DataPanel 统计行与弹窗预览行必须逐字相同）。 */
const PARTIAL_NOTE = '全表 120 行中，当前账号可见的 40 行'
const NOTE_PATTERN = /全表 \d+ 行中，当前账号可见的 \d+ 行/g

const PROFILE_COLUMNS = [{ name: '月份', dtype: 'object', missing: 0, missing_pct: 0, unique_values: 4 }]

function visibleRows(count) {
  return Array.from({ length: count }, (_row, index) => ({ 月份: `${index + 1} 月`, 区域: '华东', 金额: index + 1 }))
}

/** 后端那一枚 row_scope（code 空串 + 两数不等的常态形状）。 */
const partialScope = { code: '', reason_code: 'department_scope', rows_in: 120, rows_visible: 40 }
const allVisibleScope = { code: '', reason_code: 'department_scope', rows_in: 40, rows_visible: 40 }
const trulyEmptyScope = { code: '', reason_code: 'department_scope', rows_in: 0, rows_visible: 0 }
const deniedScope = {
  code: ROW_SCOPE_DENIED,
  reason_code: 'department_scope',
  rows_in: 3,
  rows_visible: 0,
  message: DENIED_MESSAGE,
}
const noVisibleScope = { code: NO_VISIBLE_ROWS, reason_code: 'department_column_missing', rows_in: 7, rows_visible: 0 }

function previewPayload({ rows, rowScope, empty = false }) {
  const payload = {
    filename: FILENAME,
    columns: COLUMNS,
    rows,
    truncated: false,
    profile: {
      rows: rowScope ? rowScope.rows_visible : rows.length,
      column_count: COLUMNS.length,
      columns: PROFILE_COLUMNS,
      numeric_columns: [],
      text_columns: ['月份'],
      total_missing: 0,
      empty,
    },
  }
  if (rowScope !== undefined) payload.row_scope = rowScope
  return payload
}

const oneFileList = {
  files: [{
    filename: FILENAME,
    size: 10,
    size_label: '10 B',
    modified_at: '2026-09-23T10:00:00+08:00',
    extension: '.csv',
    dataset_id: 'ds-1',
    version_id: 'v-1',
    classification: 'internal',
  }],
}

/** 弹窗自己的真产物：整棵子树在 teleport 缓冲区里。 */
async function renderModal(props) {
  const ctx = {}
  const app = createSSRApp({
    render: () => h(DocumentPreviewModal, {
      open: true,
      filename: FILENAME,
      kind: 'table',
      columns: COLUMNS,
      rows: visibleRows(40),
      ...props,
    }),
  })
  const shell = await renderToString(app, ctx)
  const body = ctx.teleports?.body ?? ''
  // 只认「弹窗口这一格真的进了缓冲区」：被拒那一支连表格都不画，table-meta 由用例自己钉。
  expect(body, '弹窗根节点是 <Teleport to="body">：真产物只可能从缓冲区读，主返回值仅两枚标记').toContain('preview-body')
  return { shell, body, text: screen(body) }
}

/** 走真链路的面板：loadDataFiles -> openDataFile，面板与弹窗在同一次请求的同一份绑定上。 */
async function renderPanel({ list = oneFileList, preview, open = false }) {
  http.get.mockImplementation(async url => (url === '/data-files' ? { data: list } : { data: preview }))
  let bindings = null
  const Capture = defineComponent({
    __name: 'R191DataPanelCapture',
    setup(_props, ctx) {
      bindings = DataPanel.setup({}, ctx)
      return () => null
    },
  })
  await renderToString(h(Capture))
  await bindings.loadDataFiles()
  if (open) await bindings.openDataFile()
  const ctx = {}
  const Probe = defineComponent({ ...DataPanel, __name: 'R191DataPanelProbe', setup: () => bindings })
  const app = createSSRApp(Probe)
  const shell = await renderToString(app, ctx)
  const modal = ctx.teleports?.body ?? ''
  return { shell, modal, text: screen(shell), modalText: screen(modal), bindings }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('R191 判据② · 部分可见那一格：弹窗报得出全表 N 行', () => {
  it('SSR 真产物：预览那一行同时说得出「全表 N」与「可见 M」', async () => {
    const { text, body } = await renderModal({ rowScope: partialScope })
    expect(text).toContain('40 行预览')
    expect(text).toContain(PARTIAL_NOTE)
    expect(body).toMatch(/40 行预览 · 全表 120 行中，当前账号可见的 40 行/)
    // M 不许冒充这张表的总行数，N 也不许被说成预览里真有一百二十行
    expect(text).not.toContain('120 行预览')
  })

  it('🔴 两个数一律来自后端：界面手里只有一行，那一句话仍报 40', async () => {
    const { text } = await renderModal({ rows: visibleRows(1), rowScope: partialScope })
    expect(text).toContain('1 行预览')
    expect(text).toContain(PARTIAL_NOTE)
    expect(text).not.toContain('全表 1 行')
    expect(text).not.toContain('当前账号可见的 1 行')
  })

  it('后端把两数报成字符串也照样说得出口（NaN 与负数都不许冒充行数）', async () => {
    const { text } = await renderModal({ rowScope: { ...partialScope, rows_in: '120', rows_visible: '40' } })
    expect(text).toContain(PARTIAL_NOTE)
    expect(text).not.toContain('NaN')
    const negative = await renderModal({ rowScope: { ...partialScope, rows_in: -5, rows_visible: -1 } })
    expect(negative.text).not.toContain('全表')
  })
})

describe('R191 判据② · 普通情形产物字节逐字不变', () => {
  it('全部可见（code === "" 且 rows_in === rows_visible）：那一行与本格装上之前逐字节相同', async () => {
    const baseline = await renderModal({})
    const scoped = await renderModal({ rowScope: allVisibleScope })
    expect(scoped.body).toBe(baseline.body)
    expect(baseline.text).not.toContain('全表')
  })

  it('真没有（code === "" 且两数皆 0）：不插字，也不许串成权限话', async () => {
    const legacy = await renderModal({ rows: [] })
    const scoped = await renderModal({ rows: [], rowScope: trulyEmptyScope })
    expect(scoped.body).toBe(legacy.body)
    expect(scoped.text).toContain('0 行预览')
    expect(scoped.text).toContain('暂无数据')
    for (const word of CAUSE_WORDS) {
      expect(scoped.text, '真空表被串成了权限话：屏上出现了「' + word + '」').not.toContain(word)
    }
  })

  it('后端根本没挂 row_scope（上传回包、旧响应）：一个字都不许多', async () => {
    const baseline = await renderModal({})
    for (const absent of [undefined, null]) {
      const { body } = await renderModal({ rowScope: absent })
      expect(body).toBe(baseline.body)
    }
  })
})

describe('R191 判据② · 另两支不许被这一格冒充', () => {
  it('row_scope_denied：弹窗说的是后端原句，且这一格一个字都不补', async () => {
    const { text } = await renderModal({ rows: [], error: DENIED_MESSAGE, rowScope: deniedScope })
    expect(text).toContain(DENIED_MESSAGE)
    // error 排在表格那一支之前：被拒的那一屏根本不画表格，也就不该同时出现「全表 N 中 M」
    expect(text).not.toContain('行预览')
    expect(text).not.toContain('全表')
  })

  it('no_visible_rows 且后端故意沉默：弹窗不许替它编因由', async () => {
    const { text } = await renderModal({ rows: [], rowScope: noVisibleScope })
    expect(text).not.toContain('全表')
    for (const word of CAUSE_WORDS) {
      expect(text, '后端沉默的那一支被弹窗编出了因由：屏上出现了「' + word + '」').not.toContain(word)
    }
  })
})

describe('R191 判据② · 两张脸逐字同源（同一次请求、同一份绑定）', () => {
  it('面板统计行说了的那句话，弹窗打开也必须说，且字面一模一样', async () => {
    const preview = previewPayload({ rows: visibleRows(40), rowScope: partialScope })
    const { text, modalText, bindings } = await renderPanel({ preview, open: true })
    expect(bindings.previewOpen.value, '这一条测的是「弹窗打开之后说了什么」').toBe(true)
    expect(bindings.previewScope.value.face).toBe('partial')
    const onPanel = text.match(NOTE_PATTERN)
    const onModal = modalText.match(NOTE_PATTERN)
    expect(onPanel, '面板那一格先失去这句话，弹窗这一格就成了无源之水').toEqual([PARTIAL_NOTE])
    expect(onModal, '🔴 弹窗打开仍只报可见的 M：R186 交工第⑥格挂账的那一句假话回来了').toEqual(onPanel)
    expect(modalText).toContain('40 行预览')
    // 面板不许把这句话补进弹窗已有的 error 通道（两张脸各自说话，不共用一栏）
    expect(bindings.previewModalError.value).toBe('')
  })

  it('关掉弹窗时那句话只在面板一处；后端没挂键时两处都没有', async () => {
    const preview = previewPayload({ rows: visibleRows(40), rowScope: partialScope })
    const closed = await renderPanel({ preview, open: false })
    expect(screen(closed.modal), '没打开的弹窗不该往 body 里写任何人能读到的字').toBe('')
    expect(closed.text.match(NOTE_PATTERN)).toEqual([PARTIAL_NOTE])

    const legacy = previewPayload({ rows: visibleRows(40), rowScope: undefined })
    const legacyRender = await renderPanel({ preview: legacy, open: true })
    expect(legacyRender.text).not.toContain('全表')
    expect(legacyRender.modalText).not.toContain('全表')
    expect(legacyRender.modalText).toContain('40 行预览')
  })

  it('被拒的那一屏：面板与弹窗说的都是后端原句，两处不许变成两句话', async () => {
    const preview = previewPayload({ rows: [], rowScope: deniedScope, empty: true })
    const { text, modalText } = await renderPanel({ preview, open: true })
    expect(text).toContain(DENIED_MESSAGE)
    expect(modalText).toContain(DENIED_MESSAGE)
    expect(modalText).not.toContain('暂无数据')
  })
})

describe('R191 判据②/④ · 接线与出处（源码形状 + builder 真逻辑）', () => {
  it('句子与判据只有一枚出处：面板不再自己拼，弹窗只读后端那三枚键', () => {
    const modal = source('../DocumentPreviewModal.vue')
    const panel = source('../DataPanel.vue')
    const start = modal.indexOf('export function rowScopeVisibleNote')
    expect(start, 'rowScopeVisibleNote 不再是导出函数：两张脸失去了同一枚出处').toBeGreaterThan(-1)
    const note = modal.slice(start, modal.indexOf('\n}', start))
    expect(note).toContain('scope.rows_in')
    expect(note).toContain('scope.rows_visible')
    expect(note).toContain("String(scope.code || '')")
    expect(note).not.toMatch(/rows\.length|props\.rows/)
    expect(modal.match(/全表 \$\{rowsIn\} 行中，当前账号可见的 \$\{rowsVisible\} 行/g)).toHaveLength(1)
    // 面板不再自己拼这句话，也不再自己比这两个数
    expect(panel).not.toMatch(/全表 \$\{/)
    expect(panel).toContain('const rowScopeNote = computed(() => rowScopeVisibleNote(rowScope.value))')
  })

  it('prop 真的接上了：面板递原样载荷，弹窗把句子挂在预览那一行', () => {
    const modal = source('../DocumentPreviewModal.vue')
    const panel = source('../DataPanel.vue')
    expect(panel).toContain(':row-scope="rowScope"')
    expect(modal).toContain('rowScope: {')
    expect(modal).toContain('const rowScopeNote = computed(() => rowScopeVisibleNote(props.rowScope))')
    expect(modal).toContain('{{ rows.length }} 行预览{{ rowScopeSuffix }}')
    // 那句话排在既有的截断提示之前，且不新插一枚 v-if（普通情形才有字节不变的把握）
    expect(modal.indexOf('行预览{{ rowScopeSuffix }}')).toBeLessThan(modal.indexOf('<span v-if="truncated">'))
  })

  it('builder 的取值域逐支对判：只有 code 空串且 0 < M < N 那一支开口', () => {
    expect(rowScopeVisibleNote(partialScope)).toBe(PARTIAL_NOTE)
    expect(rowScopeVisibleNote(null)).toBe('')
    expect(rowScopeVisibleNote({})).toBe('')
    expect(rowScopeVisibleNote({ code: '', rows_in: 40, rows_visible: 40 })).toBe('')
    expect(rowScopeVisibleNote({ code: '', rows_in: 0, rows_visible: 0 })).toBe('')
    expect(rowScopeVisibleNote({ code: '', rows_in: 5, rows_visible: 0 })).toBe('')
    expect(rowScopeVisibleNote({ code: '', rows_in: 40, rows_visible: 60 })).toBe('')
    expect(rowScopeVisibleNote(deniedScope)).toBe('')
    expect(rowScopeVisibleNote(noVisibleScope)).toBe('')
  })

  it('三枚键名与后端构形处同源：弹窗读的就是 data.py 写出去的那几枚', () => {
    const route = source('../../../../app/api/v1/data.py')
    const built = route.slice(route.indexOf('status = {'), route.indexOf('return status'))
    for (const key of ['code', 'reason_code', 'rows_in', 'rows_visible']) {
      expect(built, '后端那一层不再写 ' + key + '：契约与本屏都得重读').toContain('"' + key + '"')
    }
    const modal = source('../DocumentPreviewModal.vue')
    expect(modal).toContain('scope.rows_in')
    expect(modal).toContain('scope.rows_visible')
  })
})
