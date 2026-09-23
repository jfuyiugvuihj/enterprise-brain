<script setup>
import { computed, onMounted, ref } from 'vue'
import { errorDetail, http, isPermissionDenied } from '../lib/http'
import { UiButton, UiEmptyState, UiErrorState, UiLoadingState } from './ui'
import DocumentPreviewModal from './DocumentPreviewModal.vue'
// 产物列表（W2-2 挂载）与两步删除状态机共用一份实现：两处删除入口的确认行为不许各写一遍
import ArtifactList, { advanceDelete, deleteButtonLabel, deleteErrorView, isPendingDelete } from './ArtifactList.vue'

/**
 * R186 · 行级判定的三张脸。后端（R180）已经把结论写进两枚成功体字段 ——
 * preview.row_scope（app/api/v1/data.py:132-169 构形、:319 挂上）与 GET /data-files 的
 * restricted（app/api/v1/data.py:240-249）。这一枚面板只做一件事：把后端已经做出的判定
 * 说出去，一个字都不替它猜。
 *
 * 三张脸必须互不相同，且都不是「不存在」（R163 归的 B 类病就死在最后半句上）：
 *   ① 真没有      code === '' 且 rows_in === 0 —— 归 R170 那套 empty 画像口径，这里一个字
 *                 都不插，插了就是把一张真空表说成权限问题；
 *   ② 有但看不见   code === 'row_scope_denied' —— 用后端 message 原句，键缺席时才用兜底句，
 *                 两句都说得出「行存在」这件事；
 *   ②b 一行未剩   code === 'no_visible_rows' —— 后端故意不给 message（部门维度一行没藏过时，
 *                 猜因由就是把没裁过的维度说成权限，R64/R62 裁过）。这一支不许出现「权限 /
 *                 可见范围 / 部门」任何一枚词，也不许复用 ② 的那句话；
 *   ③ 只裁一部分   rows_in > rows_visible > 0 —— 正常答案加一行交代：明说全表 N 行、可见 M 行，
 *                 不许让 M 冒充这张表的总行数。
 */
const ROW_SCOPE_DENIED = 'row_scope_denied'
const NO_VISIBLE_ROWS = 'no_visible_rows'
/**
 * 兜底句只在后端没挂 message 键时开口（契约允许缺席：data.py:166-167 是 if message 才写）。
 * 它必须与后端原句同义：说得出「行存在」，并把下一步指回部门归属核对 —— 因为 code 本身就
 * 是后端对「部门维度真的藏了行」的认定（app/agents/tools.py:955-970 那一份唯一判据源）。
 */
const ROW_SCOPE_DENIED_FALLBACK =
  '这份数据文件里确实有数据行，只是不在当前账号的行级可见范围内，界面上一行都没有显示；如需查看，请联系管理员核对你的部门归属与文件的部门标注。'
/** 同上：restricted.message 按契约恒在（data.py:244-247），这一句只在缺席时兜底，且不点名文件。 */
const RESTRICTED_FILES_FALLBACK =
  '有数据文件存在，但不在当前账号的可见范围内，所以没有出现在上面的列表里；如需访问，请联系管理员核对你的部门归属与文件的部门标注。'

/** 计数只认非负整数：后端给 int，界面上不许出现 NaN、负数或小数冒充行数。 */
function rowCount(value) {
  const count = Number(value)
  return Number.isFinite(count) && count > 0 ? Math.trunc(count) : 0
}

const profile = ref(null)
const dataFile = ref('')
const tableColumns = ref([])
const tableRows = ref([])
const tableTruncated = ref(false)
const previewOpen = ref(false)
const previewLoading = ref(false)
const previewError = ref('')
const previewDenied = ref(false)
const uploading = ref(false)
const dataFiles = ref([])
const filesLoading = ref(false)
const filesError = ref('')
// 行级判定的两份原始载荷：预览那一屏的 row_scope 与列表那一屏的 restricted，各自随请求重置。
const rowScope = ref(null)
const restrictedFiles = ref(null)
// 无权限 / 坏了 / 空列表是三张脸（R1c），文件列表与预览各自判一次。
const filesDenied = ref(false)
const selectingFile = ref(false)
// 删除所选数据文件（W2-3）：只对当前选中的那一个发 DELETE，两步内联确认，不用 window.confirm
const pendingFileDelete = ref('')
const deletingFile = ref(false)
const fileDeleteError = ref('')
const fileDeleteDenied = ref(false)

