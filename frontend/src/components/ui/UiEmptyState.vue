<script>
/**
 * UiEmptyState —— 面板级空态（V5 原语 · 面板状态类）
 *
 * props:
 *   title         String  一句人话，默认「暂无数据」（视觉文档 §8.5 反对「无数据」这种系统口吻）
 *   description   String  可选补充说明，只在需要解释「为什么是空的」时给
 *   actionLabel   String  主操作文案；留空即整条操作区不渲染
 *   actionVariant String  'primary' | 'secondary' | 'ghost'，默认 primary
 *   dense         Boolean 卡片内紧凑档：横向一行、图标降一级、文字左对齐
 * emits: action  主操作被点击
 * slots:
 *   icon         覆盖默认内联图标（A 线统一换 lucide 时从调用方替换，本目录不 import）
 *   description  覆盖说明位（要放链接时用它）
 *   default      说明之后的额外正文
 *   actions      覆盖整个操作区（多个按钮时用）
 * 语义：role="status" —— 空态是「查询结果」，不该像失败那样打断读屏（与 UiToast 的 info 同档）。
 * 视觉：只借中性色 + 一条虚线框，不做插画、不做动画、不加发光（彩色预算见视觉文档 §5.3）。
 */
export default { name: 'UiEmptyState' }
</script>

<script setup>
import { computed } from 'vue'
import UiButton from './UiButton.vue'
import './UiEmptyState.css'

const props = defineProps({
  title: { type: String, default: '暂无数据' },
  description: { type: String, default: '' },
  actionLabel: { type: String, default: '' },
  actionVariant: { type: String, default: 'primary' },
  dense: { type: Boolean, default: false },
})

const emit = defineEmits(['action'])

const variant = computed(() => (['primary', 'secondary', 'ghost'].includes(props.actionVariant) ? props.actionVariant : 'primary'))
const buttonSize = computed(() => (props.dense ? 'sm' : 'md'))
</script>

<template>
  <div class="ui-empty-state" :class="{ 'ui-empty-state--dense': dense }" role="status" data-testid="ui-empty-state">
    <span class="ui-empty-state__mark" aria-hidden="true">
      <slot name="icon">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3.5 13.5v3.2a1.8 1.8 0 0 0 1.8 1.8h13.4a1.8 1.8 0 0 0 1.8-1.8v-3.2" />
          <path d="M6.6 9.4 12 14.8l5.4-5.4" />
          <path d="M12 14.6V4.4" />
        </svg>
      </slot>
    </span>

    <div class="ui-empty-state__body">
      <p class="ui-empty-state__title">{{ title }}</p>
      <p v-if="description || $slots.description" class="ui-empty-state__desc">
        <slot name="description">{{ description }}</slot>
      </p>
      <slot />
    </div>

    <div v-if="actionLabel || $slots.actions" class="ui-empty-state__actions">
      <slot name="actions">
        <UiButton :variant="variant" :size="buttonSize" :label="actionLabel" data-testid="ui-empty-action" @click="emit('action')" />
      </slot>
    </div>
  </div>
</template>
