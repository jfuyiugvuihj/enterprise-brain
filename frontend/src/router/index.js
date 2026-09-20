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
 */
import { createRouter, createWebHistory } from 'vue-router'

import ApprovalPanel from '../components/ApprovalPanel.vue'
import ChatPanel from '../components/ChatPanel.vue'
import DashboardPanel from '../components/DashboardPanel.vue'
import DataPanel from '../components/DataPanel.vue'
import DocPanel from '../components/DocPanel.vue'
import GraphPanel from '../components/GraphPanel.vue'
import InsightPanel from '../components/InsightPanel.vue'

/** 登录后与未认识地址的落点，也是 '/' 唯一指向的那一屏。 */
export const DEFAULT_SCREEN = 'overview'

/**
 * meta 约定（判据 1：一屏一路由，name 即屏 id，title 必填）：
 *   screen    这一条是一「屏」，会被 <router-view> 渲染
 *   title     顶栏标题与浏览器标签标题
 *   icon      侧栏图标的 SVG path，原来手写在 navigation 数组里，现在跟着屏走
 *   primary   false = 不进一级导航。只有图谱这一条，理由写在它下面
 *   keepAlive 切走不卸载。只有对话这一条，理由见 cachedScreens
 */
export const routes = [
  { path: '/', redirect: { name: DEFAULT_SCREEN } },
  {
    path: '/overview',
    name: 'overview',
    component: DashboardPanel,
    meta: { screen: true, title: '总览', icon: 'M4 11.5 12 4l8 7.5v8.5a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z' },
  },
  {
    path: '/docs',
    name: 'docs',
    component: DocPanel,
    meta: { screen: true, title: '文档', icon: 'M6 3h8l4 4v14H6zM14 3v5h5M9 13h6M9 17h6' },
  },
  {
    path: '/data',
    name: 'data',
    component: DataPanel,
    meta: { screen: true, title: '数据', icon: 'M5 5h14v14H5zM8 16V9M12 16V7M16 16v-4' },
  },
  {
    path: '/insights',
    name: 'insights',
    component: InsightPanel,
    meta: { screen: true, title: '洞察', icon: 'M4 17l5-5 4 3 7-8M17 7h3v3' },
  },
  {
    path: '/approval',
    name: 'approval',
    component: ApprovalPanel,
    meta: { screen: true, title: '审批', icon: 'M6 4h12v16H6zM9 9h6M9 13h6M9 17h3M5 12l3 3 6-7' },
  },
  {
    path: '/chat',
    name: 'chat',
    component: ChatPanel,
    meta: { screen: true, title: '对话', icon: 'M5 6h14v10H9l-4 4zM8 10h8M8 13h5', keepAlive: true },
  },
  // D13①（计划书 §6.1）撤的是图谱的一级入口，不是功能：它的定位早已裁定为「候选断言采集表」
  // 而非推理引擎（docs/design/knowledge-graph-positioning.md），摆在侧栏一级就是误导使用者。
  // primary:false 让它派生不出导航项，但 /graph 是真地址：这一条就是 §44.1 留给 R104 的
  // 「非一级落点」，图谱屏从此既能被深链转发，也不会再出现在侧栏里。
  {
    path: '/graph',
    name: 'graph',
    component: GraphPanel,
    meta: { screen: true, title: '图谱', primary: false },
  },
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

/** 全部屏 id，含非一级的图谱：用来判断一个 goto 目标是不是真实存在的屏。 */
export const screenRouteIds = routes.filter(isScreen).map(route => route.name)

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
