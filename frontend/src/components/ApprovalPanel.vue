<script>
// R247 判据①：员工在面板间来回切时 Vue 会反复 unmount/mount，而每一发预审在背后都是
// 一次真知识库检索（app/approval/assistant.py 的 resolve_standard_from_knowledge_base），
// 知识库不在线时那一发直接回 503。所以这里放一枚模块级的一次性缓存：同一组自查参数在
// 同一枚 app（= 一次页面会话）里只真发一次，后来的挂载直接复用那一次的读数。
// 键挂 app 而不是纯全局：刷新页面是一枚新 app，本来就该重取新鲜数 —— 把上一次会话的
// 读数端给员工才是假话。参数改了是另一组问题，照实重取；失败的读数不进缓存，没有可复用的数。
const precheckMemo = new WeakMap()
</script>

<script setup>
import { computed, getCurrentInstance, onMounted, ref, watch } from 'vue'
import { api } from '../lib/api'
import { DEPARTMENT_KEY, errorDetail, isPermissionDenied } from '../lib/http'
import { errorCodeOf, isRetryable, normalizeError } from '../lib/errcodes'
import { demoForm } from '../devFixtures/approval-demo'
import { UiButton, UiEmptyState, UiErrorState } from './ui'
import HitlPendingPanel from './hitl/HitlPendingPanel.vue'

const props = defineProps({ mode: { type: String, default: 'all' } })
const showPending = computed(() => props.mode !== 'selfcheck')
const showSelfcheck = computed(() => props.mode !== 'pending')

// R40 判据③：比较用的标准不由这一屏持有。这枚值是发给后端的【口径】，不是一个数 ——
// 它要求服务端去知识库里把标准检索出来（app/approval/assistant.py 的
// resolve_standard_from_knowledge_base），取不到就回 null，由屏上如实说「未给出」。
// 本文件里从此不许再出现 standard 常量：那等于把客户的制度阈值抄死在界面里。
const STANDARD_SOURCE_AUTO = 'auto_from_knowledge_base'

// R247 判据②：知识库检索不到那一个标准时，后端不猜数，直接回 503 + 这一枚稳定码
// （app/api/v1/intelligence.py 的 approval_precheck）。它既不是「跑挂了」也不是「没有数据」，
// 是「此刻取不到比的那个数」—— 所以单独一张脸，与通用失败分开画（无权限 / 空 / 降级 / 错误）。
const KB_UNAVAILABLE_CODE = 'retrieval_unavailable'

// R277 判据①：部门那一格被拒时后端吐的是 DEPARTMENT_SELF_REPORT_DENIED（枚名见下），
// 出处 app/common/authorization.py::verify_department_self_report。R270 已把它收进字典并
// 折向 validation_error，所以它今天【不再是】isPermissionDenied 那一张脸：这是一次被拒的
// 请求，不是一格可计算的范围，也不是一句「你没权限」。
const DEPARTMENT_OVERRIDE_CODE = 'department_override_denied'

