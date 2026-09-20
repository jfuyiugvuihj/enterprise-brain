/**
 * R104 · 路由表就是全站唯一的「屏 ↔ URL ↔ 面板」真源
 *
 * 环境仍是 node + @vue/server-renderer（vitest.config.js 的 environment=node，仓库里没有
 * jsdom / @vue/test-utils，也不许 npm i）。所以三条腿各管各的事，不假装验过自己验不了的：
 *   ① 真路由对象：createAppRouter 注入 createMemoryHistory，深链用 router.push 走一遍完整的
 *      导航解析（重定向、命名路由、meta 合并都参与），不是拿 routes 数组 grep 字符串。
 *   ② 真渲染：把路由解析出来的组件交给 renderToString，与「直接渲染那个面板」的 HTML 比相等，
 *      这才叫「深链直达渲染的是同一屏」，而不是名字对上了。
 *   ③ 源码级：焦点与「不许留第二套真源」是 App.vue <script setup> 里的事，node 拿不到实例，
 *      于是钉住接线本身；导航与面板映射则已经是可 import 的模块，不必再退化成 grep。
 *
 * 三条反证（跑完即还原，不留在树里）：
 *   删掉 routes 里任意一枚一级路由       → 本文件「路由表 = 导航集合」与深链那两组当场红。
 *   App.vue 重新留一条 activeTab.value =  → 「App.vue 里没有第二套真源」红。
 *   图谱路由 meta.primary 翻成可派生      → 「一级导航就是这六个」红（本文件与 navigation.test.js 各一处）。
 */
import { readFileSync, readdirSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import { createMemoryHistory } from 'vue-router'
import { renderToString } from '@vue/server-renderer'
import ApprovalPanel from '../../components/ApprovalPanel.vue'
import ChatPanel from '../../components/ChatPanel.vue'
import DashboardPanel from '../../components/DashboardPanel.vue'
import DataPanel from '../../components/DataPanel.vue'
import DocPanel from '../../components/DocPanel.vue'
import GraphPanel from '../../components/GraphPanel.vue'
import InsightPanel from '../../components/InsightPanel.vue'
import { FOCUSABLE_SELECTOR } from '../../components/ui/focus-trap.js'
import {
  DEFAULT_SCREEN,
  cachedScreens,
  createAppRouter,
  navigation,
  routes,
  screenIds,
  screenRouteIds,
} from '../index.js'
import { focusScreenMain, isRoveKey, navItems, nextNavItem } from '../nav-focus.js'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const app = read('../../App.vue')
const main = read('../../main.js')

/** 一屏一条：深链地址、路由名、期望挂载的面板组件。 */
const SCREENS = [
  ['/overview', 'overview', DashboardPanel],
  ['/docs', 'docs', DocPanel],
  ['/data', 'data', DataPanel],
  ['/insights', 'insights', InsightPanel],
  ['/approval', 'approval', ApprovalPanel],
  ['/chat', 'chat', ChatPanel],
  // 图谱是屏，但不是一级入口：它只有一条非一级路由，深链进得来。
  ['/graph', 'graph', GraphPanel],
]

const screenRoutes = routes.filter(route => route.meta?.screen)

/** 面板里所有能把用户送去另一屏的字面量：goto 直写、指标卡 target、快捷入口 id。 */
function gotoTargetsOf(source) {
  return [
    ...source.matchAll(/\bemit\(\s*'goto',\s*'([^']+)'\s*\)/g),
    ...source.matchAll(/\btarget:\s*'([^']+)'/g),
    ...source.matchAll(/\bid:\s*'([^']+)'/g),
  ].map(match => match[1])
}

