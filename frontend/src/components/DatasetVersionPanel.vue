<script setup>
import { computed, ref, watch } from 'vue'
import { errorDetail, http } from '../lib/http'
import { fileAccessLabel } from '../lib/file-access'
import { UiButton } from './ui'

const props = defineProps({
  target: { type: Object, default: null },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['completed', 'refresh'])

const fileInput = ref(null)
const targetSnapshot = ref(null)
const replacementFile = ref(null)
const busy = ref(false)
const errorMessage = ref('')
const resultMessage = ref('')
const needsRefresh = ref(false)
const changeSummary = ref(null)
watch(() => props.target, () => { if (!busy.value) needsRefresh.value = false })
const targetExtension = computed(() => extensionOf(targetSnapshot.value?.filename || ''))

function extensionOf(filename) {
  const match = String(filename).match(/\.[^.]+$/)
  return match ? match[0].toLowerCase() : ''
}

function chooseReplacement() {
  if (props.disabled || busy.value || needsRefresh.value || !props.target) return
  if (!props.target.version_id) {
    errorMessage.value = '当前文件缺少版本标识，请刷新数据文件列表后再试。'
    resultMessage.value = ''
    return
  }
  const extension = extensionOf(props.target.filename)
  if (!['.csv', '.xlsx'].includes(extension)) {
    errorMessage.value = '当前文件格式不支持版本更新，仅支持 .csv 或 .xlsx。'
    resultMessage.value = ''
    return
  }

  targetSnapshot.value = {
    filename: props.target.filename,
    version_id: props.target.version_id,
    classification: props.target.classification,
    owner_id: props.target.owner_id,
    department_ids: Array.isArray(props.target.department_ids) ? [...props.target.department_ids] : props.target.department_ids,
  }
  replacementFile.value = null
  errorMessage.value = ''
  resultMessage.value = ''
  changeSummary.value = null
  if (fileInput.value) fileInput.value.value = ''
  fileInput.value?.click()
}

function handleFileChange(event) {
  const file = event.target.files?.[0]
  if (!file || busy.value) return
  const incomingExtension = extensionOf(file.name)
  if (!['.csv', '.xlsx'].includes(incomingExtension) || incomingExtension !== targetExtension.value) {
    replacementFile.value = null
    errorMessage.value = '新文件必须与原文件使用相同的 .csv 或 .xlsx 格式；原文件内容未修改。'
    return
  }
  replacementFile.value = file
  errorMessage.value = ''
  resultMessage.value = ''
}

function cancelUpdate() {
  if (busy.value) return
  replacementFile.value = null
  targetSnapshot.value = null
  errorMessage.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

function failureMessage(error) {
  const status = error?.response?.status
  if (status === 409) return '当前文件版本已变化。请刷新数据文件列表并重新选择后再更新。'
  if (status === 503) return '版本更新暂不可用；上一版本仍保留，请稍后重试。'
  if (status === 403) return '当前账号无权更新此数据文件，请联系管理员核对权限。'
  if (!error?.response || ['ECONNABORTED', 'ETIMEDOUT', 'ERR_NETWORK'].includes(error?.code)) {
    return '请求结果暂时无法确认。请先查看当前数据文件列表，确认版本后再决定是否重试。'
  }
  return errorDetail(error, '数据版本更新失败，请稍后重试。')
}

async function confirmUpdate() {
  if (busy.value || props.disabled || needsRefresh.value || !replacementFile.value || !targetSnapshot.value) return
  const target = targetSnapshot.value
  const form = new FormData()
  form.append('file', replacementFile.value, target.filename)
  form.append('new_version', 'true')
  form.append('expected_version_id', String(target.version_id))

  busy.value = true
  errorMessage.value = ''
  resultMessage.value = ''
  try {
    const response = await http.post('/upload-excel', form)
    if (response.status !== 200) {
      needsRefresh.value = true
      errorMessage.value = '服务器未确认版本更新。请刷新数据文件列表核对当前版本。'
      return
    }
    const data = response.data || {}
    if (!data.version_id) {
      needsRefresh.value = true
      errorMessage.value = '更新回执缺少版本信息，结果暂时无法确认。请先刷新列表核对。'
      return
    }
    changeSummary.value = data.version_change || null
    resultMessage.value = data.version_unchanged
      ? '文件内容没有变化，当前版本保持不变。'
      : `版本已更新：${data.version_id || data.version || '新版本'}`
    replacementFile.value = null
    emit('completed', target.filename)
  } catch (error) {
    needsRefresh.value = error?.response?.status === 409 || !error?.response
    errorMessage.value = failureMessage(error)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="dataset-version" data-testid="dataset-version-panel">
    <UiButton
      variant="secondary"
      class="data-action-btn dataset-version__start"
      type="button"
      data-testid="dataset-version-start"
      :disabled="disabled || busy || needsRefresh || !target"
      @click="chooseReplacement"
    >更新版本</UiButton>
    <input
      ref="fileInput"
      class="dataset-version__input"
      type="file"
      accept=".csv,.xlsx"
      data-testid="dataset-version-input"
      :disabled="disabled || busy"
      @change="handleFileChange"
    >

    <div v-if="replacementFile && targetSnapshot" class="dataset-version__confirmation" data-testid="dataset-version-confirmation">
      <p><strong>目标文件：</strong><span class="dataset-version__value">{{ targetSnapshot.filename }}</span></p>
      <p><strong>当前版本：</strong><span class="dataset-version__value">{{ targetSnapshot.version_id }}</span></p>
      <p><strong>新文件：</strong><span class="dataset-version__value">{{ replacementFile.name }}</span></p>
      <p><strong>原权限：</strong>{{ fileAccessLabel(targetSnapshot) }}</p>
      <p class="dataset-version__permissions">确认后保留原文件名，文件密级、负责人和部门权限不变。</p>
      <p class="dataset-version__permissions">旧任务和报告保留原版本。现有阈值提醒在下次巡检时使用当前版本，请在确认前核对相关规则。</p>
      <div class="dataset-version__actions">
        <UiButton variant="ghost" type="button" data-testid="dataset-version-cancel" :disabled="busy" @click="cancelUpdate">取消</UiButton>
        <UiButton type="button" data-testid="dataset-version-confirm" :disabled="busy || disabled || needsRefresh" @click="confirmUpdate">
          {{ busy ? '正在更新…' : '确认更新' }}
        </UiButton>
      </div>
    </div>
    <p v-if="errorMessage" class="dataset-version__message dataset-version__message--error" role="alert" data-testid="dataset-version-error">{{ errorMessage }}</p>
    <UiButton v-if="needsRefresh" variant="secondary" type="button" data-testid="dataset-version-refresh" @click="emit('refresh', targetSnapshot?.filename)">刷新列表核对</UiButton>
    <p v-if="resultMessage" class="dataset-version__message" role="status" data-testid="dataset-version-result">{{ resultMessage }}</p>
    <p v-if="changeSummary" class="dataset-version__message">文件记录数：{{ changeSummary.previous_rows }} → {{ changeSummary.rows }}；新增字段：{{ changeSummary.added_columns?.join('、') || '无' }}；移除字段：{{ changeSummary.removed_columns?.join('、') || '无' }}。</p>
  </div>
</template>

<style scoped>
.dataset-version {
  flex: 1 1 100%;
  min-width: 0;
  max-width: 100%;
  padding: 12px 14px;
  box-sizing: border-box;
}

.dataset-version__input {
  display: none;
}

.dataset-version__confirmation {
  width: 100%;
  max-width: 420px;
  box-sizing: border-box;
  margin-top: 8px;
  padding: 10px;
  border: 1px solid var(--line-strong);
  border-radius: 7px;
  background: var(--legacy-paper);
  color: var(--text);
  overflow-wrap: anywhere;
}

.dataset-version__confirmation p {
  margin: 0 0 6px;
  font-size: 13px;
}

.dataset-version__value {
  overflow-wrap: anywhere;
}

.dataset-version__permissions {
  color: var(--muted);
}

.dataset-version__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.dataset-version__actions button {
  min-width: 0;
  min-height: 40px;
  padding: 4px 8px;
  border: 1px solid var(--line-strong);
  border-radius: 5px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
}

.dataset-version__actions button:disabled,
.dataset-version__start:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.dataset-version__message {
  max-width: 360px;
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.dataset-version__message--error {
  color: var(--danger);
}
</style>
