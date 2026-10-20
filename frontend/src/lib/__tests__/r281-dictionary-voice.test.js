/**
 * R281 判据①②③④⑤ · 人话位改判：字典赢，后端原文一个字符都不丢
 *
 * 病灶（上一单 R277 坐实，本单复取证后动手）：lib/errcodes.js::fromEnvelope 把信封里的
 * message 顶在字典句之前。后端今天真发的那一种形状是 { code, message }，而 message 是英文
 * 原句（app/common/authorization.py:94-99），于是屏上画的是
 * "department must match the authenticated principal" —— 客户读到的是缺陷，不是信息。
 *
 * 改判之后只有一条规则，它同时回答判据①与判据③：
 *   分流只看「这枚 code 有没有被字典收编」（errcodes.js::dictionaryClaims），
 *   不看「后端有没有回 message」。
 *     收编（枚举本尊 / LEGACY_ALIASES / PROSE_ALIASES / 正文内嵌且认得出枚举码）⇒ 人话位归字典；
 *     收不下 ⇒ 字典关于这一发只有兜底句，后端那句 message 仍是唯一线索，照旧占人话位。
 *   两档都不丢原文：信封 message 一律另存进 normalizeError() 的 rawMessage。
 * 为什么不选「一律丢弃 message」：未知码那一档会被删掉唯一的信息源，屏幕上只剩
 *   「操作没有完成，请稍后重试。」—— 排查路当场堵死，判据③明令不许。
 * 为什么不选改判前的「有 message 就用 message」：那人话位归不归字典就取决于后端有没有回话，
 *   判据①的洞原样留着。丙组最后那枚「换码名即换说法」的对照钉把这一条钉成红。
 *
 * 钉法：全部打在 lib 的公开出口上，不引组件、不起渲染器（本单写域不含任何 .vue 件）。
 *   甲 反证钉①  信封带英文 message ⇒ 出字典句；并拿三张表的**每一个键**正向扫一遍 ——
 *               这条同时是 dictionaryClaims() 的覆盖钉：谁在 resolveCode 里加一条命中路径而
 *               dictionaryClaims 没跟上，那枚键就红。
 *   乙 判据②    department_override_denied 两形状同句，errorDetail 这条薄通道也拿得到。
 *   丙 反证钉②  未知码那一档的逐字行为 + 同一句 message 换码名的分流对照。
 *   丁 判据④    http.js 那句假注释已改口（源码侧钉）+ 改回「英文原句优先」必红（行为侧钉）。
 *   戊 反证钉③  形状 1 裸串、形状 3 校验数组、传输层、blob 都没被这次改判碰到。
 *   己          通道唯一性：只加了一格数据，没把「错误码：xxx」那条小字改成常开。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

import {
  ERROR_CODES,
  FALLBACK_MESSAGE,
  LEGACY_ALIASES,
  PROSE_ALIASES,
  blobErrorText,
  errorCodeLabel,
  errorText,
  formatError,
  normalizeError,
} from '../errcodes'
import { errorDetail } from '../http'

/** 后端真发的那句英文原话（app/common/authorization.py:94-99），本单全篇的反面角色。 */
const BACKEND_ENGLISH = 'department must match the authenticated principal'
/** 通用反面夹具：任何在册码配上这句话，屏上都不许出现它。 */
const ANY_ENGLISH = 'the requested resource is not available for this principal'
/** 字典收不下的码名（未知码那一档的主角）。 */
const MYSTERY = 'mystery_backend_code_nobody_registered'

/** 形状 2 夹具：status 默认 0，逼字典自己认码，不许靠 STATUS_CODES 兜底蒙对。 */
function envelopeError(detail, status = 0) {
  return {
    isAxiosError: true,
    message: 'Request failed with status code ' + (status || 0),
    response: { status, data: { detail } },
  }
}

const envelope = (code, message = ANY_ENGLISH, retryable) =>
  envelopeError({ code, message, ...(retryable === undefined ? {} : { retryable }) })

/** 人话位不许出现英文整句：本仓给人看的句子全是中文散文（裸码名另有 no-bare-code 那道闸）。 */
function expectNoEnglish(text, label) {
  expect(/[A-Za-z]{4,}\s+[A-Za-z]{4,}/.test(text), label + ' ⇒ ' + text).toBe(false)
}

