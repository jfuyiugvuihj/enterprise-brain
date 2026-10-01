/**
 * R338 · 上传回执里那格「这几页 OCR 没跑成」上屏
 *
 * 病灶（行号在基点 466d8a1 现取）：app/api/v1/chat.py:4412 的 _pdf_extraction_cell 早就把【这一次
 * 上传】的逐页读数交出来了（契约 docs/api/contract-v1.md:2342，R301），而 DocPanel.vue:528-533
 * 那一支只取 res.data.status 与 res.data.message —— pdf_extraction 整格没人读。于是员工传一份
 * 有 12 页扫描页、OCR 那一档没跑成的 PDF，屏上只留下一句「上传完成」：那 12 页的内容永远搜不到，
 * 而界面对此一个字都不说。客户第一次装机就会问「明明传了为什么搜不到」。
 *
 * 🔴 这一格【不落库】：rg -n pdf_extraction app/documents/catalog.py 命中 0 处，契约第 4 条
 * （:2390）明写「a reading, not a ledger」。所以本件有三组反向钉，钉的都是这条硬边界：
 *   庚组 不长第二本账 —— 刷新即消失、盘上零留痕、目录行零新增列、也不为它多打一次请求；
 *   己组 一个请求都不多打 —— 带读数与不带读数两次上传，服务器收到的请求逐字相同；
 *   戊组 不顶掉现有那张脸 —— item.status / item.msg / skipped 那几行一字未动，新格只是追加。
 *
 * 判据 ①-⑧ 逐枚对号：甲=①（null 与 {} 分家）乙=②（R298 两档不合并）丙=③（只抄不改口）
 * 丁=④（页码与截断）戊=⑤（不替换）己=⑥（零新增请求）庚=硬边界 辛=⑦⑧（可达性与色值）。
 *
 * 手法沿用 r313 / r288：本仓没有 jsdom、也不 npm i。createRenderer + 内存虚拟节点挂 DocPanel
 * 自己编译出的 setup（onMounted → loadDocs 走产品那一遍），再把 SFC 那份 ssrRender 套在活
 * setupState 上出 HTML —— 判的是真模板产物，不是源码字符串。
 */
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, getCurrentInstance, h, nextTick } from 'vue'
import { renderToString } from '@vue/server-renderer'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() }, authedFetch: vi.fn() }
})

vi.mock('../../lib/artifacts', () => ({
  isArtifactRequest: src => Boolean(src) && String(src).startsWith('artifact:'),
  fetchArtifactBlob: () => new Promise(() => {}),
}))

import DocPanel, {
  PDF_PAGE_LIST_CAP,
  PDF_PAGE_SOURCE_LABEL,
  PDF_PAGE_SOURCE_ORDER,
  hasPdfExtraction,
  pdfExtractionLines,
  pdfPageNumberPhrase,
  pdfSourceCountEntries,
} from '../DocPanel.vue'
import { http } from '../../lib/http'

// ==================== 无 DOM 的真生命周期 + 真模板（r313 同款） ====================

function vnode(tag) {
  return { tag, props: {}, children: [], parent: null, text: '' }
}
const parentOf = target => target.parent

const nodeOps = {
  createElement: tag => vnode(tag),
  createText: text => Object.assign(vnode('#text'), { text }),
  createComment: text => Object.assign(vnode('#comment'), { text }),
  setText: (target, text) => { target.text = text },
  setElementText: (el, text) => { el.children.length = 0; el.text = text },
  parentNode: target => target.parent || null,
  nextSibling(target) {
    const parent = target.parent
    if (!parent) return null
    return parent.children[parent.children.indexOf(target) + 1] || null
  },
  insert(target, parent, anchor) {
    if (target.parent) {
      const from = target.parent.children.indexOf(target)
      if (from >= 0) target.parent.children.splice(from, 1)
    }
    target.parent = parent
    const at = anchor ? parent.children.indexOf(anchor) : -1
    if (at < 0) parent.children.push(target)
    else parent.children.splice(at, 0, target)
  },
  remove(target) {
    const parent = parentOf(target)
    if (parent) {
      parent.children.splice(parent.children.indexOf(target), 1)
      target.parent = null
    }
  },
  patchProp: (el, key, _prev, next) => {
    if (next === null || next === undefined) delete el.props[key]
    else el.props[key] = next
  },
  cloneNode: original => Object.assign(vnode(original.tag), { props: { ...original.props }, text: original.text }),
  insertStaticContent: () => [vnode('#static'), vnode('#static')],
  querySelector: () => null,
  setScopeId: () => {},
}

