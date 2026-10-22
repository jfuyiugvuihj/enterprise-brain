<script>
/**
 * UiLoadingState —— 面板级加载态（V5 原语 · 面板状态类）
 *
 * 视觉文档 §8.4 第 5 条钉的是「骨架屏（--surface-3 微光扫过）而不是转圈」，所以这里给的是
 * 骨架条 + 一句进度说明，不给 spinner。动效属于状态反馈（theme.css:95 的口径），且
 * prefers-reduced-motion 下整段关掉；截图脚本关动效后拿到的是静态骨架，不会漂。
 *
 * props:
 *   label    String  一句人话，默认「正在加载」。只说在做什么，不下任何结论（与 UiEmptyState 同一口径）
 *   rows     Number  骨架条根数，默认 3；给 0 就只剩文案（适合按钮下方一行小字的场合）
 *   size     String  骨架条高度档：sm | md | lg，默认 md；未知值退回 md
 *   variant  String  rows（默认，多行文本骨架）| block（单块占位，给预览与图表区）
 *   dense    Boolean 卡片内紧凑档：间距降一级、文案降到 --t-xs
 * emits: 无（加载态没有可点的东西）
 * slots:
 *   label     覆盖文案位（要挂链接或换行时用它）
 *   default   文案之后的额外正文
 * 语义：role="status" + aria-busy="true" —— 加载是「结果还没到」，不该像失败那样打断读屏。
 * 视觉：只用 --surface-3 / --surface-2 两档表面色做明暗扫动，不描边、不发光（§5.3 彩色预算）。
 */
export default { name: 'UiLoadingState' }
</script>

<script setup>
import { computed } from 'vue'
import './UiLoadingState.css'

const props = defineProps({
  label: { type: String, default: '正在加载' },
  rows: { type: Number, default: 3 },
  size: { type: String, default: 'md' },
  variant: { type: String, default: 'rows' },
  dense: { type: Boolean, default: false },
})

const sizeClass = computed(() => (['sm', 'md', 'lg'].includes(props.size) ? 'ui-loading-state--' + props.size : 'ui-loading-state--md'))
const shapeClass = computed(() => (props.variant === 'block' ? 'ui-loading-state--block' : 'ui-loading-state--rows'))
/** rows 只认 0..12：负数与 NaN 会渲染出没人要的一堆节点，钳住比解释清楚 */
const barCount = computed(() => Math.max(0, Math.min(12, Math.round(Number(props.rows) || 0))))
</script>

<template>
  <div
    class="ui-loading-state"
    :class="[sizeClass, shapeClass, { 'ui-loading-state--dense': dense }]"
    role="status"
    aria-busy="true"
    data-testid="ui-loading-state"
  >
    <p class="ui-loading-state__label">
      <slot name="label">{{ label }}</slot>
    </p>
    <slot />
    <div v-if="variant === 'block'" class="ui-loading-state__block" data-testid="ui-loading-block"></div>
    <div v-else-if="barCount" class="ui-loading-state__bars">
      <span v-for="row in barCount" :key="row" class="ui-loading-state__bar" data-testid="ui-loading-row"></span>
    </div>
  </div>
</template>