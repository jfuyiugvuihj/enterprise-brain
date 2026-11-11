/**
 * R368 · 「重新加载」那颗按钮的取值只出自一本账（lib/alerts.js::readFailureView）
 *
 * 病灶（一手取证，读的是本树 b291324 的字节）：lib/alerts.js::readFailureView 的最后一行 return 对
 * **所有**既非 unauthorized 也非 denied 的失败硬编 retryable: true，而同一仓的字典 lib/errcodes.js
 * 给 storage_unavailable 判的是 false，并在 :99-107 写着三条理由。两本账各说各话，而屏幕赢在那一行
 * 硬编上。R359（并树 4382443）之后 GET /alerts 在生产无库时**真的**回 503 storage_unavailable ——
 * 于是告警面板会在一枚「必须有人把迁移跑完」才变得了的故障上挂「重新加载」，那是指错路，不是体验。
 *
 * 口径交代在这里（本单不改 API 语义，所以不往 docs/ 追加契约节）：
 *  甲 判据① 字典认得的码 ⇒ 屏上那一格跟着字典走。字典只有 lib/errcodes.js 那三张表
 *     （ERROR_CODES / LEGACY_ALIASES / PROSE_ALIASES），取值走现成的 isRetryable；「字典认不认得
 *     这一发」走新出口的 dictionaryAdjudicatesRetry。alerts.js 里一个错误码名字都不抄。
 *  乙 判据② 字典没说过的那一族仍然给重试：没有码 / 后端回了收不下的码名 / 只按 HTTP 状态兜底归类
 *     / 422 校验数组 / 断网 / 裸 Error / 结构不对（shapeFailureView 那一支逐字不动）。
 *     这一组同时是「把修复做成一律 false」那枚反方向假绿的绊线。
 *  丙 判据③ internal_error 的句子与 flag 不再互相打脸。裁定：改文案、flag 保持 false（三条理由写在
 *     errcodes.js 那一格上面），本件把它升格成全称律 —— 三张表里凡判 false 的那一格，句子都不许承诺
 *     「稍后重试」那一族字样；正则逐字沿用 r208-dictionary-voice.test.js:26。
 *  丁 判据④ 三枚点名用例逐枚落屏：insight-alerts.test.js 那三枚钉（frontend/src/components/__tests__/insight-alerts.test.js:819 / :823 / :830）的改口读数
 *     以本件的断言为准，frontend/src/components/__tests__/insight-alerts.test.js:823 那枚按判据②保持 true 不动。
 *  戊 判据⑤ 字典注释里引用的后端行号当场对账：两把尺一律从 git show HEAD:app/agents/evidence.py 现读推导 —— 
 *     说集合的那一枚对 _RETRIABLE_CODES 的定义行，说「retryable=error_code in _RETRIABLE_CODES」那一句的每一枚对各自的出口行。
 *     R562 换锚的理由：旧尺只有定义行一把，而字典注释里两档都有，拿定义行量出口就是拿错尺（钉的是尺子形状，不是某个数字）。
 *
 * 读后端口径一律 git show HEAD，绝不 readFileSync 工作树的 app/**：那条教训记在
 * r316-users-contract.test.js:52-59（工作树那一版可能与判据所依据的版本不同，读它就是永远绿的假绿）。
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { ERROR_CODES, LEGACY_ALIASES, PROSE_ALIASES, dictionaryAdjudicatesRetry, errorText, isRetryable } from '../errcodes'
import { readFailureView, shapeFailureView } from '../alerts'

const ARGS = { deniedTitle: '这个账号没有查看告警的权限', failedTitle: '告警列表没能读出来' }
/** 给人看的句子里不许夹 snake_case 码名（V6 裸码闸门同一条口径）。 */
const SNAKE = /[a-z][a-z0-9]*_[a-z0-9_]+/
/** 「等一会儿它自己会变好」那一族口头邀请：正则逐字沿用 r208-dictionary-voice.test.js:26。 */
const RETRY_LATER = /稍后重试|稍后再试|请稍等|稍等|过一会儿|一会儿再|待会儿|回头再/

