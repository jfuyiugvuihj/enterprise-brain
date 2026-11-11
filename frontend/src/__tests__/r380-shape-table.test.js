/**
 * R380 判据① · 人话位形状全表（本班现场取证的可执行版）
 *
 * 这枚件不是一条断言，是一张表：今天所有能走到「给人看的那一句」的响应形状，逐格写清三件事
 *   ① shape  形状本身（响应体长什么样 + HTTP 状态）
 *   ② before 改判前屏上印的是哪一句、出处在 errcodes.js 第几行（基点 285e265 的行号）
 *      —— 取证手法：给 clampResult 插一根栈记录探针跑一遍，量完按字节复原（sha256 进出相等）
 *   ③ message/code/rawMessage/label  改判之后屏上该是哪一句、出自哪张表、原文走哪条出口
 *
 * 表的完整性由下面四枚元断言钉住，不靠人眼：每一格都必须填 before 与出处行号；id 不许重；
 * 裸串那一族（bare:true）改判之后一格都不许剩无中文的人话位；全表无中文的人话位只准落在
 * ENGLISH_SLOTS 那份封闭名单里，名单扩容必须连 R281 判据③一起改判，不许悄悄加一格。
 *
 * 后端真源现读 app/**（不采信派工词）：中文 detail 见 app/api/v1/auth.py:75/:130/:179/:222/:225/:281、
 * alerts.py:1020、app/common/auth.py:603 起那一段、common/authorization.py:23；ASCII-only 的 detail
 * 字面量在 118 个 py 文件里共 73 枚，逐枚数过全是 snake_case 码名（走 frontend/src/lib/errcodes.js:309 那一档，压根到不了
 * 散文位）。屏上那句英文只可能出自框架与代理：app 没有 @exception_handler，未捕获 500 由
 * Starlette 回 "Internal Server Error"，另有 "Not Found" / "Too Many Requests" / "Bad Gateway"
 * 与 nginx 502 正文。逐枚中文人的句子的穷举钉在 __tests__/r380-detail-voice.test.js 乙组。
 */
import { describe, expect, it } from 'vitest'

import {
  ERROR_CODES,
  FALLBACK_MESSAGE,
  LEGACY_ALIASES,
  blobErrorText,
  errorCodeLabel,
  normalizeError,
} from '../lib/errcodes'

/** 本单反面角色：框架/代理那句英文原话 */
const FRAMEWORK_EN = 'Internal Server Error'
/** R281 那枚反面角色：后端信封里的英文原句（app/common/authorization.py:94-99） */
const BACKEND_EN = 'department must match the authenticated principal'
const ZH_LOGIN = '用户名或密码错误'
const HTML_502 =
  '<!DOCTYPE html><html><head><title>502 Bad Gateway</title></head><body>nginx</body></html>'

/** 与现场同形的 axios 错误：status + data 两格，人话位竞争从这一发开始 */
function httpError(status, data) {
  return {
    isAxiosError: true,
    message: 'Request failed with status code ' + status,
    response: { status, data },
  }
}

/** 人话位出处的全部合法说法。冒出第五种 = 长出了第二真相源 */
const DICT = '字典码句'
const DICT_STATUS = '字典状态句'
const FALLBACK = '兜底句'
const BACKEND = '后端人话直出'
const TRANSPORT = '传输层专用句'
const TEMPLATE = '字典校验模板句'
const SLOTS = [DICT, DICT_STATUS, FALLBACK, BACKEND, TRANSPORT, TEMPLATE]

/** 无中文的人话位名单（封闭）：这几格仍会印英文，每一格都写明为什么不归本单收 */
const ENGLISH_SLOTS = {
  C2: 'R281 判据③钉住的那一档：信封带了码而字典收不下它，后端那句 message 是唯一线索。',
  C5: '同上一档的另一形状（信封压根没有 code）。收它要动 fromEnvelope，判据⑤不许放宽 R281。',
  C7: '同上一档：裸信封对象没有 response 包裹，走的还是 fromEnvelope 那一处分流。',
  E6: '错误体只有 message 一格，pickPayload:582 把它当信封交出去，落进同上一档。',
  D4: '422 数组里 loc 为空：句子出自 pydantic 而不是后端散文，收它要在 fromValidation 开第二道闸。',
  F5: '本地 Error 的 message（不是响应体）：走 resolveTransport:610，与后端原文无关，R281 戊组明令不背这个责任。',
}

