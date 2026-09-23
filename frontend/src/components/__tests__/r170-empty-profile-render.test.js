/**
 * R170 · 数据面板：后端把「有列无行」当错误回的那一刻，界面不许在渲染期抛错
 *
 * 缺陷链（R169 验收扫出，本文件钉前端这一头）：
 *   app/tools/excel.py 的 profile_dataframe 对 0 行的帧回 `{"error": "数据为空"}`
 *   → data.py 的 build_dataframe_preview 原样塞进 profile
 *   → DataPanel.vue 的 `v-if="profile"` 判真，统计行读 `profile.column_count || profile.columns.length`
 *   → 错误 dict 里没有 columns → `undefined.length` 在渲染期抛 → 客户上传空表当场崩。
 *
 * 三条腿同仓库既有口径（参照 r169-data-chart.test.js）：
 *   ① 真逻辑：跑 DataPanel 自己的 setup，网络层换成进程内假实现，走真的 selectDataFile → applyDataPreview；
 *   ② 真产物：把同一份绑定交给 DataPanel 自己的 render 出真 HTML，崩溃点就在这一步；
 *   ③ 跨层形状：后端 excel.py 若被改回 `{"error": ...}` 那一支，本文件的源码钉一起红。
 * 🔴 不放宽断言、不 skip：①② 是改前就红的两枚真钉。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { readFileSync } from 'node:fs'
import { renderToString } from '@vue/server-renderer'

// 只换网络层：errorDetail / isPermissionDenied 保持真身（同 r169 的手法）。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }
})
vi.mock('../../lib/artifacts', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, fetchArtifactBlob: vi.fn() }
})

import { http } from '../../lib/http'
import DataPanel from '../DataPanel.vue'

const source = path => readFileSync(new URL(path, import.meta.url), 'utf8').replace(/\r\n/g, '\n')

/**
 * 跑真 setup 拿绑定 → 用进程内假 http 走真的 selectDataFile → 再用组件自己的 render 渲一次。
 * SSR 不跑 onMounted，所以「选中一个文件之后画什么」只能这样接上真链路。
 */
async function renderPreview(payload) {
  http.get.mockResolvedValue({ data: payload })
  let bindings = null
  const Capture = defineComponent({
    __name: 'R170DataPanelCapture',
    setup(_props, ctx) {
      bindings = DataPanel.setup({}, ctx)
      return () => null
    },
  })
  await renderToString(h(Capture))
  await bindings.selectDataFile(payload.filename)
  expect(bindings.profile.value, '假 http 的 profile 应原样落到组件状态里').toBeTruthy()

  const Probe = defineComponent({ ...DataPanel, __name: 'R170DataPanelProbe', setup: () => bindings })
  return await renderToString(h(Probe))
}

/** 改之前后端对「只有表头」的那张表真实回的东西，一字不改。 */
const BROKEN_EMPTY_PROFILE = { error: '数据为空' }

/** 修之后后端该回的空表画像：形状完整 + 一枚诚实的空表标记（契约见 tests/test_r170_header_only_dataframe_profile.py）。 */
const EMPTY_TABLE_PROFILE = {
  rows: 0,
  column_count: 1,
  columns: [{ name: '月份', dtype: 'object', missing: 0, missing_pct: 0.0, unique_values: 0 }],
  numeric_columns: [],
  text_columns: ['月份'],
  total_missing: 0,
  empty: true,
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('R170 · 错误形状的画像不许把面板炸掉', () => {
  it('后端只回 {"error": ...}：渲染不许抛，也不许把 undefined 印到屏上', async () => {
    const html = await renderPreview({
      filename: '全年预算.csv',
      columns: ['月份'],
      rows: [],
      truncated: false,
      profile: BROKEN_EMPTY_PROFILE,
    })
    expect(html).not.toContain('undefined')
  })

  it('非画像的载荷不进画像卡：错误不该被渲染成一张「0 列的画像」', async () => {
    const html = await renderPreview({
      filename: '全年预算.csv',
      columns: ['月份'],
      rows: [],
      truncated: false,
      profile: BROKEN_EMPTY_PROFILE,
    })
    // 认卡不认文案：卡整块不该出现，逐列行也不该出现（错误被说成一次统计 = 本单的崩溃现场）
    expect(html).not.toContain('class="profile-card"')
    expect(html).not.toContain('col-item')
  })

  it('列数只从画像里带防的通道取：未防空的那处读取位不许回来', () => {
    const dataPanel = source('../DataPanel.vue')
    expect(dataPanel).toContain('profile.column_count || profile.columns?.length')
    expect(dataPanel).not.toContain('profile.columns.length')
    expect(dataPanel).toContain('v-if="profile && !profile.error"')
  })
})

describe('R170 · 有列无行是一张合法的空表画像', () => {
  it('0 行 × 1 列照原样上屏，列名一格不少', async () => {
    const html = await renderPreview({
      filename: '全年预算.csv',
      columns: ['月份'],
      rows: [],
      truncated: false,
      profile: EMPTY_TABLE_PROFILE,
    })
    expect(html).toContain('class="profile-card"')
    expect(html).toContain('📋 数据画像')
    expect(html).toMatch(/0 行 × 1 列/)
    expect(html).toContain('月份')
    expect(html).not.toContain('undefined')
    expect(html).not.toContain('null')
  })

  it('空表要让人看得懂：0 行不等于统计失败', async () => {
    const html = await renderPreview({
      filename: '全年预算.csv',
      columns: ['月份'],
      rows: [],
      truncated: false,
      profile: EMPTY_TABLE_PROFILE,
    })
    expect(html).toContain('空表')
    expect(http.get).toHaveBeenCalledTimes(1)
  })
})

describe('R170 · 跨层反证：后端改回裸错误那一支，这里也红', () => {
  it('excel.py 不再对 0 行的帧吐 {"error": "数据为空"}', () => {
    const excel = source('../../../../app/tools/excel.py')
    expect(excel).not.toContain('"数据为空"')
    expect(excel).toContain('"empty": ')
  })
})
