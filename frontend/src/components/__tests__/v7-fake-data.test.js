/**
 * D-4 · V7-1 / V7-2 / V7-3 / V7-5 的"不许回退"锚点
 *
 * 这四条在 V7 落地时只改了实现、没留断言（V7-4 已由总控钉在
 * tests/test_frontend_request_cancel.py，方向是禁止「取消生成」字样回来，这里不重复）。
 * 手法与 panel-states.test.js 一致：能首屏渲染的用 SSR，必须请求才有脸的用源码断言，
 * 不假装验过自己验不了的（仓库里没有 jsdom，environment=node）。
 */
import { existsSync, readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import GraphPanel from '../GraphPanel.vue'
import InsightPanel from '../InsightPanel.vue'
import ApprovalPanel from '../ApprovalPanel.vue'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const source = f => read(`../${f}`)
const srcSource = f => read(`../../${f}`)
const render = component => renderToString(h({ render: () => h(component) }))

const PANELS = [
  'ApprovalPanel.vue',
  'ChatPanel.vue',
  'DashboardPanel.vue',
  'DataPanel.vue',
  'DocPanel.vue',
  'GraphPanel.vue',
  'InsightPanel.vue',
]

describe('V7-1 · 知识图谱的关系只可能是库里的真关系', () => {
  it('读取路径唯一：api.get 在整个面板里只出现一次，就是 relations', () => {
    const s = source('GraphPanel.vue')
    expect(s.match(/api\.get\(/g)).toHaveLength(1)
    expect(s).toContain("api.get('/knowledge-graph/relations')")
  })

  it('relations 的每一次赋值要么是接口数组、要么是空数组，没有第三条路', () => {
    const s = source('GraphPanel.vue')
    const assigns = s.match(/relations\.value = [^\n]*/g)
    expect(assigns.length).toBeGreaterThanOrEqual(3)
    for (const a of assigns) expect(a).toMatch(/^relations\.value = (list|\[\])$/)
    // 失败态里塞常量 = 把服务坏了画成"图谱长这样"，这是 V7-1 明令禁止的回落。
    expect(s).not.toMatch(/devFixtures/)
  })

  it('表单不再预填示例关系：四个字段默认全空串', () => {
    const s = source('GraphPanel.vue')
    expect(s).toContain("return { source_entity: '', relation: '', target: '', source: '' }")
    expect(s).not.toMatch(/source_entity:\s*'[^']/)
  })

  it('SSR 首屏（还没发过请求）画空态，屏上不存在任何连线', async () => {
    const html = await render(GraphPanel)
    expect(html).toContain('知识库里还没有已登记的关系')
    expect(html).not.toContain('差旅费')
  })
})

describe('V7-2 · 编造的常量只住在 src/devFixtures/，面板源码里一个数值都不留', () => {
  // 680 / 500 故意不在名单里：ApprovalPanel 的说明句要如实报出"预审参数是编的"，
  // 那是给人看的披露文字，不是数据源。
  const FAKE_VALUES = ['18600', '9200', '14200', '7600', '4200', '5400', '12600', '7200', '9800', '6100', '4600']
  const FAKE_TITLES = ['市场部差旅费异常', '财务部报销波动', '行政部住宿费上升']

  it('七块面板里只有等 R13/R14 的三块引用 devFixtures，图谱与聊天明确不引用', () => {
    const users = PANELS.filter(f => source(f).includes('devFixtures')).sort()
    expect(users).toEqual(['ApprovalPanel.vue', 'DashboardPanel.vue', 'InsightPanel.vue'])
  })

  it.each([...FAKE_VALUES, ...FAKE_TITLES])('演示常量 %s 不许出现在任何面板源码里', fake => {
    for (const f of PANELS) expect(source(f)).not.toContain(fake)
  })

  it('每个演示文件都自带"上线前必须清空"的告示，防止被当成真数据留下', () => {
    for (const f of ['approval-demo.js', 'dashboard-demo.js', 'insights-demo.js']) {
      expect(readFileSync(new URL(`../../devFixtures/${f}`, import.meta.url), 'utf8')).toContain('上线前必须清空')
    }
  })
})

describe('V7-3 · 演示面板必须挂牌，且不许借用告警语言', () => {
  it('洞察 / 审批首屏就带「演示数据」徽标与 data-demo 标记', async () => {
    for (const C of [InsightPanel, ApprovalPanel]) {
      const html = await render(C)
      expect(html).toContain('data-demo="fixtures"')
      expect(html).toContain('demo-flag')
      expect(html).toContain('演示数据')
    }
  })

  it('总览面板的徽标在位（它首屏是 loading，所以这条只能钉源码），三处子卡各挂一个', () => {
    const s = source('DashboardPanel.vue')
    expect(s).toContain('data-demo="fixtures"')
    expect(s.match(/class="demo-flag"/g)).toHaveLength(3)
  })

  it('critical 只剩一处计数过滤，不参与 class 也不参与配色；warning 在面板里归零', () => {
    const s = source('DashboardPanel.vue')
    expect(s.match(/critical/g)).toHaveLength(1)
    expect(s).toContain("item.severity === 'critical'")
    expect(s).not.toMatch(/class="[^"]*critical/)
    expect(s).not.toMatch(/:class=[^\n]*critical/)
    expect(s).not.toMatch(/severity[\s\S]{0,40}(#|rgba?\()/)
    for (const f of ['InsightPanel.vue', 'ApprovalPanel.vue']) expect(source(f)).not.toMatch(/critical|warning/)
  })

  it('徽标本身不写裸色值：demo-flag 一段样式里没有 hex，只有 token 与中性 rgba', () => {
    const t = srcSource('assets/theme.css')
    const from = t.indexOf('演示数据徽标')
    const block = t.slice(from, t.indexOf('.demo-note {', from))
    expect(from).toBeGreaterThan(-1)
    expect(block).toContain('.demo-flag')
    expect(block).not.toMatch(/#[0-9a-fA-F]{3}/)
  })
})

describe('V7-5 · 登录页不得出现任何未溯源数字', () => {
  it('login-demo.js 已经不在树里', () => {
    expect(existsSync(new URL('../../devFixtures/login-demo.js', import.meta.url))).toBe(false)
  })

  it('八份 .vue 源码里找不到 1.2M / 300K / +42 这三个假数字', () => {
    for (const f of [...PANELS, 'App.vue']) {
      const s = f === 'App.vue' ? srcSource(f) : source(f)
      for (const fake of ['1.2M', '300K', '+42']) expect(s).not.toContain(fake)
    }
  })

  it('换成三条不含数字的定性能力标语，而且是 DOM 文本（不烤进位图）', () => {
    const app = srcSource('App.vue')
    const from = app.indexOf('class="login-capabilities"')
    const block = app.slice(from, app.indexOf('</div>', app.indexOf('智能分析', from)))
    const labels = block.match(/<span>([^<]*)<\/span>/g) || []
    expect(labels).toHaveLength(3)
    expect(labels.join('')).toContain('数据安全')
    expect(labels.join('')).toContain('知识沉淀')
    expect(labels.join('')).toContain('智能分析')
    for (const label of labels) expect(label).not.toMatch(/[0-9]/)
  })
})