<script>
/**
 * NotificationBell —— 顶栏那枚欠回来的铃铛（R333）
 *
 * 这一格的历史（不是新增玩法，是把当年欠的那格接回来）：R278 按判据 G16①② 主动摘掉顶栏两枚
 * 按了没反应的假控件，其中通知那一枚摘在「今天没有一句诚实的条数可摆」（r278-topbar.test.js:14）——
 * 那时 GET /hitl/pending 的 count 只是一页过滤后的长度，dashboard 那一格自己写着「可能高估」。
 * R299 把出口补上了：GET /notifications 按【全集口径】交回未读总数（unread_total），
 * 并在窗口裁过时把 is_exact 落成 false。所以今天这枚徽标有真数字可摆，代价是诚实口径：
 *   · 数字只出自 lib/notifications.js 的全集未读，页内条数在那一层就不往上交（判据①）；
 *   · is_exact=false 说的是「至少」，不是「正好」（判据①的后半）；
 *   · 还没读到 / 读失败时【不画数字】也不说「没有未读」，0 与未知是两张脸（判据③）；
 *   · 一次动作之后的新数字来自再读一次后端，不来自 unread - changed 那种自己算（判据④⑤）。
 *
 * 四张脸互不顶替（判据⑥），顺序即语义：loading 优先于一切，失败排在「空」之前——
 * 把「读不到」画成「没有通知」是这一单最不能犯的错，反证钉专门打这一条。
 *
 * 可达性（判据⑦）：触发件是 components/ui 的 UiButton（真 button，Enter/Space 是原生行为，
 * 不在这里另造一套），带 aria-label 的可读句子（「3 条未读通知」而不是孤零零一个 3）、
 * aria-expanded / aria-controls；Esc 关闭（复用 ui/focus-trap.js 那一枚 shouldCloseOnKey，
 * 不在输入元素里抢「清空输入」的语义），关闭后焦点交回触发件。Tab 可达由原生 button 保证。
 *
 * 判据⑧：搜索那一格仍【没有】接——全站没有一枚诚实的全局检索端点，接了就是回到假控件。
 * 这里只接通知这一枚。
 *
 * R385 接上的是欠着的那半张脸：后端从 R366（a9762df）起在响应里带一台缺席台账（`sources`，
 * 每格 {included, reason_code, candidates, scanned, truncated}），本组件此前一个字都没读它。
 * 于是 PG 迁移没跑齐时，员工在这儿看到的只是「少了几条通知」——屏上没有一句话告诉他
 * 「审批那一格今天没答」。两脸在这儿分开画，与后端那一刀同判据：
 *   账本在答而 candidates=0 -> 还是原来那张「现在没有要看的通知」，本件一个字都不许多；
 *   账本 included=false      -> 多一行「某某账本这次没答上来：…」，中性色 + role=status，
 *                              不红、不弹、不打断读屏（判据②：不许把员工吓走）。
 * 句子出自本文件下面那张 LEDGER_COPY（判据③：一张表、一处写法，面板与读屏念的是同一串字）；
 * 为什么这张表长在这儿而不是 lib/notifications.js —— 取证见下面 LEDGER_COPY 那一段：那一枚文件
 * 的导出面与每一枚既有函数体被 R375 的 scope 钉逐字冻在 796540e，台账在那一层无路可走。
 * 未读数、分页、徽标一条都不经台账（判据④）：缺席格既不算成 0 条未读，它的 candidates 也不进合计。
 */
import { errorDetail, http } from '../lib/http'
import {
  ALL_FILTER,
  INBOX_PATH,
  INBOX_PAGE_LIMIT,
  bellLabel,
  badgeText,
  collectUnreadIds,
  dismissNotifications,
  isShapeFailure,
  markAllUnread,
  markRead,
  normalizeInbox,
  panelSummary,
  readFailureViewOf,
  shapeFailureViewOf,
  writeFailureView,
} from '../lib/notifications'
import { shouldCloseOnKey } from './ui/focus-trap.js'

export default { name: 'NotificationBell' }

export const PANEL_TITLE = '通知'
/** 空态说的是「后端确实报了没有」，不是「我没读到」：两句话不许互相顶替。 */
export const EMPTY_TITLE = '现在没有要看的通知'
export const EMPTY_DESCRIPTION = '这一格是那三本既有账的投影：挂起待办、异常告警、已入库文档。'
  + '这里为空只说明现在没有可读回来的条目，不等于公司一切正常，也不等于这一格坏了。'

