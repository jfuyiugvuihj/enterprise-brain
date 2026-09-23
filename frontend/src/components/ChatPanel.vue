<script>
/**
 * R174 · 冷启动深链：`/chat?session=<会话号>&request=<轮号>` 要落到那一轮
 *
 * 一句话：同事把链接发过来，打开的人看到的就该是那一轮，而不是登录页、也不是最新一轮。
 * 这件事今天做不到 —— 本面板原先只读 `?lane=` 那一枚参数（R141 的落点），session / request
 * 两枚写进地址就没人读（R168 的 chatAnchor 一直在往地址上挂它们，落点却是空的）。
 *
 * 为什么这一段纯逻辑住在普通 <script> 块里（与 hitl/HitlPendingRow.vue 同一写法）：
 * 深链的四种落不到只有交给真函数跑得一遍才算验过 —— 放在 <script setup> 里，node +
 * @vue/server-renderer 既拿不到 ref 也等不到 promise，测试就只能去扫源码，那是自欺。
 * 状态机本身不碰网络也不碰 DOM：读正文、切会话、交回 store 三件事一律由调用方递进来，
 * 所以用例调的就是面板自己调的那一枚函数，不是它的副本。
 */
import {
  adoptBackendSession,
  DEEP_LINK_ID_RE,
  localMessagesOf,
  readBackendSession,
  SESSION_READ,
} from '../lib/sessions'

/**
 * 深链那两枚参数的形状就是 lib/sessions.js 的 DEEP_LINK_ID_RE 那一枚：地址里的写法与后端认的
 * 写法必须只有一本账，所以这里是 import 而不是再抄一遍正则（普通 <script> 块与 <script setup>
 * 同属一个模块作用域，HitlPendingPanel.vue 同此写法）。后端两枚 id 都在十六进制族里：
 * uuid hex / req-<hex> / 本地 genId 的 base36。
 */
export const DEEP_ID_SHAPE = DEEP_LINK_ID_RE

/**
 * 每一张脸：blocking = 这一屏下面什么都不该画（连别人正在看的那条会话也不该顶上来）；
 * retry = 只给「再问一次后端有可能换个结果」的那一张，无权与「没有」都不给重试（判据④）。
 *
 * 九句两两不同（判据①第 4 件要分的四类，加上今天真的分得出来的另几类）：
 *   四类里「后端读不到」= unreachable 那一句，「不是你的」= not_yours，
 *   「这一轮不存在」= turnMissing，「参数缺失或格式不对」= bad-session / bad-request 两句。
 *   noTurnIds 那一句是 R174 实取后端之后多出来的一格：它既不是「没有这一轮」也不是「读不到」，
 *   而是「后端把正文给了、但正文里没有轮号可对」，所以它单独占一张脸，不与任何一张并格。
 */
export const DEEP_LINK_FACES = {
  'bad-session': {
    blocking: true, tone: 'warn', retry: false,
    text: '这条链接没带会话号，或会话号的写法系统认不出来，所以这一屏不知道该打开哪一条 —— 就没有打开任何东西。',
  },
  'bad-request': {
    blocking: false, tone: 'warn', retry: false,
    text: '链接里的轮号写法系统认不出来（会话号是好的）：这一条会话照旧打开，但没有定位到某一轮。',
  },
  [SESSION_READ.notFound]: {
    blocking: true, tone: 'error', retry: false,
    text: '后端给了确定回答：没有这一条会话。要留意它的口径 —— 归属对不上时后端也回同一句（见交付说明的 B 单），'
      + '所以这一句不能排除「它属于别人」；但它是后端读回来了的答案，不等于「读不到」。',
  },
  [SESSION_READ.notYours]: {
    blocking: true, tone: 'error', retry: false,
    text: '这一条不是你的：后端认出现在这个身份看不着它（没登录或没这份权限），所以正文没交出来。'
      + '先登录对上的那个账号，或找管理员开权限 —— 反复点这条链接不会把它变出来。',
  },
  [SESSION_READ.unreachable]: {
    blocking: true, tone: 'error', retry: true,
    text: '后端这会儿读不到（连接没建立，或服务回了 5xx）。这不代表那一轮不存在，也不代表这条会话没有：'
      + '只是这一屏没拿到答案，等服务通了再问一次。',
  },
  [SESSION_READ.badBody]: {
    blocking: true, tone: 'error', retry: false,
    text: '后端回话了，但这一格的形状系统不认识（读不到 messages 那一列）。系统没有把它当成「这条会话是空的」：'
      + '那是两回事，认不出形状就说认不出。',
  },
  noTurnIds: {
    blocking: false, tone: 'warn', retry: false,
    text: '这一条会话的正文读到了，但正文里的每一轮都没带轮号，所以「是哪一轮」这件事在这一屏对不上号。'
      + '这不是「没有这一轮」：会话就在下面，只是没法替你把那一轮挑出来 —— 缺的是后端那一格，已具名报总控。',
  },
  turnMissing: {
    blocking: false, tone: 'error', retry: false,
    text: '这一轮不存在：这一条会话里每一轮都带着轮号，其中没有链接上写的那个。'
      + '可能是那一轮被删了，也可能是链接抄错了；下面打开的是这一条会话本身。',
  },
  sessionOnly: {
    blocking: false, tone: 'info', retry: false,
    text: '这条链接只指到会话、没指到某一轮，所以下面打开的是整条对话。',
  },
}

const deepIdOf = value => (
  typeof value === 'string' && DEEP_ID_SHAPE.test(value.trim()) ? value.trim() : ''
)

/** 地址里那两枚参数 → 一次落点请求。没写这两枚就不是深链（返回 null，正常进这一屏）。 */
export function deepLinkFromQuery(query) {
  const bag = query && typeof query === 'object' ? query : {}
  if (bag.session === undefined && bag.request === undefined) return null
  const session = deepIdOf(bag.session)
  if (!session) return { session: '', request: '', bad: 'bad-session' }
  if (bag.request === undefined) return { session, request: '', bad: '' }
  const request = deepIdOf(bag.request)
  // 轮号写坏了但会话号是好的：不整条链接一起作废，会话照开，只多说一句轮号不认。
  if (!request) return { session, request: '', bad: 'bad-request' }
  return { session, request, bad: '' }
}

const turnIdOf = row => {
  if (!row || typeof row !== 'object') return ''
  const value = row.requestId === undefined || row.requestId === null || row.requestId === ''
    ? row.request_id
    : row.requestId
  return typeof value === 'string' ? value.trim() : ''
}

/**
 * 在一份消息里找那一轮。只按字面比轮号，一次模糊匹配都不做（位次、时间、内容长度全都不算证据）。
 * hasIds 单独报出来：整份都没轮号时，「找不到」这句话就不许说成「这一轮不存在」。
 */
export function locateDeepTurn(list, requestId) {
  const rows = Array.isArray(list) ? list : []
  const wanted = typeof requestId === 'string' ? requestId.trim() : ''
  const ids = rows.map(turnIdOf).filter(Boolean)
  return {
    hasIds: ids.length > 0,
    found: Boolean(wanted) && ids.indexOf(wanted) >= 0,
    index: wanted ? rows.findIndex(row => turnIdOf(row) === wanted) : -1,
  }
}

/** 一次「后端有没有这一条」的读数 → 该说哪一句。认得的四种各一张脸，认不出的不许并成「没有」。 */
export function deepLinkFaceOfRead(read) {
  const outcome = read && typeof read === 'object' ? String(read.outcome || '') : ''
  // 正文到手不是一张脸：它是「接着往下走」的那一态，所以 found 要在这里就被摘出去。
  if (outcome === SESSION_READ.found) return ''
  return Object.prototype.hasOwnProperty.call(DEEP_LINK_FACES, outcome) ? outcome : SESSION_READ.badBody
}

/**
 * 「这一轮到底在哪」的结论只算一次：本机那条路与后端那条路都汇到这里，两腿不各写一套判定
 * （判据①第 2 件的原话是两条路落到同一份 store，这里落到的是同一份结论）。
 */
export function concludeDeepTurn(link, list, from) {
  const base = { face: '', session: link.session, request: link.request, turn: -1, from }
  if (!link.request) {
    // 轮号写坏了与会话号没问题：都不该假装定位到了某一轮，各说一句各的事。
    return { ...base, state: 'session', face: link.bad === 'bad-request' ? 'bad-request' : 'sessionOnly' }
  }
  const at = locateDeepTurn(list, link.request)
  if (!at.hasIds) return { ...base, state: 'session', face: 'noTurnIds' }
  if (!at.found) return { ...base, state: 'session', face: 'turnMissing' }
  return { ...base, state: 'turn', turn: at.index }
}

/**
 * 本地那一腿：判据①第 1 件要的是「本机有这一条就直接定位」，一次请求都不该发，
 * 所以它必须是同步的 —— 冷启动的第一帧就能画出结论，而不是先闪一下别人的最新一条。
 * 返回 null = 本机没有这一条，得交给后端那一腿。
 *
 * deps 三件都是面板递进来的真通道，本文件不自己碰网络也不自己碰 DOM：
 *   localMessages(id) 本机 store 里这一条的正文（lib/sessions.js::localMessagesOf）
 *   readSession(id)   本机没有时向后端取正文（lib/sessions.js::readBackendSession）
 *   adopt(id, list)   取到的正文交回【同一份】store（lib/sessions.js::adoptBackendSession）
 *   switchTo(id)      站内点击与冷启动共用的那一次切换（lib/sessions.js::switchSession）
 */
export function resolveLocalDeepLink(deps = {}) {
  const link = deepLinkFromQuery(deps.query)
  if (!link) return { state: 'none', face: '', session: '', request: '', turn: -1, from: '' }
  if (link.bad === 'bad-session') {
    return { state: 'face', face: 'bad-session', session: '', request: '', turn: -1, from: '' }
  }
  const list = typeof deps.localMessages === 'function' ? deps.localMessages(link.session) : null
  if (!Array.isArray(list)) return null
  if (typeof deps.switchTo === 'function') deps.switchTo(link.session)
  return concludeDeepTurn(link, list, 'local')
}

