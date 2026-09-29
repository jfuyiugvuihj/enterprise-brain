<!--
  R505 · 「三档目标账」屏壳：给 GET /api/v1/slo 第一枚消费者

  欠的那一格不在后端：读腿早就在树（app/api/v1/observability.py 里那条 GET /slo），前端一个
  消费者都没有（基点 85572c1 现取：rg -nF "/slo" frontend/src 除 </slot> 外 0 枚生产命中）。
  这一枚壳接的就是它，零新增端点、零新增字段、零取数算术 —— 判码、归脸、句子全在 src/lib/slo.js。

  🔴 这一屏的判据是 A：不许把「没量过」画成达成。三条落地写法，逐条有钉
  （src/components/__tests__/r505-slo-screen.test.js）：
    ① 每一档都把「欠样本 / 不可测」与还欠几枚印出来：p50/p95 在服务端答 null 的地方，屏上就是
       「未记录」这一句人话。今天三档的 target_status 一律是 awaiting_real_samples，所以这一屏
       没有任何一处可以画出「达标」两个字，也没有任何一处把 0 当读数。
    ② blockers 逐条挂出来，code 用后端原名（lane_attribution_absent 那一族属乙半未清）：
       合并成一句「还有障碍」就是把欠的账擦掉。
    ③ 样本闸不是查询参数：这一屏连一个输入框都没有，屏上那枚下限是回包里的 sample_floor。

  入口形状逐字照 /admin 与 /traces 的先例：primary:false 派生不出一级入口，administratorOnly:true
  让它只长进管理员那一份入口清单 —— 加这一屏不改壳层一个字。为什么不挂一级：这一屏过的审计权限
  只登记在管理员与审计人员名下，给员工摆一枚按下去只会说「不向你开放」的按钮就是假控件。
  🔴 而「侧栏按客户端角色派生」这件事本身仍是假权限（缺口清单 §4.3 b 那笔没销的账）：这一屏只是
  不谎称自己解决了它，读不读得到只在服务端那道闸上说，屏上那三张失败脸就是它的答案。

  三张失败脸分开留名（判据 D）：403 不向你开放 / 503 存储不可用 / 500 读回失败，另加 401 与
  「回包读不出形状」，各一张、各一句出处，谁都不塌成一句「加载失败」。

  零新色值：本文件的样式块只有 grid / gap / margin / padding 这一族排版声明，一格颜色都不写，
  色值与字体一律沿用 theme.css 既有类（样式块里连 var() 都没出现，就没有第二处色值真源）。
  零枚裸 <button>、动作全部走 ui 原语。
-->
<script>
export default { name: 'SloPanel' }
</script>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  SLO_FACE_LOADING,
  SLO_FACE_READY,
  SLO_LOADING_TEXT,
  loadSlo,
  sloBlankView,
  sloFaceView,
} from '../lib/slo'
import { UiButton, UiErrorState, UiLoadingState, UiTable } from './ui'

/** 取数闸门（沿用 R316 / R399 那一枚手法，不发明第二套）：每次读领一号，作废用旧号。 */
let sloToken = 0

const view = ref(sloBlankView())
const busy = ref(false)

const loading = computed(() => view.value.face === SLO_FACE_LOADING)
const ready = computed(() => view.value.face === SLO_FACE_READY)
const failure = computed(() => (!loading.value && !ready.value ? sloFaceView(view.value) : null))
const head = computed(() => view.value.head || {})
const tiers = computed(() => view.value.tiers || [])
const units = computed(() => view.value.units || [])
const pool = computed(() => view.value.pool || null)

/** 数字那一表：列就是回包里的格，formatter 一律不吃算术（值在 lib 层已经折成文本）。 */
const numberColumns = [
  { key: 'label', label: '哪一格' },
  { key: 'statusText', label: '这一格今天怎么说' },
  { key: 'samples', label: '已有样本' },
  { key: 'requiredSamples', label: '出数要几枚' },
  { key: 'shortfall', label: '还欠' },
  { key: 'p50Text', label: '一半在这儿' },
  { key: 'p95Text', label: '九成五在这儿' },
  { key: 'targetText', label: '目标值' },
]

const stageColumns = [
  { key: 'label', label: '哪一段' },
  { key: 'statusText', label: '这一段今天怎么说' },
  { key: 'samples', label: '已有样本' },
  { key: 'shortfall', label: '还欠' },
  { key: 'p95Text', label: '九成五在这儿' },
]

