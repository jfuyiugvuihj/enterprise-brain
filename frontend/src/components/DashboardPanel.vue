<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../lib/api'
import { errorDetail, isPermissionDenied } from '../lib/http'
import { demoInsights, demoRows, demoTrendShape } from '../devFixtures/dashboard-demo'
import { UiEmptyState, UiErrorState } from './ui'

const emit = defineEmits(['goto'])
const loading = ref(true)
const error = ref('')
// 驾驶舱整体取不到 vs 取到了但没权限，是两件事；证据卡自己也可能单独失败（R1c）。
const denied = ref(false)
const evidenceError = ref('')
const evidenceDenied = ref(false)
const dashboard = ref({ metrics: {}, departments: {}, insights: [] })
const metricQuery = ref('住宿费标准')
const metricContext = ref(null)
const documents = ref([])
const dataFiles = ref([])

const quickActions = [
  { id: 'docs', icon: 'M12 4v11M7 9l5-5 5 5M5 20h14', label: '上传文档' },
  { id: 'data', icon: 'M5 5h14v14H5zM8 16V9M12 16V7M16 16v-4', label: '数据分析' },
  { id: 'insights', icon: 'M12 3a4 4 0 0 0-2 7.46V13H8v2h2v2h4v-2h2v-2h-2v-2.54A4 4 0 0 0 12 3Z', label: '新建洞察' },
  { id: 'approval', icon: 'M6 4h12v16H6zM9 9h6M9 13h6M9 17h3M5 12l3 3 6-7', label: '发起审批' },
]

const metricEntries = computed(() => Object.entries(dashboard.value.metrics || {}))
const departmentBars = computed(() => Object.entries(dashboard.value.departments || {})
  .map(([name, metrics]) => ({
    name,
    total: Object.values(metrics).reduce((sum, item) => sum + Number(item || 0), 0),
  }))
  .sort((a, b) => b.total - a.total))
const latestInsights = computed(() => (dashboard.value.insights || []).slice(0, 4))
const totalAmount = computed(() => departmentBars.value.reduce((sum, item) => sum + item.total, 0))
const topDepartment = computed(() => departmentBars.value[0]?.name || '暂无')
const approvalCount = computed(() => latestInsights.value.filter(item => item.severity === 'critical').length)
const kpis = computed(() => [
  {
    id: 'docs',
    label: '文档总量',
    value: documents.value.length.toLocaleString('zh-CN'),
    delta: documents.value.length ? '已解析' : '待上传',
    icon: 'M6 3h8l4 4v14H6zM14 3v5h5M9 13h6M9 17h6',
    tone: 'blue',
    trend: 'line',
  },
  {
    id: 'data',
    label: '数据表',
    value: dataFiles.value.length.toLocaleString('zh-CN'),
    delta: dataFiles.value.length ? '可分析' : '待上传',
    icon: 'M5 5h14v14H5zM8 16V9M12 16V7M16 16v-4',
    tone: 'cyan',
    trend: 'bars',
  },
  {
    id: 'insights',
    label: '智能洞察',
    value: latestInsights.value.length.toLocaleString('zh-CN'),
    delta: latestInsights.value.length ? '待关注' : '暂无',
    icon: 'M12 3a4 4 0 0 0-2 7.46V13H8v2h2v2h4v-2h2v-2h-2v-2.54A4 4 0 0 0 12 3Z',
    tone: 'violet',
    trend: 'wave',
  },
  {
    id: 'approval',
    label: '审批任务',
    value: approvalCount.value.toLocaleString('zh-CN'),
    delta: approvalCount.value ? '需处理' : '暂无待办',
    icon: 'M12 3 19 7v6c0 4-3 6.5-7 8-4-1.5-7-4-7-8V7zM9 12l2 2 4-4',
    tone: 'green',
    trend: 'bars',
  },
])

const trendLines = computed(() => {
  const base = Math.max(totalAmount.value, 1)
  const insightBase = Math.max(latestInsights.value.length * 100, 1)
  const scales = { total: base, insights: insightBase }
  return {
    labels: demoTrendShape.labels,
    series: demoTrendShape.series.map(series => ({
      label: series.label,
      color: series.color,
      values: series.weights.map(weight => Math.round(scales[series.scale] * weight)),
    })),
  }
})

const trendMax = computed(() => Math.max(...trendLines.value.series.flatMap(item => item.values), 1))

