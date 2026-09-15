<script setup>
import { onMounted, ref } from 'vue'
import { errorDetail, http, isPermissionDenied } from '../lib/http'
import { UiEmptyState, UiErrorState } from './ui'
import DocumentPreviewModal from './DocumentPreviewModal.vue'

const profile = ref(null)
const dataFile = ref('')
const tableColumns = ref([])
const tableRows = ref([])
const tableTruncated = ref(false)
const previewOpen = ref(false)
const previewLoading = ref(false)
const previewError = ref('')
const previewDenied = ref(false)
const uploading = ref(false)
const dataFiles = ref([])
const filesLoading = ref(false)
const filesError = ref('')
// 无权限 / 坏了 / 空列表是三张脸（R1c），文件列表与预览各自判一次。
const filesDenied = ref(false)
const selectingFile = ref(false)

const quickActions = [
  { label: '📊 各列对比', query: '对比各列数据的最大最小值' },
  { label: '📈 趋势分析', query: '分析数据的变化趋势' },
  { label: '📋 生成报告', query: '根据这份数据生成一份分析报告' },
  { label: '🔍 找出最高', query: '找出每列的最高值和最低值' },
  { label: '📉 异常检测', query: '检测数据中是否存在异常值' },
  { label: '💡 总结摘要', query: '用一段话总结这份数据的关键信息' },
]

const emit = defineEmits(['ask'])

async function uploadExcel(e) {
  const file = e.target.files?.[0]
  if (!file) return

  const form = new FormData()
  form.append('file', file)

  uploading.value = true
  try {
    const res = await http.post('/upload-excel', form)
    applyDataPreview(res.data)
    await loadDataFiles(file.name)
  } catch (err) {
        filesError.value = errorDetail(err, '数据上传失败')
  } finally {
    uploading.value = false
    e.target.value = ''
  }
}

function applyDataPreview(data) {
  dataFile.value = data.filename || ''
  profile.value = data.profile || null
  tableColumns.value = data.columns || []
  tableRows.value = data.rows || []
  tableTruncated.value = Boolean(data.truncated)
}

async function loadDataFiles(preferredFilename = '') {
  filesLoading.value = true
  filesError.value = ''
  try {
    const res = await http.get('/data-files', { params: { _ts: Date.now() } })
    dataFiles.value = res.data.files || []
    const currentExists = dataFiles.value.some(file => file.filename === dataFile.value)
    const preferredExists = dataFiles.value.some(file => file.filename === preferredFilename)
    const nextFilename = preferredExists
      ? preferredFilename
      : currentExists
        ? dataFile.value
        : dataFiles.value[0]?.filename
    if (nextFilename && (nextFilename !== dataFile.value || !profile.value)) {
      await selectDataFile(nextFilename)
    }
  } catch (err) {
        filesDenied.value = isPermissionDenied(err)
        filesError.value = filesDenied.value
          ? '当前账号没有查看数据文件列表的权限，请联系管理员开通。'
          : errorDetail(err, '数据文件列表加载失败')
  } finally {
    filesLoading.value = false
  }
}

async function selectDataFile(filename) {
  dataFile.value = filename
  selectingFile.value = true
  previewError.value = ''
  previewDenied.value = false
  try {
    const res = await http.get(
      `/data-files/${encodeURIComponent(filename)}/preview`,
      { params: { _ts: Date.now() } }
    )
    applyDataPreview(res.data)
  } catch (err) {
        // 别人的数据集会走到这里：data.py:89-90 用 policy 的 reason code 回 403。
        previewDenied.value = isPermissionDenied(err)
        previewError.value = previewDenied.value
          ? '这份数据文件不属于你的可见范围，当前账号打不开它。'
          : errorDetail(err, '数据文件预览失败')
  } finally {
    selectingFile.value = false
  }
}

async function openDataFile() {
  if (!dataFile.value) return
  previewOpen.value = true
  previewLoading.value = true
  try {
    await selectDataFile(dataFile.value)
  } catch (err) {
        previewError.value = errorDetail(err, '数据预览失败')
  } finally {
    previewLoading.value = false
  }
}

