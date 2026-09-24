/**
 * R208 判据① · 停表名单的别名覆盖面：逐枚登记 + 两本账对平，不许拿「今天发不出」当安全依据
 *
 * 要收的账（R202 施工方「只报不动」第二笔）：ChatPanel.vue:847 那一格登记的是
 * (403, authorization_unavailable)，而判码走 errorCodeOf —— LEGACY_ALIASES 把
 * app/common/policy.py 的 resource_scope_missing / resource_scope_invalid 折到这枚码上，
 * 于是这两枚一旦出现在那一发应答里，轮询就被叫停。R202 报的是「今天 /queue/status 发不出
 * 这两枚」，本件按判据不采信这句话：可达性看调用点，不看今天的报文。
 *
 * 三组账，两份真源都只读（ChatPanel.vue 一行不改，R48 排队等那一枚文件）：
 *   甲 覆盖面 —— 别名表 × 名单格 的交叉集逐枚在册，多一枚即红；顺手补上 R202 没报的第二笔
 *       （permission_denied 那一格同样被 department_scope_denied / clearance_insufficient 折中）；
 *   乙 收窄用的判据 isAliasFoldedCode —— 别名折入回 true、队列那五枚本尊回 false，
 *       并钉住「不按是不是本尊取反」：散文折入与状态兜底那两族今天照旧叫停，本件不改判；
 *   丙 调用点 —— 队列那条腿的五枚拒绝出口逐枚从 app/api/v1/chat.py 抠出来，四枚别名的
 *       emitter 逐枚与后端登记册 tests/test_error_code_vocabulary.py 对平，policy.py 里
 *       那几行 _decision(False, ...) 的 raise 处逐枚数得出来。这才是「谁可能发出这个 code」。
 * 真源一律 git show HEAD:<path>，与本目录 errcodes.test.js:38-52 同一口径：工作树可以停在
 * 分支点，也可以被同机另一枚 Agent 弄脏，object DB 里那一份才是本件钉的那一份。
 */
import { execFileSync } from 'node:child_process'
import { describe, expect, it } from 'vitest'
import {
  LEGACY_ALIASES,
  STATUS_CODES,
  errorCodeOf,
  isAliasFoldedCode,
  normalizeError,
} from './errcodes'

function show(path) {
  let text
  try {
    text = execFileSync('git', ['show', 'HEAD:' + path], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
  } catch (cause) {
    throw new Error('读不到真源 HEAD:' + path + '（git show 失败：' + cause.message + '）')
  }
  if (typeof text !== 'string' || !text.trim()) throw new Error('git show HEAD:' + path + ' 返回空内容')
  return text.replace(/\r\n/g, '\n')
}

const panel = show('frontend/src/components/ChatPanel.vue')
const chatRoute = show('app/api/v1/chat.py')
const vocabulary = show('tests/test_error_code_vocabulary.py')
const gateway = show('app/main.py')
const policy = show('app/common/policy.py')

/** 停表名单里那几格的 code：就地从面板源码抠，测试不另抄一份名单。 */
function stopperCodes(source) {
  const from = source.indexOf('const QUEUE_POLL_STOPPERS')
  if (from < 0) throw new Error('停表名单不在 ChatPanel.vue 里了：本件取不到真源必须红')
  const block = source.slice(from, source.indexOf(']', from))
  return [...block.matchAll(/code:\s*'([a-z_]+)'/g)].map((match) => match[1])
}

const CELLS = stopperCodes(panel)
const CELL_SET = new Set(CELLS)

/** R208 立案时钉住的交叉集：四枚，一枚不多一枚不少。 */
const FOLDED_INTO_CELLS = [
  'clearance_insufficient',
  'department_scope_denied',
  'resource_scope_invalid',
  'resource_scope_missing',
]

/** 别名表里有哪些码名折进了名单某一格。 */
function foldedIntoCells(table, cells) {
  return Object.keys(table).filter((name) => cells.has(table[name].code)).sort()
}

/** 抠后端登记册：枚枚都要有 emitter 与 folds_into，解析不出来就抛，不许退化成空对账。 */
function parseBareCodeRegister(src) {
  const start = src.indexOf('BARE_CODES_OUTSIDE_THE_ENUM = {')
  if (start < 0) throw new Error('后端登记册 BARE_CODES_OUTSIDE_THE_ENUM 不在了：本件取不到真源必须红')
  const register = {}
  for (const entry of src.slice(start).matchAll(/^ {4}"([a-z_]+)": \{([\s\S]*?)^ {4}\},$/gm)) {
    const name = entry[1]
    const inner = entry[2]
    const emitter = /"emitter":\s*"([^"]+)"/.exec(inner)
    const folds = /"folds_into":\s*"([^"]+)"/.exec(inner)
    if (!emitter || !folds) {
      throw new Error('登记册 ' + name + ' 抠不到 emitter/folds_into：那边格式变了，这里的解析要跟着改')
    }
    const others = /"also_emitted_by":\s*\[([^\]]*)\]/.exec(inner)
    register[name] = {
      emitter: emitter[1],
      foldsInto: folds[1],
      alsoEmittedBy: others ? [...others[1].matchAll(/"([^"]+)"/g)].map((item) => item[1]) : [],
    }
  }
  if (!Object.keys(register).length) throw new Error('登记册解析出零枚：本件成了假绿，必须红')
  return register
}

