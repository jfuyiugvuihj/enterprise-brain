/**
 * R141 · 「档位 ↔ 地址」那张表（判据③ 的第一半：选中项写进地址、刷新留得住）
 *
 * 这一枚是纯函数面：不需要 DOM、不需要网络，所以能真跑而不是 grep。
 * 后端那三枚档位名由 tests/test_r32_lane_contract.py 钉成闭集，这里钉的是前端不许漂。
 */
import { describe, expect, it } from 'vitest'
import {
  LANE_CHOICES,
  LANE_UNDECLARED,
  LANE_VALUES,
  laneFromQuery,
  queryWithLane,
} from '../lane-choice.js'

describe('L1 · 取值闭集与后端逐字相同', () => {
  it('四枚取值：qa / analysis / report 加一枚空串，没有第五种拼写', () => {
    expect(LANE_VALUES).toEqual(['', 'qa', 'analysis', 'report'])
    expect(LANE_UNDECLARED).toBe('')
  })

  it('每枚选项都带着说给人看的名，且空串那枚不叫「问答档」', () => {
    const byValue = Object.fromEntries(LANE_CHOICES.map(c => [c.value, c.label]))
    expect(byValue['']).toBe('系统判断')
    expect(byValue.qa).toBe('问答档')
    expect(byValue.report).toBe('报告档')
  })
})

describe('L2 · 地址栏 → 选择框', () => {
  it('认得的值原样认下来', () => {
    for (const value of LANE_VALUES) {
      expect(laneFromQuery({ lane: value })).toBe(value)
    }
  })

  it('地址里没这一格、写成空、写成认不得的，一律落回「系统判断」', () => {
    expect(laneFromQuery({})).toBe(LANE_UNDECLARED)
    expect(laneFromQuery({ lane: '' })).toBe(LANE_UNDECLARED)
    // 用户手改地址栏是常态：拼错的一律不认，也不原样发回后端（/ask 的闸会 400）
    expect(laneFromQuery({ lane: 'REPORT' })).toBe(LANE_UNDECLARED)
    expect(laneFromQuery(undefined)).toBe(LANE_UNDECLARED)
  })
})

describe('L3 · 选择框 → 地址栏', () => {
  it('选了一档就写进地址，别的查询参数一格不少', () => {
    expect(queryWithLane({ session: 'abc' }, 'analysis')).toEqual({ session: 'abc', lane: 'analysis' })
  })

  it('退回「系统判断」是把那一格删掉，而不是留一枚 ?lane=', () => {
    // 留着空值参数等于让"没人选"看起来像一次选择，转发出去的链接还会带上它
    expect(queryWithLane({ lane: 'report' }, '')).toEqual({})
  })

  it('喂进一个不认识的档位也不会把它写进地址', () => {
    expect(queryWithLane({}, 'whatever')).toEqual({})
  })

  it('反证锚：把写入函数换成原样返回，上面三条必红（这里钉住它真的会改对象）', () => {
    const query = { tab: 'docs' }
    const next = queryWithLane(query, 'qa')
    expect(next).not.toBe(query)
    expect(query).toEqual({ tab: 'docs' })
  })
})
