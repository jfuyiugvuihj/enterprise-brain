<script>
/**
 * HitlPendingPanel —— 「挂起待办」那一块（R168）
 *
 * 一句话：智能体停下来等确认的那件事，今天只画在对话流里（ChatPanel 的那张卡片），一滚屏就找不着。
 * 这块把「我手头有几件要办的事、办完回哪儿去」抽成一屏。数据只有一个来源：
 *   GET  /hitl/pending   挂起账本（app/api/v1/chat.py:2294；契约 docs/api/contract-v1.md
 *                        的 HITL Pending Listing 一节）
 * 写操作也只有一个出口：
 *   POST /approve        body 恰为 { session_id, approved }，回来的是一条 SSE 流（chat.py:2415）
 *
 * 字段逐条照契约抄，不猜：items[].{session_id, owner_user_id, parked_steps, labels, status,
 * created_at, expires_at, request_id, trace_id, task_id}，外层 {items, count, limit, offset, has_more}。
 * count 是「过滤后的长度」，契约明写不得当总数用 —— 所以这一屏不摆「待办 N 条」那种数字，
 * 只如实说这一页取了最近多少笔、账本里还有没有更早的。
 *
 * R175 起同一份响应里还有第二格：failed_turns[] + failed_turns_has_more。它装的是
 * 「员工批过板、而那一轮被系统跑挂了」的那几行账（app/storage/pending_approvals.py 的
 * FAILED）。这一格与待办是两件事，画法也必须是两件事：
 *   · 它【不进】items，所以不会被列成一条新的待办，也不带批准/驳回按钮 ——
 *     后端闭合那一行之后，图很可能还挂在同一个中断上，再点一次就是让同一轮 resume 第二遍；
 *   · 它【不进】复核循环：check_interrupt 问「还挂着吗」，答案必然是「没挂着」，
 *     走那条腿就会被就地判成 stale，于是「你批过而那一轮失败了」在屏上变成「已作废」；
 *   · 它【不许】被画成「已拒绝」，也不许被画成「已完成」—— 账上那一格叫 failed，
 *     三句里它是唯一一句真话。
 *
 * 四张脸互不冒充（判据①，看板 G4 口径）：
 *   loading      进页面先「在读」—— 还没读过账本就说「没有待办」是句假话，所以它优先于一切。
 *   失败         UiErrorState（role=alert）：没权限 / 没登录 / 账本没就绪 / 真坏了，四句话各不相同。
 *   200 空 items UiEmptyState（role=status）：真的没有挂着的事。
 *   200 有行     列表，一行就是账本里的一笔。
 *   无权限与空列表是两条不可能互相顶替的路径：失败只可能来自 catch，200 空数组走不到 catch。
 *   备注（诚实记账）：/hitl/pending 今天不会回 403 —— 它对 anonymous 回 401、对别人的会话回 404
 *   而不是 403（chat.py:583-587 的「读不到就像不存在」惯例），归属靠 owner 过滤 fail-closed。
 *   403 那张脸照样留着：哪天归属换成分层权限，这一屏不许把它悄悄画成「暂无待办」。
 *
 * 位阶最高的一条（判据③）：行只可能来自真响应。没有真 pending 就留空态，不造演示行、
 * 不拿历史会话冒充待办、读失败时也不清成一张「看起来像待办」的表。落成了三条硬约束：
 *   ① rows 的每次赋值要么来自 items.map(mapPendingRow)，要么是 []；
 *   ② 演示常量目录在本文件一次都不 import，也没有任何写死的行；
 *   ③ 失败路径先清 rows 再画 failure，而 pendingFace 里 failure 排在 rowCount 之前。
 *
 * 判据④（R168 那一半，一行未动）：switchSession 拿不到那个 id 时会就地新建一份同名空会话，
 * 那是伪造历史，canReplayTurn() 就是把这道门的，绝不让它有机会被踩。
 *
 * R174 判据②改的是这道门的【判据】，不是这道门：能不能回看从今天起由【后端】说了算 ——
 * GET /sessions 返回的就是「这个账号在后端还留着哪些会话」（chat.py::list_sessions 已按归属
 * 过滤，app/storage/sessions.py:85 的 is_owned_by 是唯一那道闸）。旧口径判的是这台浏览器的
 * 会话历史，于是员工把链接发给同事、同事换台机器打开就说「没有可回看的对话」——那句话是假的，
 * 正文明明在服务端。本机那份历史从此只当【对照】用：后端没有而本机有，另说一句
 * REPLAY_LOCAL_ONLY，不与「真的没有」并成一格。
 */
