<script setup>
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import ChartViewer from './ChartViewer.vue'
import {
  abortStream,
  activeDataFilename,
  activeId,
  beginStream,
  consumeSseStream,
  endStream,
  ensureSession,
  flush,
  friendlyErrorText,
  genId,
  hitl,
  loadSessions,
  loading,
  messages,
  newSession,
  persist,
  rememberScroll,
  removeSession,
  restoreActive,
  scrollOffset,
  scrollTo,
  sessions,
  switchSession,
  syncActive,
} from '../lib/sessions'

const API = '/api/v1'

const input = ref('')
const chatEl = ref(null)
const sidebarOpen = ref(true)
const cancelPhase = ref('idle')
const streamNote = ref('')
const noteTone = ref('info')

// 会话与消息存在模块级 store 里：面板卸载或切走再回来都不会丢，生成中的流也不会断。
const sessionId = activeId

function authHeaders() {
  const token = localStorage.getItem('eb_token') || window._authToken
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function chatFetch(path, { headers, ...options } = {}) {
  return fetch(`${API}${path}`, { ...options, headers: { ...authHeaders(), ...(headers || {}) } })
}

function note(text, tone = 'info') {
  streamNote.value = text
  noteTone.value = tone
}

// ==================== 会话管理 ====================

function formatTime(ts) {
  const d = new Date(ts)
  const diff = Date.now() - d
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前'
  if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前'
  return (d.getMonth() + 1) + '/' + d.getDate()
}

async function deleteSession(id) {
  if (!confirm('删除此会话？')) return
  try {
    await removeSession(id)
  } catch (err) {
    note(`会话未能从服务端删除：${err.message || err}`, 'error')
  }
  await scrollBottom()
}

// ==================== 图表解析 ====================

// 图表以 ![标题](/api/v1/artifacts/<id>/content) 的形式出现在回答里，该地址需要携带 Bearer
// 头才能取回，所以匹配范围必须覆盖 artifact 相对地址；/static/ 保留给历史会话。
const CHART_IMAGE_PATTERN = /!\[([^\]]*)\]\(((?:\/(?:static|api\/v1)\/|v1\/artifacts\/|artifacts\/)[^)]+)\)/g

function parseCharts(content) {
  const charts = []
  if (!content) return charts
  const re = new RegExp(CHART_IMAGE_PATTERN.source, 'g')
  let m
  while ((m = re.exec(content)) !== null) {
    charts.push({ caption: m[1], src: m[2] })
  }
  return charts
}

function stripChartMarkers(content) {
  if (!content) return content
  return content.replace(new RegExp(CHART_IMAGE_PATTERN.source, 'g'), '')
}

// ==================== 聊天 ====================

function onChatAsk(e) {
  const detail = e.detail
  const query = typeof detail === 'string' ? detail : detail?.query
  if (!query) return
  activeDataFilename.value = typeof detail === 'string'
    ? activeDataFilename.value
    : detail?.filename || activeDataFilename.value
  input.value = query
  send(activeDataFilename.value)
}


function onScroll(e) {
  scrollOffset.value = e.target.scrollTop
}

async function scrollBottom() {
  await scrollTo(chatEl.value)
}

async function restoreScroll() {
  await nextTick()
  if (!chatEl.value) return
  if (scrollOffset.value > 0) chatEl.value.scrollTop = scrollOffset.value
  else await scrollTo(chatEl.value, 'auto')
}

onMounted(() => {
  window.addEventListener('chat-ask', onChatAsk)
  if (!sessions.value.length) {
    const storedActive = loadSessions()
    if (!activeId.value && storedActive) activeId.value = storedActive
  }
  if (!activeId.value) activeId.value = genId()
  // 只在 store 里还没有这份会话时回填，避免把正在写入的流替换掉。
  if (!messages.value.length) restoreActive(activeId.value)
  ensureSession()
  restoreScroll()
})

onUnmounted(() => {
  window.removeEventListener('chat-ask', onChatAsk)
  rememberScroll()
})

