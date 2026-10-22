/**
 * R288 · G01 —— 上传之后不刷新，也要看得见「解析中 → 已可检索」
 *
 * 判据原文：状态推进必须来自服务端读数（parse_status / index_status 那一族既有字段，
 * 按调用点取证）；禁止前端自己 setTimeout 假推进；禁止把「我提交了」当「已可检索」；
 * 刷新与不刷新两条路径最终必须落在同一张脸上；解析失败与长时间不完成要有各自不同的脸，
 * 不许静默停在「解析中」。
 *
 * 取证（行号在本件基点 e441d10 上由 git grep 复现，未抄上一班快照）：
 *   后端读点只有一条 —— app/api/v1/chat.py 的 GET /documents/catalog 经
 *   _classify_document_rows → catalog.py:220 public_document_row 随每一行发出 parse_status；
 *   catalog.py:243-252 明写 index_status 三种读法（indexed / excluded / 键缺席=历史行）。
 *   parse_status 只有 pending / parsing / ready / failed 四个合法值（catalog.py:29，
 *   且 migrations/0006 是 DB 层 CHECK）；上传落库写的是 ready 或 failed
 *   （chat.py:3879、3926、4013），POST /upload 回执（chat.py:3745 _upload_receipt）另带
 *   index_status 与 index_message。也就是说：服务端从不写 parsing，
 *   「解析中」这张脸只有两种诚实来源 —— 后端真说了 parsing，或本屏自己那发上传还挂着。
 *
 * 手法沿用 r237-r49-index-face.test.js：本仓没有 jsdom，也不 npm i。
 *   createRenderer + 内存虚拟节点挂 DocPanel 自己编译出的 setup ⇒ onMounted → loadDocs →
 *   http.get('/documents/catalog') 走的是产品那一遍，换掉的只有网络层与渲染器；
 *   再把 SFC 自己那份 ssrRender 套在活 setupState 上出 HTML —— 判的是真模板产物。
 *   时钟走 vi.useFakeTimers()，一格 1.5 秒，不真等。
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
  isArtifactRequest: (src) => Boolean(src) && String(src).startsWith('artifact:'),
  fetchArtifactBlob: () => new Promise(() => {}),
}))

import ChartViewer from '../ChartViewer.vue'
import DocPanel from '../DocPanel.vue'
import { http } from '../../lib/http'
import {
  RETRIEVAL_FACE_LABEL,
  UPLOAD_POLL_INTERVAL_MS,
  UPLOAD_POLL_MAX_TICKS,
  isUnsettledFace,
  retrievalFace,
  retrievalFaceLabel,
  shouldReadUploadAgain,
} from '../DocPanel.vue'

const SRC_ROOT = new URL('../', import.meta.url)
const readSrc = rel => readFileSync(new URL(rel, SRC_ROOT), 'utf8').replace(/\r\n/g, '\n')
// ==================== 无 DOM 的真生命周期 + 真模板 ====================

function node(tag) {
  return { tag, props: {}, children: [], parent: null, text: '' }
}

const nodeOps = {
  createElement: tag => node(tag),
  createText: text => Object.assign(node('#text'), { text }),
  createComment: text => Object.assign(node('#comment'), { text }),
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
    if (target.parent) {
      parent(target).children.splice(parent(target).children.indexOf(target), 1)
      target.parent = null
    }
  },
  patchProp: (el, key, _prev, next) => {
    if (next === null || next === undefined) delete el.props[key]
    else el.props[key] = next
  },
  cloneNode: original => Object.assign(node(original.tag), { props: { ...original.props }, text: original.text }),
  insertStaticContent: () => [node('#static'), node('#static')],
  querySelector: () => null,
  setScopeId: () => {},
}
const parent = target => target.parent

const { createApp } = createRenderer(nodeOps)
const SSR_CONTEXT_KEY = Symbol.for('v-scx')

/** 服务端那一侧的账：只有改它才算「后端改口」，界面上的定时器改不了它。 */
let serverRows = []
let catalogReads = 0
let catalogFailures = 0
let live = null

