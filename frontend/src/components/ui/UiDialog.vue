<script>
/**
 * UiDialog —— 模态框（V5 原语 5/8）
 *
 * props:
 *   modelValue      Boolean  v-model，控制开合
 *   title           String   标题（20px 档，见视觉文档 §6.1）
 *   description     String   标题下一句人话说明
 *   size            String   'sm' | 'md' | 'lg'，默认 md
 *   closeOnBackdrop Boolean  默认 true
 *   closeOnEsc      Boolean  默认 true
 *   busy            Boolean  页脚主按钮置忙（配合 UiButton :loading）
 *   ariaLabel       String   无可见标题时的无障碍名
 * emits: update:modelValue, open, close
 * slots: default（正文）、footer（操作区）
 * 键盘：Esc 关闭；Tab 在弹层内循环，不会逃到背景页面；关闭后焦点回到打开前的元素。
 */
export default { name: 'UiDialog' }
</script>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { FOCUSABLE_SELECTOR, nextFocusableIndex, shouldCloseOnKey } from './focus-trap.js'
import './UiDialog.css'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  description: { type: String, default: '' },
  size: { type: String, default: 'md' },
  closeOnBackdrop: { type: Boolean, default: true },
  closeOnEsc: { type: Boolean, default: true },
  busy: { type: Boolean, default: false },
  ariaLabel: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'open', 'close'])

const panel = ref(null)
const titleId = 'ui-dialog-title'
const descId = 'ui-dialog-description'
const sizeClass = computed(() => (['sm', 'md', 'lg'].includes(props.size) ? props.size : 'md'))
let restoreFocusTo = null

function openNext(next) {
  if (props.modelValue === next) return
  emit('update:modelValue', next)
  if (next) emit('open')
  else emit('close')
}

function focusables() {
  if (!panel.value || typeof panel.value.querySelectorAll !== 'function') return []
  return Array.from(panel.value.querySelectorAll(FOCUSABLE_SELECTOR)).filter((node) => node.offsetParent !== null || node === document.activeElement)
}

function onKeydown(event) {
  if (!props.modelValue) return
  if (props.closeOnEsc && shouldCloseOnKey(event.key, event.target?.tagName)) {
    event.preventDefault()
    openNext(false)
    return
  }
  if (event.key !== 'Tab') return
  const nodes = focusables()
  if (!nodes.length) {
    event.preventDefault()
    return
  }
  const current = nodes.indexOf(document.activeElement)
  const next = nextFocusableIndex(current, nodes.length, event.shiftKey)
  if (next >= 0) {
    event.preventDefault()
    nodes[next].focus()
  }
}

watch(
  () => props.modelValue,
  (next) => {
    if (typeof document === 'undefined') return
    if (next) {
      restoreFocusTo = document.activeElement
      nextTick(() => {
        const nodes = focusables()
        ;(nodes[0] || panel.value)?.focus?.()
      })
      document.addEventListener('keydown', onKeydown, true)
    } else {
      document.removeEventListener('keydown', onKeydown, true)
      if (restoreFocusTo?.focus) restoreFocusTo.focus()
      restoreFocusTo = null
    }
  },
)

onBeforeUnmount(() => {
  if (typeof document !== 'undefined') document.removeEventListener('keydown', onKeydown, true)
})

function close() {
  openNext(false)
}

defineExpose({ close, panel })
</script>

<template>
  <Teleport to="body">
    <div
      v-if="modelValue"
      class="ui-dialog"
      data-testid="ui-dialog"
      @click.self="closeOnBackdrop && close()"
    >
      <div
        class="ui-dialog__panel"
        :class="`ui-dialog__panel--${sizeClass}`"
        ref="panel"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="title ? titleId : undefined"
        :aria-describedby="description ? descId : undefined"
        :aria-label="title ? undefined : ariaLabel || undefined"
        tabindex="-1"
      >
        <header class="ui-dialog__head">
          <div class="ui-dialog__titles">
            <h2 v-if="title" :id="titleId" class="ui-dialog__title">{{ title }}</h2>
            <p v-if="description" :id="descId" class="ui-dialog__desc">{{ description }}</p>
            <slot name="description" />
          </div>
          <button class="ui-dialog__close" type="button" aria-label="关闭" data-testid="ui-dialog-close" @click="close">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true">
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        </header>

        <div class="ui-dialog__body">
          <slot />
        </div>

        <footer v-if="$slots.footer" class="ui-dialog__foot">
          <slot name="footer" :close="close" />
        </footer>
      </div>
    </div>
  </Teleport>
</template>

