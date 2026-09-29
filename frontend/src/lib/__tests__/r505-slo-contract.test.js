/**
 * R505 判据 A + D · 「三档目标账」那枚取数模块（src/lib/slo.js）的对账钉与归脸钉
 *
 * 三件事分开验，各自有出处：
 *  甲 对账：本模块的词表与字段名，是不是后端此刻真发的那一套。读的是 `git show HEAD:app/**`
 *    而不是工作树（手法逐字照 r399-traces-contract.test.js —— 本单一枚后端文件都不改，
 *    HEAD 就是那一份真源；拿工作树对账会被自己的脏盘喂成假绿）。
 *  乙 判据 A：这一屏存在的全部理由 —— 「没量过」不许画成达成。三格机制逐格钉：
 *    样本闸不是查询参数、null 百分位一律「未记录」、目标值一格都不许出现数字。
 *  丙 判据 D：三张失败脸两两不等（403 / 503 / 500），另加 401 与「回包读不出形状」。
 *
 * 真 HTML 那一半在 src/components/__tests__/r505-slo-screen.test.js，入口形状在
 * src/router/__tests__/r505-admin-screens.test.js。
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// 只换网络层：errcodes 的判码与句子、traces 的格式化保持真身（同 r399 / r494 的手法）。
vi.mock('../../lib/http', async importOriginal => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn() } }
})

import { UNRECORDED } from '../alerts'
import { errorText } from '../errcodes'
import { PERMISSION_DENIED } from '../http'
import { http } from '../http'
import { durationText } from '../traces'
import {
  SLO_FACES,
  SLO_FACE_DENIED,
  SLO_FACE_FAILED,
  SLO_FACE_MALFORMED,
  SLO_FACE_READY,
  SLO_FACE_STORAGE,
  SLO_FACE_UNAUTHORIZED,
  SLO_LOADING_TEXT,
  SLO_PATH,
  SLO_RETRYABLE_FACES,
  SLO_STATUS_INSUFFICIENT,
  SLO_STATUS_LABELS,
  SLO_STATUS_MEASURED,
  SLO_STATUS_NOT_MEASURABLE,
  SLO_STATUS_UNKNOWN,
  SLO_SOURCE_LABELS,
  SLO_TARGET_LABELS,
  SLO_TARGET_PENDING,
  SLO_TITLES,
  loadSlo,
  sloBlankView,
  sloBlockerViews,
  sloFaceView,
  sloHasReadableNumber,
  sloHeadView,
  sloNumberView,
  sloPoolView,
  sloSourceLabel,
  sloTierViews,
  sloViewFromError,
  sloViewFromResponse,
} from '../slo'

const REPO_REF = 'HEAD'
const REPO_ROOT = fileURLToPath(new URL('../../../..', import.meta.url))
const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const MODULE_SOURCE = read('../slo.js')

function gitShow(path) {
  let text = ''
  try {
    text = execFileSync('git', ['show', REPO_REF + ':' + path], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
  } catch (cause) {
    throw new Error('读不到真源 ' + REPO_REF + ':' + path + '（git show 失败：' + cause.message + '）。对账不许降级成 skip。')
  }
  if (!text.trim()) throw new Error('git show ' + REPO_REF + ':' + path + ' 返回空内容，无法对账。')
  return text
}
const observability = () => gitShow('app/api/v1/observability.py')

/** 后端那一行 `NAME = "value"`：词表值一律从它现取，本件不把字符串抄第二份当尺子。 */
function pyLiteral(name) {
  const match = new RegExp('^' + name + '(?:: [^=]+)? = "([^"]+)"', 'm').exec(observability())
  expect(match, '后端读不到常量 ' + name).toBeTruthy()
  return match[1]
}
function pyNumber(name) {
  const match = new RegExp('^' + name + ' = (\\d+)', 'm').exec(observability())
  expect(match, '后端读不到常量 ' + name).toBeTruthy()
  return Number(match[1])
}
/** SLO_BLOCKERS 那本名册的键（后端 :777 起）：判据 A 要求码名原样上屏，先要知道原名有哪些。 */
function backendBlockerCodes() {
  const body = /^SLO_BLOCKERS: dict\[str, str\] = \{([\s\S]*?)^\}/m.exec(observability())
  expect(body, '读不到 SLO_BLOCKERS 那本名册').toBeTruthy()
  return [...body[1].matchAll(/^\s{4}"([a-z][a-z0-9_]+)":/gm)].map(match => match[1])
}