/** 后端那一腿：本机没有这一条时，先向后端问「这一条你那儿有正文吗」，再走同一枚结论。 */
export async function resolveDeepLinkWith(deps = {}) {
  const local = resolveLocalDeepLink(deps)
  if (local && local.state !== 'none') return local
  const link = deepLinkFromQuery(deps.query)
  if (!link || link.bad === 'bad-session') return local
  const read = typeof deps.readSession === 'function' ? await deps.readSession(link.session) : null
  const face = deepLinkFaceOfRead(read)
  if (face) return { state: 'face', face, session: link.session, request: link.request, turn: -1, from: 'backend' }
  if (!Array.isArray(read.messages)) {
    return { state: 'face', face: SESSION_READ.badBody, session: link.session, request: link.request, turn: -1, from: 'backend' }
  }
  // 交回同一份 store 之后再定位：站内点击与冷启动看的、滚的、标的都是 store 里这一份。
  if (typeof deps.adopt === 'function') deps.adopt(link.session, read.messages)
  // 两条路共用同一次切换落在同一份 store 上（后端那一腿 adopt 已经把它设成当前这条，
  // 这里再走一次是同一枚 switchSession，不是第二条落点通道）。
  if (typeof deps.switchTo === 'function') deps.switchTo(link.session)
  return concludeDeepTurn(link, read.messages, 'backend')
}

/** 那一轮在屏上的锚点：每一行都带位次，被点中的那一行另外带一枚 target 标记。 */
export function deepTurnSelector(index) {
  return `[data-turn="${Number(index)}"]`
}

/**
 * 滚动这一件事拆成可单测的纯函数：传进来的是一个「有 querySelector 的容器」，
 * node 里给它一枚假容器就能真验「找的是哪一行、滚没滚」，不必等 jsdom。
 * 找不到那一行时返回 found:false —— 面板不猜位置，也不静默滚到最新一条。
 */
export function revealDeepTurnIn(container, index) {
  const selector = deepTurnSelector(index)
  if (!container || typeof container.querySelector !== 'function') {
    return { found: false, scrolled: false, selector }
  }
  const target = container.querySelector(selector)
  if (!target) return { found: false, scrolled: false, selector }
  const top = Math.max(0, (Number(target.offsetTop) || 0) - 12)
  if (typeof container.scrollTo === 'function') container.scrollTo({ top, behavior: 'smooth' })
  else container.scrollTop = top
  return { found: true, scrolled: true, selector, top }
}

/**
 * 面板用到的那张接线表（本地正文 / 向后端取正文 / 交回 store / 切会话）。
 * 它单独成为一枚函数只为了一件事：用例吃的必须就是面板自己用的这一份，而不是照着抄的副本 ——
 * 否则「把向后端取正文那一腿摘掉」只会红在源码钉上，红不到跨机器回看那条行为。
 * 面板这一侧只是换个人来填同一张表，落点路径一字未改。
 */
export function buildDeepDeps(query) {
  return {
    query,
    localMessages: localMessagesOf,
    readSession: readBackendSession,
    adopt: adoptBackendSession,
    switchTo: switchSession,
  }
}
</script>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import CacheFace from './CacheFace.vue'
import ChartViewer from './ChartViewer.vue'
import DocumentPreviewModal from './DocumentPreviewModal.vue'
import QueueFace from './QueueFace.vue'
import SourceCard from './SourceCard.vue'
import { fetchRuntimeHealth, modelState, modelStatusText } from '../lib/health.js'
import {
  abortStream,
  activeDataFilename,
  activeId,
  beginStream,
  consumeSseStream,
  endStream,
  ensureSession,
  flush,
  friendlyErrorText,
  genId,
  hitl,
  loadSessions,
  loading,
  messages,
  newSession,
  persist,
  rememberScroll,
  removeSession,
  restoreActive,
  scrollOffset,
  scrollTo,
  sessions,
  switchSession,
  syncActive,
} from '../lib/sessions'
import { authedFetch, errorDetail, http } from '../lib/http'
import { errorCodeLabel, errorCodeOf, normalizeError } from '../lib/errcodes'
import {
  cacheFace,
  queueFace,
  queuePollFailedFace,
  queueRejectedFace,
  queueStatsFace,
  revisionsAfter,
  sourcesFace,
} from '../lib/provenance'
import { UiEmptyState, UiErrorState } from './ui'
import { LANE_CHOICES, LANE_UNDECLARED, laneFromQuery, queryWithLane } from '../router/lane-choice.js'

const input = ref('')
const chatEl = ref(null)
const sidebarOpen = ref(true)
const cancelPhase = ref('idle')
const streamNote = ref('')
const noteTone = ref('info')

// ==================== R141 · 档位选择器（选了必须真的改行为） ====================
//
// 这枚控件今天才准上屏：R32 那次拒交的原话是「要让标签真改变行为须动 nodes.py 与
// orchestrator.py，两者皆在写域外」。R141 把那一格补齐了（天花板/地板/读数三件事都在
// tests/test_r141_lane_behavior.py 里成了行为用例），所以下面这根控件有权存在。
//
// 三件事缺一条就是假控件：① 发出去真的带这一格（send 的 body）；② 选中项写进地址，
// 刷新与转发都留得住；③ 每一轮画回**生效读数**——读不到就不画，绝不用选择框代替证据。
//
// 值那张表在 ../router/lane-choice.js（含「为什么不发明第四种拼写」的理由），本面板不抄第二份；
// 空串＝不声明，服务端按 R42 判别器以题面自选，那一格在读数里叫「系统判的」。
// 响应头是这一腿唯一的读数来源：SSE 帧的解析住在 lib/sessions.js（本单写域之外），
// 而 request.started 的 data 今天到不了这里。头名逐字对齐 app/api/v1/chat.py 的三枚常量。
const LANE_HEADER_EFFECTIVE = 'x-effective-lane'
const LANE_HEADER_SOURCE = 'x-lane-source'
const LANE_HEADER_DECLARED = 'x-declared-lane'
const LANE_NAMES = { qa: '问答档', analysis: '分析档', report: '报告档' }
// 档位在界面上的承诺，与 nodes.LANE_WORKERS 那张表同一方向（只写人话，不写腿名清单）：
// 读的是「选了会怎样」，不是替后端宣布它跑了什么。
const LANE_PROMISES = {
  '': '按问题内容自动挑一条最省的路',
  qa: '只查知识库回答，不算数、不出图、不产文件',
  analysis: '允许进数据分析与图表，但不产文件',
  report: '一定走导出这一腿（会先请你确认）',
}

// 路由在这里是**可选**的：组件被单测裸渲染（renderToString，无 router 上下文）时
// useRoute()/useRouter() 返回 undefined，全部访问点都走可选链，读不到就当地址没写。
const route = useRoute()
const router = useRouter()

const laneFromAddress = () => laneFromQuery(route?.query)
const selectedLane = ref(laneFromAddress())
// 地址是真相：从别的屏带 ?lane= 跳进来、或后退回这一屏时，选择框跟着地址走。
watch(() => route?.query?.lane, () => { selectedLane.value = laneFromAddress() })

function chooseLane(value) {
  selectedLane.value = queryWithLane({}, value).lane ?? LANE_UNDECLARED
  router?.replace({ query: queryWithLane(route?.query, selectedLane.value) })
}

/**
 * 本轮档位读数（响应头那三枚）。没有读数就整条不画——留白不等于「系统判断」，
 * 更不等于后端没实现：它可能只是被网关吃掉了头，那种情况下界面不许编一句。
 *
 * 与出处/缓存/排队那三张脸同一形状：bag 里那份管重渲染，消息对象上那份管随会话
 * 落盘与刷新复原（档位住在地址里，读数住在这一轮的答案上，两件事各自留痕）。
 */
const laneReads = ref({})

function readLaneHeaders(turn, msg, response) {
  const header = (name) => (
    typeof response?.headers?.get === 'function' ? response.headers.get(name) || '' : ''
  )
  const read = {
    lane: header(LANE_HEADER_EFFECTIVE),
    source: header(LANE_HEADER_SOURCE),
    declared: header(LANE_HEADER_DECLARED),
    observed: true,
  }
  laneReads.value = storeBag(laneReads, turn, read)
  if (msg) msg.lane = read
  return read
}

// 会话与消息存在模块级 store 里：面板卸载或切走再回来都不会丢，生成中的流也不会断。
const sessionId = activeId

// ==================== R174 · 冷启动深链落到那一轮 ====================
//
const deepDeps = buildDeepDeps(route?.query)

/** 落点结论到手之后才谈得上滚动：nextTick 等 DOM 就位，交完活把结果原样带回去。 */
async function revealDeepTurn(result) {
  if (!result || result.state !== 'turn') return result
  await nextTick()
  revealDeepTurnIn(chatEl.value, result.turn)
  return result
}

/**
 * 不用发一个请求就能定下来的那部分，全部在这里算完（判据①第 1 件）：
 * 本机有这一条 → 直接给出结论（命中那一轮 / 这一轮不存在 / 这一份没轮号可对）；
 * 本机没有 → 只给 'reading' 那一态。'reading' 不许省：向后端问话的这段时间里，
 * 屏上既不许是空白，也不许把别人上次看的那一条当成链接的落点画出来。
 * loadSessions() 读的是盘上那份，不发请求，所以它有权在这里跑一次。
 */
function deepOpening() {
  const query = route?.query
  deepDeps.query = query
  const link = deepLinkFromQuery(query)
  if (!link) return null
  if (!sessions.value.length) loadSessions()
  const local = resolveLocalDeepLink(deepDeps)
  if (local) return local.state === 'none' ? null : local
  return { state: 'reading', face: '', session: link.session, request: link.request, turn: -1, from: 'backend' }
}

/** setup 期就把这一格算完：SSR 与客户端同一条路，冷启动第一帧就有结论。 */
const deepLink = ref(deepOpening())

/** 本地定不下来时才发那一枪；结论回来后换掉 'reading'，再滚到点中的那一行。 */
function applyDeepLink() {
  deepLink.value = deepOpening()
  const opening = deepLink.value
  if (opening && opening.state === 'reading') {
    return resolveDeepLinkWith(deepDeps).then(result => {
      deepLink.value = result
      return revealDeepTurn(result)
    })
  }
  return revealDeepTurn(opening)
}

