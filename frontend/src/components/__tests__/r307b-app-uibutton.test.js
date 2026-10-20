/**
 * R307 第二棒 · App.vue 那 8 枚裸按钮接进 UiButton，并把 r197 夹具的桩件假绿一并收掉
 *
 * 派工判据（工单 R307 第二棒）：
 *   ① 八枚全接 ./components/ui 的 UiButton，档位照表；:disabled / @click / aria-* / type /
 *      v-for 的 :key 一枚不许掉；屏上仍必须是真的 <button>，testid / 类名 / 点击语义逐枚不变；
 *   ③ 棘轮只准改小（App.vue 8 → 0、合计 17 → 9），且盯着数字本身的刀要留着；
 *   ④ r197 那枚夹具补注册之后，必须证明它盯的仍然是真组件而不是解析不到的桩。
 *
 * 三条腿（沿用本仓口径：node 环境，无 jsdom / @vue/test-utils，也不 npm i）：
 *   ① 形状腿（甲组）= 逐枚扫 App.vue 里的 `<UiButton` 开标签。这一条只当「逐枚对照表」用：
 *      它回答「八枚各接了什么档位、掉了没掉属性」，它不当「屏上是什么」的验收 ——
 *      后者正是上一棒砍到 r278 的那把刀的形状，本件不再犯一次。
 *   ② 真产物腿（乙组）= 跑真 App.vue 的 setup() 并以它自己的 ssrRender 出真 HTML，
 *      在 HTML 上数真的 <button>、按类名与 data-testid 找每一枚、验 ⌄ 与 × 真在屏上、
 *      真调 openForgotPassword / closeForgotPassword / showToast 验开合。
 *   ③ 地基腿（丁组）= 现场对照「注册原语」与「不注册原语」两种跑法各自叫成什么样：
 *      不注册时 SSR 与客户端挂载都会退化成解析不到的桩（stderr 里就是那句
 *      Failed to resolve component: UiButton），注册之后归零。r197 那 30 条读数就是这么来的。
 *
 * 本件不做的两件事（写在这里，别当成验过了）：
 *   · App.vue 那 8 枚今天一枚都不绑 :disabled（现取：八枚的绑定名单里没有 disabled），
 *     所以「掉 :disabled」那一把反证不在本件，它由 r307-sourcecard-uibutton.test.js 的甲4 带着；
 *   · 像素、hover 底色、焦点环宽度这三格不起浏览器验不了 —— 丙组只钉「复位规则在不在、
 *     有没有偷添裸色值」，具体画相对不对齐见回执的诚实账。
 *
 * 反证（本单实跑，跑完按字节还原并复验 sha256）：
 *   · 把 :436 那枚退回裸 `<button` ⇒ 甲1/甲5 红、r288 乙组与丙组「合计=9」那条一起红；
 *   · 把 DEBT_RATCHET 的 App.vue 抬回 8 或把合计抬回 17 ⇒ r288 新加的「棘轮自己不许变大」红；
 *   · 摘掉侧栏某一枚的 @click ⇒ r278 甲2（逐枚对照渲染节点）红；
 *   · 把 r197 夹具的 components 去掉 ⇒ 本件丁1 红（它就是钉这一格的）；
 *   · 给 UiButton 加一枚 link 档 ⇒ 甲6 红（本单不许动原语）。
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it, vi } from 'vitest'
import { compile, createSSRApp, defineComponent, h, reactive } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { routeLocationKey, routerKey } from 'vue-router'

// 整件用例一发网络请求都不许真起（登录与 toast 那两腿走的是界面态，不是请求）。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { ...actual.http, get: vi.fn(), post: vi.fn(), delete: vi.fn() } }
})

import App from '../../App.vue'
import SourceCard from '../../components/SourceCard.vue'
import { navigation } from '../../router'
import { UiButton } from '../../components/ui'
import { sourcesFace } from '../../lib/provenance'
import { countNativeButtons, stripComments } from './r288-native-button-scan.js'

const TESTS_DIR = dirname(fileURLToPath(import.meta.url))
const SRC_ROOT = join(TESTS_DIR, '..', '..')
const readSrc = rel => readFileSync(join(SRC_ROOT, rel), 'utf8').replace(/\r\n/g, '\n')
const appSource = readSrc('App.vue')
const appCode = stripComments(appSource)
const primitiveSource = readSrc(join('components', 'ui', 'UiButton.vue'))
const r197Source = readSrc(join('components', '__tests__', 'r197-turn-key-inheritance.test.js'))
const TOKEN_KEY = 'eb_token'
const USER_KEY = 'eb_user'
const ROLE_KEY = 'eb_role'

/** 派工那张档位表，一行一枚：类名 → 该接的 variant / size / 活着的画法 / 显式 testid。 */
const WIRING = [
  { cls: 'login-control__ghost', variant: 'ghost', size: 'sm', type: 'button', live: 'click', testid: '' },
  { cls: 'login-link', variant: 'ghost', size: 'sm', type: 'button', live: 'click', testid: 'login-forgot' },
  { cls: 'login-submit', variant: 'primary', size: '', type: 'submit', live: 'submit', testid: 'login-submit' },
  { cls: 'login-dialog__close', variant: 'ghost', size: 'sm', type: 'button', live: 'click', testid: 'login-forgot-close' },
  { cls: 'login-dialog__action', variant: 'primary', size: '', type: 'button', live: 'click', testid: '' },
  { cls: 'nav-item', variant: 'ghost', size: '', type: 'button', live: 'click', testid: 'nav-' },
  { cls: 'logout-link', variant: 'ghost', size: 'sm', type: 'button', live: 'click', testid: '' },
  { cls: 'auth-toast-close', variant: 'ghost', size: 'sm', type: 'button', live: 'click', testid: '' },
]

