/**
 * R195 判据① · 出处卡片那两枚动作真的按得动，且说得出「记上没记上」
 *
 * 手法沿用 r191-modal-row-scope.test.js：node + @vue/server-renderer，无 jsdom。
 * 三条腿：
 *   ① 模型是真的：卡片吃的 face 出自 lib/provenance.js::sourcesFace（后端那几格的读法），
 *      不在测试里手捏一份「看起来像出处」的行；
 *   ② 产物是真的：两枚按钮在不在、disabled 在不在、aria-pressed 亮没亮、说明句写的是什么，
 *      一律从 SSR 真 HTML 读，不读组件内部变量；
 *   ③ 网络层是唯一被换掉的一层：措辞与状态机走 lib/feedback.js 真身，
 *      所以「发出去的 body 只含两枚键」钉的是真组装结果。
 *
 * 五条红线，逐条钉在下面：
 *   甲 一行两枚（有用 / 没用），互斥；
 *   乙 「另有 N 处命中未展示」与「本轮没有检索到可用文档」那两句空话节点一枚按钮都不摆；
 *   丙 回执没回来之前一枚都不许亮，回来后只亮点过的那一枚；
 *   丁 🔴 记上之后再点第二下一枚请求都不发（后端只有两枚枚举值，没有撤回出口，
 *      反向信号不是撤回而是假账）；
 *   戊 401 / 422 / 断网三张脸两两不同，且没有一张说「已记录」；发出去的每一枚字节里
 *      不许有问句、答案与命中句。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'

// 只换网络层：feedback.js 的组装、状态机、失败脸与 http.js 的 errorDetail 全走真身。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }
})

import { http } from '../../lib/http'
import { MAX_FILENAME_CHARS, SIGNAL_ACCEPTED, SIGNAL_REJECTED } from '../../lib/feedback'
import { sourcesFace } from '../../lib/provenance'
import SourceCard from '../SourceCard.vue'

/** 屏上真正被人读到的那几个字：SSR 会把模板注释一起吐出来。 */
const screen = html => html.replace(/<!--[\s\S]*?-->/g, ' ').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
const tags = html => (html.match(/<button[\s\S]*?<\/button>/g) || []).map(tag => ({
  testid: (/data-testid="([^"]+)"/.exec(tag) || [, ''])[1],
  text: tag.replace(/<[^>]*>/g, '').trim(),
  disabled: /\bdisabled\b/.test(tag.split('>')[0]),
  pressed: /aria-pressed="true"/.test(tag.split('>')[0]),
}))
const buttonsOf = html => tags(html).filter(item => item.testid.startsWith('source-feedback-'))
/** 一枚出处行一块：按住的是哪一笔要按行数着看，别的行不许跟着变灰。 */
const rowsOf = html => (html.match(/<li class="source-row"[\s\S]*?<\/li>/g) || []).map(block => buttonsOf(block))

const NAME = '差旅费报销制度-2026.pdf'
const OTHER = '采购管理办法.docx'
const QUESTION = '上个季度华东区的销售额是多少，同比涨了多少'
const ANSWER = '根据销售明细.csv，上季度华东区销售额为 1280 万元，同比上涨 12%'
const HIT = '第四条 差旅费按职级实报实销，超出部分由本人承担'

const row = (over = {}) => ({
  filename: NAME,
  sourceId: 'doc-travel',
  chunkIndex: 4,
  score: 0.412,
  scoreType: 'rerank',
  versionId: '7',
  classification: '2',
  department: '销售部',
  excerpt: '',
  ...over,
})

/** 真模型：两行出处、另有两处没展示。 */
const faceOf = (rows, hidden = 0) => sourcesFace({ rows, hitCount: rows.length + hidden, hiddenCount: hidden, scopeReasonCode: 'department_scope' })
const visibleFace = (rows = [row(), row({ filename: OTHER, sourceId: 'doc-buy', chunkIndex: 1 })], hidden = 0) => faceOf(rows, hidden)
const noneFace = () => faceOf([])
const allHiddenFace = () => faceOf([], 3)

