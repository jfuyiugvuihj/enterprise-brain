import { expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createMemoryHistory, createRouter } from 'vue-router'
import DataPanel from '../DataPanel.vue'
import { FEED_TABS } from '../../router/feed-tabs.js'

async function face(role) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: DataPanel }] })
  const app = createSSRApp(DataPanel, { userRole: role })
  app.use(router)
  await router.push('/')
  await router.isReady()
  return renderToString(app)
}

it('offers data upload levels the signed-in role can use', async () => {
  expect(FEED_TABS.find(tab => tab.id === 'data')?.needsUserRole).toBe(true)
  for (const [role, expected] of [['staff', [1]], ['manager', [1, 2]], ['admin', [1, 2, 3]]]) {
    const html = await face(role)
    const select = html.match(/<select[^>]*data-testid="data-upload-classification"[^>]*>([\s\S]*?)<\/select>/)?.[1]
    expect(select).toBeTruthy()
    expect([...select.matchAll(/<option[^>]*value="(\d+)"/g)].map(match => Number(match[1]))).toEqual(expected)
    if (role === 'staff') expect(select).toMatch(/<option[^>]*value="1"[^>]*selected/)
  }
  expect(await face('auditor')).not.toContain('data-testid="data-upload-input"')
})
