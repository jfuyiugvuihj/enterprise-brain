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
  if (!sessions.value.length) {
    const storedActive = loadSessions()
    if (!activeId.value && storedActive) activeId.value = storedActive
  }
  if (!activeId.value) activeId.value = genId()
  // 只在 store 里还没有这份会话时回填，避免把正在写入的流替换掉。
  if (!messages.value.length) restoreActive(activeId.value)
  ensureSession()
  restoreScroll()
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

function queueFaceOf(msg, index) {
  const key = turnKey(msg, index)
  if (rejectedReads.value[key]) return queueRejectedFace(rejectedReads.value[key])
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

      <!-- 消息区 -->
      <div class="chat-messages" ref="chatEl" @scroll.passive="onScroll">
        <div v-if="messages.length === 0" class="welcome-screen">
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

        <TransitionGroup name="msg">
          <div v-for="(msg, i) in messages" :key="i"
               :class="['msg-row', msg.role]">
            <div v-if="msg.role === 'assistant'" class="msg-avatar ai">
              {{ loading && i === messages.length - 1 && !msg.content ? '⏳' : '🤖' }}
            </div>

            <div class="msg-bubble-wrap">
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
                  <SourceCard
                    v-if="sourceFaceOf(msg, i)"
                    :face="sourceFaceOf(msg, i)"
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
