/**
 * R410 · 驾驶舱那八枚裸 <button> 接进 ./ui 的 UiButton：屏上逐枚对账
 *
 * 病灶（本案卷 docs/handoff/2026-09-27-v2-gap-recheck-2.md §3 R410 那一格，现取自本单基点 5621e8d）：
 *   components/DashboardPanel.vue 里全仓最后一批裸 <button> 八枚，源码开标签现取 8 枚，
 *   r288 乙组的按文件棘轮（:52 'components/DashboardPanel.vue': 8）与合计棘轮（:56 = 8）
 *   正好贴在那同一个数上。本单把这八枚接进 ./ui 的 UiButton，两格一起降到 0。
 *   八枚的源码行号（改前）：:341 KPI 卡、:451 异常卡头、:464 异常行、:490 文档卡头、
 *   :502 文档行、:519 证据卡头、:544 查询、:551 快速操作。
 *
 * 为什么本件数的是【屏上】而不是【源码字符串】：
 *   r288 那一族的第二棒已经把「拿 /<button/g 数源文件」判成假刀（见 r278-topbar.test.js :79-113
 *   那一段改口记录：源码里数得到的字符串既可以是注释、也可以是根本不渲染的分支）。
 *   本件两腿都跑真组件：甲腿用产品自己那份 ssrRender 出真 HTML 再逐枚抠 <button> 节点，
 *   丙腿挂一次真壳层（createRenderer + 把模板过一遍运行时编译器，手法与 r278 / r307b 同一套）
 *   读渲染节点上真的 onClick 并按下去。桩件不算绿：戊组专钉这一格。
 *
 * 三条对账（任一侧漂了都要红，不许各说各话）：
 *   ① 屏上 21 枚逐枚对照表（甲组）——枚数、类名列表、testid、可见文本、type、disabled 一格一格对。
 *   ② 清单 ↔ 棘轮 ↔ 屏上裸枚数（乙组）——r288 那两格数字 = scanNativeButtons 现取 = 屏上
 *      「该有原语脸却没有」的槽位枚数。只改账（把 8 改 0 而模板不动）→ ②红；
 *      只改脸（把某一枚接回裸 button）→ ②红；换成一件仍渲染原生 button 的包装件
 *      （components/ui 整棵不进扫描面，所以清单会读成 0）→ 屏上那一枚没有 ui-button 脸 → ②红。
 *   ③ 逐枚按下去的落点（丙组）——emit('goto', ?) 的参数序列与改前逐字相同，查询那一枚仍走 lookupMetric。
 *
 * 改前读数（K0 影子：git clone --no-hardlinks 纯净基点 5621e8d，同夹具同腿跑出来的，
 * 不是我推的、也不是照抄派工词）：屏上 21 枚，其中 17 枚画在八枚裸 <button> 上
 * （KPI 4 + 异常行 2 + 文档行 3 + 快速操作 4 + 三枚卡头「查看全部 ›」+「查询」），
 * 另 4 枚本来就是原语：卡头「去上传数据 ›」与「按月 / 按周」（R341）各带 ui-button 档类，
 * UiSelect 那一枚触发件带 ui-select__trigger。逐枚字段与落点序列抄在本件下方 EXPECTED 表里。
 *
 * 反证（本单实跑，跑完按字节还原并复验 sha256）：
 *   刀A 只改账：两格棘轮保持 0、把 :502 文档行接回裸 <button> ⇒ 乙2 红（现取 1 ≠ 屏上 0）、
 *       r288 乙组「只减不增」与「合计一格不差等于上限」一起红；
 *   刀B 假包装：把 :544「查询」换成 components/ui 里一枚只转发原生 button 的件 ⇒ 清单仍读 0，
 *       乙2 与甲组那一枚的类名断言红（它渲染成真的 button 却没有原语脸）；
 *   刀C 摘断言：摘掉 r288 乙组「全仓裸按钮欠账只减不增」那整条 it ⇒ 刀A 那一把仍然红
 *       （「合计一格不差等于上限」与本件乙2 两条都盯着），证明这条断言摘不掉东西；
 *   刀D 摘本件的屏上腿：把 EXPECTED 表里某一枚的 ui-button 档类改成手写类名 ⇒ 戊组红。
 *
 * 本件不做的两件事（写在这里，别当成验过了）：
 *   · 像素、hover 底色、焦点环宽度不起浏览器验不了（vitest 里 css:false，见 vitest.config.js）。
 *     丁组只钉「复位名单在不在、有没有偷添裸色值、!important 有没有用」，
 *     改前改后的计算值对账与那三处 hover 让位记在回执的诚实账里。
 *   · 后端、路由、其它屏一概不管：emit('goto') 的落点归 App.vue 的 openScreen，本件只验参数没换。
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, getCurrentInstance, h, nextTick } from 'vue'
import { renderToString } from '@vue/server-renderer'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn() } }
})

import { http } from '../../lib/http'
import DashboardPanel from '../DashboardPanel.vue'
import { SUMMARY_PATH, TREND_PATH } from '../../lib/dashboard'
import { UiButton, UiEmptyState, UiErrorState, UiLoadingState, UiSelect } from '../ui'
import { countNativeButtons, scanNativeButtons, stripComments } from './r288-native-button-scan.js'

const TESTS_DIR = dirname(fileURLToPath(import.meta.url))
const SRC_ROOT = join(TESTS_DIR, '..', '..')
const readSrc = rel => readFileSync(join(SRC_ROOT, rel), 'utf8').replace(/\r\n/g, '\n')
const panelSource = readSrc('components/DashboardPanel.vue')
const panelCode = stripComments(panelSource)
const ratchetSource = readSrc(join('components', '__tests__', 'r288-native-buttons.test.js'))
const chr39 = String.fromCharCode(39)
const chr34 = String.fromCharCode(34)
const GUARD_FILE = 'components/__tests__/r288-native-buttons.test.js'

// ==================== 夹具：一屏全都有数（改前改后同一份，两侧才可比） ====================

const SUMMARY = {
  generated_for: 'boss',
  pending_approvals: 1,
  documents: 3,
  datasets: 2,
  alerts: { total: 2, unread: 1 },
}
// 三行文档三档解析状态、两档索引状态：文档行那一枚的可访问名逐字来自这几行。
const CATALOG = [
  { filename: 'a.pdf', parse_status: 'ready', index_status: 'indexed' },
  { filename: 'b.pdf', parse_status: 'parsing', index_status: 'excluded' },
  { filename: 'c.pdf', parse_status: 'pending' },
]
const ALERTS = [
  { id: 7, rule_id: 3, message: '差旅报销单超 3 日未审批', ai_analysis: '', created_at: '2026-09-25T09:12:00Z', department: '财务', status: 'open' },
  { id: 8, rule_id: 4, message: '库存周转天数 42 大于阈值 30', ai_analysis: '建议看超时清单', created_at: '2026-09-26T02:40:00Z', department: '供应链', status: 'resolved' },
]
/** 趋势回包按契约自洽（buckets === series.length、时区自报、period 取服务端认的那两枚）。 */
function trendPoint(bucket, documents, ready, datasets, alerts, alertsOpen) {
  return { bucket, start: bucket + '-01', documents, documents_ready: ready, datasets, alerts, alerts_open: alertsOpen }
}
const TREND = {
  generated_for: 'boss',
  period: 'month',
  buckets: 2,
  time_zone: 'Asia/Shanghai',
  series: [trendPoint('2026-08', 2, 1, 3, 4, 0), trendPoint('2026-09', 6, 4, 1, 2, 2)],
  undated: { documents: 0, documents_ready: 0, datasets: 0, alerts: 0, alerts_open: 0 },
}
const MATCH = {
  context: { metric_name: '住宿费标准', source_file: '差旅制度.xlsx', warnings: ['未与已上传制度文件核对'] },
  definition_source: 'metric_definitions',
  provenance: { verified_against_documents: false },
}