/* ==========================================================================
 * R385 · 缺席台账：GET /notifications 那台 sources 的唯一读取处与唯一文案处
 * ======================================================================== *
 * 后端从 R366（a9762df）起在响应里带一台台账：`sources` 是按 source_type 索引的对象，
 * 每一格五枚 {included, reason_code, candidates, scanned, truncated}（键名逐枚见
 * docs/api/contract-v1.md R299 一节末尾「The five keys of one sources.<source>
 * projection」；生产者 = app/notifications/inbox.py::build_inbox 那一行 as_projection）。
 * 它把两件事分得很清，本件照抄这一刀，一格都不许并：
 *   included=true  / reason=ok / candidates=0 -> 这本账在答，确实没有那类事项（今天那张脸）；
 *   included=false / reason=<那本账自己的码>  -> 这一格今天不供数，屏上的条数里没有它。
 * 在这一单之前，前端一个字节都没读它：PG 迁移没跑齐、或某一腿被 403 拒答时，员工在小铃铛里
 * 看到的只是「少了几条通知」，屏上没有一句话告诉他审批那一格没答——他会以为没人找他审批。
 *
 * 判据③「句子出处只有一处」：屏上的话全部出自下面这张 LEDGER_COPY，它在本件自有，
 * 与状态名解耦——键是后端交回来的状态名（只用来分流），值里一枚状态名都没有（判据②，
 * 与 R268 / R281 / R380 同一条口：后端原话不许占人话位）。为什么不搬进 lib/errcodes.js：
 * 字典的键是 ErrorEnvelope.code 的封闭枚举（与后端 contracts 不多不少，由码表对账钉住），
 * 而这一格不是错误信封——它是三本账各自的读数，多的是「哪一格」这一维，少的是状态码与
 * retryable。搬进字典就得给三腿各造组合码，那是 R380「零新增码」先例的反面。
 *
 * 判据⑥：这张表为什么长在本文件而不是 lib/notifications.js —— 三枚既有钉把那条路钉死了，
 * 逐枚现跑取证（都在 r375-write-retryable-dict.test.js / r333-notification-inbox.test.js）：
 *   1) 「导出面只多出一枚 failureRetryable」对 notifications.js 断言 added 恒为空：
 *      任何新导出（sourceCells / LEDGER_LEGS…）当场红；
 *   2) 「除这两枚之外的每一枚导出与基线同 sha」把 notifications.js 里每一枚既有函数体
 *      逐字冻在 REF=796540e：改 normalizeInbox / readInbox / bellLabel 任何一枚即红；
 *   3) 「取数层没有第二本错误码账」现量 notifications.js 代码体的码名集合恰为
 *      ['storage_unavailable']：本件的 reason 分流一旦出现 permission_denied /
 *      principal_inactive 就当场红（本单实跑过，报数在交回里）。
 *   另有一枚 r333 把 normalizeInbox 的返回值钉死成八枚键，台账搭不上车。
 * 四枚钉都不许改（不在本单写域，改别人的钉得先由总控裁定），所以本件自己做这一次读：
 * 借的还是 lib/http.js 那枚共享实例、lib/notifications.js 自己那三枚常量，
 * 计数账仍旧整包交给 lib 的 normalizeInbox 去算——本件一行都没抄它的算法，只多解析
 * 那一台它交不出来的台账。要把它挪回取数层，得先由总控放宽上面第 1、2、3 枚，已在交回里具名报。
 * ======================================================================== */

/** 每一格账本的人话名。键 = 后端 contracts.py::NOTIFICATION_SOURCES 的取值；枚数与取值集合由
 *  r385-ledger-contract.test.js 现读后端真源对账（多一格、少一格、名字漂了都当场红）。 */
export const LEDGER_LEGS = {
  approval: '审批账本',
  alert: '告警账本',
  document: '文档账本',
}

/** 契约里「这本账答上了」的那一枚取值：它不是缺席，屏上一格字都不许多。 */
export const LEDGER_ANSWERED = 'ok'

/** 第四格真来了而本件还不认识它：宁可说一句笼统的真话，也不把后端那枚键直插人话位。 */
const LEG_UNKNOWN = '有一格账本'

