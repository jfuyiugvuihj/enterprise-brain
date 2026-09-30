/**
 * R333 · 通知中心唯一的读写出路（判据①②③④⑤在这一层收口）
 *
 * 后端早就有出口（app/api/v1/notifications.py 的三条路由，契约见 docs/api/contract-v1.md 的
 * R299 一节），前端今天零引用。这一枚文件是它与界面之间唯一的一条路：
 *   判据② 请求只走 lib/http.js 那枚共享 axios 实例 —— 本文件不 import axios、不写 fetch、
 *          不拼 /api/v1 前缀（baseURL 与 Bearer 都由那一层给），参数一律走 params；
 *   判据① 未读数只认后端交回的全集口径 unread_total，本页长度在本层就地丢掉，组件拿不到；
 *   判据③ 失败句子只出自 lib/errcodes.js 的词典（手法与 HitlPendingPanel.vue 同一套：
 *          本层只决定「字典没话说时退到哪一句场景话」，码名走 errorCodeLabel 的独立通道）；
 *   判据④ 一次写超过 50 枚在前端切批，回执逐枚核对，一枚都不许静默丢；
 *   判据⑤ 没有本地未读副本、没有第二本账：一次动作之后的新数字来自【再读一次后端】，
 *          本层不提供也不许任何人用 unread - changed 那种自己算的减法。
 *
 * 四条口径逐条对着契约抄，不猜：
 *   · returned / unread_returned 是【本页】长度，total / unread_total 是【全集】总数。
 *     R278 当年摘掉那枚铃铛，理由是「今天没有一句诚实的条数可摆」——那说的是只有页内长度。
 *   · is_exact=false 时两个总数都只是下界，屏上说的是「至少这么多」，不是「正好这么多」。
 *   · 未读总数那一格缺失或不是数 = 读不到，抛形状错；绝不回落成 0（0 会说「没有未读」）。
 *   · changed=false 是「这一次没改变结论」（第 N 次点、或本来就是这个状态），不是失败。
 */
import { errorDetail, http, PERMISSION_DENIED } from './http'
import { errorCodeLabel, errorCodeOf } from './errcodes'
import { failureRetryable, formatStamp, readFailureView, SHAPE_FAILURE_DESCRIPTION } from './alerts'

/** 三条路由：一条读，两条写（notifications.py:187 / :212 / :218）。 */
export const INBOX_PATH = '/notifications'
export const READ_ACTION_PATH = '/notifications/read'
export const DISMISS_ACTION_PATH = '/notifications/dismiss'

/** 与后端 notifications.py::MAX_IDS_PER_CALL 同值；对平由 r333 用例钉住，不靠注释。 */
export const MAX_IDS_PER_CALL = 50

/** 与后端 inbox.py::MAX_LIMIT 同值：一次读 100 行；默认 20 行不够一屏看。 */
export const INBOX_PAGE_LIMIT = 100

/** 读过滤值（inbox.py::STATE_FILTERS 的三枚）；划掉不是过滤值，喂给它后端回 422。 */
export const UNREAD_FILTER = 'unread'
export const ALL_FILTER = 'all'

/** 回执里「这一枚我管不着」的稳定码（后端 NOT_ADDRESSABLE 同值）：只用来判脸，绝不上屏。 */
export const NOT_ADDRESSABLE = 'notification_not_addressable'

/** 「全部标已读」要逐页收 id：收不完就说谎，所以这里有一枚安全阀，撞顶即抛错。 */
export const MAX_COLLECTION_PAGES = 20

export const READ_FAILED_TITLE = '通知没能读出来'
export const READ_DENIED_TITLE = '这个账号读不到通知'
export const STORAGE_TITLE = '通知表还没就绪'
/** 一次「标已读 / 划掉」没成时的那句场景话：说的是动作没成，不是「没有通知」。 */
export const WRITE_FAILED_FALLBACK = '这次动作没能改成，通知的条数以重新读取的结果为准。'
export const STORAGE_DESCRIPTION = '这一格要数据库迁移跑过才有内容，现在一条都读不出来。'
  + '请让管理员确认迁移是否执行 —— 这不是「没有未读通知」，也不是在这里多点一次就能变好的事。'

