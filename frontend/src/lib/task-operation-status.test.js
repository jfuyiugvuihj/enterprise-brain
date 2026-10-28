import { afterEach, describe, expect, it } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import ChatPanel from '../components/ChatPanel.vue'
import { activeId, createStreamReducer, createStreamState, messages, settleReportStepFromContent } from './sessions'

afterEach(() => { messages.value = []; activeId.value = '' })

describe('操作状态按实际结果呈现', () => {
  it.each(['failed', 'rejected', 'cancelled', 'completed'])('运行后收到 %s 不改写成 done', (status) => {
    const message = { content: '', steps: [] }
    const reduce = createStreamReducer(message, createStreamState())
    reduce({ event: 'step', payload: { tool: 'export', label: '导出报告', status: 'running' } })
    reduce({ event: 'step', payload: { tool: 'export', status, elapsed: 1.2 } })
    expect(message.steps).toEqual([{ tool: 'export', label: '导出报告', status, elapsed: 1.2 }])
  })

  it('未知或缺失状态不冒充成功', () => {
    const message = { steps: [] }
    const reduce = createStreamReducer(message, createStreamState())
    reduce({ event: 'step', payload: { tool: 'export' } })
    expect(message.steps[0].status).toBe('unknown')
  })

  it('确认后的真实终态更新同一步骤', () => {
    const message = { steps: [{ tool: 'export', status: 'unknown' }] }
    createStreamReducer(message, createStreamState())({ event: 'step',
      payload: { tool: 'export', status: 'failed' } })
    expect(message.steps).toEqual([{ tool: 'export', status: 'failed', elapsed: null }])
  })

  it('正文下载链接不能证明导出成功', () => {
    const message = {
      content: '报告已生成: [📋 下载报告](/api/v1/artifacts/abc/download)',
      steps: [{ tool: 'export', label: '导出报告', status: 'unknown' }],
    }
    expect(settleReportStepFromContent(message)).toBe(false)
    expect(message.steps[0].status).toBe('unknown')
  })

  it('正文只有失败或拒绝时不覆盖终态', () => {
    const message = {
      content: '报告已生成: [📋 下载报告](/api/v1/artifacts/abc/download)',
      steps: [{ tool: 'export', label: '导出报告', status: 'failed' }],
    }
    expect(settleReportStepFromContent(message)).toBe(false)
    expect(message.steps[0].status).toBe('failed')
  })

  it.each([
    ['failed', '执行失败', '⚠'], ['rejected', '已拒绝，未执行', '✕'],
    ['cancelled', '已取消', '⏹'], ['completed', '执行成功', '✅'],
    ['done', '处理结束', '•'], ['unknown', '结果未确认', '?'],
    ['partial', '部分结果待核对', '◐'],
  ])('%s 状态有准确文字与图标', async (status, text, icon) => {
    activeId.value = 'task-review-status'
    messages.value = [{ role: 'assistant', content: '核查结果', mid: 'status-turn',
      steps: [{ tool: 'export', label: '导出报告', status, elapsed: null }] }]
    const html = await renderToString(h(ChatPanel))
    expect(html).toContain(text)
    expect(html).toContain(icon)
    if (status !== 'completed') expect(html).not.toContain('✅</span>')
    expect(html).not.toContain('class="step-time pulse"')
  })
})