async function downloadDataFile() {
  if (!dataFile.value) return
  try {
    const res = await http.get(
      `/data-files/${encodeURIComponent(dataFile.value)}/file`,
      { responseType: 'blob', params: { inline: false, _ts: Date.now() } }
    )
    const url = URL.createObjectURL(res.data)
    const link = document.createElement('a')
    link.href = url
    link.download = dataFile.value
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (err) {
        previewError.value = errorDetail(err, '数据文件下载失败')
  }
}

function closeDataPreview() {
  previewOpen.value = false
  previewError.value = ''
}

function askQuestion(q) {
  if (!dataFile.value) return
  emit('ask', { query: q, filename: dataFile.value })
}

function typeIcon(dtype) {
  if (!dtype) return '❓'
  if (dtype.includes('int') || dtype.includes('float')) return '🔢'
  if (dtype.includes('object')) return '📝'
  if (dtype.includes('datetime')) return '📅'
  return '📦'
}

function missingClass(pct) {
  if (pct === 0) return 'ok'
  if (pct < 10) return 'warn'
  return 'bad'
}

function formatModifiedAt(value) {
  return value ? value.replace('T', ' ').replace(/([+-]\d{2}:\d{2})$/, '') : ''
}

onMounted(loadDataFiles)
</script>

<template>
  <div class="data-panel" data-testid="data-panel">
    <!-- 上传区 -->
    <div class="upload-section">
      <label class="upload-btn" :class="{ loading: uploading }">
        {{ uploading ? '⏳ 解析中...' : '📊 上传 Excel' }}
        <input data-testid="data-upload-input" type="file" hidden accept=".xlsx,.xls,.csv"
               @change="uploadExcel" :disabled="uploading" />
      </label>
      <p class="upload-hint">上传经营数据开始分析</p>
    </div>

    <section class="data-files-section">
      <div class="section-heading">
        <span>数据文件</span>
        <span v-if="dataFiles.length" class="file-count">{{ dataFiles.length }}</span>
      </div>

      <p v-if="filesLoading" class="data-state">正在读取数据文件...</p>
      <UiErrorState
        v-else-if="filesError"
        title="数据文件列表没读到"
        :description="filesError"
        :retryable="!filesDenied"
        retry-text="重新加载"
        :busy="filesLoading"
        dense
        @retry="loadDataFiles"
      />
      <UiEmptyState
        v-else-if="!dataFiles.length"
        title="暂无数据文件"
        description="上传 Excel 或 CSV 开始分析。"
        dense
      />

      <div v-else class="data-file-list">
        <button
          v-for="file in dataFiles"
          :key="file.filename"
          type="button"
          :class="['data-file-item', { active: file.filename === dataFile, loading: selectingFile && file.filename === dataFile }]"
          @click="selectDataFile(file.filename)"
        >
          <span class="data-file-icon">{{ file.extension === '.csv' ? 'CSV' : 'XLS' }}</span>
          <span class="data-file-main">
            <span class="data-file-name">{{ file.filename }}</span>
            <span class="data-file-meta">{{ file.size_label }} · {{ formatModifiedAt(file.modified_at) }}</span>
          </span>
        </button>
      </div>
    </section>

    <UiErrorState
      v-if="previewError && !previewOpen"
      title="数据预览没打开"
      :description="previewError"
      :retryable="!previewDenied"
      retry-text="重试"
      :busy="selectingFile"
      dense
      @retry="selectDataFile(dataFile)"
    />

    <!-- 数据画像 -->
    <div v-if="profile" class="profile-card">
      <div class="profile-header">
        <div class="profile-heading">
          <span class="profile-title">📋 数据画像</span>
          <span class="profile-stats">
            {{ profile.rows }} 行 × {{ profile.column_count || profile.columns.length }} 列
          </span>
        </div>
        <div class="data-file-actions">
          <button type="button" class="data-action-btn" @click="openDataFile">打开</button>
          <button type="button" class="data-action-btn" @click="downloadDataFile">下载</button>
        </div>
      </div>

      <!-- 列信息 -->
      <div class="col-list">
        <div v-for="col in profile.columns" :key="col.name" class="col-item">
          <div class="col-head">
            <span class="col-icon">{{ typeIcon(col.dtype) }}</span>
            <span class="col-name">{{ col.name }}</span>
            <span class="col-type">{{ col.dtype }}</span>
            <span v-if="col.missing_pct > 0" :class="['col-missing', missingClass(col.missing_pct)]">
              {{ col.missing }} 缺失
            </span>
          </div>
          <div v-if="col.min !== undefined" class="col-stats">
            最小 {{ col.min }} · 最大 {{ col.max }} · 均值 {{ col.mean }}
          </div>
          <div v-else-if="col.unique_values !== undefined" class="col-stats">
            {{ col.unique_values }} 个唯一值
          </div>
        </div>
      </div>
    </div>

    <!-- 快捷提问 -->
    <div class="quick-actions" data-testid="data-quick-actions">
      <h4>💡 快捷提问</h4>
      <button v-for="act in quickActions" :key="act.label"
              class="quick-chip" @click="askQuestion(act.query)">
        {{ act.label }}
      </button>
    </div>

    <DocumentPreviewModal
      :open="previewOpen"
      :filename="dataFile"
      kind="table"
      :columns="tableColumns"
      :rows="tableRows"
      :loading="previewLoading"
      :error="previewError"
      :truncated="tableTruncated"
      @close="closeDataPreview"
      @download="downloadDataFile"
    />
  </div>
</template>

<style scoped>
.data-panel {
  padding: 0 18px 18px;
  overflow-y: auto;
}

.data-panel::-webkit-scrollbar {
  width: 4px;
}
.data-panel::-webkit-scrollbar-thumb {
  background: #d0d5dd;
  border-radius: 4px;
}

/* 上传 */
.upload-section {
  text-align: center;
  padding: 18px 0 14px;
  border-bottom: 1px solid rgba(0,0,0,0.05);
}

.upload-btn {
  display: inline-block;
  padding: 10px 22px;
  background: linear-gradient(135deg, #10b981, #059669);
  color: #fff;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}

.upload-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(16,185,129,0.3);
}

.upload-btn.loading {
  background: #a7f3d0;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.upload-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.data-files-section {
  padding: 16px 0 2px;
  border-bottom: 1px solid rgba(0,0,0,0.05);
}

.section-heading {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 9px;
  color: #303133;
  font-size: 13px;
  font-weight: 600;
}

.file-count {
  min-width: 18px;
  padding: 1px 6px;
  border-radius: 99px;
  background: rgba(16,185,129,0.12);
  color: #047857;
  font-size: 11px;
  text-align: center;
}

.data-file-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 210px;
  overflow-y: auto;
  padding-right: 2px;
}

.data-file-item {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 9px;
  padding: 9px 10px;
  border: 1px solid #edf0f2;
  border-radius: 8px;
  background: #fff;
  color: #303133;
  cursor: pointer;
  font: inherit;
  text-align: left;
  transition: border-color 0.15s, background 0.15s, transform 0.15s;
}

.data-file-item:hover {
  border-color: #6ee7b7;
  background: #f0fdf4;
  transform: translateX(2px);
}

.data-file-item.active {
  border-color: #10b981;
  background: linear-gradient(135deg, #ecfdf5, #f0fdf4);
  box-shadow: 0 2px 8px rgba(16,185,129,0.1);
}

.data-file-item.loading {
  opacity: 0.65;
}

.data-file-icon {
  flex: 0 0 auto;
  min-width: 30px;
  padding: 4px 3px;
  border-radius: 5px;
  background: #dcfce7;
  color: #047857;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.4px;
  text-align: center;
}

.data-file-main {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 3px;
}

.data-file-name {
  overflow: hidden;
  color: #374151;
  font-size: 12px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.data-file-meta {
  color: #9ca3af;
  font-size: 10px;
}

.data-state {
  margin: 4px 0 10px;
  color: #909399;
  font-size: 12px;
  line-height: 1.5;
}

/* 数据画像 */
.profile-card {
  margin-top: 16px;
  background: rgba(255,255,255,0.8);
  border-radius: 10px;
  border: 1px solid rgba(0,0,0,0.04);
  overflow: hidden;
}

.profile-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: rgba(16,185,129,0.06);
  border-bottom: 1px solid rgba(0,0,0,0.04);
}

.profile-heading {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.profile-title {
  font-size: 13px;
  font-weight: 600;
}

.profile-stats {
  font-size: 11px;
  color: #909399;
}

.data-file-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.data-action-btn {
  padding: 4px 9px;
  border: 1px solid #d1d5db;
  border-radius: 5px;
  background: #fff;
  color: #4b5563;
  cursor: pointer;
  font: inherit;
  font-size: 11px;
}

.data-action-btn:hover {
  border-color: #10b981;
  color: #047857;
}

.col-list {
  padding: 8px 0;
}

.col-item {
  padding: 10px 14px;
  border-bottom: 1px solid #f5f5f5;
}

.col-item:last-child {
  border-bottom: none;
}

.col-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.col-icon {
  font-size: 13px;
}

.col-name {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
}

.col-type {
  font-size: 11px;
  color: #909399;
  background: #f0f2f5;
  padding: 1px 6px;
  border-radius: 4px;
}

.col-missing {
  margin-left: auto;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
}

.col-missing.ok { color: #67c23a; background: rgba(103,194,58,0.08); }
.col-missing.warn { color: #e6a23c; background: rgba(230,162,60,0.08); }
.col-missing.bad { color: #f56c6c; background: rgba(245,108,108,0.08); }

.col-stats {
  font-size: 11px;
  color: #909399;
}

/* 快捷操作 */
.quick-actions {
  margin-top: 20px;
}

.quick-actions h4 {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
}

.quick-chip {
  display: block;
  width: 100%;
  text-align: left;
  padding: 10px 14px;
  margin-bottom: 6px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-family: inherit;
  color: #303133;
  transition: all 0.15s;
}

.quick-chip:hover {
  border-color: #409eff;
  color: #409eff;
  background: rgba(64,158,255,0.03);
  transform: translateX(3px);
}

.data-panel {
  color: var(--text);
  padding: 0 18px 18px;
}

.data-panel::-webkit-scrollbar-thumb {
  background: rgba(157, 178, 207, .25);
}

.upload-section,
.data-files-section {
  border-bottom-color: var(--line);
}

.upload-btn {
  background: linear-gradient(135deg, var(--cyan), #1a9f9a);
  color: #061016;
  box-shadow: 0 10px 24px rgba(53, 211, 200, .14);
}

.upload-btn.loading {
  background: rgba(53, 211, 200, .25);
  color: var(--ink-soft);
}

.upload-hint,
.data-state,
.data-file-meta,
.col-type,
.col-stats {
  color: var(--muted);
}

.section-heading,
.quick-actions h4,
.col-name {
  color: var(--text);
}

.file-count,
.col-type {
  background: rgba(53, 211, 200, .1);
  color: var(--cyan);
}

.data-file-item,
.profile-card,
.col-item,
.quick-chip {
  background: rgba(255, 255, 255, .035);
  border-color: var(--line);
}

.data-file-item:hover,
.data-file-item.active,
.quick-chip:hover {
  border-color: rgba(53, 211, 200, .42);
  background: rgba(53, 211, 200, .08);
  color: var(--cyan);
}

.data-file-name,
.profile-title,
.profile-stats {
  color: var(--text);
}

.data-action-btn {
  border-color: var(--line-strong);
  background: rgba(255, 255, 255, .04);
  color: var(--ink-soft);
}

.data-action-btn:hover {
  border-color: var(--blue);
  color: #b5c4ff;
}

.col-missing.ok {
  color: var(--green);
  background: rgba(101, 212, 154, .1);
}

.col-missing.warn {
  color: var(--amber);
  background: rgba(228, 162, 74, .1);
}

.col-missing.bad {
  color: #ff9da5;
  background: rgba(238, 109, 120, .1);
}
</style>