function stubRoutes() {
  http.get.mockImplementation(async (url) => {
    if (url === SUMMARY_PATH) return { status: 200, data: SUMMARY }
    if (url === '/documents/catalog') return { status: 200, data: { documents: CATALOG } }
    if (url === '/alerts') return { status: 200, data: { alerts: ALERTS } }
    if (url === TREND_PATH) return { status: 200, data: TREND }
    throw new Error('不该被请求的路径：' + url)
  })
  http.post.mockImplementation(async (url) => {
    if (url === '/semantics/match') return { status: 200, data: MATCH }
    throw new Error('不该被请求的路径：' + url)
  })
}

// ==================== 逐枚对照表（屏上 DOM 顺序，一行一枚，改前读数抄自 K0） ====================

/**
 * primitive: 'slot' = 本单八枚槽位之一（屏上必须带原语脸）；'was' = 改前就已是原语/组件产物，
 * 本单一根手指都不碰，改前改后逐字节相同。
 * own: 这一枚归哪一格槽位（同一槽位的几枚共用一格计数：r288 的清单数的是源码开标签，一格一枚）。
 * cls: 改后屏上类名列表（原语自己排在前面，接的 class 落在后面——顺序本身就是证据）。
 * kls: 改前屏上的类名列表（K0 读数，只有 'was' 两腿才用得上它做逐字节比对）。
 * goto: 按下去 emit('goto', ?) 的参数；null = 不落 goto（查询那一枚走 lookupMetric）。
 * disabled: 改前改后都必须是没有 disabled 属性（这一屏这八枚一枚都不绑 :disabled）。
 */
