<script>
/**
 * ArtifactList —— 分析产物列表（W2-1：接上后端已交付但界面用不到的两条契约）
 *
 * 看板 §4O.2 记着的两条悬空：R2 的 GET /api/v1/artifacts 分页列表在前端 0 消费者；
 * R8 的 DELETE /api/v1/artifacts/{id} 与 DELETE /data-files/{filename} 没有任何删除入口
 * —— 误生成的图表与误传的数据在界面上删不掉，存量清理只能走脚本。这个组件接上列表与
 * 产物侧删除，数据文件侧的删除入口在 DataPanel.vue。
 *
 * 三条判据写在代码里，不靠 review 记忆：
 *   ① 四态各有唯一出口，顺序即语义：进行 -> 失败 -> 空 -> 列表。判据集中在 listFace() 一个
 *      纯函数里，模板只认它的返回值。「无权限」与「空列表」是两张脸而不是两张同样的人：
 *      403 走 UiErrorState 且 retryable=false（权限不是重试能试出来的），200 空数组走
 *      UiEmptyState。空列表是 200 响应、走不到 catch，所以两条路径天然不会互相冒充。
 *   ② 产物字节只从带 Bearer 的通道取：lib/artifacts.js 的 fetchArtifactBlob（全站唯一的
 *      axios 实例挂 Authorization）。content_url / download_url 一律不进 <img :src>、
 *      <a :href> 或 window.open —— 那些请求不带 Authorization，会把 401/403 伪装成
 *      「图坏了」（ChartViewer.vue:8-10 同一条判据）。界面上出现过的地址只有 blob: 地址。
 *   ③ 删除是两步内联确认，不用 window.confirm：第一次点击把按钮变成「确认删除？」，第二次
 *      点击才发 DELETE。状态机是 advanceDelete() 这个纯函数，点另一行只会把待确认挪到那一行
 *      （返回 arm 而不是 execute），所以一次错位点击不可能删掉没点过的行。DataPanel 的数据
 *      文件删除共用同一个状态机，两处行为不会各写一遍再各自漂移。
 *
 * 文案纪律（B-5 ②）：给人看的句子只说人话 + 下一步，后端码名走 lib/errcodes.js 的独立通道，
 * 不进正文。artifact_type 的原始值只进 data-artifact-type 属性供排查与 e2e 取数，屏上显示的
 * 是 artifactTypeLabel() 的中文；未知类型宁可说「分析产物」也不回显后端原串。
 *
 * 视觉：只借 theme.css 的既有类（.section-head / .chip）与 var(--*) 令牌，零裸色值；
 * 按钮一律用 UiButton 原语，不手搓第二套控件。
 */
export default { name: 'ArtifactList' }

/** 一页取多少条。后端 MAX_LIST_LIMIT=100（app/api/v1/artifacts.py），20 够一屏，超出走「读取更多」。 */
export const ARTIFACT_PAGE_SIZE = 20

const TYPE_LABELS = {
  chart: '图表',
  report: '报告',
  document: '文档',
  export: '导出数据',
  table: '数据表',
}

/** 产物类型 -> 中文。未知值给通用说法，绝不把后端原串画上屏。 */
export function artifactTypeLabel(value) {
  const key = typeof value === 'string' ? value.trim().toLowerCase() : ''
  return TYPE_LABELS[key] || '分析产物'
}

/**
 * ISO 串 -> 「YYYY-MM-DD HH:MM」。刻意不做时区换算也不走 Intl：列表要的是与后端记录一致的
 * 可比时间，不是按访客机器改写的「本地惊喜」；与 DataPanel 的 formatModifiedAt 同一口径。
 */
export function formatArtifactTime(value) {
  const raw = typeof value === 'string' ? value.trim() : ''
  if (!raw) return ''
  const parts = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(raw)
  if (!parts) return raw.replace('T', ' ')
  const [, year, month, day, hour, minute] = parts
  return year + '-' + month + '-' + day + ' ' + hour + ':' + minute
}

/** 过期时间只在后端真给了的时候说，且只给到日：时刻级的过期提醒没有可操作的余地。 */
export function artifactExpiryText(value) {
  const stamp = formatArtifactTime(value)
  return stamp ? '有效期至 ' + stamp.slice(0, 10) : ''
}

