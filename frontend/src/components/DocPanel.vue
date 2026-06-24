<script setup>
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'

// axios 拦截器：自动带上 JWT
axios.interceptors.request.use(config => {
  const token = window._authToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

const API = '/api/v1'
const docs = ref([])
const uploads = ref([])
const dragOver = ref(false)
const isAdmin = ref(false)
const searchQuery = ref('')

// 过滤后的文档列表
const filteredDocs = computed(() => {
  if (!searchQuery.value) return docs.value
  const q = searchQuery.value.toLowerCase()
  return docs.value.filter(d => d.toLowerCase().includes(q))
})

async function loadDocs() {
  try {
    const res = await axios.get(`${API}/documents`)
    docs.value = res.data.documents || []
  } catch (e) {
    console.error('加载失败', e)
  }
}

async function uploadFiles(files) {
  for (const file of files) {
    const item = { name: file.name, status: 'uploading', msg: '解析中...' }
    uploads.value.unshift(item)
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await axios.post(`${API}/upload`, form)
      item.status = res.data.status === 'ok' ? 'done' : 'skipped'
      item.msg = res.data.message
    } catch (err) {
      item.status = 'error'
      item.msg = `失败: ${err.message}`
    }
  }
  await loadDocs()
}

function onFileInput(e) {
  if (e.target.files.length) uploadFiles([...e.target.files])
  e.target.value = ''
}

function onDrop(e) {
  dragOver.value = false
  if (e.dataTransfer?.files.length) uploadFiles([...e.dataTransfer.files])
}

// 批量删除
const selectedFiles = ref(new Set())

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

async function deleteSelected() {
  const files = [...selectedFiles.value]
  if (!files.length) return
  if (!confirm(`确定删除 ${files.length} 个文件？`)) return
  for (const f of files) {
    try {
      await axios.delete(`${API}/documents/${encodeURIComponent(f)}`)
    } catch (e) { console.error('删除失败', e) }
  }
  selectedFiles.value.clear()
  await loadDocs()
}

async function deleteOne(filename) {
  if (!confirm(`删除 "${filename}"？`)) return
  try {
    await axios.delete(`${API}/documents/${encodeURIComponent(filename)}`)
    await loadDocs()
  } catch (err) { console.error('删除失败', err) }
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
</script>

<template>
  <div class="doc-panel">
    <!-- 面板标题 -->
    <div class="panel-hd">
      <div class="panel-hd-left">
        <span>📁</span>
        <strong>知识库</strong>
        <span class="badge">{{ docs.length }}</span>
      </div>

      <!-- 管理员开关 -->
      <label class="admin-toggle" title="切换管理员模式">
        <span class="admin-label">🔑</span>
        <input type="checkbox" v-model="isAdmin" />
        <span class="toggle-slider"></span>
      </label>
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
    <div class="drop-zone" :class="{ drag: dragOver }"
         @dragover.prevent="dragOver = true"
         @dragleave.prevent="dragOver = false"
         @drop.prevent="onDrop">
      <label class="upload-label">
        <span class="upload-icon">☁️</span>
        <span>拖拽或点击上传 · 支持多选</span>
        <input type="file" hidden multiple accept=".pdf,.docx,.doc,.txt" @change="onFileInput" />
      </label>
    </div>

    <!-- 上传队列 -->
    <TransitionGroup name="queue">
      <div v-for="item in uploads" :key="item.name" :class="['upload-item', item.status]">
        <span>{{ item.status === 'uploading' ? '⏳' : item.status === 'done' ? '✅' : item.status === 'skipped' ? '⏭️' : '❌' }}</span>
        <span class="up-name">{{ item.name }}</span>
        <span class="up-msg">{{ item.msg }}</span>
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
    <div class="doc-list">
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

          <!-- 删除按钮（管理员） -->
          <button v-if="isAdmin" class="del-btn" @click.stop="deleteOne(doc)" title="删除">✕</button>
        </div>
      </TransitionGroup>
    </div>

    <!-- 底栏统计 -->
    <div v-if="docs.length > 0" class="panel-footer">
      <span>共 {{ docs.length }} 个文档</span>
      <span v-if="isAdmin" class="footer-hint">点击选择 · 批量删除</span>
    </div>
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
</style>
