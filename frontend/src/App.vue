<script setup>
import { computed, nextTick, onMounted, onUnmounted, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { DEFAULT_SCREEN, FEED_SCREEN, cachedScreens, navigationForRole, screenRouteIds } from './router'
import { focusScreenMain, navItems, nextNavItem } from './router/nav-focus'
import { resetSessions } from './lib/sessions'
import { UiButton } from './components/ui'
import NotificationBell from './components/NotificationBell.vue'
import {
  clearSession,
  errorDetail,
  hasSession,
  http,
  ROLE_KEY,
  saveSession,
  startExpiryWatch,
  subscribeAuth,
  USER_KEY,
} from './lib/http'

const route = useRoute()
const router = useRouter()
const navEl = shallowRef(null)
const workspaceEl = shallowRef(null)
const isLoggedIn = shallowRef(false)
const username = shallowRef('')
const userRole = shallowRef('staff')
const loginUser = shallowRef('')
const loginPass = shallowRef('')
const loginError = shallowRef('')
const rememberMe = shallowRef(false)
const showPassword = shallowRef(false)
const showForgotDialog = shallowRef(false)
const forgotUsername = shallowRef('')

const REMEMBER_KEY = 'eb_remember_username'

// 全站唯一的鉴权状态来自 lib/http.js；这里只留界面态。
let stopExpiryWatch = null
let unsubscribeAuth = null
let toastTimer = null
const toast = shallowRef(null)

// R104：侧栏那几项与「点下去渲染谁」都从 src/router 的一张路由表派生，这里不再手写第二份。
// 图谱的非一级落点（/graph）也在那张表上，D13① 撤的是一级入口而不是功能。
// R136：屏名同样只在那张表上写一遍（meta.title），顶栏与侧栏都是它的派生视图。

// 顶栏标题（面包屑的末级）只认路由元信息：它以前回头查 navigation 数组，等于「现在在哪一屏」
// 有两份记账，查的那份还可能是过期的。
const activeMeta = computed(() => route.meta || {})
// user-role 这项入参今天只有「喂料」屏里的文档那一枚标签要：绑给谁由 src/router 的标签表
// （feed-tabs.js 的 needsUserRole 那一列）决定，这里只认屏名，不认面板，也不写 'docs' 字面量。
// 其余屏不该收到多余属性。
const screenProps = computed(() => (route.name === FEED_SCREEN ? { userRole: userRole.value } : {}))
const roleLabel = computed(() => userRole.value === 'admin' ? '管理员' : '普通用户')

/**
 * R278 · G16 · 顶栏不留死控件（改造前：两枚 button 挂着但没有 @click，按下去什么都不发生）
 *
 * 搜索那一枚【摘掉】而不是接半截：全站没有一枚「全局检索」端点可用。app/api 的路由名单里
 * 只有 POST /retrieval/debug（管理侧的可观测工具，不是员工搜索框）与各屏自己的列表
 * （documents/catalog、artifacts、data-files）。壳层要接，只能把关键字塞进「当前那一屏」的
 * 筛选框，而壳层不认识各屏的输入框，硬猜就是第二件假控件。
 *
 * 通知那一枚同样【摘掉】，理由是今天没有一句诚实的「条数」可说：
 *   · GET /hitl/pending 回的那个计数是过滤并逐行向图复核之后【这一页】的长度，契约
 *     docs/api/contract-v1.md 的 HITL Pending Listing 一节明写它不得当总数用；
 *   · GET /dashboard/summary 那一格虽是全集长度，却不向图复核，它自己模块头写着「可能高估、
 *     绝不会少报」——拿它摆徽标就是把已经办完的事说成还等着拍板；
 *   · 徽标要在人点开之前就有数，只能每屏挂载时多发一次请求去猜，这笔代价不该由壳层背。
 * R333（2026-09-26）把上面那段对「通知」的判据改了一半：摘它的理由是「今天没有一句诚实的
 * 条数可摆」，而 R299 的 GET /notifications 交回的是【全集】未读总数（unread_total，窗口裁过时
 * is_exact=false，两个总数只算下界）。所以顶栏现在摆得动这枚徽标，也只剩这里能摆。
 * 搜索那一枚的判据一字未动：全站仍没有一枚诚实的全局检索端点，那一格继续空着（判据⑧）。
 * 真待办的正脸在侧栏那一屏（components/hitl/HitlPendingPanel.vue 读同一本账），入口不在这枚钮上。
 */
// 退出那枚原先只画一个「⌄」：读屏念出来只有「按钮」，看着像下拉箭头，按下去却是登出。
// 可及名称补上「当前是谁」——私有化机器常是几个人共用一个浏览器，这一句同时是「要把谁下线」
// 的确认。账号名读的是 lib/http 那份唯一真源；没有名字（异常态）就只说「退出登录」，不编一个。
const logoutLabel = computed(() => (username.value
  ? `退出登录（当前账号 ${username.value}）`
  : '退出登录'))

/**
 * 跨屏跳转的唯一出口：目标是路由名（屏 id），不再是 tab 字符串。
 * 认不出的屏什么都不做 —— 面板可以随便加按钮，但按不动一张没有的地址。
 */
function openScreen(screen) {
  const name = String(screen || '')
  if (!screenRouteIds.includes(name) || route.name === name) return undefined
  return router.push({ name })
}

async function handleAsk(query) {
  // 对话面板改由 /chat 路由决定挂载（改造前是 v-show 常驻），事件早一拍发就没人接，
  // 所以先等这一屏挂上，再把问题交给它。nextTick 的回调形状留着不要改写成 await：
  // tests/test_data_file_catalog.py::test_chat_request_forwards_selected_data_filename
  // 是按源码文本钉这条「切屏之后才派发」的顺序的，后端侧那份账不在本单写域里。
  await openScreen('chat')
  nextTick(() => window.dispatchEvent(new CustomEvent('chat-ask', { detail: query })))
}

function checkAuth() {
  const rememberedUsername = localStorage.getItem(REMEMBER_KEY)
  if (rememberedUsername) {
    loginUser.value = rememberedUsername
    rememberMe.value = true
  }
  if (!hasSession()) return
  username.value = localStorage.getItem(USER_KEY) || ''
  userRole.value = localStorage.getItem(ROLE_KEY) || 'staff'
  enterWorkspace()
}

async function enterWorkspace() {
  isLoggedIn.value = true
  stopExpiryWatch?.()
  stopExpiryWatch = startExpiryWatch()
  // 登录不改地址，所以不会触发下面的切屏 watch；焦点由这里自己收尾到工作区主区。
  await nextTick()
  focusScreenMain(workspaceEl.value)
}

function showToast(message, tone = 'error', holdMs = 6000) {
  toast.value = { message, tone }
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = null }, holdMs)
}

