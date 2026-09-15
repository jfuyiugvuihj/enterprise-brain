<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { http, errorDetail } from '../lib/http'
import DocumentPreviewModal from './DocumentPreviewModal.vue'

const docs = ref([])
// 本面板自己的失败提示；401 不在这里判，统一交给 lib/http.js 的响应拦截。
const notice = ref('')
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
const filteredDocs = computed(() => {
  if (!searchQuery.value) return docs.value
  const q = searchQuery.value.toLowerCase()
  return docs.value.filter(d => d.toLowerCase().includes(q))
})

async function loadDocs() {
  notice.value = ''
  try {
    const res = await http.get('/documents/catalog', {
      params: { _ts: Date.now() }
    })
    docs.value = (res.data.documents || [])
      .map(item => (typeof item === 'string' ? item : item.filename))
      .filter(Boolean)
  } catch (err) {
    console.error('文档列表加载失败', err)
    notice.value = errorDetail(err, '文档列表加载失败')
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
    notice.value = errorDetail(err, '文件下载失败')
  }
}

async function uploadFiles(files) {
  for (const file of files) {
    const item = reactive({
      name: file.name,
      status: 'uploading',
      phase: 'uploading',
      progress: 0,
      progressTimer: null,
      msg: '正在上传...'
    })
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
  await loadDocs()
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
    if (failed.length) notice.value = `有 ${failed.length} 个文档未能删除：${failed.join('、')}`
  } catch (err) {
    notice.value = errorDetail(err, '删除失败')
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
    <div v-if="notice" class="doc-notice" role="alert" data-testid="documents-notice">
      <span class="doc-notice-text">{{ notice }}</span>
      <button class="doc-notice-retry" type="button" @click="loadDocs">重新加载</button>
      <button class="doc-notice-close" type="button" aria-label="关闭提示" @click="notice = ''">×</button>
    </div>

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
      <div v-if="docs.length === 0" class="empty">
        <span class="empty-icon">📭</span>
        <p>知识库是空的</p>
        <p class="empty-sub">上传公司制度、手册或数据开始</p>
      </div>

      <div v-else-if="filteredDocs.length === 0" class="empty">
        <p>没有匹配 "{{ searchQuery }}" 的文档</p>
      </div>

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
  padding: 14px 0 10px; border-bottom: 1px solid rgba(0,0,0,0.05);
  font-size: 14px; gap: 8px;
}
.panel-hd-left { display: flex; align-items: center; gap: 6px; }
.badge { background: #e8ecf1; color: #606266; font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 10px; }

/* 管理员开关 */
.admin-toggle { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 11px; }
.admin-label { font-size: 13px; }
.admin-toggle input { display: none; }
.toggle-slider { width: 32px; height: 18px; border-radius: 10px; background: #d0d5dd; position: relative; transition: all 0.2s; }
.toggle-slider::after { content: ''; position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%; background: #fff; transition: all 0.2s; box-shadow: 0 1px 3px rgba(0,0,0,0.15); }
.admin-toggle input:checked + .toggle-slider { background: #f56c6c; }
.admin-toggle input:checked + .toggle-slider::after { left: 16px; }

/* ===== 搜索栏 ===== */
.search-bar {
  display: flex; align-items: center; gap: 6px;
  margin: 10px 0; padding: 7px 10px;
  background: rgba(0,0,0,0.03); border-radius: 8px;
}
.search-icon { font-size: 13px; opacity: 0.5; }
.search-input {
  flex: 1; border: none; background: none; outline: none;
  font-size: 12px; font-family: inherit; color: #303133;
}
.search-input::placeholder { color: #c0c4cc; }
.search-result { font-size: 11px; color: #909399; flex-shrink: 0; }

/* ===== 上传区 ===== */
.drop-zone {
  border: 1.5px dashed #d0d5dd; border-radius: 8px;
  transition: all 0.2s; background: rgba(255,255,255,0.4); margin-bottom: 8px;
}
.drop-zone.drag { border-color: #409eff; background: rgba(64,158,255,0.04); }
.upload-label {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 10px; cursor: pointer; font-size: 12px; color: #606266;
}
.upload-icon { font-size: 16px; }

/* ===== 上传队列 ===== */
.upload-item {
  display: flex; align-items: center; gap: 6px; padding: 6px 10px; margin-bottom: 4px;
  border-radius: 6px; font-size: 11px; background: #fff; border: 1px solid #ebeef5;
}
.upload-item.done { background: rgba(103,194,58,0.04); border-color: #b3e19d; }
.upload-item.error { background: rgba(245,108,108,0.04); border-color: #fab6b6; }
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
  color: #409eff;
  animation: upload-progress-spin 0.85s linear infinite;
  transform-origin: 50% 50%;
}
.upload-progress-track {
  height: 4px;
  margin-top: 5px;
  overflow: hidden;
  border-radius: 999px;
  background: #edf2f7;
}
.upload-progress-bar {
  height: 100%;
  min-width: 2px;
  border-radius: inherit;
  background: linear-gradient(90deg, #409eff, #67c23a);
  transition: width 0.2s ease;
}
.upload-progress-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 3px;
  color: #909399;
  font-size: 10px;
}
.up-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.up-msg { color: #67c23a; flex-shrink: 0; }
.upload-item.error .up-msg { color: #f56c6c; }
.clear-btn {
  display: block; width: 100%; padding: 4px; border: none; background: none;
  color: #909399; cursor: pointer; font-size: 11px; font-family: inherit;
  border-radius: 4px; margin-bottom: 4px;
}
.clear-btn:hover { color: #606266; background: #f0f2f5; }

/* ===== 批量操作栏 ===== */
.batch-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 8px; margin-bottom: 4px;
  background: rgba(245,108,108,0.04); border-radius: 6px;
}
.batch-toggle { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; color: #606266; }
.batch-toggle input { cursor: pointer; }
.batch-text { user-select: none; }
.batch-del {
  padding: 4px 12px; border: 1px solid #fab6b6; border-radius: 4px;
  background: #fff; color: #f56c6c; cursor: pointer; font-size: 12px;
  font-family: inherit; transition: all 0.15s;
}
.batch-del:hover { background: #f56c6c; color: #fff; }

/* ===== 文档列表 ===== */
.doc-list { flex: 1; overflow-y: auto; }
.doc-list::-webkit-scrollbar { width: 3px; }
.doc-list::-webkit-scrollbar-thumb { background: #d0d5dd; border-radius: 3px; }

.empty { text-align: center; padding: 30px 10px; font-size: 13px; color: #909399; }
.empty-icon { font-size: 30px; display: block; margin-bottom: 8px; opacity: 0.4; }
.empty-sub { font-size: 11px; color: #c0c4cc; margin-top: 4px; }

/* ===== 文档行 ===== */
.doc-row {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 8px; margin-bottom: 2px;
  border-radius: 6px; font-size: 12px;
  transition: all 0.15s; cursor: pointer;
  border: 1px solid transparent;
}
.doc-row:hover { background: rgba(64,158,255,0.03); }
.doc-row.selected { background: rgba(64,158,255,0.06); border-color: rgba(64,158,255,0.15); }

.check-box { font-size: 14px; flex-shrink: 0; color: #909399; }
.doc-row.selected .check-box { color: #409eff; }

.doc-icon { font-size: 13px; flex-shrink: 0; }
.doc-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #303133; }
.doc-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.doc-open-btn {
  border: 1px solid #d0d5dd;
  background: #fff;
  color: #606266;
  border-radius: 6px;
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
}
.doc-open-btn:hover { background: #f5f7fa; color: #409eff; }

.del-btn {
  background: none; border: none; color: #c0c4cc; cursor: pointer;
  padding: 3px 6px; border-radius: 4px; font-size: 12px; flex-shrink: 0;
  opacity: 0; transition: all 0.15s;
}
.doc-row:hover .del-btn { opacity: 1; }
.del-btn:hover { color: #f56c6c; background: rgba(245,108,108,0.08); }

/* ===== 底栏 ===== */
.panel-footer {
  display: flex; justify-content: space-between; padding: 8px 0 0;
  border-top: 1px solid rgba(0,0,0,0.04); font-size: 11px; color: #c0c4cc; flex-shrink: 0;
}
.footer-hint { color: #f56c6c; }

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
  background: rgba(255, 255, 255, .035);
  border-color: var(--line);
}

.badge {
  color: var(--cyan);
  background: rgba(53, 211, 200, .1);
}

.search-bar {
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .02);
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
.empty-sub,
.footer-hint,
.up-msg,
.panel-footer {
  color: var(--muted);
}

.drop-zone {
  border-color: rgba(53, 211, 200, .28);
  background: rgba(53, 211, 200, .035);
}

.drop-zone.drag {
  border-color: var(--cyan);
  background: rgba(53, 211, 200, .1);
}

.upload-label {
  color: var(--ink-soft);
}

.doc-row:hover,
.doc-row.selected {
  background: rgba(106, 140, 255, .1);
  border-color: rgba(106, 140, 255, .28);
}

.doc-open-btn,
.del-btn,
.batch-del,
.clear-btn {
  border-color: var(--line-strong);
  background: rgba(255, 255, 255, .04);
  color: var(--ink-soft);
}

.doc-open-btn:hover {
  border-color: var(--blue);
  color: #b5c4ff;
  background: rgba(106, 140, 255, .12);
}

.del-btn:hover,
.batch-del:hover {
  border-color: var(--red);
  color: #ffabb2;
  background: rgba(238, 109, 120, .12);
}

.empty {
  color: var(--ink-soft);
}

.panel-footer {
  border-top-color: var(--line);
}

.doc-notice {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-left: 3px solid var(--red);
  border-radius: var(--radius-sm);
  background: rgba(238, 109, 120, .08);
  color: var(--text);
  font-size: 13px;
}

.doc-notice-text {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}

.doc-notice-retry {
  padding: 3px 10px;
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text);
  font-size: 12px;
  cursor: pointer;
}

.doc-notice-close {
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}
</style>