/** 后端真发的一格（照 _slo_stat / _slo_not_measurable 的键名与取值形状抄，不增不减）。 */
const STAT_SLOT = {
  n: 3, required_samples: 100, shortfall: 97, status: SLO_STATUS_INSUFFICIENT,
  p50_ms: null, p95_ms: null, percentile_source: 'app/common/performance.py::PerformanceStats',
  target: null, target_status: SLO_TARGET_PENDING, reason: 'insufficient samples: 3 of 100 observed',
}
const MEASURED_SLOT = { ...STAT_SLOT, n: 120, shortfall: 0, status: SLO_STATUS_MEASURED, p50_ms: 412.5, p95_ms: 1890 }
const NOT_MEASURABLE_SLOT = {
  n: 0, required_samples: 100, shortfall: 100, status: SLO_STATUS_NOT_MEASURABLE,
  p50_ms: null, p95_ms: null, percentile_source: 'app/common/performance.py::PerformanceStats',
  target: null, target_status: SLO_TARGET_PENDING, reason: 'qa.end_to_end_p95_ms has no measurement piece',
  label: '端到端九成五', population: 'this lane request windows', measured_from: 'no_measurement_piece',
  blockers: [{ code: 'lane_attribution_absent', detail: 'spans never carry a lane' }],
}
const TIER_PAYLOAD = {
  lane: 'qa', label: '问答档', note: 'the plain question lane',
  screen: { route: 'chat', path: '/chat', source: 'frontend/src/router/index.js' },
  endpoints: ['/api/v1/chat'], stages: ['retrieval'], observed_requests: 7,
  numbers: { end_to_end_p95_ms: { ...STAT_SLOT, label: '整条请求的九成五', population: 'request windows', measured_from: 'stage_ledger' } },
  stage_numbers: { retrieval: { ...NOT_MEASURABLE_SLOT } },
}
const REPORT = {
  schema: 'r105.slo/1', sample_floor: 100, target_status: SLO_TARGET_PENDING,
  percentile_source: 'app/common/performance.py::PerformanceStats (nearest rank)',
  units: { product_lane: { owns_the_name: 'tiers.py', decided_by: 'slo_tiers()', members: ['qa'], this_is_the_unit_of_the_slo: true } },
  tiers: [TIER_PAYLOAD],
  unattributed_pool: { what: 'every request window this process recorded', blockers: [{ code: 'lane_attribution_absent', detail: 'no lane on the event' }], end_to_end: { ...STAT_SLOT } },
  sample_population_note: 'requests are counted whether they completed, failed or were cancelled',
  requested_by: { username: 'root', roles: ['admin'], department: '', clearance: 3, auth_source: 'local' },
}

