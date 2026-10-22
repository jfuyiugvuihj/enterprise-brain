/**
 * R313 · 格三 —— 文档行就地给出真值：谁传的 / 多大 / 这一版到哪一步了
 *
 * 后端早给了（app/documents/catalog.py::public_document_row 随每一行发出 owner_id、size_bytes、
 * parse_status），缺的只是界面没读。判据三条：读的是【已有字段】、🔴 不为此多开一次请求、
 * 不新增后端字段；而且判据要能反证 —— 把某一行换成别人的 owner_id，屏上必须跟着变
 * （不变就说明那一格是写死的样板文案，不是真读了行）。
 *
 * 两条诚实边界承接本仓已成的口径，不在这里新立：
 *   ① 「无主」与「读不到」是两件事：后端把无主行记成 None（catalog.py 的 _is_unowned），
 *      而【键缺席】是老部署只回一串文件名时本屏自己造的 { filename } 行 —— 服务端压根没答过，
 *      所以它不许被画成「无主」（那是一句关于数据的断言，这里没有断言的资格）。
 *   ② pending 不许画成「解析中」：_normalise_parse_status 把「没记过」与认不出的值一并归成
 *      pending，界面分不出「正在解析」与「这台机器从没记过这一列」，也就不许装成分得出来
 *      （与上面 retrievalFace 判据 2 同一条，R288 已定）。
 *
 * 手法同 r237-r49 / r288：createRenderer 挂 DocPanel 自己的 setup（onMounted → loadDocs 走产品
 * 那一遍），再把 SFC 那份 ssrRender 套在活 setupState 上出 HTML —— 判的是真模板产物。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
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
  TRUTH_UNREADABLE_SUFFIX,
  documentSizeLabel,
  ownerTruth,
  sizeTruth,
  stageTruth,
} from '../DocPanel.vue'
import { http } from '../../lib/http'

// ==================== 无 DOM 的真生命周期 + 真模板 ====================

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
      const from = parentOf(target).children.indexOf(target)
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
let catalogReads = 0
/** 服务端那一腿的账：界面上的定时器改不了它。 */
let serverRows = []

