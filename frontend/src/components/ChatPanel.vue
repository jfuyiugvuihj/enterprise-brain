<script setup>
import { ref, nextTick, onMounted, onUnmounted, watch } from 'vue'
import ChartViewer from './ChartViewer.vue'

const API = '/api/v1'
const STORAGE_KEY = 'eb_sessions_v2'
const messages = ref([])
const input = ref('')
const loading = ref(false)
const modelSource = ref('deepseek')
const chatEl = ref(null)
const sessionId = ref('')
const sessions = ref([])  // [{id, title, msgCount, updatedAt, messages: [...]}]
const sidebarOpen = ref(true)
const hitl = ref(null)  // { pending: [...], labels: [...] } — HITL 待确认

// ==================== 会话管理 ====================

function genId() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 8) }

function persist() {
  const data = { activeId: sessionId.value, sessions: sessions.value }
  // 消息体较大，存到单独的 key
  const slim = sessions.value.map(s => {
    const { messages: _, ...rest } = s
    localStorage.setItem('eb_msg_' + s.id, JSON.stringify(s.messages))
    return rest
  })
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ activeId: sessionId.value, sessions: slim }))
}

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const data = JSON.parse(raw)
    // 恢复消息
    const full = (data.sessions || []).map(s => {
      let msgs = []
      try {
        const mr = localStorage.getItem('eb_msg_' + s.id)
        if (mr) msgs = JSON.parse(mr)
      } catch (_) {}
      return { ...s, messages: msgs }
    })
    sessions.value = full
    return data.activeId || ''
  } catch (_) { return '' }
}

function syncSession() {
  // 将当前 messages 同步到 sessions 数组中
  const sid = sessionId.value
  if (!sid) return
  const exists = sessions.value.find(s => s.id === sid)
  const userMsgs = messages.value.filter(m => m.role === 'user')
  const title = userMsgs.length ? (userMsgs[0].content || '').slice(0, 30) : ''
  const entry = {
    id: sid,
    title,
    msgCount: userMsgs.length,
    updatedAt: Date.now(),
    messages: [...messages.value]
  }
  if (exists) {
    Object.assign(exists, entry)
  } else {
    sessions.value.unshift(entry)
  }
  persist()
}

function newSession() {
  syncSession()
  const sid = genId()
  sessionId.value = sid
  messages.value = []
  // 总是创建新条目
  sessions.value.unshift({
    id: sid,
    title: '',
    msgCount: 0,
    updatedAt: Date.now(),
    messages: []
  })
  persist()
}

function switchSession(id) {
  if (id === sessionId.value) return
  syncSession()
  sessionId.value = id
  const s = sessions.value.find(s => s.id === id)
  messages.value = s ? [...s.messages] : []
  persist()
  nextTick(() => scrollBottom())
}

function deleteSession(id) {
  if (!confirm('删除此会话？')) return
  sessions.value = sessions.value.filter(s => s.id !== id)
  try { localStorage.removeItem('eb_msg_' + id) } catch (_) {}
  if (id === sessionId.value) {
    if (sessions.value.length) {
      sessionId.value = sessions.value[0].id
      messages.value = [...sessions.value[0].messages]
    } else {
      const sid = genId()
      sessionId.value = sid
      messages.value = []
      sessions.value = [{ id: sid, title: '', msgCount: 0, updatedAt: Date.now(), messages: [] }]
    }
  }
  persist()
  fetch(`${API}/sessions/${id}`, { method: 'DELETE' }).catch(() => {})
}

function formatTime(ts) {
  const d = new Date(ts)
  const now = new Date()
  const diff = now - d
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前'
  if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前'
  return (d.getMonth() + 1) + '/' + d.getDate()
}

// ==================== 图表解析 ====================

function parseCharts(content) {
  const charts = []
  const re = /!\[([^\]]*)\]\((\/static\/[^)]+)\)/g
  let m
  while ((m = re.exec(content)) !== null) {
    charts.push({ caption: m[1], src: m[2] })
  }
  return charts
}

function stripChartMarkers(content) {
  return content.replace(/!\[([^\]]*)\]\((\/static\/[^)]+)\)/g, '')
}

// ==================== 聊天 ====================

function onChatAsk(e) {
  input.value = e.detail
  send()
}