/** 后端行 -> 视图模型。snake_case 字段名只在这一个函数里出现，模板里全是视图字段。 */
export function mapArtifactRow(row) {
  const source = row && typeof row === 'object' ? row : {}
  return {
    artifactId: String(source.artifact_id || ''),
    filename: String(source.filename || '未命名产物'),
    typeRaw: String(source.artifact_type || ''),
    typeLabel: artifactTypeLabel(source.artifact_type),
    contentUrl: String(source.content_url || ''),
    downloadUrl: String(source.download_url || ''),
    createdAt: formatArtifactTime(source.created_at),
    expiryText: artifactExpiryText(source.expires_at),
  }
}

/** 四态判定：进行 -> 失败 -> 空 -> 列表。失败必须先于「空」被否掉，否则读不到列表会被说成没有产物。 */
export function listFace(state) {
  if (state.loading) return 'loading'
  if (state.errorText) return 'error'
  if (!Number(state.rowCount)) return 'empty'
  return 'list'
}

/** 列表失败态的三件套：无权限与「坏了」各一句人话，只有后者配重试。 */
export function listErrorView(state) {
  const denied = Boolean(state.denied)
  return {
    title: denied ? '没有权限查看分析产物' : '分析产物没读到',
    description: denied
      ? '当前账号没有查看分析产物的权限，请联系管理员开通。'
      : state.detail || '分析产物列表加载失败，请稍后重试。',
    retryable: !denied,
  }
}

/**
 * 取内容失败态：没权限与坏了分开，坏了才允许再取一次（fetchArtifactBlob 已把错误归成人话）。
 * retryable 只有两个来源：调用方明确说「再试也没用」（这一行根本没有取字节的地址、
 * 或 lib/artifacts.js 的分类器判定不可重试）。没有人说不能重试时默认允许。
 */
export function openErrorView(state) {
  const denied = Boolean(state.denied)
  return {
    title: denied ? '没有权限打开这条产物' : '这条产物没能打开',
    description: denied
      ? '当前账号没有查看这份内容的权限，请联系管理员开通。'
      : state.detail || '产物内容没能取回来，请稍后重试。',
    retryable: !denied && state.retryable !== false,
  }
}

/**
 * 删除失败态。retryable 恒为 false，这不是偷懒而是保留判据：失败卡上放一个直接重发 DELETE 的
 * 按钮，等于把两步确认压成一步。用户再点一次「删除」会重新走 arm -> execute。
 */
export function deleteErrorView(state) {
  const subject = state.subject || '这条产物'
  const denied = Boolean(state.denied)
  return {
    title: denied ? '没有权限删除' + subject : subject + '没能删除',
    description: denied
      ? '当前账号没有删除它的权限，请联系管理员开通。'
      : state.detail || '删除没有完成，请稍后再试。',
    retryable: false,
  }
}

/**
 * 两步内联确认状态机（DataPanel 的数据文件删除共用这一个实现）。
 * idle = 没有可删目标；arm = 第一次点击，只把按钮改成确认文案；execute = 同一目标第二次点击。
 * 换目标只会返回 arm，永远不会因为「上一行点过一次」就把这一行顺手删掉。
 */
export function advanceDelete(pendingId, targetId) {
  const target = typeof targetId === 'string' ? targetId : ''
  if (!target) return 'idle'
  return pendingId === target ? 'execute' : 'arm'
}

/** 这一行是不是「等待确认」的那一行。 */
export function isPendingDelete(pendingId, itemId) {
  return Boolean(itemId) && pendingId === itemId
}

/** 删除按钮的三档文案：常态 / 待确认 / 删除中。 */
export function deleteButtonLabel(state) {
  if (state.busy) return '删除中…'
  return state.pending ? '确认删除？' : (state.label || '删除')
}

/**
 * 取字节的地址：content_url 优先，后端没给才退到 download_url。
 * 两个地址都只能从 fetchArtifactBlob 走（带 Bearer），任何情况下不进 <img :src> 或 <a :href>。
 */
export function openTargetUrl(row) {
  const source = row && typeof row === 'object' ? row : {}
  return String(source.contentUrl || source.downloadUrl || '')
}

