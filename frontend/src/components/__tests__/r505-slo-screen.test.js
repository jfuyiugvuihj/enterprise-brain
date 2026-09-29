/**
 * R505 判据 A + D · 「三档目标账」这一屏真画出来的样子（SSR 真 HTML）
 *
 * 手法逐字照 r494-profile-screen.test.js（本仓没有 jsdom / @vue/test-utils，vitest 跑在 node）：
 *   ① 真逻辑：跑 SloPanel 自己的 setup，只把网络层换成进程内假实现，走真的 loadIntoView；
 *   ② 真产物：把同一份绑定交给组件自己的 render 出真 HTML —— 「屏上画的就是这一句」只能这样证；
 *   ③ 源码级：不许有裸 button、外部资源、裸色值，也不许出现第二处出口地址。
 *
 * 判据 A 在这一屏只有一句话：「没量过」不许画成达成。四格逐格钉：
 *  null 百分位 -> 「未记录」；屏上今天不出现「达标」二字；blockers 逐条挂着后端原码名；
 *  样本闸那枚数只可能来自回包（改回包 → 屏面跟着改）。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'

vi.mock('../../lib/http', async importOriginal => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn() } }
})

import { UNRECORDED } from '../../lib/alerts'
import { http } from '../../lib/http'
import {
  SLO_FACE_DENIED,
  SLO_FACE_FAILED,
  SLO_FACE_MALFORMED,
  SLO_FACE_STORAGE,
  SLO_PATH,
  SLO_STATUS_INSUFFICIENT,
  SLO_STATUS_LABELS,
  SLO_STATUS_MEASURED,
  SLO_STATUS_NOT_MEASURABLE,
  SLO_TARGET_LABELS,
  SLO_TARGET_PENDING,
  SLO_TITLES,
} from '../../lib/slo'
import SloPanel from '../SloPanel.vue'
import { countNativeButtons } from './r288-native-button-scan.js'
import { routes } from '../../router/index.js'

const PANEL = '../SloPanel.vue'
const LIB = '../../lib/slo.js'
const THEME = '../../assets/theme.css'
const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const panelSource = () => read(PANEL)
const sloRoute = routes.find(route => route.name === 'slo')

/** scoped 样式会给每个元素插一枚 data-v-xxxx，标签形状断言因此只认属性段，不认字面紧邻。 */
const codeChip = code => new RegExp('<code[^>]*>' + code + '</code>')

const slot = (over = {}) => ({
  n: 3, required_samples: 100, shortfall: 97, status: SLO_STATUS_INSUFFICIENT,
  p50_ms: null, p95_ms: null, percentile_source: 'app/common/performance.py::PerformanceStats',
  target: null, target_status: SLO_TARGET_PENDING, reason: 'insufficient samples: 3 of 100 observed',
  blockers: [{ code: 'lane_attribution_absent', detail: 'no lane on the request event' }],
  label: '整条请求的九成五', population: 'request windows', measured_from: 'stage_ledger', ...over,
})
const tier = (lane, label, over = {}) => ({
  lane, label, note: 'the ' + lane + ' lane', screen: { route: 'chat', path: '/chat', source: 'frontend/src/router/index.js' },
  endpoints: ['/api/v1/chat'], stages: ['retrieval'], observed_requests: 7,
  numbers: { end_to_end_p95_ms: slot() }, stage_numbers: { retrieval: slot({ label: '检索那一段' }) }, ...over,
})
const PAYLOAD = {
  schema: 'r105.slo/1', sample_floor: 100, target_status: SLO_TARGET_PENDING,
  percentile_source: 'app/common/performance.py::PerformanceStats (nearest rank)',
  units: { product_lane: { owns_the_name: 'tiers', decided_by: 'slo_tiers()', members: ['qa'], this_is_the_unit_of_the_slo: true } },
  tiers: [tier('qa', '问答档'), tier('analysis', '分析档'), tier('report', '报告档')],
  unattributed_pool: { what: 'every request window this process recorded', blockers: [{ code: 'cache_hits_are_not_traced', detail: 'a hit records no window' }], end_to_end: slot() },
  sample_population_note: 'requests are counted whether they completed, failed or were cancelled',
  requested_by: { username: 'root', roles: ['admin'], auth_source: 'local' },
}
const REFUSALS = {
  denied: { response: { status: 403, data: { detail: { code: 'permission_denied', message: 'nope', details: {} } } } },
  storage: { response: { status: 503, data: { detail: { code: 'storage_unavailable', message: 'nope', details: {} } } } },
  failed: { response: { status: 500, data: { detail: { code: 'internal_error', message: 'nope', details: {} } } } },
}

