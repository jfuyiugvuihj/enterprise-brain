/**
 * R237 · R49 判据② —— 被排除的文档必须在 UI 上看得见为「未索引」
 *
 * 判据原文（跟进单 §21 表 L520）：「② 被排除文档在 UI 可见为『未索引』」。
 * 禁改边界：不得静默丢弃用户上传。
 *
 * 取证（行号在本件基点 a856593 上由 rg 复现，未抄上一班快照 866c2f3）：
 *   后端早有这枚事实 —— app/documents/index_policy.py:28-30 给出 indexed / excluded / unknown，
 *   app/documents/catalog.py:225 的 public_document_row 随每一行发出 index_status 与
 *   index_reason；catalog.py:239-252 明写「键缺席 = R49 之前入库的历史行，客户端不得据此
 *   显示未索引」。GET /documents/catalog（app/api/v1/chat.py:3691）经 _classify_document_rows
 *   → public_document_row 把这两枚字段原样带进响应体。
 *   缺的【不是】后端契约：改之前的 DocPanel.vue loadDocs 把每一行压成裸 filename，
 *   服务端答了、界面把答案扔了 —— 被排除的那篇就此在列表里没有脸。本单补的就是这张脸。
 *
 * 手法（本仓没有 jsdom，也不 npm i；沿用 r198 / r202 那条「取真身」路）：
 *   ① createRenderer + 内存虚拟节点挂 DocPanel 自己的 setup ⇒ onMounted → loadDocs →
 *     http.get('/documents/catalog') 走的是产品那一遍，换掉的只有网络层与渲染器；
 *   ② 再把【SFC 自己编译出的那份 ssrRender】套在这份活 setupState 上出 HTML ——
 *     屏上那五个字判的是真模板产物，不是测试自己拼的一行，也不是源码字符串。
 *   总控可照同一批 data-testid（documents-panel / doc-row / doc-index-status /
 *   doc-index-reason / document-excluded-count）用 npx playwright 复验。
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, getCurrentInstance, h, nextTick } from 'vue'
import { renderToString } from '@vue/server-renderer'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() }, authedFetch: vi.fn() }
})

import DocPanel from '../DocPanel.vue'
import { http } from '../../lib/http'

const SRC_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const readSrc = rel => readFileSync(join(SRC_ROOT, rel), 'utf8').replace(/\r\n/g, '\n')
const panelSource = () => readSrc(join('components', 'DocPanel.vue'))
const codeOnly = text => text
  .replace(/<!--[\s\S]*?-->/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .split('\n')
  .filter(line => !/^\s*\/\//.test(line))
  .join('\n')

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
      target.parent.children.splice(target.parent.children.indexOf(target), 1)
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

const { createApp } = createRenderer(nodeOps)
const SSR_CONTEXT_KEY = Symbol.for('v-scx')

let live = null

/** 真挂一次：跑完 onMounted 那一发列表请求，把活 setupState 留在 live 上。 */
async function mountPanel(rows, props = {}, failure = null) {
  http.get.mockImplementation(async (url) => {
    if (String(url).endsWith('/documents/catalog')) {
      if (failure) throw failure
      return { data: { documents: rows } }
    }
    return { data: {} }
  })
  let instance = null
  const app = createApp({
    __name: 'R237DocPanelHost',
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
  await nextTick()
  await nextTick()
  live = { app, state: instance.setupState }
  return live.state
}

/** 屏：把 SFC 自己那份 ssrRender 套在活状态上，拿到真模板 HTML。
 *  注释一并剥掉：模板里那句「不许拿上传跳过冒充未索引」是写给工程师看的，
 *  不在屏上 ——「屏上有没有这五个字」只准判可见产物，否则反向钉就是空转。 */
const stripComments = html => html.replace(/<!--[\s\S]*?-->/g, '')
const screen = async () => stripComments(await renderToString(h({
  __name: 'R237DocPanelFace',
  setup: () => live.state,
  ssrRender: DocPanel.ssrRender,
})))

const stripTags = html => html.replace(/<[^>]*>/g, '')

/** 按 data-testid 取元素：属性从开标签读，正文从内层剥标签读。 */
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

afterEach(() => {
  live?.app?.unmount()
  live = null
  http.get.mockReset()
})

// ==================== 行形状逐字段照抄后端，不猜 ====================

const row = (over = {}) => ({
  filename: '正常制度.pdf',
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

// 六枚稳定原因码逐枚点名（app/documents/index_policy.py:44-48）。
const REASON_CASES = [
  ['no_text_content', '解析出来是空的'],
  ['below_minimum_size', '正文太短'],
  ['placeholder_skeleton', '未填写的占位符'],
  ['outline_only_shell', '只有小节标题'],
  ['unchanged_content', '内容未变化'],
  ['index_refused', '索引层拒绝'],
]

describe('甲 · 判据②本体：excluded 行必须画出一张带原因的脸', () => {
  it.each(REASON_CASES)('稳定码 %s 在屏上是一张人话脸，且裸码名不外泄', async (reason, needle) => {
    await mountPanel([row({ filename: '草稿.md', index_status: 'excluded', index_reason: reason })])
    const html = await screen()

    const flag = byTestId(html, 'doc-index-status')
    expect(flag, `${reason} 这一行没画出「未索引」`).toHaveLength(1)
    expect(flag[0].text).toBe('未索引')
    expect(flag[0].attr('data-index-status')).toBe('excluded')

    const notice = byTestId(html, 'doc-index-reason')
    expect(notice, `${reason} 这一行没给出原因`).toHaveLength(1)
    expect(notice[0].text).toContain(needle)
    // 禁改边界：被排除不等于被丢弃 —— 屏上必须说文件与目录行都还在。
    expect(notice[0].text).toContain('文件与目录记录均已保留')
    expect(notice[0].attr('data-index-reason')).toBe(reason)
    // V6 同族：给人看的那一行里不许夹裸码名（码走 data-* 通道给测试与诊断用）。
    expect(notice[0].text).not.toContain(reason)
  })

  // R421 改口（同一口径，断言一字未减）：本件原钉的是「兜底那一句的字面量」。它钉的事实没换过 ——
  // 未知码与缺字段那一格仍要给人话、不带数字、不带裸码名、不许 undefined；换掉的只是那句人话里的
  // 一个词：屏名「知识库」从这屏的文案里退下去了（这一屏叫什么由路由 meta.title 一个人说，R412/R421），
  // 兜底句今天说「未进入检索索引」，钉的还是同一段文字所在的同一个位置。
  it('excluded 但没带原因码：仍然有脸，不许因为读不出原因就整格消失', async () => {
    await mountPanel([row({ index_status: 'excluded', index_reason: '' })])
    const html = await screen()
    expect(byTestId(html, 'doc-index-status')).toHaveLength(1)
    expect(byTestId(html, 'doc-index-reason')[0].text).toContain('未进入检索索引')
  })

  it('原因码是字典里没有的新码：给人话兜底，不给 undefined', async () => {
    await mountPanel([row({ index_status: 'excluded', index_reason: 'a_reason_nobody_registered_yet' })])
    const text = byTestId(await screen(), 'doc-index-reason')[0].text
    expect(text).toContain('未进入检索索引')
    expect(text).not.toContain('undefined')
  })

  it('未索引计数只来自响应里的行', async () => {
    await mountPanel([
      row({ filename: 'a.md', index_status: 'excluded', index_reason: 'no_text_content' }),
      row({ filename: 'b.md', index_status: 'excluded', index_reason: 'below_minimum_size' }),
      row({ filename: 'c.md', index_status: 'indexed' }),
    ])
    const html = await screen()
    const count = byTestId(html, 'document-excluded-count')
    expect(count).toHaveLength(1)
    expect(count[0].text).toContain('2')
    expect(byTestId(html, 'doc-index-status')).toHaveLength(2)
  })

  it('被排除的那一行仍然在列表里，打开/下载/删除三个动作一个不少', async () => {
    await mountPanel([row({ filename: '空壳.md', index_status: 'excluded', index_reason: 'no_text_content' })])
    const html = await screen()
    expect(byTestId(html, 'doc-row')).toHaveLength(1)
    expect(html).toContain('空壳.md')
    for (const label of ['打开', '下载']) expect(html).toContain(`>${label}<`)
  })
})

describe('乙 · 反向钉：这张脸只可能由数据驱动', () => {
  it('全是 indexed 的响应：屏上一个「未索引」都不许出现', async () => {
    await mountPanel([row({ filename: 'a.md' }), row({ filename: 'b.md' })])
    const html = await screen()
    expect(html).not.toContain('未索引')
    expect(byTestId(html, 'doc-index-status')).toHaveLength(0)
    expect(byTestId(html, 'document-excluded-count')).toHaveLength(0)
  })

  it('键缺席的历史行（R49 之前入库）：留 unrecorded 一行，绝不画成「故意未索引」', async () => {
    const legacy = row({ filename: '老文件.txt' })
    delete legacy.index_status
    delete legacy.index_reason
    await mountPanel([legacy])
    const html = await screen()
    const lines = byTestId(html, 'doc-row')
    expect(lines, '历史行不许从列表里消失（不得静默丢弃用户上传）').toHaveLength(1)
    expect(lines[0].attr('data-index-status')).toBe('unrecorded')
    expect(html).not.toContain('未索引')
  })

  it('indexed 行如实标 indexed，不蹭那张未索引的脸', async () => {
    await mountPanel([row({ filename: 'a.md', index_status: 'indexed' })])
    const html = await screen()
    expect(byTestId(html, 'doc-row')[0].attr('data-index-status')).toBe('indexed')
    expect(html).not.toContain('未索引')
  })

  it('上传那一格回 skipped 不等于库内未索引：两条路在源码里互不引用', () => {
    const code = codeOnly(panelSource())
    expect(code).toMatch(/v-if="isExcluded\(row\)"/)
    expect(code).toMatch(/item\.status = res\.data\.status === 'ok' \? 'done' : 'skipped'/)
    expect(code).not.toMatch(/index_status[\s\S]{0,160}item\.status/)
  })
})

describe('丙 · 行改成对象之后，列表原有能力一项不许掉', () => {
  it('loadDocs 不再把行压成裸 filename：index_status 有地方住', () => {
    const code = panelSource()
    expect(code).not.toMatch(/\.map\(item => \(typeof item === 'string' \? item : item\.filename\)\)/)
    expect(code).toMatch(/\{ filename: item \}/)
  })

  it('搜索按文件名过滤仍然生效（行对象没把过滤打挂）', async () => {
    await mountPanel([row({ filename: '差旅制度.pdf' }), row({ filename: '年会通知.docx' })])
    expect(byTestId(await screen(), 'doc-row')).toHaveLength(2)
    live.state.searchQuery = '差旅'
    await nextTick()
    const left = byTestId(await screen(), 'doc-row')
    expect(left).toHaveLength(1)
    expect(left[0].attr('data-index-status')).toBe('indexed')
    expect(await screen()).toContain('差旅制度.pdf')
    expect(await screen()).not.toContain('年会通知.docx')
  })

  it('管理员全选走的是文件名，未索引行也在同一份选择集里', async () => {
    await mountPanel([
      row({ filename: 'a.md', index_status: 'excluded', index_reason: 'no_text_content' }),
      row({ filename: 'b.md' }),
    ], { userRole: 'admin' })
    expect(live.state.isAdmin).toBe(true)
    live.state.toggleAll()
    expect([...live.state.selectedFiles].sort()).toEqual(['a.md', 'b.md'])
    expect(byTestId(await screen(), 'doc-index-status')).toHaveLength(1)
  })

  it('这一屏只读 /documents/catalog 一条列表端点', async () => {
    await mountPanel([row()])
    const urls = http.get.mock.calls.map(call => String(call[0]))
    expect(urls.length).toBeGreaterThanOrEqual(1)
    expect(urls.every(url => url.endsWith('/documents/catalog'))).toBe(true)
  })
})

describe('丁 · 首屏诚实：响应没回来之前不画任何索引状态', () => {
  it('在读的时候不摆「未索引」，回来之后才摆', async () => {
    let release
    http.get.mockImplementation(() => new Promise(resolve => { release = resolve }))
    let instance = null
    const app = createApp({
      __name: 'R237PendingHost',
      props: DocPanel.props,
      setup: DocPanel.setup,
      render() { instance = getCurrentInstance(); return h('div') },
    }, {})
    app.config.warnHandler = () => {}
    app.provide(SSR_CONTEXT_KEY, {})
    app.mount(node('#root'))
    await nextTick()
    live = { app, state: instance.setupState }
    expect(await screen()).not.toContain('未索引')

    release({ data: { documents: [row({ index_status: 'excluded', index_reason: 'no_text_content' })] } })
    await nextTick()
    await nextTick()
    expect(byTestId(await screen(), 'doc-index-status')).toHaveLength(1)
  })

  it('列表请求失败：说清没拿到，也不拿空数组冒充「全都索引了」', async () => {
    await mountPanel([], {}, Object.assign(new Error('Network Error'), {
      isAxiosError: true, code: 'ERR_NETWORK', request: {}, config: { url: '/documents/catalog' },
    }))
    const html = await screen()
    expect(html).toContain('文档列表没加载出来')
    expect(html).not.toContain('未索引')
  })
})