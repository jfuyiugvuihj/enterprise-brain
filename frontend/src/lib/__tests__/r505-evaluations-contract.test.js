/**
 * R505 判据 B + D · 「评测报告」那枚取数模块（src/lib/evaluations.js）的对账钉与归脸钉
 *
 * 判据 B 在这一屏只有一句话：它是读，不是跑。四格落地，逐格有钉：
 *  ① 载荷自己写着 execution.runs_on_request=false —— 本模块把这句、它给的理由、那句命令原样端出来；
 *  ② 全模块只有 GET：本件数 evaluations.js 里的写腿（post/put/patch/delete），一枚都不许有；
 *  ③ reports 为空 = status=no_reports 走空态脸，屏上不出现「0 分」这种看着像读数的东西；
 *  ④ truncated / limits 逐格如实，「没列全」不许被画成「就这些」。
 *
 * 字段一律对账 `git show HEAD:app/api/v1/observability.py`（同 r399 / r505-slo 的手法）：
 * 本单一枚后端文件都不改，HEAD 就是那一份真源，拿工作树对账会被自己的脏盘喂成假绿。
 * 真 HTML 在 src/components/__tests__/r505-evaluations-screen.test.js。
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../lib/http', async importOriginal => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn() } }
})

import { UNRECORDED } from '../alerts'
import { errorText } from '../errcodes'
import { http, PERMISSION_DENIED } from '../http'
import {
  EVALUATIONS_PATH,
  EVALUATIONS_STORAGE_CODE,
  EVAL_FACES,
  EVAL_FACE_DENIED,
  EVAL_FACE_EMPTY,
  EVAL_FACE_FAILED,
  EVAL_FACE_LOADING,
  EVAL_FACE_MALFORMED,
  EVAL_FACE_READY,
  EVAL_FACE_STORAGE,
  EVAL_FACE_UNAUTHORIZED,
  EVAL_EMPTY_DESCRIPTION,
  EVAL_LOADING_TEXT,
  EVAL_REPORT_SOURCE_LABELS,
  EVAL_REPORT_SOURCE_UNKNOWN,
  EVAL_REPORT_STATUS_LABELS,
  EVAL_REPORT_STATUS_UNKNOWN,
  EVAL_RETRYABLE_FACES,
  EVAL_RUNS_NO,
  EVAL_RUNS_UNKNOWN,
  EVAL_RUNS_YES,
  EVAL_STATUS_NO_REPORTS,
  EVAL_STATUS_REPORTS,
  EVAL_TITLES,
  evalBoolText,
  evalHeadView,
  evalLimitsView,
  evalMetricPairs,
  evalReportRow,
  evalReportSourceLabel,  evalReportStatusLabel,
  evalSuiteRow,
  evaluationExecutionView,
  evaluationsBlankView,
  evaluationsFaceView,
  evaluationsParams,
  evaluationsViewFromError,
  evaluationsViewFromResponse,
  loadEvaluations,
} from '../evaluations'

const REPO_REF = 'HEAD'
const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const MODULE_SOURCE = read('../evaluations.js')
const REPO_ROOT = fileURLToPath(new URL('../../../..', import.meta.url))

function gitShow(path) {
  try {
    const text = execFileSync('git', ['show', REPO_REF + ':' + path], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
    if (!text.trim()) throw new Error('内容为空')
    return text
  } catch (cause) {
    throw new Error('读不到真源 ' + REPO_REF + ':' + path + '（git show 失败：' + cause.message + '）。对账不许降级成 skip。')
  }
}
const observability = () => gitShow('app/api/v1/observability.py')
const handlerBody = () => {
  const match = /async def read_evaluations\([\s\S]*?\n\n\n/.exec(observability())
  expect(match, '读不到 read_evaluations 那一条出口').toBeTruthy()
  return match[0]
}

/** 后端真发的一发（键名逐格抄 :1172-1195 与 :443-477、:481-488）。 */
const REPORT_ROW = {
  id: 'r498-quality', path: 'reports/r498-quality.json', source: 'configured', status: 'ok',
  metrics: { overall_pass_rate: 0.9123, failed_case_ids: ['c-1', 'c-7'] },
  size_bytes: 40_960, modified_at: '2026-09-28T01:02:03+00:00', category_count: 4,
}
const SUITE_ROW = {
  id: 'ops-hygiene', path: 'fixtures/ops-hygiene.jsonl', exists: true,
  case_count: 84, categories: ['retrieval', 'refusal'], truncated: false,
}
const EXECUTION = {
  runs_on_request: false,
  reason: 'An evaluation executes the full retrieval and model stack over every case, so it cannot run inside a read-only management request.',
  command_template: 'python scripts/run_quality_evaluation.py --fixture {fixture} --answers {answers} --output {output}',
  report_module: 'app.quality.runner.run_recorded_evaluation',
}
const PAYLOAD = {
  status: EVAL_STATUS_REPORTS, requested_by: { username: 'root', roles: ['admin'], auth_source: 'local' },
  generated_at: '2026-09-29T02:03:04+00:00', reports: [REPORT_ROW], reports_total: 3, truncated: true,
  evaluation_sets: [SUITE_ROW], execution: EXECUTION,
  limits: { max_reports: 20, applied_limit: 20, requested_limit: null, clamped: false },
}
const REFUSALS = {
  unauthorized: { response: { status: 401, data: { detail: { code: 'authentication_required', message: 'A valid principal is required.', details: {} } } } },
  denied: { response: { status: 403, data: { detail: { code: 'permission_denied', message: 'evaluation:read is not permitted for this principal.', details: { reason_code: 'admin_role_required' } } } } },
  storage: { response: { status: 503, data: { detail: { code: 'storage_unavailable', message: 'report directory is not readable', details: {} } } } },
  failed: { response: { status: 500, data: { detail: { code: 'internal_error', message: 'evaluation listing blew up', details: {} } } } },
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('R505 甲 · 对账（读 git show ' + REPO_REF + ':app/api/v1/observability.py）', () => {
  it('出口地址就是那条装饰器；本模块只有一处地址字面量', () => {
    const match = /@router\.get\("([^"]+)", responses=_ERROR_RESPONSES\)\nasync def read_evaluations\(/.exec(observability())
    expect(match, '后端没有这条 GET /evaluations 了：对账的尺子本身过期').toBeTruthy()
    expect(EVALUATIONS_PATH).toBe(match[1])
    expect(MODULE_SOURCE.split("'" + EVALUATIONS_PATH + "'").length - 1).toBe(1)
  })

  it('这一屏读的每一格字段名都真在那条出口里存在，一枚都不许是界面自己造的', () => {
    const body = handlerBody()
    for (const key of ['status', 'requested_by', 'generated_at', 'reports', 'reports_total', 'truncated', 'evaluation_sets', 'execution', 'limits']) {
      expect(body, '回执里没这一格：' + key).toContain('"' + key + '"')
    }
    expect(body).toContain('"runs_on_request": False')
    expect(body).toContain('"reason"')
    expect(body).toContain('"command_template"')
    expect(body).toContain('"report_module"')
    // 报告行与评测集行的键名在 :443-477 / :481-488 现取，本模块只读这些，不加键。
    const source = observability()
    for (const key of ['id', 'path', 'source', 'status', 'metrics', 'size_bytes', 'modified_at', 'category_count', 'exists', 'case_count', 'categories', 'truncated']) {
      expect(source, '行模型里出现后端没交出的格：' + key).toContain('"' + key + '"')
    }
    for (const key of ['max_reports', 'applied_limit', 'requested_limit', 'clamped']) {
      expect(body, 'limits 里没这一格：' + key).toContain('"' + key + '"')
    }
  })

  it('状态、报告来源、报告结果三本词表逐字对齐后端，表外只认不下', () => {
    const body = handlerBody()
    expect(EVAL_STATUS_REPORTS).toBe(/"status": "([^"]+)" if summaries/.exec(body)[1])
    expect(EVAL_STATUS_NO_REPORTS).toBe(/else "([^"]+)",/.exec(body)[1])
    expect(Object.keys(EVAL_REPORT_STATUS_LABELS).sort()).toEqual(['ok', 'too_large', 'unreadable'])
    expect(Object.keys(EVAL_REPORT_SOURCE_LABELS).sort()).toEqual(['configured', 'shipped_default'])
    expect(evalReportStatusLabel('schrödinger')).toBe(EVAL_REPORT_STATUS_UNKNOWN)
    expect(evalReportSourceLabel('mirror_blessed')).toBe(EVAL_REPORT_SOURCE_UNKNOWN)
    expect(evalReportStatusLabel('unreadable')).toBe(EVAL_REPORT_STATUS_LABELS.unreadable)
  })

  it('这条出口只认一枚查询参数 limit：本模块发出去的键不许有第二种', () => {
    expect(/async def read_evaluations\(request: Request, (\w+): int \| None = None\)/.exec(observability())).toBeTruthy()
    expect(evaluationsParams('12')).toEqual({ limit: 12 })
    expect(evaluationsParams(12.7)).toEqual({ limit: 12 })
    for (const blank of ['', '   ', null, undefined, 'abc', {}]) {
      expect(evaluationsParams(blank), JSON.stringify(blank) + ' 被当成了一枚查询参数').toBeUndefined()
    }
  })
})

