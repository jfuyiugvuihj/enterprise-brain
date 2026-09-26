<script>
import { errorDetail, isPermissionDenied } from '../lib/http'

/**
 * 行级可见范围「只裁掉一部分」那一格（R191 · Bohr 交工第⑥格挂账）。
 *
 * 这句话在这里定义、也只在这里定义：DataPanel 的统计行与本弹窗的预览行是同一件事的两张脸。
 * R186 让面板开始说「全表 120 行中，当前账号可见的 40 行」，而弹窗打开仍只报
 * 「40 行预览」—— 把一部分说成全部（R163 归的 B 类），客户一开弹窗就抓到。两处各写一套
 * 迟早漂成两句互相打架的真话，所以句子只有这一枚出处。
 *
 * 三个不许：
 *   ① 不许数行：两个数一律来自后端 preview.row_scope 的 rows_in / rows_visible
 *      （app/api/v1/data.py::_row_scope_status 构形、:319 挂上），一枚 rows.length 都不参与；
 *   ② 不许猜因由：code 非空（row_scope_denied / no_visible_rows）就是后端自己的裁决，那一支
 *      的句子归后端的 message（走本组件已有的 error prop），这里一个字都不补 —— 只裁掉一部分
 *      的情形 code 恒为空串（契约 docs/api/contract-v1.md「Dataset Row-Level Visibility」）；
 *   ③ 不许越界说话：rows_in === rows_visible（含两者皆 0 的真空表）与读不到 row_scope 的载荷
 *      （上传回包、旧响应）一律空串，产物字节与本格装上之前逐字相同。
 */
export function rowScopeVisibleNote(scope) {
  if (!scope) return ''
  const rowsIn = scopeRowCount(scope.rows_in)
  const rowsVisible = scopeRowCount(scope.rows_visible)
  if (String(scope.code || '') !== '') return ''
  if (rowsIn > 0 && rowsVisible > 0 && rowsVisible < rowsIn) {
    return `全表 ${rowsIn} 行中，当前账号可见的 ${rowsVisible} 行`
  }
  return ''
}

/** 计数只认正整数：后端给 int，界面上不许出现 NaN、负数或小数冒充行数。 */
function scopeRowCount(value) {
  const count = Number(value)
  return Number.isFinite(count) && count > 0 ? Math.trunc(count) : 0
}

/**
 * R314 · 「依据 / 相关制度」这一格的全部判据（图谱撤下一级入口之后的承接面）。
 *
 * 计划书 docs/frontend-plan-2026-09-14.md 撤图谱一级入口时写的是「降为文档预览『依据 /
 * 相关制度』子视图」，而承接面一直没装上：员工读一篇制度，屏幕上没有任何一处告诉他这篇与
 * 别的文档登记过什么关系，那层关系只能去另一屏手输主体/关系/客体才看得到。
 *
 * 四条口径，逐条对上工单判据：
 *   ① 认文档只认整名（去空白、ASCII 大小写折叠后逐字相等）。「员工手册」与「员工手册.pdf」
 *      是两篇文档，差一个字也不许挂到这篇头上（判据②）；认不出来就走空那一支。
 *   ② 取数只有 GET /knowledge-graph/relations 一把读法，与 GraphPanel 同源：不带查询参数取
 *      全量，再在客户端按已取回的行筛。后端那道主体过滤是「整名相等且只筛主体」，拿它按文档
 *      过滤会漏掉本篇出现在客体位的关系，所以筛在客户端而不另发明第二套读法（判据①）。
 *      密级与部门一律不在这里重算，本屏只显示服务端裁过之后交回来的行（判据④）。
 *   ③ idle / loading / failed / empty / matched 各说各的话，读失败绝不落到 empty 那一支
 *      （判据③，与 GraphPanel 里「取不到就摆失败态」同一条不变量）。
 *   ④ 界面不产出任何统计量与推断：只把行摊开，不数「共几条」，不猜某条关系成不成立（判据⑤）。
 */

/** 文档名的比对形状：整名相等才算同一篇，空白与 ASCII 大小写不参与。 */
export function documentIdentityKey(value) {
  const text = String(value ?? '').replace(/\s+/g, '')
  return text.toLowerCase()
}

