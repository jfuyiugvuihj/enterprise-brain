<script setup>
import { ref, onMounted } from 'vue'
import DocPanel from './components/DocPanel.vue'
import DataPanel from './components/DataPanel.vue'
import ChatPanel from './components/ChatPanel.vue'

const sidebarOpen = ref(true)
const activeTab = ref('docs')
const isLoggedIn = ref(false)
const username = ref('')
const loginUser = ref('')
const loginPass = ref('')
const loginError = ref('')
const isRegistering = ref(false)

function handleAsk(q) {
  window.dispatchEvent(new CustomEvent('chat-ask', { detail: q }))
}

// ===== 登录 =====
const TOKEN_KEY = 'eb_token'
const USER_KEY = 'eb_user'

function checkAuth() {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    isLoggedIn.value = true
    username.value = localStorage.getItem(USER_KEY) || ''
    // 设置 axios/fetch 默认头
    window._authToken = token
  }
}

async function doLogin() {
  loginError.value = ''
  try {
    const resp = await fetch('/api/v1/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: loginUser.value, password: loginPass.value })
    })
    if (!resp.ok) {
      const err = await resp.json()
      loginError.value = err.detail || '登录失败'
      return
    }
    const data = await resp.json()
    localStorage.setItem(TOKEN_KEY, data.token)
    localStorage.setItem(USER_KEY, data.username)
    window._authToken = data.token
    isLoggedIn.value = true
    username.value = data.username
  } catch (e) {
    loginError.value = '网络错误: ' + e.message
  }
}

function doLogout() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  delete window._authToken
  isLoggedIn.value = false
  username.value = ''
}

function onLoginKeydown(e) {
  if (e.key === 'Enter') doLogin()
}

async function doRegister() {
  loginError.value = ''
  if (!loginUser.value || !loginPass.value) { loginError.value = '请填写用户名和密码'; return }
  if (loginPass.value.length < 6) { loginError.value = '密码至少 6 位'; return }
  try {
    const resp = await fetch('/api/v1/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: loginUser.value, password: loginPass.value })
    })
    if (!resp.ok) {
      const err = await resp.json()
      loginError.value = err.detail || '注册失败'
      return
    }
    // 注册成功，自动登录
    await doLogin()
  } catch (e) {
    loginError.value = '网络错误: ' + e.message
  }
}

onMounted(checkAuth)
</script>

<template>
  <!-- ===== 登录页 ===== -->
  <div v-if="!isLoggedIn" class="login-screen">
    <div class="login-card">
      <div class="login-icon">🧠</div>
      <h1>企业智脑</h1>
      <p class="login-sub">私有化 AI 智能分析平台</p>

      <div class="login-form">
        <input v-model="loginUser" placeholder="用户名" class="login-input"
               @keydown="onLoginKeydown" autocomplete="username" />
        <input v-model="loginPass" type="password" placeholder="密码" class="login-input"
               @keydown="onLoginKeydown" autocomplete="current-password" />
        <div v-if="loginError" class="login-error">{{ loginError }}</div>
        <button v-if="!isRegistering" class="login-btn" @click="doLogin">登 录</button>
        <button v-else class="login-btn" @click="doRegister">注 册</button>
      </div>
      <p class="login-switch">
        <template v-if="!isRegistering">
          没有账号？<a href="#" @click.prevent="isRegistering = true; loginError = ''">注册一个</a>
        </template>
        <template v-else>
          已有账号？<a href="#" @click.prevent="isRegistering = false; loginError = ''">返回登录</a>
        </template>
      </p>

    </div>
  </div>

  <!-- ===== 主应用 ===== -->
  <div v-else class="app-shell">
    <!-- 顶栏 -->
    <header class="topbar">
      <div class="topbar-brand" @click="sidebarOpen = !sidebarOpen">
        <span class="brand-icon">🧠</span>
        <span class="brand-text">企业智脑</span>
        <span class="brand-sub">Enterprise Brain</span>
      </div>
      <div class="topbar-right">
        <span class="topbar-user">👤 {{ username }}</span>
        <button class="logout-btn" @click="doLogout">退出</button>
        <span class="status-dot online"></span>
        <span class="status-label">系统就绪</span>
      </div>
    </header>

    <div class="app-body">
      <aside class="sidebar" :class="{ collapsed: !sidebarOpen }">
        <div v-show="sidebarOpen" class="sidebar-tabs">
          <button :class="['tab-btn', { active: activeTab === 'docs' }]"
                  @click="activeTab = 'docs'">📁 知识库</button>
          <button :class="['tab-btn', { active: activeTab === 'data' }]"
                  @click="activeTab = 'data'">📊 数据分析</button>
        </div>
        <DocPanel v-show="sidebarOpen && activeTab === 'docs'" />
        <DataPanel v-show="sidebarOpen && activeTab === 'data'" @ask="handleAsk" />
      </aside>

      <main class="main-area">
        <ChatPanel ref="chatPanel" />
      </main>
    </div>
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body, #app {
  height: 100%;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #f0f2f5;
  color: #1a1a2e;
}

