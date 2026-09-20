/**
 * R104 · 切屏后的焦点落点与侧栏键盘走位
 *
 * 零件仓库里已经有：ui/list-nav.js 的下标算绪（下拉与标签页用的就是它）、ui/focus-trap.js 的
 * 可聚焦元素选择器。这里只补「路由变了之后焦点交给谁」这一层，不新写一套方向键语义 ——
 * 第二套焦点管理和第二张导航表是同一类缺陷。
 *
 * 全部是纯函数（接受 DOM 或它的桩），因为本仓库测试跑在 node 环境、没有 jsdom；
 * 这样焦点决策能被真断言，而不是在源码里 grep 一遍「看起来接上了」。
 */
import { FOCUSABLE_SELECTOR } from '../components/ui/focus-trap.js'
import { moveActiveIndex } from '../components/ui/list-nav.js'

/**
 * 侧栏只接管这四个键。Tab / Enter / Space 刻意不拦：Tab 是离开导航的正常出路，
 * 后两者是 <button> 原生的激活语义，抢过来只会让键盘用户更难用。
 */
const ROVE_KEYS = Object.freeze(['ArrowUp', 'ArrowDown', 'Home', 'End'])

/** 这个键该不该由侧栏接管 */
export function isRoveKey(key) {
  return ROVE_KEYS.includes(key)
}

/** 按 DOM 顺序取出导航条目；没有容器就给空数组，不抛。 */
export function navItems(container) {
  if (!container || typeof container.querySelectorAll !== 'function') return []
  return Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR))
}

/**
 * 方向键 / Home / End 之后该把焦点交给哪一条。
 * @param {unknown[]} items 导航条目
 * @param {unknown} activeElement 当前焦点落点，不在列表里时按「没有活动项」处理
 * @param {string} key 键盘事件按键
 * @returns {unknown|null} 目标条目；null 表示这个键不该管，或没有可去之处
 */
export function nextNavItem(items, activeElement, key) {
  const list = Array.isArray(items) ? items : []
  if (!isRoveKey(key) || !list.length) return null
  const index = moveActiveIndex(list.indexOf(activeElement), list.length, key, { orientation: 'vertical' })
  return index >= 0 ? list[index] ?? null : null
}

/**
 * 切屏后把焦点交给新屏主区（主区带 tabindex="-1"）。不这么做，焦点会留在侧栏：
 * 屏幕已经换了一屏，而键盘与读屏用户完全听不出来。
 * @returns {boolean} 真的移动了焦点才返回 true
 */
export function focusScreenMain(element) {
  if (!element || typeof element.focus !== 'function') return false
  element.focus({ preventScroll: true })
  return true
}