/** 形状 1：detail 里就是一枚码名或散文（app/api/v1/artifacts.py:120 那一类 raise HTTPException(500, detail=码名)）。 */
function httpError(status, detail) {
  return {
    isAxiosError: true,
    message: 'Request failed with status code ' + status,
    response: { status, data: { detail } },
  }
}

/** 形状 2：ErrorEnvelope。本件只用到 code 与可选的 retryable 两格。 */
function envelopeError(status, detail) {
  return httpError(status, detail)
}

/** 别名/散文那一格的生效取值：自己写了就用自己那格，没写才回落到目标码（与 resolveCode 同一读法）。 */
function effectiveVerdict(entry) {
  return typeof entry.retryable === 'boolean' ? entry.retryable : ERROR_CODES[entry.code].retryable
}

/** 三张表摊平成 [名字, 句子, 生效 flag]：全称律扫这张清单，不点名任何一枚码。 */
function dictionarySentences() {
  const rows = []
  for (const code of Object.keys(ERROR_CODES)) {
    rows.push([code, ERROR_CODES[code].message, ERROR_CODES[code].retryable])
  }
  for (const legacy of Object.keys(LEGACY_ALIASES)) {
    const entry = LEGACY_ALIASES[legacy]
    rows.push([legacy, entry.message || ERROR_CODES[entry.code].message, effectiveVerdict(entry)])
  }
  for (const prose of Object.keys(PROSE_ALIASES)) {
    const entry = PROSE_ALIASES[prose]
    rows.push([prose, entry.message || ERROR_CODES[entry.code].message, effectiveVerdict(entry)])
  }
  return rows
}

const sourceOf = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')

