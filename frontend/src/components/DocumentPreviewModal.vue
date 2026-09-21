<script setup>
import { UiLoadingState } from './ui'

defineProps({
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
  truncated: Boolean
})

const emit = defineEmits(['close', 'download'])
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
                <span>{{ rows.length }} 行预览</span>
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