// lib/http.js 只有一条失效收尾：真过期与 401 共用同一个 unauthorized 事件（令牌已经不再
// 可信，留着只会让界面继续拿它发请求）；expiring 只是「快到期」的提醒，只弹提示不动会话。
// R171：这一支收的是「任何」鉴权事件，不能假定发出方带了文案。今天 shipped 的两枚事件都带
// （lib/http.js:95 / :127），但少带 message、带空串、带非字符串都会把人从工作台踢回登录页，
// 而错误条与提示条两处一起空着——员工看到的是「莫名其妙被登出」。这里补两句自家话，两张脸
// 各一句：真失效说失效，来路不明说来路不明；两句话面不同，都不含英文稳定码。
const AUTH_EXPIRED_MESSAGE = '登录状态已失效，请重新登录。'
const AUTH_EVENT_UNKNOWN_MESSAGE = '收到无法识别的账号状态事件，为安全起见已退出，请重新登录。'

/** 只有「去掉首尾空白仍非空的字符串」算一句话：undefined / null / 数字 / 纯空白一律不算。 */
function readableMessage(message) {
  return typeof message === 'string' && message.trim() !== '' ? message : ''
}

function onAuthEvent(event) {
  if (!event) return
  if (event.type === 'expiring') {
    showToast(event.message, 'warn', 12000)
    return
  }
  // 认不得的 type 不借用它带来的文案：来路不明的句子不是可信信息，只按「无法识别」这一张脸说。
  const message = event.type === 'unauthorized'
    ? (readableMessage(event.message) || AUTH_EXPIRED_MESSAGE)
    : AUTH_EVENT_UNKNOWN_MESSAGE
  clearSession()
  goToLogin()
  loginError.value = message
  showToast(message, 'error', 6000)
}

function persistRememberedUsername() {
  const normalizedUsername = loginUser.value.trim()
  if (rememberMe.value && normalizedUsername) {
    localStorage.setItem(REMEMBER_KEY, normalizedUsername)
  } else {
    localStorage.removeItem(REMEMBER_KEY)
  }
}

