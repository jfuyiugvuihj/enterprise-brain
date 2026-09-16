<!--
  异常与告警（W7 · 看板 §4F.5 裁定 (c) 的前端半边）

  这一页原先是一台「客户端自问自答」的演示机：五格手填阈值 + 三行写死在前端常量里的假数据，
  POST /insights/detect 只对送上去的 rows 做算术，不查库（后端 R14 未落地），
  于是屏上的「待关注 N 条」既不是告警也不是异常。现在整条链路换成服务端真端点：
    GET    /alerts              触发中的告警（后端 LIMIT 100）
    GET    /alerts/rules        已登记的规则
    POST   /alerts/rules        新增一条
    DELETE /alerts/rules/{id}   删除一条（两步确认）
    POST   /alerts/check        手动巡检一次（会写库并发通知，所以只有人手点才发）

  四张脸必须分开（R1 裁定 (c)：后端零改动，GET /alerts 对 staff 保持 403）：
    401 -> 登录状态已失效        403 -> 这个账号没有查看告警的权限（并说明去哪申请）
    200 空 -> 当前没有触发中的告警  200 有行 -> 列表
  判据与文案都在 lib/alerts.js 里单点实现，本文件只做状态编排与渲染，
  所以「失败被画成空态」这件事不可能在这里再写错一遍。

  进页面只发两条 GET：巡检与规则增删是写操作，一律等人工点击。
-->
<script>
export default { name: 'InsightPanel' }
</script>

<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  ALERTS_EMPTY_DESCRIPTION,
  ALERTS_EMPTY_TITLE,
  ALERTS_FEED_LIMIT,
  ALERTS_LIMIT_NOTE,
  RULES_EMPTY_DESCRIPTION,
  RULES_EMPTY_TITLE,
  RULE_OPERATORS,
  advanceRuleDelete,
  checkOutcomeView,
  createRule,
  emptyRuleForm,
  faceOf,
  fetchAlerts,
  fetchRules,
  mapAlertRow,
  mapRuleRow,
  readFailureView,
  removeRule,
  runCheck,
  shapeFailureView,
  validateRuleForm,
} from '../lib/alerts'
import { UiButton, UiEmptyState, UiErrorState, UiField, UiLoadingState, UiSelect } from './ui'

const alerts = ref([])
const alertsLoading = ref(true)
const alertsFailure = ref(null)

const rules = ref([])
const rulesLoading = ref(true)
const rulesFailure = ref(null)

const checking = ref(false)
const checkOutcome = ref(null)
const checkFailure = ref(null)

const ruleForm = ref(emptyRuleForm())
const ruleErrors = ref({})
const savingRule = ref(false)
const ruleSaveFailure = ref(null)

const pendingRuleId = ref('')
const deletingRuleId = ref('')
const ruleDeleteFailure = ref(null)

// 读取失败优先于「空」：拿不到列表说「没有告警」就是 R1(c) 要拆的那条缝。
const alertsFace = computed(() => {
  if (alertsLoading.value) return 'loading'
  if (alertsFailure.value) return alertsFailure.value.face
  return faceOf({ rowCount: alerts.value.length })
})

const rulesFace = computed(() => {
  if (rulesLoading.value) return 'loading'
  if (rulesFailure.value) return rulesFailure.value.face
  return faceOf({ rowCount: rules.value.length })
})

// 五个端点过的是同一项权限：查看被 403 判掉，写操作也不该留成可点的按钮。
const denied = computed(() => alertsFace.value === 'denied')
const canManage = computed(() => !denied.value)

// 计数格在读取失败时给的是「没读到」而不是 0：0 只可能来自真拿到空数组。
function countText(face, rows) {
  if (face === 'loading') return '正在读取'
  if (face === 'denied') return '没有权限'
  if (face === 'unauthorized') return '未登录'
  if (face === 'error') return '没读到'
  return String(rows.length)
}

const summary = computed(() => [
  { label: '最近告警', value: countText(alertsFace.value, alerts.value) },
  { label: '告警规则', value: countText(rulesFace.value, rules.value) },
])