const { createApp } = createRenderer(nodeOps)
const SSR_CONTEXT_KEY = Symbol.for('v-scx')
let live = null

function mountPanel(props = {}) {
  http.get.mockImplementation(async (url) => (
    String(url).endsWith('/documents/catalog')
      ? { data: { documents: [{ filename: '制度汇编.pdf', owner_id: 'u-1', size_bytes: 2048, parse_status: 'ready', index_status: 'indexed' }] } }
      : { data: {} }
  ))
  http.post.mockImplementation(async () => ({
    data: { status: 'ok', message: '已收录', filename: '制度汇编.pdf', pdf_extraction: null },
  }))
  let instance = null
  const app = createApp({
    __name: 'R338ReadoutHost',
    props: DocPanel.props,
    setup: DocPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div')
    },
  }, props)
  app.config.warnHandler = () => {}
  app.provide(SSR_CONTEXT_KEY, {})
  app.mount(vnode('#root'))
  live = { app, state: instance.setupState }
  return live.state
}

function unmountPanel() {
  if (live) {
    live.app.unmount()
    live = null
  }
}

// 模板注释不上屏（r288 同款剥法）：不先剥掉，注释里那句「这几页 OCR 没跑成」会把断言带偏，
// 测试读到的是注释而不是屏上的字。
const stripComments = html => html.replace(/<!--[\s\S]*?-->/g, '')
const stripTags = html => html.replace(/<[^>]*>/g, '')
const squeeze = text => text.replace(/\s+/g, ' ').trim()
const plainText = html => squeeze(stripTags(stripComments(html)))
const faceRender = name => renderToString(h({
  __name: name,
  setup: () => live.state,
  ssrRender: DocPanel.ssrRender,
}))
const screen = async () => plainText(await faceRender('R338ReadoutFace'))
const screenHtml = async () => stripComments(await faceRender('R338ReadoutHtml'))

async function settle() {
  await nextTick()
  await nextTick()
}

const fileFixture = () => new File(['制度'], '制度汇编.pdf', { type: 'application/pdf' })
const READOUT = 'upload-pdf-readout'
const countOf = (haystack, needle) => haystack.split(needle).length - 1
const lineOf = (cell, key) => pdfExtractionLines(cell).find(line => line.key === key)

/** 一次完整上传：回执里带不带读数由入参决定，其余与今天这一屏实际发生的一模一样。 */
async function runUpload(pdf, extra = {}) {
  // 一次运行一本账：判据⑥比的是【这一发上传】打了哪些请求，不清空就会把上一发的账记到这一发头上。
  http.get.mockClear()
  http.post.mockClear()
  http.delete.mockClear()
  const state = mountPanel()
  await settle()
  http.post.mockImplementation(async () => ({
    data: { status: 'ok', message: '已收录', filename: '制度汇编.pdf', pdf_extraction: pdf, ...extra },
  }))
  await state.uploadSingleFile(fileFixture())
  await settle()
  const out = { state, text: await screen(), html: await screenHtml(), calls: callLog() }
  state.stopUploadPoll()
  return out
}

/** 判据⑥的凭据：本屏打给服务器的每一发，按方法与 URL 记账。 */
function callLog() {
  return {
    get: http.get.mock.calls.map(call => String(call[0])),
    post: http.post.mock.calls.map(call => String(call[0])),
    del: http.delete.mock.calls.map(call => String(call[0])),
  }
}

// ==================== 后端那几枚字面量：现读，不抄快照 ====================

const BACKEND_OCR = readFileSync(new URL('../../../../app/rag/ocr.py', import.meta.url), 'utf8')
const BACKEND_LOADER = readFileSync(new URL('../../../../app/rag/loader.py', import.meta.url), 'utf8')
const SRC = readFileSync(new URL('../DocPanel.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')

function pick(source, re, label) {
  const hit = re.exec(source)
  if (!hit) throw new Error(label)
  return hit[1]
}

/** R298 那两档的句头：降级句的前半截只出自后端，界面一个字都不许自己编（判据②③）。 */
const ENGINE_HEAD = pick(BACKEND_OCR, /ENGINE_UNAVAILABLE_NOTE = "([^"]*)"/, 'ocr.py 里读不到 ENGINE_UNAVAILABLE_NOTE：这一枚钉该改法而不是被跳过')
const DEGRADED_HEAD = pick(BACKEND_LOADER, /DEGRADATION_NOTE_PREFIX = "([^"]*)"/, 'loader.py 里读不到 DEGRADATION_NOTE_PREFIX：这一枚钉该改法而不是被跳过')
/** 后端在线上传出的那五枚桶名（loader.py:73-77），界面不许有第二套词表。 */
const WIRE_BUCKETS = [...BACKEND_LOADER.matchAll(/^PAGE_SOURCE_[A-Z_]+ = "([^"]+)"/gm)].map(hit => hit[1])

