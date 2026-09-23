/**
 * R104 · 「屏 ↔ URL」的唯一真源
 *
 * 改造前这件事分两张表：App.vue 的 navigation 数组决定侧栏长什么样，workspaceMap 决定点下去
 * 渲染谁，两张表之间没有任何机器约束，加一屏要改两处，漏一处就是「导航里有、点下去一片空白」。
 * 现在一条路由记录同时给出 URL、屏 id、标题、图标与面板组件，侧栏导航（navigation）是它的
 * 派生视图 —— 漂移在结构上就不可能，而不是靠测试兜住。
 *
 * 默认落点选 overview：与改造前 App.vue 里 activeTab 的初值一致，登录后进的还是总览。
 * '/' 与未认识到的地址各一条 redirect 指过去，落点有且只有一个。
 *
 * history 模式取 createWebHistory：deploy/nginx.conf 的 location / 已经是
 * `try_files $uri $uri/ /index.html`，/docs 这类深链在交付环境里落得到 index.html，
 * 不必退回 hash 模式；同事之间转发的链接也就不会多出一段 #。
 *
 * R136（屏名与工作区映射）在这张表上追加两件事，都在同一处声明，不另开口子：
 *  ① 屏名只有 meta.title 一个人说。顶栏（App.vue 的 activeMeta.title）与侧栏
 *    （navigation 的派生）取的都是这一格，计划书 §四 的定名就写在这里：
 *    总览 / 喂料 / 问一句 / 异常与告警 / 审批与待办。旧名「洞察 / 审批 / 对话」是
 *    §71 点名的病：页内标题早就改了，顶栏还认旧名，同一屏两个名字。
 *  ② 「喂料」= 文档 + 数据 两标签一屏，老地址 /docs、/data 不许白屏，见下面由
 *    FEED_TABS 派生的那组 redirect。标签与老地址同是一条记录的两张脸，写在
 *    src/router/feed-tabs.js 那一张表里，这里不抄第二份。
 */
import { createRouter, createWebHistory } from 'vue-router'

import ApprovalPanel from '../components/ApprovalPanel.vue'
import ChatPanel from '../components/ChatPanel.vue'
import DashboardPanel from '../components/DashboardPanel.vue'
import FeedPanel from '../components/FeedPanel.vue'
import GraphPanel from '../components/GraphPanel.vue'
import InsightPanel from '../components/InsightPanel.vue'

// 「喂料」的标签清单与它名下的老地址是同一条记录的两张脸，只写在 feed-tabs.js 一遍；
// 这一枚文件是消费方。DocPanel / DataPanel 的 import 随之搬去那张表里。
import { FEED_SCREEN, FEED_TABS, LEGACY_FEED_NAMES, legacyFeedRedirect } from './feed-tabs.js'

/** 登录后与未认识地址的落点，也是 '/' 唯一指向的那一屏。 */
export const DEFAULT_SCREEN = 'overview'

/**
 * meta 约定（判据 1：一屏一路由，name 即屏 id，title 必填）：
 *   screen    这一条是一「屏」，会被 <router-view> 渲染
 *   title     屏名，全站唯一一处：顶栏、浏览器标签标题、侧栏文案都从这一格来。
 *             面板页内另写一句屏名的，R136 那枚同源用例当场红
 *   icon      侧栏图标的 SVG path，原来手写在 navigation 数组里，现在跟着屏走
 *   tabs      「喂料」这类一屏多标签才有：标签清单，值就是 feed-tabs.js 那张表
 *   primary   false = 不进一级导航。只有图谱这一条，理由写在它下面
 *   keepAlive 切走不卸载。只有对话这一条，理由见 cachedScreens
 *   legacyScreenOf 挂在老地址上（下面那组派生 redirect），值是它现在真正落到的屏
 */
