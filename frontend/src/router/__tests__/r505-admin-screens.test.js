/**
 * R505 · 三枚管理屏的入口形状：可深链、不占一级入口、只长进管理员那一份清单
 *
 * 手法逐字照 r494-profile-route.test.js（同一族先例：primary:false 的那一屏怎么写就怎么写），
 * 入口派生的口径照 r316-admin-entry.test.js 与 r399-trace-screen.test.js。
 *
 * 判据钉的是三件事：
 *  ① 三条路由一条一枚，字面 path、字面 name、挂的是那枚壳、meta 四格齐全、不是重定向；
 *  ② 深链直接进真能渲染：解析到的组件与直接渲染那枚壳交出逐字相同的 HTML（不是「路由表里有这一条」）；
 *  ③ 侧栏入口只有派生那一条路：壳层（App.vue）里不许出现这三枚名字的任何字面量 ——
 *    出现了就是第二套真源，而第二套真源正是 R104 要拆掉的东西。
 *    🔴 交付里同步写明：客户端角色派生入口这件事本身仍是假权限（缺口清单 §4.3 b），本件不宣称已解决。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import { createMemoryHistory } from 'vue-router'
import { renderToString } from '@vue/server-renderer'

import AuditEventsPanel from '../../components/AuditEventsPanel.vue'
import EvaluationsPanel from '../../components/EvaluationsPanel.vue'
import SloPanel from '../../components/SloPanel.vue'
import {
  ADMINISTRATOR_ROLE,
  administratorNavigation,
  createAppRouter,
  navigation,
  navigationForRole,
  routes,
  screenIds,
} from '../../router/index.js'

const SCREENS = [
  { path: '/slo', name: 'slo', title: '服务等级目标', component: SloPanel, key: 'slo-panel' },
  { path: '/evaluations', name: 'evaluations', title: '评测报告', component: EvaluationsPanel, key: 'evaluations-panel' },
  { path: '/audit/events', name: 'audit-events', title: '审计事件', component: AuditEventsPanel, key: 'audit-panel' },
]
const SCREEN_NAMES = SCREENS.map(item => item.name)
const routeByName = name => routes.filter(route => route.name === name)
const nonPrimaryIds = routes.filter(route => route.meta?.screen && route.meta.primary === false).map(route => route.name)

async function routerAt(location) {
  const router = createAppRouter({ history: createMemoryHistory() })
  await router.push(location)
  return router
}

describe('R505 · 三条路由的形状（字面量、壳、meta、非重定向）', () => {
  it.each(SCREENS)('$name：路由表里恰好一条，四格 meta 齐全', ({ path, name, title, component }) => {
    expect(routeByName(name), '路由表里应该有且只有 ' + name).toHaveLength(1)
    expect(routes.filter(route => route.path === path)).toHaveLength(1)
    const route = routeByName(name)[0]
    expect(route.path).toBe(path)
    expect(route.component, path + ' 挂的不是那枚壳').toBe(component)
    expect(route.redirect, path + ' 不该是重定向，它是一屏').toBeUndefined()
    expect(route.meta.screen, path + ' 没登记成一屏').toBe(true)
    expect(route.meta.title).toBe(title)
    expect(route.meta.icon).toMatch(/^M/)
    expect(route.meta.primary, path + ' 被写成一级入口了').toBe(false)
    expect(route.meta.administratorOnly, path + ' 没登记成管理员独占').toBe(true)
  })

  it('屏名三枚互不相同，且不与任何一枚在册屏名撞车（屏名全站唯一的口径归 R136）', () => {
    const titles = routes.filter(route => route.meta?.screen).map(route => route.meta.title)
    expect(new Set(titles).size, '有两屏共用了同一个屏名').toBe(titles.length)
    titles.forEach(title => {
      expect(title).toBeTruthy()
      expect(title).not.toMatch(/\b[a-z][a-z0-9]*_[a-z0-9]+\b/)
    })
  })

  it('写法不自造第三种形状：与 /admin、/traces 同一条书写式', () => {
    for (const name of ['admin', 'traces']) {
      const elder = routeByName(name)[0]
      expect(elder.meta.primary, name + ' 的先例被改写了').toBe(false)
      expect(elder.meta.administratorOnly, name + ' 的先例被改写了').toBe(true)
    }
    expect(administratorNavigation.map(item => item.id)).toEqual(['admin', 'traces', ...SCREEN_NAMES])
  })
})

describe('R505 · 深链直接进真能渲染（不是只「路由表里有这一条」）', () => {
  it.each(SCREENS)('$path：解析到这一屏，HTML 与直接渲染那枚壳逐字相同', async ({ path, name, title, component, key }) => {
    const router = await routerAt(path)
    expect(router.currentRoute.value.name, path + ' 没落在这一屏上（多半是掉进了通配兜底）').toBe(name)
    const resolved = router.resolve(path)
    const matched = resolved.matched[resolved.matched.length - 1]
    expect(matched.components.default, path + ' 挂的不是那枚壳').toBe(component)
    expect(resolved.meta.title).toBe(title)
    const viaRoute = await renderToString(h(matched.components.default))
    expect(viaRoute.length, path + ' 渲染出一片空白').toBeGreaterThan(50)
    expect(viaRoute).toBe(await renderToString(h(component)))
    expect(viaRoute).toContain('data-testid="' + key + '"')
  })

  it('渲染时没有一句 Failed to resolve component：三枚壳都真解析得开', async () => {
    for (const { component, key } of SCREENS) {
      const lines = []
      const warn = console.warn
      const error = console.error
      console.warn = (...args) => lines.push(args.join(' '))
      console.error = (...args) => lines.push(args.join(' '))
      let html = ''
      try {
        html = await renderToString(h(component))
      } finally {
        console.warn = warn
        console.error = error
      }
      expect(lines.filter(line => /Failed to resolve component/.test(line)), key + ' 的组件没解析就画了空标签').toEqual([])
      expect(html).toContain('data-testid="' + key + '"')
    }
  })
})

describe('R505 · 入口只由路由表派生：管理员多出三枚，其余角色一枚不多', () => {
  it('一级屏那六枚一枚未增未减：加这三屏没把任何人的入口挤掉', () => {
    expect(screenIds).toEqual(['overview', 'feed', 'insights', 'approval', 'chat', 'artifacts'])
    expect(navigation).toHaveLength(6)
    for (const name of SCREEN_NAMES) {
      expect(screenIds).not.toContain(name)
      expect(nonPrimaryIds).toContain(name)
    }
  })

  it.each(['staff', 'manager', 'auditor', 'editor', '', undefined, null])('角色 %s：入口清单里三枚管理屏一枚都没有', role => {
    const ids = navigationForRole(role).map(item => item.id)
    expect(ids).toEqual(['overview', 'feed', 'insights', 'approval', 'chat', 'artifacts'])
    for (const name of SCREEN_NAMES) {
      expect(ids, '侧栏长出了管理员屏入口：' + name).not.toContain(name)
    }
  })

  it('系统管理员那一档恰好多这三枚，顺序 = 路由表顺序', () => {
    const forAdmin = navigationForRole(ADMINISTRATOR_ROLE)
    expect(forAdmin.map(item => item.id)).toEqual([
      'overview', 'feed', 'insights', 'approval', 'chat', 'artifacts',
      'admin', 'traces', 'slo', 'evaluations', 'audit-events',
    ])
    expect(forAdmin).toHaveLength(navigation.length + 5)
    expect(forAdmin.slice(0, navigation.length)).toEqual(navigation)
    for (const { name, title } of SCREENS) {
      const entry = forAdmin.find(item => item.id === name)
      expect(entry, name + ' 的入口没有可及名称').toBeTruthy()
      expect(entry.label).toBe(title)
    }
  })
})

describe('R505 · 壳层没有第二套导航清单', () => {
  it('App.vue 里找不到这三枚名字的任何字面量：入口是派生出来的，不是补上去的', () => {
    const source = readFileSync(new URL('../../App.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
    expect(source).toMatch(/v-for="item in navigationForRole\(userRole\)"/)
    for (const needle of ["'slo'", "'evaluations'", "'audit-events'", '/audit/events', 'slo-panel', 'evaluations-panel', 'audit-panel']) {
      expect(source, 'App.vue 里出现了第二处入口清单：' + needle).not.toContain(needle)
    }
  })

  it('这三枚屏都不在派生之外另开口子：路由表里带这三枚名字的记录总数就是三', () => {
    expect(routes.filter(route => SCREEN_NAMES.includes(String(route.name)))).toHaveLength(3)
    expect(routes.filter(route => route.meta?.administratorOnly === true)).toHaveLength(5)
  })
})
