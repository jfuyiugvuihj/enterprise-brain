/**
 * R424 · 「服务端这一轮实际用了哪份数据文件」从线上交到 state 的那一手
 *
 * 病（本单唯一的断点，改前取证取在 18ca560）：后端 R414 已经在 request.completed 的终态帧里交来
 * data_filename（app/api/v1/chat.py:2795 与 :3439 两枚出口，三态语义出自 :361 terminal_data_filename
 * ——正好一枚交文件名，零枚与多枚都交空串），面板也早写好了三张脸（ChatPanel.vue 的 serverDataOf），
 * 可中间那一截断在这里：request.completed 那一支只抄 awaiting_hitl 与 awaiting_steps，data 的其余键
 * 全丢 ⇒ 线上明明带了那一格，屏上那一行一枚字都不画。R415 交单时把这枚断点钉成「会自己报红的标记」，
 * 本件是它红过之后补上的正面钉（丙组那四枚端到端在 r415 里，与本件同一件事的两端）。
 *
 * 🔴 判据①只有一句话：【只在亲眼读到字符串时】才写 terminalDataFilename 这一枚键。
 *   · 把缺席写成空串 = 替后端宣布「这一轮说不准是哪张表」，而后端今天一个字都没说；
 *   · 把缺席写成请求值 = 拿界面刚才点的那一张冒充服务端读数，是更假的假话。
 * 所以「空串」与「整格缺席」在这里必须是两件事，本件逐枚钉开：空串要让键在场（屏上才有「说不准」
 * 那一句），缺席与任何非字符串都要让键根本不存在（屏上那一行一枚字都不画）。
 *
 * 反证怎么算红（每一把都现跑过，读数见 R424 回执）：
 *   摘掉 sessions.js 里那一行 if → 甲1 甲2 丙1 当场红（读不到就永远不报名字）；
 *   把它压成一态（无条件赋值或 textOf 归一）→ 甲3 甲4 红（缺席被写成「说不准」）；
 *   键名写成别的（面板读的是 state.terminalDataFilename）→ 丙1 丙2 红；
 *   往本文件上面插行挪行号 → 丁组三枚在册手抄坐标当场红。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { consumeSseStream, createStreamReducer, createStreamState, parseSseFrame } from '../sessions.js'

/** 面板 serverDataOf / adoptServerDataRead 读的那一枚键名：逐字对齐，两边不许各写一套。 */
const WIRE_KEY = 'terminalDataFilename'

const source = name => readFileSync(new URL(name, import.meta.url), 'utf8').replace(/\r?\n/g, '\n')
const lineOf = (text, n) => text.split('\n')[n - 1] || ''

/** 喂一枚真帧给真 reducer：走的是 parseSseFrame + canonical 闸门，不在这里做半点简化。 */
function reduceEvent(event, data) {
  const msg = { role: 'assistant', content: '', steps: [] }
  const state = createStreamState()
  const frame = `event: ${event}\ndata: ${JSON.stringify({ request_id: 'req-1', sequence: 1, data })}\n\n`
  return { msg, state, result: createStreamReducer(msg, state)(parseSseFrame(frame)) }
}

/** 终态帧：data 里有没有 data_filename、是什么形状，全由调用方给（undefined 经 JSON 一序列化就是整格缺席）。 */
const completedWith = data => reduceEvent('request.completed', data)

describe('甲 · 那一枚键只在【读到字符串】时在场（空串与缺席是两件事）', () => {
  it('报名字：data_filename 是一枚文件名 → 键抄成 terminalDataFilename，值就是那一个名字', () => {
    const { state, result } = completedWith({ session_id: 's-1', data_filename: 'sales.xlsx' })
    expect(result.action).toBe('terminal')
    expect(state.terminal).toBe('completed')
    expect(state[WIRE_KEY]).toBe('sales.xlsx')
  })

  it('空串是一枚读数而不是缺席：键必须在场，值就是空串（屏上那一句要说「说不准」）', () => {
    const { state } = completedWith({ session_id: 's-1', data_filename: '' })
    expect(WIRE_KEY in state, '空串被丢了就是丢掉后端唯一一次表态').toBe(true)
    expect(state[WIRE_KEY]).toBe('')
  })

  it('整格缺席：键必须根本不存在 —— 写成空串是替后端宣布「说不准」，写成请求值更是假话', () => {
    const { state, msg } = completedWith({ session_id: 's-1', awaiting_hitl: false })
    expect(WIRE_KEY in state, '后端没说话，state 里就不许多出这一枚键').toBe(false)
    expect(state[WIRE_KEY]).toBeUndefined()
    expect(msg[WIRE_KEY], '消息对象那一份也不许由 lib 凭空造出来').toBeUndefined()
  })

  it('非字符串一律不写键：null / 7 / {} / [] / true 五枚形状各自验一遍', () => {
    for (const shape of [null, 7, {}, [], true]) {
      const { state } = completedWith({ session_id: 's-1', data_filename: shape })
      expect(WIRE_KEY in state, `形状 ${JSON.stringify(shape)} 混进了读数那一格`).toBe(false)
    }
  })
})

