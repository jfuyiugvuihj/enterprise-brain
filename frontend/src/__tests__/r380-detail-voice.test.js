/**
 * R380 判据②③④ · 人话位的第二形状收口：闸只有一道，中文一个不杀
 *
 * 病灶（本班现场取证，形状全表见 __tests__/r380-shape-table.test.js）：errcodes.js::resolveCode
 * 的散文尾那一档把「后端回来的那串文字」无条件当人话，于是未捕获 500 的
 * "Internal Server Error"、404 的 "Not Found"、nginx 502 的 "Bad Gateway" 直接印上人话位
 * （基点 285e265 的 :468-471 / :476 两道 return；摘码没摘明白的内嵌码那一支 :448-453 同罪）。
 * R281 已经把**信封形状**的英文原句挡住了（dictionaryClaims() 分流，原文改由 rawMessage 报告），
 * 本单不是新口径，是把同一条原则铺满第二个形状。
 *
 * 三条钉子各管一条判据：
 *   甲 反证钉① 把散文直出改回去 ⇒ 红。框架英文这一族逐枚点名（含 blob 下载链路）。
 * 乙 判据③   后端写给人的中文句子逐枚上屏对账（每一枚都带 app/** 位锚）⇒ 把闸开宽一寸就红。
 *   丙 判据②   防线唯一性：全仓非测试源码里「用文字形状当闸」的地方只准有一处，
 *              proseIsForHumans 只准有一个调用点，errorDetail 的函数体逐字钉死。
 *              ⇒ 把防线抄进 http.js（或任何第二处）当场红。
 *   丁 判据④   零新增错误码、零新增 reason、零新增文案：与基点逐字对账四张表的码与文案本体（R562 甲案：注释行不在这把尺上）。
 *   戊          errorDetail 这条薄通道拿到的仍是字典句；字典没话说时才退回面板场景文案。
 *   己          后端原文的第二条腿（R291 的折叠详情区）没被本单堵掉，也没多开第三条。
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { readdirSync } from 'node:fs'
import { join, dirname, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import {
  ERROR_CODES,
  FALLBACK_MESSAGE,
  LEGACY_ALIASES,
  PROSE_ALIASES,
  STATUS_CODES,
  blobErrorText,
  errorCodeLabel,
  formatError,
  normalizeError,
} from '../lib/errcodes'
import { errorDetail } from '../lib/http'
import { rawDetailOf } from '../components/ui/error-detail'

/** 与 r281 同一批反面角色，不另造 */
const FRAMEWORK_EN = 'Internal Server Error'
const BACKEND_EN = 'department must match the authenticated principal'

function httpError(status, data) {
  return {
    isAxiosError: true,
    message: 'Request failed with status code ' + status,
    response: { status, data },
  }
}

/** 人话位只准有中文：检测法照 r281 那把尺的写法反过来用（判据③要的是"必须给人看"） */
const HAS_CJK = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]/
const EN_SENTENCE = /[A-Za-z]{4,}\s+[A-Za-z]{4,}/