/** 队列那条腿的拒绝出口：逐枚 status + detail，出处只在 _authorize_queue_task 函数体内。 */
function queueOutlets(source) {
  const from = source.indexOf('def _authorize_queue_task(')
  if (from < 0) throw new Error('抠不到 _authorize_queue_task：本件取不到真源必须红')
  const body = source.slice(from, source.indexOf('# ==================== PostgreSQL', from))
  return [...body.matchAll(/_refused\((\d+), "([a-z_]+)"\)/g)].map((item) => item[1] + ' ' + item[2])
}

function httpError(status, detail) {
  return {
    isAxiosError: true,
    response: { status, data: detail === undefined ? {} : { detail } },
    config: { url: '/queue/status/req-r208' },
    message: 'Request failed with status code ' + status,
  }
}

describe('甲 · R208 判据① 覆盖面：别名表 × 停表名单的交叉集', () => {
  it('交叉集逐枚在册：四枚，多一枚即红', () => {
    expect(CELLS).toEqual([
      'resource_not_found',
      'permission_denied',
      'authorization_unavailable',
      'authentication_required',
    ])
    expect(foldedIntoCells(LEGACY_ALIASES, CELL_SET)).toEqual(FOLDED_INTO_CELLS)
  })

  it('R202 报的那一笔：两枚 policy 码折进 authorization_unavailable 那一格', () => {
    for (const raw of ['resource_scope_missing', 'resource_scope_invalid']) {
      expect(LEGACY_ALIASES[raw].code, raw).toBe('authorization_unavailable')
      expect(CELL_SET.has(errorCodeOf(httpError(403, raw))), raw + ' 打得中名单那一格').toBe(true)
    }
  })

  it('R202 没报的第二笔：permission_denied 那一格同样被两枚 policy 码折中', () => {
    for (const raw of ['department_scope_denied', 'clearance_insufficient']) {
      expect(LEGACY_ALIASES[raw].code, raw).toBe('permission_denied')
      expect(CELL_SET.has(errorCodeOf(httpError(403, raw))), raw + ' 打得中名单那一格').toBe(true)
    }
  })

  it('要收的是停表权，不是归一：这一族的折叠还得留着分「判不了」与「没权限」', () => {
    const missing = httpError(403, 'resource_scope_missing')
    expect(errorCodeOf(missing)).not.toBe('permission_denied')
    expect(normalizeError(missing).message).toContain('判断不了你能不能看')
  })

  it('这枚账不是瞎的：夹具里多一枚别名折进名单，当场点名', () => {
    const widened = { ...LEGACY_ALIASES, zzz_scope_unlisted: { code: 'authentication_required' } }
    expect(foldedIntoCells(widened, CELL_SET)).toEqual([...FOLDED_INTO_CELLS, 'zzz_scope_unlisted'].sort())
  })
})