/** 下面三句是「为什么没答」的人话，逐枚对应后端真会交出来的那一枚 reason（取证见甲组用例）。 */
const CAUSE_STORE = '它要的数据表在这台机器上还没准备好，要管理员把数据库迁移跑过才会恢复'
const CAUSE_DENIED = '这个账号没有看它的权限，要问企业管理员'
const CAUSE_INACTIVE = '这个账号已经停用，那一格不认它'
/** 表里没登记的原因：说一句短的实话，既不猜它为什么，也不把状态名端给人看。 */
const CAUSE_UNKNOWN = '它没说明原因'

/** 句子的两头：头说「谁没答」，尾把那两脸的分界钉在句子里——不含它 ≠ 那一类真的没有。 */
const LEDGER_HEAD = '这次没答上来：'
const LEDGER_TAIL = '。现在这些通知里不含它那一类，不代表那一类事情真的没有。'

/** 后端 reason_code -> 人话。键的合法性由 __tests__/r385-ledger-contract.test.js 现读后端真源判：
 *  一枚都不许是本件自造的状态名，也不许漏掉后端今天真会交出来的那几枚。 */
export const LEDGER_CAUSES = {
  storage_unavailable: CAUSE_STORE,
  permission_denied: CAUSE_DENIED,
  principal_inactive: CAUSE_INACTIVE,
}

const hasLedgerKey = (table, key) => Object.prototype.hasOwnProperty.call(table, key)
const ledgerText = (value) => (value == null ? '' : String(value))

/** 这一格屏上叫什么。表里没有的键一律走笼统名：这里没有第四枚人话名可编。 */
export function ledgerLegName(sourceType) {
  const key = ledgerText(sourceType)
  return hasLedgerKey(LEDGER_LEGS, key) ? LEDGER_LEGS[key] : LEG_UNKNOWN
}

/** 这一格为什么没答。表里没有的原因退到笼统句，绝不回读后端那枚状态名。 */
export function ledgerReasonCopy(reasonCode) {
  const key = ledgerText(reasonCode)
  return hasLedgerKey(LEDGER_CAUSES, key) ? LEDGER_CAUSES[key] : CAUSE_UNKNOWN
}

/** 一格的屏上原句：本件唯一一处拼这句话的地方（判据③）。答上了的那一格交回空句。 */
export function absenceCopy(cell) {
  if (!cell || cell.included === true) return ''
  return ledgerLegName(cell.sourceType) + LEDGER_HEAD + ledgerReasonCopy(cell.reasonCode) + LEDGER_TAIL
}

/**
 * 响应里那台台账 -> 逐格读数。三条口径：
 *   · 只遍历响应【真有的】那些键：后端少交一格就是少一格，本件不替它补齐三格（补=自造账本）；
 *   · included 只认严格 true，其余一律算没答——与 lib 里 isExact 那条同一种 fail-closed：
 *     把这格读成「答上了」正是本单要修的假话，读成「没答」至多让员工去核一次；
 *   · sources 整格缺失 / 不是对象 = 读不到台账，交回空表：那三格账本不因此长出一句话来。
 */
export function ledgerCells(payload) {
  const ledger = payload && typeof payload === 'object' ? payload.sources : null
  if (!ledger || typeof ledger !== 'object' || Array.isArray(ledger)) return []
  const cells = []
  for (const sourceType of Object.keys(ledger)) {
    const cell = ledger[sourceType]
    if (!cell || typeof cell !== 'object' || Array.isArray(cell)) continue
    cells.push({
      sourceType,
      included: cell.included === true,
      reasonCode: ledgerText(cell.reason_code),
      candidates: cell.candidates,
      scanned: cell.scanned,
      truncated: cell.truncated === true,
    })
  }
  return cells
}

/** 台账里没答上的那些格——屏上要说话的就是它们。 */
export function silentCells(cells) {
  return (Array.isArray(cells) ? cells : []).filter(cell => cell && cell.included !== true)
}

/** 逐格原句 -> 屏上清单。顺序就是响应里那些键的顺序，本件不重排、不补格。 */
export function absenceLines(cells) {
  return silentCells(cells).map(absenceCopy).filter(Boolean)
}

