<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { http, errorDetail } from '../lib/http'
import DocumentPreviewModal from './DocumentPreviewModal.vue'
import { UiButton, UiEmptyState, UiErrorState } from './ui'

const docs = ref([])
// 本面板自己的失败提示；401 不在这里判，统一交给 lib/http.js 的响应拦截。
const notice = ref('')
// notice 以前是一句话，外加一个不管发生什么都「重新加载列表」的按钮。
// 现在把「哪一种事没成」和「重载列表是不是真的补救动作」分开带，交给 UiErrorState 呈现。
const noticeTitle = ref('知识库这一步没有完成')
const noticeRetry = ref(false)

function raiseNotice(title, detail, retryable) {
  noticeTitle.value = title
  notice.value = detail
  noticeRetry.value = Boolean(retryable)
}

function dismissNotice() {
  notice.value = ''
  noticeRetry.value = false
}
const uploads = ref([])
const dragOver = ref(false)
const props = defineProps({
  userRole: {
    type: String,
    default: 'staff'
  }
})
const isAdmin = computed(() => props.userRole === 'admin')
const searchQuery = ref('')
const preview = reactive({
  open: false,
  filename: '',
  kind: 'text',
  text: '',
  blobUrl: '',
  loading: false,
  error: '',
  truncated: false
})

function startProgressTimer(item) {
  item.progress = Math.max(item.progress, 5)
  item.progressTimer = setInterval(() => {
    if (item.status !== 'uploading') {
      stopProgressTimer(item)
      return
    }
    const limit = item.phase === 'processing' ? 99 : 60
    if (item.progress < limit) {
      item.progress += Math.max(1, Math.ceil((limit - item.progress) * 0.12))
    }
  }, 400)
}

function stopProgressTimer(item) {
  if (!item.progressTimer) return
  clearInterval(item.progressTimer)
  item.progressTimer = null
}

function createUploadItem(file) {
  return reactive({
    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    name: file.name,
    status: 'uploading',
    phase: 'uploading',
    progress: 0,
    progressTimer: null,
    msg: '正在上传...'
  })
}

// 过滤后的文档列表
// 搜索无结果的那句话里带双引号，放进模板属性字面量会撞 Vue 的无引号属性限制，
// 所以在 script 里拼；文案与接线前逐字相同。
const noMatchTitle = computed(() => `没有匹配 "${searchQuery.value}" 的文档`)

const filteredDocs = computed(() => {
  if (!searchQuery.value) return docs.value
  const q = searchQuery.value.toLowerCase()
  return docs.value.filter(d => d.toLowerCase().includes(q))
})

async function loadDocs() {
  dismissNotice()
  try {
    const res = await http.get('/documents/catalog', {
      params: { _ts: Date.now() }
    })
    docs.value = (res.data.documents || [])
      .map(item => (typeof item === 'string' ? item : item.filename))
      .filter(Boolean)
  } catch (err) {
    console.error('文档列表加载失败', err)
    raiseNotice('文档列表没加载出来', errorDetail(err, '文档列表加载失败'), true)
  }
}

async function fetchDocumentBlob(filename, inline = false) {
  const res = await http.get(`/documents/${encodeURIComponent(filename)}/file`, {
    responseType: 'blob',
    params: { inline, _ts: Date.now() }
  })
  return res.data
}

async function openDocument(filename) {
  if (preview.blobUrl) {
    URL.revokeObjectURL(preview.blobUrl)
    preview.blobUrl = ''
  }
  preview.open = true
  preview.filename = filename
  preview.kind = 'text'
  preview.text = ''
  preview.loading = true
  preview.error = ''
  preview.truncated = false
  try {
    const res = await http.get(`/documents/${encodeURIComponent(filename)}/preview`, {
      params: { _ts: Date.now() }
    })
    preview.kind = res.data.kind || 'text'
    preview.text = res.data.text || ''
    preview.truncated = Boolean(res.data.truncated)
    if (preview.kind === 'pdf') {
      const blob = await fetchDocumentBlob(filename, true)
      preview.blobUrl = URL.createObjectURL(blob)
    }
  } catch (err) {
    preview.error = errorDetail(err, '文件预览失败')
  } finally {
    preview.loading = false
  }
}