describe('R505 判据 B 之① · 「不跑分」这三格如实端出来', () => {
  it('服务端说 false，屏上就是 false 那一句：理由与命令一起原样转达', () => {
    const view = evaluationExecutionView(EXECUTION)
    expect(view.runs).toBe(false)
    expect(view.runsText).toBe(EVAL_RUNS_NO)
    expect(view.reason).toBe(EXECUTION.reason)
    expect(view.commandTemplate).toBe(EXECUTION.command_template)
    expect(view.reportModule).toBe(EXECUTION.report_module)
  })

  it('命令那一格是字符串，不是可点的东西：本模块不解析它、不拼接它、更不执行它', () => {
    const view = evaluationExecutionView(EXECUTION)
    expect(view.commandTemplate).toBe(EXECUTION.command_template)
    expect(view.commandTemplate).toContain('{fixture}')
    // 占位符没被前端 substitue 成真的评测集名 —— 那一步是「在界面上凑一条能跑的命令」。
    expect(view.commandTemplate).toContain('{answers}')
    expect(view.commandTemplate).toContain('{output}')
  })

  it('缺席与第三种答案都不许被折成 false：回执没答就是没答，答 true 就是前提已破', () => {
    expect(evaluationExecutionView(null).runs).toBeNull()
    expect(evaluationExecutionView(null).runsText).toBe(EVAL_RUNS_UNKNOWN)
    expect(evaluationExecutionView({ runs_on_request: 'false' }).runs).toBeNull()
    const yes = evaluationExecutionView({ ...EXECUTION, runs_on_request: true })
    expect(yes.runs).toBe(true)
    expect(yes.runsText).toBe(EVAL_RUNS_YES)
    expect(EVAL_RUNS_YES).not.toBe(EVAL_RUNS_NO)
    expect(EVAL_RUNS_YES).not.toBe(EVAL_RUNS_UNKNOWN)
    expect(new Set([EVAL_RUNS_NO, EVAL_RUNS_YES, EVAL_RUNS_UNKNOWN]).size).toBe(3)
  })
})

