<script>
/**
 * UiField —— 带标签 / 提示 / 错误位的输入框（V5 原语 2/8）
 *
 * props:
 *   modelValue  String | Number        v-model
 *   label       String                 可见标签（必填项内嵌「必填」字样，不用英文 eyebrow）
 *   hint        String                 标签下的辅助说明
 *   error       String                 错误文案（来自 normalizeError / formatError）
 *   codeLabel   String                 「错误码：xxx」小字，仅未知码时有值
 *   type        String                 text | password | email | number | search
 *   multiline   Boolean                切 textarea
 *   rows        Number                 textarea 行数，默认 3
 *   size        String                 md | sm
 *   required / disabled / readonly / autofocus  Boolean
 *   placeholder / name / id / maxlength / autocomplete  String
 * slots: label | hint | error（自定义文案时覆盖）
 * 可访问性：label 与 input 用 useId 绑定；error 进 aria-describedby。
 */
export default { name: 'UiField' }
</script>

<script setup>
import { computed, useId } from 'vue'
import './UiField.css'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  label: { type: String, default: '' },
  hint: { type: String, default: '' },
  error: { type: String, default: '' },
  codeLabel: { type: String, default: '' },
  type: { type: String, default: 'text' },
  multiline: { type: Boolean, default: false },
  rows: { type: Number, default: 3 },
  size: { type: String, default: 'md' },
  required: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  readonly: { type: Boolean, default: false },
  autofocus: { type: Boolean, default: false },
  placeholder: { type: String, default: '' },
  name: { type: String, default: '' },
  id: { type: String, default: '' },
  maxlength: { type: [String, Number], default: undefined },
  autocomplete: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'change', 'blur', 'focus'])

const autoId = useId()
const inputId = computed(() => props.id || `ui-field-${autoId}`)
const hintId = computed(() => `${inputId.value}-hint`)
const errorId = computed(() => `${inputId.value}-error`)
const describedBy = computed(() => {
  const ids = []
  if (props.hint) ids.push(hintId.value)
  if (props.error || props.codeLabel) ids.push(errorId.value)
  return ids.length ? ids.join(' ') : undefined
})
const sizeClass = computed(() => (props.size === 'sm' ? 'sm' : 'md'))

function onInput(event) {
  emit('update:modelValue', event.target.value)
}

function onChange(event) {
  emit('change', event.target.value)
}
</script>

<template>
  <div
    class="ui-field"
    :class="[`ui-field--${sizeClass}`, { 'ui-field--invalid': Boolean(error), 'ui-field--disabled': disabled }]"
    data-testid="ui-field"
  >
    <label v-if="label || $slots.label" class="ui-field__label" :for="inputId">
      <slot name="label">{{ label }}</slot>
      <span v-if="required" class="ui-field__required">必填</span>
    </label>

    <textarea
      v-if="multiline"
      class="ui-field__control"
      :id="inputId"
      :value="modelValue"
      :name="name || undefined"
      :rows="rows"
      :disabled="disabled"
      :readonly="readonly"
      :required="required"
      :autofocus="autofocus"
      :placeholder="placeholder"
      :maxlength="maxlength"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="describedBy"
      data-testid="ui-field-input"
      @input="onInput"
      @change="onChange"
      @blur="$emit('blur', $event)"
      @focus="$emit('focus', $event)"
    ></textarea>
    <input
      v-else
      class="ui-field__control"
      :id="inputId"
      :type="type"
      :value="modelValue"
      :name="name || undefined"
      :disabled="disabled"
      :readonly="readonly"
      :required="required"
      :autofocus="autofocus"
      :placeholder="placeholder"
      :maxlength="maxlength"
      :autocomplete="autocomplete || undefined"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="describedBy"
      data-testid="ui-field-input"
      @input="onInput"
      @change="onChange"
      @blur="$emit('blur', $event)"
      @focus="$emit('focus', $event)"
    />

    <p v-if="hint || $slots.hint" class="ui-field__hint" :id="hintId">
      <slot name="hint">{{ hint }}</slot>
    </p>
    <div v-if="error || codeLabel" class="ui-field__error" :id="errorId" role="alert">
      <span v-if="error">{{ error }}</span>
      <span v-if="codeLabel" class="ui-field__code">{{ codeLabel }}</span>
    </div>
  </div>
</template>