async function doLogin() {
  loginError.value = ''
  persistRememberedUsername()
  try {
    const res = await http.post('/login', {
      username: loginUser.value.trim(),
      password: loginPass.value,
    })
    const data = res.data || {}
    if (!data.token) {
      loginError.value = '登录响应缺少令牌，请重试或联系管理员。'
      return
    }
    saveSession(data)
    username.value = data.username || loginUser.value.trim()
    userRole.value = data.role || 'staff'
    enterWorkspace()
  } catch (err) {
    loginError.value = errorDetail(err, '登录服务暂时不可用')
  }
}

function openForgotPassword() {
  forgotUsername.value = loginUser.value.trim()
  showForgotDialog.value = true
}

function closeForgotPassword() {
  showForgotDialog.value = false
}

/**
 * R278 · 判据④ · 退出清到哪一格，两件事叠在一起判一次
 *
 * 取证（本单基点 951909b，全站可写出的 eb_* 一枚枚数过）：
 *   eb_token / eb_user / eb_role / eb_department / eb_token_expires_at —— lib/http.js:8-12，clearSession() 清；
 *   eb_sessions_v2 / eb_msg_<id> —— lib/sessions.js:13-14，resetSessions() -> clearStoredSessions() 清；
 *   eb_remember_username —— 只有它该活下来（那是「下次给你预填账号名」，不是数据）。
 * 原先那段 eb_* 整包扫挂在 doLogout 里，于是有一个真实的不一致：手动退出洗得到兜底位，
 * 401/过期那条收尾（同一个 goToLogin，却没有那一刀）洗不到。今天两者刚好等价，纯粹因为
 * 暂时没有第六枚键；下一次谁新加一枚 eb_*，被踢下线那台浏览器就会留着上一位的。
 * 所以这一刀上收到两条路共用的出口里：doLogout 的净效果一行未变（该清的照样清），
 * 换人使用的口径从此只有一处：两条收尾走同一把扫帚，不再有「只洗一条路」的第二种写法。
 * 🔴 名单清掉不等于历史找不回来：那一列的第二条腿是 R268 的「点一次从服务端取回」，
 *   它读的是 GET /sessions（服务端按归属过滤），并的是内存 store，本机一行都没有也建得出整张表
 *   （判据钉在 r278-logout-locality 的乙组，与 r268-session-pull 丙组那条同向）。
 */
function goToLogin() {
  resetSessions()
  // 兜底：任何一枚 eb_* 都不许留给下一位使用者，只有「记住我」的账号名例外。
  try {
    const keys = []
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index)
      if (key?.startsWith('eb_') && key !== REMEMBER_KEY) keys.push(key)
    }
    keys.forEach(key => localStorage.removeItem(key))
  } catch {
    /* 隐私模式下没有本地态可清 */
  }
  stopExpiryWatch?.()
  stopExpiryWatch = null
  isLoggedIn.value = false
  username.value = ''
  userRole.value = 'staff'
  loginPass.value = ''
  if (route.name !== DEFAULT_SCREEN) router.replace({ name: DEFAULT_SCREEN })
}

function doLogout() {
  clearSession()
  goToLogin()
}

/**
 * 侧栏方向键走位：下标算绪与下拉、标签页同一份（ui/list-nav.js），可聚焦条目
 * 的选择器与弹层焦点循环同一份（ui/focus-trap.js）。Tab 与 Enter/Space 一概不拦。
 */
function onNavKeydown(event) {
  const target = nextNavItem(navItems(navEl.value), document.activeElement, event.key)
  if (!target) return
  event.preventDefault()
  target.focus()
}

// 切屏后把焦点交给新屏主区，否则焦点还留在侧栏，键盘与读屏用户不知道屏幕已经换了。
watch(() => route.name, async () => {
  await nextTick()
  focusScreenMain(workspaceEl.value)
})

onMounted(() => {
  unsubscribeAuth = subscribeAuth(onAuthEvent)
  checkAuth()
})

onUnmounted(() => {
  unsubscribeAuth?.()
  stopExpiryWatch?.()
  clearTimeout(toastTimer)
})
</script>