import { errorDetail } from '../../lib/http'
import { errorCodeLabel, errorCodeOf, errorText, normalizeError } from '../../lib/errcodes'
import { formatStamp, readFailureView, SHAPE_FAILURE_DESCRIPTION } from '../../lib/alerts'
// SESSION_READ 在普通 <script> 块里 import 一次就够了：两个块同属一个模块作用域。
import { SESSION_READ } from '../../lib/sessions'
// rowLabels / shortId 住在那一枚文件里：动作名与长 id 的说法全站只有一份，这里不抄第二份。
import { REPLAY_LOCAL_ONLY, REPLAY_NONE, rowLabels, shortId } from './HitlPendingRow.vue'

export default { name: 'HitlPendingPanel' }

/** 读取端点与一页取多少笔：后端默认 50、硬上限 200（chat.py 的 DEFAULT/MAX_PENDING_LIMIT）。 */
export const PENDING_PATH = '/hitl/pending'
export const PENDING_PAGE_SIZE = 50

/** 批准与驳回共用同一个 resolver，只有 approved 分真假（契约 R11：被驳回的动作确实不执行）。 */
export const APPROVE_PATH = '/approve'

export const READ_FAILED_TITLE = '挂起待办没能读出来'

/** 空态说的是「确实没有挂着的事」，而且要和「没权限」分得开：两句话不许互相顶替。 */
export const EMPTY_TITLE = '现在没有等你拍板的事'
export const EMPTY_DESCRIPTION = '这一屏读的是服务端的挂起账本：只有智能体真的停下来等确认时才会写下一笔。'
  + '这里为空就说明确实没有挂着的事，不等于这个账号没权限看账本，也不等于已经有人替你办了。'

/** 三句失败话各说各的事：没权限 / 表没建 / 没登录。 */
export const DENIED_TITLE = '这个账号没有读挂起账本的权限'
/** 权限卡要指得出下一步才算活路（与 lib/alerts.js 的 PERMISSION_WHERE 同一条规矩）：读不到不等于没有。 */
export const DENIED_WHERE = '这一屏读不到不一定是「没有」：挂起待办按归属过滤，也可能只是这项权限没放开。'
  + '请让企业管理员核对账号权限后重新读取；重新登录本身不会让这项权限出现。'
export const STORAGE_TITLE = '挂起账本还没就绪'
export const STORAGE_DESCRIPTION = '这张表要数据库迁移跑过才有内容，现在一笔都读不出来。'
  + '请让管理员确认迁移是否执行 —— 这不是「没有待办」，也不是重试能解决的事。'

/** 账本一行 -> 视图模型。后端字段名只在这一个函数里出现，模板与判定全用驼峰的视图字段。 */
export function mapPendingRow(row) {
  const source = row && typeof row === 'object' ? row : {}
  const steps = Array.isArray(source.parked_steps) ? source.parked_steps.map(String) : []
  const given = Array.isArray(source.labels) ? source.labels.filter(Boolean).map(String) : []
  return {
    sessionId: String(source.session_id == null ? '' : source.session_id),
    requestId: String(source.request_id == null ? '' : source.request_id),
    traceId: String(source.trace_id == null ? '' : source.trace_id),
    taskId: String(source.task_id == null ? '' : source.task_id),
    steps,
    labels: given,
    status: String(source.status == null ? '' : source.status),
    createdAt: formatStamp(source.created_at),
    expiresAt: formatStamp(source.expires_at),
  }
}

// 形状钉：上面这个返回值由 tests/…/r168-hitl-pending.test.js 逐字段钉住（本单写域之外，
// 不许动那枚钉子）。所以失败那一行的 ``decided_at`` 【不进】视图模型 —— 屏上那句
// 「批过了、那一轮失败了」用的是挂起时间与请求号，够人对账；账本里那一格仍然留着
// decided_at，哪天要把「断于几点」画上屏，先要过一次那枚形状钉。

/**
 * 后端那一格 failed_turns -> 视图行数组。
 *
 * 只认响应里真的有这一格：老镜像没有它、或后端坏成形状不对，一律回空数组 ——
 * 那一屏于是只说「没有等你拍板的事」，绝不凭空造一句「你批过而失败了」。
 */
export function failedTurnsOf(payload) {
  const rows = payload && payload.failed_turns
  return Array.isArray(rows) ? rows : []
}

