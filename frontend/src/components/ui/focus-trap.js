/**
 * UiDialog 焦点循环纯函数：只算下标，不碰 DOM。
 */

export const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type=hidden])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

/**
 * Tab / Shift+Tab 之后应停留的下标；触边回到另一头，把焦点锁在弹层内。
 * @param {number} index 当前焦点在可聚焦元素数组里的下标
 * @param {number} total 可聚焦元素数量
 */
export function nextFocusableIndex(index, total, shift = false) {
  if (!total || total < 1) return -1
  const current = Number.isInteger(index) && index >= 0 ? index : 0
  return shift ? (current - 1 + total) % total : (current + 1) % total
}

/** Esc 是否应关闭弹层：在可输入元素里不抢走「清空输入」语义 */
export function shouldCloseOnKey(key, tagName = '') {
  if (key !== 'Escape') return false
  return !['INPUT', 'TEXTAREA', 'SELECT'].includes(String(tagName).toUpperCase())
}