function mountPanel(props = {}) {
  http.get.mockImplementation(async (url) => {
    if (!String(url).endsWith('/documents/catalog')) return { data: {} }
    catalogReads += 1
    if (catalogFailures > 0) {
      catalogFailures -= 1
      throw Object.assign(new Error('Network Error'), { isAxiosError: true, code: 'ERR_NETWORK', request: {}, config: { url } })
    }
    return { data: { documents: serverRows.map(row => ({ ...row })) } }
  })
  http.post.mockImplementation(async () => { throw new Error('本用例没打算上传') })
  http.delete.mockImplementation(async () => ({ data: { status: 'ok' } }))
  let instance = null
  const app = createApp({
    __name: 'R288DocPanelHost',
    props: DocPanel.props,
    setup: DocPanel.setup,
    render() {
      instance = getCurrentInstance()
      return h('div')
    },
  }, props)
  app.config.warnHandler = () => {}
  app.provide(SSR_CONTEXT_KEY, {})
  app.mount(node('#root'))
  live = { app, state: instance.setupState }
  return live.state
}

const stripComments = html => html.replace(/<!--[\s\S]*?-->/g, '')
const screen = async () => stripComments(await renderToString(h({
  __name: 'R288DocPanelFace',
  setup: () => live.state,
  ssrRender: DocPanel.ssrRender,
})))

const stripTags = html => html.replace(/<[^>]*>/g, '')

function byTestId(html, id) {
  const out = []
  const re = new RegExp('<(\\w+)([^>]*data-testid="' + id + '"[^>]*)>', 'g')
  let match
  while ((match = re.exec(html))) {
    const tag = match[1]
    const attrs = match[2]
    const end = html.indexOf('</' + tag + '>', re.lastIndex)
    out.push({
      tag,
      attrs,
      text: stripTags(end < 0 ? '' : html.slice(re.lastIndex, end)),
      attr: name => {
        const hit = new RegExp('(?:^|\\s)' + name + '="([^"]*)"').exec(attrs)
        return hit ? hit[1] : null
      },
    })
  }
  return out
}

const row = (over = {}) => ({
  filename: '报销制度.pdf',
  resource_id: 'doc-1',
  version: 1,
  size_bytes: 4096,
  parse_status: 'ready',
  owner_id: 'u-1',
  department: '市场部',
  created_at: '2026-09-20T00:00:00+00:00',
  index_status: 'indexed',
  index_reason: '',
  ...over,
})

async function settle() {
  await nextTick()
  await nextTick()
}

/** 走满一整轮窗口：次数用尽，返回每一拍屏上看到的那几个字。 */
async function runFullWindow() {
  const faces = []
  for (let tick = 0; tick < UPLOAD_POLL_MAX_TICKS; tick += 1) {
    await vi.advanceTimersByTimeAsync(UPLOAD_POLL_INTERVAL_MS)
    await settle()
    faces.push((byTestId(await screen(), 'doc-retrieval')[0] || { text: '' }).text)
  }
  return faces
}
// ==================== 甲 · 脸的唯一算法（纯函数判据） ====================

