/**
 * R150 · 业主计划 v2 §5「三张脸」的措辞与判定（纯函数，零 IO、零 DOM、零网络）
 *
 * 分工是一枚缺陷换来的：lib/sessions.js 负责【把帧读成事实】，本模块负责【把事实说成人话】，
 * ChatPanel.vue 只做接线。三处不合并，是为了让「后端报了但界面没说」这种缺陷有唯一归属：
 * 数字缺了找 sessions.js，句子不顺找本模块，元素没挂上找 ChatPanel。
 *
 * 三条硬口径：
 *  ① 「另有 N 处命中未展示」与「没检索到」是两句不同的话，分属两个 DOM 节点。私有化部署最
 *     常被追问的就是这一句：把「资料存在但不给你看」说成「没有资料」，等于替客户误判自己的库。
 *  ② 三态不许合并成一句「出错了」。每一态都给下一步（该换账号、该重问、该等资源），
 *     且下一步只说界面真能做到的事。
 *  ③ 句子出现的每一个时间都必须是从线上读回来的读数（缓存生成时间、版本入库时间）。本模块
 *     【不调 Date.now()】：改版提示一旦允许「现在」参与比较，就能凭空造出一个「已改版」。
 *
 * 码名纪律（V6 闸门 lib/no-bare-code.test.js）：给人看的句子零裸码名；码名只走对象键、
 * data-code 属性与 errcodes.js 的「错误码：xxx」小字通道。
 */
import { errorCodeLabel, errorText, normalizeError } from './errcodes'

/** 检索范围理由的两个合法取值（真源 app/rag/filters.py:92 / :109，用例逐枚对账）。 */
export const SCOPE_REASON_TEXT = {
  administrator_scope: '本账号可见范围覆盖全库（管理级）',
  department_scope: '本账号只在本部门与授权密级范围内可见',
}

/**
 * 版本行的时间列只有一个真源：document_versions.created_at（app/documents/catalog.py:36 的
 * _SELECT_COLUMNS、:469 的建表语句、:521 的写入点）。上传/发布之类别的列名今天不存在，
 * 不替后端提前发明键名——读不到时间就明说「无从核对」，比拿一个猜来的键装作量到了强。
 */
const VERSION_TIME_KEYS = ['created_at']

