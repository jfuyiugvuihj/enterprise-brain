/**
 * R48 路线甲 · 判据 ④：首屏那张卡的三态，屏上各长一张脸
 *
 * 派工词 §5 判据 ④ 要的是「拿到卡 / 没拿到卡（补齐失败）/ 本轮不该有卡」三种形状各自一枚用例，
 * 外加判据 ⑤ 那句「卡片不许叫结论」与判据 ③ 那句「不许复用 done-no-result 的文案」。
 *
 * 环境是 node + @vue/server-renderer（与 panel-states / r175 同一口径：仓库里没有 jsdom，也不
 * 许 npm i）。所以断言分两类，各管各的事，不假装验过自己验不了的：
 *   ① SSR 真产物：把组件按三态各渲一次，读屏上真出现的那句话；
 *   ② 收端真跑：把后端真发的那枚帧字面喂给 parseSseFrame + createStreamReducer，证明它落到
 *      msg.headline 而不是 msg.content（判据 ② 在屏上的那一半）；
 *   ③ 同源现读：事件名从工作树 chat.py 现抠，不抄第二份名单。
 * 全程离线：零活网络、零模型往返、零端口。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'

import AnswerHeadlineCard from '../AnswerHeadlineCard.vue'
import {
  EVENT_CLAIMS,
  activeId,
  consumeSseStream,
  createStreamReducer,
  createStreamState,
  headlineFromEnvelope,
  isClaimedEvent,
  messages,
  parseSseFrame,
} from '../../lib/sessions.js'
import { sourcesFace } from '../../lib/provenance.js'
import ChatPanel from '../ChatPanel.vue'

const source = f => readFileSync(new URL(f, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const chatSource = () => source('../../../../app/api/v1/chat.py')
async function renderPanel(turns) {
  activeId.value = 'r48-session'
  messages.value = turns
  return renderToString(h({ render: () => h(ChatPanel) }))
}
const turn = over => ({ role: 'assistant', content: '限额以内据实报销。', steps: [], mid: 't1', ...over })

const text = html => html.replace(/<!--[\s\S]*?-->/g, ' ').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()

const EVENT = 'answer.headline'

/** 一枚来源行：字段名按 chat.py::_document_source_row 上线时的那一份（下划线命名）。 */
const row = (name, extra = {}) => ({
  source: name,
  source_id: `${name}#chunk=0`,
  chunk_index: 0,
  score: 0.812,
  score_type: 'rerank',
  excerpt: `${name} 里的那一句命中正文。`,
  classification: 2,
  department: 'finance',
  permission_checked: true,
  document_version_id: 7,
  ...extra,
})

/** 卡片载荷：与 app/api/v1/chat.py::_headline_card_data 逐键同形。 */
const cardData = (rows, { shown, hit, hidden, elapsed } = {}) => ({
  carries_answer: false,
  sources: rows,
  shown_count: shown ?? rows.length,
  hit_count: hit ?? rows.length,
  unauthorized_count: hidden ?? 0,
  elapsed_ms: elapsed ?? 742,
})

const canonicalFrame = (name, data, sequence) => 'event: ' + name + '\ndata: ' + JSON.stringify({
  request_id: 'req-r48', trace_id: 'trace-r48', task_id: 'task-r48',
  sequence, timestamp: '2026-09-24T10:00:00.000Z', status: 'running', data,
}) + '\n\n'

const renderCard = props => renderToString(h({ render: () => h(AnswerHeadlineCard, props) }))

/**
 * 组件吃的 prop 由**收端那枚真归一函数**从真载荷算出来（`headlineFromEnvelope`），不是测试手搓
 * 一份形状：手搓的那份会漂——本班第一版就搓错了形（拿线上传输形直接喂组件），屏上一格文件名
 * 都没画出来，而用例照样跑得过去。这一枚改法把「载荷 -> 屏上」这条链整体纳入断言。
 */
const cardProp = (rows, extra = {}) => headlineFromEnvelope(cardData(rows, extra))

