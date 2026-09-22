/**
 * R136 · 「喂料」屏的标签表：一屏两标签，标签就是合屏之前的那两块面板。
 *
 * 为什么这张表单独成枚文件、而且同时管着「标签」与「老地址」两件事：
 * 计划书 §四 把 文档 + 数据 合成一屏「喂料 /feed」，但 /docs 与 /data 是已经在树里的地址
 * （总览的卡片与列表还在往 @goto 发这两个名字）。标签清单与老地址清单一旦分开写，就会出
 * 「加了第三个标签、忘给老地址」「改了标签名、老链接指向别处」这类漂移 —— 同一条记录的两张
 * 脸必须来自同一次声明，所以这里只写一遍：id 既是标签，也是老地址的尾段。
 *
 * 单独成枚（而不是塞进 index.js）是为了让 FeedPanel 能 import 它而不绕成循环引用：
 * index.js → FeedPanel.vue → 这一枚，方向只有一条。
 */
import DataPanel from '../components/DataPanel.vue'
import DocPanel from '../components/DocPanel.vue'

/** 「喂料」这一屏的路由名（App.vue 与用例都取这一枚，不许再抄字面量）。 */
export const FEED_SCREEN = 'feed'

/** 当前标签写在地址里的哪一格：标签态住 URL，刷新与转发都留得住。 */
export const FEED_TAB_PARAM = 'tab'

/**
 * 两枚标签。needsUserRole 挂在标签上而不是挂在面板名字上：整个前端只有 DocPanel 的
 * 管理员开关要这项入参（App.vue:48 改造前就是按「只有文档面板」这句写的），
 * 把它写成表里的一列，面板换需求时改这张表就够，不用去组件里加 if。
 */
export const FEED_TABS = [
  { id: 'docs', label: '文档', component: DocPanel, needsUserRole: true },
  { id: 'data', label: '数据', component: DataPanel },
]

/** 没有 tab 参数时进哪一枚标签：取表的顺序，不另写一个「默认值」常数。 */
export const FEED_DEFAULT_TAB = FEED_TABS[0].id

/** 老屏地址：/docs、/data —— 由这张表派生，与标签同名同序。 */
export const LEGACY_FEED_PATHS = FEED_TABS.map(tab => `/${tab.id}`)

/** 老屏地址对应的路由名（= 合屏之前的屏 id，@goto 的老落点仍然认得）。 */
export const LEGACY_FEED_NAMES = FEED_TABS.map(tab => tab.id)

/**
 * 老地址落到这一屏时怎么写地址：
 *   query 原样带走（面板靠它过滤/选中的那几格不能丢），tab 这一格由【地址本身】说了算，
 *   hash 带走（锚点指向的是渲染出来的位置，重定向不该把它抹平）。
 * 带不上的只有 query 里原本就写着 tab 的那一格：/docs?tab=data 自相矛盾，地址尾段赢 ——
 * 老链接的语义在路径上，不在参数上。这条写在返回之前，别只写在注释里。
 */
export function legacyFeedRedirect(tabId) {
  return to => ({
    path: `/${FEED_SCREEN}`,
    query: { ...to.query, [FEED_TAB_PARAM]: tabId },
    hash: to.hash || '',
  })
}

/**
 * 读地址里的标签态。认不出的一律回默认那一枚，而不是 undefined：
 * 一屏的标签写错了字，代价应该是「回到第一枚标签」，不是「画一片空白的工作台」。
 */
export function resolveFeedTab(value, tabs = FEED_TABS) {
  const wanted = typeof value === 'string' ? value : ''
  return tabs.find(tab => tab.id === wanted) || tabs.find(tab => tab.id === FEED_DEFAULT_TAB) || tabs[0]
}