function closeDocumentPreview() {
  preview.open = false
  if (preview.blobUrl) {
    URL.revokeObjectURL(preview.blobUrl)
    preview.blobUrl = ''
  }
}

async function downloadDocument(filename) {
  try {
    const blob = await fetchDocumentBlob(filename, false)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (err) {
    raiseNotice('文件没能下载', errorDetail(err, '文件下载失败'), false)
  }
}

async function uploadFilesParallel(files) {
  const tasks = files.map(file => uploadSingleFile(file))
  await Promise.allSettled(tasks)
  await loadDocs()
}

async function uploadSingleFile(file) {
  const item = createUploadItem(file)
  uploads.value.unshift(item)
  startProgressTimer(item)
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await http.post('/upload', form, {
      onUploadProgress: (event) => {
        if (event.total) {
          const uploaded = event.loaded / event.total
          item.progress = Math.max(item.progress, Math.min(70, Math.round(uploaded * 70)))
        }
        if (!event.total || event.loaded >= event.total) {
          item.phase = 'processing'
          item.msg = '正在解析并入库...'
        }
      }
    })
    stopProgressTimer(item)
    item.progress = Math.max(item.progress, 70)
    item.status = res.data.status === 'ok' ? 'done' : 'skipped'
    if (item.status === 'done') {
      item.progress = 100
      item.phase = 'done'
    }
    item.msg = res.data.message || '上传完成'
    await loadDocs()
  } catch (err) {
    stopProgressTimer(item)
    item.status = 'error'
    item.phase = 'error'
    item.msg = errorDetail(err, '上传失败')
  }
}

function onFileInput(e) {
  if (e.target.files.length) uploadFilesParallel([...e.target.files])
  e.target.value = ''
}

function onDrop(e) {
  dragOver.value = false
  if (e.dataTransfer?.files.length) uploadFilesParallel([...e.dataTransfer.files])
}

// 批量删除
const selectedFiles = ref(new Set())
const deleting = ref(false)

function toggleSelect(filename) {
  if (!isAdmin.value) return
  if (selectedFiles.value.has(filename)) {
    selectedFiles.value.delete(filename)
  } else {
    selectedFiles.value.add(filename)
  }
}

function toggleAll() {
  if (selectedFiles.value.size === filteredDocs.value.length) {
    selectedFiles.value.clear()
  } else {
    filteredDocs.value.forEach(d => selectedFiles.value.add(d))
  }
}

async function deleteDocuments(files) {
  if (!files.length || deleting.value) return
  if (!confirm(`确定删除选中的 ${files.length} 个文档？删除后无法恢复。`)) return
  deleting.value = true
  try {
    const results = await Promise.allSettled(
      files.map(filename => http.delete(`/documents/${encodeURIComponent(filename)}`))
    )
    const failed = results
      .filter(r => r.status === 'rejected')
      .map(r => errorDetail(r.reason, ''))
      .filter(Boolean)
    selectedFiles.value.clear()
    await loadDocs()
    if (failed.length) raiseNotice('部分文档没能删除', `有 ${failed.length} 个文档未能删除：${failed.join('、')}`, false)
  } catch (err) {
    raiseNotice('删除没有完成', errorDetail(err, '删除失败'), false)
  } finally {
    deleting.value = false
  }
}

async function deleteSelected() {
  await deleteDocuments([...selectedFiles.value])
}

async function deleteOne(filename) {
  await deleteDocuments([filename])
}

function fileIcon(name) {
  if (name.includes('案例')) return '📋'
  if (name.includes('MYO') || name.includes('MYBI') || name.includes('MYOps')) return '🔧'
  if (name.includes('制度') || name.includes('管理') || name.includes('规范')) return '📜'
  if (name.includes('报告') || name.includes('分析') || name.includes('经营')) return '📊'
  if (name.includes('会议') || name.includes('纪要')) return '📝'
  if (name.includes('法律') || name.includes('合规') || name.includes('安全')) return '🔒'
  if (name.includes('通知') || name.includes('放假') || name.includes('团建') || name.includes('年会')) return '📢'
  if (name.includes('教程') || name.includes('培训') || name.includes('指南') || name.includes('入职')) return '📖'
  return '📄'
}

