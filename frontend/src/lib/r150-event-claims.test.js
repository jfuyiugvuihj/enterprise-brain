/**
 * R150 · 出处事件的「谁认领」账（判据① 的根因面）
 *
 * 缺陷形状是这么长出来的：后端 R41 就把 sources 提升成 canonical 事件了，前端
 * `isCanonicalEvent()` 认它是 canonical，落进 switch 的 default，塞进
 * `state.unknownEvents` —— 而 unknownEvents 全仓零读取方。于是「后端早就吐到线上」在界面上
 * 等于没有，R41 判据③「引用条可点回原文」就这么没销账。
 *
 * 所以这里钉的不是「今天画得像不像」，而是【新增一种后端事件必须当场红】：
 * 事件名的真源只有一处 = `app/api/v1/chat.py` 的出口调用点，测试现场从 git 对象里枚举，
 * 不手抄名单（手抄的名单就是下一次漂移的现场）。取不到真源一律抛错，禁止 skip。
 *
 * 环境是 node：零活网络、零模型往返、零端口（R56 闸门）。所有帧都是测试自己造的假 Response。
 */
import { execFileSync } from 'node:child_process'
import { describe, expect, it, vi } from 'vitest'
import { formatDayStamp } from './provenance.js'
import {
  EVENT_CLAIMS,
  LEGACY_EVENTS,
  consumeSseStream,
  createStreamReducer,
  createStreamState,
  isClaimedEvent,
  parseSseFrame,
  sourcesFromEnvelope,
} from './sessions.js'

/** 与 lib/errcodes.test.js 同一枚 ref：三个 worktree 共享同一个 object DB，读法与工作树新旧无关。 */
const BACKEND_REF = 'codex/data-file-catalog'
const CHAT_SOURCE = 'app/api/v1/chat.py'

function backendSource() {
  let text
  try {
    text = execFileSync('git', ['show', `${BACKEND_REF}:${CHAT_SOURCE}`], {
      encoding: 'utf8',
      maxBuffer: 32 * 1024 * 1024,
    })
  } catch (cause) {
    throw new Error(
      `读不到后端真源 ${BACKEND_REF}:${CHAT_SOURCE}（git show 失败：${cause.message}）。`
      + '事件名对账不许降级：这里必须红，skip 等于把这条闸门退回成装饰。',
    )
  }
  if (typeof text !== 'string' || !text.trim()) {
    throw new Error(`git show ${BACKEND_REF}:${CHAT_SOURCE} 返回空内容，无法对账。`)
  }
  return text
}

/**
 * 三形制全枚举（少一种就会漏名字，chat.py 里三形制并存是既成事实）：
 *   canonical_sse_event("x")   —— 带 request_id/sequence 的信封出口
 *   sse_event("x")             —— 走构造器的 legacy 出口
 *   yield f"event: x\ndata:..." —— 直写帧的 legacy 出口
 */