/* ==========================================================================
 * R388 · 生命周期那本账自己也会不供数：状态这一格的缺席走同一道闸、同一族句式
 * ======================================================================== *
 * 后端从 R388 起在响应里多交一格 state_ledger：{included, reason_code,
 * unknown_total, unknown_returned}（生产者 = app/notifications/inbox.py::build_inbox，
 * 形状与上面那台 sources 同族，键名逐枚见 docs/api/contract-v1.md R388 一节）。它说的是
 * 「谁读过、谁划掉过」这一本账今天答不答得上——客户机上 PG 没起、或 0016 没跑时答不上。
 *
 * 为什么这一格由本件读、而不并进上面那台台账：sources 的键集合等于后端 NOTIFICATION_SOURCES
 * 那三枚，由 __tests__/r385-ledger-contract.test.js 现读后端真源钉死（一枚不多一枚不少），
 * 把第四格塞进 LEDGER_LEGS 当场红。所以这里借的还是同一条闸（included 只认严格 true）与同一族
 * 句式（那一格的名字 + 那个原因的人话），只换尾巴那一句：它丢的不是「少了几条通知」，是
 * 「谁读过什么」这本账，员工要听到的是后者，不是「这些全是新的」。
 *
 * 判「答没答」的信号只有一个来源：响应里那一格。本件不猜、也不拿未读数反推（反推就是第二本
 * 账）；那一格整个缺席（旧后端）= 还不知道，一句字都不许多。它说「没答」时，逐行那枚「未读」
 * 也不许再画——那正是本单治的假话本身。
 * ======================================================================== */

/** 生命周期那一格在屏上叫什么。它不进 LEDGER_LEGS：那张表的键集合钉给后端那三枚源。 */
const STATE_LEG_NAME = '已读状态账本'

/** 尾巴换一句：这一格不供数丢的不是某一类事项，是「谁读过什么」这本账。 */
const STATE_LEG_TAIL = '。这一屏里的未读数数不清：读过、划掉过的都还可能在这里，不代表它们全都是新的。'

/**
 * 响应里那一格 -> 本件内部的读数。三条口径与 ledgerCells 同一把尺：只遍历真有的那一格、
 * included 只认严格 true（fail-closed）、整格缺席交回 null（那是「还不知道」，不是「没答」）。
 * 两枚 unknown_* 原样留着，本件一枚都不拿它们做徽标算术。
 */
export function stateLedgerCell(payload) {
  const cell = payload && typeof payload === 'object' ? payload.state_ledger : null
  if (!cell || typeof cell !== 'object' || Array.isArray(cell)) return null
  return {
    included: cell.included === true,
    reasonCode: ledgerText(cell.reason_code),
    unknownTotal: cell.unknown_total,
    unknownReturned: cell.unknown_returned,
  }
}

/** 这一格的屏上原句：答上了、或整格读不到，都交回空句。全件唯一一处拼这句话的地方（判据③）。 */
export function stateLedgerCopy(cell) {
  if (!cell || cell.included === true) return ''
  return STATE_LEG_NAME + LEDGER_HEAD + ledgerReasonCopy(cell.reasonCode) + STATE_LEG_TAIL
}

/** 逐行那枚「未读」还能不能说：只有那一格在场且说「没答」才是不能说；读不到不算知道。 */
export function stateWordsKnown(cell) {
  return cell === null || cell.included === true
}

/**
 * 台账数字的算术只在这一处（判据④）。两条不许：
 *   · 缺席格的 candidates / scanned 一枚都不进合计——那一格交回的 0 说的是「问不出」，
 *     不是「数出来是 0」，并进去就是替它宣布了一次数出来的结果；
 *   · 合计不参与徽标。徽标永远只读后端全集口径 unread_total（那是 normalizeInbox 的事）。
 * 数不出来的格子按未知处理并把 exact 落成 false：下界不许冒充精确数（契约 R299 同一条口）。
 */
export function ledgerSums(cells) {
  let candidates = 0
  let scanned = 0
  let answeredLegs = 0
  let silentLegs = 0
  let exact = true
  for (const cell of Array.isArray(cells) ? cells : []) {
    if (!cell) continue
    if (cell.included !== true) {
      silentLegs += 1
      continue
    }
    answeredLegs += 1
    const counted = typeof cell.candidates === 'number' && Number.isFinite(cell.candidates) && cell.candidates >= 0 ? Math.floor(cell.candidates) : null
    const looked = typeof cell.scanned === 'number' && Number.isFinite(cell.scanned) && cell.scanned >= 0 ? Math.floor(cell.scanned) : null
    if (counted === null || looked === null) exact = false
    candidates += counted === null ? 0 : counted
    scanned += looked === null ? 0 : looked
  }
  return { candidates, scanned, answeredLegs, silentLegs, exact }
}

