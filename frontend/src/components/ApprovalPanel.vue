<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../lib/api'

const form = ref({
  amount: 680,
  standard: 500,
  department: '市场部',
  expense_type: '住宿费',
  evidence: ['差旅费报销制度.pdf'],
})
const result = ref(null)
const loading = ref(false)
const error = ref('')

async function submitCheck() {
  loading.value = true
  error.value = ''
  try {
    const response = await api.post('/approval/precheck', form.value)
    result.value = response.data
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '审批预审失败'
  } finally {
    loading.value = false
  }
}

onMounted(submitCheck)
</script>

<template>
  <div class="panel-shell" data-testid="approval-panel">
    <header class="panel-head">
      <div>
        <div class="eyebrow">Approval</div>
        <h3>智能审批</h3>
        <p>快速判断金额是否超出标准，并给出下一步建议。</p>
      </div>
    </header>

    <div class="panel-grid">
      <section class="panel-card">
        <div class="section-head"><h4>审批参数</h4></div>
        <div class="form-grid">
          <label><span>金额</span><input v-model.number="form.amount" type="number" /></label>
          <label><span>标准</span><input v-model.number="form.standard" type="number" /></label>
          <label><span>部门</span><input v-model="form.department" /></label>
          <label><span>费用类型</span><input v-model="form.expense_type" /></label>
        </div>
        <label class="full">
          <span>证据</span>
          <input :value="form.evidence.join(', ')" @change="form.evidence = $event.target.value.split(',').map(value => value.trim()).filter(Boolean)" />
        </label>
        <div class="actions">
          <button class="primary-btn" data-testid="run-approval" :disabled="loading" @click="submitCheck">
            {{ loading ? '分析中' : '生成预审建议' }}
          </button>
          <span v-if="error" class="inline-error">{{ error }}</span>
        </div>
      </section>

      <section class="panel-card">
        <div class="section-head"><h4>预审结论</h4></div>
        <div v-if="!result" class="empty-state">等待分析</div>
        <div v-else class="result-card">
          <div class="result-top">
            <strong>{{ result.status }}</strong>
            <span :class="['badge', result.risk_level]">{{ result.risk_level }}</span>
          </div>
          <div class="result-grid">
            <span>金额：{{ result.amount }}</span>
            <span>标准：{{ result.standard }}</span>
            <span>超出：{{ result.excess_amount }}</span>
            <span>超比：{{ (result.excess_ratio * 100).toFixed(1) }}%</span>
          </div>
          <p class="recommendation">{{ result.recommendation }}</p>
          <div class="chips">
            <span v-for="item in result.evidence || []" :key="item" class="chip">{{ item }}</span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.panel-grid {
  display: grid;
  grid-template-columns: .95fr 1.05fr;
  gap: 16px;
}

.form-grid,
.result-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

label {
  display: grid;
  gap: 6px;
  color: var(--muted);
  font-size: 12px;
}

.full {
  margin-top: 12px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}

.result-card {
  display: grid;
  gap: 14px;
  padding: 14px;
}

.result-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.result-grid {
  color: var(--ink-soft);
  font-size: 12px;
}

.recommendation {
  margin: 0;
  padding: 14px;
  color: var(--text);
  background: rgba(255, 255, 255, .05);
  border-radius: 12px;
  font-size: 12px;
  line-height: 1.7;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

@media (max-width: 760px) {
  .panel-grid,
  .form-grid,
  .result-grid {
    grid-template-columns: 1fr;
  }
}
</style>
