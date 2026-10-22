/**
 * R494 判据②③④ · 「我的账号」这一屏：四格逐格来自后端回包，三张失败脸各画各的，档位缺席就明说
 *
 * 手法沿用 r170（本仓没有 jsdom / @vue/test-utils，vitest 跑在 node 环境）：
 *   ① 真逻辑：跑 ProfilePanel 自己的 setup，网络层换成进程内假实现，走真的 loadIntoView / saveProfile；
 *   ② 真产物：把同一份绑定交给组件自己的 render 出真 HTML——「屏上画的就是这一句」只能这样证；
 *   ③ 源码级：只读那一格不许变成输入框、屏上不许多长一枚演示值、不许有外部资源与裸色值。
 * 🔴 不放宽任何一枚在册钉，也不 skip：三张失败脸的夹具形状逐枚照 app/api/v1/auth.py 真发的那枚 detail 抄。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'

// 只换网络层：errcodes 的判码与句子保持真身（同 r170 的手法）。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), put: vi.fn() } }
})

import { http } from '../../lib/http'
import ProfilePanel from '../ProfilePanel.vue'
import { countNativeButtons } from './r288-native-button-scan.js'
import { CLEARANCE_UNKNOWN_TEXT, PROFILE_SAVED_NOTE } from '../../lib/profile'
import { routes } from '../../router/index.js'

/** 屏名的唯一真源：路由表那一格。本件从它读，不把「我的账号」再抄一遍。 */
const profileRoute = routes.find(route => route.name === 'profile')

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const PANEL = '../ProfilePanel.vue'
const LIB = '../../lib/profile.js'
const ROUTER = '../../router/index.js'
const THEME = '../../assets/theme.css'
const panelSource = () => read(PANEL)

/** 后端真发的三枚写腿失败形状（403 信封 / 503 裸码 / 500 裸中文散文），各配一张自己的脸。 */
const REFUSALS = {
  department: {
    response: {
      status: 403,
      data: {
        detail: {
          code: 'department_override_denied',
          message: '画像里的 department 是只读派生值，员工自助改不了；要挪部门请用 PUT /api/v1/users/department（需要 users:manage）',
        },
      },
    },
    title: '部门那一格不归你写',
  },
  storage: { response: { status: 503, data: { detail: 'storage_unavailable' } }, title: '画像存储还没就绪' },
  saveFailed: { response: { status: 500, data: { detail: '画像保存失败' } }, title: '这一发后端没写成' },
}

const FULL_ROW = {
  username: 'lishan',
  role: 'manager',
  department: '研发部',
  position: '产品负责人',
  preferences: ['先给结论', '图表优先'],
  clearance: 2,
}

/**
 * 跑一次真 setup，按 step 驱动真的读/写，再拿组件自己的 render 出 HTML。
 * SSR 不跑 onMounted，所以「读回来之后画什么」只能这样接上真链路（r170 同一条理由）。
 */
async function renderAfter(step) {
  let bindings = null
  const Capture = defineComponent({
    __name: 'R494ProfilePanelCapture',
    setup(_props, ctx) {
      bindings = ProfilePanel.setup({}, ctx)
      return () => null
    },
  })
  await renderToString(h(Capture))
  await step(bindings)
  const Probe = defineComponent({ ...ProfilePanel, __name: 'R494ProfilePanelProbe', setup: () => bindings })
  return { html: await renderToString(h(Probe)), bindings }
}

const renderWith = row => renderAfter(async bindings => {
  http.get.mockResolvedValue({ data: { profile: row } })
  await bindings.loadIntoView()
})

