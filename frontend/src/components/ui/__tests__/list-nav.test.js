import { describe, expect, it } from 'vitest'
import { closesList, confirmsSelection, findIndexByPrefix, isNavKey, moveActiveIndex } from '../list-nav.js'

/** UiSelect / UiTabs 传给这个纯函数的实参形状 */
const OPTIONS = [
  { label: '市场部', value: 'mkt', disabled: false },
  { label: '财务部', value: 'fin', disabled: true },
  { label: '运营部', value: 'ops', disabled: false },
  { label: '人力', value: 'hr', disabled: false },
]
const vertical = { orientation: 'vertical', isDisabled: (index) => Boolean(OPTIONS[index].disabled) }
const horizontal = { orientation: 'horizontal', isDisabled: (index) => Boolean(OPTIONS[index].disabled) }

describe('moveActiveIndex 键盘导航', () => {
  it('下拉里 ArrowDown 跳过禁用项', () => {
    expect(moveActiveIndex(0, OPTIONS.length, 'ArrowDown', vertical)).toBe(2)
  })

  it('ArrowUp 反向同样跳过禁用项', () => {
    expect(moveActiveIndex(2, OPTIONS.length, 'ArrowUp', vertical)).toBe(0)
  })

  it('末尾继续按下回到首个可用项', () => {
    expect(moveActiveIndex(3, OPTIONS.length, 'ArrowDown', vertical)).toBe(0)
  })

  it('标签页用水平方向键，纵向键不接管', () => {
    expect(moveActiveIndex(0, OPTIONS.length, 'ArrowRight', horizontal)).toBe(2)
    expect(moveActiveIndex(0, OPTIONS.length, 'ArrowRight', { orientation: 'horizontal' })).toBe(1)
    expect(moveActiveIndex(0, OPTIONS.length, 'ArrowDown', horizontal)).toBe(0)
  })

  it('Home / End 落在首尾可用项，而不是禁用项', () => {
    expect(moveActiveIndex(3, OPTIONS.length, 'Home', vertical)).toBe(0)
    expect(moveActiveIndex(0, OPTIONS.length, 'End', vertical)).toBe(3)
    const allButDisabled = { orientation: 'vertical', isDisabled: (index) => index !== 1 }
    expect(moveActiveIndex(0, OPTIONS.length, 'End', allButDisabled)).toBe(1)
  })

  it('无焦点时按下键从首项开始，空列表返回 -1', () => {
    expect(moveActiveIndex(-1, OPTIONS.length, 'ArrowDown', vertical)).toBe(0)
    expect(moveActiveIndex(-1, OPTIONS.length, 'ArrowUp', vertical)).toBe(3)
    expect(moveActiveIndex(-1, 0, 'ArrowDown', vertical)).toBe(-1)
  })

  it('全禁用时不越界', () => {
    const allDisabled = { orientation: 'vertical', isDisabled: () => true }
    expect(moveActiveIndex(0, 2, 'ArrowDown', allDisabled)).toBe(0)
    expect(moveActiveIndex(-1, 2, 'ArrowDown', allDisabled)).toBe(-1)
  })
})

describe('类型ahead 与前缀查找', () => {
  it('从当前项之后找第一个前缀匹配', () => {
    expect(findIndexByPrefix(OPTIONS, '运', 0)).toBe(2)
    expect(findIndexByPrefix(OPTIONS, '财', -1)).toBe(1)
    expect(findIndexByPrefix([{ label: 'Alpha' }, { label: 'beta' }], 'B', -1)).toBe(1)
  })

  it('找不到返回 -1，空前缀不猜', () => {
    expect(findIndexByPrefix(OPTIONS, 'z', 0)).toBe(-1)
    expect(findIndexByPrefix(OPTIONS, '  ', 0)).toBe(-1)
    expect(findIndexByPrefix([], 'a', 0)).toBe(-1)
  })
})

describe('按键归属', () => {
  it('Esc / Tab 收起，Enter / Space 确认', () => {
    expect(closesList('Escape')).toBe(true)
    expect(closesList('Tab')).toBe(true)
    expect(closesList('ArrowDown')).toBe(false)
    expect(confirmsSelection('Enter')).toBe(true)
    expect(confirmsSelection(' ')).toBe(true)
    expect(confirmsSelection('a')).toBe(false)
  })

  it('方向键归属随 orientation 变化', () => {
    expect(isNavKey('ArrowDown', 'vertical')).toBe(true)
    expect(isNavKey('ArrowLeft', 'horizontal')).toBe(true)
    expect(isNavKey('ArrowLeft', 'vertical')).toBe(false)
    expect(isNavKey('a', 'horizontal')).toBe(false)
  })
})