function clearUploads() {
  uploads.value = uploads.value.filter(u => u.status === 'uploading')
}

onMounted(loadDocs)
onUnmounted(() => uploads.value.forEach(stopProgressTimer))
</script>

<template>
  <div class="doc-panel" data-testid="documents-panel">
    <!-- 面板标题 -->
    <div class="panel-hd">
      <div class="panel-hd-left">
        <span>📁</span>
        <strong>知识库</strong>
        <span class="badge">{{ docs.length }}</span>
      </div>

      <!-- 管理员开关 -->
    </div>

    <!-- 面板级失败提示：可重试，不用原生弹窗 -->
    <UiErrorState
      v-if="notice"
      :title="noticeTitle"
      :description="notice"
      :retryable="false"
      dense
    >
      <template #actions>
        <UiButton v-if="noticeRetry" variant="secondary" size="sm" label="重新加载" data-testid="documents-notice-retry" @click="loadDocs" />
        <UiButton variant="ghost" size="sm" label="关闭" data-testid="documents-notice-close" @click="dismissNotice" />
      </template>
    </UiErrorState>

    <!-- 搜索 -->
    <div class="search-bar">
      <span class="search-icon">🔍</span>
      <input v-model="searchQuery" placeholder="搜索文档..." class="search-input" />
      <span v-if="searchQuery" class="search-result">
        {{ filteredDocs.length }}/{{ docs.length }}
      </span>
    </div>

    <!-- 上传区（紧凑） -->
    <div class="drop-zone" data-testid="document-drop-zone" :class="{ drag: dragOver }"
         @dragover.prevent="dragOver = true"
         @dragleave.prevent="dragOver = false"
         @drop.prevent="onDrop">
      <label class="upload-label">
        <span class="upload-icon">☁️</span>
        <span>拖拽或点击上传 · 支持多选</span>
        <input data-testid="document-upload-input" type="file" hidden multiple accept=".pdf,.docx,.doc,.txt" @change="onFileInput" />
      </label>
    </div>

    <!-- 上传队列 -->
    <TransitionGroup name="queue">
      <div v-for="item in uploads" :key="item.id" :class="['upload-item', item.status]">
        <span v-if="item.status === 'uploading'" class="sr-only" role="status">正在解析入库</span>
        <svg
          v-if="item.status === 'uploading'"
          class="upload-progress-ring"
          aria-hidden="true"
          viewBox="0 0 24 24"
        >
          <circle
            cx="12"
            cy="12"
            r="9"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-dasharray="42 14"
          />
        </svg>
        <span v-else>{{ item.status === 'done' ? '✅' : item.status === 'skipped' ? '⏭️' : '❌' }}</span>
        <div class="up-body">
          <div class="up-line">
            <span class="up-name">{{ item.name }}</span>
            <span class="up-msg">{{ item.status === 'uploading' ? (item.phase === 'processing' ? '解析入库中...' : '上传中...') : item.msg }}</span>
          </div>
          <div
            v-if="item.status === 'uploading' || item.status === 'done'"
            class="upload-progress-track"
            role="progressbar"
            aria-label="文件上传进度"
            :aria-valuenow="item.progress"
            aria-valuemin="0"
            aria-valuemax="100"
          >
            <div class="upload-progress-bar" :style="{ width: `${item.progress}%` }"></div>
          </div>
          <div v-if="item.status === 'uploading' || item.status === 'done'" class="upload-progress-meta">
            <span>{{ item.phase === 'done' ? '上传完成' : item.phase === 'processing' ? '解析入库中...' : '上传中...' }}</span>
            <span>{{ item.progress }}%</span>
          </div>
        </div>
      </div>
    </TransitionGroup>

    <button v-if="uploads.some(u => u.status !== 'uploading')" class="clear-btn" @click="clearUploads">清除已完成</button>

    <!-- 批量操作栏（管理员可见） -->
    <div v-if="isAdmin && filteredDocs.length > 0" class="batch-bar">
      <label class="batch-toggle" @click.prevent="toggleAll">
        <input type="checkbox" :checked="selectedFiles.size === filteredDocs.length && filteredDocs.length > 0" />
        <span class="batch-text">
          {{ selectedFiles.size ? `已选 ${selectedFiles.size} 个` : '全选' }}
        </span>
      </label>
      <button v-if="selectedFiles.size" class="batch-del" @click="deleteSelected">
        🗑 删除选中
      </button>
    </div>

    <!-- 文档列表 -->
    <div class="doc-list" data-testid="document-list">
      <UiEmptyState v-if="docs.length === 0" title="知识库是空的" description="上传公司制度、手册或数据开始" />
      <UiEmptyState v-else-if="filteredDocs.length === 0" :title="noMatchTitle" dense />

      <TransitionGroup name="list" tag="div">
        <div v-for="doc in filteredDocs" :key="doc"
             :class="['doc-row', { selected: selectedFiles.has(doc) }]"
             @click="toggleSelect(doc)">
          <!-- 选择框（管理员） -->
          <span v-if="isAdmin" class="check-box">
            {{ selectedFiles.has(doc) ? '☑' : '☐' }}
          </span>

          <span class="doc-icon">{{ fileIcon(doc) }}</span>
          <span class="doc-name" :title="doc">{{ doc }}</span>
          <div class="doc-actions">
            <button class="doc-open-btn" @click.stop="openDocument(doc)">打开</button>
            <button class="doc-open-btn" @click.stop="downloadDocument(doc)">下载</button>

          <!-- 删除按钮（管理员） -->
            <button v-if="isAdmin" class="del-btn" @click.stop="deleteOne(doc)" title="删除">删除</button>
          </div>
        </div>
      </TransitionGroup>
    </div>

    <!-- 底栏统计 -->
    <div v-if="docs.length > 0" class="panel-footer">
      <span>共 {{ docs.length }} 个文档</span>
      <span v-if="isAdmin" class="footer-hint">点击选择 · 批量删除</span>
    </div>

    <DocumentPreviewModal
      :open="preview.open"
      :filename="preview.filename"
      :kind="preview.kind"
      :text="preview.text"
      :blob-url="preview.blobUrl"
      :loading="preview.loading"
      :error="preview.error"
      :truncated="preview.truncated"
      @close="closeDocumentPreview"
      @download="downloadDocument(preview.filename)"
    />
  </div>
