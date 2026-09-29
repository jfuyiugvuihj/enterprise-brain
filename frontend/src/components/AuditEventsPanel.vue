<!--
  R505 · 「审计事件」屏壳：给 GET /api/v1/audit/events 第一枚消费者

  欠的那一格不在后端：读腿早就在树（app/api/v1/observability.py 里那条 GET /audit/events），
  前端一个消费者都没有（基点 85572c1 现取：rg -nF "/audit/events" frontend/src 除 </slot> 外 0 枚）。
  这一枚壳接的就是它，零新增端点、零新增字段、零计数算术 —— 判码、归脸、句子全在 src/lib/auditEvents.js。

  🔴 这一屏的判据是 C：不许把截断藏起来。回包把「这一页到底是全部还是头一段」拆成六格交出来，
  屏上逐格印：filters（服务端真正用上的那几枚，空的条件它不留）、event_count（这一页几枚）、
  events_total（按同一条件共几枚）、recorded_total（全库几枚）、truncated（还有没有没列出来的）、
  limits（默认与上限与这次实际用的）。order=newest_first 那一句也原话印出来 ——
  「先看最近这些」是服务端交代的事实，不该由界面猜，也不该在页面上悄悄翻成「这就是全部」。

  另两格要紧的：
   ① 空清单有两句不同的话：条件筛掉了 vs 这台服务一条都没记过。两句话两枚脸，谁都不许冒充谁。
   ② 界面上自己造的「空条件」不发出去：后端会把空串剔掉，屏侧要是塞一枚 username=''，
      回执的 filters 就会读起来像「操作员确实按这一格筛过一次」——那是界面撒的谎。

  入口形状逐字照 /admin 与 /traces 的先例：primary:false + administratorOnly:true，加这一屏不改壳层
  一个字。为什么不挂一级：这一屏过的审计权限只登记在管理员与审计人员名下，给员工摆一枚按下去只会
  说「不向你开放」的按钮就是假控件。🔴 而「侧栏按客户端角色派生入口」这件事本身仍是假权限
  （缺口清单 §4.3 b 那笔没销的账）：这一屏只是不谎称自己解决了它，读不读得到只在服务端那道闸上说。

  三张失败脸分开留名（判据 D）：403 / 503 / 500 各一张，另加 401 与「回包读不出形状」。
  零新色值（排版只用 theme.css 既有类）、零枚裸 <button>、动作全部走 ui 原语。
  🔴 这一屏只有读：后端那条出口自己写着「这一条路由永远不会写一枚 allowed 事件」，
  所以这里没有一枚写腿按钮，也没有一处「补记一条」。
-->
<script>
export default { name: 'AuditEventsPanel' }
</script>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import {
  AUDIT_FACE_EMPTY_FILTERED,
  AUDIT_FACE_EMPTY_RECORDED,
  AUDIT_FACE_LOADING,
  AUDIT_FACE_READY,
  AUDIT_LOADING_TEXT,
  auditFaceView,
  auditBlankView,
  auditFiltersNote,
  loadAuditEvents,
} from '../lib/auditEvents'
import { UiButton, UiEmptyState, UiErrorState, UiField, UiLoadingState, UiTable } from './ui'

/** 取数闸门（与 R316 / R399 / R494 同一手法）：每次读领一号，作废用旧号。 */
let auditToken = 0

const view = ref(auditBlankView())
const busy = ref(false)
/** 三枚过滤条件加一枚上限，逐枚对后端那条出口的四个形参；空着的就是不发。 */
const form = reactive({ username: '', action: '', outcome: '', limit: '' })

const loading = computed(() => view.value.face === AUDIT_FACE_LOADING)
const ready = computed(() => view.value.face === AUDIT_FACE_READY)
const isEmpty = computed(() => [AUDIT_FACE_EMPTY_FILTERED, AUDIT_FACE_EMPTY_RECORDED].includes(view.value.face))
const failure = computed(() => {
  if (loading.value || ready.value || isEmpty.value) return null
  return auditFaceView(view.value)
})
const rows = computed(() => (ready.value ? view.value.rows || [] : []))
const counts = computed(() => view.value.counts || {})
const limits = computed(() => view.value.limits || {})
const filters = computed(() => counts.value.filters || [])
const filtersNote = computed(() => auditFiltersNote(counts.value.filters))

const eventColumns = [
  { key: 'stampText', label: '什么时候' },
  { key: 'username', label: '谁' },
  { key: 'action', label: '做了什么（后端原名）' },
  { key: 'outcomeText', label: '结果' },
  { key: 'resource', label: '对哪一格' },
  { key: 'reason', label: '为这枚结果给的理由' },
  { key: 'requestId', label: '哪一笔请求' },
]

async function loadIntoView() {
  const mine = ++auditToken
  busy.value = true
  view.value = auditBlankView(AUDIT_FACE_LOADING)
  const next = await loadAuditEvents({ ...form })
  if (mine !== auditToken) return
  view.value = next
  busy.value = false
}

/** 「清空条件」是一次真的重读，不是把上一次的回执留在屏上：留着就会读成「筛完还是这些」。 */
function clearFilters() {
  form.username = ''
  form.action = ''
  form.outcome = ''
  form.limit = ''
  loadIntoView()
}

onMounted(loadIntoView)
onUnmounted(() => { auditToken += 1 })

function textOrUnrecorded(value) {
  const raw = typeof value === 'string' ? value.trim() : ''
  return raw || '未记录'
}
</script>