/** 取回来的字节是不是可以就地显示的图片。 */
export function isOpenableImage(mediaType) {
  return String(mediaType || '').toLowerCase().startsWith('image/')
}

/** 打开按钮的三档文案：常态 / 正在取字节 / 已展开（再点收起）。 */
export function openButtonLabel(state) {
  if (state.busy) return '打开中…'
  return state.previewing ? '收起' : '打开'
}
</script>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { errorDetail, http, isPermissionDenied } from '../lib/http'
import { fetchArtifactBlob } from '../lib/artifacts'
import { UiButton, UiEmptyState, UiErrorState, UiLoadingState } from './ui'

const rows = ref([])
const total = ref(0)
const offset = ref(0)
const hasMore = ref(false)
const loading = ref(false)
const loadingMore = ref(false)
const loadError = ref('')
const loadDenied = ref(false)
const moreError = ref('')

const pendingDelete = ref('')
const deletingId = ref('')
const openingId = ref('')
const previewId = ref('')
const previewUrl = ref('')
const actionError = ref(null)

let activeHandle = null
let openToken = 0

const face = computed(() => listFace({
  loading: loading.value,
  errorText: loadError.value,
  rowCount: rows.value.length,
}))
const listView = computed(() => listErrorView({ denied: loadDenied.value, detail: loadError.value }))
const actionView = computed(() => actionError.value || {})

function findRow(artifactId) {
  return rows.value.find(row => row.artifactId === artifactId) || null
}

/** blob: 地址只有一个，换一条产物或卸载时先释放上一个，不给演示留一地内存。 */
function releasePreview() {
  if (activeHandle) activeHandle.revoke()
  activeHandle = null
  previewId.value = ''
  previewUrl.value = ''
}

function dropList() {
  rows.value = []
  total.value = 0
  offset.value = 0
  hasMore.value = false
  pendingDelete.value = ''
}

async function loadArtifacts(options) {
  const append = Boolean(options && options.append)
  if (append ? loadingMore.value || loading.value : loading.value) return
  if (append) { loadingMore.value = true; moreError.value = '' } else { loading.value = true; loadError.value = ''; loadDenied.value = false }
  const requestOffset = append ? offset.value : 0
  try {
    // _ts 沿用 DataPanel 读列表的防缓存写法；后端多余查询参数不校验，不影响 limit/offset 判定。
    const res = await http.get('/artifacts', {
      params: { limit: ARTIFACT_PAGE_SIZE, offset: requestOffset, _ts: Date.now() },
    })
    const page = Array.isArray(res.data.artifacts) ? res.data.artifacts : []
    const mapped = page.map(mapArtifactRow)
    const returned = Number(res.data.returned ?? mapped.length)
    rows.value = append ? rows.value.concat(mapped) : mapped
    total.value = Number(res.data.total ?? mapped.length)
    hasMore.value = Boolean(res.data.has_more)
    offset.value = requestOffset + returned
  } catch (err) {
    const denied = isPermissionDenied(err)
    const detail = errorDetail(err, append ? '后面的产物没读到' : '分析产物列表加载失败')
    if (append) {
      moreError.value = detail
    } else {
      dropList()
      loadDenied.value = denied
      loadError.value = detail
    }
  } finally {
    if (append) loadingMore.value = false
    else loading.value = false
  }
}

function reload() {
  releasePreview()
  loadError.value = ''
  loadDenied.value = false
  moreError.value = ''
  actionError.value = null
  loadArtifacts()
}

function noteAction(view, kind, artifactId) {
  actionError.value = {
    title: view.title,
    description: view.description,
    retryable: view.retryable,
    kind,
    artifactId,
  }
}

/** 非图片产物（报告、导出表）取回来后交给浏览器另存：地址是 blob:，不是产物地址。 */
function saveBlob(handle, item) {
  const link = document.createElement('a')
  link.href = handle.objectUrl
  link.download = item.filename || 'artifact'
  link.click()
}

