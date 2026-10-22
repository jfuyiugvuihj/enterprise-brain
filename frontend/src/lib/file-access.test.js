import { describe, expect, it } from 'vitest'
import { filterFileClassification, fileAccessLabel } from './file-access'

describe('文件列表密级筛选与授权范围说明', () => {
  const rows = [{ filename:'一级.csv', classification:1, department_ids:['财务'] },
    { filename:'三级.csv', classification:3, department_ids:['销售'] }, { filename:'历史.csv' }]
  it('选择等级缩小列表，全部恢复原计数，不改变原记录', () => {
    expect(filterFileClassification(rows, '3').map(row=>row.filename)).toEqual(['三级.csv'])
    expect(filterFileClassification(rows, '').length).toBe(3)
    expect(rows.length).toBe(3)
  })
  it('未登记不冒充一级；未知筛选不放出全部文件', () => {
    expect(filterFileClassification(rows, 'unknown').map(row=>row.filename)).toEqual(['历史.csv'])
    expect(filterFileClassification(rows, 'invalid')).toEqual([])
  })
  it('数值和字符串等级采用同一口径', () => {
    expect(filterFileClassification([{classification:'2'}], '2')).toHaveLength(1)
    expect(filterFileClassification([{classification:'internal',classification_level:2}], '2')).toHaveLength(1)
  })
  it('密级与部门分别显示，不承诺一级全公司可见', () => {
    expect(fileAccessLabel(rows[0])).toContain('密级 1 级')
    expect(fileAccessLabel(rows[0])).toContain('部门范围：财务')
    expect(fileAccessLabel(rows[0])).not.toContain('全公司')
    expect(fileAccessLabel({classification:2, department:'研发'})).toContain('部门范围：研发')
    expect(fileAccessLabel({classification:1, department:'财务', visibility:'enterprise_shared'})).toBe('密级 1 级 · 企业内共享')
    expect(fileAccessLabel({classification:1, department:'财务', visibility:'private'})).toContain('部门范围：财务')
  })
  it('缺失授权标注明确说未登记，不猜部门或密级', () => {
    expect(fileAccessLabel({})).toBe('密级未登记 · 部门范围未登记')
  })
})