const deepFace = computed(() => {
  const state = deepLink.value
  return state && state.face ? DEEP_LINK_FACES[state.face] || null : null
})
// 这一屏下面还画不画会话：链接还没落到可看的东西之前一律先盖住 —— 拿另一条会话补位
// 就是判据①明令不许的「静默落到最新一轮」，一片空白也不许。
const deepBlocked = computed(() => {
  const state = deepLink.value
  if (!state) return false
  if (state.state === 'reading') return true
  return state.state === 'face' && Boolean(deepFace.value && deepFace.value.blocking)
})
const deepTurn = computed(() => (deepLink.value && deepLink.value.state === 'turn' ? deepLink.value.turn : -1))
const deepBadge = computed(() => {
  const state = deepLink.value
  if (!state || state.state !== 'turn') return ''
  return state.from === 'backend'
    ? '就是这一轮 · 正文由后端读回（这台浏览器原先没有这一条会话）'
    : '就是这一轮 · 由链接定位'
})

// 地址里那两枚参数变了就重新落一次点：站内点待办的「回到这一轮」、回退、转发都走这条路。
// 盯的是这两枚拼出来的一枚串而不是数组：换档位（?lane=）也会换掉 query 对象，
// 拿数组比就每次都判成「变了」，把同一枪对着后端重复发。
watch(() => `${route?.query?.session ?? ''}|${route?.query?.request ?? ''}`, () => { applyDeepLink() })


function note(text, tone = 'info') {
  streamNote.value = text
  noteTone.value = tone
}

// ==================== 会话管理 ====================

function formatTime(ts) {
  const d = new Date(ts)
  const diff = Date.now() - d
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前'
  if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前'
  return (d.getMonth() + 1) + '/' + d.getDate()
}

async function deleteSession(id) {
  if (!confirm('删除此会话？')) return
  try {
    await removeSession(id)
  } catch (err) {
    note(`会话未能从服务端删除：${err.message || err}`, 'error')
  }
  await scrollBottom()
}

// ==================== 图表解析 ====================

// 图表以 ![标题](/api/v1/artifacts/<id>/content) 的形式出现在回答里，该地址需要携带 Bearer
// 头才能取回，所以匹配范围必须覆盖 artifact 相对地址；/static/ 保留给历史会话。
const CHART_IMAGE_PATTERN = /!\[([^\]]*)\]\(((?:\/(?:static|api\/v1)\/|v1\/artifacts\/|artifacts\/)[^)]+)\)/g

function parseCharts(content) {
  const charts = []
  if (!content) return charts
  const re = new RegExp(CHART_IMAGE_PATTERN.source, 'g')
  let m
  while ((m = re.exec(content)) !== null) {
    charts.push({ caption: m[1], src: m[2] })
  }
  return charts
}

function stripChartMarkers(content) {
  if (!content) return content
  return content.replace(new RegExp(CHART_IMAGE_PATTERN.source, 'g'), '')
}

// ==================== 聊天 ====================

function onChatAsk(e) {
  const detail = e.detail
  const query = typeof detail === 'string' ? detail : detail?.query
  if (!query) return
  activeDataFilename.value = typeof detail === 'string'
    ? activeDataFilename.value
    : detail?.filename || activeDataFilename.value
  input.value = query
  send(activeDataFilename.value)
}


// 面板被 v-show 常驻，切工作区不会触发卸载钩子，所以「切走时写回 scrollTop」这条路
// 以前是断的：整页刷新后位置就丢。改成滚动本身去抖写回，与切页时机解耦。
let scrollSaveTimer = null

function flushScroll() {
  if (scrollSaveTimer) {
    clearTimeout(scrollSaveTimer)
    scrollSaveTimer = null
  }
  rememberScroll()
}

function onScroll(e) {
  scrollOffset.value = e.target.scrollTop
  if (scrollSaveTimer) return // 一串滚动只在停手后落一次盘
  scrollSaveTimer = setTimeout(flushScroll, 400)
}

// 刷新或关掉页面前，浏览器会先给一次 hidden，用它把最后一次滚动落盘。
function onVisibilityChange() {
  if (document.visibilityState === 'hidden') flushScroll()
}

async function scrollBottom() {
  await scrollTo(chatEl.value)
}

async function restoreScroll() {
  await nextTick()
  if (!chatEl.value) return
  if (scrollOffset.value > 0) chatEl.value.scrollTop = scrollOffset.value
  else await scrollTo(chatEl.value, 'auto')
}

// 顶栏那个绿点以前是写死的：不管机器上有没有模型，它都显示「本地模型」。
// 现在改成读 /health/details 的 problems，读不到就显示「状态未知」——不确定不是坏消息，
// 把不确定画成健康才是。
const runtimeHealth = ref(null)
const modelStateValue = computed(() => modelState(runtimeHealth.value))
const modelStateText = computed(() => modelStatusText(runtimeHealth.value))

async function refreshRuntimeHealth() {
  runtimeHealth.value = await fetchRuntimeHealth({ force: true })
}

onMounted(() => {
  refreshRuntimeHealth()
  restoreQueuedTurns()
  window.addEventListener('chat-ask', onChatAsk)
  document.addEventListener('visibilitychange', onVisibilityChange)
  // 地址带着深链时，「恢复上次看的那一条」这条路要关掉：那正是判据①明令不许的静默落到最新一轮。
  // loadSessions() 照旧要跑 —— 本机有没有这一条会话，靠的就是它。
  const linked = Boolean(deepLinkFromQuery(route?.query))
  if (!sessions.value.length) {
    const storedActive = loadSessions()
    if (!activeId.value && storedActive && !linked) activeId.value = storedActive
  }
  if (!activeId.value) activeId.value = genId()
  // 只在 store 里还没有这份会话时回填，避免把正在写入的流替换掉。
  if (!messages.value.length && !linked) restoreActive(activeId.value)
  ensureSession()
  restoreScroll()
  // 浏览器里才补这一刀：本地那一腿 setup 期已经走完，这里只补「本机没有 → 问后端」那一枪，
  // 以及给已经落定的那一轮滚一次（setup 期 chatEl 还没挂上，滚不动）。
  if (linked) applyDeepLink()
})

onUnmounted(() => {
  stopQueueWatches()
  window.removeEventListener('chat-ask', onChatAsk)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  flushScroll()
})

async function send(dataFilename = activeDataFilename.value) {
  const text = input.value.trim()
  if (!text || loading.value) return
  if (hitl.value) {
    note('请先处理待确认动作，再发起新一轮提问。', 'warn')
    return
  }
  if (dataFilename) activeDataFilename.value = dataFilename

  messages.value.push({ role: 'user', content: text, sources: null })
  input.value = ''
  // mid 是这一轮的脸的钥匙：排队位次与缓存改版核对都是流结束之后才异步回来的，而 store 的
  // messages 是 shallowRef，往消息对象上塞属性触发不了重渲染。派生态住在组件的 ref 表里，
  // 消息对象上那一份（msg.sources / msg.cache / msg.queue）只负责随会话落盘与历史复原。
  messages.value.push({ role: 'assistant', content: '', steps: [], sources: null, mid: genId() })
  const aiMsg = messages.value[messages.value.length - 1]
  const turn = turnKey(aiMsg, messages.value.length - 1)
  note('')
  cancelPhase.value = 'idle'
  syncActive()

  const signal = beginStream()
  await scrollBottom()

  try {
    const response = await authedFetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal,
      body: JSON.stringify({
        message: text,
        session_id: activeId.value,
        data_filename: dataFilename,
        // R141：这一格就是「发出去真的带着档位」。空串是合法取值（不声明），
        // 与后端 AskRequest.lane 的默认值同一含义，不是漏传。
        lane: selectedLane.value,
      }),
    })

    // 读数在流之前读：响应头随状态行一起到，不必等最后一帧，也就不会被中途中断吃掉。
    readLaneHeaders(turn, aiMsg, response)

    const result = await consumeSseStream(response, aiMsg, {
      signal,
      onHitl: ({ pending, labels }) => {
        // 挂起期间仍可中断，所以先结束 loading 再展示待确认卡。
        hitl.value = { pending, labels, interrupted: false }
        endStream()
      },
      onText: flush,
      onBatch: flush,
      onSources: (sources) => {
        sourceReads.value = { ...sourceReads.value, [turn]: sources }
      },
      onCache: (cache) => {
        cacheReads.value = { ...cacheReads.value, [turn]: cache }
      },
      onQueued: (queue) => {
        // 回执里只有 request_id：位次与结果必须另读 GET /queue/status/{id}（判据④）。
        watchQueueTurn(turn, queue?.requestId)
      },
      onUnknownEvent: (event) => {
        // 界面没认领的后端事件：告警在 lib/sessions.js 打一次，这里再画上屏一次，不静默吞。
        // 同时抄一份进消息对象：那一格会随会话落盘，刷新之后自陈还在（自陈不是控制台日志）。
        const seen = unseenReads.value[turn] || []
        if (seen.includes(event)) return
        unseenReads.value = { ...unseenReads.value, [turn]: [...seen, event] }
        aiMsg.unseenEvents = [...(Array.isArray(aiMsg.unseenEvents) ? aiMsg.unseenEvents : []), event]
      },
    })

    if (!result.ok) {
      aiMsg.content = `[请求错误] ${result.error}`
      note(`本轮请求未成功（HTTP ${result.status}）。`, 'error')
      // 入队这一步就失败（503 那一格）说的是「排没排上队」，与气泡里的错误行不是同一句话，
      // 两枚各画各的：错误行进气泡，排队脸进下面那张表。
      if (result.stopped === 'http_error' && result.normalized) {
        rejectedReads.value = { ...rejectedReads.value, [turn]: result.normalized }
      }
    } else if (result.state.terminal === 'failed') {
      const text2 = friendlyErrorText(result.state)
      aiMsg.content = aiMsg.content ? `${aiMsg.content}\n${text2}` : text2
      note('本轮未能完成，服务已返回失败状态。', 'error')
    } else if (result.state.terminal === 'cancelled') {
      if (!aiMsg.content) aiMsg.content = '本次回答已中断。'
    } else if (result.stopped !== 'hitl' && !aiMsg.content) {
      aiMsg.content = '本轮没有返回内容。'
    }
    // 「命中缓存但来源已改版」这句只能真读 GET /documents/{filename}/versions 才说得出。
    // 放在流结束之后而不是 onCache 里：sources 帧在 text 之后到，先查会拿着空清单误报。
    await checkCacheStaleness(turn, aiMsg)
    syncActive()
    await scrollBottom()
  } catch (err) {
    if (err?.name !== 'AbortError' && !signal.aborted) {
      aiMsg.content = `[网络错误] ${err.message}`
      note('与服务器的连接中断，未能完成本轮回答。', 'error')
    }
    syncActive()
  } finally {
    endStream()
    persist()
  }
}