</template>

<style scoped>
.doc-panel {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  padding: 0 14px 10px; user-select: none;
}

/* ===== 面板标题 ===== */
.panel-hd {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 0 10px; border-bottom: 1px solid color-mix(in srgb, var(--legacy-void) 5%, transparent);
  font-size: 14px; gap: 8px;
}
.panel-hd-left { display: flex; align-items: center; gap: 6px; }
.badge { color: var(--legacy-ink-mid); font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 10px; }

/* 管理员开关 */
.admin-toggle { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 11px; }
.admin-label { font-size: 13px; }
.admin-toggle input { display: none; }
.toggle-slider { width: 32px; height: 18px; border-radius: 10px; background: var(--legacy-line); position: relative; transition: all 0.2s; }
.toggle-slider::after { content: ''; position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%; background: var(--legacy-paper); transition: all 0.2s; box-shadow: 0 1px 3px color-mix(in srgb, var(--legacy-void) 15%, transparent); }
.admin-toggle input:checked + .toggle-slider { background: var(--legacy-ep-danger); }
.admin-toggle input:checked + .toggle-slider::after { left: 16px; }

/* ===== 搜索栏 ===== */
.search-bar {
  display: flex; align-items: center; gap: 6px;
  margin: 10px 0; padding: 7px 10px;
  background: color-mix(in srgb, var(--legacy-void) 3%, transparent); border-radius: 8px;
}
.search-icon { font-size: 13px; opacity: 0.5; }
.search-input {
  flex: 1; border: none; background: none; outline: none;
  font-size: 12px; font-family: inherit; color: var(--legacy-ink-strong);
}
.search-input::placeholder { color: var(--legacy-ink-faint); }
.search-result { font-size: 11px; color: var(--legacy-ink-soft); flex-shrink: 0; }