// ==================== 量具一：逐枚扫 <UiButton 开标签（形状腿专用） ====================

const grab = (attrs, re) => { const hit = re.exec(attrs); return hit ? hit[1] : '' }

/** 取每一枚 <UiButton 的开标签属性串（引号里的 > 不算收尾，手法与 r307 同一套）。 */
function primitiveTags(text) {
  const items = []
  const re = /<UiButton\b/g
  let match = null
  while ((match = re.exec(text))) {
    const open = match.index
    let i = open + '<UiButton'.length
    let quote = null
    while (i < text.length) {
      const ch = text[i]
      if (quote) { if (ch === quote) quote = null } else if (ch === '"' || ch === "'") quote = ch
      else if (ch === '>') break
      i += 1
    }
    const attrs = text.slice(open + '<UiButton'.length, i).replace(/\s+/g, ' ').trim()
    items.push({
      line: text.slice(0, open).split('\n').length,
      attrs,
      classes: grab(attrs, /(?:^|\s):?class="([^"]*)"/).replace(/[^0-9A-Za-z_-]+/g, ' ').trim().split(' ').filter(Boolean),
      variant: grab(attrs, /(?:^|\s)variant="([^"]*)"/),
      size: grab(attrs, /(?:^|\s)size="([^"]*)"/),
      type: grab(attrs, /(?:^|\s)type="([^"]*)"/),
      testid: grab(attrs, /(?:^|\s)data-testid="([^"]*)"/),
      click: /(?:^|\s)@click=|(?:^|\s)v-on:click=/.test(attrs),
      boundClick: /(?:^|\s):click=/.test(attrs),
      disabled: /(?:^|\s):?disabled=/.test(attrs),
      vfor: /(?:^|\s)v-for=/.test(attrs),
      key: /(?:^|\s):key=/.test(attrs),
      aria: /(?:^|\s):?aria-label=/.test(attrs),
      title: /(?:^|\s):?title=/.test(attrs),
    })
  }
  return items
}

const tags = primitiveTags(appCode)
const tagOf = cls => {
  const hits = tags.filter(item => item.classes.includes(cls))
  expect(hits, 'App.vue 里按类名找不到那一枚 <UiButton：' + cls).toHaveLength(1)
  return hits[0]
}

// ==================== 量具二：真产物（SSR 出真 HTML） ====================

/** 内存替身：node 环境没有 window / localStorage（手法同 r169 / r171 / r278）。 */
function installDomStubs(seed = {}) {
  const store = new Map(Object.entries(seed))
  globalThis.window = globalThis.window || { addEventListener() {}, removeEventListener() {} }
  globalThis.document = globalThis.document || { addEventListener() {}, removeEventListener() {}, visibilityState: 'visible' }
  globalThis.localStorage = {
    getItem: key => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: key => store.delete(key),
    clear: () => store.clear(),
    key: index => [...store.keys()][index] ?? null,
    get length() { return store.size },
  }
  return store
}

/** 从渲染产物里逐枚抠 <button>：类名列表、testid、type、aria-label、可见文本。 */
function renderedButtons(html) {
  const items = []
  const re = /<button\b/g
  let match = null
  while ((match = re.exec(html))) {
    const open = match.index
    let i = open + '<button'.length
    let quote = null
    while (i < html.length) {
      const ch = html[i]
      if (quote) { if (ch === quote) quote = null } else if (ch === '"' || ch === "'") quote = ch
      else if (ch === '>') break
      i += 1
    }
    const close = html.indexOf('</button>', i)
    const attrs = html.slice(open + '<button'.length, i).replace(/\s+/g, ' ').trim()
    items.push({
      attrs,
      classes: ' ' + grab(attrs, /class="([^"]*)"/).trim() + ' ',
      testid: grab(attrs, /data-testid="([^"]*)"/),
      type: grab(attrs, /type="([^"]*)"/),
      ariaLabel: grab(attrs, /aria-label="([^"]*)"/),
      disabled: /(?:^|\s)disabled(?:=""|\s*$)/.test(attrs),
      text: (close < 0 ? '' : html.slice(i + 1, close)).replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim(),
    })
  }
  return items
}
const byClass = (items, name) => items.filter(item => item.classes.includes(' ' + name + ' '))

