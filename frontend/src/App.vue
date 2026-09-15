<script setup>
import { computed, nextTick, onMounted, onUnmounted, shallowRef } from 'vue'
import DocPanel from './components/DocPanel.vue'
import DataPanel from './components/DataPanel.vue'
import ChatPanel from './components/ChatPanel.vue'
import DashboardPanel from './components/DashboardPanel.vue'
import InsightPanel from './components/InsightPanel.vue'
import GraphPanel from './components/GraphPanel.vue'
import ApprovalPanel from './components/ApprovalPanel.vue'
import { resetSessions } from './lib/sessions'
import { loginStats } from './devFixtures/login-demo'
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

const activeTab = shallowRef('overview')
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

const navigation = [
  { id: 'overview', label: '总览', icon: 'M4 11.5 12 4l8 7.5v8.5a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z' },
  { id: 'docs', label: '文档', icon: 'M6 3h8l4 4v14H6zM14 3v5h5M9 13h6M9 17h6' },
  { id: 'data', label: '数据', icon: 'M5 5h14v14H5zM8 16V9M12 16V7M16 16v-4' },
  { id: 'insights', label: '洞察', icon: 'M4 17l5-5 4 3 7-8M17 7h3v3' },
  { id: 'graph', label: '图谱', icon: 'M7 7a3 3 0 1 0 0 .01M17 5a3 3 0 1 0 0 .01M17 17a3 3 0 1 0 0 .01M7 19a3 3 0 1 0 0 .01M9.5 8l5-1.5M9.5 17l5-1.5M7 10v6' },
  { id: 'approval', label: '审批', icon: 'M6 4h12v16H6zM9 9h6M9 13h6M9 17h3M5 12l3 3 6-7' },
  { id: 'chat', label: '对话', icon: 'M5 6h14v10H9l-4 4zM8 10h8M8 13h5' },
]

const workspaceMap = {
  overview: DashboardPanel,
  insights: InsightPanel,
  graph: GraphPanel,
  approval: ApprovalPanel,
}

const activeMeta = computed(() => navigation.find(item => item.id === activeTab.value) || navigation[0])
const roleLabel = computed(() => userRole.value === 'admin' ? '管理员' : '普通用户')

function handleAsk(query) {
  activeTab.value = 'chat'
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

function enterWorkspace() {
  isLoggedIn.value = true
  activeTab.value = 'overview'
  stopExpiryWatch?.()
  stopExpiryWatch = startExpiryWatch()
}

function showToast(message, tone = 'error', holdMs = 6000) {
  toast.value = { message, tone }
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = null }, holdMs)
}

// lib/http.js 只有一条失效收尾：真过期与 401 共用同一个 unauthorized 事件（令牌已经不再
// 可信，留着只会让界面继续拿它发请求）；expiring 只是「快到期」的提醒，只弹提示不动会话。
function onAuthEvent(event) {
  if (!event) return
  if (event.type === 'expiring') {
    showToast(event.message, 'warn', 12000)
    return
  }
  clearSession()
  goToLogin()
  loginError.value = event.message
  showToast(event.message, 'error', 6000)
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

// 手动登出与 401/过期都收口到这里，所以会话清理只写这一处；两个分支各写一遍迟早会漏。
function goToLogin() {
  resetSessions()
  stopExpiryWatch?.()
  stopExpiryWatch = null
  isLoggedIn.value = false
  username.value = ''
  userRole.value = 'staff'
  loginPass.value = ''
  activeTab.value = 'overview'
}

function doLogout() {
  // 退出清掉所有 eb_* 本地态（含会话缓存），只保留「记住我」的账号名。
  clearSession()
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
  goToLogin()
}

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

          <dl class="login-stats">
            <div v-for="item in loginStats" :key="item.label">
              <dt>{{ item.label }}</dt>
              <dd>{{ item.value }}</dd>
            </div>
          </dl>

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
                <button class="login-control__ghost" type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="3" /></svg>
                </button>
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
              <button class="login-link" type="button" data-testid="login-forgot" @click="openForgotPassword">忘记密码？</button>
            </div>

            <button class="login-submit" type="submit" data-testid="login-submit">
              进入工作台
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14" /><path d="m12 5 7 7-7 7" /></svg>
            </button>
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
          <button class="login-dialog__close" data-testid="login-forgot-close" type="button" aria-label="关闭" @click="closeForgotPassword">×</button>
          <h2 id="forgot-title">忘记密码？</h2>
          <p>这是私有化部署系统，密码由企业管理员统一管理。</p>
          <label class="login-dialog__account">
            <span>账号</span>
            <input v-model="forgotUsername" autocomplete="username" placeholder="请输入需要找回的账号" />
          </label>
          <p class="login-dialog__note">请联系管理员在用户管理中重置该账号密码，重置后即可返回此页面登录。</p>
          <button class="login-dialog__action" type="button" @click="closeForgotPassword">返回登录</button>
        </section>
      </div>
    </main>
    <div v-else class="workbench-shell reference-workbench" data-testid="workbench">
      <aside class="sidebar" aria-label="工作区导航" data-testid="sidebar">
        <div class="sidebar-brand">
          <span class="brand-mark"><span></span></span>
          <span>
            <strong>企业智脑</strong>
            <small>ENTERPRISE BRAIN</small>
          </span>
        </div>
        <nav class="nav-list" data-testid="navigation">
          <button
            v-for="item in navigation"
            :key="item.id"
            type="button"
            :class="['nav-item', { active: activeTab === item.id }]"
            :data-testid="`nav-${item.id}`"
            :aria-current="activeTab === item.id ? 'page' : undefined"
            :aria-label="item.label"
            @click="activeTab = item.id"
          >
            <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path :d="item.icon" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            <span class="nav-label">{{ item.label }}</span>
          </button>
        </nav>
      </aside>

      <main class="workspace" data-testid="workspace">
        <header class="workspace-head" data-testid="topbar">
          <h1>{{ activeMeta.label }}</h1>
          <div class="workspace-tools">
            <button type="button" aria-label="搜索">
              <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.8" cy="10.8" r="5.8" /><path d="m15.2 15.2 5 5" /></svg>
            </button>
            <button type="button" aria-label="通知" class="bell">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4" /></svg>
            </button>
            <span class="user-avatar">{{ username.slice(0, 1).toUpperCase() || 'A' }}</span>
            <span class="identity"><strong>{{ username }}</strong><span>{{ roleLabel }}</span></span>
            <button class="logout-link" type="button" @click="doLogout">⌄</button>
          </div>
        </header>

        <section class="panel-slot" data-testid="panel-slot">
          <component
            :is="workspaceMap[activeTab]"
            v-if="workspaceMap[activeTab]"
            @goto="activeTab = $event"
          />
          <DocPanel v-else-if="activeTab === 'docs'" :user-role="userRole" />
          <DataPanel v-else-if="activeTab === 'data'" @ask="handleAsk" />
          <!-- 对话面板常驻（v-show 而非 v-if）：切走再回来会话、滚动与进行中的回答流都不丢 -->
          <ChatPanel v-show="activeTab === 'chat'" />
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
        <button
          type="button"
          class="auth-toast-close"
          aria-label="关闭提示"
          @click="toast = null"
        >
          ×
        </button>
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
</style>
