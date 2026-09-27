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

import AdminPanel from '../components/AdminPanel.vue'
import ApprovalPanel from '../components/ApprovalPanel.vue'
import ArtifactsPanel from '../components/ArtifactsPanel.vue'
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
  // R315 判据①④ · 「交成果」是一屏，也是第六枚一级入口：员工嘴里说的是「我上次做的那份东西」，
  // 不是「数据面板的第 N 个区块」。屏名沿用 docs/frontend-plan-2026-09-14.md:132 那张工作区映射表里
  // 那一行（新增「交成果」，后端依赖 B-1 / R2 —— 两条今天都已交付），写法逐字照下面 /admin 那枚先例：
  // 字面 path + 字面 name + meta.screen / meta.title / meta.icon，不自造第三种形状。
  // 与 /admin 的差别只有一格：这一屏对所有人都派生入口，所以既不写 primary:false 也不写
  // administratorOnly —— 侧栏是 navigation 的派生视图，App.vue 一个字节都不必动（判据⑥）。
  // 壳是薄壳：GET /artifacts 那一发、分页、刷新、删除、打开、四张脸全在 ArtifactList.vue 里，本单对
  // 那枚文件零改动；「喂料 → 数据」那一屏也继续挂着它，两屏同一份账（判据②③）。
  {
    path: '/artifacts',
    name: 'artifacts',
    component: ArtifactsPanel,
    meta: { screen: true, title: '交成果', icon: 'M7 3h7l4 4v14H7zM14 3v5h5M10 17v-4M13 17v-7M18 17h3' },
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
  // R316 判据① · 「账号与角色」是一屏，但今天不派生一级入口：判据④ 要求员工侧看不见它，
  // 而侧栏是 navigation 的派生视图，壳层今天还不认识角色（见下面 navigationForRole 那段）。
  // primary:false 给的是「地址是真的、入口还没接线」这个准确状态：/admin 深链直达渲染
  // AdminPanel，staff 走进去看到的是「这一屏不向你开放」那张脸（后端 403），不是空列表。
  // administratorOnly 这一格是给入口用的声明，不是第二套权限判定：能不能读仍然只在服务端
  // 那道 ACTION_MANAGE_USERS 闸上（app/api/v1/auth.py:93 与 app/common/policy.py:44/:95）。
  {
    path: '/admin',
    name: 'admin',
    component: AdminPanel,
    meta: { screen: true, title: '账号与角色', icon: 'M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM3 20c0-3 2.2-4.8 5-4.8s5 1.8 5 4.8M15 8h6M15 12h6M15 16h4', primary: false, administratorOnly: true },
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

/** 平台唯一的「这台机器上的系统管理员」判定读的是角色名本身：app/common/policy.py:44 的
 *  _ADMINISTRATOR_ROLES 就只有这一枚，users:manage 也只登记在它名下（permissions.py:15）。 */
export const ADMINISTRATOR_ROLE = 'admin'

/**
 * 管理员独占屏的入口清单：与 navigation 同一张路由表派生，写法同一条，只是多认一格
 * meta.administratorOnly。今天它还没有消费方 —— App.vue 的侧栏仍按 navigation 渲染，
 * 把入口接上去需要改那枚刚被 R333 动过的壳层，边界由总控裁定（R316 判据④ 的回执里报的
 * 就是这一格）；判据钉在 src/router/__tests__/r316-admin-entry.test.js。
 */
export const administratorNavigation = routes
  .filter(route => isScreen(route) && route.meta.administratorOnly === true)
  .map(route => ({ id: route.name, label: route.meta.title, icon: route.meta.icon }))

/**
 * 某个角色该看见的侧栏入口：角色不对就一枚都不派生（不是「画出来再藏起来」）。
 * 这一格只管入口可见性，不管能不能读 —— 读不读得到只在服务端那道闸上说，屏上那五张脸
 * 就是它的答案；所以这里既不复用 permissions，也不在前端建第二套权限表。
 */
export function navigationForRole(role) {
  return String(role || '') === ADMINISTRATOR_ROLE ? [...navigation, ...administratorNavigation] : navigation
}

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