/**
 * 挂一次真壳层出 HTML：跑真 setup()，登录门由 seed 决定；带令牌时先 checkAuth() 进工作台。
 * 面板位（RouterView）换成空桩 —— 本件看的是壳层那八枚，不是任何一屏。
 */
async function shell(seed = {}) {
  const store = installDomStubs(seed)
  const loggedIn = store.has(TOKEN_KEY)
  const route = reactive({
    name: loggedIn ? 'overview' : '', path: '/', query: {}, params: {},
    meta: { title: '屏名', screen: true }, fullPath: '/', hash: '', matched: [],
  })
  let bindings = null
  const Host = defineComponent({
    name: 'R307bShellHost',
    ssrRender: App.ssrRender,
    setup(props, ctx) {
      if (!bindings) {
        bindings = App.setup({}, ctx)
        if (loggedIn) bindings.checkAuth()
      }
      return bindings
    },
  })
  const render = async () => {
    const app = createSSRApp(Host)
    app.provide(routeLocationKey, route)
    app.provide(routerKey, { push() {}, replace() {}, currentRoute: { value: route } })
    app.component('RouterView', { ssrRender: () => {} })
    const html = await renderToString(app)
    return { html, buttons: renderedButtons(html) }
  }
  const first = await render()
  // 同一本绑定反复出图：开合与提示条那两条要的就是「按一下之后再渲染一次，屏上变成什么样」。
  return { ...first, render, bindings, store, route }
}

// ==================== 甲 · 形状腿：八枚逐枚对照表 ====================