const receipt = (signal, over = {}) => ({
  data: { status: 'ok', filename: NAME, signal, accepted_count: 4, rejected_count: 1, ...over },
})
const httpError = (status, detail) => ({ response: { status, data: { detail } }, message: 'Request failed with status code ' + status })
const networkDown = () => ({ code: 'ERR_NETWORK', request: {}, message: 'Network Error' })

/**
 * 取绑定 + 渲染同一个实例：props 走真 setup 入参，模板读的是真 face，
 * 态留在 bindings.marks 里，所以点完一下再渲染读到的就是落定之后的那一屏。
 */
async function mount(face) {
  let bindings = null
  const Capture = defineComponent({
    __name: 'R195SourceFeedbackCapture',
    setup(props, ctx) {
      bindings = SourceCard.setup(props, ctx)
      return () => null
    },
  })
  await renderToString(h({ ...Capture, props: SourceCard.props }, { face }))
  expect(bindings, '卡片应暴露可调用的 setup()').toBeTruthy()
  const html = () => renderToString(h({ ...SourceCard, __name: 'R195Probe', setup: () => bindings }, { face }))
  // 一张卡片三个动作：读产物、读屏上的字、按下去。marks 住在同一个 bindings 里，所以点完再读看到的是落定之后那一屏。
  return {
    bindings,
    face,
    html,
    text: async () => screen(await html()),
    markSignal: (target, signal) => bindings.markSignal(target, signal),
  }
}
const render = card => card.html()
const postBodies = () => http.post.mock.calls.map(call => call[1])
const firstRow = bindings => ({ filename: NAME })

beforeEach(() => {
  vi.clearAllMocks()
})

// ==================== 甲 乙 · 每一行两枚，空话节点一枚都没有 ====================

describe('R195 甲 · 真给出处的行上两枚动作都在', () => {
  it('一行两枚：字是「有用 / 没用」，idle 时都可点、都没亮', async () => {
    const bindings = await mount(visibleFace())
    const html = await render(bindings)
    const marks = buttonsOf(html)
    expect(marks.map(item => item.testid)).toEqual([
      'source-feedback-accept', 'source-feedback-reject',
      'source-feedback-accept', 'source-feedback-reject',
    ])
    expect([...new Set(marks.map(item => item.text))].sort()).toEqual(['有用', '没用'])
    expect(marks.filter(item => item.disabled)).toEqual([])
    expect(marks.filter(item => item.pressed)).toEqual([])
    expect(html).toContain('role="group"')
    expect(html).toContain('aria-label="这处出处对你有帮助吗"')
  })

  it('每枚按钮的 aria 全称带上资料名：屏上只读到「有用」也知道在说哪一份', async () => {
    const html = await render(await mount(visibleFace()))
    expect(html).toContain('aria-label="把这处出处『' + NAME + '』标记为有用"')
    expect(html).toContain('aria-label="把这处出处『' + OTHER + '』标记为没用"')
  })

  it('idle 一行都不许留评价读数：没点过就没有任何一句', async () => {
    const text = screen(await render(await mount(visibleFace())))
    expect(text).not.toContain('已记下')
    expect(text).not.toContain('正在送出')
    expect(text).not.toContain('没送出去')
  })
})