/* ===== 上传区 ===== */
.drop-zone {
  border: 1.5px dashed var(--legacy-line); border-radius: 8px;
 transition: all 0.2s; margin-bottom: 8px;
}
.drop-zone.drag { border-color: var(--legacy-ep-primary); }
.upload-label {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 10px; cursor: pointer; font-size: 12px; color: var(--legacy-ink-mid);
}
.upload-icon { font-size: 16px; }

/* ===== 上传队列 ===== */
.upload-item {
  display: flex; align-items: center; gap: 6px; padding: 6px 10px; margin-bottom: 4px;
  border-radius: 6px; font-size: 11px; background: var(--legacy-paper); border: 1px solid var(--legacy-line-pale);
}
.upload-item.done { background: color-mix(in srgb, var(--legacy-ep-success) 4%, transparent); border-color: var(--legacy-ep-success-line); }
.upload-item.error { background: color-mix(in srgb, var(--legacy-ep-danger) 4%, transparent); border-color: var(--legacy-ep-danger-line); }
.up-body { flex: 1; min-width: 0; }
.up-line { display: flex; align-items: center; gap: 8px; min-width: 0; }
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.upload-progress-ring {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: var(--legacy-ep-primary);
  animation: upload-progress-spin 0.85s linear infinite;
  transform-origin: 50% 50%;
}
.upload-progress-track {
  height: 4px;
  margin-top: 5px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--legacy-fill-mist);
}
.upload-progress-bar {
  height: 100%;
  min-width: 2px;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--legacy-ep-primary), var(--legacy-ep-success));
  transition: width 0.2s ease;
}
.upload-progress-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 3px;
  color: var(--legacy-ink-soft);
  font-size: 10px;
}
.up-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.up-msg { color: var(--legacy-ep-success); flex-shrink: 0; }
.upload-item.error .up-msg { color: var(--legacy-ep-danger); }
.clear-btn {
  display: block; width: 100%; padding: 4px; border: none; background: none;
  color: var(--legacy-ink-soft); cursor: pointer; font-size: 11px; font-family: inherit;
  border-radius: 4px; margin-bottom: 4px;
}
.clear-btn:hover { color: var(--legacy-ink-mid); background: var(--legacy-fill); }

/* ===== 批量操作栏 ===== */
.batch-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 8px; margin-bottom: 4px;
  background: color-mix(in srgb, var(--legacy-ep-danger) 4%, transparent); border-radius: 6px;
}
.batch-toggle { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; color: var(--legacy-ink-mid); }
.batch-toggle input { cursor: pointer; }
.batch-text { user-select: none; }
.batch-del {
  padding: 4px 12px; border: 1px solid var(--legacy-ep-danger-line); border-radius: 4px;
  background: var(--legacy-paper); color: var(--legacy-ep-danger); cursor: pointer; font-size: 12px;
  font-family: inherit; transition: all 0.15s;
}
.batch-del:hover { background: var(--legacy-ep-danger); color: var(--legacy-paper); }

/* ===== 文档列表 ===== */
.doc-list { flex: 1; overflow-y: auto; }
.doc-list::-webkit-scrollbar { width: 3px; }
.doc-list::-webkit-scrollbar-thumb { background: var(--legacy-line); border-radius: 3px; }

/* ===== 文档行 ===== */
.doc-row {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 8px; margin-bottom: 2px;
  border-radius: 6px; font-size: 12px;
  transition: all 0.15s; cursor: pointer;
  border: 1px solid transparent;
}
.doc-row:hover { background: color-mix(in srgb, var(--legacy-ep-primary) 3%, transparent); }
.doc-row.selected { background: color-mix(in srgb, var(--legacy-ep-primary) 6%, transparent); border-color: color-mix(in srgb, var(--legacy-ep-primary) 15%, transparent); }

