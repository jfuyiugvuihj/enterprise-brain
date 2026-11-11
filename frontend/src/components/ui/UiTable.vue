<script>
/**
 * UiTable —— 真 <table> 数据表（V5 原语 4/8）
 *
 * props:
 *   columns      Array<{ key, label, align?: 'left'|'right'|'center', sortable?: boolean,
 *                        width?: string, mono?: boolean, value?: (row) => any, formatter?: (value,row) => string }>
 *   rows         Array<object>
 *   sort         { key, order: 'asc' | 'desc' }   v-model:sort；不传则由组件内部持有
 *   rowKey       String | (row, index) => string   默认取 row.id / row.key / 下标
 *   emptyText    String  默认「暂无数据」
 *   loading      Boolean 显示骨架行（不用转圈，见视觉文档 §8.5）
 *   stickyHeader Boolean 默认 true
 *   zebra        Boolean 默认 true
 *   dense        Boolean 紧凑行高
 *   ariaLabel    String
 * emits: update:sort, sort-change({key,order}), row-click(row,index)
 * slots: cell-<key>（作用域 { value, row, index, column }）、empty、footer
 */
export default { name: 'UiTable' }
</script>

<script setup>
import { computed, ref, useId } from 'vue'
import { ariaSortFor, nextSortState, sortRows } from './table-sort.js'
import './UiTable.css'

const props = defineProps({
  columns: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
  sort: { type: Object, default: null },
  rowKey: { type: [String, Function], default: '' },
  emptyText: { type: String, default: '暂无数据' },
  loading: { type: Boolean, default: false },
  stickyHeader: { type: Boolean, default: true },
  zebra: { type: Boolean, default: true },
  dense: { type: Boolean, default: false },
  ariaLabel: { type: String, default: '' },
})

const emit = defineEmits(['update:sort', 'sort-change', 'row-click'])

const autoId = useId()
const captionId = `ui-table-${autoId}-caption`
const internalSort = ref({ key: '', order: '' })
const activeSort = computed(() => props.sort || internalSort.value)
const columnList = computed(() => props.columns || [])
const bodyRows = computed(() => sortRows(props.rows || [], activeSort.value, columnList.value))
const isEmpty = computed(() => !props.loading && bodyRows.value.length === 0)

function keyOf(row, index) {
  if (typeof props.rowKey === 'function') return props.rowKey(row, index)
  if (props.rowKey) return row?.[props.rowKey] ?? index
  if (row && (row.id !== undefined || row.key !== undefined)) return row.id ?? row.key
  return index
}

function valueOf(column, row) {
  if (typeof column.value === 'function') return column.value(row)
  return row?.[column.key]
}

function textOf(column, row) {
  const raw = valueOf(column, row)
  if (typeof column.formatter === 'function') return column.formatter(raw, row)
  if (raw === null || raw === undefined) return ''
  if (typeof raw === 'number') return raw.toLocaleString('zh-CN')
  return String(raw)
}

function sortBy(column) {
  if (!column.sortable) return
  const next = nextSortState(activeSort.value, column.key)
  if (!props.sort) internalSort.value = next
  emit('update:sort', next)
  emit('sort-change', next)
}

defineExpose({ sortedRows: bodyRows, activeSort, sortBy })
</script>

<template>
  <div
    class="ui-table"
    :class="[`ui-table--${dense ? 'dense' : 'loose'}`, { 'ui-table--zebra': zebra, 'ui-table--sticky': stickyHeader }]"
    data-testid="ui-table"
  >
    <table class="ui-table__matrix" :aria-label="ariaLabel || undefined" :aria-describedby="isEmpty ? undefined : captionId">
      <caption v-if="ariaLabel" :id="captionId" class="ui-table__caption">{{ ariaLabel }}</caption>
      <thead class="ui-table__head">
        <tr>
          <th
            v-for="(column, columnIndex) in columnList"
            :key="column.key || columnIndex"
            class="ui-table__th"
            :class="[`ui-table__th--${column.align || 'left'}`, { 'ui-table__th--sortable': column.sortable }]"
            :style="column.width ? { width: column.width } : undefined"
            scope="col"
            :aria-sort="column.sortable ? ariaSortFor(activeSort, column.key) : undefined"
          >
            <button
              v-if="column.sortable"
              class="ui-table__sorter"
              type="button"
              :data-testid="`ui-table-sort-${column.key}`"
              @click="sortBy(column)"
            >
              <span>{{ column.label }}</span>
              <span class="ui-table__sorter-mark" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                  <path
                    v-if="activeSort.key === column.key && activeSort.order === 'desc'"
                    d="m6 9 6 6 6-6"
                  />
                  <path v-else d="m6 15 6-6 6 6" />
                </svg>
              </span>
            </button>
            <span v-else>{{ column.label }}</span>
          </th>
        </tr>
      </thead>

      <tbody class="ui-table__body">
        <template v-if="loading">
          <tr v-for="rowIndex in 3" :key="`skeleton-${rowIndex}`" class="ui-table__row ui-table__row--skeleton">
          <td v-for="(column, columnIndex) in columnList" :key="`skeleton-${rowIndex}-${columnIndex}`" class="ui-table__td">
            <span class="ui-table__skeleton" aria-hidden="true"></span>
            <span class="ui-table__sr">加载中</span>
          </td>
          </tr>
        </template>

        <template v-else>
          <tr
            v-for="(row, index) in bodyRows"
            :key="keyOf(row, index)"
            class="ui-table__row"
            data-testid="ui-table-row"
            @click="emit('row-click', row, index)"
          >
            <td
              v-for="(column, columnIndex) in columnList"
              :key="column.key || columnIndex"
              class="ui-table__td"
              :class="[`ui-table__td--${column.align || 'left'}`, { 'ui-table__td--mono': column.mono || column.align === 'right' }]"
            >
              <slot :name="`cell-${column.key}`" :value="valueOf(column, row)" :row="row" :index="index" :column="column">
                {{ textOf(column, row) }}
              </slot>
            </td>
          </tr>
        </template>
      </tbody>

      <tfoot v-if="$slots.footer" class="ui-table__foot">
        <tr>
          <td class="ui-table__foot-cell" :colspan="Math.max(columnList.length, 1)">
            <slot name="footer" />
          </td>
        </tr>
      </tfoot>
    </table>

    <div v-if="isEmpty" class="ui-table__empty" data-testid="ui-table-empty" role="presentation">
      <slot name="empty">
        <p class="ui-table__empty-text">{{ emptyText }}</p>
      </slot>
    </div>
  </div>
</template>