describe('R195 乙 · 那两句空话节点摆不出按钮', () => {
  it('「本轮没有检索到可用文档」这一格零枚按钮，句子逐字不动', async () => {
    const html = await render(await mount(noneFace()))
    expect(buttonsOf(html)).toEqual([])
    const text = screen(html)
    expect(text).toContain('本轮没有检索到可用文档')
    expect(text).not.toContain('有用')
    expect(text).not.toContain('没用')
  })

  it('「另有 N 处命中未展示」那句话自己不带按钮：枚数只等于真给出去的行数', async () => {
    const html = await render(await mount(visibleFace([row()], 2)))
    const text = screen(html)
    expect(text).toContain('另有 2 处命中未展示')
    expect(buttonsOf(html)).toHaveLength(2)
  })

  it('「检索到 N 处命中，但都不在你当前的可见范围内」这一格也零枚', async () => {
    const html = await render(await mount(allHiddenFace()))
    expect(buttonsOf(html)).toEqual([])
    expect(screen(html)).toContain('检索到 3 处命中，但都不在你当前的可见范围内')
  })

  it('R150 那几枚既有产物一字不动：文件名仍可点，段次与命中句照旧', async () => {
    const html = await render(await mount(visibleFace([row({ excerpt: HIT })])))
    const text = screen(html)
    expect(html).toContain('data-testid="source-open"')
    expect(text).toContain('本轮回答引用了 1 处资料')
    expect(text).toContain('第 5 段')
    expect(text).toContain(HIT)
    expect(text).toContain(NAME)
  })
})

// ==================== 丙 · 点亮只等真回执 ====================

describe('R195 丙 · 没回音之前一枚都不亮', () => {
  it('发出去的路上：两枚都按住、都不亮，说明句只说「正在送出」', async () => {
    let settle
    http.post.mockImplementation(() => new Promise(resolve => { settle = resolve }))
    const bindings = await mount(visibleFace())
    const inflight = bindings.markSignal(row(), SIGNAL_ACCEPTED)
    const html = await render(bindings)
    expect(html).toContain('data-phase="sending"')
    const rows = rowsOf(html)
    expect(rows).toHaveLength(2)
    // 按住的是点过的那一行：两枚一起按，一枚都不亮
    expect(rows[0].map(item => item.testid)).toEqual(['source-feedback-accept', 'source-feedback-reject'])
    expect(rows[0].filter(item => !item.disabled)).toEqual([])
    expect(rows[0].filter(item => item.pressed)).toEqual([])
    // 另一行是另一笔账，不跟着变灰，也不跟着点亮
    expect(rows[1].filter(item => item.disabled)).toEqual([])
    expect(rows[1].filter(item => item.pressed)).toEqual([])
    const text = screen(html)
    expect(text).toContain('正在送出这处出处的评价')
    expect(text).not.toMatch(/已记录|已记下|成功|完成/)
    settle(receipt('accepted'))
    await inflight
  })

  it('回执到了才点亮，而且只亮点过的那一枚', async () => {
    http.post.mockResolvedValue(receipt('accepted'))
    const bindings = await mount(visibleFace())
    await bindings.markSignal(row(), SIGNAL_ACCEPTED)
    const html = await render(bindings)
    const marks = buttonsOf(html)
    expect(marks.filter(item => item.pressed).map(item => item.testid)).toEqual(['source-feedback-accept'])
    expect(html).toContain('data-phase="recorded"')
    const text = screen(html)
    expect(text).toContain('这处出处已记下「有用」。')
    expect(text).toContain('一处出处只记一次')
  })

  it('发出去的就是后端那一套：路径、两枚键、两枚值，一格不多', async () => {
    http.post.mockResolvedValue(receipt('rejected'))
    const bindings = await mount(visibleFace())
    await bindings.markSignal(row({ excerpt: HIT }), SIGNAL_REJECTED)
    expect(http.post.mock.calls).toHaveLength(1)
    const [path, body] = http.post.mock.calls[0]
    expect(path).toBe('/feedback/document')
    expect(Object.keys(body)).toEqual(['filename', 'signal'])
    expect(body).toEqual({ filename: NAME, signal: 'rejected' })
    expect(JSON.stringify(body).includes(HIT)).toBe(false)
    expect(screen(await render(bindings))).toContain('这处出处已记下「没用」。')
  })

  it('status 对不上号的 200 不算记下：不点亮，也不留第二次点击的门', async () => {
    http.post.mockResolvedValue({ data: { status: 'queued' } })
    const bindings = await mount(visibleFace())
    await bindings.markSignal(row(), SIGNAL_ACCEPTED)
    const html = await render(bindings)
    expect(html).toContain('data-phase="uncertain"')
    expect(buttonsOf(html).filter(item => item.pressed)).toEqual([])
    const text = screen(html)
    expect(text).toContain('没读到确认回执')
    expect(text).not.toMatch(/已记录|已记下/)
    await bindings.markSignal(row(), SIGNAL_REJECTED)
    expect(http.post.mock.calls).toHaveLength(1)
  })
})