/** 纯枚举：喂任意 chat.py 形状的文本，吐出事件名集合（夹具也用这一枚，不另写一套解析）。 */
function collectWireNames(src) {
  const names = new Set()
  const patterns = [
    /canonical_sse_event\(\s*["']([a-z][a-z0-9_.]*)["']/g,
    /(?<!canonical_)\bsse_event\(\s*["']([a-z][a-z0-9_.]*)["']/g,
    /event:\s*([a-z][a-z0-9_]*)\\ndata:/g,
  ]
  for (const re of patterns) {
    for (const match of src.matchAll(re)) names.add(match[1])
  }
  return names
}

/** 真源专用的量级守卫：解析形状一失效就抛，不拿残缺名单去对账（假绿比红贵）。 */
function wireEventNames(src) {
  const names = collectWireNames(src)
  if (names.size < 8) {
    throw new Error(
      `只枚举出 ${names.size} 枚事件名，少于已实量的 14 枚所在的量级：疑似解析形状失效。`
      + '拿残缺名单去对账会稳定假绿，这里选择抛错。',
    )
  }
  return names
}

const WIRE = wireEventNames(backendSource())
const CLAIMS = Object.keys(EVENT_CLAIMS)

describe('A · 事件认领表 ↔ 后端出口（新增一种后端事件当场红）', () => {
  it('枚举本身不是空的（闸门空跑等于没闸）', () => {
    expect(WIRE.has('sources'), '后端出口里应当有 sources 这枚事件').toBe(true)
    expect(WIRE.has('queued')).toBe(true)
    expect(WIRE.has('request.started')).toBe(true)
    expect(WIRE.has('heartbeat')).toBe(true)
  })

  it('后端发出的每一枚事件名都有认领交代：漏一枚就点名一枚', () => {
    const unclaimed = [...WIRE].filter(name => !isClaimedEvent(name)).sort()
    expect(unclaimed, '后端新增了事件而界面没认领：' + unclaimed.join(', ')).toEqual([])
  })

  it('认领表里不许留僵尸名字：后端不发了，这里就得删（否则漂移反向看不见）', () => {
    const zombies = CLAIMS.filter(name => !WIRE.has(name)).sort()
    expect(zombies, 'EVENT_CLAIMS 里这些名字后端已不再发出：' + zombies.join(', ')).toEqual([])
  })

  it('每一枚交代都必须落进四种处理之一，没有第五种「看着像有其实没有」', () => {
    const allowed = ['render', 'note', 'terminal', 'silent']
    for (const name of CLAIMS) {
      expect(allowed, `${name} 的认领方式不在口径内`).toContain(EVENT_CLAIMS[name])
    }
  })

  it('sources 是 render，不是 note 也不是 silent（R41 判据③ 的销账点）', () => {
    expect(EVENT_CLAIMS.sources).toBe('render')
    // 反证留档：把它降级成 'note' / 'silent' 时这一条必须红，见回执的反证矩阵 V-1。
  })

  it('夹具反向证明：把这枚闸门喂给「后端刚多了一种事件」的源，它一定点名那一种', () => {
    // 不许为了这条去改 app/**（不在写域），所以按仓库 V6 判红夹具的老办法：
    // 同一套枚举 + 同一套对账，喂一份合成源。合成源里多的名字必须被点名，一个不多一个不少。
    const synthetic = [
      'yield canonical_sse_event(',
      '    "sources",',
      '    request_id=r, sequence=1,',
      ')',
      'yield canonical_sse_event(',
      '    "answer.revised",',
      '    request_id=r, sequence=2,',
      ')',
      'yield sse_event("heartbeat", {})',
      'yield f"event: text\\ndata: {}\\n\\n"',
    ].join('\n')
    const names = collectWireNames(synthetic)
    expect([...names].sort()).toEqual(['answer.revised', 'heartbeat', 'sources', 'text'])
    expect([...names].filter(name => !isClaimedEvent(name))).toEqual(['answer.revised'])
    // 反方向：后端哪天不再发 sources，僵尸名那一腿也要点名它（对账不是单向的）。
    const dropped = synthetic.replace('"sources",', '"sources_removed",')
    expect(collectWireNames(dropped).has('sources')).toBe(false)
  })

  it('legacy 名单与认领表同源：两处清单不许各长各的', () => {
    const claimedLegacy = CLAIMS.filter(name => !name.includes('.') && name !== 'sources').sort()
    expect(claimedLegacy).toEqual([...LEGACY_EVENTS].sort())
  })

  it('heartbeat / request.started 是【显式选择不画】，与「漏接」在表里就是两个值', () => {
    expect(EVENT_CLAIMS.heartbeat).toBe('silent')
    expect(EVENT_CLAIMS['request.started']).toBe('silent')
    expect(EVENT_CLAIMS.done).toBe('terminal')
    expect(EVENT_CLAIMS.queued).toBe('render')
  })
})

// ==================== 下面全是行为：真 reducer + 真 consumeSseStream，吃自造的帧 ====================

const SOURCE_ROWS = [
  {
    worker: 'doc_agent',
    source: '差旅费报销制度-2026.pdf',
    source_id: 'doc-travel',
    chunk_index: 4,
    score: 0.412,
    score_type: 'rerank',
    document_version_id: 7,
    index_version_id: 7,
    content_sha256: 'a'.repeat(64),
    classification: 2,
    department: '销售部',
    permission_checked: true,
    provenance_status: 'verified',
  },
]

function canonicalFrame(event, data, sequence) {
  return 'event: ' + event + '\ndata: ' + JSON.stringify({
    request_id: 'req-1',
    trace_id: 'trace-1',
    task_id: 'task-1',
    sequence,
    timestamp: '2026-09-21T12:00:00Z',
    status: event === 'request.completed' ? 'completed' : 'running',
    data,
  }) + '\n\n'
}

describe('B · 出处帧读成事实（lib/sessions.js 只做搬运）', () => {
  it('canonical sources 帧 → 行、条数、不展示条数、范围理由各归一格', () => {
    const msg = { role: 'assistant', content: '' }
    const state = createStreamState()
    const reduce = createStreamReducer(msg, state)
    const frame = canonicalFrame('sources', {
      session_id: 's-1',
      sources: SOURCE_ROWS,
      hit_count: 1,
      unauthorized_count: 3,
      scope_reason_code: 'department_scope',
    }, 3)
    const result = reduce(parseSseFrame(frame))
    expect(result.action).toBe('sources')
    expect(msg.sources.rows).toHaveLength(1)
    expect(msg.sources.rows[0].filename).toBe('差旅费报销制度-2026.pdf')
    expect(msg.sources.hitCount).toBe(1)
    // 「检到了但不给你看」与「没检到」是两个数：这里必须各留一格，不许在搬运层就合并。
    expect(msg.sources.hiddenCount).toBe(3)
    expect(msg.sources.scopeReasonCode).toBe('department_scope')
    expect(state.unknownEvents).toEqual([])
  })

  it('迟到的 sources 被 sequence 闸门吃掉，不覆盖新一轮的出处', () => {
    const msg = { role: 'assistant', content: '' }
    const state = createStreamState()
    const reduce = createStreamReducer(msg, state)
    reduce(parseSseFrame(canonicalFrame('sources', { sources: SOURCE_ROWS, hit_count: 1, unauthorized_count: 0 }, 9)))
    const late = reduce(parseSseFrame(canonicalFrame('sources', {
      sources: [{ ...SOURCE_ROWS[0], source: '旧一轮的制度.pdf', source_id: 'doc-old' }], hit_count: 1, unauthorized_count: 0,
    }, 5)))
    expect(late.action).toBe('ignored')
    expect(msg.sources.rows[0].filename).toBe('差旅费报销制度-2026.pdf')
  })

  it('后端没给的键留空，不替它造一个：密级/版本/分都没给就是 null / 空串', () => {
    const bare = sourcesFromEnvelope({ sources: [{ source: '只有名字.pdf' }] })
    expect(bare.rows[0].classification).toBe('')
    expect(bare.rows[0].versionId).toBe('')
    expect(bare.rows[0].score).toBe(null)
    expect(bare.hitCount).toBe(1)
    expect(bare.hiddenCount).toBe(0)
    expect(bare.scopeReasonCode).toBe('')
  })

  it('没有 source 文件名的行不进可画集合（画一条空的引用条比不画更坏）', () => {
    const bare = sourcesFromEnvelope({ sources: [{ source: '   ' }, { source: '真文件.pdf', source_id: 'x' }] })
    expect(bare.rows.map(row => row.filename)).toEqual(['真文件.pdf'])
  })

  it('excerpt 一旦出现就有读取位（今天后端没抄这一格，见回执的需求清单）', () => {
    const withExcerpt = sourcesFromEnvelope({ sources: [{ source: 'a.pdf', excerpt: '限额以内据实报销。' }] })
    expect(withExcerpt.rows[0].excerpt).toBe('限额以内据实报销。')
    const without = sourcesFromEnvelope({ sources: [{ source: 'a.pdf' }] })
    expect(without.rows[0].excerpt).toBe('')
  })

  it('生效日期这一格是【活的读取位】：认后端真名，抄进来就上屏，没抄就是空串', () => {
    // 后端今天没把这一格抄进 sources 行（chat.py::_document_source_row），但真值在库里就有：
    // app/rag/indexing.py:102/361 的 version.published_at（574/640 写入，0002 迁移在册）。
    // 钉映射层而不是只钉卡片：卡片读的那一格是这里造出来的，两头都钉才不会出现
    // 「界面上有这一格、线上永远画不出来」的装饰品 —— 那正是 sources 事件当年的死法。
    for (const key of ['effective_date', 'published_at', 'created_at']) {
      const row = sourcesFromEnvelope({ sources: [{ source: 'a.pdf', [key]: '2026-03-01T09:00:00+08:00' }] })
      expect(row.rows[0].effectiveDate, `${key} 应当被读取位接住`).toBe('2026-03-01T09:00:00+08:00')
      expect(formatDayStamp(row.rows[0].effectiveDate), `${key} 要画出带年份的那一枚日`).toBe('2026-03-01')
    }
    // 没给这一格 -> 空串：不是「今天」，也不是 1970-01-01
    const missing = sourcesFromEnvelope({ sources: [{ source: 'a.pdf' }] })
    expect(missing.rows[0].effectiveDate).toBe('')
    expect(formatDayStamp(missing.rows[0].effectiveDate)).toBe('')
  })


  it('未认领的 canonical 事件：记名 + 报 unknown，不再静默 return ignored', () => {
    const msg = { role: 'assistant', content: '' }
    const state = createStreamState()
    const reduce = createStreamReducer(msg, state)
    const result = reduce(parseSseFrame(canonicalFrame('answer.revised', {}, 2)))
    expect(result).toMatchObject({ action: 'unknown', event: 'answer.revised' })
    expect(state.unknownEvents).toEqual(['answer.revised'])
  })

  it('不带信封的新事件名走同一条未认领通道（两条路不能一条有声一条没声）', () => {
    const msg = { role: 'assistant', content: '' }
    const state = createStreamState()
    const reduce = createStreamReducer(msg, state)
    const result = reduce(parseSseFrame('event: brand_new\ndata: {"content":"x"}\n\n'))
    expect(result.action).toBe('unknown')
    expect(result.event).toBe('brand_new')
    expect(state.unknownEvents).toEqual(['brand_new'])
  })

  it('heartbeat 是显式不画：既不记名也不报 unknown（把噪声报成缺陷也是缺陷）', () => {
    const msg = { role: 'assistant', content: '' }
    const state = createStreamState()
    const reduce = createStreamReducer(msg, state)
    const result = reduce(parseSseFrame('event: heartbeat\ndata: {"type":"heartbeat"}\n\n'))
    expect(result.action).toBe('ignored')
    expect(state.unknownEvents).toEqual([])
  })

  it('queued 回执只带 request_id 上账：位次另读状态接口，档位那两格前端一枚都不读（R32 假控件禁令）', () => {
    const msg = { role: 'assistant', content: '' }
    const reduce = createStreamReducer(msg, createStreamState())
    const result = reduce(parseSseFrame('event: queued\ndata: {"type":"queued","request_id":"req-9","status":"queued"}\n\n'))
    expect(result.action).toBe('queued')
    expect(msg.queue).toEqual({ requestId: 'req-9', status: 'queued' })
    expect(Object.keys(msg.queue).sort()).toEqual(['requestId', 'status'])
  })

  it('命中缓存的 text 帧：三枚字段原样搬运，不加工不补时间', () => {
    const hit = { role: 'assistant', content: '' }
    const reduceHit = createStreamReducer(hit, createStreamState())
    const hitResult = reduceHit(parseSseFrame('event: text\ndata: ' + JSON.stringify({
      type: 'text', content: '缓存里的答案。', cached: true,
      cache_generated_at: '2026-09-21T09:00:00Z', cache_note: '缓存结果 · 今天上午',
    }) + '\n\n'))
    expect(hitResult.action).toBe('text')
    expect(hitResult.cache).toMatchObject({ cached: true, note: '缓存结果 · 今天上午' })
    expect(hit.cache).toMatchObject({ cached: true, generatedAt: '2026-09-21T09:00:00Z' })
  })

  it('实时腿记的是【当场观察到】那格（cached:false + observed），不是替后端编一句未命中', () => {
    const live = { role: 'assistant', content: '' }
    const reduceLive = createStreamReducer(live, createStreamState())
    const liveResult = reduceLive(parseSseFrame('event: text\ndata: {"type":"text","content":"实时的答案。"}\n\n'))
    expect(liveResult.action).toBe('text')
    expect(live.cache).toEqual({ cached: false, generatedAt: '', note: '', observed: true })
    // 空帧与重复帧不该留下读数：它们压根没往正文上续东西，谈不上「看见一枚实时回答帧」。
    const empty = { role: 'assistant', content: '' }
    createStreamReducer(empty, createStreamState())(parseSseFrame('event: text\ndata: {"type":"text","content":""}\n\n'))
    expect('cache' in empty).toBe(false)
  })
})

describe('C · 读流层：告警有主，错误体不再是对象', () => {
  function byteFrames(frames) {
    const encoder = new TextEncoder()
    return frames.map(frame => encoder.encode(frame))
  }

  function fakeStream(frames) {
    const chunks = byteFrames(frames)
    let at = 0
    return {
      ok: true,
      status: 200,
      body: {
        getReader() {
          return {
            async read() {
              if (at >= chunks.length) return { done: true, value: undefined }
              const value = chunks[at]
              at += 1
              return { done: false, value }
            },
            async cancel() { /* 测试里没人取消也算通过 */ },
          }
        },
      },
    }
  }

  it('未认领事件一次一名：控制台与界面都不被同一枚名字刷屏', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const seen = []
    const msg = { role: 'assistant', content: '' }
    const result = await consumeSseStream(fakeStream([
      'event: mystery_one\ndata: {"content":"a"}\n\n',
      'event: mystery_one\ndata: {"content":"b"}\n\n',
      'event: mystery_two\ndata: {"content":"c"}\n\n',
      'event: done\ndata: {"type":"done"}\n\n',
    ]), msg, { onUnknownEvent: name => seen.push(name) })
    expect(result.ok).toBe(true)
    expect(seen).toEqual(['mystery_one', 'mystery_two'])
    expect(warn).toHaveBeenCalledTimes(2)
    warn.mockRestore()
  })

  it('sources 帧到位时界面能拿到回调（出处那张脸的触发源）', async () => {
    const got = []
    const msg = { role: 'assistant', content: '' }
    await consumeSseStream(fakeStream([
      canonicalFrame('sources', { sources: SOURCE_ROWS, hit_count: 1, unauthorized_count: 2 }, 1),
      'event: done\ndata: {"type":"done"}\n\n',
    ]), msg, { onSources: payload => got.push(payload) })
    expect(got).toHaveLength(1)
    expect(got[0].rows[0].filename).toBe('差旅费报销制度-2026.pdf')
    expect(got[0].hiddenCount).toBe(2)
  })

  it('缓存回调随 text 帧到达，不等整轮结束', async () => {
    const hits = []
    const msg = { role: 'assistant', content: '' }
    await consumeSseStream(fakeStream([
      'event: text\ndata: ' + JSON.stringify({
        type: 'text', content: '缓存答案。', cached: true, cache_generated_at: '2026-09-21T09:00:00Z', cache_note: '缓存结果 · 今天上午',
      }) + '\n\n',
      'event: done\ndata: {"type":"done"}\n\n',
    ]), msg, { onCache: cache => hits.push(cache) })
    expect(hits).toHaveLength(1)
    expect(hits[0].cached).toBe(true)
  })

  it('入队被拒的 {code,message} 错误体：句子走字典，界面拿不到 [object Object]', async () => {
    const response = {
      ok: false,
      status: 503,
      clone: () => ({
        json: async () => ({ detail: { code: 'queue_unavailable', message: '排队系统当前不可用。' } }),
      }),
    }
    const result = await consumeSseStream(response, { role: 'assistant', content: '' }, {})
    expect(result.ok).toBe(false)
    expect(result.stopped).toBe('http_error')
    expect(result.error).not.toContain('[object Object]')
    expect(result.error.length).toBeGreaterThan(4)
    // 归一成品整体带出：面板要画「没能排上队」那张脸，再归一次会洗掉 rawCode。
    expect(result.normalized).toMatchObject({ code: 'queue_unavailable', retryable: true })
    expect(typeof result.normalized.rawCode).toBe('string')
  })

  it('错误体压根不是 JSON 时按状态码归类，也不裸抛 HTTP 503 给界面', async () => {
    const response = { ok: false, status: 503, clone: () => ({ json: async () => { throw new Error('not json') } }) }
    const result = await consumeSseStream(response, { role: 'assistant', content: '' }, {})
    expect(result.ok).toBe(false)
    expect(result.error).not.toContain('[object Object]')
    expect(result.error).not.toBe('HTTP 503')
    expect(result.error).toBeTruthy()
  })
})