describe('判据 ④ · 三态各一张脸', () => {
  it('态一｜拿到卡且正文已到：filled，且明写「不是结论」', async () => {
    const html = await renderCard({ headline: cardProp([row('travel-policy.pdf')]), hasAnswer: true, streaming: false })
    const screen = text(html)
    expect(html).toContain('data-kind="filled"')
    expect(screen).toContain('travel-policy.pdf')
    expect(screen).toContain('不是结论')
    expect(screen).toContain('要引用请指向正文')
    // 每一格都指得回读数：密级、部门、版本都是载荷里那一份，界面不自己补一个。
    expect(screen).toContain('密级 2 级')
    expect(screen).toContain('finance')
    expect(screen).toContain('版本 7')
  })

  it('态二之一｜拿到卡但正文还在流：pending（这一态不许长得像 filled）', async () => {
    const filled = text(await renderCard({ headline: cardProp([row('a.pdf')]), hasAnswer: true, streaming: false }))
    const pending = text(await renderCard({ headline: cardProp([row('a.pdf')]), hasAnswer: false, streaming: true }))
    expect(pending).not.toBe(filled)
    expect(pending).toContain('正文还在生成')
    expect(pending).toContain('不是结论')
  })

  it('态二之二｜卡片在场而正文最终没到：unfilled「首屏卡片未获补齐」', async () => {
    const html = await renderCard({ headline: cardProp([row('a.pdf')]), hasAnswer: false, streaming: false })
    const screen = text(html)
    expect(html).toContain('data-kind="unfilled"')
    expect(screen).toContain('首屏卡片未获补齐')
    // 三张脸两两不同名：同一枚载荷，三种屏上读数。
    const pending = text(await renderCard({ headline: cardProp([row('a.pdf')]), hasAnswer: false, streaming: true }))
    const filled = text(await renderCard({ headline: cardProp([row('a.pdf')]), hasAnswer: true, streaming: false }))
    expect(new Set([screen, pending, filled]).size).toBe(3)
  })

  it('判据 ③ 的措辞红线｜三张脸屏上都不许出现 done-no-result 那两句话', async () => {
    const provenance = source('../../lib/provenance.js')
    const card = source('../AnswerHeadlineCard.vue')
    const old = /headline: '([^']*跑完了[^']*)'/.exec(provenance)
    expect(old, 'provenance.js 里 done-no-result 那句还在原处（本单没动它）').toBeTruthy()
    // 比的是**屏上真出现的那句话**，不是源文件全文：组件注释里正引用着那一句来解释「不许复用」，
    // 拿全文做 not.toContain 会红在注释上——那是自伤，不是红线。
    const screens = []
    for (const props of [
      { hasAnswer: true, streaming: false },
      { hasAnswer: false, streaming: true },
      { hasAnswer: false, streaming: false },
    ]) {
      screens.push(text(await renderCard({ headline: cardProp([row('a.pdf')]), ...props })))
    }
    expect(screens).toHaveLength(3)
    for (const screen of screens) {
      expect(screen).not.toContain(old[1])
      expect(screen).not.toContain('读数里没带回答案')
    }
    // 两句说的是不同的事：那一句是「跑完而没答案」，这一句是「给了线索而线索后面没接上回答」。
    expect(/headline: '首屏卡片未获补齐'/.test(card), '未补齐那句是自造的，不是从既有字典搬的').toBe(true)
  })

  it('态三｜本轮不该有卡：挂载点认按键表，收端没读到就不写这格', async () => {
    const panel = source('../ChatPanel.vue')
    const at = panel.indexOf('<AnswerHeadlineCard')
    const mount = panel.slice(at, panel.indexOf('/>', at))
    expect(mount, '面板里没找到卡片的挂载点：那这枚事件收了也没人画它').toBeTruthy()
    expect(mount).toContain('headlineOf(msg, i)')
    expect(mount).toContain("v-if=\"msg.role === 'assistant' && headlineOf(msg, i)\"")
    // 后端没发这枚事件时收端根本不写这一格 —— 用真 reducer 证一遍，不靠读源码。
    const msg = { role: 'assistant', content: '' }
    const reduce = createStreamReducer(msg, createStreamState())
    reduce(parseSseFrame(canonicalFrame('sources', { sources: [], hit_count: 0, unauthorized_count: 0 }, 1)))
    expect(msg.headline, '没收 answer.headline 却凭空有了卡片读数').toBeFalsy()
    const html = await renderPanel([turn({ headline: null })])
    expect(html).not.toContain('r48-headline-card')
  })

  it('态三的两张脸在屏上仍可分辨：none 与 all-hidden 不是同一句', () => {
    // 「本轮不该有卡」这一支后端一枚都不发，那两张脸归收尾的 sources 事件（判据④对齐既有纪律）。
    const none = sourcesFace({ rows: [], hitCount: 0, hiddenCount: 0, scopeReasonCode: 'department_scope' })
    const allHidden = sourcesFace({ rows: [], hitCount: 0, hiddenCount: 3, scopeReasonCode: 'department_scope' })
    expect(none.kind).toBe('none')
    expect(allHidden.kind).toBe('all-hidden')
    expect(none.headline).not.toBe(allHidden.headline)
  })
})

