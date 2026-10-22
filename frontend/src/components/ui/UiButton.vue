<script>
/**
 * UiButton —— token 化按钮（V5 原语 1/8）
 *
 * props:
 *   variant   'primary' | 'secondary' | 'ghost' | 'danger'   默认 secondary
 *   size      'md'(40px) | 'sm'                              默认 md
 *   type      'button' | 'submit' | 'reset'                  默认 button
 *   loading   Boolean  占用为「忙碌」：不可点 + aria-busy
 *   disabled  Boolean
 *   block     Boolean  撑满父容器宽度
 *   label     String   无默认插槽时的文字（也方便测试）
 * slots:
 *   default   按钮文字
 *   icon      前置图标（由调用方传入内联 SVG 或 lucide 组件）
 * 说明：loading 态不做旋转动画——彩色预算与「禁装饰性动画」的结论
 *      （视觉文档 §5.3 / §8.3），这里用静态细环 + 文字降透明表达忙碌。
 */
export default { name: 'UiButton' }
</script>

<script setup>
import { computed } from 'vue'
import './UiButton.css'

const props = defineProps({
  variant: { type: String, default: 'secondary' },
  size: { type: String, default: 'md' },
  type: { type: String, default: 'button' },
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  block: { type: Boolean, default: false },
  label: { type: String, default: '' },
  title: { type: String, default: '' },
})

const blocked = computed(() => props.disabled || props.loading)
const variantClass = computed(() => (['primary', 'secondary', 'ghost', 'danger'].includes(props.variant) ? props.variant : 'secondary'))
const sizeClass = computed(() => (props.size === 'sm' ? 'sm' : 'md'))
</script>

<template>
  <button
    class="ui-button"
    :class="[
      `ui-button--${variantClass}`,
      `ui-button--${sizeClass}`,
      { 'ui-button--block': block, 'ui-button--busy': loading },
    ]"
    :type="type"
    :disabled="blocked"
    :aria-busy="loading ? 'true' : undefined"
    :title="title || undefined"
    data-testid="ui-button"
  >
    <span v-if="loading" class="ui-button__busy" aria-hidden="true"></span>
    <span v-else-if="$slots.icon" class="ui-button__icon" aria-hidden="true"><slot name="icon" /></span>
    <span class="ui-button__label"><slot>{{ label }}</slot></span>
  </button>
</template>