function requestCancel() {
  if (cancelPhase.value === 'confirm') return
  cancelPhase.value = 'confirm'
}

async function confirmCancel() {
  cancelPhase.value = 'idle'
  const awaitingHitl = !!hitl.value
  abortStream()
  endStream()

  let cancelled = null
  let ok = false
  let status = 0
  try {
    const response = await authedFetch(`/ask/${activeId.value}/cancel`, { method: 'POST' })
    status = response.status
    ok = response.ok
    if (ok) {
      let body = null
      try {
        body = await response.json()
      } catch (_) {
        body = null
      }
      cancelled = body?.cancelled
    }
  } catch (err) {
    note(`中断请求未能送达：${err.message || err}`, 'error')
  }

  if (ok && cancelled === true) {
    note('已脱离本次回答，界面不再接收后续内容。', 'info')
    const last = messages.value[messages.value.length - 1]
    if (last?.role === 'assistant' && !last.content) {
      last.content = '本次回答已中断，未产出结论。'
    }
  } else if (ok && cancelled === false) {
    // HTTP 200 只说明请求被受理，不代表真的停掉了什么。
    note('当前没有正在生成的内容。', 'warn')
  } else if (ok) {
    note('服务未返回中断结果，无法确认本轮回答是否已停止产出。', 'warn')
  } else if (status) {
    note(`中断请求未被受理（HTTP ${status}）。`, 'error')
  }

  if (awaitingHitl) {
    // 显式保留待确认卡并标注已中断。R11 裁定：停止只脱离本次回答流，
    // 不构成对挂起动作的拒绝；拒绝必须在审批卡上显式点「拒绝这个动作」。
    hitl.value = { ...hitl.value, interrupted: true }
    note(`${streamNote.value} 待确认动作仍保留，请明确选择执行或取消。`, 'warn')
  }
  syncActive()
  persist()
}

async function approve(approved) {
  const pending = hitl.value
  if (!pending) return
  // 用户已经做出选择：待确认卡显式清除，不留残影。
  hitl.value = null
  note('')

  const aiMsg = messages.value[messages.value.length - 1]
  if (!aiMsg || aiMsg.role !== 'assistant') {
    loading.value = false
    syncActive()
    return
  }

  loading.value = true
  const turn = turnKey(aiMsg, messages.value.length - 1)
  const signal = beginStream()
  try {
    const response = await authedFetch('/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal,
      body: JSON.stringify({ session_id: activeId.value, approved }),
    })

    // 批准后这一轮的读数是第四态（resumed）：确认门把原始声明落在了门外面，界面照着说。
    readLaneHeaders(turn, aiMsg, response)
    const result = await consumeSseStream(response, aiMsg, {
      signal,
      onHitl: ({ pending: nextPending, labels }) => {
        hitl.value = { pending: nextPending, labels, interrupted: false }
        endStream()
      },
      onText: flush,
      onBatch: flush,
    })

    if (!result.ok) {
      aiMsg.content = aiMsg.content
        ? `${aiMsg.content}\n[请求错误] ${result.error}`
        : `[请求错误] ${result.error}`
      note(`确认结果未被受理（HTTP ${result.status}）。`, 'error')
    } else if (result.state.terminal === 'failed') {
      const failure = friendlyErrorText(result.state, '待确认动作执行失败')
      aiMsg.content = aiMsg.content ? `${aiMsg.content}\n${failure}` : failure
    } else if (result.state.terminal === 'cancelled') {
      if (!aiMsg.content) aiMsg.content = '本次回答已中断，未回传动作结果。'
    } else if (!aiMsg.content) {
      aiMsg.content = approved ? '已确认，但本轮没有返回内容。' : '已拒绝该动作。'
    }
    syncActive()
    await scrollBottom()
  } catch (err) {
    if (err?.name !== 'AbortError' && !signal.aborted) {
      aiMsg.content = `${aiMsg.content}\n[网络错误] ${err.message}`
      note('与服务器的连接中断，待确认动作状态未知。', 'error')
    }
    syncActive()
  } finally {
    // 无论走到哪条分支都必须复位，否则界面会永远停在「处理中」。
    endStream()
    cancelPhase.value = 'idle'
    persist()
  }
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

// ==================== R150 · 三张脸：出处 / 缓存 / 排队 ====================
// 后端早就把这些字段吐到线上了（R41 的 sources、R35 的 cached 三枚、R26 的 queued），
// 界面上却一处读取方都没有：sources 被 isCanonicalEvent() 判成 canonical 之后落 default，
// 塞进 state.unknownEvents 就没人读过。这里补的就是读取方。
//
// 分工写死，免得「后端报了但界面没说」这类缺陷有两个可能归属：
//   lib/sessions.js   把帧读成事实（数字与键名）
//   lib/provenance.js 把事实说成人话（几种读法各说什么、哪两句必须分开）
//   本面板            只做取数与挂元素，不当第三套判断

// 每一枚读数的键都是「哪一轮」，见 turnKey()。消息对象上那份只负责落盘与历史复原。
const sourceReads = ref({})   // sources 帧的出处读数
const cacheReads = ref({})    // text 帧上那三枚缓存字段
const unseenReads = ref({})   // 本轮发出、界面尚未认领的事件名
const queueReads = ref({})    // GET /queue/status/{id} 的最近一次读数
const queueFaults = ref({})   // 排队状态这一次没读回来时的原始错误
const queueStops = ref({})    // 这一轮的轮询被终止性判定叫停：停表之后读数不会自己回来
const rejectedReads = ref({}) // 入队这一步就失败（HTTP 5xx / 4xx）的归一结果
const cacheChecks = ref({})   // 改版核对：缺键=未查 / null=无从核对 / []=没改版 / [{}]=改版了
const queueStats = ref(null)  // GET /queue/stats 的最近一次读数（全局一块，不按轮次分）

const preview = reactive({
  open: false,
  filename: '',
  kind: 'text',
  text: '',
  blobUrl: '',
  error: '',
  loading: false,
  truncated: false,
})

const QUEUE_POLL_MS = 3000
const QUEUE_SETTLED = ['done', 'cancelled', 'failed', 'expired']

// 轮询还有另一种停法：后端明确说「这一轮你再也读不回来了」。
// 名单只收终止性判定，出处 app/api/v1/chat.py::_authorize_queue_task（401 / 404 / 403 各一枚，
// 错误体是形状 1：detail 就是稳定码名）。网络错误、超时与 5xx 一律不在名单里——
// 瞬断不能杀死排队状态的显示，那一族继续按 3 秒重试，脸上说的是「这次没读到」。
// 判码只走 lib/errcodes 那一份口径（errorCodeOf），面板不另立第二套分类。
const QUEUE_POLL_STOPPERS = [
  { status: 404, code: 'resource_not_found' },
  { status: 403, code: 'permission_denied' },
  { status: 401, code: 'authentication_required' },
]

/** 这一发失败算不算「终止性判定」：算就回那一格，不算回 null（继续轮）。 */
function queuePollStopper(err) {
  const status = Number(err?.response?.status ?? 0)
  if (!status) return null
  const code = errorCodeOf(err)
  return QUEUE_POLL_STOPPERS.find(item => item.status === status && item.code === code) || null
}
let queueWatches = []

/** 这一轮的脸挂在哪个键上：优先消息自带的 mid（随会话落盘），退回「会话 + 序号」。 */
function turnKey(msg, index) {
  if (msg && typeof msg.mid === 'string' && msg.mid) return `m${msg.mid}`
  return `${activeId.value}#${index}`
}

function storeBag(bag, key, value) {
  return { ...bag.value, [key]: value }
}

function readTurn(bag, msg, index) {
  return bag.value[turnKey(msg, index)] || null
}

function laneFaceOf(msg, index) {
  return readTurn(laneReads, msg, index) || msg.lane || null
}

/**
 * 档位读数的人话。四态分开说，一句都不许合并：
 *   explicit     你选的，而且图按它改派了腿；
 *   r42          没人选，系统按题面判的（这一格必须说得出"没人在选"这件事）；
 *   not_routed   这一轮压根没走图（缓存命中/排队），档位没参与路径；
 *   resumed      批准后从挂起点续跑，原始声明没跟着过来。
 * 后两态还要把"你明明选了 X"说回来，否则用户会以为自己的选择被无视是正常现象。
 */
function laneFaceText(read) {
  if (!read || !read.source) return ''
  const named = LANE_NAMES[read.lane] || ''
  const declaredName = LANE_NAMES[read.declared] || ''
  if (read.source === 'explicit') return `本轮档位：${named}（你选的）`
  if (read.source === 'r42') return `本轮档位：${named || '系统判断'}（系统按问题内容判的，你没选）`
  if (read.source === 'not_routed') {
    return declaredName
      ? `本轮没有走进分析图（缓存命中或已排队），档位「${declaredName}」没参与这一轮的路径`
      : '本轮没有走进分析图（缓存命中或已排队），不涉及档位'
  }
  if (read.source === 'resumed') return '批准后续跑的这一轮：原始档位声明没有跟着跨过确认门，本轮按系统默认路径走'
  return `本轮档位读数（未认识）：${read.source}`
}

/**
 * 出处那张脸。后端这一轮没发 sources 事件时返回 null，界面什么都不画。
 *
 * 这条留白是有意的：「没发出处事件」与「发了、但一条没检索到」是两件事，前者多半是这一轮
 * 压根没走文档检索（数据问答、寒暄），画一张「没有检索到可用文档」的卡等于替后端撒谎。
 */
function sourceFaceOf(msg, index) {
  return sourcesFace(readTurn(sourceReads, msg, index) || msg.sources)
}

function cacheFaceOf(msg, index) {
  // 读数的来源只有 text 帧那三枚字段；一枚都没有就把这一轮读成「实时算」（证据写在句子里）。
  const read = readTurn(cacheReads, msg, index) || msg.cache || null
  return cacheFace(read, cacheChecks.value[turnKey(msg, index)])
}