/** 这一格的一行：动作名（后端给了标签就用，没给按步骤名说中文）+ 长 id 只留前 8 位。 */
export function failedTurnLabel(turn) {
  const names = rowLabels(turn)
  const request = shortId(turn && turn.requestId)
  return names.join(' / ') + (request ? '（请求 #' + request + '）' : '')
}

/**
 * R175 判据②的那三句话。两条红线写在这里，由用例逐字钉住：
 *   · 不许出现「已拒绝 / 已驳回」—— 员工点的是同意，那一轮是系统跑挂的；
 *   · 不许出现「已完成 / 已放行」—— 什么都没产出，报办完就是伪装。
 */
export const FAILED_TURN_TITLE = '批过了，但那一轮失败了'
export const FAILED_TURN_LEAD = '下面这些步骤你当时拍了板，可那一轮没能跑完：编排报错，或者超过了系统处理时限。'
  + '它们不算新的待办，也不会再回来等你批第二次 —— 这一屏没有把它记成你驳回，也没有记成办完。'
  + '要拿到结果，请回那一轮对话重新问一次。'
export const FAILED_TURN_MORE = '更早的失败那一轮仍在账本上，这一屏只列了最近这些。'

/**
 * 谁排在谁前面：loading > failure > empty/list。
 * failure 排在 rowCount 之前是这块的命门：「读失败」与「读到零笔」是两件事，
 * 一旦写反，服务坏了就会替用户宣布「你没有待办」。
 */
export function pendingFace({ loading = false, failure = null, rowCount = 0 } = {}) {
  if (loading) return 'loading'
  if (failure) return failure.face
  return Number(rowCount) > 0 ? 'list' : 'empty'
}

/** 一张失败的成品卡：face / title / description / codeLabel / retryable 一次算完，模板只画。 */
function failureCard({ face, title, description, codeLabel = '', retryable = true }) {
  return { face, title, description, codeLabel, retryable }
}

/**
 * 读列表失败的判脸。码名一律走 lib/errcodes.js 的独立通道（codeLabel），
 * 正文只说人话 + 下一步 —— 业务同学不该在这一屏读到一串下划线。
 */
export function pendingFailureView(err) {
  const code = errorCodeOf(err)
  if (code === 'storage_unavailable') {
    return failureCard({ face: 'storage', title: STORAGE_TITLE, description: errorDetail(err, STORAGE_DESCRIPTION), retryable: false })
  }
  if (code === 'permission_denied') {
    return failureCard({
      face: 'denied',
      title: DENIED_TITLE,
      description: errorDetail(err, DENIED_TITLE) + DENIED_WHERE,
      codeLabel: errorCodeLabel(normalizeError({ detail: code })),
      retryable: false,
    })
  }
  return readFailureView(err, { deniedTitle: DENIED_TITLE, failedTitle: READ_FAILED_TITLE })
}

/** 结构不对＝坏了，不是空的：没有错误对象可归码，句子取自 lib/alerts.js 那一真源。 */
export function pendingShapeFailure() {
  return failureCard({ face: 'error', title: READ_FAILED_TITLE, description: SHAPE_FAILURE_DESCRIPTION, retryable: true })
}

/**
 * 一次决定的结果反馈（判据②）。六条分支的话各不相同，两条红线：
 *   · 批准失败一律倒扣：话里必须说「没有生效 / 仍然挂着」，绝不出现「已完成 / 已放行」；
 *   · 中断与没读到收尾信号一律 face='unknown'：契约 R11/R12 明写中断只是脱离回答流，
 *     既不构成驳回，也不许声称那一步没跑或跑完了。界面不敢替后端下结论。
 */