// 表单会改写这些值，所以拷一份，避免面板把模块常量改掉。
// evidence 不再种子假文件名：auto 口径下服务端用检索出处整条覆盖它，填了也上不了屏。
//
// 🔴 缺口 G09 的根就在这枚播种上：上一版常量里连部门一起填好，而且填的是【别人的】部门
// （演示值写死一枚），于是一个不属于它的账号一进这一屏就换来一次 403，界面再把那枚 403 画成
// 「没有权限做审批预审」。部门现在只可能是两样东西：登录响应里那枚本人部门（lib/http.js 存成
// DEPARTMENT_KEY），或者空着 —— 后端 verify_department_self_report 放行这两条，空着由服务端
// 按 principal 定，界面从此不替员工挑部门。
function ownDepartment() {
  try {
    return localStorage.getItem(DEPARTMENT_KEY) || ''
  } catch (_) {
    // 读不到存储不等于「这个账号没有部门」：SSR 首屏与隐私模式都会走到这里。留空是后端
    // 明确放行的一条路，所以宁可空着让服务端补，也不拿一枚猜来的部门去撞那道闸。
    return ''
  }
}
const form = ref({ ...demoForm, department: ownDepartment() })
const result = ref(null)
const loading = ref(false)
const error = ref('')
// 面板 onMounted 自己发那一发预审（R247 之后是「一次页面会话里最多真发一次」，见上面那枚缓存）。
// failed 把「跑失败了」与「还没跑」分开（R1c 同一判据）：失败不许画成空态那张脸。
const failed = ref(false)
const denied = ref(false)
// R277 判据②之二：这颗「重新预审」的有无改吃字典那枚 retryable，不再跟 !denied 走。
// 跟 !denied 会说谎 —— 它断言「只要有权限，重发就有救」，而 department_override_denied
// 原样重发必然再被拒（字典明写 retryable:false），摆出来就是一枚死控件（G20 那一族）。
// 出口是 lib/errcodes.js::isRetryable；改回即红的钉在本单 r277 件 ②之二。
const failureRetryable = ref(true)
// R277 判据①：「部门填的不是你的」既不是没权限也不是跑挂了，单独一格，不与那两张脸共用。
const departmentRefused = ref(false)
// R247 判据②：降级（知识库此刻取不到标准）与错误（这一发压根没跑完）是两张脸，不共用一句话。
const degraded = ref(false)
// R247 判据①：这一屏的读数取于何时、是不是复用来的 —— 两格都要上屏，不许含糊。
const readingAt = ref('')
const reusedReading = ref(false)

// 下面四枚都是【读响应】的派生值：界面无从知道标准是多少，所以只能说服务端回了什么。
// 服务端没回口径时不替它编出处 —— 那一格宁可说一句没回话，也不画一张像结论的脸。
const standardFromServer = computed(
  () => result.value !== null && result.value.standard_source === STANDARD_SOURCE_AUTO,
)
const standardGiven = computed(() => standardFromServer.value && result.value.standard != null)
const standardEvidence = computed(() => (standardFromServer.value && result.value.standard_evidence) || [])
const standardLabel = computed(() => {
  if (!standardFromServer.value) return '服务端没回取用口径'
  return standardGiven.value ? result.value.standard : '服务端未给出'
})

// 失败那一张脸的说法：部门被拒 / 无权限 / 降级 / 真失败各说各的，全部是人话，不带码名。
const failureTitle = computed(() => {
  if (departmentRefused.value) return '部门那一格填的不是你的部门'
  if (denied.value) return '没有权限做审批预审'
  if (degraded.value) return '知识库取不到报销标准'
  return '预审没有跑完'
})
const failureCopy = computed(() => {
  if (degraded.value) {
    return '这一屏没有拿到比的那个数，所以说不出超没超标。它不是「没有超标」，也不是「还在跑」，是此刻取不到；取到那个数之后再点「重新预审」，那一发才是新读数。'
  }
  return error.value
})

// 读数只报钟点：这一屏装不出秒级精度，报个大概时间比装作精确诚实。
const pad2 = value => String(value).padStart(2, '0')
const clockOf = stamp => {
  const date = new Date(stamp)
  return pad2(date.getHours()) + ':' + pad2(date.getMinutes())
}
const readingLine = computed(() => {
  if (!readingAt.value) return ''
  if (reusedReading.value) {
    return '这是上次自查留下的读数，取于 ' + readingAt.value + ' —— 切回这一屏没有重新问知识库。要新鲜的数就点「重新自查」。'
  }
  return '这是刚查出来的读数，取于 ' + readingAt.value + '。'
})

// 缓存归这一枚 app：一次页面会话一份，挂在这枚实例所属的 app 对象上。
const ownerApp = getCurrentInstance()?.appContext.app
function memoBucket() {
  if (!ownerApp) return null
  let bucket = precheckMemo.get(ownerApp)
  if (!bucket) {
    bucket = new Map()
    precheckMemo.set(ownerApp, bucket)
  }
  return bucket
}