/**
 * 轮询被终止性判定叫停那一轮的脸。
 *
 * 为什么不复用 queuePollFailedFace：它句尾写着「界面每 3 秒再读一次状态」，表都停了
 * 还这么说就是假话。为什么要在面板里写这一句：「自己还在不在轮」只有面板知道，
 * lib/provenance.js 只把读数说成人话，它读不到这张表。措辞仍走同一份字典——正文取
 * normalizeError(err).message，码名小字走 errorCodeLabel()，本函数只补一句「不再查询」。
 */
function queuePollStoppedFace(error) {
  const result = normalizeError(error)
  return {
    kind: 'unreadable-stopped',
    headline: '这一轮排队状态读不回来了，界面已停止继续查询',
    detail: `${result.message}停止查询后不会再有新读数；要看结果请把这一轮的问题原样再问一次。`,
    codeLabel: errorCodeLabel(result),
    tone: 'warn',
    retryable: result.retryable,
    ahead: null,
  }
}

function queueFaceOf(msg, index) {
  const key = turnKey(msg, index)
  if (rejectedReads.value[key]) return queueRejectedFace(rejectedReads.value[key])
  // 停表优先于一切读数：这一轮此前只要读到过一次 queued，不特别处理就会永远画着
  // 「前面还有 N 人」——那是本单病灶的屏幕半，另一半是每 3 秒一笔被拒的台账。
  if (queueStops.value[key]) return queuePollStoppedFace(queueStops.value[key])
  const read = queueReads.value[key]
  if (!read) {
    if (queueFaults.value[key]) return queuePollFailedFace(queueFaults.value[key])
    // 只收到 queued 回执、状态还没读回来：说「已排上队、位次未读到」，不补 0 也不猜人数。
    return msg.queue ? queueFace({ status: 'queued' }) : null
  }
  return queueFace(read)
}

function queueStatsOf() {
  return queueStatsFace(queueStats.value)
}

function unseenOf(msg, index) {
  const live = readTurn(unseenReads, msg, index)
  const stored = Array.isArray(msg.unseenEvents) ? msg.unseenEvents : []
  const arrived = Array.isArray(live) ? live : []
  return [...new Set([...stored, ...arrived])]
}

/** 排队答案补回这条回答：这一轮界面没有实时流，正文只来自状态读数里的 result。 */
function applyQueuedAnswer(key, answer) {
  const index = messages.value.findIndex((msg, at) => turnKey(msg, at) === key)
  if (index < 0) return
  const msg = messages.value[index]
  if (msg.content) return
  msg.content = answer
  syncActive()
}

function watchQueueTurn(key, requestId) {
  if (!requestId) return
  if (queueWatches.some(item => item.key === key)) return
  const entry = { key, timer: 0 }
  const stop = () => {
    clearInterval(entry.timer)
    queueWatches = queueWatches.filter(item => item !== entry)
  }
  const tick = async () => {
    try {
      const status = await http.get(`/queue/status/${encodeURIComponent(requestId)}`)
      const read = {
        status: typeof status.data?.status === 'string' ? status.data.status : '',
        position: Number.isFinite(Number(status.data?.position)) ? Number(status.data.position) : null,
        failure: status.data?.failure || null,
        result: typeof status.data?.result === 'string' ? status.data.result : '',
      }
      queueReads.value = storeBag(queueReads, key, read)
      queueFaults.value = storeBag(queueFaults, key, null)
      if (read.status === 'done' && read.result) applyQueuedAnswer(key, read.result)
      if (QUEUE_SETTLED.includes(read.status)) stop()
    } catch (err) {
      queueFaults.value = storeBag(queueFaults, key, err)
      if (queuePollStopper(err)) {
        // 终止性判定：继续打只会把同一句拒绝反复写进后端台账（一枚失效页签约 1200 笔/小时），
        // 屏上也不会因此多出一个字。收表，并把原因画成人话（见 queuePollStoppedFace）。
        queueStops.value = storeBag(queueStops, key, err)
        stop()
      }
    }
    try {
      const stats = await http.get('/queue/stats')
      queueStats.value = stats.data || null
    } catch (_) {
      // 全局等待人数读不到就不说这一行，不影响这一轮的位次与状态。
      queueStats.value = null
    }
  }
  tick()
  entry.timer = setInterval(tick, QUEUE_POLL_MS)
  queueWatches.push(entry)
}

// 面板常驻 v-show，卸载不是常态；但真卸载时必须停表：排队轮询会在别人不看的界面上一直打接口。
function stopQueueWatches() {
  queueWatches.forEach(entry => clearInterval(entry.timer))
  queueWatches = []
}

/** 刷新或切回来接着盯：queued 那一轮的答案在 Redis 回执过期前仍然读得到，读数过期就画过期。 */
function restoreQueuedTurns() {
  messages.value.forEach((msg, index) => {
    if (msg?.role !== 'assistant' || !msg.queue?.requestId) return
    if (msg.content) return
    watchQueueTurn(turnKey(msg, index), msg.queue.requestId)
  })
}

/**
 * 缓存改版的核对：真读 GET /documents/{filename}/versions，界面自己不造时间。
 *
 * 三条退路都明说，不并成一句「已核对」：
 *   答案没带生成时间 / 这一轮压根没交出来源文件 / 版本接口读不到 -> null（无从核对）
 *   读到了但每一版都早于生成时间 -> []（确实没改版）
 *   有晚于生成时间的版本 -> 逐文件名带上最新版本号与入库时间
 */
async function checkCacheStaleness(key, msg) {
  const cache = msg.cache
  if (!cache || cache.cached !== true) return
  const born = cache.generatedAt
  const files = [...new Set((msg.sources?.rows || []).map(row => row.filename).filter(Boolean))]
  if (!born || !files.length) {
    cacheChecks.value = storeBag(cacheChecks, key, null)
    return
  }
  const stale = []
  for (const filename of files) {
    try {
      const res = await http.get(`/documents/${encodeURIComponent(filename)}/versions`)
      const revisions = revisionsAfter(born, res.data?.versions)
      if (revisions === null) {
        cacheChecks.value = storeBag(cacheChecks, key, null)
        return
      }
      if (revisions.length) {
        stale.push({
          filename,
          revisions,
          latestVersion: revisions[0].version,
          latestMoment: revisions[0].moment,
        })
      }
    } catch (err) {
      cacheChecks.value = storeBag(cacheChecks, key, null)
      return
    }
  }
  cacheChecks.value = storeBag(cacheChecks, key, stale)
}

/** 出处卡片上的「看原文」：复用既有预览弹窗组件（只 import，不改它一行）。 */
async function openSourcePreview(row) {
  const filename = typeof row?.filename === 'string' ? row.filename.trim() : ''
  if (!filename) return
  if (preview.blobUrl) {
    URL.revokeObjectURL(preview.blobUrl)
    preview.blobUrl = ''
  }
  preview.open = true
  preview.filename = filename
  preview.kind = 'text'
  preview.text = ''
  preview.error = ''
  preview.loading = true
  preview.truncated = false
  try {
    const res = await http.get(`/documents/${encodeURIComponent(filename)}/preview`)
    preview.kind = res.data?.kind || 'text'
    preview.text = res.data?.text || ''
    preview.truncated = Boolean(res.data?.truncated)
    if (preview.kind === 'pdf') {
      const file = await http.get(`/documents/${encodeURIComponent(filename)}/file`, {
        responseType: 'blob',
        params: { inline: true },
      })
      preview.blobUrl = URL.createObjectURL(file.data)
    }
  } catch (err) {
    preview.error = errorDetail(err, '文件预览失败')
  } finally {
    preview.loading = false
  }
}

function closeSourcePreview() {
  preview.open = false
  if (preview.blobUrl) {
    URL.revokeObjectURL(preview.blobUrl)
    preview.blobUrl = ''
  }
}

