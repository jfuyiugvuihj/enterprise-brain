<script>
/**
 * UiTabs —— 标签页（V5 原语 7/8）
 *
 * props:
 *   modelValue  String | Number  v-model，当前面板 id
 *   items       Array<{ id, label, badge?, disabled? }>
 *   orientation 'horizontal' | 'vertical'  决定方向键与视觉排布
 *   ariaLabel   String  tablist 的无障碍名
 *   emptyText   String  无条目时的空态文案
 * emits: update:modelValue, change(id)
 * 键盘：roving tabindex（只有当前项 tabindex=0），方向键切换并自动选中，
 *      Home/End 跳首尾，禁用项跳过；控件条本身不响应输入型按键。
 * slots: panel-<id>（面板内容）、label-<id>（自定义标签）
 */
export default { name: 'UiTabs' }
</script>

<script setup>
import { computed, ref, useId } from 'vue'
import { moveActiveIndex } from './list-nav.js'
import './UiTabs.css'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  items: { type: Array, default: () => [] },
  orientation: { type: String, default: 'horizontal' },
  ariaLabel: { type: String, default: '' },
  emptyText: { type: String, default: '没有可切换的内容' },
})

const emit = defineEmits(['update:modelValue', 'change'])

const autoId = useId()
const orientation = computed(() => (props.orientation === 'vertical' ? 'vertical' : 'horizontal'))
const tabList = computed(() =>
  (props.items || []).map((raw) => {
    if (raw && typeof raw === 'object') {
      return {
        id: raw.id ?? raw.value ?? '',
        label: String(raw.label ?? raw.title ?? raw.id ?? ''),
        badge: raw.badge ?? raw.count ?? null,
        disabled: Boolean(raw.disabled),
      }
    }
    return { id: raw, label: String(raw ?? ''), badge: null, disabled: false }
  }),
)
const currentIndex = computed(() => tabList.value.findIndex((item) => item.id === props.modelValue))
const activeIndex = computed(() => (currentIndex.value >= 0 ? currentIndex.value : Math.max(tabList.value.findIndex((item) => !item.disabled), 0)))
const isDisabledTab = (index) => Boolean(tabList.value[index]?.disabled)
const selected = computed(() => tabList.value[activeIndex.value])
const hasItems = computed(() => tabList.value.length > 0)
const panels = ref(null)

function tabId(index) {
  return `${autoId}-tab-${index}`
}

function panelId(index) {
  return `${autoId}-panel-${index}`
}

function select(index) {
  const item = tabList.value[index]
  if (!item || item.disabled) return
  if (item.id !== props.modelValue) {
    emit('update:modelValue', item.id)
    emit('change', item.id)
  }
}

function onKeydown(event) {
  if (!hasItems.value) return
  const key = event.key
  if (!['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(key)) return
  event.preventDefault()
  const next = moveActiveIndex(activeIndex.value, tabList.value.length, key, {
    orientation: orientation.value,
    isDisabled: isDisabledTab,
  })
  if (next >= 0) {
    select(next)
    const nodes = panels.value?.parentElement?.querySelectorAll?.('.ui-tabs__tab')
    nodes?.[next]?.focus?.()
  }
}

defineExpose({ select, activeIndex, tabList })
</script>

<template>
  <div class="ui-tabs" :class="`ui-tabs--${orientation}`" data-testid="ui-tabs">
    <div
      v-if="hasItems"
      class="ui-tabs__list"
      role="tablist"
      :aria-label="ariaLabel || undefined"
      :aria-orientation="orientation"
      data-testid="ui-tabs-list"
      @keydown="onKeydown"
    >
      <button
        v-for="(item, index) in tabList"
        :id="tabId(index)"
        :key="`${item.id}-${index}`"
        class="ui-tabs__tab"
        :class="{ 'ui-tabs__tab--active': index === activeIndex, 'ui-tabs__tab--disabled': item.disabled }"
        type="button"
        role="tab"
        :aria-selected="index === activeIndex ? 'true' : 'false'"
        :aria-controls="panelId(index)"
        :tabindex="index === activeIndex ? 0 : -1"
        :disabled="item.disabled"
        :data-testid="`ui-tabs-tab-${item.id}`"
        @click="select(index)"
      >
        <span class="ui-tabs__label"><slot :name="`label-${item.id}`">{{ item.label }}</slot></span>
        <span v-if="item.badge !== null && item.badge !== ''" class="ui-tabs__badge">{{ item.badge }}</span>
      </button>
    </div>
    <p v-else class="ui-tabs__empty" data-testid="ui-tabs-empty">{{ emptyText }}</p>

    <div ref="panels" class="ui-tabs__panels">
      <template v-for="(item, index) in tabList" :key="`panel-${item.id}-${index}`">
        <div
          v-show="index === activeIndex"
          class="ui-tabs__panel"
          :id="panelId(index)"
          role="tabpanel"
          :aria-labelledby="tabId(index)"
          :tabindex="0"
        >
          <slot :name="`panel-${item.id}`" :item="item" :active="index === activeIndex" />
        </div>
      </template>
      <slot :item="selected" />
    </div>
  </div>
</template>