// ==================== 四枚形状不同的回执读数 ====================

/** 全文本层、零扫描页：这一档的「没有扫描页」是读出来的，不是造出来的。 */
const CELL_NO_SCAN = {
  page_count: 7, scanned_pages: 0, scanned_page_numbers: [],
  ocr_attempted: false, ocr_available: true, ocr_engine: 'rapidocr_onnxruntime', ocr_dpi: 300,
  source_counts: { 'text-layer': 6, blank: 1 },
  ocr_degraded_page_numbers: [], degradation_note: '',
}

/** 甲档（R298）：引擎不可用 —— 整件扫描页一起没跑成。 */
const CELL_ENGINE_DOWN = {
  page_count: 12, scanned_pages: 2, scanned_page_numbers: [3, 7],
  ocr_attempted: true, ocr_available: false, ocr_engine: 'rapidocr_onnxruntime', ocr_dpi: 300,
  source_counts: { 'text-layer': 10, 'ocr-degraded': 2 },
  ocr_degraded_page_numbers: [3, 7],
  degradation_note: ENGINE_HEAD + '：第3页：rapidocr_onnxruntime 未安装（import 找不到模块）；第7页：rapidocr_onnxruntime 未安装（import 找不到模块）',
}

/** 乙档（R298）：引擎在、就跑这几页没跑成 —— 与甲档必须是两句话（判据②）。 */
const CELL_PAGES_LOST = {
  page_count: 12, scanned_pages: 3, scanned_page_numbers: [3, 7, 12],
  ocr_attempted: true, ocr_available: true, ocr_engine: 'rapidocr_onnxruntime', ocr_dpi: 300,
  source_counts: { 'text-layer': 9, ocr: 1, 'ocr-empty': 1, 'ocr-degraded': 1 },
  ocr_degraded_page_numbers: [12],
  degradation_note: DEGRADED_HEAD + '：第12页：扫描页未送 OCR（本次调用关闭了 OCR 通道）',
}

/** 五枚桶同时在位：判据③点名的 blank 与 ocr-empty 各说各的，就在这一枚里判。 */
const CELL_ALL_FIVE = {
  page_count: 12, scanned_pages: 5, scanned_page_numbers: [3, 5, 7, 9, 12],
  ocr_attempted: true, ocr_available: true, ocr_engine: 'rapidocr_onnxruntime', ocr_dpi: 300,
  source_counts: { 'text-layer': 6, ocr: 2, 'ocr-empty': 1, 'ocr-degraded': 2, blank: 1 },
  ocr_degraded_page_numbers: [9, 12],
  degradation_note: DEGRADED_HEAD + '：第9页：图像页 OCR 失败：Timeout；第12页：扫描页未送 OCR（本次调用关闭了 OCR 通道）',
}

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
  http.delete.mockReset()
  live = null
})

afterEach(() => {
  if (live) live.state.stopUploadPoll()
  unmountPanel()
})

// 注释与代码分开判：本屏的注释里写着「不许写 localStorage」「catalog.py 对 pdf_extraction 零命中」，
// 那些是给人看的说明，不是行为。反向钉一律判这份剥掉注释之后的代码。
const CODE = SRC
  .replace(/<!--[\s\S]*?-->/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/\/\/[^\n]*/g, '')

// ==================== 甲 · 一格不多一格不少（判据①） ====================