async function send(dataFilename = activeDataFilename.value) {
  const text = input.value.trim()
  if (!text || loading.value) return
  if (hitl.value) {
    note('请先处理待确认动作，再发起新一轮提问。', 'warn')
    return
  }
  if (dataFilename) activeDataFilename.value = dataFilename

  messages.value.push({ role: 'user', content: text, sources: null })
  input.value = ''
  messages.value.push({ role: 'assistant', content: '', steps: [], sources: null })
  const aiMsg = messages.value[messages.value.length - 1]
  note('')
  cancelPhase.value = 'idle'
  syncActive()

  const signal = beginStream()
  await scrollBottom()

  try {
    const response = await chatFetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal,
      body: JSON.stringify({
        message: text,
        session_id: activeId.value,
        data_filename: dataFilename,
      }),
    })

    const result = await consumeSseStream(response, aiMsg, {
      signal,
      onHitl: ({ pending, labels }) => {
        // 挂起期间仍可中断，所以先结束 loading 再展示待确认卡。
        hitl.value = { pending, labels, interrupted: false }
        endStream()
      },
      onText: flush,
      onBatch: flush,
    })

    if (!result.ok) {
      aiMsg.content = `[请求错误] ${result.error}`
      note(`本轮请求未成功（HTTP ${result.status}）。`, 'error')
    } else if (result.state.terminal === 'failed') {
      const text2 = friendlyErrorText(result.state)
      aiMsg.content = aiMsg.content ? `${aiMsg.content}\n${text2}` : text2
      note('本轮未能完成，服务已返回失败状态。', 'error')
    } else if (result.state.terminal === 'cancelled') {
      if (!aiMsg.content) aiMsg.content = '本轮生成已中断。'
    } else if (result.stopped !== 'hitl' && !aiMsg.content) {
      aiMsg.content = '本轮没有返回内容。'
    }
    syncActive()
    await scrollBottom()
  } catch (err) {
    if (err?.name !== 'AbortError' && !signal.aborted) {
      aiMsg.content = `[网络错误] ${err.message}`
      note('与服务器的连接中断，未能完成本轮回答。', 'error')
    }
    syncActive()
  } finally {
    endStream()
    persist()
  }
}

function requestCancel() {
  if (cancelPhase.value === 'confirm') return
  cancelPhase.value = 'confirm'
}

async function confirmCancel() {
  cancelPhase.value = 'idle'
  const awaitingHitl = !!hitl.value
  abortStream()
  endStream()

  let cancelled = null
  let ok = false
  let status = 0
  try {
    const response = await chatFetch(`/ask/${activeId.value}/cancel`, { method: 'POST' })
    status = response.status
    ok = response.ok
    if (ok) {
      let body = null
      try {
        body = await response.json()
      } catch (_) {
        body = null
      }
      cancelled = body?.cancelled
    }
  } catch (err) {
    note(`中断请求未能送达：${err.message || err}`, 'error')
  }

  if (ok && cancelled === true) {
    note('已中断本轮生成。', 'info')
    const last = messages.value[messages.value.length - 1]
    if (last?.role === 'assistant' && !last.content) {
      last.content = '本轮生成已中断，未产出结论。'
    }
  } else if (ok && cancelled === false) {
    // HTTP 200 只说明请求被受理，不代表真的停掉了什么。
    note('当前没有正在生成的内容。', 'warn')
  } else if (ok) {
    note('服务未返回中断结果，无法确认是否已停止。', 'warn')
  } else if (status) {
    note(`中断请求未被受理（HTTP ${status}）。`, 'error')
  }

  if (awaitingHitl) {
    // 显式保留待确认卡并标注已中断：中断不等于拒绝挂起动作（该语义仍待后端裁定）。
    hitl.value = { ...hitl.value, interrupted: true }
    note(`${streamNote.value} 待确认动作仍保留，请明确选择执行或取消。`, 'warn')
  }
  syncActive()
  persist()
}