function mountPanel(props = {}) {
  http.get.mockImplementation(async (url) => {
    if (!String(url).endsWith('/documents/catalog')) return { data: {} }
    catalogReads += 1
    return { data: { documents: serverRows.map(row => (typeof row === 'string' ? row : { ...row })) } }
  })
  let instance = null
  const app = createApp({
    __name: 'R313RowTruthHost',
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

const stripComments = html => html.replace(/<!--[\s\S]*?-->/g, '')
const stripTags = html => html.replace(/<[^>]*>/g, '')
const plainText = html => stripTags(stripComments(html))
const faceRender = name => renderToString(h({
  __name: name,
  setup: () => live.state,
  ssrRender: DocPanel.ssrRender,
}))
const screen = async () => plainText(await faceRender('R313RowTruthFace'))

/** 每一行的真值那一格，按屏上出现顺序返回文本数组（与 r237 / r288 同一把量具）。 */
async function truthLines() {
  const html = await faceRender('R313RowTruthLines')
  const out = []
  const re = /<(\w+)[^>]*data-testid="doc-row-truth"[^>]*>/g
  let hit
  while ((hit = re.exec(html))) {
    const end = html.indexOf('</' + hit[1] + '>', hit.index + hit[0].length)
    out.push(plainText(end < 0 ? '' : html.slice(hit.index + hit[0].length, end)).trim())
  }
  return out
}

async function settle() {
  await nextTick()
  await nextTick()
}

async function openedWith(rows, props = {}) {
  serverRows = rows
  catalogReads = 0
  const state = mountPanel(props)
  await settle()
  return state
}

const row = (over = {}) => ({
  filename: '制度汇编.pdf',
  version: 3,
  owner_id: 'u-17',
  size_bytes: 20480,
  parse_status: 'ready',
  index_status: 'indexed',
  index_reason: '',
  ...over,
})

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
  catalogReads = 0
  serverRows = []
  live = null
})

// ==================== 甲 · 三句话各自的读法 ====================

describe('R313 格三 甲 · 纯函数判据（屏上那几个字只出自这三枚出口）', () => {
  it('owner_id 有值就说值，None / 空串 / 纯空白都说「无主」（与后端 _is_unowned 同一把）', () => {
    expect(ownerTruth(row({ owner_id: 'u-17' }))).toBe('上传者 u-17')
    expect(ownerTruth(row({ owner_id: ' u-2 ' }))).toBe('上传者 u-2')
    for (const unowned of [null, '', '   ']) {
      expect(ownerTruth(row({ owner_id: unowned })), '这一枚后端就算无主：' + JSON.stringify(unowned)).toBe('上传者无主')
    }
  })

  it('🔴 键【缺席】不是「无主」：服务端没答过的东西，界面不替它下断言', () => {
    expect(ownerTruth({ filename: '老文档.pdf' })).toBe('上传者' + TRUTH_UNREADABLE_SUFFIX)
    expect(ownerTruth(undefined)).toBe('上传者' + TRUTH_UNREADABLE_SUFFIX)
    expect(ownerTruth(null)).toBe('上传者' + TRUTH_UNREADABLE_SUFFIX)
    expect(ownerTruth({ filename: 'x', owner_id: null })).toBe('上传者无主')
  })

  it('字节数成人话，分档与后端 data.py::_format_data_file_size 同一把尺（B / KB / MB，一位小数）', () => {
    expect(documentSizeLabel(0)).toBe('0 B')
    expect(documentSizeLabel(512)).toBe('512 B')
    expect(documentSizeLabel(1023)).toBe('1023 B')
    expect(documentSizeLabel(1024)).toBe('1.0 KB')
    expect(documentSizeLabel(20480)).toBe('20.0 KB')
    expect(documentSizeLabel(3 * 1024 * 1024)).toBe('3.0 MB')
    for (const junk of [null, undefined, '', 'abc', -1, NaN, {}]) expect(documentSizeLabel(junk)).toBe('')
  })

  it('size_bytes 为 None（后端算不出来的那一格）⇒ 说读不到，绝不画成 0 B', () => {
    expect(sizeTruth(row({ size_bytes: null }))).toBe('大小' + TRUTH_UNREADABLE_SUFFIX)
    expect(sizeTruth(row({ size_bytes: 20480 }))).toBe('大小 20.0 KB')
    expect(sizeTruth({ filename: '老文档.pdf' })).toBe('大小' + TRUTH_UNREADABLE_SUFFIX)
  })

  it('parse_status 四个合法值各归各的脸，大小写与空白先归一', () => {
    expect(stageTruth(row({ parse_status: 'ready' }))).toBe('本版 解析完成')
    expect(stageTruth(row({ parse_status: '  READY ' }))).toBe('本版 解析完成')
    expect(stageTruth(row({ parse_status: 'failed' }))).toBe('本版 解析失败')
    expect(stageTruth(row({ parse_status: 'parsing' }))).toBe('本版 解析中')
  })

  it('🔴 pending 与键缺席都只许说读不到：后端把「没记过」也归成 pending，界面不许装成分得出来', () => {
    expect(stageTruth(row({ parse_status: 'pending' }))).toBe('本版 ' + TRUTH_UNREADABLE_SUFFIX)
    expect(stageTruth(row({ parse_status: '' }))).toBe('本版 ' + TRUTH_UNREADABLE_SUFFIX)
    expect(stageTruth(row({ parse_status: 12345 }))).toBe('本版 ' + TRUTH_UNREADABLE_SUFFIX)
    expect(stageTruth({ filename: '老文档.pdf' })).toBe('本版 ' + TRUTH_UNREADABLE_SUFFIX)
    expect(stageTruth(row({ parse_status: 'pending' }))).not.toContain('解析中')
  })
})

// ==================== 乙 · 真模板：读的是行，不是样板 ====================

describe('R313 格三 乙 · 屏上那一行真跟着行里的值走', () => {
  it('两行两样归属 ⇒ 屏上两句各不相同（写死在同一枚文案上就会红）', async () => {
    await openedWith([row({ filename: '甲.pdf', owner_id: 'u-17' }), row({ filename: '乙.pdf', owner_id: 'u-42', size_bytes: 512, parse_status: 'failed' })])
    const lines = await truthLines()
    expect(lines).toHaveLength(2)
    expect(lines[0]).toBe('上传者 u-17 · 大小 20.0 KB · 本版 解析完成')
    expect(lines[1]).toBe('上传者 u-42 · 大小 512 B · 本版 解析失败')
    expect(lines[0]).not.toBe(lines[1])
  })

  it('反证①：把这一行的 owner_id 换成别人的，屏上跟着变，邻行一个字都不动', async () => {
    await openedWith([row({ filename: '甲.pdf', owner_id: 'u-17' }), row({ filename: '乙.pdf', owner_id: 'u-42' })])
    expect((await truthLines())[0]).toContain('u-17')
    await openedWith([row({ filename: '甲.pdf', owner_id: 'u-99' }), row({ filename: '乙.pdf', owner_id: 'u-42' })])
    const lines = await truthLines()
    expect(lines[0], '换人不改脸：那一格根本没读行里的归属').toContain('上传者 u-99')
    expect(lines[0]).not.toContain('u-17')
    expect(lines[1]).toContain('上传者 u-42')
  })

  it('反证②：改 size_bytes 与 parse_status，屏上那两截也各自改（三句都真接着行）', async () => {
    await openedWith([row({ size_bytes: 20480, parse_status: 'ready' })])
    expect((await truthLines())[0]).toContain('大小 20.0 KB')
    await openedWith([row({ size_bytes: 4 * 1024 * 1024, parse_status: 'failed' })])
    const line = (await truthLines())[0]
    expect(line).toContain('大小 4.0 MB')
    expect(line).toContain('本版 解析失败')
    expect(line).not.toContain('解析完成')
  })

  it('裸值走 data-* 通道：测试与诊断读得到原值，给人看的那一行不夹码名形状', async () => {
    await openedWith([row({ owner_id: 'u-17', parse_status: 'pending' })])
    const html = await faceRender('R313RawChannel')
    expect(html).toMatch(/data-testid="doc-row-truth"[^>]*data-owner-id="u-17"/)
    expect(html).toMatch(/data-size-bytes="20480"/)
    expect(html).toMatch(/data-parse-status="pending"/)
    expect((await truthLines())[0]).not.toMatch(/[a-z]+_[a-z]+/)
  })

  it('三句与既有的那两格互不冒充：检索脸说检索，真值行说这版解析到哪一步', async () => {
    await openedWith([row({ index_status: 'indexed', parse_status: 'ready' })])
    let text = await screen()
    expect(text).toContain('已可检索')
    expect(text).toContain('本版 解析完成')
    await openedWith([row({ index_status: 'excluded', index_reason: 'no_text_content', parse_status: 'failed' })])
    text = await screen()
    expect(text).toContain('未索引')
    expect(text).toContain('本版 解析失败')
    expect(text).not.toContain('已可检索')
  })

  it('🔴 零新增请求：三行同屏只发那一发 catalog（本格不为此多开一次请求）', async () => {
    await openedWith([
      row({ filename: '甲.pdf' }),
      row({ filename: '乙.pdf', owner_id: null }),
      row({ filename: '丙.pdf', size_bytes: null, parse_status: 'pending' }),
    ])
    expect(await truthLines()).toHaveLength(3)
    await screen()
    expect(catalogReads, '每多一行就多一发请求：那正是判据禁的那件事').toBe(1)
    expect(http.get.mock.calls.map(call => call[0])).toHaveLength(1)
  })

  it('老部署只回一串文件名 ⇒ 三句都落到「读不到」，不假称无主也不假称 0 B', async () => {
    await openedWith(['裸文件名.pdf'])
    const lines = await truthLines()
    expect(lines).toHaveLength(1)
    expect(lines[0]).toBe(`上传者${TRUTH_UNREADABLE_SUFFIX} · 大小${TRUTH_UNREADABLE_SUFFIX} · 本版 ${TRUTH_UNREADABLE_SUFFIX}`)
    expect(lines[0]).not.toContain('无主')
    expect(lines[0]).not.toContain('0 B')
  })
})
