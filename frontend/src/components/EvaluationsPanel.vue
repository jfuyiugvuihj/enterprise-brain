<!--
  R505 · 「评测报告」屏壳：给 GET /api/v1/evaluations 第一枚消费者

  欠的那一格不在后端：读腿早就在树（app/api/v1/observability.py 里那条 GET /evaluations），
  前端一个消费者都没有（基点 85572c1 现取：rg -nF "/evaluations" frontend/src 除 </slot> 外 0 枚）。
  这一枚壳接的就是它，零新增端点、零新增字段、零算术 —— 判码、归脸、句子全在 src/lib/evaluations.js。

  🔴 这一屏的判据是 B：不许做成能触发跑分的样子。
    ① 载荷自己就写着 execution.runs_on_request=false 与 reason 与 command_template —— 三样逐格端出来，
       命令只读展示（放在 <code> 里，可以整段选中复制到终端），屏上没有一枚「立即运行」按钮，
       也没有一枚按下去什么都不会发生的假控件（R32 那条规矩）。
    ② reports 为空时后端答 status=no_reports：这一屏走空态脸（UiEmptyState），
       说「这台机器上一份评测报告都还没有」，绝不画一枚 0 分，也绝不说「评测一切正常」。
    ③ 一份报告自己读不读得出来是它的事：ok / unreadable / too_large 三档分开说，
       metrics 是空对象那一行就写「这份文件没交出指标」，不拿零冒充读数。

  入口形状逐字照 /admin 与 /traces 的先例：primary:false + administratorOnly:true，加这一屏不改壳层
  一个字。这一屏那道闸与另两屏不同源：它先要系统管理员角色，再要评测读取这一项权限。
  🔴 侧栏按客户端角色派生入口这件事本身仍是假权限（缺口清单 §4.3 b 那笔没销的账）：这一屏只是
  不谎称自己解决了它，能不能读只在服务端那道闸上说。

  三张失败脸分开留名（判据 D）：403 / 503 / 500 各一张，另加 401 与「回包读不出形状」。
  零新色值（排版只用 theme.css 既有类）、零枚裸 <button>、动作全部走 ui 原语。
-->
<script>
export default { name: 'EvaluationsPanel' }
</script>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import {
  EVAL_FACE_EMPTY,
  EVAL_FACE_LOADING,
  EVAL_FACE_READY,
  EVAL_LOADING_TEXT,
  evaluationsFaceView,
  evaluationsBlankView,
  loadEvaluations,
} from '../lib/evaluations'
import { UiButton, UiEmptyState, UiErrorState, UiField, UiLoadingState, UiTable } from './ui'

/** 取数闸门（与 R316 / R399 / R494 同一手法）：每次读领一号，作废用旧号。 */
let evaluationsToken = 0

const view = ref(evaluationsBlankView())
const busy = ref(false)
/** 表单里只躺一枚 limit：它是这份回执唯一一枚查询参数，空着就是不带。 */
const form = reactive({ limit: '' })

const loading = computed(() => view.value.face === EVAL_FACE_LOADING)
const ready = computed(() => view.value.face === EVAL_FACE_READY)
const isEmpty = computed(() => view.value.face === EVAL_FACE_EMPTY)
const failure = computed(() => {
  if (loading.value || ready.value || isEmpty.value) return null
  return evaluationsFaceView(view.value)
})
const rows = computed(() => (ready.value ? view.value.rows || [] : []))
const suites = computed(() => (ready.value || isEmpty.value ? view.value.suites || [] : []))
const execution = computed(() => view.value.execution || {})
const limits = computed(() => view.value.limits || {})
const head = computed(() => view.value.head || {})

const reportColumns = [
  { key: 'id', label: '哪一份报告' },
  { key: 'sourceText', label: '谁要的这份' },
  { key: 'statusText', label: '这份文件自己' },
  { key: 'sizeText', label: '多大' },
  { key: 'modifiedText', label: '改动于' },
  { key: 'categoryText', label: '分类几枚' },
]

const suiteColumns = [
  { key: 'id', label: '哪一套评测集' },
  { key: 'existsText', label: '这台机器上有吗' },
  { key: 'caseCountText', label: '几道题' },
  { key: 'categoriesText', label: '题目分类' },
  { key: 'truncatedText', label: '这一发读全了吗' },
]

async function loadIntoView() {
  const mine = ++evaluationsToken
  busy.value = true
  view.value = evaluationsBlankView(EVAL_FACE_LOADING)
  const next = await loadEvaluations(form.limit)
  if (mine !== evaluationsToken) return
  view.value = next
  busy.value = false
}

onMounted(loadIntoView)
onUnmounted(() => { evaluationsToken += 1 })

function textOrUnrecorded(value) {
  const raw = typeof value === 'string' ? value.trim() : ''
  return raw || '未记录'
}

function memberText(list) {
  return Array.isArray(list) && list.length ? list.join('、') : '没交出分类'
}

/** 指标那一栏：键名就是后端那一格自己的名字，这里不翻译、不重排、不四舍五入成另一位数。 */
function metricText(metrics) {
  if (!Array.isArray(metrics) || !metrics.length) return '这份文件没交出任何指标'
  return metrics.map(item => item.key + ' = ' + (item.isList ? item.listText : item.valueText)).join('；')
}
</script>

