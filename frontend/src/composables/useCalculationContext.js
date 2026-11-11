import { shallowRef, watch } from 'vue'
import { http } from '../lib/http'

// Each request has its own authorized calculation history; never persist or reuse
// a previous task's records when another session/account is being shown.
export function useCalculationContext(context) {
  const records = shallowRef([])
  const status = shallowRef('idle')
  watch(context, async (current, _previous, onCleanup) => {
    records.value = []
    status.value = 'idle'
    if (!current.session || !current.request || current.loading) return
    const controller = new AbortController()
    let stale = false
    onCleanup(() => { stale = true; controller.abort() })
    status.value = 'loading'
    try {
      const response = await http.get('/calculations', {
        params: { request_id: current.request, limit: 100 }, signal: controller.signal,
      })
      if (stale) return
      if (!Array.isArray(response.data?.items)) throw new Error('invalid_calculation_history')
      records.value = response.data.items.filter(row => row.request_id === current.request
        && String(row.parameters?.session_id || '').split(':')[0] === current.session)
        .sort((left, right) => String(left.started_at || '').localeCompare(String(right.started_at || '')))
      status.value = 'loaded'
    } catch (_) {
      if (!stale) status.value = 'unavailable'
    }
  }, { immediate: true })
  return { records, status }
}