describe('乙 · 收窄用的判据 isAliasFoldedCode：只认 LEGACY 这一道折痕', () => {
  it('别名折入回 true：裸码名与信封两种形状都认得这道折痕', () => {
    for (const raw of FOLDED_INTO_CELLS) {
      expect(normalizeError(httpError(403, raw)).rawCode, raw).toBe(raw)
      expect(isAliasFoldedCode(httpError(403, raw)), raw).toBe(true)
      expect(isAliasFoldedCode(httpError(403, { code: raw, message: '后端原句', retryable: false })), raw).toBe(true)
    }
  })

  it('队列那五枚出口是本尊，回 false：收窄那一行不许把终止性判定一起放走', () => {
    for (const outlet of queueOutlets(chatRoute)) {
      const parts = outlet.split(' ')
      expect(isAliasFoldedCode(httpError(Number(parts[0]), parts[1])), outlet).toBe(false)
    }
    expect(isAliasFoldedCode(httpError(403, 'authorization_unavailable'))).toBe(false)
    expect(isAliasFoldedCode(httpError(403, 'permission_denied'))).toBe(false)
  })

  it('网络错误与超时本来就不在名单门口：它们连 code 都没有', () => {
    const offline = { isAxiosError: true, code: 'ERR_NETWORK', message: 'Network Error', request: {}, config: {} }
    expect(errorCodeOf(offline)).toBe('')
    expect(isAliasFoldedCode(offline)).toBe(false)
  })

  it('不按「是不是本尊」取反：鉴权门今天吐枚举码，散文那条只是野外兜底', () => {
    expect(gateway).toMatch(/status_code=401, content=\{"detail": "authentication_required"\}/)
    expect(gateway).not.toMatch(/请先登录/)
    expect(errorCodeOf(httpError(401, '请先登录'))).toBe('authentication_required')
    expect(isAliasFoldedCode(httpError(401, '请先登录')), 'PROSE_ALIASES 折进来的不是 LEGACY 别名').toBe(false)
    expect(isAliasFoldedCode(httpError(403, '账号不可用')), '同上：散文表另成一族').toBe(false)
  })

  it('记第三笔不判：403 带未登记码时按状态兜底成 permission_denied，今天也叫得停表', () => {
    const unknown = httpError(403, 'a_code_nobody_registered_yet')
    expect(STATUS_CODES[403]).toBe('permission_denied')
    expect(errorCodeOf(unknown)).toBe(STATUS_CODES[403])
    expect(CELL_SET.has(errorCodeOf(unknown)), '这一枚打中的是 permission_denied 那一格').toBe(true)
    expect(isAliasFoldedCode(unknown), '它不是 LEGACY 别名折入：收窄那一行不许顺手把它当别名处理').toBe(false)
  })
})

describe('丙 · 调用点：谁可能发出这一格的 code（全清单，不靠报文运气）', () => {
  it('队列那条腿五枚拒绝出口逐枚在源码里，且全是枚举码本尊', () => {
    expect(queueOutlets(chatRoute)).toEqual([
      '401 authentication_required',
      '404 resource_not_found',
      '403 authorization_unavailable',
      '403 authorization_unavailable',
      '403 permission_denied',
    ])
  })

  it('这一发只过 _authorize_queue_task 一道闸：路由体里没有 policy 判定那一腿', () => {
    const from = chatRoute.indexOf('@router.get("/queue/status/{request_id}")')
    const body = chatRoute.slice(from, chatRoute.indexOf('@router.', from + 10))
    expect(from).toBeGreaterThan(-1)
    expect(body).toMatch(/_authorize_queue_task\(request, queue, request_id, ACTION_VIEW\)/)
    expect(body).not.toMatch(/authorization_decision\(/)
    // 这一枚钉的是「今天为什么还没炸」，它不是安全依据：安全依据只能是乙组那枚谓词进名单。
  })

  it('policy.py 那两枚原因码的判定处逐枚数得出来（origin 不在注释里）', () => {
    expect([...policy.matchAll(/_decision\(False, "resource_scope_missing"\)/g)]).toHaveLength(4)
    expect([...policy.matchAll(/_decision\(False, "resource_scope_invalid"\)/g)]).toHaveLength(1)
    expect(policy).toMatch(/def authorization_decision\(/)
  })

  it('后端登记册与前端的交叉集是同一本账（双向对平）', () => {
    const register = parseBareCodeRegister(vocabulary)
    expect(Object.keys(register).length).toBeGreaterThanOrEqual(17)
    const fromBackend = Object.keys(register).filter((name) => CELL_SET.has(register[name].foldsInto)).sort()
    expect(fromBackend).toEqual(FOLDED_INTO_CELLS)
    expect(fromBackend).toEqual(foldedIntoCells(LEGACY_ALIASES, CELL_SET))
    for (const name of FOLDED_INTO_CELLS) {
      expect(register[name].emitter, name).toBe('app/common/policy.py::authorization_decision')
      expect(register[name].emitter, name + ' 必须是位锚不是裸行号').toMatch(/\.py::/)
    }
  })

  it('解析器不是瞎的：登记表没了或字段缺了都抛（夹具）', () => {
    expect(() => parseBareCodeRegister('x = {}\n')).toThrow()
    expect(() => parseBareCodeRegister('BARE_CODES_OUTSIDE_THE_ENUM = {\n    "zz": {\n        "why": "缺字段",\n    },\n}\n')).toThrow()
  })
})