<template>
  <div class="panel-shell" data-testid="audit-panel" :data-face="view.face">
    <header class="panel-head">
      <div>
        <span class="eyebrow">这台服务记下的审计事件</span>
        <p>
          这一屏只读：它列的是服务端自己记下的那一条一条，从最近一条往回列。
          这里没有一处能把事件写进去、改起来或抹掉，也没有一处把「这一页」说成「全部」。
        </p>
      </div>
      <UiButton
        label="重新读取"
        variant="secondary"
        size="sm"
        :disabled="busy"
        data-testid="reload-audit"
        @click="loadIntoView"
      />
    </header>

    <!-- 过滤条件：四格逐枚对后端那四个形参，空着的那几枚整枚不发。 -->
    <section class="panel-card" data-testid="audit-filters-form">
      <div class="section-head">
        <span class="eyebrow">按条件读（可留空）</span>
        <span class="demo-note">三枚条件都是「整字段相等」，不是模糊查找：后端那一条出口就是这么筛的。</span>
      </div>
      <div class="audit-filter-grid">
        <UiField v-model="form.username" label="谁（用户名）" placeholder="留空就是不按这一格筛" />
        <UiField v-model="form.action" label="做了什么（后端原名）" placeholder="留空就是不按这一格筛" />
        <UiField v-model="form.outcome" label="结果（后端原名）" placeholder="留空就是不按这一格筛" />
        <UiField v-model="form.limit" label="最多读几条" type="number" placeholder="留空就用服务端的默认" />
      </div>
      <div class="audit-filter-actions">
        <UiButton label="按这些条件读" variant="primary" size="sm" :loading="busy" data-testid="audit-query" @click="loadIntoView" />
        <UiButton label="清空条件重读" variant="ghost" size="sm" :disabled="busy" data-testid="audit-clear" @click="clearFilters" />
      </div>
    </section>

    <UiLoadingState v-if="loading" :label="AUDIT_LOADING_TEXT" :rows="3" data-testid="audit-loading" />

    <UiErrorState
      v-else-if="failure"
      :title="failure.title"
      :description="failure.description"
      :code-label="failure.codeLabel"
      :retryable="failure.retryable"
      :busy="busy"
      data-testid="audit-failure"
      @retry="loadIntoView"
    />

    <!--
      空清单也要把六枚计数摆在屏上（判据 C）：「这一页零条」与「全库零条」是两句话，
      而它们只有在那三枚计数并排时才分得清 —— 摘掉计数只留一句空态，就是把这件事藏起来。
    -->
    <template v-else>
      <!-- 🔴 判据 C 那一格：这一页是全部还是头一段，六枚读数逐格说，一枚都不合并。 -->
      <section class="panel-card" data-testid="audit-counts">
        <div class="section-head">
          <span class="eyebrow">这一页到底列了多少</span>
          <span class="demo-note" data-testid="audit-order">{{ textOrUnrecorded(counts.orderText) }}</span>
        </div>
        <dl class="audit-facts">
          <div><dt>这一页几条</dt><dd data-testid="audit-event-count">{{ textOrUnrecorded(counts.eventCount) }}</dd></div>
          <div><dt>按这条件共几条</dt><dd data-testid="audit-events-total">{{ textOrUnrecorded(counts.eventsTotal) }}</dd></div>
          <div><dt>全库共几条（筛之前）</dt><dd data-testid="audit-recorded-total">{{ textOrUnrecorded(counts.recordedTotal) }}</dd></div>
          <div><dt>还有没列出来的吗</dt><dd data-testid="audit-truncated">{{ textOrUnrecorded(counts.truncatedText) }}</dd></div>
          <div><dt>这次用的上限</dt><dd>{{ textOrUnrecorded(limits.appliedLimit) }}</dd></div>
          <div><dt>请求里带的那一枚</dt><dd data-testid="audit-requested-limit">{{ textOrUnrecorded(limits.requestedLimit) }}</dd></div>
          <div><dt>有没有被夹住</dt><dd data-testid="audit-clamped">{{ textOrUnrecorded(limits.clampedText) }}</dd></div>
          <div><dt>默认与最多</dt><dd>{{ textOrUnrecorded(limits.defaultLimit) }} / {{ textOrUnrecorded(limits.maxLimit) }}</dd></div>
        </dl>
        <p class="demo-note">
          事件读自{{ textOrUnrecorded(counts.source) }}；这一发是谁读的：{{ textOrUnrecorded(counts.requestedBy) }}。
        </p>
        <!-- 服务端 echo 回来的那一格才是「这次真用上的条件」，界面上的表单不算。 -->
        <p class="demo-note" data-testid="audit-filters-note">{{ filtersNote }}</p>
        <ul class="audit-filter-pairs">
          <li v-for="pair in filters" :key="pair.key" data-testid="audit-filter-pair">
            {{ pair.key }} = {{ textOrUnrecorded(pair.value) }}
          </li>
        </ul>
      </section>

      <section class="panel-card" data-testid="audit-events-card" :data-face="view.face">
        <UiEmptyState
          v-if="isEmpty"
          :title="view.title"
          :description="view.description"
          data-testid="audit-empty"
        />
        <div v-else class="section-head">
          <span class="eyebrow">最近这些事件</span>
          <span class="demo-note">
            处置结果那一列认的是后端写的那几个值；认不下的原样留在「为这枚结果给的理由」旁边，不翻译、不猜。
          </span>
        </div>
        <UiTable
          v-if="ready"
          :columns="eventColumns"
          :rows="rows"
          row-key="id"
          aria-label="审计事件"
          data-testid="audit-events-table"
        />
      </section>
    </template>
  </div>
</template>

<style scoped>
.audit-filter-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.audit-filter-actions {
  display: flex;
  gap: 12px;
  margin-top: 12px;
}

.audit-facts {
  display: grid;
  gap: 6px;
  margin: 0;
}

.audit-filter-pairs {
  display: grid;
  gap: 4px;
  margin: 8px 0 0;
  padding-left: 20px;
}
</style>