/**
 * 读屏那一句的唯一装配口（判据②⑦）：lib 的 bellLabel 只管未读数那一半（它被钉冻结了，
 * 一个字都没改），这里把缺席那几句逐字并到后面。空清单时交回原句——一个字符都不多。
 */
export function bellAriaLabel(base, lines) {
  const notes = (Array.isArray(lines) ? lines : []).filter(Boolean)
  return notes.length ? base + '；' + notes.join('；') : base
}

/**
 * 一次读取 = 一个请求，交回两样东西：计数账（lib 算）与台账（本件解析）。见上方取证段。
 */
export async function readInboxPage() {
  const response = await http.get(INBOX_PATH, {
    params: { state: ALL_FILTER, limit: INBOX_PAGE_LIMIT, offset: 0 },
  })
  const payload = response && response.data
  const cells = ledgerCells(payload)
  const stateCell = stateLedgerCell(payload)
  // 状态那一格的话排在三格源账之后：本件不重排、不补格，只在末尾并上它自己那一句。
  const lines = absenceLines(cells)
  const stateNote = stateLedgerCopy(stateCell)
  if (stateNote) lines.push(stateNote)
  return {
    page: normalizeInbox(payload),
    absence: lines,
    ledger: ledgerSums(cells),
    stateLedger: stateCell,
  }
}

/**
 * 面板画哪一张脸的唯一出口（与 HitlPendingPanel.vue 的 pendingFace 同一形状）：
 * loading 优先，失败次之，只有两者都不在时才轮到「有没有行」。
 */
export function inboxFace({ loading = false, failure = null, rowCount = 0 } = {}) {
  if (loading) return 'loading'
  if (failure) return failure.face
  return Number(rowCount) > 0 ? 'list' : 'empty'
}

/** 一次读失败的成品卡：把错误对象一并留给原语的详情区（后端原文唯一的渲染出口在 error-detail.js）。 */
function readFailureCard(err) {
  const view = isShapeFailure(err) ? shapeFailureViewOf() : readFailureViewOf(err)
  return { ...view, rawError: err, detail: errorDetail(err, view.description) }
}

/**
 * 焦点落点：组件实例给的是 $el，普通元素给的是自己；拿不到可聚焦目标就什么都不做，
 * 绝不为了「看起来像有焦点」去猜一个别的选择器（本仓没有 DOM 可查）。
 */
export function focusTarget(target) {
  const node = target && target.$el ? target.$el : target
  if (node && typeof node.focus === 'function') node.focus()
  return Boolean(node && typeof node.focus === 'function')
}

/** Esc 之外一律不动作：面板里没有输入框，但将来加了也不该被这一格抢走清空语义（判据⑦）。 */
export function closeKeyAction(event) {
  if (!event || event.defaultPrevented === true) return false
  return shouldCloseOnKey(event.key, event.target && event.target.tagName)
}
</script>

<script setup>
import { computed, nextTick, onMounted, shallowRef } from 'vue'

// 模板要用的原语必须在 <script setup> 里 import：普通 <script> 的绑定进不了 setupState，
// 放在那里模板只会解析不到组件、静默画出一枚不认识的标签（本单实撞过一次，这条不是猜的）。
import UiButton from './ui/UiButton.vue'
import UiEmptyState from './ui/UiEmptyState.vue'
import UiErrorState from './ui/UiErrorState.vue'
import UiLoadingState from './ui/UiLoadingState.vue'

const inbox = shallowRef(null)
const rows = shallowRef([])
// R385 判据②：那台缺席台账的两格派生值。初值【空】就是「还不知道」——
// 「还没读到」不是「有一格没答」，所以这一格既不常驻，也不许在正常态长出一句「系统正常」。
const absence = shallowRef([])
const ledger = shallowRef(null)
// R388：状态那一格答没答，是逐行那枚「未读」的唯一依据；null = 还不知道（旧后端同此）。
const stateLedger = shallowRef(null)
// 初值就是在读：一次都没读过的时候，这一格不配替后端宣布「没有通知」（判据③⑥的命门）。
const loading = shallowRef(true)
const failure = shallowRef(null)
const writeFailure = shallowRef(null)
const busy = shallowRef('')
const open = shallowRef(false)