describe('R338 甲 · null 就是没读过，整格一笔都不画', () => {
  it('.docx / .txt 那一支（回执 pdf_extraction = null）：屏上找不到这一格的任何一个字', async () => {
    const run = await runUpload(null)
    expect(run.html).not.toContain(READOUT)
    expect(run.text).not.toContain('扫描页')
    expect(run.text).not.toContain('逐页来源')
    expect(run.text).not.toContain('本次共')
    expect(run.state.uploads[0].pdfLines).toEqual([])
  })

  it('键整个缺席（老部署只回一串字段）与 null 同判：一样不画', async () => {
    const state = mountPanel()
    await settle()
    http.post.mockImplementation(async () => ({ data: { status: 'ok', message: '已收录', filename: '制度汇编.pdf' } }))
    await state.uploadSingleFile(fileFixture())
    await settle()
    expect(await screenHtml()).not.toContain(READOUT)
    state.stopUploadPoll()
  })

  it('纯函数这一层：null / undefined / 数组 / 字符串 / 数字都没有读数，返回空数组', () => {
    for (const cell of [null, undefined, [], ['ocr'], 'ocr-degraded', 0, 12, true]) {
      expect(pdfExtractionLines(cell), '这一枚不该有读数：' + String(cell)).toEqual([])
      expect(hasPdfExtraction(cell), '这一枚不该被当成读数：' + String(cell)).toBe(false)
    }
  })

  it('🔴 {} 这一档不当 null 兜：这一格在屏上，但说的全是「读不到」，一个 0 也没有', async () => {
    const run = await runUpload({})
    expect(run.html).toContain(READOUT)
    expect(run.text).toContain('总页数读不到')
    expect(run.text).toContain('扫描页读不到')
    expect(run.text).toContain('逐页来源读不到')
    expect(run.text).not.toContain('0 页')
    expect(run.text).not.toContain('没有扫描页')
  })

  it('scanned_pages 真是 0：那句「没有扫描页」是读出来的，不是替后端造的', async () => {
    const run = await runUpload(CELL_NO_SCAN)
    expect(run.text).toContain('本次共 7 页')
    expect(run.text).toContain('没有扫描页')
    expect(run.text).toContain('逐页来源：文字层出字 6 页 · 既无文字层也无图像 1 页')
    expect(run.html).not.toContain('data-pdf-line="degradation"')
  })

  it('两条一起传：只有带回读的那一条画这一格，另一条一个字都不补', async () => {
    const state = mountPanel()
    await settle()
    http.post.mockImplementation(async () => ({ data: { status: 'ok', message: '已收录', filename: '制度汇编.pdf', pdf_extraction: CELL_PAGES_LOST } }))
    http.post.mockImplementationOnce(async () => ({ data: { status: 'ok', message: '已收录', filename: '制度汇编.pdf', pdf_extraction: null } }))
    await state.uploadFilesParallel([fileFixture(), fileFixture()])
    await settle()
    expect(countOf(await screenHtml(), READOUT)).toBe(1)
    expect(state.uploads.filter(item => item.pdfLines.length)).toHaveLength(1)
    state.stopUploadPoll()
  })
})

// ==================== 乙 · R298 的两档不合并（判据②） ====================

describe('R338 乙 · 引擎不可用与这几页没跑成，是两句不同的话', () => {
  it('甲档（ocr_available=false）：上屏第一句就是后端 ENGINE_UNAVAILABLE_NOTE 那一句', async () => {
    const run = await runUpload(CELL_ENGINE_DOWN)
    expect(run.text).toContain(ENGINE_HEAD)
    expect(run.html).toContain('data-pdf-line="degradation"')
    expect(run.html).toContain('data-pdf-tone="warn"')
  })

  it('乙档（引擎在、这几页没跑成）：说的是「扫描页 OCR 降级」，不是「OCR 未启用」', async () => {
    const run = await runUpload(CELL_PAGES_LOST)
    expect(run.text).toContain(DEGRADED_HEAD)
    expect(run.text).not.toContain('未启用')
    expect(run.text).not.toContain('不可用')
    expect(run.text).not.toContain(ENGINE_HEAD)
  })

  it('🔴 两档各自成句、互不串词：把任何一档写成另一档的措辞，这一枚当场红', () => {
    const down = lineOf(CELL_ENGINE_DOWN, 'degradation')
    const lost = lineOf(CELL_PAGES_LOST, 'degradation')
    expect(down.lead.startsWith(ENGINE_HEAD)).toBe(true)
    expect(lost.lead.startsWith(DEGRADED_HEAD)).toBe(true)
    expect(down.lead).not.toBe(lost.lead)
    expect(down.lead).not.toContain(DEGRADED_HEAD)
    expect(lost.lead).not.toContain(ENGINE_HEAD)
  })

  it('data-pdf-ocr-available 原样回带布尔：false 与 true 分得开，不拿 false 冒充「没读到」', async () => {
    expect((await runUpload(CELL_ENGINE_DOWN)).html).toContain('data-pdf-ocr-available="false"')
    expect((await runUpload(CELL_PAGES_LOST)).html).toContain('data-pdf-ocr-available="true"')
    expect((await runUpload({ page_count: 1, scanned_pages: 0 })).html).toContain('data-pdf-ocr-available=""')
  })
})