/** 后端真发的三枚失败信封（_fail 的 ErrorEnvelope：detail 里是 {code,message,retryable,details}）。 */
const REFUSALS = {
  unauthorized: { response: { status: 401, data: { detail: { code: 'authentication_required', message: 'A valid principal is required.', retryable: false, details: { resource: 'slo' } } } } },
  denied: { response: { status: 403, data: { detail: { code: 'permission_denied', message: 'audit:read is not permitted for this principal.', retryable: false, details: { reason_code: 'department_scope_denied' } } } } },
  storage: { response: { status: 503, data: { detail: { code: 'storage_unavailable', message: 'audit storage is not readable', retryable: true, details: {} } } } },
  failed: { response: { status: 500, data: { detail: { code: 'internal_error', message: 'slo readout blew up', retryable: false, details: {} } } } },
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('R505 甲 · 对账（读 git show ' + REPO_REF + ':app/api/v1/observability.py）', () => {
  it('出口地址就是路由装饰器里那一条，本模块没有第二处字面量', () => {
    const match = /@router\.get\("([^"]+)", responses=_ERROR_RESPONSES\)\nasync def read_slo\(/.exec(observability())
    expect(match, '后端没有这条 GET /slo 了：对账的尺子本身过期').toBeTruthy()
    expect(SLO_PATH).toBe(match[1])
    const occurrences = MODULE_SOURCE.split("'" + SLO_PATH + "'").length - 1
    expect(occurrences, '出口地址在模块里被抄了第二份').toBe(1)
  })

  it('判定三档的词表逐字对得上后端常量，一枚不多一枚不少', () => {
    const backend = {
      [pyLiteral('SLO_MEASURED')]: true,
      [pyLiteral('SLO_INSUFFICIENT')]: true,
      [pyLiteral('SLO_NOT_MEASURABLE')]: true,
    }
    expect(Object.keys(SLO_STATUS_LABELS).sort()).toEqual(Object.keys(backend).sort())
    expect(SLO_STATUS_MEASURED).toBe(pyLiteral('SLO_MEASURED'))
    expect(SLO_STATUS_INSUFFICIENT).toBe(pyLiteral('SLO_INSUFFICIENT'))
    expect(SLO_STATUS_NOT_MEASURABLE).toBe(pyLiteral('SLO_NOT_MEASURABLE'))
    const texts = Object.values(SLO_STATUS_LABELS)
    expect(new Set(texts).size, '三档说了同一句话 = 屏上分不出欠样本与不可测').toBe(3)
    texts.forEach(text => expect(text).toBeTruthy())
  })

  it('分布出处的词表同样逐字对齐；表外值只认不下，不替后端答', () => {
    expect(Object.keys(SLO_SOURCE_LABELS).sort()).toEqual([
      pyLiteral('SLO_SOURCE_LEDGER'), pyLiteral('SLO_SOURCE_NONE'), pyLiteral('SLO_SOURCE_TRACE'),
    ].sort())
    expect(sloSourceLabel('a_brand_new_source')).toBe('未登记的出处')
    expect(sloSourceLabel('')).toBe('未登记的出处')
    expect(sloSourceLabel(null)).toBe('未登记的出处')
  })

  it('目标状态那一格只有一句人话，且那句话里不许出现毫秒数', () => {
    expect(SLO_TARGET_PENDING).toBe(pyLiteral('SLO_TARGET_PENDING'))
    expect(Object.keys(SLO_TARGET_LABELS)).toEqual([SLO_TARGET_PENDING])
    const pending = SLO_TARGET_LABELS[SLO_TARGET_PENDING]
    expect(pending).not.toMatch(/\d+\s*(毫秒|ms)/i)
    // 后端在 :744 写明「写死一个 800 毫秒就是编数据」：本模块只转达，从不替这一格补数。
    expect(sloNumberView({ ...MEASURED_SLOT, target: null }).hasTarget).toBe(false)
    expect(sloNumberView({ ...MEASURED_SLOT }).hasTarget, '回执没交出 target，屏上却宣称有目标值').toBe(false)
    // 反向证明这一格真的接在后端那一格上：明天乙半填了数，今天这枚断言就换不到绿。
    expect(sloNumberView({ ...MEASURED_SLOT, target: 800 }).hasTarget).toBe(true)
  })

  it('本模块读的每一格字段名都真在后端源码里存在（少一枚就红，不许凭派工词猜字段）', () => {
    const source = observability()
    const keys = [
      'schema', 'sample_floor', 'target_status', 'percentile_source', 'units', 'tiers',
      'unattributed_pool', 'sample_population_note', 'requested_by', 'lane', 'label', 'note',
      'screen', 'endpoints', 'stages', 'observed_requests', 'numbers', 'stage_numbers',
      'n', 'required_samples', 'shortfall', 'status', 'p50_ms', 'p95_ms', 'target',
      'reason', 'blockers', 'population', 'measured_from', 'code', 'detail', 'what', 'end_to_end',
    ]
    for (const key of keys) {
      expect(source, '本模块读了后端没有的一格：' + key).toContain('"' + key + '"')
    }
  })

  it('样本闸那枚数是后端常量，不是本模块写死的数：屏上印的一律是回包读数', () => {
    const floor = pyNumber('MIN_SLO_SAMPLES')
    expect(Number.isFinite(floor)).toBe(true)
    // 本模块自己既没有 100 也没有 200 这种数字面量：它只转达 sample_floor。
    expect(MODULE_SOURCE).not.toMatch(/sample_floor\s*(?:\|\||\?)\?\s*\d/)
    expect(sloHeadView({ ...REPORT, sample_floor: 7 }).sampleFloor).toBe('7 条')
    expect(sloHeadView({}).sampleFloor).toBe(UNRECORDED)
  })
})