export function decisionView({
  approved = false,
  ok = true,
  status = 0,
  terminal = '',
  stopped = '',
  errorCode = '',
  errorMessage = '',
  awaitingHitl = false,
} = {}) {
  const kind = approved ? 'approved' : 'rejected'
  const verb = approved ? '批准' : '驳回'
  const codeLabel = errorCode ? errorCodeLabel(normalizeError({ detail: errorCode })) : ''
  const reason = errorMessage || (errorCode ? errorText(errorCode) : '')
  // /approve 又停在新一步上时，legacy hitl 事件排在收尾事件之前，读取器当场就停了：
  // 所以"又挂起了"看 stopped，不能只等收尾事件里的那枚旗子。
  const parkedAgain = awaitingHitl || stopped === 'hitl'

  if (!ok) {
    return {
      kind,
      face: 'failed',
      title: verb + '没有送出去',
      description: '服务端回的是 HTTP ' + (status || 0) + '：' + reason
        + '。这一请求没有动那一步，列表里这一行仍在原地，不能按办完记账。',
      codeLabel,
    }
  }
  if (terminal === 'failed') {
    return {
      kind,
      face: 'failed',
      title: verb + '没有生效',
      description: (approved
        ? '那一步并没有跑出结果：' + (reason || '本轮什么也没产出') + '。这一屏不把它记成办妥，也不算你驳回。'
        : '驳回也没有生效：' + (reason || '本轮什么也没产出') + '。这一步既没执行、也没被确认否决，先别按办完记账。')
        // R175 之后「这一行也留在原地」成了半句真话：后端在报失败【之前】就把那一格闭成
        // failed，重新读取之后它不再作为待办回来。所以话只能这么说 —— 账面闭合是一回事，
        // 那一步真跑出了结果又是另一回事，前者永远不能拿来顶后者。
        + '按「重新读取」可以向账本再问一次；它要是把这笔记成了失败的那一轮，也不等于这一步真跑完了。',
      codeLabel,
    }
  }
  if (terminal === 'cancelled') {
    return {
      kind,
      face: 'unknown',
      title: '这一轮回答断了，动作结果没读回来',
      description: '中断只是脱离这次回答，既不算驳回，也不能断定那一步没跑（契约 R11 / R12）。'
        + '请回那一轮对话确认；这一行不会自己消失，也不会被画成已批准。',
      codeLabel: '',
    }
  }
  if (parkedAgain) {
    return {
      kind,
      face: 'ok',
      title: approved ? '已批准，这一步已放行；智能体又停下来问下一件事' : '已驳回，这一步不会执行；智能体又停下来问另一件事',
      description: '新的那一笔就在下面，仍然等你拍板。',
      codeLabel: '',
    }
  }
  if (terminal !== 'completed') {
    return {
      kind,
      face: 'unknown',
      title: verb + '发出去了，但没读到结果',
      description: '这条回答流走到结束也没给收尾信号，界面不敢替你宣布它成了还是没成。请重新读取列表再决定。',
      codeLabel: '',
    }
  }
  return {
    kind,
    face: 'ok',
    title: approved ? '已批准，这一步已放行' : '已驳回，这一步不会执行',
    description: (approved
      ? '这一步已交回智能体继续跑，回那一轮对话看结果。'
      : '被驳回的动作确实没有执行，这是后端契约保证的一条（R11）。') + '这一笔不再挂在待办里。',
    codeLabel: '',
  }
}

/** 请求根本没发出去（断网）：结果未知。既不写失败已确认，也不写成功。 */
export function transportDecisionView(approved, err) {
  return {
    kind: approved ? 'approved' : 'rejected',
    face: 'unknown',
    title: (approved ? '批准' : '驳回') + '没能送到服务，结果未知',
    description: errorDetail(err, '与服务器的连接中断') + '。这一步可能仍挂着，请重新读取列表再决定。',
    codeLabel: '',
  }
}

/**
 * 这一笔能不能跳回那一轮：只看「传进来的这份会话名单里有没有它」。
 * R174 判据②之后这份名单是【后端那份】（GET /sessions），不再是这台浏览器的历史 ——
 * 函数本身只认名单不认来路，所以两格的差别由调用方（decorateReplay）负责挑，一处判定只有一份。
 */
export function canReplayTurn(row, localIds) {
  const sessionId = String((row && row.sessionId) || '')
  if (!sessionId || !Array.isArray(localIds)) return false
  return localIds.indexOf(sessionId) >= 0
}

/**
 * 把「这一行能不能跳回去」判成一张按会话号索引的表。
 * 判定的结果【不写进行数据】：rows 只可能是后端 items 映射出来的行（R168 判据③那条源码钉），
 * 而「这一行能不能跳」是派生态，派生态住在派生表里，由 computed 现算，不去污染行的形状。
 * 三种判不到各说各的，一格都不许并：
 *   后端有这一条         → 给跳转（本机翻不到也给 —— 换台机器打开链接的那一位就是这一格）
 *   后端没有、本机有     → REPLAY_LOCAL_ONLY，另说一句，不并进「没有可回看」
 *   后端没有、本机也没有 → REPLAY_NONE
 *   后端那份名单读不到   → 暂时退回按本机判，并把 basis 记成 local，由屏上另一句单独认账
 * 读不到时退回本机不等于「按本机裁决」：那句话必须由屏幕上说出来，不能让行上静默换标准。
 */