/** 三张表的每一个键 → 字典为该键备的句子（取值式与 resolveCode 一致，不另算一套）。 */
const DICTIONARY_KEYS = []
for (const code of Object.keys(ERROR_CODES)) {
  DICTIONARY_KEYS.push({ input: code, sentence: ERROR_CODES[code].message, from: 'ERROR_CODES' })
}
for (const legacy of Object.keys(LEGACY_ALIASES)) {
  const entry = LEGACY_ALIASES[legacy]
  DICTIONARY_KEYS.push({
    input: legacy,
    sentence: entry.message || ERROR_CODES[entry.code].message,
    from: 'LEGACY_ALIASES',
  })
}
for (const prose of Object.keys(PROSE_ALIASES)) {
  const entry = PROSE_ALIASES[prose]
  DICTIONARY_KEYS.push({
    input: prose,
    sentence: entry.message || ERROR_CODES[entry.code].message,
    from: 'PROSE_ALIASES',
  })
}

describe('甲 · 判据① + 反证钉①：在册码配上英文 message，人话位必须归字典', () => {
  it('现场那一发（authorization.py 的 403 信封）：画字典句，英文原句改由 rawMessage 报告', () => {
    const result = normalizeError(envelopeError({
      code: 'department_override_denied',
      message: BACKEND_ENGLISH,
    }, 403))
    expect(result.code).toBe('validation_error')
    expect(result.rawCode).toBe('department_override_denied')
    expect(result.message).toContain('请求里写的部门不是你这个账号所属的部门')
    expect(result.message).not.toContain(BACKEND_ENGLISH)
    expectNoEnglish(result.message, '人话位')
    // 后端原文不许丢：这一格就是它唯一的出口
    expect(result.rawMessage).toBe(BACKEND_ENGLISH)
    expect(result.retryable).toBe(false)
  })

  it('字典在册的每一个键都扫一遍：配英文 message 也只出字典句，原文一律进 rawMessage', () => {
    expect(DICTIONARY_KEYS.length).toBeGreaterThan(40)
    for (const { input, sentence, from } of DICTIONARY_KEYS) {
      const result = normalizeError(envelope(input))
      expect(result.message, from + ' 的 ' + input).toBe(sentence)
      expect(result.rawMessage, from + ' 的 ' + input).toBe(ANY_ENGLISH)
      expectNoEnglish(result.message, from + ' 的 ' + input)
    }
  })

  it('信封没带 message 时行为一字未动：还是字典句，rawMessage 是空串', () => {
    const bare = normalizeError(envelope('parse_failed', ''))
    expect(bare.message).toBe(ERROR_CODES.parse_failed.message)
    expect(bare.rawMessage).toBe('')
    const missing = normalizeError(envelopeError({ code: 'conflict' }))
    expect(missing.message).toBe(ERROR_CODES.conflict.message)
    expect(missing.rawMessage).toBe('')
  })

  it('retryable 不在改判范围：那一格仍由信封覆盖，字典默认值让位', () => {
    expect(normalizeError(envelope('internal_error', ANY_ENGLISH, true)).retryable).toBe(true)
    expect(normalizeError(envelope('internal_error', ANY_ENGLISH)).retryable).toBe(false)
  })

  it('中文后端句一样让位：改的是出处，不是语种', () => {
    const result = normalizeError(envelope('unsupported_file', '这个文件类型不支持'))
    expect(result.message).toBe(ERROR_CODES.unsupported_file.message)
    expect(result.rawMessage).toBe('这个文件类型不支持')
  })
})

describe('乙 · 判据②：department_override_denied 两形状同句（专用逻辑已下沉到字典层）', () => {
  const sentence = LEGACY_ALIASES.department_override_denied.message
  const shape2 = () => envelopeError({ code: 'department_override_denied', message: BACKEND_ENGLISH }, 403)

  it('形状 1（裸串）与形状 2（{code,message} 信封）出同一句人话', () => {
    const one = normalizeError(envelopeError('department_override_denied', 403))
    const two = normalizeError(shape2())
    expect(one.message).toBe(sentence)
    expect(two.message).toBe(sentence)
    expect(two.message).toBe(one.message)
    expect(two.code).toBe(one.code)
    expect(two.retryable).toBe(one.retryable)
  })

  it('errorDetail 这条薄通道也拿得到：面板不再需要自己挑出处', () => {
    expect(errorDetail(shape2(), '审批预审失败')).toBe(sentence)
    expect(errorDetail(shape2(), '审批预审失败')).toBe(errorText('department_override_denied'))
    expect(errorDetail(shape2(), '审批预审失败')).not.toContain(BACKEND_ENGLISH)
  })

  it('结构自证：走 normalizeError 与走 errorText 已是同一个出处', () => {
    const viaNormalize = normalizeError(shape2()).message
    expect(viaNormalize).toBe(errorText('department_override_denied'))
    expect(viaNormalize).not.toBe(FALLBACK_MESSAGE)
  })
})

