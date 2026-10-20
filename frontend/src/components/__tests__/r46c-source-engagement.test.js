/**
 * R46 差格 a · 出处那一行真的发得出「点开 / 展开看过」这两枚事件
 *
 * 手法沿用 components/__tests__/r195-source-feedback.test.js：node + @vue/server-renderer，
 * 无 jsdom，网络层是唯一被换掉的一层——组装与去重走 lib/feedback.js 真身，所以钉的是真字节。
 *
 * 五条红线，逐条钉在下面：
 *   甲 一行两处动作都真接得上：点开那枚原文（click）与展开这一条详情（view）；
 *   乙 🔴 发出去的载荷【只有四枚键】，问句 / 答案 / 命中句 / 部门值 / 密级值一个字节都不许在里面；
 *   丙 同一行同一动作只发一发：折叠再展开、连点五下，都刷不出第二笔账；
 *   丁 没有题号就【一发都不发】——猜一个 "unknown" 会把不同轮次的账并成一本，那是更坏的假话；
 *   戊 记账失败不挡用户看原文：preview 照样 emit，<details> 照样展开。
 *
 * 为什么这里【不新增一枚按钮】：R307 的在册钉把这张卡片上的原语按钮数与那句
 * `@click="emit('preview', row)"` 逐字钉成闭集，多一枚、改一次接线都是去改别人的判据。
 * 所以 click 包在同一枚 emit 上、view 走原生 <details>，本件钉的是这两条路真发得出字节。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }
})

import { http } from '../../lib/http'
import {
  ENGAGEMENT_BODY_KEYS,
  ENGAGEMENT_PATH,
  EVENT_CLICK,
  EVENT_VIEW,
  engagementEventKey,
  engagementRank,
  engagementRequestBody,
  engagementThreadId,
  sendEngagementEvent,
  shouldSendEngagement,
} from '../../lib/feedback'
import { sourcesFace } from '../../lib/provenance'
import SourceCard from '../SourceCard.vue'

const screen = html => html.replace(/<!--[\s\S]*?-->/g, ' ').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
const rowsOf = html => (html.match(/<li class="source-row"[\s\S]*?<\/li>/g) || [])
const detailTags = html => (html.match(/<details[\s\S]*?>/g) || [])
const bodies = () => http.post.mock.calls.map(call => call[1])

const NAME = '差旅费报销制度-2026.pdf'
const OTHER = '采购管理办法.docx'
const QUESTION = '上个季度华东区的销售额是多少，同比涨了多少'
const ANSWER = '根据销售明细.csv，上季度华东区销售额为 1280 万元，同比上涨 12%'
const HIT = '第四条 差旅费按职级实报实销，超出部分由本人承担'
const THREAD = 's-42#3'

const row = (over = {}) => ({
  filename: NAME,
  sourceId: 'doc-travel',
  chunkIndex: 4,
  score: 0.412,
  scoreType: 'rerank',
  versionId: '7',
  classification: '2',
  department: '销售部',
  excerpt: HIT,
  ...over,
})

const faceOf = rows => sourcesFace({ rows, hitCount: rows.length, hiddenCount: 0, scopeReasonCode: 'department_scope' })

const receipt = (event, over = {}) => ({
  data: { status: 'ok', filename: NAME, event, thread_id: THREAD, rank: 1, clicks: 3, views: 1, deduplicated: false, ...over },
})
const httpError = (status, detail) => ({ response: { status, data: { detail } }, message: 'Request failed with status code ' + status })

/**
 * 取绑定 + 渲染同一个实例：props 走真 setup 入参，模板读的是真 face，两枚动作的态都留在
 * bindings 里，所以点完再渲染读到的就是落定之后那一屏。
 */
