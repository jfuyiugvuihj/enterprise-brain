<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../lib/api'
import { errorDetail, isPermissionDenied } from '../lib/http'
import { demoForm } from '../devFixtures/approval-demo'
import { UiEmptyState, UiErrorState } from './ui'

// 同理，表单会改写这些值；evidence 虽整条替换，仍拷一份，避免面板把模块常量改掉。
const form = ref({ ...demoForm, evidence: [...demoForm.evidence] })
const result = ref(null)
const loading = ref(false)
const error = ref('')
// 面板 onMounted 就自己发一次预审，所以「等待分析」在失败时是句假话：
// 它把「跑失败了」说成「还没跑」。failed 用来把这两件事分开（R1c 同一判据）。
const failed = ref(false)
const denied = ref(false)

async function submitCheck() {
  loading.value = true
  error.value = ''
  failed.value = false
  denied.value = false
  try {
    const response = await api.post('/approval/precheck', form.value)
    result.value = response.data
  } catch (err) {
    denied.value = isPermissionDenied(err)
    failed.value = true
    result.value = null
    error.value = denied.value
      ? '当前账号没有做预审的权限，请联系管理员开通。'
      : errorDetail(err, '审批预审失败')
  } finally {
    loading.value = false
  }
}

onMounted(submitCheck)
</script>

<template>
  <div class="panel-shell" data-testid="approval-panel" data-demo="fixtures">
    <header class="panel-head">
      <div>
        <div class="eyebrow">Approval</div>
        <h3>智能审批</h3>
        <p>快速判断金额是否超出标准，并给出下一步建议。</p>
      </div>
    </header>

    <!-- 真正的"挂起待办"要等后端 R13；这块是一台用假参数预演的计算器。 -->
    <aside class="demo-flag-row" data-testid="approval-demo-flag">
      <span class="demo-flag">演示数据</span>
      <span class="demo-note">预审参数（金额 680 / 标准 500 / 市场部 住宿费）来自前端常量 src/devFixtures/approval-demo.js，不是任何人的真单据；结论只是阈值算术。列挂起 HITL 待办的端点尚未实现（后端 R13），所以这里既不是待办列表，也不构成审批记录。</span>
    </aside>

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
        </div>
      </section>

      <section class="panel-card">
        <div class="section-head"><h4>预审结论</h4></div>
        <UiErrorState
          v-if="failed"
          :title="denied ? '没有权限做审批预审' : '预审没有跑完'"
          :description="error"
          :retryable="!denied"
          retry-text="重新预审"
          :busy="loading"
          dense
          @retry="submitCheck"
        />
        <UiEmptyState v-else-if="!result" title="等待分析" dense />
        <div v-else class="result-card">
          <div class="result-top">
            <strong>{{ result.status }}</strong>
            <span class="badge">演示</span>
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
