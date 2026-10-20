/**
 * R512 · legacy `done` 那一支必须把载荷里的 data_filename 采纳进 state
 *
 * 病（本单唯一的断点，改前取证取在 60a8e01）：R504 已经让后端 legacy `done` 帧与队列终态
 * 「该给 data_filename 就给、说不清就整格不落键」（app/api/v1/chat.py:372
 * attach_terminal_data_filename，唯一挂载件；两枚出口 app/api/v1/chat.py:2296 队列终态与 app/api/v1/chat.py:2345 done 帧），
 * 可屏侧这一格今天仍只由 canonical 那条腿驱动：frontend/src/lib/sessions.js 的 case done
 * 连 payload 一个字都不读 ⇒ 只走 legacy 道的那一屏（缓存命中那条腿今天压根不发
 * request.completed：chat.py:2626 cached_response 只发 status/text/sources/done），后端明明
 * 报了这一轮用的是哪份数据文件，屏上仍然不说。（同一腿的 done 今天也不交 dataset_files——
 * chat.py:2656-2663 那枚调用点没有那一枚参数，所以缓存屏这一格仍是一句不画；那是 R504 明写
 * 未治的账，不属本单，本件也不替它画成「已上屏」。
 *
 * 🔴 三形分开（与 R510 同一条纪律：绝不把「没说话」画成「说了空话」）：
 *   给了非空值 ⇒ 采纳，写进 state.terminalDataFilename —— 键名逐字照 sessions.js:481 那枚
 *             在册写法，本单不新造字段名，也不另起第二炉读法；
 *   给了空串   ⇒ 一个字都不写：既不拿它覆盖 state 里已有的非空真值，也不凭空补造一枚空键；
 *   整格缺席   ⇒ 一个字都不动。缺席用 Object.prototype.hasOwnProperty 判，undefined 另立一态。
 *
 * 🔴 两条道的优先级（现读流上次序之后定死）：canonical request.completed 在先到
 *   （chat.py:2995 yield，app/api/v1/chat.py:3014-3016 的注释明写它排在 legacy done 之前），legacy done 是流末尾
 *   那一枚（chat.py:3040 / app/api/v1/chat.py:3722）。于是规矩是「先到者胜，后到的 legacy 只填还没人说过的那一格」：
 *   后到的 legacy 空值不得覆盖先到的 canonical 真值；两枚非空值也不许互相改口。
 *
 * 🔴 形状约束（本单原地改，一行都没多）：sessions.js 的总行数由在册件 r424:160 按【工作树】钉死
 *   为 1006，r427:386 又按【HEAD】钉死 app/api/v1/chat.py:814 必须是空行。多插一行，前者在本树上立刻红、后者在总并
 *   树上红，两枚都是假红。所以采纳只许写成 case 行之下、return 行之上的那一枚行。
 *
 * 反证怎么算红（三把刀各现跑一次，红字原文与逐字节还原读数见
 * docs/testing/r512-legacy-done-data-filename-2026-09-29.md）：
 *   刀一 把 case done 那一支改回改前这形（一个字不读 payload）⇒ 实测红 7 枚：甲1 乙5 乙6 乙7 丙1 丙5 丁3；
 *   刀二 逐字照 app/api/v1/chat.py:481 抄成「是字符串就采纳」（连带摘掉非空与先到者胜两枚闸门）⇒ 实测红 5 枚：甲2 甲3 乙1 乙4 乙7；
 *   刀三 无条件赋值（缺席与非字符串都补造成空串）⇒ 实测红 13 枚：甲2 甲3 甲4 甲5 甲6 甲7 乙1 乙2 乙4 乙7 丙4 丙5 丁3。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { consumeSseStream, createStreamReducer, createStreamState, isCanonicalEvent, parseSseFrame } from '../sessions.js'

/** 面板 adoptServerDataRead 读的那一枚键名：与 sessions.js:481 逐字同源，两边不许各写一套。 */
const WIRE_KEY = 'terminalDataFilename'

const source = name => readFileSync(new URL(name, import.meta.url), 'utf8').replace(/\r?\n/g, '\n')
const lineOf = (text, n) => text.split('\n')[n - 1] || ''