async function approve(approved) {
  const pending = hitl.value
  if (!pending) return
  // 用户已经做出选择：待确认卡显式清除，不留残影。
  hitl.value = null
  note('')

  const aiMsg = messages.value[messages.value.length - 1]
  if (!aiMsg || aiMsg.role !== 'assistant') {
    loading.value = false
    syncActive()
    return
  }

  loading.value = true
  const signal = beginStream()
  try {
    const response = await chatFetch('/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal,
      body: JSON.stringify({ session_id: activeId.value, approved }),
    })

    const result = await consumeSseStream(response, aiMsg, {
      signal,
      onHitl: ({ pending: nextPending, labels }) => {
        hitl.value = { pending: nextPending, labels, interrupted: false }
        endStream()
      },
      onText: flush,
      onBatch: flush,
    })

    if (!result.ok) {
      aiMsg.content = aiMsg.content
        ? `${aiMsg.content}\n[请求错误] ${result.error}`
        : `[请求错误] ${result.error}`
      note(`确认结果未被受理（HTTP ${result.status}）。`, 'error')
    } else if (result.state.terminal === 'failed') {
      const failure = friendlyErrorText(result.state, '待确认动作执行失败')
      aiMsg.content = aiMsg.content ? `${aiMsg.content}\n${failure}` : failure
    } else if (result.state.terminal === 'cancelled') {
      if (!aiMsg.content) aiMsg.content = '待确认动作已中断。'
    } else if (!aiMsg.content) {
      aiMsg.content = approved ? '已确认，但本轮没有返回内容。' : '已取消该动作。'
    }
    syncActive()
    await scrollBottom()
  } catch (err) {
    if (err?.name !== 'AbortError' && !signal.aborted) {
      aiMsg.content = `${aiMsg.content}\n[网络错误] ${err.message}`
      note('与服务器的连接中断，待确认动作状态未知。', 'error')
    }
    syncActive()
  } finally {
    // 无论走到哪条分支都必须复位，否则界面会永远停在「处理中」。
    endStream()
    cancelPhase.value = 'idle'
    persist()
  }
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
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
  <div class="chat-layout" data-testid="chat-panel">
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
        <span class="model-status">🖥️ 本地模型</span>
      </div>

      <!-- 消息区 -->
      <div class="chat-messages" ref="chatEl" @scroll.passive="onScroll">
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
              <div :class="['hitl-card', { interrupted: hitl.interrupted }]">
                <div class="hitl-icon">⏸️</div>
                <div class="hitl-text">
                  <b>{{ hitl.interrupted ? '已中断，仍待确认' : '需要确认' }}</b>
                  <span v-if="hitl.interrupted" class="hitl-note">中断不等于拒绝该动作，请明确选择执行或取消。</span>
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
        <p v-if="streamNote" :class="['stream-note', noteTone]" role="status" data-testid="chat-note">{{ streamNote }}</p>
        <div class="input-wrapper">
        <textarea
            data-testid="chat-input"
            v-model="input"
            placeholder="输入您的问题… (Enter 发送, Shift+Enter 换行)"
            @keydown="handleKeydown"
            :disabled="loading || !!hitl"
            rows="1"
          />
          <div v-if="cancelPhase === 'confirm'" class="cancel-confirm" data-testid="chat-cancel-confirm">
            <span class="cancel-confirm-text">中断后本轮不再产出内容，也不会替你决定是否执行待确认动作。</span>
            <button class="send-pill danger" type="button" @click="confirmCancel">确认中断</button>
            <button class="send-pill ghost" type="button" @click="cancelPhase = 'idle'">返回</button>
          </div>
          <button v-else-if="loading || hitl" class="send-pill cancel-generation" type="button" data-testid="chat-cancel" @click="requestCancel">中断生成</button>
          <button v-else class="send-pill" data-testid="chat-send" @click="send()"
                  :disabled="!input.trim()">
            <svg v-if="!loading" width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M2 21l21-9L2 3v7l15 2-15 2v7z"/>
            </svg>
            <span v-else class="mini-spinner"></span>
          </button>
        </div>
        <p class="input-footer">
          本地模型推理 · 数据完全不出机器
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

