/**
 * R505 判据 B + D · 「评测报告」这一屏真画出来的样子（SSR 真 HTML）
 *
 * 手法逐字照 r505-slo-screen.test.js（本仓没有 jsdom / @vue/test-utils，vitest 跑在 node）：
 *   ① 真逻辑：跑 EvaluationsPanel 自己的 setup，只把网络层换成进程内假实现，走真的 loadIntoView；
 *   ② 真产物：把同一份绑定交给组件自己的 render 出真 HTML —— 「屏上画的就是这一句」只能这样证；
 *   ③ 源码级：零枚裸 button、零外部资源、零裸色值，出口地址只活在取数件里。
 *
 * 判据 B 在这一屏只有一句话：它是读，不是跑。四格逐格钉：
 *  ① runs_on_request / reason / command_template 三格逐字上屏，命令只在 <code> 里；
 *  ② 屏上零枚能把评测跑起来的按钮 —— 渲染出的 HTML 与壳的源码两面都钉，且后端改口那一档也不给；
 *  ③ reports 为空走本屏自己的空态脸：不画报告表，也不拿「0 分」冒充「没人跑过」；
 *  ④ truncated / limits 逐格跟着回包改：改回包 -> 屏面跟着改，这里不另记一本账。
 *
 * 字段一律取自 src/lib/evaluations.js 的导出与后端真发的那一发（键名对账在那件的契约件里做过）。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'

vi.mock('../../lib/http', async importOriginal => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn() } }
})

import { http } from '../../lib/http'
import {
  EVALUATIONS_PATH,
  EVAL_EMPTY_DESCRIPTION,
  EVAL_FACES,
  EVAL_FACE_DENIED,
  EVAL_FACE_EMPTY,
  EVAL_FACE_FAILED,
  EVAL_FACE_MALFORMED,
  EVAL_FACE_STORAGE,
  EVAL_FACE_UNAUTHORIZED,
  EVAL_RUNS_NO,
  EVAL_RUNS_UNKNOWN,
  EVAL_RUNS_YES,
  EVAL_STATUS_NO_REPORTS,
  EVAL_STATUS_REPORTS,
  EVAL_TITLES,
} from '../../lib/evaluations'
import EvaluationsPanel from '../EvaluationsPanel.vue'
import { countNativeButtons } from './r288-native-button-scan.js'
import { routes } from '../../router/index.js'

const PANEL = '../EvaluationsPanel.vue'
const LIB = '../../lib/evaluations.js'
const THEME = '../../assets/theme.css'
const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const panelSource = () => read(PANEL)
const evalRoute = routes.find(route => route.name === 'evaluations')

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
  denied: { response: { status: 403, data: { detail: { code: 'permission_denied', message: 'evaluation:read is not permitted.', details: { reason_code: 'admin_role_required' } } } } },
  storage: { response: { status: 503, data: { detail: { code: 'storage_unavailable', message: 'report directory is not readable', details: {} } } } },
  failed: { response: { status: 500, data: { detail: { code: 'internal_error', message: 'evaluation listing blew up', details: {} } } } },
}

/** scoped 样式会给每枚元素插 data-v-xxxx，标签形状断言因此只认属性段。 */
const codeChip = text => new RegExp('<code[^>]*>' + text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '</code>')
const count = (html, id) => (html.match(new RegExp('data-testid="' + id + '"', 'g')) || []).length
const countText = (haystack, needle) => haystack.split(needle).length - 1
/** 屏上真长出来的按钮文案：SSR 把插值包在 <!--[-->…<!--]--> 里。 */
const renderedButtonLabels = html => [...html.matchAll(/class="ui-button__label"><!--\[-->([^<]*)<!--\]-->/g)].map(match => match[1])
/** 壳源码里的 UiButton 文案清单（判据 B 的「零枚运行按钮」在源码那一面数一遍）。 */
const buttonLabels = source => [...source.matchAll(/<UiButton\b[\s\S]*?\/>/g)].map(match => {
  const label = /label="([^"]*)"/.exec(match[0])
  return label ? label[1] : '(这一枚 UiButton 没有 label 属性)'
})

