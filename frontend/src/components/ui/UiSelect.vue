<script>
/**
 * UiSelect —— 自研下拉（V5 原语 3/8）
 *
 * props:
 *   modelValue  any                     v-model，比对 option.value
 *   options     Array<{label,value,disabled} | string | number>
 *   label       String                  字段标签
 *   placeholder String  未选时的占位文案，默认「请选择」
 *   emptyText   String  无选项时的空态文案，默认「没有可选项」
 *   error / codeLabel / disabled / size('md'|'sm') / block
 *   optionEmptyText 保留位（无选项时的动作提示）
 * props 追加 expanded(Boolean) 受控展开
 * emits: update:modelValue, change(value), open, close
 * 键盘：ArrowDown/Up 移动（禁用项跳过、首尾循环）、Home/End 跳两端、
 *      Enter/Space 选中并收起、Esc/Tab 收起、列表内再按 Tab 交还焦点。
 * 图标：内联 SVG 占位，A 线统一换 lucide 时只替换这一处 <svg>。
 */
export default { name: 'UiSelect' }
</script>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { closesList, confirmsSelection, isNavKey, moveActiveIndex } from './list-nav.js'
import './UiSelect.css'

const props = defineProps({
  modelValue: { type: [String, Number, Object, Array, Boolean], default: '' },
  options: { type: Array, default: () => [] },
  label: { type: String, default: '' },
  placeholder: { type: String, default: '请选择' },
  emptyText: { type: String, default: '没有可选项' },
  error: { type: String, default: '' },
  codeLabel: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  size: { type: String, default: 'md' },
  block: { type: Boolean, default: true },
  /** 受控展开：供程序化打开与单测断言下拉面板（不传时由组件自己管） */
  expanded: { type: Boolean, default: false },
  ariaLabel: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'change', 'open', 'close'])

const autoId = useId()
const rootId = `ui-select-${autoId}`
const listId = `${rootId}-list`
const triggerId = `${rootId}-trigger`

const innerOpen = ref(false)
const open = computed(() => props.expanded || innerOpen.value)
const active = ref(-1)
const root = ref(null)
const trigger = ref(null)
const list = ref(null)

const items = computed(() =>
  (props.options || []).map((raw) => {
    if (raw && typeof raw === 'object') {
      return {
        label: String(raw.label ?? raw.title ?? raw.value ?? ''),
        value: raw.value ?? raw.label ?? '',
        disabled: Boolean(raw.disabled),
      }
    }
    return { label: String(raw ?? ''), value: raw, disabled: false }
  }),
)

const selectedIndex = computed(() => items.value.findIndex((item) => item.value === props.modelValue))
const selectedLabel = computed(() => (selectedIndex.value >= 0 ? items.value[selectedIndex.value].label : ''))
const isDisabledOption = (index) => Boolean(items.value[index]?.disabled)
const hasOptions = computed(() => items.value.length > 0)

function openList() {
  if (props.disabled || open.value) return
  innerOpen.value = true
  active.value = selectedIndex.value >= 0 ? selectedIndex.value : Math.max(items.value.findIndex((item) => !item.disabled), 0)
  emit('open')
}

function closeList(refocus = false) {
  if (!open.value) return
  innerOpen.value = false
  active.value = -1
  emit('close')
  if (refocus) nextTick(() => trigger.value?.focus?.())
}

function choose(index) {
  const item = items.value[index]
  if (!item || item.disabled) return
  emit('update:modelValue', item.value)
  emit('change', item.value)
  closeList()
}

function onTriggerKeydown(event) {
  const key = event.key
  if (open.value) {
    if (isNavKey(key, 'vertical')) event.preventDefault()
    if (closesList(key)) {
      closeList(true)
      return
    }
    if (confirmsSelection(key)) {
      choose(active.value)
      return
    }
    const next = moveActiveIndex(active.value, items.value.length, key, { orientation: 'vertical', isDisabled: isDisabledOption })
    if (next >= 0) active.value = next
    return
  }
  if (key === 'ArrowDown' || key === 'ArrowUp' || confirmsSelection(key) || key === ' ' || key === 'Enter') {
    event.preventDefault()
    openList()
  }
}

function onListKeydown(event) {
  const key = event.key
  if (closesList(key)) {
    event.preventDefault()
    closeList(true)
    return
  }
  if (confirmsSelection(key)) {
    event.preventDefault()
    choose(active.value)
    return
  }
  const next = moveActiveIndex(active.value, items.value.length, key, { orientation: 'vertical', isDisabled: isDisabledOption })
  if (next >= 0) {
    event.preventDefault()
    active.value = next
  }
}

function onDocumentPointerdown(event) {
  if (!open.value) return
  if (root.value && !root.value.contains(event.target)) closeList()
}

onMounted(() => {
  if (typeof document !== 'undefined') document.addEventListener('pointerdown', onDocumentPointerdown, true)
})

onBeforeUnmount(() => {
  if (typeof document !== 'undefined') document.removeEventListener('pointerdown', onDocumentPointerdown, true)
})

defineExpose({ openList, closeList, choose, active, open, items })
</script>

<template>
  <div
    class="ui-select"
    :class="[`ui-select--${size === 'sm' ? 'sm' : 'md'}`, { 'ui-select--block': block, 'ui-select--open': open, 'ui-select--invalid': Boolean(error), 'ui-select--disabled': disabled }]"
    ref="root"
    data-testid="ui-select"
  >
    <label v-if="label" class="ui-select__label" :for="triggerId">{{ label }}</label>

    <button
      class="ui-select__trigger"
      :id="triggerId"
      ref="trigger"
      type="button"
      role="combobox"
      :aria-expanded="open ? 'true' : 'false'"
      :aria-controls="open ? listId : undefined"
      :aria-haspopup="'listbox'"
      :aria-label="label ? undefined : ariaLabel || placeholder"
      :disabled="disabled"
      :aria-invalid="error ? 'true' : undefined"
      data-testid="ui-select-trigger"
      @click="open ? closeList(true) : openList()"
      @keydown="onTriggerKeydown"
    >
      <span class="ui-select__value" :class="{ 'ui-select__value--muted': !selectedLabel }">
        {{ selectedLabel || placeholder }}
      </span>
      <span class="ui-select__chevron" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </span>
    </button>

    <ul
      v-if="open"
      class="ui-select__list"
      :id="listId"
      ref="list"
      role="listbox"
      :aria-labelledby="label ? triggerId : undefined"
      tabindex="-1"
      data-testid="ui-select-list"
      @keydown="onListKeydown"
    >
      <li
        v-for="(item, index) in items"
        :key="`${item.value}-${index}`"
        class="ui-select__option"
        :class="{ 'ui-select__option--active': index === active, 'ui-select__option--selected': index === selectedIndex, 'ui-select__option--disabled': item.disabled }"
        role="option"
        :aria-selected="index === selectedIndex ? 'true' : 'false'"
        :aria-disabled="item.disabled ? 'true' : undefined"
        @mouseenter="item.disabled ? null : (active = index)"
        @click="choose(index)"
      >
        {{ item.label }}
      </li>
      <li v-if="!hasOptions" class="ui-select__empty" role="presentation" data-testid="ui-select-empty">{{ emptyText }}</li>
    </ul>

    <div v-if="error || codeLabel" class="ui-select__error" role="alert">
      <span v-if="error">{{ error }}</span>
      <span v-if="codeLabel" class="ui-select__code" data-testid="ui-select-code">{{ codeLabel }}</span>
    </div>
  </div>
</template>