/**
 * 真 done 帧的键集：现读 app/api/v1/chat.py:2335-2344 done_sse_frame 的 payload 字面量。
 * data_filename 只在后端真读得出那一份时才出现（attach_terminal_data_filename 交空串就整格不落键），
 * 所以「缺席」这一形就是本函数的默认形状，overrides 不给这一格即是缺席。
 */
function donePayload(overrides = {}) {
  return {
    type: 'done',
    terminal_state: 'answered',
    answer_present: true,
    sources_present: false,
    sources: [],
    sources_error: '',
    usage: {},
    approval: null,
    ...overrides,
  }
}

/** 走真 parseSseFrame：这一帧确实从 legacy 道进来，不是在测试里假装。 */
function reduceWire(event, payload, state = createStreamState()) {
  const msg = { role: 'assistant', content: '', steps: [] }
  const frame = `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`
  return { msg, state, result: createStreamReducer(msg, state)(parseSseFrame(frame)) }
}

/** 不经 JSON：JSON 会丢掉 undefined，这一枚只用来单独验 undefined 那一态。 */
function reduceObject(event, payload, state = createStreamState()) {
  const msg = { role: 'assistant', content: '', steps: [] }
  return { msg, state, result: createStreamReducer(msg, state)({ event, payload }) }
}

/** canonical 那一腿的终态帧：信封形状现读 chat.py::canonical_sse_event 的调用点。 */
const reduceCompleted = (data, state) => reduceWire('request.completed', { request_id: 'req-1', sequence: 1, data }, state)

/** 同一枚 state 上连打两帧：优先级只能在「先到 / 后到」的序列里才量得出来。 */
function twoLegs(canonicalData, doneOverrides) {
  const state = createStreamState()
  if (canonicalData !== null) reduceCompleted(canonicalData, state)
  const msg = { role: 'assistant', content: '', steps: [] }
  const reduce = createStreamReducer(msg, state)
  const second = reduce(parseSseFrame(`event: done\ndata: ${JSON.stringify(donePayload(doneOverrides))}\n\n`))
  return { state, msg, second }
}

describe('甲 · legacy done 那一支的三形各一枚：非空才采纳，空串与缺席都不许写字', () => {
  it('甲1 给了非空值 → 采纳，键名就是 :481 那枚 terminalDataFilename，值就是那一个名字', () => {
    const { state, result } = reduceWire('done', donePayload({ data_filename: 'sales.xlsx' }))
    expect(result.action).toBe('terminal')
    expect(state.terminal).toBe('completed')
    expect(state[WIRE_KEY]).toBe('sales.xlsx')
  })

  it('甲2 给了空串 → 键根本不存在：不许凭空补造一枚空值替后端宣布「说不准」', () => {
    const { state, result } = reduceWire('done', donePayload({ data_filename: '' }))
    expect(result.action).toBe('terminal')
    expect(state.terminal, '空串那一形也不能把终态那一格带坏：done 仍是流结束的信号').toBe('completed')
    expect(Object.prototype.hasOwnProperty.call(state, WIRE_KEY), '空串被采纳了：屏上会凭空多出「说不准」那一句').toBe(false)
    expect(state[WIRE_KEY]).toBeUndefined()
  })

  it('甲3 给了空串而 state 里已有非空真值 → 真值原样保留（空串不许覆盖）', () => {
    const state = createStreamState()
    state[WIRE_KEY] = 'sales.xlsx'
    reduceWire('done', donePayload({ data_filename: '' }), state)
    expect(state[WIRE_KEY]).toBe('sales.xlsx')
  })

  it('甲4 整格缺席 → 一个字都不动：hasOwnProperty 判缺席，键必须根本不存在', () => {
    const { state } = reduceWire('done', donePayload())
    expect(Object.prototype.hasOwnProperty.call(state, WIRE_KEY), '后端没说话，state 里就不许多出这一枚键').toBe(false)
    expect(state[WIRE_KEY]).toBeUndefined()
  })

  it('甲5 undefined 另立一态：键在位而值是 undefined，同样不许写成空串那一形', () => {
    const { state } = reduceObject('done', { type: 'done', data_filename: undefined })
    expect(Object.prototype.hasOwnProperty.call(state, WIRE_KEY), 'undefined 被并成了「后端说了空话」').toBe(false)
    expect(state.terminal).toBe('completed')
  })

  it('甲6 非字符串一律不写：null / 7 / {} / [] / true 五枚形状各自验一遍', () => {
    for (const shape of [null, 7, {}, [], true]) {
      const { state } = reduceObject('done', donePayload({ data_filename: shape }))
      expect(Object.prototype.hasOwnProperty.call(state, WIRE_KEY), `形状 ${JSON.stringify(shape)} 混进了读数那一格`).toBe(false)
    }
  })

  it('甲7 载荷整枚缺席（payload 为 null）也不崩：终态照旧，那一格一个字不写', () => {
    const { state, result } = reduceObject('done', null)
    expect(result.action).toBe('terminal')
    expect(state.terminal).toBe('completed')
    expect(Object.prototype.hasOwnProperty.call(state, WIRE_KEY)).toBe(false)
  })

  it('甲8 这一帧今天确实走 legacy 道：isCanonicalEvent 现读为 false，闸门不会替它抄键', () => {
    expect(isCanonicalEvent('done', donePayload({ data_filename: 'sales.xlsx' }))).toBe(false)
  })
})

