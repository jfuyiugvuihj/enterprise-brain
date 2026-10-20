/**
 * R182 · 文本列要真的出现在屏上，不是只在 JSON 里多一个字段
 *
 * 缺陷链（总控 2026-09-23 主树亲跑）：
 *   pandas 3.0.3 把字符串列判成 `str`，app/tools/excel.py 的文本列那一支比的是字面 "object"
 *   → profile 里 text_columns 为空、每列的 unique_values 永远不发
 *   → DataPanel.vue 的列卡：`col.unique_values !== undefined` 那一格永远不进，
 *     typeIcon 又按 dtype 串挑图标，`str` 谁都不认 -> 落进兜底的 📦
 *   => 客户真文档的「文本列」区块常年空白：界面在说「这台机器上没有文本列」。
 *
 * 三条腿：
 *   ① 真产物：下面两份 profile JSON 都是后端实跑交回的原文（RENDERED_PROFILE 取修复后的
 *      profile_dataframe，BLIND_PROFILE 取修复前 HEAD `218bd6e` 同一张帧的输出），手改一个字都不许；
 *   ② 真渲染：跑 DataPanel 自己的 setup，走真的 selectDataFile → applyDataPreview，
 *      再用组件自己的 render 出真 HTML（同 r170-empty-profile-render.test.js 的手法）；
 *   ③ 源码钉：typeIcon 认 `str` 这件事被改回去，本文件立刻红。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { readFileSync } from 'node:fs'
import { renderToString } from '@vue/server-renderer'

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

/** 同一张真字符串帧：`月份` / `部门` 在 pandas 3 里判成 str，`额` 是 float64 且缺一格。 */
const RENDERED_PROFILE = {
  rows: 3,
  columns: [
    { name: '月份', dtype: 'str', missing: 0, missing_pct: 0.0, unique_values: 3 },
    { name: '部门', dtype: 'str', missing: 0, missing_pct: 0.0, unique_values: 2 },
    { name: '额', dtype: 'float64', missing: 1, missing_pct: 33.3, min: 10.0, max: 20.0, mean: 15.0, sum: 30.0 },
  ],
  column_count: 3,
  empty: false,
  numeric_columns: ['额'],
  text_columns: ['月份', '部门'],
  total_missing: 1,
}

/** 修复前的后端对同一张帧真实回的东西，一字不改：文本列名单是空的，两列都没有 unique_values。 */
const BLIND_PROFILE = {
  rows: 3,
  columns: [
    { name: '月份', dtype: 'str', missing: 0, missing_pct: 0.0 },
    { name: '部门', dtype: 'str', missing: 0, missing_pct: 0.0 },
    { name: '额', dtype: 'float64', missing: 1, missing_pct: 33.3, min: 10.0, max: 20.0, mean: 15.0, sum: 30.0 },
  ],
  column_count: 3,
  empty: false,
  numeric_columns: ['额'],
  text_columns: [],
  total_missing: 1,
}

async function renderPreview(payload) {
  http.get.mockResolvedValue({ data: payload })
  let bindings = null
  const Capture = defineComponent({
    __name: 'R182DataPanelCapture',
    setup(_props, ctx) {
      bindings = DataPanel.setup({}, ctx)
      return () => null
    },
  })
  await renderToString(h(Capture))
  await bindings.selectDataFile('月度经营.csv')
  expect(bindings.profile.value, '假 http 的 profile 应原样落到组件状态里').toBeTruthy()

  const Probe = defineComponent({ ...DataPanel, __name: 'R182DataPanelProbe', setup: () => bindings })
  const html = await renderToString(h(Probe))
  return { html, cards: () => html.split('class="col-item"').slice(1) }
}

/**
 * 按列名取它那张卡的 HTML：卡的先后顺序由后端画像决定，这里按名字取，不按下标赌。
 * 属性匹配留了容错位 —— SSR 会给元素插 data-v-* 作用域属性，写死 class 的收尾会落空。
 */
function cardOf(cards, name) {
  const card = cards.find(chunk => new RegExp(`class="col-name"[^>]*>\s*${name}\s*<`).test(chunk))
  expect(card, `屏上没有 ${name} 这一列的卡`).toBeTruthy()
  return card
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('R182 · 文本列的卡要真的上屏', () => {
  it('str 列挑中 📝，并且把「多少个不同取值」说出来', async () => {
    const { cards } = await renderPreview({
      filename: '月度经营.csv',
      columns: ['月份', '部门', '额'],
      rows: [],
      truncated: false,
      profile: RENDERED_PROFILE,
    })
    const chunks = cards()

    const month = cardOf(chunks, '月份')
    expect(month).toContain('📝')
    expect(month).toContain('3 个唯一值')
    expect(month).not.toContain('📦')

    const dept = cardOf(chunks, '部门')
    expect(dept).toContain('📝')
    expect(dept).toContain('2 个唯一值')
  })

  it('数值列不被顺手改动：仍是 🔢 与最小/最大/均值那一行', async () => {
    const { cards } = await renderPreview({
      filename: '月度经营.csv',
      columns: ['月份', '部门', '额'],
      rows: [],
      truncated: false,
      profile: RENDERED_PROFILE,
    })
    const amount = cardOf(cards(), '额')

    expect(amount).toContain('🔢')
    expect(amount).toContain('最小 10 · 最大 20 · 均值 15')
    // 一列不许被说两次：数值列的卡上不许同时出现「个唯一值」
    expect(amount).not.toContain('个唯一值')
  })

  it('取值数只落在文本列那两张卡上，整屏不许有空读数', async () => {
    const { html } = await renderPreview({
      filename: '月度经营.csv',
      columns: ['月份', '部门', '额'],
      rows: [],
      truncated: false,
      profile: RENDERED_PROFILE,
    })

    expect(html).not.toContain('undefined')
    expect(html).not.toContain('null')
    expect(html.match(/个唯一值/g)).toHaveLength(2)
  })
})

describe('R182 · 病灶留档：后端不发这一格时，界面自己变不出来', () => {
  it('修复前那份真产物渲染出来，文本列一格取值数都没有', async () => {
    const { cards } = await renderPreview({
      filename: '月度经营.csv',
      columns: ['月份', '部门', '额'],
      rows: [],
      truncated: false,
      profile: BLIND_PROFILE,
    })
    const chunks = cards()

    expect(chunks).toHaveLength(3)
    for (const name of ['月份', '部门']) {
      expect(cardOf(chunks, name)).not.toContain('个唯一值')
    }
  })
})

describe('R182 · 跨层反证：图标判定改回只认 object，这里也红', () => {
  it('typeIcon 认 pandas 3 的字符串 dtype，不再只认 object', () => {
    const dataPanel = source('../DataPanel.vue')
    const icon = dataPanel.slice(dataPanel.indexOf('function typeIcon'))

    expect(icon).toContain("dtype === 'str'")
    expect(icon).toContain("dtype === 'string'")
    expect(icon).toContain("dtype.includes('object')")
  })

  it('excel.py 里那处字面 dtype 比较不许回来', () => {
    const excel = source('../../../../app/tools/excel.py')

    expect(excel).not.toContain('"object"')
    expect(excel).not.toContain("'object'")
    expect(excel).not.toContain('dtype ==')
    expect(excel).toContain('pd.api.types.is_string_dtype')
  })
})