/**
 * 运行期健康度的前端读法：只要「本机模型在不在」这一件事，别在这里做第二套判定。
 *
 * 数据源是 `GET /health/details` 的 `problems` 数组（后端 `app/common/monitoring.py` 里
 * 判 `model_not_available`）。这条链路存在的理由很具体：模型权重没拉时，问答并不会报错，
 * 而是把检索到的原文当成回答吐回来——界面上如果继续挂着绿点和「本地模型」，
 * 就是在替客户制造「AI 正常，只是答案短」的错觉。这属于计划 §不假装健康 那条。
 *
 * 三条约定：
 * 1. **读不到就当不知道**，返回 `null`，由界面渲染「状态未知」，绝不渲染成「就绪」。
 * 2. 结果缓存 60 秒：顶栏是每次进对话页都要显示的，不该每次都打一次健康检查。
 * 3. 不抛异常。健康检查失败本身不该把对话页变成红屏。
 */
import { http } from './http.js'

export const MODEL_NOT_AVAILABLE = 'model_not_available'

const CACHE_MS = 60_000

let cached = null
let cachedAt = 0

export function resetRuntimeHealthCache() {
  cached = null
  cachedAt = 0
}

export async function fetchRuntimeHealth({ force = false } = {}) {
  const now = Date.now()
  if (!force && cached && now - cachedAt < CACHE_MS) return cached
  try {
    const res = await http.get('/health/details', { timeout: 8000 })
    const body = res?.data
    if (!body || typeof body !== 'object') {
      cached = null
      return null
    }
    cached = {
      status: typeof body.status === 'string' ? body.status : '',
      problems: Array.isArray(body.problems) ? body.problems.map(String) : [],
      modelName: String(body?.model?.name || ''),
      modelSource: String(body?.model?.source || ''),
    }
    cachedAt = now
    return cached
  } catch {
    // 一次读不到不代表模型坏了，但也不代表它是好的：交给「未知」那张脸。
    cached = null
    cachedAt = 0
    return null
  }
}

/** ready / down / unknown —— 界面只按这三档显示，不做第四个状态。 */
export function modelState(health) {
  if (!health || !Array.isArray(health.problems)) return 'unknown'
  return health.problems.includes(MODEL_NOT_AVAILABLE) ? 'down' : 'ready'
}

export const MODEL_STATE_TEXT = {
  ready: '本地模型就绪',
  down: '本机模型未就绪',
  unknown: '模型状态未知',
}

export function modelStatusText(health) {
  return MODEL_STATE_TEXT[modelState(health)]
}
