/**
 * R186 · 后端已经不撒谎了，界面上得有人替它把话说出来
 *
 * R180（并树 4f96cb6）把行级判定写进两枚成功体字段：preview.row_scope
 * （app/api/v1/data.py:132-169 构形、:319 挂上）与 GET /data-files 的 restricted
 * （app/api/v1/data.py:240-249）。改之前整棵前端一个字都不读它们（全 src 只有
 * src/lib/errcodes.js 的 error-envelope 一族认得 row_scope_denied），所以员工看到的仍是
 * 「列表空空、预览空白」= 与「不存在」长得一模一样 —— R163 归的 B 类病在界面层的最后一公里。
 *
 * 三条腿按仓库口径（手法照 r170-empty-profile-render.test.js）：
 *   ① 真逻辑：跑 DataPanel 自己的 setup，只换网络层，走真的 loadDataFiles → selectDataFile
 *      → applyDataPreview，行级结论从真载荷流到真 computed；
 *   ② 真产物：同一份绑定交给组件自己的 render 出真 HTML，脸对不对只在这一步才算数；
 *   ③ 源码形状：接线与码名同源钉在源码上（面板没接上的东西，渲染结果就是空响）。
 * 🔴 不放宽既存断言、不 skip、不新增错误码：本文件一枚码都不发明，码名从 app/api/v1/data.py 现取。
 * 🔴 「屏上说了什么」一律读去掉标签与注释之后的文本：SSR 会把模板注释一起吐出来，
 *    拿裸 HTML 扫无依据字样会扫到注释，那是自证清白不是断言。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { readFileSync } from 'node:fs'
import { renderToString } from '@vue/server-renderer'

// 只换网络层：errorDetail / isPermissionDenied 保持真身（同 r170 的手法）。
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

/** 屏上真正被人读到的那几个字。 */
const screen = html => html.replace(/<!--[\s\S]*?-->/g, '').replace(/<[^>]*>/g, '')

/** 后端 message 的原句形状：app/agents/tools.py:925-937 的 department_scope 分支现算那一句。 */
const DENIED_MESSAGE = '本表 3 行属于其他部门，都不在当前账号（部门「财务」）的可见范围内'
/** 判据 2 的无依据字样清单：与 tests/test_tools_row_scope_messaging.py::TestNoGuessing 同族。 */
const CAUSE_WORDS = ['权限', '可见范围', '部门', '标注', '密级', '不属于']
/** 列表那一屏的后端原句（app/api/v1/data.py:244-247 逐字）。 */
const RESTRICTED_MESSAGE = '有 3 个数据文件存在，但不在当前账号的可见范围内；如需访问，请联系管理员核对你的部门归属与文件的部门标注。'

const COLUMNS = ['月份', '区域', '金额']
const PROFILE_COLUMNS = [{ name: '月份', dtype: 'object', missing: 0, missing_pct: 0, unique_values: 4 }]

/** 一份合法的画像：R170 之后空表也是完整形状 + empty 标记，不许再退成 {"error": ...}。 */
function profileOf({ rows, empty }) {
  return {
    rows,
    column_count: COLUMNS.length,
    columns: PROFILE_COLUMNS,
    numeric_columns: [],
    text_columns: ['月份'],
    total_missing: 0,
    empty,
  }
}

/** 预览回包：rowScope 传 undefined 就是「后端没挂这枚键」（契约允许缺席）。 */
function previewPayload({ profileRows, empty, rowScope, rows = [] }) {
  const payload = {
    filename: '销售明细.csv',
    columns: COLUMNS,
    rows,
    truncated: false,
    profile: profileOf({ rows: profileRows, empty }),
  }
  if (rowScope !== undefined) payload.row_scope = rowScope
  return payload
}

/**
 * 跑真 setup → 真的 loadDataFiles（它会自己选中第一个文件并发预览那一枪）→ 组件自己的 render。
 * SSR 不跑 onMounted，所以这一屏的脸只能这样接上真链路。
 */