describe('R505 判据 A 之① · 样本闸不是查询参数', () => {
  it('读腿只带一条路径：不带 params、不带 limit、不带 min_samples', async () => {
    http.get.mockResolvedValue({ data: REPORT })
    const view = await loadSlo()
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(http.get.mock.calls[0][0]).toBe(SLO_PATH)
    expect(http.get.mock.calls[0].length, '这条读腿多带了查询参数：样本闸被当成可調的旋钮了').toBe(1)
    expect(view.face).toBe(SLO_FACE_READY)
  })

  it('屏上那枚下限来自回包 sample_floor：改回包就得改屏面', async () => {
    http.get.mockResolvedValue({ data: { ...REPORT, sample_floor: 4_000 } })
    const view = await loadSlo()
    expect(view.head.sampleFloor).toBe('4000 条')
    http.get.mockResolvedValue({ data: { ...REPORT, sample_floor: null } })
    expect((await loadSlo()).head.sampleFloor).toBe(UNRECORDED)
  })
})

describe('R505 判据 A 之② · 没量过就是没量过', () => {
  it('服务端答 null 的两枚百分位，屏上只有「未记录」，一枚 0 都不许出现', () => {
    const view = sloNumberView(STAT_SLOT)
    expect(view.p50Text).toBe(UNRECORDED)
    expect(view.p95Text).toBe(UNRECORDED)
    expect(view.p50Text).not.toBe(durationText(0))
    expect(view.statusText).toBe(SLO_STATUS_LABELS[SLO_STATUS_INSUFFICIENT])
    expect(view.statusText).toContain('欠样本')
    expect(sloHasReadableNumber(STAT_SLOT)).toBe(false)
  })

  it('欠样本与不可测说的是两句话：shortfall 原样转达，本层不重算', () => {
    const insufficient = sloNumberView(STAT_SLOT)
    const notMeasurable = sloNumberView(NOT_MEASURABLE_SLOT)
    expect(insufficient.shortfall).toBe('97 条')
    expect(notMeasurable.shortfall).toBe('100 条')
    expect(notMeasurable.samples).toBe('0 条样本')
    expect(notMeasurable.statusText).toContain('不可测')
    expect(notMeasurable.statusText).not.toBe(insufficient.statusText)
    // 后端把「还欠几枚」折好了交给屏（:1016）：屏面只做单位换算，不做减法。
    expect(notMeasurable.requiredSamples).toBe('100 条')
  })

  it('n=0 是真读数，但零样本换不来一枚 0 毫秒的 P95', () => {
    const view = sloNumberView(NOT_MEASURABLE_SLOT)
    expect(view.samples).toBe('0 条样本')
    expect(view.p95Text).toBe(UNRECORDED)
    expect(view.hasTarget, '回执说 target 是 null，屏上却宣称有目标值').toBe(false)
    expect(sloHasReadableNumber({ ...MEASURED_SLOT, p50_ms: null, p95_ms: null })).toBe(false)
  })

  it('表外判定只认不下：后端明天加第四档，屏上说「未登记的判定」而不是替它编一句', () => {
    const view = sloNumberView({ ...STAT_SLOT, status: 'partially_measured_we_hope' })
    expect(view.statusText).toBe(SLO_STATUS_UNKNOWN)
    expect(view.statusRaw).toBe('partially_measured_we_hope')
  })

  it('判据 A 的反面：只有 measured 且真带回数字，屏上才允许出现毫秒', () => {
    const measured = sloNumberView(MEASURED_SLOT)
    expect(measured.p95Text).toBe('1890 毫秒')
    expect(sloHasReadableNumber(MEASURED_SLOT)).toBe(true)
    // 而「量到了」也不许被读成「达标」：目标值那一格仍然是待填。
    expect(measured.targetText).toBe(SLO_TARGET_LABELS[SLO_TARGET_PENDING])
  })
})