// ==================== 丙 · 只抄不改口（判据③） ====================

/** 走一遍真实入口，只看桶名：确认「缺席不画」这条走的是同一份算法。 */
function wordsIn(cell) {
  return lineOf(cell, 'sources').entries.map(entry => entry.word)
}

describe('R338 丙 · 降级说明只抄原文，桶一枚一说不合并', () => {
  it('降级那一行的每一个字都等于回执里的 degradation_note（=== 而不是「差不多」）', () => {
    for (const cell of [CELL_ENGINE_DOWN, CELL_PAGES_LOST, CELL_ALL_FIVE]) {
      const line = lineOf(cell, 'degradation')
      expect(line, '这一枚回应有降级句却没上屏').toBeTruthy()
      expect(line.lead).toBe(cell.degradation_note)
    }
  })

  it('判的是模板产物：上屏的纯文本里就是那句原文', async () => {
    expect((await runUpload(CELL_PAGES_LOST)).text).toContain(CELL_PAGES_LOST.degradation_note)
  })

  it('五枚桶一枚一句、五句两两不同，合计就是 page_count（判据③点名的不合并）', async () => {
    const entries = pdfSourceCountEntries(CELL_ALL_FIVE.source_counts)
    expect(entries.map(entry => entry.word)).toEqual([...PDF_PAGE_SOURCE_ORDER])
    expect(new Set(entries.map(entry => entry.text)).size).toBe(5)
    expect(entries.reduce((sum, entry) => sum + entry.count, 0)).toBe(CELL_ALL_FIVE.page_count)
    const run = await runUpload(CELL_ALL_FIVE)
    expect(countOf(run.html, 'data-pdf-source="')).toBe(5)
    expect(run.text).toContain('既无文字层也无图像 1 页')
    expect(run.text).toContain('OCR 跑了没检出字 1 页')
    expect(run.text).toContain('OCR 没跑成 2 页')
  })

  it('回执里没有的桶不替它补一句「0 页」：缺席就是没说，界面不许替后端说', async () => {
    const run = await runUpload(CELL_NO_SCAN)
    expect(run.text).not.toContain('OCR 出字')
    expect(run.text).not.toContain('OCR 跑了没检出字')
    expect(run.text).not.toContain('OCR 没跑成')
    expect(wordsIn(CELL_NO_SCAN)).toEqual(['text-layer', 'blank'])
  })

  it('词表不外扩：界面上那几枚桶名与后端 loader 的字面量一一对应', () => {
    expect(WIRE_BUCKETS.length).toBeGreaterThanOrEqual(5)
    expect([...PDF_PAGE_SOURCE_ORDER].sort()).toEqual([...WIRE_BUCKETS].sort())
    expect(Object.keys(PDF_PAGE_SOURCE_LABEL).sort()).toEqual([...WIRE_BUCKETS].sort())
    expect(new Set(Object.values(PDF_PAGE_SOURCE_LABEL)).size).toBe(WIRE_BUCKETS.length)
  })

  it('后端若添了第六枚桶，界面按原词上屏 —— 宁可看不懂，也不静默丢掉一格读数', () => {
    const entries = pdfSourceCountEntries({ 'text-layer': 3, 'future-bucket': 2 })
    expect(entries.map(entry => entry.word)).toEqual(['text-layer', 'future-bucket'])
    expect(entries[1].text).toContain('future-bucket')
    expect(entries[1].text).toContain('2 页')
  })

  it('桶里的条数读不到（非数字）时说「读不到」，不画成 0 页', () => {
    const entries = pdfSourceCountEntries({ 'text-layer': null, blank: 'x' })
    expect(entries.map(entry => entry.text)).toEqual(['文字层出字读不到', '既无文字层也无图像读不到'])
  })
})

// ==================== 丁 · 页码说人话与截断（判据④） ====================