.model-status {
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
  color: #606266;
  background: rgba(103,194,58,0.08);
  border: 1px solid rgba(103,194,58,0.2);
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

.chat-layout,
.chat-panel {
  color: var(--text);
}

.session-sidebar {
  background: rgba(13, 20, 34, .78);
  border-right-color: var(--line);
}

.sidebar-title,
.session-title,
.chat-title,
.step-label,
.msg-content :deep(b) {
  color: var(--text);
}

.sidebar-toggle,
.session-meta,
.session-empty,
.model-status,
.input-footer,
.step-time {
  color: var(--muted);
}

.sidebar-toggle:hover,
.session-item:hover {
  color: var(--cyan);
  background: rgba(53, 211, 200, .08);
}

.new-session-btn {
  border-color: rgba(53, 211, 200, .28);
  color: var(--ink-soft);
}

.new-session-btn:hover,
.session-item.active {
  border-color: rgba(53, 211, 200, .36);
  color: var(--cyan);
  background: rgba(53, 211, 200, .08);
}

.chat-topbar,
.chat-input-bar {
  background: rgba(13, 20, 34, .86);
  border-color: var(--line);
}

.model-status {
  background: rgba(101, 212, 154, .08);
  border-color: rgba(101, 212, 154, .22);
  color: var(--green);
}

.chat-messages {
  background:
    radial-gradient(circle at 60% 18%, rgba(106, 140, 255, .08), transparent 30rem),
    transparent;
}

.wc-sub,
.wc-hint {
  color: var(--muted);
}

.welcome-card h1 {
  background: linear-gradient(135deg, #f0f4fb, var(--cyan));
  -webkit-background-clip: text;
}

.wc-feat {
  background: rgba(17, 27, 44, .82);
  border-color: var(--line);
  color: var(--ink-soft);
}

.msg-bubble.assistant {
  background: rgba(17, 27, 44, .9);
  border-color: var(--line);
  box-shadow: 0 12px 30px rgba(0, 0, 0, .16);
}

.msg-avatar.ai {
  background: linear-gradient(135deg, rgba(53, 211, 200, .28), rgba(106, 140, 255, .28));
}

.msg-avatar.user {
  background: linear-gradient(135deg, var(--blue), var(--violet));
}

.step-card {
  border-color: var(--line);
  background: rgba(255, 255, 255, .035);
}

.step-card.running {
  border-color: rgba(106, 140, 255, .62);
  background: rgba(106, 140, 255, .1);
}

.step-card.done {
  border-color: rgba(101, 212, 154, .4);
  background: rgba(101, 212, 154, .08);
}

.msg-content :deep(code) {
  background: rgba(255, 255, 255, .08);
  color: #9de9df;
}

.msg-content :deep(blockquote) {
  color: var(--ink-soft);
  border-left-color: var(--cyan);
  background: rgba(53, 211, 200, .06);
}

.input-wrapper {
  background: #111b2c;
  border-color: var(--line-strong);
}

.input-wrapper textarea {
  color: var(--text);
}

.input-wrapper textarea::placeholder {
  color: var(--muted);
}

.send-pill {
  background: linear-gradient(135deg, var(--blue), var(--violet));
}

.send-pill:disabled {
  background: rgba(157, 178, 207, .2);
}

.hitl-card {
  background: #172238;
  border-color: var(--amber);
  box-shadow: 0 12px 34px rgba(228, 162, 74, .12);
}

.hitl-text {
  color: var(--ink-soft);
}

.hitl-text b {
  color: var(--text);
}

.hitl-btn.cancel {
  background: rgba(255, 255, 255, .04);
  color: var(--muted);
  border-color: var(--line);
}

/* 中断生成的二次确认与结果提示：文字按钮不能沿用 40x40 图标胶囊 */
.stream-note {
  margin: 0 0 6px;
  font-size: 12px;
  line-height: 1.5;
  color: #9eacc1;
}
.stream-note.warn { color: #e6a23c; }
.stream-note.error { color: #f56c6c; }
.hitl-card.interrupted { border-color: rgba(230, 162, 60, .55); }
.hitl-note { color: #e6a23c; font-size: 12px; }
.cancel-confirm { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cancel-confirm-text { font-size: 12px; color: #e6a23c; line-height: 1.5; }
.send-pill.cancel-generation,
.send-pill.danger,
.send-pill.ghost {
  width: auto;
  min-width: 40px;
  padding: 0 14px;
  font-size: 12px;
  font-family: inherit;
  white-space: nowrap;
}
.send-pill.cancel-generation { background: #f56c6c; }
.send-pill.danger { background: #f56c6c; }
.send-pill.danger:hover { background: #f78c8c; }
.send-pill.ghost {
  background: transparent;
  border: 1px solid rgba(157, 178, 207, .34);
  color: #9eacc1;
}
.send-pill.ghost:hover {
  background: rgba(157, 178, 207, .12);
  transform: none;
}
</style>
