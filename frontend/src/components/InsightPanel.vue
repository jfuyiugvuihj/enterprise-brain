<!--
  异常与告警（W7 起接真告警链 · 看板 §4F.5 裁定 (c) 的前端半边；R271 补上「看到了能就地办完」那半条）

  这一页原先是一台「客户端自问自答」的演示机：五格手填阈值 + 三行写死在前端常量里的编造数值，
  POST /insights/detect 只对送上去的 rows 做算术，不查库（后端 R14 未落地），
  于是屏上的「待关注 N 条」既不是告警也不是异常。现在整条链路换成服务端真端点：
    GET    /alerts              触发中的告警（后端 LIMIT 100）
    GET    /alerts/rules        已登记的规则
    POST   /alerts/rules        新增一条
    DELETE /alerts/rules/{id}   删除一条（两步确认）
    POST   /alerts/check        手动巡检一次（会写库并发通知，所以只有人手点才发）
    POST   /alerts/{id}/ack     确认：open -> acknowledged，落确认人与确认时间
    POST   /alerts/{id}/close   关闭：open / acknowledged -> closed，closed 是终态
    POST   /alerts/{id}/assign  转派：只换处置人、不动状态；请求体只有目标用户名一格

  四张脸必须分开（R1 裁定 (c)：后端零改动，GET /alerts 对 staff 保持 403）：
    401 -> 登录状态已失效        403 -> 这个账号没有查看告警的权限（并说明去哪申请）
    200 空 -> 当前没有触发中的告警  200 有行 -> 列表
  处置三枚动作另加六张脸，一张都不许顶替另一张：401 登录失效 / 403 没有处置告警的权限 /
  404 这一条读不到 / 409 刚被别人改过 / 400 转派目标不合格 / 剩下的才归「这一件没做完」。
  再加两张：编号读不出来所以请求根本没发，与「写成了但列表读不回来」的降级。
  这八张与上面四张谁也不许顶替谁，判据与话术都在 lib/alerts.js，逐张比对钉在 r271-alert-loop.test.js。
  每一枚处置动作交回的都是**处置之后的那一行**，所以这一屏先让服务端那一行上屏、再按
  GET /alerts 重读一次：刷新后仍看得见是谁、什么时候办的，凭的是读回来的一行，
  不是弹一条提示，也不是前端自己盖的时钟。

  判据与文案都在 lib/alerts.js 里单点实现，本文件只做状态编排与渲染，
  所以「失败被画成空态」这件事不可能在这里再写错一遍。

  进页面只发两条 GET：巡检、规则增删与处置三动作都是写操作，一律等人工点击。
-->
<script>
export default { name: 'InsightPanel' }
</script>

<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  ALERT_ACTION_NOTES,
  ALERTS_EMPTY_DESCRIPTION,
  ALERTS_EMPTY_TITLE,
  ALERTS_FEED_LIMIT,
  ALERTS_LIMIT_NOTE,
  DISPOSED_BUT_UNREADABLE,
  INVALID_ID_FAILURE,
  RULES_EMPTY_DESCRIPTION,
  RULES_EMPTY_TITLE,
  RULE_OPERATORS,
  advanceRuleDelete,
  advanceTwoStep,
  assigneeError,
  checkOutcomeView,
  createRule,
  disposeAlert,
  disposalFailureView,
  disposalOutcomeView,
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

// 处置三动作（确认 / 关闭 / 指派）的编排态。写成「动作:编号」一枚在飞锁：
// 同一时刻只允许一笔写操作在路上，两下连点不会发出两条 POST。
const disposing = ref('')
// 关闭是终态，所以和删除规则一样按两下：第一次只把「确认关闭？」挪到这一行。
const pendingCloseId = ref('')
// 转派草稿与报错按告警编号各记一格，别让上一行填的用户名串到下一行去。
const assignOpen = ref('')
const assignDrafts = ref({})
const assignErrors = ref({})
// 回执与失败都挂在「哪一行」上：只画在当前处置过的那一条上。
const actionReceipt = ref(null)
const actionFailure = ref(null)

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