/** 状态词只翻后端在册的四枚值；翻不出就把服务器给的那个字原样带出，不替它编级别。 */
const RELATION_STATUS_WORDS = {
  candidate: '本人登记，还没核对',
  confirmed: '登记者已确认',
  promoted: '已核实并提升为口径',
  rejected: '已被驳回',
}

export function relationStatusWord(status) {
  const raw = String(status ?? '').trim()
  if (!raw) return ''
  return RELATION_STATUS_WORDS[raw] || raw
}

/** 登记时间只取日期那一段；不是日期形状就原样带出，不替后端格式化它没给的东西。 */
function relationDate(value) {
  const raw = String(value ?? '').trim()
  return /^\d{4}-\d{2}-\d{2}/.test(raw) ? raw.slice(0, 10) : raw
}

/** 对端文档名：登记时漏填就明说漏填，不许留一格空白让人猜。 */
function otherDocumentName(value) {
  const raw = String(value ?? '').trim()
  return raw ? `《${raw}》` : '（登记时没填文档名）'
}

const CURRENT_DOC_WORD = '这篇文档'

/**
 * 把服务端交回来的关系行摊成「这篇文档认得出自己那一头」的行。
 * role：source = 这篇在主体位；target = 这篇在客体位；both = 两端都是这篇。
 * 摊平之后模板只读自己的字段，后端那几枚裸字段名一个字符都不上屏。
 */
export function relationsAboutDocument(filename, relations) {
  const key = documentIdentityKey(filename)
  if (!key) return []
  const rows = []
  const list = Array.isArray(relations) ? relations : []
  list.forEach((item, index) => {
    if (!item || typeof item !== 'object') return
    const subject = String(item.source_entity ?? '').trim()
    const object = String(item.target ?? '').trim()
    const isSubject = !!subject && documentIdentityKey(subject) === key
    const isObject = !!object && documentIdentityKey(object) === key
    if (!isSubject && !isObject) return
    rows.push({
      rowKey: String(item.relation_id ?? '').trim() || 'relation-row-' + index,
      role: isSubject && isObject ? 'both' : isSubject ? 'source' : 'target',
      leftName: isSubject ? CURRENT_DOC_WORD : otherDocumentName(subject),
      rightName: isObject ? CURRENT_DOC_WORD : otherDocumentName(object),
      linkWord: String(item.relation ?? '').trim() || '（登记时没填关系）',
      evidence: String(item.source ?? '').trim(),
      statusWord: relationStatusWord(item.status),
      author: String(item.owner_id ?? '').trim(),
      registeredOn: relationDate(item.created_at),
    })
  })
  return rows
}

/** 五枚面的初值：还没开口之前，这一格一个字也不许替员工下结论。 */
const RELATED_DOCS_IDLE = { face: 'idle', rows: [], message: '', denied: false }

/**
 * 读一次「这篇文档的关联」：出口只有 failed / empty / matched 三种。
 * fetchRelations 抛错、以及回的东西根本不是数组，都算 failed —— 把读失败画成「没有关联」
 * 是本项目反复被抓的那类假话，所以这里从返回值上就把两支分开，不给它们共用一张脸。
 */
export async function readDocumentRelations(filename, fetchRelations) {
  try {
    const list = await fetchRelations()
    if (!Array.isArray(list)) {
      return { ...RELATED_DOCS_IDLE, face: 'failed', message: '关系列表返回的数据结构不对，未能加载。' }
    }
    const rows = relationsAboutDocument(filename, list)
    if (rows.length) return { ...RELATED_DOCS_IDLE, face: 'matched', rows }
    return { ...RELATED_DOCS_IDLE, face: 'empty' }
  } catch (err) {
    const denied = isPermissionDenied(err)
    return {
      ...RELATED_DOCS_IDLE,
      face: 'failed',
      denied,
      message: denied
        ? '当前账号看不到这些关联登记，请联系管理员开通。'
        : errorDetail(err, '服务没有给出原因，稍后再试一次。'),
    }
  }
}

/**
 * 这一格的状态机：idle → loading →（failed | empty | matched）。
 * ref 由 <script setup> 递进来，于是每一次转场都能被测试真跑一遍，而不是只钉源码形状。
 * token 防的是「换了一篇文档，屏上还挂着上一篇的结论」：换了名字或重新打开，迟到的回包一律丢掉。
 */