const EXPECTED = [
  { own: 'kpi', primitive: 'slot', variant: 'secondary', size: 'md', theme: 'reference-kpi tone-blue', testid: 'dashboard-kpi-documents', type: 'button', disabled: false, text: '文档总量3已解析篇数未记录', target: 'docs', goto: 'docs' },
  { own: 'kpi', primitive: 'slot', variant: 'secondary', size: 'md', theme: 'reference-kpi tone-cyan', testid: 'dashboard-kpi-datasets', type: 'button', disabled: false, text: '数据表2可分析', target: 'data', goto: 'data' },
  { own: 'kpi', primitive: 'slot', variant: 'secondary', size: 'md', theme: 'reference-kpi tone-green', testid: 'dashboard-kpi-pendingApprovals', type: 'button', disabled: false, text: '待我审批1等你处理', target: 'approval', goto: 'approval' },
  { own: 'kpi', primitive: 'slot', variant: 'secondary', size: 'md', theme: 'reference-kpi tone-violet', testid: 'dashboard-kpi-alerts', type: 'button', disabled: false, text: '告警2未读 1 条', target: 'insights', goto: 'insights', alertState: 'counted' },
  { own: 'trend-upload', primitive: 'was', kls: 'ui-button ui-button--ghost ui-button--sm', testid: 'ui-button', type: 'button', disabled: false, text: '去上传数据 ›', goto: 'data' },
  { own: 'trend-month', primitive: 'was', kls: 'ui-button ui-button--ghost ui-button--sm', testid: 'ui-button', type: 'button', disabled: false, text: '按月', goto: null, ariaPressed: 'true' },
  { own: 'trend-week', primitive: 'was', kls: 'ui-button ui-button--ghost ui-button--sm', testid: 'ui-button', type: 'button', disabled: false, text: '按周', goto: null, ariaPressed: 'false' },
  { own: 'trend-buckets', primitive: 'was', kls: 'ui-select__trigger', testid: 'ui-select-trigger', type: 'button', disabled: false, text: '近 12 期', goto: null, role: 'combobox' },
  { own: 'goto-insights', primitive: 'slot', variant: 'ghost', size: 'sm', theme: '', testid: 'dashboard-goto-insights', type: 'button', disabled: false, text: '查看全部 ›', goto: 'insights' },
  { own: 'risk-row', primitive: 'slot', variant: 'secondary', size: 'md', theme: 'risk-item', testid: 'dashboard-risk-row', type: 'button', disabled: false, text: '差旅报销单超 3 日未审批2026-09-25 09:12', goto: 'insights' },
  { own: 'risk-row', primitive: 'slot', variant: 'secondary', size: 'md', theme: 'risk-item', testid: 'dashboard-risk-row', type: 'button', disabled: false, text: '库存周转天数 42 大于阈值 302026-09-26 02:40', goto: 'insights' },
  { own: 'goto-docs', primitive: 'slot', variant: 'ghost', size: 'sm', theme: '', testid: 'dashboard-goto-docs', type: 'button', disabled: false, text: '查看全部 ›', goto: 'docs' },
  { own: 'doc-row', primitive: 'slot', variant: 'secondary', size: 'md', theme: 'reference-list-row', testid: 'dashboard-doc-row', type: 'button', disabled: false, text: 'a.pdf已入检索索引已解析', goto: 'docs' },
  { own: 'doc-row', primitive: 'slot', variant: 'secondary', size: 'md', theme: 'reference-list-row', testid: 'dashboard-doc-row', type: 'button', disabled: false, text: 'b.pdf未索引正在解析', goto: 'docs' },
  { own: 'doc-row', primitive: 'slot', variant: 'secondary', size: 'md', theme: 'reference-list-row', testid: 'dashboard-doc-row', type: 'button', disabled: false, text: 'c.pdf索引状态未记录排队待解析', goto: 'docs' },
  { own: 'goto-chat', primitive: 'slot', variant: 'ghost', size: 'sm', theme: '', testid: 'dashboard-goto-chat', type: 'button', disabled: false, text: '查看全部 ›', goto: 'chat' },
  { own: 'lookup', primitive: 'slot', variant: 'primary', size: 'sm', theme: '', testid: 'dashboard-metric-lookup', type: 'button', disabled: false, text: '查询', goto: null },
  { own: 'quick', primitive: 'slot', variant: 'secondary', size: 'md', theme: '', testid: 'dashboard-quick-action', type: 'button', disabled: false, text: '上传文档', goto: 'docs' },
  { own: 'quick', primitive: 'slot', variant: 'secondary', size: 'md', theme: '', testid: 'dashboard-quick-action', type: 'button', disabled: false, text: '数据分析', goto: 'data' },
  { own: 'quick', primitive: 'slot', variant: 'secondary', size: 'md', theme: '', testid: 'dashboard-quick-action', type: 'button', disabled: false, text: '新建洞察', goto: 'insights' },
  { own: 'quick', primitive: 'slot', variant: 'secondary', size: 'md', theme: '', testid: 'dashboard-quick-action', type: 'button', disabled: false, text: '发起审批', goto: 'approval' },
]