describe('甲 · 一行的脸只由服务端读数决定', () => {
  it('indexed 才有「已可检索」这一句', () => {
    const face = retrievalFace(row({ index_status: 'indexed' }))
    expect(face).toBe('retrievable')
    expect(retrievalFaceLabel(face)).toBe('已可检索')
  })

  it('parse_status=ready 但索引那列没记录：只说「已解析」，绝不许说「已可检索」', () => {
    const legacy = { filename: '老文件.pdf', parse_status: 'ready' }
    expect(retrievalFace(legacy)).toBe('parsed')
    const label = retrievalFaceLabel(retrievalFace(legacy))
    expect(label).toBe('已解析')
    expect(label).not.toBe(RETRIEVAL_FACE_LABEL.retrievable)
  })

  it('只有「提交了」这一件事时不许出现「已可检索」：pending 不是一颗成功的种子', () => {
    const fresh = { filename: '刚传的.pdf', parse_status: 'pending' }
    expect(retrievalFaceLabel(retrievalFace(fresh))).not.toBe('已可检索')
    expect(retrievalFace(fresh)).toBe('unreadable')
  })

  it('本屏自己那发上传还挂着 → 解析中（界面亲眼看见的在途，不是猜的）', () => {
    expect(retrievalFace(row({ parse_status: 'pending', index_status: '' }), ['报销制度.pdf'], [], [])).toBe('parsing')
    // 在途的是别的文件，不许顺手把这一行也涂成解析中。
    expect(retrievalFace(row({ parse_status: 'pending', index_status: '' }), ['别的文件.pdf'], [], [])).toBe('unreadable')
  })

  it('后端明说 parsing → 解析中；后端说 failed → 解析失败（两张不同的脸）', () => {
    expect(retrievalFace(row({ parse_status: 'parsing', index_status: '' }))).toBe('parsing')
    expect(retrievalFace(row({ parse_status: 'failed', index_status: '' }))).toBe('failed')
    expect(retrievalFaceLabel('failed')).toBe('解析失败')
    // 上一版还挂在索引里也不许报「已可检索」：这一次的重传确实失败了。
    expect(retrievalFace(row({ parse_status: 'failed', index_status: 'indexed' }))).toBe('failed')
    // 但 excluded 优先：空正文那一档已经有「未索引 + 原因」两句话在一行上了。
    expect(retrievalFace(row({ parse_status: 'failed', index_status: 'excluded', index_reason: 'no_text_content' }))).toBe('excluded')
  })

  it('excluded 在这一格不给第二张脸：R49 那张「未索引」已经说过这件事了', () => {
    const face = retrievalFace(row({ index_status: 'excluded', index_reason: 'no_text_content' }))
    expect(face).toBe('excluded')
    expect(retrievalFaceLabel(face)).toBe('')
  })

  it('盯过一整轮窗口仍没落定 → 「还没等到结果」，既不静默停在解析中也不假报成功', () => {
    const stale = { filename: '慢文件.pdf', parse_status: 'pending' }
    expect(retrievalFace(stale, [], [], ['慢文件.pdf'])).toBe('stalled')
    expect(retrievalFaceLabel('stalled')).toBe('还没等到结果')
    // 没盯过的同一枚读数只能报「读不到」：两件事不是一张脸。
    expect(retrievalFace(stale)).toBe('unreadable')
  })

  it('读数归一：大小写与首尾空白都收，认不出的取值一律当没读到', () => {
    expect(retrievalFace(row({ index_status: '  INDEXED  ' }))).toBe('retrievable')
    expect(retrievalFace(row({ parse_status: 12345, index_status: null }))).toBe('unreadable')
    expect(retrievalFace(undefined)).toBe('unreadable')
    expect(retrievalFace(row({ index_status: 'indexed' }), '不是数组', null, undefined)).toBe('retrievable')
  })

  it('六张脸的用词两两不同，「解析失败」与「长时间没完成」与「读不到」不是一张脸', () => {
    const faces = ['parsing', 'retrievable', 'parsed', 'failed', 'stalled', 'unreadable']
    const labels = faces.map(face => retrievalFaceLabel(face))
    expect(labels).toEqual(['解析中', '已可检索', '已解析', '解析失败', '还没等到结果', '读不到'])
    expect(new Set(labels).size).toBe(labels.length)
  })

  it('isUnsettledFace 只认两张没落定的脸；failed 与 stalled 都是终态', () => {
    expect(['parsing', 'unreadable'].map(isUnsettledFace)).toEqual([true, true])
    expect(['retrievable', 'parsed', 'failed', 'stalled', 'excluded'].map(isUnsettledFace)).toEqual([false, false, false, false, false])
  })

  it('窗口判据：数满上限就停、窗口空了就停、全部落定就停', () => {
    expect(shouldReadUploadAgain(['parsing'], 0, 6)).toBe(true)
    expect(shouldReadUploadAgain(['retrievable'], 0, 6)).toBe(false)
    expect(shouldReadUploadAgain([], 0, 6)).toBe(false)
    expect(shouldReadUploadAgain(['parsing'], 6, 6)).toBe(false)
  })
})

// ==================== 乙 · 不刷新那条路 ====================

