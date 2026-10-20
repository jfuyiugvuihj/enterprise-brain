/**
 * R343 · 「依据与相关制度」那一格里的对端文档要点得开（R314 的第二棒）
 *
 * 病：R314 把对端的名字摊上了屏，但只是摊上屏 —— 员工想知道「这条依据的那份文件到底写了
 * 什么」，还得关掉预览、回文档列表自己搜。
 *
 * 三类证据（本仓没有 jsdom，手法与 r314 同）：
 *   甲 真逻辑：名单认名、回包整形、屏上那一篇的取数、跳转层与名单层每一次转场都真跑；
 *   乙 真产物：SSR 首屏与关闭态的真字面，外加「可点那一枚」与两张新脸拿本格同一份 props
 *      渲出的形状 —— 组件内部的跳转态在 SSR 里进不去（没有 DOM 就没有点击），那部分由甲
 *      组跑状态机、丙组钉分支表，两处的缝隙在下面各条用例名里写明；
 *   丙 源码形状：对外契约零改动、不新开实例、不走路由、五枚面各占一支、闸门在位、
 *      界面不重算可见范围、请求预算 —— 这四件只有源码能钉。
 *
 * 反证（每把摘掉实现里哪一行会红，实测数字在工单回执里）：
 *   1 让非文档实体也可点（按名字形状猜）→ 甲组「对端不在名单就不长可点状」与丙组「只认名单」红；
 *   2 摘掉跳转腿的 token 闸门 → 甲组「迟到的一发」三枚红；
 *   3 把「对端读不到」画成「这篇没内容」→ 甲组 404 那一枚与丙组分支表、乙组两张脸的红字面同时红；
 *   4 用裸 <button> 画可点那一行 → r288 的棘轮与「六枚文件裸按钮归零」红；
 *   5 在界面按可见范围筛对端 → R314 那把反证与本件丙组「不重算」一起红；
 *   6 名单层放开每次都读 → 甲组「一次打开只读一回」红；
 *   7 跳过去之后让父组件那句错误顶在屏上 → 甲组「屏上那一篇」红；
 *   8 被闸门丢掉的那一发照样创建对象 URL → 甲组「回收」两枚红。
 */
import { describe, expect, it, vi } from 'vitest'
import { createSSRApp, h, ref } from 'vue'
import { readFileSync } from 'node:fs'
import { renderToString } from '@vue/server-renderer'
import { parse, compileScript } from '@vue/compiler-sfc'

// 只换网络层：api 是 lib/http 那个唯一实例的别名，本格的取数必须真的经过它。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), request: vi.fn() } }
})

import { http } from '../../lib/http'
import DocumentPreviewModal, {
  createDocumentNameStore,
  createPreviewNavStore,
  documentIdentityKey,
  documentNamesFromCatalog,
  markOpenableRelations,
  normalizePreviewPayload,
  previewScreenView,
  relationsAboutDocument,
  resolveCatalogName,
} from '../DocumentPreviewModal.vue'
import UiButton from '../ui/UiButton.vue'
import UiErrorState from '../ui/UiErrorState.vue'

