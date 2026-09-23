<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../lib/api'
import { errorDetail, isPermissionDenied } from '../lib/http'
import { demoForm } from '../devFixtures/approval-demo'
import { UiEmptyState, UiErrorState } from './ui'
import HitlPendingPanel from './hitl/HitlPendingPanel.vue'

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
        <h3>审批与待办</h3>
        <p>这是一台报销政策自查工具：填一组参数，看金额按标准算是否超标，并拿到下一步建议。它不办理审批。</p>
        <p>真正在等你拍板的事在上方那一块：每一笔都能就地定夺，也能跳回产生它的那一轮对话。</p>
      </div>
    </header>

    <!-- 这句话已经过时：R13 那半条端点早就落了地，R168 把「等你拍板」那一问从对话流里抽出来，
         接的就是 GET /hitl/pending + POST /approve 两条真端点 —— 也就是下面这一整块。 -->
    <HitlPendingPanel />

    <!-- 这一行以下才是一台用假参数预演的计算器。 -->
    <aside class="demo-flag-row" data-testid="approval-demo-flag">
      <span class="demo-flag">演示数据</span>
      <span class="demo-note">预审参数（金额 680 / 标准 500 / 市场部 住宿费）来自前端常量 src/devFixtures/approval-demo.js，不是任何人的真单据；结论只是阈值算术。这块只管下面「自查参数 / 自查结论」两格，不构成审批记录；上方那一屏挂起待办读的是服务端真账本，跟这些假参数没有关系。</span>
    </aside>

    <!-- F4（checklist L111）当年裁定：这一屏只做「自查」，工单模型 C-1 没建，所以这里既没有
         待办列表，也不许出现批准与驳回按钮——放了就是假审批。人工确认只有一个入口，在对话页的 HITL 卡片上。
         R168 更正它的前提：C-1 说的「工单模型」根本没打算建，因为这件事后端已经用另一条路交付了 ——
         挂起账本（GET /hitl/pending）与唯一的 resolver（POST /approve）。于是上方那一块确实带着
         批准与驳回按钮：它们按的是对话页那张卡片同一个端点、同一个判定，不是这里另造的第二套结论。
         下面「自查参数 / 自查结论」那一块仍然不办理审批，F4 那半条裁定照旧有效。 -->
    <aside class="scope-note" data-testid="approval-scope-note">
      <strong>自查工具，不是审批</strong>
      <p>它回答的只有一个问题：这组费用参数按标准算超没超标。查完不会生成工单，不会记在任何人名下，也不会改变任何单据的状态。</p>
      <p>需要人工确认时，入口在对话页那一轮卡片上；上方那一屏列的就是同一批待确认的事。两处按的是同一个
          resolver、同一个判定，账本只有一份 —— 在哪儿点都一样，这一屏不放第二套结论，免得两处互相打架。</p>
      <p>「挂起待办」这一屏读的是服务端挂起账本（GET /hitl/pending），一行一笔，没有真挂着的事就留空态。
          它仍然不摆「待审批 N 条」那种数字：后端给的 count 是过滤后的长度，契约明写不得当总数用，
          那就无处可取的数继续不摆。</p>
    </aside>

    <div class="panel-grid">
      <section class="panel-card">
        <div class="section-head"><h4>自查参数</h4></div>
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
            {{ loading ? '正在自查' : '重新自查' }}
          </button>
        </div>
      </section>

      <section class="panel-card">
        <div class="section-head"><h4>自查结论</h4></div>
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

.scope-note {
  display: grid;
  gap: var(--s-1);
  margin-top: var(--s-2);
  padding: var(--s-3);
  border: 1px solid var(--line);
  border-left: 3px solid var(--cyan);
  border-radius: var(--radius-sm);
}

.scope-note strong {
  color: var(--text);
  font-size: var(--t-sm);
  font-weight: 600;
}

.scope-note p {
  margin: 0;
  color: var(--muted);
  font-size: var(--t-xs);
  line-height: 1.6;
}

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