const quickActions = [
  { label: '📊 各列对比', query: '对比各列数据的最大最小值' },
  { label: '📈 趋势分析', query: '分析数据的变化趋势' },
  { label: '📋 生成报告', query: '根据这份数据生成一份分析报告' },
  { label: '🔍 找出最高', query: '找出每列的最高值和最低值' },
  { label: '📉 异常检测', query: '检测数据中是否存在异常值' },
  { label: '💡 总结摘要', query: '用一段话总结这份数据的关键信息' },
]

const emit = defineEmits(['ask'])

async function uploadExcel(e) {
  const file = e.target.files?.[0]
  if (!file) return

  const form = new FormData()
  form.append('file', file)

  uploading.value = true
  try {
    const res = await http.post('/upload-excel', form)
    applyDataPreview(res.data)
    await loadDataFiles(file.name)
  } catch (err) {
        filesError.value = errorDetail(err, '数据上传失败')
  } finally {
    uploading.value = false
    e.target.value = ''
  }
}

function applyDataPreview(data) {
  dataFile.value = data.filename || ''
  profile.value = data.profile || null
  tableColumns.value = data.columns || []
  tableRows.value = data.rows || []
  tableTruncated.value = Boolean(data.truncated)
  rowScope.value = data.row_scope || null
}

async function loadDataFiles(preferredFilename = '') {
  filesLoading.value = true
  filesError.value = ''
  // 上一轮那句「有 N 个看不见」不属于这一轮：重载先清，失败也清，不许留成陈话。
  restrictedFiles.value = null
  try {
    const res = await http.get('/data-files', { params: { _ts: Date.now() } })
    dataFiles.value = res.data.files || []
    restrictedFiles.value = res.data.restricted || null
    const currentExists = dataFiles.value.some(file => file.filename === dataFile.value)
    const preferredExists = dataFiles.value.some(file => file.filename === preferredFilename)
    const nextFilename = preferredExists
      ? preferredFilename
      : currentExists
        ? dataFile.value
        : dataFiles.value[0]?.filename
    if (nextFilename && (nextFilename !== dataFile.value || !profile.value)) {
      await selectDataFile(nextFilename)
    }
  } catch (err) {
        restrictedFiles.value = null
        filesDenied.value = isPermissionDenied(err)
        filesError.value = filesDenied.value
          ? '当前账号没有查看数据文件列表的权限，请联系管理员开通。'
          : errorDetail(err, '数据文件列表加载失败')
  } finally {
    filesLoading.value = false
  }
}

async function selectDataFile(filename) {
  dataFile.value = filename
  selectingFile.value = true
  previewError.value = ''
  previewDenied.value = false
  // 换文件与请求失败都不许留着上一个文件的行级结论：那一屏的因由改由 previewError 说。
  rowScope.value = null
  try {
    const res = await http.get(
      `/data-files/${encodeURIComponent(filename)}/preview`,
      { params: { _ts: Date.now() } }
    )
    applyDataPreview(res.data)
  } catch (err) {
        // 别人的数据集会走到这里：data.py:89-90 用 policy 的 reason code 回 403。
        previewDenied.value = isPermissionDenied(err)
        previewError.value = previewDenied.value
          ? '这份数据文件不属于你的可见范围，当前账号打不开它。'
          : errorDetail(err, '数据文件预览失败')
  } finally {
    selectingFile.value = false
  }
}

async function openDataFile() {
  if (!dataFile.value) return
  previewOpen.value = true
  previewLoading.value = true
  try {
    await selectDataFile(dataFile.value)
  } catch (err) {
        previewError.value = errorDetail(err, '数据预览失败')
  } finally {
    previewLoading.value = false
  }
}