describe('R338 丁 · 页码可核对，总数只从读数来', () => {
  const shownPages = phrase => phrase.replace(/^第 /, '').replace(/ 页.*$/, '').split('、').map(Number)

  it('三页：画成「第 3、7、12 页」这种能逐页核对的写法', async () => {
    const run = await runUpload(CELL_PAGES_LOST)
    expect(run.text).toContain('第 3、7、12 页')
    expect(lineOf(CELL_PAGES_LOST, 'tally').lead).toContain('扫描页 3 页 · 第 3、7、12 页')
  })

  it('恰好到截断线：一枚不截，也就不说「另有」', () => {
    const exact = Array.from({ length: PDF_PAGE_LIST_CAP }, (_page, index) => index + 1)
    const phrase = pdfPageNumberPhrase(exact)
    expect(phrase).toBe('第 ' + exact.join('、') + ' 页')
    expect(phrase).not.toContain('另有')
  })

  it('超过截断线：只列前若干枚，尾巴一句「另有 N 页未列出」就是没画下的那几页', async () => {
    const wide = {
      ...CELL_PAGES_LOST,
      page_count: 60,
      scanned_pages: 40,
      source_counts: { 'text-layer': 20, 'ocr-degraded': 40 },
      scanned_page_numbers: Array.from({ length: 40 }, (_page, index) => index + 1),
    }
    const phrase = pdfPageNumberPhrase(wide.scanned_page_numbers)
    expect(shownPages(phrase)).toHaveLength(PDF_PAGE_LIST_CAP)
    expect(Number(/另有 (\d+) 页/.exec(phrase)[1])).toBe(40 - PDF_PAGE_LIST_CAP)
    const run = await runUpload(wide)
    expect(run.text).toContain('扫描页 40 页')
    expect(run.text).toContain('另有 ' + (40 - PDF_PAGE_LIST_CAP) + ' 页未列出')
    expect(run.text).not.toContain('11、12、13 页')
  })

  it('🔴 总数只从 scanned_pages / page_count 来：列表比读数短时，绝不拿列表长度冒充总数', () => {
    const short = { ...CELL_PAGES_LOST, scanned_pages: 40, scanned_page_numbers: [1, 2, 3] }
    const lead = lineOf(short, 'tally').lead
    expect(lead).toContain('扫描页 40 页')
    expect(lead).toContain('第 1、2、3 页')
    expect(lead).not.toContain('另有')
  })

  it('总数读不到时页码清单照旧上屏：藏掉它就是替客户把「没读到」说成「没有这回事」', () => {
    const lead = lineOf({ scanned_page_numbers: [1, 2, 3], source_counts: {} }, 'tally').lead
    expect(lead).toContain('总页数读不到')
    expect(lead).toContain('扫描页读不到')
    expect(lead).toContain('第 1、2、3 页')
    expect(lead).not.toMatch(/扫描页 \d+ 页/)
  })

  it('清单里的垃圾（null / 0 / 负数 / 非数字）不当页码画；字符串数字照收', () => {
    expect(pdfPageNumberPhrase([3, null, '7', 0, -1, 'x', 12])).toBe('第 3、7、12 页')
    expect(pdfPageNumberPhrase([])).toBe('')
    expect(pdfPageNumberPhrase(undefined)).toBe('')
  })
})

// ==================== 戊 · 不许顶掉现有那张脸（判据⑤） ====================

