/**
 * R136 判据②③ · 「喂料」合屏：老地址不许白屏、图谱入口不许被顺手改掉
 *
 * 这一枚文件比 routes.test.js 多做一件事：把整屏连**路由上下文**一起渲染
 * （createSSRApp + app.use(router) + renderToString），于是「重定向之后到底渲染没渲染出
 * 东西」是拿 HTML 说话。白屏的定义就是没有 HTML，光比对路由名字证不了这件事。
 *
 * 顺带把 §71 那半句不成立的判断留在这儿，免得下一班又照抄：
 * 「图谱仍可从文档预览进入」今天为假 —— 全量扫 src/ 没有任何指向 /graph 的出口，而且
 * routes.test.js:189 与 navigation.test.js:63 两枚已并树的断言正明令禁止从面板绕后门。
 * 所以这一枚文件只钉得住的真事实：/graph 是真地址、深链解析并渲染 GraphPanel、
 * primary:false 让侧栏派生不出它的入口。「改名改到把入口删了」这半句由这三条挡住；
 * 「从预览进图谱」要等谁真把那条链接加上，再由那一单补它的用例。
 *
 * 反证（跑完即还原）：
 *   摘掉 FEED_TABS 派生的那组老地址 redirect → 本文件「/docs /data 不白屏」当场红。
 *   把图谱那条 primary:false 摘掉            → 「侧栏派生不出图谱入口」当场红。
 */