/** 本资源今天发不出 403（契约 R299 明写「deliberately no 403」）。这张脸留着不为今天，
 *  是为归属哪天改动时不许把「读不到」顺手提成「没有通知」——与 HitlPendingPanel 同一条纪律。 */
export const DENIED_WHERE = '这一格读不到不一定是「没有」：通知是那三本账的投影，能看到哪几枚由那三本账自己的读路径裁定，'
  + '请让企业管理员核对账号权限后重新读取；重新登录本身不会让这项权限出现。'

/** 服务端回来的形状对不上：这句话说的是「读不到」，不是「没有」。 */
export class InboxShapeError extends Error {}

function shapeFailure(message) {
  const error = new InboxShapeError(message)
  error.shapeFailure = true
  return error
}

export function isShapeFailure(err) {
  return err instanceof InboxShapeError || Boolean(err && err.shapeFailure === true)
}

const text = (value) => (value == null ? '' : String(value))

/**
 * 计数只认「非负有限数」。缺失 / null / 字符串 / 负数 / NaN 一律算读不到（交回 null），
 * 而不是顺手当 0 —— 0 是一张会说「没有未读」的脸，读不到不许冒充它（判据③）。
 */
export function countOrUnknown(value) {
  const num = typeof value === 'number' ? value : NaN
  if (!Number.isFinite(num) || num < 0) return null
  return Math.floor(num)
}

/** 账本一行 -> 视图行。后端字段名只在这一个函数里出现，模板只认驼峰视图字段。 */
export function mapRow(row) {
  const source = row && typeof row === 'object' ? row : {}
  const state = text(source.state)
  return {
    id: text(source.id),
    sourceType: text(source.source_type),
    sourceId: text(source.source_id),
    title: text(source.title) || '（这一枚没给标题）',
    detail: text(source.detail),
    createdAt: formatStamp(source.created_at),
    state,
    read: state === 'read',
  }
}

/**
 * 收件箱响应的唯一解析出口。
 *
 * 刻意【不向上交】returned / unread_returned 那一类本页长度：判据①要的是「徽标只可能来自
 * 全集口径」，把本页条数递进组件就是给它一次用错的机会。翻页只靠 has_more 与 offset。
 */
export function normalizeInbox(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw shapeFailure('服务端没把收件箱交回来：这一格现在是未知，不是空。')
  }
  if (!Array.isArray(payload.notifications)) {
    throw shapeFailure('服务端交回的收件箱列表形状不对：这一格现在是未知，不是空。')
  }
  const unread = countOrUnknown(payload.unread_total)
  if (unread === null) throw shapeFailure('服务端没交回全集未读总数：这一格现在是未知，不是零。')
  const total = countOrUnknown(payload.total)
  if (total === null) throw shapeFailure('服务端没交回全集总条数：这一格现在是未知，不是零。')
  return {
    rows: payload.notifications.map(mapRow),
    // 全集未读：这一枚数字是徽标唯一可能的出处。
    unread,
    total,
    // 候选窗口裁过任何一本账，上面两个数就只是下界；这一格没给一律按不精确说话（fail-closed）。
    isExact: payload.is_exact === true,
    hasMore: payload.has_more === true,
    state: text(payload.state),
    limit: countOrUnknown(payload.limit),
    offset: countOrUnknown(payload.offset),
  }
}

/** 读一页收件箱。 */
export async function readInbox({ state = ALL_FILTER, limit = INBOX_PAGE_LIMIT, offset = 0 } = {}) {
  const response = await http.get(INBOX_PATH, { params: { state, limit, offset } })
  return normalizeInbox(response && response.data)
}

/**
 * 去重 + 切批（判据④）。三句硬话：
 *   ① 重复 id 先收敛成一枚（同一枚再点一次本就幂等，没必要发第二遍）；
 *   ② 每批不超过 size，size 默认取后端那道上界；
 *   ③ 批次摊平后必须与去重后的清单逐枚同序相等 —— 谁在这儿写「取前 50 枚、其余下次再说」，
 *      r333「一枚都不许丢」那枚用例当场红。
 */
