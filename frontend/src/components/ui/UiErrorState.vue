<script>
/**
 * UiErrorState —— 面板级失败态（V5 原语 · 面板状态类）
 *
 * props:
 *   title        String  一句人话，默认「操作没有完成」（与 errcodes 兜底句同一说法，去掉重复的「请稍后重试」）
 *   description  String  后端回来的具体原因：直接喂 normalizeError(err).message 或 formatError(err)
 *   codeLabel    String  「错误码：xxx」小字，只在未知码时给（用 barrel 里的 errorCodeLabel(err)）
 *   retryText    String  重试按钮文案，默认「重试」；加载类面板建议传「重新加载」
 *   retryable    Boolean 默认 true；false 时整条操作区不渲染（权限类失败就不该给重试）
 *   busy         Boolean 重试进行中：借 UiButton 的 loading，按钮置灰 + aria-busy，挡重复点击
 *   dense        Boolean 卡片内紧凑档
 * emits: retry  重试被点击
 * slots:
 *   icon         覆盖默认内联图标
 *   description  覆盖说明位
 *   default      说明之后的额外正文
 *   actions      覆盖整个操作区（总控说的「onRetry 或具名 slot」里的第二条腿）
 * 语义：role="alert" —— 失败必须打断读屏（与 UiToast 的 danger 同档）。
 * 视觉：只占 --danger 一个色相 + 一条左描边，不加发光、不加动画（视觉文档 §5.3）。
 */
export default { name: 'UiErrorState' }
</script>

<script setup>
import { computed } from 'vue'
import UiButton from './UiButton.vue'
import './UiErrorState.css'

const props = defineProps({
  title: { type: String, default: '操作没有完成' },
  description: { type: String, default: '' },
  codeLabel: { type: String, default: '' },
  retryText: { type: String, default: '重试' },
  retryable: { type: Boolean, default: true },
  busy: { type: Boolean, default: false },
  dense: { type: Boolean, default: false },
})

const emit = defineEmits(['retry'])

const buttonSize = computed(() => (props.dense ? 'sm' : 'md'))
</script>

<template>
  <div class="ui-error-state" :class="{ 'ui-error-state--dense': dense }" role="alert" data-testid="ui-error-state">
    <span class="ui-error-state__mark" aria-hidden="true">
      <slot name="icon">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 4.5 3.5 19h17L12 4.5Z" />
          <path d="M12 10v4" />
          <path d="M12 16.6h.01" />
        </svg>
      </slot>
    </span>

    <div class="ui-error-state__body">
      <p class="ui-error-state__title">{{ title }}</p>
      <p v-if="description || $slots.description" class="ui-error-state__desc">
        <slot name="description">{{ description }}</slot>
      </p>
      <slot />
      <p v-if="codeLabel" class="ui-error-state__code">{{ codeLabel }}</p>
    </div>

    <div v-if="retryable || $slots.actions" class="ui-error-state__actions">
      <slot name="actions">
        <UiButton variant="secondary" :size="buttonSize" :loading="busy" :label="retryText" data-testid="ui-error-retry" @click="emit('retry')" />
      </slot>
    </div>
  </div>
</template>
