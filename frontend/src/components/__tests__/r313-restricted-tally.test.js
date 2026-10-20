/**
 * R313 · 格二 —— 对着后端明挂的 restricted 说「知识库是空的」，那是 P1 级假话
 *
 * 病灶（行号在基点 217d542 现取）：GET /documents/catalog 在 app/api/v1/chat.py:4235 挂了
 * `result["restricted"] = restricted_summary(withheld, DOCUMENT_TEMPLATE)`（形状全站只出自
 * app/api/v1/restricted.py 那一份 —— R200），而 DocPanel:717 只看 `docs.length === 0` 就说
 * 「知识库是空的」。一名权限不足的员工站在有资料的库里，界面告诉他「这里什么都没有」——
 * 他去猜、去重复上传、去找管理员；管理员看到的还是同一句假话。
 *
 * 判据与样板都借同仓既有那一份（DataPanel.vue:124 取 res.data.restricted、frontend/src/components/DataPanel.vue:288 起那段
 * restrictedNotice 就是既定的说法），本单不另创口径：
 *   ① 把 restricted 读出来并给正脸，说「有 N 份存在但你看不见」；
 *   ② 🔴 一个文件名都不点 —— 点名一件无权访问的资源本身就是泄露，那两份投影里也没有名字；
 *   ③ 「有，但看不见」与「没有」是两句正相反的话，不许同时站在这块屏上；
 *   ④ 上一轮的 N 不属于这一轮：重载先清、失败也清，不许留成陈话；断网刷这一屏不许白屏。
 *
 * 手法同 r237-r49 / r288：createRenderer + 内存虚拟节点挂 DocPanel 自己的 setup（onMounted →
 * loadDocs 走产品那一遍，网络层换掉），再把 SFC 那份 ssrRender 套在活 setupState 上出 HTML。
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

import DocPanel from '../DocPanel.vue'
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
/** 服务端这一腿的账：只有改它才算「后端改口」，界面上的字改不了它。 */
let server = { body: { documents: [] }, fail: false }