/** 八格槽位（r288 清单按源码开标签计，一格一枚），与 EXPECTED 里 primitive='slot' 的行同源。 */
const SLOT_ORDER = ['kpi', 'goto-insights', 'risk-row', 'goto-docs', 'doc-row', 'goto-chat', 'lookup', 'quick']
const slotRows = own => EXPECTED.filter(row => row.own === own)

const expectedClasses = row => (row.primitive === 'was'
  ? row.kls.split(' ')
  : ['ui-button', 'ui-button--' + row.variant, 'ui-button--' + row.size].concat(row.theme.split(' ').filter(Boolean)))

// ==================== 甲腿：SSR 真产物 ====================

async function ssrPanel() {
  stubRoutes()
  let bindings = null
  const Host = {
    name: 'R410SsrHost',
    setup(props, ctx) {
      bindings = DashboardPanel.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Host))
  await bindings.loadDashboard()
  await bindings.lookupMetric()
  await bindings.loadTrend()
  const html = await renderToString(h({ ...DashboardPanel, setup: () => bindings }))
  return { html, bindings }
}

/** 从真 HTML 里逐枚抠 <button>：属性串、类名列表、可见文本（手法与 r278 同一份）。 */
function renderedButtons(html) {
  const items = []
  const re = /<button\b/g
  let match = null
  while ((match = re.exec(html))) {
    const open = match.index
    let i = open + '<button'.length
    let quote = null
    while (i < html.length) {
      const ch = html[i]
      if (quote) { if (ch === quote) quote = null } else if (ch === '"' || ch === "'") quote = ch
      else if (ch === '>') break
      i += 1
    }
    const close = html.indexOf('</button>', i)
    const attrs = html.slice(open + '<button'.length, i).replace(/\s+/g, ' ').trim()
    items.push({
      attrs,
      classes: (/class="([^"]*)"/.exec(attrs) || [, ''])[1].trim().split(' ').filter(Boolean),
      testid: (/data-testid="([^"]*)"/.exec(attrs) || [, ''])[1],
      type: (/type="([^"]*)"/.exec(attrs) || [, ''])[1],
      disabled: /\bdisabled(?!=|="false")/.test(attrs),
      ariaPressed: (/aria-pressed="([^"]*)"/.exec(attrs) || [, null])[1],
      role: (/role="([^"]*)"/.exec(attrs) || [, ''])[1],
      target: (/data-target="([^"]*)"/.exec(attrs) || [, ''])[1],
      alertState: (/data-alert-state="([^"]*)"/.exec(attrs) || [, ''])[1],
      hasTitle: /\btitle="/.test(attrs),
      text: (close < 0 ? '' : html.slice(i + 1, close)).replace(/<!--[\s\S]*?-->/g, '').replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim(),
    })
  }
  return items
}

describe('R410 甲 · 屏上 21 枚逐枚对照（SSR 真产物，枚数与每一格脸谱）', () => {
  it('屏上真的 <button> 恰为 21 枚，DOM 顺序与对照表逐行对齐', async () => {
    const { html } = await ssrPanel()
    const items = renderedButtons(html)
    expect(items.map(item => item.testid + ' | ' + item.classes.join(' ')),
      '屏上枚数或顺序与对照表对不上：\n' + items.map(item => item.attrs).join('\n'))
      .toHaveLength(EXPECTED.length)
    items.forEach((item, at) => {
      const row = EXPECTED[at]
      expect(item.classes, '#' + at + ' 类名列表漂了：' + item.attrs).toEqual(expectedClasses(row))
      expect(item.testid, '#' + at + ' testid 被原语自己的值顶掉了：' + item.attrs).toBe(row.testid)
      expect(item.type, '#' + at + ' type 掉了').toBe(row.type)
      expect(item.disabled, '#' + at + ' 屏上多出一个 disabled（这一屏八枚一枚都不该绑）').toBe(row.disabled)
      expect(item.text, '#' + at + ' 可见文本（可访问名的来源）换了').toBe(row.text)
    })
  })

  it('改前那四枚原语产物一字未动，本单八枚槽位全带 ui-button 脸与档位类', async () => {
    const { html } = await ssrPanel()
    const items = renderedButtons(html)
    EXPECTED.forEach((row, at) => {
      if (row.primitive !== 'was') return
      expect(items[at].classes.join(' '), '本单没碰的那一枚换了脸：' + row.own).toBe(row.kls)
    })
    const slots = EXPECTED.filter(row => row.primitive === 'slot')
    expect(slots, '对照表里归本单的枚数不是 17').toHaveLength(17)
    slots.forEach(row => expect(row.testid, '槽位没有 testid，逐枚对账无从落笔').toBeTruthy())
  })

  it('插槽那一层真的多出来了：带内容的每一枚屏上画着一层 ui-button__label，文字没丢', async () => {
    const { html } = await ssrPanel()
    // SSR 在插槽与插值两边留水合注释锚点、scoped 属性又跟在类名后面，
    // 比形状之前先把注释剥掉，比对只比到类名为止（剥的只是本断言里的这一份）。
    const flat = html.replace(/<!--[\s\S]*?-->/g, '')
    const labelled = [...flat.matchAll(/<span class="ui-button__label">/g)]
    const fromPrimitive = row => row.primitive === 'slot' || row.kls.startsWith('ui-button')
    // 21 枚 <button> 里 20 枚出自 UiButton（每一枚套一层 label），另外那一枚是 UiSelect 的触发件。
    expect(EXPECTED.filter(fromPrimitive), '对照表里出自 UiButton 的枚数不是 20').toHaveLength(20)
    expect(labelled, '屏上 ui-button__label 层数不等于渲染出的 UiButton 枚数').toHaveLength(20)
    expect(flat).toContain('<span class="ui-button__label">查看全部 ›</span>')
    expect(flat).toContain('<span class="ui-button__label">查询</span>')
    expect(flat).toContain('<span class="ui-button__label"><span class="kpi-icon"')
    expect(flat).toContain('<span class="ui-button__label"><span class="risk-icon"')
    expect(flat).toContain('<span class="ui-button__label"><span class="row-icon"')
  })
})

