<script>
/**
 * UiUpload —— 文件选择 / 拖拽上传条（V5 原语 8/8）
 *
 * props:
 *   label      String  控件标题，默认「上传文件」
 *   hint       String  约束说明（会按 accept / maxSizeMb 自动补一句）
 *   accept     String  与 <input accept> 同格式：`.pdf,.docx` 或 `application/pdf`
 *   multiple   Boolean 默认 true
 *   maxSizeMb  Number  0 表示前端不限（后端仍可能拒）
 *   items      Array<{ name, size?, status?, progress?, error? }>  上传中/已上传的清单
 *   busy       Boolean 进行中：禁止再选，进度条接管
 *   disabled   Boolean
 *   error      String  接口返回的成品句（调用方传 formatError(err) 或 normalizeError(err).message）
 *   codeLabel  String  「错误码：xxx」
 *   emptyText  String  清单为空时的文案
 * emits:
 *   select(files)          通过校验的文件，调用方负责真正上传与进度回填
 *   reject({ file, code }) 被前端挡下的项，code 取自 errcodes 码名
 *   remove(index) / retry(index)
 * 图标：内联 SVG 占位（A 线统一换 lucide 时替换 `<svg>` 即可）。
 */
export default { name: 'UiUpload' }
</script>

<script setup>
import { computed, ref } from 'vue'
import { errorText } from '../../lib/errcodes.js'
import { formatBytes, validateFiles } from './upload-rules.js'
import './UiUpload.css'

const props = defineProps({
  label: { type: String, default: '上传文件' },
  hint: { type: String, default: '' },
  accept: { type: String, default: '' },
  multiple: { type: Boolean, default: true },
  maxSizeMb: { type: Number, default: 0 },
  items: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  error: { type: String, default: '' },
  codeLabel: { type: String, default: '' },
  emptyText: { type: String, default: '还没有选择文件' },
})

const emit = defineEmits(['select', 'reject', 'remove', 'retry'])

const input = ref(null)
const dragging = ref(false)
const rejected = ref([])
const blocked = computed(() => props.disabled || props.busy)
const hasItems = computed(() => (props.items || []).length > 0)
const autoHint = computed(() => {
  const parts = []
  if (props.accept) parts.push(`可传 ${props.accept.split(',').map((token) => token.trim()).filter(Boolean).join(' / ')}`)
  if (Number(props.maxSizeMb) > 0) parts.push(`单个不超过 ${props.maxSizeMb}MB`)
  if (!props.multiple) parts.push('一次一个文件')
  return parts.join('，')
})
const hint = computed(() => [props.hint, autoHint.value].filter(Boolean).join(' · '))

function openPicker() {
  if (blocked.value) return
  input.value?.click?.()
}

function take(fileList) {
  const { accepted, rejected: refused } = validateFiles(fileList, {
    accept: props.accept,
    multiple: props.multiple,
    maxSizeMb: props.maxSizeMb,
  })
  rejected.value = refused.map((entry) => ({ name: entry.file?.name || '未命名文件', code: entry.code, message: errorText(entry.code) }))
  refused.forEach((entry) => emit('reject', entry))
  if (accepted.length) emit('select', accepted)
}

function onDragOver(event) {
  if (blocked.value) return
  dragging.value = true
  event.preventDefault()
}

function onDragLeave() {
  dragging.value = false
}

function onDrop(event) {
  dragging.value = false
  if (blocked.value) return
  event.preventDefault()
  take(event.dataTransfer?.files)
}

function progressOf(item) {
  const raw = Number(item?.progress)
  if (!Number.isFinite(raw)) return 0
  return Math.min(Math.max(raw, 0), 100)
}

function statusText(item) {
  if (item?.error) return '未成功'
  if (item?.status === 'done') return '已完成'
  if (item?.status === 'uploading' || progressOf(item) > 0) return '上传中'
  return '待上传'
}

defineExpose({ openPicker, take, rejected })
</script>

<template>
  <div
    class="ui-upload"
    :class="{ 'ui-upload--dragging': dragging, 'ui-upload--busy': busy, 'ui-upload--disabled': disabled }"
    data-testid="ui-upload"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <div class="ui-upload__head">
      <p class="ui-upload__label">{{ label }}</p>
      <p v-if="hint" class="ui-upload__hint">{{ hint }}</p>
    </div>

    <div class="ui-upload__dropzone">
      <span class="ui-upload__icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 16V4" />
          <path d="m7 9 5-5 5 5" />
          <path d="M4 17v1a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3v-1" />
        </svg>
      </span>
      <p class="ui-upload__tip">
        {{ busy ? '正在上传…' : hasItems ? '可继续拖入文件' : '把文件拖到这里，或' }}
      </p>
      <button
        class="ui-upload__pick"
        type="button"
        :disabled="blocked"
        data-testid="ui-upload-pick"
        @click="openPicker"
      >
        选择文件
      </button>
      <input
        ref="input"
        class="ui-upload__input"
        type="file"
        :accept="accept || undefined"
        :multiple="multiple"
        :disabled="blocked"
        tabindex="-1"
        data-testid="ui-upload-input"
        @change="take($event.target.files)"
      />
    </div>

    <ul v-if="hasItems" class="ui-upload__list" data-testid="ui-upload-list">
      <li v-for="(item, index) in items" :key="`${item.name}-${index}`" class="ui-upload__item" data-testid="ui-upload-item">
        <span class="ui-upload__name">{{ item.name }}</span>
        <span v-if="item.size" class="ui-upload__size">{{ formatBytes(item.size) }}</span>
        <span class="ui-upload__status" :class="{ 'ui-upload__status--failed': Boolean(item.error) }">
          {{ item.error || statusText(item) }}
        </span>
        <span
          v-if="progressOf(item) > 0 && !item.error"
          class="ui-upload__bar"
          role="progressbar"
          :aria-valuenow="progressOf(item)"
          aria-valuemin="0"
          aria-valuemax="100"
        >
          <span class="ui-upload__bar-fill" :style="{ width: `${progressOf(item)}%` }"></span>
        </span>
        <span class="ui-upload__item-actions">
          <button v-if="item.error" class="ui-upload__action" type="button" data-testid="ui-upload-retry" @click="emit('retry', index)">重试</button>
          <button class="ui-upload__action" type="button" data-testid="ui-upload-remove" @click="emit('remove', index)">移除</button>
        </span>
      </li>
    </ul>
    <p v-else class="ui-upload__empty" data-testid="ui-upload-empty">{{ emptyText }}</p>

    <ul v-if="rejected.length" class="ui-upload__rejected" role="alert" data-testid="ui-upload-rejected">
      <li v-for="entry in rejected" :key="entry.name" class="ui-upload__rejected-item">
        {{ entry.name }}：{{ entry.message }}
        <span class="ui-upload__code">{{ entry.code }}</span>
      </li>
    </ul>

    <div v-if="error || codeLabel" class="ui-upload__error" role="alert">
      <span v-if="error">{{ error }}</span>
      <span v-if="codeLabel" class="ui-upload__code">{{ codeLabel }}</span>
    </div>
  </div>
</template>