async function downloadSourcedFile() {
  const filename = preview.filename
  if (!filename) return
  try {
    const file = await http.get(`/documents/${encodeURIComponent(filename)}/file`, {
      responseType: 'blob',
      params: { inline: false },
    })
    const url = URL.createObjectURL(file.data)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (err) {
    note(`原文没能下载：${errorDetail(err, '文件下载失败')}`, 'error')
  }
}

/** 排队被拒且可重试：把原问题照原样再问一次，不改字、不猜意图。 */
function retryTurn(index) {
  if (loading.value || hitl.value) return
  let question = ''
  for (let at = index; at >= 0; at -= 1) {
    if (messages.value[at]?.role === 'user') {
      question = String(messages.value[at].content || '')
      break
    }
  }
  if (!question.trim()) return
  input.value = question
  send()
}

// ==================== Markdown ====================

function renderMd(raw) {
  if (!raw) return ''
  let html = raw
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const l = lang || ''
    return `<div class="code-block"><div class="code-lang">${l}</div><pre><code>${code.trim()}</code></pre></div>`
  })

  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="md-link">$1</a>')
  html = html.replace(/^&gt;\s?(.*)$/gm, '<blockquote>$1</blockquote>')
  html = html.replace(/^[-*]\s+(.*)$/gm, '<li>$1</li>')
  html = html.replace(/\n\n/g, '</p><p>')
  html = html.replace(/\n/g, '<br>')
  html = `<p>${html}</p>`

  return html
}
</script>
<template>
  <div class="chat-layout" data-testid="chat-panel">
    <!-- ===== 会话侧边栏 ===== -->
    <aside :class="['session-sidebar', { collapsed: !sidebarOpen }]">
      <div class="sidebar-hd">
        <span v-if="sidebarOpen" class="sidebar-title">💬 会话</span>
        <button class="sidebar-toggle" @click="sidebarOpen = !sidebarOpen" :title="sidebarOpen ? '收起' : '展开'">
          {{ sidebarOpen ? '◀' : '▶' }}
        </button>
      </div>

      <template v-if="sidebarOpen">
        <button class="new-session-btn" @click="newSession">＋ 新建会话</button>

        <div class="session-list">
          <!-- 会话列表读的是本地 store（lib/sessions.js），不发请求，所以这里不需要「无权限」那张脸。 -->
          <UiEmptyState v-if="sessions.length === 0" title="暂无历史会话" dense />
          <div v-for="s in sessions" :key="s.id"
               :class="['session-item', { active: s.id === sessionId }]"
               @click="switchSession(s.id)">
            <div class="session-info">
              <div class="session-title">{{ s.title || '新会话' }}</div>
              <div class="session-meta">
                <span>{{ s.msgCount || 0 }} 问</span>
                <span>·</span>
                <span>{{ formatTime(s.updatedAt) }}</span>
              </div>
            </div>
            <button class="session-del" @click.stop="deleteSession(s.id)" title="删除">✕</button>
          </div>
        </div>
      </template>
    </aside>

    <!-- ===== 主聊天区 ===== -->
    <div class="chat-panel">
      <!-- 顶栏 -->
      <div class="chat-topbar">
        <div class="chat-topbar-left">
          <span class="chat-dot" :class="`chat-dot--${modelStateValue}`" data-testid="model-dot"></span>
          <span class="chat-title">智能问答</span>
        </div>
        <span class="model-status" :class="`model-status--${modelStateValue}`" data-testid="model-status">
          🖥️ {{ modelStateText }}
        </span>
      </div>

      <!-- 模型没就绪时，答案只是检索原文：这句话必须由系统说，不能等老板自己发现。 -->
      <div v-if="modelStateValue === 'down'" class="model-degraded-notice" role="status" data-testid="model-degraded-notice">
        本机还没有可用的模型权重，下面的回答只是**检索到的原文片段**，不是模型给出的结论。
        先在服务器上拉取模型（或在本机模型设置里选一个已存在的），再回来提问。
      </div>

      <div class="chat-messages" ref="chatEl" @scroll.passive="onScroll">
        <!-- R174 · 深链落点先说一句，再画会话本体。落不到的那几张脸各自一句（判据①第 4 件），
             其中 blocking 那几张干脆把会话区盖住：宁可不画，也不许把另一条会话当成链接的落点。 -->
        <p v-if="deepLink && deepLink.state === 'reading'" class="deep-link-note" data-tone="info"
           data-state="reading" data-testid="deep-link-note">
          这条链接指的是另一条会话里的某一轮，正在问后端有没有把它交给我们……
        </p>
        <div v-else-if="deepFace" class="deep-link-note" :data-tone="deepFace.tone"
             :role="deepFace.tone === 'error' ? 'alert' : 'status'" :data-face="deepLink.face"
             :data-session="deepLink.session || null" :data-request="deepLink.request || null"
             data-testid="deep-link-note">
          <span class="deep-link-text">{{ deepFace.text }}</span>
          <button v-if="deepFace.retry" type="button" class="deep-link-retry"
                  data-testid="deep-link-retry" @click="applyDeepLink()">再问一次后端</button>
        </div>
        <div v-if="messages.length === 0 && !deepBlocked" class="welcome-screen">
          <div class="welcome-glow"></div>
          <div class="welcome-card">
            <div class="wc-icon">🧠</div>
            <h1>企业智脑</h1>
            <p class="wc-sub">您的私有 AI 知识助手</p>
            <div class="wc-features">
              <div class="wc-feat">
                <span class="wc-feat-icon">📄</span>
                <span>上传文档 · 智能问答</span>
              </div>
              <div class="wc-feat">
                <span class="wc-feat-icon">📊</span>
                <span>数据分析 · 图表生成</span>
              </div>
              <div class="wc-feat">
                <span class="wc-feat-icon">🔒</span>
                <span>数据不出机器 · 安全私有</span>
              </div>
            </div>
            <p class="wc-hint">在左侧上传文档，然后开始提问</p>
          </div>
        </div>

        <!-- 链接落不到可看的东西之前，这一条会话整段先不画：拿另一条补位就是「静默落到最新一轮」。 -->
        <TransitionGroup v-if="!deepBlocked" name="msg">
          <div v-for="(msg, i) in messages" :key="i"
               :data-turn="i"
               :data-deep-target="i === deepTurn ? '1' : null"
               :class="['msg-row', msg.role, { 'is-deep-target': i === deepTurn }]">
            <div v-if="msg.role === 'assistant'" class="msg-avatar ai">
              {{ loading && i === messages.length - 1 && !msg.content ? '⏳' : '🤖' }}
            </div>

            <div class="msg-bubble-wrap">
              <!-- 可视标记：链接点中的那一轮，一眼看得出就是这条。 -->
              <p v-if="i === deepTurn" class="deep-link-badge" role="status"
                 data-testid="deep-link-badge" :data-request="msg.requestId || null">{{ deepBadge }}</p>
              <div :class="['msg-bubble', msg.role]">
                <!-- 进度卡片 -->
                <div v-if="msg.steps && msg.steps.length" class="steps-bar">
                  <div v-for="(st, si) in msg.steps" :key="si"
                       :class="['step-card', st.status]">
                    <span class="step-icon">{{ st.status === 'running' ? '🔄' : '✅' }}</span>
                    <span class="step-label">{{ st.label }}</span>
                    <span v-if="st.elapsed !== null" class="step-time">{{ st.elapsed }}s</span>
                    <span v-else class="step-time pulse">…</span>
                  </div>
                </div>

                <div v-if="msg.role === 'assistant' && loading && i === messages.length - 1 && !msg.content && !msg.steps?.length"
                     class="typing-dots">
                  <span></span><span></span><span></span>
                </div>
                <div v-else-if="msg.role === 'assistant'"
                     class="msg-content" v-html="renderMd(stripChartMarkers(msg.content))" />
                <div v-else class="msg-content">{{ msg.content }}</div>

                <ChartViewer v-for="(ch, ci) in parseCharts(msg.content)"
                             :key="ci" :src="ch.src" :caption="ch.caption" />

                <!-- R150 · 三张脸。字段都是后端早已发出的（sources / cached / queued），
                     这里只是第一次有人读它们。措辞与判据在 lib/provenance.js，本面板不当第三套判断。
                     sourceFaceOf / cacheFaceOf / queueFaceOf 各调两次（v-if 与 :face）是有意的：
                     数据住在 shallowRef 的消息对象上，包一层 computed 会缓存成旧值。 -->
                <div v-if="msg.role === 'assistant'" class="face-stack" data-testid="r150-faces">
                  <!-- R197 · 出处卡按【哪一轮】挂 key，不按【下标】：R195 那两枚一次性动作的态是按
                       filename 存在卡片实例里的，而外层消息循环是按位次挂 key 的，不补这枚按轮 key
                       的话切会话时实例被复用，上一轮那把「已记下」的锁会跟着文件名跟到新一轮去。
                       形状照下面的 CacheFace，键走既有 turnKey()；判据钉在 components/__tests__/
                       r197-turn-key-inheritance.test.js（乙段直接从本行源码抠 key）。 -->
                  <SourceCard
                    v-if="sourceFaceOf(msg, i)"
                    :face="sourceFaceOf(msg, i)"
                    :key="`source-${turnKey(msg, i)}`"
                    @preview="openSourcePreview"
                  />
                  <!-- 「实时算」也是必须说出口的一态（不是留白），但它只对当场看到的轮次说。 -->
                  <CacheFace v-if="cacheFaceOf(msg, i)" :face="cacheFaceOf(msg, i)" :key="`cache-${turnKey(msg, i)}`" />
                  <QueueFace
                    v-if="queueFaceOf(msg, i)"
                    :face="queueFaceOf(msg, i)"
                    :stats="queueStatsOf()"
                    @retry="retryTurn(i)"
                  />
                  <!-- 档位那张脸：读的是响应头给的本轮真读数，不是选择框的当前值。
                       用户中途改选择框不会回改已落定的那一轮；后端没发读数就整条不画。 -->
                  <p v-if="laneFaceText(laneFaceOf(msg, i))" class="lane-readout" role="status"
                     data-testid="lane-readout">{{ laneFaceText(laneFaceOf(msg, i)) }}</p>
                  <!-- 界面没认领的后端事件：画成系统自陈，而不是静默丢进 unknownEvents 当没看见。
                       这行的「技术信息」四个字同时是 V6 裸码闸门认得的诊断区标记。 -->
                  <p v-if="unseenOf(msg, i).length" class="face-unseen" role="status" data-testid="face-unseen">
                    本轮后端还发出过界面尚未认领的事件（技术信息）：{{ unseenOf(msg, i).join('、') }}。
                    答案正文照旧，但这几格的读数今天画不出来，请当成缺陷报给前端。
                  </p>
                </div>
              </div>
            </div>

            <!-- HITL 确认弹窗 -->
            <div v-if="hitl && i === messages.length - 1" class="hitl-bar">
              <div :class="['hitl-card', { interrupted: hitl.interrupted }]">
                <div class="hitl-icon">⏸️</div>
                <div class="hitl-text">
                  <b>{{ hitl.interrupted ? '已中断，仍待确认' : '需要确认' }}</b>
                  <span v-if="hitl.interrupted" class="hitl-note">中断只停止了回答的显示，没有拒绝这个动作，请明确选择执行或拒绝。</span>
                  <span v-for="(lbl, li) in hitl.labels" :key="li">{{ lbl }}</span>
                </div>
                <div class="hitl-actions">
                  <button class="hitl-btn approve" @click="approve(true)">✅ 确认执行</button>
                  <button class="hitl-btn cancel" type="button" data-testid="hitl-reject" @click="approve(false)">✕ 拒绝这个动作</button>
                </div>
              </div>
            </div>

            <div v-if="msg.role === 'user'" class="msg-avatar user">👤</div>
          </div>
        </TransitionGroup>
      </div>

      <!-- 输入区 -->
      <div class="chat-input-bar">
        <!-- R141 · 档位选择器。三件事在这一屏上闭环，缺一件就不许上屏：
             ① 选中项写进地址（?lane=），刷新与转发都留得住；
             ② 发出去真的带这一格（send 的 body 里那一行 lane）；
             ③ 每一轮画回**档位读数**（下面气泡里的 lane-readout），读不到就不画。
             用原生 <select> 而不是自造下拉：键盘/读屏/输入法行为不用重新发明，也不新增色值。 -->
        <div class="lane-bar" data-testid="chat-lane-picker">
          <label class="lane-label" for="chat-lane-select">本轮档位</label>
          <select id="chat-lane-select" class="lane-picker" :value="selectedLane"
                  @change="chooseLane($event.target.value)">
            <option v-for="choice in LANE_CHOICES" :key="choice.value" :value="choice.value">
              {{ choice.label }}
            </option>
          </select>
          <span class="lane-promise" data-testid="chat-lane-promise">{{ LANE_PROMISES[selectedLane] }}</span>
        </div>
        <!-- 失败提示原先只是换行色的 <p role="status">：读屏不会打断，等于把错误当通知。
             这些句子都是一次性结果，不是一条能重试的面板加载，所以 retryable=false。 -->
        <UiErrorState v-if="streamNote && noteTone === 'error'" :title="streamNote" :retryable="false" dense />
        <p v-else-if="streamNote" :class="['stream-note', noteTone]" role="status" data-testid="chat-note">{{ streamNote }}</p>
        <div class="input-wrapper">
        <textarea
            data-testid="chat-input"
            v-model="input"
            placeholder="输入您的问题… (Enter 发送, Shift+Enter 换行)"
            @keydown="handleKeydown"
            :disabled="loading || !!hitl"
            rows="1"
          />
          <div v-if="cancelPhase === 'confirm'" class="cancel-confirm" data-testid="chat-cancel-confirm">
            <span class="cancel-confirm-text">中断只是不再接收本轮回答，不会撤销任何动作：待确认的动作仍挂在卡片上，已经批准的动作后端仍会继续执行完。</span>
            <button class="send-pill danger" type="button" @click="confirmCancel">确认中断</button>
            <button class="send-pill ghost" type="button" @click="cancelPhase = 'idle'">返回</button>
          </div>
          <button v-else-if="loading || hitl" class="send-pill cancel-generation" type="button" data-testid="chat-cancel" @click="requestCancel">中断本次回答</button>
          <button v-else class="send-pill" data-testid="chat-send" @click="send()"
                  :disabled="!input.trim()">
            <svg v-if="!loading" width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M2 21l21-9L2 3v7l15 2-15 2v7z"/>
            </svg>
            <span v-else class="mini-spinner"></span>
          </button>
        </div>
        <p class="input-footer">
          本地模型推理 · 数据完全不出机器
        </p>
      </div>
    </div>
    <!-- 「看原文」复用的预览弹窗：只 import 既有组件，本单不改它一行（R151 的写域）。 -->
    <DocumentPreviewModal
      :open="preview.open"
      :filename="preview.filename"
      :kind="preview.kind"
      :text="preview.text"
      :blob-url="preview.blobUrl"
      :loading="preview.loading"
      :error="preview.error"
      :truncated="preview.truncated"
      @close="closeSourcePreview"
      @download="downloadSourcedFile"
    />
  </div>
