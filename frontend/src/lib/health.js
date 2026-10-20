/**
 * 运行期健康度的前端读法：这一台机器此刻哪儿不对劲，界面就照实说哪一格不对劲。
 *
 * 数据源是 `GET /health/details`（后端 `app/common/monitoring.py`）：`problems` 数组是当下故障
 * 的枚举，`model.inference_compute` 那一族是推理算力那一格的具名读数。
 *
 * R268 · G07 补的是「只认一枚码」这个缺陷。改前整份文件只对 model_not_available 有反应
 * （旧 :57 那一行 includes(...) ? 'down' : 'ready'），于是后端明明已经报了向量检索模型缺失、
 * 后台队列连不上、存储被切成只读，顶栏照样是绿点加「本地模型就绪」——「假装健康」在这一格里
 * 不是措辞问题，是把后端已经给出的坏消息读丢了（monitoring.py 早就把这些码交出来了）。
 * 今天这份文件把 problems 里的每一族各自说一句话：检索模型 / 队列 / 只读 / 依赖没应答 /
 * 账号库不落盘 / 没走加速，六族六张脸两两不同，谁都不许替另一格说话（判据③）。
 *
 * 三条老规矩一个字不改：
 * 1. **读不到就当不知道**，返回 `null`，由界面渲染「状态未知」，绝不渲染成「就绪」。
 * 2. 结果缓存 60 秒：顶栏是每次进对话页都要显示的，不该每次都打一次健康检查。
 * 3. 不抛异常。健康检查失败本身不该把对话页变成红屏。
 * 第四条是 R268 加的：降级不是只有一张红脸。`modelState()` 多出来那一档 `degraded` 说的是
 * 「模型权重在，但这一台机器有别的东西不对」——既不并入 `down`（那句讲的是权重），
 * 更不是 `ready`（那是一句假话）。
 *
 * R465 补的是「这一发在不在路上」对外没有读数这一格。改前（本单基点 d824b10 现读 :31-41）这枚模块
 * 只有私有 `cached` / `cachedAt` 两格，它们讲的是【落地之后有没有货】，没有一格讲【此刻有没有一发
 * 在路上】。于是壳层那一发还没回来时面板就挂上来（App.vue:64 与 ChatPanel.vue:795 两处伸手），第二格
 * 查缓存查到的只是「没有」，只能自己再发一发 —— R458 丙5 把这枚数实量成 2 发。
 * 现在多一枚模块级 `inFlight`：同一时刻只允许一发在路上，后来的伸手等同一枚在飞的 promise；落地与
 * 失败都从同一个 `finally` 过，槽位一定清干净（不清就泄漏成「永远在飞」，界面此后一次也问不到新读数，
 * 那比多发一发更坏）。
 * `force` 穿的是那 60 秒缓存，不是「允许第二发同时在路上」：员工按「再看一次」那一刻若已经有一发在飞，
 * 那一发就是它要的答案——它比缓存里那份新，最多多等一次 8 秒超时。
 */
import { http } from './http.js'

export const MODEL_NOT_AVAILABLE = 'model_not_available'
export const EMBEDDING_MODEL_MISSING = 'embedding_model_missing'
export const QUEUE_UNAVAILABLE = 'queue_unavailable'
export const USERS_STORE_NOT_PERSISTENT = 'users_store_not_persistent'

const CACHE_MS = 60_000

let cached = null
let cachedAt = 0
// 在飞那一发：null = 此刻没有请求在路上。R465 之前这枚槽位根本不存在，「同时伸手」才数得出两发。
let inFlight = null

export function resetRuntimeHealthCache() {
  cached = null
  cachedAt = 0
  inFlight = null
}

/** 此刻有没有一发读数在路上；有就把那一枚 promise 交出去，后来的伸手等它，不另开一枪（判据①）。 */
export function runtimeHealthReadInFlight() {
  return inFlight
}

export async function fetchRuntimeHealth({ force = false } = {}) {
  // 这一行就是 single-flight 本身：先看在飞、再看缓存，两格都查完才轮到「发不发」。摘掉它判据① 当场红。
  if (inFlight) return inFlight
  const now = Date.now()
  if (!force && cached && now - cachedAt < CACHE_MS) return cached
  const read = probeOnce(now)
  inFlight = read
  try {
    return await read
  } finally {
    // 落地或失败都要清槽位；比对身份再清，免得把别人刚挂上的那一枚一起抹掉（泄漏 = 界面永远问不到新读数）。
    if (inFlight === read) inFlight = null
  }
}