describe('丙 · 判据③ + 反证钉②：未知码那一档一分未退', () => {
  it('未登记码 + 后端 message：message 仍占人话位，与改判前逐字相同', () => {
    const result = normalizeError(envelopeError({ code: MYSTERY, message: ANY_ENGLISH }, 500))
    expect(result.code).toBe('internal_error')
    expect(result.rawCode).toBe(MYSTERY)
    expect(result.message).toBe(ANY_ENGLISH)
    expect(result.message).not.toBe(FALLBACK_MESSAGE)
    // 同一句原文也照样进 rawMessage：两格同字是刻意的（理由见 clampResult 注释的第②条）
    expect(result.rawMessage).toBe(ANY_ENGLISH)
  })

  it('未登记码 + 没 message：还是兜底句，不硬编一句假人话', () => {
    const result = normalizeError(envelopeError({ code: MYSTERY }, 500))
    expect(result.message).toBe(FALLBACK_MESSAGE)
    expect(result.rawMessage).toBe('')
  })

  it('状态也归不下时 code 为空，人话位仍留给后端那句', () => {
    const result = normalizeError(envelopeError({ code: MYSTERY, message: ANY_ENGLISH }, 418))
    expect(result.code).toBe('')
    expect(result.rawCode).toBe(MYSTERY)
    expect(result.message).toBe(ANY_ENGLISH)
  })

  it('只有 message 没有 code：这一发字典无话可说，人话位仍归后端（信息量不降级）', () => {
    const result = normalizeError(envelopeError({ message: '导出列名不能为空' }, 400))
    expect(result.code).toBe('validation_error')
    expect(result.message).toBe('导出列名不能为空')
    expect(result.rawMessage).toBe('导出列名不能为空')
  })

  it('分流判据是「码在不在字典」，不是「有没有 message」：同一句英文换码名即换说法', () => {
    const claimed = normalizeError(envelopeError({ code: 'validation_error', message: ANY_ENGLISH }, 400))
    const unclaimed = normalizeError(envelopeError({ code: MYSTERY, message: ANY_ENGLISH }, 400))
    expect(claimed.message).toBe(ERROR_CODES.validation_error.message)
    expect(unclaimed.message).toBe(ANY_ENGLISH)
    expect(claimed.message).not.toBe(unclaimed.message)
    // 两档的后端原文都还在，差别只在人话位归谁
    expect(claimed.rawMessage).toBe(unclaimed.rawMessage)
  })

  it('未登记码仍可报告：小字通道语义一字未改', () => {
    const err = envelopeError({ code: MYSTERY, message: ANY_ENGLISH }, 500)
    const result = normalizeError(err)
    expect(errorCodeLabel(result)).toBe('错误码：' + MYSTERY)
    expect(formatError(err)).toBe(ANY_ENGLISH + '（错误码：' + MYSTERY + '）')
  })
})