describe('乙 · 只有终态帧那一个出口做这一手，同帧另两格照旧', () => {
  it('request.failed / request.cancelled 里冒出 data_filename 也不许当成用表读数', () => {
    for (const event of ['request.failed', 'request.cancelled']) {
      const { state } = reduceEvent(event, { session_id: 's-1', data_filename: 'sales.xlsx' })
      expect(WIRE_KEY in state, `${event} 不是终态读数那一格`).toBe(false)
    }
  })

  it('request.started 仍是 ignored，也不许提前交出这一格', () => {
    const { state, result } = reduceEvent('request.started', { session_id: 's-1', data_filename: 'sales.xlsx' })
    expect(result.action).toBe('ignored')
    expect(WIRE_KEY in state).toBe(false)
  })

  it('抄这一格不许动同帧那两格：awaiting_hitl 与 awaiting_steps 的形状一字未改', () => {
    const { state } = completedWith({
      session_id: 's-1', data_filename: 'sales.xlsx', awaiting_hitl: true, awaiting_steps: ['export'],
    })
    expect(state.awaitingHitl).toBe(true)
    expect(state.pendingSteps).toEqual(['export'])
    expect(state[WIRE_KEY]).toBe('sales.xlsx')
  })

  it('legacy done 帧（非 canonical）不补造读数：载荷里没那一格 ⇒ 键根本不存在，屏上仍是「不画」', async () => {
    const msg = { role: 'assistant', content: '', steps: [] }
    const state = createStreamState()
    const reduce = createStreamReducer(msg, state)
    reduce(parseSseFrame('event: done\ndata: {"content":""}\n\n'))
    expect(state.terminal).toBe('completed')
    expect(WIRE_KEY in state).toBe(false)
  })
})

describe('丙 · 真流跑到底：交回面板的是同一枚键名，面板那一份才谈得上落盘', () => {
  function sseResponse(frames) {
    const bytes = frames.map(frame => new TextEncoder().encode(frame))
    let index = 0
    return {
      ok: true,
      status: 200,
      headers: { get: () => null },
      body: { getReader() { return { async read() { return index < bytes.length ? { done: false, value: bytes[index++] } : { done: true } } } } },
    }
  }

  it('真 consumeSseStream 吃到带文件名的终态帧 → result.state 里就是那一个名字', async () => {
    const frame = `event: request.completed\ndata: ${JSON.stringify({ request_id: 'req-1', sequence: 1, data: { session_id: 's-1', data_filename: 'sales.xlsx' } })}\n\n`
    const result = await consumeSseStream(sseResponse([frame]), { role: 'assistant', content: '', steps: [] }, {})
    expect(result.stopped).toBe('done')
    expect(result.state[WIRE_KEY]).toBe('sales.xlsx')
  })

  it('接缝的键名两边逐字一致：lib 写的那一枚就是面板读的那一枚', () => {
    const lib = source('../sessions.js')
    const panel = source('../../components/ChatPanel.vue')
    expect(lib, 'lib 写的键名漂了：面板读不到，那一行永远不画').toContain(`state.${WIRE_KEY} = data.data_filename`)
    expect(panel, '面板读的键名漂了：同一件事在两处各写一套').toContain(`result?.state?.${WIRE_KEY}`)
  })
})

describe('丁 · 手抄坐标必须是活坐标（本单往这一格里改码，一行都没多一行都没少）', () => {
  const lib = source('../sessions.js')
  const chat = source('../../../../app/api/v1/chat.py')

  it('chat.py 的注释引 sessions.js:524-531 讲三条分支：那七行今天确实写着三条分支', () => {
    expect(chat).toContain('frontend/src/lib/sessions.js:524-531')
    expect(lineOf(lib, 524)).toContain('state.segments.includes(chunk)')
    expect(lineOf(lib, 528)).toContain('if (covering) msg.content = chunk')
    expect(lineOf(lib, 529)).toContain("${msg.content || ''}${chunk}")
    expect(lineOf(lib, 531)).toBe('        }')
  })

  it('两枚后端门里的注释引 :209 / :219 / :625：三行今天确实写着它们说的那三件事', () => {
    const cancel = source('../../../../tests/test_frontend_request_cancel.py')
    const catalog = source('../../../../tests/test_data_file_catalog.py')
    expect(cancel).toContain('lib/sessions.js:209')
    expect(cancel).toContain('lib/sessions.js:219')
    expect(catalog).toContain('lib/sessions.js:625')
    expect(lineOf(lib, 209)).toContain('controller = new AbortController()')
    expect(lineOf(lib, 219)).toContain('export function abortStream()')
    expect(lineOf(lib, 625)).toContain('if (!response.ok) {')
  })

  it('request.completed 那一支仍然只占五行：插一行就会把上面五枚坐标全挪位', () => {
    const at = lib.split('\n').findIndex(text => text.includes("case 'request.completed'"))
    expect(at).toBeGreaterThan(0)
    expect(lineOf(lib, at + 5)).toContain("return { action: 'terminal' }")
    expect(lib.split('\n').length - 1, '本文件的行数是那五枚坐标的地基：多一行少一行都会挪死别人手抄的数字').toBe(1006)
  })
})
