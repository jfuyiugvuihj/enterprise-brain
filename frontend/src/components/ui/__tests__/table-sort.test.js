import { describe, expect, it } from 'vitest'
import { ariaSortFor, nextSortState, sortRows } from '../table-sort.js'

const COLUMNS = [
  { key: 'department', label: '部门', sortable: true },
  { key: 'amount', label: '金额', sortable: true, align: 'right' },
  { key: 'updated', label: '更新' },
]

const ROWS = [
  { department: '市场部', amount: 12600, updated: '2026-09-01' },
  { department: '财务部', amount: 9800, updated: '2026-09-03' },
  { department: '运营部', amount: 4200, updated: '2026-09-02' },
]

describe('表头点击循环', () => {
  it('无 → asc → desc → 无', () => {
    const first = nextSortState({ key: '', order: '' }, 'amount')
    expect(first).toEqual({ key: 'amount', order: 'asc' })
    expect(nextSortState(first, 'amount')).toEqual({ key: 'amount', order: 'desc' })
    expect(nextSortState({ key: 'amount', order: 'desc' }, 'amount')).toEqual({ key: '', order: '' })
  })

  it('换列重新从升序开始', () => {
    expect(nextSortState({ key: 'amount', order: 'desc' }, 'department')).toEqual({ key: 'department', order: 'asc' })
  })
})

describe('sortRows', () => {
  it('数值升序与降序', () => {
    expect(sortRows(ROWS, { key: 'amount', order: 'asc' }, COLUMNS).map((row) => row.amount)).toEqual([4200, 9800, 12600])
    expect(sortRows(ROWS, { key: 'amount', order: 'desc' }, COLUMNS).map((row) => row.amount)).toEqual([12600, 9800, 4200])
  })

  it('中文列按拼音归并排序', () => {
    expect(sortRows(ROWS, { key: 'department', order: 'asc' }, COLUMNS).map((row) => row.department)).toEqual(['财务部', '市场部', '运营部'])
  })

  it('字符串数字按数值比较，不出现 10 < 9', () => {
    const rows = [{ n: '10' }, { n: '9' }, { n: '100' }]
    expect(sortRows(rows, { key: 'n', order: 'asc' }, [{ key: 'n' }]).map((row) => row.n)).toEqual(['9', '10', '100'])
  })

  it('空值一律沉底，正反序都一样', () => {
    const rows = [{ n: null }, { n: 3 }, { n: undefined }, { n: 1 }]
    expect(sortRows(rows, { key: 'n', order: 'asc' }, [{ key: 'n' }]).map((row) => row.n)).toEqual([1, 3, null, undefined])
    expect(sortRows(rows, { key: 'n', order: 'desc' }, [{ key: 'n' }]).map((row) => row.n).slice(0, 2)).toEqual([3, 1])
  })

  it('不改动传入数组（表格组件依赖这个不变量）', () => {
    const rows = ROWS.slice()
    const snapshot = ROWS.map((row) => row.amount)
    sortRows(rows, { key: 'amount', order: 'desc' }, COLUMNS)
    expect(rows.map((row) => row.amount)).toEqual(snapshot)
  })

  it('无排序状态时按原顺序返回', () => {
    expect(sortRows(ROWS, { key: '', order: '' }, COLUMNS).map((row) => row.department)).toEqual(['市场部', '财务部', '运营部'])
    expect(sortRows(ROWS, null, COLUMNS)).toHaveLength(3)
    expect(sortRows([], { key: 'amount', order: 'asc' }, COLUMNS)).toEqual([])
  })

  it('列自带 value 取值函数时按派生值排', () => {
    const columns = [{ key: 'ratio', value: (row) => row.current / row.threshold }]
    const rows = [
      { current: 9, threshold: 10 },
      { current: 1, threshold: 10 },
      { current: 8, threshold: 10 },
    ]
    expect(sortRows(rows, { key: 'ratio', order: 'asc' }, columns).map((row) => row.current)).toEqual([1, 8, 9])
  })
})

describe('aria-sort', () => {
  it('未排序的列报 none', () => {
    expect(ariaSortFor({ key: 'amount', order: 'asc' }, 'department')).toBe('none')
    expect(ariaSortFor(null, 'amount')).toBe('none')
  })

  it('当前列报 ascending / descending', () => {
    expect(ariaSortFor({ key: 'amount', order: 'asc' }, 'amount')).toBe('ascending')
    expect(ariaSortFor({ key: 'amount', order: 'desc' }, 'amount')).toBe('descending')
  })
})
