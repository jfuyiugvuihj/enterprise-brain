/**
 * R501 · 终态帧唯一解码处不再丢 `data` 的其余键（frontend/src/lib/sessions.js）
 *
 * 病（现读取证，坐标自本单基点 092fb34 自己扫，不抄别人行号）：`createStreamReducer` 的
 * `request.completed` 那一支今天只把 `awaiting_hitl`／`awaiting_steps`／`data_filename` 三格抄进
 * state，`data` 里其余的键（今天线上真给的还有 `session_id`／`worker_count`／`elapsed`／
 * `answer_length`）在这一格被丢掉。这是「**后端给了、解码处丢了**」那一张，与「**后端根本没给**」
 * 是两件事：后者（legacy `done` 帧与队列终态载荷不带 `data_filename`、缓存命中那一腿压根不发
 * `request.completed`）归后端那一手，本件一枚字都不替它说，也不在前端补造。
 *
 * 🔴 后端今天真给的键集不抄任何人的清单：甲组从 `app/api/v1/chat.py` 当场派生两枚
 * `status="completed"` 的 canonical `request.completed` 出口各自的 `data` 字面键。读 HEAD 那一份
 * 与 r369／r416 同一口径（工作树可能与派工基点不同，拿它对账等于永远绿的假绿）；这一读是
 * 「今天线上给什么」的事实源，**不是改前对比**——本单 `app/**` 一行未动，`git diff app/` 为空。
 *
 * 三态不并脸：`request.started`（还在跑）不交读数，`state` 里连那一枚键都不许多出来；
 * `request.completed`／`request.failed`／`request.cancelled` 各交自己那一张，`event` 逐枚不同名，
 * 失败那一张还带着自己的码。
 *
 * 反证怎么算红（每一把都现跑过，红句原文见 docs/testing/r501-terminal-frame-no-dropped-keys.md）：
 *   刀① 把解码处退回只抄两枚键的旧形（删掉 `state.terminalRead` 那一行，或改回逐枚白名单抄写）
 *        → 甲2 甲3 丙2 丁1 当场红，并且**点名丢掉的那几枚键名**；
 *   刀② 把三态并成一格（completed 那一张的 `event` 写成通用的 terminal 串）→ 乙2 乙3 红；
 *   顺手把缺席补造成空串（`data_filename` 没给也写 `""`）→ 丙1 红，r424 甲3 同刻红（那枚在册钉
 *        本单没放宽也没删）。
 *
 * 🔴 本件只钉 lib 这一格，不碰屏：`r415-server-data-readout.test.js`（含那枚「不许拿发依据填回显」
 * 的反向钉）与 `r424-terminal-data-on-the-wire.test.js` 两枚在册件一行未改，只做追补。
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { consumeSseStream, createStreamReducer, createStreamState, parseSseFrame } from '../sessions.js'

/** 面板与 lib 两边逐字对齐的那枚旧键名：本单没改它，甲组顺带钉它不许被顶掉。 */
const WIRE_KEY = 'terminalDataFilename'
const READ_KEY = 'terminalRead'