/** 跑一次真 setup，按 step 驱动真的读，再拿组件自己的 render 出 HTML（SSR 不跑 onMounted）。 */
async function renderAfter(step) {
  let bindings = null
  const Capture = defineComponent({
    __name: 'R505SloPanelCapture',
    setup(_props, ctx) {
      bindings = SloPanel.setup({}, ctx)
      return () => null
    },
  })
  await renderToString(h(Capture))
  await step(bindings)
  const Probe = defineComponent({ ...SloPanel, __name: 'R505SloPanelProbe', setup: () => bindings })
  return { html: await renderToString(h(Probe)), bindings }
}
const renderWith = payload => renderAfter(async bindings => {
  http.get.mockResolvedValue({ data: payload })
  await bindings.loadIntoView()
})
const renderFailure = error => renderAfter(async bindings => {
  http.get.mockRejectedValue(error)
  await bindings.loadIntoView()
})
const count = (html, id) => (html.match(new RegExp('data-testid="' + id + '"', 'g')) || []).length
/** 通用计数：数一段文本里某一枚字面片段出现了几遍（本件的正控用它）。 */
const countText = (haystack, needle) => haystack.split(needle).length - 1
function cellText(html, id) {
  const open = html.indexOf(`data-testid="${id}"`)
  expect(open, `屏上少了 ${id} 那一格`).toBeGreaterThan(-1)
  const match = />([^<]*)<\//.exec(html.slice(open))
  return match ? match[1] : ''
}
function buttonLabels(source) {
  return [...source.matchAll(/<UiButton\b[\s\S]*?\/>/g)].map(match => {
    const label = /label="([^"]*)"/.exec(match[0])
    return label ? label[1] : '(这一枚 UiButton 没有 label 属性)'
  })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('R505 判据 A · 三档逐档画欠账，一枚 0 都不许画成读数', () => {
  it('三档就是三张卡；未归因那一池不冒充第四档', async () => {
    const { html } = await renderWith(PAYLOAD)
    expect(count(html, 'slo-tier')).toBe(3)
    expect(html).toContain('问答档')
    expect(html).toContain('分析档')
    expect(html).toContain('报告档')
    expect(count(html, 'slo-pool')).toBe(1)
    expect(html).toContain('它不是一档，也不能被当成一档来读')
  })

  it('服务端答 null 的两枚百分位，屏上只有「未记录」：整屏今天没有一枚 0 毫秒', async () => {
    const { html } = await renderWith(PAYLOAD)
    expect(html).toContain(UNRECORDED)
    expect(html).not.toContain('0 毫秒')
    expect(html).not.toContain('0.0 毫秒')
  })

  it('今天这一屏画不出「达标」两个字：目标值那一格只有待填那一句', async () => {
    const { html } = await renderWith(PAYLOAD)
    expect(html).not.toContain('达标')
    expect(cellText(html, 'slo-target-status')).toBe(SLO_TARGET_LABELS[SLO_TARGET_PENDING])
    expect(html).toContain('目标值待填')
  })

  it('样本闸那枚数只可能来自回包：改 sample_floor，屏上跟着改', async () => {
    const { html } = await renderWith({ ...PAYLOAD, sample_floor: 4_000 })
    expect(cellText(html, 'slo-floor')).toContain('4000 条')
    const blank = await renderWith({ ...PAYLOAD, sample_floor: null })
    expect(cellText(blank.html, 'slo-floor')).toContain(UNRECORDED)
  })

  it('欠样本与不可测在屏上是两句话；还欠几枚原样转达，界面不做减法', async () => {
    const { html } = await renderWith({
      ...PAYLOAD,
      tiers: [tier('qa', '问答档', {
        numbers: {
          end_to_end_p95_ms: slot({ status: SLO_STATUS_NOT_MEASURABLE, n: 0, shortfall: 100, label: '首屏那一格' }),
          cache_p95_ms: slot({ status: SLO_STATUS_INSUFFICIENT, n: 3, shortfall: 97, label: '缓存命中那一格' }),
        },
      })],
    })
    // 逐字要取取数件里那一整句（本件不抄第二份字符串）：两句话各自说清一档欠账，屏上不许合并。
    expect(html).toContain(SLO_STATUS_LABELS[SLO_STATUS_NOT_MEASURABLE])
    expect(html).toContain(SLO_STATUS_LABELS[SLO_STATUS_INSUFFICIENT])
    expect(html).toContain('100 条')
    expect(html).toContain('97 条')
  })

  it('只有真量到的那一格才允许出现毫秒；出现了毫秒也不等于出现「达标」', async () => {
    const { html } = await renderWith({
      ...PAYLOAD,
      tiers: [tier('qa', '问答档', { numbers: { end_to_end_p95_ms: slot({ status: SLO_STATUS_MEASURED, n: 120, shortfall: 0, p50_ms: 412, p95_ms: 1890, reason: '' }) } })],
    })
    expect(html).toContain('1890 毫秒')
    expect(html).not.toContain('达标')
  })

  it('blockers 逐条挂着，码名用后端原名（技术信息那一行），一枚不合并、一枚不改名', async () => {
    const { html } = await renderWith(PAYLOAD)
    expect(count(html, 'slo-blocker')).toBe(6)
    expect(html).toMatch(codeChip('lane_attribution_absent'))
    expect(html).toContain('技术信息 · 码名')
    expect(count(html, 'slo-pool-blocker')).toBe(1)
    expect(html).toMatch(codeChip('cache_hits_are_not_traced'))
    // 反向：把某一格的障碍摘掉，屏上就少一条 —— 证明这一枚枚数真来自回包，不是写死的句子。
    const stripped = await renderWith({
      ...PAYLOAD,
      tiers: PAYLOAD.tiers.map((row, index) => (index === 0 ? { ...row, numbers: { end_to_end_p95_ms: slot({ blockers: [] }) }, stage_numbers: { retrieval: slot({ blockers: [] }) } } : row)),
    })
    expect(count(stripped.html, 'slo-blocker')).toBe(4)
    expect(stripped.html).toContain('这一档的回执没交出任何一条障碍')
  })

  it('这一屏连一枚输入框都没有：样本闸不是能被界面调低的旋钮', async () => {
    const { html } = await renderWith(PAYLOAD)
    expect(html).not.toMatch(/<input\b/i)
    expect(panelSource()).not.toMatch(/<UiField\b/)
    expect(html).toContain('界面上没有任何一格能把它调低')
  })
})

