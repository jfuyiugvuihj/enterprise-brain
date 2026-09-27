/**
 * R316 判据④ · 「账号与角色」的入口可达性
 *
 * 这一屏今天的状态必须说准：地址是真的，入口还没接线。
 *   · /admin 是一屏（meta.screen），深链直达渲染的就是 AdminPanel —— 与图谱同一类落点；
 *   · 它不在 screenIds 里，侧栏（navigation 的派生视图）今天对任何角色都画不出这一枚入口，
 *     所以「员工侧看不见」这一半天然成立，而「管理员侧 Tab 可达」那一半还欠 App.vue 一行接线
 *     （那枚文件刚被 R333 改过，本单按派工不动它，改口由总控裁定）；
 *   · 派生入口的那张嘴已经在这儿了：navigationForRole(role) 与 administratorNavigation，
 *     接线只改一处，不在壳层里再抄一份「谁能看见什么」。
 *
 * 为什么入口规则只认角色名一枚，而不在前端建第二套权限表：能不能读只在服务端那道
 * ACTION_MANAGE_USERS 闸上说（app/api/v1/auth.py:93、app/common/policy.py:44/:95、
 * app/common/permissions.py:15 只有 admin 名下有这一项），前端把它抄一份就是两份真源。
 * 最后那枚钉子钉的是「接线之后仍然不许在壳层里长出一张权限表」。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createMemoryHistory } from 'vue-router'
import AdminPanel from '../../components/AdminPanel.vue'
import {
  ADMINISTRATOR_ROLE,
  administratorNavigation,
  createAppRouter,
  navigation,
  navigationForRole,
  routes,
  screenIds,
  screenRouteIds,
} from '../index.js'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const app = read('../../App.vue')
const adminRoute = routes.find(route => route.name === 'admin')

describe('R316④ · /admin 是一屏，而且是真落点', () => {
  it('路由表里有一条 /admin 挂 AdminPanel，屏名只写一遍（meta.title）', () => {
    expect(adminRoute, '路由表里没有 /admin 这一屏').toBeTruthy()
    expect(adminRoute.path).toBe('/admin')
    expect(adminRoute.component).toBe(AdminPanel)
    expect(adminRoute.meta.screen).toBe(true)
    expect(adminRoute.meta.title).toBe('账号与角色')
    expect(adminRoute.meta.administratorOnly).toBe(true)
    expect(adminRoute.meta.icon).toMatch(/^M/)
  })

  it('深链直达解析得到、渲染的就是这一屏（不是「名字对上了」而是同一份 HTML）', async () => {
    const router = createAppRouter({ history: createMemoryHistory() })
    await router.push('/admin')
    expect(router.currentRoute.value.name).toBe('admin')
    const resolved = router.resolve('/admin')
    const mounted = resolved.matched[resolved.matched.length - 1].components.default
    expect(mounted).toBe(AdminPanel)
    expect(resolved.meta.title).toBe('账号与角色')
    expect(await renderToString(h(mounted))).toBe(await renderToString(h(AdminPanel)))
  })

  it('它是一屏但不是「一级」：screenIds 与 navigation 都没有它，谁都不许多出一枚入口', () => {
    expect(screenRouteIds).toContain('admin')
    expect(screenIds).not.toContain('admin')
    expect(navigation.map(item => item.id)).not.toContain('admin')
    expect(adminRoute.meta.primary).toBe(false)
    // 非一级的写法与图谱同一条（primary:false 派生不出导航项），这一格不许被改成默认一级
    expect(navigation.every(item => item.id !== 'admin')).toBe(true)
  })
})

describe('R316④ · 入口该由谁派生', () => {
  // R316 定下这一格时清单里就一枚；R399 判据①（甲案）交出第二枚「运行留痕」，走的是同一枚
  // administratorOnly 声明。断言强度未降：名单仍是定长 toEqual（顺序 = 路由表顺序），
  // 多一枚、少一枚、把别人的入口混进来都当场红，没换成包含式。
  it('管理员独占屏的入口清单就这两枚，字段齐，可及名称取的是同一格 meta.title', () => {
    expect(administratorNavigation).toHaveLength(2)
    expect(administratorNavigation.map(item => item.id)).toEqual(['admin', 'traces'])
    const item = administratorNavigation[0]
    expect(item).toEqual({ id: 'admin', label: '账号与角色', icon: adminRoute.meta.icon })
    expect(item.label, '入口没有可及名称').toBeTruthy()
    expect(item.icon).toMatch(/^M/)
    const traceRoute = routes.find(route => route.name === 'traces')
    expect(administratorNavigation[1]).toEqual({ id: 'traces', label: '运行留痕', icon: traceRoute.meta.icon })
  })

  it('角色不对就一枚都不派生：staff / manager / auditor / 没有角色，四档拿到的都是同一份 navigation', () => {
    for (const role of ['staff', 'manager', 'auditor', '', undefined, null, 'Admin', 'ADMIN']) {
      expect(navigationForRole(role), `角色 ${String(role)} 拿到了不该看见的入口`).toEqual(navigation)
      const ids = navigationForRole(role).map(item => item.id)
      expect(ids).not.toContain('admin')
      // R399：第二枚管理员屏走的是同一张嘴，员工侧同样派生不出来（不是「画出来再藏起来」）。
      expect(ids).not.toContain('traces')
    }
  })

  it('系统管理员那一档只多这两枚：加入口，一级屏那六枚一枚未减', () => {
    // R399 往同一份清单里加第二枚入口：写法不变，仍是定长 toEqual 与「navigation 那一截原样在前」。
    const forAdmin = navigationForRole(ADMINISTRATOR_ROLE)
    expect(forAdmin.map(item => item.id)).toEqual([...screenIds, 'admin', 'traces'])
    expect(forAdmin.slice(0, navigation.length)).toEqual(navigation)
    expect(forAdmin).toHaveLength(navigation.length + 2)
  })

  it('ADMINISTRATOR_ROLE 就是后端那枚角色名，不是前端新造的词', () => {
    expect(ADMINISTRATOR_ROLE).toBe('admin')
  })

  it('入口规则不许长成第二套权限表：这一格只认角色名，不复述 ACTION_ 与权限集', () => {
    const source = read('../index.js')
    const block = /export function navigationForRole[\s\S]*?\n\}/.exec(source)
    if (!block) throw new Error('router/index.js 里解析不到 navigationForRole：入口派生这一格换了形状，改的必须是这里。')
    expect(block[0]).not.toMatch(/ACTION_|permission|ROLE_PERMISSIONS|users:manage/)
  })
})

describe('R316④ · 接线缺口与后门', () => {
  it('壳层真的按角色派生入口：import 认得到，v-for 吃的就是 navigationForRole(userRole)', () => {
    // R316 判据④ 接线的账（总控 2026-09-27 批准动 App.vue:4 与 :448 这两行，本单内补完）。
    // 这枚钉原来钉的是「还没接」，接线之后按同一强度改口成「真的接了，而且仍只从一处派生」，
    // 三种倒退各自撞哪一种：
    //   · v-for 改回 navigation（不分角色，员工侧也长出这一枚入口）→ 本条第二行红；
    //   · navigationForRole 的 admin 分支被摘（不分角色 / 管理员那档不再多一枚）→ 本文件
    //     「角色不对就一枚都不派生」与「系统管理员那一档只多这一枚」两条红；
    //   · 在 App.vue 里再抄一份侧栏清单（第二套真源）→ 下面「v-for 一处都不许多」红。
    expect(app).toMatch(/import \{[^}]*\bnavigationForRole\b[^}]*\} from '\.\/router'/)
    expect(app).toMatch(/v-for="item in navigationForRole\(userRole\)"/)
    const loops = app.match(/v-for="item in [^"]*"/g) || []
    expect(loops, '侧栏清单换了画法，量具得先跟着改，不许放过第二处入口清单').toHaveLength(1)
    expect(loops[0]).toBe('v-for="item in navigationForRole(userRole)"')
    // 派生吃的是登录回包里那枚角色态（App.vue:27 的 userRole，lib/http 存的 eb_role），不是写死的名单
    expect(app).toMatch(/const userRole = shallowRef\('staff'\)/)
    expect(app).not.toContain('nav-admin')
  })

  it('没有任何面板往 admin 发 goto：员工不会被一块卡片送进这一屏（与图谱同一条规矩）', () => {
    const panelSources = ['DashboardPanel.vue', 'FeedPanel.vue', 'InsightPanel.vue', 'ApprovalPanel.vue', 'ChatPanel.vue', 'GraphPanel.vue', 'AdminPanel.vue']
    for (const name of panelSources) {
      const text = read(`../../components/${name}`)
      expect(text, `${name} 里藏了一枚指向 admin 的入口`).not.toMatch(/emit\(\s*'goto',\s*'admin'/)
      expect(text).not.toMatch(/target:\s*'admin'/)
      expect(text).not.toMatch(/id:\s*'admin'/)
    }
  })

  it('本屏不写不删：路由表这一格只挂一屏一路由，没有第二个 admin', () => {
    expect(routes.filter(route => route.name === 'admin')).toHaveLength(1)
    expect(routes.filter(route => route.path === '/admin')).toHaveLength(1)
  })
})