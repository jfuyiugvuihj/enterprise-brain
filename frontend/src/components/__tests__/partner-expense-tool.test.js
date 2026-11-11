import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import ApprovalPanel from '../ApprovalPanel.vue'
import { routes } from '../../router/index.js'

describe('费用自查作为独立场景工具', () => {
  it('待办页只呈现真实操作确认，不自动查询费用制度', async () => {
    const route = routes.find(item => item.name === 'approval')
    const html = await renderToString(h(route.component, route.props))
    expect(html).toContain('data-testid="hitl-pending"')
    expect(html).not.toContain('data-testid="approval-demo-flag"')
    expect(html).not.toContain('data-testid="run-approval"')
  })

  it('场景工具呈现费用自查，并与操作确认分开', async () => {
    const route = routes.find(item => item.name === 'expense-selfcheck')
    expect(route).toBeTruthy()
    const html = await renderToString(h(route.component, route.props))
    expect(html).toContain('data-testid="approval-demo-flag"')
    expect(html).toContain('data-testid="run-approval"')
    expect(html).not.toContain('data-testid="hitl-pending"')
  })
})
