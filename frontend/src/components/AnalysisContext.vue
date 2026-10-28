<script setup>
import { computed } from 'vue'
import { UiButton } from './ui'

const props = defineProps({
  selectedData: { type: String, default: '' },
  referenceDocuments: { type: Array, default: () => [] },
  usedData: { type: String, default: '' },
  recordedData: { type: String, default: '' },
  origin: { type: Object, default: null },
  sources: { type: Array, default: () => [] },
  sourceFace: { type: Object, default: null },
  scope: { type: Object, default: () => ({}) },
  calculations: { type: Array, default: () => [] },
  calculationStatus: { type: String, default: 'idle' },
  loading: { type: Boolean, default: false },
  hasAnswer: { type: Boolean, default: false },
  hasRecordedRequest: { type: Boolean, default: false },
  reuseDisabled: { type: Boolean, default: false },
  reuseStatus: { type: String, default: '' },
})
const emit = defineEmits(['preview', 'goto', 'focus', 'report', 'remove-reference', 'clear-references', 'reuse'])
const isQueryInput = row => row.parameters?.operation === 'query_data'
  || row.result?.analysis_scope?.kind === 'query_input'
const calculationRows = computed(() => {
  const seen = new Set()
  return props.calculations.filter(row => {
    const key = JSON.stringify([row.parameters?.query, row.dataset_version_id, row.status, row.result?.analysis_scope])
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})
</script>

<template>
  <aside class="analysis-context" aria-label="资料、依据与下一步" data-testid="analysis-context">
    <section class="analysis-context__card">
      <header><h3>本次使用的资料</h3><UiButton variant="ghost" size="sm" @click="emit('goto', 'feed')">调整资料</UiButton></header>
      <div v-if="origin?.kind === 'alert'" class="analysis-context__origin" data-testid="analysis-origin">
        <strong>来自异常提醒 #{{ origin.id }}</strong><p>{{ origin.title }}</p>
        <UiButton variant="ghost" size="sm" @click="emit('goto', { name: 'insights', query: { alert: origin.id } })">返回这条异常提醒 →</UiButton>
      </div>
      <div v-if="usedData" class="analysis-context__file"><span class="analysis-context__file-icon analysis-context__file-icon--data" aria-hidden="true">X</span><div><strong>{{ usedData }}</strong><small>本轮计算实际使用的数据表</small></div></div>
      <div v-else-if="recordedData" class="analysis-context__file"><span class="analysis-context__file-icon analysis-context__file-icon--data" aria-hidden="true">X</span><div><strong>{{ recordedData }}</strong><small>原分析正文记载的文件</small></div></div>
      <div v-if="selectedData && selectedData !== usedData" class="analysis-context__file"><span class="analysis-context__file-icon analysis-context__file-icon--data" aria-hidden="true">X</span><div><strong>{{ selectedData }}</strong><small>下一轮已选择的经营数据</small></div></div>
      <div v-if="referenceDocuments.length" data-testid="selected-document-scope">
        <p>下一轮参考 {{ referenceDocuments.length }} 份文档；实际引用见下方依据。</p>
        <p v-if="selectedData" class="analysis-context__note">与所选经营数据联合核查；数据计算与文档依据分别记录。</p>
        <div v-for="filename in referenceDocuments" :key="filename" class="analysis-context__file">
          <span class="analysis-context__file-icon" aria-hidden="true">▤</span>
          <div><strong>{{ filename }}</strong><small>提问时指定的参考文档</small>
            <UiButton variant="ghost" size="sm" @click="emit('preview', { filename })">打开核对</UiButton>
            <UiButton variant="ghost" size="sm" :disabled="loading" :aria-label="'移除参考文档 ' + filename" @click="emit('remove-reference', filename)">移除</UiButton>
          </div>
        </div>
        <UiButton variant="ghost" size="sm" :disabled="loading" data-testid="clear-reference-documents" @click="emit('clear-references')">清空参考文档</UiButton>
      </div>
      <div v-for="(row, i) in sources" :key="row.sourceId || row.filename + i" class="analysis-context__file"><span class="analysis-context__file-icon" aria-hidden="true">文</span><div><strong>{{ row.filename }}</strong><small>本轮检索引用资料</small></div></div>
      <p v-if="!usedData && !recordedData && !selectedData && !referenceDocuments.length && !sources.length">可以直接查询知识库；分析经营数据时，请先选择文件。</p>
      <p v-if="recordedData && !usedData" class="analysis-context__note">历史记录未保留实际用表读数；文件名来自原分析正文，请核对原始资料。</p>
      <p v-if="selectedData && selectedData !== usedData" class="analysis-context__note">已选资料会用于下一轮；本轮依据以实际使用记录为准。</p>
    </section>
    <section class="analysis-context__card">
      <h3>分析范围</h3>
      <p v-if="calculationStatus === 'loading'">正在读取本轮计算记录……</p>
      <p v-else-if="calculationStatus === 'unavailable'" role="status">本轮计算记录暂时无法读取，分析范围尚未核实。请稍后重新打开任务。</p>
      <template v-if="calculationRows.length">
        <details v-for="(row, index) in calculationRows" :key="row.calculation_run_id" :open="calculationRows.length === 1" data-testid="calculation-scope">
          <summary>{{ calculationRows.length > 1 ? `第 ${index + 1} 项 · ` : '' }}{{ row.parameters?.filename || '计算记录' }} · {{ row.status === 'completed' ? '已计算' : '未完成' }}</summary>
          <p>{{ row.parameters?.query }}</p>
          <p v-if="isQueryInput(row)" class="analysis-context__note">以下是查询前的输入范围。查询可能继续筛选或汇总，输入记录数和字段单位不代表查询结果的行数或单位。</p>
          <dl class="analysis-context__scope">
            <dt>数据版本</dt><dd>{{ row.dataset_version_id }}</dd>
            <dt>{{ isQueryInput(row) ? '输入期间' : '期间' }}</dt><dd>{{ row.result?.analysis_scope?.period || '此记录未单独保存期间，请核对原分析；未从正文推断' }}</dd>
            <dt>{{ isQueryInput(row) ? '输入筛选' : '筛选' }}</dt><dd>{{ row.result?.analysis_scope?.filter || row.result?.filter_note || '未单独保存' }}</dd>
            <dt>{{ isQueryInput(row) ? '输入字段单位' : '单位' }}</dt><dd><template v-if="row.result?.analysis_scope?.units?.length"><span v-for="metric in row.result.analysis_scope.units" :key="metric.column" style="display:block">{{ metric.column }}：{{ metric.unit }}</span></template><template v-else>未单独保存</template></dd>
            <dt>{{ isQueryInput(row) ? '输入记录数' : '记录数' }}</dt><dd>{{ row.result?.rows ?? '未得到结果' }}</dd>
            <dt>工作表</dt><dd>{{ row.result?.analysis_scope?.sheet || row.result?.sheet_name || '未单独保存' }}</dd>
          </dl>
          <small>计算记录：{{ row.calculation_run_id }}</small>
          <UiButton v-if="row.status === 'completed'" variant="secondary" size="sm" data-testid="analysis-reuse"
            :disabled="loading || reuseDisabled" @click="emit('reuse', row)">按这次条件再分析</UiButton>
        </details>
      </template>
      <template v-else-if="calculationStatus !== 'unavailable' && calculationStatus !== 'loading'">
        <p v-if="hasAnswer">{{ hasRecordedRequest ? '本轮尚无独立计算范围可核对，未从回答正文推断。请核对原始资料。' : '旧正文摘录，尚未核实；不能替代独立计算记录。' }}</p>
        <dl v-if="hasAnswer && !hasRecordedRequest" class="analysis-context__scope"><dt>期间</dt><dd>{{ scope.period || '未单独记录' }}</dd><dt>筛选</dt><dd>{{ scope.filter || '未单独记录' }}</dd><dt>单位</dt><dd>{{ scope.unit || '未单独记录' }}</dd></dl>
        <p v-if="!hasAnswer">完成分析后，在这里查看实际计算范围。</p>
      </template>
      <p v-if="reuseStatus" role="status" data-testid="analysis-reuse-status">{{ reuseStatus }}</p>
    </section>
    <section class="analysis-context__card" data-testid="analysis-evidence">
      <h3>依据与后续操作</h3>
      <ul v-if="sources.length" class="analysis-context__sources">
        <li v-for="(row, i) in sources" :key="row.sourceId || row.filename + i">
          <UiButton variant="ghost" size="sm" @click="emit('preview', row)">{{ row.filename }} <span aria-hidden="true">↗</span></UiButton>
          <small>打开原文，核对引用内容</small>
        </li>
      </ul>
      <p v-if="sourceFace && ['all-hidden', 'scope-error'].includes(sourceFace.kind)">{{ sourceFace.headline }}。{{ sourceFace.reason }}</p>
      <p v-else-if="sourceFace?.hiddenLine">{{ sourceFace.hiddenLine }}</p>
      <p v-if="!usedData && !sources.length">{{ loading ? '正在处理，依据会随结果显示。' : hasAnswer ? '本轮暂未记录可打开的资料依据，请结合结果说明核查。' : '提问后，在这里查看实际使用的数据和引用资料。' }}</p>
      <p v-if="usedData">计算来自「{{ usedData }}」，统计范围以原分析说明为准。</p>
      <UiButton v-if="usedData || recordedData" variant="secondary" size="sm" data-testid="analysis-open-data" @click="emit('goto', { name: 'feed', query: { tab: 'data', filename: usedData || recordedData } })">核对这份经营数据</UiButton>
      <div class="analysis-context__next">
      <p>你可以核对资料后继续追问，或生成保留本次分析内容的报告。</p>
      <UiButton variant="secondary" size="sm" @click="emit('focus')">继续追问</UiButton>
      <UiButton variant="ghost" size="sm" @click="emit('goto', 'artifacts')">查看已生成成果 →</UiButton>
      </div>
    </section>
  </aside>
</template>