const bellEl = shallowRef(null)
const panelEl = shallowRef(null)

// 徽标与读屏句子的数字出处只有一个：后端全集未读。inbox 为 null 就是「未知」，不是 0。
const unread = computed(() => (inbox.value ? inbox.value.unread : null))
const isExact = computed(() => Boolean(inbox.value && inbox.value.isExact))
// 判「这一屏还能不能说未读」只看响应里那一格，不拿未读数反推（反推=第二本账）。
const stateUnknown = computed(() => !stateWordsKnown(stateLedger.value))
const badge = computed(() => badgeText(unread.value, { isExact: isExact.value }))
// 徽标只看 unread / isExact 这两格，台账一格都不参与（判据④）：缺席只往读屏里加句子，绝不动数字。
const ariaLabel = computed(() => bellAriaLabel(
  bellLabel(unread.value, { isExact: isExact.value, failed: Boolean(failure.value) }),
  absence.value,
))
const summary = computed(() => panelSummary(inbox.value))
const face = computed(() => inboxFace({ loading: loading.value, failure: failure.value, rowCount: rows.value.length }))
const hasUnread = computed(() => unread.value !== null && unread.value > 0)

async function refresh() {
  loading.value = true
  failure.value = null
  try {
    const read = await readInboxPage()
    const page = read.page
    inbox.value = page
    rows.value = page.rows
    absence.value = read.absence
    ledger.value = read.ledger
    stateLedger.value = read.stateLedger === undefined ? null : read.stateLedger
  } catch (err) {
    // 读不到就承认读不到：旧数字一律清掉，不许留着上一轮的读数冒充这一次。
    inbox.value = null
    rows.value = []
    absence.value = []
    ledger.value = null
    stateLedger.value = null
    failure.value = readFailureCard(err)
  } finally {
    loading.value = false
  }
}

async function openPanel() {
  open.value = true
  writeFailure.value = null
  await nextTick()
  focusTarget(panelEl.value)
  if (!loading.value) await refresh()
}

function closePanel() {
  if (!open.value) return
  open.value = false
  focusTarget(bellEl.value)
}

async function togglePanel() {
  if (open.value) {
    closePanel()
    return
  }
  await openPanel()
}

async function onKeydown(event) {
  if (!open.value || !closeKeyAction(event)) return
  if (typeof event.preventDefault === 'function') event.preventDefault()
  closePanel()
}

/**
 * 一次写的收尾一律是【再读一次后端】：徽标的数字只可能由那一次读决定。
 * changed 为真为假都不在这里做减法（判据④：第 N 次点同一枚时后端回 changed=false，
 * 全集未读没动，重读回来的还是同一个数——用例把这条钉成红/绿两态）。
 */
async function afterWrite() {
  await refresh()
}

async function markOne(row, action) {
  const id = row && row.id ? row.id : ''
  if (!id || busy.value) return null
  busy.value = id
  writeFailure.value = null
  try {
    const receipt = action === 'dismiss' ? await dismissNotifications([id]) : await markRead([id])
    await afterWrite()
    return receipt
  } catch (err) {
    writeFailure.value = writeFailureView(err)
    await afterWrite()
    return null
  } finally {
    busy.value = ''
  }
}

async function markEverything() {
  if (busy.value) return null
  busy.value = 'all'
  writeFailure.value = null
  try {
    const receipt = await markAllUnread()
    await afterWrite()
    return receipt
  } catch (err) {
    writeFailure.value = writeFailureView(err)
    await afterWrite()
    return null
  } finally {
    busy.value = ''
  }
}

onMounted(() => {
  // 徽标要在人点开之前就有数，所以挂载读一次——今天读得起，因为 R299 交回的是全集口径而不是页内长度。
  refresh()
})

defineExpose({
  absence,
  ariaLabel,
  bellEl,
  badge,
  busy,
  closePanel,
  face,
  failure,
  inbox,
  ledger,
  loading,
  markEverything,
  markOne,
  onKeydown,
  open,
  openPanel,
  panelEl,
  refresh,
  rows,
  summary,
  togglePanel,
  unread,
  writeFailure,
})
</script>

