import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'
vi.mock('../../lib/http', async (original) => ({ ...await original(), authedFetch: vi.fn(), http: { get: vi.fn() } }))
import { authedFetch, http } from '../../lib/http'
import { activeId, hitl, loading, messages, reconcileAuthoritativeBody, sessions } from '../../lib/sessions'
import ChatPanel from '../ChatPanel.vue'
import HitlPendingPanel, { decisionView } from '../hitl/HitlPendingPanel.vue'
async function bindings(component = ChatPanel) {
  let state
  await renderToString(h({ setup(_, ctx) { state = component.setup({}, ctx); return () => null } }))
  return state
}
beforeEach(() => {
  vi.clearAllMocks()
  activeId.value = 'confirm-test'
  sessions.value = []
  loading.value = false
  hitl.value = { pending: ['export'], labels: ['导出报告'] }
  messages.value = [{ role: 'assistant', content: '核查结果', steps: [{ tool: 'export', status: 'unknown' }] }]
  http.get.mockResolvedValue({ data: { ledger_status: 'awaiting' } })
})
describe('确认决定不提前冒充后端结果', () => {
  it('从待办返回对话时按服务端终态更新步骤，不保留旧待确认牌', async () => {
    http.get.mockResolvedValue({ data: { messages: [{ role: 'assistant', content: '报告已生成',
      steps: [{ tool: 'export', status: 'completed' }] }] } })
    expect(await reconcileAuthoritativeBody()).toBe(true)
    expect(messages.value[0].content).toBe('报告已生成')
    expect(messages.value[0].steps[0].status).toBe('completed')
  })
  it('收到取消终态替换旧等待确认正文，未完成步骤显示取消', async () => {
    messages.value[0].content = '等待你确认，尚未产出回答内容。'
    const body = 'event: request.cancelled\ndata: {"type":"request.cancelled","event_type":"request.cancelled","status":"cancelled"}\n\n'
    authedFetch.mockResolvedValue(new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }))
    http.get.mockResolvedValue({ data: { ledger_status: 'abandoned' } })
    const state = await bindings()
    await state.approve(true)
    expect(messages.value[0].content).toContain('本次操作已取消')
    expect(messages.value[0].content).not.toContain('等待你确认')
    expect(messages.value[0].steps[0].status).toBe('cancelled')
  })
  it('取消不能抹掉已完成分析和已登记成果链接', async () => {
    messages.value[0].content = '已算出30件，[下载已完成图表](/api/v1/artifacts/chart1/download)'
    messages.value[0].steps.unshift({ tool: 'data', status: 'completed' })
    authedFetch.mockResolvedValue(new Response('event: request.cancelled\ndata: {"type":"request.cancelled","status":"cancelled"}\n\n', { headers: { 'Content-Type': 'text/event-stream' } }))
    http.get.mockResolvedValue({ data: { ledger_status: 'abandoned' } })
    const state = await bindings();await state.approve(true)
    expect(messages.value[0].content).toContain('30件')
    expect(messages.value[0].content).toContain('/api/v1/artifacts/chart1/download')
    expect(messages.value[0].steps[0].status).toBe('completed')
  })
  it('聊天失败正文保留业务说明，内部原因码不显示在正文', async () => {
    const state = await bindings()
    const html = state.renderMd('本轮未导出，请管理员补部门归属（error_code=department_scope_required）')
    expect(html).toContain('请管理员补部门归属')
    expect(html).not.toContain('error_code')
  })
  it('发送拒绝期间保留卡片与步骤，阻止重复决定；HTTP失败后可以重试', async () => {
    let resolve
    authedFetch.mockReturnValue(new Promise(r => { resolve = r }))
    const state = await bindings()
    const pending = state.approve(false)
    expect(hitl.value).not.toBeNull()
    expect(messages.value[0].steps[0].status).toBe('unknown')
    await state.approve(true)
    expect(authedFetch).toHaveBeenCalledTimes(1)
    resolve(new Response(JSON.stringify({ detail: 'permission_denied' }), { status: 403 }))
    await pending
    expect(hitl.value).not.toBeNull()
    expect(messages.value[0].steps[0].status).toBe('unknown')
    expect(loading.value).toBe(false)
    expect(hitl.value.decisionUnknown).toBe(false)
  })
  it('后续收尾失败不能断言拒绝没有生效', () => {
    const view = decisionView({ approved: false, terminal: 'failed' })
    expect(view.face).toBe('unknown')
    expect(view.title + view.description).not.toContain('没有生效')
  })
  it('服务端记录拒绝后即使收尾失败也呈现已拒绝；读不到不能声称成功', () => {
    expect(decisionView({ approved: false, terminal: 'failed', ledgerStatus: 'refused' }).title).toBe('已驳回，这一步不会执行')
    expect(decisionView({ approved: false, terminal: 'completed', ledgerStatus: '' }).face).toBe('unknown')
  })
  it('决定读取失败时保留未知卡，重新读取仍待确认后才恢复操作', async () => {
    authedFetch.mockResolvedValue(new Response('{}', { status: 503 }))
    http.get.mockRejectedValue(new Error('offline'))
    const state = await bindings()
    await state.approve(false)
    expect(hitl.value.decisionUnknown).toBe(true)
    await state.approve(true)
    expect(authedFetch).toHaveBeenCalledTimes(1)
    http.get.mockResolvedValue({ data: { ledger_status: 'awaiting' } })
    await state.refreshPendingDecision()
    expect(hitl.value.decisionUnknown).toBe(false)
    expect(messages.value[0].steps[0].status).toBe('unknown')
  })
  it('只有服务端拒绝回执才把导出步骤改成拒绝', async () => {
    authedFetch.mockResolvedValue(new Response('{}', { status: 503 }))
    http.get.mockResolvedValue({ data: { ledger_status: 'refused' } })
    const state = await bindings()
    await state.approve(false)
    expect(hitl.value).toBeNull()
    expect(messages.value[0].steps[0].status).toBe('rejected')
  })
  it('待办从真实SSE收尾失败中核实拒绝决定，而不是把拒绝判成失败', async () => {
    const body = 'event: request.failed\ndata: {"type":"request.failed","event_type":"request.failed","status":"failed","data":{"error_code":"internal_error"}}\n\n'
    authedFetch.mockResolvedValue(new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }))
    http.get.mockImplementation(path => Promise.resolve({ data: path.startsWith('/hitl/decision/')
      ? { ledger_status: 'refused' } : { items: [], has_more: false } }))
    const state = await bindings(HitlPendingPanel)
    const view = await state.decide({ row: { sessionId: 'confirm-test' }, approved: false })
    expect(http.get).toHaveBeenCalledWith('/hitl/decision/confirm-test')
    expect(view.title).toBe('已驳回，这一步不会执行')
    expect(view.description).toContain('收尾失败')
  })
})
