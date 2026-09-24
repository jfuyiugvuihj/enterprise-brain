/**
 * R208 判据① + 判据② · 停表那一屏并列的两句不许自相矛盾，归属句必须出自字典
 *
 * 病灶（改前取证，本件基点 a218fa6）：
 *   lib/errcodes.js:49 给 authorization_unavailable 的原句写着「请稍后重试」，
 *   ChatPanel.vue:929/930 的停表脸写的是「界面已停止继续查询」+「停止查询后不会再有新读数」，
 *   而这一枚码正是 :847 停表名单里那一格 ⇒ 同一张脸并排两句真话：用户同时读到「再试试」
 *   和「不试了」。两句各自都不假，并排读就是自相矛盾。
 *
 * 本件不改 ChatPanel.vue（R48 排队等那一枚文件），两份真源在这里都当只读用：
 *   沿用 r202 乙3 的手法读面板源码抠结构，把字典句填进面板自己的模板，再判这一屏。
 *   钉子钉的是屏幕上真正会出现的那一行，不是测试自己臆造的一行。
 *
 * 甲组钉矛盾，乙组钉「零第二套文案」，两组各带一枚反向夹具证明判据本身不瞎：
 *   甲拿改动之前的旧原文当夹具（旧句上屏必红），乙拿「组件里硬写一句新话」当夹具。
 *   R198 丙组与 R202 甲5/甲6 那四枚反证钉在本件里一字不放宽，只加不减。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { ERROR_CODES, FALLBACK_MESSAGE, normalizeError } from './errcodes'

const panel = readFileSync(new URL('../components/ChatPanel.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const BACKTICK = String.fromCharCode(96)

/** 「等一会儿它自己会变好」这一类承诺：表已经停了，这句就是假话。 */
const RETRY_LATER = /稍后重试|稍后再试|请稍等|稍等|过一会儿|一会儿再|待会儿|回头再/
/** 归属句的领域词：这些字出现在面板自己的字面量里，就说明组件另写了一句解释。 */
const DENIAL_VOICE = /权限|部门|授权|停用/
/** 面板把归属句写在模板字符串里：这里要的只是它的定界符，本件不引组件、不起渲染器。 */
const LITERALS = new RegExp("'([^'\\n]*)'|" + BACKTICK + '([^' + BACKTICK + ']*)' + BACKTICK, 'g')
/** 字典句在 detail 模板里的插值位：normalizeError(error).message 那一个。 */
const DICT_SLOT = /\$\{result\.message\}/

/** 改动之前那一版原文（判据①的病灶本体，本件拿它当反向夹具）。 */
const BEFORE = '暂时确认不了你的数据权限范围，请稍后重试；仍不行的话请换带部门授权的账号或联系管理员。'

/** axios 错误的最小形状：这一发只用得到 response.status 与 response.data.detail。 */
function httpError(status, detail) {
  return {
    isAxiosError: true,
    response: { status, data: detail === undefined ? {} : { detail } },
    config: { url: '/queue/status/req-r208' },
    message: 'Request failed with status code ' + status,
  }
}

/** 停表名单里那几格的 code：就地从面板源码抠，测试不另抄一份名单。 */
function stopperCodes(source) {
  const from = source.indexOf('const QUEUE_POLL_STOPPERS')
  if (from < 0) throw new Error('停表名单不在 ChatPanel.vue 里了：本件取不到真源必须红')
  const block = source.slice(from, source.indexOf(']', from))
  return [...block.matchAll(/code:\s*'([a-z_]+)'/g)].map((match) => match[1])
}

/** 停表脸那一整块源码（headline 与 detail 都在里面）。 */
function stoppedFaceBlock(source) {
  const from = source.indexOf('function queuePollStoppedFace')
  if (from < 0) throw new Error('停表脸不在 ChatPanel.vue 里了：本件取不到真源必须红')
  return source.slice(from, source.indexOf('\n}', from) + 2)
}

/** 面板写在 detail 位上的那段模板正文（含插值位）。 */
function detailTemplate(source) {
  const block = stoppedFaceBlock(source)
  const at = block.indexOf('detail:')
  const open = block.indexOf(BACKTICK, at)
  const close = block.indexOf(BACKTICK, open + 1)
  return open >= 0 && close > open ? block.slice(open + 1, close) : ''
}

/**
 * 屏上真正会出现的那一行：headline 与 detail 逐字取自面板源码，
 * 再把传进来的那句字典原文填进它自己的插值位。
 */