const HAS_CJK = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]/

/** 表体：每一格的期望都写成符号引用（ERROR_CODES[...] / FALLBACK_MESSAGE / 原句本身），不抄文案 */
const ROWS = [
  {
    id: 'A1',
    bare: true,
    shape: '{detail:"用户名或密码错误"} · 401（后端写好的中文人话，app/api/v1/auth.py:75）',
    before: '用户名或密码错误',
    line: ':471',
    input: () => httpError(401, {detail:"用户名或密码错误"}),
    code: 'authentication_required',
    slot: BACKEND,
    message: ZH_LOGIN,
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'A2',
    bare: true,
    shape: '{detail:"Internal Server Error"} · 500（Starlette 未捕获异常的默认体；app 里没有 @exception_handler）',
    before: 'Internal Server Error',
    line: ':471',
    input: () => httpError(500, {detail:"Internal Server Error"}),
    code: 'internal_error',
    slot: DICT_STATUS,
    message: ERROR_CODES.internal_error.message,
    rawMessage: FRAMEWORK_EN,
    label: '',
    retryable: false,
  },
  {
    id: 'A3',
    bare: true,
    shape: '{detail:"Not Found"} · 404（框架英文原话）',
    before: 'Not Found',
    line: ':471',
    input: () => httpError(404, {detail:"Not Found"}),
    code: 'resource_not_found',
    slot: DICT_STATUS,
    message: ERROR_CODES.resource_not_found.message,
    rawMessage: 'Not Found',
    label: '',
    retryable: false,
  },
  {
    id: 'A4',
    bare: true,
    shape: '{detail:"Too Many Requests"} · 429（框架英文原话）',
    before: 'Too Many Requests',
    line: ':471',
    input: () => httpError(429, {detail:"Too Many Requests"}),
    code: 'rate_limited',
    slot: DICT_STATUS,
    message: ERROR_CODES.rate_limited.message,
    rawMessage: 'Too Many Requests',
    label: '',
    retryable: true,
  },
  {
    id: 'A5',
    bare: true,
    shape: '{detail:"Bad Gateway"} · 502（反代英文原话）',
    before: 'Bad Gateway',
    line: ':471',
    input: () => httpError(502, {detail:"Bad Gateway"}),
    code: 'model_unavailable',
    slot: DICT_STATUS,
    message: ERROR_CODES.model_unavailable.message,
    rawMessage: 'Bad Gateway',
    label: '',
    retryable: true,
  },
  {
    id: 'A6',
    bare: true,
    shape: '{detail:"Insufficient Storage"} · 507（状态不在 STATUS_CODES）',
    before: 'Insufficient Storage',
    line: ':476',
    input: () => httpError(507, {detail:"Insufficient Storage"}),
    code: '',
    slot: FALLBACK,
    message: FALLBACK_MESSAGE,
    rawMessage: 'Insufficient Storage',
    label: '',
    retryable: false,
  },
  {
    id: 'A7',
    bare: true,
    shape: '{detail:"Internal Server Error"} · status 0（没有状态码可归类）',
    before: 'Internal Server Error',
    line: ':476',
    input: () => ({ response: { status: 0, data: { detail: FRAMEWORK_EN } } }),
    code: '',
    slot: FALLBACK,
    message: FALLBACK_MESSAGE,
    rawMessage: FRAMEWORK_EN,
    label: '',
    retryable: false,
  },
  {
    id: 'A8',
    bare: true,
    shape: '{detail:"unsupported_file"} · 415（裸串=枚举码本尊）',
    before: '这个文件类型系统暂不支持，请换一种格式再传。（改判前后同句）',
    line: ':414',
    input: () => httpError(415, {detail:"unsupported_file"}),
    code: 'unsupported_file',
    slot: DICT,
    message: ERROR_CODES.unsupported_file.message,
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'A9',
    bare: true,
    shape: '{detail:"department_override_denied"} · 403（裸串=LEGACY 别名码）',
    before: '同句（走别名表，本就出自字典）',
    line: ':420',
    input: () => httpError(403, {detail:"department_override_denied"}),
    code: 'validation_error',
    slot: DICT,
    message: LEGACY_ALIASES.department_override_denied.message,
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'A10',
    bare: true,
    shape: '{detail:500}（detail 是数字）',
    before: '500',
    line: ':471',
    input: () => httpError(500, { detail: 500 }),
    code: 'internal_error',
    slot: DICT_STATUS,
    message: ERROR_CODES.internal_error.message,
    rawMessage: '500',
    label: '',
    retryable: false,
  },
  {
    id: 'A11',
    bare: true,
    shape: '{detail:"Error"} · 500（单个英文词，不是码名形状）',
    before: 'Error',
    line: ':471',
    input: () => httpError(500, {detail:"Error"}),
    code: 'internal_error',
    slot: DICT_STATUS,
    message: ERROR_CODES.internal_error.message,
    rawMessage: 'Error',
    label: '',
    retryable: false,
  },
  {
    id: 'B1',
    bare: true,
    shape: '{detail:"请先登录"} · 401（PROSE_ALIASES 在册的中文散文）',
    before: '同句（散文表命中，本就出自字典）',
    line: ':431',
    input: () => httpError(401, {detail:"请先登录"}),
    code: 'authentication_required',
    slot: DICT,
    message: ERROR_CODES.authentication_required.message,
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'B2',
    bare: true,
    shape: '{detail:"storage_backend_down"} · 500（未登记的码名）',
    before: '同句（未知码走兜底句 + 小字，本就如此）',
    line: ':459',
    input: () => httpError(500, {detail:"storage_backend_down"}),
    code: 'internal_error',
    slot: FALLBACK,
    message: FALLBACK_MESSAGE,
    rawMessage: '',
    label: '错误码：storage_backend_down',
    retryable: false,
  },
  {
    id: 'B3',
    bare: true,
    shape: '{detail:"storage_backend_down"} · status 0（未登记码名且没有状态可归类）',
    before: '同句（:459 那一档与状态无关）',
    line: ':459',
    input: () => ({ response: { status: 0, data: { detail: 'storage_backend_down' } } }),
    code: '',
    slot: FALLBACK,
    message: FALLBACK_MESSAGE,
    rawMessage: '',
    label: '错误码：storage_backend_down',
    retryable: false,
  },
  {
    id: 'B4',
    bare: true,
    shape: '{detail:"本轮未产出任何结论（error_code=no_answer_produced），…"} · 500（正文内嵌枚举码）',
    before: '同句（摘码后认得是枚举码）',
    line: ':445',
    input: () => httpError(500, {detail:"本轮未产出任何结论（error_code=no_answer_produced），请重试或补充数据范围。"}),
    code: 'no_answer_produced',
    slot: DICT,
    message: ERROR_CODES.no_answer_produced.message,
    rawMessage: '',
    label: '',
    retryable: true,
  },
  {
    id: 'B5',
    bare: true,
    shape: '{detail:"upstream refused (some_random_code)"} · status 0（内嵌码摘不动）',
    before: 'upstream refused',
    line: ':448',
    input: () => ({ response: { status: 0, data: { detail: 'upstream refused (some_random_code)' } } }),
    code: '',
    slot: FALLBACK,
    message: FALLBACK_MESSAGE,
    rawMessage: 'upstream refused',
    label: '错误码：some_random_code',
    retryable: false,
  },
  {
    id: 'B6',
    bare: true,
    shape: '{detail:"model 已降级，请改用本地模型"} · 500（中英混排，含中文）',
    before: '同句（含中文，改判前后一字不差）',
    line: ':471',
    input: () => httpError(500, {detail:"model 已降级，请改用本地模型"}),
    code: 'internal_error',
    slot: BACKEND,
    message: "model 已降级，请改用本地模型",
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'B7',
    bare: true,
    shape: '{detail:"upstream 无响应"} · 507（中英混排 + 状态未在册）',
    before: '同句（含中文）',
    line: ':476',
    input: () => httpError(507, {detail:"upstream 无响应"}),
    code: '',
    slot: BACKEND,
    message: "upstream 无响应",
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'C1',
    shape: '{detail:{code:"department_override_denied",message:英文原话}} · 403（R281 现场那一发）',
    before: '字典句（R281 已收口，本单未动）',
    line: ':533',
    input: () => httpError(403, { detail: { code: 'department_override_denied', message: BACKEND_EN } }),
    code: 'validation_error',
    slot: DICT,
    message: LEGACY_ALIASES.department_override_denied.message,
    rawMessage: BACKEND_EN,
    label: '',
    retryable: false,
  },
  {
    id: 'C2',
    shape: '{detail:{code:未登记码,message:英文原话}} · 500（未知码那一档）',
    before: '同句（R281 判据③钉住：字典收不下这枚 code 时后端那句仍是唯一线索）',
    line: ':533',
    input: () => httpError(500, { detail: { code: 'mystery_backend_code', message: BACKEND_EN } }),
    code: 'internal_error',
    slot: BACKEND,
    message: BACKEND_EN,
    rawMessage: BACKEND_EN,
    label: '错误码：mystery_backend_code',
    retryable: false,
  },
  {
    id: 'C3',
    shape: '{detail:{code:未登记码,message:中文}} · 500',
    before: '同句（未动）',
    line: ':533',
    input: () => httpError(500, { detail: { code: 'mystery_backend_code', message: '导出列名不能为空' } }),
    code: 'internal_error',
    slot: BACKEND,
    message: "导出列名不能为空",
    rawMessage: "导出列名不能为空",
    label: '错误码：mystery_backend_code',
    retryable: false,
  },
  {
    id: 'C4',
    shape: '{detail:{code:枚举码,message:中文}} · 415',
    before: '同句（改的是出处不是语种，R281 甲组）',
    line: ':533',
    input: () => httpError(415, { detail: { code: 'unsupported_file', message: '这个文件类型不支持' } }),
    code: 'unsupported_file',
    slot: DICT,
    message: ERROR_CODES.unsupported_file.message,
    rawMessage: "这个文件类型不支持",
    label: '',
    retryable: false,
  },
  {
    id: 'C5',
    shape: '{detail:{message:英文原话}} · 500（信封压根没有 code）',
    before: '同句（本单未动 · 见残留名单）',
    line: ':533',
    input: () => httpError(500, { detail: { message: BACKEND_EN } }),
    code: 'internal_error',
    slot: BACKEND,
    message: BACKEND_EN,
    rawMessage: BACKEND_EN,
    label: '',
    retryable: false,
  },
  {
    id: 'C6',
    shape: '{detail:{error_code:"queue_unavailable",message:英文}} · SSE（码名走 error_code）',
    before: '同句（envelopeCode() 两格都认，R281 未动）',
    line: ':533',
    input: () => ({ response: { status: 0, data: { detail: { error_code: 'queue_unavailable', message: BACKEND_EN } } } }),
    code: 'queue_unavailable',
    slot: DICT,
    message: ERROR_CODES.queue_unavailable.message,
    rawMessage: BACKEND_EN,
    label: '',
    retryable: true,
  },
  {
    id: 'C7',
    shape: '裸信封对象 {code:未登记码,message:英文}（没有 response 包裹）',
    before: '同句（未动 · 见残留名单）',
    line: ':533',
    input: () => ({ code: 'mystery_backend_code', message: BACKEND_EN }),
    code: '',
    slot: BACKEND,
    message: BACKEND_EN,
    rawMessage: BACKEND_EN,
    label: '错误码：mystery_backend_code',
    retryable: false,
  },
  {
    id: 'D1',
    shape: 'FastAPI 422 列表 [{loc:["body","department"],msg:"Field required",type:"missing"}]',
    before: '同句（模板句，未动）',
    line: ':557',
    input: () => httpError(422, { detail: [{ loc: ['body', 'department'], msg: 'Field required', type: 'missing' }] }),
    code: 'validation_error',
    slot: TEMPLATE,
    message: "「department」为必填项，请补充后再提交。",
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'D2',
    shape: 'FastAPI 422 列表 type=value_error（pydantic 英文原因贴在中文模板句尾）',
    before: '同句（未动 · 见残留名单）',
    line: ':553',
    input: () => httpError(422, { detail: [{ loc: ['body', 'rows'], msg: 'Value error, rows must be positive', type: 'value_error' }] }),
    code: 'validation_error',
    slot: TEMPLATE,
    message: "「rows」填写有误：Value error, rows must be positive",
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'D3',
    shape: 'FastAPI 422 空列表 · 500（等于没有错误体）',
    before: '同句（空数组退状态归类，未动）',
    line: ':471',
    input: () => httpError(500, { detail: [] }),
    code: 'internal_error',
    slot: DICT_STATUS,
    message: ERROR_CODES.internal_error.message,
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'D4',
    shape: 'FastAPI 422 列表 loc 为空 [{loc:[],msg:"Input should be a valid integer"}]',
    before: '同句（未动 · 见残留名单）',
    line: ':555',
    input: () => httpError(422, { detail: [{ loc: [], msg: 'Input should be a valid integer', type: 'int_parsing' }] }),
    code: 'validation_error',
    slot: BACKEND,
    message: "Input should be a valid integer",
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'E1',
    shape: '{detail:"<!DOCTYPE html>…nginx…"} · 502（网关整页塞进 detail）',
    before: '同句（cleanText 早把 HTML 清了，未动）',
    line: ':471',
    input: () => httpError(502, { detail: HTML_502 }),
    code: 'model_unavailable',
    slot: DICT_STATUS,
    message: ERROR_CODES.model_unavailable.message,
    rawMessage: '',
    label: '',
    retryable: true,
  },
  {
    id: 'E2',
    shape: 'data 直接是 HTML 文本串 · 502',
    before: '同句（未动）',
    line: ':471',
    input: () => httpError(502, HTML_502),
    code: 'model_unavailable',
    slot: DICT_STATUS,
    message: ERROR_CODES.model_unavailable.message,
    rawMessage: '',
    label: '',
    retryable: true,
  },
  {
    id: 'E3',
    shape: 'data 是纯文本英文体 · 500（text/plain 的 "Internal Server Error"）',
    before: 'Internal Server Error',
    line: ':471',
    input: () => httpError(500, FRAMEWORK_EN),
    code: 'internal_error',
    slot: DICT_STATUS,
    message: ERROR_CODES.internal_error.message,
    rawMessage: FRAMEWORK_EN,
    label: '',
    retryable: false,
  },
  {
    id: 'E4',
    shape: '空错误体 {} · 500',
    before: '同句（未动）',
    line: ':471',
    input: () => httpError(500, {}),
    code: 'internal_error',
    slot: DICT_STATUS,
    message: ERROR_CODES.internal_error.message,
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'E5',
    shape: '压根没有 response.data · 500',
    before: '同句（未动）',
    line: ':471',
    input: () => ({ response: { status: 500 } }),
    code: 'internal_error',
    slot: DICT_STATUS,
    message: ERROR_CODES.internal_error.message,
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'E6',
    shape: '错误体只有 message 一格 {message:英文原话} · 500（没有 detail/error_code/code）',
    before: '同句（pickPayload 把它当信封交出去，未动 · 残留名单）',
    line: ':533',
    input: () => httpError(500, { message: BACKEND_EN }),
    code: 'internal_error',
    slot: BACKEND,
    message: BACKEND_EN,
    rawMessage: BACKEND_EN,
    label: '',
    retryable: false,
  },
  {
    id: 'E7',
    shape: '错误体只有 error 一格 {error:"Something went wrong"} · 500',
    before: 'Something went wrong',
    line: ':471',
    input: () => httpError(500, { error: 'Something went wrong' }),
    code: 'internal_error',
    slot: DICT_STATUS,
    message: ERROR_CODES.internal_error.message,
    rawMessage: "Something went wrong",
    label: '',
    retryable: false,
  },
  {
    id: 'F1',
    shape: '传输层断网 {code:"ERR_NETWORK"}（没有响应体）',
    before: '同句（未动）',
    line: ':604',
    input: () => ({ code: 'ERR_NETWORK', message: 'Network Error' }),
    code: '',
    slot: TRANSPORT,
    message: "连不上服务，请确认网络或稍后重试。",
    rawMessage: '',
    label: '',
    retryable: true,
  },
  {
    id: 'F2',
    shape: '传输层超时 {code:"ECONNABORTED"}',
    before: '同句（未动）',
    line: ':601',
    input: () => ({ code: 'ECONNABORTED', message: 'timeout of 30000ms exceeded' }),
    code: 'task_timeout',
    slot: DICT,
    message: ERROR_CODES.task_timeout.message,
    rawMessage: '',
    label: '',
    retryable: true,
  },
  {
    id: 'F3',
    shape: 'axios 自己的英文原句 + 空体 · 500（"Request failed with status code 500"）',
    before: '同句（cleanText 清了 axios 原句，未动）',
    line: ':471',
    input: () => ({ isAxiosError: true, message: 'Request failed with status code 500', response: { status: 500, data: {} } }),
    code: 'internal_error',
    slot: DICT_STATUS,
    message: ERROR_CODES.internal_error.message,
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'F4',
    shape: '裸 Error（前端自己写的中文：new Error("会话已过期")）',
    before: '同句（本地 Error 的 message 走传输层通道，未动）',
    line: ':610',
    input: () => new Error('会话已过期'),
    code: '',
    slot: BACKEND,
    message: "会话已过期",
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'F5',
    shape: '裸 Error（运行时英文：new Error("Request aborted")）',
    before: '同句（未动 · 残留名单：本地 Error 的 message 不是响应体）',
    line: ':610',
    input: () => new Error('Request aborted'),
    code: '',
    slot: BACKEND,
    message: "Request aborted",
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'G1',
    shape: '什么都没有（normalizeError(undefined)）',
    before: '同句（未动）',
    line: ':476',
    input: () => undefined,
    code: '',
    slot: FALLBACK,
    message: FALLBACK_MESSAGE,
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'G2',
    shape: '裸字符串入参 "unsupported_file"（pickPayload 收成 {detail}）',
    before: '同句（未动）',
    line: ':414',
    input: () => 'unsupported_file',
    code: 'unsupported_file',
    slot: DICT,
    message: ERROR_CODES.unsupported_file.message,
    rawMessage: '',
    label: '',
    retryable: false,
  },
  {
    id: 'G3',
    shape: '裸英文串入参（无状态可归类）',
    before: 'department must match the authenticated principal',
    line: ':476',
    input: () => BACKEND_EN,
    code: '',
    slot: FALLBACK,
    message: FALLBACK_MESSAGE,
    rawMessage: BACKEND_EN,
    label: '',
    retryable: false,
  },
  {
    id: 'H1',
    shape: 'blob 错误体（下载/预览）：JSON 体里 detail 是英文原话 · 500',
    before: 'Internal Server Error',
    line: ':471',
    direct: true,
    input: () => blobErrorText('{"detail":"Internal Server Error"}', 500),
    code: 'internal_error',
    slot: DICT_STATUS,
    message: ERROR_CODES.internal_error.message,
    rawMessage: FRAMEWORK_EN,
    label: '',
    retryable: false,
  },
  {
    id: 'H2',
    shape: 'blob 错误体非 JSON（纯文本英文）· 500',
    before: '同句（非 JSON 正文刻意不采信，未动）',
    line: ':471',
    direct: true,
    input: () => blobErrorText('Internal Server Error', 500),
    code: 'internal_error',
    slot: DICT_STATUS,
    message: ERROR_CODES.internal_error.message,
    rawMessage: '',
    label: '',
    retryable: false,
  },
]