async function renderPanel({ list = { files: [] }, preview }) {
  http.get.mockImplementation(async url => (url === '/data-files' ? { data: list } : { data: preview }))
  let bindings = null
  const Capture = defineComponent({
    __name: 'R186DataPanelCapture',
    setup(_props, ctx) {
      bindings = DataPanel.setup({}, ctx)
      return () => null
    },
  })
  await renderToString(h(Capture))
  await bindings.loadDataFiles()
  const Probe = defineComponent({ ...DataPanel, __name: 'R186DataPanelProbe', setup: () => bindings })
  const html = await renderToString(h(Probe))
  return { html, text: screen(html), bindings }
}

const deniedPreview = previewPayload({
  profileRows: 0,
  empty: true,
  rowScope: {
    code: 'row_scope_denied',
    reason_code: 'department_scope',
    rows_in: 3,
    rows_visible: 0,
    message: DENIED_MESSAGE,
  },
})

const noVisiblePreview = previewPayload({
  profileRows: 0,
  empty: true,
  // 后端在这一支故意不给 message 键：部门维度一行没藏过时，猜因由就是把没裁的维度说成权限。
  rowScope: { code: 'no_visible_rows', reason_code: 'department_column_missing', rows_in: 7, rows_visible: 0 },
})

const partialPreview = previewPayload({
  profileRows: 40,
  empty: false,
  rowScope: { code: '', reason_code: 'department_scope', rows_in: 120, rows_visible: 40 },
  rows: [{ 月份: '1 月', 区域: '华东', 金额: 10 }],
})

const trulyEmptyPreview = previewPayload({
  profileRows: 0,
  empty: true,
  rowScope: { code: '', reason_code: 'department_scope', rows_in: 0, rows_visible: 0 },
})

const visiblePreview = previewPayload({
  profileRows: 40,
  empty: false,
  rowScope: { code: '', reason_code: 'department_scope', rows_in: 40, rows_visible: 40 },
  rows: [{ 月份: '1 月', 区域: '华东', 金额: 10 }],
})