function linePoints(values) {
  const width = 720
  const height = 190
  const left = 28
  const top = 12
  const innerWidth = width - left - 10
  const innerHeight = height - top - 20
  return values.map((value, index) => {
    const x = left + (innerWidth * index / Math.max(values.length - 1, 1))
    const y = top + innerHeight - (value / trendMax.value * innerHeight)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

function formatAmount(value) {
  return Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

function documentName(item) {
  return typeof item === 'string' ? item : item.filename
}

async function loadDashboard() {
  loading.value = true
  error.value = ''
  denied.value = false
  try {
    const [dashboardResponse, docsResponse, dataResponse] = await Promise.all([
      api.post('/dashboard', {
        rows: demoRows,
        insights: demoInsights,
      }),
      api.get('/documents/catalog'),
      api.get('/data-files'),
    ])
    dashboard.value = dashboardResponse.data
    documents.value = docsResponse.data.documents || []
    dataFiles.value = dataResponse.data.files || []
  } catch (err) {
    denied.value = isPermissionDenied(err)
    error.value = denied.value
      ? '当前账号没有查看经营总览的权限，请联系管理员开通。'
      : errorDetail(err, '经营驾驶舱加载失败')
  } finally {
    loading.value = false
  }
}

async function lookupMetric() {
  // 这个 catch 原先把错误整个吞掉，于是「查失败了」和「还没查」都长成
  // 「查询指标口径后显示证据」那一句空话——R1(c) 要拆的就是这种同脸。
  evidenceError.value = ''
  evidenceDenied.value = false
  try {
    const response = await api.post('/semantics/match', { question: metricQuery.value })
    metricContext.value = response.data.context || null
  } catch (err) {
    metricContext.value = null
    evidenceDenied.value = isPermissionDenied(err)
    evidenceError.value = evidenceDenied.value
      ? '当前账号没有查询指标口径的权限，请联系管理员开通。'
      : errorDetail(err, '指标口径查询失败')
  }
}

onMounted(async () => {
  await loadDashboard()
  await lookupMetric()
})
</script>

<template>
  <div class="dashboard-panel reference-dashboard" data-testid="dashboard-panel" data-demo="fixtures">
    <div v-if="loading" class="panel-state">正在加载经营数据</div>
    <UiErrorState
      v-else-if="error"
      :title="denied ? '没有权限查看经营总览' : '经营总览没加载出来'"
      :description="error"
      :retryable="!denied"
      retry-text="重新加载"
      :busy="loading"
      @retry="loadDashboard"
    />

    <template v-else>
      <!-- 见 src/devFixtures/README.md：R14 落地前，趋势与异常两块的输入是编造的。 -->
      <aside class="demo-flag-row" data-testid="dashboard-demo-flag">
        <span class="demo-flag">演示数据</span>
        <span class="demo-note">「数据趋势」「异常与风险」以及由它们算出的「智能洞察」「审批任务」两个数字，全部来自前端常量 src/devFixtures/dashboard-demo.js，不来自任何接口；只有「文档总量」「数据表」是真实条数。</span>
      </aside>
      <section class="kpi-grid" data-testid="dashboard-kpis">
        <button
          v-for="item in kpis"
          :key="item.id"
          type="button"
          :class="['reference-kpi', `tone-${item.tone}`]"
          @click="emit('goto', item.id)"
        >
          <span class="kpi-icon">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="item.icon" /></svg>
          </span>
          <span class="kpi-copy">
            <small>{{ item.label }}</small>
            <strong>{{ item.value }}</strong>
            <em>{{ item.delta }}</em>
          </span>
          <span v-if="item.trend === 'bars'" class="kpi-bars"><i></i><i></i><i></i><i></i><i></i></span>
          <svg v-else class="kpi-spark" viewBox="0 0 92 36" aria-hidden="true">
            <path d="M2 28 C16 29 16 13 28 20 S40 27 49 16 S63 18 72 8 S84 11 91 2" />
          </svg>
        </button>
      </section>

      <section class="dashboard-main-grid">
        <article class="reference-card trend-card">
          <header class="reference-card-head">
            <div>
              <h2>数据趋势</h2>
              <p>演示形状 · 最近 7 个观察点 <span class="demo-flag">演示数据</span></p>
            </div>
            <div class="trend-tools">
              <span v-for="series in trendLines.series" :key="series.label">
                <i :style="{ background: series.color }"></i>{{ series.label }}
              </span>
              <button type="button">近7天⌄</button>
            </div>
          </header>
          <div class="trend-chart">
            <div class="chart-y-axis">
              <span>{{ formatAmount(trendMax) }}</span>
              <span>{{ formatAmount(trendMax * .66) }}</span>
              <span>{{ formatAmount(trendMax * .33) }}</span>
              <span>0</span>
            </div>
            <svg viewBox="0 0 720 210" role="img" aria-label="数据趋势图">
              <line v-for="row in 4" :key="row" x1="28" :y1="12 + (row - 1) * 58" x2="710" :y2="12 + (row - 1) * 58" />
              <line v-for="(label, index) in trendLines.labels" :key="label" :x1="28 + index * 113.6" y1="12" :x2="28 + index * 113.6" y2="190" class="vertical-grid" />
              <polyline
                v-for="series in trendLines.series"
                :key="series.label"
                :points="linePoints(series.values)"
                :stroke="series.color"
              />
              <circle
                v-for="(value, index) in trendLines.series[0].values"
                :key="`dot-${index}`"
                :cx="28 + index * 113.6"
                :cy="12 + 158 - (value / trendMax * 158)"
                r="3"
                fill="#1bcfe6"
              />
            </svg>
            <div class="chart-x-axis">
              <span v-for="label in trendLines.labels" :key="label">周{{ label }}</span>
            </div>
          </div>
        </article>

        <article class="reference-card risk-card">
          <header class="reference-card-head">
            <div><h2>异常与风险</h2><p>需要优先处理的业务线索 <span class="demo-flag">演示数据</span></p></div>
            <button type="button" @click="emit('goto', 'insights')">查看全部 ›</button>
          </header>
          <div v-if="latestInsights.length" class="risk-list">
            <button v-for="item in latestInsights" :key="item.title" type="button" class="risk-item" @click="emit('goto', 'insights')">
              <span class="risk-icon">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="m12 4 8 4v5c0 3.8-2.6 6.4-8 8-5.4-1.6-8-4.2-8-8V8zM12 9v4M12 16v.01" />
                </svg>
              </span>
              <span class="risk-copy"><strong>{{ item.title }}</strong><small>{{ item.department }} · {{ item.metric }}</small></span>
              <span class="risk-time">演示</span>
            </button>
          </div>
          <UiEmptyState v-else title="当前没有异常线索" dense />
        </article>
      </section>

      <section class="dashboard-bottom-grid">
        <article class="reference-card list-card">
          <header class="reference-card-head">
            <h2>最新文档</h2>
            <button type="button" @click="emit('goto', 'docs')">查看全部 ›</button>
          </header>
          <div v-if="documents.length" class="reference-list">
            <button v-for="item in documents.slice(0, 3)" :key="documentName(item)" type="button" class="reference-list-row" @click="emit('goto', 'docs')">
              <span class="row-icon">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6zM14 3v5h5M9 13h6M9 17h6" /></svg>
              </span>
              <span><strong>{{ documentName(item) }}</strong><small>知识库 · 已解析</small></span>
              <em>已解析</em>
            </button>
          </div>
          <UiEmptyState v-else title="上传制度或业务文档后显示在这里" dense />
        </article>

        <article class="reference-card list-card evidence-card">
          <header class="reference-card-head">
            <h2>知识证据</h2>
            <button type="button" @click="emit('goto', 'chat')">查看全部 ›</button>
          </header>
          <UiErrorState
            v-if="evidenceError"
            :title="evidenceDenied ? '没有权限查询指标口径' : '指标口径没查到'"
            :description="evidenceError"
            :retryable="!evidenceDenied"
            retry-text="重新查询"
            dense
            @retry="lookupMetric"
          />
          <div v-else-if="metricContext" class="evidence-main">
            <span class="row-icon">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6zM14 3v5h5M9 13h6M9 17h6" /></svg>
            </span>
            <div><strong>{{ metricContext.metric_name }}</strong><small>基于 {{ metricContext.source_file }}</small></div>
            <b>高可信</b>
          </div>
          <UiEmptyState v-else title="查询指标口径后显示证据" dense />
          <div class="evidence-query">
            <input v-model="metricQuery" placeholder="查询指标口径" @keyup.enter="lookupMetric" />
            <button type="button" @click="lookupMetric">查询</button>
          </div>
        </article>

        <article class="reference-card quick-card">
          <header class="reference-card-head"><h2>快速操作</h2></header>
          <div class="quick-grid">
            <button v-for="item in quickActions" :key="item.id" type="button" @click="emit('goto', item.id)">
              <span>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="item.icon" /></svg>
              </span>{{ item.label }}
            </button>
          </div>
        </article>
      </section>
    </template>
  </div>
</template>
