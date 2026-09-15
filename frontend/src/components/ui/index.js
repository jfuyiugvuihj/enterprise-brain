/**
 * V5 token 化原语的统一出口（A 线接线时只 import 这里）
 *
 * 样式随组件自带：每个 .vue 在 <script setup> 里 import 同目录 .css，
 * 全局类名统一 ui- 前缀，不再叠加主题层覆盖（视觉文档 §11 最后一条）。
 */
export { default as UiButton } from './UiButton.vue'
export { default as UiField } from './UiField.vue'
export { default as UiSelect } from './UiSelect.vue'
export { default as UiTable } from './UiTable.vue'
export { default as UiDialog } from './UiDialog.vue'
export { default as UiToast } from './UiToast.vue'
export { default as UiToastHost } from './UiToastHost.vue'
export { default as UiTabs } from './UiTabs.vue'
export { default as UiUpload } from './UiUpload.vue'
export { default as UiEmptyState } from './UiEmptyState.vue'
export { default as UiErrorState } from './UiErrorState.vue'

export { useToasts, pushToast, notifyError, notifySuccess, dismissToast, clearToasts } from './toasts.js'
export { normalizeError, formatError, errorCodeLabel, isRetryable, ERROR_CODES } from '../../lib/errcodes.js'
export { moveActiveIndex, findIndexByPrefix } from './list-nav.js'
export { nextSortState, sortRows, ariaSortFor } from './table-sort.js'
export { validateFiles, formatBytes } from './upload-rules.js'
export { nextFocusableIndex, FOCUSABLE_SELECTOR } from './focus-trap.js'