describe('R505 判据 D · 三张失败脸分开留名（真 HTML）', () => {
  it('403 / 503 / 500 各画自己那一句，HTML 两两不等', async () => {
    const denied = await renderFailure(REFUSALS.denied)
    const storage = await renderFailure(REFUSALS.storage)
    const failed = await renderFailure(REFUSALS.failed)
    expect(denied.html).toContain(SLO_TITLES[SLO_FACE_DENIED])
    expect(storage.html).toContain(SLO_TITLES[SLO_FACE_STORAGE])
    expect(failed.html).toContain(SLO_TITLES[SLO_FACE_FAILED])
    expect(denied.html).not.toContain(SLO_TITLES[SLO_FACE_STORAGE])
    expect(storage.html).not.toContain(SLO_TITLES[SLO_FACE_FAILED])
    expect(denied.html).not.toBe(storage.html)
    expect(storage.html).not.toBe(failed.html)
    expect(denied.html).toContain('data-face="' + SLO_FACE_DENIED + '"')
  })

  it('403 那张脸不给「重试」：重放同一发不会让权限长出来', async () => {
    const denied = await renderFailure(REFUSALS.denied)
    expect(denied.html).toContain('重新登录')
    // UiErrorState 的动作区只在 retryable（或有 actions 插槽）时才渲染 —— 「不给重试」在 HTML 上
    // 就是这一格整枚不存在；存储脸同一口径：重放这一发也变不出一个落得下读数的存储。
    expect(denied.html, '403 那张脸长出了重试按钮：重放同一发不会让权限长出来').not.toContain('ui-error-state__actions')
    const storage = await renderFailure(REFUSALS.storage)
    expect(storage.html, '503 那张脸长出了重试按钮').not.toContain('ui-error-state__actions')
    const plain = await renderFailure(REFUSALS.failed)
    expect(plain.html).not.toBe(denied.html)
    expect(plain.html, '500 那张脸该留着「重新读取」：读失败是可能自愈的').toContain('ui-error-state__actions')
  })

  it('三张脸都不画档位卡：失败就是失败，不许留一份看着像读数的空壳', async () => {
    for (const error of [REFUSALS.denied, REFUSALS.storage, REFUSALS.failed]) {
      const { html } = await renderFailure(error)
      expect(count(html, 'slo-tier')).toBe(0)
      expect(count(html, 'slo-head')).toBe(0)
      expect(count(html, 'slo-failure')).toBe(1)
    }
  })

  it('200 但形状读不出：走形状脸，不滑成「三档都是零」', async () => {
    const { html } = await renderAfter(async bindings => {
      http.get.mockResolvedValue({ data: { schema: 'r105.slo/1' } })
      await bindings.loadIntoView()
    })
    expect(html).toContain(SLO_TITLES[SLO_FACE_MALFORMED])
    expect(count(html, 'slo-tier')).toBe(0)
    expect(html, '形状脸该能重读一次').toContain('ui-error-state__actions')
  })
})