<template>
  <div class="notif" data-testid="notification-bell">
    <UiButton
      ref="bellEl"
      class="notif__bell"
      variant="ghost"
      size="sm"
      type="button"
      :aria-label="ariaLabel"
      :title="ariaLabel"
      aria-haspopup="dialog"
      aria-controls="notification-panel"
      :aria-expanded="open ? 'true' : 'false'"
      data-testid="notification-trigger"
      @click="togglePanel"
      @keydown="onKeydown"
    >
      <template #icon>
        <svg class="notif__icon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M6 9a6 6 0 0 1 12 0c0 4 1.4 5.6 2 6.4H4c.6-.8 2-2.4 2-6.4Z" />
          <path d="M10 19a2 2 0 0 0 4 0" />
        </svg>
      </template>
      <span v-if="badge" class="notif__badge" data-testid="notification-badge" aria-hidden="true">{{ badge }}</span>
      <span v-else-if="failure" class="notif__marker" aria-hidden="true">!</span>
    </UiButton>

    <section
      v-if="open"
      id="notification-panel"
      ref="panelEl"
      class="notif__panel"
      role="dialog"
      :aria-label="ariaLabel"
      tabindex="-1"
      data-testid="notification-panel"
      @keydown="onKeydown"
    >
      <header class="notif__head">
        <h2 class="notif__title">{{ PANEL_TITLE }}</h2>
        <p class="notif__summary">{{ summary }}</p>
        <UiButton
          class="notif__close"
          variant="ghost"
          size="sm"
          type="button"
          aria-label="关闭通知"
          data-testid="notification-close"
          @click="closePanel"
        >×</UiButton>
      </header>

      <p v-if="writeFailure" class="notif__note" role="status" data-testid="notification-write-note">
        {{ writeFailure.title }}：{{ writeFailure.description }}
      </p>

      <!-- R385 判据②③④：这一格说的是「哪本账没答」，不是「有没有通知」，两脸分开画。
           句子逐字出自本件上面那两张表（LEDGER_LEGS 与 LEDGER_CAUSES），这里不写第二份；
           中性色 + role="status"（不是 role="alert"）：不许把员工吓走，也不许打断读屏。
           它在面板自己的 grid 里占一行（下面那条 list/empty 被推着走），不遮正文（判据⑦）。
           data-ledger-* 是台账自己的算术，只合计答上了的那几格，只给机器读，不占人话位。 -->
      <ul
        v-if="absence.length"
        class="notif__note notif__ledger"
        role="status"
        data-testid="notification-ledger"
        :data-ledger-silent="absence.length"
        :data-ledger-candidates="ledger ? ledger.candidates : ''"
      >
        <li
          v-for="(line, index) in absence"
          :key="'ledger-' + index"
          class="notif__ledger-item"
          data-testid="notification-ledger-item"
        >{{ line }}</li>
      </ul>

      <UiLoadingState
        v-if="face === 'loading'"
        dense
        :rows="3"
        label="正在读取通知"
      />
      <UiErrorState
        v-else-if="failure"
        dense
        :title="failure.title"
        :description="failure.description"
        :code-label="failure.codeLabel"
        :raw-error="failure.rawError"
        :retryable="failure.retryable"
        :busy="loading"
        retry-text="重新加载"
        @retry="refresh"
      />
      <UiEmptyState
        v-else-if="face === 'empty'"
        dense
        :title="EMPTY_TITLE"
        :description="EMPTY_DESCRIPTION"
      />
      <ul v-else class="notif__list" data-testid="notification-list">
        <li v-for="row in rows" :key="row.id" class="notif__row" data-testid="notification-row">
          <p class="notif__row-title">{{ row.title }}</p>
          <p v-if="row.detail" class="notif__row-detail">{{ row.detail }}</p>
          <p class="notif__row-meta">
            <span v-if="row.createdAt">{{ row.createdAt }}</span>
            <!-- R388：状态那本账没答时，「未读」这两个字没有依据，宁可不画。 -->
            <span v-if="!row.read && !stateUnknown" class="notif__row-state">未读</span>
          </p>
          <div class="notif__row-actions">
            <UiButton
              v-if="!row.read"
              variant="secondary"
              size="sm"
              type="button"
              label="标为已读"
              :loading="busy === row.id"
              :disabled="Boolean(busy) && busy !== row.id"
              :aria-label="row.title + '：标为已读'"
              data-testid="notification-mark-read"
              @click="markOne(row, 'read')"
            />
            <UiButton
              variant="ghost"
              size="sm"
              type="button"
              label="划掉"
              :loading="busy === row.id"
              :disabled="Boolean(busy) && busy !== row.id"
              :aria-label="row.title + '：划掉这条通知'"
              data-testid="notification-dismiss"
              @click="markOne(row, 'dismiss')"
            />
          </div>
        </li>
      </ul>

      <footer v-if="face === 'list' || face === 'empty'" class="notif__foot">
        <UiButton
          variant="secondary"
          size="sm"
          type="button"
          label="全部标为已读"
          :loading="busy === 'all'"
          :disabled="!hasUnread"
          data-testid="notification-mark-all"
          @click="markEverything"
        />
      </footer>
    </section>
  </div>