async function downloadDataFile() {
  if (!dataFile.value) return
  try {
    const res = await http.get(
      `/data-files/${encodeURIComponent(dataFile.value)}/file`,
      { responseType: 'blob', params: { inline: false, _ts: Date.now() } }
    )
    const url = URL.createObjectURL(res.data)
    const link = document.createElement('a')
    link.href = url
    link.download = dataFile.value
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (err) {
        previewError.value = errorDetail(err, '数据文件下载失败')
  }
}

/**
 * 删完不留残影（W2-3）：后端 R8 把数据文件与它自己的登记行一起 tombstone，
 * 界面这边要同步清掉画像、表头与行，否则「已删除的文件」还在屏幕上带着完整预览，
 * 下一次点开会让人以为它还在。dataFile 清空后 loadDataFiles 会自己挑剩下第一个补位。
 */
function clearTableState() {
  profile.value = null
  tableColumns.value = []
  tableRows.value = []
  tableTruncated.value = false
  rowScope.value = null
  dataFile.value = ''
  pendingFileDelete.value = ''
}

/**
 * 预览那一屏的行级状态。判定形状在这里定，句子一律读后端那一层给的 code / message / 计数。
 */
const previewScope = computed(() => {
  const scope = rowScope.value
  if (!scope) return null
  const rowsIn = rowCount(scope.rows_in)
  const rowsVisible = rowCount(scope.rows_visible)
  const code = String(scope.code || '')
  if (code === ROW_SCOPE_DENIED) {
    return {
      face: 'denied',
      rowsIn,
      rowsVisible,
      message: String(scope.message || '') || ROW_SCOPE_DENIED_FALLBACK,
    }
  }
  if (code === NO_VISIBLE_ROWS && rowsIn > 0) {
    // 只把后端已经报过的事实（rows_in 是它的计数）复述一遍，不补一个字的因由。
    return {
      face: 'no-visible',
      rowsIn,
      rowsVisible,
      message: `这份数据文件里共有 ${rowsIn} 行，界面上一行都没有显示出来。显示为空不代表文件里没有数据行。`,
    }
  }
  if (rowsIn > 0 && rowsVisible > 0 && rowsVisible < rowsIn) {
    return { face: 'partial', rowsIn, rowsVisible, message: '' }
  }
  // 判据 1①：真空表（code==='' 且 rows_in===0）与全部可见都落在这里 —— 这一格不归本层说。
  return null
})

/**
 * 「一行都没显示出来」的两张脸（② / ②b）。retryable 一律不给：行级可见范围是账号的确定
 * 属性，同一个请求重发筛出来的还是那批行 —— 与 lib/errcodes.js 给这两枚码判 retryable:false
 * 的三条依据同源，这里不另立口径。两句标题也各自分开，且都不说「不存在」。
 */
const previewScopeNotice = computed(() => {
  const scope = previewScope.value
  if (!scope) return null
  if (scope.face === 'denied') {
    return { title: '这份数据文件有行，只是没有显示给你', description: scope.message }
  }
  if (scope.face === 'no-visible') {
    return { title: '这份数据文件没有显示任何一行', description: scope.message }
  }
  return null
})

/**
 * 画像卡统计行后面那半句：把「这张表多大」和「你看到多少」分成两个数说（判据 1③）。
 * 没有 row_scope 的载荷（上传回包、旧响应）逐字回到 R170 的口径，一个字节都不改。
 */
const profileStatsSuffix = computed(() => {
  const scope = previewScope.value
  if (!scope) return profile.value?.empty ? ' · 空表，尚无数据行' : ''
  if (scope.face === 'partial') {
    return ` · 全表 ${scope.rowsIn} 行中，当前账号可见的 ${scope.rowsVisible} 行`
  }
  return ' · 当前显示 0 行'
})

/**
 * 列表那一屏的 restricted：说「有 N 个存在但你看不见」，不点名文件 —— 点名一件无权访问的
 * 资源本身就是泄露，后端那份 message 里也没有名字，界面这边一枚都不补。
 */
const restrictedNotice = computed(() => {
  const restricted = restrictedFiles.value
  const count = rowCount(restricted?.count)
  if (!count) return null
  return {
    count,
    title: `还有 ${count} 个数据文件没有列在这里`,
    description: String(restricted?.message || '') || RESTRICTED_FILES_FALLBACK,
  }
})

/**
 * 预览弹窗的 error 通道：那枚组件不在本单写域里，改不了它自己的形状，但它空着那一支内置
 * 的话是「暂无数据」—— 正是要消灭的那句假话。所以「一行都没显示」的两张脸借这枚已有的
 * 字符串 prop 说真句子；真失败（previewError）优先，弹窗不许把「坏了」说成「被拒绝」。
 */
const previewModalError = computed(() => previewError.value || previewScopeNotice.value?.description || '')

const fileDeleteView = computed(() => deleteErrorView({
  denied: fileDeleteDenied.value,
  detail: fileDeleteError.value,
  subject: '这个数据文件',
}))

async function removeDataFile(filename) {
  if (!filename || deletingFile.value) return
  deletingFile.value = true
  fileDeleteError.value = ''
  fileDeleteDenied.value = false
  try {
    await http.delete('/data-files/' + encodeURIComponent(filename))
    clearTableState()
    await loadDataFiles()
  } catch (err) {
    // 别人的数据集删不掉是「没权限」，不是「删完了」：两张脸分开，且不给重试按钮（两步确认不许被压缩）。
    fileDeleteDenied.value = isPermissionDenied(err)
    fileDeleteError.value = errorDetail(err, '数据文件没能删除')
  } finally {
    deletingFile.value = false
  }
}

function requestFileDelete() {
  if (!dataFile.value || deletingFile.value) return
  const step = advanceDelete(pendingFileDelete.value, dataFile.value)
  if (step === 'arm') {
    pendingFileDelete.value = dataFile.value
    fileDeleteError.value = ''
    fileDeleteDenied.value = false
    return
  }
  if (step !== 'execute') return
  pendingFileDelete.value = ''
  removeDataFile(dataFile.value)
}

function cancelFileDelete() {
  pendingFileDelete.value = ''
}

function closeDataPreview() {
  previewOpen.value = false
  previewError.value = ''
}

function askQuestion(q) {
  if (!dataFile.value) return
  emit('ask', { query: q, filename: dataFile.value })
}

function typeIcon(dtype) {
  if (!dtype) return '❓'
  if (dtype.includes('int') || dtype.includes('float')) return '🔢'
  // R182：pandas 3 起字符串列的 dtype 是 str / string，只认 object 会让真机数据的文本列挑中 📦。
  if (dtype === 'str' || dtype === 'string' || dtype.includes('object')) return '📝'
  if (dtype.includes('datetime')) return '📅'
  return '📦'
}

function missingClass(pct) {
  if (pct === 0) return 'ok'
  if (pct < 10) return 'warn'
  return 'bad'
}

function formatModifiedAt(value) {
  return value ? value.replace('T', ' ').replace(/([+-]\d{2}:\d{2})$/, '') : ''
}

onMounted(loadDataFiles)
</script>

<template>
  <div class="data-panel" data-testid="data-panel">
    <!-- 上传区 -->
    <div class="upload-section">
      <label class="upload-btn" :class="{ loading: uploading }">
        {{ uploading ? '⏳ 解析中...' : '📊 上传 Excel' }}
        <input data-testid="data-upload-input" type="file" hidden accept=".xlsx,.xls,.csv"
               @change="uploadExcel" :disabled="uploading" />
      </label>
      <p class="upload-hint">上传经营数据开始分析</p>
    </div>

    <section class="data-files-section">
      <div class="section-heading">
        <span>数据文件</span>
        <span v-if="dataFiles.length" class="file-count">{{ dataFiles.length }}</span>
      </div>

      <UiLoadingState v-if="filesLoading" label="正在读取数据文件..." dense />
      <UiErrorState
        v-else-if="filesError"
        title="数据文件列表没读到"
        :description="filesError"
        :retryable="!filesDenied"
        retry-text="重新加载"
        :busy="filesLoading"
        dense
        @retry="loadDataFiles"
      />
      <template v-else-if="!dataFiles.length">
        <!-- 「一枚都没有」与「有 N 枚被权限藏起来」是两张脸（判据 1④）：同一屏既说「暂无数据
             文件」又说「还有 N 个看不见」是一句话自相矛盾。所以空态只在 restricted 缺席时才开口，
             被藏起来的那些由下面那一块单独说，两块不共用一句文案。 -->
        <UiEmptyState
          v-if="!restrictedNotice"
          title="暂无数据文件"
          description="上传 Excel 或 CSV 开始分析。"
          dense
        />
      </template>

      <div v-else class="data-file-list">
        <button
          v-for="file in dataFiles"
          :key="file.filename"
          type="button"
          :class="['data-file-item', { active: file.filename === dataFile, loading: selectingFile && file.filename === dataFile }]"
          @click="selectDataFile(file.filename)"
        >
          <span class="data-file-icon">{{ file.extension === '.csv' ? 'CSV' : 'XLS' }}</span>
          <span class="data-file-main">
            <span class="data-file-name">{{ file.filename }}</span>
            <span class="data-file-meta">{{ file.size_label }} · {{ formatModifiedAt(file.modified_at) }}</span>
          </span>
        </button>
      </div>

      <!-- R186：后端在成功体里已经说了「有 N 个数据文件存在，但不在当前账号的可见范围内」
           （app/api/v1/data.py:240-249），这一屏此前一个字都不提，员工看到的仍是「没有文件」。
           原句照搬，不点名文件；列表有货时同样要说，所以它站在那条三张脸链之外单独一枚。 -->
      <UiErrorState
        v-if="restrictedNotice"
        :title="restrictedNotice.title"
        :description="restrictedNotice.description"
        :retryable="false"
        data-testid="data-files-restricted"
        dense
      />
    </section>

    <!-- 分析产物（W2-2）：接 GET /artifacts 分页列表，挂在「数据文件」区之后 -->
    <ArtifactList />

    <UiErrorState
      v-if="previewError && !previewOpen"
      title="数据预览没打开"
      :description="previewError"
      :retryable="!previewDenied"
      retry-text="重试"
      :busy="selectingFile"
      dense
      @retry="selectDataFile(dataFile)"
    />

    <!-- R186 判据 1②/1②b：文件打开了、行级却一行都没显示 —— 这既不是「空表」也不是「没这个
         文件」，是两张互不相同的脸，句子各归后端的那个 code，这里不合并、不串味。 -->
    <UiErrorState
      v-if="previewScopeNotice"
      :title="previewScopeNotice.title"
      :description="previewScopeNotice.description"
      :retryable="false"
      :data-testid="`row-scope-${previewScope.face}`"
      dense
    />

    <!-- 数据画像 -->
    <!-- R170：这张卡只认结构完整的画像。后端把「什么都没解析出来」装进信封回过来时 profile.error 在，
         卡就不许出现 —— 把一条错误渲染成一次统计，正是 R169 扫出来的崩溃现场。 -->
    <div v-if="profile && !profile.error" class="profile-card">
      <div class="profile-header">
        <div class="profile-heading">
          <span class="profile-title">📋 数据画像</span>
          <span class="profile-stats">
            {{ profile.rows }} 行 × {{ profile.column_count || profile.columns?.length || 0 }} 列{{ profileStatsSuffix }}
          </span>
        </div>
        <div class="data-file-actions">
          <button type="button" class="data-action-btn" @click="openDataFile">打开</button>
          <button type="button" class="data-action-btn" @click="downloadDataFile">下载</button>
          <button
            type="button"
            class="data-action-btn data-action-btn--danger"
            :disabled="deletingFile"
            data-testid="data-file-delete"
            @click="requestFileDelete"
          >
            {{ deleteButtonLabel({ pending: isPendingDelete(pendingFileDelete, dataFile), busy: deletingFile, label: '删除所选数据文件' }) }}
          </button>
          <UiButton
            v-if="isPendingDelete(pendingFileDelete, dataFile)"
            variant="ghost"
            size="sm"
            label="取消"
            data-testid="data-file-delete-cancel"
            @click="cancelFileDelete"
          />
        </div>
      </div>

      <UiErrorState
        v-if="fileDeleteError"
        :title="fileDeleteView.title"
        :description="fileDeleteView.description"
        :retryable="false"
        data-testid="data-file-delete-error"
        dense
      />

      <!-- 列信息 -->
      <div class="col-list">
        <div v-for="col in profile.columns" :key="col.name" class="col-item">
          <div class="col-head">
            <span class="col-icon">{{ typeIcon(col.dtype) }}</span>
            <span class="col-name">{{ col.name }}</span>
            <span class="col-type">{{ col.dtype }}</span>
            <span v-if="col.missing_pct > 0" :class="['col-missing', missingClass(col.missing_pct)]">
              {{ col.missing }} 缺失
            </span>
          </div>
          <div v-if="col.min !== undefined" class="col-stats">
            最小 {{ col.min }} · 最大 {{ col.max }} · 均值 {{ col.mean }}
          </div>
          <div v-else-if="col.unique_values !== undefined" class="col-stats">
            {{ col.unique_values }} 个唯一值
          </div>
        </div>
      </div>
    </div>

    <!-- 快捷提问 -->
    <div class="quick-actions" data-testid="data-quick-actions">
      <h4>💡 快捷提问</h4>
      <button v-for="act in quickActions" :key="act.label"
              class="quick-chip" @click="askQuestion(act.query)">
        {{ act.label }}
      </button>
    </div>

    <DocumentPreviewModal
      :open="previewOpen"
      :filename="dataFile"
      kind="table"
      :columns="tableColumns"
      :rows="tableRows"
      :loading="previewLoading"
      :truncated="tableTruncated"
      :error="previewModalError"
      @close="closeDataPreview"
      @download="downloadDataFile"
    />
  </div>
</template>

<style scoped>
.data-panel {
  padding: 0 18px 18px;
  overflow-y: auto;
}

.data-panel::-webkit-scrollbar {
  width: 4px;
}
.data-panel::-webkit-scrollbar-thumb {
  border-radius: 4px;
}

/* 上传 */
.upload-section {
  text-align: center;
  padding: 18px 0 14px;
  border-bottom: 1px solid color-mix(in srgb, var(--legacy-void) 5%, transparent);
}

.upload-btn {
  display: inline-block;
  padding: 10px 22px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}

.upload-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--legacy-emerald) 30%, transparent);
}

