<script>
/**
 * HitlPendingPanel —— 「挂起待办」那一块（R168）
 *
 * 一句话：智能体停下来等确认的那件事，今天只画在对话流里（ChatPanel 的那张卡片），一滚屏就找不着。
 * 这块把「我手头有几件要办的事、办完回哪儿去」抽成一屏。数据只有一个来源：
 *   GET  /hitl/pending   挂起账本（app/api/v1/chat.py:2181；契约 docs/api/contract-v1.md
 *                        的 HITL Pending Listing 一节）
 * 写操作也只有一个出口：
 *   POST /approve        body 恰为 { session_id, approved }，回来的是一条 SSE 流（chat.py:2271）
 *
 * 字段逐条照契约抄，不猜：items[].{session_id, owner_user_id, parked_steps, labels, status,
 * created_at, expires_at, request_id, trace_id, task_id}，外层 {items, count, limit, offset, has_more}。
 * count 是「过滤后的长度」，契约明写不得当总数用 —— 所以这一屏不摆「待办 N 条」那种数字，
 * 只如实说这一页取了最近多少笔、账本里还有没有更早的。
 *
 * 四张脸互不冒充（判据①，看板 G4 口径）：
 *   loading      进页面先「在读」—— 还没读过账本就说「没有待办」是句假话，所以它优先于一切。
 *   失败         UiErrorState（role=alert）：没权限 / 没登录 / 账本没就绪 / 真坏了，四句话各不相同。
 *   200 空 items UiEmptyState（role=status）：真的没有挂着的事。
 *   200 有行     列表，一行就是账本里的一笔。
 *   无权限与空列表是两条不可能互相顶替的路径：失败只可能来自 catch，200 空数组走不到 catch。
 *   备注（诚实记账）：/hitl/pending 今天不会回 403 —— 它对 anonymous 回 401、对别人的会话回 404
 *   而不是 403（chat.py:242-246 的「读不到就像不存在」惯例），归属靠 owner 过滤fail-closed。
 *   403 那张脸照样留着：哪天归属换成分层权限，这一屏不许把它悄悄画成「暂无待办」。
 *
 * 位阶最高的一条（判据③）：行只可能来自真响应。没有真 pending 就留空态，不造演示行、
 * 不拿历史会话冒充待办、读失败时也不清成一张「看起来像待办」的表。落成了三条硬约束：
 *   ① rows 的每次赋值要么来自 items.map(mapPendingRow)，要么是 []；
 *   ② 演示常量目录在本文件一次都不 import，也没有任何写死的行；
 *   ③ 失败路径先清 rows 再画 failure，而 pendingFace 里 failure 排在 rowCount 之前。
 *
 * 判据④用的是这台浏览器自己的会话历史（lib/sessions.js 的 sessions 列表）：ChatPanel 读的就是
 * 那一份，所以切过去就是产生这一笔的那一轮。对不上就明写「这一笔没有可回看的对话」——
 * switchSession 拿不到那个 id 时会就地新建一份同名空会话，那是伪造历史，
 * canReplayTurn() 就是把这道门的，绝不让它有机会被踩。
 */
import { errorDetail } from '../../lib/http'
import { errorCodeLabel, errorCodeOf, errorText, normalizeError } from '../../lib/errcodes'
import { formatStamp, readFailureView, SHAPE_FAILURE_DESCRIPTION } from '../../lib/alerts'

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
        ? '那一步并没有跑出结果：' + (reason || '本轮什么也没产出') + '。这一屏不把它记成办妥，这一行也留在原地。'
        : '驳回也没有生效：' + (reason || '本轮什么也没产出') + '。这一步既没执行、也没被确认否决，先别按办完记账。')
        // 账本可能已经把这笔记成已处理（后端在报失败之前先闭合了账面），那也只是账面：
        // 不代表这一步真跑出了结果。要说清楚，免得「重新读取」把这一行抹掉后被当成办妥。
        + '按「重新读取」可以向账本再问一次；它要是把这笔记成了已处理，也不等于这一步真跑完了。',
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
 * 这一笔能不能跳回那一轮：只在「这台浏览器的会话历史里真有那一条」时才给。
 * 账本记的是服务器上的挂起，会话正文存在浏览器本地，两者不是一回事；对不上就老实说
 * 「没有可回看的对话」，绝不新建一份空会话冒充（判据④的「不许静默」与「不许新开」同一条）。
 */
export function canReplayTurn(row, localIds) {
  const sessionId = String((row && row.sessionId) || '')
  if (!sessionId || !Array.isArray(localIds)) return false
  return localIds.indexOf(sessionId) >= 0
}

/** 深链落到对话屏，并把这一笔的编号带在地址上：转发与对账用的是同一条地址。 */
export function chatAnchor(row) {
  const query = { session: String((row && row.sessionId) || '') }
  const requestId = String((row && row.requestId) || '')
  if (requestId) query.request = requestId
  return { name: 'chat', query }
}
</script>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { authedFetch, http } from '../../lib/http'
import { listRows } from '../../lib/alerts'
import { consumeSseStream, loadSessions, sessions, switchSession } from '../../lib/sessions'
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

const pageSize = PENDING_PAGE_SIZE
const emptyCopy = { title: EMPTY_TITLE, description: EMPTY_DESCRIPTION }

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
 */
function readLocalIds() {
  if (!sessions.value.length) loadSessions()
  return sessions.value.map(item => String(item.id))
}

/** 模板只认这一屏自己的绑定，跨块的纯函数一律包一层再交给模板。 */
function canOpen(row) {
  return canReplayTurn(row, localIds.value)
}

function outcomeOf(row) {
  return outcomes.value[row.sessionId] || null
}

async function loadPending({ append = false } = {}) {
  // inFlight 与 loading 是两件事：loading 首帧就该是 true（还没读过账本，不能画空态），
  // 但它一旦兼作重入闸门，onMounted 那第一次读取就会被自己挡掉 —— 屏上永远停在「正在读取」。
  if (inFlight.value) return
  inFlight.value = true
  if (append) loadingMore.value = true
  else { loading.value = true; failure.value = null; moreError.value = '' }
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
      failure.value = pendingShapeFailure()
      return
    }
    const mapped = items.map(mapPendingRow)
    rows.value = append ? rows.value.concat(mapped) : mapped
    hasMore.value = Boolean(response.data.has_more)
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

function openTurn(row) {
  if (!canReplayTurn(row, localIds.value)) return false
  switchSession(row.sessionId)
  if (router) router.push(chatAnchor(row))
  return true
}

function loadMore() {
  return loadPending({ append: true })
}

onMounted(() => {
  localIds.value = readLocalIds()
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
</style>