async function openArtifact(item) {
  if (!item) return
  if (previewId.value === item.artifactId) { releasePreview(); return }
  if (openingId.value) return
  const target = openTargetUrl(item)
  if (!target) {
    noteAction(openErrorView({ denied: false, retryable: false, detail: '这条产物没有可打开的地址。' }), 'open', item.artifactId)
    return
  }
  const token = ++openToken
  openingId.value = item.artifactId
  actionError.value = null
  try {
    const handle = await fetchArtifactBlob(target)
    if (token !== openToken) { handle.revoke(); return }
    releasePreview()
    activeHandle = handle
    if (isOpenableImage(handle.mediaType)) {
      previewId.value = item.artifactId
      previewUrl.value = handle.objectUrl
    } else {
      saveBlob(handle, item)
    }
  } catch (err) {
    if (token !== openToken || err.code === 'aborted') return
    // retryable 吃 fetchArtifactBlob 带回来的分类结果：404「内容已被移除」再配一个重试按钮，
    // 只会把同一句失败读第二遍（lib/artifacts.js:55 已把 retryable 挂在 error 上）。
    noteAction(
      openErrorView({ denied: isPermissionDenied(err), detail: err.message || '', retryable: err.retryable }),
      'open',
      item.artifactId,
    )
  } finally {
    if (token === openToken) openingId.value = ''
  }
}

function retryAction() {
  const note = actionError.value
  if (!note || note.kind !== 'open') return
  openArtifact(findRow(note.artifactId))
}

async function removeArtifact(item) {
  if (!item || deletingId.value) return
  deletingId.value = item.artifactId
  actionError.value = null
  try {
    await http.delete('/artifacts/' + encodeURIComponent(item.artifactId))
    if (previewId.value === item.artifactId) releasePreview()
    rows.value = rows.value.filter(row => row.artifactId !== item.artifactId)
    total.value = Math.max(0, total.value - 1)
    // 后端 newest-first（R2 的排序判据）：删掉一行会让后面每行的下标前移一位，
    // 不把 offset 也退一格，下一页会整行漏掉一条。
    offset.value = Math.max(0, offset.value - 1)
  } catch (err) {
    noteAction(deleteErrorView({ denied: isPermissionDenied(err), detail: errorDetail(err, '') }), 'delete', item.artifactId)
  } finally {
    deletingId.value = ''
  }
}

function requestDelete(item) {
  if (!item || deletingId.value || loading.value || loadingMore.value) return
  const step = advanceDelete(pendingDelete.value, item.artifactId)
  if (step === 'arm') { pendingDelete.value = item.artifactId; actionError.value = null; return }
  if (step !== 'execute') return
  pendingDelete.value = ''
  removeArtifact(item)
}

function cancelDelete() {
  pendingDelete.value = ''
}

onBeforeUnmount(() => {
  openToken += 1
  releasePreview()
})

defineExpose({ loadArtifacts, reload })
</script>

