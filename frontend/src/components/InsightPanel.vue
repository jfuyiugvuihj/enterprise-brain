<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../lib/api'
import { demoRows } from '../devFixtures/insights-demo'

// 表格里每行都被 v-model 直接改写，所以逐行浅拷贝：
// 共享模块级数组会让第二次挂载带着上一次被删改过的数据。
const rows = ref(demoRows.map(row => ({ ...row })))
const loading = ref(false)
const insights = ref([])
const error = ref('')

const summary = computed(() => [
  { label: '输入行数', value: rows.value.length },
  { label: '待关注', value: insights.value.length },
])

function addRow() {
  rows.value.push({ department: '新部门', metric: '指标', current: 0, previous: 0, threshold: 0 })
}

function removeRow(index) {
  rows.value.splice(index, 1)
}

async function runDetection() {
  loading.value = true
  error.value = ''
  try {
    const response = await api.post('/insights/detect', { rows: rows.value })
    insights.value = response.data.insights || []
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '洞察分析失败'
  } finally {
    loading.value = false
  }
}

onMounted(runDetection)
</script>

<template>
  <div class="panel-shell" data-testid="insights-panel">
    <header class="panel-head">
      <div>
        <div class="eyebrow">Active Insight</div>
        <h3>主动洞察</h3>
        <p>系统自动识别异常变化，帮你更早发现问题。</p>
      </div>
      <div class="head-stats">
        <div v-for="item in summary" :key="item.label" class="mini-stat">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>
    </header>

    <div class="panel-grid">
      <section class="panel-card">
        <div class="section-head">
          <h4>分析数据</h4>
          <button class="ghost-btn" @click="addRow">新增一行</button>
        </div>
        <div class="row-list">
          <article v-for="(row, index) in rows" :key="index" class="row-card">
            <div class="row-fields">
              <label><span>部门</span><input v-model="row.department" /></label>
              <label><span>指标</span><input v-model="row.metric" /></label>
              <label><span>当前值</span><input v-model.number="row.current" type="number" /></label>
              <label><span>上期值</span><input v-model.number="row.previous" type="number" /></label>
              <label><span>阈值</span><input v-model.number="row.threshold" type="number" /></label>
            </div>
            <button class="remove-btn" @click="removeRow(index)">删除</button>
          </article>
        </div>
        <div class="actions">
          <button class="primary-btn" data-testid="run-insights" :disabled="loading" @click="runDetection">
            {{ loading ? '分析中' : '生成洞察' }}
          </button>
          <span v-if="error" class="inline-error">{{ error }}</span>
        </div>
      </section>

      <section class="panel-card">
        <div class="section-head"><h4>洞察结果</h4></div>
        <div v-if="!insights.length" class="empty-state">暂时没有异常</div>
        <div v-else class="insight-list">
          <article v-for="item in insights" :key="item.title" class="insight-item">
            <div>
              <strong>{{ item.title }}</strong>
              <p>{{ item.department }} · {{ item.metric }}</p>
              <small>{{ (item.reasons || []).join(' / ') }}</small>
            </div>
            <span :class="['severity', item.severity]">{{ item.severity }}</span>
          </article>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.head-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(90px, 1fr));
  gap: 8px;
}

.mini-stat {
  display: grid;
  gap: 8px;
  padding: 12px;
}

.mini-stat span {
  color: var(--muted);
  font-size: 10px;
}

.mini-stat strong {
  color: var(--cyan);
  font-family: var(--font-mono);
  font-size: 20px;
}

.panel-grid {
  display: grid;
  grid-template-columns: 1.1fr .9fr;
  gap: 16px;
}

.row-list,
.insight-list {
  display: grid;
  gap: 10px;
}

.row-card,
.insight-item {
  padding: 13px;
}

.row-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

label {
  display: grid;
  gap: 6px;
  color: var(--muted);
  font-size: 11px;
}

.remove-btn {
  margin-top: 10px;
  padding: 7px 11px;
  color: #ffadb4;
  background: rgba(238, 109, 120, .10);
  border: 1px solid rgba(238, 109, 120, .20);
  border-radius: 8px;
  cursor: pointer;
  font-size: 11px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}

.insight-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.insight-item p,
.insight-item small {
  display: block;
  margin-top: 5px;
  color: var(--muted);
  font-size: 10px;
}

@media (max-width: 760px) {
  .panel-grid,
  .row-fields {
    grid-template-columns: 1fr;
  }
}
</style>