describe('R505 判据 A 之③ · blockers 逐条挂出来，码名留后端原名', () => {
  it('每一条形如 {code, detail} 的障碍都留着自己的码名，一枚不合并、一枚不改名', () => {
    const codes = backendBlockerCodes()
    expect(codes.length, '后端那本名册读空了：对账的尺子本身过期').toBeGreaterThan(3)
    const views = sloBlockerViews(codes.map(code => ({ code, detail: 'why ' + code })))
    expect(views.map(item => item.codeName)).toEqual(codes)
    expect(views[0].id).toBe('blocker-0')
    expect(new Set(views.map(item => item.id)).size).toBe(views.length)
  })

  it('档上的障碍清单就是这一档各格障碍的并集：一条都不许被折成「还有障碍」', () => {
    const tier = sloTierViews({ tiers: [TIER_PAYLOAD] })[0]
    expect(tier.blockerList).toHaveLength(1)
    expect(tier.blockerList[0].codeName).toBe('lane_attribution_absent')
    expect(tier.blockerList[0].detail).toBe('spans never carry a lane')
    // 反向证明「分段那一格的障碍」确实被收进来了：把它摘掉，这一档就一枚障碍都没有 ——
    // 旧写法只读 numbers，这一条断言会当场红成 0 枚（码名一起丢）。
    expect(sloTierViews({ tiers: [{ ...TIER_PAYLOAD, stage_numbers: {} }] })[0].blockerList).toEqual([])
    const both = sloTierViews({
      tiers: [{
        ...TIER_PAYLOAD,
        numbers: { end_to_end_p95_ms: { ...STAT_SLOT, blockers: [{ code: 'cache_hits_are_not_traced', detail: 'no window for a hit' }] } },
      }],
    })[0]
    expect(both.blockerList.map(item => item.codeName)).toEqual(['cache_hits_are_not_traced', 'lane_attribution_absent'])
    expect(new Set(both.blockerList.map(item => item.id)).size, '两枚障碍共用了同一个 key').toBe(2)
    expect(tier.label).toBe('问答档')
    expect(tier.screenRoute).toBe('chat')
    expect(tier.endpoints).toEqual(['/api/v1/chat'])
    expect(tier.observedRequests).toBe('7 枚请求窗口')
  })

  it('非数组的 blockers 一律当「没交出障碍」，不猜、不补一条', () => {
    expect(sloBlockerViews(undefined)).toEqual([])
    expect(sloBlockerViews({ code: 'lane_attribution_absent' })).toEqual([])
    expect(sloBlockerViews([null])).toEqual([{ id: 'blocker-0', codeName: '', detail: '' }])
  })

  it('未归因那一池单独说：它不是一档，读不到就整格缺席', () => {
    const pool = sloPoolView(REPORT)
    expect(pool.blockers.map(item => item.codeName)).toEqual(['lane_attribution_absent'])
    expect(pool.endToEnd.p95Text).toBe(UNRECORDED)
    expect(sloPoolView({})).toBeNull()
    expect(sloPoolView({ unattributed_pool: 'yes' })).toBeNull()
  })
})

describe('R505 丙 · 形状读不出就是读不出（200 也可能什么都不知道）', () => {
  it('缺 tiers 的回包走 malformed，不许滑成「三档都是零」', () => {
    for (const payload of [{}, null, undefined, { tiers: null }, { tiers: 'three' }, []]) {
      expect(sloViewFromResponse(payload).face, JSON.stringify(payload)).toBe(SLO_FACE_MALFORMED)
    }
  })

  it('tiers 是空数组：屏上没有任何一档，但这一发确实读回来了', () => {
    const view = sloViewFromResponse({ ...REPORT, tiers: [] })
    expect(view.face).toBe(SLO_FACE_READY)
    expect(view.tiers).toEqual([])
    expect(view.tiers.length).toBe(0)
  })

  it('blank 视图只可能是加载或失败两张脸，且加载那一枚不许带标题', () => {
    const loading = sloBlankView()
    expect(loading.description).toBe(SLO_LOADING_TEXT)
    expect(loading.title).toBe('')
    expect(sloBlankView('anything else').face).toBe(SLO_FACE_FAILED)
  })
})

