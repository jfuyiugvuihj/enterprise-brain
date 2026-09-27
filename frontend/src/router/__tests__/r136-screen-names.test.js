/**
 * R136 判据① · 屏名只有一个来源：路由表的 meta.title
 *
 * 要销的病（跟进单 §71 亲读代码点名）：顶栏只认 meta.title，而页内标题是面板自己写的
 * 一句字。于是「洞察」这屏顶栏写「洞察」、页内写「异常与告警」，同一屏两个名字，用户在
 * 顶栏看到的是旧名。改名不改第二处，就是漂移；两处各写一份，迟早漂。
 *
 * 三条腿（各自验各自能验的，不假装验过别的）：
 *   ① 定名精确：计划书 §四 那五个名字，一枚不多一枚不少，旧名一律不得再作屏名。
 *   ② 派生同源：侧栏文案与顶栏标题都是 meta.title 的派生视图 —— 取的是同一条路由记录
 *      上的同一格，不是「两份相等的字符串」。
 *   ③ 页内同源：把每一屏真的渲染一遍，从 HTML 里取页级标题（画法全站只有一种：
 *      header.panel-head 里的 <h3>），与 meta.title 逐字比。
 *
 * 为什么第 ③ 条只看 panel-head 的 h3：ChatPanel 的 <h1>企业智脑</h1> 是空态里的品牌字、
 * DashboardPanel 的 <h2> 是卡片小节的标题，都不是屏名。把规则定成「任何 h 级标题」等于
 * 把两种东西混进一枚断言，下一次改文案就会红得莫名其妙。R136 写下这条时带页级屏名的屏是三枚，
 * R315 交出第四枚「交成果」：它凭什么不是从顶栏读 —— 计划书把它的入口名定成员工嘴里的动词，
 * 员工从侧栏进来第一眼要看见的是同一句字（跟进单「说人话」硬规矩③），于是页内照既有唯一画法补一句
 * <h3>，并由下面的同源用例真渲染逐字比对 meta.title，而不是允许它另起一名。
 * 用例同时钉死这个枚数：第五枚偷偷加一句屏名，或这四枚里有谁把标题删了，都会红。
 *
 * 反证（跑完即还原）：
 *   把任一 meta.title 改回旧名（'异常与告警' → '洞察'）→ ①定名 与 ③页内同源 同时红。
 *   把 App.vue 的顶栏改回硬编码一句屏名 → ②同源 的字面量那条红。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { navigation, routes, screenIds } from '../index.js'
import AdminPanel from '../../components/AdminPanel.vue'
import { FEED_TABS } from '../feed-tabs.js'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const app = read('../../App.vue')

/**
 * 计划书 §四「八屏逐屏处置」给一级屏定的名（写这里是一次独立的引用，不是第二处真源：
 * 生产代码里的屏名只有 routes[].meta.title 那一处，这一枚常数只存在于用例文件里）。
 */
const PLAN_TITLES = {
  overview: '总览',
  feed: '喂料',
  chat: '问一句',
  insights: '异常与告警',
  approval: '审批与待办',
  // R315 判据① 追加：这一枚的出处不是 §四 那张表，而是 docs/frontend-plan-2026-09-14.md:132
  // 工作区映射表里那一行「（新增）『交成果』」—— 后端依赖 B-1 / R2 今天都已交付，屏才有资格落地；
  // 员工用词那一头见 docs/handoff/2026-09-15-backend-followup-requests.md:2099 硬规矩③。
  artifacts: '交成果',
}

/** 合屏之前与改名之前的旧屏名：一律不得再作任何一屏的 meta.title。 */
const RETIRED_TITLES = ['文档', '数据', '洞察', '审批', '对话', '图谱']

const screenRoutes = routes.filter(route => route.meta?.screen)
const primaryRoutes = screenRoutes.filter(route => route.meta.primary !== false)
const byName = new Map(routes.map(route => [String(route.name), route]))

/** 页级屏名的唯一画法：<header class="panel-head"> 里的第一个 <h3>。 */
const PAGE_TITLE_RE = /<header\b[^>]*class="[^"]*\bpanel-head\b[^"]*"[^>]*>[\s\S]*?<h3\b[^>]*>([^<]*)<\/h3>/
const pageTitleOf = html => {
  const match = PAGE_TITLE_RE.exec(html)
  return match ? match[1].trim() : ''
}

/** 屏名以外的东西不许当屏名用：注释里出现旧名是叙述，不算。 */
function withoutComments(text) {
  return text
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[\s;:{}])\/\/[^\n]*/g, '$1')
}

describe('R316 判据⑤ · 追加的那一枚屏不改计划书那笔账，也不自带第二份屏名', () => {
  it('§四 的定名名单没被 admin 挤进去（R315 只加了「交成果」那一行），屏名仍然全站唯一', () => {
    // R316 当年这条钉的是「screenIds 仍是那五枚」；R315 判据④ 把一级入口换成六枚，加的就是 artifacts。
    // 换的是名单本身，不是断言强度：仍然逐字相等、仍然多一枚少一枚都红；admin 那一格两条原样留着。
    expect(screenIds).toEqual(['overview', 'feed', 'insights', 'approval', 'chat', 'artifacts'])
    expect(PLAN_TITLES).not.toHaveProperty('admin')
    const admin = routes.find(route => route.name === 'admin')
    expect(admin.meta.title).toBe('账号与角色')
    const titles = screenRoutes.map(route => route.meta.title)
    expect(new Set(titles).size, '两屏共用了同一个屏名').toBe(titles.length)
  })

  it('admin 这一屏页内不写第二份屏名：它没有页级标题（R315 也没给它补一句）', async () => {
    const html = await renderToString(h(AdminPanel))
    expect(pageTitleOf(html), 'AdminPanel 里又写了一句屏名').toBe('')
  })
})