describe('甲 · 反证钉①：框架英文不许上人话位（把散文直出改回去必红）', () => {
  const FRAMEWORK_CASES = [
    ['500 Internal Server Error', 500, 'Internal Server Error', 'internal_error'],
    ['404 Not Found', 404, 'Not Found', 'resource_not_found'],
    ['405 Method Not Allowed', 405, 'Method Not Allowed', ''],
    ['429 Too Many Requests', 429, 'Too Many Requests', 'rate_limited'],
    ['502 Bad Gateway', 502, 'Bad Gateway', 'model_unavailable'],
    ['503 Service Unavailable', 503, 'Service Unavailable', 'model_unavailable'],
    ['504 Gateway Timeout', 504, 'Gateway Timeout', 'task_timeout'],
  ]
  for (const [label, status, english, code] of FRAMEWORK_CASES) {
    it(`裸串 detail：${label} ⇒ 屏上画字典那句，英文进 rawMessage`, () => {
      const result = normalizeError(httpError(status, { detail: english }))
      expect(result.code).toBe(code)
      const expectDict = code && STATUS_CODES[status] === code
      if (expectDict) {
        expect(result.message).toBe(ERROR_CODES[code].message)
      } else {
        expect(result.message).toBe(FALLBACK_MESSAGE)
      }
      expect(HAS_CJK.test(result.message), label + ' 屏上那句不含中文').toBe(true)
      expect(EN_SENTENCE.test(result.message), label + ' 屏上仍是英文整句').toBe(false)
      expect(result.rawMessage, label + ' 后端原文没进 rawMessage').toBe(english)
      expect(errorCodeLabel(result), label + ' 小字通道').toBe('')
      expect(result.retryable).toBe(Boolean(code && ERROR_CODES[code] && ERROR_CODES[code].retryable))
    })
  }

  it("纯文本错误体（text/plain 的 500，Starlette 未捕获异常就回这一种）同罪同判", () => {
    const result = normalizeError(httpError(500, FRAMEWORK_EN))
    expect(result.message).toBe(ERROR_CODES.internal_error.message)
    expect(result.rawMessage).toBe(FRAMEWORK_EN)
  })

  it("blob 下载链路（readBlobError 的纯函数内核）走的是同一道闸，不留第二条读路径", () => {
    const json = blobErrorText('{"detail":"Internal Server Error"}', 500)
    expect(json.message).toBe(ERROR_CODES.internal_error.message)
    expect(json.rawMessage).toBe(FRAMEWORK_EN)
    const text = blobErrorText("Bad Gateway", 502)
    expect(text.message).toBe(ERROR_CODES.model_unavailable.message)
    expect(text.rawMessage).toBe('')
  })

  it("单个英文词与数字 detail 也不算人话：Error / 500 一并退回字典", () => {
    expect(normalizeError(httpError(500, { detail: 'Error' })).message).toBe(ERROR_CODES.internal_error.message)
    expect(normalizeError(httpError(500, { detail: 500 })).message).toBe(ERROR_CODES.internal_error.message)
    expect(normalizeError(httpError(500, { detail: 'Error' })).rawMessage).toBe('Error')
  })

  it("内嵌码摘不动的那一句英文同样不许上屏：码名仍走「错误码：xxx」小字", () => {
    const result = normalizeError({ response: { status: 0, data: { detail: 'upstream refused (some_random_code)' } } })
    expect(result.message).toBe(FALLBACK_MESSAGE)
    expect(result.rawMessage).toBe('upstream refused')
    expect(errorCodeLabel(result)).toBe('错误码：some_random_code')
    expect(formatError({ response: { status: 0, data: { detail: 'upstream refused (some_random_code)' } } }))
      .toBe(FALLBACK_MESSAGE + '（错误码：some_random_code）')
  })
})
/**
 * 判据③的正面对手戏：后端真的写给客户看的句子，一枚都不许被闸掉。
 * 每一枚都带 app/** 位锚（现读源码逐枚抄下，不采信派工词）。把闸开宽一寸 —— 例如连含中文的
 * 串一起退回字典 —— 本组当场红。screen 那一格写的是改判之后屏上该出现的那句：绝大多数就是
 * 原句逐字直出，只有内嵌码那两枚例外（摘码是 R281 之前就定下的文案政策），例外照实写。
 */
