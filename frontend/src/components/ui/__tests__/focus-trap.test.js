import { describe, expect, it } from 'vitest'
import { FOCUSABLE_SELECTOR, nextFocusableIndex, shouldCloseOnKey } from '../focus-trap.js'

describe('弹层焦点循环', () => {
  it('Tab 到底回到首项，Shift+Tab 到顶回到末项', () => {
    expect(nextFocusableIndex(0, 3)).toBe(1)
    expect(nextFocusableIndex(2, 3)).toBe(0)
    expect(nextFocusableIndex(0, 3, true)).toBe(2)
    expect(nextFocusableIndex(2, 3, true)).toBe(1)
  })

  it('焦点还在背景上时从第一项开始，空列表返回 -1', () => {
    expect(nextFocusableIndex(-1, 3)).toBe(1)
    expect(nextFocusableIndex(0, 0)).toBe(-1)
  })

  it('可聚焦选择器覆盖按钮/输入/链接与 tabindex', () => {
    expect(FOCUSABLE_SELECTOR).toContain('button:not([disabled])')
    expect(FOCUSABLE_SELECTOR).toContain('[tabindex]:not([tabindex="-1"])')
  })
})

describe('Esc 关闭判定', () => {
  it('在非输入元素上关闭', () => {
    expect(shouldCloseOnKey('Escape', 'BUTTON')).toBe(true)
    expect(shouldCloseOnKey('Escape', '')).toBe(true)
  })

  it('在输入控件里不抢走清空语义', () => {
    expect(shouldCloseOnKey('Escape', 'input')).toBe(false)
    expect(shouldCloseOnKey('Escape', 'TEXTAREA')).toBe(false)
    expect(shouldCloseOnKey('Enter', 'BUTTON')).toBe(false)
  })
})