describe('乙 · 上传后不刷新：状态只跟着服务端读数走', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    serverRows = []
    catalogReads = 0
    catalogFailures = 0
  })

  afterEach(() => {
    live?.app?.unmount()
    live = null
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('挂载只发一发列表：这一屏不留常驻定时器', async () => {
    serverRows = [row()]
    mountPanel()
    await settle()
    expect(catalogReads).toBe(1)
    await vi.advanceTimersByTimeAsync(UPLOAD_POLL_INTERVAL_MS * UPLOAD_POLL_MAX_TICKS * 2)
    await settle()
    expect(catalogReads).toBe(1)
  })

  it('服务端不改口，屏上就不许出现「已可检索」：走满窗口才收，且收得干净', async () => {
    serverRows = [{ filename: '慢文件.pdf', parse_status: 'pending' }]
    mountPanel()
    await settle()
    live.state.armUploadPoll(['慢文件.pdf'])

    const faces = await runFullWindow()
    // 每一拍都真的去读了一次：状态推进的物理来源只有这一发 GET。
    expect(catalogReads).toBe(1 + UPLOAD_POLL_MAX_TICKS)
    expect(faces).not.toContain('已可检索')
    // 数满次数：脸从「读不到」换成「还没等到结果」，并且就此收表，不在后台无限续。
    expect(faces[faces.length - 1]).toBe('还没等到结果')
    const before = catalogReads
    await vi.advanceTimersByTimeAsync(UPLOAD_POLL_INTERVAL_MS * 3)
    await settle()
    expect(catalogReads).toBe(before)
  })

  it('服务端第 2 拍改口 indexed：不刷新也立刻换成「已可检索」，并顺手停表', async () => {
    serverRows = [{ filename: '慢文件.pdf', parse_status: 'pending' }]
    mountPanel()
    await settle()
    live.state.armUploadPoll(['慢文件.pdf'])

    await vi.advanceTimersByTimeAsync(UPLOAD_POLL_INTERVAL_MS)
    await settle()
    expect((byTestId(await screen(), 'doc-retrieval')[0] || {}).text).toBe('读不到')

    serverRows = [row({ filename: '慢文件.pdf' })]
    await vi.advanceTimersByTimeAsync(UPLOAD_POLL_INTERVAL_MS)
    await settle()
    const face = byTestId(await screen(), 'doc-retrieval')[0]
    expect(face.text).toBe('已可检索')
    expect(face.attr('data-retrieval-face')).toBe('retrievable')
    // 落定即停表：后面那几拍不该再替它发请求。
    const before = catalogReads
    await vi.advanceTimersByTimeAsync(UPLOAD_POLL_INTERVAL_MS * 5)
    await settle()
    expect(catalogReads).toBe(before)
  })

  it('服务端说 failed：脸是「解析失败」，不是「解析中」，也不是一句「读不到」', async () => {
    serverRows = [row({ filename: '坏文件.pdf', parse_status: 'failed', index_status: '' })]
    mountPanel()
    await settle()
    live.state.armUploadPoll(['坏文件.pdf'])
    await vi.advanceTimersByTimeAsync(UPLOAD_POLL_INTERVAL_MS)
    await settle()
    const face = byTestId(await screen(), 'doc-retrieval')[0]
    expect(face.text).toBe('解析失败')
    expect(face.attr('data-retrieval-face')).toBe('failed')
  })

  it('取数失败与长时间没完成是两张脸：一个说「读不到」，一个说「还没等到结果」', async () => {
    serverRows = [{ filename: '慢文件.pdf', parse_status: 'pending' }]
    mountPanel()
    await settle()
    live.state.armUploadPoll(['慢文件.pdf'])
    catalogFailures = 1
    await vi.advanceTimersByTimeAsync(UPLOAD_POLL_INTERVAL_MS)
    await settle()
    const failedRead = byTestId(await screen(), 'doc-retrieval')[0]
    expect(failedRead.text).toBe('读不到')
    expect(failedRead.attr('data-retrieval-face')).toBe('unreadable')

    catalogFailures = 0
    const rest = await runFullWindow()
    expect(rest[rest.length - 1]).toBe('还没等到结果')
  })

  it('「还没等到结果」旁边要有出口：点一次「再读一次」重新开窗，旧的那句话同时作废', async () => {
    serverRows = [{ filename: '慢文件.pdf', parse_status: 'pending' }]
    mountPanel()
    await settle()
    live.state.armUploadPoll(['慢文件.pdf'])
    await runFullWindow()
    const stalled = byTestId(await screen(), 'doc-retrieval')[0]
    expect(stalled.text).toBe('还没等到结果')
    expect(byTestId(await screen(), 'doc-retrieval-recheck')).toHaveLength(1)

    const before = catalogReads
    live.state.armUploadPoll(['慢文件.pdf'])
    await settle()
    expect(byTestId(await screen(), 'doc-retrieval')[0].text).not.toBe('还没等到结果')
    await vi.advanceTimersByTimeAsync(UPLOAD_POLL_INTERVAL_MS)
    await settle()
    expect(catalogReads).toBe(before + 1)
  })

  it('同一篇重传：请求还挂着的时候这一行退回「解析中」，不许拿上一版的 indexed 冒充这一次', async () => {
    serverRows = [row()]
    mountPanel()
    await settle()
    expect(byTestId(await screen(), 'doc-retrieval')[0].text).toBe('已可检索')

    let release
    http.post.mockImplementation(() => new Promise(resolve => {
      release = () => resolve({
        data: { status: 'ok', filename: '报销制度.pdf', parse_status: 'ready', index_status: 'indexed', message: '已进入知识库索引' },
      })
    }))
    const pending = live.state.uploadSingleFile({ name: '报销制度.pdf' })
    await settle()
    const during = byTestId(await screen(), 'doc-retrieval')[0]
    expect(during.text, '上传还挂着就报「已可检索」：把「我提交了」当成了「已经能问到」').toBe('解析中')
    expect(during.attr('data-retrieval-face')).toBe('parsing')

    release()
    await pending
    await settle()
    expect(byTestId(await screen(), 'doc-retrieval')[0].text).toBe('已可检索')
  })

  it('上传回执那条路（整屏不重新挂载）与刷新那条路落在同一张脸上', async () => {
    // 不刷新：先空列表挂载，再走真实的 uploadSingleFile。
    mountPanel()
    await settle()
    http.post.mockImplementation(async () => {
      // 后端在同一个请求里就把行落库：这里照它的行为改服务端那一侧的账。
      serverRows = [row({ filename: '新制度.pdf' })]
      return {
        data: {
          status: 'ok',
          filename: '新制度.pdf',
          parse_status: 'ready',
          index_status: 'indexed',
          index_message: '已进入知识库索引',
          message: '已进入知识库索引',
        },
      }
    })
    await live.state.uploadSingleFile({ name: '新制度.pdf' })
    await settle()
    const noRefresh = byTestId(await screen(), 'doc-retrieval')[0]
    expect(noRefresh.text).toBe('已可检索')

    // 刷新：重新挂载一发，服务端同一行同一次读数。
    live.app.unmount()
    live = null
    serverRows = [row({ filename: '新制度.pdf' })]
    mountPanel()
    await settle()
    const refreshed = byTestId(await screen(), 'doc-retrieval')[0]
    expect(refreshed.text).toBe(noRefresh.text)
    expect(refreshed.attr('data-retrieval-face')).toBe(noRefresh.attr('data-retrieval-face'))
  })

  it('离开这一屏之后，窗口不再替它发请求', async () => {
    serverRows = [{ filename: '慢文件.pdf', parse_status: 'pending' }]
    mountPanel()
    await settle()
    live.state.armUploadPoll(['慢文件.pdf'])
    await vi.advanceTimersByTimeAsync(UPLOAD_POLL_INTERVAL_MS)
    await settle()
    live.app.unmount()
    live = null
    const before = catalogReads
    await vi.advanceTimersByTimeAsync(UPLOAD_POLL_INTERVAL_MS * UPLOAD_POLL_MAX_TICKS)
    expect(catalogReads).toBe(before)
  })
})
// ==================== 丙 · 接上原语之后门还在 ====================