<template>
  <div class="app-root">
    <main v-if="!isLoggedIn" class="login-v2" data-testid="login-page">
      <div class="login-bg" aria-hidden="true">
        <span class="login-bg__base"></span>
        <span class="login-bg__art"></span>
        <span class="login-bg__grid"></span>
        <span class="login-bg__noise"></span>
        <span class="login-bg__scrim"></span>
      </div>

      <header class="login-brand">
        <svg class="login-brand__mark" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <path d="M16 2.6 27.4 9.3v13.4L16 29.4 4.6 22.7V9.3z" stroke-linejoin="round" />
          <path d="M16 10.4 21.4 13.5v6.2L16 22.8l-5.4-3.1v-6.2z" stroke-linejoin="round" opacity=".55" />
          <circle cx="16" cy="16.6" r="1.9" fill="currentColor" stroke="none" />
        </svg>
        <span class="login-brand__name">企业智脑</span>
        <span class="login-brand__rule" aria-hidden="true"></span>
        <span class="login-brand__latin">Enterprise Brain</span>
      </header>

      <div class="login-stage">
        <section class="login-pitch" aria-labelledby="login-hero-title" data-testid="login-hero">
          <span class="login-pitch__rule" aria-hidden="true"></span>
          <h1 id="login-hero-title">私有化企业智能分析平台</h1>
          <p class="login-pitch__lead">让企业数据，成为生产力</p>

          <div class="login-capabilities" aria-label="平台能力">
            <div>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3 19 6v5c0 4.6-2.8 8-7 10-4.2-2-7-5.4-7-10V6z" /></svg>
              <span>数据安全</span>
            </div>
            <div>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12 3 8 4-8 4-8-4zM4 12l8 4 8-4M4 17l8 4 8-4" /></svg>
              <span>知识沉淀</span>
            </div>
            <div>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 19V9M12 19V5M19 19v-7" /></svg>
              <span>智能分析</span>
            </div>
          </div>
        </section>

        <section class="login-card" aria-labelledby="login-title" data-testid="login-panel">
          <h2 id="login-title">欢迎回来</h2>
          <p class="login-card__lead">使用企业账号登录工作台</p>

          <div v-if="loginError" class="login-alert" data-testid="login-error" role="alert">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
              <circle cx="12" cy="12" r="9" /><path d="M12 8v5" stroke-linecap="round" /><path d="M12 16.2h.01" stroke-linecap="round" />
            </svg>
            <span>{{ loginError }}</span>
          </div>

          <form data-testid="login-form" autocomplete="on" @submit.prevent="doLogin">
            <label class="login-field">
              <span class="login-field__label">用户名</span>
              <span class="login-control">
                <span class="login-control__icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></svg>
                </span>
                <input v-model="loginUser" data-testid="login-username" type="text" placeholder="请输入用户名" autocomplete="username" required />
              </span>
            </label>

            <label class="login-field">
              <span class="login-field__label">密码</span>
              <span class="login-control">
                <span class="login-control__icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="10.5" width="17" height="10.5" rx="2.5" /><path d="M7.5 10.5V7a4.5 4.5 0 0 1 9 0v3.5" /></svg>
                </span>
                <input v-model="loginPass" data-testid="login-password" :type="showPassword ? 'text' : 'password'" placeholder="请输入密码" autocomplete="current-password" required />
                <UiButton
                  class="login-control__ghost"
                  variant="ghost"
                  size="sm"
                  type="button"
                  :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                  @click="showPassword = !showPassword"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="3" /></svg>
                </UiButton>
              </span>
            </label>

            <div class="login-row">
              <label class="login-check">
                <input v-model="rememberMe" data-testid="login-remember" type="checkbox" />
                <span class="login-check__box" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
                </span>
                <span>记住我</span>
              </label>
              <UiButton
                class="login-link"
                variant="ghost"
                size="sm"
                type="button"
                data-testid="login-forgot"
                @click="openForgotPassword"
              >忘记密码？</UiButton>
            </div>

            <UiButton
              class="login-submit"
              variant="primary"
              type="submit"
              data-testid="login-submit"
            >
              进入工作台
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14" /><path d="m12 5 7 7-7 7" /></svg>
            </UiButton>
          </form>

          <p class="login-card__foot">没有账号？联系管理员在工作台内开通</p>
        </section>
      </div>

      <footer class="login-foot">
        <div class="login-foot__meta">
          <span class="login-badge">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 13c0 5-3.5 7.5-7.7 8.9a1 1 0 0 1-.7 0C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.2-2.7a1 1 0 0 1 1.6 0C14.5 3.8 17 5 19 5a1 1 0 0 1 1 1z" /><path d="m9 12 2 2 4-4" /></svg>
            <span>本机部署 · 数据不出内网</span>
          </span>
          <span class="login-foot__dot" aria-hidden="true"></span>
          <span>企业内网专用</span>
        </div>
      </footer>

      <div v-if="showForgotDialog" class="login-dialog-backdrop" data-testid="login-forgot-dialog">
        <section class="login-dialog" role="dialog" aria-modal="true" aria-labelledby="forgot-title">
          <UiButton
            class="login-dialog__close"
            variant="ghost"
            size="sm"
            data-testid="login-forgot-close"
            type="button"
            aria-label="关闭"
            @click="closeForgotPassword"
          >×</UiButton>
          <h2 id="forgot-title">忘记密码？</h2>
          <p>这是私有化部署系统，密码由企业管理员统一管理。</p>
          <label class="login-dialog__account">
            <span>账号</span>
            <input v-model="forgotUsername" autocomplete="username" placeholder="请输入需要找回的账号" />
          </label>
          <p class="login-dialog__note">请联系管理员在用户管理中重置该账号密码，重置后即可返回此页面登录。</p>
          <UiButton
            class="login-dialog__action"
            variant="primary"
            type="button"
            @click="closeForgotPassword"
          >返回登录</UiButton>
        </section>
      </div>
    </main>
    <div v-else class="workbench-shell reference-workbench" data-testid="workbench">
      <!-- R148 背景四层（L0 基底 / L1 美术 / L2 网格 / L3 遮罩）：纯装饰，aria-hidden +
           pointer-events: none，不放噪点层。参数全部在 theme.css 的 .app-bg* 里。 -->
      <div class="app-bg" aria-hidden="true">
        <span class="app-bg__base"></span>
        <span class="app-bg__art"></span>
        <span class="app-bg__grid"></span>
        <span class="app-bg__scrim"></span>
      </div>
      <aside class="sidebar" aria-label="工作区导航" data-testid="sidebar">
        <div class="sidebar-brand">
          <span class="brand-mark"><span></span></span>
          <span>
            <strong>企业智脑</strong>
            <small>ENTERPRISE BRAIN</small>
          </span>
        </div>
        <nav ref="navEl" class="nav-list" data-testid="navigation" @keydown="onNavKeydown">
          <UiButton
            v-for="item in navigationForRole(userRole)"
            :key="item.id"
            variant="ghost"
            type="button"
            :class="['nav-item', { active: route.name === item.id }]"
            :data-testid="`nav-${item.id}`"
            :aria-current="route.name === item.id ? 'page' : undefined"
            :aria-label="item.label"
            @click="openScreen(item.id)"
          >
            <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path :d="item.icon" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            <span class="nav-label">{{ item.label }}</span>
          </UiButton>
        </nav>
      </aside>

      <main ref="workspaceEl" class="workspace" tabindex="-1" data-testid="workspace">
        <header class="workspace-head" data-testid="topbar">
          <h1>{{ activeMeta.title }}</h1>
          <div class="workspace-tools">
            <!-- R278 · G16①②：这里原先摆着两枚按了没反应的按钮（搜索、通知），一并摘掉。
                 为什么不接半截、今天为什么没有一枚诚实的条数可摆，账记在上面 script 里那段；
                 判据钉在 src 下的顶栏用例 r278-topbar 里。 -->
