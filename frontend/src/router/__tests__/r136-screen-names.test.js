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
 *   ③ 页内同源：把每一屏真的渲染一遍，从 HTML 里取页级标题（画法全仓现读三式，见 PAGE_TITLE_SHAPES），
 *      与 meta.title 逐字比；同一屏同时命中两式也红 —— 一屏只许有一处主标题。
 *
 * 为什么第 ③ 条从「只看 panel-head 的 h3」扩成认三式（R421）：R136 写下这枚钉时，「画法全站只有一种」
 * 在当时是真话；到 R412 手里它已经是假话 —— 全仓页内主标题实测三式：DocPanel 用 div.panel-hd 里的
 * strong（src/components/DocPanel.vue 里 div.panel-hd-left 那一格），ChatPanel 用 [data-testid=chat-screen-name]
 * （src/components/ChatPanel.vue:1813），两式都落在旧正则的射程之外。后果不是风格问题：「知识库」正是
 * 长在 ② 那一格里活到 R412 的，而这枚钉从头到尾绿着 —— 一枚看不见病灶的钉，它的绿就是假绿。今天把
 * 射程铺满三式，「第二枚屏名偷偷长在页内主标题位」这条路从此不再取决于它用的是哪一式。
 * 边界仍然守着，没有放宽成「任何 h 级标题」：ChatPanel 的 <h1>企业智脑</h1> 是空态里的品牌字、
 * DashboardPanel 的 <h2> 是卡片小节的标题，都不是屏名；把两种东西混进一枚断言，下一次改文案就会红得
 * 莫名其妙。所以这枚钉认的是【主标题位的那三格画法】，不是【那三种标签】。
 * R136 写下这条时带页级屏名的屏是三枚，R315 交出第四枚「交成果」：它凭什么不是从顶栏读 —— 计划书把
 * 它的入口名定成员工嘴里的动词，员工从侧栏进来第一眼要看见的是同一句字（跟进单「说人话」硬规矩③），
 * 于是页内照既有画法补一句 <h3>，并由下面的同源用例真渲染逐字比对 meta.title，而不是允许它另起一名。
 * 名单到今天是六枚：feed 与 chat 不是新长出来的两枚屏名，而是早就写在页内、这枚钉今天才看见的两枚
 * （R421 换的是可见性，不是断言强度）。用例同时钉死这个枚数：第七枚偷偷加一句屏名，或这六枚里有谁把
 * 标题删了，都会红。
 *
 * 反证（跑完即还原）：
 *   把任一 meta.title 改回旧名（'异常与告警' → '洞察'）→ ①定名 与 ③页内同源 同时红。
 *   把 App.vue 的顶栏改回硬编码一句屏名 → ②同源 的字面量那条红。
 *   R421 再补三把（牙检逐把读数在派工回执）：改掉 router/index.js 的 meta.title → ③ 跟着红（页内那句
 *   是派生，不是第二份真源）；把旧叫法塞回 DocPanel 主标题那一格 → ③ 红；把 feed 从 WITH_PAGE_TITLE
 *   里摘掉 → 枚数那条红。
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
  // 员工用词那一头见 docs/handoff/2026-09-15-backend-followup-requests.md:2114 硬规矩③。
  artifacts: '交成果',
}

/** 合屏之前与改名之前的旧屏名：一律不得再作任何一屏的 meta.title。 */
const RETIRED_TITLES = ['文档', '数据', '洞察', '审批', '对话', '图谱']

const screenRoutes = routes.filter(route => route.meta?.screen)
const primaryRoutes = screenRoutes.filter(route => route.meta.primary !== false)
const byName = new Map(routes.map(route => [String(route.name), route]))

/**
 * 页级屏名的画法，全仓现读三式（R421；R412 逐屏点名过，本件是那三式的登记处）。两格要紧事都在这枚
 * 钉自己犯过的错上：
 *   · 每一式只取自己那一格【有界】的区段，否则正则会一路滑到页面深处，把某一枚小节标题当成主标题；
 *   · 必须容得下 SSR 给每个标签补的 data-v-* 作用域属性：照模板里那个裸标签形状去匹配渲染产物，实测
 *     九屏全部取不到 —— 那样写出来的钉会一路绿到底，是这类钉最容易犯的假绿。
 */
const PAGE_TITLE_SHAPES = [
  {
    shape: 'header.panel-head 里的第一个 h3',
    pick(html) {
      const open = /<header\b[^>]*class="[^"]*\bpanel-head\b[^"]*"[^>]*>/.exec(html)
      if (!open) return ''
      const body = html.slice(open.index + open[0].length)
      const end = body.indexOf('</header>')
      const hit = /<h3\b[^>]*>([^<]*)<\/h3>/.exec(end < 0 ? body : body.slice(0, end))
      return hit ? hit[1].trim() : ''
    },
  },
  {
    shape: 'div.panel-hd 里、本格收口之前的第一个 strong',
    pick(html) {
      const cell = /<div\b[^>]*class="panel-hd"[^>]*>([\s\S]*?)<\/div>/.exec(html)
      if (!cell) return ''
      const hit = /<strong\b[^>]*>([^<]*)<\/strong>/.exec(cell[1])
      return hit ? hit[1].trim() : ''
    },
  },
  {
    shape: '[data-testid=chat-screen-name] 那一格',
    pick(html) {
      const hit = /data-testid="chat-screen-name"[^>]*>([^<]*)</.exec(html)
      return hit ? hit[1].trim() : ''
    },
  },
]