.upload-btn.loading {
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.upload-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--legacy-ink-soft);
}

.data-files-section {
  padding: 16px 0 2px;
  border-bottom: 1px solid color-mix(in srgb, var(--legacy-void) 5%, transparent);
}

.section-heading {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 9px;
  color: var(--legacy-ink-strong);
  font-size: 13px;
  font-weight: 600;
}

.file-count {
  min-width: 18px;
  padding: 1px 6px;
  border-radius: 99px;
  background: color-mix(in srgb, var(--legacy-emerald) 12%, transparent);
  color: var(--legacy-emerald-deeper);
  font-size: 11px;
  text-align: center;
}

.data-file-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 210px;
  overflow-y: auto;
  padding-right: 2px;
}

.data-file-item {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 9px;
  padding: 9px 10px;
  border: 1px solid var(--legacy-fill-cool);
  border-radius: 8px;
  background: var(--legacy-paper);
  color: var(--legacy-ink-strong);
  cursor: pointer;
  font: inherit;
  text-align: left;
  transition: border-color 0.15s, background 0.15s, transform 0.15s;
}

.data-file-item:hover {
  border-color: var(--legacy-emerald-300);
  background: var(--legacy-emerald-pale);
  transform: translateX(2px);
}

.data-file-item.active {
  border-color: var(--legacy-emerald);
  background: linear-gradient(135deg, var(--legacy-emerald-mist), var(--legacy-emerald-pale));
  box-shadow: 0 2px 8px color-mix(in srgb, var(--legacy-emerald) 10%, transparent);
}