export function createRelatedDocsStore({ ref, fetchRelations }) {
  const state = ref({ ...RELATED_DOCS_IDLE })
  let token = 0

  async function load(filename) {
    const mine = ++token
    const name = String(filename ?? '').trim()
    if (!name) {
      state.value = { ...RELATED_DOCS_IDLE }
      return
    }
    state.value = { ...RELATED_DOCS_IDLE, face: 'loading' }
    const next = await readDocumentRelations(name, fetchRelations)
    if (mine !== token) return
    state.value = next
  }

  function reset() {
    token += 1
    state.value = { ...RELATED_DOCS_IDLE }
  }

  return { state, load, reset }
}
</script>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../lib/api'
import { UiButton, UiEmptyState, UiErrorState, UiLoadingState } from './ui'

const props = defineProps({
  open: Boolean,
  filename: {
    type: String,
    default: ''
  },
  kind: {
    type: String,
    default: 'text'
  },
  text: {
    type: String,
    default: ''
  },
  blobUrl: {
    type: String,
    default: ''
  },
  columns: {
    type: Array,
    default: () => []
  },
  rows: {
    type: Array,
    default: () => []
  },
  loading: Boolean,
  error: {
    type: String,
    default: ''
  },
  truncated: Boolean,
  // R191：后端 preview.row_scope 的原样载荷（rows_in / rows_visible / code / reason_code）。
  // 缺席（null）= 这一份响应没有行级判定可说，弹窗照旧一个字都不插。
  rowScope: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['close', 'download'])

const rowScopeNote = computed(() => rowScopeVisibleNote(props.rowScope))
// 分隔符由这一格自己带上：后端两数相等（或读不到 row_scope）时它是空串，
// 预览那一行的产物字节与本格装上之前逐字相同（R191 判据②）。
const rowScopeSuffix = computed(() => (rowScopeNote.value ? ` · ${rowScopeNote.value}` : ''))

// R314 · 「依据 / 相关制度」这一格。取数与 GraphPanel 同一把读法：不带参数取全量，
// 交回来的 relations 原样交给客户端按文档名筛，这里不发明第二套取数口径。
async function fetchRelationRows() {
  const response = await api.get('/knowledge-graph/relations')
  return response?.data?.relations
}

const relatedDocs = createRelatedDocsStore({ ref, fetchRelations: fetchRelationRows })
const relatedFace = computed(() => relatedDocs.state.value.face)
const relatedRows = computed(() => relatedDocs.state.value.rows)
const relatedMessage = computed(() => relatedDocs.state.value.message)
const relatedDenied = computed(() => relatedDocs.state.value.denied)
const relatedBusy = computed(() => relatedFace.value === 'loading')

function readRelatedDocs() {
  relatedDocs.load(props.filename)
}

// 弹窗开一次读一次：这一格不缓存上一轮的结论，也不在一篇文档的名字下面摆另一篇的关系。
// 关掉即清空（重开先回到「未加载」），换文档时 store 里的 token 会把迟到的回包丢掉。
// 两枚源分开写：watch 一个每次新建的数组等于每次都算「变了」，预览的 loading/text 一变就重发一发。
watch([() => props.open, () => props.filename], ([open, filename]) => {
  if (!open) {
    relatedDocs.reset()
    return
  }
  relatedDocs.load(filename)
})

// SSR 不跑 onMounted：这一支只补「挂载时就已经是打开的」那种父组件，真浏览器里才成立。
onMounted(() => {
  if (props.open) relatedDocs.load(props.filename)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="preview-modal">
      <div v-if="open" class="preview-overlay" @click.self="emit('close')">
        <section class="preview-container" role="dialog" aria-modal="true" :aria-label="filename">
          <header class="preview-header">
            <div class="preview-heading">
              <strong>{{ filename }}</strong>
              <span v-if="kind === 'pdf'">PDF 阅读</span>
              <span v-else-if="kind === 'table'">数据预览</span>
              <span v-else>文本预览</span>
            </div>
            <div class="preview-actions">
              <UiButton class="preview-btn" type="button" label="下载" data-testid="preview-download" @click="emit('download')" />
              <UiButton class="preview-close" type="button" variant="ghost" aria-label="关闭" label="×" data-testid="preview-close-x" @click="emit('close')" />
            </div>
          </header>

          <div class="preview-body">
            <UiLoadingState v-if="loading" label="正在加载预览..." variant="block" />
            <div v-else-if="error" class="preview-state preview-error">{{ error }}</div>
            <iframe
              v-else-if="kind === 'pdf' && blobUrl"
              class="pdf-frame"
              :src="blobUrl"
              :title="filename"
            ></iframe>
            <pre v-else-if="kind === 'text'" class="text-preview">{{ text }}</pre>
            <div v-else-if="kind === 'table'" class="table-preview" data-preview>
              <div class="table-meta">
                <span>{{ rows.length }} 行预览{{ rowScopeSuffix }}</span>
                <span v-if="truncated">仅显示前 100 行</span>
              </div>
              <div v-if="!rows.length" class="preview-state">暂无数据</div>
              <div v-else class="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th v-for="column in columns" :key="column">{{ column }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, rowIndex) in rows" :key="rowIndex">
                      <td v-for="column in columns" :key="column">
                        {{ row[column] === null || row[column] === undefined ? '' : row[column] }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!--
            R314 · 图谱撤下一级入口之后由这一格承接：员工读一篇制度时就地看到「这篇和哪些
            文档登记过关系、是谁登记的」，不必去另一屏手输三元组。
            五枚面各说各的话：还没查 / 正在查 / 没查到 / 没查到对得上名字的 / 查到了。
            密级与部门不在这里重算，这一格只摆服务端裁过之后交回来的行。
          -->
          <aside class="related-docs" data-testid="document-relations" aria-label="依据与相关制度">
            <div class="related-docs-head">
              <h4>依据与相关制度</h4>
              <span>别人登记过的、文档名与这篇完全相同的关联</span>
            </div>

            <UiLoadingState
              v-if="relatedFace === 'loading'"
              label="正在查这篇文档的关联..."
              :rows="2"
              size="sm"
              dense
            />
            <p v-else-if="relatedFace === 'idle'" class="related-docs-note" data-testid="r314-face-idle">
              还没有去查这篇文档的关联。
            </p>
            <UiErrorState
              v-else-if="relatedFace === 'failed'"
              :title="relatedDenied ? '这个账号看不到关联登记' : '这篇文档的关联没查到'"
              :description="relatedMessage"
              :retryable="!relatedDenied"
              retry-text="重新加载"
              :busy="relatedBusy"
              dense
              data-testid="r314-face-failed"
              @retry="readRelatedDocs"
            />
            <UiEmptyState
              v-else-if="relatedFace === 'empty'"
              title="登记的关联里，没有文档名与这篇相同的"
              description="关联要有人一条条登记，登记过之后就会出现在这里。"
              dense
              data-testid="r314-face-empty"
            />
            <ul v-else class="related-docs-list" data-testid="r314-face-matched">
              <li v-for="row in relatedRows" :key="row.rowKey" class="related-docs-item">
                <div class="related-docs-triple">
                  <strong :class="{ 'is-current': row.role !== 'target' }">{{ row.leftName }}</strong>
                  <span class="related-docs-link">{{ row.linkWord }}</span>
                  <strong :class="{ 'is-current': row.role !== 'source' }">{{ row.rightName }}</strong>
                </div>
                <div class="related-docs-meta">
                  <span>依据：{{ row.evidence || '登记时没填' }}</span>
                  <span v-if="row.statusWord">状态：{{ row.statusWord }}</span>
                  <span v-if="row.author">登记账号：{{ row.author }}</span>
                  <span v-if="row.registeredOn">登记于 {{ row.registeredOn }}</span>
                </div>
              </li>
            </ul>
          </aside>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.preview-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: color-mix(in srgb, var(--legacy-veil) 82%, transparent);
  backdrop-filter: blur(4px);
}

.preview-container {
  width: min(1100px, 96vw);
  height: min(820px, 92vh);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--legacy-night-2);
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--legacy-steel) 18%, transparent);
  box-shadow: 0 24px 80px color-mix(in srgb, var(--legacy-void) 42%, transparent);
}