describe('乙 · 两条道的优先级：先到者胜，后到的 legacy 只填还没人说过的那一格', () => {
  it('乙1 canonical 真值先到 + legacy 空串后到 → 屏上仍是 canonical 那一个名字（本单点名要钉的那一枚）', () => {
    const { state, second } = twoLegs({ session_id: 's-1', data_filename: 'sales.xlsx' }, { data_filename: '' })
    expect(second.action).toBe('terminal')
    expect(state[WIRE_KEY]).toBe('sales.xlsx')
  })

  it('乙2 canonical 真值先到 + legacy 整格缺席 → 原样保留，不许抹成空', () => {
    const { state } = twoLegs({ session_id: 's-1', data_filename: 'sales.xlsx' }, {})
    expect(state[WIRE_KEY]).toBe('sales.xlsx')
  })

  it('乙3 canonical 真值先到 + legacy 同一枚真值 → 值不变（两枚同源：都出自 terminal_data_filename(dataset_files)）', () => {
    const { state } = twoLegs({ session_id: 's-1', data_filename: 'sales.xlsx' }, { data_filename: 'sales.xlsx' })
    expect(state[WIRE_KEY]).toBe('sales.xlsx')
  })

  it('乙4 canonical 真值先到 + legacy 另一枚真值 → 先到者胜，后到的一枚不改口', () => {
    const { state } = twoLegs({ session_id: 's-1', data_filename: 'sales.xlsx' }, { data_filename: 'other.xlsx' })
    expect(state[WIRE_KEY], '两条道各报各的：屏上那句话被后到的一枚改了口').toBe('sales.xlsx')
  })

  it('乙5 canonical 空串先到（键在场）+ legacy 非空 → 填上名字：非空优先于「说不准」', () => {
    const { state } = twoLegs({ session_id: 's-1', data_filename: '' }, { data_filename: 'sales.xlsx' })
    expect(Object.prototype.hasOwnProperty.call(state, WIRE_KEY)).toBe(true)
    expect(state[WIRE_KEY]).toBe('sales.xlsx')
  })

  it('乙6 流上没有 canonical 终态、只有 legacy done 这一枚 → 名字照样上屏（本单存在的理由）', () => {
    const { state } = reduceWire('done', donePayload({ data_filename: 'sales.xlsx' }))
    expect(state[WIRE_KEY]).toBe('sales.xlsx')
  })

  it('乙7 两枚 legacy done（重放）→ 第一枚赢，第二枚不改口', () => {
    const state = createStreamState()
    reduceWire('done', donePayload({ data_filename: 'first.xlsx' }), state)
    reduceWire('done', donePayload({ data_filename: 'second.xlsx' }), state)
    expect(state[WIRE_KEY]).toBe('first.xlsx')
  })
})