// ==================== 乙腿：清单 ↔ 棘轮 ↔ 屏上 三方同源对账 ====================

const debtRows = scanNativeButtons(SRC_ROOT)
const debtOf = file => debtRows.find(row => row.file === file)?.count ?? 0
const ratchetOf = rel => {
  const hit = new RegExp("'" + rel + "':\\s*(\\d+)").exec(ratchetSource)
  expect(hit, GUARD_FILE + ' 里找不到 ' + rel + ' 那一格（行被改了形状或被摘了）').toBeTruthy()
  return Number(hit[1])
}
const totalRatchet = () => {
  const hit = /const DEBT_TOTAL_RATCHET = (\d+)/.exec(ratchetSource)
  expect(hit, GUARD_FILE + ' 里合计棘轮那一行被改了形状或被摘了').toBeTruthy()
  return Number(hit[1])
}

describe('R410 乙 · 清单、棘轮、屏上三方对账（谁漂了谁红，不许各说各话）', () => {
  it('DashboardPanel 的清单现取为 0，且与 r288 那一格数字、合计那一格一字不差', () => {
    expect(debtOf('components/DashboardPanel.vue'), 'DashboardPanel.vue 还剩裸按钮').toBe(0)
    expect(ratchetOf('components/DashboardPanel.vue'), 'r288 按文件那一格没跟着降').toBe(0)
    expect(totalRatchet(), 'r288 合计那一格没跟着降').toBe(0)
    expect(debtRows.reduce((sum, row) => sum + row.count, 0), '全仓合计现取与合计棘轮不等：\n' + JSON.stringify(debtRows)).toBe(totalRatchet())
  })

  it('棘轮只准降不许升：这一格的历史读数是 8 → 0，写回 8 就是自打嘴巴', () => {
    expect(ratchetOf('components/DashboardPanel.vue')).toBeLessThanOrEqual(8)
    expect(ratchetOf('App.vue')).toBe(0)
    expect(ratchetOf('components/SourceCard.vue')).toBe(0)
    expect(countNativeButtons(panelSource), '源码现取裸开标签').toBe(0)
  })

  it('屏上枚枚有原语脸：清单说 0 枚裸的，屏上「该有脸却没有」的槽位就必须是 0 格', async () => {
    const { html } = await ssrPanel()
    const items = renderedButtons(html)
    const faceless = EXPECTED.filter((row, at) => row.primitive === 'slot' && !items[at].classes.includes('ui-button'))
      .map(row => row.own)
    const bareSlots = [...new Set(faceless)]
    expect(bareSlots.join(','), '这些槽位渲染成了不带 ui-button 脸的原生 button（假包装就在这一格里）')
      .toBe('')
    expect(bareSlots.length, '屏上裸槽位与清单枚数对不上').toBe(debtOf('components/DashboardPanel.vue'))
  })

  it('量具不误伤：components/ui 整棵不进扫描面，本件与 r288 用的是同一份数法', () => {
    expect(debtRows.some(row => row.file.startsWith('components/ui/')), '扫描面漏进了原语自身：' + JSON.stringify(debtRows)).toBe(false)
    expect(debtOf('components/DocPanel.vue'), '本单没碰的 DocPanel 长出裸按钮了').toBe(0)
  })
})

// ==================== 丙腿：挂载真 onClick（点击落点逐枚按一次） ====================