// ==================== 丁 · 没有撤回那一支 ====================

describe('R195 丁 · 记上之后再点第二下，一枚请求都不发', () => {
  it('同一枚点第二下不发、反向那枚点第二下也不发，屏上仍是原来那一枚亮着', async () => {
    http.post.mockResolvedValue(receipt('accepted'))
    const bindings = await mount(visibleFace())
    await bindings.markSignal(row(), SIGNAL_ACCEPTED)
    expect(http.post).toHaveBeenCalledTimes(1)

    expect(await bindings.markSignal(row(), SIGNAL_ACCEPTED)).toBeNull()
    expect(await bindings.markSignal(row(), SIGNAL_REJECTED)).toBeNull()
    expect(http.post).toHaveBeenCalledTimes(1)

    const marks = buttonsOf(await render(bindings))
    expect(marks.filter(item => item.pressed).map(item => item.testid)).toEqual(['source-feedback-accept'])
    const text = screen(await render(bindings))
    expect(text).toContain('改不了')
    expect(text).toContain('撤回')
    expect(text).not.toMatch(/已取消|未评价|已撤回/)
  })

  it('同一份文件命中两段时两行共用一笔账：第二行点不出第二笔', async () => {
    http.post.mockResolvedValue(receipt('accepted'))
    const rows = [row({ chunkIndex: 2 }), row({ chunkIndex: 7 })]
    const bindings = await mount(visibleFace(rows))
    await bindings.markSignal(rows[0], SIGNAL_ACCEPTED)
    expect(http.post).toHaveBeenCalledTimes(1)
    await bindings.markSignal(rows[1], SIGNAL_REJECTED)
    expect(http.post).toHaveBeenCalledTimes(1)
    const html = await render(bindings)
    expect(screen(html).match(/这处出处已记下「有用」。/g)).toHaveLength(2)
  })

  it('失败那一次可以补点：那不算第二枚信号，是同一枚补上', async () => {
    http.post.mockRejectedValueOnce(httpError(401, 'authentication_required'))
    http.post.mockResolvedValueOnce(receipt('accepted'))
    const bindings = await mount(visibleFace())
    await bindings.markSignal(row(), SIGNAL_ACCEPTED)
    expect(screen(await render(bindings))).not.toMatch(/已记录|已记下/)
    await bindings.markSignal(row(), SIGNAL_ACCEPTED)
    expect(http.post).toHaveBeenCalledTimes(2)
    expect(buttonsOf(await render(bindings)).filter(item => item.pressed)).toHaveLength(1)
  })
})

// ==================== 戊 · 失败那张脸必须诚实 ====================

