/**
 * R150 · 三张脸真的挂在 ChatPanel 上（判据①②③④ 的界面半）
 *
 * 环境 node + @vue/server-renderer（仓库没有 jsdom / @vue/test-utils，也不许 npm i），所以断言分两档：
 *   ① SSR 真产物：把带 sources / cache / queue 的轮次喂进 store，画出来的就是那几句人话。
 *      这一档是「字段上屏」的实据，不是源码里搜到字符串就算接线了。
 *   ② 源码级：改版核对、排队轮询、看原文这三条腿必须真调那几个只读端点——SSR 不跑 onMounted、
 *      node 里没有网络层可打，所以钉住调用点唯一 + 端点名，跑通归 tests/visual（总控统一跑）。
 *
 * 反证口径见文件末的 G 段与回执：把某张脸换成空列表 / 把两处拆开的句子并成一句，用例必红。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import ChatPanel from '../ChatPanel.vue'
import { activeId, messages } from '../../lib/sessions.js'

const source = f => readFileSync(new URL(`../${f}`, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const panel = source('ChatPanel.vue')

const hitRow = {
  filename: '差旅费报销制度-2026.pdf',
  sourceId: 'doc-travel',
  chunkIndex: 4,
  score: 0.412,
  scoreType: 'rerank',
  versionId: '7',
  classification: '2',
  department: '销售部',
  excerpt: '',
}

function assistantTurn(over = {}) {
  return { role: 'assistant', content: '限额以内据实报销。', steps: [], mid: 'turn-' + Math.random().toString(36).slice(2), ...over }
}

async function renderWith(turns) {
  activeId.value = 'r150-session'
  messages.value = turns
  return renderToString(h({ render: () => h(ChatPanel) }))
}

describe('G1 · 出处那张脸上屏（R41 判据③ 的销账实据）', () => {
  it('一条命中：文件名是可点的按钮，卡片上带着版本/密级/部门/相关度', async () => {
    const html = await renderWith([assistantTurn({ sources: { rows: [hitRow], hitCount: 1, hiddenCount: 0, scopeReasonCode: 'department_scope' } })])
    expect(html).toContain('data-testid="source-card"')
    expect(html).toContain('data-testid="source-open"')
    expect(html).toContain('差旅费报销制度-2026.pdf')
    expect(html).toContain('aria-label="打开原文：差旅费报销制度-2026.pdf"')
    expect(html).toContain('版本 7')
    expect(html).toContain('密级 2 级')
    expect(html).toContain('销售部')
    expect(html).toContain('重排分')
    expect(html).toContain('第 5 段')
  })

  it('判据①「生效日期」这一格：后端抄了名字就上屏，没抄就不画（界面不补今天）', async () => {
    const dated = await renderWith([assistantTurn({
      sources: { rows: [{ ...hitRow, effectiveDate: '2026-03-01T09:00:00+08:00' }], hitCount: 1, hiddenCount: 0, scopeReasonCode: '' },
    })])
    expect(dated).toContain('data-testid="source-effective"')
    expect(dated).toContain('生效 2026-03-01')
    const undated = await renderWith([assistantTurn({
      sources: { rows: [hitRow], hitCount: 1, hiddenCount: 0, scopeReasonCode: '' },
    })])
    expect(undated).not.toContain('data-testid="source-effective"')
    expect(undated).not.toContain('生效')
  })

  it('卡片与位次都来自这一轮自己的读数：两轮各画各的，写死常数当场红', async () => {
    const html = await renderWith([
      assistantTurn({ sources: { rows: [hitRow], hitCount: 1, hiddenCount: 0, scopeReasonCode: '' } }),
      assistantTurn({ sources: { rows: [], hitCount: 0, hiddenCount: 4, scopeReasonCode: 'department_scope' } }),
    ])
    expect(html).toContain('本轮回答引用了 1 处资料')
    expect(html).toContain('检索到 4 处命中，但都不在你当前的可见范围内')
    expect(html.match(/data-testid="source-card"/g)).toHaveLength(2)
  })

  it('后端这一轮没发 sources 事件：界面不画出处卡（留白不等于「没检索到」）', async () => {
    const html = await renderWith([assistantTurn({ sources: null })])
    expect(html).not.toContain('data-testid="source-card"')
    expect(html).not.toContain('没有检索到')
  })

  it('判据②：「另有 N 处命中未展示」与「没有检索到」分属两个节点，同一轮里不同时出现', async () => {
    const both = await renderWith([
      assistantTurn({ sources: { rows: [hitRow], hitCount: 1, hiddenCount: 2, scopeReasonCode: '' } }),
    ])
    // 未展示那句是独立一个 <p>：两个 testid 各一枚，且这句没被拼进条数那句里
    expect(both.match(/data-testid="source-headline"/g)).toHaveLength(1)
    expect(both.match(/data-testid="source-hidden-line"/g)).toHaveLength(1)
    expect(both).toContain('>另有 2 处命中未展示<')
    expect(both.match(/本轮回答引用了 1 处资料/g)).toHaveLength(1)
    expect(both).not.toContain('没有检索到')

    const none = await renderWith([
      assistantTurn({ sources: { rows: [], hitCount: 0, hiddenCount: 0, scopeReasonCode: '' } }),
    ])
    expect(none).toContain('本轮没有检索到可用文档')
    expect(none).not.toContain('未展示')
  })

  it('命中句这一格后端还没抄进 sources 行：读取位留着，出现就上屏（需求清单转总控）', async () => {
    const html = await renderWith([
      assistantTurn({ sources: { rows: [{ ...hitRow, excerpt: '单笔限额 5000 元以内据实报销。' }], hitCount: 1, hiddenCount: 0, scopeReasonCode: '' } }),
    ])
    expect(html).toContain('data-testid="source-excerpt"')
    expect(html).toContain('单笔限额 5000 元以内据实报销。')
  })
})

describe('G2 · 缓存那张脸上屏（三态不许并成一句）', () => {
  it('实时算：正文一出来就有这一格，句子里写着它的证据', async () => {
    // 这就是今天实时腿在流上留下的那格读数（lib/sessions.js::cacheFromFrame 的形状）
    const html = await renderWith([assistantTurn({ cache: { cached: false, generatedAt: '', note: '', observed: true } })])
    expect(html).toContain('data-testid="cache-face"')
    expect(html).toContain('本轮实时生成')
    expect(html).toContain('没有带回缓存读数')
  })

  it('本单之前入库的老消息没有这格读数：界面不替它宣布「实时算」', async () => {
    const html = await renderWith([assistantTurn({ content: '上一轮的答案，来源已不可考。' })])
    expect(html).not.toContain('data-testid="cache-face"')
    expect(html).not.toContain('本轮实时生成')
  })

  it('命中缓存：屏上的钟点来自后端那枚 cache_generated_at，界面自己不造时间', async () => {
    const html = await renderWith([assistantTurn({ cache: { cached: true, generatedAt: '2026-09-21T09:00:00Z', note: '缓存结果 · 昨天下午' } })])
    expect(html).toContain('data-kind="cached"')
    expect(html).toContain('缓存结果 · 昨天下午')
    expect(html).toContain('正在核对来源文件是否已经改版')
  })

  it('命中缓存但这一轮没再交来源清单 → 第四枚读数，不许画成「没改版」', async () => {
    const html = await renderWith([assistantTurn({ cache: { cached: true, generatedAt: '2026-09-21T09:00:00Z', note: '缓存结果' } })])
    // SSR 不跑异步核对，这一轮还没查：界面此刻只能说「正在核对」，绝不提前宣布没改版
    expect(html).not.toContain('没有新版本')
  })
})

describe('G3 · 排队那张脸上屏（位次只来自状态读数）', () => {
  it('只收到 queued 回执：说「已排上队、位次未读到」，不补 0 也不报人数', async () => {
    const html = await renderWith([assistantTurn({ queue: { requestId: 'req-9', status: 'queued' } })])
    expect(html).toContain('data-testid="queue-face"')
    expect(html).toContain('data-kind="queued"')
    expect(html).toContain("data-ahead=\"unknown\"")
    expect(html).toContain('暂时读不到你前面有几个人')
  })

  it('后端压根没排队这一轮：这一格不存在，不是画一句「未排队」', async () => {
    const html = await renderWith([assistantTurn({})])
    expect(html).not.toContain('data-testid="queue-face"')
  })
})

describe('G4 · 未认领事件：unknownEvents 从此有读取方', () => {
  it('面板把未认领事件画成系统自陈，元素与 testid 唯一', () => {
    expect(panel.match(/data-testid="face-unseen"/g)).toHaveLength(1)
    expect(panel).toContain('unseenOf(msg, i).length')
    // 自陈句里带「技术信息」：这既是给人看的说明，也是 V6 裸码闸门认得的诊断区标记
    expect(panel).toContain('技术信息')
  })

  it('自陈会随会话落盘：刷新回来那一句还在（它不是控制台日志）', async () => {
    const html = await renderWith([assistantTurn({ unseenEvents: ['answer.revised'] })])
    expect(html).toContain('data-testid="face-unseen"')
    expect(html).toContain('answer.revised')
    // 同一名只出现一次：读盘那份与本轮新到那份并集去重，不重复刷屏
    const dedup = await renderWith([
      assistantTurn({ unseenEvents: ['answer.revised'] }),
    ])
    expect(dedup.match(/answer\.revised/g)).toHaveLength(1)
  })

  it('全仓不再存在「记进 unknownEvents 却没人读」的那条路', () => {
    const sessions = source('../lib/sessions.js')
    // 三处记名：canonical 的 default、LEGACY_EVENTS 名单外、名单内但本文件漏了 case。
    // 三条都是「后端发了 / 前端没接」的现场，全都必须流向同一个有读取方的出口。
    expect(sessions.match(/state\.unknownEvents\.push/g)).toHaveLength(3)
    expect(sessions).toContain('handlers.onUnknownEvent?.')
    expect(sessions).toContain('console.warn(`[SSE] 界面未认领的事件')
  })
})

describe('G5 · 三条腿的取数端点（源码级：SSR 不跑 onMounted，node 里没网络可打）', () => {
  it('看原文走 /documents/{f}/preview，弹窗组件只 import 不改一行', () => {
    expect(panel).toContain('/documents/${encodeURIComponent(filename)}/preview')
    expect(panel).toContain("import DocumentPreviewModal from './DocumentPreviewModal.vue'")
    // R150 的写域不含这枚组件：本单对它零改动（改动了这条就会红，配合回执里的 git diff 自证）
    expect(panel).not.toMatch(/preview\.vue[\s\S]{0,40}defineProps/)
  })

  it('改版核对真调 /documents/{f}/versions，且只在命中缓存那一轮调', () => {
    expect(panel).toContain('/documents/${encodeURIComponent(filename)}/versions')
    expect(panel).toMatch(/if \(!cache \|\| cache\.cached !== true\) return/)
  })

  it('排队走 /queue/status/{id} 与 /queue/stats，节奏 3 秒一枚，卸载必停表', () => {
    expect(panel).toContain('/queue/status/${encodeURIComponent(requestId)}')
    expect(panel).toContain("http.get('/queue/stats')")
    expect(panel).toMatch(/const QUEUE_POLL_MS = 3000/)
    expect(panel).toMatch(/setInterval\(tick, QUEUE_POLL_MS\)/)
    expect(panel).toMatch(/onUnmounted\(\(\) => \{\s*stopQueueWatches\(\)/)
  })

  it('排队答完把 result 补回这条回答，且已有正文时不覆盖', () => {
    expect(panel).toMatch(/if \(read\.status === 'done' && read\.result\) applyQueuedAnswer\(key, read\.result\)/)
    expect(panel).toMatch(/function applyQueuedAnswer\(key, answer\) \{[\s\S]*?if \(msg\.content\) return/)
  })

  it('色值纪律：新加的这块样式零裸色，可读性不靠 text-shadow', () => {
    const block = panel.slice(panel.indexOf('/* R150 · 三张脸的容器'))
    expect(block).not.toMatch(/#[0-9a-fA-F]{3,6}\b/)
    expect(block).not.toMatch(/rgba?\(/)
    expect(panel).not.toMatch(/text-shadow:\s*var\(--/)
    expect(panel).not.toMatch(/text-shadow:[^n]/)
  })
})