describe('R338 戊 · 新格是追加，不是替换', () => {
  it('done 那一支：✅、「已收录」、进度那一行全在，新格只往下追加', async () => {
    const run = await runUpload(CELL_PAGES_LOST)
    expect(run.state.uploads[0].status).toBe('done')
    expect(run.html).toContain('✅')
    expect(run.text).toContain('已收录')
    expect(run.text).toContain('上传完成')
    expect(run.text).toContain('本次共 12 页')
    expect(run.html).toContain(READOUT)
  })

  it('skipped 那一支：⏭️ 与后端那句 message 一字未动，这一发没被新格抬成成功', async () => {
    const run = await runUpload(CELL_PAGES_LOST, { status: 'skipped', message: '这一版按策略不入索引' })
    expect(run.state.uploads[0].status).toBe('skipped')
    expect(run.html).toContain('⏭️')
    expect(run.html).not.toContain('✅')
    expect(run.text).toContain('这一版按策略不入索引')
    expect(run.text).toContain(DEGRADED_HEAD)
  })

  it('在途那一条还没回执 ⇒ 整格不画；回执一落地才追加（不许提前把「0 页」摆出来）', async () => {
    const state = mountPanel()
    await settle()
    let release = null
    http.post.mockImplementation(() => new Promise(resolve => { release = resolve }))
    const flying = state.uploadSingleFile(fileFixture())
    await settle()
    expect(release, '这一发没挂起，在途判据就没测到').toBeTruthy()
    expect(state.uploads[0].pdf).toBeNull()
    expect(await screenHtml()).not.toContain(READOUT)
    release({ data: { status: 'ok', message: '已收录', filename: '制度汇编.pdf', pdf_extraction: CELL_ENGINE_DOWN } })
    await flying
    await settle()
    expect(await screenHtml()).toContain(READOUT)
    state.stopUploadPoll()
  })

  it('失败那一支没有回执可读 ⇒ 不画，也不拿上一发的值留着', async () => {
    const state = mountPanel()
    await settle()
    http.post.mockImplementation(async () => { throw Object.assign(new Error('boom'), { response: { status: 500 } }) })
    await state.uploadSingleFile(fileFixture())
    await settle()
    expect(state.uploads[0].status).toBe('error')
    expect(state.uploads[0].pdf).toBeNull()
    expect(await screenHtml()).not.toContain(READOUT)
    state.stopUploadPoll()
  })

  it('源码级：回执那两行（status / msg）没被这一格动过，新格只有一枚写点', () => {
    expect(SRC).toMatch(/item\.status = res\.data\.status === 'ok' \? 'done' : 'skipped'/)
    expect(SRC).toMatch(/item\.msg = res\.data\.message \|\| '上传完成'/)
    expect(CODE).toMatch(/item\.pdf = res\.data\.pdf_extraction \?\? null/)
    expect(countOf(SRC, 'item.pdf = ')).toBe(1)
    expect(countOf(SRC, 'item.pdfLines = ')).toBe(1)
  })
})

// ==================== 己 · 零新增请求（判据⑥） ====================