// 读台账、写规则、手动巡检与处置三动作过的是同一项权限：查看被 403 判掉，写操作也不该留成可点的按钮。
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
  // 一次列表读取＝一块新账本：上一轮的待确认、草稿与回执都不再作数，留着只会指错行。
  pendingCloseId.value = ''
  assignOpen.value = ''
  assignDrafts.value = {}
  assignErrors.value = {}
  actionReceipt.value = null
  actionFailure.value = null
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

// ==================== 处置闭环：就地确认 / 关闭 / 指派 ====================

/** 这一行的这一枚动作正在飞：只锁这一格，不把整页按钮一起灰掉。 */
function disposalBusy(action, item) {
  return Boolean(item && item.id) && disposing.value === action + ':' + item.id
}

/**
 * 能不能点：编号可用、状态词认得、服务端那套跳转允许从这一格出发、账号没被判掉权限、
 * 且没有另一笔写在飞。判定本身仍然只在后端，这里只是不打一发注定被拒的 POST。
 */
function canDispose(action, item) {
  if (!item || !item.addressable || !item.statusKnown) return false
  if (item.actions.indexOf(action) < 0) return false
  return canManage.value && disposing.value === ''
}

function closeLabel(item) {
  if (disposalBusy('close', item)) return '关闭中'
  return Boolean(item && item.id) && pendingCloseId.value === item.id ? '确认关闭？' : '关闭'
}

/** 关闭是终态：第一次点击只点亮「确认关闭？」，第二次才真发 POST。与删除规则共用一枚状态机。 */
function askCloseAlert(item) {
  const next = advanceTwoStep(pendingCloseId.value, item ? item.id : '')
  if (next === 'arm') {
    pendingCloseId.value = item.id
    return
  }
  if (next !== 'execute') {
    pendingCloseId.value = ''
    return
  }
  pendingCloseId.value = ''
  runDisposal(item, 'close')
}

/** 指派分两步：先点亮输入框，填完登录用户名再发。空着一个请求都不发。 */
function openAssign(item) {
  if (!item || !item.id) return
  assignOpen.value = assignOpen.value === item.id ? '' : item.id
  assignErrors.value = { ...assignErrors.value, [item.id]: '' }
}

function assigningTo(item) {
  return Boolean(item && item.id) && assignOpen.value === item.id
}

function setAssignDraft(item, value) {
  if (!item || !item.id) return
  assignDrafts.value = { ...assignDrafts.value, [item.id]: String(value === null || value === undefined ? '' : value) }
}

function confirmAssign(item) {
  if (!item || !item.id) return
  const error = assigneeError(assignDrafts.value[item.id])
  assignErrors.value = { ...assignErrors.value, [item.id]: error }
  if (error) return
  runDisposal(item, 'assign')
}

/** 处置之后：先让服务端交回的那一行上屏，再按 GET /alerts 重读一次，回执只写读回来的那一句。 */
async function runDisposal(item, action) {
  if (!item || !item.id) return
  // 最后一道闸：这一格根本出发不了这枚动作（状态词认不下、已经是终态、后端那一格只从别处出发），
  // 就不发这发注定被 409 拒掉的 POST。为什么点不动，屏上由 rowActionNote 那句话说给客户听。
  if (!Array.isArray(item.actions) || item.actions.indexOf(action) < 0) return
  const assignee = action === 'assign' ? String(assignDrafts.value[item.id] || '').trim() : ''
  disposing.value = action + ':' + item.id
  actionFailure.value = null
  actionReceipt.value = null
  let failure = null
  let serverRow = null
  let receipt = ''
  try {
    const verdict = await disposeAlert(item.id, action, assignee)
    receipt = verdict.receipt
    serverRow = verdict.row
  } catch (err) {
    failure = { id: item.id, action, message: item.message, ...disposalFailureView(err, action) }
  }
  disposing.value = ''
  // 顺序要紧：loadAlerts() 一进去就把上一轮的回执与失败条擦了，所以必须先重读、再把这一发的话
  // 留在屏上。反过来写的后果是 404 / 409 点完像什么都没发生——那张脸被自己的重读顶掉了。
  if (failure) {
    // 404 与 409 说的是「屏上这一版已经不作数」：先重读，别拿旧的一格继续点。
    if (failure.reload) await loadAlerts()
    actionFailure.value = failure
    return
  }
  if (receipt === 'invalid') {
    await loadAlerts()
    actionFailure.value = { id: item.id, action, message: item.message, ...INVALID_ID_FAILURE }
    return
  }
  if (serverRow) {
    const rows = alerts.value.slice()
    const at = rows.findIndex(row => row.id === serverRow.id)
    if (at >= 0) {
      rows[at] = serverRow
      alerts.value = rows
    }
  }
  await loadAlerts()
  if (alertsFailure.value) {
    // 写成了却读不回来：仍是降级那张脸，不宣布成功，也不说这一条没有了。
    actionReceipt.value = { id: item.id, message: item.message, ...DISPOSED_BUT_UNREADABLE }
    return
  }
  const readBack = alerts.value.find(row => row.id === item.id) || serverRow
  actionReceipt.value = { id: item.id, message: item.message, ...disposalOutcomeView(action, readBack) }
  if (action === 'assign') {
    assignDrafts.value = { ...assignDrafts.value, [item.id]: '' }
    assignOpen.value = ''
  }
}