describe('乙 · 判据③：后端写给人看的中文一句都不许被误杀', () => {
  const HUMAN_SENTENCES = [
    ['auth.py:75 登录失败', 401, '用户名或密码错误', '用户名或密码错误', 'authentication_required'],
    ['auth.py:130/:179 用户不存在', 404, '用户不存在', '用户不存在', 'resource_not_found'],
    ['auth.py:222 SSO 未启用', 401, 'SSO 未启用或请求未通过验证', 'SSO 未启用或请求未通过验证', 'authentication_required'],
    ['auth.py:225 缺身份头', 401, '缺少 SSO 身份头', '缺少 SSO 身份头', 'authentication_required'],
    ['auth.py:281 画像保存失败', 500, '画像保存失败', '画像保存失败', 'internal_error'],
    ['alerts.py:1020 非法操作符', 400, '非法操作符: ge', '非法操作符: ge', 'validation_error'],
    ['authorization.py:23 权限不足 + 括号里的原因码', 403, '权限不足: users:manage (clearance_insufficient)', '权限不足: users:manage', 'permission_denied'],
    ['chat.py 那类正文内嵌枚举码', 500, '本轮未产出任何结论（error_code=no_answer_produced），请重试或补充数据范围。', '__DICT:no_answer_produced', 'no_answer_produced'],
    ['中英混排（状态在册 500）', 500, 'model 已降级，请改用本地模型', 'model 已降级，请改用本地模型', 'internal_error'],
    ['中英混排（状态未在册 507）', 507, 'upstream 无响应', 'upstream 无响应', ''],
    ['带全角引号的中文句', 500, '「部门」这一格不能为空', '「部门」这一格不能为空', 'internal_error'],
  ]
  for (const [anchor, status, chinese, screen, code] of HUMAN_SENTENCES) {
    const expectScreen = screen.startsWith('__DICT:')
      ? ERROR_CODES[screen.slice(7)].message
      : screen
    it(`${anchor} ⇒ 屏上仍是这句中文`, () => {
      const result = normalizeError(httpError(status, { detail: chinese }))
      expect(result.message, anchor + ' 这句中文被闸掉了').toBe(expectScreen)
      expect(HAS_CJK.test(result.message), anchor + ' 屏上那句不含中文').toBe(true)
      expect(result.code, anchor + ' 归类码').toBe(code)
      expect(result.rawMessage, anchor + ' 中文不该占原文出口').toBe('')
    })
  }

  it('common/auth.py:603-744 那批中文句（走 auth.py:120/:144/:198 的 detail=msg）一枚不少', () => {
    const STORE_SENTENCES = [
      "用户名和密码不能为空",
      "密码至少 6 位",
      "非法角色: superuser",
      "用户 'zhangsan' 已存在",
      "用户名不能为空",
      "原密码错误",
      "新密码至少 6 位",
      "SSO 用户同步失败: connection refused",
    ]
    for (const sentence of STORE_SENTENCES) {
      const result = normalizeError(httpError(400, { detail: sentence }))
      expect(result.message, sentence).toBe(sentence)
      expect(result.code).toBe('validation_error')
      expect(result.rawMessage).toBe('')
    }
  })

  it('未登记码名那一档一分未动：兜底句 + 「错误码：xxx」小字，rawMessage 不背这个责任', () => {
    const result = normalizeError(httpError(500, { detail: 'storage_backend_down' }))
    expect(result.message).toBe(FALLBACK_MESSAGE)
    expect(errorCodeLabel(result)).toBe('错误码：storage_backend_down')
    expect(result.rawMessage).toBe('')
  })

  it('PROSE_ALIASES 在册的中文散文仍出字典句：闸口开在查表之后，查表顺序一分未改', () => {
    const proseKeys = Object.keys(PROSE_ALIASES)
    expect(proseKeys.length).toBeGreaterThan(0)
    for (const prose of proseKeys) {
      const result = normalizeError(httpError(401, { detail: prose }))
      expect(result.code, prose).toBe(PROSE_ALIASES[prose].code)
      expect(result.message, prose).toBe(ERROR_CODES[PROSE_ALIASES[prose].code].message)
      expect(result.rawMessage, prose).toBe('')
    }
  })
})


/** src 根：丙丁两组都拿源码文本当被测物（测试件自己的夹具不算第二道闸） */
const SRC_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')

const BACKSLASH = String.fromCharCode(92)
/** 匹配「用 \uXXXX-\uYYYY 字符类当判据」的那一行 —— 防英文的闸长这样 */
const CJK_GUARD = new RegExp(BACKSLASH + 'u[0-9a-f]{4}' + BACKSLASH + '-', 'i')