export function replayVerdicts(rows, read, localIds) {
  const known = Boolean(read && read.known)
  const basis = known ? read.ids : localIds
  const verdicts = {}
  for (const row of Array.isArray(rows) ? rows : []) {
    const canOpen = canReplayTurn(row, basis)
    verdicts[row.sessionId] = {
      canOpen,
      note: canOpen ? '' : (known && canReplayTurn(row, localIds) ? REPLAY_LOCAL_ONLY : REPLAY_NONE),
      basis: known ? 'backend' : 'local',
    }
  }
  return verdicts
}

/** 深链落到对话屏，并把这一笔的编号带在地址上：转发与对账用的是同一条地址。 */
export function chatAnchor(row) {
  const query = { session: String((row && row.sessionId) || '') }
  const requestId = String((row && row.requestId) || '')
  if (requestId) query.request = requestId
  return { name: 'chat', query }
}

/**
 * 点了「回到这一轮」之后后端那句认账的话（R174 判据②：这一枪真的发出去才知道有没有）。
 * 与行上那两句各说各的事：那两句说的是「这一屏判过了不给跳转」，这几句说的是
 * 「屏上判着该给，点下去正文却没回来」——两种落不到不许并成一张脸。
 */
export const REPLAY_READ_FAILED = {
  [SESSION_READ.notFound]: '那一轮的会话后端说没有：这一条链接可能已经过期，也可能对方把它删了。',
  [SESSION_READ.notYours]: '那一轮的会话不是当前这个账号能看的：换回发起这一问的那个账号再点一次。',
  [SESSION_READ.unreachable]: '那一轮的正文没能读回来：后端这会儿读不到。这一笔仍然挂在上面，没被抹掉。',
  [SESSION_READ.badBody]: '那一轮的正文没能读回来：后端回的形状系统不认识。这一笔仍然挂在上面，没被抹掉。',
}

/**
 * 后端那份名单没读到，这一屏只能暂时按本机判：换标准这件事必须自己说出口（判据②「别静默」）。
 * 它成为一枚常量而不是模板里的一段裸话，只为了一件事 —— 屏上这几张脸两两不同句这条规矩，
 * 用例能把这一句一起拉进来比，而不是比一份抄来的副本。
 */
export const REPLAY_BASIS_LOCAL_NOTE = '后端那份会话名单这会儿没读到，上面几行「能不能回到那一轮」暂时只能按这台浏览器判：'
  + '换台机器、换个浏览器打开同一串链接，这一格可能给出的不是同一个答案。'
</script>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { authedFetch, http } from '../../lib/http'
import { listRows } from '../../lib/alerts'
import {
  adoptBackendSession,
  consumeSseStream,
  hasLocalSession,
  loadSessions,
  readBackendSession,
  readBackendSessionIds,
  sessions,
  switchSession,
} from '../../lib/sessions'
import { UiButton, UiEmptyState, UiErrorState, UiLoadingState } from '../ui'
import HitlPendingRow from './HitlPendingRow.vue'

const router = useRouter()

const rows = ref([])
// 初值就是「在读」：SSR 与首帧都不许先画一张空表骗人。
const loading = ref(true)
const loadingMore = ref(false)
const inFlight = ref(false)
const failure = ref(null)
const hasMore = ref(false)
const moreError = ref('')
const offset = ref(0)
const busyId = ref('')
const outcomes = ref({})
const localIds = ref([])
// 判据②的那份【后端】会话名单。asked = 这一屏有没有真去问过；known = 问到了没有。
// 「没问过」「问了但读不到」「问到了而且名单是空的」是三件事，一句都不许顶另一句。
const backendRead = ref({ asked: false, known: false, ids: [], failure: '' })
// 点了跳转、正文却没回来时的那一句：与「这一笔没有可回看的对话」不是一格，各说各的。
const openFailure = ref('')
// R175：批过了而那一轮失败的那几笔。它与 rows 各存一份、永不并格 —— rows 只可能是待办，
// 这一份只可能是已闭合的失败轮。两份混成一份，屏上就会重新出现「拿故障当新待办」。
const failedTurns = ref([])
const failedTurnsMore = ref(false)

/** 判定表：行 + 后端那份名单 + 本机那份对照，三样现算，任何一样变了都自动跟上。 */
const verdicts = computed(() => replayVerdicts(rows.value, backendRead.value, localIds.value))

const verdictOf = row => verdicts.value[row.sessionId] || null

const pageSize = PENDING_PAGE_SIZE
const emptyCopy = { title: EMPTY_TITLE, description: EMPTY_DESCRIPTION }
const replayBasisNote = REPLAY_BASIS_LOCAL_NOTE
const failedCopy = { title: FAILED_TURN_TITLE, lead: FAILED_TURN_LEAD, more: FAILED_TURN_MORE }
const failedLine = failedTurnLabel