/** 回执与失败条都得点名是哪一条：只说一句「操作成功」，等于把刚发生的事擦成一句废话。 */
function actionTargetText(record) {
  if (!record) return ''

  const which = record.id ? '（编号 ' + record.id + '）' : '（这一行没有可用的编号）'
  return '说的是这一条' + which + '：' + record.message
}

/** 失败卡上的「再试一次」：只对还点得动的那一行、那一枚动作重发一次，不拿旧引用盲投。 */
function retryDisposal() {
  const record = actionFailure.value
  if (!record) return
  const item = alerts.value.find(row => row.id === record.id)
  actionFailure.value = null
  if (!item || !canDispose(record.action, item)) return
  runDisposal(item, record.action)
}

/** 动作点不动，屏上得说清为什么：终态、状态词认不下、编号读不出，是三句不同的话。 */
function rowActionNote(item) {
  if (!item) return ''
  if (!item.addressable) return '这一行没有可用的编号，确认、关闭与指派都发不出去。'
  if (!item.statusKnown) return '后端回来的处置状态词前端认不下，动作先不给点：认不下就不猜。'
  if (item.status === 'closed') return '已关闭是终态：这一条到此为止，确认、关闭与指派都不再发出。'
  return ''
}

onMounted(loadAll)
</script>