describe('R505 判据 D · 三张失败脸分开留名，另加 401 与形状脸', () => {
  const faces = [SLO_FACE_UNAUTHORIZED, SLO_FACE_DENIED, SLO_FACE_STORAGE, SLO_FACE_FAILED, SLO_FACE_MALFORMED]

  it('五张脸各有一句自己的标题，一枚都不塌成「加载失败」；脸谱名册定长', () => {
    const titles = faces.map(face => SLO_TITLES[face])
    expect(new Set(titles).size, '有两张脸共用了同一句标题').toBe(titles.length)
    titles.forEach(title => expect(title).toBeTruthy())
    expect(SLO_FACES).toEqual(['loading', 'ready', 'unauthorized', 'denied', 'storage', 'malformed', 'failed'])
    expect(SLO_TITLES[SLO_FACE_READY], '正常脸不该有一句标题：它画的是账，不是一句话').toBe('')
    for (const face of faces) {
      expect(sloFaceView({ face }).title, face + ' 这张脸没有自己的标题').toBe(SLO_TITLES[face])
    }
    // 表外的脸不许被静默接住：它落到 failed 那句上，而不是画出一片空白。
    expect(sloFaceView({ face: 'shrödinger' }).title).toBe(SLO_TITLES[SLO_FACE_FAILED])
  })

  it('403 给 denied、503 给 storage、500 给 failed：三张脸两两不等', () => {
    expect(sloViewFromError(REFUSALS.denied).face).toBe(SLO_FACE_DENIED)
    expect(sloViewFromError(REFUSALS.storage).face).toBe(SLO_FACE_STORAGE)
    expect(sloViewFromError(REFUSALS.failed).face).toBe(SLO_FACE_FAILED)
    const three = [sloViewFromError(REFUSALS.denied), sloViewFromError(REFUSALS.storage), sloViewFromError(REFUSALS.failed)]
    expect(new Set(three.map(view => view.title)).size).toBe(3)
    expect(new Set(three.map(view => view.face)).size).toBe(3)
  })

  it('401 与形状脸也不与上面同名', () => {
    expect(sloViewFromError(REFUSALS.unauthorized).face).toBe(SLO_FACE_UNAUTHORIZED)
    expect(sloViewFromResponse({}).face).toBe(SLO_FACE_MALFORMED)
    const all = [...[SLO_FACE_UNAUTHORIZED, SLO_FACE_DENIED, SLO_FACE_STORAGE, SLO_FACE_FAILED, SLO_FACE_MALFORMED].map(face => SLO_TITLES[face])]
    expect(new Set(all).size).toBe(5)
  })

  it('403 那张脸必须指出下一步去哪，且明说界面上没有能把闸调低的地方', () => {
    const view = sloViewFromError(REFUSALS.denied)
    // 句子出自 lib/errcodes.js 那本全仓唯一的字典（本模块不自造错误文案）；后端原话不进文案，
    // 它进的是 codeLabel 那一格 —— 两件事各有各的通道，这里各钉各的。
    expect(view.description.startsWith(errorText(PERMISSION_DENIED)), '这一屏在自造第二份错误文案').toBe(true)
    expect(view.description).toContain('重新登录')
    expect(view.description).toContain('样本闸')
    expect(view.codeLabel).toBe('')
    expect(sloViewFromError({ response: { status: 403, data: { detail: { code: 'brand_new_denial_code', message: 'nope' } } } }).codeLabel)
      .toContain('brand_new_denial_code')
  })

  it('只有「读回失败 / 读不出形状」两张脸值得再按一次：没权限与坏存储重放同一发不改变结果', () => {
    const face = given => sloFaceView(sloViewFromError(given)).face
    expect(sloFaceView({ face: SLO_FACE_DENIED }).retryable).toBe(false)
    expect(sloFaceView({ face: SLO_FACE_STORAGE }).retryable).toBe(false)
    expect(sloFaceView({ face: SLO_FACE_UNAUTHORIZED }).retryable).toBe(false)
    expect(sloFaceView({ face: SLO_FACE_FAILED }).retryable).toBe(true)
    expect(sloFaceView({ face: SLO_FACE_MALFORMED }).retryable).toBe(true)
    expect(SLO_RETRYABLE_FACES).toEqual([SLO_FACE_FAILED, SLO_FACE_MALFORMED])
    expect(face(REFUSALS.denied)).toBe(SLO_FACE_DENIED)
  })

  it('没有响应体的网络层异常落在 failed 上，而不是崩给屏看', () => {
    const view = sloViewFromError(new Error('Network Error'))
    expect(view.face).toBe(SLO_FACE_FAILED)
    expect(view.title).toBe(SLO_TITLES[SLO_FACE_FAILED])
    expect(view.tiers).toEqual([])
  })

  it('读腿把失败也变成一次归脸：不抛出、不留下 pending promise', async () => {
    http.get.mockRejectedValue(REFUSALS.storage)
    await expect(loadSlo()).resolves.toMatchObject({ face: SLO_FACE_STORAGE })
  })
})