const face = computed(() => pendingFace({
  loading: loading.value,
  failure: failure.value,
  rowCount: rows.value.length,
}))

/**
 * 可回看的会话只从内存里那份 store 取（lib/sessions.js 的 sessions 是全站唯一的一份）。
 * 刻意不每次都用盘上的副本去覆盖它：loadSessions() 会把 sessions.value 整份换成 localStorage 里的
 * 内容，而对话屏是 keep-alive 的、正在跑的那一轮还没落盘 —— 这一屏只是想读个名单，
 * 不该顺手把别人正在用的那份列表回滚一次。所以只在它还是空的时候补一次盘。
 * R174 判据②之后这份名单【降级为对照】：它只用来认出「后端没有而本机还留着」那一格。
 */
function readLocalIds() {
  if (!sessions.value.length) loadSessions()
  return sessions.value.map(item => String(item.id))
}

/**
 * 向后端问一次「这些会话你那儿还留着哪些」：一发 GET /sessions 判全部行，
 * 不给每一行各发一枪（一页 50 笔就是 50 枪）。这一屏每次开屏问一次，
 * 问到的名单就地进判定表；行本身一个字段都不必动。
 */
async function refreshReplayBasis() {
  const read = await readBackendSessionIds()
  backendRead.value = { ...read, asked: true }
  return read
}

/** 模板只认这一屏自己的绑定，跨块的纯函数一律包一层再交给模板。 */
function canOpen(row) {
  const verdict = verdictOf(row)
  return Boolean(verdict && verdict.canOpen)
}

function replayOf(row) {
  return verdictOf(row) || { canOpen: false, note: REPLAY_NONE, basis: 'local' }
}

function outcomeOf(row) {
  return outcomes.value[row.sessionId] || null
}

/** 后端名单判到了就直接采信，没判到（这一屏还没问过、或那一枪没读回来）才就地算一次。 */
function replayable(row) {
  return canOpen(row)
}

/**
 * 跳回产生这一笔的那一轮。
 * 本机有这一条：同步切过去（R168 那条既有行为，一毫秒都不许多等）。
 * 本机没有、后端有：这正是「换台机器打开同事发来的链接」那一格 —— 先把地址落到那一轮，
 * 正文在后台取；取不到就把人带回这一屏并明说一句，绝不静默留一份空会话在对话屏上。
 */
function openTurn(row) {
  if (!row || !replayable(row)) return false
  openFailure.value = ''
  if (!hasLocalSession(row.sessionId)) {
    if (router) router.push(chatAnchor(row))
    void replayFromBackend(row)
    return true
  }
  switchSession(row.sessionId)
  if (router) router.push(chatAnchor(row))
  return true
}

async function replayFromBackend(row) {
  const read = await readBackendSession(row.sessionId)
  if (read.outcome === SESSION_READ.found) {
    // 交回那份唯一的 store：对话屏读的就是这一份，站内点击与冷启动不会各存一套。
    adoptBackendSession(row.sessionId, read.messages)
    return true
  }
  openFailure.value = REPLAY_READ_FAILED[read.outcome] || REPLAY_READ_FAILED[SESSION_READ.badBody]
  if (router) router.replace({ name: 'approval' })
  return false
}