<!-- R333 · 通知这一格接回来了：不是新增玩法，是把 R278 当年欠的那格补齐。
     当年摘它的理由是「今天没有一句诚实的条数可摆」，R299 用 GET /notifications 的
     全集未读口径（unread_total，另带 is_exact 说明是不是下界）把那句话推翻了；
     搜索那一枚仍不接——它到今天也没有诚实出处，接了就是回到假控件（判据⑧）。
     判据钉在 src/lib/notifications.js、src/components/NotificationBell.vue 与 r333 用例里。 -->
<NotificationBell />
            <span class="user-avatar">{{ username.slice(0, 1).toUpperCase() || 'A' }}</span>
            <span class="identity"><strong>{{ username }}</strong><span>{{ roleLabel }}</span></span>
            <UiButton
              class="logout-link"
              variant="ghost"
              size="sm"
              type="button"
              :aria-label="logoutLabel"
              :title="logoutLabel"
              @click="doLogout"
            >⌄</UiButton>
          </div>
        </header>

        <section class="panel-slot" data-testid="panel-slot">
          <RouterView v-slot="{ Component }">
            <!-- 对话面板切走不卸载：进行中的回答流、输入草稿与滚动位置都得留着（改造前靠 v-show）。
                 其余六屏照旧每次进来重挂载重取数据，与改造前的 v-if 语义一致。 -->
            <KeepAlive :include="cachedScreens">
              <component :is="Component" v-bind="screenProps" @goto="openScreen" @ask="handleAsk" />
            </KeepAlive>
          </RouterView>
        </section>
      </main>
    </div>

    <!-- 鉴权提示：401 失效与临期提醒共用这一条，替代原生 alert -->
    <Transition name="auth-toast">
      <div
        v-if="toast"
        class="auth-toast"
        :class="toast.tone"
        role="status"
        aria-live="polite"
        data-testid="auth-toast"
      >
        <span class="auth-toast-icon" aria-hidden="true">{{ toast.tone === 'warn' ? '⏰' : '🔒' }}</span>
        <span class="auth-toast-text">{{ toast.message }}</span>
        <UiButton
          type="button"
          class="auth-toast-close"
          variant="ghost"
          size="sm"
          aria-label="关闭提示"
          @click="toast = null"
        >
          ×
        </UiButton>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.auth-toast {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 90;
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: min(420px, calc(100vw - 48px));
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-left: 3px solid var(--red);
  border-radius: var(--radius-md);
  background: var(--bg-panel-2);
  color: var(--text);
  font-size: 13px;
  box-shadow: var(--shadow-sm);
}