/** 七块面板扫出来的 goto 落点全集（DataPanel 的 ask 另算，它不是跨屏目标而是提问）。 */
function allGotoTargets() {
  const dir = new URL('../../components/', import.meta.url)
  const names = readdirSync(dir).filter(name => name.endsWith('.vue'))
  const targets = new Set()
  for (const name of names) {
    const source = readFileSync(new URL(`../../components/${name}`, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
    if (!/defineEmits\(\[[^\]]*'goto'/.test(source)) continue
    for (const target of gotoTargetsOf(source)) targets.add(target)
  }
  expect(targets.size, '一块面板的 goto 都没扫到，扫描本身失灵了').toBeGreaterThan(0)
  return [...targets].sort()
}

async function routerAt(location) {
  const router = createAppRouter({ history: createMemoryHistory() })
  await router.push(location)
  return router
}

describe('R104 判据 1 · 一级屏一屏一路由，导航是它的派生视图', () => {
  it('路由表 = 导航集合：一级屏与派生出的导航项逐条对得上', () => {
    expect(screenIds).toEqual(navigation.map(item => item.id))
    expect(screenIds).toEqual(['overview', 'docs', 'data', 'insights', 'approval', 'chat'])
    // 屏的全集只比一级多图谱一枚，且它就是那条非一级路由
    expect(screenRouteIds.filter(id => !screenIds.includes(id))).toEqual(['graph'])
    // 一屏一条路由：地址、组件、标题都不许多也不许少
    expect(screenRoutes.map(route => route.path)).toEqual(SCREENS.map(entry => entry[0]))
    expect(screenRoutes.map(route => route.name)).toEqual(SCREENS.map(entry => entry[1]))
  })

  it('每一枚一级路由都有 name、path 与图标，图谱不进导航', () => {
    for (const item of navigation) {
      expect(item.id).toBeTruthy()
      expect(item.label, `${item.id} 缺一级导航文案`).toBeTruthy()
      expect(item.icon, `${item.id} 缺侧栏图标`).toMatch(/^M/)
      expect(screenRoutes.some(route => route.name === item.id), item.id).toBe(true)
    }
    expect(navigation.map(item => item.id)).not.toContain('graph')
  })

  it('meta.title 必填：每一屏都有顶栏要的人话标题', () => {
    for (const route of screenRoutes) {
      expect(route.meta.title, `${String(route.name)} 没有 meta.title`).toBeTruthy()
      // 标题不许把码名/裸标识符塞进给人看的句子（与文案政策同一条规矩）
      expect(route.meta.title).not.toMatch(/[a-z][a-z0-9]*(_[a-z0-9]+)+/)
    }
  })

  it('默认落点有且只有一个：/ 与认错地址都回 overview', async () => {
    const roots = routes.filter(route => route.path === '/')
    expect(roots).toHaveLength(1)
    expect(roots[0].redirect).toEqual({ name: DEFAULT_SCREEN })
    expect(DEFAULT_SCREEN).toBe('overview')
    // 通配回落也只指这一枚，不存在第二个「不知道去哪就去这」的落点
    const fallbacks = routes.filter(route => String(route.name) === 'unknown-screen')
    expect(fallbacks).toHaveLength(1)
    expect(fallbacks[0].redirect).toEqual({ path: `/${DEFAULT_SCREEN}` })
    expect((await routerAt('/')).currentRoute.value.name).toBe('overview')
    expect((await routerAt('/nothing-like-this')).currentRoute.value.name).toBe('overview')
  })

  it('认错地址只回默认落点，也不在控制台刷/vue-router 的丢参数警告', async () => {
    const warnings = []
    const originalWarn = console.warn
    console.warn = (...args) => { warnings.push(args.join(' ')) }
    let landed = ''
    try {
      landed = (await routerAt('/nothing-like-this')).currentRoute.value.name
    } finally {
      console.warn = originalWarn
    }
    expect(landed).toBe(DEFAULT_SCREEN)
    // 通配记录自带 pathMatch，按名字回落实例会把它带过去再丢掉，每错一次地址就刷一条警告
    expect(warnings.filter(line => /Discarded invalid param/.test(line))).toEqual([])
  })
})

describe('R104 判据 3 · 深链直达解析并渲染同一屏', () => {
  for (const [path, name, panel] of SCREENS) {
    it(`${path} 解析到 ${name}，渲染出的 HTML 与直接渲染该面板一致`, async () => {
      const router = await routerAt(path)
      const current = router.currentRoute.value
      expect(current.name, `${path} 没落在 ${name} 上`).toBe(name)
      const resolved = router.resolve(path)
      expect(resolved.matched.length, `${path} 没有匹配到任何记录`).toBeGreaterThan(0)
      const mounted = resolved.matched[resolved.matched.length - 1].components.default
      expect(mounted, `${path} 挂的不是 ${name} 的面板`).toBe(panel)
      expect(resolved.meta.title).toBeTruthy()
      const viaRoute = await renderToString(h(mounted))
      const direct = await renderToString(h(panel))
      expect(viaRoute.length).toBeGreaterThan(50)
      expect(viaRoute).toBe(direct)
    })
  }

  it('图谱只有深链这一条路：它是一屏，但侧栏派生不出它的入口', async () => {
    const router = await routerAt('/graph')
    expect(router.currentRoute.value.name).toBe('graph')
    expect(navigation.map(item => item.id)).not.toContain('graph')
    const listed = app.match(/nav-\$\{item\.id\}/g) || []
    expect(listed.length, '侧栏还是按自己的清单渲染，没用派生出来的导航').toBe(1)
  })
})

describe('R104 判据 2 · 面板 @goto 目标可达，且 App.vue 不留第二套真源', () => {
  const targets = allGotoTargets()

  it('面板发出的每一个 goto 目标都是一条真路由，且是一级屏', async () => {
    const router = createAppRouter({ history: createMemoryHistory() })
    for (const target of targets) {
      expect(screenRouteIds, `${target} 不是路由表里的屏`).toContain(target)
      expect(screenIds, `${target} 不是一级屏，侧栏里没有它的入口`).toContain(target)
      expect(router.resolve({ name: target }).name, `${target} 解析不出地址`).toBe(target)
      await router.push({ name: target })
      expect(router.currentRoute.value.name).toBe(target)
    }
  })

  it('goto 目标里不许有图谱：D13① 撤的入口不能从面板后门绕回来', () => {
    expect(targets).not.toContain('graph')
  })

  it('App.vue 把 @goto / @ask 接到路由上，而不是接到某个 tab 状态上', () => {
    expect(app).toMatch(/@goto="openScreen"/)
    expect(app).toMatch(/@ask="handleAsk"/)
    expect(app).toMatch(/function openScreen\(screen\)/)
    expect(app).toMatch(/router\.push\(\{ name \}\)/)
    // 数据面板的「就这个问题去对话」仍然要落到对话屏，并且等面板挂上才发事件。
    // nextTick 用回调形式：后端 tests/test_data_file_catalog.py 按源码文本钉这条顺序。
    expect(app).toMatch(/await openScreen\('chat'\)\s*\n\s*nextTick\(\(\) => window\.dispatchEvent\(new CustomEvent\('chat-ask'/)
  })

  it('没有任何第二套真源：activeTab / workspaceMap / 手写导航数组都不在 App.vue 里', () => {
    expect(app).not.toMatch(/activeTab/)
    expect(app).not.toMatch(/workspaceMap/)
    // 侧栏清单与「点下去渲染谁」都来自 src/router，App.vue 自己不再抄一份
    expect(app).not.toMatch(/const navigation = \[/)
    expect(app).toMatch(/import \{[^}]*navigation[^}]*\} from '\.\/router'/)
    expect(app).toMatch(/<RouterView/)
    expect(app).toMatch(/v-slot="\{ Component \}"/)
    expect(app).toMatch(/:is="Component"/)
    // 顶栏标题取路由元信息，不再回头查导航数组
    expect(app).toMatch(/const activeMeta = computed\(\(\) => route\.meta/)
    expect(app).toMatch(/\{\{ activeMeta\.title \}\}/)
    // 面板组件的 import 只该存在于路由表里
    for (const [, , panel] of SCREENS) {
      const file = panel.__name || panel.name
      expect(app, `App.vue 还自己 import 了 ${file}`).not.toContain(`components/${file}.vue`)
    }
  })

  it('main.js 装了路由，并等首帧解析完再挂载', () => {
    expect(main).toMatch(/app\.use\(router\)/)
    expect(main).toMatch(/router\.isReady\(\)\.then\(\(\) => app\.mount\('#app'\)\)/)
  })
})

describe('R104 判据 3 · 切屏不丢会话，也不改别人家的重挂载语义', () => {
  it('只有对话屏切走不卸载，keep-alive 名单对得上组件自己的名字', () => {
    const alive = routes.filter(route => route.meta?.screen && route.meta.keepAlive)
    expect(alive.map(route => String(route.name))).toEqual(['chat'])
    expect(cachedScreens).toEqual(['ChatPanel'])
    // keep-alive 的 include 匹配的是组件名；<script setup> 的名字由文件名推断成 __name，
    // 名单必须真能从 ChatPanel 身上取到，否则 :include 静默失效、会话照丢。
    expect(ChatPanel.name || ChatPanel.__name).toBe('ChatPanel')
    expect(app).toMatch(/<KeepAlive :include="cachedScreens">/)
  })

  it('其余六屏照旧每次进来重挂载：没有被塞进 keep-alive 名单', () => {
    const names = screenRoutes.map(route => route.component.name || route.component.__name)
    expect(names).toEqual(['DashboardPanel', 'DocPanel', 'DataPanel', 'InsightPanel', 'ApprovalPanel', 'ChatPanel', 'GraphPanel'])
    expect(names.filter(name => cachedScreens.includes(name))).toEqual(['ChatPanel'])
  })
})

describe('R104 判据 3 · 焦点与键盘可达（复用 ui 那两份，不造第三套）', () => {
  const stub = label => ({ label, hits: 0, focus(options) { this.hits += 1; this.last = options } })
  const items = [stub('总览'), stub('文档'), stub('数据')]
  const container = selector => ({ seen: selector, querySelectorAll: () => items })

  it('侧栏只接管方向键与 Home/End，Tab / Enter / Space 一概放行', () => {
    expect(['ArrowUp', 'ArrowDown', 'Home', 'End'].every(isRoveKey)).toBe(true)
    for (const key of ['Tab', 'Enter', ' ', 'a', 'PageDown', '']) {
      expect(isRoveKey(key), `${key} 不该被侧栏抢走`).toBe(false)
      expect(nextNavItem(items, items[0], key), `${key} 被拦下来了`).toBeNull()
    }
  })

  it('走位下标用的是 list-nav.js 那一份算绪：首尾循环、跳过禁用项的语义与下拉一致', () => {
    expect(nextNavItem(items, items[0], 'ArrowDown')).toBe(items[1])
    expect(nextNavItem(items, items[1], 'ArrowUp')).toBe(items[0])
    expect(nextNavItem(items, items[2], 'ArrowDown')).toBe(items[0])
    expect(nextNavItem(items, items[0], 'ArrowUp')).toBe(items[2])
    expect(nextNavItem(items, null, 'Home')).toBe(items[0])
    expect(nextNavItem(items, null, 'End')).toBe(items[2])
    expect(nextNavItem(items, {}, 'ArrowDown')).not.toBeNull()
    expect(nextNavItem([], items[0], 'ArrowDown')).toBeNull()
    expect(nextNavItem(undefined, items[0], 'ArrowDown')).toBeNull()
  })

  it('取可聚焦条目走 focus-trap.js 的选择器，不另写一份 :where 清单', () => {
    const probe = container(FOCUSABLE_SELECTOR)
    expect(navItems(probe)).toHaveLength(3)
    expect(probe.seen).toBe(FOCUSABLE_SELECTOR)
    expect(FOCUSABLE_SELECTOR).toContain('button:not([disabled])')
    expect(navItems(null)).toEqual([])
    expect(navItems({})).toEqual([])
  })

  it('切屏后焦点交给新屏主区，且带着 preventScroll', () => {
    const main = stub('主区')
    expect(focusScreenMain(main)).toBe(true)
    expect(main.hits).toBe(1)
    expect(main.last).toEqual({ preventScroll: true })
    expect(focusScreenMain(null)).toBe(false)
    expect(focusScreenMain({})).toBe(false)
  })

  it('App.vue 真的把这三件事接上了：主区可聚焦、切屏有 watch、侧栏有 keydown', () => {
    expect(app).toMatch(/<main ref="workspaceEl" class="workspace" tabindex="-1"/)
    expect(app).toMatch(/watch\(\(\) => route\.name,[\s\S]*?await nextTick\(\)[\s\S]*?focusScreenMain\(workspaceEl\.value\)/)
    expect(app).toMatch(/<nav ref="navEl"[\s\S]*?@keydown="onNavKeydown"/)
    expect(app).toMatch(/nextNavItem\(navItems\(navEl\.value\), document\.activeElement, event\.key\)/)
    expect(app).toMatch(/event\.preventDefault\(\)/)
    // 登录后地址没变、触发不了上面那个 watch，所以焦点由 enterWorkspace 自己收尾
    expect(app).toMatch(/async function enterWorkspace\(\)[\s\S]*?focusScreenMain\(workspaceEl\.value\)/)
  })
})
