import { describe, expect, it } from 'vitest'
import { analysisReuseDraft } from '../analysis-reuse'

const record = overrides => ({ status: 'completed', parameters: { query: '精确问题？', filename: 'sales.csv' }, result: { columns: ['收入'] }, ...overrides })
const preview = overrides => ({ filename: 'sales.csv', version_id: 'v2', profile: { columns: [{ name: '收入', dtype: 'number' }, { name: '部门' }] }, ...overrides })
const metricBinding = overrides => ({ definition_id: 'metric:revenue:v3', metric_name: '收入', definition_version: '3', formula: '销售额 - 退款', ...overrides })
const boundRecord = () => record({
  calculation_run_id: 'run-17',
  metric_definition_id: 'metric:revenue:v3',
  parameters: { query: '精确问题？', filename: 'sales.csv', metric_binding: metricBinding() },
})
const reusePreview = overrides => preview({
  reuse: {
    calculation_run_id: 'run-17',
    metric_binding: metricBinding(),
    metric_binding_sha256: 'sha256:original-binding',
  },
  ...overrides,
})

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
  it('preserves a bound metric only with matching server reuse metadata', () => {
    expect(analysisReuseDraft(boundRecord(), reusePreview())).toEqual({
      question: '精确问题？', filename: 'sales.csv', version_id: 'v2',
      metric_binding: metricBinding(), metric_binding_sha256: 'sha256:original-binding',
    })
  })
  it('rejects missing or mismatched binding metadata instead of downgrading to plain analysis', () => {
    const record = boundRecord()
    expect(() => analysisReuseDraft(record, preview())).toThrow('指标口径')
    expect(() => analysisReuseDraft(record, reusePreview({ reuse: { ...reusePreview().reuse, calculation_run_id: 'run-other' } }))).toThrow('指标口径')
    expect(() => analysisReuseDraft(record, reusePreview({ reuse: { ...reusePreview().reuse, metric_binding: null } }))).toThrow('指标口径')
    expect(() => analysisReuseDraft(record, reusePreview({ reuse: { ...reusePreview().reuse, metric_binding_sha256: '' } }))).toThrow('指标口径')
    expect(() => analysisReuseDraft(record, reusePreview({ reuse: { ...reusePreview().reuse, metric_binding: metricBinding({ definition_id: 'metric:other:v1' }) } }))).toThrow('指标口径')
  })
})