export function chunkIds(ids, size = MAX_IDS_PER_CALL) {
  const width = Number.isInteger(size) && size > 0 ? size : MAX_IDS_PER_CALL
  const seen = new Set()
  const unique = []
  for (const item of Array.isArray(ids) ? ids : []) {
    const id = text(item).trim()
    if (!id || seen.has(id)) continue
    seen.add(id)
    unique.push(id)
  }
  const batches = []
  for (let at = 0; at < unique.length; at += width) batches.push(unique.slice(at, at + width))
  return batches
}

/**
 * 一次写的回执 -> 视图。只认逐枚 results，不信外层那个批内计数：
 * 一次动作可能被切成几批，外层计数是【每批】的，聚合它等于在前端再记一遍账。
 *   changed=true   这一次真的动了它（第一次点）；
 *   changed=false  结论没变（第 N 次点，或它本来就是这个状态）——不是失败；
 *   refused=true   对不上号或不是你的，与「不存在」同一张脸，这里不解释也不上屏。
 */
export function normalizeReceipt(payload, requestedIds) {
  if (!payload || typeof payload !== 'object' || !Array.isArray(payload.results)) {
    throw shapeFailure('服务端没交回这次动作的逐枚回执，不能算完成。')
  }
  const wanted = Array.isArray(requestedIds) ? requestedIds : []
  const byId = new Map()
  for (const item of payload.results) {
    if (!item || typeof item !== 'object') continue
    const id = text(item.id)
    if (id && !byId.has(id)) byId.set(id, item)
  }
  const missing = wanted.filter(id => !byId.has(id))
  if (missing.length) throw shapeFailure('回执少了 ' + missing.length + ' 枚，这次动作不能算完成。')
  const results = wanted.map(id => {
    const item = byId.get(id)
    return {
      id,
      state: item.state == null ? '' : text(item.state),
      changed: item.changed === true,
      refused: text(item.reason) === NOT_ADDRESSABLE,
    }
  })
  return summarize(results)
}

function summarize(results) {
  return {
    requested: results.length,
    changed: results.filter(row => row.changed).length,
    refused: results.filter(row => row.refused).length,
    results,
  }
}

/**
 * 把一份清单按不超过 50 枚切开发出去，逐枚回执拼成一份总回执。
 *
 * 空清单一发都不发：后端对空 ids 回 422（notifications.py::_ids_from_body），
 * 发出去就是把「没东西可标」自己造成一次失败。
 * 任何一批失败就地抛出、后面的批不再发：调用方画失败脸，绝不把半截成功说成全部完成。
 */
export async function applyAction(path, ids) {
  const batches = chunkIds(ids)
  if (!batches.length) return summarize([])
  const results = []
  for (const batch of batches) {
    const response = await http.post(path, { ids: batch })
    results.push(...normalizeReceipt(response && response.data, batch).results)
  }
  const receipt = summarize(results)
  receipt.batches = batches.length
  return receipt
}

export function markRead(ids) {
  return applyAction(READ_ACTION_PATH, ids)
}

export function dismissNotifications(ids) {
  return applyAction(DISMISS_ACTION_PATH, ids)
}

/**
 * 「全部标已读」的 id 从哪儿来：向后端逐页要 state=unread 的清单，不是从组件里那几行抄。
 *
 * 两条不许：
 *   · 只把【当前这一页】的未读当成「全部」；后端说还有更多却没给行，同样不许蒙混；
 *   · 撞到翻页上限还没收完就抛错 —— 「没收完」画成「已读完」是一句假话。
 */
export async function collectUnreadIds() {
  const ids = []
  let offset = 0
  for (let page = 0; page < MAX_COLLECTION_PAGES; page += 1) {
    const inbox = await readInbox({ state: UNREAD_FILTER, offset })
    if (!inbox.rows.length) {
      if (inbox.hasMore) throw shapeFailure('未读清单还没读完就不给行了，这不能当成全部已读。')
      return ids
    }
    for (const row of inbox.rows) ids.push(row.id)
    offset += inbox.rows.length
    if (!inbox.hasMore) return ids
  }
  throw shapeFailure('未读清单超出翻页上限，这不能当成全部已读。')
}