describe('判据 ② 的屏上那一半 · 卡片绝不写进正文', () => {
  it('卡片帧落到 msg.headline，msg.content 一个字都不动', () => {
    const msg = { role: 'assistant', content: '' }
    const reduce = createStreamReducer(msg, createStreamState())
    const result = reduce(parseSseFrame(canonicalFrame(EVENT, cardData([row('travel-policy.pdf')], { hidden: 2 }), 2)))
    expect(result.action).toBe('headline')
    expect(msg.content).toBe('')
    expect(msg.headline.rows[0].filename).toBe('travel-policy.pdf')
    expect(msg.headline.hiddenCount).toBe(2)
  })

  it('卡片在场时正文照旧逐片累计：帧的先后不改 covering 语义', () => {
    const msg = { role: 'assistant', content: '' }
    const state = createStreamState()
    const reduce = createStreamReducer(msg, state)
    reduce(parseSseFrame(canonicalFrame(EVENT, cardData([row('a.pdf')]), 2)))
    reduce(parseSseFrame('event: text\ndata: {"type":"text","content":"一线"}\n\n'))
    reduce(parseSseFrame('event: text\ndata: {"type":"text","content":"一线城市 500 元"}\n\n'))
    expect(msg.content).toBe('一线城市 500 元')
    expect(msg.headline.rows).toHaveLength(1)
    expect(state.unknownEvents).toEqual([])     // 判据 ①：真实一轮里这格必须是空的
  })

  it('卡片载荷缺格时留空而不是造一个：hit/shown 读不到就按行数收', () => {
    const msg = { role: 'assistant', content: '' }
    const reduce = createStreamReducer(msg, createStreamState())
    reduce(parseSseFrame(canonicalFrame(EVENT, { carries_answer: false, sources: [row('a.pdf')] }, 3)))
    expect(msg.headline.shownCount).toBe(1)
    expect(msg.headline.hiddenCount).toBe(0)
    expect(msg.headline.elapsedMs).toBe(0)
    expect(msg.headline.carriesAnswer).toBe(false)
  })

  it('carries_answer 缺席不等于真：界面不许替后端断言「这格是结论」', () => {
    const msg = { role: 'assistant', content: '' }
    createStreamReducer(msg, createStreamState())(parseSseFrame(canonicalFrame(EVENT, { sources: [row('a.pdf')] }, 3)))
    expect(msg.headline.carriesAnswer).toBe(false)
  })

  it('迟到的卡片不许覆盖新一轮：sequence 闸门同样管它', () => {
    const msg = { role: 'assistant', content: '' }
    const state = createStreamState()
    const reduce = createStreamReducer(msg, state)
    reduce(parseSseFrame(canonicalFrame(EVENT, cardData([row('新.pdf')]), 5)))
    const late = reduce(parseSseFrame(canonicalFrame(EVENT, cardData([row('旧.pdf')]), 4)))
    expect(late.action).toBe('ignored')
    expect(msg.headline.rows[0].filename).toBe('新.pdf')
  })
})

