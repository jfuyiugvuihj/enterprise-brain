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
import AuditEventsPanel from '../components/AuditEventsPanel.vue'
import ChatPanel from '../components/ChatPanel.vue'
import DashboardPanel from '../components/DashboardPanel.vue'
import EvaluationsPanel from '../components/EvaluationsPanel.vue'
import FeedPanel from '../components/FeedPanel.vue'
import GraphPanel from '../components/GraphPanel.vue'
import InsightPanel from '../components/InsightPanel.vue'
import ProfilePanel from '../components/ProfilePanel.vue'
import SloPanel from '../components/SloPanel.vue'
import TracePanel from '../components/TracePanel.vue'

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
  // R494 判据② · 「我的账号」是一屏：员工嘴里那三句话（我是谁、我在哪个部门、我能读到哪几级文档）
  // 今天在界面上无处可查 —— 路由表里就没有这一格，缺口清单的 G10 因此记「半」。这一屏的四格逐格来自
  // GET /profile 的回执，取数与判脸全在 src/lib/profile.js 一处，屏壳自己不做第二本账。
  // 为什么这一条不写 meta.icon 也不挂一级入口：本单写域不含侧栏那几枚定长名单钉（一级屏从六枚变七枚要
  // 同时改口 navigation.test.js 与 r315 / r399 / r136 那四枚在册件），所以先按 /graph 那一枚先例落
  // 「真地址、可深链、不占一级」这一格准确状态：primary:false 派生不出导航项，入口要不要挂归总控裁定，
  // 挂着一枚没人接的 icon 才是这里该防的死数据。
  {
    path: '/profile',
    name: 'profile',
    component: ProfilePanel,
    meta: { screen: true, title: '我的账号', primary: false },
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
  // 而侧栏是 navigation 的派生视图 —— 壳层认得出角色这一条今天已经接上了：App.vue 侧栏那枚
  // v-for 吃的就是 navigationForRole(userRole)，判据钉在 src/router/__tests__/r316-admin-entry.test.js。
  // primary:false 给的是「它不占一级入口、只长进管理员那一份清单」这个准确状态：/admin 深链直达
  // 渲染 AdminPanel，staff 走进去看到的是「这一屏不向你开放」那张脸（后端 403），不是空列表。
  // administratorOnly 只声明入口，不是第二套权限判定：能不能读仍然只在服务端那道 ACTION_MANAGE_USERS 闸上（app/api/v1/auth.py:107 与 app/common/policy.py:44/:95）。
  {
    path: '/admin',
    name: 'admin',
    component: AdminPanel,
    meta: { screen: true, title: '账号与角色', icon: 'M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM3 20c0-3 2.2-4.8 5-4.8s5 1.8 5 4.8M15 8h6M15 12h6M15 16h4', primary: false, administratorOnly: true },
  },
  // R399 判据①（甲案）· 「运行留痕」是一屏，写法逐字照上面 /admin 那一枚先例：primary:false 派生不出
  // 一级入口，administratorOnly:true 让它只长进管理员那一份入口清单（administratorNavigation 就是
  // App.vue:472 侧栏那枚 v-for 的真源，加这一屏不改壳层一个字 —— 这一条由 R309 复核在 §G11 里翻案并留证据）。
  // 为什么不挂一级：这一屏读的三枚出口过的是审计那一项权限 —— audit:read 只登记在 admin 与 auditor
  // 名下（app/common/permissions.py:15 与 :16），staff 与 manager 那两档没有（:13 与 :14），给员工
  // 摆一枚按下去只会说「不向你开放」的按钮，
  // 就是 R32 明令禁的假控件；管理员那一档多出来的是入口，读不读得到仍然只在服务端那道闸上说。
  // 编号也从这格地址上带进来：/traces?trace=<编号> 是真落点，接的就是后端在
  // app/api/v1/observability.py:594 自己写出的那一格 replay_path 里的编号；不带 query 就是清单脸。
  {
    path: '/traces',
    name: 'traces',
    component: TracePanel,
    meta: { screen: true, title: '运行留痕', icon: 'M4 7h16M4 12h10M4 17h6M14 12l3 3 5-6', primary: false, administratorOnly: true },
  },
  // R505 判据 A · 「服务等级目标」是一屏：GET /api/v1/slo 这条读腿今天在前端零消费者，而它交的全是
  // 欠账 —— 三档的每一个数字格都写着「欠样本」或「不可测」，目标值整格待填。写法逐字照上面 /admin 与
  // /traces 那两枚先例：primary:false 派生不出一级入口，administratorOnly:true 让它只长进管理员那一份
  // 入口清单（administratorNavigation 就是 App.vue 侧栏那枚 v-for 的真源，加这三屏不改壳层一个字）。
  // 这一屏上没有任何一处能把样本闸调低：那一枚下限写在服务端，能调低的下限不是下限。
  {
    path: '/slo',
    name: 'slo',
    component: SloPanel,
    meta: { screen: true, title: '服务等级目标', icon: 'M4 18a8 8 0 1 1 16 0M12 18l4-5', primary: false, administratorOnly: true },
  },
  // R505 判据 B · 「评测报告」是一屏，但它不跑分：那条出口自己就写着 runs_on_request=false，
  // 屏上把这句原话、它给的理由与那句只在命令行上敲的命令一起端出来，零枚「立即运行」按钮。
  // 同一条先例，同一个理由：它先要系统管理员角色，再要评测读取这一项权限，员工侧摆一枚只会说
  // 「不向你开放」的按钮就是 R32 明令禁的假控件。
  {
    path: '/evaluations',
    name: 'evaluations',
    component: EvaluationsPanel,
    meta: { screen: true, title: '评测报告', icon: 'M5 6h5M5 12h5M5 18h5M13 6l2 2 3-3M13 12l2 2 3-3M13 18l2 2 3-3', primary: false, administratorOnly: true },
  },
  // R505 判据 C · 「审计事件」是一屏，而且只读：那条出口自己写着它永不写入一枚 allowed 事件。
  // 这一屏把「这一页是全部还是头一段」摆在明面上 —— 三枚计数、一枚截断旗与那格上限逐格印，
  // 排序也照服务端给的那一句说。入口形状与上面两屏同一条先例，过的仍是审计那一项权限。
  {
    path: '/audit/events',
    name: 'audit-events',
    component: AuditEventsPanel,
    meta: { screen: true, title: '审计事件', icon: 'M12 4l7 3v5c0 4-3 7-7 8-4-1-7-4-7-8V7zM9 12l2 2 4-4', primary: false, administratorOnly: true },
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
 * meta.administratorOnly。消费方是 App.vue 侧栏那枚 v-for（它吃 navigationForRole(userRole)，
 * 管理员那一档就是 navigation 之后接上这一份）—— 这一格由 R316 判据④ 接线，今天 R399 交出
 * 这一份清单里的第二枚入口；加屏不必改壳层一个字（R309 复核 §G11）。
 * 判据钉在 src/router/__tests__/r316-admin-entry.test.js。
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