export async function markAllUnread() {
  const ids = await collectUnreadIds()
  return applyAction(READ_ACTION_PATH, ids)
}

/**
 * 一次读取失败 -> 一张卡。四档脸互不顶替（判据③），差别全在字段里：
 *   storage       表没就绪：句子出自词典，不给重试（重试不会把迁移跑出来）
 *   unauthorized  登录失效：同一句词典话，回登录由 lib/http.js 统一收尾
 *   denied        没权限：说清去哪问，不给重试
 *   error         真坏了 / 连不上：给「重新加载」
 * 本层只补「哪件事没做成」这一层场景话，人话位归词典。
 */
export function readFailureViewOf(err) {
  const code = errorCodeOf(err)
  if (code === 'storage_unavailable') {
    return { face: 'storage', title: STORAGE_TITLE, description: errorDetail(err, STORAGE_DESCRIPTION), codeLabel: '', retryable: false }
  }
  if (code === PERMISSION_DENIED) {
    return {
      face: 'denied',
      title: READ_DENIED_TITLE,
      description: errorDetail(err, READ_DENIED_TITLE) + DENIED_WHERE,
      codeLabel: errorCodeLabel(err),
      retryable: false,
    }
  }
  return readFailureView(err, { deniedTitle: READ_DENIED_TITLE, failedTitle: READ_FAILED_TITLE })
}

/** 形状不合：没有错误对象可归码，按「坏了」给重试，绝不画成空态（句子取自 lib/alerts.js 那一真源）。 */
export function shapeFailureViewOf() {
  return { face: 'error', title: READ_FAILED_TITLE, description: SHAPE_FAILURE_DESCRIPTION, codeLabel: '', retryable: true }
}

/**
 * 一次写失败的人话：同样只出自词典，只是说的不是「读不到」而是「这次动作没成」。
 * retryable 同出一把尺（R375 判据①）：吃 lib/alerts.js 那一枚 failureRetryable，本层不自判码、
 * 不再硬编 true —— 503 storage_unavailable 这种「跑完迁移才会变」的失败，点多少次都是同一枚 503。
 */
export function writeFailureView(err, fallback = WRITE_FAILED_FALLBACK) {
  return { title: '这次动作没能改成', description: errorDetail(err, fallback), codeLabel: errorCodeLabel(err), retryable: failureRetryable(err) }
}

/**
 * 徽标与面板标题的唯一文案出口（判据①③⑦）：一句话只有一处写法，两处画的是同一句。
 *
 * 数字只可能来自 normalizeInbox() 的全集未读；null 是「还没读到 / 读失败」，
 * 那一档既不画数字，也不说「没有未读」，更不许拿 0 冒充未知（判据③的最后一格）。
 * isExact=false 说的是「至少」：候选窗口裁过的那两个总数本来就是下界（契约 R299 那张表）。
 */
function unreadPhrase(unread, { isExact = true, failed = false } = {}) {
  if (failed) return '没能读出来'
  const count = countOrUnknown(unread)
  if (count === null) return '未读数还没读出来'
  if (count <= 0) return '没有未读通知'
  return (isExact ? '' : '至少 ') + count + ' 条未读通知'
}

/** 读屏念出来的那一句：未读数要有可读表达，不许是孤零零一个数字（判据⑦）。 */
export function bellLabel(unread, { isExact = true, failed = false } = {}) {
  if (failed) return '通知没能读出来，打开可以看到原因'
  return '通知，' + unreadPhrase(unread, { isExact, failed })
}

export function badgeText(unread, { isExact = true } = {}) {
  const count = countOrUnknown(unread)
  if (count === null || count <= 0) return ''
  return isExact ? String(count) : String(count) + '+'
}

export function panelSummary(inbox) {
  if (!inbox) return ''
  return unreadPhrase(inbox.unread, { isExact: inbox.isExact })
}
