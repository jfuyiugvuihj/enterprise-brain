<script setup>
import { computed, nextTick, onMounted, onUnmounted, shallowRef } from 'vue'
import DocPanel from './components/DocPanel.vue'
import DataPanel from './components/DataPanel.vue'
import ChatPanel from './components/ChatPanel.vue'
import DashboardPanel from './components/DashboardPanel.vue'
import InsightPanel from './components/InsightPanel.vue'
import GraphPanel from './components/GraphPanel.vue'
import ApprovalPanel from './components/ApprovalPanel.vue'
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

// 401 与到期的收尾都从 lib/http.js 发出来：清会话、提示、回登录，不再用原生弹窗。
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

function goToLogin() {
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
    <main v-if="!isLoggedIn" class="auth-shell reference-login" data-testid="login-page">
      <div class="login-visual-backdrop" aria-hidden="true"></div>
      <div class="auth-atmosphere" aria-hidden="true">
        <span class="orbit orbit-one"></span>
        <span class="orbit orbit-two"></span>
        <span class="orbit orbit-three"></span>
        <svg class="globe-visual" viewBox="0 0 760 600" role="presentation">
          <defs>
            <radialGradient id="globe-fill" cx="38%" cy="30%" r="72%">
              <stop offset="0%" stop-color="#175a8d" stop-opacity=".72" />
              <stop offset="54%" stop-color="#082d54" stop-opacity=".68" />
              <stop offset="100%" stop-color="#031328" stop-opacity=".08" />
            </radialGradient>
            <radialGradient id="globe-halo" cx="42%" cy="42%" r="58%">
              <stop offset="0%" stop-color="#3cdfff" stop-opacity=".18" />
              <stop offset="68%" stop-color="#1d9bd7" stop-opacity=".05" />
              <stop offset="100%" stop-color="#1d9bd7" stop-opacity="0" />
            </radialGradient>
            <pattern id="globe-dots" width="15" height="15" patternUnits="userSpaceOnUse">
              <circle cx="2.2" cy="2.2" r="1.25" fill="#5cddff" fill-opacity=".78" />
              <circle cx="9.5" cy="8" r=".75" fill="#65d8ff" fill-opacity=".38" />
            </pattern>
            <clipPath id="globe-clip">
              <circle cx="372" cy="288" r="236" />
            </clipPath>
            <filter id="globe-glow" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="8" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <circle cx="372" cy="288" r="260" fill="url(#globe-halo)" />
          <circle cx="372" cy="288" r="236" fill="url(#globe-fill)" stroke="#2494cc" stroke-opacity=".5" />
          <g clip-path="url(#globe-clip)">
            <ellipse cx="372" cy="288" rx="222" ry="232" fill="none" stroke="#39c8f4" stroke-opacity=".20" />
            <ellipse cx="372" cy="288" rx="180" ry="232" fill="none" stroke="#39c8f4" stroke-opacity=".18" />
            <ellipse cx="372" cy="288" rx="104" ry="232" fill="none" stroke="#39c8f4" stroke-opacity=".14" />
            <ellipse cx="372" cy="288" rx="232" ry="76" fill="none" stroke="#39c8f4" stroke-opacity=".24" transform="rotate(-18 372 288)" />
            <ellipse cx="372" cy="288" rx="232" ry="142" fill="none" stroke="#39c8f4" stroke-opacity=".18" transform="rotate(-18 372 288)" />
            <path d="M145 270 C231 229 295 216 377 224 C466 233 533 273 603 337" fill="none" stroke="#50dcff" stroke-opacity=".32" />
            <path d="M160 360 C244 309 321 300 405 310 C485 319 540 348 582 394" fill="none" stroke="#50dcff" stroke-opacity=".20" />
            <path d="M252 130 C319 184 350 244 348 318 C346 382 324 435 288 470" fill="none" stroke="#50dcff" stroke-opacity=".19" />
            <path d="M456 124 C397 188 389 252 408 320 C426 379 456 428 492 456" fill="none" stroke="#50dcff" stroke-opacity=".16" />
            <rect x="126" y="62" width="500" height="460" fill="url(#globe-dots)" opacity=".88" />
          </g>
          <path d="M116 359 C238 198 405 115 629 153" fill="none" stroke="#39e1ff" stroke-opacity=".66" stroke-width="1.2" />
          <path d="M139 435 C278 352 441 337 630 396" fill="none" stroke="#39e1ff" stroke-opacity=".32" stroke-width="1" />
          <g filter="url(#globe-glow)">
            <circle cx="464" cy="201" r="4.5" fill="#5cf4ff" />
            <circle cx="536" cy="345" r="4" fill="#5cf4ff" />
            <circle cx="300" cy="283" r="3.5" fill="#5cf4ff" />
          </g>
          <circle cx="464" cy="201" r="11" fill="none" stroke="#5cf4ff" stroke-opacity=".18" />
          <circle cx="536" cy="345" r="11" fill="none" stroke="#5cf4ff" stroke-opacity=".15" />
        </svg>
        <span class="globe-node node-a"></span>
        <span class="globe-node node-b"></span>
        <span class="globe-node node-c"></span>
        <span class="floating-stat stat-data">
          <span class="stat-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="5.5" /><path d="m15 15 5 5" /></svg>
          </span>
          <span><b>数据</b><strong>1.2M+</strong></span>
        </span>
        <span class="floating-stat stat-insight">
          <span class="stat-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="m12 4 2 4 4 .6-3 3 1 4.4-4-2.2-4 2.2 1-4.4-3-3L10 8z" /></svg>
          </span>
          <span><b>洞察</b><strong>+42%</strong></span>
        </span>
        <span class="floating-stat stat-knowledge">
          <span class="stat-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M12 3a6.5 6.5 0 0 0-3.8 11.8V18h7.6v-3.2A6.5 6.5 0 0 0 12 3Z" /><path d="M9.5 21h5M10 18h4" /></svg>
          </span>
          <span><b>知识</b><strong>300K+</strong></span>
        </span>
      </div>

      <header class="auth-brandbar">
        <div class="brand-lockup">
          <span class="brand-mark reference-brand-mark" aria-hidden="true">
            <svg viewBox="0 0 48 48">
              <path d="m24 3 17 10v22L24 45 7 35V13z" />
              <path d="m24 12 9 5.3v10.4L24 33l-9-5.3V17.3z" />
              <path d="m24 19 4 2.3v4.4L24 28l-4-2.3v-4.4z" />
              <path d="m15 17.3 9 5.2 9-5.2M15 27.7l9-5.2 9 5.2" />
            </svg>
          </span>
          <span class="brand-copy">
            <strong>企业智脑</strong>
            <small>ENTERPRISE BRAIN</small>
          </span>
        </div>
        <p>数据 × 知识 × AI，驱动更聪明的企业</p>
      </header>

      <section class="auth-hero" aria-labelledby="auth-title" data-testid="login-hero">
        <h1 id="auth-title">私有化企业智能<br />分析平台</h1>
        <p class="auth-lead">让企业数据，成为生产力</p>
        <div class="auth-capabilities" aria-label="平台能力">
          <article>
            <span>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 19 6v5c0 4.6-2.8 8-7 10-4.2-2-7-5.4-7-10V6z" /></svg>
            </span>
            <strong>数据安全</strong>
          </article>
          <article>
            <span>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 8 4-8 4-8-4zM4 12l8 4 8-4M4 17l8 4 8-4" /></svg>
            </span>
            <strong>知识沉淀</strong>
          </article>
          <article>
            <span>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19V9M12 19V5M19 19v-7" /></svg>
            </span>
            <strong>智能分析</strong>
          </article>
        </div>
        <div class="auth-track">
          <span class="track-active"></span>
          <span></span>
          <span></span>
          <b>ENTERPRISE BRAIN</b>
        </div>
      </section>

      <section class="auth-panel" aria-labelledby="login-title" data-testid="login-panel">
        <h2 id="login-title">欢迎回来</h2>
        <p class="panel-lead">登录进入企业智能分析平台</p>
        <form class="login-form" data-testid="login-form" @submit.prevent="doLogin">
          <label class="field">
            <span class="field-icon">
              <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3.2" /><path d="M5.5 20c.6-3.6 2.7-5.3 6.5-5.3s5.9 1.7 6.5 5.3" /></svg>
            </span>
            <input v-model="loginUser" data-testid="login-username" placeholder="输入用户名" autocomplete="username" required />
          </label>
          <label class="field">
            <span class="field-icon">
              <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
            </span>
            <input v-model="loginPass" data-testid="login-password" :type="showPassword ? 'text' : 'password'" placeholder="输入密码" autocomplete="current-password" required />
            <button class="field-icon trailing field-action" type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 12s3.2-5 8.5-5 8.5 5 8.5 5-3.2 5-8.5 5-8.5-5-8.5-5Z" /><circle cx="12" cy="12" r="2" /></svg>
            </button>
          </label>
          <div v-if="loginError" class="notice error" data-testid="login-error" role="alert">{{ loginError }}</div>
          <button class="primary-btn login-submit" data-testid="login-submit" type="submit">
            <span>进入工作台</span>
            <span aria-hidden="true">→</span>
          </button>
          <div class="login-options">
            <label class="remember-me">
              <input v-model="rememberMe" data-testid="login-remember" type="checkbox" />
              <span>记住我</span>
            </label>
            <button data-testid="login-forgot" type="button" @click="openForgotPassword">忘记密码？</button>
          </div>
          <p class="login-hint">没有账号？联系管理员开通</p>
        </form>
      </section>
      <div v-if="showForgotDialog" class="forgot-dialog-backdrop" data-testid="login-forgot-dialog">
        <section class="forgot-dialog" role="dialog" aria-modal="true" aria-labelledby="forgot-title">
          <button class="forgot-dialog-close" data-testid="login-forgot-close" type="button" aria-label="关闭" @click="closeForgotPassword">×</button>
          <span class="forgot-dialog-kicker">ACCOUNT RECOVERY</span>
          <h2 id="forgot-title">忘记密码？</h2>
          <p>这是私有化部署系统，密码由企业管理员统一管理。</p>
          <label class="forgot-account">
            <span>账号</span>
            <input v-model="forgotUsername" autocomplete="username" placeholder="请输入需要找回的账号" />
          </label>
          <p class="forgot-dialog-note">请联系管理员在用户管理中重置该账号密码，重置后即可返回此页面登录。</p>
          <button class="primary-btn forgot-dialog-action" type="button" @click="closeForgotPassword">返回登录</button>
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
