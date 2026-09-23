<script>
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
</script>

<script setup>
import { computed } from 'vue'
import { UiLoadingState } from './ui'

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
              <button class="preview-btn" type="button" @click="emit('download')">下载</button>
              <button class="preview-close" type="button" aria-label="关闭" @click="emit('close')">×</button>
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