.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
  border-bottom: 1px solid color-mix(in srgb, var(--legacy-steel) 16%, transparent);
}

.preview-heading {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.preview-heading strong {
  overflow: hidden;
  color: var(--ink);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-heading span {
  flex-shrink: 0;
  color: var(--legacy-ink-steel);
  font-size: 12px;
}

.preview-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.preview-btn,
.preview-close {
  border: 1px solid color-mix(in srgb, var(--legacy-steel) 22%, transparent);
  border-radius: 6px;
  background: color-mix(in srgb, var(--legacy-paper) 4%, transparent);
  color: var(--legacy-tint-azure);
  cursor: pointer;
  font: inherit;
}

.preview-btn {
  padding: 6px 12px;
  font-size: 12px;
}

.preview-btn:hover {
  border-color: var(--legacy-periwinkle-strong);
  color: var(--legacy-periwinkle-mid);
}

.preview-close {
  width: 30px;
  height: 30px;
  font-size: 20px;
  line-height: 1;
}

.preview-close:hover {
  background: color-mix(in srgb, var(--legacy-periwinkle-strong) 12%, transparent);
}

.preview-body {
  flex: 1;
  min-height: 0;
  background: var(--legacy-night-1);
}

.preview-state {
  display: grid;
  height: 100%;
  place-items: center;
  padding: 24px;
  color: var(--legacy-ink-steel);
  font-size: 13px;
}

.preview-error {
  color: var(--legacy-coral);
}

.pdf-frame {
  width: 100%;
  height: 100%;
  border: 0;
  background: var(--legacy-slate-dark);
}

.text-preview {
  height: 100%;
  margin: 0;
  overflow: auto;
  padding: 24px;
  color: var(--legacy-tint-azure-soft);
  background: var(--legacy-night-3);
  font: 13px/1.75 Consolas, "Microsoft YaHei", monospace;
  white-space: pre-wrap;
  word-break: break-word;
}

.table-preview {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 16px;
}

.table-meta {
  display: flex;
  gap: 16px;
  margin-bottom: 10px;
  color: var(--legacy-ink-steel);
  font-size: 12px;
}

.table-scroll {
  flex: 1;
  overflow: auto;
  border: 1px solid color-mix(in srgb, var(--legacy-steel) 16%, transparent);
  background: var(--legacy-night-4);
}

table {
  width: 100%;
  min-width: max-content;
  border-collapse: collapse;
  font-size: 12px;
}

th,
td {
  min-width: 120px;
  max-width: 280px;
  padding: 9px 12px;
  border-right: 1px solid color-mix(in srgb, var(--legacy-steel) 12%, transparent);
  border-bottom: 1px solid color-mix(in srgb, var(--legacy-steel) 12%, transparent);
  text-align: left;
  vertical-align: top;
  white-space: nowrap;
}

th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--legacy-aqua-night);
  color: var(--legacy-mint);
  font-weight: 600;
}