function mountPanel(props = {}) {
  http.get.mockImplementation(async (url) => {
    if (!String(url).endsWith('/documents/catalog')) return { data: {} }
    catalogReads += 1
    if (server.fail) {
      throw Object.assign(new Error('Network Error'), {
        isAxiosError: true, code: 'ERR_NETWORK', request: {}, config: { url },
      })
    }
    return { data: server.body }
  })
  let instance = null
  const app = createApp({
    __name: 'R313RestrictedHost',
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
const screen = async () => plainText(await faceRender('R313RestrictedFace'))
const screenHtml = async () => faceRender('R313RestrictedHtml')

/** 由 data-testid 取出那一块的文本（与 r237 / r288 同一把量具）。 */
function blockByTestId(html, id) {
  const out = []
  const re = new RegExp('<(\\w+)([^>]*data-testid="' + id + '"[^>]*)>', 'g')
  let match
  let hitAttrs
  while ((hitAttrs = re.exec(html))) {
    const tag = hitAttrs[1]
    const attrs = hitAttrs[2]
    const bodyStart = hitAttrs.index + hitAttrs[0].length
    const end = html.indexOf('</' + tag + '>', bodyStart)
    out.push({
      tag,
      attrs,
      text: plainText(end < 0 ? '' : html.slice(bodyStart, end)),
      attr: name => {
        const hit = new RegExp('(?:^|\\s)' + name + '="([^"]*)"').exec(attrs)
        return hit ? hit[1] : null
      },
    })
  }
  return out
}

// R421 改口（同一口径，断言一字未减）：这枚常数钉的是【文档标签那一格空脸的原文】，不是屏名。
// 换它的原因正是那句原文里带着一枚被裁定退下的叫法 ——「知识库」（跟进单 G17，R412 已裁定它不作这屏的名）。
// 本件真正钉的两件事一个字没动：有 restricted 时空脸不许上屏、没有 restricted 时空脸必须上屏。
// 下面所有断言都从这枚常数取字，所以改这一处就够，不在用例里抄第二份原文。
const EMPTY_FACE = '这里还没有文档'
const RESTRICTED_FACE = 'documents-restricted'
/** 后端那一句原话（app/api/v1/restricted.py::DOCUMENT_TEMPLATE，count 换成 2）：照搬，不另写。 */
const BACKEND_MESSAGE = '有 2 份文档存在，但不在当前账号的可见范围内；如需访问，请联系管理员核对你的部门归属与文档的部门、密级标注。'
const ROW = { filename: '制度汇编.pdf', owner_id: 'u-1', size_bytes: 2048, parse_status: 'ready', index_status: 'indexed' }

async function settle() {
  await nextTick()
  await nextTick()
}

/** 起一屏：先摆好服务端那一腿的账，再挂载（onMounted 就是这一发 GET /documents/catalog）。 */
async function openedWith(body, fail = false) {
  server = { body: body === null ? {} : body, fail }
  const state = mountPanel()
  await settle()
  return state
}

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
  catalogReads = 0
  server = { body: { documents: [] }, fail: false }
  live = null
})

// ==================== 甲 · 那句假话被换掉 ====================

describe('R313 格二 甲 · 「有 N 份存在但你看不见」必须给正脸', () => {
  it('库里被挡掉 2 份 ⇒ 屏上说「还有 2 份文档没有列在这里」，且不说空脸那一句', async () => {
    await openedWith({ documents: [], restricted: { count: 2, reason_codes: ['department_scope_denied'], message: BACKEND_MESSAGE } })
    const html = await faceRender('R313A1')
    const text = plainText(html)
    expect(blockByTestId(html, RESTRICTED_FACE)).toHaveLength(1)
    expect(text).toContain('还有 2 份文档没有列在这里')
    expect(text).toContain(BACKEND_MESSAGE)
    expect(text).not.toContain(EMPTY_FACE)
  })

  it('列表有货时同样要说：两句话各说各的，谁也不许盖住谁', async () => {
    await openedWith({ documents: [{ ...ROW }], restricted: { count: 3, message: '有 3 份文档存在，但不在当前账号的可见范围内。' } })
    const text = await screen()
    expect(text).toContain('制度汇编.pdf')
    expect(text).toContain('还有 3 份文档没有列在这里')
    expect(text).not.toContain(EMPTY_FACE)
  })

  it('句子读的是 restricted.message 本身：后端改口，屏上跟着改（不是写死的样板文案）', async () => {
    const state = await openedWith({ documents: [], restricted: { count: 2, message: BACKEND_MESSAGE } })
    expect(await screen()).toContain('请联系管理员核对你的部门归属')
    server.body = { documents: [], restricted: { count: 2, message: '后端换了一句话：这两份在另一条链上。' } }
    await state.loadDocs()
    await settle()
    const text = await screen()
    expect(text).toContain('后端换了一句话')
    expect(text).not.toContain('请联系管理员核对你的部门归属')
  })

  it('🔴 一枚文件名都不点：投影里就算混进名字，也不许上屏', async () => {
    await openedWith({
      documents: [],
      restricted: {
        count: 2,
        reason_codes: ['department_scope_denied', 'clearance_insufficient'],
        message: BACKEND_MESSAGE,
        documents: ['机密薪酬表.pdf', '并购方案.pdf'],
        filenames: ['组织架构调整.xlsx'],
      },
    })
    const text = await screen()
    for (const leaked of ['机密薪酬表', '并购方案', '组织架构调整']) {
      expect(text, '点名了一件对方无权访问的资源：' + leaked).not.toContain(leaked)
    }
    // 裸码名也不进给人看的那一行（V6 同族口径：码走 data-* 通道）。
    expect(text).not.toContain('department_scope_denied')
    expect(text).not.toContain('clearance_insufficient')
  })

  it('这一格不给「重试」：重试不会把权限试出来（与 DataPanel 的 restricted 同一档）', async () => {
    await openedWith({ documents: [], restricted: { count: 2, message: BACKEND_MESSAGE } })
    const html = await faceRender('R313A5')
    expect(blockByTestId(html, RESTRICTED_FACE)[0].text).toContain('还有 2 份')
    expect(html).not.toContain('data-testid="ui-error-retry"')
  })
})

// ==================== 乙 · 数与形状 ====================

describe('R313 格二 乙 · 只认正整数，其余一律不编话', () => {
  it('标题里的数与 data-restricted-count 是同一枚数（界面不数第二遍）', async () => {
    await openedWith({ documents: [{ ...ROW }], restricted: { count: 4, message: '有 4 份文档存在，但不在当前账号的可见范围内。' } })
    const block = blockByTestId(await faceRender('R313B1'), RESTRICTED_FACE)[0]
    expect(block.attr('data-restricted-count')).toBe('4')
    expect(block.text).toContain('还有 4 份文档没有列在这里')
  })

  it('字符串与小数都收成正整数（"3"→3、2.7→2），后端给什么形状都不糊', async () => {
    for (const [given, shown] of [['3', '还有 3 份'], [2.7, '还有 2 份'], [10, '还有 10 份']]) {
      server = { body: { documents: [], restricted: { count: given, message: '' } }, fail: false }
      catalogReads = 0
      mountPanel()
      await settle()
      expect(await screen(), 'count=' + JSON.stringify(given)).toContain(shown)
    }
  })

  it('0 / 负数 / NaN / 缺席 / 非对象 ⇒ 这一格不存在，空脸那一句才许说话', async () => {
    for (const junk of [0, -5, NaN, Infinity, null, undefined, 'abc', {}, [], '有 3 份']) {
      await openedWith({ documents: [], restricted: junk })
      const html = await faceRender('R313B3')
      expect(blockByTestId(html, RESTRICTED_FACE), '这一枚不该说话：' + JSON.stringify(junk)).toHaveLength(0)
      expect(plainText(html)).toContain(EMPTY_FACE)
    }
  })

  it('只给 count 不给 message：兜底句仍说「不在可见范围内」，也不假称空', async () => {
    await openedWith({ documents: [], restricted: { count: 5 } })
    const text = await screen()
    expect(text).toContain('还有 5 份文档没有列在这里')
    expect(text).toContain('不在当前账号的可见范围内')
    expect(text).not.toContain(EMPTY_FACE)
    expect(text).not.toContain('undefined')
  })
})

// ==================== 丙 · 陈话、断网、请求账 ====================

describe('R313 格二 丙 · 上一轮的话不属于这一轮', () => {
  it('重载后后端不再拒任何东西 ⇒ 那句 N 必须消失，不许留成陈话', async () => {
    const state = await openedWith({ documents: [], restricted: { count: 2, message: BACKEND_MESSAGE } })
    expect(await screen()).toContain('还有 2 份')
    server.body = { documents: [{ ...ROW }] }
    await state.loadDocs()
    await settle()
    const text = await screen()
    expect(text).not.toContain('还有 2 份')
    expect(text).not.toContain('有 2 份文档存在')
  })

  it('断网（这一发失败）⇒ 不白屏、不给陈话，只说「文档列表没加载出来」', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const state = await openedWith({ documents: [], restricted: { count: 2, message: BACKEND_MESSAGE } })
    expect(await screen()).toContain('还有 2 份')
    server = { body: {}, fail: true }
    await state.loadDocs()
    await settle()
    const text = await screen()
    expect(text).toContain('文档列表')
    expect(text).toContain('没加载出来')
    expect(text, '请求失败却把上一轮的 N 留在屏上').not.toContain('还有 2 份')
    // 原钉的是 toContain('知识库')：那是拿一枚屏名当「屏上还有东西」的代理字 —— 既比事实松（任何一句带
    // 这个词的话都能蒙过），又正好撞上 R421 要退下去的那一枚。换成现读空脸原文：钉的还是「失败时不白屏」。
    expect(text, '失败时空脸那一句仍在（第二句假话不许可，但更不许整块白屏）').toContain(EMPTY_FACE)
    spy.mockRestore()
  })

  it('断网首屏也不白屏：面板骨架与错误脸都在，没有半截 restricted', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    await openedWith({}, true)
    const html = await faceRender('R313C3')
    const text = plainText(html)
    // 同上：这一格要的是「首屏失败也还剩一张能读的脸」，读的是空脸原文本身，不是一枚屏名。
    expect(text).toContain(EMPTY_FACE)
    expect(blockByTestId(html, RESTRICTED_FACE)).toHaveLength(0)
    expect(text).not.toContain('还有')
    spy.mockRestore()
  })

  it('这一格零新增请求：restricted 就住在 catalog 那一发里', async () => {
    const state = await openedWith({ documents: [{ ...ROW }], restricted: { count: 2, message: BACKEND_MESSAGE } })
    expect(catalogReads).toBe(1)
    const urls = http.get.mock.calls.map(call => call[0])
    expect(urls.every(url => String(url).endsWith('/documents/catalog'))).toBe(true)
    await screen()
    await screen()
    await state.loadDocs()
    await settle()
    expect(http.get.mock.calls.length, '多出来的那一发就是「为此多开一次请求」').toBe(urls.length + 1)
    expect(catalogReads).toBe(2)
  })
})