describe('丁 · 判据④：http.js 那句假注释改口，且改回「英文原句优先」必须红', () => {
  const httpSource = readFileSync(new URL('../http.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n')

  it('假话已从源码里消失：把那句注释写回来即红', () => {
    expect(httpSource).not.toMatch(/已经把它们清了/)
    expect(httpSource).not.toMatch(/不用在这儿防/)
    expect(httpSource).not.toMatch(/cleanText\(:\d/)
    // 改口之后的说法：防线在字典侧的分流，出口是 rawMessage
    expect(httpSource).toContain('dictionaryClaims')
    expect(httpSource).toContain('rawMessage')
    expect(httpSource).toMatch(/R281 判据④/)
  })

  it('行为侧：在册码配英文 message 走 errorDetail 也不许上屏（把 fromEnvelope 改回 message 优先即红）', () => {
    const err = envelopeError({ code: 'retrieval_unavailable', message: 'the policy standard could not be retrieved' }, 503)
    const text = errorDetail(err, '知识库取不到报销标准')
    expect(text).toBe(ERROR_CODES.retrieval_unavailable.message)
    expect(text).not.toContain('the policy standard')
    expectNoEnglish(text, 'errorDetail')
  })

  it('对照：这枚钉不是恒真 —— 未登记码那一档 errorDetail 仍直出后端句', () => {
    expect(errorDetail(envelopeError({ code: MYSTERY, message: ANY_ENGLISH }, 500), 'x')).toBe(ANY_ENGLISH)
  })
})

describe('戊 · 反证钉③：这次改判只动形状 2，其余形状一字未退', () => {
  it('形状 1 裸码名：出字典句，rawMessage 恒为空串', () => {
    const result = normalizeError(envelopeError('department_override_denied', 403))
    expect(result.message).toBe(LEGACY_ALIASES.department_override_denied.message)
    expect(result.rawMessage).toBe('')
    expect(normalizeError(envelopeError('unsupported_file', 415)).rawMessage).toBe('')
  })

  it('形状 1 后端写好的中文人话：照旧直出，没有被这次改判吃掉', () => {
    const result = normalizeError(envelopeError('用户名或密码错误', 401))
    expect(result.message).toBe('用户名或密码错误')
    expect(result.code).toBe('authentication_required')
    expect(result.rawMessage).toBe('')
  })

  it('形状 3 校验数组：模板句里仍带字段名，rawMessage 恒为空串', () => {
    const result = normalizeError(envelopeError([{ loc: ['body', 'department'], msg: 'Field required', type: 'missing' }], 422))
    expect(result.message).toBe('「department」为必填项，请补充后再提交。')
    expect(result.rawMessage).toBe('')
  })

  it('传输层与 axios 英文原句：该清的还是清了，rawMessage 不背这个责任', () => {
    const aborted = normalizeError({ code: 'ECONNABORTED', message: 'timeout of 30000ms exceeded' })
    expect(aborted.code).toBe('task_timeout')
    expect(aborted.message).toBe(ERROR_CODES.task_timeout.message)
    expect(aborted.rawMessage).toBe('')
    const plain = normalizeError(envelopeError('', 422))
    expect(plain.message).not.toMatch(/^Request failed with status code/)
    expect(plain.rawMessage).toBe('')
  })

  it('blob 错误体（下载与预览）走同一条 fromEnvelope：在册码出字典句 + 原文进 rawMessage', () => {
    const hit = blobErrorText('{"detail":{"code":"permission_denied","message":"department must match"}}', 403)
    expect(hit.message).toBe(ERROR_CODES.permission_denied.message)
    expect(hit.rawMessage).toBe('department must match')
    const miss = blobErrorText('{"detail":{"code":"odd_download_code","message":"odd download reason"}}', 200)
    expect(miss.code).toBe('')
    expect(miss.message).toBe('odd download reason')
    expect(miss.rawMessage).toBe('odd download reason')
  })
})

describe('己 · 通道唯一性：只加了一格数据，没造第二条并列出口', () => {
  it('在册码不发小字：这次没把「错误码：xxx」改成常开', () => {
    for (const { input, sentence } of DICTIONARY_KEYS) {
      const result = normalizeError(envelope(input))
      expect(errorCodeLabel(result), input).toBe('')
      expect(formatError(result), input).toBe(sentence)
    }
  })

  it('每一条出口都带 rawMessage 这一格，且一定是字符串（消费方可以无条件读）', () => {
    const battery = [
      undefined, null, {}, 'unsupported_file', 0,
      { detail: { code: 'conflict', message: ANY_ENGLISH } },
      envelopeError({ code: 'parse_failed', message: ANY_ENGLISH }, 500),
      envelopeError([{ loc: ['body', 'rows'], msg: 'Field required', type: 'missing' }], 422),
      envelopeError('请先登录', 401),
      new Error('会话已过期'),
    ]
    for (const input of battery) {
      const result = normalizeError(input)
      expect(typeof result.rawMessage, String(JSON.stringify(input) || input)).toBe('string')
    }
  })

  it('normalizeError 的产物直接回喂也不改判：人话位仍归字典', () => {
    const once = normalizeError(envelopeError({ code: 'parse_failed', message: ANY_ENGLISH }, 500))
    const twice = normalizeError(once)
    expect(once.message).toBe(ERROR_CODES.parse_failed.message)
    expect(twice.message).toBe(once.message)
    expect(twice.code).toBe(once.code)
    expect(twice.retryable).toBe(once.retryable)
  })
})