const vnodeNode = tag => ({
  tag, props: {}, children: [], parent: null, text: '',
  addEventListener() {}, removeEventListener() {}, hasAttribute: () => false, getRootNode: () => ({}),
})
const parentOf = node => node.parent || null
function detach(node) {
  const siblings = parentOf(node) ? parentOf(node).children : null
  const at = siblings ? siblings.indexOf(node) : -1
  if (at >= 0) siblings.splice(at, 1)
  node.parent = null
}
const nodeOps = {
  createElement: tag => vnodeNode(tag),
  createText: text => Object.assign(vnodeNode('#text'), { text }),
  createComment: text => Object.assign(vnodeNode('#comment'), { text }),
  setText: (node, text) => { node.text = text },
  setElementText: (el, text) => { el.children.length = 0; el.text = text },
  parentNode: node => parentOf(node),
  nextSibling(node) {
    const siblings = parentOf(node) ? parentOf(node).children : null
    return siblings ? siblings[siblings.indexOf(node) + 1] || null : null
  },
  insert(node, parent, anchor) {
    detach(node)
    const at = anchor ? parent.children.indexOf(anchor) : -1
    if (at < 0) parent.children.push(node)
    else parent.children.splice(at, 0, node)
    node.parent = parent
  },
  remove: node => detach(node),
  patchProp: (el, key, prev, next) => { if (next === null || next === undefined) delete el.props[key]; else el.props[key] = next },
  cloneNode: node => Object.assign(vnodeNode(node.tag), { props: { ...node.props }, text: node.text }),
  insertStaticContent(content, parent, anchor) {
    const node = Object.assign(vnodeNode('#static'), { text: content })
    nodeOps.insert(node, parent, anchor)
    return [node, node]
  },
  querySelector: () => null,
  setScopeId: (el, id) => { el.props[id] = '' },
}
const { createApp } = createRenderer(nodeOps)
const hasOwn = (obj, key) => Object.prototype.hasOwnProperty.call(obj || {}, key)
function renderScope(instance) {
  const empty = {}
  const { setupState, props } = instance
  const names = new Set([...Object.keys(setupState || {}), ...Object.keys(props || {})])
  const PUBLIC_KEYS = /^\$(slots|attrs|props|el|data|setupState|emit|options|refs|root|parent|nextTick)$/
  return new Proxy(empty, {
    has: (_t, key) => typeof key === 'string' && (names.has(key) || PUBLIC_KEYS.test(key)),
    get: (_t, key) => {
      if (typeof key !== 'string') return undefined
      if (setupState && hasOwn(setupState, key)) return setupState[key]
      if (props && hasOwn(props, key)) return props[key]
      return instance.proxy[key]
    },
  })
}
/**
 * node 环境里 vite 把 SFC 编成【只有 ssrRender】的产物，客户端挂载缺一枚 render：
 * 把产品自己那份模板原文过一遍运行时编译器补上。setup / props / 模板全用真身，
 * 换掉的只有「元素怎么落地」那一层。编译器不在位当场报错，绝不静默退成桩件。
 */
function clientify(label, rel, sfc, extraComponents) {
  if (typeof compile !== 'function') {
    throw new Error('R410 夹具：解析到的 vue 构建里没有运行时编译器（compile），请人工核对，不要静默跳过')
  }
  const file = readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
  const template = /<template>([\s\S]*)<\/template>/.exec(file)
  if (!template) throw new Error('R410 夹具：' + rel + ' 里取不到 <template>')
  const compiled = compile(template[1])
  return {
    __name: label,
    props: sfc.props,
    emits: sfc.emits,
    components: { ...extraComponents },
    setup: sfc.setup,
    render(_ctx, _cache) {
      return compiled(renderScope(getCurrentInstance()), _cache)
    },
  }
}
/** 原语走真身：档位类名必须是 UiButton 自己算出来的，不是夹具捏的（少注册一枚就退成桩）。 */
const CUiButton = clientify('R410UiButton', '../ui/UiButton.vue', UiButton)
const CUiLoadingState = clientify('R410UiLoadingState', '../ui/UiLoadingState.vue', UiLoadingState)
const CUiErrorState = clientify('R410UiErrorState', '../ui/UiErrorState.vue', UiErrorState, { UiButton: CUiButton })
const CUiEmptyState = clientify('R410UiEmptyState', '../ui/UiEmptyState.vue', UiEmptyState, { UiButton: CUiButton })
const CUiSelect = clientify('R410UiSelect', '../ui/UiSelect.vue', UiSelect, { UiButton: CUiButton })
const CPanel = clientify('R410DashboardPanel', '../DashboardPanel.vue', DashboardPanel, {
  UiButton: CUiButton,
  UiLoadingState: CUiLoadingState,
  UiErrorState: CUiErrorState,
  UiEmptyState: CUiEmptyState,
  UiSelect: CUiSelect,
})

function walk(node, out = []) {
  out.push(node)
  ;(node.children || []).forEach(child => walk(child, out))
  return out
}
const classOf = node => String(node.props.class || '').replace(/\s+/g, ' ').trim()

async function mountPanel() {
  stubRoutes()
  globalThis.window = globalThis.window || { addEventListener() {}, removeEventListener() {} }
  globalThis.document = globalThis.document || { addEventListener() {}, removeEventListener() {}, visibilityState: 'visible' }
  const root = vnodeNode('#root')
  const got = []
  const app = createApp(CPanel, { onGoto: (...args) => got.push(args) })
  app.provide(Symbol.for('v-scx'), {})
  app.mount(root)
  for (let i = 0; i < 16; i++) { await nextTick(); await Promise.resolve() }
  return { buttons: walk(root).filter(node => node.tag === 'button'), got }
}