const unitColumns = [
  { key: 'ownsTheName', label: '这个名字归谁' },
  { key: 'decidedBy', label: '由谁决定' },
  { key: 'membersText', label: '成员' },
  { key: 'unitText', label: '这是不是「三档」的那个单位' },
]

async function loadIntoView() {
  const mine = ++sloToken
  busy.value = true
  view.value = sloBlankView(SLO_FACE_LOADING)
  const next = await loadSlo()
  if (mine !== sloToken) return
  view.value = next
  busy.value = false
}

onMounted(loadIntoView)
onUnmounted(() => { sloToken += 1 })

/** 屏上一切数字都经由这两枚函数出口：读不到就是「未记录」，本文件一处都不写默认值。 */
function textOrUnrecorded(value) {
  const raw = typeof value === 'string' ? value.trim() : ''
  return raw || '未记录'
}

function memberText(list) {
  return Array.isArray(list) && list.length ? list.join('、') : '未记录'
}

function unitKindText(unit) {
  if (unit.unitOfSlo === true) return '就是它：SLO 按这一枚枚举分档'
  if (unit.unitOfSlo === false) return '不是它：别拿这一枚枚举当「三档」'
  return '未记录'
}
</script>

<template>
  <div class="panel-shell" data-testid="slo-panel" :data-face="view.face">
    <header class="panel-head">
      <div>
        <span class="eyebrow">三档目标账：今天能说什么、不能说什么</span>
        <p>
          这一屏列的是问答 / 分析 / 报告三档各自的目标读数，以及服务端为每一格交代的欠账。
          屏上每一个数字都是回包里那一格的读数：这里不数样本、不加和、不算百分位，也不替任何一格补目标值。
        </p>
      </div>
      <UiButton
        label="重新读取"
        variant="secondary"
        size="sm"
        :disabled="busy"
        data-testid="reload-slo"
        @click="loadIntoView"
      />
    </header>

    <UiLoadingState v-if="loading" :label="SLO_LOADING_TEXT" :rows="3" data-testid="slo-loading" />

    <UiErrorState
      v-else-if="failure"
      :title="failure.title"
      :description="failure.description"
      :code-label="failure.codeLabel"
      :retryable="failure.retryable"
      :busy="busy"
      data-testid="slo-failure"
      @retry="loadIntoView"
    />

    <template v-else>
      <!-- 顶栏那一行：样本闸、目标状态、百分位出处，三格都只可能来自回包。 -->
      <section class="panel-card" data-testid="slo-head">
        <div class="section-head">
          <span class="eyebrow">这份账的算法与闸口</span>
          <span class="demo-note" data-testid="slo-floor">
            出百分位要{{ textOrUnrecorded(head.sampleFloor) }}：这一枚下限写在服务端，不是查询参数，
            界面上没有任何一格能把它调低。
          </span>
        </div>
        <dl class="slo-facts">
          <div><dt>回执形状</dt><dd data-testid="slo-schema">{{ textOrUnrecorded(head.schema) }}</dd></div>
          <div><dt>目标值这一格</dt><dd data-testid="slo-target-status">{{ textOrUnrecorded(head.targetText) }}</dd></div>
          <div><dt>百分位出自</dt><dd data-testid="slo-percentile-source">{{ textOrUnrecorded(head.percentileSource) }}</dd></div>
          <div><dt>这次是谁读的</dt><dd data-testid="slo-requested-by">{{ textOrUnrecorded(head.requestedBy) }}</dd></div>
        </dl>
        <p class="demo-note" data-testid="slo-population-note">{{ textOrUnrecorded(head.populationNote) }}</p>
      </section>

      <!-- 三档：每一档一张卡，卡里两块（目标格 + 分段），欠账逐条挂在卡尾。 -->
      <section
        v-for="tier in tiers"
        :key="tier.id"
        class="panel-card"
        data-testid="slo-tier"
        :data-lane="tier.lane"
      >
        <div class="section-head">
          <span class="eyebrow">{{ textOrUnrecorded(tier.label) }}（{{ textOrUnrecorded(tier.lane) }}）</span>
          <span class="demo-note" data-testid="slo-observed">
            这台服务在这一档今天有{{ textOrUnrecorded(tier.observedRequests) }}——分档的样本池就是它，不多不少。
          </span>
        </div>
        <p v-if="tier.note" class="demo-note">{{ tier.note }}</p>
        <p class="demo-note">
          这一档落在{{ textOrUnrecorded(tier.screenPath) }}那一屏，走的是{{ memberText(tier.endpoints) }}；
          「屏」这个字的名册归{{ textOrUnrecorded(tier.screenSource) }}。
        </p>

        <UiTable
          :columns="numberColumns"
          :rows="tier.numbers"
          row-key="key"
          aria-label="这一档的目标读数"
          data-testid="slo-numbers"
        />
        <UiTable
          :columns="stageColumns"
          :rows="tier.stages"
          row-key="key"
          aria-label="这一档的分段读数"
          data-testid="slo-stage-numbers"
        />

        <!-- 欠样本 / 不可测的因由：逐格原话，服务端给到哪儿就说到哪儿。 -->
        <ul class="slo-reasons" data-testid="slo-reasons">
          <li v-for="slot in tier.numbers" :key="slot.key" data-testid="slo-reason">
            <span>{{ textOrUnrecorded(slot.label) }}：{{ textOrUnrecorded(slot.statusText) }}</span>
            <span class="demo-note">{{ textOrUnrecorded(slot.reason) }}</span>
            <span class="demo-note">这一格的分布来自{{ textOrUnrecorded(slot.sourceText) }}</span>
          </li>
        </ul>

        <!-- 🔴 blockers 逐条挂出来，码名留后端原名（技术信息区），一枚都不合并。 -->
        <div class="slo-blockers" data-testid="slo-blockers">
          <p class="eyebrow">这一档还挂着哪些障碍（逐条，不合并）</p>
          <p v-if="!tier.blockerList.length" class="demo-note">这一档的回执没交出任何一条障碍。</p>
          <ul v-else>
            <li v-for="blocker in tier.blockerList" :key="blocker.id" data-testid="slo-blocker">
              <span class="demo-note">技术信息 · 码名 <code>{{ blocker.codeName }}</code></span>
              <p>{{ textOrUnrecorded(blocker.detail) }}</p>
            </li>
          </ul>
        </div>
      </section>

      <!-- 未归因那一池：它不是任何一档，屏上也不许把它当一档。 -->
      <section v-if="pool" class="panel-card" data-testid="slo-pool">
        <div class="section-head">
          <span class="eyebrow">还没归到任何一档的那一池</span>
          <span class="demo-note">它不是一档，也不能被当成一档来读；屏上这一格存在的意义就是说清这件事。</span>
        </div>
        <p class="demo-note">{{ textOrUnrecorded(pool.what) }}</p>
        <UiTable
          :columns="numberColumns"
          :rows="[{ ...pool.endToEnd, key: 'pool-end-to-end' }]"
          row-key="key"
          aria-label="那一池的端到端读数"
          data-testid="slo-pool-numbers"
        />
        <ul>
          <li v-for="blocker in pool.blockers" :key="blocker.id" data-testid="slo-pool-blocker">
            <span class="demo-note">技术信息 · 码名 <code>{{ blocker.codeName }}</code></span>
            <p>{{ textOrUnrecorded(blocker.detail) }}</p>
          </li>
        </ul>
      </section>

      <!-- 「三档」这个词在仓里撞在三枚枚举上：三枚都列出来，不挑一枚当真理。 -->
      <section v-if="units.length" class="panel-card" data-testid="slo-units">
        <div class="section-head">
          <span class="eyebrow">「档」这个字撞在三枚枚举上</span>
          <span class="demo-note">三枚都是真存在的名册，逐枚列出来，谁也不许改名去讨好谁。</span>
        </div>
        <UiTable
          :columns="unitColumns"
          :rows="units.map(unit => ({ ...unit, membersText: memberText(unit.members), unitText: unitKindText(unit) }))"
          row-key="id"
          aria-label="三枚枚举"
          data-testid="slo-unit-table"
        />
        <ul>
          <li v-for="unit in units.filter(item => item.bridge.length || item.bridgeNote)" :key="'bridge-' + unit.id">
            <span class="demo-note">从问答档到模型档的桥：{{ memberText(unit.bridge) }}</span>
            <p v-if="unit.bridgeNote" class="demo-note">{{ unit.bridgeNote }}</p>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.slo-facts {
  display: grid;
  gap: 6px;
  margin: 0;
}

.slo-reasons,
.slo-blockers ul {
  display: grid;
  gap: 8px;
  margin: 12px 0 0;
  padding-left: 20px;
}
</style>