/**
 * 真打网络的那一发，只在没有同路人的时候才被叫起来。它自己不 reject：读不到就交回 null，
 * 由界面画「状态未知」那第三张脸（老规矩 1 与 3）。
 */
async function probeOnce(now) {
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
      // R268 · G07 接的四枚读数：算力那一族后端早有具名读数，缺的只是「有人读它」。
      // 一律按「读到才有」的形状存：读不到留空串 / null，界面据此闭嘴，不替后端编一格。
      computeKind: typeof body?.model?.inference_compute === 'string' ? body.model.inference_compute : '',
      computeDetail: String(body?.model?.inference_compute_detail || ''),
      computeErrorCode: body?.model?.inference_compute_error_code == null
        ? ''
        : String(body.model.inference_compute_error_code),
      computeAgeSeconds: Number.isFinite(Number(body?.model?.inference_compute_age_seconds))
        ? Number(body.model.inference_compute_age_seconds)
        : null,
      // 只读名单直接取后端算好的那一列（monitoring.py 的 storage_snapshot），前端不重算判定。
      readOnlyProtected: Array.isArray(body?.storage?.read_only_protected)
        ? body.storage.read_only_protected.map(String)
        : [],
    }
    cachedAt = now
    return cached
  } catch {
    // 一次读不到不代表模型坏了，但也不代表它是好的：交给「未知」那张脸。
    // 🔴 失败一律把缓存作废（判据②）：留着旧读数再盖一枚新时间戳，就是拿一份过期读数冒充「刚刚问过了」。
    cached = null
    cachedAt = 0
    return null
  }
}

/** 子系统名 → 员工认得出的那一格的名字。名单外的原样带出，不猜、不并格。 */
const SUBSYSTEM_NAMES = {
  memories: '长期记忆',
  user_profiles: '用户画像',
  knowledge_graph: '知识图谱',
  open_platform_apps: '开放平台应用',
  users: '账号库',
  queue: '后台任务队列',
}

/** 依赖名 → 人话。monitoring.py 交出来的是 postgres / redis / ollama 三枚。 */
const DEPENDENCY_NAMES = {
  postgres: '主数据库',
  redis: '队列与缓存服务',
  ollama: '本机模型服务',
}

const namedSubsystem = (name) => SUBSYSTEM_NAMES[name] || String(name)
const namedDependency = (name) => DEPENDENCY_NAMES[name] || String(name)

/**
 * 一枚故障码归哪一族：model / embedding / queue / store / readOnly / dependency / other。
 * 返回值是给界面挂 key 与用例取证用的身份，不是文案。
 * 只读与依赖那两族在后端是拼出来的（f-string），所以这里按前后缀认，不硬抄枚举行。
 * 「其它」那一档必须留着一张自己的脸：后端新加一格时界面说「这一格我还不认识」，
 * 而不是闭嘴——闭嘴就又回到报绿。
 */
export function problemFamily(problem) {
  const code = String(problem || '')
  if (code === MODEL_NOT_AVAILABLE) return 'model'
  if (code === EMBEDDING_MODEL_MISSING) return 'embedding'
  if (code === QUEUE_UNAVAILABLE) return 'queue'
  if (code === USERS_STORE_NOT_PERSISTENT) return 'store'
  if (code.endsWith('_read_only')) return 'readOnly'
  if (/^(postgres|redis|ollama)_[a-z_]+$/.test(code)) return 'dependency'
  return 'other'
}

/**
 * 一族一句话。🔴 六句两两不同：判据③点名「不许用一条红文案兜三格」，所以这里是一族一句，
 * 不是一句模板换三个主语。句子里一律不带裸码名（V6 那闸门认的就是那个形状）：要说哪一格
 * 出了问题，只说这一格的人话名字。
 */
