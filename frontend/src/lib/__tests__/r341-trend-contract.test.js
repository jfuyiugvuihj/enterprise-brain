/**
 * R341 · 「数据趋势」接 `/dashboard/trend` 的契约钉（lib 层）
 *
 * 钉的是这一层的四条判据，全部对着 docs/api/contract-v1.md:2509 起那一节写：
 *   ② 数字只从这条路由来（不碰聚合、不按 created_at 自己切期、窗口不由前端截断）；
 *   ④ 告警两键整键缺席 = 权限，不是 0、也不是横杠；
 *   ⑤ period / buckets 原样做成查询参数，422 与 503 两张脸分开；
 *   ⑧ 回包形状读不出就是失败，绝不降级成「空序列」。
 * 手法沿用 dashboard-summary.test.js：环境 node，只 mock 网络层那一枚 axios 实例。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn() } }
})

import { http } from '../http'
import { ERROR_CODES } from '../errcodes'
import {
  ALERT_STATE_COUNTED,
  ALERT_STATE_DENIED,
  ALERT_STATE_UNREADABLE,
  COUNT_PLACEHOLDER,
  loadDashboardTrend,
  parseTrendPayload,
  SUMMARY_PATH,
  TREND_ALERTS_DENIED_NOTE,
  TREND_ALERTS_OPEN_NOTE,
  TREND_ALERTS_UNREADABLE_NOTE,
  TREND_BUCKET_OPTIONS,
  TREND_DEFAULT_BUCKETS,
  TREND_DENIED_TITLE,
  TREND_FACE_DENIED,
  TREND_FACE_FAILED,
  TREND_FACE_INVALID,
  TREND_FACE_LOADING,
  TREND_FACE_MALFORMED,
  TREND_FACE_NEVER,
  TREND_FACE_READY,
  TREND_FACE_STORAGE,
  TREND_FAILED_TITLE,
  TREND_INVALID_TITLE,
  TREND_MAX_BUCKETS,
  TREND_MALFORMED_TITLE,
  TREND_PATH,
  TREND_STORAGE_TITLE,
  TREND_UNDATED_CLEAR_NOTE,
  trendUndatedNote,
  TREND_ZERO_NOTE,
  trendBlankView,
  trendBucketLabel,
  trendFailureFace,
  trendHasNumbers,
  trendRequestParams,
} from '../dashboard'

function point(bucket, documents, datasets, extra = {}) {
  return {
    bucket,
    start: `${bucket}-01`,
    documents,
    documents_ready: documents,
    datasets,
    ...extra,
  }
}

/** 服务端有告警权那一档：每枚桶都带 alerts 与 alerts_open。 */
function adminSeries() {
  return [
    point('2026-08', 2, 0, { alerts: 1, alerts_open: 0 }),
    point('2026-09', 6, 3, { alerts: 4, alerts_open: 2 }),
  ]
}

function adminPayload(overrides = {}) {
  return {
    generated_for: 'finance-manager',
    period: 'month',
    buckets: 2,
    time_zone: 'Asia/Shanghai',
    series: adminSeries(),
    undated: { documents: 0, documents_ready: 0, datasets: 0, alerts: 0, alerts_open: 0 },
    ...overrides,
  }
}

/** staff 那一档：两枚键在任何一桶里都不出现（不是 0，也不是 null）。 */
function staffPayload() {
  const series = adminSeries().map(row => {
    const copy = { ...row }
    delete copy.alerts
    delete copy.alerts_open
    return copy
  })
  const undated = { ...adminPayload().undated }
  delete undated.alerts
  delete undated.alerts_open
  return adminPayload({ series, undated })
}

function ok(data) {
  return { status: 200, data }
}

function axiosError(status, detail) {
  return { response: { status, data: { detail } } }
}

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
})