</template>

<style scoped>
.notif {
  position: relative;
}

.notif__bell {
  position: relative;
  width: var(--control-h-sm);
  min-height: var(--control-h-sm);
  padding: 0 var(--s-2);
  color: var(--text-2);
  border-radius: var(--r-sm);
}

.notif__bell:hover {
  color: var(--accent-hover);
}

.notif__icon {
  display: block;
}

.notif__badge {
  position: absolute;
  top: -2px;
  right: -2px;
  min-width: 16px;
  padding: 0 4px;
  color: var(--text-invert);
  background: var(--danger);
  border-radius: var(--r-pill);
  font-size: var(--t-xs);
  font-weight: 700;
  line-height: 16px;
  text-align: center;
}

.notif__marker {
  position: absolute;
  top: -2px;
  right: -2px;
  color: var(--danger);
  font-size: var(--t-xs);
  font-weight: 700;
}

.notif__panel {
  position: absolute;
  top: var(--s-6);
  right: 0;
  z-index: var(--z-dropdown);
  display: grid;
  gap: var(--s-2);
  width: 360px;
  max-width: 90vw;
  padding: var(--s-4);
  background: var(--surface-2);
  border: 1px solid var(--border-2);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-2);
}

.notif__head {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: start;
  gap: var(--s-2);
}

.notif__title {
  margin: 0;
  color: var(--text-1);
  font-size: var(--t-md);
  font-weight: 700;
}

.notif__summary {
  grid-column: 1;
  margin: 0;
  color: var(--text-3);
  font-size: var(--t-xs);
}

.notif__close {
  grid-column: 2;
  grid-row: span 2;
  width: var(--control-h-sm);
  min-height: var(--control-h-sm);
  padding: 0;
  color: var(--text-2);
  font-size: var(--t-lg);
}

.notif__note {
  margin: 0;
  padding: var(--s-2);
  color: var(--text-1);
  background: var(--surface-3);
  border-left: 3px solid var(--warning);
  border-radius: var(--r-sm);
  font-size: var(--t-xs);
}

/* 只借上面那条既有 .notif__note 的底色与警示边：本块一个新色值都不开（判据⑤色值预算）。
   刻意不用 position:absolute —— 面板是 grid，这一行走位，把下面的清单往下推，不遮正文。 */
.notif__ledger {
  display: grid;
  gap: var(--s-1);
  margin: 0;
  padding: var(--s-2);
  list-style: none;
}

.notif__ledger-item {
  margin: 0;
  color: var(--text-1);
  font-size: var(--t-xs);
}

.notif__list {
  display: grid;
  gap: var(--s-3);
  margin: 0;
  padding: 0;
  list-style: none;
}

.notif__row {
  display: grid;
  gap: var(--s-1);
  padding-bottom: var(--s-3);
  border-bottom: 1px solid var(--border-1);
}

.notif__row:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.notif__row-title {
  margin: 0;
  color: var(--text-1);
  font-size: var(--t-sm);
}

.notif__row-detail {
  margin: 0;
  color: var(--text-2);
  font-size: var(--t-xs);
}

.notif__row-meta {
  display: flex;
  gap: var(--s-2);
  margin: 0;
  color: var(--text-3);
  font-size: var(--t-xs);
}

.notif__row-state {
  color: var(--accent);
}

.notif__row-actions {
  display: flex;
  gap: var(--s-2);
}

.notif__foot {
  display: flex;
  justify-content: flex-end;
  gap: var(--s-2);
}
</style>