<template>
  <section class="artifact-section" data-testid="artifact-list">
    <div class="section-head">
      <h4>🧾 分析产物</h4>
      <div class="artifact-tools">
        <span v-if="total" class="chip">{{ total }} 项</span>
        <UiButton
          variant="ghost"
          size="sm"
          :label="loading ? '正在读取…' : '刷新'"
          :loading="loading"
          data-testid="artifact-reload"
          @click="reload"
        />
      </div>
    </div>

    <UiLoadingState v-if="face === 'loading'" label="正在读取分析产物..." dense />
    <UiErrorState
      v-else-if="face === 'error'"
      :title="listView.title"
      :description="listView.description"
      :retryable="listView.retryable"
      retry-text="重新加载"
      :busy="loading"
      data-testid="artifact-list-error"
      dense
      @retry="reload"
    />
    <UiEmptyState
      v-else-if="face === 'empty'"
      title="暂无分析产物"
      description="让 AI 生成一张图表或一份报告，成果会出现在这里。"
      dense
    />

    <template v-else>
      <div class="artifact-list" data-testid="artifact-items">
        <div
          v-for="item in rows"
          :key="item.artifactId"
          :data-artifact-type="item.typeRaw"
          :class="['artifact-item', { 'artifact-item--pending': isPendingDelete(pendingDelete, item.artifactId), 'artifact-item--preview': previewId === item.artifactId }]"
          data-testid="artifact-item"
        >
          <span class="artifact-type">{{ item.typeLabel }}</span>
          <span class="artifact-main">
            <span class="artifact-name">{{ item.filename }}</span>
            <span class="artifact-meta">
              {{ item.createdAt }}
              <template v-if="item.expiryText">· {{ item.expiryText }}</template>
            </span>
          </span>
          <span class="artifact-actions">
            <UiButton
              variant="secondary"
              size="sm"
              :label="openButtonLabel({ busy: openingId === item.artifactId, previewing: previewId === item.artifactId })"
              :loading="openingId === item.artifactId"
              data-testid="artifact-open"
              @click="openArtifact(item)"
            />
            <UiButton
              variant="danger"
              size="sm"
              :label="deleteButtonLabel({ pending: isPendingDelete(pendingDelete, item.artifactId), busy: deletingId === item.artifactId, label: '删除' })"
              :loading="deletingId === item.artifactId"
              data-testid="artifact-delete"
              @click="requestDelete(item)"
            />
            <UiButton
              v-if="isPendingDelete(pendingDelete, item.artifactId)"
              variant="ghost"
              size="sm"
              label="取消"
              data-testid="artifact-delete-cancel"
              @click="cancelDelete"
            />
          </span>
        </div>
      </div>

      <figure v-if="previewId" class="artifact-preview" data-testid="artifact-preview">
        <img :src="previewUrl" :alt="findRow(previewId) ? findRow(previewId).filename : '产物内容'" />
        <figcaption>{{ findRow(previewId) ? findRow(previewId).filename : '' }}</figcaption>
      </figure>

      <UiErrorState
        v-if="actionError"
        :title="actionView.title"
        :description="actionView.description"
        :retryable="actionView.retryable"
        retry-text="再试一次"
        :busy="Boolean(openingId)"
        data-testid="artifact-action-error"
        dense
        @retry="retryAction"
      />

      <div v-if="hasMore" class="artifact-more">
        <UiButton
          variant="ghost"
          size="sm"
          :label="loadingMore ? '正在读取…' : '读取更多'"
          :loading="loadingMore"
          data-testid="artifact-more"
          @click="loadArtifacts({ append: true })"
        />
      </div>
      <p v-if="moreError" class="artifact-more-error" role="alert" data-testid="artifact-more-error">{{ moreError }}</p>
    </template>
  </section>
</template>

<style scoped>
.artifact-section {
  padding: var(--s-4) 0 var(--s-1);
  border-bottom: 1px solid var(--border-1);
}

.artifact-tools {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}

.artifact-list {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.artifact-item {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  padding: var(--s-2) var(--s-3);
  border: 1px solid var(--border-1);
  border-radius: var(--r-sm);
  background: var(--surface-2);
  transition: border-color var(--motion-fast);
}

.artifact-item--pending {
  border-color: var(--danger);
}

.artifact-item--preview {
  border-color: var(--accent);
}

.artifact-type {
  flex: 0 0 auto;
  min-width: var(--s-7);
  padding: var(--s-1);
  border-radius: var(--r-sm);
  background: var(--surface-3);
  color: var(--text-2);
  font-size: var(--t-xs);
  text-align: center;
}

.artifact-main {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: var(--s-1);
}

.artifact-name {
  overflow: hidden;
  color: var(--text-1);
  font-size: var(--t-sm);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artifact-meta {
  color: var(--text-3);
  font-size: var(--t-xs);
}

.artifact-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: var(--s-1);
}

/* 预览只绑 blob: 地址；限高是为了不让一张长图把整块面板顶走。 */
.artifact-preview {
  margin: var(--s-2) 0 0;
  max-width: 100%;
}

.artifact-preview img {
  display: block;
  max-width: 100%;
  max-height: 240px;
  border: 1px solid var(--border-1);
  border-radius: var(--r-sm);
}

.artifact-preview figcaption {
  margin-top: var(--s-1);
  color: var(--text-3);
  font-size: var(--t-xs);
}

.artifact-more {
  margin-top: var(--s-2);
  text-align: center;
}

.artifact-more-error {
  margin: var(--s-2) 0 0;
  color: var(--danger);
  font-size: var(--t-xs);
}
</style>