async function loadAlerts() {
  alertsLoading.value = true
  alertsFailure.value = null
  try {
    const rows = await fetchAlerts()
    if (rows === null) {
      alertsFailure.value = shapeFailureView('告警列表没能读出来')
      return
    }
    alerts.value = rows.map(mapAlertRow)
  } catch (err) {
    alertsFailure.value = readFailureView(err, {
      deniedTitle: '这个账号没有查看告警的权限',
      failedTitle: '告警列表没能读出来',
    })
  } finally {
    alerts.value = alertsFailure.value ? [] : alerts.value
    alertsLoading.value = false
  }
}

async function loadRules() {
  rulesLoading.value = true
  rulesFailure.value = null
  pendingRuleId.value = ''
  try {
    const rows = await fetchRules()
    if (rows === null) {
      rulesFailure.value = shapeFailureView('告警规则没能读出来')
      return
    }
    rules.value = rows.map(mapRuleRow)
  } catch (err) {
    rulesFailure.value = readFailureView(err, {
      deniedTitle: '这个账号没有查看告警规则的权限',
      failedTitle: '告警规则没能读出来',
    })
  } finally {
    rules.value = rulesFailure.value ? [] : rules.value
    rulesLoading.value = false
  }
}

function loadAll() {
  return Promise.all([loadAlerts(), loadRules()])
}

async function runManualCheck() {
  checking.value = true
  checkFailure.value = null
  checkOutcome.value = null
  try {
    checkOutcome.value = checkOutcomeView(await runCheck())
  } catch (err) {
    checkFailure.value = readFailureView(err, {
      deniedTitle: '这个账号没有手动巡检的权限',
      failedTitle: '巡检没有跑完',
    })
    return
  } finally {
    checking.value = false
  }
  // 巡检可能刚写入新记录，列表得跟着刷新，否则这一屏会停在上一轮的结果上。
  await loadAlerts()
}

async function addRule() {
  const verdict = validateRuleForm(ruleForm.value)
  ruleErrors.value = verdict.errors
  if (!verdict.ok) return
  savingRule.value = true
  ruleSaveFailure.value = null
  try {
    await createRule(ruleForm.value)
    ruleForm.value = emptyRuleForm()
  } catch (err) {
    ruleSaveFailure.value = readFailureView(err, {
      deniedTitle: '这个账号没有新增告警规则的权限',
      failedTitle: '规则没有保存成功',
    })
    return
  } finally {
    savingRule.value = false
  }
  await loadRules()
}

/** 第一步点击只把「待确认」挪到这一行，第二次点击才真的发 DELETE。 */
function askDeleteRule(rule) {
  const next = advanceRuleDelete(pendingRuleId.value, rule ? rule.id : '')
  if (next === 'arm') {
    pendingRuleId.value = rule.id
    return
  }
  if (next !== 'execute') {
    pendingRuleId.value = ''
    return
  }
  pendingRuleId.value = ''
  deleteRuleRow(rule)
}

async function deleteRuleRow(rule) {
  deletingRuleId.value = rule.id
  ruleDeleteFailure.value = null
  try {
    const receipt = await removeRule(rule.id)
    if (receipt === 'invalid') {
      ruleDeleteFailure.value = shapeFailureView('这条规则的编号不对，删除没有发出')
      return
    }
    if (receipt === 'not_found') {
      ruleDeleteFailure.value = shapeFailureView('这条规则已经不在了，列表已重新读取')
    }
  } catch (err) {
    ruleDeleteFailure.value = readFailureView(err, {
      deniedTitle: '这个账号没有删除告警规则的权限',
      failedTitle: '规则没有删除成功',
    })
    return
  } finally {
    deletingRuleId.value = ''
  }
  await loadRules()
}

function ruleDeleteLabel(rule) {
  if (deletingRuleId.value === rule.id) return '删除中'
  return pendingRuleId.value === rule.id ? '确认删除？' : '删除'
}

onMounted(loadAll)
</script>