describe('R341⑤ · 参数照后端走', () => {
  it('默认就是服务端那对默认值，取值域也只认月/周与 1..60', () => {
    expect(trendRequestParams({})).toEqual({ period: 'month', buckets: TREND_DEFAULT_BUCKETS })
    expect(trendRequestParams({ period: 'week', buckets: TREND_MAX_BUCKETS })).toEqual({ period: 'week', buckets: 60 })
    expect(trendRequestParams({ period: 'quarter' })).toBe(null)
    expect(trendRequestParams({ buckets: 61 })).toBe(null)
    expect(trendRequestParams({ buckets: 0 })).toBe(null)
    expect(trendRequestParams({ buckets: 2.5 })).toBe(null)
    expect(trendRequestParams({ buckets: 'abc' })).toBe(null)
  })

  it('界面给的档位一格一格对上后端上限，最大那一档就是 60', () => {
    expect(TREND_BUCKET_OPTIONS.map(item => item.value)).toEqual([6, 12, 24, TREND_MAX_BUCKETS])
  })

  it('请求只打这一条路径，period 与 buckets 原样进查询参数', async () => {
    http.get.mockResolvedValue(ok(adminPayload()))
    await loadDashboardTrend({ period: 'week', buckets: 60 })
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(http.get.mock.calls[0][0]).toBe(TREND_PATH)
    expect(http.get.mock.calls[0][1].params).toEqual({ period: 'week', buckets: 60 })
    expect(http.get.mock.calls.some(call => call[0] === SUMMARY_PATH)).toBe(false)
  })

  it('参数不合法时那一发请求压根不发，直接给「参数没有被接受」那张脸', async () => {
    const view = await loadDashboardTrend({ period: 'month', buckets: 61 })
    expect(http.get).toHaveBeenCalledTimes(0)
    expect(view.face).toBe(TREND_FACE_INVALID)
    expect(view.title).toBe(TREND_INVALID_TITLE)
    expect(view.rows).toEqual([])
  })
})

describe('R341②③ · 只搬回执里的数，单位是条目数', () => {
  it('窗口、时区、期数全部读回执自报值，前端不猜今天是哪一期', () => {
    const view = parseTrendPayload(adminPayload({ period: 'week', buckets: 2 }))
    expect(view.period).toBe('week')
    expect(view.timeZone).toBe('Asia/Shanghai')
    expect(view.buckets).toBe(2)
    expect(view.rows.map(row => row.bucket)).toEqual(['2026-08', '2026-09'])
  })

  it('月份与 ISO 周各读成中文；读不成的标签逐字留着，不替它编一个日期', () => {
    expect(trendBucketLabel('month', '2026-09')).toBe('2026 年 9 月')
    expect(trendBucketLabel('week', '2026-W40')).toBe('2026 年第 40 周')
    expect(trendBucketLabel('month', '2026-9')).toBe('2026 年 9 月')
    expect(trendBucketLabel('month', '2026-Q3')).toBe('2026-Q3')
  })

  it('口径句子只说条目数并显式否认金额，占位符仍复用总览那一枚', () => {
    const view = parseTrendPayload(adminPayload())
    const joined = view.notes.join('')
    expect(joined).toContain('这一期新增了几条')
    expect(joined).toContain('文档按条')
    expect(joined).toContain('不是金额')
    expect(joined).not.toMatch(/[¥￥]|万元|元\/|营收/)
    expect(view.windowLabel).toBe('最近 2 个月')
  })

  it('序列之和与聚合数字互不解释：这一层根本不读聚合', () => {
    const view = parseTrendPayload(adminPayload())
    expect(view).not.toHaveProperty('documents')
    expect(view).not.toHaveProperty('datasets')
    expect(view.rows[1].documents).toBe(6)
  })
})