/** 跑一次真 setup，按 step 驱动真的读，再拿组件自己的 render 出 HTML（SSR 不跑 onMounted）。 */
async function renderAfter(step) {
  let bindings = null
  const Capture = defineComponent({
    __name: 'R505EvaluationsPanelCapture',
    setup(_props, ctx) {
      bindings = EvaluationsPanel.setup({}, ctx)
      return () => null
    },
  })
  await renderToString(h(Capture))
  await step(bindings)
  const Probe = defineComponent({ ...EvaluationsPanel, __name: 'R505EvaluationsPanelProbe', setup: () => bindings })
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

beforeEach(() => {
  vi.clearAllMocks()
})

describe('R505 判据 B · 这一屏说的是「读」，不是一枚能按的跑分键', () => {
  it('第一格就是「不跑分」：那句原话、它给的理由、那句命令，三格逐字上屏', async () => {
    const { html } = await renderWith(PAYLOAD)
    expect(count(html, 'evaluations-execution')).toBe(1)
    expect(html).toContain(EVAL_RUNS_NO)
    expect(html).toContain(EXECUTION.reason)
  })

  it('命令只在 <code> 里：只读展示，屏上没有任何一处 form/action 能把它发出去', async () => {
    const { html } = await renderWith(PAYLOAD)
    // 整条命令原样躺在同一枚 <code> 里（不是截一段贴出来），屏上也不为它建任何一枚提交入口。
    // 取的是回包里那一格的键名 command_template —— view 层才叫它 commandTemplate。
    expect(html).toMatch(codeChip(EXECUTION.command_template))
    expect(html).not.toMatch(/<form\b|action=|method=/i)
    expect(html).toContain(EXECUTION.report_module)
  })

  it('零枚运行按钮：渲染出的 HTML 上只有「重新读取」，壳的源码里也没有第二枚按钮文案', async () => {
    const { html } = await renderWith(PAYLOAD)
    expect(renderedButtonLabels(html)).toEqual(['重新读取'])
    expect(countNativeButtons(panelSource())).toBe(0)
    expect(buttonLabels(panelSource())).toEqual(['重新读取'])
    expect(panelSource()).not.toMatch(/label="[^"]*(运行|执行|跑一轮|开始|触发|提交)/)
  })

  it('后端哪天改口说这一发会跑评测：屏上原话说破这一屏的只读前提已不成立，仍然一枚按钮都不给', async () => {
    const { html } = await renderWith({ ...PAYLOAD, execution: { ...EXECUTION, runs_on_request: true } })
    expect(html).toContain(EVAL_RUNS_YES)
    expect(html).not.toContain(EVAL_RUNS_NO)
    expect(renderedButtonLabels(html)).toEqual(['重新读取'])
  })

  it('回包没回答这一发会不会跑评测：屏上说「没回答」，不替后端答一句「不会」', async () => {
    const blind = { ...EXECUTION }
    delete blind.runs_on_request
    const { html } = await renderWith({ ...PAYLOAD, execution: blind })
    expect(html).toContain(EVAL_RUNS_UNKNOWN)
    expect(html).not.toContain(EVAL_RUNS_NO)
    expect(html).not.toContain(EVAL_RUNS_YES)
  })

  it('reports 为空是本屏自己的空态脸：报告表一枚不画，也不拿「0 分」冒充「没人跑过」', async () => {
    const { html } = await renderWith({ ...PAYLOAD, status: EVAL_STATUS_NO_REPORTS, reports: [], reports_total: 0 })
    expect(html).toContain('data-face="' + EVAL_FACE_EMPTY + '"')
    expect(count(html, 'evaluations-empty')).toBe(1)
    expect(count(html, 'eval-reports-table')).toBe(0)
    expect(count(html, 'eval-report-metrics')).toBe(0)
    expect(html).toContain(EVAL_TITLES[EVAL_FACE_EMPTY])
    expect(html).toContain(EVAL_EMPTY_DESCRIPTION)
    expect(html).not.toMatch(/0(\.0+)?\s*分/)
    // 空态下「这一屏不跑分」那一格照旧要说：空目录不是它跑出来的理由。
    expect(count(html, 'evaluations-execution')).toBe(1)
  })

  it('截断与上限逐格跟着回包改：改 reports_total / truncated / requested_limit，屏面就跟着改', async () => {
    const { html } = await renderWith({
      ...PAYLOAD,
      reports_total: 11,
      truncated: false,
      limits: { max_reports: 20, applied_limit: 11, requested_limit: 11, clamped: false },
    })
    expect(html).toContain('11 份')
    expect(html).toContain('这一发把回执认得的报告都列出来了')
    expect(html).not.toContain('这一发只交出前若干份')
    expect(html).toContain('请求里带的那一枚')
    expect(html).toContain('没夹')
    const first = await renderWith(PAYLOAD)
    expect(first.html).toContain('这一发只交出前若干份，报告目录里还有更早的没列出')
    expect(first.html).toContain('这一发没带 limit')
  })

  it('limit 那一格真带得出去：表单里填了才有查询参数，空着就一枚不带', async () => {
    await renderAfter(async bindings => {
      http.get.mockResolvedValue({ data: PAYLOAD })
      bindings.form.limit = 7
      await bindings.loadIntoView()
    })
    expect(http.get).toHaveBeenLastCalledWith(EVALUATIONS_PATH, { params: { limit: 7 } })
    await renderAfter(async bindings => {
      http.get.mockResolvedValue({ data: PAYLOAD })
      await bindings.loadIntoView()
    })
    expect(http.get).toHaveBeenLastCalledWith(EVALUATIONS_PATH, undefined)
  })
})