describe('R505 交付卫生 · 这一屏不自造第二套真源', () => {
  it('零枚裸 <button>：动作全部走 ui 原语，屏上只有「重新读取」一枚按钮', () => {
    expect(countNativeButtons(panelSource())).toBe(0)
    expect(buttonLabels(panelSource())).toEqual(['重新读取'])
    expect(panelSource()).not.toMatch(/label="[^"]*(运行|执行|跑一轮|开始|触发)/)
  })

  it('运行时零外部请求、零位图、零裸色值（色值只归 theme.css）', () => {
    const source = panelSource()
    expect(source).not.toMatch(/https?:\/\/|\bwww\./i)
    expect(source).not.toMatch(/\.(png|jpe?g|gif|svg|webp)\b/i)
    expect(source).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(source).not.toMatch(/rgba?\(/)
    const styleBlock = /<style scoped>([\s\S]*?)<\/style>/.exec(source)
    expect(styleBlock, '样式块读不出来：这一屏的排版声明去哪儿了？').toBeTruthy()
    expect(styleBlock[1]).not.toMatch(/color|background|border|font-/)
    for (const token of styleBlock[1].match(/var\(--[\w-]+\)/g) || []) {
      expect(read(THEME) + source, token + ' 没有定义').toContain(token)
    }
  })

  it('取数只在 lib/slo.js：壳里不许出现第二处出口地址或 axios', () => {
    const code = panelSource().replace(/<!--[\s\S]*?-->/g, '').replace(/\/\*[\s\S]*?\*\//g, '')
    // 出口地址要找的是「被引号包起来的那一枚常量值」；裸 SLO_PATH（/slo）会命中本屏自己
    // import 的那一行 '../lib/slo'，那是取数件的名字，不是第二处出口地址。
    for (const needle of ['axios', 'fetch(', "from '../lib/http'", '/api/v1/', "'" + SLO_PATH + "'"]) {
      expect(code, '屏壳里出现了取数件：' + needle).not.toContain(needle)
    }
    expect(code).toMatch(/from '\.\.\/lib\/slo'/)
    // 正控：那枚出口地址确实只在取数件里被定义一次 —— 上面那条「壳里没有」才不会是空话。
    const libSource = read(LIB)
    expect(libSource).toContain("SLO_PATH = '" + SLO_PATH + "'")
    expect(countText(libSource, "'" + SLO_PATH + "'"), '出口地址在取数件里也不许出现第二遍').toBe(1)
  })

  it('屏上没有页级主标题：屏名只由路由表那一格说一次', () => {
    const source = panelSource()
    expect(source).not.toMatch(/<header\b[^>]*class="[^"]*\bpanel-head\b[^>]*>[\s\S]*?<h3\b/)
    expect(source).not.toMatch(/class="panel-hd"[\s\S]*?<strong>/)
    expect(sloRoute.meta.title).toBe('服务等级目标')
    expect(panelSource(), '这一屏自己起了第二枚页级屏名').not.toContain('chat-screen-name')
  })
})