describe('R195 戊 · 401 / 422 / 断网三张脸各长得不一样', () => {
  const cases = [
    ['登录', httpError(401, 'authentication_required'), /登录状态已经过期/],
    ['提交被挡', httpError(422, 'validation_error'), /这次提交被服务端挡下/],
    ['断网', networkDown(), /连不上服务端/],
  ]

  it('三张脸三句话：标题两两不同，且没有一张说记上了', async () => {
    const heads = []
    for (const [label, error, pattern] of cases) {
      vi.clearAllMocks()
      http.post.mockRejectedValue(error)
      const bindings = await mount(visibleFace([row({ filename: OTHER })]))
      await bindings.markSignal(row({ filename: OTHER }), SIGNAL_ACCEPTED)
      const html = await render(bindings)
      expect(html, label).toContain('data-phase="failed"')
      expect(buttonsOf(html).filter(item => item.pressed), label).toEqual([])
      const text = screen(html)
      expect(text, label).toMatch(pattern)
      expect(text, label).not.toMatch(/已记录|已记下|已采纳/)
      heads.push(pattern.source)
      expect(http.post, label).toHaveBeenCalledTimes(1)
    }
    expect(new Set(heads).size).toBe(3)
  })

  it('401 与 422 说的是两件不同的事：一个要重登，一个是提交形状不对', async () => {
    const say = async error => {
      vi.clearAllMocks()
      http.post.mockRejectedValue(error)
      const bindings = await mount(visibleFace())
      await bindings.markSignal(row(), SIGNAL_ACCEPTED)
      return screen(await render(bindings))
    }
    const unauthorized = await say(httpError(401, 'authentication_required'))
    const refused = await say(httpError(422, 'validation_error'))
    expect(unauthorized).toContain('重新登录')
    expect(refused).toContain('出口只认资料名与「有用 / 没用」两格')
    expect(unauthorized).not.toContain('出口只认资料名')
    expect(refused).not.toContain('重新登录')
  })

  it('屏上的每一句人话里都不许夹带裸码名', async () => {
    http.post.mockRejectedValue(httpError(503, 'storage_unavailable'))
    const bindings = await mount(visibleFace())
    await bindings.markSignal(row(), SIGNAL_ACCEPTED)
    const text = screen(await render(bindings))
    expect(text).toMatch(/计数表没写成/)
    expect(text).not.toMatch(/[a-z][a-z0-9]*(_[a-z0-9]+)+/)
  })

  it('🔴 无论哪一张脸，问句、答案与命中句都没跟着出去', async () => {
    http.post.mockRejectedValue(httpError(403, 'permission_denied'))
    const bindings = await mount(visibleFace([row({ excerpt: HIT })]))
    await bindings.markSignal(row({ excerpt: HIT }), SIGNAL_REJECTED)
    const wire = JSON.stringify(postBodies())
    expect(wire).toContain(NAME)
    expect(wire).toContain('rejected')
    for (const secret of [QUESTION, ANSWER, HIT]) {
      expect(wire.includes(secret), wire).toBe(false)
    }
  })
})

// ==================== 没有名字的行：把话说清，不摆哑按钮 ====================

describe('R195 补 · 名字都不有的行说得出为什么按不了', () => {
  it('缺文件名：零枚按钮、一句解释、一条请求都不发', async () => {
    const bindings = await mount(visibleFace([row({ filename: '   ' })]))
    const html = await render(bindings)
    await expect(bindings.markSignal(row({ filename: '   ' }), SIGNAL_ACCEPTED)).resolves.toBeNull()
    expect(buttonsOf(html)).toEqual([])
    expect(html).toContain('data-testid="source-feedback-blocked"')
    expect(screen(html)).toContain('这一行没有可记录的出处名称')
    expect(http.post).not.toHaveBeenCalled()
  })

  it('名字超长（塞得进一行也塞不进那一格）：不摆按钮，为什么送不出去先写在屏上', async () => {
    const long = '名'.repeat(MAX_FILENAME_CHARS + 1)
    http.post.mockResolvedValue(receipt('accepted'))
    const card = await mount(visibleFace([row({ filename: long })]))
    await card.markSignal(row({ filename: long }), SIGNAL_ACCEPTED)
    const html = await render(card)
    expect(buttonsOf(html)).toEqual([])
    expect(screen(html)).toContain('这份资料的名称太长，评价送不出去')
    expect(screen(html)).not.toMatch(/已记录|已记下/)
    expect(http.post).not.toHaveBeenCalled()
  })
})