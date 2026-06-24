<script setup>
import { ref } from 'vue'
import axios from 'axios'

// axios 拦截器：自动带上 JWT
axios.interceptors.request.use(config => {
  const token = window._authToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

const API = '/api/v1'
const profile = ref(null)
const uploading = ref(false)

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
    const res = await axios.post(`${API}/upload-excel`, form)
    profile.value = res.data.profile  // 取 profile 字段
  } catch (err) {
    console.error('上传失败', err)
  } finally {
    uploading.value = false
    e.target.value = ''
  }
}

function askQuestion(q) {
  emit('ask', q)
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
</script>

<template>
  <div class="data-panel">
    <!-- 上传区 -->
    <div class="upload-section">
      <label class="upload-btn" :class="{ loading: uploading }">
        {{ uploading ? '⏳ 解析中...' : '📊 上传 Excel' }}
        <input type="file" hidden accept=".xlsx,.xls,.csv"
               @change="uploadExcel" :disabled="uploading" />
      </label>
      <p class="upload-hint">上传经营数据开始分析</p>
    </div>

    <!-- 数据画像 -->
    <div v-if="profile" class="profile-card">
      <div class="profile-header">
        <span class="profile-title">📋 数据画像</span>
        <span class="profile-stats">
          {{ profile.rows }} 行 × {{ profile.columns }} 列
        </span>
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
    <div class="quick-actions">
      <h4>💡 快捷提问</h4>
      <button v-for="act in quickActions" :key="act.label"
              class="quick-chip" @click="askQuestion(act.query)">
        {{ act.label }}
      </button>
    </div>
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

.profile-title {
  font-size: 13px;
  font-weight: 600;
}

.profile-stats {
  font-size: 11px;
  color: #909399;
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
</style>
