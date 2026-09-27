/**
 * R399 判据①⑤ · 「运行留痕」这一屏的形状钉（源码级，不碰网络）
 *
 * 这一枚文件只量「屏壳长什么样」五件事，每件都能被一处反向改动当场抓住：
 *  甲 入口形状：/traces 是一屏、不是一级入口、只长进管理员那一份入口清单（判据① 甲案的三枚 meta
 *     声明）；并且它不自造第三种写法 —— 逐字照 /admin 那一枚先例，先例本身也钉一次，
 *     否则下一位把 /admin 换了画法，本枚钉会红着说自己验过形状。
 *  乙 壳不取数也不判码：取数只在 lib/traces.js 一处，模板里不许出现第二处码名比较。
 *  丙 判据① 的后半：屏上没有一处「手输编号」。取号只有两条路 —— 从服务端清单里点、或从地址上带。
 *     本枚只量屏壳这一半（模板里没有输入控件）；另一半（点中会把编号写回地址、地址里有编号就直接读）
 *     在 src/__tests__/r399-trace-render.test.js 里用真渲染量。
 *  丁 判据⑤ 三条硬约束里的源码级那两条：零新色值、零枚裸 <button>（用 r288 那枚量具现数，
 *     不另写一份数法）、运行时零外部请求。
 *  戊 屏名不写第二遍：页级屏名的全站唯一画法是 header.panel-head 里那枚 <h3>（R136 判据①），
 *     这一屏靠 meta.title 说名字，屏壳里一屏名都不抄 —— 于是 r136-screen-names 那枚「四枚」的
 *     定长钉不必为本单换号；本枚把「不许偷偷加第五枚」钉在这里。
 *
 * 环境仍是 node + @vue/server-renderer（本仓没有 jsdom / @vue/test-utils，也不许 npm i）。
 *
 * 反证刀（都在影子副本里注入，跑完按字节复原；本文件一个字不改树）：
 *   刀甲 摘掉 administratorOnly → 甲组第一条红（它派生进了一级入口）。
 *   刀乙 在模板里加一枚 <input> 让管理员手输编号 → 丙组红。
 *   刀丁 给屏壳加一段 <style> 写一枚 hex → 丁组红。
 *   刀戊 在 panel-head 里加一句 <h3>运行留痕</h3> → 戊组与 r136-screen-names 同时红。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { ADMINISTRATOR_ROLE, administratorNavigation, navigationForRole, routes, screenIds } from '../../router/index.js'
import TracePanel from '../TracePanel.vue'
import { countNativeButtons } from './r288-native-button-scan.js'

const readSrc = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const shellSource = () => readSrc('../TracePanel.vue')

/** 剥掉不画上屏的注释：模板注释、块注释、行注释（口径同 r136 / r315 / r316 那三枚 helper）。 */
function withoutComments(text) {
  return text
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[\s;:{}])\/\/[^\n]*/g, '$1')
}

const shellCode = () => withoutComments(shellSource())

/** <template> 那一截，同样先剥注释：注释里提到 <input> 不算屏上有输入框。 */
function shellTemplate() {
  const block = /<template>([\s\S]*)<\/template>/.exec(shellCode())
  expect(block, '屏壳里没有 <template> 块，本枚钉就白写').toBeTruthy()
  return block[1]
}

/** <script setup> 那一截：动作原语必须在这里 import（R333 踩过「画出 <uibutton>」那一把）。 */
function setupBlock() {
  const block = /<script setup>([\s\S]*?)<\/script>/.exec(shellSource())
  expect(block, '屏壳里没有 <script setup> 块').toBeTruthy()
  return block[1]
}

const traceRoute = routes.find(route => route.name === 'traces')
const adminRoute = routes.find(route => route.name === 'admin')