.data-file-item.loading {
  opacity: 0.65;
}

.data-file-icon {
  flex: 0 0 auto;
  min-width: 30px;
  padding: 4px 3px;
  border-radius: 5px;
  background: var(--legacy-emerald-100);
  color: var(--legacy-emerald-deeper);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.4px;
  text-align: center;
}

.data-file-main {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 3px;
}

.data-file-name {
  overflow: hidden;
  color: var(--legacy-ink-graphite);
  font-size: 12px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.data-file-meta {
  color: var(--legacy-ink-mute);
  font-size: 10px;
}

/* 数据画像 */
.profile-card {
  margin-top: 16px;
  background: color-mix(in srgb, var(--legacy-paper) 80%, transparent);
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--legacy-void) 4%, transparent);
  overflow: hidden;
}

.profile-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: color-mix(in srgb, var(--legacy-emerald) 6%, transparent);
  border-bottom: 1px solid color-mix(in srgb, var(--legacy-void) 4%, transparent);
}

.profile-heading {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.profile-title {
  font-size: 13px;
  font-weight: 600;
}

.profile-stats {
  font-size: 11px;
  color: var(--legacy-ink-soft);
}

.data-file-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.data-action-btn {
  padding: 4px 9px;
  border: 1px solid var(--legacy-line-mute);
  border-radius: 5px;
  color: var(--legacy-ink-graphite-deep);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
}

.col-list {
  padding: 8px 0;
}

.col-item {
  padding: 10px 14px;
  border-bottom: 1px solid var(--legacy-fill-plain);
}

.col-item:last-child {
  border-bottom: none;
}

.col-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.col-icon {
  font-size: 13px;
}

.col-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--legacy-ink-strong);
}