describe('R410 丙 · 挂一次真壳层：这八枚槽位逐枚按下去，落点一枚不换', () => {
  it('挂载量具不是空的：屏上真的 button 节点 21 枚，与 SSR 腿同一张表', async () => {
    const { buttons } = await mountPanel()
    expect(buttons.map(node => classOf(node)), '挂载腿数到的枚数/顺序与对照表不一致：\n' + buttons.map(node => classOf(node)).join('\n'))
      .toHaveLength(EXPECTED.length)
    buttons.forEach((node, at) => {
      expect(node.props.type, '#' + at + ' 渲染节点没带 type=button').toBe(EXPECTED[at].type)
      expect(String(node.props['data-testid'] || ''), '#' + at + ' testid 漂了').toBe(EXPECTED[at].testid)
    })
  })

  it('每一枚都追得到真 onClick（读渲染节点上挂的那个函数，不读源码串）', async () => {
    const { buttons } = await mountPanel()
    const dead = buttons
      .map((node, at) => ({ node, at }))
      .filter(({ node }) => typeof node.props.onClick !== 'function')
      .map(({ at }) => '#' + at + ' ' + EXPECTED[at].own)
    expect(dead.join(','), '这些渲染出的按钮没挂上可追的行为').toBe('')
  })

  it('逐枚按一次：emit("goto", ?) 的参数序列与改前逐字相同，查询那一枚仍走 lookupMetric', async () => {
    const box = await mountPanel()
    // 逐枚单独按一次，每枚记下它自己按出来的 goto 参数（空串 = 这一枚不落 goto）。
    // K0 影子同一夹具跑出来的改前读数：17 枚落 goto（参数见对照表 goto 那一格），
    // 「按月 / 按周」走 setTrendPeriod、下拉走 openList、「查询」走 lookupMetric，都不落 goto。
    const landed = []
    for (let at = 0; at < box.buttons.length; at++) {
      const before = box.got.length
      box.buttons[at].props.onClick({})
      await nextTick()
      landed.push(box.got.slice(before).map(args => args.join('|')).join(','))
    }
    // onGoto 这个 prop 只在 emit('goto', ?) 时才会被叫到：按得动而 got 没长，就是这一枚不落 goto。
    expect(landed, '逐枚按下去的落点与改前对不上（下标 = 屏上 DOM 顺序）')
      .toEqual(EXPECTED.map(row => (row.goto === null ? '' : row.goto)))
    expect(landed.filter(Boolean).join(','), '落 goto 的那 17 枚参数序列漂了')
      .toBe('docs,data,approval,insights,data,insights,insights,insights,docs,docs,docs,docs,chat,docs,data,insights,approval')
  })

  it('禁用态逐枚对账：改前一枚都不绑 :disabled，改后屏上也没有一枚被原语禁用', async () => {
    const { buttons } = await mountPanel()
    const off = buttons.filter(node => node.props.disabled === true).map(node => classOf(node))
    expect(off.join(','), '这些枚改后按不动了（原语把 disabled 顶上去了）').toBe('')
    expect(panelCode.match(/:disabled=/g) || [], '本屏今天不该有绑定 disabled 的按钮').toHaveLength(0)
  })
})

// ==================== 丁腿：基线复位那一段 CSS ====================

const styleBlock = /<style scoped>([\s\S]*)<\/style>/.exec(panelSource)?.[1] || ''
const mark = styleBlock.indexOf('R410')
const reset = mark < 0 ? '' : styleBlock.slice(mark)