describe('丙 · 真流跑到底：交回面板的还是同一枚键名', () => {
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
  const doneFrame = overrides => `event: done\ndata: ${JSON.stringify(donePayload(overrides))}\n\n`
  const completedFrame = data => `event: request.completed\ndata: ${JSON.stringify({ request_id: 'req-1', sequence: 1, data })}\n\n`

  it('丙1 真流只发 legacy done 带文件名 → result.state 里就是那一个名字，stopped 仍是 done', async () => {
    const result = await consumeSseStream(sseResponse([doneFrame({ data_filename: 'sales.xlsx' })]), { role: 'assistant', content: '', steps: [] }, {})
    expect(result.stopped).toBe('done')
    expect(result.state[WIRE_KEY]).toBe('sales.xlsx')
  })

  it('丙2 真流 canonical(名字) → legacy done(名字) → 交回面板的还是那一个名字，两条道打不成一架', async () => {
    const result = await consumeSseStream(sseResponse([completedFrame({ session_id: 's-1', data_filename: 'sales.xlsx' }), doneFrame({ data_filename: 'sales.xlsx' })]), { role: 'assistant', content: '', steps: [] }, {})
    expect(result.state[WIRE_KEY]).toBe('sales.xlsx')
  })

  it('丙3 真流 canonical(空串) → legacy done(缺席) → 键在场且值为空串：那一态是「说不准」，legacy 不许抹掉', async () => {
    const result = await consumeSseStream(sseResponse([completedFrame({ session_id: 's-1', data_filename: '' }), doneFrame()]), { role: 'assistant', content: '', steps: [] }, {})
    expect(Object.prototype.hasOwnProperty.call(result.state, WIRE_KEY)).toBe(true)
    expect(result.state[WIRE_KEY]).toBe('')
  })

  it('丙4 真流只发 legacy done 且整格缺席 → 键根本不存在：屏上那一行一枚字都不画', async () => {
    const result = await consumeSseStream(sseResponse([doneFrame()]), { role: 'assistant', content: '', steps: [] }, {})
    expect(result.stopped).toBe('done')
    expect(Object.prototype.hasOwnProperty.call(result.state, WIRE_KEY)).toBe(false)
  })

  it('丙5 接缝两边键名逐字一致：lib 写的这一枚就是面板 adoptServerDataRead 读的那一枚', () => {
    const lib = source('../sessions.js')
    const panel = source('../../components/ChatPanel.vue')
    expect(lib, 'legacy 腿写的键名漂了：面板读不到，那一行永远不画').toContain(`state.${WIRE_KEY} = payload.data_filename`)
    expect(panel, '面板读的键名与 lib 写的不是同一枚').toContain(`result?.state?.${WIRE_KEY}`)
  })
})

describe('丁 · 原地改：行数与在册手抄坐标一枚都不许挪', () => {
  const lib = source('../sessions.js')

  it('丁1 本文件行数仍是 1006：r424 丁组与 r427 戊组都按这枚地基数手抄行号', () => {
    expect(lib.split('\n').length - 1, '行数漂了：多一行少一行都会挪死别人手抄的数字').toBe(1006)
  })

  it('丁2 六枚在册活坐标逐枚现读仍指着原处：:128 / :524 / :529 / :531 / :625，且 :814 仍是空行', () => {
    expect(lineOf(lib, 128)).toContain('messages.value = entry ?')
    expect(lineOf(lib, 524)).toContain('state.segments.includes(chunk)')
    expect(lineOf(lib, 529)).toContain('else msg.content = ')
    expect(lineOf(lib, 531)).toBe('        }')
    expect(lineOf(lib, 625)).toContain('if (!response.ok) {')
    expect(lineOf(lib, 814).trim(), ':814 不再是空行：r427 戊组那枚反向自证会在总并树上转红').toBe('')
  })

  it('丁3 case done 那一支仍占三行：case 行 / 采纳行 / return 行，一行都不许多', () => {
    const at = lib.split('\n').findIndex(text => text.includes("case 'done'"))
    expect(at).toBeGreaterThan(0)
    expect(lineOf(lib, at + 1)).toContain('state.terminal = ')
    expect(lineOf(lib, at + 2)).toContain(`state.${WIRE_KEY} = payload.data_filename`)
    expect(lineOf(lib, at + 3), 'done 那一支多出一行就会挪死 :814').toBe("        return { action: 'terminal' }")
  })
})
