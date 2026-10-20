<script setup>
import { computed, onBeforeUnmount, shallowRef, watch } from 'vue'
import { errorDetail, http, isPermissionDenied } from '../lib/http'
import { fetchArtifactBlob } from '../lib/artifacts'
import { UiButton, UiEmptyState, UiErrorState, UiLoadingState, UiTable } from './ui'

const props = defineProps({ traceId: { type: String, default: '' } })
const rows = shallowRef([])
const selected = shallowRef(null)
const loading = shallowRef(false)
const detailLoading = shallowRef(false)
const loadError = shallowRef(null)
const detailError = shallowRef(null)
const downloadError = shallowRef(null)
const downloading = shallowRef('')
let listController
let detailController
let downloadController
const downloads = new Set()

const statusLabel = value => ({ running: '计算中', completed: '已完成', failed: '计算失败' }[value] || '状态未识别')
const timeLabel = value => value ? new Date(value).toLocaleString('zh-CN') : '未记录'
const listColumns = [
  { key: 'calculation_run_id', label: '计算编号', mono: true },
  { key: 'parameters', label: '输入文件', formatter: value => value?.filename || '未记录' },
  { key: 'status', label: '状态', formatter: statusLabel },
  { key: 'created_at', label: '创建时间', formatter: timeLabel },
  { key: 'open', label: '详情' },
]
const statisticColumns = [
  { key: 'name', label: '数据列' },
  { key: 'sum', label: '合计', align: 'right' },
  { key: 'mean', label: '均值', align: 'right' },
  { key: 'min', label: '最小值', align: 'right' },
  { key: 'max', label: '最大值', align: 'right' },
]
const parameters = computed(() => selected.value?.parameters || {})
const result = computed(() => selected.value?.result || {})
const statistics = computed(() => result.value.numeric_statistics || [])
const answers = computed(() => Array.isArray(result.value.answer) ? result.value.answer : [])
const artifacts = computed(() => selected.value?.artifacts || [])
const sheetName = computed(() => result.value.sheet_name || parameters.value.sheet_name || '未指定')
const filterNote = computed(() => result.value.filter_note || parameters.value.filter_note || '未记录额外筛选条件')
const completeResult = computed(() => JSON.stringify(result.value, null, 2))

function clearDownloads() {
  downloadController?.abort()
  downloading.value = ''
  downloadError.value = null
  for (const handle of downloads) handle.revoke()
  downloads.clear()
}

async function load() {
  listController?.abort()
  detailController?.abort()
  clearDownloads()
  const controller = new AbortController()
  listController = controller
  rows.value = []
  selected.value = null
  loadError.value = null
  detailError.value = null
  detailLoading.value = false
  loading.value = Boolean(props.traceId)
  if (!props.traceId) return
  try {
    const response = await http.get('/calculations', { params: { trace_id: props.traceId, limit: 50 }, signal: controller.signal })
    if (controller.signal.aborted) return
    if (!Array.isArray(response.data?.items)) throw new Error('计算记录返回格式不完整')
    rows.value = response.data.items
  } catch (error) {
    if (!controller.signal.aborted) loadError.value = error
  } finally {
    if (!controller.signal.aborted) loading.value = false
  }
}

async function open(row) {
  detailController?.abort()
  clearDownloads()
  const controller = new AbortController()
  detailController = controller
  selected.value = null
  detailError.value = null
  detailLoading.value = true
  try {
    const response = await http.get('/calculations/' + encodeURIComponent(row.calculation_run_id), { signal: controller.signal })
    if (!controller.signal.aborted) selected.value = response.data
  } catch (error) {
    if (!controller.signal.aborted) detailError.value = error
  } finally {
    if (!controller.signal.aborted) detailLoading.value = false
  }
}

async function download(artifact) {
  if (downloading.value) return
  const controller = new AbortController()
  downloadController = controller
  downloading.value = artifact.artifact_id
  downloadError.value = null
  try {
    const handle = await fetchArtifactBlob(artifact.download_url, { signal: controller.signal })
    if (controller.signal.aborted) { handle.revoke(); return }
    downloads.add(handle)
    const link = document.createElement('a')
    link.href = handle.objectUrl
    link.download = artifact.display_name || '分析文件'
    link.click()
    setTimeout(() => { handle.revoke(); downloads.delete(handle) }, 1000)
  } catch (error) {
    if (!controller.signal.aborted) downloadError.value = error
  } finally {
    if (!controller.signal.aborted) downloading.value = ''
  }
}

watch(() => props.traceId, load, { immediate: true })
onBeforeUnmount(() => { listController?.abort(); detailController?.abort(); clearDownloads() })
</script>