function textOf(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function countOf(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= 0 ? Math.trunc(parsed) : 0
}

/** ISO 时间 → 「09-21 20:31」；读不出来的串一律空串，绝不用「现在」兜底。 */
export function formatMoment(value) {
  const raw = textOf(value)
  if (!raw) return ''
  const stamp = Date.parse(raw)
  if (!Number.isFinite(stamp)) return ''
  const date = new Date(stamp)
  const pad = part => String(part).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/**
 * ISO 时间 → 「2026-03-01」（只到日，带年份）。
 *
 * 与 formatMoment 分开是有意：改版那句要的是「比答案晚几分钟」，月份加钟点够了；而制度的
 * 【生效日期】是按年说话的，画成「03-01」会让客户分不清 2026 年还是 2025 年版。
 * 读不出来一律空串，绝不用「今天」兜底。
 */
export function formatDayStamp(value) {
  const raw = textOf(value)
  if (!raw) return ''
  const stamp = Date.parse(raw)
  if (!Number.isFinite(stamp)) return ''
  const date = new Date(stamp)
  const pad = part => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** 取一版记录里能读到的时间；一枚都没有就回空串（调用方据此说「无法核对」）。 */
export function versionMoment(row) {
  if (!row || typeof row !== 'object') return ''
  for (const key of VERSION_TIME_KEYS) {
    const value = textOf(row[key])
    if (value) return value
  }
  return ''
}

// ==================== 出处那张脸 ====================

/**
 * sources 帧 → 卡片模型。null＝本轮后端没交出处事件（不是「没检索到」，两件事必须分得开）。
 *
 * rows 与 hit_count 是同一条 len() 的两侧（chat.py:1557），一旦不相等说明线上出了我们没见过的
 * 形状：这里以能画出来的行为准，并把差值如实写进 diagnostics，不静默取其一。
 */
export function sourcesFace(sources) {
  if (!sources || typeof sources !== 'object') return null
  const rows = Array.isArray(sources.rows) ? sources.rows : []
  const visible = rows.length
  const hidden = countOf(sources.hiddenCount)
  const declared = Number.isFinite(Number(sources.hitCount)) ? countOf(sources.hitCount) : visible
  const reasonCode = textOf(sources.scopeReasonCode)
  const scopeError = SCOPE_REASON_TEXT[reasonCode] === undefined && reasonCode ? normalizeError({ detail: reasonCode }) : null

  const diagnostics = []
  if (declared !== visible) diagnostics.push(`出处条数与行数不一致（读出 ${declared}，可画 ${visible}）`)

  const base = { rows, visible, hidden, reasonCode, diagnostics }
  if (visible === 0 && hidden === 0 && scopeError) {
    return {
      ...base,
      kind: 'scope-error',
      tone: 'danger',
      headline: '本轮未能按你的权限范围做文档检索',
      reason: scopeError.message,
      hiddenLine: '',
      searchable: false,
    }
  }
  if (visible === 0 && hidden === 0) {
    return {
      ...base,
      kind: 'none',
      tone: 'muted',
      headline: '本轮没有检索到可用文档',
      reason: '下面的回答不来自知识库。要按制度或既有资料回答，请先确认文档已上传并解析完成，再重新提问。',
      hiddenLine: '',
      searchable: false,
    }
  }
  if (visible === 0 && hidden > 0) {
    return {
      ...base,
      kind: 'all-hidden',
      tone: 'warn',
      headline: `检索到 ${hidden} 处命中，但都不在你当前的可见范围内`,
      reason: '这不是「库里没有」：资料在，只是按部门与密级对你不可见。请换有权限的账号，或请管理员核对这份资料的授权范围。',
      hiddenLine: `另有 ${hidden} 处命中未展示`,
      searchable: false,
    }
  }
  return {
    ...base,
    kind: 'visible',
    tone: 'ok',
    headline: `本轮回答引用了 ${visible} 处资料`,
    reason: visible === 1 ? '只有这一处命中，点开可回原文核对。' : '按命中名次排列，点开任意一条回原文核对。',
    hiddenLine: hidden > 0 ? `另有 ${hidden} 处命中未展示` : '',
    searchable: true,
  }
}

/** 密级：整数级直接说级，不替客户发明名字（3 级在后端同时对应两枚名字，猜必错）。 */
export function classificationLabel(value) {
  const raw = textOf(value)
  if (!raw) return ''
  return Number.isFinite(Number(raw)) ? `密级 ${Number(raw)} 级` : raw
}

/**
 * 相关度：后端报的是重排名次分时，不许写成百分比（score_type 真源 app/agents/evidence.py:82）。
 *
 * 空值必须先原样退回：`Number(null)` 与 `Number('')` 都是 0，直接进 Number() 会把「后端没给分」
 * 印成「相关度 0」——那是最低分，是一句编出来的读数，比不印更坏。lib/sessions.js 对缺分的行
 * 明确给的是 null，这一格吃的就是它。
 */
export function scoreLabel(row) {
  const raw = row?.score
  if (raw === null || raw === undefined || raw === '') return ''
  const score = Number(raw)
  if (!Number.isFinite(score)) return ''
  const fixed = score.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')
  return row?.scoreType === 'rerank' ? `相关度 ${fixed}（重排分）` : `相关度 ${fixed}`
}

// ==================== 缓存那张脸 ====================

/**
 * 版本历史里晚于答案生成时间的每一版。
 *
 * 返回 null＝【判断不了】（答案没带生成时间，或这一枚文件压根没有时间读数）。
 * null 与 [] 不是一回事：[] 是「查过了，确实没改版」，null 是「无从判断」。把两者合并成
 * 一句「已改版」或一句「无变化」，就是把取证当成了表态。
 */
export function revisionsAfter(sinceIso, rows) {
  const since = Date.parse(textOf(sinceIso))
  if (!Number.isFinite(since)) return null
  // 压根没拿到数组 != 拿到了一个空数组：前者是「没查成」，后者才是「查过了，没有晚于它的版本」。
  // 把 undefined 当成 [] 用，就是接口返回形状一变，界面立刻宣布「没有改版」。
  if (!Array.isArray(rows)) return null
  const newer = []
  for (const row of rows) {
    const moment = versionMoment(row)
    const stamp = Date.parse(moment)
    // 有一版读不出时间，整份核对就作废：跳过它继续算，等于把「查不动」说成「查过了没改版」。
    if (!Number.isFinite(stamp)) return null
    if (stamp > since) newer.push({ version: row?.version ?? null, moment })
  }
  return newer
}

/**
 * cache 帧 + 逐文件改版读数 → 三态。staleness 为 undefined＝还没查（第一帧先画前两种态）。
 *
 * 时间一律来自后端：note 与 generatedAt 出自 chat.py:1307-1311，版本时间出自
 * GET /documents/{filename}/versions。界面不自己造时间。
 */
export function cacheFace(cache, staleness) {
  if (!cache || typeof cache !== 'object') return null
  if (cache.cached !== true) {
    // 未命中这一态只说给【当场看到的轮次】：observed 由 lib/sessions.js 在续上正文那一刻写下。
    // 老消息复原时整格都没有，界面就别说这一态——把缺席当证据正是这一族缺陷的母形状。
    if (cache.observed !== true) return null
    // 句子把证据一起说出来：万一哪天命中路径漏发那三枚，这句会跟着一起变谎，写在脸上才复查得动。
    return {
      kind: 'live',
      headline: '本轮实时生成',
      detail: '这一轮的回答帧当场看着生成，没有带回缓存读数。',
      tone: 'muted',
    }
  }
  const note = textOf(cache.note)
  const moment = formatMoment(cache.generatedAt)
  const born = note || (moment ? `缓存结果 · 生成于 ${moment}` : '缓存结果 · 生成时间未知')
  if (staleness === undefined) {
    return { kind: 'cached', headline: born, detail: '正在核对来源文件是否已经改版。', tone: 'info' }
  }
  const stale = (Array.isArray(staleness) ? staleness : []).filter(item => item?.revisions?.length)
  if (staleness === null || !Array.isArray(staleness)) {
    return {
      kind: 'cached-unknown',
      headline: born,
      detail: '这一轮的回答没有再交出来源清单，是否改版无从核对。要看最新资料下的结论，请改动问题里的任一措辞重新提问。',
      tone: 'warn',
    }
  }
  if (!stale.length) {
    return { kind: 'cached', headline: born, detail: '已核对来源文件：自那次生成以来没有新版本入库。', tone: 'info' }
  }
  const detail = stale
    .map(item => `${item.filename} 在 ${formatMoment(item.latestMoment) || '（时间读数缺失）'} 又入库了第 ${item.latestVersion ?? '?'} 版`)
    .join('；')
  return {
    kind: 'cached-stale',
    headline: `${born}，但来源已改版`,
    detail: `${detail}。这份回答用的是旧版内容，需要按新版重算时请改动问题里的任一措辞重新提问。`,
    tone: 'warn',
  }
}

// ==================== 排队那张脸 ====================

/**
 * 排队帧 + /queue/status 读数 → 三态，且失败态各说各的话。
 *
 * 真机读数范围（app/api/v1/chat.py:2930-3003 与 app/common/reliable_queue.py）：状态只有
 * queued / processing / done / cancelled / failed，键过期时接口另给 expired；位次 position
 * 是 1 起的队内序号，取不到时为 null。今天的后端【没有任何「队列长度上限」读数】，
 * 所以「排不下」这一态只能来自入队请求本身被拒（HTTP 503 的 queue_unavailable），
 * 界面不许自己按排队人数编一个「已满」。
 */
export function queueFace(queue) {
  if (!queue || typeof queue !== 'object') {
    return { kind: 'idle', headline: '', detail: '', tone: 'muted', ahead: null }
  }
  const status = textOf(queue.status) || 'queued'
  if (status === 'queued') {
    const position = Number.isFinite(Number(queue.position)) && Number(queue.position) > 0
      ? Math.trunc(Number(queue.position))
      : null
    return {
      kind: 'queued',
      headline: position === null
        ? '本轮已转入后台排队，暂时读不到你前面有几个人'
        : `本轮已转入后台排队，前面还有 ${position - 1} 人`,
      detail: position === null
        ? '位次读数来自队列快照，取不到时不猜数字；跑完会自动接上结果。'
        : '可以先看别的问题，跑完这一轮结果会回到本会话。排队期间随时可以中断。',
      tone: 'info',
      ahead: position === null ? null : position - 1,
    }
  }
  if (status === 'processing') {
    return { kind: 'processing', headline: '轮到你了，正在后台生成', detail: '跑完之后界面会从状态读数里把答案补回这条回答。', tone: 'info', ahead: 0 }
  }
  if (status === 'done') {
    // 「跑完了」与「结果取回来了」是两件事：done 分支的 result 出自 chat.py:2948-2954，
    // 空串 / null 都说不上答案，不能借一个 done 就宣布界面上有答案。
    if (!textOf(queue.result)) {
      return {
        kind: 'done-no-result',
        headline: '后端说这一轮跑完了，但读数里没带回答案',
        detail: '状态读数里的 result 是空的，界面没有答案可显示。请重新提问；每次都停在这里请让管理员查后台任务。',
        tone: 'warn',
        ahead: 0,
      }
    }
    return {
      kind: 'done',
      headline: '这一轮后台跑完了，答案取自排队状态读数',
      detail: '这一轮界面没有实时流，正文来自排队状态读数里的 result 字段，已补进这条回答。',
      tone: 'ok',
      ahead: 0,
    }
  }
  if (status === 'cancelled') {
    return { kind: 'cancelled', headline: '这一轮排队任务已取消', detail: '需要结果的话请重新提问。', tone: 'muted', ahead: null }
  }
  if (status === 'expired') {
    return {
      kind: 'expired',
      headline: '这一轮排队记录已过期，取不到结果了',
      detail: '队列只保留一段时间的回执。请重新提问；如果每次都停在过期，说明后台 worker 没有跑起来，需要管理员查服务。',
      tone: 'warn',
      ahead: null,
    }
  }
  // failed 与后端给的其它状态：一句「出错了」不算交代，必须带上第几次尝试与归类后的原因。
  const failure = queue.failure && typeof queue.failure === 'object' ? queue.failure : null
  const attempts = failure ? countOf(failure.attempts) : 0
  const maxAttempts = failure ? countOf(failure.max_attempts) : 0
  const reason = failure && textOf(failure.last_error) ? asErrorResult({ detail: String(failure.last_error) }) : null
  const tried = attempts && maxAttempts ? `已尝试 ${attempts}/${maxAttempts} 次仍失败。` : attempts ? `已尝试 ${attempts} 次仍失败。` : ''
  return {
    kind: 'failed',
    headline: '这一轮在后台执行失败，没有产出答案',
    detail: `${tried}${reason ? reason.message : '请稍后重试；连续失败请让管理员查看后台任务与模型服务。'}`,
    tone: 'danger',
    ahead: null,
  }
}

/**
 * 这条小字只在【已经归一过一次】的错误结果上成立，所以先认形状再决定要不要归一。
 *
 * 为什么要这一层守卫：normalizeError 对自己刚产出的成品并不幂等——code 是已知枚举时走
 * fromEnvelope 能原样回来，但 code 为空串那种（未知码 / 只有中文的失败）再过一遍会把 rawCode
 * 洗成空串，于是「错误码：xxx」这条小字静默消失。lib/sessions.js 的 http_error 分支已经归一过
 * 一次，这里再归一次就是丢字。r150 用例把「成品」与「原料」两种输入各钉一条，防的就是这个形状。
 */
function asErrorResult(input) {
  const shaped = input && typeof input === 'object'
  if (shaped && typeof input.code === 'string' && typeof input.rawCode === 'string'
    && typeof input.retryable === 'boolean' && typeof input.message === 'string') {
    return input
  }
  return normalizeError(input)
}

/** 入队这一步就失败（HTTP 503 等）：连队都没排上，不能画成「排队中」。 */
export function queueRejectedFace(error) {
  const result = asErrorResult(error)
  return {
    kind: 'rejected',
    headline: '这一轮没能排上队，也没有实时生成',
    detail: result.message,
    // 「错误码：xxx」这条小字全仓只有一个合法生产者：errcodes.errorCodeLabel()。
    // 自己拼 ${result.rawCode} 就是第二套口径，V6 裸码闸门的 interp 判据第一个咬它。
    codeLabel: errorCodeLabel(result),
    tone: 'danger',
    retryable: result.retryable,
    ahead: null,
  }
}

/**
 * 排队读数这一次没取回来（轮询本身失败）：这既不是「排队中」也不是「执行失败」，不能说谎。
 * 界面继续按点重试，读数恢复前不猜前面有几个人。
 */
export function queuePollFailedFace(error) {
  const result = asErrorResult(error)
  return {
    kind: 'unreadable',
    headline: '这一轮已经排上队，但排队状态这次没读到',
    detail: `${result.message}界面每 3 秒再读一次状态，读数回来之前不猜你前面有几个人。`,
    codeLabel: errorCodeLabel(result),
    tone: 'warn',
    retryable: result.retryable,
    ahead: null,
  }
}

/** 全局排队人数（GET /queue/stats）：只用于「前面 N 人」之外的补充交代，读不到就不说。 */
export function queueStatsFace(stats) {
  const length = Number(stats?.queue_length)
  const processing = Number(stats?.processing)
  if (!Number.isFinite(length) && !Number.isFinite(processing)) return null
  const waiting = Number.isFinite(length) ? Math.trunc(length) : 0
  const running = Number.isFinite(processing) ? Math.trunc(processing) : 0
  return { waiting, running, headline: `队列现状：等待 ${waiting} 个 · 正在跑 ${running} 个` }
}

/** 三张脸的字典查询出口（用例与诊断区共用，避免第二处抄写）。 */
export function scopeReasonText(code) {
  const raw = textOf(code)
  return SCOPE_REASON_TEXT[raw] || errorText(raw)
}