async function mount(rows, threadId = THREAD) {
  const face = faceOf(rows)
  let bindings = null
  const Capture = defineComponent({
    __name: 'R46cEngagementCapture',
    setup(props, ctx) {
      bindings = SourceCard.setup(props, ctx)
      return () => null
    },
  })
  await renderToString(h({ ...Capture, props: SourceCard.props }, { face, threadId }))
  expect(bindings, '卡片应暴露可调用的 setup()').toBeTruthy()
  const html = () => renderToString(h({ ...SourceCard, __name: 'R46cProbe', setup: () => bindings }, { face, threadId }))
  return {
    bindings,
    face,
    rows,
    html,
    text: async () => screen(await html()),
    // 用户视角的两个动作：点开那枚原文（走模板里那句 emit），展开那一条详情（走 <details> 的 toggle）。
    click: index => bindings.emit('preview', rows[index]),
    expand: index => bindings.onDetailToggle(rows[index], index, { target: { open: true } }),
    collapse: index => bindings.onDetailToggle(rows[index], index, { target: { open: false } }),
  }
}

const visibleCard = (over = []) => mount([row(), row({ filename: OTHER, sourceId: 'doc-buy', chunkIndex: 1 }), ...over])

beforeEach(() => {
  vi.clearAllMocks()
  http.post.mockResolvedValue(receipt(EVENT_CLICK))
})

// ==================== 甲 · 两处动作都真接得上 ====================

describe('R46c 甲 · 出处那一行真的长出了这半张动作', () => {
  it('每一行都长出一格可展开的详情，收起时不带 open', async () => {
    const card = await visibleCard()
    const tags = detailTags(await card.html())
    expect(tags).toHaveLength(2)
    expect(tags.every(tag => !/\bopen\b/.test(tag))).toBe(true)
    expect(await card.text()).toContain('展开这处详情')
  })

  it('展开之后看得见名次与出处号：那一枚 view 说的就是"这一条被真看过"', async () => {
    http.post.mockResolvedValue(receipt(EVENT_VIEW))
    const card = await visibleCard()
    await card.expand(0)
    const html = await card.html()
    expect(detailTags(html)[0]).toMatch(/\bopen\b/)
    expect(rowsOf(html)[0]).toContain('本轮第 1 名')
    expect(rowsOf(html)[0]).toContain('出处 doc-travel')
  })
})

// ==================== 乙 🔴 载荷只有四枚键 ====================

describe('R46c 乙 · 发出去的字节里没有正文', () => {
  it('点开原文：路径与键名一字不多', async () => {
    const card = await visibleCard()
    await card.click(0)
    expect(http.post.mock.calls.map(call => call[0])).toEqual([ENGAGEMENT_PATH])
    expect(Object.keys(bodies()[0]).sort()).toEqual([...ENGAGEMENT_BODY_KEYS].sort())
    expect(bodies()[0]).toEqual({ filename: NAME, event: EVENT_CLICK, thread_id: THREAD, rank: 1 })
  })

  it('🔴 名次是 1 起：第三行发出去的是 3，不是下标 2', async () => {
    const card = await mount([row({ sourceId: 'a' }), row({ sourceId: 'b' }), row({ sourceId: 'c' })])
    await card.click(2)
    expect(bodies()[0].rank).toBe(3)
  })

  it('问句 / 答案 / 命中句 / 出处号 / 部门值 / 密级值都不在载荷里', async () => {
    const card = await visibleCard()
    await card.click(0)
    await card.expand(1)
    const wire = JSON.stringify(bodies())
    for (const banned of [QUESTION, ANSWER, HIT, '销售部', 'doc-travel', 'doc-buy']) {
      expect(wire).not.toContain(banned)
    }
    // 身份与时刻都不从这一侧出：请求体里没有那两格，后端自己取。
    expect(wire).not.toMatch(/username|occurred_at|note|content|query|question|excerpt|answer/)
  })

  it('纯函数这一层同样拒收：超长名、带换行、名次越界、不认识的动作，一律组装不出来', () => {
    expect(engagementRequestBody('x'.repeat(513), EVENT_CLICK, THREAD, 1)).toBeNull()
    expect(engagementRequestBody('a\r\nb.txt', EVENT_CLICK, THREAD, 1)).toBeNull()
    expect(engagementRequestBody(NAME, EVENT_CLICK, THREAD, 0)).toBeNull()
    expect(engagementRequestBody(NAME, EVENT_CLICK, THREAD, 101)).toBeNull()
    expect(engagementRequestBody(NAME, 'hover', THREAD, 1)).toBeNull()
    expect(engagementRequestBody(NAME, EVENT_CLICK, '这一句是问题原文', 1)).toBeNull()
  })
})

// ==================== 丙 · 一次动作只算一次事实 ====================

