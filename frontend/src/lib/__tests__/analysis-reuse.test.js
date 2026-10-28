import { describe, expect, it } from 'vitest'
import { analysisReuseDraft } from '../analysis-reuse'

const record = overrides => ({ status: 'completed', parameters: { query: '精确问题？', filename: 'sales.csv' }, result: { columns: ['收入'] }, ...overrides })
const preview = overrides => ({ filename: 'sales.csv', version_id: 'v2', profile: { columns: [{ name: '收入', dtype: 'number' }, { name: '部门' }] }, ...overrides })

describe('analysisReuseDraft', () => {
  it('keeps the exact question, permits added fields, and returns only a draft', () => {
    const draft = analysisReuseDraft(record(), preview())
    expect(draft).toEqual({ question: '精确问题？', filename: 'sales.csv', version_id: 'v2' })
    expect(draft).not.toHaveProperty('result')
  })
  it('refuses missing or unit-changed fields by exact name', () => {
    expect(() => analysisReuseDraft(record(), preview({ profile: { columns: ['部门'] } }))).toThrow('收入')
    const unitRecord = record({ result: { analysis_scope: { units: [{ column: '收入（万元）' }] } } })
    expect(() => analysisReuseDraft(unitRecord, preview({ profile: { columns: ['收入'] } }))).toThrow('收入（万元）')
  })
  it('refuses another filename and old records without verifiable fields', () => {
    expect(() => analysisReuseDraft(record(), preview({ filename: 'other.csv' }))).toThrow('同名')
    expect(() => analysisReuseDraft(record({ result: undefined }), preview())).toThrow('未记录')
  })
})