const source = path => readFileSync(new URL(path, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
/** 屏上真正被人读到的字：SSR 会把模板注释一起吐出来，这里剥掉标签与注释。 */
const screen = html => html.replace(/<!--[\s\S]*?-->/g, '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()

const MODAL = source('../DocumentPreviewModal.vue')

const DOC = '差旅费报销制度.pdf'
const OTHER = '费用科目表.xlsx'
const PERSON = '张三'
const CODE_WORD = 'HR-001'

const deniedError = { response: { status: 403, data: { detail: 'permission_denied' } }, message: 'Request failed with status code 403' }
const missingError = { response: { status: 404, data: { detail: 'resource_not_found' } }, message: 'Request failed with status code 404' }
const brokenError = { response: { status: 503, data: { detail: 'storage_read_only' } }, message: 'Request failed with status code 503' }
const unsupportedError = { response: { status: 415, data: { detail: 'unsupported_preview' } }, message: 'Request failed with status code 415' }

function deferred() {
  let resolve = null
  let reject = null
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

/** 后端一行关系的形状（与 r314 同一份，扩展名字段由本格自己加）。 */
function row(extra = {}) {
  return {
    relation_id: 'rel-1',
    source_entity: DOC,
    relation: '依据',
    target: OTHER,
    source: '2026 版制度汇编第 3 章',
    owner_id: 'baiye',
    status: 'candidate',
    created_at: '2026-09-20T10:00:00+08:00',
    ...extra,
  }
}

const textPayload = (name = OTHER, text = '第一行正文') => ({ filename: name, kind: 'text', text, truncated: false })
const pdfPayload = (name = OTHER) => ({ filename: name, kind: 'pdf', text: '', blob: { size: 1 } })

// 两张新脸的字面：各写一次，用例拿它们比对分支归属。
const NAV_FAILED_TITLE = '这篇对端文档的预览没读到'
const NAV_DENIED_TITLE = '这个账号打不开这篇对端文档'
const UNREGISTERED_COPY = '对不上这一篇文档'

// ==================== 甲 · 对端是不是一篇文档（判据①） ====================

describe('甲 · 对端「确实是一篇文档」只由名单裁定（判据①）', () => {
  it('名单的形状：行对象、裸字符串、混合都认；没名字与不是数组的行不当名字', () => {
    expect(documentNamesFromCatalog([{ filename: OTHER }, { filename: ' ' + DOC + ' ' }, '旧部署.txt', null, 7, {}])).toEqual([OTHER, DOC, '旧部署.txt'])
    for (const bad of [undefined, null, 'documents', 42, {}]) {
      expect(documentNamesFromCatalog(bad), JSON.stringify(bad)).toEqual([])
    }
  })

  it('认名只认整名：尺子就是 R314 那一枚，扩展名参与、近似名不算', () => {
    const names = [OTHER, DOC]
    expect(resolveCatalogName(' ' + OTHER + ' ', names)).toBe(OTHER)
    expect(resolveCatalogName(OTHER.replace('.xlsx', '.XLSX'), names)).toBe(OTHER)
    // 少一个扩展名、多一个字、被包住：都是另一篇，一律认不出
    expect(resolveCatalogName('费用科目表', names)).toBe('')
    expect(resolveCatalogName(OTHER + '（副本）', names)).toBe('')
    expect(resolveCatalogName('新版' + OTHER, names)).toBe('')
    expect(documentIdentityKey(resolveCatalogName(OTHER.replace('.xlsx', '.XLSX'), names))).toBe(documentIdentityKey(OTHER))
  })

  it('认不出与名单没读回来都是空串：不许返回「最像的那一枚」冒充', () => {
    expect(resolveCatalogName(PERSON, [OTHER])).toBe('')
    expect(resolveCatalogName(CODE_WORD, [OTHER])).toBe('')
    expect(resolveCatalogName(OTHER, [])).toBe('')
    expect(resolveCatalogName(OTHER, undefined)).toBe('')
    expect(resolveCatalogName('', [OTHER])).toBe('')
  })

  it('🔴 反证 1：对端不在名单（人名、制度编号、没填名字）就不许长出可点状', () => {
    const names = [OTHER]
    const asSubject = markOpenableRelations(relationsAboutDocument(DOC, [row()]), names)[0]
    expect(asSubject.rightOpen).toBe(OTHER)
    // 这篇自己那一头永远不可点：它已经在屏上了
    expect(asSubject.leftOpen).toBe('')
    // 对端换成人名与编号：摊出来的名字照旧上屏，可点状一枚都不长
    const person = markOpenableRelations(relationsAboutDocument(DOC, [row({ target: PERSON })]), names)[0]
    expect(person.rightName).toBe('《' + PERSON + '》')
    expect(person.rightOpen).toBe('')
    const codeWord = markOpenableRelations(relationsAboutDocument(DOC, [row({ target: CODE_WORD })]), names)[0]
    expect(codeWord.rightOpen).toBe('')
    // 没填文档名那一格也不长可点状
    const blank = markOpenableRelations(relationsAboutDocument(DOC, [row({ target: '  ' })]), names)[0]
    expect(blank.rightOpen).toBe('')
    // 两端都是这篇：两头都不长
    const both = markOpenableRelations(relationsAboutDocument(DOC, [row({ target: DOC })]), names)[0]
    expect([both.leftOpen, both.rightOpen]).toEqual(['', ''])
  })

  it('名单没读回来（还没读、读失败、空库）时一行都不长可点状，摊平的显示字段一个不动', () => {
    const rows = relationsAboutDocument(DOC, [row()])
    for (const names of [[], undefined, null]) {
      const [marked] = markOpenableRelations(rows, names)
      expect(marked.leftOpen).toBe('')
      expect(marked.rightOpen).toBe('')
    }
    const [marked] = markOpenableRelations(rows, [OTHER])
    for (const field of ['rowKey', 'role', 'leftName', 'rightName', 'linkWord', 'evidence', 'statusWord', 'author', 'registeredOn']) {
      expect(marked[field], field).toBe(rows[0][field])
    }
    expect(Object.keys(marked).some(key => key.includes('_'))).toBe(false)
    // 后端来的行不是数组：不炸，也不凭空长出可点的行
    for (const bad of [undefined, null, 'rows', 42]) {
      expect(markOpenableRelations(bad, [OTHER])).toEqual([])
    }
  })
})

// ==================== 甲 · 回包整形与屏上那一篇 ====================

describe('甲 · 预览回包只认后端在册的两枚 kind（判据⑤）', () => {
  it('text 与 pdf 各自要求自己的正文：缺正文是读不到，不是「这篇没内容」', () => {
    expect(normalizePreviewPayload(OTHER, textPayload())).toMatchObject({ filename: OTHER, kind: 'text', text: '第一行正文' })
    expect(normalizePreviewPayload(OTHER, pdfPayload())).toMatchObject({ filename: OTHER, kind: 'pdf', blob: { size: 1 } })
    expect(normalizePreviewPayload(OTHER, { filename: OTHER, kind: 'text' })).toBe(null)
    expect(normalizePreviewPayload(OTHER, { filename: OTHER, kind: 'text', text: null })).toBe(null)
    expect(normalizePreviewPayload(OTHER, { filename: OTHER, kind: 'pdf' })).toBe(null)
    expect(normalizePreviewPayload(OTHER, { filename: OTHER, kind: 'table', columns: [] })).toBe(null)
    for (const bad of [undefined, null, 'text', 42, [], [{ kind: 'text' }]]) {
      expect(normalizePreviewPayload(OTHER, bad), JSON.stringify(bad)).toBe(null)
    }
  })

  it('回包没带名字就用刚请求的那一枚：不许把上一跳的名字顶上来', () => {
    expect(normalizePreviewPayload(OTHER, { kind: 'text', text: '' }).filename).toBe(OTHER)
    expect(normalizePreviewPayload(OTHER, { filename: '  ', kind: 'text', text: '' }).filename).toBe(OTHER)
    expect(normalizePreviewPayload(OTHER, { filename: DOC, kind: 'text', text: '' }).filename).toBe(DOC)
  })
})

describe('甲 · 屏上那一篇 = 跳转层那一篇（判据②③⑦）', () => {
  const root = { filename: DOC, kind: 'pdf', text: '父组件给的正文', blobUrl: 'blob:root', loading: false, error: '' }

  it('没跳过：六枚字段就是父组件递进来的那六枚', () => {
    expect(previewScreenView({ face: 'root', doc: null }, root)).toEqual({
      filename: DOC, kind: 'pdf', text: '父组件给的正文', blobUrl: 'blob:root', loading: false, error: '',
    })
    expect(previewScreenView(null, root).filename).toBe(DOC)
    expect(previewScreenView({ face: 'root' }, { ...root, loading: true }).loading).toBe(true)
  })

  it('跳过去了：标题、正文、字节都换成对端那一篇', () => {
    const view = previewScreenView({ face: 'ready', doc: { filename: OTHER, kind: 'text', text: '对端正文', blobUrl: '' } }, root)
    expect(view).toEqual({ filename: OTHER, kind: 'text', text: '对端正文', blobUrl: '', loading: false, error: '' })
  })

  it('🔴 反证 7：换过去的那一刻起，父组件那句错误不再顶在屏上，正在读的就是正在读', () => {
    const broken = { ...root, error: '文件预览失败' }
    expect(previewScreenView({ face: 'root' }, broken).error).toBe('文件预览失败')
    for (const face of ['loading', 'failed', 'unregistered']) {
      const view = previewScreenView({ face, doc: { filename: OTHER } }, broken)
      expect(view.error, face).toBe('')
      expect(view.text, face).toBe('')
      expect(view.blobUrl, face).toBe('')
      expect(view.kind, face).toBe('')
      expect(view.filename, face).toBe(OTHER)
    }
    expect(previewScreenView({ face: 'loading', doc: { filename: OTHER } }, root).loading).toBe(true)
    expect(previewScreenView({ face: 'failed', doc: { filename: OTHER } }, root).loading).toBe(false)
  })
})

// ==================== 甲 · 跳转层状态机（判据③④⑤） ====================

function makeNav(fetchPreview, ledger) {
  const book = ledger || { created: [], revoked: [], serial: 0 }
  return {
    book,
    store: createPreviewNavStore({
      ref,
      fetchPreview,
      createObjectUrl: () => {
        book.serial += 1
        const url = 'blob:' + book.serial
        book.created.push(url)
        return url
      },
      revokeObjectUrl: url => book.revoked.push(url),
    }),
  }
}

describe('甲 · 跳转层五枚面互不顶替（判据⑤）', () => {
  it('root → loading → ready →（返回）root：每一步都真转，返回把屏交回父组件那一篇', async () => {
    const { store } = makeNav(async name => textPayload(name))
    expect(store.state.value.face).toBe('root')
    const pending = store.open(OTHER)
    expect(store.state.value.face).toBe('loading')
    // loading 的那一刻屏上已经换成了对端的名字：正文区吃的是自己的进行态
    expect(store.state.value.doc.filename).toBe(OTHER)
    await pending
    expect(store.state.value.face).toBe('ready')
    expect(store.state.value.doc.text).toBe('第一行正文')
    store.back()
    expect(store.state.value.face).toBe('root')
    expect(store.state.value.doc).toBe(null)
  })

  it('404 = 对端没有登记预览，403 / 503 / 415 = 读不到：两张脸，句子两两不等', async () => {
    const unregistered = await makeNav(async () => { throw missingError }).store
    await unregistered.open(OTHER)
    expect(unregistered.state.value.face).toBe('unregistered')
    expect(unregistered.state.value.face).not.toBe('failed')
    expect(unregistered.state.value.message).toContain(UNREGISTERED_COPY)
    // 判据⑤：这一张脸绝不说「这篇没有内容」
    expect(unregistered.state.value.message).not.toMatch(/暂无数据|没有内容|没有正文|内容为空/)
    expect(unregistered.state.value.message).toContain(OTHER)

    const failed = await makeNav(async () => { throw brokenError }).store
    await failed.open(OTHER)
    expect(failed.state.value.face).toBe('failed')
    expect(failed.state.value.denied).toBe(false)
    expect(failed.state.value.message).not.toBe('')
    expect(failed.state.value.message).not.toContain(UNREGISTERED_COPY)

    const denied = await makeNav(async () => { throw deniedError }).store
    await denied.open(OTHER)
    expect(denied.state.value.face).toBe('failed')
    expect(denied.state.value.denied).toBe(true)

    const unsupported = await makeNav(async () => { throw unsupportedError }).store
    await unsupported.open(OTHER)
    // 415 说的是「这种类型展不开」，那句是服务器给的，不是本屏编的
    expect(unsupported.state.value.message).toContain('不支持在线预览')
    expect(unsupported.state.value.face).not.toBe('unregistered')

    const words = [unregistered.state.value.message, failed.state.value.message, denied.state.value.message, '']
    for (let i = 0; i < words.length; i += 1) {
      for (let j = i + 1; j < words.length; j += 1) expect(words[i]).not.toBe(words[j])
    }
  })

  it('回包形状不对落 failed，不落 ready，也不落「没有内容」', async () => {
    const { store } = makeNav(async () => ({ kind: 'text' }))
    await store.open(OTHER)
    expect(store.state.value.face).toBe('failed')
    expect(store.state.value.message).toContain('数据结构不对')
    expect(store.state.value.doc.text ?? '').toBe('')
  })

  it('PDF 的字节换不出本地地址就是读不到：不摆空 iframe，也不说这篇没内容', async () => {
    const noUrl = createPreviewNavStore({ ref, fetchPreview: async () => pdfPayload(), createObjectUrl: () => '', revokeObjectUrl: () => {} })
    await noUrl.open(OTHER)
    expect(noUrl.state.value.face).toBe('failed')
    expect(noUrl.state.value.message).not.toMatch(/暂无数据|没有内容|内容为空/)
  })

  it('没名字就不开口，也一发请求都不发', async () => {
    const fetchPreview = vi.fn(async () => textPayload())
    const { store } = makeNav(fetchPreview)
    expect(await store.open('   ')).toBe(false)
    expect(fetchPreview).not.toHaveBeenCalled()
    expect(store.state.value.face).toBe('root')
  })
})

describe('甲 · 🔴 反证 2：跳转腿的 token 闸门与 R314 同一把尺子（判据④）', () => {
  it('连点两篇：先出发的那发迟到也不许把屏换成它', async () => {
    const first = deferred()
    const second = deferred()
    const queue = [() => first.promise, () => second.promise]
    const { store } = makeNav(name => queue.shift()())
    const pendingA = store.open(OTHER)
    const pendingB = store.open(DOC)
    expect(store.state.value.face).toBe('loading')
    second.resolve(textPayload(DOC))
    await pendingB
    expect(store.state.value.doc.filename).toBe(DOC)
    first.resolve(textPayload(OTHER))
    await pendingA
    // 迟到的一发不许把「制度表」这一屏换回别的一篇
    expect(store.state.value.face).toBe('ready')
    expect(store.state.value.doc.filename).toBe(DOC)
    expect(store.state.value.doc.text).toBe('第一行正文')
  })

  it('按了返回之后迟到的那一发丢掉：屏回父组件那一篇，也不长出半个对端字段', async () => {
    const gate = deferred()
    const { store } = makeNav(() => gate.promise)
    const pending = store.open(OTHER)
    store.back()
    gate.resolve(textPayload())
    expect(await pending).toBe(false)
    expect(store.state.value.face).toBe('root')
    expect(store.state.value.doc).toBe(null)
  })

  it('父组件换文档（reset）之后迟到的那一发同样丢掉', async () => {
    const gate = deferred()
    const { store } = makeNav(() => gate.promise)
    const pending = store.open(OTHER)
    store.reset()
    gate.resolve(textPayload())
    expect(await pending).toBe(false)
    expect(store.state.value.face).toBe('root')
  })

  it('🔴 反证 8：被丢掉的那发一枚对象 URL 都不许创建；赢了的那发换篇与返回都要回收', async () => {
    const ledger = { created: [], revoked: [] }
    const gate = deferred()
    const { store } = makeNav(() => gate.promise, ledger)
    const pending = store.open(OTHER)
    store.back()
    gate.resolve(pdfPayload())
    await pending
    expect(ledger.created).toEqual([])
    expect(ledger.revoked).toEqual([])

    const live = makeNav(async name => pdfPayload(name))
    await live.store.open(OTHER)
    expect(live.book.created).toHaveLength(1)
    await live.store.open(DOC)
    expect(live.book.created).toHaveLength(2)
    expect(live.book.revoked).toEqual(live.book.created.slice(0, 1))
    live.store.back()
    expect(live.book.revoked).toEqual(live.book.created)
  })
})

describe('甲 · 名单一次「打开」只读一回（判据⑧）', () => {
  it('🔴 反证 6：load 连点三回只发一发出网，读失败也不自己重试', async () => {
    const fetchNames = vi.fn(async () => [OTHER])
    const store = createDocumentNameStore({ ref, fetchNames })
    await Promise.all([store.load(), store.load(), store.load()])
    expect(fetchNames).toHaveBeenCalledTimes(1)
    expect(store.state.value).toEqual({ face: 'ready', names: [OTHER] })
    await store.load()
    expect(fetchNames).toHaveBeenCalledTimes(1)
  })

  it('读失败是一张自己的脸：名单空着，等下一次打开再说', async () => {
    const store = createDocumentNameStore({ ref, fetchNames: async () => { throw brokenError } })
    await store.load()
    expect(store.state.value.face).toBe('failed')
    expect(store.state.value.names).toEqual([])
    const back = createDocumentNameStore({ ref, fetchNames: async () => 'not a list' })
    await back.load()
    expect(back.state.value.face).toBe('failed')
  })

  it('关掉再开（reset）才允许重读；迟到的名单回包丢掉', async () => {
    const gate = deferred()
    const fetchNames = vi.fn(() => gate.promise)
    const store = createDocumentNameStore({ ref, fetchNames })
    const pending = store.load()
    expect(store.state.value.face).toBe('loading')
    store.reset()
    gate.resolve([OTHER])
    await pending
    expect(store.state.value).toEqual({ face: 'idle', names: [] })
    store.load()
    expect(fetchNames).toHaveBeenCalledTimes(2)
  })
})

// ==================== 乙 · 真产物 ====================

async function renderModal(props) {
  const ctx = {}
  const app = createSSRApp({ render: () => h(DocumentPreviewModal, { open: true, filename: DOC, kind: 'text', ...props }) })
  await renderToString(app, ctx)
  // 弹窗的根节点是 <Teleport to="body">：产物在 teleport 缓冲区里，取晚一步就是空串
  const body = ctx.teleports?.body ?? ''
  return { body, text: screen(body) }
}

describe('乙 · 真产物：SSR 首屏、单一实例与两张新脸', () => {
  it('SSR 首屏：屏上就是父组件那一篇，抬头只有下载、没有「回到」，这一腿一个请求都不发', async () => {
    const { body, text } = await renderModal({ text: '正文在第一行' })
    expect(text).toContain(DOC)
    expect(text).toContain('正文在第一行')
    expect(text).toContain('下载')
    expect(text).not.toContain('回到《')
    expect(body).not.toContain('r343-back-to-opened')
    expect(body).not.toContain('r343-face-nav-failed')
    expect(body).not.toContain('r343-face-nav-unregistered')
    expect(http.request).not.toHaveBeenCalled()
    expect(http.get).not.toHaveBeenCalled()
  })

  it('就地换 = 同一枚弹窗：产物里只有一枚 preview-container，也没有第二份弹窗根节点', async () => {
    const { body } = await renderModal({})
    expect(body.match(/class="preview-container/g)).toHaveLength(1)
    expect(body.match(/class="preview-overlay/g)).toHaveLength(1)
    expect(body.match(/role="dialog"/g)).toHaveLength(1)
  })

  it('可点那一枚的真产物是按钮，且说出点的是哪一篇（判据⑦）', async () => {
    const html = await renderToString(h(UiButton, {
      size: 'sm', variant: 'ghost', label: '《' + OTHER + '》', 'aria-label': '打开这一篇：《' + OTHER + '》',
    }))
    expect(html).toMatch(/^<button/)
    expect(html).toContain('class="ui-button')
    expect(html).toContain('type="button"')
    expect(html).toContain('aria-label="打开这一篇：《' + OTHER + '》"')
    // 可见文字是 accessible name 的子串：读屏与「标签即名称」同一条
    expect(screen(html)).toContain('《' + OTHER + '》')
  })

  it('「回到《…》」的产物点名回的是哪一篇', async () => {
    const html = await renderToString(h(UiButton, { variant: 'ghost', label: '回到《' + DOC + '》', 'aria-label': '回到《' + DOC + '》' }))
    expect(html).toMatch(/^<button/)
    expect(html).toContain('回到《' + DOC + '》')
  })

  it('读不到与没登记是两张脸：alert 与中性那一条两两不等，都不说「这篇没内容」', async () => {
    // 三张脸的字面全部来自真状态机与真原语：句子不是这里手抄的
    const gone = makeNav(async () => { throw missingError })
    await gone.store.open(OTHER)
    const broken = makeNav(async () => { throw brokenError })
    await broken.store.open(OTHER)
    const denied = makeNav(async () => { throw deniedError })
    await denied.store.open(OTHER)
    const failedCard = await renderToString(h(UiErrorState, {
      title: NAV_FAILED_TITLE, description: broken.store.state.value.message, retryText: '再打开一次', dense: true,
    }))
    const deniedCard = await renderToString(h(UiErrorState, {
      title: NAV_DENIED_TITLE, description: denied.store.state.value.message, retryable: false, dense: true,
    }))
    const unregisteredRow = await renderToString(h('div', { class: 'preview-state preview-unregistered' }, gone.store.state.value.message))
    expect(failedCard).toMatch(/role="alert"/)
    expect(deniedCard).toMatch(/role="alert"/)
    expect(screen(failedCard)).toContain(NAV_FAILED_TITLE)
    expect(screen(deniedCard)).toContain(NAV_DENIED_TITLE)
    // 无权限不给重试，真坏了才给
    expect(deniedCard).not.toContain('再打开一次')
    expect(failedCard).toContain('再打开一次')
    // 第三张脸不是一张 alert，也不是空态组件：它说的是「名字对不上库里的文档」
    expect(unregisteredRow).not.toMatch(/role="alert"/)
    expect(screen(unregisteredRow)).toContain(UNREGISTERED_COPY)
    const copies = [screen(failedCard), screen(deniedCard), screen(unregisteredRow)]
    for (const copy of copies) {
      expect(copy).not.toMatch(/暂无数据|没有内容|内容为空|这篇是空的/)
    }
    for (let i = 0; i < copies.length; i += 1) {
      for (let j = i + 1; j < copies.length; j += 1) expect(copies[i]).not.toBe(copies[j])
    }
  })

  it('新增的字面里没有英文装饰字（R314 清掉那枚眉标的口径继续算）', () => {
    const copy = MODAL.slice(MODAL.indexOf('<template>'))
    for (const added of ['对端那一篇', '再打开一次', '这会儿对不上库里的文档名单', '打开这一篇：']) {
      expect(copy, added).toContain(added)
    }
    expect(MODAL).toContain('回到《${props.filename}》')
    expect(copy).not.toMatch(/<(strong|span|p|h4|div)[^>]*>(?:PDF|Preview|Document|Relation|Open|Back|Knowledge)[A-Za-z .&-]*<\/(strong|span|p|h4|div)>/)
  })
})

// ==================== 丙 · 源码形状 ====================

const asideStart = MODAL.indexOf('<aside class="related-docs"')
const aside = MODAL.slice(asideStart, MODAL.indexOf('</aside>', asideStart))
const bodyStart = MODAL.indexOf('<div class="preview-body">')
const previewBody = MODAL.slice(bodyStart, MODAL.indexOf('</div>\n          </div>', bodyStart))

describe('丙 · 契约、闸门与预算（判据②③⑥⑧，源码形状）', () => {
  it('对外契约零改动：props 与 emits 的字面还在原处，也没有第二枚弹窗实例', () => {
    expect(MODAL).toContain("const emit = defineEmits(['close', 'download'])")
    for (const prop of ['open: Boolean', 'filename: {', 'kind: {', 'text: {', 'blobUrl: {', 'columns: {', 'rows: {', 'loading: Boolean', 'error: {', 'truncated: Boolean', 'rowScope: {']) {
      expect(MODAL, prop).toContain(prop)
    }
    expect(MODAL.match(/props: \{/g) ?? []).toHaveLength(0)
    // 就地换，不开第二个实例：本组件不自接自己
    expect(MODAL).not.toContain('<DocumentPreviewModal')
    expect(MODAL).not.toMatch(/import[^\n]*DocumentPreviewModal/)
  })

  it('不许引入路由跳转：本文件不碰 router，也不写绝对地址', () => {
    expect(MODAL).not.toMatch(/vue-router|useRouter|\$router|router\.push|route\.params/)
    expect(MODAL).not.toMatch(/https?:\/\//)
    expect(MODAL).not.toMatch(/cdn\.|unpkg|jsdelivr|googleapis/)
  })

  it('覆盖层真接上了模板：让 vue 自己编译一次，六枚名字得是 setup 绑定而不是 props', () => {
    // 这条不是正则形状 —— 编译器认谁就是谁：模板里的 filename / loading 吃到的是覆盖层，
    // 而 props 那五枚没被吃掉，父组件递进来的东西照旧进得来（判据②的「父组件零改动」）。
    const { descriptor } = parse(MODAL, { filename: 'DocumentPreviewModal.vue' })
    const compiled = compileScript(descriptor, { id: 'r343' })
    expect(descriptor.scriptSetup, '<script setup> 没被解析出来').toBeTruthy()
    for (const name of ['filename', 'kind', 'text', 'blobUrl', 'loading', 'error']) {
      expect(compiled.bindings[name], name + ' 不再由覆盖层供值：屏上那一篇换不动了').toBe('setup-ref')
    }
    for (const name of ['open', 'columns', 'rows', 'truncated', 'rowScope']) {
      expect(compiled.bindings[name], name + ' 被覆盖层吃掉了：对外契约动了').toBe('props')
    }
  })

  it('回退选的是「本组件自己的一格栈」，选型理由写在注释里（判据③）', () => {
    expect(MODAL).toContain('一格栈')
    expect(aside).not.toContain('router-link')
    // 出口只有抬头那一枚，且它吃的是父组件那一篇的名字
    expect(MODAL).toContain(':label="returnLabel"')
    expect(MODAL).toContain('const returnLabel = computed(() => `回到《${props.filename}》`)')
  })

  it('五枚面各占一支：进行吃 shadow 的 loading，读不到是 alert，没登记是中性那一条', () => {
    const marks = [
      '<UiLoadingState v-if="loading"',
      '<div v-else-if="error" class="preview-state preview-error"',
      '<div v-else-if="navFailed" class="preview-state"',
      '<div v-else-if="navUnregistered" class="preview-state preview-unregistered"',
      "v-else-if=\"kind === 'pdf' && blobUrl\"",
      "v-else-if=\"kind === 'text'\"",
    ]
    const at = marks.map(mark => {
      const position = previewBody.indexOf(mark)
      expect(position, '分支缺了这一支：' + mark).toBeGreaterThan(-1)
      return position
    })
    expect(at).toEqual([...at].sort((a, b) => a - b))
    expect(previewBody).toContain('<UiErrorState')
    const unregisteredAt = previewBody.indexOf('navUnregistered')
    expect(previewBody.slice(unregisteredAt).match(/UiErrorState|UiEmptyState/g) ?? []).toHaveLength(0)
    // 没登记那一张脸不许借「没有内容」那两句话
    expect(previewBody).not.toMatch(/preview-unregistered[^>]*>[^<]*(?:暂无数据|没有内容)/)
    expect(MODAL).toContain('<span v-if="navActive && !navReady">对端那一篇</span>')
  })

  it('🔴 反证 4：可点那一行是 components/ui 的真按钮，不是 div 也不是裸 button', () => {
    expect(aside.match(/<UiButton\s+\n?\s+v-if="row\.(?:left|right)Open"/g) ?? aside.match(/v-if="row\.(left|right)Open"/g)).toHaveLength(2)
    expect(aside).not.toMatch(/<div[^>]*@click/)
    expect(aside).not.toMatch(/<span[^>]*@click/)
    expect(aside).not.toContain('<button')
    expect(MODAL).not.toMatch(/<(?:p|li|ul|strong)[^>]*@click/)
    // 两处都点名了要打开哪一篇
    expect(aside.match(/:aria-label="'打开这一篇：'/g)).toHaveLength(2)
  })

  it('两把 token 闸门都在位：R314 那一枚一字未动，跳转腿与名单腿各加一枚同形的', () => {
    expect(MODAL).toContain('if (mine !== token) return')
    expect(MODAL.match(/if \(mine !== token\) return/g)).toHaveLength(3)
    const relations = MODAL.slice(MODAL.indexOf('export function createRelatedDocsStore'), MODAL.indexOf('export function createPreviewNavStore'))
    expect(relations).toContain('const next = await readDocumentRelations(name, fetchRelations)')
    expect(relations).toContain('if (mine !== token) return')
    // 关掉与换文档都先作废这一层，再谈读不读
    const watcher = MODAL.slice(MODAL.indexOf('watch([() => props.open'), MODAL.indexOf('watch(relatedRows'))
    expect(watcher).toContain('previewNav.reset()')
    expect(watcher).toContain('documentNames.reset()')
    expect(watcher).toContain('relatedDocs.reset()')
    // 卸载兜底：这一层自己造的对象 URL，组件没了它也必须没
    expect(MODAL).toContain('onBeforeUnmount(() => {\n  previewNav.reset()')
  })

  it('🔴 反证 5：密级与部门仍然不在界面重算，可点只由名单裁定', () => {
    expect(MODAL).not.toMatch(/clearance|department|classification|visibility|principal/)
    expect(MODAL).not.toMatch(/item\.visibility|if \([^\n]*public/)
    const opener = MODAL.slice(MODAL.indexOf('function openRelatedDocument'), MODAL.indexOf('/** 回到父组件打开的那一篇'))
    expect(opener).toContain('resolveCatalogName(')
    // 名字形状不是凭据：这里不许出现按扩展名猜的代码
    expect(opener).not.toMatch(/\.pdf|\.docx|\.xlsx|endsWith|startsWith|includes\(/)
    const marker = MODAL.slice(MODAL.indexOf('export function markOpenableRelations'), MODAL.indexOf('export const PREVIEW_NAV_ROOT'))
    expect(marker).toContain('resolveCatalogName(')
    expect(marker).not.toMatch(/\.(?:pdf|docx|xlsx)|endsWith|startsWith/)
  })

  it('请求预算：关联表仍是一枚 get（R348 起带 ?document=），新腿只有 request 三发，名单一次打开只读一回', () => {
    expect(MODAL.match(/api\.get\(/g)).toHaveLength(1)
    // 🔴 与 r314 的反证 3 同一件事的改口：那一枚 get 现在把本篇登记名的原文交给服务端筛。
    // 形状判据一条没松 —— 读法仍只有一枚，跳转腿（openRelatedDocument → readRelatedDocs）
    // 也不许多出第二枚关系读法，更不许多带第二枚过滤参数。
    expect(MODAL).toContain('api.get(relationsListingUrl(documentName))')
    expect(MODAL).toContain("`/knowledge-graph/relations?document=${encodeURIComponent(")
    expect(MODAL.match(/api\.request\(/g)).toHaveLength(3)
    expect(MODAL).toContain("url: '/documents/catalog'")
    expect(MODAL.match(/documentNames\.load\(/g)).toHaveLength(1)
    expect(MODAL.match(/relatedDocs\.load\(/g)).toHaveLength(3)
    expect(MODAL.match(/previewNav\.open\(/g)).toHaveLength(2)
    // 没有为「按文档筛关系」改后端，也没有新端点
    expect(MODAL).not.toMatch(/source_entity=|source-entity/)
    expect(MODAL).not.toMatch(/api\.request\([^)]*\?/)
  })

  it('新增样式只借既有 token：两块新规则里没有一枚裸色值', () => {
    const style = MODAL.slice(MODAL.indexOf('<style'), MODAL.indexOf('</style>'))
    for (const anchor of ['.preview-unregistered {', '.related-docs-open {']) {
      const from = style.indexOf(anchor)
      expect(from, anchor).toBeGreaterThan(-1)
      const block = style.slice(from, style.indexOf('}', from) + 1)
      expect(block).not.toMatch(/#[0-9a-fA-F]{3}/)
      expect(block).not.toMatch(/\brgba?\(|\bhsla?\(/)
      expect(block).not.toMatch(/var\(\s*--[\w-]+\s*,/)
    }
  })
})