/** 页级屏名的全站唯一画法（与 R136 判据①、r315 同一条口径）。 */
const PAGE_TITLE_RE = /<header\b[^>]*class="[^"]*\bpanel-head\b[^"]*"[^>]*>[\s\S]*?<h3\b[^>]*>([^<]*)<\/h3>/

describe('R399 甲 · /traces 是一屏，写法逐字照 /admin 先例', () => {
  it('路由表里恰好一条 /traces：字面 path、字面 name、挂的是这枚壳、三枚 meta 声明齐全', () => {
    expect(traceRoute, '路由表里没有「运行留痕」这一屏了').toBeTruthy()
    expect(routes.filter(route => route.name === 'traces')).toHaveLength(1)
    expect(routes.filter(route => route.path === '/traces')).toHaveLength(1)
    expect(traceRoute.path).toBe('/traces')
    expect(traceRoute.component, '/traces 挂的不是那枚壳').toBe(TracePanel)
    expect(traceRoute.meta.screen).toBe(true)
    expect(traceRoute.meta.title).toBe('运行留痕')
    expect(traceRoute.meta.icon).toMatch(/^M/)
    // 甲案的两枚声明：是一屏，但不派生一级入口，且只长进管理员那一份清单。
    expect(traceRoute.meta.primary, '这一屏被写成一级入口了').toBe(false)
    expect(traceRoute.meta.administratorOnly, '这一屏没登记成管理员独占').toBe(true)
  })

  it('不自造第三种形状：与 /admin 同一条书写式，先例本身也钉一次', () => {
    const source = readSrc('../../router/index.js')
    expect(source).toMatch(/path: '\/traces',\n\s*name: 'traces',\n\s*component: TracePanel,/)
    expect(source).toMatch(/path: '\/admin',\n\s*name: 'admin',\n\s*component: AdminPanel,/)
    expect(adminRoute.meta.primary).toBe(false)
    expect(adminRoute.meta.administratorOnly).toBe(true)
    // 不是重定向：重定向那一格是「老地址不是一屏」用的（见 routes.test.js 的 LEGACY 那一族）。
    expect(traceRoute.redirect, '「运行留痕」不该是重定向，它是一屏').toBeUndefined()
  })

  it('它进的是管理员那一份入口清单，顺序 = 路由表顺序；员工与 auditor 拿不到', () => {
    expect(administratorNavigation.map(item => item.id)).toEqual(['admin', 'traces'])
    const staffIds = navigationForRole('staff').map(item => item.id)
    const auditorIds = navigationForRole('auditor').map(item => item.id)
    expect(staffIds, '员工侧栏长出管理员屏的入口 = 一枚按下去只会说「不向你开放」的假控件').not.toContain('traces')
    expect(auditorIds, 'auditor 后端读得到、这一屏今天没给它入口：这是 R316 的既有口径，不许悄悄半开').not.toContain('traces')
    expect(navigationForRole(ADMINISTRATOR_ROLE).map(item => item.id)).toContain('traces')
  })

  it('一级屏那六枚一枚未增未减：加这一屏没有把任何人的入口挤掉', () => {
    expect(screenIds).toEqual(['overview', 'feed', 'insights', 'approval', 'chat', 'artifacts'])
  })
})

describe('R399 乙 · 壳不取数、不判码、不自造句子', () => {
  it('壳里没有任何 axios / fetch 调用，也没有第二处出口地址字面量：取数只在 lib/traces.js', () => {
    const code = shellCode()
    for (const needle of ['axios', 'fetch(', "from '../lib/http'", '/api/v1/']) {
      expect(code, '屏壳里出现了取数件：' + needle).not.toContain(needle)
    }
    expect(code).toMatch(/from '\.\.\/lib\/traces'/)
  })

  it('三格只有一处判脸：模板里不再出现码名与 face 字面量比较', () => {
    const tpl = shellTemplate()
    for (const needle of ['permission_denied', 'authentication_required', 'resource_not_found', "face === '"]) {
      expect(tpl, '模板里又判了一遍码：' + needle).not.toContain(needle)
    }
    for (const name of ['rosterKind', 'eventKind', 'ledgerKind']) {
      expect(tpl, name + ' 这一格没走那把唯一的尺').toContain(name)
    }
    const calls = setupBlock().match(/= computed\(\(\) => cellKind\(/g) || []
    expect(calls, 'cellKind 的调用点不该是三处以外的形状').toHaveLength(3)
    expect(setupBlock()).not.toMatch(/view\.face ===|\.face === '/)
  })

  it('一句人话都不写在壳里：那五句常见错误套话一枚都不许出现', () => {
    const code = shellCode()
    for (const needle of ['加载失败', '没有权限', '出错了', '请稍后重试', '暂无数据']) {
      expect(code, '屏壳自造了一句人话：' + needle).not.toContain(needle)
    }
  })
})

describe('R399 丙 · 判据① 后半：编号不许是手输框', () => {
  it('模板里没有输入控件，也没有可输文本的槽位', () => {
    const tpl = shellTemplate()
    for (const needle of ['<input', '<textarea', 'UiField', 'contenteditable', 'type="text"', 'v-model.trim']) {
      expect(tpl, '屏上多了一枚手输编号的地方：' + needle).not.toContain(needle)
    }
  })

  it('取号那格是 UiSelect：选项由服务端清单派生，屏壳不排号也不补号', () => {
    const tpl = shellTemplate()
    expect(tpl).toContain('<UiSelect')
    expect(tpl).toMatch(/:options="runOptions"/)
    // runOptions 是从 runRows 映射来的，而 runRows 只在那一格 face 为 ready 时才给行。
    expect(setupBlock()).toMatch(/const runOptions = computed\(\(\) => runRows\.value\.map/)
    // 没有 sort / reverse：一排序就成了「前端替服务端决定先看哪一枚」。
    expect(shellCode()).not.toMatch(/\.sort\(|\.reverse\(/)
  })

  it('地址是主、屏上是影：query 里那一格叫 trace；点选后把编号写回地址', () => {
    const code = shellCode()
    expect(code).toMatch(/route\?\.query\?\.trace/)
    expect(code).toMatch(/router\?\.replace\(\{ query: \{ \.\.\.route\?\.query, trace: next \} \}\)/)
    // 点选走的是那枚下拉的显式事件，不是第二条并行的 watch：一个动作只有处一个后果。
    const tpl = shellTemplate()
    expect(tpl).toMatch(/:model-value="picked"/)
    expect(tpl).toMatch(/@update:model-value="adoptRun"/)
    expect(tpl).not.toMatch(/v-model="picked"/)
  })
})

describe('R399 丁 · 判据⑤ 三条硬约束的源码级那两条', () => {
  it('零枚裸 <button>：用 r288 那枚量具现数，不另写一份数法', () => {
    expect(countNativeButtons(shellSource())).toBe(0)
  })

  it('动作与展示全走 ui 原语，且在 <script setup> 里 import（R333 踩过的那把刀）', () => {
    const block = setupBlock()
    for (const name of ['UiButton', 'UiTable', 'UiSelect', 'UiEmptyState', 'UiErrorState', 'UiLoadingState']) {
      expect(block, name + ' 没在 <script setup> 里 import').toContain(name)
    }
    expect(block).toMatch(/import \{[^}]*\bUiButton\b[^}]*\} from '\.\/ui'/)
  })

  it('一枚新色值都不加：屏壳没有 <style>，也没有 hex / rgba() / hsl()', () => {
    const text = shellSource()
    expect(text).not.toMatch(/<style/)
    expect(text).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(text).not.toMatch(/rgba?\(|hsla?\(/)
  })

  it('运行时零外部请求：屏壳里没有任何绝对 URL，也不引 CDN 字体', () => {
    const text = shellSource()
    expect(text).not.toMatch(/https?:\/\//)
    expect(text).not.toMatch(/@import|fonts\.(googleapis|gstatic)/)
  })
})

describe('R399 戊 · 屏名不写第二遍', () => {
  it('页级屏名的画法（panel-head 里的 h3）在本壳里零命中：屏名只有 meta.title 一处', () => {
    expect(PAGE_TITLE_RE.test(shellCode()), '这一屏偷偷加了第五枚页级屏名，r136 那枚定长钉要一起换号').toBe(false)
    expect(shellCode()).not.toMatch(/<h[123][\s>]/)
  })

  it('眉标说的是内容不是屏名：panel-head 里那句 eyebrow 不等于 meta.title', () => {
    const eyebrow = /<span class="eyebrow">([^<]*)<\/span>/.exec(shellCode())
    expect(eyebrow, '屏壳顶栏结构变了，本枚钉该跟着改口而不是悄悄红').toBeTruthy()
    expect(eyebrow[1]).not.toBe(traceRoute.meta.title)
  })
})