describe('R410 丁 · 基线复位块：名单齐、零裸色值、插槽那一层撤得掉', () => {
  it('复位块在位，八枚槽位的类名/容器一条都不许漏（漏一枚就是那枚的脸没人管）', () => {
    expect(reset.length, 'DashboardPanel.vue 里没有 R410 那段复位块').toBeGreaterThan(400)
    expect(reset).toMatch(/:deep\(\.ui-button__label\)\s*\{[^}]*display:\s*contents/)
    expect(reset).toMatch(/\.reference-list-row :deep\(\.ui-button__label > span:nth-child\(2\)\)[^{]*\{[^}]*display:\s*grid/)
    expect(reset).toMatch(/\.quick-grid :deep\(\.ui-button__label\)\s*\{[^}]*color:\s*inherit/)
    ;['.reference-kpi', '.risk-item', '.reference-list-row', '.quick-grid .ui-button', '.evidence-query .ui-button'].forEach(selector => {
      expect(reset, '复位块里没有 ' + selector + ' 这一格').toContain(selector)
    })
  })

  it('本单新增的 CSS 一枚裸色值都不许添（全走 var(--*)），也不许用 !important 硬顶权重', () => {
    expect(reset).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(reset).not.toMatch(/\brgba?\(/)
    expect(reset).not.toMatch(/\bhsla?\(/)
    expect(reset).not.toMatch(/:\s*(white|black|red|blue|green|gray|grey|silver|navy|teal)\b/)
    expect(reset).not.toMatch(/!important/)
    expect(reset).toMatch(/outline:\s*2px solid var\(--cyan\)/)
    expect(reset).toMatch(/outline-offset:\s*3px/)
  })

  it('焦点环那一格点名到本单那三枚卡头按钮，不连 R341 那一枚一起改脸', () => {
    const block = /([^{}]*(?::focus-visible[^{},\n]*)?(?:,\s*[^{}]*:focus-visible[^{},\n]*)*)\{[^}]*outline:[^}]*\}/.exec(reset)?.[1] || ''
    expect(block.replace(/\s+/g, ' ').trim(), '找不到那一条焦点环复位').not.toBe('')
    ;['.reference-kpi:focus-visible', '.risk-item:focus-visible', '.reference-list-row:focus-visible',
      '.quick-grid .ui-button:focus-visible', '.evidence-query .ui-button:focus-visible',
      '.reference-card-head .ui-button[data-testid^=' + chr34 + 'dashboard-goto' + chr34 + ']:focus-visible'].forEach(selector => {
      expect(block, '焦点环名单里漏了 ' + selector).toContain(selector)
    })
    expect(block, 'R341 那一枚卡头按钮不许被本单的焦点环点名').not.toContain('去上传数据')
  })
})

// ==================== 戊腿：量具地基 ====================

describe('R410 戊 · 地基：模板接的是 ./ui 那份真原语，桩件不算绿', () => {
  it('DashboardPanel 从 ./ui 引 UiButton，模板里 <UiButton 开标签 11 枚（八枚本单 + 三枚 R341 已有）', () => {
    expect(panelSource).toMatch(/import\s*\{[^}]*\bUiButton\b[^}]*\}\s*from\s*'\.\/ui'/)
    expect((panelCode.match(/<UiButton\b/g) || []).length).toBe(11)
    expect((panelCode.match(/<\/UiButton>/g) || []).length).toBe(4)
    expect(panelCode).not.toMatch(/<button[\s/>]/)
  })

  it('档位类名由原语自己算：UiButton.vue 源码里那三档拼接与本件表头一致，且它自己带着一枚裸 button', () => {
    const primitiveSource = readSrc(join('components', 'ui', 'UiButton.vue'))
    expect(primitiveSource).toMatch(/data-testid="ui-button"/)
    expect(primitiveSource).toMatch(/class="ui-button"/)
    expect(countNativeButtons(primitiveSource), '原语自身就该带一枚裸 button（它不进扫描面）').toBe(1)
    EXPECTED.filter(row => row.primitive === 'slot').forEach(row => {
      expect(['primary', 'secondary', 'ghost', 'danger']).toContain(row.variant)
      expect(['sm', 'md']).toContain(row.size)
    })
  })

  it('挂载腿不退化成桩：注册表里少 UiButton 就画不出那枚 button，本件当场跑一遍给后面的人看', async () => {
    // 与 r278 :111-113 / r307b 丁组同一格顾虑：模板遇到解析不到的组件会静默退化成桩，
    // 一跑就绿、绿的却是桩。这一腿把两种跑法各跑一次，说清本件数到的是真身。
    const template = compile('<div><UiButton label=' + chr39 + 'x' + chr39 + ' /></div>')
    const lone = extra => ({
      __name: 'R410Lone',
      components: extra,
      render(_ctx, _cache) {
        return template(renderScope(getCurrentInstance()), _cache)
      },
    })
    const run = async component => {
      const root = vnodeNode('#root')
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const app = createApp(component)
      app.provide(Symbol.for('v-scx'), {})
      app.mount(root)
      await nextTick()
      const missed = warn.mock.calls.map(call => String(call[0])).filter(line => line.includes('Failed to resolve component'))
      warn.mockRestore()
      return { nodes: walk(root).filter(node => node.tag === 'button'), missed }
    }
    const bare = await run(lone({}))
    expect(bare.missed.some(line => line.includes('UiButton')), '不注册 UiButton 却没报解析不到：这一腿的量具不可信').toBe(true)
    expect(bare.nodes.filter(node => classOf(node).includes('ui-button')), '解析不到的桩居然也画出了原语类名').toHaveLength(0)
    const wired = await run(lone({ UiButton: CUiButton }))
    expect(wired.missed, '注册了 UiButton 还在报解析不到：本件的注册表要重看').toEqual([])
    expect(wired.nodes.map(node => classOf(node))).toEqual(['ui-button ui-button--secondary ui-button--md'])
    expect(wired.nodes[0].props['data-testid'], '真身的 data-testid 不是那一句').toBe('ui-button')
  })
})
