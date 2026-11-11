/**
 * R494 判据② · 「我的账号」是一屏，而屏清单全站只有路由表这一处
 *
 * 这一枚件只管三件事，都不重复别人已经钉过的：
 *   甲 /profile 是一屏且是真落点：解析得到、挂载的就是 ProfilePanel 自己（拿同一份 HTML 比，不是拿名字比）；
 *   乙 它今天的准确状态是「真地址、可深链、不占一级入口」：primary:false，与 /graph 同一先例。
 *     入口要不要挂上侧栏（一级屏从六枚变七枚）归总控裁定，不在本单写域，这里只钉现状不许悄悄漂：
 *     谁把它翻成可派生，navigation.test.js 与 r315 / r399 / r136 那四枚在册件会一起开口。
 *   丙 屏名只写一遍：meta.title 是唯一一处，App.vue 一个字节都没为这一屏动过（侧栏是派生视图，
 *     加一屏不改壳层是 R104 立表的初衷）；屏清单也不许长出第二份（src/router 下只许 index.js 声明 meta.screen）。
 *
 * 环境仍是 node + @vue/server-renderer（本仓没有 jsdom / @vue/test-utils），手法与 r316 / r399 同一套。
 */
import { readdirSync, readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createMemoryHistory } from 'vue-router'
import ProfilePanel from '../../components/ProfilePanel.vue'
import { stripComments } from '../../components/__tests__/r288-native-button-scan.js'
import {
  administratorNavigation,
  cachedScreens,
  createAppRouter,
  navigation,
  routes,
  screenIds,
  screenRouteIds,
} from '../index.js'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const profileRoute = routes.find(route => route.name === 'profile')

describe('R494 甲 · /profile 是一屏，而且是真落点', () => {
  it('路由表里有一条 /profile 挂 ProfilePanel，屏名只写一遍（meta.title）', () => {
    expect(profileRoute, '路由表里没有 /profile 这一屏').toBeTruthy()
    expect(profileRoute.path).toBe('/profile')
    expect(profileRoute.component).toBe(ProfilePanel)
    expect(profileRoute.meta.screen).toBe(true)
    expect(profileRoute.meta.title).toBe('我的账号')
  })

  it('深链直达解析得到、渲染的就是这一屏（同一份 HTML，不是名字对上）', async () => {
    const router = createAppRouter({ history: createMemoryHistory() })
    await router.push('/profile')

    expect(router.currentRoute.value.name).toBe('profile')
    const resolved = router.resolve('/profile')
    const mounted = resolved.matched[resolved.matched.length - 1].components.default
    expect(mounted).toBe(ProfilePanel)
    expect(resolved.meta.title).toBe('我的账号')
    expect(await renderToString(h(mounted))).toBe(await renderToString(h(ProfilePanel)))
  })

  it('它是一条独立记录：/profile 这一条不多不少，也不与老屏名撞车', () => {
    expect(routes.filter(route => route.name === 'profile')).toHaveLength(1)
    expect(routes.filter(route => route.path === '/profile')).toHaveLength(1)
    // 通配那条兜底仍然在它之后：认错地址回总览，认对 /profile 就该落这一屏
    expect(routes[routes.length - 1].name).toBe('unknown-screen')
  })
})

describe('R494 乙 · 它今天的状态：可深链，不占一级入口', () => {
  it('是一屏但不是一级：screenRouteIds 有它，screenIds 与 navigation 都没有它', () => {
    expect(screenRouteIds).toContain('profile')
    expect(screenIds).not.toContain('profile')
    expect(navigation.map(item => item.id)).not.toContain('profile')
    expect(profileRoute.meta.primary).toBe(false)
  })

  // R505 换号：管理员那一截从两枚长成五枚（多出的是目标账 / 评测报告 / 审计事件三枚管理屏）。
  // 换的是名单本身，不是强度 —— 仍然定长 toEqual、仍然「多一枚少一枚都红」，
  // 而这一条要钉的事一字未动：profile 不在那一截里，它自己也不是管理员独占屏。
  it('它也不是管理员独占屏：administratorNavigation 那一截里始终没有 profile 这一枚', () => {
    expect(administratorNavigation.map(item => item.id)).toEqual(['admin', 'traces', 'slo', 'evaluations', 'audit-events'])
    expect(profileRoute.meta.administratorOnly).toBeUndefined()
  })

  it('它没有图标可画也不欠一枚：primary:false 派生不出导航项，留着 icon 就是死数据', () => {
    expect(profileRoute.meta.icon).toBeUndefined()
    expect(navigation.filter(item => item.id === 'profile')).toHaveLength(0)
  })

  it('切走就卸载：这一屏每次进来都重新读一发，不吃 keep-alive（画像不该是上一次会话的快照）', () => {
    expect(cachedScreens).toEqual(['ChatPanel'])
    expect(profileRoute.meta.keepAlive).toBeUndefined()
  })
})

describe('R494 丙 · 屏清单与屏名都只有一处', () => {
  it('屏名全站唯一：meta.title 里「我的账号」只出现一次，别处不许再抄一份', () => {
    const titled = routes.filter(route => route.meta?.title === '我的账号')
    expect(titled).toHaveLength(1)
    expect(titled[0].name).toBe('profile')
  })

  it('src/router 之下声明 meta.screen 的文件只有 index.js 一枚（不许第二处抄第二份屏清单）', () => {
    const dir = new URL('../', import.meta.url)
    const declarers = readdirSync(dir, { withFileTypes: true })
      .filter(entry => entry.isFile() && entry.name.endsWith('.js'))
      .filter(entry => /screen:\s*true/.test(read(`../${entry.name}`)))
    expect(declarers.map(entry => entry.name)).toEqual(['index.js'])
  })

  it('壳层一个字节都没为这一屏动过：App.vue 里连 profile 这个词都不该出现', () => {
    const app = read('../../App.vue')
    expect(app).not.toMatch(/profile/i)
    // 侧栏仍然是那一枚派生循环，没有为新增屏手写第二份清单
    expect(app).toContain('v-for="item in navigationForRole(userRole)"')
  })

  it('这一屏的取数与判脸只在 lib/profile.js 一处：面板壳自己不碰 axios，也不写第二张档位表', () => {
    // 剥掉注释再扫：屏壳的头注释要说清档位从哪来，那一句里出现 clearance_for 是说理不是读数
    const panel = stripComments(read('../../components/ProfilePanel.vue'))
    expect(panel).toContain("from '../lib/profile'")
    expect(panel).not.toMatch(/axios|fetch\(|authedFetch/)
    expect(panel).not.toMatch(/ROLE_CLEARANCE|clearance_for/)
    expect(panel).not.toMatch(/第 ?1?\s*[–-]\s*\d+\s*级/)
  })
})