.col-type {
  font-size: 11px;
  color: var(--legacy-ink-soft);
  background: var(--legacy-fill);
  padding: 1px 6px;
  border-radius: 4px;
}

.col-missing {
  margin-left: auto;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
}

.col-missing.warn { color: var(--legacy-ep-orange); }

.col-stats {
  font-size: 11px;
  color: var(--legacy-ink-soft);
}

/* 快捷操作 */
.quick-actions {
  margin-top: 20px;
}

.quick-actions h4 {
  font-size: 13px;
  font-weight: 600;
  color: var(--legacy-ink-strong);
  margin-bottom: 10px;
}

.quick-chip {
  display: block;
  width: 100%;
  text-align: left;
  padding: 10px 14px;
  margin-bottom: 6px;
  background: var(--legacy-paper);
  border: 1px solid var(--legacy-line-hair);
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-family: inherit;
  color: var(--legacy-ink-strong);
  transition: all 0.15s;
}

.quick-chip:hover {
  border-color: var(--legacy-ep-primary);
  color: var(--legacy-ep-primary);
  background: color-mix(in srgb, var(--legacy-ep-primary) 3%, transparent);
  transform: translateX(3px);
}

.data-panel {
  color: var(--text);
  padding: 0 18px 18px;
}

.data-panel::-webkit-scrollbar-thumb {
  background: color-mix(in srgb, var(--legacy-steel) 25%, transparent);
}