describe('R136 判据① · 计划书 §四 的定名落在 meta.title 上', () => {
  it('一级屏就这六枚，名字逐字对上计划书（一枚不许多、不许少）', () => {
    // R315 判据④ 往同一枚定长名单里加一项（artifacts），并往 PLAN_TITLES 加那一行出处；
    // 两条 toEqual 的写法一字未改，名字与 meta.title 仍然是逐字对账，没降成包含式。
    expect(screenIds).toEqual(['overview', 'feed', 'insights', 'approval', 'chat', 'artifacts'])
    expect(screenIds.map(id => byName.get(id).meta.title)).toEqual(
      screenIds.map(id => PLAN_TITLES[id]),
    )
  })

  it('旧屏名一枚都不许再作 meta.title（改名不是加别名）', () => {
    const titles = screenRoutes.map(route => route.meta.title)
    for (const retired of RETIRED_TITLES) {
      expect(titles, `${retired} 还在被当成一屏的名字用`).not.toContain(retired)
    }
  })

  it('改名的两枚正是 §71 点名的那两处：洞察 → 异常与告警、审批（旧名）→ 审批与待办（R174 定名）', () => {
    expect(byName.get('insights').meta.title).toBe('异常与告警')
    expect(byName.get('approval').meta.title).toBe('审批与待办')
    // 图谱不在 §四 的定名栏里，但它页内早就写着「知识图谱」，同源就一并跟上
    expect(byName.get('graph').meta.title).toBe('知识图谱')
  })
})

describe('R136 判据① · 顶栏与侧栏都是 meta.title 的派生视图', () => {
  it('每一枚一级屏的侧栏文案与它自己那条路由的 meta.title 是同一格（不是两份相等的字）', () => {
    expect(navigation).toHaveLength(screenIds.length)
    for (const item of navigation) {
      const route = byName.get(item.id)
      expect(route, `${item.id} 的导航项指不到任何路由`).toBeTruthy()
      expect(item.label, `${item.id} 的侧栏文案不是从 meta.title 派生的`).toBe(route.meta.title)
    }
  })

  it('App.vue 只把 meta.title 交出去，自己不抄任何一句屏名', () => {
    const product = withoutComments(app)
    // 顶栏取的是路由元信息（这一格已在 routes.test.js 钉过接线，这里补的是「不许出现第二份字」）
    expect(product).toMatch(/\{\{\s*activeMeta\.title\s*\}\}/)
    // 五枚定名一枚都不许以字面量的形式出现在 App.vue 的正文里（注释里叙述旧名不算）：
    // 出现了就是「屏名有两处」，改一处忘一处。
    for (const title of Object.values(PLAN_TITLES)) {
      expect(product, `App.vue 里硬编码了屏名「${title}」，等于开了第二处真源`).not.toContain(title)
    }
  })
})

describe('R136 判据① · 页内标题与 meta.title 同源（真渲染比对）', () => {
  /**
   * 带页级屏名的屏：R136 定下三枚，R315 交出第四枚「交成果」（凭什么不是从顶栏读，见文件头那段）。
   * 第五枚要加，先想清楚它凭什么不是从顶栏读 —— 名单仍然定长逐字相等，加了不许漏、漏了不许多。
   */
  const WITH_PAGE_TITLE = ['insights', 'approval', 'graph', 'artifacts']

  it('每一屏渲染出来的页级标题与 meta.title 逐字相等', async () => {
    for (const route of screenRoutes) {
      const html = await renderToString(h(route.component))
      const page = pageTitleOf(html)
      if (!page) {
        expect(WITH_PAGE_TITLE, `${String(route.name)} 新加了一句页级屏名`).not.toContain(String(route.name))
        continue
      }
      expect(page, `${String(route.name)} 页内写的屏名「${page}」与 meta.title「${route.meta.title}」不是一份字`).toBe(route.meta.title)
    }
  })

  it('页级标题的枚数钉死：四枚有、三枚没有（喂料与总览与问一句靠顶栏说名字）', async () => {
    const withTitle = []
    for (const route of screenRoutes) {
      const html = await renderToString(h(route.component))
      if (pageTitleOf(html)) withTitle.push(String(route.name))
    }
    // R315 判据④ 换号：三枚 → 四枚，加的是 artifacts（理由写在 WITH_PAGE_TITLE 那段），
    // toEqual 与 toHaveLength 两枚都保留、都没换成包含式 —— 第五枚偷偷加标题照样当场红。
    expect(withTitle.sort()).toEqual(WITH_PAGE_TITLE.slice().sort())
    expect(withTitle).toHaveLength(4)
  })

  it('「喂料」这一屏不自带页级标题：屏名只有顶栏一处，标签文案说的是内容', async () => {
    const feed = byName.get('feed')
    const html = await renderToString(h(feed.component))
    expect(pageTitleOf(html), 'FeedPanel 里又写了一句屏名').toBe('')
    // 标签文案（文档 / 数据）说的是这一格装的内容，不是屏名：它们只许出现在标签条上，
    // 一处一格，多一处就是有人又写了一遍。
    // @vue/server-renderer 在插值两侧留分段注释（<!--[--> 与 <!--]-->），取文案要先剥注释。
    const labelSpans = out => out
      .split('<span class="ui-tabs__label">')
      .slice(1)
      .map(chunk => chunk.split('</span>')[0].replace(/<!--[\s\S]*?-->/g, '').trim())
    expect(html).toContain('data-testid="ui-tabs"')
    // 标签条就是那张表的派生视图：枚数、顺序、文案都取自表，一格不多一格不少，也没有第二遍
    expect(labelSpans(html)).toEqual(FEED_TABS.map(tab => tab.label))
  })
})