/** 只留代码体：错误码的名字当然允许活在注释与字典里，本件要扫的是屏幕那一侧的代码。 */
function codeOnly(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .split('\n')
    .filter(line => !/^\s*\/\//.test(line))
    .join('\n')
}

/** git 对象现读：判据⑤对面那半本账只能从这里拿。 */
function showAtRef(path, ref = 'HEAD') {
  let text
  try {
    text = execFileSync('git', ['show', ref + ':' + path], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
  } catch (cause) {
    throw new Error('读不到真源 ' + ref + ':' + path + '（git show 失败：' + cause.message + '）。行号对账不许降级，这里必须红，skip 等于回到手抄。')
  }
  if (!text.trim()) throw new Error('git show ' + ref + ':' + path + ' 返回空内容，无法对账。')
  return text.replace(/\r\n/g, '\n')
}

/** 两把尺都当场推导：集合定义那一行，加上每一枚写着 retryable=error_code in _RETRIABLE_CODES 的出口行。 */
function retriableSites(src) {
  const lines = src.split('\n')
  const def = lines.findIndex(line => /^\s*_RETRIABLE_CODES\s*=\s*\{/.test(line))
  const outs = lines.map((line, index) => (/retryable=error_code in _RETRIABLE_CODES/.test(line) ? index + 1 : 0)).filter(Boolean)
  if (def < 0 || !outs.length) throw new Error('app/agents/evidence.py 里认不出 _RETRIABLE_CODES 的定义行，或那句 retryable=error_code in _RETRIABLE_CODES 已被摘掉：两把尺都落空，这一格不许降级')
  return { definition: { line: def + 1, text: lines[def] }, outlets: outs.map(n => ({ line: n, text: lines[n - 1] })) }
}

/** 字典注释里的每一枚 evidence.py 坐标，按它自己那一行说的话分档：写着出口语句的那一档，其余那档说的是集合。 */
function evidenceCites(text) {
  return text.split('\n').flatMap((line, index) => [...line.matchAll(/app\/agents\/evidence\.py:(\d+)((?:\s*(?:[与和、,]|[/])\s*:(\d+))*)/g)]
    .flatMap(item => [Number(item[1])].concat((item[2].match(/\d+/g) || []).map(Number))
      .map(n => ({ n, at: index + 1, outlet: line.includes('retryable=error_code in _RETRIABLE_CODES') }))))
}

/** 后端那一枚集合的成员名同样当场从 git 对象里抠，不在本件里手抄一遍。 */
function retriableCodes(src) {
  const body = /\{([^}]*)\}/.exec(retriableSites(src).definition.text)
  return (body[1].match(/"[a-z_]+"/g) || []).map(token => token.replace(/"/g, ''))
}

describe('R368 甲 · 判据①：字典认得的码，屏上那一格跟着字典走', () => {
  it('ERROR_CODES 每一个键：readFailureView 的 retryable 逐枚等于字典那一枚（整表扫，不点名）', () => {
    for (const code of Object.keys(ERROR_CODES)) {
      const err = httpError(500, code)
      expect(dictionaryAdjudicatesRetry(err), code + ' ⇒ 在册却没被认成在册，屏上会走兜底那一条').toBe(true)
      const view = readFailureView(err, ARGS)
      expect(view.retryable, code + ' ⇒ 屏上 ' + view.retryable + '，字典 ' + ERROR_CODES[code].retryable).toBe(ERROR_CODES[code].retryable)
    }
  })

  it('LEGACY_ALIASES 每一个别名：同上；别名自己写了 retryable 就按它，没写才回落到目标码', () => {
    for (const legacy of Object.keys(LEGACY_ALIASES)) {
      const expected = effectiveVerdict(LEGACY_ALIASES[legacy])
      const view = readFailureView(httpError(500, legacy), ARGS)
      expect(view.retryable, legacy + ' ⇒ 屏上 ' + view.retryable + '，字典 ' + expected).toBe(expected)
    }
  })

  it('PROSE_ALIASES 每一条散文：同上（野外兜底那两条也归字典说话，不算「没码」）', () => {
    for (const prose of Object.keys(PROSE_ALIASES)) {
      const expected = effectiveVerdict(PROSE_ALIASES[prose])
      expect(readFailureView(httpError(500, prose), ARGS).retryable, prose).toBe(expected)
    }
  })

  it('后端信封自己带了 retryable 时跟信封走：同一本账里那一格优先，字典只补默认值', () => {
    expect(readFailureView(envelopeError(500, { code: 'storage_unavailable', message: 'tables missing' }), ARGS).retryable).toBe(false)
    expect(readFailureView(envelopeError(500, { code: 'storage_unavailable', message: 'm', retryable: true }), ARGS).retryable).toBe(true)
    expect(readFailureView(envelopeError(500, { code: 'internal_error', message: 'm' }), ARGS).retryable).toBe(false)
    expect(readFailureView(envelopeError(500, { code: 'internal_error', message: 'm', retryable: true }), ARGS).retryable).toBe(true)
  })

  it('字典在册却判可重试的那一格（authorization_unavailable）没被这单改硬：屏上仍给重试', () => {
    expect(ERROR_CODES.authorization_unavailable.retryable).toBe(true)
    expect(readFailureView(httpError(403, 'authorization_unavailable'), ARGS).retryable).toBe(true)
  })
})

describe('R368 乙 · 判据②：字典没说过的那一族，屏上仍给「重新加载」', () => {
  const UNADJUDICATED = {
    '500 空错误体（只剩 HTTP 状态兜底）': httpError(500, ''),
    '500 后端默认散文体': httpError(500, 'Internal Server Error'),
    '500 字典收不下的新码名': httpError(500, 'brand_new_backend_code'),
    '没有状态只有一枚新码名': httpError(0, 'mystery_backend_code_nobody_registered'),
    '422 校验数组（后端没给码名）': httpError(422, [{ loc: ['body', 'threshold'], msg: 'Value error', type: 'value_error' }]),
    '断网（有 request 无 response）': { request: {}, message: 'Network Error' },
    '断网（axios ERR_NETWORK）': { isAxiosError: true, code: 'ERR_NETWORK', message: 'Network Error', request: {} },
    '裸 Error（连归码的地方都没有）': new Error('boom'),
    什么都没有: null,
  }
  for (const name of Object.keys(UNADJUDICATED)) {
    const err = UNADJUDICATED[name]
    it(name + ' ⇒ retryable 仍为 true，且不冒充字典判定', () => {
      expect(dictionaryAdjudicatesRetry(err), name + ' ⇒ 这一发后端没点名，不该算字典说过').toBe(false)
      const view = readFailureView(err, ARGS)
      expect(view.face, name + ' ⇒ 仍是「坏了」那张脸，不许退成空态').toBe('error')
      expect(view.retryable, name + ' ⇒ 屏上 ' + view.retryable).toBe(true)
    })
  }

  it('判据②不越界：403 加一枚没登记的新码仍是「没权限」那张脸，也不因这条兜底改口给重试', () => {
    const view = readFailureView(httpError(403, 'alert_scope_required'), ARGS)
    expect(view.face).toBe('denied')
    expect(view.retryable).toBe(false)
    expect(view.codeLabel).toBe('错误码：alert_scope_required')
  })

  it('401 那张脸一个字都没被改坏：句子出自字典，不给重试', () => {
    const view = readFailureView(httpError(401, 'authentication_required'), ARGS)
    expect(view.face).toBe('unauthorized')
    expect(view.title).toBe('登录状态已失效')
    expect(view.description).toBe(ERROR_CODES.authentication_required.message)
    expect(view.retryable).toBe(false)
  })

  it('shapeFailureView（结构不对）那一支逐字未动：仍给重试，仍与空态两张脸', () => {
    const view = shapeFailureView(ARGS.failedTitle)
    expect(view.face).toBe('error')
    expect(view.title).toBe(ARGS.failedTitle)
    expect(view.codeLabel).toBe('')
    expect(view.retryable).toBe(true)
    expect(view.description).toContain('结构不对')
  })
})

describe('R368 丙 · 判据③：internal_error 的句子与 flag 不再互相打脸（裁定：改文案，flag 不动）', () => {
  it('flag 一分不动：这一枚仍是 false（后端两枚信封出口当场写着它不可重试）', () => {
    expect(ERROR_CODES.internal_error.retryable).toBe(false)
  })

  it('句子收掉「等一会儿再试」那一层邀请，点名故障与下一步的信息一分不退', () => {
    const message = ERROR_CODES.internal_error.message
    expect(message.startsWith('系统内部出现异常')).toBe(true)
    expect(message).not.toMatch(RETRY_LATER)
    expect(message).not.toMatch(SNAKE)
    expect(message).toContain('请联系管理员')
  })

  it('全称律：三张表里凡判 false 的那一格，句子都不许承诺「稍后重试」那一族字样', () => {
    const rows = dictionarySentences()
    expect(rows.length, '三张表摊平后至少该有几十格，扫空了就是这枚钉白写').toBeGreaterThan(40)
    for (const [name, message, flag] of rows) {
      if (flag) continue
      expect(RETRY_LATER.test(message), name + ' ⇒ flag=false 却写着「' + message + '」').toBe(false)
    }
  })

  it('屏上那句就是字典那句（不放宽成「另一句人话」），屏上也不出现口头重试邀请', () => {
    const view = readFailureView(httpError(500, 'internal_error'), ARGS)
    expect(view.description).toBe(ERROR_CODES.internal_error.message)
    expect(view.description).not.toMatch(RETRY_LATER)
    expect(view.retryable).toBe(false)
    expect(view.face).toBe('error')
  })
})

describe('R368 丁 · 判据④：三枚点名用例逐枚落屏（insight-alerts 那三枚钉的改口读数以此为准）', () => {
  it('503 storage_unavailable ⇒ 不挂重试，句子仍指向「联系管理员 / 确认迁移」', () => {
    const view = readFailureView(httpError(503, 'storage_unavailable'), ARGS)
    expect(view.face).toBe('error')
    expect(view.retryable).toBe(false)
    expect(view.description).toBe(ERROR_CODES.storage_unavailable.message)
    expect(view.description).toContain('联系管理员')
    expect(view.description).toContain('迁移')
    expect(errorText('storage_unavailable')).toContain('迁移')
  })

  it('500 internal_error ⇒ 改前 true（屏上硬编）／改后 false（跟字典）；脸与标题那两格一分未动', () => {
    const view = readFailureView(httpError(500, 'internal_error'), ARGS)
    expect(view.retryable).toBe(false)
    expect(view.face).toBe('error')
    expect(view.title).toBe(ARGS.failedTitle)
  })

  it('403 resource_scope_missing（error 脸）⇒ 改前 true／改后 false：别名那格本来就判 false，屏上不再另立', () => {
    const view = readFailureView(httpError(403, 'resource_scope_missing'), ARGS)
    expect(view.face).toBe('error')
    expect(view.retryable).toBe(false)
    expect(view.description).toBe(LEGACY_ALIASES.resource_scope_missing.message)
    expect(view.description).toContain('判断不了你能不能看')
    expect(view.codeLabel).toBe('')
  })

  it('Network Error ⇒ 保持 true 不动（判据②那一枚钉：它红了就说明判据②做坏了）', () => {
    const view = readFailureView({ request: {}, message: 'Network Error' }, ARGS)
    expect(view.face).toBe('error')
    expect(view.retryable).toBe(true)
    expect(view.description).toContain('连不上服务')
  })
})

describe('R368 戊 · 判据⑤：字典注释里引用的后端行号当场对得上（不抄数字）', () => {
  const EVIDENCE = 'app/agents/evidence.py'

  it('errcodes.js 每一枚 evidence.py 坐标都等于它自己那句话点名那一格的当场推导：说集合的钉定义行、说出口的钉各自那一枚出口行', () => {
    const sites = retriableSites(showAtRef(EVIDENCE))
    const cited = evidenceCites(sourceOf('../errcodes.js'))
    expect(cited.length, '字典里一处 evidence.py 引用都没有：引用被删了，这枚钉就白写').toBeGreaterThan(0)
    const outletCites = cited.filter(row => row.outlet).map(row => row.n)
    const setCites = [...new Set(cited.filter(row => !row.outlet).map(row => row.n))]
    expect(sites.outlets.length, '注释说「两枚信封出口」，后端现读却数出 ' + sites.outlets.length + ' 枚 retryable=error_code in _RETRIABLE_CODES：这句注释与后端不再是同一件事').toBe(2)
    expect(outletCites, '出口那一档漂了：注释逐枚是 ' + outletCites.join('、') + '，当场推导的出口行是 ' + sites.outlets.map(site => site.line).join('、')).toEqual(sites.outlets.map(site => site.line))
    expect(setCites, '集合那一档漂了：注释逐枚是 ' + setCites.join('、') + '，当场推导的定义行是 ' + sites.definition.line).toEqual([sites.definition.line])
  })

  it('反弹牙：把那句出口语句或那枚集合定义从 HEAD 那一版里摘掉 ⇒ 尺必须抛，不许静默数出零枚出口', () => {
    const src = showAtRef(EVIDENCE)
    const OUTLET = 'retryable=error_code in _RETRIABLE_CODES'
    expect(src.split(OUTLET).length, '后端那句话换了写法：这把尺得重新取证，不许拿旧形状算绿').toBeGreaterThan(2)
    expect(() => retriableSites(src.split(OUTLET).join('retryable = isRetriable(error_code)')), '摘掉出口语句还能算出位置：那把尺是假的').toThrow(/两把尺都落空/)
    expect(() => retriableSites(src.replace(/^(\s*)_RETRIABLE_CODES(\s*)=\s*\{/m, '$1$2NOT_A_SET = {')), '摘掉集合定义还能算出位置：那把尺是假的').toThrow(/两把尺都落空/)
  })

  it('注释那句「收了五档、刻意没有这一档」当场成立：档位数目与成员都从 git 对象现读', () => {
    const codes = retriableCodes(showAtRef(EVIDENCE))
    expect(codes.length, '后端 _RETRIABLE_CODES 的成员数变了：注释那句「五档」得跟着改口').toBe(5)
    expect(codes).not.toContain('storage_unavailable')
    expect(codes).not.toContain('internal_error')
    expect(dictionaryAdjudicatesRetry(httpError(503, 'storage_unavailable'))).toBe(true)
    expect(isRetryable(httpError(503, 'storage_unavailable'))).toBe(false)
  })
})

describe('R368 己 · 判据①的反面：取数层不许有第二本错误码账', () => {
  it('alerts.js 的代码体里没有那一族的码名，读数一律走字典那两条通道', () => {
    const code = codeOnly(sourceOf('../alerts.js'))
    for (const banned of ['storage_unavailable', 'knowledge_graph_unconfigured', 'open_platform_unconfigured', 'internal_error']) {
      expect(code.includes(banned), 'alerts.js 代码体里出现了 ' + banned + '：那是在抄第二本账').toBe(false)
    }
    expect(code.includes('dictionaryAdjudicatesRetry(')).toBe(true)
    expect(code.includes('isRetryable(')).toBe(true)
  })
})
