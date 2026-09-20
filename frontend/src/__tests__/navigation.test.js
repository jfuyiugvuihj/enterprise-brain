/**
 * R103 · D13① —— 图谱退出「一级导航」，但功能一个字都没删
 *
 * 为什么不是渲染断言：本仓库没有 jsdom / @vue/test-utils（见 vitest.config.js 的
 * environment=node），而 App.vue 的 navigation 在 <script setup> 里，SSR 只能拿到未登录
 * 的那一屏，侧栏根本不出现在 HTML 里。所以这里既不拿整份源码 grep 字符串、也不假装渲染过
 * 导航：把 navigation / workspaceMap / goto 目标解析成**数据**再断言，改坏了照样红。
 * 反证：把 { id: 'graph', label: '图谱' … } 加回 navigation，第 1 条当场红。
 */
import { existsSync, readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const app = read('../App.vue')
const dashboard = read('../components/DashboardPanel.vue')

/** 取 `const NAME = [ … ]` 或 `= { … }` 的字面量本体（到行首的 ] / } 为止）。 */
function literal(source, name, opener, closer) {
  const start = source.indexOf(`const ${name} = ${opener}`)
  expect(start, `源码里找不到 const ${name} = ${opener}`).toBeGreaterThan(-1)
  const end = source.indexOf(`\n${closer}`, start)
  expect(end, `const ${name} 的字面量没有收尾的 ${closer}`).toBeGreaterThan(-1)
  return source.slice(start, end)
}

const navigationBody = literal(app, 'navigation', '[', ']')
const navigationIds = [...navigationBody.matchAll(/id:\s*'([^']+)'/g)].map(match => match[1])
const workspaceKeys = [...literal(app, 'workspaceMap', '{', '}').matchAll(/^\s+(\w+):\s/gm)].map(match => match[1])

/** 所有能把 activeTab 设成某个值的地方：导航项、App.vue 自己的赋值、面板 emit 的 goto。 */
const gotoTargets = [
  ...dashboard.matchAll(/\bemit\(\s*'goto',\s*'([^']+)'\s*\)/g),
  ...dashboard.matchAll(/\btarget:\s*'([^']+)'/g),
  ...literal(dashboard, 'quickActions', '[', ']').matchAll(/id:\s*'([^']+)'/g),
].map(match => match[1])
const directTabAssignments = [...app.matchAll(/activeTab\.value\s*=\s*'([^']+)'/g)].map(match => match[1])

describe('R103 · 图谱的一级入口已撤下', () => {
  it('一级导航就是这六个，图谱不在其中（一条不许多、一条不许少）', () => {
    expect(navigationIds).toEqual(['overview', 'docs', 'data', 'insights', 'approval', 'chat'])
    expect(navigationIds).not.toContain('graph')
  })

  it('撤入口不等于删功能：面板组件与 workspaceMap 的 graph 映射都还在', () => {
    expect(workspaceKeys).toContain('graph')
    expect(app).toContain("import GraphPanel from './components/GraphPanel.vue'")
    expect(existsSync(new URL('../components/GraphPanel.vue', import.meta.url))).toBe(true)
    expect(existsSync(new URL('../components/__tests__/panel-states.test.js', import.meta.url))).toBe(true)
  })

  it('今天没有任何路径能进图谱屏：导航之外的每个落点都不指向它', () => {
    expect(gotoTargets.length).toBeGreaterThan(0)
    expect(new Set(gotoTargets)).not.toContain('graph')
    expect(new Set(directTabAssignments)).not.toContain('graph')
    // 导航项与 goto/赋值都必须落在真实存在的屏上，否则「无入口」这条结论本身就不可信。
    for (const target of [...gotoTargets, ...directTabAssignments]) {
      expect(navigationIds, `${target} 不是一条一级导航`).toContain(target)
    }
  })
})