function applyReusedReading(hit) {
  result.value = hit.result
  error.value = ''
  failed.value = false
  denied.value = false
  failureRetryable.value = true
  departmentRefused.value = false
  degraded.value = false
  loading.value = false
  readingAt.value = clockOf(hit.fetchedAt)
  reusedReading.value = true
}

async function submitCheck(force = false) {
  const payload = { ...form.value, standard_source: STANDARD_SOURCE_AUTO }
  const signature = [payload.amount, payload.department, payload.expense_type].join('|')
  if (force !== true) {
    const hit = memoBucket()?.get(signature)
    if (hit) {
      // 复用上次读数，不再打知识库：上屏的是「上次结果 + 取其时间」，不是新鲜结论。
      applyReusedReading(hit)
      return
    }
  }
  loading.value = true
  error.value = ''
  failed.value = false
  denied.value = false
  failureRetryable.value = true
  departmentRefused.value = false
  degraded.value = false
  readingAt.value = ''
  reusedReading.value = false
  try {
    const response = await api.post('/approval/precheck', payload)
    result.value = response.data
    const fetchedAt = Date.now()
    memoBucket()?.set(signature, { result: response.data, fetchedAt })
    readingAt.value = clockOf(fetchedAt)
  } catch (err) {
    // 判据⑤：句子一律出自字典，这一屏不再自己编一句「当前账号没有做预审的权限」——
    // 同一枚 403 今天按权限维度与按部门维度各有说法（app/common/policy.py 那一族原因码经
    // lib/errcodes.js 分开讲），界面替它挑一种因由就是说半句真话。
    const verdict = normalizeError(err)
    denied.value = isPermissionDenied(err)
    // 能不能重发由字典说（denied 只管「这张脸叫什么」，它管不了「按了有没有用」）。
    failureRetryable.value = isRetryable(err)
    departmentRefused.value = !denied.value && verdict.rawCode === DEPARTMENT_OVERRIDE_CODE
    degraded.value = !denied.value && !departmentRefused.value && errorCodeOf(err) === KB_UNAVAILABLE_CODE
    failed.value = true
    result.value = null
    // 句子出处只有一处：R281 把「形状 2 的信封 message 占人话位」改判之后，errorDetail() 对
    // department_override_denied（LEGACY_ALIASES 在册）出的已经是字典那句中文，后端那句英文改走
    // rawMessage。原先这两行的三元是给那个洞打的现场补丁，今天补丁与 errorDetail 逐字同一
    // （等值性由 lib/__tests__/r281-dictionary-voice.test.js:155 钉着），留着就是给同一句话开第二条出口。
    // departmentRefused 本身照留：frontend/src/lib/__tests__/r281-dictionary-voice.test.js:174 它驱动失败卡那张脸（frontend/src/lib/__tests__/r281-dictionary-voice.test.js:89 的标题），管的是脸不是句子。
    error.value = errorDetail(err, '审批预审失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => { if (showSelfcheck.value) submitCheck() })
watch(() => props.mode, mode => { if (mode === 'selfcheck') submitCheck() })
</script>

<template>
  <div class="panel-shell" data-testid="approval-panel" :data-demo="showSelfcheck ? 'fixtures' : undefined">
    <header class="panel-head">
      <div>
        <h3>{{ showPending ? '待办事项' : '费用制度自查' }}</h3>
        <p v-if="showPending">查看真实待确认操作。可以批准、驳回，或返回对应对话核对详情；执行失败会单独提示。</p>
        <p v-if="showSelfcheck">按知识库中的费用标准自查参数。自查仅给出建议，不办理正式业务审批。</p>
      </div>
    </header>

    <!-- 这句话已经过时：R13 那半条端点早就落了地，R168 把「等你拍板」那一问从对话流里抽出来，
         接的就是 GET /hitl/pending + POST /approve 两条真端点 —— 也就是下面这一整块。 -->
    <HitlPendingPanel v-if="showPending" />

    <template v-if="showSelfcheck">

    <!-- 这一行以下才是一台拿演示初始值预演的计算器：上方那一块待办不是它的一部分。 -->
    <aside class="demo-flag-row" data-testid="approval-demo-flag">
      <span class="demo-flag">演示数据</span>
      <span class="demo-note">下方金额 {{ form.amount }}、费用类型 {{ form.expense_type }} 为演示初始值，请按实际情况填写。部门取自你这个账号在系统里登记的部门；报销标准由知识库提供，未查到时会明确提示。自查不会生成审批记录；待确认操作请到“待办事项”查看。</span>
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
      <p>真实待确认操作在“待办事项”或对应对话中处理，本工具不参与处置。</p>
    </aside>

    <div class="panel-grid">
      <section class="panel-card">
        <div class="section-head"><h4>自查参数</h4></div>
        <div class="form-grid">
          <label><span>金额</span><input v-model.number="form.amount" type="number" /></label>
          <label><span>部门</span><input v-model="form.department" /></label>
          <label><span>费用类型</span><input v-model="form.expense_type" /></label>
        </div>
        <p class="source-hint" data-testid="approval-standard-source-hint">
          报销标准与依据由系统从知识库查询，无法在此手动修改。
        </p>
        <div class="actions">
          <UiButton class="primary-btn" variant="primary" :loading="loading" :label="loading ? '正在自查' : '重新自查'" data-testid="run-approval" @click="submitCheck(true)" />
        </div>
      </section>

      <section class="panel-card">
        <div class="section-head"><h4>自查结论</h4></div>
        <!-- R277 判据②之二已结清（总控落笔，同批改口 panel-states.test.js 钉的表达式）：这颗
             「重新预审」的有无改吃字典那枚 retryable，不再跟 !denied 走。面板底部那颗「重新自查」
             是员工自己发起的动作，与字典无关，一直可用。 -->
        <UiErrorState
          v-if="failed"
          :title="failureTitle"
          :description="failureCopy"
          :retryable="failureRetryable"
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
          <p v-if="readingLine" class="reading-age" data-testid="approval-reading-age">{{ readingLine }}</p>
          <div class="result-grid">
            <span>金额：{{ result.amount }}</span>
            <span data-testid="approval-standard">标准：{{ standardLabel }}</span>
            <span data-testid="approval-excess">超出：{{ result.excess_amount == null ? '算不出' : result.excess_amount }}</span>
            <span data-testid="approval-ratio">超比：{{ result.excess_ratio == null ? '算不出' : (Number(result.excess_ratio) * 100).toFixed(1) + '%' }}</span>
          </div>
          <p class="source-line" data-testid="approval-standard-source" :data-standard-source="result.standard_source || ''">
            {{ standardGiven ? '标准来自知识库。' : '未从知识库取得可用标准，不能判断是否超标。' }}
          </p>
          <div v-if="standardEvidence.length" class="chips" data-testid="approval-standard-evidence">
            <span v-for="item in standardEvidence" :key="item" class="chip">{{ item }}</span>
          </div>
          <p class="recommendation">{{ result.recommendation }}</p>
        </div>
      </section>
    </div>
    </template>
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

.source-hint,
.source-line {
  margin: var(--s-2) 0 0;
  color: var(--muted);
  font-size: var(--t-xs);
  line-height: 1.6;
}

.source-line {
  padding: var(--s-2);
  border: 1px dashed var(--line-strong);
  border-radius: var(--radius-sm);
}

.reading-age {
  margin: 0;
  padding: var(--s-2);
  color: var(--muted);
  font-size: var(--t-xs);
  line-height: 1.6;
  border-left: 2px solid var(--line-strong);
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
