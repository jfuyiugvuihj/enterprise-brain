<script setup>
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
            <div v-if="loading" class="preview-state">正在加载预览...</div>
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
  background: rgba(3, 7, 16, .82);
  backdrop-filter: blur(4px);
}

.preview-container {
  width: min(1100px, 96vw);
  height: min(820px, 92vh);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #111b2c;
  border-radius: 10px;
  border: 1px solid rgba(157, 178, 207, .18);
  box-shadow: 0 24px 80px rgba(0, 0, 0, .42);
}

.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(157, 178, 207, .16);
}

.preview-heading {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.preview-heading strong {
  overflow: hidden;
  color: #f0f4fb;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-heading span {
  flex-shrink: 0;
  color: #9eacc1;
  font-size: 12px;
}

.preview-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.preview-btn,
.preview-close {
  border: 1px solid rgba(157, 178, 207, .22);
  border-radius: 6px;
  background: rgba(255, 255, 255, .04);
  color: #dbe5f3;
  cursor: pointer;
  font: inherit;
}

.preview-btn {
  padding: 6px 12px;
  font-size: 12px;
}

.preview-btn:hover {
  border-color: #6a8cff;
  color: #aabdff;
}

.preview-close {
  width: 30px;
  height: 30px;
  font-size: 20px;
  line-height: 1;
}

.preview-close:hover {
  background: rgba(106, 140, 255, .12);
}

.preview-body {
  flex: 1;
  min-height: 0;
  background: #0b1220;
}

.preview-state {
  display: grid;
  height: 100%;
  place-items: center;
  padding: 24px;
  color: #9eacc1;
  font-size: 13px;
}

.preview-error {
  color: #ff9da5;
}

.pdf-frame {
  width: 100%;
  height: 100%;
  border: 0;
  background: #525659;
}

.text-preview {
  height: 100%;
  margin: 0;
  overflow: auto;
  padding: 24px;
  color: #e7eef9;
  background: #0d1728;
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
  color: #9eacc1;
  font-size: 12px;
}

.table-scroll {
  flex: 1;
  overflow: auto;
  border: 1px solid rgba(157, 178, 207, .16);
  background: #142035;
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
  border-right: 1px solid rgba(157, 178, 207, .12);
  border-bottom: 1px solid rgba(157, 178, 207, .12);
  text-align: left;
  vertical-align: top;
  white-space: nowrap;
}

th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #172a36;
  color: #8ce2bf;
  font-weight: 600;
}

td {
  color: #dbe5f3;
}

tr:hover td {
  background: rgba(106, 140, 255, .08);
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
