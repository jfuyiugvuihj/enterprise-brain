/**
 * R103 · 图谱退出「一级导航」，但功能一个字都没删 —— R104 之后这笔账搬到了路由表上
 *
 * 为什么不是渲染断言：本仓库没有 jsdom / @vue/test-utils（见 vitest.config.js 的
 * environment=node），而 App.vue 的登录门在 <script setup> 里，SSR 只能拿到未登录那一屏，
 * 侧栏根本不出现在 HTML 里。所以这里既不拿整份源码 grep 字符串、也不假装渲染过导航。
 *
 * 为什么 R104 改了数据源（三条用例一条没删，只换断言对象）：
 * R103 写下这三条时，「哪几个入口是一级」与「点下去渲染谁」是 App.vue 里手写的 navigation
 * 数组和 workspaceMap 两张表，node 里 import 不到 <script setup> 内部的常量，只能把源码
 * 解析成数据再断言。R104 判据 2 要求 workspaceMap 退役、导航与屏统一由 src/router 那张表
 * 给出 —— 那张表是普通模块，可以直接 import，于是断言跑的是真值而不是长得像真值的字符串。
 * 原来钉的「App.vue 里 activeTab 的直赋」这一路今天已经不存在（改成路由了），由
 * src/router/__tests__/routes.test.js 的「App.vue 不许留第二套真源」一条接管，更硬。
 *
 * 反证：给图谱那条路由补上 meta.icon（等价于把它挂回一级导航），第 1 条当场红。
 */
import { existsSync, readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { navigation, routes, screenRouteIds } from '../router'
import GraphPanel from '../components/GraphPanel.vue'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const dashboard = read('../components/DashboardPanel.vue')

/** 取 `const NAME = [ … ]` 或 `= { … }` 的字面量本体（到行首的 ] / } 为止）。 */
function literal(source, name, opener, closer) {
  const start = source.indexOf(`const ${name} = ${opener}`)
  expect(start, `源码里找不到 const ${name} = ${opener}`).toBeGreaterThan(-1)
  const end = source.indexOf(`\n${closer}`, start)
  expect(end, `const ${name} 的字面量没有收尾的 ${closer}`).toBeGreaterThan(-1)
  return source.slice(start, end)
}

/** 路由表里真正的一「屏」；一级的那些才派生得出侧栏入口。 */
const screenRoutes = routes.filter(route => route.meta?.screen)
const navigationIds = navigation.map(item => item.id)

/** 面板里所有能把用户送去另一屏的地方：字面 goto、指标卡落点、快捷入口 id。 */
const gotoTargets = [
  ...dashboard.matchAll(/\bemit\(\s*'goto',\s*'([^']+)'\s*\)/g),
  ...dashboard.matchAll(/\btarget:\s*'([^']+)'/g),
  ...literal(dashboard, 'quickActions', '[', ']').matchAll(/id:\s*'([^']+)'/g),
].map(match => match[1])

describe('R103 · 图谱的一级入口已撤下', () => {
  it('一级导航就是这五枚，图谱不在其中（一条不许多、一条不许少）', () => {
    // R136 合屏：docs + data 两枚一级入口并成一枚 feed（老地址改重定向，不再派生入口）。
    // 断言强度未降——名单仍然逐字相等、仍然多一条少一条都红，只是名单本身换了。
    expect(navigationIds).toEqual(['overview', 'feed', 'insights', 'approval', 'chat'])
    expect(navigationIds).not.toContain('graph')
  })

  it('撤入口不等于删功能：面板组件还在，路由表也还给图谱留着落点', () => {
    const graph = screenRoutes.find(route => route.name === 'graph')
    expect(graph, '路由表里没有图谱这一屏了').toBeTruthy()
    expect(graph.path).toBe('/graph')
    expect(graph.component, '图谱路由挂的不是 GraphPanel').toBe(GraphPanel)
    expect(existsSync(new URL('../components/GraphPanel.vue', import.meta.url))).toBe(true)
    expect(existsSync(new URL('../components/__tests__/panel-states.test.js', import.meta.url))).toBe(true)
  })

  it('除深链之外没有任何路径能进图谱屏：导航与每个 goto 落点都不指向它', () => {
    expect(gotoTargets.length).toBeGreaterThan(0)
    expect(new Set(gotoTargets)).not.toContain('graph')
    expect(new Set(navigationIds)).not.toContain('graph')
    // 落点必须落在真实存在的屏上，否则「无入口」这条结论本身就不可信。
    for (const target of gotoTargets) {
      expect(screenRouteIds, `${target} 不是一屏路由`).toContain(target)
    }
  })
})