.auth-toast.warn {
  border-left-color: var(--amber);
}

.auth-toast-text {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}

.auth-toast-close {
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}

.auth-toast-enter-active,
.auth-toast-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.auth-toast-enter-from,
.auth-toast-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
/* ==========================================================================
 * R307 第二棒 · 上面那八枚裸 <button> 接进 ./ui 的 UiButton 之后的基线复位
 *
 * 原语给每一档都配了控件高、内距、字重、hover 皮肤与焦点环，而这八枚在 R148 / R169 /
 * R278 定稿时各有自己的脸。这里只补「原语会改、而 theme.css 与本文件上面那些旧规则
 * 一个字都没写」的那几格，一条裸色值都不添 —— 全部走 theme.css 已有的 var(--*)。
 *
 * 为什么这样写就够（打包顺序是这件事的前提，别在没核对顺序之前改下面的权重）：
 *   main.js 先 import App.vue、后 import ./assets/theme.css，UiButton.css 又随组件走，
 *   所以级联里落地的先后是 UiButton.css → 本文件的 scoped 样式 → theme.css；同权重后来者胜。
 *     · theme.css 已经声明过的属性（display / color / background / border / padding /
 *       font-size / font-weight / min-height / transition …）一处都不必重复：它必然压得过原语；
 *     · 本文件的选择器刻意停在「一枚类名 + scoped 属性」＝(0,2,0) 与
 *       「一枚类名 + :hover / :active + scoped 属性」＝(0,3,0) 这两档：
 *       刚好赢过原语的 .ui-button--*:hover:not(:disabled)＝(0,3,0)（同权重而本文件在后），
 *       却仍然输给 theme.css 的 .reference-workbench .nav-item.active 与窄屏那几条响应式规则
 *       —— 复位不许把点亮态、侧栏窄屏版式压掉，那才是这八枚今天真正的脸。
 * ==========================================================================*/

/* 原语把默认插槽包进一层 .ui-button__label：这一层得从布局里撤掉，图标与文字才回到
   按钮这根 flex 轴上，与接原语前同一排布（侧栏的 svg+文字、主按钮的文字+箭头都在这一格）。
   子组件内部的节点拿不到 scoped 属性，所以走仓里既有的 :deep() 写法。 */
:deep(.ui-button__label) {
  display: contents;
}

/* 焦点环仍是全站那一句（theme.css 的 button:focus-visible）：原语给的 --accent + 2px
   会把登录卡、侧栏与顶栏这一圈青蓝换成另一种颜色与偏移。 */
