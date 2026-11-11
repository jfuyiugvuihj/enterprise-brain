/**
 * UiTable 排序纯函数（V5 验收项「排序」的单测目标）。
 * 中文用 zh-CN 归并排序，数字按数值比，空值永远沉底。
 */

const collator = new Intl.Collator('zh-CN', { numeric: true, sensitivity: 'base' })

export const SORT_ASC = 'asc'
export const SORT_DESC = 'desc'

/** 点表头时的下一状态：无 → asc → desc → 无 */
export function nextSortState(current, key) {
  if (!current || current.key !== key) return { key, order: SORT_ASC }
  if (current.order === SORT_ASC) return { key, order: SORT_DESC }
  return { key: '', order: '' }
}

/** 表头 aria-sort 取值 */
export function ariaSortFor(sort, key) {
  if (!sort || sort.key !== key || !sort.order) return 'none'
  return sort.order === SORT_ASC ? 'ascending' : 'descending'
}

function isEmpty(value) {
  return value === null || value === undefined || value === ''
}

function compare(left, right) {
  const leftNumber = typeof left === 'number' || (typeof left === 'string' && left.trim() !== '' && Number.isFinite(Number(left)))
  const rightNumber = typeof right === 'number' || (typeof right === 'string' && right.trim() !== '' && Number.isFinite(Number(right)))
  if (leftNumber && rightNumber) return Number(left) - Number(right)
  if (left instanceof Date && right instanceof Date) return left.getTime() - right.getTime()
  return collator.compare(String(left), String(right))
}

/**
 * 返回排好序的新数组（不改动入参）。
 * @param {Array<Record<string, any>>} rows
 * @param {{ key?: string, order?: 'asc' | 'desc' }} sort
 * @param {Array<{ key: string, value?: string | ((row: any) => any) }>} columns
 */
export function sortRows(rows, sort, columns = []) {
  const list = Array.isArray(rows) ? rows.slice() : []
  if (!sort || !sort.key || !sort.order) return list
  const column = columns.find((item) => item.key === sort.key)
  const pick = (row) => {
    if (column && typeof column.value === 'function') return column.value(row)
    return row?.[sort.key]
  }
  const direction = sort.order === SORT_DESC ? -1 : 1
  return list.sort((left, right) => {
    const valueLeft = pick(left)
    const valueRight = pick(right)
    // 空值固定沉底，不参与升降序翻转，否则 desc 时空行跑到最前
    if (isEmpty(valueLeft) || isEmpty(valueRight)) {
      if (isEmpty(valueLeft) && isEmpty(valueRight)) return 0
      return isEmpty(valueLeft) ? 1 : -1
    }
    return compare(valueLeft, valueRight) * direction
  })
}
