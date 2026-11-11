<script>
/**
 * UiToastHost —— UiToast 的挂载点（不算第 9 个原语，是 UiToast 的容器）
 *
 * props: position 'br' | 'tr' | 'tc'（默认 br）
 * 用法：A 线在 App.vue 根节点挂一次 `<UiToastHost />`，
 *      各面板 catch 里只需 `notifyError(err)`，不再插值 `{{ error }}`。
 * 空态：没有任何提示时容器是空的，不出占位框。
 */
export default { name: 'UiToastHost' }
</script>

<script setup>
import { computed } from 'vue'
import UiToast from './UiToast.vue'
import { useToasts } from './toasts.js'
import './UiToastHost.css'

const props = defineProps({
  position: { type: String, default: 'br' },
})

const emit = defineEmits(['retry'])
const { toasts, dismiss } = useToasts()
const positionClass = computed(() => (['br', 'tr', 'tc'].includes(props.position) ? props.position : 'br'))
</script>

<template>
  <div class="ui-toast-host" :class="`ui-toast-host--${positionClass}`" data-testid="ui-toast-host" role="region" aria-label="操作提示" aria-live="polite">
    <UiToast
      v-for="toast in toasts"
      :key="toast.id"
      :tone="toast.tone"
      :message="toast.message"
      :code-label="toast.codeLabel"
      :retryable="toast.retryable"
      data-testid="ui-toast-item"
      @close="dismiss(toast.id)"
      @retry="emit('retry', toast); dismiss(toast.id)"
    />
  </div>
</template>