<template>
  <div class="panel-shell" data-testid="alerts-panel">
    <header class="panel-head">
      <div>
        <div class="eyebrow">Alerts</div>
        <h3>异常与告警</h3>
        <p>规则命中才会写告警。这一页只列服务端真实记录下来的告警与规则。</p>
      </div>
      <div class="head-stats">
        <div v-for="item in summary" :key="item.label" class="mini-stat">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>
    </header>

    <div class="panel-grid">
      <section class="panel-card" data-testid="alerts-card" :data-face="alertsFace">
        <div class="section-head">
          <h4>触发中的告警</h4>
          <UiButton
            size="sm"
            variant="ghost"
            :loading="alertsLoading"
            label="重新加载"
            data-testid="reload-alerts"
            @click="loadAlerts"
          />
        </div>

        <UiLoadingState v-if="alertsFace === 'loading'" label="正在读取告警列表..." dense />
        <UiErrorState
          v-else-if="alertsFailure"
          :title="alertsFailure.title"
          :description="alertsFailure.description"
          :code-label="alertsFailure.codeLabel"
          :retryable="alertsFailure.retryable"
          retry-text="重新加载"
          :busy="alertsLoading"
          dense
          @retry="loadAlerts"
        />
        <UiEmptyState
          v-else-if="alertsFace === 'empty'"
          :title="ALERTS_EMPTY_TITLE"
          :description="ALERTS_EMPTY_DESCRIPTION"
          dense
        />
        <div v-else class="record-list" data-testid="alert-rows">
          <article v-for="item in alerts" :key="item.id" class="record-item">
            <div class="record-body">
              <strong>{{ item.message }}</strong>
              <p v-if="item.analysis" class="record-analysis">{{ item.analysis }}</p>
            </div>
            <div class="record-meta">
              <span v-if="item.createdAt" class="chip">{{ item.createdAt }}</span>
              <span v-if="item.ruleId" class="chip">规则 #{{ item.ruleId }}</span>
            </div>
          </article>
        </div>

        <p v-if="alerts.length >= ALERTS_FEED_LIMIT" class="foot-note">{{ ALERTS_LIMIT_NOTE }}</p>
      </section>

      <div class="side-stack">
        <section class="panel-card" data-testid="alerts-check-card">
          <div class="section-head"><h4>手动巡检</h4></div>
          <p class="lead-note">
            按已启用规则重算一遍可见范围内的经营数据，命中才写入告警。进这一页不会自动跑巡检。
          </p>
          <div class="actions">
            <UiButton
              variant="primary"
              :loading="checking"
              :disabled="checking || denied"
              label="立即巡检"
              data-testid="run-alert-check"
              @click="runManualCheck"
            />
          </div>
          <p v-if="denied" class="foot-note">巡检与查看告警走的是同一项权限，当前账号点不动它。</p>
          <UiErrorState
            v-if="checkFailure"
            :title="checkFailure.title"
            :description="checkFailure.description"
            :code-label="checkFailure.codeLabel"
            :retryable="checkFailure.retryable"
            retry-text="重新巡检"
            :busy="checking"
            dense
            @retry="runManualCheck"
          />
          <div v-else-if="checkOutcome" class="receipt" data-testid="check-receipt" :data-kind="checkOutcome.kind">
            <strong>{{ checkOutcome.title }}</strong>
            <p>{{ checkOutcome.detail }}</p>
          </div>
        </section>

        <section class="panel-card" data-testid="rules-card" :data-face="rulesFace">
          <div class="section-head">
            <h4>告警规则</h4>
            <UiButton
              size="sm"
              variant="ghost"
              :loading="rulesLoading"
              label="重新加载"
              data-testid="reload-rules"
              @click="loadRules"
            />
          </div>

          <UiLoadingState v-if="rulesFace === 'loading'" label="正在读取告警规则..." dense />
          <UiErrorState
            v-else-if="rulesFailure"
            :title="rulesFailure.title"
            :description="rulesFailure.description"
            :code-label="rulesFailure.codeLabel"
            :retryable="rulesFailure.retryable"
            retry-text="重新加载"
            :busy="rulesLoading"
            dense
            @retry="loadRules"
          />
          <UiEmptyState
            v-else-if="rulesFace === 'empty'"
            :title="RULES_EMPTY_TITLE"
            :description="RULES_EMPTY_DESCRIPTION"
            dense
          />
          <div v-else class="record-list" data-testid="rule-rows">
            <article v-for="item in rules" :key="item.id" class="rule-item">
              <div class="record-body">
                <strong>{{ item.name }}</strong>
                <p class="rule-rule">{{ item.metricText }} {{ item.opLabel }} {{ item.thresholdText }}</p>
              </div>
              <div class="record-meta">
                <span v-if="!item.enabled" class="chip">已停用</span>
                <UiButton
                  size="sm"
                  variant="ghost"
                  :disabled="deletingRuleId === item.id || !canManage"
                  :label="ruleDeleteLabel(item)"
                  data-testid="delete-rule"
                  @click="askDeleteRule(item)"
                />
              </div>
            </article>
          </div>

          <UiErrorState
            v-if="ruleDeleteFailure"
            :title="ruleDeleteFailure.title"
            :description="ruleDeleteFailure.description"
            :code-label="ruleDeleteFailure.codeLabel"
            :retryable="ruleDeleteFailure.retryable"
            retry-text="重新加载规则"
            :busy="rulesLoading"
            dense
            @retry="loadRules"
          />

          <div class="rule-form" data-testid="rule-form">
            <UiField
              v-model="ruleForm.name"
              label="规则名称"
              hint="例如：月度差旅费上限"
              :error="ruleErrors.name"
              :disabled="!canManage || savingRule"
            />
            <UiField
              v-model="ruleForm.metric"
              label="指标列名"
              hint="写经营数据里的列名，后端按列取合计再比较"
              :error="ruleErrors.metric"
              :disabled="!canManage || savingRule"
            />
            <UiSelect
              v-model="ruleForm.op"
              label="比较方式"
              :options="RULE_OPERATORS"
              :error="ruleErrors.op"
              :disabled="!canManage || savingRule"
            />
            <UiField
              v-model="ruleForm.threshold"
              type="number"
              label="阈值"
              hint="可以是小数"
              :error="ruleErrors.threshold"
              :disabled="!canManage || savingRule"
            />
            <div class="actions">
              <UiButton
                variant="primary"
                :loading="savingRule"
                :disabled="savingRule || !canManage"
                label="新增规则"
                data-testid="create-rule"
                @click="addRule"
              />
            </div>
            <UiErrorState
              v-if="ruleSaveFailure"
              :title="ruleSaveFailure.title"
              :description="ruleSaveFailure.description"
              :code-label="ruleSaveFailure.codeLabel"
              :retryable="ruleSaveFailure.retryable"
              retry-text="再试一次"
              :busy="savingRule"
              dense
              @retry="addRule"
            />
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.head-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(90px, 1fr));
  gap: var(--s-2);
}