describe('R505 判据 B 之② · 这一屏没有任何一条写腿', () => {
  it('本模块里对 http 的调用只有 http.get 一枚：多一条写腿当场红', () => {
    // 数的是「调用形状」而不是子串：'output' 里那三个字母不算写腿，http.post() 才算。
    expect(MODULE_SOURCE.match(/http\.[A-Za-z_$][\w$]*\s*\(/g), '这一屏的读腿长出了第二种方法').toEqual(['http.get('])
    expect(MODULE_SOURCE).not.toMatch(/\b(?:fetch|axios|XMLHttpRequest)\s*\(/)
    // 命令那一格永远是文本：本模块不许出现 eval / new Function 这类把它变成动作的东西。
    expect(MODULE_SOURCE).not.toMatch(/\beval\s*\(|new Function\s*\(/)
  })

  it('空报告走空态脸：那一句说的是「一份都没有」，不是「零分」', () => {
    const view = evaluationsViewFromResponse({
      ...PAYLOAD, status: EVAL_STATUS_NO_REPORTS, reports: [], reports_total: 0, truncated: false,
    })
    expect(view.face).toBe(EVAL_FACE_EMPTY)
    expect(view.rows).toEqual([])
    expect(view.suites).toHaveLength(1)
    expect(view.title).toBe(EVAL_TITLES[EVAL_FACE_EMPTY])
    expect(view.description).toBe(EVAL_EMPTY_DESCRIPTION)
    expect(view.head.status).toBe(EVAL_STATUS_NO_REPORTS)
    // 反向：这一发仍然把 execution 那三格端出来 —— 空态不是「整屏闭嘴」。
    expect(view.execution.commandTemplate).toBe(EXECUTION.command_template)
  })

  it('读不出 reports / evaluation_sets 才是 malformed，不许滑进空态', () => {
    for (const payload of [{}, null, { reports: [] }, { reports: [], evaluation_sets: 'x' }, { reports: null, evaluation_sets: [] }]) {
      expect(evaluationsViewFromResponse(payload).face, JSON.stringify(payload)).toBe(EVAL_FACE_MALFORMED)
    }
  })
})

describe('R505 判据 B 之③ · 一行的读数面：文件读不出就直说', () => {
  it('一份报告一行：来源、状态、字节、改动时间、分类数各走各的格', () => {
    const row = evalReportRow(REPORT_ROW)
    expect(row.id).toBe('r498-quality')
    expect(row.sourceText).toBe(EVAL_REPORT_SOURCE_LABELS.configured)
    expect(row.statusText).toBe(EVAL_REPORT_STATUS_LABELS.ok)
    expect(row.sizeText).toBe('40960 字节')
    expect(row.modifiedText).toBe('2026-09-28 01:02')
    expect(row.categoryText).toBe('4 类')
    expect(row.hasMetrics).toBe(true)
  })

  it('metrics 是空对象就说「没交出指标」，不画零', () => {
    const row = evalReportRow({ ...REPORT_ROW, metrics: {}, status: 'unreadable' })
    expect(row.hasMetrics).toBe(false)
    expect(row.metrics).toEqual([])
    expect(row.statusText).toBe(EVAL_REPORT_STATUS_LABELS.unreadable)
    // size_bytes / modified_at 是条件性交的格（:452 那句 OSError 就直接 return）：没有就是未记录。
    const partial = evalReportRow({ id: 'gone', path: 'reports/gone.json', source: 'shipped_default', status: 'unreadable', metrics: {} })
    expect(partial.sizeText).toBe(UNRECORDED)
    expect(partial.modifiedText).toBe('')
    expect(partial.categoryText).toBe(UNRECORDED)
  })

  it('指标键名用后端那一格自己的名字，值只收成可读位数', () => {
    const pairs = evalMetricPairs(REPORT_ROW.metrics)
    expect(pairs.map(item => item.key)).toEqual(['overall_pass_rate', 'failed_case_ids'])
    expect(pairs[0].valueText).toBe('0.9123')
    expect(pairs[1].isList).toBe(true)
    expect(pairs[1].listText).toBe('c-1、c-7')
    expect(evalMetricPairs(null)).toEqual([])
  })

  it('评测集那一句：文件不存在时的零是「没这份文件」，不是「零道题全错」', () => {
    const missing = evalSuiteRow({ ...SUITE_ROW, exists: false, case_count: 0, categories: [], truncated: true })
    expect(missing.existsText).toBe('这台机器上没有这份文件')
    expect(missing.caseCountText).toBe('0 题')
    expect(missing.truncatedText).toBe('题号清单在这一发里被截过')
    expect(missing.exists).toBe(false)
    expect(evalSuiteRow({ ...SUITE_ROW, exists: 'yes' }).exists).toBeNull()
  })

  it('布尔三档：是 / 否 / 回执没答 —— 第三档存在的全部意义就是不替它答', () => {
    expect(evalBoolText(true, '甲', '乙')).toBe('甲')
    expect(evalBoolText(false, '甲', '乙')).toBe('乙')
    for (const notABoolean of [undefined, null, 'true', 1, 0]) {
      expect(evalBoolText(notABoolean, '甲', '乙'), JSON.stringify(notABoolean)).toBe(UNRECORDED)
    }
  })
})

describe('R505 判据 B 之④ · 截断与上限逐格如实', () => {
  it('truncated=true 说的是「还有更早的没列出」，不许读成「就这些」', () => {
    const head = evalHeadView(PAYLOAD)
    expect(head.truncated).toBe(true)
    expect(head.truncatedText).toBe('这一发只交出前若干份，报告目录里还有更早的没列出')
    expect(head.reportsTotal).toBe('3 份')
    expect(evalHeadView({ ...PAYLOAD, truncated: false }).truncatedText).toBe('这一发把回执认得的报告都列出来了')
    expect(evalHeadView({ ...PAYLOAD, truncated: 'yes' }).truncatedText).toBe(UNRECORDED)
    expect(evalHeadView({ ...PAYLOAD, truncated: null }).truncated).toBeNull()
  })

  it('limits 四格分开说：请求过几枚、实际给几枚、有没有被夹、出口最多给几枚', () => {
    const limits = evalLimitsView(PAYLOAD.limits)
    expect(limits.maxReports).toBe('20 份')
    expect(limits.appliedLimit).toBe('20 份')
    expect(limits.requestedLimit).toBe('这一发没带 limit')
    expect(limits.clampedText).toBe('没夹')
    const clamped = evalLimitsView({ max_reports: 20, applied_limit: 20, requested_limit: 900, clamped: true })
    expect(clamped.requestedLimit).toBe('900 份')
    expect(clamped.clamped).toBe(true)
    expect(clamped.clampedText).toBe('被后端夹过')
    expect(evalLimitsView(null).appliedLimit).toBe(UNRECORDED)
  })

  it('读腿不带 limit 就是真的不带：屏侧不替操作员宣称「我要默认那一档」', async () => {
    http.get.mockResolvedValue({ data: PAYLOAD })
    await loadEvaluations()
    expect(http.get.mock.calls[0]).toEqual([EVALUATIONS_PATH, undefined])
    await loadEvaluations('')
    expect(http.get.mock.calls[1]).toEqual([EVALUATIONS_PATH, undefined])
    await loadEvaluations(5)
    expect(http.get.mock.calls[2]).toEqual([EVALUATIONS_PATH, { params: { limit: 5 } }])
  })
})

describe('R505 判据 D · 三张失败脸分开留名', () => {
  const failureFaces = [EVAL_FACE_UNAUTHORIZED, EVAL_FACE_DENIED, EVAL_FACE_STORAGE, EVAL_FACE_FAILED, EVAL_FACE_MALFORMED]

  it('五张脸五句标题两两不等；脸谱名册定长', () => {
    const titles = failureFaces.map(face => EVAL_TITLES[face])
    expect(new Set(titles).size).toBe(5)
    titles.forEach(title => expect(title).toBeTruthy())
    expect(EVAL_FACES).toEqual(['loading', 'ready', 'empty', 'unauthorized', 'denied', 'storage', 'malformed', 'failed'])
    expect(EVAL_TITLES[EVAL_FACE_READY]).toBe('')
    expect(evaluationsBlankView().face).toBe(EVAL_FACE_LOADING)
    expect(evaluationsBlankView().description).toBe(EVAL_LOADING_TEXT)
  })

  it('403 / 503 / 500 三张脸各自落到自己那一格上', () => {
    const three = [REFUSALS.denied, REFUSALS.storage, REFUSALS.failed].map(evaluationsViewFromError)
    expect(three.map(view => view.face)).toEqual([EVAL_FACE_DENIED, EVAL_FACE_STORAGE, EVAL_FACE_FAILED])
    expect(new Set(three.map(view => view.title)).size).toBe(3)
    expect(evaluationsViewFromError(REFUSALS.unauthorized).face).toBe(EVAL_FACE_UNAUTHORIZED)
  })

  it('403 的句子出自那本全仓唯一的字典，后面接一句「下一步去哪」', () => {
    const view = evaluationsViewFromError(REFUSALS.denied)
    expect(view.description.startsWith(errorText(PERMISSION_DENIED))).toBe(true)
    expect(view.description).toContain('重新登录')
    expect(view.description).not.toContain('立即运行')
  })

  it('只有 failed / malformed 值得再按一次', () => {
    for (const face of [EVAL_FACE_DENIED, EVAL_FACE_STORAGE, EVAL_FACE_UNAUTHORIZED]) {
      expect(evaluationsFaceView({ face }).retryable, face).toBe(false)
    }
    expect(EVAL_RETRYABLE_FACES).toEqual([EVAL_FACE_FAILED, EVAL_FACE_MALFORMED])
    expect(evaluationsFaceView({ face: EVAL_FACE_FAILED }).retryable).toBe(true)
  })

  it('读腿把失败也变成一次归脸；表外形状落回 failed 那句，不画空白', async () => {
    http.get.mockRejectedValue(REFUSALS.storage)
    await expect(loadEvaluations()).resolves.toMatchObject({ face: EVAL_FACE_STORAGE })
    expect(evaluationsFaceView({ face: 'who_knows' }).title).toBe(EVAL_TITLES[EVAL_FACE_FAILED])
    expect(evaluationsFaceView(null).face).toBe('')
  })
})
