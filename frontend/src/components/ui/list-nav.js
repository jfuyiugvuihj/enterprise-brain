/**
 * 列表型控件（UiSelect / UiTabs）共用的键盘导航纯函数。
 * 抽出来是为了能在无 DOM 环境下断言（V5 验收项「键盘导航」）。
 */

const FORWARD = { horizontal: 'ArrowRight', vertical: 'ArrowDown' }
const BACKWARD = { horizontal: 'ArrowLeft', vertical: 'ArrowUp' }

/** 该按键是否归本控件处理（方向键随 orientation 变化） */
export function isNavKey(key, orientation = 'horizontal') {
  return [FORWARD[orientation], BACKWARD[orientation], 'Home', 'End', 'Enter', ' ', 'Escape', 'Tab'].includes(key)
}

/**
 * 方向键 / Home / End 之后的目标下标：禁用项跳过，首尾循环。
 * @param {number} current 当前活动下标，-1 表示没有
 * @param {number} total 条目数
 * @param {string} key 键盘 key
 * @param {{ orientation?: 'horizontal' | 'vertical', isDisabled?: (index: number) => boolean }} options
 * @returns {number} 新下标；total 为 0 时返回 -1
 */
export function moveActiveIndex(current, total, key, options = {}) {
  const { orientation = 'horizontal', isDisabled = null } = options
  if (!total || total < 1) return -1
  const usable = (index) => !(isDisabled ? isDisabled(index) : false)
  const hasCurrent = Number.isInteger(current) && current >= 0

  let delta = 0
  if (key === FORWARD[orientation]) delta = 1
  else if (key === BACKWARD[orientation]) delta = -1

  if (delta) {
    // 无活动项时把起点放在边界外一格，第一下正好落在首/末项
    let index = hasCurrent ? current : delta > 0 ? -1 : total
    for (let guard = 0; guard <= total; guard += 1) {
      index = (index + delta + total) % total
      if (usable(index)) return index
    }
    return hasCurrent ? current : -1
  }

  if (key === 'Home' || key === 'End') {
    const stepWidth = key === 'Home' ? 1 : -1
    for (let index = key === 'Home' ? 0 : total - 1; index >= 0 && index < total; index += stepWidth) {
      if (usable(index)) return index
    }
  }
  return hasCurrent ? current : -1
}

/** 类型ahead：从 from 之后找第一个以前缀开头的条目下标 */
export function findIndexByPrefix(items, prefix, from = -1) {
  const needle = String(prefix || '').trim().toLowerCase()
  const list = Array.isArray(items) ? items : []
  if (!needle || !list.length) return -1
  const labels = list.map((item) =>
    item && typeof item === 'object' ? String(item.label ?? item.title ?? item.value ?? '') : String(item ?? ''),
  )
  const start = Number.isInteger(from) && from >= 0 ? from : -1
  for (let offset = 1; offset <= labels.length; offset += 1) {
    const index = (start + offset) % labels.length
    if (labels[index].trim().toLowerCase().startsWith(needle)) return index
  }
  return -1
}

/** Esc / Tab 收起下拉 */
export function closesList(key) {
  return key === 'Escape' || key === 'Tab'
}

/** Enter / Space 确认当前项 */
export function confirmsSelection(key) {
  return key === 'Enter' || key === ' ' || key === 'Spacebar'
}