.mini-stat {
  display: grid;
  gap: var(--s-1);
  padding: var(--s-3);
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
  grid-template-columns: 1.15fr .85fr;
  gap: var(--s-4);
  align-items: start;
}

.side-stack {
  display: grid;
  gap: var(--s-4);
}

.record-list,
.rule-form {
  display: grid;
  gap: var(--s-2);
}

.record-item,
.rule-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--s-3);
  padding: var(--s-3);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
}

.record-body {
  min-width: 0;
}

.record-body strong {
  color: var(--text);
  font-size: var(--t-sm);
  font-weight: 600;
}

.record-analysis,
.rule-rule {
  display: block;
  margin: var(--s-1) 0 0;
  color: var(--muted);
  font-size: var(--t-xs);
  line-height: 1.6;
}

.record-analysis {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.record-meta {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: var(--s-2);
}

.lead-note,
.foot-note {
  margin: var(--s-2) 0 0;
  color: var(--muted);
  font-size: var(--t-xs);
  line-height: 1.6;
}

.foot-note {
  color: var(--ink-faint);
}

.receipt {
  margin-top: var(--s-3);
  padding: var(--s-3);
  border: 1px solid var(--line);
  border-left: 3px solid var(--cyan);
  border-radius: var(--radius-sm);
}

.receipt strong {
  color: var(--text);
  font-size: var(--t-sm);
}

.receipt p {
  margin: var(--s-1) 0 0;
  color: var(--muted);
  font-size: var(--t-xs);
  line-height: 1.6;
}

.actions {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  margin-top: var(--s-2);
}

@media (max-width: 760px) {
  .panel-grid {
    grid-template-columns: 1fr;
  }
}
</style>