</template>

<style scoped>
/* ===== 整体布局 ===== */
.chat-layout {
  flex: 1;
  display: flex;
  height: 100%;
  overflow: hidden;
}

/* ===== 会话侧边栏 ===== */
.session-sidebar {
  width: 200px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(0,0,0,0.06);
  background: rgba(248,249,252,0.9);
  transition: width 0.25s ease;
  overflow: hidden;
}
.session-sidebar.collapsed {
  width: 32px;
}
.session-sidebar.collapsed .sidebar-hd {
  flex-direction: column;
  padding: 10px 0;
}

.sidebar-hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 12px 8px;
  flex-shrink: 0;
}
/* 收起时：toggle 居中 */
.session-sidebar.collapsed .sidebar-hd {
  justify-content: center;
  padding: 10px 4px;
}
.sidebar-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
}
.sidebar-toggle {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 11px;
  color: #909399;
  padding: 4px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}
.sidebar-toggle:hover { color: #409eff; background: rgba(64,158,255,0.08); }

.new-session-btn {
  margin: 4px 8px 8px;
  padding: 7px 0;
  border: 1px dashed #d0d5dd;
  border-radius: 8px;
  background: none;
  cursor: pointer;
  font-size: 12px;
  color: #606266;
  font-family: inherit;
  transition: all 0.2s;
  white-space: nowrap;
}
.new-session-btn:hover {
  border-color: #409eff;
  color: #409eff;
  background: rgba(64,158,255,0.04);
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 6px;
}

.session-list::-webkit-scrollbar { width: 3px; }
.session-list::-webkit-scrollbar-thumb { background: #d0d5dd; border-radius: 3px; }

.session-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  margin-bottom: 2px;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
}
.session-item:hover { background: rgba(64,158,255,0.04); }
.session-item.active {
  background: rgba(64,158,255,0.08);
  border-color: rgba(64,158,255,0.15);
}

.session-info {
  flex: 1;
  min-width: 0;
}
.session-title {
  font-size: 12px;
  font-weight: 500;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.session-meta {
  font-size: 10px;
  color: #c0c4cc;
  margin-top: 2px;
}

.session-del {
  background: none;
  border: none;
  color: #c0c4cc;
  cursor: pointer;
  font-size: 11px;
  padding: 3px 5px;
  border-radius: 4px;
  flex-shrink: 0;
  opacity: 0;
  transition: all 0.15s;
}
.session-item:hover .session-del { opacity: 1; }
.session-del:hover { color: #f56c6c; background: rgba(245,108,108,0.08); }

/* ===== 聊天面板 ===== */
.chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* ===== 顶栏 ===== */
.chat-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 56px;
  background: rgba(255,255,255,0.7);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid rgba(0,0,0,0.04);
  flex-shrink: 0;
}
.chat-topbar-left { display: flex; align-items: center; gap: 8px; }
.chat-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--muted);
}
.chat-dot--ready {
  background: var(--green);
  box-shadow: 0 0 6px var(--green);
}
.chat-dot--down { background: var(--amber); }
.chat-title { font-size: 15px; font-weight: 600; }

.model-status {
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
  color: var(--muted);
  border: 1px solid var(--line);
}
.model-status--ready { color: var(--green); }
.model-status--down {
  color: var(--amber);
  border-color: var(--amber);
}

.model-degraded-notice {
  padding: 8px 24px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--amber);
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}

/* ===== 消息区 ===== */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
.chat-messages::-webkit-scrollbar { width: 5px; }
.chat-messages::-webkit-scrollbar-thumb { background: #d0d5dd; border-radius: 5px; }

/* R174 · 深链那一句与「就是这一轮」那枚标记：只借 theme.css 既有令牌，零裸色值。 */
.deep-link-note {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
  margin: 0 0 var(--s-2);
  padding: var(--s-2) var(--s-3);
  border: 1px solid var(--line);
  border-left: 3px solid var(--muted);
  border-radius: var(--radius-sm);
  color: var(--ink-soft);
  font-size: var(--t-xs);
  line-height: 1.6;
}

.deep-link-note[data-tone='error'] {
  border-left-color: var(--danger);
}

.deep-link-note[data-tone='warn'] {
  border-left-color: var(--warning);
}

.deep-link-note[data-tone='info'] {
  border-left-color: var(--cyan);
}

.deep-link-retry {
  padding: var(--s-1) var(--s-2);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--surface-3);
  color: var(--text);
  font-size: var(--t-xs);
  cursor: pointer;
}

.deep-link-badge {
  margin: 0 0 var(--s-1);
  color: var(--muted);
  font-size: var(--t-xs);
}

.msg-row.is-deep-target .msg-bubble {
  outline: 2px solid var(--accent);
}