describe('R338 己 · 这一格一个请求都不许多打', () => {
  it('带读数与不带读数两次上传，服务器收到的每一发逐字相同', async () => {
    const withCell = await runUpload(CELL_PAGES_LOST)
    const without = await runUpload(null)
    expect(withCell.calls).toEqual(without.calls)
    expect(withCell.calls.post).toEqual(['/upload'])
  })

  it('画完再画、反复重绘，也不会冒出第二发请求', async () => {
    const run = await runUpload(CELL_PAGES_LOST)
    const before = callLog()
    await screen()
    await screenHtml()
    await screen()
    expect(callLog()).toEqual(before)
  })

  it('本屏全部请求的 URL 里都不许出现「第二本账」要读的那一列', () => {
    const requestLines = CODE.split('\n').filter(line => /http\.(get|post|delete)\(/.test(line))
    expect(requestLines).toHaveLength(5)
    expect(requestLines.join('\n')).not.toMatch(/pdf|extraction/i)
  })

  it('pdf_extraction 这一枚键在本屏只被读过一次，而且只从回执读', () => {
    expect(countOf(SRC, 'res.data.pdf_extraction')).toBe(1)
  })
})

// ==================== 庚 · 不落第二本账（硬边界） ====================

describe('R338 庚 · 这一格只活在刚回来的那次回执里', () => {
  it('刷新（重新挂载一次面板）之后必须消失：读不到就是读不到', async () => {
    const run = await runUpload(CELL_PAGES_LOST)
    expect(run.html).toContain(READOUT)
    unmountPanel()
    const second = mountPanel()
    await settle()
    const html = await screenHtml()
    const text = await screen()
    expect(html).not.toContain(READOUT)
    expect(text).not.toContain('扫描页')
    expect(text).not.toContain('逐页来源')
    second.stopUploadPoll()
  })

  it('「清除已完成」之后这一格一起消失，不留尾巴', async () => {
    const run = await runUpload(CELL_PAGES_LOST)
    expect(run.html).toContain(READOUT)
    run.state.clearUploads()
    await settle()
    expect(await screenHtml()).not.toContain(READOUT)
  })

  it('这一格只长在上传那一条上：目录区里一个读数节点都没有', async () => {
    const run = await runUpload(CELL_PAGES_LOST)
    const listAt = run.html.indexOf('document-list')
    expect(listAt).toBeGreaterThan(-1)
    expect(run.html.slice(listAt)).not.toContain(READOUT)
    expect(run.html.slice(listAt)).not.toContain('扫描页')
    expect(countOf(run.html, READOUT)).toBe(1)
  })

  it('目录行那一句真值仍是 R313 那三格，没被塞进第四格', async () => {
    const truthOf = html => squeeze((/data-testid="doc-row-truth"[^>]*>([\s\S]*?)<\/p>/.exec(html) || [])[1] || '')
    const withCell = truthOf((await runUpload(CELL_PAGES_LOST)).html)
    const without = truthOf((await runUpload(null)).html)
    expect(withCell).toBeTruthy()
    expect(withCell).toBe(without)
    expect(withCell).not.toMatch(/OCR|扫描/)
  })

  it('盘上零留痕：这一格的上传路径一次都没写过 localStorage', async () => {
    const writes = []
    globalThis.localStorage = {
      setItem: (...args) => writes.push(args),
      getItem: () => null,
      removeItem: () => {},
      clear: () => {},
      key: () => null,
      length: 0,
    }
    try {
      const run = await runUpload(CELL_PAGES_LOST)
      expect(run.html).toContain(READOUT)
    } finally {
      delete globalThis.localStorage
    }
    expect(writes).toEqual([])
  })

  it('源码级：这一屏不碰任何缓存介质（注释里那句「不许写」不算数）', () => {
    expect(CODE).not.toMatch(/localStorage|sessionStorage|indexedDB|indexedDb/)
  })
})

// ==================== 辛 · 可达性与色值（判据⑦⑧） ====================

describe('R338 辛 · 读屏念得到，而且没带进新色值', () => {
  it('容器 role="status"，⚠ 只是装饰（aria-hidden），降级那句在纯文本里就读得到', async () => {
    const run = await runUpload(CELL_ENGINE_DOWN)
    expect(run.html).toMatch(/class="up-pdf"[^>]*role="status"/)
    expect(run.html).toMatch(/aria-hidden="true"[^>]*>⚠/)
    expect(run.text).toContain(ENGINE_HEAD)
  })

  it('🔴 把 class 与 style 全剥掉，那几句照样读得出来：警告不靠颜色成立', async () => {
    const run = await runUpload(CELL_PAGES_LOST)
    const colorless = run.html.replace(/\s(class|style)="[^"]*"/g, '')
    expect(plainText(colorless)).toContain(DEGRADED_HEAD)
    expect(plainText(colorless)).toContain('第 3、7、12 页')
    expect(plainText(colorless)).toContain('OCR 没跑成 1 页')
  })

  it('warn 与 info 两档的差别写在【字】里：降级句头只在 warn 那一行出现', () => {
    const lines = pdfExtractionLines(CELL_PAGES_LOST)
    const warn = lines.find(line => line.tone === 'warn')
    const info = lines.find(line => line.key === 'tally')
    expect(warn.lead).toContain(DEGRADED_HEAD)
    expect(info.lead).not.toContain(DEGRADED_HEAD)
    expect(lines.filter(line => line.tone === 'warn')).toHaveLength(1)
  })

  it('判据⑧：没新增色值 —— 文件里既没有 hex 也没有 rgb，引用的 token 全部已在 theme.css 声明', () => {
    expect(SRC).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(SRC).not.toMatch(/rgba?\(|hsla?\(/)
    const styleBlock = /<style scoped>([\s\S]*)<\/style>/.exec(SRC)
    expect(styleBlock, '取不到样式块：这一枚钉该改法而不是被跳过').toBeTruthy()
    const theme = readFileSync(new URL('../../assets/theme.css', import.meta.url), 'utf8')
    const tokens = [...styleBlock[1].matchAll(/var\((--[a-z0-9-]+)/g)].map(hit => hit[1])
    expect(tokens.length).toBeGreaterThan(0)
    for (const token of new Set(tokens)) {
      expect(theme, 'DocPanel 引用了没在 theme.css 声明的 token：' + token).toContain(token + ':')
    }
  })

  it('判据⑧：没新增裸 <button>（r288 那枚 DEBT_TOTAL_RATCHET = 9 不许被顶破）', () => {
    expect(SRC).not.toMatch(/<button/)
    expect(countOf(SRC, '<UiButton')).toBeGreaterThan(0)
  })
})
