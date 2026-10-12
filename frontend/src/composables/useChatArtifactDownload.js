import { onScopeDispose, shallowRef } from 'vue'
import { fetchArtifactBlob } from '../lib/artifacts'

export function useChatArtifactDownload() {
  const busy = shallowRef('')
  const error = shallowRef(null)
  const handles = new Map()
  let controller
  let disposed = false
  onScopeDispose(() => {
    disposed = true
    controller?.abort()
    for (const [handle, timer] of handles) { clearTimeout(timer); handle.revoke() }
    handles.clear()
  })
  async function onClick(event, turn) {
    const anchor = event.target?.closest?.('a')
    if (!anchor) return
    let target
    try { target = new URL(anchor.getAttribute('href') || '', window.location.origin) } catch (_) { return }
    if (target.origin !== window.location.origin || !/^\/api\/v1\/artifacts\/[\w-]+\/download$/.test(target.pathname)) return
    event.preventDefault()
    if (busy.value || disposed) return
    busy.value = turn
    error.value = null
    controller = new AbortController()
    try {
      const handle = await fetchArtifactBlob(target.pathname, { signal: controller.signal })
      if (disposed) { handle.revoke(); return }
      const link = document.createElement('a')
      link.href = handle.objectUrl
      link.download = handle.filename || '分析报告.pdf'
      link.click()
      const timer = setTimeout(() => { handle.revoke(); handles.delete(handle) }, 1000)
      handles.set(handle, timer)
    } catch (cause) {
      if (!disposed && cause?.code !== 'aborted') error.value = { turn, cause }
    } finally {
      busy.value = ''
    }
  }
  return { busy, error, onClick }
}