const LEGAL_CODES = new Set([...Object.keys(ERROR_CODES), ''])

describe('R380 判据① · 形状全表逐格对账（' + ROWS.length + ' 格）', () => {
  for (const row of ROWS) {
    it(row.id + " · " + row.shape, () => {
      // blobErrorText 的返回值本身就是 normalizeError 的产物：再复算一遍会把字典那句人话当成
      // 信封 message 收进 rawMessage（error-detail.js 口径①同一条教训），所以这一格直接读。
      const result = row.direct ? row.input() : normalizeError(row.input())
      expect(result.message, row.id + " 屏上那句").toBe(row.message)
      expect(result.code, row.id + " 归类码").toBe(row.code)
      expect(result.rawMessage, row.id + " 原文出口").toBe(row.rawMessage)
      expect(errorCodeLabel(result), row.id + " 小字通道").toBe(row.label)
      expect(result.retryable, row.id + " retryable").toBe(row.retryable)
      expect(SLOTS, row.id + " 出处种类").toContain(row.slot)
    })
  }
})

describe('R380 判据① · 表的完整性（元断言）', () => {
  it("每一格都填了改判前那句与基点行号，出处行号必须是 errcodes.js 的三位数行号", () => {
    for (const row of ROWS) {
      expect(row.before.length, row.id + " 缺改判前那句").toBeGreaterThan(0)
      expect(row.line, row.id + " 缺出处行号").toMatch(/^:\d{3}$/)
      expect(row.shape.length, row.id + " 缺形状描述").toBeGreaterThan(8)
    }
  })

  it("id 两两不等，格子数与名单数都对得上（不靠人眼数）", () => {
    const ids = ROWS.map((row) => row.id)
    expect(new Set(ids).size, "有重复 id").toBe(ids.length)
    expect(ids.length).toBe(46)
    expect(Object.keys(ENGLISH_SLOTS).every((id) => ids.includes(id)), "残留名单里有不认识的 id").toBe(true)
  })

  it("裸串那一族：改判之后一格都不许剩无中文的人话位", () => {
    const leaked = ROWS.filter((row) => row.bare).filter((row) => !HAS_CJK.test(row.message))
    expect(leaked.map((row) => row.id), "形状 1 又把英文送上了人话位").toEqual([])
  })

  it("全表无中文的人话位 == 封闭名单，一格不多一格不少；名单里每一格都写了理由", () => {
    const noCjk = ROWS.filter((row) => !HAS_CJK.test(row.message)).map((row) => row.id)
    expect(noCjk.sort(), "人话位上的英文格子变了：扩容要连 R281 判据③一起改判").toEqual(Object.keys(ENGLISH_SLOTS).sort())
    for (const id of Object.keys(ENGLISH_SLOTS)) {
      expect(ENGLISH_SLOTS[id].length, id + " 没写为什么不归本单收").toBeGreaterThan(20)
    }
  })

  it("code 那一格永远在封闭枚举或空串里（硬不变量，本单新增的出口也不例外）", () => {
    for (const row of ROWS) expect(LEGAL_CODES.has(row.code), row.id).toBe(true)
  })

  it("字典句那一族：屏上那句必须逐字出自三张表，不许是前端另编的", () => {
    const sentences = new Set([
      ...Object.values(ERROR_CODES).map((entry) => entry.message),
      ...Object.values(LEGACY_ALIASES).map((entry) => entry.message).filter(Boolean),
      FALLBACK_MESSAGE,
    ])
    for (const row of ROWS) {
      if (row.slot === DICT || row.slot === DICT_STATUS || row.slot === FALLBACK) {
        expect(sentences.has(row.message), row.id + " 这句不在字典里").toBe(true)
      }
    }
  })
})