onMounted(() => {
  window.addEventListener('chat-ask', onChatAsk)
  const activeId = load()
  if (activeId) {
    sessionId.value = activeId
    const s = sessions.value.find(s => s.id === activeId)
    if (s) messages.value = [...s.messages]
  } else {
    sessionId.value = genId()
    messages.value = []
  }
  // 确保至少有一个当前会话条目
  if (!sessions.value.find(s => s.id === sessionId.value)) {
    sessions.value.unshift({ id: sessionId.value, title: '', msgCount: 0, updatedAt: Date.now(), messages: [] })
  }
})
onUnmounted(() => window.removeEventListener('chat-ask', onChatAsk))

// 消息变化时自动持久化
watch(messages, () => syncSession(), { deep: true })

async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return

  messages.value.push({ role: 'user', content: text, sources: null })
  input.value = ''

  messages.value.push({ role: 'assistant', content: '', steps: [], sources: null })
  const aiIdx = messages.value.length - 1
  const aiMsg = messages.value[aiIdx]
  loading.value = true

  await scrollBottom()

  try {
    const response = await fetch(`${API}/ask`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(window._authToken ? { Authorization: `Bearer ${window._authToken}` } : {}),
      },
      body: JSON.stringify({ message: text, session_id: sessionId.value })
    })

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''

      for (const part of parts) {
        if (!part.trim()) continue
        let eventType = ''
        let dataStr = ''

        for (const line of part.split('\n')) {
          if (line.startsWith('event: ')) eventType = line.slice(7).trim()
          else if (line.startsWith('data: ')) dataStr = line.slice(6)
        }

        if (!dataStr) continue
        try {
          const payload = JSON.parse(dataStr)

          if (eventType === 'step') {
            const existing = aiMsg.steps.find(s => s.tool === payload.tool && s.status === 'running')
            if (existing && payload.status === 'done') {
              existing.status = 'done'
              existing.elapsed = payload.elapsed
            } else if (payload.status === 'running') {
              if (aiMsg.content) aiMsg._correcting = true
              aiMsg.steps.push({
                tool: payload.tool,
                label: payload.label,
                status: 'running',
                elapsed: null
              })
            }
          } else if (eventType === 'hitl') {
            // 人工确认中断：暂停，等用户确认后再继续
            hitl.value = { pending: payload.pending, labels: payload.labels }
            loading.value = false
            break  // 跳出 SSE 读取，等待 /approve 调用
          } else if (eventType === 'text') {
            if (aiMsg._correcting) {
              aiMsg.content = payload.content
              aiMsg._correcting = false
            } else {
              aiMsg.content += payload.content
            }
          } else if (eventType === 'error') {
            aiMsg.content = `[错误] ${payload.content}`
          }
        } catch (_) {}
      }

      await scrollBottom()
    }
  } catch (err) {
    aiMsg.content = `[网络错误] ${err.message}`
  } finally {
    loading.value = false
  }
}