.upload-section,
.data-files-section {
  border-bottom-color: var(--line);
}

.upload-btn {
  background: linear-gradient(135deg, var(--cyan), var(--legacy-aqua));
  color: var(--legacy-night);
  box-shadow: 0 10px 24px color-mix(in srgb, var(--legacy-aqua-bright) 14%, transparent);
}

.upload-btn.loading {
  background: color-mix(in srgb, var(--legacy-aqua-bright) 25%, transparent);
  color: var(--ink-soft);
}

.upload-hint,
.data-file-meta,
.col-type,
.col-stats {
  color: var(--muted);
}

.section-heading,
.quick-actions h4,
.col-name {
  color: var(--text);
}

.file-count,
.col-type {
  background: color-mix(in srgb, var(--legacy-aqua-bright) 10%, transparent);
  color: var(--cyan);
}

.data-file-item,
.profile-card,
.col-item,
.quick-chip {
  background: color-mix(in srgb, var(--legacy-paper) 3.5%, transparent);
  border-color: var(--line);
}

.data-file-item:hover,
.data-file-item.active,
.quick-chip:hover {
  border-color: color-mix(in srgb, var(--legacy-aqua-bright) 42%, transparent);
  background: color-mix(in srgb, var(--legacy-aqua-bright) 8%, transparent);
  color: var(--cyan);
}

.data-file-name,
.profile-title,
.profile-stats {
  color: var(--text);
}

.data-action-btn {
  border-color: var(--line-strong);
  background: color-mix(in srgb, var(--legacy-paper) 4%, transparent);
  color: var(--ink-soft);
}

.data-action-btn:hover {
  border-color: var(--blue);
  color: var(--legacy-periwinkle-pale);
}

/* 删除入口（W2-3）：只借 --danger 一个语义色，不给它加底色渐变（视觉文档 §5.3 彩色预算） */
.data-action-btn--danger {
  border-color: var(--border-2);
  color: var(--danger);
}

.data-action-btn--danger:hover {
  border-color: var(--danger);
}

.col-missing.ok {
  color: var(--green);
  background: color-mix(in srgb, var(--green) 10%, transparent);
}

.col-missing.warn {
  color: var(--amber);
  background: color-mix(in srgb, var(--amber) 10%, transparent);
}

.col-missing.bad {
  color: var(--legacy-coral);
  background: color-mix(in srgb, var(--red) 10%, transparent);
}
</style>
