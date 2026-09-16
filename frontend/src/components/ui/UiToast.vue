<script>
/**
 * UiToast —— 单条轻提示（V5 原语 6/8）
 *
 * props:
 *   tone        'info' | 'success' | 'warning' | 'danger'   默认 info
 *   message     String   一句人话（来自 normalizeError / formatError）
 *   codeLabel   String   「错误码：xxx」小字，仅未知码时有值
 *   retryable   Boolean  是否显示「重试」
 *   sticky      Boolean  不自动消失
 *   dismissible Boolean  默认 true
 * emits: close, retry
 * 说明：tone 只借语义色 token，不加发光；danger/warning 用 role="alert"，
 *      info/success 用 role="status"，读屏不会误打断。
 */
export default { name: 'UiToast' }
</script>

<script setup>
import { computed } from 'vue'
import './UiToast.css'

const props = defineProps({
  tone: { type: String, default: 'info' },
  message: { type: String, default: '' },
  codeLabel: { type: String, default: '' },
  retryable: { type: Boolean, default: false },
  sticky: { type: Boolean, default: false },
  dismissible: { type: Boolean, default: true },
})

const emit = defineEmits(['close', 'retry'])

const toneClass = computed(() => (['info', 'success', 'warning', 'danger'].includes(props.tone) ? props.tone : 'info'))
const role = computed(() => (props.tone === 'danger' || props.tone === 'warning' ? 'alert' : 'status'))
</script>

<template>
  <div class="ui-toast" :class="`ui-toast--${toneClass}`" :role="role" data-testid="ui-toast">
    <span class="ui-toast__mark" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <template v-if="tone === 'success'">
          <circle cx="12" cy="12" r="9" />
          <path d="m8.5 12.5 2.4 2.4 4.6-5" />
        </template>
        <template v-else-if="tone === 'danger' || tone === 'warning'">
          <path d="M12 4.5 3.5 19h17L12 4.5Z" />
          <path d="M12 10v4" />
          <path d="M12 16.6h.01" />
        </template>
        <template v-else>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 11v5" />
          <path d="M12 8.4h.01" />
        </template>
      </svg>
    </span>

    <span class="ui-toast__text">
      <slot>{{ message }}</slot>
      <span v-if="codeLabel" class="ui-toast__code" data-testid="ui-toast-code">{{ codeLabel }}</span>
    </span>

    <span class="ui-toast__actions">
      <button v-if="retryable" class="ui-toast__action" type="button" data-testid="ui-toast-retry" @click="emit('retry')">重试</button>
      <button v-if="dismissible" class="ui-toast__dismiss" type="button" aria-label="关闭提示" data-testid="ui-toast-close" @click="emit('close')">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true">
          <path d="M6 6l12 12M18 6 6 18" />
        </svg>
      </button>
    </span>
  </div>
</template>