describe('R307b 甲 · App.vue 的八枚一枚不多一枚不少，档位照派工那张表', () => {
  it('App.vue 的源码里裸 button 开标签归零，接原语的恰有八枚', () => {
    expect(countNativeButtons(appSource), 'App.vue 又长出裸按钮了').toBe(0)
    expect(tags, '接原语的枚数不是八枚').toHaveLength(8)
  })

  it.each(WIRING)('$cls 那一枚：variant=$variant / size=$size / type=$type', row => {
    const tag = tagOf(row.cls)
    expect(tag.variant, row.cls + ' 的档位不是派工表上那一档').toBe(row.variant)
    expect(tag.size, row.cls + ' 的尺寸档不对').toBe(row.size)
    expect(tag.type, row.cls + ' 的 type 掉了或换人了').toBe(row.type)
  })

  it('七枚带 @click，剩下那一枚必须是 type="submit"（一枚都不许按不动）', () => {
    const quiet = tags.filter(tag => !tag.click && tag.type !== 'submit')
    expect(quiet.map(tag => ':' + tag.line + ' ' + tag.classes.join('.')), '这些枚既没接 @click 也不走表单提交').toEqual([])
    // :click 这种「绑到一枚可能不存在的表达式」的写法今天一枚都不该有：看着像接上了，按下去没反应。
    expect(tags.filter(tag => tag.boundClick).map(tag => ':' + tag.line), '出现了 :click 写法').toEqual([])
    // 派工写明这八枚本来一枚都不绑 :disabled；哪天有人加上去，这条会先要求把它写进档位表。
    const withDisabled = tags.filter(tag => tag.disabled).map(tag => tag.classes.join('.'))
    expect(withDisabled, '这八枚今天不绑 disabled：要加就先改本件的档位表并交代清楚').toEqual([])
  })

  it('侧栏那一枚仍带着 v-for 与 :key，aria-current / :data-testid / :aria-label 一字不掉', () => {
    const nav = tagOf('nav-item')
    expect(nav.vfor, '侧栏不再是 v-for 出来的了').toBe(true)
    expect(nav.key, '侧栏那一枚的 :key 掉了').toBe(true)
    expect(nav.aria, '侧栏每一枚的可及名称掉了').toBe(true)
    expect(nav.attrs).toMatch(/:aria-current=/)
    expect(nav.attrs).toMatch(/:data-testid="\S*nav-/)
    expect(nav.classes).toContain('nav-item')
  })

  it('退出那枚仍把同一句名称同时给 aria-label 与 title；弹窗与提示条那两枚仍自报家门', () => {
    const logout = tagOf('logout-link')
    expect(logout.aria, '退出的可及名称掉了').toBe(true)
    expect(logout.title, '退出的 title 掉了（悬停那一格与读屏念的是同一句）').toBe(true)
    expect(logout.attrs).toMatch(/:aria-label="logoutLabel"/)
    expect(logout.attrs).toMatch(/:title="logoutLabel"/)
    expect(tagOf('auth-toast-close').attrs).toMatch(/aria-label="关闭提示"/)
    expect(tagOf('login-dialog__close').attrs).toMatch(/aria-label="关闭"/)
    expect(tagOf('login-control__ghost').attrs).toMatch(/:aria-label="showPassword \?/)
  })

  it('引的是 components/ui 那一份出口，本件没有另开一套平行实现', () => {
    expect(appSource).toMatch(/import\s*\{[^}]*\bUiButton\b[^}]*\}\s*from\s*'\.\/components\/ui'/)
    expect(appSource).not.toMatch(/UiButton\.vue'/)
  })

  it('原语一字未改：variant 白名单仍是四档，没有为这八枚新开 link 档', () => {
    expect(primitiveSource).toMatch(/\['primary', 'secondary', 'ghost', 'danger'\]/)
    expect(primitiveSource).not.toMatch(/'link'/)
    expect(primitiveSource).toMatch(/data-testid="ui-button"/)
  })

  it('背景五层一枚没碰：login-bg 五格、app-bg 四格与那两行「干净切图」注释原样在位', () => {
    expect(appCode).toContain('class="login-bg"')
    expect(appCode).toContain('class="app-bg"')
    expect(['base', 'art', 'grid', 'noise', 'scrim'].every(part => appCode.includes('login-bg__' + part))).toBe(true)
    expect(['base', 'art', 'grid', 'scrim'].every(part => appCode.includes('app-bg__' + part))).toBe(true)
    // 层数与「纯装饰」那两格也钉住：登录五层、工作台四层，每层都 aria-hidden，一层都不许被换成图片槽。
    expect((appCode.match(/class="login-bg__\w+"/g) || []).length, '登录背景不是五层').toBe(5)
    expect((appCode.match(/class="app-bg__\w+"/g) || []).length, '工作台背景不是四层').toBe(4)
    expect(appCode).toMatch(/<div class="login-bg" aria-hidden="true">/)
    expect(appCode).toMatch(/<div class="app-bg" aria-hidden="true">/)
    expect(appSource).toContain('R148 背景四层')
    // 派工词里说注释有「干净切图到位后再取消注释」那两行：本树现取零命中（见回执），
    // 所以这一格改钉成「背景四层这一段注释一字未动」。
    expect((appSource.match(/R148 背景/g) || []).length).toBe(1)
  })
})

// ==================== 乙 · 真产物腿：屏上仍是那几枚真 button，点击语义逐枚不变 ====================

describe('R307b 乙 · 渲染产物：接原语之后屏上还是那些控件，一枚没少、一枚没换人', () => {
  const STAFF = { [TOKEN_KEY]: 'jwt-live', [USER_KEY]: 'baiye', [ROLE_KEY]: 'staff' }

  it('地基：每一枚渲染出的 button 都带 ui-button 基类与档位类（解析不到的桩没有这两格）', async () => {
    const { buttons } = await shell(STAFF)
    // 枚数基线随真实屏上的控件长一格（R333，2026-09-27，总控裁定一走 ②不走 ①）：顶栏
    // .workspace-tools 自 R333 起合法多出一枚【接了原语】的按钮 —— components/NotificationBell.vue
    // 的触发件（./ui 的 UiButton，data-testid="notification-trigger"）。这一行【仍然是精确相等】：
    // 换成 toBeGreaterThanOrEqual 才是放宽，它抓不到「侧栏少接了一枚」这种倒退，本仓规矩是能精确就精确。
    // 多出来的那一枚「是谁」由下面三条具名钉住，不许退成「随便多一枚都算对」。
    expect(buttons.length, '工作台一枚控件都没渲染出来，下面所有逐枚对照都会退成空集').toBe(navigation.length + 2)
    buttons.forEach(item => {
      expect(item.classes, '这一枚不是 UiButton 渲染的：' + item.attrs).toContain(' ui-button ')
      expect(/ui-button--(primary|secondary|ghost|danger)/.test(item.classes), '档位类没算出来：' + item.attrs).toBe(true)
    })
    // 具名一：多出来那一枚必须是通知 —— 按类名只数到一枚，可及名称以「通知」开头。
    const bell = byClass(buttons, 'notif__bell')
    expect(bell, '顶栏多出来那一枚不是通知（notif__bell 没渲染出来，枚数就不该长这一格）').toHaveLength(1)
    expect(bell[0].ariaLabel, '这一枚的可及名称不是「通知」开头：多出来的不是通知那一枚').toMatch(/^通知/)
    // 具名二：它走的是原语，不是又长出一枚裸 <button>（r288 的合计棘轮 9 枚同时盯着这一格）。
    expect(bell[0].testid, '通知那一枚没有自报家门').toBe('notification-trigger')
    // 具名三：把通知这一枚摘干净就退回原基线 —— 这一格与 navigation.length + 1 之间的差只有它。
    expect(buttons.filter(item => !item.classes.includes(' notif__bell ')), '除通知那一枚之外不是「侧栏 + 退出」的原样').toHaveLength(navigation.length + 1)
  })

  it('工作台那一屏：侧栏 navigation.length 枚 + 顶栏一枚退出，data-testid 逐枚对得上', async () => {
    const { buttons } = await shell(STAFF)
    const nav = byClass(buttons, 'nav-item')
    expect(nav, '侧栏渲染出的枚数与路由表对不上').toHaveLength(navigation.length)
    nav.forEach((item, index) => {
      expect(item.testid, '侧栏第 ' + (index + 1) + ' 枚的 testid 被原语自己那一格顶掉了').toBe('nav-' + navigation[index].id)
      expect(item.text).toBe(navigation[index].label)
      expect(item.type).toBe('button')
    })
    const logout = byClass(buttons, 'logout-link')
    expect(logout, '顶栏那枚退出没渲染出来').toHaveLength(1)
    expect(logout[0].text, '退出那一格画的还是不是 ⌄').toBe('⌄')
    expect(logout[0].ariaLabel).toBe('退出登录（当前账号 baiye）')
    expect(logout[0].classes).toContain(' ui-button--ghost ')
    expect(logout[0].classes).toContain(' ui-button--sm ')
  })

  it('登录那一屏：三枚真 <button>，档位各就各位，显式 testid 不被原语顶掉', async () => {
    const { buttons } = await shell({})
    expect(buttons.length, '登录屏该有那三枚').toBe(3)
    const ghost = byClass(buttons, 'login-control__ghost')
    expect(ghost).toHaveLength(1)
    expect(ghost[0].classes).toContain(' ui-button--sm ')
    expect(ghost[0].ariaLabel).toBe('显示密码')
    const link = byClass(buttons, 'login-link')
    expect(link[0].testid, '忘记密码那枚的 testid 被顶掉了').toBe('login-forgot')
    expect(link[0].text).toBe('忘记密码？')
    const submit = byClass(buttons, 'login-submit')
    expect(submit[0].type, '进入工作台那枚不再是 submit，表单那条路就断了').toBe('submit')
    expect(submit[0].classes).toContain(' ui-button--primary ')
    expect(submit[0].testid).toBe('login-submit')
    // 三枚里两枚写了显式 testid 就保住两枚；没写的那一枚（显示密码）留着原语自带的那一格，
    // 这不是被顶掉 —— 名单对得上才算接线没漏。
    expect(buttons.map(item => item.testid).sort()).toEqual(['login-forgot', 'login-submit', 'ui-button'].sort())
  })

  it('开合：真调 openForgotPassword 多出两枚（× 与 返回登录），再真调 closeForgotPassword 两枚下屏', async () => {
    const box = await shell({})
    box.bindings.openForgotPassword()
    const after = await box.render()
    const close = byClass(after.buttons, 'login-dialog__close')
    expect(close, '弹窗右上角那枚 × 没渲染出来').toHaveLength(1)
    expect(close[0].text).toBe('×')
    expect(close[0].testid).toBe('login-forgot-close')
    expect(close[0].ariaLabel).toBe('关闭')
    const action = byClass(after.buttons, 'login-dialog__action')
    expect(action, '「返回登录」那枚没渲染出来').toHaveLength(1)
    expect(action[0].text).toBe('返回登录')
    expect(action[0].classes).toContain(' ui-button--primary ')
    box.bindings.closeForgotPassword()
    const gone = await box.render()
    expect(byClass(gone.buttons, 'login-dialog__close'), '关了之后 × 还在屏上').toHaveLength(0)
    expect(byClass(gone.buttons, 'login-dialog__action'), '关了之后「返回登录」还在屏上').toHaveLength(0)
  })

  it('提示条那一枚 ×：真调 showToast 上屏，真关掉之后下屏，aria-label 一路不变', async () => {
    const box = await shell(STAFF)
    expect(byClass(box.buttons, 'auth-toast-close'), '没有提示的时候不该有这枚').toHaveLength(0)
    box.bindings.showToast('登录状态已失效，请重新登录。', 'error')
    const shown = await box.render()
    const close = byClass(shown.buttons, 'auth-toast-close')
    expect(close, '提示条那枚 × 没渲染出来').toHaveLength(1)
    expect(close[0].text).toBe('×')
    expect(close[0].ariaLabel).toBe('关闭提示')
    expect(close[0].classes).toContain(' ui-button--ghost ')
    box.bindings.toast.value = null
    const gone = await box.render()
    expect(byClass(gone.buttons, 'auth-toast-close'), '关掉之后那枚 × 还钉在屏上').toHaveLength(0)
  })

  it('显示密码那枚按下去真的换字形：aria-label 与密码框的 type 跟着 showPassword 走', async () => {
    const box = await shell({})
    expect(box.bindings.showPassword.value, '本来该是藏着的样子').toBe(false)
    expect(box.html).toContain('data-testid="login-password" type="password"')
    box.bindings.showPassword.value = true
    const again = await box.render()
    const ghost = byClass(again.buttons, 'login-control__ghost')
    expect(ghost[0].ariaLabel).toBe('隐藏密码')
    expect(again.html).toContain('data-testid="login-password" type="text"')
  })
})

// ==================== 丙 · 基线复位那一段 CSS ====================

describe('R307b 丙 · 接原语补的基线复位：名单齐、不添裸色值、插槽那一层撤得掉', () => {
  const style = /<style scoped>([\s\S]*)<\/style>/.exec(appSource)?.[1] || ''
  const mark = style.indexOf('R307 第二棒')
  const reset = mark < 0 ? '' : style.slice(mark)

  it('复位块在位，八枚类名一条都不许漏（漏一枚就是那枚的脸没人管）', () => {
    expect(mark, 'App.vue 里找不到那段基线复位的起点注释').toBeGreaterThan(-1)
    expect(reset.length, '复位块短得不像话').toBeGreaterThan(400)
    WIRING.forEach(row => {
      expect(reset, '复位块里没有 ' + row.cls + ' 这一格').toContain('.' + row.cls)
    })
  })

  it('焦点环仍指全站那一句（--cyan / 3px），八枚全在名单里', () => {
    const block = /([^{}]*:focus-visible[^{}]*)\{([^}]*)\}/.exec(reset)
    expect(block, '找不到那一条 :focus-visible 复位').toBeTruthy()
    WIRING.forEach(row => expect(block[1]).toContain('.' + row.cls + ':focus-visible'))
    expect(block[2]).toMatch(/outline:\s*2px solid var\(--cyan\)/)
    expect(block[2]).toMatch(/outline-offset:\s*3px/)
  })

  it('本单新增的 CSS 一枚裸色值都不许添（只准 var(--*)），也不许用 !important 硬顶权重', () => {
    expect(reset).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(reset).not.toMatch(/\brgba?\(/)
    expect(reset).not.toMatch(/:\s*(white|black|red|blue|green|gray|grey|silver|navy|teal)\b/)
    expect(reset).not.toMatch(/!important/)
  })

  it('插槽多包的那一层撤得掉：:deep(.ui-button__label) 那一条在位', () => {
    expect(reset).toMatch(/:deep\(\.ui-button__label\)\s*\{[^}]*display:\s*contents/)
  })
})

// ==================== 戊 · 真浏览器实测的复原格位（数值是量出来的，不是推出来的） ====================

/**
 * 丙组钉的是「名单齐、不添裸色值」，那一钉对「复原成了哪一格」是软的：
 * 把 .logout-link 的内距从实测的 1px 6px 改回 0，屏上那枚 ⌄ 会从 20px 宽缩成 8px，丙组照样绿。
 * 所以这一组钉具体格位。数值来源：改前那份打包件（App.vue 取 1dda05e，其余文件与本树同一份）
 * 与本棒这份各起一次真 Chromium（1280×860，注入 *{transition:none;animation:none} 去掉采样噪声），
 * 逐枚读 getComputedStyle / getBoundingClientRect，再按元素盒裁图逐像素比。
 * 读数记在这里，是为了说清第一版复位错在哪（第一版按级联推导写的，推导本身有错）：
 *   .logout-link                width 20px → 8px（原语把 UA 给 <button> 的 1px 6px 内距撤掉了）
 *   .auth-toast-close           19.81×18px → 7.81×22px（同上，外加把本文件自己那条 line-height: 1 顶成 normal）
 *   [data-testid=login-forgot]  height 21.4375px → 18px（line-height 写 normal，把祖先那档 1.65 丢了）
 *   .login-dialog__close        × 的落点：display:block + UA 内距 被换成 flex 居中
 *   .nav-item / .login-control__ghost   font-size 16px → 14px / 13px（原语字级顶掉 button{font:inherit}）
 * 复原之后同一套量法再跑一遍（27 格 = 9 枚 × rest/hover/Tab 三态，各取元素盒外扩 4px）：
 *   · 24 格逐像素 0 差；
 *   · 2 格是「忘记密码？」的 rest 与 hover：整块 73×30 裁图（含外扩那 4px 的边框圈）逐点 ±1/255，
 *     盒尺寸 65×21.44px 与每一格绘制属性（color / background / border / box-shadow / opacity）都相同 ——
 *     差的不是这枚控件本身，而是它身后那张登录卡 backdrop 的光栅取整；这一条本棒没能归因到某一格声明上；
 *   · 1 格是 .logout-link 的 hover：≥16/255 的像素 18 枚，max=141（见本组最后一条那笔账）。
 * 同一份打包件自己比自己（噪声地板）：27 格全 0 差 —— 上面这些数不是采样抖动。
 */
describe('R307b 戊 · 基线复位复原到了哪一格（真浏览器实测值）', () => {
  const style = /<style scoped>([\s\S]*)<\/style>/.exec(appSource)?.[1] || ''
  const mark = style.indexOf('R307 第二棒')
  const resetNoComment = mark < 0 ? '' : style.slice(mark).replace(/\/\*[\s\S]*?\*\//g, '')
  /** 取出这一格里某一枚类名的声明。bare=true 只要裸类名（不含伪类），bare='hover' 只要 :hover 那一条。 */
  function declOf(cls, bare) {
    const want = bare === true ? '.' + cls : bare ? '.' + cls + ':' + bare : null
    expect(want, '戊组量具用错了参数').toBeTruthy()
    const parts = []
    const re = /([^{}]+)\{([^{}]*)\}/g
    let match = null
    while ((match = re.exec(resetNoComment))) {
      const sels = match[1].split(',').map(s => s.replace(/\s+/g, ' ').trim())
      if (sels.includes(want)) parts.push(match[2].replace(/\s+/g, ' ').trim())
    }
    return parts.join(' ')
  }

  const RESTORE = [
    { cls: 'login-control__ghost', need: ['font: inherit', 'min-height: auto', 'padding: 1px 6px'] },
    { cls: 'login-link', need: ['display: block', 'min-height: auto', 'border-radius: 0', 'line-height: inherit', 'font-weight: inherit'] },
    { cls: 'login-submit', need: ['min-height: 0', 'padding: 1px 6px', 'line-height: inherit'] },
    { cls: 'login-dialog__close', need: ['display: block', 'min-height: auto', 'padding: 1px 6px', 'transition: none'] },
    { cls: 'login-dialog__action', need: ['min-height: 0', 'line-height: inherit', 'transition: none'] },
    { cls: 'nav-item', need: ['font-size: inherit', 'justify-content: flex-start'] },
    { cls: 'logout-link', need: ['display: block', 'min-height: auto', 'padding: 1px 6px', 'line-height: normal'] },
    { cls: 'auth-toast-close', need: ['display: block', 'min-height: auto', 'padding: 1px 6px', 'transition: none'] },
  ]

  it.each(RESTORE)('$cls 的复原格位齐（实测值）', row => {
    const decl = declOf(row.cls, true)
    expect(decl, '复位块里找不到 .' + row.cls + ' 这一条裸类名声明').not.toBe('')
    row.need.forEach(d => expect(decl, '.' + row.cls + ' 少了复原项「' + d + '」').toContain(d))
  })

  it('四枚小控件的内距钉在 UA 实测那一格：谁改回 padding: 0，⌄ 与 × 就先缩掉 12px', () => {
    ['login-control__ghost', 'login-dialog__close', 'logout-link', 'auth-toast-close'].forEach(cls => {
      const decl = declOf(cls, true)
      expect(decl, '.' + cls + ' 这一格没有把 UA 内距写回来').toMatch(/padding:\s*1px 6px/)
      expect(decl, '.' + cls + ' 又出现了 padding: 0（那会把 UA 那一格顶掉）').not.toMatch(/padding:\s*0(;|\s|$)/)
    })
  })

  it('提示条 × 的行高不归这一段管：复位块里不许给它写 line-height', () => {
    // 改前那一格是 16px，来源是本文件上面那条 .auth-toast-close{line-height: 1}（16px 字级 × 1）。
    // 复位块里写 line-height 的两种写法都会把它顶掉：normal → 实测盒子从 18px 撑成 22px。
    expect(declOf('auth-toast-close', true), '.auth-toast-close 的复位里不许出现 line-height')
      .not.toMatch(/line-height/)
  })

  it('字级不许停在原语那一档：ghost 与侧栏条目都走继承', () => {
    expect(declOf('login-control__ghost', true)).toMatch(/font:\s*inherit/)
    expect(declOf('nav-item', true)).toMatch(/font-size:\s*inherit/)
    const listed = ['login-control__ghost', 'nav-item', 'login-link', 'logout-link', 'auth-toast-close']
    listed.forEach(cls => {
      expect(declOf(cls, true), '.' + cls + ' 写死了原语的字级').not.toMatch(/font-size:\s*1[345]px/)
    })
  })

  it('顶栏退出 hover 那一格是一笔记了账的残留：这一段只压底色，不许偷偷写文字色', () => {
    // 实测：改前 rgb(91,234,255)（theme.css:1799 .workspace-tools > button:hover{color:#5beaff}，
    // 权重 (0,2,1)）被原语 .ui-button--ghost:hover:not(:disabled){color:var(--text-1)}（(0,3,0)）压掉。
    // 本棒写域里没有 theme.css，全站也没有任何一枚 token 等于 #5beaff（--cyan=#59e4e5，
    // --accent-hover=#57c4f5），而 lint 预算 148 已满 ⇒ 写死色值当场红。所以这一格现在是真的复不了原。
    // 这条钉把残留摆成显式状态：补上 color（无论 var 还是 hex）当场红，逼改的人回来更新这笔账；
    // 正解在 theme.css:1799 把选择器写成 .workspace-tools > button.ui-button:hover（一处、零新色值）。
    const hover = declOf('logout-link', 'hover')
    expect(hover, '.logout-link:hover 的底色复位掉了').toContain('background: transparent')
    expect(hover, '.logout-link:hover 出现了文字色：要么这笔残留已经还掉（请同步改注释与回执），要么是偷偷写死色值')
      .not.toMatch(/(^|\s)color:/)
  })
})

// ==================== 丁 · r197 夹具：桩件与真组件的差别，现场对照一次 ====================

describe('R307b 丁 · 判据④：夹具注册的是真原语，绿的不再是桩', () => {
  const row = {
    filename: '差旅费报销制度-2026.pdf', sourceId: 'doc-travel', chunkIndex: 4, score: 0.412,
    scoreType: 'rerank', versionId: '7', classification: '2', department: '销售部', excerpt: '',
  }
  const face = sourcesFace({ rows: [row], hitCount: 1, hiddenCount: 0, scopeReasonCode: 'department_scope' })

  // 为什么这一格只能钉在「编译产物的形状 + 夹具自己」这两处，而不是钉一条渲染出来的对照：
  // 产品自己那份 ssrRender（vite 编的）带着 <script setup> 的绑定表，模板里的 <UiButton>
  // 编成了 _unref(UiButton) —— 那条路【不问注册表】，所以拿 createSSRApp 不管注册不注册都渲染得出来。
  // 夹具不一样：它把模板原文再过一遍运行时编译器（没有绑定表），编出来的是按【名字】解析的
  // resolveComponent("UiButton") —— 只有这一条路上，注册表缺那一枚才会退化成解析不到的桩。
  // 那 30 条 "Failed to resolve component: UiButton" 的读数就是这么来的，收工前后各一次见回执。
  it('机制前提：夹具那条 compile 出来的路径确实按名字解析 UiButton（所以必须注册）', () => {
    const template = /<template>([\s\S]*)<\/template>/.exec(readSrc(join('components', 'SourceCard.vue')))
    expect(template, 'SourceCard.vue 里取不到 <template>').toBeTruthy()
    // vue 的运行时 compile 交回的是编好的 render 函数，函数体原文就是那份生成码。
    const generated = String(compile(template[1]))
    expect(generated).toMatch(/resolveComponent\w*\(\s*["']UiButton["']/)
    // 负对照：原语自己的模板不引用任何组件，编译产物里不该有这一句。
    const own = /<template>([\s\S]*)<\/template>/.exec(primitiveSource)
    expect(String(compile(own[1]))).not.toMatch(/resolveComponent\w*\(\s*["']UiButton["']/)
  })

  it('产品真身那三枚确实渲染得出来：三枚真 <button> 与两格档位类（这是乙组的地基）', async () => {
    installDomStubs()
    const html = await renderToString(createSSRApp({ render: () => h(SourceCard, { face }) }))
    const items = renderedButtons(html)
    expect(items, '出处卡上该有三枚真按钮').toHaveLength(3)
    expect(items.map(item => item.testid)).toEqual(['source-open', 'source-feedback-accept', 'source-feedback-reject'])
    expect(items[0].classes).toContain(' ui-button--ghost ')
    expect(items[1].classes).toContain(' ui-button--secondary ')
    expect(html).not.toContain('<uibutton')
  })

  it('r197 的夹具确实注册了原语，注册的还是客户端化那一份', () => {
    expect(r197Source).toMatch(/components:\s*\{\s*UiButton:\s*clientUiButton\(\)\s*\}/)
    expect(r197Source).toMatch(/function\s+clientUiButton\s*\(/)
    expect(r197Source).toMatch(/source\('ui\/UiButton\.vue'\)/)
    // 只把 ssrRender-only 那份注册进客户端夹具会报 Missing render function：客户端化那一格必须在。
    expect(r197Source).toMatch(/compile\(template\[1\]\)/)
  })

  it('r197 没被顺手改口：四组组名与那把「跨轮不许带锁」的行为钉原样在位', () => {
    ['R197 甲', 'R197 乙', 'R197 丙', 'R197 丁'].forEach(name => {
      expect(r197Source, '组名不见了：' + name).toContain(name)
    })
    expect(r197Source).toContain("expect(markButton(loop.root, 'source-feedback-accept')")
    expect(r197Source).toContain('toEqual({ disabled: true, pressed: true })')
    expect(r197Source).toContain('switchTo')
    expect(r197Source).toContain('不许跟着 filename 跨轮走')
  })
})