describe('R341④ · 整键缺席不等于 0', () => {
  it('staff 那一档：两列的脸是「没权限」，单元格是 null，不是 0 也不是横杠', () => {
    const view = parseTrendPayload(staffPayload())
    expect(view.alertsState).toBe(ALERT_STATE_DENIED)
    expect(view.alertsColumn).toBe(false)
    expect(view.alertsNote).toBe(TREND_ALERTS_DENIED_NOTE)
    for (const row of view.rows) {
      expect(row.alerts).toBe(null)
      expect(row.alertsOpen).toBe(null)
      expect(row.alerts).not.toBe(0)
      expect(row.alerts).not.toBe(COUNT_PLACEHOLDER)
    }
  })

  it('有权限那一档：两列照数画，并附一句「未闭环按当时回放」的口径', () => {
    const view = parseTrendPayload(adminPayload())
    expect(view.alertsState).toBe(ALERT_STATE_COUNTED)
    expect(view.alertsColumn).toBe(true)
    expect(view.rows.map(row => row.alerts)).toEqual(['1', '4'])
    expect(view.rows.map(row => row.alertsOpen)).toEqual(['0', '2'])
    expect(view.alertsNote).toBe(TREND_ALERTS_OPEN_NOTE)
  })

  // R340 · 口径句子逐字钉：这一句是员工判断「上周那根柱子会不会自己变矮」的唯一依据。
  // 上一枚 it 拿常量名对常量名，证不了措辞有没有跟着服务端翻面，所以这里钉字面。
  it('R340 · 未闭环那一列的句子说的是「每一档自己结束的那一刻」，不再承认当下投影', () => {
    expect(TREND_ALERTS_OPEN_NOTE).toContain('每一档自己结束的那一刻')
    expect(TREND_ALERTS_OPEN_NOTE).toContain('不会回头改写它')
    // 最新那一档没有「已经结束的那一刻」可回放，句子必须自己承认它按当下算。
    expect(TREND_ALERTS_OPEN_NOTE).toContain('最新那一档还没结束')
    expect(TREND_ALERTS_OPEN_NOTE).not.toMatch(/这次请求时刻的处置状态计算|事后回看/)
    // 列名与那一格的口必须一致：标签改了句子没改（或反之）都算屏上留假话。
    expect(TREND_ALERTS_DENIED_NOTE).toContain('其中当时未闭环')
    expect(TREND_ALERTS_OPEN_NOTE).toContain('其中当时未闭环')
  })

  it('键在位但读不出数：整列只画横杠，并按「读不出」说，不冒充 0', () => {
    const broken = adminPayload({
      series: [
        { ...adminSeries()[0], alerts: null, alerts_open: null },
        { ...adminSeries()[1], alerts: 'many', alerts_open: 2 },
      ],
    })
    const view = parseTrendPayload(broken)
    expect(view.alertsState).toBe(ALERT_STATE_UNREADABLE)
    expect(view.alertsColumn).toBe(true)
    expect(view.rows.map(row => row.alerts)).toEqual([COUNT_PLACEHOLDER, COUNT_PLACEHOLDER])
    expect(view.alertsNote).toBe(TREND_ALERTS_UNREADABLE_NOTE)
  })

  it('部分桶带键部分桶不带（服务端自相矛盾）算读不出，不算没权限，也不算 0', () => {
    const without = { ...adminSeries()[1] }
    delete without.alerts
    const view = parseTrendPayload(adminPayload({ series: [adminSeries()[0], without] }))
    expect(view.alertsState).toBe(ALERT_STATE_UNREADABLE)
    expect(view.rows[1].alerts).toBe(COUNT_PLACEHOLDER)
  })
})

describe('R341⑤ · 失败的两张脸分开', () => {
  it('503 是「存储没就绪」：整格失败，没有部分序列可以画', async () => {
    http.get.mockRejectedValue(axiosError(503, 'storage_unavailable'))
    const view = await loadDashboardTrend({})
    expect(view.face).toBe(TREND_FACE_STORAGE)
    expect(view.title).toBe(TREND_STORAGE_TITLE)
    expect(view.rows).toEqual([])
    expect(trendHasNumbers(view)).toBe(false)
  })

  it('422 是「参数没有被接受」，与 503 不同一句', async () => {
    http.get.mockRejectedValue(axiosError(422, 'validation_error'))
    const view = await loadDashboardTrend({})
    expect(view.face).toBe(TREND_FACE_INVALID)
    expect(view.title).toBe(TREND_INVALID_TITLE)
    expect(view.title).not.toBe(TREND_STORAGE_TITLE)
  })

  it('403 是没权限且不给重试；500 就是读不到', async () => {
    http.get.mockRejectedValueOnce(axiosError(403, 'permission_denied'))
    const denied = await loadDashboardTrend({})
    expect(denied.face).toBe(TREND_FACE_DENIED)
    expect(denied.title).toBe(TREND_DENIED_TITLE)
    expect(denied.retryable).toBe(false)
    http.get.mockRejectedValueOnce(axiosError(500, 'internal_error'))
    const failed = await loadDashboardTrend({})
    expect(failed.face).toBe(TREND_FACE_FAILED)
    expect(failed.title).toBe(TREND_FAILED_TITLE)
    expect(failed.retryable).toBe(true)
  })

  it('失败脸不新增错误码：这一层能回传的 code 全在既有字典里', async () => {
    for (const [status, detail] of [[503, 'storage_unavailable'], [422, 'validation_error'], [403, 'permission_denied'], [500, 'internal_error']]) {
      http.get.mockRejectedValueOnce(axiosError(status, detail))
      const view = await loadDashboardTrend({})
      if (view.code) expect(Object.keys(ERROR_CODES), '越界码名：' + view.code).toContain(view.code)
    }
  })
})