import { describe, expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { createMemoryHistory, RouterView } from 'vue-router'
import { renderToString } from '@vue/server-renderer'
import DataPanel from '../../components/DataPanel.vue'
import DocPanel from '../../components/DocPanel.vue'
import FeedPanel from '../../components/FeedPanel.vue'
import GraphPanel from '../../components/GraphPanel.vue'
import { createAppRouter, navigation, routes, screenIds, screenRouteIds } from '../index.js'
import {
  FEED_SCREEN,
  FEED_TAB_PARAM,
  FEED_TABS,
  LEGACY_FEED_PATHS,
  resolveFeedTab,
} from '../feed-tabs.js'

const byName = new Map(routes.map(route => [String(route.name), route]))

/**
 * 老地址 -> 该落到哪一枚标签 -> 那块面板渲染出来的根 testid。
 * 这一列写在用例里是对 §四 的独立引用，不是生产代码的第二份：生产侧只认 FEED_TABS。
 */
const LEGACY_LANDINGS = [
  ['/docs', 'docs', 'documents-panel'],
  ['/data', 'data', 'data-panel'],
]
const stripComments = html => html.replace(/<!--[\s\S]*?-->/g, '')

/** 走一趟真实导航（含重定向），再把落地那一屏连路由上下文一起渲染。 */
async function visit(location) {
  const router = createAppRouter({ history: createMemoryHistory() })
  await router.push(location)
  const app = createSSRApp({ render: () => h(RouterView) })
  app.use(router)
  const html = await renderToString(app)
  const current = router.currentRoute.value
  return {
    current,
    html,
    landed: String(current.name),
    tab: current.query[FEED_TAB_PARAM],
    path: current.path,
  }
}

describe('R136 判据② · 一屏两标签，标签清单只有一处声明', () => {
  it('「喂料」挂的是 FeedPanel，meta.tabs 就是 feed-tabs.js 那张表本身（同引用，不是抄一份）', () => {
    const feed = byName.get(FEED_SCREEN)
    expect(feed, '路由表里没有喂料这一屏').toBeTruthy()
    expect(feed.component).toBe(FeedPanel)
    expect(feed.meta.screen).toBe(true)
    expect(feed.meta.title).toBe('喂料')
    expect(feed.meta.tabs).toBe(FEED_TABS)
    expect(FEED_TABS.map(tab => tab.id)).toEqual(['docs', 'data'])
    expect(FEED_TABS.map(tab => tab.label)).toEqual(['文档', '数据'])
    // 标签带的就是合屏之前那两块面板，组件本体一字节未改
    expect(FEED_TABS.map(tab => tab.component)).toEqual([DocPanel, DataPanel])
  })

  it('/feed 渲染出标签条与默认那一枚面板：默认取自表的顺序，不是另写一个常数', async () => {
    const { html, landed } = await visit(`/${FEED_SCREEN}`)
    expect(landed).toBe(FEED_SCREEN)
    expect(html).toContain('data-testid="feed-panel"')
    expect(html).toContain('data-testid="ui-tabs"')
    for (const tab of FEED_TABS) expect(html).toContain(`data-testid="ui-tabs-tab-${tab.id}"`)
    // 默认那一枚标签 = 表的第一枚，它渲染的就是文档面板
    expect(FEED_TABS[0].id).toBe('docs')
    expect(html).toContain('data-testid="documents-panel"')
  })

  it('标签条的无障碍名跟着 meta.title 走：屏名与顶栏是同一格字，不是第二处', async () => {
    const { html } = await visit(`/${FEED_SCREEN}?${FEED_TAB_PARAM}=data`)
    expect(html).toContain('aria-label="喂料"')
    // 只有当前那一枚标签的面板在渲染：两块同时挂就是两份请求、两份滚动位置
    expect(html).toContain('data-testid="data-panel"')
    expect(html).not.toContain('data-testid="documents-panel"')
  })

  it('地址里那格标签认不出就回默认一枚，而不是画一片空白工作台', () => {
    expect(resolveFeedTab('data').id).toBe('data')
    for (const junk of [undefined, '', 'nope', null, 42, ['docs'], {}]) {
      expect(resolveFeedTab(junk).id).toBe(FEED_TABS[0].id)
    }
    // 表里没有谁就还谁，这条不靠组件里写 if
    expect(resolveFeedTab('docs').component).toBe(DocPanel)
  })
})

describe('R136 判据② · 老地址 /docs、/data 重定向到新屏，不许白屏', () => {
  it('老屏地址由标签表派生，一条不多一条不少，而且都不是屏', () => {
    expect(LEGACY_FEED_PATHS).toEqual(['/docs', '/data'])
    for (const path of LEGACY_FEED_PATHS) {
      const record = routes.find(route => route.path === path)
      expect(record, `${path} 这条地址没了 —— 老链接会掉进通配兜底`).toBeTruthy()
      expect(record.meta.screen, `${path} 还冒充一屏`).toBeFalsy()
      expect(record.meta.legacyScreenOf).toBe(FEED_SCREEN)
      expect(typeof record.redirect).toBe('function')
    }
  })

  for (const [path, tabId, panelTestid] of LEGACY_LANDINGS) {
    it(`${path} 落在喂料屏上，并且真渲染出那块面板`, async () => {
      const { landed, path: at, tab, html } = await visit(path)
      expect(landed, `${path} 没落在喂料屏`).toBe(FEED_SCREEN)
      expect(at).toBe(`/${FEED_SCREEN}`)
      expect(tab).toBe(tabId)
      // 不白屏的判据是 HTML 里有内容，不是路由名字对上了
      expect(html.length).toBeGreaterThan(200)
      expect(stripComments(html)).toContain(`data-testid="${panelTestid}"`)
    })

    it(`${path} 用名字跳（总览的 @goto 走的就是这条）也落得到`, async () => {
      const { landed, tab, html } = await visit({ name: tabId })
      expect(landed).toBe(FEED_SCREEN)
      expect(tab).toBe(tabId)
      expect(stripComments(html)).toContain(`data-testid="${panelTestid}"`)
    })
  }

  it('重定向把 query 与 hash 原样带走：面板认得的那几格不能丢', async () => {
    const { current, tab } = await visit('/docs?file=%E9%A2%84%E7%AE%97%E8%A1%A8.xlsx#section-2')
    expect(current.query.file).toBe('预算表.xlsx')
    expect(current.hash).toBe('#section-2')
    expect(tab).toBe('docs')
  })

  it('带不上的那一格写清楚：地址尾段与 ?tab 自相矛盾时，尾段赢', async () => {
    // /docs?tab=data 是两个说法，老链接的语义在路径上，不在参数上
    const { tab, landed } = await visit('/docs?tab=data')
    expect(landed).toBe(FEED_SCREEN)
    expect(tab).toBe('docs')
    const reversed = await visit('/data?tab=docs')
    expect(reversed.tab).toBe('data')
  })

  it('老屏名不再是屏，但仍是入口：从入口表里掉出去就是总览上的死键', () => {
    for (const [, tabId] of LEGACY_LANDINGS) {
      expect(screenIds, `${tabId} 不该还在一级屏里`).not.toContain(tabId)
      expect(navigation.map(item => item.id)).not.toContain(tabId)
      expect(screenRouteIds, `${tabId} 从可达落点里掉了 —— @goto 会按不下去`).toContain(tabId)
    }
  })
})

describe('R136 判据③ · 图谱维持非一级，功能一项没撤', () => {
  it('primary:false 还在，侧栏派生不出图谱入口', () => {
    const graph = byName.get('graph')
    expect(graph.path).toBe('/graph')
    expect(graph.component).toBe(GraphPanel)
    expect(graph.meta.primary, '图谱被挂回一级导航了').toBe(false)
    expect(navigation.map(item => item.id)).not.toContain('graph')
    expect(screenIds).not.toContain('graph')
    // 一级屏就是五枚，没多没少；图谱仍然在屏的全集里，所以深链不是走通配兜底
    expect(screenIds).toHaveLength(5)
    expect(screenRouteIds).toContain('graph')
  })

  it('/graph 是真地址：深链解析并渲染出图谱面板本身，不白屏', async () => {
    const { landed, html } = await visit('/graph')
    expect(landed).toBe('graph')
    expect(stripComments(html)).toContain('data-testid="graph-panel"')
    expect(html.length).toBeGreaterThan(200)
  })
})