.login-control__ghost:focus-visible,
.login-link:focus-visible,
.login-submit:focus-visible,
.login-dialog__close:focus-visible,
.login-dialog__action:focus-visible,
.nav-item:focus-visible,
.logout-link:focus-visible,
.auth-toast-close:focus-visible {
  outline: 2px solid var(--cyan);
  outline-offset: 3px;
}

/* 登录卡「显示密码」那枚：theme.css 给的是 44×满高的格子，字级走全站那一句
   button { font: inherit }；原语的 sm 档把字号、字重、行高、内距、控件高一起换掉了。
   下面这些复原值取真浏览器实测（Chromium，1440×900，改前那一版打包件）：
   padding: 1px 6px 是 UA 给 <button> 的默认内距 —— theme.css 这一枚没写 padding，
   改屏上就是这一格；接原语之后由 .ui-button 的 0 12px 顶上来，只能在这里写死它。 */
.login-control__ghost {
  font: inherit;
  min-height: auto;
  padding: 1px 6px;
  border: 0;
  border-radius: 0;
  gap: 0;
}

.login-control__ghost:hover {
  background: none;
}

/* 「忘记密码？」是一枚行内文字链：改前 display: block，行高是祖先那一档 1.65 乘自己的
   13px＝21.45px（实测高 21.4375px）；原语给的是 flex 居中的 18px 小盒。 */
.login-link {
  display: block;
  min-height: auto;
  border-radius: 0;
  font-weight: inherit;
  line-height: inherit;
}

.login-link:hover {
  color: var(--accent-hover);
  background: none;
}

/* 主按钮：改前的内距同样是 UA 那 1px 6px，盒子高由 theme.css 的 height 定，
   原语的 min-height: 40px 与 0 16px 都不属于它；行高取回继承那一档（15×1.65）。 */
.login-submit {
  min-height: 0;
  padding: 1px 6px;
  line-height: inherit;
}

/* 主按钮按下那一下：theme.css 只写了 transform 与内阴影，底色不写就会被原语换成
   --accent-press（比原来的 --accent-hover 深一档）。 */
.login-submit:active {
  background: var(--accent-hover);
}

/* 弹窗右上角的 ×：28×28 的方块，改前是 display: block 加 UA 内距 —— 盒子大小不变，
   但 × 落点由这两格决定：原语的 flex 居中会把它从左上挪到正中。 */
.login-dialog__close {
  display: block;
  min-height: auto;
  padding: 1px 6px;
  font-weight: inherit;
  transition: none;
  gap: 0;
}

.login-dialog__close:hover {
  color: var(--text-1);
  background: var(--surface-3);
}

/* 「返回登录」今天没有按下态也没有过渡，原语给了 translateY(1px) 与 --accent-press。 */
.login-dialog__action {
  min-height: 0;
  line-height: inherit;
  transition: none;
}

.login-dialog__action:active {
  background: var(--accent);
  transform: none;
}

/* 侧栏那七枚（v-for 一处开标签）：theme.css 的脸是左对齐的菜单条目，原语默认居中。
   窄屏那几条 .reference-workbench .nav-item 响应式规则权重不低于这里，照旧把它们摆回居中。
   font-size 走继承（实测改前 16px）：条目里的字都在 .nav-label 自己身上，这一格不改也看不出来，
   但「看不出来」不是「不一样」，照实测复原。 */
.nav-item {
  font-size: inherit;
  justify-content: flex-start;
  font-weight: inherit;
  line-height: normal;
}

.nav-item:hover {
  color: var(--text);
}

/* 顶栏的 ⌄ 与提示条的 ×：改前都是无框无底的 block 小控件 + UA 内距 1px 6px。
   ⌄ 那一枚实测宽 20px＝8px 字形 + 12px 内距，原语把内距撤掉就缩成 8px；
   × 那一枚实测 19.81×18px。两枚的行高不同源：⌄ 改前就是 normal（继承链上没人写行高），
   × 由本文件上面那条 .auth-toast-close 的 line-height: 1 定（实测 16px）——
   所以 × 那一枚不许在这里写 line-height，写了会把它的盒子从 18px 撑成 22px。 */
.logout-link,
.auth-toast-close {
  display: block;
  min-height: auto;
  padding: 1px 6px;
  border: 0;
  border-radius: 0;
  font-weight: inherit;
  transition: none;
  gap: 0;
}

.logout-link {
  line-height: normal;
}

.logout-link:hover {
  background: transparent;
}

.auth-toast-close:hover {
  color: var(--muted);
  background: transparent;
}

</style>