async function loadPending({ append = false } = {}) {
  // inFlight 与 loading 是两件事：loading 首帧就该是 true（还没读过账本，不能画空态），
  // 但它一旦兼作重入闸门，onMounted 那第一次读取就会被自己挡掉 —— 屏上永远停在「正在读取」。
  if (inFlight.value) return
  inFlight.value = true
  if (append) loadingMore.value = true
  else {
    loading.value = true
    failure.value = null
    moreError.value = ''
    // 重读之前先撤下那一句：账本这会儿是什么样还不知道，屏上不许拿上一次的话冒充这一次。
    failedTurns.value = []
    failedTurnsMore.value = false
  }
  // 能不能跳回那一轮，取决于这台浏览器的会话历史长什么样；每次读列表前重取一次，
  // 免得用户在对话里跑了几轮之后回到这一屏，行上还按旧账给跳转。
  localIds.value = readLocalIds()
  const requestOffset = append ? offset.value : 0
  try {
    const response = await http.get(PENDING_PATH, { params: { limit: PENDING_PAGE_SIZE, offset: requestOffset } })
    const items = listRows(response.data, 'items')
    if (!items) {
      // 形状不对＝坏了，不是空的：画失败脸，绝不落到「现在没有等你拍板的事」。
      rows.value = []
      hasMore.value = false
      failedTurns.value = []
      failure.value = pendingShapeFailure()
      return
    }
    const mapped = items.map(mapPendingRow)
    rows.value = append ? rows.value.concat(mapped) : mapped
    hasMore.value = Boolean(response.data.has_more)
    // 失败那一格不翻页：翻页游标说的是待办，而这一格说的是「最近这些轮失败了」。
    // append 那一枪带回来的是同一批，重复赋值只会让屏上的行数抖一下。
    if (!append) {
      failedTurns.value = failedTurnsOf(response.data).map(mapPendingRow)
      failedTurnsMore.value = Boolean(response.data.failed_turns_has_more)
    }
    // 游标推进按「这一页真正消费掉多少行账本」：后端取 limit+1 行、截到 limit 行再逐行复核，
    // 复核不过的行就地排除 —— 所以 mapped.length 可能小于它消费掉的行数。
    // 按 mapped 推进会把被复核掉的行再读一遍（同一笔待办在屏上出现两次）。
    offset.value = requestOffset + (hasMore.value ? Number(response.data.limit) || mapped.length : mapped.length)
  } catch (err) {
    if (append) {
      moreError.value = errorDetail(err, '更早的挂起待办没能读出来')
    } else {
      rows.value = []
      hasMore.value = false
      offset.value = 0
      failedTurns.value = []
      failure.value = pendingFailureView(err)
    }
  } finally {
    if (append) loadingMore.value = false
    else loading.value = false
    inFlight.value = false
  }
}

/**
 * 批准 / 驳回都走这一条：POST /approve + 真读取器 consumeSseStream。
 * 流的正文属于那一轮对话，不进这一屏，所以喂给它的是一个本地累加器，
 * 不去动 sessions 里那条会话的消息 —— 这一屏只负责把「办没办成」说清楚。
 */
async function decide({ row, approved } = {}) {
  if (!row || !row.sessionId || busyId.value) return null
  busyId.value = row.sessionId
  let view = null
  try {
    const response = await authedFetch(APPROVE_PATH, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: row.sessionId, approved }),
    })
    const scratch = { role: 'assistant', content: '', sources: [] }
    const result = await consumeSseStream(response, scratch)
    const state = result.state || {}
    view = decisionView({
      approved,
      ok: result.ok,
      status: result.status,
      terminal: state.terminal || '',
      stopped: result.stopped || '',
      errorCode: state.errorCode || result.errorCode || '',
      errorMessage: result.ok ? '' : result.error || '',
      awaitingHitl: Boolean(state.awaitingHitl),
    })
  } catch (err) {
    view = transportDecisionView(approved, err)
  }
  outcomes.value = { ...outcomes.value, [row.sessionId]: view }
  busyId.value = ''
  // 只有真办成才重读账本。失败时重读等于让一次刷新把这一笔洗掉：后端在跑崩那一支
  // 也可能已经把挂起行改成终态，届时屏上只剩下一句「没有待办」——那是把失败说成办完。
  if (view.face === 'ok') {
    localIds.value = readLocalIds()
    await loadPending()
  }
  return view
}

function loadMore() {
  return loadPending({ append: true })
}

onMounted(() => {
  localIds.value = readLocalIds()
  // 判据②：这一屏每次开屏向后端问一次「这些会话你还留着哪些」——能不能回看由它判，
  // 不由这台浏览器的历史判。它不占 loadPending 那一枪的预算：读账本与读名单是两件事。
  refreshReplayBasis()
  loadPending()
})
</script>

