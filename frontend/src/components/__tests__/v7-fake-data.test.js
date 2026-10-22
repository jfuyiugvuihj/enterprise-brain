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

  // W7 起洞察页改接真告警链，devFixtures 那三行假数据整块摘掉，引用面从三块缩到两块。
  // R267 把这里欠的那句提醒兑掉了：总览的三枚常量随接线一起删，趋势卡画空态、
  // 异常卡读告警账本，所以名单缩成审批页一枚（F4 裁定保留的「自查计算器」输入）。
  it('七块面板里只剩等 R13 的审批页引用 devFixtures：总览、图谱、聊天与洞察明确不引用', () => {
    const users = PANELS.filter(f => source(f).includes('devFixtures')).sort()
    expect(users).toEqual(['ApprovalPanel.vue'])
  })

  it('W7 反向钉：洞察页源码不再引用 devFixtures，SSR 首屏也不再挂演示徽标', async () => {
    expect(source('InsightPanel.vue')).not.toMatch(/devFixtures|demo-flag|data-demo/)
    const html = await render(InsightPanel)
    expect(html).not.toContain('data-demo="fixtures"')
    expect(html).not.toContain('演示数据')
  })

  it.each([...FAKE_VALUES, ...FAKE_TITLES])('演示常量 %s 不许出现在任何面板源码里', fake => {
    for (const f of PANELS) expect(source(f)).not.toContain(fake)
  })

  it('每个演示文件都自带"上线前必须清空"的告示，防止被当成真数据留下', () => {
    for (const f of ['approval-demo.js', 'insights-demo.js']) {
      expect(readFileSync(new URL(`../../devFixtures/${f}`, import.meta.url), 'utf8')).toContain('上线前必须清空')
    }
  })

  // R267：总览那份常量不是「清空」而是整枚摘掉——留一份空文件在 devFixtures 里，
  // 下一个接线的人只会照着它再编一次数据。
  it('dashboard-demo.js 随总览接线一起从树里消失，不许留成空壳', () => {
    expect(existsSync(new URL('../../devFixtures/dashboard-demo.js', import.meta.url))).toBe(false)
  })
})

describe('V7-3 · 演示面板必须挂牌，且不许借用告警语言', () => {
  it('审批页首屏仍带「演示数据」徽标与 data-demo 标记（W7 只改定位措辞，没摘这块牌）', async () => {
    const html = await render(ApprovalPanel)
    expect(html).toContain('data-demo="fixtures"')
    expect(html).toContain('demo-flag')
    expect(html).toContain('演示数据')
  })

  // R267：三枚子卡的假数据各自归真或退场，徽标不该再一处挂一个；但屏幕正文里那句
  // 「演示数据」+ 一句人话是诚实牌，摘牌就等于把剩下的那一格没接线藏起来。
  // data-demo="fixtures" 这枚机器标记随常量一起摘：这一屏已经没有 fixture 输入了。
  it('总览的诚实牌仍在（徽标一处 + 一句人话），但不再自称 fixtures', () => {
    const s = source('DashboardPanel.vue')
    expect(s).not.toContain('data-demo=')
    expect(s).toContain('data-testid="dashboard-demo-flag"')
    expect(s.match(/class="demo-flag"/g)).toHaveLength(1)
    expect(s).toContain('演示数据')
  })

  // 钉的是「改回假数据就必须红」：告警账本没有 severity 这一列，谁要再把演示常量
  // 那套 critical/warning 权威语义搬回总览，前两针立刻撞。
  it('总览不再收 severity/critical，也不许把告警语义贴到配色上；洞察与审批页维持归零', () => {
    const s = source('DashboardPanel.vue')
    expect(s).not.toMatch(/critical/)
    expect(s).not.toMatch(/severity/)
    expect(s).not.toMatch(/warning[\s\S]{0,40}(#|rgba?\()/)
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