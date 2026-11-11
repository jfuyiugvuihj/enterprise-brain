import { effectScope } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
const { fetchBlob } = vi.hoisted(() => ({ fetchBlob: vi.fn() }))
vi.mock('../lib/artifacts', () => ({ fetchArtifactBlob: fetchBlob }))
import { useChatArtifactDownload } from './useChatArtifactDownload'
let scope, click, revoke, saved
beforeEach(() => {
  fetchBlob.mockReset(); click = vi.fn(); revoke = vi.fn(); saved = {}
  vi.stubGlobal('window', { location: { origin: 'http://127.0.0.1' } })
  vi.stubGlobal('document', { createElement: () => saved = { click } })
  scope = effectScope()
})
afterEach(() => { scope.stop(); vi.unstubAllGlobals() })
const event = (href) => ({ target: { closest: () => ({ getAttribute: () => href }) }, preventDefault: vi.fn() })
it('chat report click uses authenticated Blob and business filename', async () => {
  fetchBlob.mockResolvedValue({ objectUrl: 'blob:report', filename: '费用分析简报.pdf', revoke })
  const download = scope.run(useChatArtifactDownload); const e = event('/api/v1/artifacts/a1/download')
  await download.onClick(e, 'turn-1')
  expect(e.preventDefault).toHaveBeenCalled(); expect(fetchBlob).toHaveBeenCalledWith('/api/v1/artifacts/a1/download', expect.objectContaining({ signal: expect.any(AbortSignal) }))
  expect(saved.href).toBe('blob:report'); expect(saved.download).toBe('费用分析简报.pdf'); expect(click).toHaveBeenCalledOnce()
  scope.stop(); expect(revoke).toHaveBeenCalledOnce()
})
it('external links keep default navigation and never receive the token', async () => {
  const download = scope.run(useChatArtifactDownload); const e = event('https://example.com/api/v1/artifacts/a1/download')
  await download.onClick(e, 'turn-1'); expect(fetchBlob).not.toHaveBeenCalled(); expect(e.preventDefault).not.toHaveBeenCalled()
})
it('denied downloads report an error on the clicked turn and save nothing', async () => {
  const denied = Object.assign(new Error('没有权限下载此文件'), { status: 403 }); fetchBlob.mockRejectedValue(denied)
  const download = scope.run(useChatArtifactDownload)
  await download.onClick(event('/api/v1/artifacts/a1/download'), 'turn-1')
  expect(download.error.value).toEqual({ turn: 'turn-1', cause: denied }); expect(click).not.toHaveBeenCalled(); expect(download.busy.value).toBe('')
})
it('unmount cancels an outstanding download and never saves late bytes', async () => {
  let resolve; fetchBlob.mockImplementation(() => new Promise(r => resolve = r))
  const download = scope.run(useChatArtifactDownload); const job = download.onClick(event('/api/v1/artifacts/a1/download'), 'turn-1')
  const signal = fetchBlob.mock.calls[0][1].signal; scope.stop(); expect(signal.aborted).toBe(true)
  resolve({ objectUrl: 'blob:late', filename: 'report.pdf', revoke }); await job
  expect(click).not.toHaveBeenCalled(); expect(revoke).toHaveBeenCalledOnce()
})