/** 工作树那一份：钉的是本单改完之后的形状，拿 HEAD 对账等于钉住改前。 */
function showAtWorktree(repoPath) {
  return readFileSync(new URL('../../../../' + repoPath, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
}

function showAtHead(path) {
  let text
  try {
    text = execFileSync('git', ['show', `HEAD:${path}`], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
  } catch (cause) {
    throw new Error(`读不到真源 HEAD:${path}（git show 失败：${cause.message}）。键集对账不许降级成 skip。`)
  }
  if (!String(text).trim()) throw new Error(`git show HEAD:${path} 返回空内容，无法对账。`)
  return String(text).replace(/\r\n/g, '\n')
}

/** 当场派生：两枚 canonical request.completed 出口各自的 data 字面键（不抄清单，不写死枚数）。 */
function backendTerminalDataKeys() {
  const chat = showAtHead('app/api/v1/chat.py')
  const sites = [...chat.matchAll(/canonical_sse_event\(\s*"request\.completed",[\s\S]{0,1200}?data=\{([^}]*)\}/g)]
  return sites.map(site => [...site[1].matchAll(/"([a-z][a-z0-9_]*)"\s*:/g)].map(item => item[1]))
}

const SITES = backendTerminalDataKeys()
const BACKEND_KEYS = [...new Set(SITES.flat())]

/** 喂一枚真帧给真 reducer：parseSseFrame 与 canonical 闸门都不做简化。 */
function reduceCompleted(data) {
  return reduceEvent('request.completed', data)
}

function reduceEvent(event, data, sequence = 1) {
  const msg = { role: 'assistant', content: '', steps: [] }
  const state = createStreamState()
  const frame = `event: ${event}\ndata: ${JSON.stringify({ request_id: 'req-1', sequence, data })}\n\n`
  return { msg, state, result: createStreamReducer(msg, state)(parseSseFrame(frame)) }
}

/** 一组按后端键集铺出来的可辨值：每一枚键的值都不一样，混格与错位当场红。 */
function sampleFor(keys) {
  const sample = {}
  keys.forEach((key, index) => {
    sample[key] = key === 'data_filename' ? 'sales.xlsx' : `probe-${index}-${key}`
  })
  return sample
}

describe('甲 · 后端真给的键集（现读自 app/api/v1/chat.py）一枚都不许丢在解码处', () => {
  it('取证的先决条件：派生到两枚出口，且两枚的键集逐枚相等（少一枚或漂一枚都算取证失效）', () => {
    expect(SITES, 'request.completed 的出口枚数派生为 0，等于本件没有事实源').toHaveLength(2)
    expect(SITES[0].length, '键集派生为空：正则没命中 data 字面，本件必须红而不是永远绿').toBeGreaterThan(0)
    expect(SITES[1], '两枚出口的 data 键集漂了：本件按第一枚放行会漏掉第二枚').toEqual(SITES[0])
    expect(BACKEND_KEYS).toContain('data_filename')
  })

  it('解码处把后端给的每一枚键原样交回：seen 与 data 都逐枚相等，值一枚都不许被改写', () => {
    const sample = sampleFor(BACKEND_KEYS)
    const { state } = reduceCompleted(sample)
    const read = state[READ_KEY]
    // 读失败也要点枚枚数：整格没交出时 seen 记成空表，红句里逐枚点名丢掉的是哪几枚键。
    const seen = read && Array.isArray(read.seen) ? read.seen : []
    const dropped = BACKEND_KEYS.filter(key => !seen.includes(key))
    expect(dropped, '解码处丢掉了后端真给的键：' + dropped.join(' / ') + '（这一帧到了，界面一枚都没接住）').toEqual([])
    expect([...seen].sort()).toEqual([...BACKEND_KEYS].sort())
    expect(Object.keys(read.data).sort()).toEqual([...BACKEND_KEYS].sort())
    const mangled = BACKEND_KEYS.filter(key => read.data[key] !== sample[key])
    expect(mangled, '这些键的值在解码处被改写了：' + mangled.join(' / ')).toEqual([])
  })

  it('后端明天往 data 里多加一枚键，解码处不用改码也交得回（不靠白名单抄写）', () => {
    const canary = 'r501_canary_key'
    const sample = { ...sampleFor(BACKEND_KEYS), [canary]: 'probe-canary' }
    const { state } = reduceCompleted(sample)
    expect(state[READ_KEY].seen, '白名单式抄写：新键又被丢了').toContain(canary)
    expect(state[READ_KEY].data[canary]).toBe('probe-canary')
    expect(state[WIRE_KEY], '抄新键不许动旧键那一格：面板读的还是 terminalDataFilename').toBe('sales.xlsx')
    expect(state.terminal).toBe('completed')
  })

  it('抄这一格不许动同帧那三格：awaiting_hitl／awaiting_steps／data_filename 形状一字未改', () => {
    const { state } = reduceCompleted({
      session_id: 's-1', data_filename: 'sales.xlsx', awaiting_hitl: true, awaiting_steps: ['export'],
    })
    expect(state.awaitingHitl).toBe(true)
    expect(state.pendingSteps).toEqual(['export'])
    expect(state[WIRE_KEY]).toBe('sales.xlsx')
    expect(state[READ_KEY].event).toBe('request.completed')
  })
})

describe('乙 · 三态不并脸：还在跑 / 成功 / 失败 / 取消各是各的一张', () => {
  it('request.started 不交读数：那一格还没跑完，state 里连这一枚键都不许多出来', () => {
    const { state, result } = reduceEvent('request.started', { session_id: 's-1', data_filename: 'sales.xlsx' })
    expect(result.action).toBe('ignored')
    expect(READ_KEY in state, '把「还在跑」写成一张终态读数就是并脸').toBe(false)
    expect(state.terminal).toBeNull()
  })

  it('成功／失败／取消三张读数彼此不同名，terminal 也各归各的，一枚都不许顶掉另一枚', () => {
    const cases = [
      ['request.completed', { session_id: 's-1', data_filename: 'sales.xlsx' }, 'completed', 'terminal'],
      ['request.failed', { error_code: 'task_timeout' }, 'failed', 'failed'],
      ['request.cancelled', { session_id: 's-1' }, 'cancelled', 'cancelled'],
    ]
    const reads = []
    for (const [event, data, terminal, action] of cases) {
      const { state, result } = reduceEvent(event, data)
      expect(result.action).toBe(action)
      expect(state.terminal).toBe(terminal)
      expect(state[READ_KEY], `${event} 没交出自己那一张读数`).toBeTruthy()
      expect(state[READ_KEY].event).toBe(event)
      reads.push(state[READ_KEY].event)
    }
    expect(new Set(reads).size, '三态并成一格了：' + reads.join(' / ')).toBe(3)
  })

  it('失败那一张仍说失败的话：自己的码在，也不许被读成成功那一张', () => {
    const { state } = reduceEvent('request.failed', { error_code: 'no_answer_produced', worker_count: 0 })
    expect(state.errorCode).toBe('no_answer_produced')
    expect(state.terminal).toBe('failed')
    expect(state[READ_KEY].event).toBe('request.failed')
    expect(state[READ_KEY].seen).toContain('error_code')
    expect(WIRE_KEY in state, '失败那一帧不交用表读数，界面也不许替它造一枚').toBe(false)
  })

  it('legacy done 帧（非 canonical）不造读数：那一腿今天根本没有这一帧，只能是一张「没到」', () => {
    const msg = { role: 'assistant', content: '', steps: [] }
    const state = createStreamState()
    createStreamReducer(msg, state)(parseSseFrame('event: done\ndata: {"content":""}\n\n'))
    expect(state.terminal).toBe('completed')
    expect(READ_KEY in state).toBe(false)
  })
})

describe('丙 · 给了与没给必须分得开：缺席不补造，空表也不谎报', () => {
  it('data 只给 session_id：seen 只有那一枚，其余键根本不存在，也不许写出空的 terminalDataFilename', () => {
    const { state } = reduceCompleted({ session_id: 's-1' })
    expect(state[READ_KEY].seen).toEqual(['session_id'])
    expect('data_filename' in state[READ_KEY].data, '后端没给这一格，前端不许凭空造一个键').toBe(false)
    expect(WIRE_KEY in state).toBe(false)
  })

  it('空表（这一帧到了但一格都没给）是一张「没到读数」之外的脸：seen 是空数组而不是没这一枚键', () => {
    const { state } = reduceCompleted({})
    expect(READ_KEY in state, '帧到了却一格没给，与帧没到是两件事，这里必须能分开').toBe(true)
    expect(Array.isArray(state[READ_KEY].seen)).toBe(true)
    expect(state[READ_KEY].seen).toEqual([])
    expect(state.terminal).toBe('completed')
  })

  it('非字符串的 data_filename 仍走「没给」那一张：旧键不写，但整格读数照原样交回', () => {
    const { state } = reduceCompleted({ session_id: 's-1', data_filename: null })
    expect(WIRE_KEY in state).toBe(false)
    expect(state[READ_KEY].seen).toEqual(['session_id', 'data_filename'])
    expect(state[READ_KEY].data.data_filename).toBeNull()
  })
})

describe('丁 · 真流跑到底 + 解码处形状的地基', () => {
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

  it('真 consumeSseStream 吃到终态帧 → result.state 交回的就是后端给的全部键', async () => {
    const sample = sampleFor(BACKEND_KEYS)
    const frame = `event: request.completed\ndata: ${JSON.stringify({ request_id: 'req-1', sequence: 2, data: sample })}\n\n`
    const result = await consumeSseStream(sseResponse([frame]), { role: 'assistant', content: '', steps: [] }, {})
    expect(result.stopped).toBe('done')
    const seen = result.state[READ_KEY] && Array.isArray(result.state[READ_KEY].seen) ? result.state[READ_KEY].seen : []
    const dropped = BACKEND_KEYS.filter(key => !seen.includes(key))
    expect(dropped, '真流跑到终态之后解码处丢掉了这些键：' + dropped.join(' / ')).toEqual([])
    expect(result.state[READ_KEY].event).toBe('request.completed')
    expect(result.state[WIRE_KEY]).toBe('sales.xlsx')
  })

  it('乱序闸门照旧：迟到的终态帧不许把读数洗成新的一轮', () => {
    const msg = { role: 'assistant', content: '', steps: [] }
    const state = createStreamState()
    const reduce = createStreamReducer(msg, state)
    const frame = (sequence, data) => parseSseFrame(`event: request.completed\ndata: ${JSON.stringify({ request_id: 'req-1', sequence, data })}\n\n`)
    reduce(frame(3, { session_id: 's-1', data_filename: 'new.xlsx' }))
    const dropped = reduce(frame(2, { session_id: 's-1', data_filename: 'old.xlsx' }))
    expect(dropped.action).toBe('ignored')
    expect(state[READ_KEY].data.data_filename).toBe('new.xlsx')
  })

  it('request.completed 那一支仍只占五行：多占一行就把 r424 丁组那五枚手抄坐标全挪位', () => {
    const lib = showAtWorktree('frontend/src/lib/sessions.js')
    const lines = lib.split('\n')
    const at = lines.findIndex(text => text.includes("case 'request.completed'"))
    expect(at).toBeGreaterThan(0)
    // 分支占五行（0-based at..at+4）：第五行既是本单的抄写处，也是那枚 terminal 出口。
    expect(lines[at + 4], '第五行必须抄写与出口同一行：拆开就多占一行，r424 丁组那五枚坐标全挪位')
      .toContain("state.terminalRead = { event: 'request.completed'")
    expect(lines[at + 4]).toContain("return { action: 'terminal' }")
    expect(lines[at + 3], '第四行仍是面板读的那枚旧键名：不许被本单挪走').toContain('terminalDataFilename')
    expect(lines[at + 5], '第六行就是失败那一支：本支多一行它就挪位').toBe("        case 'request.failed':")
  })
})