async function approve(approved) {
  // 用户确认/取消 HITL 操作
  const confirmMsg = hitl.value
  hitl.value = null
  loading.value = true

  const aiMsg = messages.value[messages.value.length - 1]
  if (!aiMsg || aiMsg.role !== 'assistant') return

  try {
    const response = await fetch(`${API}/approve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(window._authToken ? { Authorization: `Bearer ${window._authToken}` } : {}),
      },
      body: JSON.stringify({ session_id: sessionId.value, approved })
    })

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''

      for (const part of parts) {
        if (!part.trim()) continue
        let eventType = ''
        let dataStr = ''

        for (const line of part.split('\n')) {
          if (line.startsWith('event: ')) eventType = line.slice(7).trim()
          else if (line.startsWith('data: ')) dataStr = line.slice(6)
        }

        if (!dataStr) continue
        try {
          const payload = JSON.parse(dataStr)
          if (eventType === 'text') {
            aiMsg.content += payload.content
          } else if (eventType === 'error') {
            aiMsg.content += `\n[错误] ${payload.content}`
          }
        } catch (_) {}
      }
      await scrollBottom()
    }
  } catch (err) {
    aiMsg.content += `\n[网络错误] ${err.message}`
  } finally {
    loading.value = false
  }
}

async function scrollBottom() {
  await nextTick()
  if (chatEl.value) {
    chatEl.value.scrollTo({ top: chatEl.value.scrollHeight, behavior: 'smooth' })
  }
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

function toggleModel() {
  modelSource.value = modelSource.value === 'deepseek' ? 'ollama' : 'deepseek'
}

// ==================== Markdown ====================

function renderMd(raw) {
  if (!raw) return ''
  let html = raw
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const l = lang || ''
    return `<div class="code-block"><div class="code-lang">${l}</div><pre><code>${code.trim()}</code></pre></div>`
  })

  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="md-link">$1</a>')
  html = html.replace(/^&gt;\s?(.*)$/gm, '<blockquote>$1</blockquote>')
  html = html.replace(/^[-*]\s+(.*)$/gm, '<li>$1</li>')
  html = html.replace(/\n\n/g, '</p><p>')
  html = html.replace(/\n/g, '<br>')
  html = `<p>${html}</p>`

  return html
}
</script>

<template>
  <div class="chat-layout">
    <!-- ===== 会话侧边栏 ===== -->
    <aside :class="['session-sidebar', { collapsed: !sidebarOpen }]">
      <div class="sidebar-hd">
        <span v-if="sidebarOpen" class="sidebar-title">💬 会话</span>
        <button class="sidebar-toggle" @click="sidebarOpen = !sidebarOpen" :title="sidebarOpen ? '收起' : '展开'">
          {{ sidebarOpen ? '◀' : '▶' }}
        </button>
      </div>

      <template v-if="sidebarOpen">
        <button class="new-session-btn" @click="newSession">＋ 新建会话</button>

        <div class="session-list">
          <div v-if="sessions.length === 0" class="session-empty">暂无历史会话</div>
          <div v-for="s in sessions" :key="s.id"
               :class="['session-item', { active: s.id === sessionId }]"
               @click="switchSession(s.id)">
            <div class="session-info">
              <div class="session-title">{{ s.title || '新会话' }}</div>
              <div class="session-meta">
                <span>{{ s.msgCount || 0 }} 问</span>
                <span>·</span>
                <span>{{ formatTime(s.updatedAt) }}</span>
              </div>
            </div>
            <button class="session-del" @click.stop="deleteSession(s.id)" title="删除">✕</button>
          </div>
        </div>
      </template>
    </aside>

    <!-- ===== 主聊天区 ===== -->
    <div class="chat-panel">
      <!-- 顶栏 -->
      <div class="chat-topbar">
        <div class="chat-topbar-left">
          <span class="chat-dot online"></span>
          <span class="chat-title">智能问答</span>
        </div>
        <button class="model-chip" @click="toggleModel"
                :title="modelSource === 'deepseek' ? '切换本地 Ollama' : '切换 DeepSeek 云端'">
          {{ modelSource === 'deepseek' ? '☁️ DeepSeek' : '🖥️ Ollama 本地' }}
        </button>
      </div>

      <!-- 消息区 -->
      <div class="chat-messages" ref="chatEl">
        <div v-if="messages.length === 0" class="welcome-screen">
          <div class="welcome-glow"></div>
          <div class="welcome-card">
            <div class="wc-icon">🧠</div>
            <h1>企业智脑</h1>
            <p class="wc-sub">您的私有 AI 知识助手</p>
            <div class="wc-features">
              <div class="wc-feat">
                <span class="wc-feat-icon">📄</span>
                <span>上传文档 · 智能问答</span>
              </div>
              <div class="wc-feat">
                <span class="wc-feat-icon">📊</span>
                <span>数据分析 · 图表生成</span>
              </div>
              <div class="wc-feat">
                <span class="wc-feat-icon">🔒</span>
                <span>数据不出机器 · 安全私有</span>
              </div>
            </div>
            <p class="wc-hint">在左侧上传文档，然后开始提问</p>
          </div>
        </div>

        <TransitionGroup name="msg">
          <div v-for="(msg, i) in messages" :key="i"
               :class="['msg-row', msg.role]">
            <div v-if="msg.role === 'assistant'" class="msg-avatar ai">
              {{ loading && i === messages.length - 1 && !msg.content ? '⏳' : '🤖' }}
            </div>

            <div class="msg-bubble-wrap">
              <div :class="['msg-bubble', msg.role]">
                <!-- 进度卡片 -->
                <div v-if="msg.steps && msg.steps.length" class="steps-bar">
                  <div v-for="(st, si) in msg.steps" :key="si"
                       :class="['step-card', st.status]">
                    <span class="step-icon">{{ st.status === 'running' ? '🔄' : '✅' }}</span>
                    <span class="step-label">{{ st.label }}</span>
                    <span v-if="st.elapsed !== null" class="step-time">{{ st.elapsed }}s</span>
                    <span v-else class="step-time pulse">…</span>
                  </div>
                </div>

                <div v-if="msg.role === 'assistant' && loading && i === messages.length - 1 && !msg.content && !msg.steps?.length"
                     class="typing-dots">
                  <span></span><span></span><span></span>
                </div>
                <div v-else-if="msg.role === 'assistant'"
                     class="msg-content" v-html="renderMd(stripChartMarkers(msg.content))" />
                <div v-else class="msg-content">{{ msg.content }}</div>

                <ChartViewer v-for="(ch, ci) in parseCharts(msg.content)"
                             :key="ci" :src="ch.src" :caption="ch.caption" />
              </div>
            </div>

            <!-- HITL 确认弹窗 -->
            <div v-if="hitl && i === messages.length - 1" class="hitl-bar">
              <div class="hitl-card">
                <div class="hitl-icon">⏸️</div>
                <div class="hitl-text">
                  <b>需要确认</b>
                  <span v-for="(lbl, li) in hitl.labels" :key="li">{{ lbl }}</span>
                </div>
                <div class="hitl-actions">
                  <button class="hitl-btn approve" @click="approve(true)">✅ 确认执行</button>
                  <button class="hitl-btn cancel" @click="approve(false)">✕ 取消</button>
                </div>
              </div>
            </div>

            <div v-if="msg.role === 'user'" class="msg-avatar user">👤</div>
          </div>
        </TransitionGroup>
      </div>

      <!-- 输入区 -->
      <div class="chat-input-bar">
        <div class="input-wrapper">
          <textarea
            v-model="input"
            placeholder="输入您的问题… (Enter 发送, Shift+Enter 换行)"
            @keydown="handleKeydown"
            :disabled="loading"
            rows="1"
          />
          <button class="send-pill" @click="send"
                  :disabled="loading || !input.trim()">
            <svg v-if="!loading" width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M2 21l21-9L2 3v7l15 2-15 2v7z"/>
            </svg>
            <span v-else class="mini-spinner"></span>
          </button>
        </div>
        <p class="input-footer">
          {{ modelSource === 'deepseek' ? 'DeepSeek 云端推理 · 数据仅用于本次回答' : 'Ollama 本地模型 · 数据完全不出机器' }}
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ===== 整体布局 ===== */
.chat-layout {
  flex: 1;
  display: flex;
  height: 100%;
  overflow: hidden;
}

/* ===== 会话侧边栏 ===== */
.session-sidebar {
  width: 200px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(0,0,0,0.06);
  background: rgba(248,249,252,0.9);
  transition: width 0.25s ease;
  overflow: hidden;
}
.session-sidebar.collapsed {
  width: 32px;
}
.session-sidebar.collapsed .sidebar-hd {
  flex-direction: column;
  padding: 10px 0;
}

.sidebar-hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 12px 8px;
  flex-shrink: 0;
}
/* 收起时：toggle 居中 */
.session-sidebar.collapsed .sidebar-hd {
  justify-content: center;
  padding: 10px 4px;
}
.sidebar-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
}
.sidebar-toggle {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 11px;
  color: #909399;
  padding: 4px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}
.sidebar-toggle:hover { color: #409eff; background: rgba(64,158,255,0.08); }

.new-session-btn {
  margin: 4px 8px 8px;
  padding: 7px 0;
  border: 1px dashed #d0d5dd;
  border-radius: 8px;
  background: none;
  cursor: pointer;
  font-size: 12px;
  color: #606266;
  font-family: inherit;
  transition: all 0.2s;
  white-space: nowrap;
}
.new-session-btn:hover {
  border-color: #409eff;
  color: #409eff;
  background: rgba(64,158,255,0.04);
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 6px;
}

.session-list::-webkit-scrollbar { width: 3px; }
.session-list::-webkit-scrollbar-thumb { background: #d0d5dd; border-radius: 3px; }

.session-empty {
  text-align: center;
  padding: 20px 8px;
  font-size: 12px;
  color: #c0c4cc;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  margin-bottom: 2px;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
}
.session-item:hover { background: rgba(64,158,255,0.04); }
.session-item.active {
  background: rgba(64,158,255,0.08);
  border-color: rgba(64,158,255,0.15);
}

.session-info {
  flex: 1;
  min-width: 0;
}
.session-title {
  font-size: 12px;
  font-weight: 500;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.session-meta {
  font-size: 10px;
  color: #c0c4cc;
  margin-top: 2px;
}

.session-del {
  background: none;
  border: none;
  color: #c0c4cc;
  cursor: pointer;
  font-size: 11px;
  padding: 3px 5px;
  border-radius: 4px;
  flex-shrink: 0;
  opacity: 0;
  transition: all 0.15s;
}
.session-item:hover .session-del { opacity: 1; }
.session-del:hover { color: #f56c6c; background: rgba(245,108,108,0.08); }

/* ===== 聊天面板 ===== */
.chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* ===== 顶栏 ===== */
.chat-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 56px;
  background: rgba(255,255,255,0.7);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid rgba(0,0,0,0.04);
  flex-shrink: 0;
}
.chat-topbar-left { display: flex; align-items: center; gap: 8px; }
.chat-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #67c23a;
  box-shadow: 0 0 6px rgba(103,194,58,0.4);
}
.chat-title { font-size: 15px; font-weight: 600; }

.model-chip {
  padding: 6px 16px;
  border: 1px solid #dcdfe6;
  border-radius: 20px;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  color: #606266;
  transition: all 0.2s;
  font-family: inherit;
}
.model-chip:hover {
  border-color: #409eff;
  color: #409eff;
  box-shadow: 0 2px 8px rgba(64,158,255,0.12);
}

/* ===== 消息区 ===== */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
.chat-messages::-webkit-scrollbar { width: 5px; }
.chat-messages::-webkit-scrollbar-thumb { background: #d0d5dd; border-radius: 5px; }

/* ===== 欢迎页 ===== */
.welcome-screen {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  position: relative;
}
.welcome-glow {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(64,158,255,0.08) 0%, transparent 70%);
  pointer-events: none;
}
.welcome-card { text-align: center; position: relative; }
.wc-icon {
  font-size: 52px;
  margin-bottom: 12px;
  animation: float 3s ease-in-out infinite;
}
@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}
.welcome-card h1 {
  font-size: 28px; font-weight: 700;
  background: linear-gradient(135deg, #1a1a2e, #409eff);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin-bottom: 6px;
}
.wc-sub { font-size: 14px; color: #909399; margin-bottom: 32px; }
.wc-features { display: flex; flex-direction: column; gap: 12px; margin-bottom: 28px; }
.wc-feat {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 20px;
  background: rgba(255,255,255,0.8);
  border-radius: 10px;
  border: 1px solid rgba(0,0,0,0.04);
  font-size: 14px; color: #303133;
}
.wc-feat-icon { font-size: 18px; }
.wc-hint { font-size: 13px; color: #c0c4cc; }

/* ===== 消息行 ===== */
.msg-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 24px;
  max-width: 85%;
}
.msg-row.assistant { align-self: flex-start; }
.msg-row.user { margin-left: auto; flex-direction: row-reverse; }

.msg-avatar {
  width: 36px; height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}
.msg-avatar.ai { background: linear-gradient(135deg, #e8f4fd, #d4e9ff); }
.msg-avatar.user { background: linear-gradient(135deg, #409eff, #66b1ff); }

.msg-bubble-wrap { flex: 1; min-width: 0; }
.msg-bubble {
  padding: 12px 18px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
}
.msg-bubble.assistant {
  background: #fff;
  border: 1px solid rgba(0,0,0,0.05);
  border-top-left-radius: 4px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.03);
}
.msg-bubble.user {
  background: linear-gradient(135deg, #409eff, #3a8ee6);
  color: #fff;
  border-top-right-radius: 4px;
}

/* ===== 打字动画 ===== */
.typing-dots { display: flex; gap: 4px; padding: 4px 0; }
.typing-dots span {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #909399;
  animation: dotBounce 1.4s infinite both;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes dotBounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.3; }
  40% { transform: scale(1); opacity: 1; }
}

/* ===== 进度卡片 ===== */
.steps-bar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.step-card {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 12px;
  border: 1px solid #e4e7ed;
  background: #fafbfc;
  transition: all 0.3s ease;
}
.step-card.running {
  border-color: #409eff;
  background: rgba(64,158,255,0.04);
  box-shadow: 0 0 0 2px rgba(64,158,255,0.12);
  animation: stepPulse 2s ease-in-out infinite;
}
.step-card.done {
  border-color: #b3e19d;
  background: rgba(103,194,58,0.04);
}
@keyframes stepPulse {
  0%, 100% { box-shadow: 0 0 0 2px rgba(64,158,255,0.12); }
  50% { box-shadow: 0 0 0 4px rgba(64,158,255,0.06); }
}
.step-icon { font-size: 13px; flex-shrink: 0; }
.step-card.running .step-icon { animation: spin 1.5s linear infinite; }
.step-label { color: #303133; font-weight: 500; white-space: nowrap; }
.step-time { font-size: 11px; color: #909399; flex-shrink: 0; }
.step-time.pulse { color: #409eff; animation: dotPulse 0.8s ease-in-out infinite; }
@keyframes dotPulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}

/* ===== Markdown 样式 ===== */
.msg-content :deep(.code-block) {
  background: #1a1a2e;
  border-radius: 8px;
  margin: 10px 0;
  overflow: hidden;
}
.msg-content :deep(.code-lang) {
  padding: 6px 14px;
  font-size: 11px;
  color: #8899aa;
  text-transform: uppercase;
  letter-spacing: 1px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.msg-content :deep(.code-block pre) { padding: 14px; overflow-x: auto; margin: 0; }
.msg-content :deep(.code-block code) {
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 13px; color: #e0e0e0; line-height: 1.6;
}
.msg-content :deep(code) {
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  background: rgba(0,0,0,0.05);
  padding: 2px 6px;
  border-radius: 4px;
  color: #e43;
}
.msg-content :deep(blockquote) {
  border-left: 3px solid #409eff;
  padding: 8px 14px;
  margin: 8px 0;
  background: rgba(64,158,255,0.04);
  border-radius: 0 6px 6px 0;
  color: #606266;
}
.msg-content :deep(li) { margin: 4px 0 4px 20px; }
.msg-content :deep(b) { font-weight: 600; color: #1a1a2e; }

/* ===== 输入区 ===== */
.chat-input-bar {
  padding: 16px 24px 12px;
  background: rgba(255,255,255,0.7);
  backdrop-filter: blur(8px);
  border-top: 1px solid rgba(0,0,0,0.04);
  flex-shrink: 0;
}
.input-wrapper {
  display: flex;
  gap: 10px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 14px;
  padding: 8px 8px 8px 18px;
  transition: all 0.2s;
  align-items: flex-end;
}
.input-wrapper:focus-within {
  border-color: #409eff;
  box-shadow: 0 0 0 3px rgba(64,158,255,0.08);
}
.input-wrapper textarea {
  flex: 1;
  border: none;
  outline: none;
  font-size: 14px;
  line-height: 1.5;
  resize: none;
  padding: 6px 0;
  font-family: inherit;
  max-height: 120px;
}
.send-pill {
  width: 40px; height: 40px;
  border: none;
  background: linear-gradient(135deg, #409eff, #3a8ee6);
  color: #fff;
  border-radius: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}
.send-pill:hover {
  background: linear-gradient(135deg, #66b1ff, #409eff);
  box-shadow: 0 4px 12px rgba(64,158,255,0.3);
  transform: scale(1.05);
}
.send-pill:disabled {
  background: #c8d6e5;
  box-shadow: none;
  cursor: not-allowed;
  transform: none;
}
.mini-spinner {
  width: 14px; height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
.input-footer {
  text-align: center;
  font-size: 11px;
  color: #c0c4cc;
  margin-top: 8px;
}

/* ===== HITL 确认栏 ===== */
.hitl-bar {
  display: flex;
  justify-content: flex-start;
  padding: 0 0 12px 46px;
}
.hitl-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 20px;
  background: #fff;
  border: 2px solid #e6a23c;
  border-radius: 14px;
  box-shadow: 0 4px 20px rgba(230,162,60,0.15);
  animation: hitlIn 0.3s ease;
}
@keyframes hitlIn {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}
.hitl-icon { font-size: 28px; flex-shrink: 0; }
.hitl-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  color: #606266;
}
.hitl-text b { color: #303133; font-size: 14px; }
.hitl-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.hitl-btn {
  padding: 8px 18px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  transition: all 0.2s;
}
.hitl-btn.approve {
  background: linear-gradient(135deg, #67c23a, #5daf34);
  color: #fff;
}
.hitl-btn.approve:hover { box-shadow: 0 4px 12px rgba(103,194,58,0.3); transform: translateY(-1px); }
.hitl-btn.cancel {
  background: #f5f7fa;
  color: #909399;
  border: 1px solid #e4e7ed;
}
.hitl-btn.cancel:hover { background: #fef0f0; color: #f56c6c; border-color: #f56c6c; }

/* ===== 消息动画 ===== */
.msg-enter-active { transition: all 0.35s ease; }
.msg-enter-from { opacity: 0; transform: translateY(12px); }
.msg-move { transition: transform 0.3s ease; }
</style>