export const routes = [
  { path: '/', redirect: { name: DEFAULT_SCREEN } },
  {
    path: '/overview',
    name: 'overview',
    component: DashboardPanel,
    meta: { screen: true, title: '总览', icon: 'M4 11.5 12 4l8 7.5v8.5a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z' },
  },
  // R136 判据② · 文档与数据合成一屏两标签：这一屏只挂 FeedPanel，两块面板一字节未改，
  // 各自仍管自己的接口与交互。图标沿用原「文档」那枚 —— 本单只重排名称与挂载，
  // 不顺手发明美术；原「数据」那枚 path 还活在 DashboardPanel 的快捷入口里，没有丢。
  {
    path: `/${FEED_SCREEN}`,
    name: FEED_SCREEN,
    component: FeedPanel,
    meta: { screen: true, title: '喂料', icon: 'M6 3h8l4 4v14H6zM14 3v5h5M9 13h6M9 17h6', tabs: FEED_TABS },
  },
  {
    path: '/insights',
    name: 'insights',
    component: InsightPanel,
    meta: { screen: true, title: '异常与告警', icon: 'M4 17l5-5 4 3 7-8M17 7h3v3' },
  },
  {
    path: '/approval',
    name: 'approval',
    component: ApprovalPanel,
    // R174 判据③ · 定名「审批与待办」：这一屏今天挂着真待办（GET /hitl/pending）与真审批
    // （POST /approve），而「报销」是一枚业务专属词 —— 客户一装机就以为产品只管报销。
    meta: { screen: true, title: '审批与待办', icon: 'M6 4h12v16H6zM9 9h6M9 13h6M9 17h3M5 12l3 3 6-7' },
  },
  {
    path: '/chat',
    name: 'chat',
    component: ChatPanel,
    meta: { screen: true, title: '问一句', icon: 'M5 6h14v10H9l-4 4zM8 10h8M8 13h5', keepAlive: true },
  },
  // D13①（计划书 §6.1）撤的是图谱的一级入口，不是功能：它的定位早已裁定为「候选断言采集表」
  // 而非推理引擎（docs/design/knowledge-graph-positioning.md），摆在侧栏一级就是误导使用者。
  // primary:false 让它派生不出导航项，但 /graph 是真地址：这一条就是 §44.1 留给 R104 的
  // 「非一级落点」，图谱屏从此既能被深链转发，也不会再出现在侧栏里。
  {
    path: '/graph',
    name: 'graph',
    component: GraphPanel,
    meta: { screen: true, title: '知识图谱', primary: false },
  },
  // R136 判据② · 老地址不许白屏：/docs、/data 是合屏之前的两屏，存量链接与总览往
  // @goto 发的落点今天仍指着这两个名字。这一组由 FEED_TABS 派生，于是「加第三枚标签」
  // 与「老链接指向哪」是同一件事，不会只改到一半。它们不是屏（不带 meta.screen），
  // 所以侧栏派生不出它们的入口，但仍然是可达的落点：认不出就是死键。
  ...FEED_TABS.map(tab => ({
    path: `/${tab.id}`,
    name: tab.id,
    redirect: legacyFeedRedirect(tab.id),
    meta: { legacyScreenOf: FEED_SCREEN },
  })),
  // 未认识的地址回默认落点，而不是留一片空白的工作台：地址栏写错一个字母不该看起来像系统坏了。
  // 这里刻意用 path 形式而不是 { name: DEFAULT_SCREEN }：通配记录自带 pathMatch 参数，
  // 按名字回落实例会把那个参数一起带过去再丢掉，于是每一次认错地址都在控制台刷一条
  // 「Discarded invalid param(s) "pathMatch"」。routes.test.js 把这条钉住了。
  { path: '/:pathMatch(.*)*', name: 'unknown-screen', redirect: { path: '/overview' } },
]

const isScreen = route => Boolean(route.meta?.screen)
const isPrimaryScreen = route => isScreen(route) && route.meta.primary !== false

/**
 * 侧栏导航：路由表的派生视图，顺序就是路由表顺序。
 * 面板与 App.vue 都不许再抄一份这样的数组，否则又回到两张表。
 */
export const navigation = routes.filter(isPrimaryScreen).map(route => ({
  id: route.name,
  label: route.meta.title,
  icon: route.meta.icon,
}))

/** 一级屏 id（= navigation 的 id 列）。 */
export const screenIds = navigation.map(item => item.id)

/**
 * 一个落点（goto 目标 / 深链名字）在不在表上，看这一枚：屏的全集，含非一级的图谱，
 * 再加上 R136 合屏之后仍要可达的老屏名。
 *
 * 老屏名不许从这张表里掉出去：DashboardPanel 的指标卡与快捷入口还在往 'docs' / 'data'
 * 发 @goto，App.vue 的 openScreen 认不出就当没这个按钮 —— 按下去什么都不发生的那种
 * 缺陷（R32 明令禁的假控件）。它们今天不再是「屏」，但仍然是入口，所以两种身份分开记：
 * 屏走 meta.screen，入口走 LEGACY_FEED_NAMES。
 */
export const screenRouteIds = [...routes.filter(isScreen).map(route => route.name), ...LEGACY_FEED_NAMES]

// 「喂料」这一屏的名字从这张表过一道手：App.vue 与用例都只 import src/router，不必知道
// feed-tabs.js 的存在 —— 那张表是路由表的实现细节，不是第二处入口。
export { FEED_SCREEN }

/**
 * 切走仍不卸载的屏。对话面板里有进行中的回答流、输入草稿与滚动位置，改造前靠
 * v-show 常驻；现在交给 <keep-alive :include>。值取组件自己的名字，因为 keep-alive
 * 匹配的就是组件名（Vue 对 <script setup> 用文件名推断出 __name）。
 */
export const cachedScreens = routes
  .filter(route => isScreen(route) && route.meta.keepAlive)
  .map(route => route.component.name || route.component.__name)

/**
 * 建路由实例。history 可注入是必需的而不是便利：仓库的测试跑在 node 环境
 * （vitest.config.js 的 environment=node，没有 jsdom），createWebHistory() 在没有
 * window 的地方会直接抛，所以用例传 createMemoryHistory() 进来。
 * @param {{ history?: ReturnType<typeof createWebHistory> }} [options]
 */
export function createAppRouter({ history } = {}) {
  const router = createRouter({ history: history || createWebHistory(), routes })
  return router
}
