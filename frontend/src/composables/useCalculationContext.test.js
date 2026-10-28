import { effectScope, nextTick, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
vi.mock('../lib/http', () => ({ http: { get: vi.fn() } }))
import { http } from '../lib/http'
import { useCalculationContext } from './useCalculationContext'

describe('实际计算范围', () => {
  it('换会话后清除旧依据，迟到的返回不能串到新任务', async () => {
    let finishOld
    http.get.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve }))
      .mockResolvedValueOnce({ data: { items: [{ calculation_run_id: 'new', request_id: 'r2',
        parameters: { session_id: 's2:data' }, status: 'completed' }] } })
    const context = ref({ session: 's1', request: 'r1', loading: false })
    const scope = effectScope()
    const result = scope.run(() => useCalculationContext(context))
    context.value = { session: 's2', request: 'r2', loading: false }
    await nextTick()
    await nextTick()
    finishOld({ data: { items: [{ calculation_run_id: 'old' }] } })
    await nextTick()
    expect(result.records.value.map(row => row.calculation_run_id)).toEqual(['new'])
    expect(http.get.mock.calls[1][1].params.request_id).toBe('r2')
    context.value = { session: 's3', request: '', loading: false }
    await nextTick()
    expect(result.records.value).toEqual([])
    scope.stop()
  })

  it('读取失败明确未知，不用上一轮或正文拼成计算依据', async () => {
    http.get.mockRejectedValueOnce(new Error('unavailable'))
    const scope = effectScope()
    const result = scope.run(() => useCalculationContext(ref({ session: 's', request: 'r', loading: false })))
    await nextTick()
    expect(result.status.value).toBe('unavailable')
    expect(result.records.value).toEqual([])
    scope.stop()
  })
})