<template>
  <div class="panel-shell" data-testid="evaluations-panel" :data-face="view.face">
    <header class="panel-head">
      <div>
        <span class="eyebrow">这台机器上存着的评测报告</span>
        <p>
          这一屏只读：它列的是已经躺在报告目录里的评测结果，以及服务端为「为什么这一屏不能跑分」给的那句原话。
          屏上每一个数字都是回包里那一格的读数，这里不平均、不排名，也不拿零冒充没量到的东西。
        </p>
      </div>
      <div class="eval-tools">
        <UiField
          v-model="form.limit"
          label="最多列几份（留空就是不带这一格）"
          hint="这一枚数只是这份回执的条数上限；真要改它，重新读一次就带上"
          type="number"
        />
        <UiButton
          label="重新读取"
          variant="secondary"
          size="sm"
          :disabled="busy"
          data-testid="reload-evaluations"
          @click="loadIntoView"
        />
      </div>
    </header>

    <UiLoadingState v-if="loading" :label="EVAL_LOADING_TEXT" :rows="3" data-testid="evaluations-loading" />

    <UiErrorState
      v-else-if="failure"
      :title="failure.title"
      :description="failure.description"
      :code-label="failure.codeLabel"
      :retryable="failure.retryable"
      :busy="busy"
      data-testid="evaluations-failure"
      @retry="loadIntoView"
    />

    <template v-else>
      <!-- 这一屏的第一格就是「它不跑分」：三样如实端出来，命令只读。 -->
      <section class="panel-card" data-testid="evaluations-execution">
        <div class="section-head">
          <span class="eyebrow">这一屏会不会跑一轮评测</span>
          <span class="demo-note" data-testid="eval-runs">{{ textOrUnrecorded(execution.runsText) }}</span>
        </div>
        <p data-testid="eval-reason">{{ textOrUnrecorded(execution.reason) }}</p>
        <p class="demo-note">要跑评测请在服务器上按这一句敲（这里只给读，不给按）：</p>
        <code class="eval-command" data-testid="eval-command">{{ textOrUnrecorded(execution.commandTemplate) }}</code>
        <p class="demo-note" data-testid="eval-report-module">
          跑完之后负责把结果落成报告的那一格：{{ textOrUnrecorded(execution.reportModule) }}
        </p>
      </section>

      <!-- 这份回执读了什么：状态、时间、总数与是不是把清单截短了，四格分开说。 -->
      <section class="panel-card" data-testid="evaluations-head">
        <div class="section-head">
          <span class="eyebrow">这一发回执自己怎么说</span>
          <span class="demo-note" data-testid="eval-truncated">{{ textOrUnrecorded(head.truncatedText) }}</span>
        </div>
        <dl class="eval-facts">
          <div><dt>状态</dt><dd data-testid="eval-status">{{ textOrUnrecorded(head.status) }}</dd></div>
          <div><dt>生成于</dt><dd>{{ textOrUnrecorded(head.generatedText) }}</dd></div>
          <div><dt>报告目录里共有</dt><dd data-testid="eval-total">{{ textOrUnrecorded(head.reportsTotal) }}</dd></div>
          <div><dt>这次是谁读的</dt><dd>{{ textOrUnrecorded(head.requestedBy) }}</dd></div>
          <div><dt>这一发用的上限</dt><dd>{{ textOrUnrecorded(limits.appliedLimit) }}</dd></div>
          <div><dt>请求里带的那一枚</dt><dd data-testid="eval-requested-limit">{{ textOrUnrecorded(limits.requestedLimit) }}</dd></div>
          <div><dt>有没有被夹住</dt><dd data-testid="eval-clamped">{{ textOrUnrecorded(limits.clampedText) }}</dd></div>
          <div><dt>出口最多给</dt><dd>{{ textOrUnrecorded(limits.maxReports) }}</dd></div>
        </dl>
      </section>

      <section class="panel-card" data-testid="evaluations-reports">
        <div class="section-head">
          <span class="eyebrow">存着的报告</span>
          <span class="demo-note">一份报告一行；它自己读不读得出来由它那一格说，屏上不替它圆。</span>
        </div>
        <!-- 空报告走这一屏自己的空态脸（判据 B 的②）：它说的是「一份都没有」，不是零分。 -->
        <UiEmptyState
          v-if="isEmpty"
          :title="view.title"
          :description="view.description"
          data-testid="evaluations-empty"
        />
        <UiTable
          v-else
          :columns="reportColumns"
          :rows="rows"
          row-key="id"
          aria-label="存着的评测报告"
          data-testid="eval-reports-table"
        />
        <ul v-if="!isEmpty" class="eval-metrics">
          <li v-for="report in rows" :key="'metrics-' + report.id" data-testid="eval-report-metrics">
            <span>{{ report.id }}</span>
            <span class="demo-note">{{ report.path }}</span>
            <p>{{ metricText(report.metrics) }}</p>
          </li>
        </ul>
      </section>

      <section class="panel-card" data-testid="evaluations-sets">
        <div class="section-head">
          <span class="eyebrow">配置的评测集</span>
          <span class="demo-note">
            文件在这台机器上不存在，那一行的题数就是零 —— 这句话说的是「没这份文件」，不是「零道题全错」。
          </span>
        </div>
        <UiTable
          :columns="suiteColumns"
          :rows="suites.map(suite => ({ ...suite, categoriesText: memberText(suite.categories) }))"
          row-key="id"
          aria-label="配置的评测集"
          data-testid="eval-sets-table"
        />
      </section>
    </template>
  </div>
</template>

<style scoped>
.eval-tools {
  display: grid;
  gap: 8px;
  justify-items: end;
}

.eval-facts {
  display: grid;
  gap: 6px;
  margin: 0;
}

.eval-metrics {
  display: grid;
  gap: 8px;
  margin: 12px 0 0;
  padding-left: 20px;
}

.eval-command {
  display: block;
  overflow-wrap: anywhere;
  color: var(--text-1);
  font-family: var(--font-mono);
  user-select: all;
}
</style>