/* ===== 欢迎页 ===== */
.welcome-screen {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  position: relative;
}
.welcome-glow {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(64,158,255,0.08) 0%, transparent 70%);
  pointer-events: none;
}
.welcome-card { text-align: center; position: relative; }
.wc-icon {
  font-size: 52px;
  margin-bottom: 12px;
  animation: float 3s ease-in-out infinite;
}
@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}
.welcome-card h1 {
  font-size: 28px; font-weight: 700;
  background: linear-gradient(135deg, #1a1a2e, #409eff);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin-bottom: 6px;
}
.wc-sub { font-size: 14px; color: #909399; margin-bottom: 32px; }
.wc-features { display: flex; flex-direction: column; gap: 12px; margin-bottom: 28px; }
.wc-feat {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 20px;
  background: rgba(255,255,255,0.8);
  border-radius: 10px;
  border: 1px solid rgba(0,0,0,0.04);
  font-size: 14px; color: #303133;
}
.wc-feat-icon { font-size: 18px; }
.wc-hint { font-size: 13px; color: #c0c4cc; }

/* ===== 消息行 ===== */
.msg-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 24px;
  max-width: 85%;
}
.msg-row.assistant { align-self: flex-start; }
.msg-row.user { margin-left: auto; flex-direction: row-reverse; }

.msg-avatar {
  width: 36px; height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}
.msg-avatar.ai { background: linear-gradient(135deg, #e8f4fd, #d4e9ff); }
.msg-avatar.user { background: linear-gradient(135deg, #409eff, #66b1ff); }

.msg-bubble-wrap { flex: 1; min-width: 0; }
.msg-bubble {
  padding: 12px 18px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
}
.msg-bubble.assistant {
  background: #fff;
  border: 1px solid rgba(0,0,0,0.05);
  border-top-left-radius: 4px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.03);
}
.msg-bubble.user {
  background: linear-gradient(135deg, #409eff, #3a8ee6);
  color: #fff;
  border-top-right-radius: 4px;
}

/* ===== 打字动画 ===== */
.typing-dots { display: flex; gap: 4px; padding: 4px 0; }
.typing-dots span {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #909399;
  animation: dotBounce 1.4s infinite both;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes dotBounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.3; }
  40% { transform: scale(1); opacity: 1; }
}

/* ===== 进度卡片 ===== */
.steps-bar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.step-card {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 12px;
  border: 1px solid #e4e7ed;
  background: #fafbfc;
  transition: all 0.3s ease;
}
.step-card.running {
  border-color: #409eff;
  background: rgba(64,158,255,0.04);
  box-shadow: 0 0 0 2px rgba(64,158,255,0.12);
  animation: stepPulse 2s ease-in-out infinite;
}
.step-card.done {
  border-color: #b3e19d;
  background: rgba(103,194,58,0.04);
}
@keyframes stepPulse {
  0%, 100% { box-shadow: 0 0 0 2px rgba(64,158,255,0.12); }
  50% { box-shadow: 0 0 0 4px rgba(64,158,255,0.06); }
}
.step-icon { font-size: 13px; flex-shrink: 0; }
.step-card.running .step-icon { animation: spin 1.5s linear infinite; }
.step-label { color: #303133; font-weight: 500; white-space: nowrap; }
.step-time { font-size: 11px; color: #909399; flex-shrink: 0; }
.step-time.pulse { color: #409eff; animation: dotPulse 0.8s ease-in-out infinite; }
@keyframes dotPulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}

/* ===== Markdown 样式 ===== */
.msg-content :deep(.code-block) {
  background: #1a1a2e;
  border-radius: 8px;
  margin: 10px 0;
  overflow: hidden;
}
.msg-content :deep(.code-lang) {
  padding: 6px 14px;
  font-size: 11px;
  color: #8899aa;
  text-transform: uppercase;
  letter-spacing: 1px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.msg-content :deep(.code-block pre) { padding: 14px; overflow-x: auto; margin: 0; }
.msg-content :deep(.code-block code) {
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 13px; color: #e0e0e0; line-height: 1.6;
}
.msg-content :deep(code) {
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  background: rgba(0,0,0,0.05);
  padding: 2px 6px;
  border-radius: 4px;
  color: #e43;
}
.msg-content :deep(blockquote) {
  border-left: 3px solid #409eff;
  padding: 8px 14px;
  margin: 8px 0;
  background: rgba(64,158,255,0.04);
  border-radius: 0 6px 6px 0;
  color: #606266;
}
.msg-content :deep(li) { margin: 4px 0 4px 20px; }
.msg-content :deep(b) { font-weight: 600; color: #1a1a2e; }

/* ===== 输入区 ===== */
.chat-input-bar {
  padding: 16px 24px 12px;
  background: rgba(255,255,255,0.7);
  backdrop-filter: blur(8px);
  border-top: 1px solid rgba(0,0,0,0.04);
  flex-shrink: 0;
}
.input-wrapper {
  display: flex;
  gap: 10px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 14px;
  padding: 8px 8px 8px 18px;
  transition: all 0.2s;
  align-items: flex-end;
}
.input-wrapper:focus-within {
  border-color: #409eff;
  box-shadow: 0 0 0 3px rgba(64,158,255,0.08);
}
.input-wrapper textarea {
  flex: 1;
  border: none;
  outline: none;
  font-size: 14px;
  line-height: 1.5;
  resize: none;
  padding: 6px 0;
  font-family: inherit;
  max-height: 120px;
}
.send-pill {
  width: 40px; height: 40px;
  border: none;
  background: linear-gradient(135deg, #409eff, #3a8ee6);
  color: #fff;
  border-radius: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}
.send-pill:hover {
  background: linear-gradient(135deg, #66b1ff, #409eff);
  box-shadow: 0 4px 12px rgba(64,158,255,0.3);
  transform: scale(1.05);
}
.send-pill:disabled {
  background: #c8d6e5;
  box-shadow: none;
  cursor: not-allowed;
  transform: none;
}
.mini-spinner {
  width: 14px; height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
.input-footer {
  text-align: center;
  font-size: 11px;
  color: #c0c4cc;
  margin-top: 8px;
}

/* ===== HITL 确认栏 ===== */
.hitl-bar {
  display: flex;
  justify-content: flex-start;
  padding: 0 0 12px 46px;
}
.hitl-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 20px;
  background: #fff;
  border: 2px solid #e6a23c;
  border-radius: 14px;
  box-shadow: 0 4px 20px rgba(230,162,60,0.15);
  animation: hitlIn 0.3s ease;
}
@keyframes hitlIn {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}
.hitl-icon { font-size: 28px; flex-shrink: 0; }
.hitl-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  color: #606266;
}
.hitl-text b { color: #303133; font-size: 14px; }
.hitl-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.hitl-btn {
  padding: 8px 18px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  transition: all 0.2s;
}
.hitl-btn.approve {
  background: linear-gradient(135deg, #67c23a, #5daf34);
  color: #fff;
}
.hitl-btn.approve:hover { box-shadow: 0 4px 12px rgba(103,194,58,0.3); transform: translateY(-1px); }
.hitl-btn.cancel {
  background: #f5f7fa;
  color: #909399;
  border: 1px solid #e4e7ed;
}
.hitl-btn.cancel:hover { background: #fef0f0; color: #f56c6c; border-color: #f56c6c; }

/* ===== 消息动画 ===== */
.msg-enter-active { transition: all 0.35s ease; }
.msg-enter-from { opacity: 0; transform: translateY(12px); }
.msg-move { transition: transform 0.3s ease; }

.chat-layout,
.chat-panel {
  color: var(--text);
}

.session-sidebar {
  background: rgba(13, 20, 34, .78);
  border-right-color: var(--line);
}

.sidebar-title,
.session-title,
.chat-title,
.step-label,
.msg-content :deep(b) {
  color: var(--text);
}

.sidebar-toggle,
.session-meta,
.model-status,
.input-footer,
.step-time {
  color: var(--muted);
}

.sidebar-toggle:hover,
.session-item:hover {
  color: var(--cyan);
  background: rgba(53, 211, 200, .08);
}

.new-session-btn {
  border-color: rgba(53, 211, 200, .28);
  color: var(--ink-soft);
}

.new-session-btn:hover,
.session-item.active {
  border-color: rgba(53, 211, 200, .36);
  color: var(--cyan);
  background: rgba(53, 211, 200, .08);
}

.chat-topbar,
.chat-input-bar {
  background: rgba(13, 20, 34, .86);
  border-color: var(--line);
}

.model-status {
  background: rgba(101, 212, 154, .08);
  border-color: rgba(101, 212, 154, .22);
  color: var(--green);
}

.chat-messages {
  background:
    radial-gradient(circle at 60% 18%, rgba(106, 140, 255, .08), transparent 30rem),
    transparent;
}

.wc-sub,
.wc-hint {
  color: var(--muted);
}

.welcome-card h1 {
  background: linear-gradient(135deg, #f0f4fb, var(--cyan));
  -webkit-background-clip: text;
}

.wc-feat {
  background: rgba(17, 27, 44, .82);
  border-color: var(--line);
  color: var(--ink-soft);
}

.msg-bubble.assistant {
  background: rgba(17, 27, 44, .9);
  border-color: var(--line);
  box-shadow: 0 12px 30px rgba(0, 0, 0, .16);
}

.msg-avatar.ai {
  background: linear-gradient(135deg, rgba(53, 211, 200, .28), rgba(106, 140, 255, .28));
}

.msg-avatar.user {
  background: linear-gradient(135deg, var(--blue), var(--violet));
}

.step-card {
  border-color: var(--line);
  background: rgba(255, 255, 255, .035);
}

.step-card.running {
  border-color: rgba(106, 140, 255, .62);
  background: rgba(106, 140, 255, .1);
}

.step-card.done {
  border-color: rgba(101, 212, 154, .4);
  background: rgba(101, 212, 154, .08);
}

.msg-content :deep(code) {
  background: rgba(255, 255, 255, .08);
  color: #9de9df;
}

.msg-content :deep(blockquote) {
  color: var(--ink-soft);
  border-left-color: var(--cyan);
  background: rgba(53, 211, 200, .06);
}

.input-wrapper {
  background: #111b2c;
  border-color: var(--line-strong);
}

.input-wrapper textarea {
  color: var(--text);
}

.input-wrapper textarea::placeholder {
  color: var(--muted);
}

.send-pill {
  background: linear-gradient(135deg, var(--blue), var(--violet));
}

.send-pill:disabled {
  background: rgba(157, 178, 207, .2);
}

.hitl-card {
  background: #172238;
  border-color: var(--amber);
  box-shadow: 0 12px 34px rgba(228, 162, 74, .12);
}

.hitl-text {
  color: var(--ink-soft);
}

.hitl-text b {
  color: var(--text);
}

.hitl-btn.cancel {
  background: rgba(255, 255, 255, .04);
  color: var(--muted);
  border-color: var(--line);
}

/* 中断本次回答的二次确认与结果提示：文字按钮不能沿用 40x40 图标胶囊 */
.stream-note {
  margin: 0 0 6px;
  font-size: 12px;
  line-height: 1.5;
  color: #9eacc1;
}
.stream-note.warn { color: #e6a23c; }
.hitl-card.interrupted { border-color: rgba(230, 162, 60, .55); }
.hitl-note { color: #e6a23c; font-size: 12px; }
.cancel-confirm { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cancel-confirm-text { font-size: 12px; color: #e6a23c; line-height: 1.5; }
.send-pill.cancel-generation,
.send-pill.danger,
.send-pill.ghost {
  width: auto;
  min-width: 40px;
  padding: 0 14px;
  font-size: 12px;
  font-family: inherit;
  white-space: nowrap;
}
.send-pill.cancel-generation { background: #f56c6c; }
.send-pill.danger { background: #f56c6c; }
.send-pill.danger:hover { background: #f78c8c; }
.send-pill.ghost {
  background: transparent;
  border: 1px solid rgba(157, 178, 207, .34);
  color: #9eacc1;
}
.send-pill.ghost:hover {
  background: rgba(157, 178, 207, .12);
  transform: none;
}

/* R150 · 三张脸的容器。色值纪律：这里一个新裸色都不写，全部借 theme.css 的 token——
   lint:colors 的告警数此刻正好顶在 334 条预算上，多一条 CI 当场红。需要新 token 走回执具名上报。 */
.face-stack {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  margin-top: var(--s-2);
}

.face-unseen {
  margin: 0;
  padding: var(--s-1) var(--s-2);
  border: 1px dashed var(--border-2);
  border-radius: var(--r-sm);
  font-size: var(--t-xs);
  color: var(--text-3);
}
/* ===== R141 · 档位选择器与生效读数 =====
   一条裸色值都不写：色值预算 148 是上限，多一条 CI 当场红；这里全部走 theme.css 的 token。 */
.lane-bar {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-bottom: var(--s-2);
  flex-wrap: wrap;
}
.lane-label {
  font-size: var(--t-xs);
  color: var(--text-3);
}
.lane-picker {
  font-size: var(--t-xs);
  color: var(--text-2);
  background: var(--surface-2);
  border: 1px solid var(--border-2);
  border-radius: var(--r-sm);
  padding: var(--s-1) var(--s-2);
}
.lane-promise {
  font-size: var(--t-xs);
  color: var(--text-3);
}
.lane-readout {
  margin: 0;
  padding: var(--s-1) var(--s-2);
  border: 1px dashed var(--border-2);
  border-radius: var(--r-sm);
  font-size: var(--t-xs);
  color: var(--text-3);
}
</style>