/** 命中几式、各是什么字，全都交回用例判；这里不替它挑一枚「最像的」。 */
const pageTitleHits = html => PAGE_TITLE_SHAPES
  .map(entry => ({ shape: entry.shape, text: entry.pick(html) }))
  .filter(hit => hit.text)

/** 一屏只许有一处主标题：同时命中两式当场红，不给「两处各自都好看」留活路。 */
const pageTitleOf = (html, who) => {
  const hits = pageTitleHits(html)
  expect(hits.length, `${who} 用多于一式画了主标题，一屏只许有一处：${JSON.stringify(hits)}`).toBeLessThanOrEqual(1)
  return hits.length ? hits[0].text : ''
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
    expect(pageTitleOf(html, 'admin'), 'AdminPanel 里又写了一句屏名').toBe('')
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
   * 带页级屏名的屏：R136 定下三枚，R315 交出第四枚「交成果」（凭什么不是从顶栏读，见文件头那段），
   * R421 把画法从一种扩到三式之后又登记两枚 —— feed 那一枚是 DocPanel.vue 里 div.panel-hd > div.panel-hd-left > strong（R412 把
   * 那一句旧叫法换成了 meta.title），chat 那一枚是 ChatPanel.vue:1813 的 [data-testid=chat-screen-name]
   * （R268 丙组早就硬写在页内、逐字对账 meta.title 的那一句）。这两枚不是本单新长的屏名，是这枚钉
   * 今天才看见的既有屏名：名单从四枚换成六枚，换的是可见性，不是断言强度。
   * 第七枚要加，先想清楚它凭什么不是从顶栏读 —— 名单仍然定长逐字相等，加了不许漏、漏了不许多。
   * R494 交出第七枚：profile 的页级屏名来自 ProfilePanel.vue 自己那一句页头，不是从顶栏读的，
   * 而且它与 meta.title 逐字相等由上一枚钉盯着；这里仍然只往同一枚定长名单加一项，没换成包含式。
   */
  const WITH_PAGE_TITLE = ['insights', 'approval', 'graph', 'artifacts', 'feed', 'chat', 'profile']

  it('每一屏渲染出来的页级标题与 meta.title 逐字相等（三式都算，同时命中两式也算红）', async () => {
    for (const route of screenRoutes) {
      const name = String(route.name)
      const html = await renderToString(h(route.component))
      const page = pageTitleOf(html, name)
      if (!page) {
        expect(WITH_PAGE_TITLE, `${name} 新加了一句页级屏名`).not.toContain(name)
        continue
      }
      expect(page, `${name} 页内写的屏名「${page}」与 meta.title「${route.meta.title}」不是一份字`).toBe(route.meta.title)
    }
  })

  it('页级标题的枚数钉死：七枚有、三枚没有（总览与账号与留痕靠顶栏说名字）', async () => {
    const withTitle = []
    for (const route of screenRoutes) {
      const html = await renderToString(h(route.component))
      if (pageTitleHits(html).length) withTitle.push(String(route.name))
    }
    // R315 判据④ 换过一次号（三枚 → 四枚），R421 再换一次（四枚 → 六枚，加的是 feed 与 chat，
    // 理由写在 WITH_PAGE_TITLE 那段）。两次换的都是名单本身：toEqual 与 toHaveLength 两枚都保留、
    // 都没换成包含式 —— 第七枚偷偷加一句标题，或这六枚里有谁把标题删了，照样当场红。
    expect(withTitle.sort()).toEqual(WITH_PAGE_TITLE.slice().sort())
    expect(withTitle).toHaveLength(7)
  })

  it('「喂料」这一屏只说一句屏名：页内那一句逐字等于 meta.title，标签文案说的是内容', async () => {
    const feed = byName.get('feed')
    const html = await renderToString(h(feed.component))
    // 这一格以前钉的是 toBe('')，而它当时绿着：R412 把主标题位那句旧叫法换成 meta.title 之后，这一屏
    // 其实【已经】有了一句页级屏名，旧断言只是看不见它。今天改成对现读的屏名逐字比 —— 不是允许这一屏
    // 多一处名字，是把那一处既有的名字纳进「屏名只有一处真源」这条账：它必须逐字等于 meta.title。
    expect(pageTitleOf(html, 'feed'), '喂料屏把页内主标题弄丢了：名字不许靠删文案统一掉').toBe(feed.meta.title)
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
    // 标签条与页级屏名是两格，不许互相串字：这一屏的主标题位说的是屏名，标签条说的是内容名。
    expect(labelSpans(html), '标签条里混进了一格屏名：同一屏上就是两处名字').not.toContain(feed.meta.title)
  })
})