td {
  color: var(--legacy-tint-azure);
}

tr:hover td {
  background: color-mix(in srgb, var(--legacy-periwinkle-strong) 8%, transparent);
}

/* R314 · 「依据 / 相关制度」这一格：贴在预览正文下面的一条抽屉，只借既有的深色档与中性字色。 */
.related-docs {
  flex-shrink: 0;
  max-height: 34%;
  overflow-y: auto;
  padding: 12px 18px 16px;
  border-top: 1px solid color-mix(in srgb, var(--legacy-steel) 16%, transparent);
  background: var(--legacy-night-2);
}

.related-docs-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 8px;
}

.related-docs-head h4 {
  margin: 0;
  color: var(--ink);
  font-size: 13px;
  font-weight: 600;
}

.related-docs-head span {
  color: var(--legacy-ink-steel);
  font-size: 11px;
}

.related-docs-note {
  margin: 0;
  color: var(--legacy-ink-steel);
  font-size: 12px;
}

.related-docs-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.related-docs-item {
  padding: 9px 11px;
  border: 1px solid color-mix(in srgb, var(--legacy-steel) 12%, transparent);
  border-radius: 6px;
  background: var(--legacy-night-4);
}

.related-docs-triple {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--legacy-tint-azure);
  font-size: 12px;
}

.related-docs-triple .is-current {
  color: var(--legacy-mint);
}

.related-docs-link {
  color: var(--legacy-ink-steel);
  font-size: 11px;
}

.related-docs-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 6px;
  color: var(--legacy-ink-steel);
  font-size: 11px;
}

.preview-modal-enter-active,
.preview-modal-leave-active {
  transition: opacity 0.18s ease;
}

.preview-modal-enter-active .preview-container,
.preview-modal-leave-active .preview-container {
  transition: transform 0.18s ease;
}

.preview-modal-enter-from,
.preview-modal-leave-to {
  opacity: 0;
}

.preview-modal-enter-from .preview-container {
  transform: translateY(10px) scale(0.98);
}
</style>