describe('丙 · 反证③的靶子：权限门、两步确认门、忙碌门都还在', () => {
  beforeEach(() => {
    serverRows = [row()]
    catalogReads = 0
    catalogFailures = 0
  })

  afterEach(() => {
    live?.app?.unmount()
    live = null
    vi.restoreAllMocks()
  })

  it('非管理员这一屏不画删除入口，也不画批量栏；管理员才画', async () => {
    mountPanel({ userRole: 'staff' })
    await settle()
    const staff = await screen()
    expect(byTestId(staff, 'document-delete-one')).toHaveLength(0)
    expect(byTestId(staff, 'document-delete-selected')).toHaveLength(0)

    live.app.unmount()
    mountPanel({ userRole: 'admin' })
    await settle()
    const admin = await screen()
    expect(byTestId(admin, 'document-delete-one')).toHaveLength(1)
    expect(byTestId(admin, 'document-delete-one')[0].attr('disabled')).toBeNull()
  })

  it('第一次点击只把这一行改成「确认删除？」，第二次的点击才真的发 DELETE', async () => {
    mountPanel({ userRole: 'admin' })
    await settle()
    expect(http.delete).not.toHaveBeenCalled()

    await live.state.requestDeleteOne('报销制度.pdf')
    await settle()
    expect(http.delete, '第一发点击就把文件删了：两步确认门被摘了').not.toHaveBeenCalled()
    const armed = await screen()
    expect(byTestId(armed, 'document-delete-one')[0].text).toContain('确认删除')
    expect(byTestId(armed, 'document-delete-one-cancel')).toHaveLength(1)

    await live.state.requestDeleteOne('报销制度.pdf')
    await settle()
    expect(http.delete).toHaveBeenCalledTimes(1)
  })

  it('删除进行中不补第二刀：忙碌门与两步确认门是两枚不同的门', async () => {
    mountPanel({ userRole: 'admin' })
    await settle()
    // 把这发 DELETE 停在「还没回来」：忙碌态必须是真忙碌，否则测的是另一枚门。
    let release
    http.delete.mockImplementation(() => new Promise(resolve => {
      release = () => resolve({ data: { status: 'ok' } })
    }))
    await live.state.requestDeleteOne('报销制度.pdf')
    expect(http.delete).not.toHaveBeenCalled()
    live.state.requestDeleteOne('报销制度.pdf')
    await settle()
    expect(http.delete).toHaveBeenCalledTimes(1)

    live.state.requestDeleteOne('报销制度.pdf')
    live.state.requestDeleteOne('报销制度.pdf')
    await settle()
    expect(http.delete, '删除进行中又补了一刀：忙碌门被摘了').toHaveBeenCalledTimes(1)
    release()
    await settle()
    expect(http.delete).toHaveBeenCalledTimes(1)
  })

  it('换目标不会拿着上一行的确认去删这一行：点 A 之后再点 B，两行都没删', async () => {
    serverRows = [row({ filename: 'A.pdf' }), row({ filename: 'B.pdf' })]
    mountPanel({ userRole: 'admin' })
    await settle()
    await live.state.requestDeleteOne('A.pdf')
    await live.state.requestDeleteOne('B.pdf')
    await settle()
    expect(http.delete).not.toHaveBeenCalled()
    expect(live.state.uploadStalled).toEqual([])
  })

  it('图没回来的时候放大按钮是 disabled，图回来了才放开：门跟着读数走', async () => {
    const pending = await renderToString(h(ChartViewer, { src: 'artifact:chart-1', caption: '费用趋势' }))
    const locked = byTestId(pending, 'chart-zoom')[0]
    expect(locked, '放大按钮没接 disabled：图还没回来就能点').toBeDefined()
    expect(locked.attrs).toMatch(/disabled/)

    const ready = await renderToString(h(ChartViewer, { src: '/static/chart-1.png', caption: '费用趋势' }))
    expect(byTestId(ready, 'chart-zoom')[0].attrs).not.toMatch(/disabled/)
    expect(byTestId(ready, 'chart-zoom')).toHaveLength(1)
  })
})