/** 某一格自己那一句：只取那一枚 data-testid 所在元素里的文本，不拿整页 HTML 当量具。 */
function cellText(html, id) {
  const open = html.indexOf(`data-testid="${id}"`)
  expect(open, `屏上少了 ${id} 那一格`).toBeGreaterThan(-1)
  const match = />([^<]*)<\//.exec(html.slice(open))
  return match ? match[1] : ''
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('R494 判据② · 屏上那四格逐格真接后端', () => {
  it('四格齐：用户名 / 角色 / 部门 / 可读档位，值全部来自这一发的回包', async () => {
    const { html } = await renderWith(FULL_ROW)

    expect(cellText(html, 'cell-username-value')).toBe('lishan')
    expect(cellText(html, 'cell-role-value')).toBe('部门负责人')
    expect(html).toContain('研发部')
    expect(cellText(html, 'cell-clearance-value')).toBe('你能读到第 1–2 级')
    expect(html).not.toContain(CLEARANCE_UNKNOWN_TEXT)
    expect(html).not.toContain('undefined')
  })

  it('每一格都挂在它自己的 data-testid 上：少一格就是一格没接线，不是文案没写', async () => {
    const { html } = await renderWith(FULL_ROW)

    for (const id of ['cell-username', 'cell-role', 'cell-department', 'cell-clearance']) {
      expect(html, `屏上少了 ${id} 那一格`).toContain(`data-testid="${id}"`)
    }
  })

  it('角色词表走 lib/users.js 那一份，本屏不抄第二张角色表', async () => {
    const { html } = await renderWith({ ...FULL_ROW, role: 'auditor' })

    expect(cellText(html, 'cell-role-value')).toBe('审计人员')
    expect(panelSource()).not.toMatch(/ROLE_LABELS|USER_ROLE_LABELS/)
  })

  it('部门一格说人话：只读、找管理员、走 PUT 那一枚出口、需要 users:manage', async () => {
    const { html } = await renderWith(FULL_ROW)

    expect(html).toContain('部门（只读）')
    expect(html).toContain('PUT /api/v1/users/department')
    expect(html).toContain('users:manage')
    expect(html).toContain('找管理员')
  })

  it('🔴 部门与档位都不许变成输入框：这一屏可改的只有职位与偏好两格', async () => {
    const { html, bindings } = await renderWith(FULL_ROW)

    expect(Object.keys(bindings.form).sort()).toEqual(['position', 'preferences'])
    expect(bindings.form.department).toBeUndefined()
    const departmentCell = html.split('data-testid="cell-department"')[1].split('data-testid="cell-clearance"')[0]
    expect(departmentCell).not.toMatch(/<(input|textarea|select)\b/)
    const clearanceCell = html.split('data-testid="cell-clearance"')[1].split('data-testid="profile-edit"')[0]
    expect(clearanceCell).not.toMatch(/<(input|textarea|select)\b/)

    // 不只盯那两格自己：全屏的输入控件枚数也要钉死——职位一枚 input、偏好一枚 textarea，第三枚无论藏在哪里都红。
    const editable = html.match(/<(?:input|textarea|select)\b/g) || []
    expect(editable, '这一屏可改的只有职位与偏好两格，其余三格永远只读：' + JSON.stringify(editable)).toHaveLength(2)
  })

  it('后端没回 position / preferences 时那两格就是空的，前端不替它填一个「默认职位」', async () => {
    const { html } = await renderWith({ username: 'a', role: 'staff', department: '研发部', clearance: 1 })

    expect(cellText(html, 'cell-clearance-value')).toBe('你能读到第 1–1 级')
    expect(html).not.toContain('工程师')
    expect(html).not.toContain('图表优先')
  })
})

describe('R494 判据② · 档位拿不到就明写，不许糊一个数上去', () => {
  it('回执里没有 clearance 那一格：那一格自己说的就是那句实话', async () => {
    const row = { ...FULL_ROW }
    delete row.clearance

    const { html } = await renderWith(row)

    expect(cellText(html, 'cell-clearance-value')).toBe(CLEARANCE_UNKNOWN_TEXT)
    expect(cellText(html, 'cell-clearance-value')).not.toMatch(/\d/)
    // 「读不到」与「第 1 级」是两件事：那一格不许因为缺值就自己落回 1
    expect(html).not.toMatch(/你能读到第 \d+–\d+ 级/)
    expect(html).toContain('不是「你能读到第 1 级」')
  })

  it('后端回了 0 / 字符串 / 负数 / 空：同一句实话，一次都不许画成数字', async () => {
    for (const bad of [0, '2', -1, null, '', 1.5]) {
      const { html } = await renderWith({ ...FULL_ROW, clearance: bad })
      const text = cellText(html, 'cell-clearance-value')
      expect(text, `档位拿到 ${JSON.stringify(bad)} 却仍然画了数`).toBe(CLEARANCE_UNKNOWN_TEXT)
      expect(text).not.toMatch(/\d/)
    }
  })
})

describe('R494 判据③ · 三张失败脸在屏上分开画（判码全在 lib 一处）', () => {
  /** 三张脸都是「保存这一发」的脸：写腿才有「没写成」这一说。 */
  async function renderWriteFailure(key) {
    return renderAfter(async bindings => {
      http.get.mockResolvedValue({ data: { profile: FULL_ROW } })
      await bindings.loadIntoView()
      http.put.mockRejectedValue(REFUSALS[key].response)
      await bindings.saveProfile()
    })
  }

  it.each(Object.keys(REFUSALS))('%s 那一发画的是它自己的标题，另外两张一枚都不出现', async (key) => {
    const { html } = await renderWriteFailure(key)

    expect(html).toContain(REFUSALS[key].title)
    for (const other of Object.keys(REFUSALS)) {
      if (other !== key) expect(html, `${key} 那张脸把 ${other} 的标题也画上了屏`).not.toContain(REFUSALS[other].title)
    }
  })

  it('500 那张脸把后端那句原话说出去（R383 之后它只剩「存储自报就绪却没写成」这一种含义）', async () => {
    const { html } = await renderWriteFailure('saveFailed')

    expect(html).toContain('这一发后端没写成')
    expect(html).toContain('画像保存失败')
    expect(html).not.toMatch(/保存失败\s*$/)
  })

  it('三张标题两两不等，也没有任何一张叫「保存失败」：并句就是这一枚钉红的时候', async () => {
    const titles = Object.values(REFUSALS).map(face => face.title)
    expect(new Set(titles).size).toBe(3)

    const { html } = await renderWriteFailure('department')
    expect(html).toContain('这次没有执行')
    expect(html).not.toContain('画像保存失败')
  })

  it('读腿的 500 不冒充「没写成」：那一发没写过任何东西，它只能说「没加载出来」', async () => {
    const { html } = await renderAfter(async bindings => {
      http.get.mockRejectedValue({ response: { status: 500, data: { detail: 'Internal Server Error' } } })
      await bindings.loadIntoView()
    })

    expect(html).toContain('账号信息没加载出来')
    expect(html).not.toContain('这一发后端没写成')
  })

  it('写腿那一发被 403 拒了之后：屏上说清是部门那一格，且没有再发第二次写', async () => {
    const { html } = await renderWriteFailure('department')

    expect(html).toContain('部门那一格不归你写')
    expect(http.put).toHaveBeenCalledTimes(1)
    // 不乐观：写完无论如何都重读一次，屏上那四格只可能来自后端回包
    expect(http.get).toHaveBeenCalledTimes(2)
  })

  it('🔴 出门的那一发请求体里没有 department 这枚键（判据④的屏侧钉）', async () => {
    await renderAfter(async bindings => {
      http.get.mockResolvedValue({ data: { profile: FULL_ROW } })
      await bindings.loadIntoView()
      bindings.form.position = '改了职位'
      bindings.form.preferences = '先给结论'
      http.put.mockResolvedValue({ data: { status: 'ok' } })
      await bindings.saveProfile()
    })

    const sent = http.put.mock.calls[0][1]
    expect(Object.keys(sent).sort()).toEqual(['position', 'preferences'])
    expect('department' in sent).toBe(false)
    expect(sent.position).toBe('改了职位')
    expect(sent.preferences).toEqual(['先给结论'])
  })

  it('写成一发之后屏上那句回执只说「后端收下了」，不替后端宣布值已经是什么', async () => {
    const { html } = await renderAfter(async bindings => {
      http.get.mockResolvedValue({ data: { profile: { ...FULL_ROW, position: '' } } })
      await bindings.loadIntoView()
      bindings.form.position = '新职位'
      http.put.mockResolvedValue({ data: { status: 'ok' } })
      await bindings.saveProfile()
    })

    expect(html).toContain(PROFILE_SAVED_NOTE)
    // 第二发读回来的还是后端那一行（职位为空），屏上不许把表单里那句「新职位」当已生效的值继续画
    expect(html).not.toContain('新职位')
  })
})

describe('R494 · 这一屏不许有的东西（运行时零外部请求 / 无裸色值 / 无原生按钮）', () => {
  it('新增的三枚前端件里一个外链都没有：不连 CDN，不连 google fonts，不连任何 http(s)', () => {
    for (const file of [PANEL, LIB, ROUTER]) {
      expect(read(file), `${file} 里出现了外部请求`).not.toMatch(/https?:\/\//)
    }
  })

  it('不接 lucide-vue-next（在册判定：死依赖），也不引任何图标库', () => {
    expect(panelSource()).not.toMatch(/lucide/)
    expect(read(LIB)).not.toMatch(/lucide/)
  })

  it('原生 button 零枚：按钮一律走 components/ui 的 UiButton（复用 r288 那唯一一枚量具）', () => {
    expect(countNativeButtons(panelSource())).toBe(0)
  })

  it('样式块里零枚裸色值：新色值只准进 theme.css，这一屏只引用它已经定义好的 token', () => {
    const text = panelSource()
    const style = text.slice(text.indexOf('<style'), text.indexOf('</style>'))

    expect(style).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(style).not.toMatch(/\b(?:rgba?|hsla?)\(/)
    expect(style).not.toMatch(/:\s*[^;]*\b(?:red|blue|green|white|black|gray|grey|silver|navy|teal)\b/)
    const tokens = [...style.matchAll(/var\(--([\w-]+)\)/g)].map(match => `--${match[1]}`)
    expect(tokens.length).toBeGreaterThan(0)
    const theme = read(THEME)
    for (const token of new Set(tokens)) {
      expect(theme, `${token} 在 theme.css 里没有定义：引用一枚不存在的 token 就是画不出颜色`).toContain(`${token}:`)
    }
  })

  it('屏名只由路由表说一遍：页内那一句主标题逐字等于 meta.title，且全屏只许有一处', async () => {
    const { html } = await renderWith(FULL_ROW)

    // r412 那枚遍历钉要求每一屏「页内报一句主标题，或者由某张派生入口表替它说」。这一屏 today primary:false、
    // 也不在管理员那截导航里，所以它只能自报——而自报的唯一合法出处就是路由表那一格：字从它抄，不许再抄第二份。
    const opened = html.indexOf('<header')
    expect(opened, '这一屏的页头不在了：与 /admin、/traces 同族的 panel-head 写法散了').toBeGreaterThanOrEqual(0)
    const header = html.slice(opened, html.indexOf('</header>', opened))
    expect(header.includes('class="panel-head"'), '页头那块不再叫 panel-head').toBe(true)
    const hits = header.match(/<h[1-6]\b[^>]*>([^<]*)<\/h[1-6]>/g) || []
    expect(hits, '页头里的主标题位只许有一处：' + JSON.stringify(hits)).toHaveLength(1)
    const said = hits[0].replace(/<[^>]*>/g, '').trim()
    expect(said, '页再报的那句屏名不是从路由表抄的，是第二份真源').toBe(profileRoute.meta.title)
    expect(panelSource().match(/<h3[^>]*>[^<]*<\/h3>/g) || [], '本屏只剩一句页级屏名').toHaveLength(1)
    expect(panelSource().match(/<h4[^>]*>[^<]*<\/h4>/g) || [], '编辑区那块的层级标题也只许一处').toHaveLength(1)
    // 补一格：屏名不许在页头之外再说第二遍（F6 那把刀第一跑抓不到，旧钉只数页头）。
    const screenName = String(profileRoute.meta.title)
    expect(html.split(screenName).length - 1).toBe(1)
    const nameHeadingTags = (panelSource().match(/<h[1-6]\b[^>]*>[^<]*<\/h[1-6]>/g) || []).filter((tag) => tag.includes(screenName))
    expect(nameHeadingTags).toHaveLength(1)
  })

  it('首帧（还没读回来）画的是加载那张脸，不是一张空白工作台，也不是一句「没有画像」', async () => {
    const { html } = await renderAfter(async () => {})

    expect(html).toContain('正在读取这个账号在这台服务器上的样子')
    expect(html).not.toContain('data-testid="profile-cells"')
    expect(html).not.toContain(CLEARANCE_UNKNOWN_TEXT)
  })
})