describe('R341⑧ · 形状读不出就是失败，不降级成空', () => {
  const brokenCases = {
    'series 不是数组': adminPayload({ series: 'none' }),
    '空序列（服务端从不回空）': adminPayload({ series: [] }),
    'buckets 与序列长度自相矛盾': adminPayload({ buckets: 12 }),
    '时区没有自报': adminPayload({ time_zone: '' }),
    'period 不是那两枚取值': adminPayload({ period: 'quarter' }),
    '一枚桶缺 documents': adminPayload({ buckets: 1, series: [{ bucket: '2026-09', start: '2026-09-01', documents_ready: 1, datasets: 0 }] }),
    '已解析比总数还大': adminPayload({ buckets: 1, series: [point('2026-09', 2, 0, { documents_ready: 5 })] }),
    '桶标签缺失': adminPayload({ buckets: 1, series: [{ start: '2026-09-01', documents: 1, documents_ready: 1, datasets: 0 }] }),
  }
  for (const [name, payload] of Object.entries(brokenCases)) {
    it(`${name} -> parseTrendPayload 回 null`, () => {
      expect(parseTrendPayload(payload)).toBe(null)
    })
  }

  it('200 但形状坏了：走「读不出数」那张脸，不是空态、也不是零新增', async () => {
    http.get.mockResolvedValue(ok({ generated_for: 'boss', period: 'month', buckets: 12, time_zone: 'Asia/Shanghai' }))
    const view = await loadDashboardTrend({})
    expect(view.face).toBe(TREND_FACE_MALFORMED)
    expect(view.title).toBe(TREND_MALFORMED_TITLE)
    expect(trendFailureFace(view)).toBe(TREND_FACE_MALFORMED)
    expect(view.rows).toEqual([])
  })

  it('真·零新增是 ready 加一句说明，数字在位且不许被读成失败', () => {
    const view = parseTrendPayload(adminPayload({
      series: [point('2026-08', 0, 0, { alerts: 0, alerts_open: 0 }), point('2026-09', 0, 0, { alerts: 0, alerts_open: 0 })],
    }))
    expect(view.face).toBe(TREND_FACE_READY)
    expect(view.allZero).toBe(true)
    expect(trendHasNumbers(view)).toBe(true)
    expect(view.rows.map(row => row.documents)).toEqual([0, 0])
    expect(view.rows.map(row => row.documentsWidth)).toEqual(['0%', '0%'])
    expect(view.notes.join('')).toContain(TREND_ZERO_NOTE)
  })

  it('条形与那一格的数同序：最高那格画满，其余等比，零那格收成零长', () => {
    const view = parseTrendPayload(adminPayload())
    expect(view.rows[0].documentsWidth).toBe('33.3%')
    expect(view.rows[1].documentsWidth).toBe('100.0%')
  })

  it('documents 与 documents_ready 是两个数，不许合并成一格', () => {
    const view = parseTrendPayload(adminPayload({
      buckets: 1,
      series: [point('2026-09', 4, 0, { documents_ready: 1, alerts: 0, alerts_open: 0 })],
    }))
    expect(view.rows[0].documents).toBe(4)
    expect(view.rows[0].documentsReady).toBe(1)
    expect(view.notes.join('')).toContain('其中已解析')
  })
})