describe('判据 ① 的第三处 · 认领表 ↔ 工作树发射面同源', () => {
  it('EVENT_CLAIMS 把卡片认成 render，不是 note 也不是 silent', () => {
    expect(isClaimedEvent(EVENT)).toBe(true)
    expect(EVENT_CLAIMS[EVENT]).toBe('render')
  })

  it('发射点上这枚名字是 sink-call 字面量（不是手拼帧）：r150 的枚举只认这一形制', () => {
    const emitted = [...chatSource().matchAll(/canonical_sse_event\(\s*["']([a-z][a-z0-9_.]*)["']/g)].map(m => m[1])
    expect(emitted, '工作树里 canonical_sse_event 的字面名一个都没抠到').toContain(EVENT)
    // 反手钉一格形制：手拼直写帧那条正则 `event:\s*([a-z][a-z0-9_]*)\ndata:` 字符类里没有点，
    // 带点的名字走那条腿必然漏 —— 所以本枚事件不许改成手拼帧。
    const handWritten = [...chatSource().matchAll(/event:\s*([a-z][a-z0-9_]*)\\ndata:/g)].map(m => m[1])
    expect(handWritten).not.toContain(EVENT)
  })

  it('判据 ③ 的「位图里不许有字」：这张卡压根不画位图，一格文字都不许藏在图里', async () => {
    const card = source('../AnswerHeadlineCard.vue')
    const html = await renderCard({ headline: cardProp([row('a.pdf')]), hasAnswer: true, streaming: false })
    for (const tag of ['<img', '<svg', '<canvas', '<picture', 'background-image']) {
      expect(card + html, "卡片里出现了 " + tag + "：文字必须是可以被读屏与复制的 DOM 文本").not.toContain(tag)
    }
    // 屏上每一格都出自身数：把载荷里的文件名换掉，屏上那句话必须跟着换（不是任何一张预渲染图）。
    const other = await renderCard({ headline: cardProp([row('另一个文件.pdf')]), hasAnswer: true, streaming: false })
    expect(text(other)).toContain('另一个文件.pdf')
    expect(text(html)).not.toContain('另一个文件.pdf')
  })

  it('卡片组件里不许出现裸色值：新色值只准进 theme.css（lint:colors 的预算归那一个文件）', () => {
    const card = source('../AnswerHeadlineCard.vue')
    const style = card.slice(card.indexOf('<style'))
    expect(/#[0-9a-fA-F]{3,8}\b/.test(style), '组件样式里出现了 hex 色值').toBe(false)
    expect(/rgba?\(/.test(style), '组件样式里出现了裸 rgb/rgba 色值').toBe(false)
    expect(style).toContain('var(--')
  })
})

// ==================== H · 面板级接线（本班抓到的一枚假绿）====================
/**
 * G 段那几枚只渲组件本身，把挂载点写成 msg.headline 也一样绿 —— 而 ChatPanel 的 messages 是
 * store 里的 shallowRef（lib/sessions.js:19），往消息对象上塞属性面板不会重渲染，这句话是
 * lib/sessions.js:539-540 自己写下的。所以「卡片在流里当场出现」这件事必须在**面板**这一层钉：
 * 模板读的必须是按键表（headlineReads），而不是消息对象上那一份。
 * 前一版就是栽在这里：组件级 15 枚全绿，屏上根本不画。
 */
describe('H · 卡片真挂在 ChatPanel 上，且走的是能触发重渲染那条通道', () => {
  const panel = source('../ChatPanel.vue')

  it('本轮带卡片：面板产物里真出现这张卡，而且画在正文之前', async () => {
    const html = await renderPanel([turn({ headline: cardProp([row('a.pdf')]) })])
    expect(html).toContain('data-testid="r48-headline-card"')
    expect(text(html)).toContain('a.pdf')
    const flat = text(html)
    const cardAt = flat.indexOf('本轮命中的资料')
    const answerAt = flat.indexOf('限额以内据实报销')
    expect(cardAt).toBeGreaterThan(-1)
    expect(answerAt).toBeGreaterThan(-1)
    expect(cardAt).toBeLessThan(answerAt)
  })

  it('本轮不该有卡（无来源/无权限那一支）：面板里一格都不许有它，也不许留一张空壳', async () => {
    const html = await renderPanel([turn({ headline: null })])
    expect(html).not.toContain('r48-headline-card')
    expect(text(html)).toContain('限额以内据实报销')
  })

  it('🔴 触发通道：模板读按键表，不读消息对象属性（shallowRef 塞属性不重渲染）', () => {
    // ① 读数表本身是一枚能触发的 ref
    expect(panel, 'ChatPanel 里没有 headlineReads 这枚按键表').toMatch(/const headlineReads = ref\(\{\}\)/)
    // ② 收端回调走「整表换掉」那一步：shallowRef 只认 .value 被替换
    const onHeadline = panel.slice(panel.indexOf('onHeadline: (headline) => {'))
    expect(onHeadline).toContain('headlineReads.value = { ...headlineReads.value, [turn]: headline }')
    // ③ 挂载点经过 headlineOf()，而 headlineOf 读的是那张表
    const at = panel.indexOf('<AnswerHeadlineCard')
    const mount = panel.slice(at, panel.indexOf('/>', at))
    expect(mount).toContain('headlineOf(msg, i)')
    expect(mount, '挂载点直接读 msg.headline：这一轮在流里不会重渲染，正是本班抓到过的假绿')
      .not.toContain('msg.headline')
    expect(panel).toMatch(/function headlineOf\(msg, index\) \{\r?\n  return readTurn\(headlineReads, msg, index\)/)
  })

  it('卡片那张表的键是 turnKey：两轮各画各的，写死常数当场红', async () => {
    const html = await renderPanel([
      turn({ mid: 'one', headline: cardProp([row('第一轮的.pdf')]) }),
      turn({ mid: 'two', headline: cardProp([row('第二轮的.pdf')]) }),
    ])
    const seen = text(html)
    expect(seen).toContain('第一轮的.pdf')
    expect(seen).toContain('第二轮的.pdf')
    expect(panel).toMatch(/:key="`headline-\$\{turnKey\(msg, i\)\}`"/)
  })
})

// ==================== I · 读流层：面板到底有没有被通知到 ====================
/**
 * H 段钉的是「模板读那张表」，但那张表要有人写才算接线：写它的唯一入口是
 * consumeSseStream 的 onHeadline 回调（ChatPanel 在 /ask 那一腿里把它接到
 * headlineReads.value = {...} 上，整表替换才触发得动 shallowRef）。
 * 这一枚是因为真机取证时「卡片到了 store 却当场没画」才补的：少了回调，
 * 收端写 msg.headline 与面板画卡是两件事，不能拿前者给后者作证。
 */
describe('I · 读流层的 onHeadline：卡片到账即通知，且不混进正文回调', () => {
  function fakeStream(frames) {
    const enc = new TextEncoder()
    const chunks = frames.map(f => enc.encode(f))
    let at = 0
    return {
      ok: true,
      status: 200,
      body: {
        getReader() {
          return {
            async read() {
              if (at >= chunks.length) return { done: true, value: undefined }
              return { done: false, value: chunks[at++] }
            },
            async cancel() { /* 测试里没人取消也算通过 */ },
          }
        },
      },
    }
  }
  const textFrame = body => 'event: text\ndata: ' + JSON.stringify({ type: 'text', content: body }) + '\n\n'
  const doneFrame = 'event: done\ndata: {"type":"done"}\n\n'

  async function run(frames, handlers) {
    const msg = { role: 'assistant', content: '', steps: [], sources: null, mid: 'i1' }
    const order = []
    const wrap = {}
    for (const [name, fn] of Object.entries(handlers)) {
      wrap[name] = payload => { order.push(name); return fn(payload) }
    }
    const result = await consumeSseStream(fakeStream(frames), msg, wrap)
    return { msg, order, result }
  }

  it('卡片帧到位就回调一次，带的就是那张表要的读数', async () => {
    const got = []
    const { order } = await run([
      canonicalFrame(EVENT, cardData([row('travel-policy.pdf')], { hidden: 0 }), 1),
      doneFrame,
    ], { onHeadline: payload => got.push(payload) })
    expect(order).toEqual(['onHeadline'])
    expect(got).toHaveLength(1)
    expect(got[0].rows[0].filename).toBe('travel-policy.pdf')
  })

  it('卡片先到、正文后到：回调顺序与正文互不冒充（onText 不为卡片帧而响）', async () => {
    const { msg, order } = await run([
      canonicalFrame('request.started', { session_id: 's' }, 0),
      canonicalFrame(EVENT, cardData([row('a.pdf'), row('b.pdf')], { hidden: 1 }), 1),
      textFrame('一线城市'),
      textFrame('一线城市住宿费上限 500 元。'),
      canonicalFrame('sources', { sources: [], hit_count: 0, unauthorized_count: 0 }, 2),
      canonicalFrame('request.completed', { session_id: 's' }, 3),
      doneFrame,
    ], { onHeadline: () => {}, onText: () => {}, onSources: () => {} })
    expect(order).toEqual(['onHeadline', 'onText', 'onText', 'onSources'])
    expect(msg.content).toBe('一线城市住宿费上限 500 元。')
    expect(msg.headline.rows).toHaveLength(2)
    expect(msg.headline.hitCount).toBe(2)
    expect(msg.headline.hiddenCount).toBe(1)
    // 卡片载荷里那两枚文件名一个字都不许出现在正文里
    expect(msg.content).not.toContain('a.pdf')
    expect(msg.content).not.toContain('b.pdf')
  })

  it('一轮里来两枚卡片：回调两次、后一枚整表替换前一枚（屏上不留两张卡），正文照旧不动', async () => {
    const got = []
    const { msg } = await run([
      canonicalFrame(EVENT, cardData([row('第一版.pdf')]), 1),
      canonicalFrame(EVENT, cardData([row('第二版.pdf')]), 2),
      doneFrame,
    ], { onHeadline: payload => got.push(payload) })
    expect(got).toHaveLength(2)
    expect(got[1].rows[0].filename).toBe('第二版.pdf')
    expect(msg.headline.rows[0].filename).toBe('第二版.pdf')
    expect(msg.content).toBe('')
  })
})