<template>
  <section class="panel-card" data-testid="calculation-runs">
    <div class="section-head">
      <span class="eyebrow">计算记录</span>
      <UiButton label="刷新计算记录" variant="ghost" size="sm" :disabled="!traceId" :loading="loading" @click="load" />
    </div>
    <UiEmptyState v-if="!traceId" title="请选择一次运行" description="选择运行后，可回查该次计算的输入、口径、结果和生成文件。" />
    <UiLoadingState v-else-if="loading" label="正在读取计算记录…" />
    <UiErrorState v-else-if="loadError" title="计算记录读取失败" :description="errorDetail(loadError, '计算记录暂时无法读取')" :raw-error="loadError" :retryable="!isPermissionDenied(loadError)" @retry="load" />
    <UiEmptyState v-else-if="!rows.length" title="这次运行没有独立计算记录" description="历史运行未登记的计算无法补推；问答与事件记录仍可在本页查看。" />
    <template v-else>
      <p class="demo-note">列出最近保存的至多 50 条记录，查看详情不会重新执行计算。</p>
      <UiTable :columns="listColumns" :rows="rows" row-key="calculation_run_id" aria-label="本次运行的计算记录" data-testid="calculations-table">
        <template #cell-open="{ row }">
          <UiButton label="查看计算" size="sm" @click="open(row)" />
        </template>
      </UiTable>
      <UiLoadingState v-if="detailLoading" label="正在读取计算详情…" />
      <UiErrorState v-else-if="detailError" title="计算详情读取失败" :description="errorDetail(detailError, '计算详情暂时无法读取，请重新选择记录')" :raw-error="detailError" :retryable="false" />
      <div v-else-if="selected" class="calculation-detail" data-testid="calculation-detail" :data-calculation-id="selected.calculation_run_id">
        <dl class="calculation-fields">
          <dt>计算编号</dt><dd>{{ selected.calculation_run_id }}</dd>
          <dt>状态</dt><dd>{{ statusLabel(selected.status) }}</dd>
          <dt>输入文件</dt><dd>{{ parameters.filename || '未记录' }}</dd>
          <dt>数据版本</dt><dd>{{ selected.dataset_version_id || '未记录' }}</dd>
          <dt>工作表</dt><dd>{{ sheetName }}</dd>
          <dt>计算问题</dt><dd>{{ parameters.query || '未记录' }}</dd>
          <dt>筛选口径</dt><dd>{{ filterNote }}</dd>
          <dt>开始时间</dt><dd>{{ timeLabel(selected.started_at) }}</dd>
          <dt>完成时间</dt><dd>{{ timeLabel(selected.completed_at) }}</dd>
          <template v-if="selected.formula"><dt>计算方式</dt><dd>{{ selected.formula }}</dd></template>
        </dl>
        <template v-if="selected.status === 'completed'">
          <h4>已保存的计算结果</h4>
          <p v-if="result.rows !== undefined" data-testid="calculation-row-count">参与计算：{{ result.rows }} 行</p>
          <p v-for="(answer, index) in answers" :key="index">{{ answer }}</p>
          <UiTable v-if="statistics.length" :columns="statisticColumns" :rows="statistics" row-key="name" aria-label="计算统计结果" />
          <details><summary>完整计算结果</summary><pre class="calculation-result">{{ completeResult }}</pre></details>
        </template>
        <UiErrorState v-else-if="selected.status === 'failed'" title="这次计算没有完成" description="本次计算已记录失败，请检查输入后重新发起。" :code-label="selected.error_code ? '错误码：' + selected.error_code : ''" :retryable="false" />
        <p v-else class="demo-note">计算尚未完成，可刷新记录查看最新状态。</p>
        <h4>对应生成文件</h4>
        <p v-if="!artifacts.length" class="demo-note">本次计算没有登记关联的生成文件。</p>
        <div v-for="artifact in artifacts" :key="artifact.artifact_id" class="calculation-artifact">
          <span>{{ artifact.display_name || '分析文件' }}</span>
          <UiButton label="下载文件" size="sm" :disabled="!artifact.download_url || Boolean(downloading)" :loading="downloading === artifact.artifact_id" @click="download(artifact)" />
        </div>
        <UiErrorState v-if="downloadError" title="文件下载失败" :description="errorDetail(downloadError, '请检查权限和文件状态后重试')" :raw-error="downloadError" :retryable="false" />
      </div>
    </template>
  </section>
</template>

<style scoped>
.calculation-detail { margin-top: var(--s-4); }
.calculation-fields { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: var(--s-2) var(--s-4); }
.calculation-fields dt { color: var(--text-3); }
.calculation-fields dd { margin: 0; overflow-wrap: anywhere; }
.calculation-result { white-space: pre-wrap; overflow-wrap: anywhere; font-size: var(--t-sm); }
.calculation-artifact { display: flex; justify-content: space-between; align-items: center; gap: var(--s-3); margin-top: var(--s-2); }
</style>