<template>
  <section class="panel-card hitl-pending" data-testid="hitl-pending" :data-face="face">
    <div class="section-head">
      <h4>挂起待办</h4>
      <UiButton
        v-if="face === 'list' || face === 'empty'"
        variant="ghost"
        size="sm"
        label="重新读取"
        data-testid="hitl-reload"
        @click="loadPending()"
      />
    </div>

    <p class="hitl-lead">
      智能体跑到需要你点头的那一步就会停下来挂在这里，而那一问今天埋在对话流里，一滚屏就找不着。
      这一屏把它摊开：手头有哪几笔在等你拍板、批准还是驳回、办完之后回到哪一轮去看结果。
    </p>

    <!-- R174 判据②：那份名单没读到时，这一格换成了按本机判 —— 必须自己说出口，
         不能让行上悄悄换了标准还装作是后端的答复。asked 之前不画这句：没问不等于问不到。 -->
    <p v-if="rows.length && backendRead.asked && !backendRead.known" class="hitl-note"
       role="status" data-basis="local" data-testid="hitl-replay-basis">
      {{ replayBasisNote }}
    </p>
    <!-- 点了跳转而正文没回来：与行上那两句各说各的事，也单独一句。 -->
    <p v-if="openFailure" class="hitl-note" role="alert" data-testid="hitl-open-failure">{{ openFailure }}</p>

    <!-- R175 判据②：员工批过板而那一轮被系统跑挂了。那一行账已在后端闭合成 failed，
         所以它【不】会作为待办回来（那等于让同一个中断 resume 第二遍），但也不能无声消失 ——
         「我明明点了同意，它自己没了」还是半句假话。这一格只说这一件事：不带批准/驳回按钮，
         不进上面那四张脸，也不许被画成「已拒绝」。 -->
    <section v-if="failedTurns.length" class="hitl-failed" role="status" data-testid="hitl-failed-turns">
      <h5 class="hitl-failed__title">{{ failedCopy.title }}</h5>
      <p class="hitl-failed__lead">{{ failedCopy.lead }}</p>
      <ul class="hitl-failed__list">
        <li
          v-for="turn in failedTurns"
          :key="turn.sessionId + '/' + turn.requestId"
          class="hitl-failed__item"
          data-testid="hitl-failed-turn"
          :data-session="turn.sessionId"
          :data-request="turn.requestId"
          :data-status="turn.status"
        >
          {{ failedLine(turn) }}
          <span v-if="turn.createdAt">· 挂起于 {{ turn.createdAt }}</span>
        </li>
      </ul>
      <p v-if="failedTurnsMore" class="hitl-note" data-testid="hitl-failed-more">{{ failedCopy.more }}</p>
    </section>

    <UiLoadingState v-if="face === 'loading'" label="正在读取挂起待办..." dense />
    <UiErrorState
      v-else-if="failure"
      :title="failure.title"
      :description="failure.description"
      :code-label="failure.codeLabel"
      :retryable="failure.retryable"
      retry-text="重新读取"
      :busy="loading"
      dense
      @retry="loadPending()"
    />
    <UiEmptyState
      v-else-if="face === 'empty'"
      :title="emptyCopy.title"
      :description="emptyCopy.description"
      dense
    />
    <div v-else class="hitl-rows" data-testid="hitl-rows">
      <HitlPendingRow
        v-for="row in rows"
        :key="row.sessionId"
        :row="row"
        :replay="replayOf(row)"
        :can-open="canOpen(row)"
        :busy="busyId === row.sessionId"
        :outcome="outcomeOf(row)"
        @decide="decide"
        @open="openTurn"
      />
      <p v-if="moreError" class="hitl-note" data-testid="hitl-more-error">{{ moreError }}</p>
      <template v-if="hasMore">
        <p class="hitl-note" data-testid="hitl-has-more">
          这一页只取了最近 {{ pageSize }} 笔，账本里还有更早的挂起。
        </p>
        <UiButton
          variant="ghost"
          size="sm"
          :loading="loadingMore"
          label="看更早的"
          data-testid="hitl-more"
          @click="loadMore"
        />
      </template>
    </div>
  </section>
</template>

<style scoped>
.hitl-pending {
  display: grid;
  gap: var(--s-3);
  margin-top: var(--s-3);
  border-left: 3px solid var(--warning);
}

.hitl-lead {
  margin: 0;
  color: var(--muted);
  font-size: var(--t-xs);
  line-height: 1.7;
}

.hitl-rows {
  display: grid;
  gap: var(--s-3);
}

.hitl-note {
  margin: 0;
  color: var(--ink-soft);
  font-size: var(--t-xs);
  line-height: 1.6;
}

/* 只借 theme.css 既有令牌与 var(--*)，零裸色值 —— 与 HitlPendingRow 同一份视觉口径。 */
.hitl-failed {
  display: grid;
  gap: var(--s-2);
  padding: var(--s-3);
  border: 1px solid var(--line);
  border-left: 3px solid var(--danger);
  border-radius: var(--r-md);
  background: var(--surface-2);
}

.hitl-failed__title {
  color: var(--text);
  font-size: var(--t-sm);
  font-weight: 600;
}

.hitl-failed__lead,
.hitl-failed__item {
  color: var(--ink-soft);
  font-size: var(--t-xs);
  line-height: 1.6;
}

.hitl-failed__list {
  display: grid;
  gap: var(--s-1);
  margin: 0;
  padding-left: var(--s-3);
}
</style>
