<script setup>
import { UiButton } from './ui'

defineProps({
  selectedData: { type: String, default: '' },
  referenceDocuments: { type: Array, default: () => [] },
  usedData: { type: String, default: '' },
  recordedData: { type: String, default: '' },
  origin: { type: Object, default: null },
  sources: { type: Array, default: () => [] },
  sourceFace: { type: Object, default: null },
  scope: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false },
  hasAnswer: { type: Boolean, default: false },
})
const emit = defineEmits(['preview', 'goto', 'focus', 'report', 'remove-reference', 'clear-references'])
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
      <dl class="analysis-context__scope"><dt>期间</dt><dd>{{ scope.period || '结果中未单独记录' }}</dd><dt>筛选</dt><dd>{{ scope.filter || '以计算范围说明为准' }}</dd><dt>单位</dt><dd>{{ scope.unit || '以来源资料标注为准' }}</dd><dt>可见范围</dt><dd>当前账号授权范围</dd></dl>
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