describe('R505 判据 D · 五张失败脸分开留名（真 HTML）', () => {
  it('401 / 403 / 503 / 500 各画自己那一句，HTML 两两不等', async () => {
    const faces = [EVAL_FACE_UNAUTHORIZED, EVAL_FACE_DENIED, EVAL_FACE_STORAGE, EVAL_FACE_FAILED]
    const rendered = []
    for (const face of faces) {
      const { html } = await renderFailure(REFUSALS[face])
      rendered.push(html)
      expect(html, '这一张脸没上屏：' + face).toContain(EVAL_TITLES[face])
      expect(html).toContain('data-face="' + face + '"')
      expect(count(html, 'evaluations-failure')).toBe(1)
    }
    for (let a = 0; a < rendered.length; a += 1) {
      for (let b = a + 1; b < rendered.length; b += 1) {
        expect(rendered[a], '两张脸塌成了一张：' + faces[a] + ' / ' + faces[b]).not.toBe(rendered[b])
      }
    }
    for (const face of EVAL_FACES) {
      expect(EVAL_TITLES, '脸谱名册里少这一张：' + face).toHaveProperty(face)
    }
  })

  it('403 与 503 不给「重试」：重放同一发既不会让权限长出来，也不会让报告目录变得可读', async () => {
    for (const face of [EVAL_FACE_UNAUTHORIZED, EVAL_FACE_DENIED, EVAL_FACE_STORAGE]) {
      const { html } = await renderFailure(REFUSALS[face])
      expect(html, face + ' 那张脸长出了重试按钮').not.toContain('ui-error-state__actions')
    }
    const plain = await renderFailure(REFUSALS.failed)
    expect(plain.html, '500 那张脸该留着重读一次').toContain('ui-error-state__actions')
  })

  it('失败脸上不画读数：执行卡、回执卡、报告表一枚都不许留', async () => {
    for (const error of Object.values(REFUSALS)) {
      const { html } = await renderFailure(error)
      expect(count(html, 'evaluations-execution')).toBe(0)
      expect(count(html, 'evaluations-head')).toBe(0)
      expect(count(html, 'evaluations-reports')).toBe(0)
      expect(count(html, 'evaluations-sets')).toBe(0)
    }
  })

  it('200 但形状读不出：走形状脸，不滑成「一份报告都没有」', async () => {
    const { html } = await renderAfter(async bindings => {
      http.get.mockResolvedValue({ data: { status: EVAL_STATUS_REPORTS } })
      await bindings.loadIntoView()
    })
    expect(html).toContain(EVAL_TITLES[EVAL_FACE_MALFORMED])
    expect(html).not.toContain(EVAL_TITLES[EVAL_FACE_EMPTY])
    expect(count(html, 'evaluations-empty')).toBe(0)
    expect(html).toContain('ui-error-state__actions')
  })
})

describe('R505 交付卫生 · 这一屏不自造第二套真源', () => {
  it('运行时零外部请求、零位图、零裸色值（色值只归 theme.css）', () => {
    const source = panelSource()
    expect(source).not.toMatch(/https?:\/\/|\bwww\./i)
    expect(source).not.toMatch(/\.(png|jpe?g|gif|svg|webp)\b/i)
    expect(source).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(source).not.toMatch(/rgba?\(/)
    const styleBlock = /<style scoped>([\s\S]*?)<\/style>/.exec(source)
    expect(styleBlock, '样式块读不出来：这一屏的排版声明去哪儿了？').toBeTruthy()
    // 着色那一类只准引用 theme.css 里的令牌：裸色值（hex / rgb() / rgba() / hsl()）一枚都不许有，
    // 而 color / font-family 这类会着色的属性必须逐条走 var(--…) —— 令牌有没有定义由下面那圈钉。
    expect(styleBlock[1]).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/)
    for (const declaration of styleBlock[1].match(/(?:^|\n)\s*(?:color|background|background-color|border-color|font-family)\s*:\s*([^;]+);/g) || []) {
      expect(declaration, '样式块里有一枚不走令牌的着色声明：' + declaration.trim()).toContain('var(--')
    }
    for (const token of styleBlock[1].match(/var\(--[\w-]+\)/g) || []) {
      expect(read(THEME) + source, token + ' 没有定义').toContain(token)
    }
  })

  it('取数只在 lib/evaluations.js：壳里不许出现第二处出口地址或 axios', () => {
    const code = panelSource().replace(/<!--[\s\S]*?-->/g, '').replace(/\/\*[\s\S]*?\*\//g, '')
    for (const needle of ['axios', 'fetch(', "from '../lib/http'", '/api/v1/', "'" + EVALUATIONS_PATH + "'"]) {
      expect(code, '屏壳里出现了取数件：' + needle).not.toContain(needle)
    }
    expect(code).toMatch(/from '\.\.\/lib\/evaluations'/)
    const libSource = read(LIB)
    expect(libSource).toContain("EVALUATIONS_PATH = '" + EVALUATIONS_PATH + "'")
    expect(countText(libSource, "'" + EVALUATIONS_PATH + "'"), '出口地址在取数件里也不许出现第二遍').toBe(1)
  })

  it('屏上没有页级主标题：屏名只由路由表那一格说一次', () => {
    const source = panelSource()
    expect(source).not.toMatch(/<header\b[^>]*class="[^"]*\bpanel-head\b[^>]*>[\s\S]*?<h3\b/)
    expect(source).not.toMatch(/class="panel-hd"[\s\S]*?<strong>/)
    expect(evalRoute.meta.title).toBe('评测报告')
    expect(source, '这一屏自己起了第二枚页级屏名').not.toContain('chat-screen-name')
  })
})