const FAMILY_FACES = {
  embedding: {
    label: '检索模型缺失',
    headline: '这台机器上的向量检索模型没就绪',
    detail: '问答照旧能发，但「按语义找资料」这一环今天没有可用的模型，检索质量会退化。请让管理员在本机模型设置里把这枚检索模型拉下来。',
  },
  queue: {
    label: '队列服务连不上',
    headline: '后台任务队列连不上',
    detail: '这一刻排不进队列的提问会被当场回绝，界面拦不住它。请让管理员检查队列服务有没有起来——队列只在连得上的时候工作。',
  },
  store: {
    label: '账号库不落盘',
    headline: '账号库没有落在持久存储上',
    detail: '现在建出来的账号重启就会丢。上线之前请让管理员把账号库切到持久存储。',
  },
  dependency: {
    headline: '',
    detail: '这一项服务此刻没应答，凡是走到它的功能都会失败或降级。请让管理员检查这一项服务有没有起来。',
  },
  compute: {
    headline: '',
    detail: '',
  },
  other: {
    label: '界面还不认识的降级',
    headline: '健康接口报了一格界面还不认识的降级',
    detail: '这一格的读法今天没接线，界面不猜它是什么。请把这一句原样报给运维，让它长出自己的那句话。',
  },
}

const simpleFace = (kind) => ({
  kind,
  label: FAMILY_FACES[kind].label || FAMILY_FACES[kind].headline,
  headline: FAMILY_FACES[kind].headline,
  detail: FAMILY_FACES[kind].detail,
})

/** 只读那一族：哪几格只读是后端名单说了算，界面只负责把名字念出来。 */
export function readOnlyFace(codesOrNames) {
  const list = (Array.isArray(codesOrNames) ? codesOrNames : []).map((item) => {
    const raw = String(item || '')
    return namedSubsystem(raw.endsWith('_read_only') ? raw.slice(0, -'_read_only'.length) : raw)
  }).filter(Boolean)
  const what = list.join('、')
  return {
    kind: 'readOnly',
    label: list.length ? `${what}只读` : '只读保护',
    headline: list.length ? `${what}跑在只读保护下` : '有子系统跑在只读保护下',
    detail: (list.length ? '受影响的格子：' + what + '。' : '')
      + '这几格没有落在持久存储上，正处在只读保护里：写进去的内容不保证留得住，重启就可能丢。请让管理员给这几格配上持久存储。',
  }
}

/**
 * 依赖状态名 → 人话。monitoring.py 今天只交出这三枚非 ok 值（同文件的 unavailable /
 * not_configured / degraded），名单外的新状态界面不照抄码名：屏上那一句是给人读的，
 * 裸码名在这仓里走的是另一条诊断通道（data-code / 「错误码：xxx」小字），V6 闸门钉着它。
 * 认不出来时也要开口说「这一格我还不认识」，不许闭嘴——闭嘴就又回到报绿。
 */
const DEPENDENCY_STATUS_TEXT = {
  unavailable: { label: '连不上', text: '这一刻连不上' },
  not_configured: { label: '没配置', text: '还没配置好，这项服务今天不可能应答' },
  degraded: { label: '应答降级', text: '能连上但应答降级' },
}

/** 依赖那一族：三枚依赖各是一张脸——主数据库坏了与模型服务坏了不是同一句话。 */
export function dependencyFaces(problems) {
  const out = []
  for (const code of (Array.isArray(problems) ? problems : [])) {
    const match = /^(postgres|redis|ollama)_(.+)$/.exec(String(code))
    if (!match) continue
    const name = namedDependency(match[1])
    const known = DEPENDENCY_STATUS_TEXT[match[2]] || null
    out.push({
      kind: 'dependency',
      id: String(code),
      label: `${name}${known ? known.label : '状态不认识'}`,
      headline: known
        ? `${name}${known.text}`
        : `${name}这一刻不对劲，而后端给的状态名不在界面认识的那几格里，界面不猜它是什么`,
      detail: FAMILY_FACES.dependency.detail,
    })
  }
  return out
}

/**
 * 算力那一格：它不住在 problems 里，住在 model 那节的降级码上。
 * 「没探过」与「探了但看不见设备」都是 unknown——那一格不是坏消息，界面不许把它说成故障，
 * 也不许借它宣布「加速正常」。只有后端真的记了一枚降级码，这张脸才有资格存在。
 */