function screenLine(source, dictMessage) {
  const block = stoppedFaceBlock(source)
  const headline = (/headline:\s*'([^']*)'/.exec(block) || [])[1] || ''
  return headline + ' ' + detailTemplate(source).replace(DICT_SLOT, dictMessage)
}

/** 名单里哪几格的字典句承诺了「等一会儿再试」：回 code 名单，空数组才算干净。 */
function retryLaterViolations(codes, dictionary) {
  const table = dictionary || ERROR_CODES
  return codes.filter((code) => RETRY_LATER.test((table[code] || {}).message || ''))
}

/** 那一块里所有「组件自己另写一句解释」的字面量：命中归属句的领域词才算。 */
function secondVoices(block) {
  return [...block.matchAll(LITERALS)]
    .map((match) => match[1] ?? match[2])
    .filter((text) => DENIAL_VOICE.test(text))
}

describe('甲 · 判据① 停表那一屏不许同时说「再试试」和「不试了」', () => {
  it('名单四格在档：本件读的是真名单，不多抄一枚不少抄一枚', () => {
    expect(stopperCodes(panel)).toEqual([
      'resource_not_found',
      'permission_denied',
      'authorization_unavailable',
      'authentication_required',
    ])
  })

  it('名单里每一格的字典句都不承诺「等一会儿再试」（真树零违规）', () => {
    expect(retryLaterViolations(stopperCodes(panel))).toEqual([])
  })

  it('这条判据不瞎：把「稍后再试」那一族塞进名单就当场点名', () => {
    const wide = ['rate_limited', 'queue_unavailable', 'model_unavailable', 'internal_error']
    expect(retryLaterViolations(wide)).toEqual(wide)
  })

  it('旧原文正是这条钉子要抓的东西（改前那一版上屏必红）', () => {
    expect(retryLaterViolations(['authorization_unavailable'], { authorization_unavailable: { message: BEFORE } }))
      .toEqual(['authorization_unavailable'])
    expect(screenLine(panel, BEFORE)).toMatch(RETRY_LATER)
    expect(screenLine(panel, ERROR_CODES.authorization_unavailable.message)).not.toMatch(RETRY_LATER)
  })

  it('新句仍说得出哪件事没做成、谁能修，且不脏屏', () => {
    const message = ERROR_CODES.authorization_unavailable.message
    expect(message).toContain('数据权限范围')
    expect(message).toContain('部门')
    expect(message).toContain('联系管理员')
    expect(message).not.toBe(FALLBACK_MESSAGE)
    expect(message).not.toMatch(/重试|再试/)
    expect(message).not.toMatch(/\b[a-z][a-z0-9]*(_[a-z0-9]+)+/)
  })

  it('retryable 仍为 true：「按原文再问一次」那颗按钮是重试这一层的唯一生产者', () => {
    expect(ERROR_CODES.authorization_unavailable.retryable).toBe(true)
    expect(normalizeError(httpError(403, 'authorization_unavailable')).retryable).toBe(true)
  })
})

describe('乙 · 判据② 屏上那句归属话必须出自字典（零第二套文案）', () => {
  it('停表脸的正文走 normalizeError → 字典插值位，面板不另起一句', () => {
    expect(stoppedFaceBlock(panel)).toMatch(/const result = normalizeError\(error\)/)
    expect(detailTemplate(panel)).toMatch(DICT_SLOT)
    expect(secondVoices(stoppedFaceBlock(panel))).toEqual([])
  })

  it('这条判据不瞎：组件里把归属句硬写成一句新话，当场点名（夹具）', () => {
    const real = stoppedFaceBlock(panel)
    const fixture = real.replace(
      "headline: '这一轮排队状态读不回来了，界面已停止继续查询',",
      "headline: '这一轮读不回来：暂时确认不了你的数据权限范围，请联系管理员补齐授权',",
    )
    expect(fixture).not.toBe(real)
    expect(secondVoices(fixture)).toEqual(
      ['这一轮读不回来：暂时确认不了你的数据权限范围，请联系管理员补齐授权'],
    )
  })

  it('填进模板的就是字典原文：四格每一格停下来的那一屏都整句含字典句', () => {
    for (const code of stopperCodes(panel)) {
      const message = ERROR_CODES[code].message
      const screen = screenLine(panel, message)
      expect(screen, code).toContain(message)
      expect(screen, code).toMatch(/停止|不再/)
      expect(screen, code).not.toMatch(/每 3 秒再读一次/)
    }
  })

  it('authentication_required 那句留着「再试」：它的前置动作在人身上，不在等待上', () => {
    const message = ERROR_CODES.authentication_required.message
    expect(message).toMatch(/再试/)
    expect(message).not.toMatch(RETRY_LATER)
  })
})