describe('R46c 丙 · 连点与折叠再展开都刷不出第二笔', () => {
  it('同一行连点五次原文，只发一发', async () => {
    const card = await visibleCard()
    for (let i = 0; i < 5; i += 1) await card.click(0)
    expect(http.post).toHaveBeenCalledTimes(1)
  })

  it('展开→收起→再展开，view 只有一发；而 click 与 view 各记各的', async () => {
    const card = await visibleCard()
    await card.expand(0)
    await card.collapse(0)
    await card.expand(0)
    await card.click(0)
    expect(http.post.mock.calls.map(call => call[1].event)).toEqual([EVENT_VIEW, EVENT_CLICK])
  })

  it('两份不同的资料各记一发，名次按各自的位置走', async () => {
    const card = await visibleCard()
    await card.click(0)
    await card.click(1)
    expect(bodies().map(item => [item.filename, item.rank])).toEqual([[NAME, 1], [OTHER, 2]])
  })

  it('同一份资料的两条命中在同一道题里是【同一个事实】：只发一发，与库里那枚 UNIQUE 同形', async () => {
    const card = await mount([row({ sourceId: 'a' }), row({ sourceId: 'b', chunkIndex: 9 })])
    await card.click(0)
    await card.click(1)
    expect(http.post).toHaveBeenCalledTimes(1)
    // 先到的是哪一名就记哪一名：名次记的是"用户当时点的是第几名"，不是这篇的最好名次。
    expect(bodies()[0].rank).toBe(1)
  })
})

// ==================== 丁 · 没有题号就一发都不发 ====================

describe('R46c 丁 · 说不出是哪一道题就不落账', () => {
  it('threadId 缺失：两枚动作都静默不发，界面照常能用', async () => {
    const card = await mount([row(), row({ filename: OTHER, sourceId: 'doc-buy' })], '')
    await card.click(0)
    await card.expand(1)
    expect(http.post).not.toHaveBeenCalled()
    expect(await card.text()).toContain(NAME)
  })

  it('题号不成形（带空格 / 带中日韩）也当没有：那不会是一个轮次标识', () => {
    expect(engagementThreadId('m7')).toBe('m7')
    expect(engagementThreadId('s-1#2')).toBe('s-1#2')
    expect(engagementThreadId('第 3 轮')).toBe('')
    expect(engagementThreadId('a b')).toBe('')
    expect(engagementThreadId('x'.repeat(129))).toBe('')
    expect(engagementEventKey({ filename: NAME, event: EVENT_CLICK, threadId: '' })).toBe('')
    expect(shouldSendEngagement(new Set(), { filename: NAME, event: EVENT_CLICK, threadId: '' })).toBe(false)
  })

  it('名次那一格只认真整数：数字字符串与小数都不发（后端那一格是 int，两侧同尺）', () => {
    expect(engagementRank(7)).toBe(7)
    expect(engagementRank('7')).toBeNull()
    expect(engagementRank(2.5)).toBeNull()
    expect(engagementRank(null)).toBeNull()
  })
})

// ==================== 戊 · 记账失败不挡用户 ====================

describe('R46c 戊 · 后端拒了也不许把原文藏起来', () => {
  it('403 两发都拒：preview 这一路不被 await 挡住，展开照常展开，也不自动补第三发', async () => {
    http.post.mockRejectedValue(httpError(403, 'permission_denied'))
    const card = await visibleCard()
    await card.click(0)
    await card.expand(0)
    expect(http.post).toHaveBeenCalledTimes(2)
    const html = await card.html()
    expect(detailTags(html)[0]).toMatch(/\bopen\b/)
    expect(screen(html)).not.toMatch(/没有记上|没送出去|已记录|失败/)
    await card.click(0)
    expect(http.post).toHaveBeenCalledTimes(2)
  })

  it('发送视图本身带码不带详情：不把后端回显抄进界面', async () => {
    http.post.mockRejectedValueOnce(httpError(403, QUESTION))
    const view = await sendEngagementEvent({ filename: NAME, event: EVENT_CLICK, threadId: THREAD, rank: 1 })
    expect(view.kind).toBe('failed')
    expect(JSON.stringify(view)).not.toContain(QUESTION)
  })
})