export function computeFace(health) {
  if (!health || typeof health !== 'object') return null
  const code = String(health.computeErrorCode || '')
  if (!code) return null
  const kind = String(health.computeKind || '')
  if (kind && kind !== 'cpu') {
    return {
      kind: 'compute',
      label: '推理算力读数自相矛盾',
      headline: '后端给推理算力记了一枚降级码，可算力档位读到的不是那一个（档位：' + kind + '）',
      detail: '这两格是分开读的，界面不替它们圆场。请让管理员看一次本机模型探测那一段的日志。',
    }
  }
  const age = Number.isFinite(health.computeAgeSeconds) ? `（读数取自约 ${Math.round(health.computeAgeSeconds)} 秒前）` : ''
  return {
    kind: 'compute',
    label: '没走加速设备',
    headline: '这台机器的推理没走加速设备，落在 CPU 上' + age,
    detail: '回答会比较慢，长文档与出图更明显。这不是模型没装好，是这台机器没让推理用上加速卡：请让管理员核对显卡与驱动。',
  }
}

/**
 * 把一次健康读数摊成「这台机器现在有几张不对劲的脸」。
 * 模型权重那一格（problems 里那一枚）不在这里出现：它由面板上那条既有的「本机模型未就绪」
 * 提示条单独说（chat-model-status 那枚件钉着那条路径唯一），这里再说一遍就是同屏两句重复话。
 */
export function runtimeFaces(health) {
  if (!health || !Array.isArray(health.problems)) return []
  const problems = health.problems
  const faces = []
  const keys = new Set()
  const push = (face) => {
    if (!face) return
    const key = String(face.kind) + (face.id || '') + (face.headline || '')
    if (keys.has(key)) return
    keys.add(key)
    faces.push(face)
  }
  if (problems.includes(EMBEDDING_MODEL_MISSING)) push(simpleFace('embedding'))
  if (problems.includes(QUEUE_UNAVAILABLE)) push(simpleFace('queue'))
  if (problems.includes(USERS_STORE_NOT_PERSISTENT)) push(simpleFace('store'))
  const readOnly = problems.filter((code) => String(code).endsWith('_read_only'))
  if (readOnly.length) push(readOnlyFace(readOnly))
  for (const face of dependencyFaces(problems)) push(face)
  // 陌生码并成一行，但那一句必须报得出枚数：两格并成「一格」是假话，逐格画两句一模一样的
  // 话又是噪音——界面拿得出的人话只有「有几格我还不认识」这一枚信息。
  const unknown = problems.filter((code) => problemFamily(code) === 'other')
  if (unknown.length) {
    const face = simpleFace('other')
    push({
      ...face,
      id: 'other',
      headline: unknown.length === 1 ? face.headline : face.headline.replace('一格', `${unknown.length} 格`),
    })
  }
  push(computeFace(health))
  return faces
}

/**
 * ready / down / degraded / unknown —— 界面按这四档画那枚点与标签。
 * 第四档是 R268 补的：后端报了别的格子、唯独没报权重缺失，那一格既不是「权重没了」，
 * 更不是「一切都好」——画成绿点就是替客户制造「AI 正常」的错觉。
 */
export function modelState(health) {
  if (!health || !Array.isArray(health.problems)) return 'unknown'
  if (health.problems.includes(MODEL_NOT_AVAILABLE)) return 'down'
  if (health.problems.length) return 'degraded'
  // 权重在、problems 也空，但后端仍然给推理记了一枚降级码：这一格不许算绿。
  return computeFace(health) ? 'degraded' : 'ready'
}

export const MODEL_STATE_TEXT = {
  ready: '本地模型就绪',
  down: '本机模型未就绪',
  degraded: '本机服务降级',
  unknown: '模型状态未知',
}

/**
 * 顶栏那一枚短标签。降级时说的是「降级的是哪一格」，不是笼统一句红了：
 * 一张脸就念那一格的名字，多张脸就说枚数，界面不替后端把它们并成一句。
 */
export function modelStatusText(health) {
  const state = modelState(health)
  if (state !== 'degraded') return MODEL_STATE_TEXT[state]
  const faces = runtimeFaces(health)
  if (faces.length === 1) return `本机服务降级：${faces[0].label}`
  if (faces.length > 1) return `本机服务降级（${faces.length} 格）`
  return MODEL_STATE_TEXT.degraded
}