/* ===== 外壳 ===== */
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
}

/* ===== 顶栏 ===== */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 56px;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  color: #fff;
  box-shadow: 0 2px 12px rgba(0,0,0,0.15);
  z-index: 100;
  flex-shrink: 0;
}

.topbar-brand {
  display: flex;
  align-items: baseline;
  gap: 10px;
  cursor: pointer;
  user-select: none;
}

.brand-icon { font-size: 22px; }
.brand-text { font-size: 18px; font-weight: 700; letter-spacing: 1px; }
.brand-sub {
  font-size: 11px; font-weight: 400; opacity: 0.55;
  letter-spacing: 2px; text-transform: uppercase;
}

.topbar-right {
  display: flex; align-items: center; gap: 12px;
  font-size: 13px; opacity: 0.85;
}
.topbar-user { color: rgba(255,255,255,0.9); }
.logout-btn {
  padding: 4px 12px;
  border: 1px solid rgba(255,255,255,0.3);
  border-radius: 4px;
  background: none;
  color: rgba(255,255,255,0.7);
  cursor: pointer;
  font-size: 11px;
  font-family: inherit;
}
.logout-btn:hover { border-color: #f56c6c; color: #f56c6c; }

.topbar-status {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; opacity: 0.85;
}

.status-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #67c23a; box-shadow: 0 0 8px rgba(103,194,58,0.5);
  animation: pulse-dot 2s infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ===== 主体 ===== */
.app-body {
  flex: 1; display: flex; overflow: hidden;
}

/* ===== 侧边栏 ===== */
.sidebar {
  width: 340px;
  background: rgba(255,255,255,0.85);
  backdrop-filter: blur(12px);
  border-right: 1px solid rgba(0,0,0,0.06);
  display: flex; flex-direction: column;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden; flex-shrink: 0;
  box-shadow: 2px 0 20px rgba(0,0,0,0.04);
}

.sidebar.collapsed {
  width: 0; border-right: none; box-shadow: none;
}

/* ===== Tab 切换 ===== */
.sidebar-tabs {
  display: flex; gap: 4px; padding: 12px 14px 0;
}

.tab-btn {
  flex: 1; padding: 8px 0; border: none; border-radius: 8px;
  background: transparent; cursor: pointer; font-size: 13px;
  font-weight: 500; color: #909399; font-family: inherit;
  transition: all 0.2s;
}

.tab-btn:hover { color: #303133; background: rgba(0,0,0,0.03); }

.tab-btn.active {
  color: #fff; background: linear-gradient(135deg, #409eff, #3a8ee6);
  box-shadow: 0 2px 8px rgba(64,158,255,0.25);
}

/* ===== 主区域 ===== */
.main-area {
  flex: 1; display: flex; flex-direction: column; min-width: 0;
  background: radial-gradient(ellipse at top, rgba(64,158,255,0.03) 0%, transparent 60%);
}

/* ===== 登录页 ===== */
.login-screen {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
}
.login-card {
  text-align: center;
  background: rgba(255,255,255,0.06);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 20px;
  padding: 48px 40px;
  width: 380px;
  max-width: 90vw;
}
.login-icon { font-size: 52px; margin-bottom: 12px; }
.login-card h1 { color: #fff; font-size: 26px; margin-bottom: 4px; }
.login-sub { color: rgba(255,255,255,0.45); font-size: 13px; margin-bottom: 32px; }

.login-form { display: flex; flex-direction: column; gap: 14px; }
.login-input {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 10px;
  background: rgba(255,255,255,0.06);
  color: #fff;
  font-size: 14px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.2s;
}
.login-input::placeholder { color: rgba(255,255,255,0.3); }
.login-input:focus { border-color: #409eff; }

.login-error {
  color: #f56c6c;
  font-size: 12px;
  text-align: center;
  padding: 6px;
  background: rgba(245,108,108,0.1);
  border-radius: 6px;
}

.login-btn {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #409eff, #3a8ee6);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s;
}
.login-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(64,158,255,0.3); }

.login-hint {
  margin-top: 20px;
  color: rgba(255,255,255,0.25);
  font-size: 11px;
}

.login-switch {
  margin-top: 16px;
  text-align: center;
  font-size: 13px;
  color: rgba(255,255,255,0.4);
}
.login-switch a {
  color: #409eff;
  text-decoration: none;
  cursor: pointer;
}
.login-switch a:hover { text-decoration: underline; }
</style>