const oneFileList = {
  files: [{
    filename: '销售明细.csv',
    size: 10,
    size_label: '10 B',
    modified_at: '2026-09-23T10:00:00+08:00',
    extension: '.csv',
    dataset_id: 'ds-1',
    version_id: 'v-1',
    classification: 'internal',
  }],
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('R186 判据 1② · 有行但你不能看全：后端原句上屏，不再顶着「空表」那两个字', () => {
  it('message 原句逐字上屏，标题也说得得出「行存在」', async () => {
    const { html, text, bindings } = await renderPanel({ list: oneFileList, preview: deniedPreview })
    expect(bindings.previewScope.value.face).toBe('denied')
    expect(html).toContain('data-testid="row-scope-denied"')
    expect(text).toContain(DENIED_MESSAGE)
    expect(text).toContain('这份数据文件有行，只是没有显示给你')
    expect(text).not.toContain('undefined')
    expect(text).not.toContain('null')
  })

  it('同一屏不许再说「空表」：后端说它有 3 行，屏上是 0 行可见，不是表里没有', async () => {
    const { text } = await renderPanel({ list: oneFileList, preview: deniedPreview })
    expect(text).not.toContain('空表')
    expect(text).toContain('当前显示 0 行')
  })

  it('不给重试按钮：行级可见范围是账号的确定属性，重发一次还是那批行', async () => {
    const { html } = await renderPanel({ list: oneFileList, preview: deniedPreview })
    expect(html).not.toContain('data-testid="ui-error-retry"')
  })

  it('后端没挂 message 键：本地兜底句照样说得出「行存在」，也仍指回部门归属核对', async () => {
    const noMessage = previewPayload({
      profileRows: 0,
      empty: true,
      rowScope: { code: 'row_scope_denied', reason_code: 'authorization_unavailable', rows_in: 5, rows_visible: 0 },
    })
    const { html, text, bindings } = await renderPanel({ list: oneFileList, preview: noMessage })
    expect(bindings.previewScope.value.message).not.toBe('')
    expect(html).toContain('data-testid="row-scope-denied"')
    expect(text).toContain('这份数据文件里确实有数据行')
    expect(text).toContain('可见范围')
    expect(text).toContain('部门')
  })
})

describe('R186 判据 2 · no_visible_rows：话只能由后端说，前端一个字都不猜因由', () => {
  it('只复述后端已经报过的事实（rows_in 是它的计数），无依据字样一枚都不许上屏', async () => {
    const { html, text, bindings } = await renderPanel({ list: oneFileList, preview: noVisiblePreview })
    expect(bindings.previewScope.value.face).toBe('no-visible')
    expect(html).toContain('data-testid="row-scope-no-visible"')
    // 这一枚放在计数之前：反证 (b) 要求「猜因由」当场就是这枚红，不许被后面的断言挡在前面。
    for (const word of CAUSE_WORDS) {
      expect(text, 'no_visible_rows 这一支屏上出现了「' + word + '」：因由不归前端猜').not.toContain(word)
    }
    expect(text).toContain('共有 7 行')
  })

  it('🔴 不许与 row_scope_denied 共用同一句话：两张脸两两不同，谁都不许变成对方', async () => {
    const denied = await renderPanel({ list: oneFileList, preview: deniedPreview })
    const neutral = await renderPanel({ list: oneFileList, preview: noVisiblePreview })
    expect(neutral.text).not.toContain(DENIED_MESSAGE)
    expect(neutral.text).not.toContain('这份数据文件有行，只是没有显示给你')
    expect(denied.text).not.toContain('这份数据文件没有显示任何一行')
    expect(neutral.bindings.previewScopeNotice.value.description)
      .not.toBe(denied.bindings.previewScopeNotice.value.description)
    expect(neutral.html).not.toBe(denied.html)
  })

  it('它也不许被说成「空表」，更不许退成弹窗里那句「暂无数据」', async () => {
    const { text, bindings } = await renderPanel({ list: oneFileList, preview: noVisiblePreview })
    expect(text).not.toContain('空表')
    expect(text).not.toContain('暂无数据')
    expect(bindings.previewModalError.value).toContain('共有 7 行')
  })
})

describe('R186 判据 1③ · 只裁掉一部分：明说全表 N 行、可见 M 行', () => {
  it('统计行分成两个数说，M 不许冒充这张表的总行数', async () => {
    const { text, bindings } = await renderPanel({ list: oneFileList, preview: partialPreview })
    expect(bindings.previewScope.value.face).toBe('partial')
    expect(text).toMatch(/40 行 × 3 列 · 全表 120 行中，当前账号可见的 40 行/)
  })

  it('正常答案不披失败的外衣：这一支不出错误框，也不说「空表」', async () => {
    const { html, text, bindings } = await renderPanel({ list: oneFileList, preview: partialPreview })
    expect(html).not.toContain('data-testid="ui-error-state"')
    expect(html).not.toContain('row-scope-')
    expect(text).not.toContain('空表')
    // 行本身交给预览弹窗（面板这一格只画画像），但那一格必须拿到可见的那 1 行、且不披错误文案。
    expect(bindings.tableRows.value).toHaveLength(1)
    expect(bindings.previewModalError.value).toBe('')
  })
})

describe('R186 判据 1① · 真没有：走 R170 的 empty 画像口径，一个字都不许串成权限话', () => {
  it('code 空串 + rows_in 0：说的还是「空表，尚无数据行」，屏上没有一枚权限词', async () => {
    const { html, text, bindings } = await renderPanel({ list: oneFileList, preview: trulyEmptyPreview })
    expect(bindings.previewScope.value).toBe(null)
    expect(text).toMatch(/0 行 × 3 列 · 空表，尚无数据行/)
    expect(html).not.toContain('row-scope-')
    for (const word of CAUSE_WORDS) {
      expect(text, '真空表被串成了权限话：屏上出现了「' + word + '」').not.toContain(word)
    }
  })

  it('全部可见（rows_in === rows_visible > 0）也不许多说话', async () => {
    const { html, text, bindings } = await renderPanel({ list: oneFileList, preview: visiblePreview })
    expect(bindings.previewScope.value).toBe(null)
    expect(text).toContain('40 行 × 3 列')
    expect(text).not.toContain('全表')
    expect(html).not.toContain('row-scope-')
  })

  it('后端根本没挂 row_scope 键（上传回包、旧响应）：口径逐字回到 R170', async () => {
    const legacy = previewPayload({ profileRows: 0, empty: true, rowScope: undefined })
    const { html, text } = await renderPanel({ list: oneFileList, preview: legacy })
    expect(text).toMatch(/0 行 × 3 列 · 空表，尚无数据行/)
    expect(html).not.toContain('row-scope-')
  })

  it('三张脸互不相同：①/②/②b 两两的屏上文本不许相等', async () => {
    const empty = await renderPanel({ list: oneFileList, preview: trulyEmptyPreview })
    const denied = await renderPanel({ list: oneFileList, preview: deniedPreview })
    const neutral = await renderPanel({ list: oneFileList, preview: noVisiblePreview })
    const partial = await renderPanel({ list: oneFileList, preview: partialPreview })
    const faces = [empty.text, denied.text, neutral.text, partial.text]
    expect(new Set(faces).size).toBe(4)
  })
})

describe('R186 判据 1④ · 列表那一屏：有 N 个存在但你看不见，且不点名文件', () => {
  const restrictedList = {
    ...oneFileList,
    restricted: { count: 3, reason_codes: ['department_scope_denied'], message: RESTRICTED_MESSAGE },
  }

  it('后端原句逐字上屏，标题给出 N，屏上不出现任何一枚没点名的文件名', async () => {
    const { html, text, bindings } = await renderPanel({ list: restrictedList, preview: visiblePreview })
    expect(bindings.restrictedNotice.value.count).toBe(3)
    expect(html).toContain('data-testid="data-files-restricted"')
    expect(text).toContain('还有 3 个数据文件没有列在这里')
    expect(text).toContain(RESTRICTED_MESSAGE)
    // 后端没给名字，界面也不许自己补：这一屏只可能出现看得起的那一枚。
    for (const hidden of ['薪酬汇总.csv', '工资明细.csv', '人事表.xlsx']) {
      expect(text, '看不见的那 N 个被点名了：' + hidden).not.toContain(hidden)
    }
    expect(text).toContain('销售明细.csv')
  })

  it('不给重试按钮：被文件级授权拒掉的那些，重发一次还是拒', async () => {
    const { html } = await renderPanel({ list: restrictedList, preview: visiblePreview })
    expect(html).not.toContain('data-testid="ui-error-retry"')
  })

  it('列表一枚都没有 + 有 N 个被藏起来：空态那句「暂无数据文件」必须闭嘴', async () => {
    const onlyHidden = {
      files: [],
      restricted: { count: 2, reason_codes: ['department_scope_denied'], message: '有 2 个数据文件存在，但不在当前账号的可见范围内。' },
    }
    const { html, text } = await renderPanel({ list: onlyHidden, preview: visiblePreview })
    expect(html).toContain('data-testid="data-files-restricted"')
    expect(text).toContain('有 2 个数据文件存在')
    expect(text, '同一屏既说「暂无数据文件」又说有 2 个看不见 = 一句话自相矛盾').not.toContain('暂无数据文件')
  })

  it('真的一枚都没有：空态照旧说「暂无数据文件」，也不凭空造出提示块', async () => {
    const { html, text, bindings } = await renderPanel({ list: { files: [] }, preview: visiblePreview })
    expect(bindings.restrictedNotice.value).toBe(null)
    expect(text).toContain('暂无数据文件')
    expect(html).not.toContain('data-files-restricted')
    for (const word of CAUSE_WORDS) {
      expect(text, '真空列表被说成了权限问题：屏上出现了「' + word + '」').not.toContain(word)
    }
  })

  it('restricted 没给 message 键：兜底句照样说得出「存在」，仍不点名', async () => {
    const noMessage = { ...oneFileList, restricted: { count: 1, reason_codes: ['clearance_insufficient'] } }
    const { text } = await renderPanel({ list: noMessage, preview: visiblePreview })
    expect(text).toContain('有数据文件存在，但不在当前账号的可见范围内')
    expect(text).toContain('还有 1 个数据文件没有列在这里')
  })

  it('后端不挂键 = 这里一个字都不说（不许把「没说过」读成「有 N 个」）', async () => {
    const { html } = await renderPanel({ list: oneFileList, preview: visiblePreview })
    expect(html).not.toContain('data-files-restricted')
  })

  it('重载先清陈话：上一轮的 restricted 不许留成这一轮的拒绝', async () => {
    http.get.mockResolvedValue({ data: restrictedList })
    let bindings = null
    const Capture = defineComponent({
      __name: 'R186StaleCapture',
      setup(_props, ctx) {
        bindings = DataPanel.setup({}, ctx)
        return () => null
      },
    })
    await renderToString(h(Capture))
    await bindings.loadDataFiles()
    expect(bindings.restrictedNotice.value).not.toBe(null)
    let release
    http.get.mockImplementation(() => new Promise((resolve, reject) => { release = reject }))
    const pending = bindings.loadDataFiles()
    expect(bindings.restrictedNotice.value, '请求还在飞，屏上却还挂着上一轮的结论').toBe(null)
    release(new Error('boom'))
    await pending
  })
})

describe('R186 判据 3/7 · 接线、码名同源与零裸色', () => {
  it('预览弹窗那一格：拒绝句走已有的 error 通道喂进去，且那条通道在弹窗里排在表格之前', async () => {
    const { bindings, text } = await renderPanel({ list: oneFileList, preview: deniedPreview })
    // ① 真逻辑：喂给弹窗 error prop 的那个值就是后端原句（空表那一支才不会开口说「暂无数据」）。
    expect(bindings.previewModalError.value).toBe(DENIED_MESSAGE)
    // ② 源码形状：DataPanel 真的把这枚 computed 绑上去了，没继续绑裸的 previewError。
    const dataPanel = source('../DataPanel.vue')
    expect(dataPanel).toContain(':error="previewModalError"')
    expect(dataPanel).not.toContain(':error="previewError"')
    // ③ 跨文件形状：弹窗自己的分支顺序决定这枚 prop 管不管用 —— error 必须排在表格那支之前。
    const modal = source('../DocumentPreviewModal.vue')
    expect(modal.indexOf('v-else-if="error"')).toBeGreaterThan(-1)
    expect(modal.indexOf('v-else-if="error"')).toBeLessThan(modal.indexOf('class="preview-state">暂无数据'))
    expect(text).toContain(DENIED_MESSAGE)
  })

  it('面板读的就是后端那两枚键（源码形状）', () => {
    const dataPanel = source('../DataPanel.vue')
    expect(dataPanel).toContain('data.row_scope')
    expect(dataPanel).toContain('res.data.restricted')
    expect(dataPanel).toContain('v-if="restrictedNotice"')
    expect(dataPanel).toContain('v-if="previewScopeNotice"')
  })

  it('两枚码的名字与后端契约同源：前端不许自造码名', () => {
    const dataPanel = source('../DataPanel.vue')
    const route = source('../../../../app/api/v1/data.py')
    const front = name => new RegExp('const ' + name + " = '([^']+)'").exec(dataPanel)?.[1]
    const back = name => new RegExp('^' + name + ' = "([^"]+)"', 'm').exec(route)?.[1]
    expect(front('ROW_SCOPE_DENIED')).toBe(back('ROW_SCOPE_DENIED'))
    expect(front('NO_VISIBLE_ROWS')).toBe(back('NO_VISIBLE_ROWS'))
    expect(front('ROW_SCOPE_DENIED')).toBe('row_scope_denied')
    expect(front('NO_VISIBLE_ROWS')).toBe('no_visible_rows')
  })

  it('新文案全部走原语：DataPanel 的 style 里一枚裸色值都没有，错误出口仍只有 UiErrorState', () => {
    const dataPanel = source('../DataPanel.vue')
    const style = dataPanel.slice(dataPanel.indexOf('<style'))
    expect(style).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(style).not.toMatch(/\b(?:rgba?|hsla?)\(/)
    expect(style).not.toMatch(/text-shadow/)
    // filesError / fileDeleteError / previewError / row_scope 那一屏 / restricted 那一屏
    expect(dataPanel.match(/<UiErrorState/g)).toHaveLength(5)
    expect(dataPanel).not.toMatch(/class="data-state/)
  })

  it('喂料屏那一格挂的就是这块面板：行级提示跟着它一起上屏（接线，FeedPanel 一字节未改）', async () => {
    const { FEED_TABS } = await import('../../router/feed-tabs.js')
    const tab = FEED_TABS.find(item => item.component === DataPanel)
    expect(tab, '喂料屏的数据标签不再是 DataPanel：这一屏的脸要跟着改地方说').toBeTruthy()
    const feed = source('../FeedPanel.vue')
    expect(feed).toContain('tab.component')
  })
})