<template>
  <div class="panel-shell" data-testid="alerts-panel">
    <header class="panel-head">
      <div>
        <div class="eyebrow">服务端告警账本</div>
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
              <div class="alert-ledger" data-testid="alert-ledger">
                <p class="ledger-line" data-testid="alert-status-line">
                  <span
                    class="chip"
                    :data-status="item.statusKnown ? item.status : 'unknown'"
                  >{{ item.statusLabel }}</span>
                  <span class="ledger-dept">{{ item.departmentText }}</span>
                </p>
                <p
                  v-for="line in item.ledger"
                  :key="line.key"
                  class="ledger-line"
                  :data-recorded="line.recorded ? 'yes' : 'no'"
                  data-testid="alert-ledger-line"
                >
                  <span class="ledger-label">{{ line.label }}</span>
                  <span class="ledger-who">{{ line.who }}</span>
                  <span v-if="line.to" class="ledger-to">派给 {{ line.to }}</span>
                  <span class="ledger-at">{{ line.at }}</span>
                </p>
              </div>
              <div class="alert-actions" data-testid="alert-actions">
                <UiButton
                  size="sm"
                  variant="secondary"
                  :disabled="!canDispose('ack', item)"
                  :loading="disposalBusy('ack', item)"
                  label="确认"
                  :title="ALERT_ACTION_NOTES.ack"
                  data-testid="alert-ack"
                  @click="runDisposal(item, 'ack')"
                />
                <UiButton
                  size="sm"
                  variant="secondary"
                  :disabled="!canDispose('close', item)"
                  :loading="disposalBusy('close', item)"
                  :label="closeLabel(item)"
                  :title="ALERT_ACTION_NOTES.close"
                  data-testid="alert-close"
                  @click="askCloseAlert(item)"
                />
                <UiButton
                  size="sm"
                  variant="ghost"
                  :disabled="!canDispose('assign', item)"
                  :label="assigningTo(item) ? '收起指派' : '指派'"
                  :title="ALERT_ACTION_NOTES.assign"
                  data-testid="alert-assign"
                  @click="openAssign(item)"
                />
              </div>
              <p v-if="rowActionNote(item)" class="alert-note">{{ rowActionNote(item) }}</p>
              <div v-if="assigningTo(item)" class="assign-form" data-testid="assign-form">
                <UiField
                  :model-value="assignDrafts[item.id] || ''"
                  label="派给谁"
                  hint="填对方登录用的用户名。他得管得了告警，且这一条在他的可见范围里，否则后端不认这次转派。"
                  :error="assignErrors[item.id] || ''"
                  :disabled="disposing !== ''"
                  @update:model-value="value => setAssignDraft(item, value)"
                />
                <UiButton
                  size="sm"
                  variant="primary"
                  :loading="disposalBusy('assign', item)"
                  :disabled="disposing !== ''"
                  label="派给这个人"
                  data-testid="alert-assign-send"
                  @click="confirmAssign(item)"
                />
              </div>
            </div>
            <div class="record-meta">
              <span v-if="item.createdAt" class="chip">{{ item.createdAt }}</span>
              <span v-if="item.ruleId" class="chip">规则 #{{ item.ruleId }}</span>
            </div>
          </article>
        </div>

        <!--
          处置的回执与失败条挂在卡层而不是行内：404 / 409 / 写成却读不回来这三件事都会顺手重读列表，
          行内那一格可能已经不在了——回执跟着行一起消失，就等于把刚发生的事擦掉。
          条上点名是哪一条（编号 + 原文），员工读到的仍然是一行的事，不是一句无处着落的 toast。
        -->
        <div v-if="actionFailure" class="alert-action-error" data-testid="alert-action-failure">
          <UiErrorState
            :title="actionFailure.title"
            :description="actionFailure.description"
            :code-label="actionFailure.codeLabel"
            :retryable="actionFailure.retryable"
            retry-text="再试这一件"
            :busy="disposing !== ''"
            dense
            @retry="retryDisposal"
          />
          <p class="alert-note">{{ actionTargetText(actionFailure) }}</p>
        </div>
        <div v-else-if="actionReceipt" class="receipt" data-testid="alert-action-receipt" :data-kind="actionReceipt.kind">
          <strong>{{ actionReceipt.title }}</strong>
          <p>{{ actionReceipt.detail }}</p>
          <p class="alert-note">{{ actionTargetText(actionReceipt) }}</p>
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

/* 处置台账三行：谁、什么时候。缺的那一格写「未记录」，不摆空白，也不涂成 0。 */
.alert-ledger {
  display: grid;
  gap: var(--s-1);
  margin-top: var(--s-2);
}

.ledger-line {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--s-2);
  margin: 0;
  color: var(--muted);
  font-size: var(--t-xs);
}

.ledger-label,
.ledger-dept {
  color: var(--ink-faint);
}

.ledger-who,
.ledger-at {
  font-family: var(--font-mono);
}

.ledger-line[data-recorded='no'] .ledger-who,
.ledger-line[data-recorded='no'] .ledger-at {
  color: var(--ink-faint);
}

.chip[data-status='open'] {
  color: var(--cyan);
}

.chip[data-status='acknowledged'] {
  color: var(--amber);
}

.chip[data-status='closed'],
.chip[data-status='unknown'] {
  color: var(--ink-faint);
}

.alert-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
  margin-top: var(--s-2);
}

.assign-form {
  display: grid;
  gap: var(--s-2);
  margin-top: var(--s-2);
}

.alert-action-error {
  margin-top: var(--s-2);
}

.receipt[data-kind='degraded'] {
  border-left-color: var(--amber);
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