/** 与 no-bare-code.test.js 同一套扫描范围：__tests__ 与 *.test.js 不进扫描 */
function collectSources(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === '__tests__' || entry.name === 'node_modules') continue
      collectSources(full, out)
    } else if (/\.(js|vue|css)$/.test(entry.name) && !/\.(test|spec)\.js$/.test(entry.name)) {
      out.push(full)
    }
  }
  return out
}

function readSource(repoRelative) {
  return readFileSync(join(SRC_ROOT, ...repoRelative.split('/')), 'utf8').replace(/\r\n/g, '\n')
}

describe('丙 · 判据②：防英文的地方只有一处（形状钉，抄第二道防线即红）', () => {
  it('全仓非测试源码里 CJK 字符类只有一枚，而且就在 lib/errcodes.js 的散文闸上', () => {
    const found = []
    for (const file of collectSources(SRC_ROOT)) {
      const text = readFileSync(file, 'utf8').replace(/\r\n/g, '\n')
      text.split('\n').forEach((line, index) => {
        if (CJK_GUARD.test(line)) found.push(relative(SRC_ROOT, file).split(sep).join('/') + ':' + (index + 1))
      })
    }
    expect(found.length, '防英文的闸不止一枚：' + JSON.stringify(found)).toBe(1)
    expect(found[0].split(':')[0]).toBe('lib/errcodes.js')
  })

  it('proseIsForHumans 全仓只有一个调用点：散文的人话位裁决不发生第二次', () => {
    const lines = readSource('lib/errcodes.js').split('\n').filter((line) => {
      if (!/proseIsForHumans\(/.test(line)) return false
      if (/^\s*(\/\/|\*|\/\*)/.test(line)) return false
      return !/^function proseIsForHumans\(/.test(line)
    })
    expect(lines.map((line) => line.trim())).toEqual(['const humanVoice = proseIsForHumans(voice)'])
  })

  it('这道闸不许被 export 出去：别的模块要用它，就得先把自己变成第二处防线', () => {
    expect(/^export function proseIsForHumans/m.test(readSource('lib/errcodes.js'))).toBe(false)
    for (const consumer of ['lib/http.js', 'lib/alerts.js', 'lib/notifications.js', 'lib/dashboard.js']) {
      const codeLines = readSource(consumer)
        .split('\n')
        .filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line))
        .join('\n')
      expect(/proseIsForHumans\s*\(/.test(codeLines), consumer + ' 里冒出了第二道闸').toBe(false)
    }
  })

  it('lib/http.js::errorDetail 函数体逐字钉死：这里长出第二处过滤即红', () => {
    const text = readSource('lib/http.js')
    const start = text.indexOf('export function errorDetail(')
    if (start < 0) throw new Error('errorDetail 不见了，本枚形状钉落空')
    const body = text.slice(start, text.indexOf('\n}', start) + 2)
    expect(body).toBe([
      "export function errorDetail(err, fallback = '请求失败') {",
      '  const message = normalizeError(err).message',
      '  return message === FALLBACK_MESSAGE ? (fallback || FALLBACK_MESSAGE) : message',
      '}',
    ].join('\n'))
    expect(/[.]test[(]|[.]replace[(]|[.]match[(]|RegExp|[.]includes[(]/.test(body), 'errorDetail 里长出了过滤').toBe(false)
  })
})

describe('丁 · 判据④：零新增错误码、零新增 reason、零新增文案', () => {
  /** 本单基点（派工词指定的树基点）。读法照仓里规矩：git show 拿对象，绝不读工作树来比。 */
  const BASE_REF = '285e265'
  const BASE_PATH = 'frontend/src/lib/errcodes.js'

  function showAtRef(ref, repoPath) {
    let text
    try {
      text = execFileSync('git', ['show', ref + ':' + repoPath], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
    } catch (cause) {
      throw new Error('读不到 ' + ref + ':' + repoPath + '（' + cause.message + '）。判据④的账不许降级，这里必须红。')
    }
    return text.replace(/\r\n/g, '\n')
  }

  /**
   * 字典区域 = 四张表 + 兜底句，从枚数注释起、到 CODE_PATTERN 止。判据④的账是这一段里的码体：
   * 原来这一段连每一枚位锚注释都冻着。R562 甲案把这把尺收到码体与文案：那一族注释记的正是后端行号，
   * 剥掉注释之后与基点逐字相同；扩字典的那一单得带着自己的判据来改这一格。
   * 而 R562 这枚单子的本职就是去改那些行号 —— 冻住它们等于判「行号不许说真话」。码名与文案照旧一字不许动。
   */
  /**
   * 剥掉注释只剩码体：块注释整段摘掉，行注释按「行首、或不被冒号顶着」的那一道斜杠切，再削行尾空白。
   * 这一段里字符串不含 `//`（R562 现取 245 行逐枚数过：行尾挂注释的只有 5 行，全是 `// …policy.py:…` 那一种），
   * 所以这里不必上完整的字符串状态机；真长出带斜杠的文案，切多=码体看着变了=本组红，不会假绿。
   */
  function codeOnly(text) {
    return text
      .replace(/\/\*[\s\S]*?\*\//g, ' ')
      .split('\n')
      .map(line => line.replace(/(^|[^:])\/\/.*$/, '$1').trimEnd())
      .filter(line => line.trim() !== '')
      .join('\n')
  }

  /** 判据④真正冻的东西：码名、别名、散文、状态归类、文案本体。R562 甲案把「连注释一起冻」收到这一层。 */
  function dictionaryBody(text) {
    return codeOnly(dictionaryRegion(text))
  }

  function dictionaryRegion(text) {
    const start = text.indexOf('/** 与后端封闭枚举一一对应的键')
    const end = text.indexOf('const CODE_PATTERN')
    if (start < 0 || end < 0 || end <= start) throw new Error('字典区域认不出来，本枚对账钉落空')
    return text.slice(start, end)
  }

  it('四张表的码与文案本体逐字未动（位锚注释按新事实改口不在这把尺上 —— R562 甲案）', () => {
    const base = showAtRef(BASE_REF, BASE_PATH)
    const now = readSource('lib/errcodes.js')
    expect(dictionaryRegion(base).length, '基点那一份的字典区域读成空段：尺子落空，本组不许绿').toBeGreaterThan(1000)
    expect(dictionaryBody(now), '四张表的码名／别名／散文／状态归类／文案与基点不同：判据④是零新增，要扩字典得带着自己的判据来改这一格').toBe(dictionaryBody(base))
  })

  it('这把尺两头都有牙：注释层剥得干净（否则冻结是假的），码体层改一个字就露馅（否则尺子量不到东西）', () => {
    const region = dictionaryRegion(readSource('lib/errcodes.js'))
    expect(codeOnly(region), '剥完注释还留着位锚注释的痕迹：这一把尺没剥干净，「注释可以改口」那句话是空的').not.toMatch(/policy\.py:|evidence\.py:|contracts\.py:|sessions\.js:/)
    const mutated = region.replace('要找的内容不存在或已被移除。', '要找的内容不存在或已被移除。X')
    expect(mutated, '内存里那一改没落进这段区域：尺子量的不是这段文本').not.toBe(region)
    expect(codeOnly(mutated), '改了一枚文案，剥完注释却看不出差别：码体根本不在这把尺上，冻结是假的').not.toBe(codeOnly(region))
  })

  it('reason 那一层也没有新词：STATUS_CODES 的取值全部落在封闭枚举里', () => {
    for (const code of Object.values(STATUS_CODES)) {
      expect(Object.prototype.hasOwnProperty.call(ERROR_CODES, code), code).toBe(true)
    }
  })

  it('被闸下来的那一族不产生任何新说法：屏上只可能是字典句或兜底句', () => {
    const sentences = new Set([
      ...Object.values(ERROR_CODES).map((entry) => entry.message),
      ...Object.values(LEGACY_ALIASES).map((entry) => entry.message).filter(Boolean),
      FALLBACK_MESSAGE,
    ])
    const killed = [
      'Internal Server Error', 'Not Found', 'Too Many Requests', 'Bad Gateway',
      'Service Unavailable', 'Gateway Timeout', 'Something went wrong', 'Insufficient Storage',
    ]
    for (const english of killed) {
      for (const status of [400, 404, 429, 500, 502, 503, 504, 507, 0]) {
        const result = normalizeError(httpError(status, { detail: english }))
        expect(sentences.has(result.message), status + ' ' + english + ' ⇒ ' + result.message).toBe(true)
      }
    }
  })
})

describe('戊 · errorDetail 这条薄通道：字典句优先，字典没话说才退面板场景文案', () => {
  const PANEL = '面板场景文案'
  const DICT_EN = [
    [500, 'Internal Server Error'],
    [404, 'Not Found'],
    [405, 'Method Not Allowed'],
    [429, 'Too Many Requests'],
    [502, 'Bad Gateway'],
    [503, 'Service Unavailable'],
    [504, 'Gateway Timeout'],
    [507, 'Insufficient Storage'],
    [0, 'Internal Server Error'],
  ]

  it('500 + 框架英文：面板拿到字典那句，既不是英文原话也不是面板自己的文案', () => {
    const err = httpError(500, { detail: FRAMEWORK_EN })
    expect(errorDetail(err, PANEL)).toBe(ERROR_CODES.internal_error.message)
    expect(errorDetail(err, PANEL)).not.toContain(FRAMEWORK_EN)
  })

  it('状态也归不下的英文（507 / status 0）：退面板那句，英文一个字都不上屏', () => {
    expect(errorDetail(httpError(507, { detail: 'Insufficient Storage' }), PANEL)).toBe(PANEL)
    expect(errorDetail(httpError(507, { detail: 'Insufficient Storage' }))).toBe('请求失败')
    for (const [status, english] of DICT_EN) {
      const text = errorDetail(httpError(status, { detail: english }), PANEL)
      expect(EN_SENTENCE.test(text), `${status} ${english} ⇒ 屏上仍是英文整句：${text}`).toBe(false)
      expect(HAS_CJK.test(text), `${status} ${english} ⇒ 屏上不含中文：${text}`).toBe(true)
    }
  })

  it('后端写好的中文（401 登录失败）：面板拿到的还是那句中文，没有被换成字典通用句', () => {
    expect(errorDetail(httpError(401, { detail: '用户名或密码错误' }), PANEL)).toBe('用户名或密码错误')
  })
});

describe('己 · 后端原文的第二条腿（R291 折叠详情区）没有被本单堵掉，也没有开第三条', () => {
  it('500 裸串英文被闸下人话位之后，运维仍然拿得到那句原文', () => {
    const err = httpError(500, { detail: FRAMEWORK_EN })
    const shown = errorDetail(err, '面板场景文案')
    expect(shown).toBe(ERROR_CODES.internal_error.message)
    expect(rawDetailOf(err, { shown })).toBe(FRAMEWORK_EN)
    expect(rawDetailOf(err)).toBe(FRAMEWORK_EN)
  })

  it('越权面那一族照 R291 口径③沉默：403 的框架英文既不上人话位，也不进详情区', () => {
    const err = httpError(403, { detail: 'Forbidden' })
    expect(errorDetail(err, '面板场景文案')).toBe(ERROR_CODES.permission_denied.message)
    expect(rawDetailOf(err, { shown: ERROR_CODES.permission_denied.message })).toBe('')
  })

  it('字典收不下那枚码的一发（R281 判据③）：人话位与详情区不同字重复', () => {
    const err = httpError(500, { detail: { code: 'mystery_backend_code', message: BACKEND_EN } })
    const shown = errorDetail(err, '面板场景文案')
    expect(shown).toBe(BACKEND_EN)
    expect(rawDetailOf(err, { shown })).toBe('')
  })

  it('中文人话那一发没有原文可报告：详情区这一块不渲染，也不编一句「后端没给原文」', () => {
    const err = httpError(401, { detail: '用户名或密码错误' })
    expect(errorDetail(err, '面板场景文案')).toBe('用户名或密码错误')
    expect(rawDetailOf(err, { shown: '用户名或密码错误' })).toBe('')
  })
})