.check-box { font-size: 14px; flex-shrink: 0; color: var(--legacy-ink-soft); }
.doc-row.selected .check-box { color: var(--legacy-ep-primary); }

.doc-icon { font-size: 13px; flex-shrink: 0; }
.doc-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--legacy-ink-strong); }
.doc-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.doc-open-btn {
  border: 1px solid var(--legacy-line);
  background: var(--legacy-paper);
  color: var(--legacy-ink-mid);
  border-radius: 6px;
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
}

.del-btn {
  background: none; border: none; color: var(--legacy-ink-faint); cursor: pointer;
  padding: 3px 6px; border-radius: 4px; font-size: 12px; flex-shrink: 0;
  opacity: 0; transition: all 0.15s;
}
.doc-row:hover .del-btn { opacity: 1; }
.del-btn:hover { color: var(--legacy-ep-danger); background: color-mix(in srgb, var(--legacy-ep-danger) 8%, transparent); }

/* ===== 底栏 ===== */
.panel-footer {
  display: flex; justify-content: space-between; padding: 8px 0 0;
  border-top: 1px solid color-mix(in srgb, var(--legacy-void) 4%, transparent); font-size: 11px; color: var(--legacy-ink-faint); flex-shrink: 0;
}
.footer-hint { color: var(--legacy-ep-danger); }

/* ===== 动画 ===== */
.list-enter-active { transition: all 0.2s ease; }
.list-leave-active { transition: all 0.15s ease; }
.list-enter-from { opacity: 0; transform: translateX(-8px); }
.list-leave-to { opacity: 0; transform: translateX(8px); }
.list-move { transition: transform 0.2s ease; }
.queue-enter-active { transition: all 0.2s ease; }
.queue-leave-active { transition: all 0.15s ease; }
.queue-enter-from { opacity: 0; transform: translateY(-6px); }
.queue-leave-to { opacity: 0; }

@keyframes upload-progress-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.doc-panel {
  color: var(--text);
  padding: 0 18px 18px;
}

.panel-hd {
  border-bottom-color: var(--line);
  color: var(--text);
}

.badge,
.search-bar,
.upload-item,
.doc-row,
.batch-bar {
  background: color-mix(in srgb, var(--legacy-paper) 3.5%, transparent);
  border-color: var(--line);
}

.badge {
  color: var(--cyan);
  background: color-mix(in srgb, var(--legacy-aqua-bright) 10%, transparent);
}

.search-bar {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--legacy-paper) 2%, transparent);
}

.search-input,
.doc-name,
.up-name,
.panel-hd strong {
  color: var(--text);
}

.search-input::placeholder,
.search-result,
.upload-hint,
.footer-hint,
.up-msg,
.panel-footer {
  color: var(--muted);
}

.drop-zone {
  border-color: color-mix(in srgb, var(--legacy-aqua-bright) 28%, transparent);
  background: color-mix(in srgb, var(--legacy-aqua-bright) 3.5%, transparent);
}

.drop-zone.drag {
  border-color: var(--cyan);
  background: color-mix(in srgb, var(--legacy-aqua-bright) 10%, transparent);
}

.upload-label {
  color: var(--ink-soft);
}

.doc-row:hover,
.doc-row.selected {
  background: color-mix(in srgb, var(--legacy-periwinkle-strong) 10%, transparent);
  border-color: color-mix(in srgb, var(--legacy-periwinkle-strong) 28%, transparent);
}

.doc-open-btn,
.del-btn,
.batch-del,
.clear-btn {
  border-color: var(--line-strong);
  background: color-mix(in srgb, var(--legacy-paper) 4%, transparent);
  color: var(--ink-soft);
}

.doc-open-btn:hover {
  border-color: var(--blue);
  color: var(--legacy-periwinkle-pale);
  background: color-mix(in srgb, var(--legacy-periwinkle-strong) 12%, transparent);
}

.del-btn:hover,
.batch-del:hover {
  border-color: var(--red);
  color: var(--legacy-coral-soft);
  background: color-mix(in srgb, var(--red) 12%, transparent);
}

.panel-footer {
  border-top-color: var(--line);
}
</style>