describe('R341 · 八张脸互斥，读不到与没取过各归各', () => {
  it('never / loading 两张空脸都在说「还没有数」，都不许被读成零新增', () => {
    const never = trendBlankView()
    const loading = trendBlankView(TREND_FACE_LOADING)
    expect(never.face).toBe(TREND_FACE_NEVER)
    expect(loading.face).toBe(TREND_FACE_LOADING)
    expect(never.text).toContain('不画线')
    expect(loading.text).toContain('正在向服务端取')
    expect(never.text).not.toContain('0')
    expect(trendHasNumbers(never)).toBe(false)
    expect(trendFailureFace(never)).toBe('')
    expect(trendFailureFace(loading)).toBe('')
  })

  it('ready 不算失败脸，五张失败脸各归各', () => {
    expect(trendFailureFace({ face: TREND_FACE_READY })).toBe('')
    for (const face of [TREND_FACE_DENIED, TREND_FACE_STORAGE, TREND_FACE_INVALID, TREND_FACE_MALFORMED, TREND_FACE_FAILED]) {
      expect(trendFailureFace({ face })).toBe(face)
    }
  })
})

describe("R342 · 「没有期间」那一格是回包的一部分，不是可选装饰", () => {
  const undatedOf = over => ({ ...adminPayload().undated, ...over })

  it("整块缺席就是读不出数：不许当成「一律有期间」，也不许当成 0", () => {
    const bare = { ...adminPayload() }
    delete bare.undated
    expect(parseTrendPayload(bare)).toBe(null)
    expect(parseTrendPayload(adminPayload({ undated: null }))).toBe(null)
    expect(parseTrendPayload(adminPayload({ undated: [] }))).toBe(null)
  })

  it("三本核心账缺任意一枚、或形状读不出数，都算回包坏了", () => {
    for (const key of ["documents", "documents_ready", "datasets"]) {
      const missing = undatedOf({})
      delete missing[key]
      expect(parseTrendPayload(adminPayload({ undated: missing }))).toBe(null)
      expect(parseTrendPayload(adminPayload({ undated: undatedOf({ [key]: "" }) }))).toBe(null)
      expect(parseTrendPayload(adminPayload({ undated: undatedOf({ [key]: -1 }) }))).toBe(null)
    }
  })

  it("桶里没有告警列时 undated 也不许带告警键：那等于把告警账本递给没权限的账号", () => {
    const leak = staffPayload()
    leak.undated = undatedOf({ alerts: 3, alerts_open: 3 })
    expect(parseTrendPayload(leak)).toBe(null)
    const short = adminPayload()
    delete short.undated.alerts_open
    expect(parseTrendPayload(short)).toBe(null)
  })

  it("读得出来就逐字搬进视图：一个数都不许多算，也不许少算", () => {
    const view = parseTrendPayload(adminPayload({ undated: undatedOf({ datasets: 4, alerts: 2, alerts_open: 1 }) }))
    expect(view.undated).toEqual({ documents: 0, documents_ready: 0, datasets: 4, alerts: 2, alerts_open: 1 })
    expect(view.rows.map(row => row.datasets)).toEqual([0, 3])
    expect(view.notes).toHaveLength(5)
  })

  it("文案：一格里都没有才说「没有报出」，有 N 就说 N，绝不把 N 写成 0", () => {
    expect(trendUndatedNote(undatedOf({}))).toBe(TREND_UNDATED_CLEAR_NOTE)
    const note = trendUndatedNote(undatedOf({ documents: 2, datasets: 3, alerts: 1 }))
    expect(note).toContain("另有")
    expect(note).toContain("没有时间")
    expect(note).toContain("未计入上面任何一期")
    expect(note).toContain("2 条文档")
    expect(note).toContain("3 个数据集")
    expect(note).toContain("1 条告警")
    expect(note).not.toMatch(/另有 0|^0 /)
    expect(trendUndatedNote(null)).toBe("")
  })
})

