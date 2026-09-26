<script>
/**
 * R288 · G01 —— 「这一篇到底能不能被问到」那张脸的唯一算法，放在模块作用域，
 * 好让用例直接对判据本身打反证，不必隔着模板猜。
 *
 * 读数只有一个来源：GET /documents/catalog 的每一行（app/documents/catalog.py 的
 * public_document_row 随每行发出 parse_status 与 index_status），本屏不新增端点，
 * 也不接半截 —— 拿不到的状态一律画「读不到」。
 *
 * 三条判据写在这里：
 *   1 只有 index_status 为 indexed 才可以说「已可检索」。parse_status 为 ready 只说明
 *      解析那一步成了，不等于检索得到：两枚字段在后端是正交的（index_policy.py 的注释
 *      明写「解析成功但按策略不入索引」没有第五个 parse_status 可写）。
 *      拿 ready 冒充 indexed 就是本仓最看重的那类假话。
 *   2 后端把「没记过」和认不出的值一并归成 pending（catalog.py 的 _normalise_parse_status），
 *      所以 pending 分不出「正在解析」与「这台机器从没记过这一列」，不许画成「解析中」；
 *      只有 parsing 才是后端明说的在途值。
 *   3 「解析中」还有第二条诚实来源：本屏自己那发上传请求还挂着 —— 这是界面亲眼看见的
 *      在途，不是猜的。inflight 由调用方显式传进来，纯函数不读全局状态。
 */
export default { name: 'DocPanel' }

const INDEX_STATUS_EXCLUDED = 'excluded'
const INDEX_STATUS_INDEXED = 'indexed'

/** 后端给的字面量归一：非字符串、大小写、首尾空白都在此收口，其余一律当没读到。 */
function statusWord(value) {
  return typeof value === 'string' ? value.trim().toLowerCase() : ''
}

/** 屏上那几个字只出自这张表；excluded 不在表里，它走 R49 那张「未索引」的脸。 */
export const RETRIEVAL_FACE_LABEL = {
  parsing: '解析中',
  retrievable: '已可检索',
  parsed: '已解析',
  failed: '解析失败',
  stalled: '还没等到结果',
  unreadable: '读不到',
}

/**
 * 一行的检索状态。参数全部显式传入，所以「谁在途」「谁这次没读到」都由调用方负责：
 *   inflight   本屏还挂着上传请求的文件名（界面自己知道的在途，优先级最高）
 *   unreadable 这一格这次取数没成功时点名的文件名（只点刚上传那几条，不牵连同屏其它行）
 *   stalledNames 盯过一整轮窗口仍没落定的文件名：界面不替后端猜，改说「还没等到结果」
 */
export function retrievalFace(row, inflight, unreadable, stalledNames) {
  const source = row && typeof row === 'object' ? row : {}
  const name = typeof source.filename === 'string' ? source.filename : ''
  const waiting = Array.isArray(inflight) ? inflight : []
  const missed = Array.isArray(unreadable) ? unreadable : []
  const expired = Array.isArray(stalledNames) ? stalledNames : []
  if (name && waiting.includes(name)) return 'parsing'
  if (name && missed.includes(name)) return 'unreadable'
  const index = statusWord(source.index_status)
  const parse = statusWord(source.parse_status)
  // excluded 排第一：那一行本来就有「未索引」+ 原因两句话（R49 判据②），本格再摆一张就成三句。
  // 空正文正是这一档最常见的组合：chat.py:3879 给它的读数是 parse_status=failed + excluded。
  if (index === INDEX_STATUS_EXCLUDED) return 'excluded'
  // 最新一版解析失败：这一行的最后一句话必须是失败，不许被上一版留下的 indexed 盖成成功。
  if (parse === 'failed') return 'failed'
  if (index === INDEX_STATUS_INDEXED) return 'retrievable'
  if (parse === 'parsing') return 'parsing'
  if (parse === 'ready') return 'parsed'
  // 后端只给 pending 时，界面分不出「还在解析」与「这一列从没记过」，也就不许装成分得出来：
  // 盯过一整轮窗口的报「还没等到结果」，没盯过的报「读不到」。两张脸都不说「已可检索」。
  return name && expired.includes(name) ? 'stalled' : 'unreadable'
}

/** excluded 返回空串：那一行已经有「未索引」加原因两句话，本格不再重复画一张脸。 */
export function retrievalFaceLabel(face) {
  return RETRIEVAL_FACE_LABEL[face] || ''
}

/**
 * 还没落定的两张脸：解析中与读不到都值得再读一次；其余就是终态。
 * stalled 刻意不在其内 —— 它是「窗口数满，这一屏不再自己猜」的收口，
 * 下一步由人点「再读一次」重新开窗，不由界面在后台无限续期。
 */
export function isUnsettledFace(face) {
  return face === 'parsing' || face === 'unreadable'
}

/** 轮询窗口的两个上限写死在模块里：次数与间隔，不靠调用方每次现编。 */
export const UPLOAD_POLL_MAX_TICKS = 6
export const UPLOAD_POLL_INTERVAL_MS = 1500

/**
 * 有限轮询的停止判据（纯函数）：窗口里一个名字都没有就停；数满上限次数就停；
 * 全部落定就停。返回 true 才许再发下一发取数。
 */
export function shouldReadUploadAgain(faces, ticksDone, maxTicks) {
  const limit = Number.isFinite(maxTicks) ? maxTicks : UPLOAD_POLL_MAX_TICKS
  const done = Number.isFinite(ticksDone) ? ticksDone : 0
  const list = Array.isArray(faces) ? faces : []
  if (done >= limit) return false
  if (!list.length) return false
  return list.some(face => isUnsettledFace(face))
}

// ==================== 上传密级（R313 格一） ====================
/**
 * 默认值就是后端那一句 classification: int = Form(1)（app/api/v1/chat.py:3933）里的 1。
 * 这一枚数字是「用户不动选择框」的唯一出口：表单带着 1 发出去，FastAPI 收到的分类与今天
 * （前端压根不发这一枚字段、由 Form 默认补上 1）逐字相同 —— 落库行、检索判定都不变，零行为变化。
 * 要挪这个默认只能连着后端那句一起挪：只改这里等于把默认悄悄换了位。
 */
export const DEFAULT_UPLOAD_CLASSIFICATION = 1

/**
 * 可选档位只放**今天真有人读得到**的那几档：1/2/3。出处是 app/common/rbac.py:31 的
 * ROLE_CLEARANCE = {staff:1, manager:2, admin:3} —— 检索按「主语 clearance >= 文档密级」判可见，
 * 所以上面这三档每一档都至少有一类账号看得见。
 * 后端词表里还有第 4 档（policy.py:25 core），但今天没有任何角色的 clearance 够得着它：把它放上
 * 下拉，等于让员工一键把自己的资料对全公司【含管理员】锁死，只剩 owner 通道能取回，而且界面上
 * 没有任何一句话会告诉他这件事。放不放 4 档属密级口径，是业主的闸门（H13/U5），不是界面该替客户定的。
 * 本屏也不给档位起名字 —— 3 级在后端同时对应 confidential 与 secret 两枚字面量，替客户挑一个名字
 * 就是造假。下拉每一档显示的仍是 lib/provenance.js 的 classificationLabel 那一句「密级 N 级」，全站只有那一份措辞。
 */
export const UPLOAD_CLASSIFICATION_LEVELS = Object.freeze([1, 2, 3])

/**
 * 表单值归一：只有名单里的整数才发得出去。空串、NaN、越界、被人手改过的 DOM value 一律退回默认档，
 * 免得把垃圾值写进 classification 那枚 NOT NULL 列 —— 后端不做白名单校验（它按 principal 判可见性），
 * 界面这边不能跟着不设防。
 */
export function normalizeClassification(value) {
  const level = Number(value)
  return UPLOAD_CLASSIFICATION_LEVELS.includes(level)
    ? level
    : DEFAULT_UPLOAD_CLASSIFICATION
}

// ==================== 行内真值（R313 格三） ====================
// 三句话读的全是 app/documents/catalog.py::public_document_row 随【每一行】发出的既有字段
// （owner_id / size_bytes / parse_status），本格不为任何人多开一次请求，也不要求后端加字段。
// 取不到就是取不到：那一格说「读不到」，不拿 0 B、不拿「无主」顶替。

/** 没有可信读数时的说法。与上面 retrievalFace 的「读不到」同词，不在这里另立第二套。 */
export const TRUTH_UNREADABLE_SUFFIX = '读不到'

/**
 * 归属人。后端把无主行记成 None（catalog.py 的 _is_unowned：None 或纯空白），legacy 行就是这个形状。
 * 键【缺席】是另一件事：那是老部署只回一串文件名时本屏自己造的 { filename } 行，服务端压根没答过
 * 归属，所以它不许被画成「无主」—— 那是一句关于数据的断言，而这一屏在那里没有断言的资格。
 */
export function ownerTruth(row) {
  const source = row && typeof row === 'object' ? row : {}
  if (!Object.prototype.hasOwnProperty.call(source, 'owner_id')) return '上传者' + TRUTH_UNREADABLE_SUFFIX
  const raw = source.owner_id
  const text = raw === null || raw === undefined ? '' : String(raw).trim()
  return text ? `上传者 ${text}` : '上传者无主'
}

/**
 * 「这一格有没有读数」只判一次。null / undefined / 空串 / 布尔 / 对象都不算数 —— 这里必须点名
 * 一条 JavaScript 的坑：Number(null) 与 Number('') 都是 0，直接 Number() 一下就把「后端没给出大小」
 * 画成了「0 B」，那是一句关于文件大小的假话（catalog.py::_resolved_size 返回的正是 int 或 None）。
 */
export function sizeNumber(value) {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'boolean' || typeof value === 'object') return null
  const size = Number(value)
  return Number.isFinite(size) && size >= 0 ? Math.trunc(size) : null
}

/** 字节数成人话：分档尺子与 app/api/v1/data.py::_format_data_file_size 同一把（B / KB / MB，一位小数）。 */
export function documentSizeLabel(bytes) {
  const size = sizeNumber(bytes)
  if (size === null) return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

export function sizeTruth(row) {
  const source = row && typeof row === 'object' ? row : {}
  const label = documentSizeLabel(source.size_bytes)
  return label ? `大小 ${label}` : '大小' + TRUTH_UNREADABLE_SUFFIX
}

/**
 * 这一版解析到哪一步。后端只有四个合法值（catalog.py 的 PARSE_STATUSES，migrations/0006 的 CHECK），
 * 而 _normalise_parse_status 把「没记过」与认不出的值一并归成 pending —— 所以 pending 与键缺席都画
 * 「读不到」：这一屏分不出「正在解析」与「这台机器从没记过这一列」，也就不许装成分得出来。
 * 这条口径承接上面判据 2 已成的结论，不是本单新立的。
 */
export const VERSION_STAGE_LABEL = {
  ready: '本版 解析完成',
  parsing: '本版 解析中',
  failed: '本版 解析失败',
}

export function stageTruth(row) {
  const source = row && typeof row === 'object' ? row : {}
  return VERSION_STAGE_LABEL[statusWord(source.parse_status)] || '本版 ' + TRUTH_UNREADABLE_SUFFIX
}
</script>

<script setup>
import { computed, onDeactivated, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { http, errorDetail } from '../lib/http'
import DocumentPreviewModal from './DocumentPreviewModal.vue'
import { UiButton, UiEmptyState, UiErrorState } from './ui'
// 删除确认沿用本仓已有那一套两步内联状态机（ArtifactList.vue 的 advanceDelete，
// DataPanel.vue 与 ChatPanel.vue 都是这么引的），不再新建第三套词汇。
import { advanceDelete, deleteButtonLabel, isPendingDelete } from './ArtifactList.vue'
// 密级这一格不自造措辞：整数级怎么说成人话，全站只有 lib/provenance.js 那一份口径
// （classificationLabel：整数级就说「密级 N 级」，不替客户发明档位名字）。
import { classificationLabel } from '../lib/provenance'

// 列表存的是【行】而不是裸文件名：GET /documents/catalog 每一行都带着
// index_status / index_reason（app/documents/catalog.py 的 public_document_row），
// R49 判据②要的那张「未索引」脸只能从这两枚字段来。以前这里把行压成 filename 就丢掉
// 了它们 —— 服务端答了，界面把答案扔了，用户上传被排除的那篇就此在库里查无此脸。
const docs = ref([])
// R313 格二 · 「有 N 份存在，但你看不见」那一格。读的是 GET /documents/catalog 成功体里的
// restricted（app/api/v1/chat.py:4235；形状只出自 app/api/v1/restricted.py 那一份 —— R200）。
// 后端早就把这句话发出来了，界面此前一个字都不提，权限不足的员工站在有资料的库里听到的仍是
// 「知识库是空的」—— 那是会让人去重复上传、去找管理员的假话，不是措辞洁癖。
// 这里只取 count 与 message 两格：restricted_summary 本来就不点名资源，界面这边一枚也不补。
const restricted = ref(null)
// 本面板自己的失败提示；401 不在这里判，统一交给 lib/http.js 的响应拦截。
const notice = ref('')
// notice 以前是一句话，外加一个不管发生什么都「重新加载列表」的按钮。
// 现在把「哪一种事没成」和「重载列表是不是真的补救动作」分开带，交给 UiErrorState 呈现。
const noticeTitle = ref('知识库这一步没有完成')
const noticeRetry = ref(false)

function raiseNotice(title, detail, retryable) {
  noticeTitle.value = title
  notice.value = detail
  noticeRetry.value = Boolean(retryable)
}

function dismissNotice() {
  notice.value = ''
  noticeRetry.value = false
}
const uploads = ref([])
const dragOver = ref(false)
const props = defineProps({
  userRole: {
    type: String,
    default: 'staff'
  }
})
const isAdmin = computed(() => props.userRole === 'admin')
const searchQuery = ref('')
// R313 格一 · 这一发上传按几级走。默认值与后端 chat.py 的 Form(1) 同值：不碰选择框 ⇒ 发出去的
// 仍是 1 级，与今天（压根不发这一枚字段）等价。改它只影响改后拼出去的那几份表单：
// 每一发读这一枚值的时刻在「建 FormData 那一刻」（见 uploadSingleFile），表单拼完之后再改下拉追不上它。
const uploadClassification = ref(DEFAULT_UPLOAD_CLASSIFICATION)

/**
 * 密级这一格的说法只经由全站那一份 classificationLabel（lib/provenance.js:147：整数级就说「密级 N 级」，
 * 不替客户发明档位名字）。它吃的是字符串（同文件 textOf 只认 string），所以这里补那一枚转换，
 * 措辞一个字都不改；顺手把值归一，屏上说的与表单发的中间就没有第二条路。
 */
function classificationWords(level) {
  return classificationLabel(String(normalizeClassification(level)))
}

/** 下拉里的每一档：文案走上面那一枚出口，本屏只负责把档位排出来。 */
const classificationChoices = computed(() => UPLOAD_CLASSIFICATION_LEVELS.map(level => ({
  value: level,
  label: classificationWords(level),
  isDefault: level === DEFAULT_UPLOAD_CLASSIFICATION,
})))

/** 选择框旁边那一句：只说这一屏真做得到的事。部门那一格归服务端（chat.py 的 docstring 明写理由）。 */
const classificationNote = computed(() =>
  `这一发按 ${classificationWords(uploadClassification.value)} 上传 · 部门由服务端按你的账号判定`)

/**
 * 后端在成功体里说「有 N 份文档存在，但不在当前账号的可见范围内」，界面此前一个字都不提。
 * 计数只认正整数：restricted_summary 给的是 len(withheld)，界面上不许出现 NaN、负数或小数
 * 冒充份数；拿不到正的数就当这一格不存在。这把尺与 DataPanel.vue 的 rowCount 同一条（R186 已成口径）。
 */
function restrictedCount(value) {
  const count = Number(value)
  return Number.isFinite(count) && count > 0 ? Math.trunc(count) : 0
}

/** message 缺席时的兜底句：句式与后端那一句同构，只是没有数（有数的时候一律用后端原句）。 */
const RESTRICTED_DOCS_FALLBACK =
  '有文档存在，但不在当前账号的可见范围内，所以没有出现在上面的列表里；如需访问，请联系管理员核对你的部门归属与文档的部门、密级标注。'

/**
 * 那一格的正脸：说「有 N 份存在但你看不见」，一个文件名都不点。
 * 点名一件对方无权访问的文档本身就是泄露，后端那两份投影里也没有名字，界面这边一枚都不补。
 * 形状照 DataPanel.vue:288 的 restrictedNotice，不另创第二套说法。
 */
const restrictedNotice = computed(() => {
  const tally = restricted.value
  const count = restrictedCount(tally && tally.count)
  if (!count) return null
  return {
    count,
    title: `还有 ${count} 份文档没有列在这里`,
    description: String((tally && tally.message) || '') || RESTRICTED_DOCS_FALLBACK,
  }
})
const preview = reactive({
  open: false,
  filename: '',
  kind: 'text',
  text: '',
  blobUrl: '',
  loading: false,
  error: '',
  truncated: false
})

function startProgressTimer(item) {
  item.progress = Math.max(item.progress, 5)
  item.progressTimer = setInterval(() => {
    if (item.status !== 'uploading') {
      stopProgressTimer(item)
      return
    }
    const limit = item.phase === 'processing' ? 99 : 60
    if (item.progress < limit) {
      item.progress += Math.max(1, Math.ceil((limit - item.progress) * 0.12))
    }
  }, 400)
}

function stopProgressTimer(item) {
  if (!item.progressTimer) return
  clearInterval(item.progressTimer)
  item.progressTimer = null
}

function createUploadItem(file) {
  return reactive({
    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    name: file.name,
    status: 'uploading',
    phase: 'uploading',
    progress: 0,
    progressTimer: null,
    msg: '正在上传...',
    // 队列项带得上「这一发实际带出去的那一档」，回执之后回看还在（R313 格一）。
    // 初值就是后端 Form(1) 那一枚：uploadSingleFile 建表单时会按选择框改写它。
    classification: DEFAULT_UPLOAD_CLASSIFICATION
  })
}

// ==================== 未索引那张脸（R49 判据②） ====================
// 两枚字面量与 retrievalFace 共用模块作用域里的那一份，不在这里再声明一遍。

// 后端把「为什么没入索引」编成了稳定码（app/documents/index_policy.py），这里只把码念成
// 人话：句子不带数字，也不带码名——实测长度与阈值归服务端那句 notice 说，界面不另算一份。
const INDEX_REASON_TEXT = {
  no_text_content: '解析出来是空的，正文里没有可检索的文字',
  below_minimum_size: '正文太短，承载不了可检索的信息',
  placeholder_skeleton: '正文以未填写的占位符为主，按模板骨架处理',
  outline_only_shell: '只有小节标题、正文没有内容，按草稿骨架处理',
  unchanged_content: '同名文档内容未变化，索引沿用了已有版本',
  index_refused: '索引层拒绝了这份正文',
}
const INDEX_REASON_UNKNOWN = '该文档未进入知识库索引'

/** 三态分明：excluded 才有脸，indexed 不涂，键 absent 是 R49 之前入库的历史行。
 *  契约（catalog.py 的 public_document_row）明写客户端不许靠字段消失去推断，也不许把
 *  「从没判过」画成「故意不入索引」—— 所以 unrecorded 这一格什么都不画。 */
function indexStatus(row) {
  const status = row.index_status
  return status === INDEX_STATUS_EXCLUDED || status === INDEX_STATUS_INDEXED ? status : 'unrecorded'
}

function isExcluded(row) {
  return indexStatus(row) === INDEX_STATUS_EXCLUDED
}

function indexReasonText(row) {
  const reason = row.index_reason
  const known = typeof reason === 'string' && Object.prototype.hasOwnProperty.call(INDEX_REASON_TEXT, reason)
  return known ? INDEX_REASON_TEXT[reason] : INDEX_REASON_UNKNOWN
}

const excludedDocs = computed(() => docs.value.filter(row => isExcluded(row)))

// 过滤后的文档列表
// 搜索无结果的那句话里带双引号，放进模板属性字面量会撞 Vue 的无引号属性限制，
// 所以在 script 里拼；文案与接线前逐字相同。
const noMatchTitle = computed(() => `没有匹配 "${searchQuery.value}" 的文档`)

const filteredDocs = computed(() => {
  if (!searchQuery.value) return docs.value
  const q = searchQuery.value.toLowerCase()
  return docs.value.filter(row => row.filename.toLowerCase().includes(q))
})

/**
 * restricted 只按【形状】读：这一格只承认 count 与 message 两枚字段，别的一概不带进界面。
 * 后端今天不给名字（restricted_summary 的注释明写「资源标识一个字节都不进返回体」），
 * 界面这里再设一道：将来谁把投影改胖了，也带不出一串文件清单。
 */
function readRestricted(payload) {
  if (!payload || typeof payload !== 'object') return null
  return { count: payload.count, message: payload.message }
}

/** 返回值就是「这一发列表读到了没有」：轮询那一格要据此决定读不读得到状态。 */
async function loadDocs() {
  dismissNotice()
  // 上一轮那句「有 N 份看不见」不属于这一轮：重载先清，失败也清，不许留成陈话（与 DataPanel 同一条）。
  restricted.value = null
  try {
    const res = await http.get('/documents/catalog', {
      params: { _ts: Date.now() }
    })
    // 行原样留下，索引状态才有地方住；老部署只回一串文件名时也接得住（回退成 unrecorded）。
    docs.value = (res.data.documents || [])
      .map(item => (typeof item === 'string' ? { filename: item } : item))
      .filter(row => Boolean(row && row.filename))
    // 服务端这一腿答了「有 N 份你看不见」，界面就得说这句话；它没给就是真没有。
    restricted.value = readRestricted(res.data.restricted)
    return true
  } catch (err) {
    restricted.value = null
    console.error('文档列表加载失败', err)
    raiseNotice('文档列表没加载出来', errorDetail(err, '文档列表加载失败'), true)
    return false
  }
}

async function fetchDocumentBlob(filename, inline = false) {
  const res = await http.get(`/documents/${encodeURIComponent(filename)}/file`, {
    responseType: 'blob',
    params: { inline, _ts: Date.now() }
  })
  return res.data
}

async function openDocument(filename) {
  if (preview.blobUrl) {
    URL.revokeObjectURL(preview.blobUrl)
    preview.blobUrl = ''
  }
  preview.open = true
  preview.filename = filename
  preview.kind = 'text'
  preview.text = ''
  preview.loading = true
  preview.error = ''
  preview.truncated = false
  try {
    const res = await http.get(`/documents/${encodeURIComponent(filename)}/preview`, {
      params: { _ts: Date.now() }
    })
    preview.kind = res.data.kind || 'text'
    preview.text = res.data.text || ''
    preview.truncated = Boolean(res.data.truncated)
    if (preview.kind === 'pdf') {
      const blob = await fetchDocumentBlob(filename, true)
      preview.blobUrl = URL.createObjectURL(blob)
    }
  } catch (err) {
    preview.error = errorDetail(err, '文件预览失败')
  } finally {
    preview.loading = false
  }
}

function closeDocumentPreview() {
  preview.open = false
  if (preview.blobUrl) {
    URL.revokeObjectURL(preview.blobUrl)
    preview.blobUrl = ''
  }
}

async function downloadDocument(filename) {
  try {
    const blob = await fetchDocumentBlob(filename, false)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (err) {
    raiseNotice('文件没能下载', errorDetail(err, '文件下载失败'), false)
  }
}

async function uploadFilesParallel(files) {
  const tasks = files.map(file => uploadSingleFile(file))
  await Promise.allSettled(tasks)
  await loadDocs()
}

// 🔴 这两枚签名（uploadSingleFile(file) / createUploadItem(file)）钉在
// tests/test_frontend_upload_auth.py:66-68 与 :99 那三枚字面量上（本单写集之外，一字未动）。
// 密级这一格因此不走「多传一枚参数」，改成建表单那一刻现读选择框 —— 语义等价：JS 单线程，
// uploadFilesParallel 的 map 会把每一发的表单在同一次同步执行里拼完，之后改下拉追不上已拼好的那几份。
async function uploadSingleFile(file) {
  const item = createUploadItem(file)
  uploads.value.unshift(item)
  startProgressTimer(item)
  const form = new FormData()
  form.append('file', file)
  // R313 格一：密级这一枚值【真发出去】。在这一行之前整个面板只有上面那一枚 append，所以后端
  // 永远拿的是 Form(1) 那个默认 —— 上传人从没被问过一句，全库默认 1 级。
  // 不碰选择框时这里发的就是同一枚 1：请求结果与今天相同（FastAPI 今天用 Form 默认补的那一枚也是 1）。
  // 🔴 这里永远不 append department：app/api/v1/chat.py 那段 docstring 写明了理由 —— 检索按
  // 【来问的人】的部门去匹配文档，客户端能挑部门就等于允许往别人的结果里投稿，服务端按 principal 自己定。
  item.classification = normalizeClassification(uploadClassification.value)
  form.append('classification', String(item.classification))
  try {
    const res = await http.post('/upload', form, {
      onUploadProgress: (event) => {
        if (event.total) {
          const uploaded = event.loaded / event.total
          item.progress = Math.max(item.progress, Math.min(70, Math.round(uploaded * 70)))
        }
        if (!event.total || event.loaded >= event.total) {
          item.phase = 'processing'
          item.msg = '正在解析并入库...'
        }
      }
    })
    stopProgressTimer(item)
    item.progress = Math.max(item.progress, 70)
    item.status = res.data.status === 'ok' ? 'done' : 'skipped'
    if (item.status === 'done') {
      item.progress = 100
      item.phase = 'done'
    }
    item.msg = res.data.message || '上传完成'
    await loadDocs()
    // G01：回执落地才打开轮询窗口，盯的就是刚传的这一批。文件名取回执那一份，不拿本地
    // File.name 顶 —— 服务端会把显示名规范化，两串不是一回事。
    armUploadPoll([res.data.filename || item.name])
  } catch (err) {
    stopProgressTimer(item)
    item.status = 'error'
    item.phase = 'error'
    item.msg = errorDetail(err, '上传失败')
  }
}

function onFileInput(e) {
  if (e.target.files.length) uploadFilesParallel([...e.target.files])
  e.target.value = ''
}

/**
 * 密级这一格只有这一枚入口：DOM 交回来的永远是字符串（"3"），越界与垃圾一律走
 * normalizeClassification 那道门退回默认档。所以「屏上显示的那一档」与「表单发出去的那一档」
 * 中间不存在第二条路 —— 也就不会出现界面写着 3 级、请求里其实另有一枚值。
 */
function chooseClassification(value) {
  uploadClassification.value = normalizeClassification(value)
}

/** 同一枚判据的 data-* 通道：没有读数就留空串，不写 0、也不写 "null" 这种看着像值的字符串。 */
function sizeAttr(row) {
  const source = row && typeof row === 'object' ? row : {}
  const size = sizeNumber(source.size_bytes)
  return size === null ? '' : String(size)
}

function onDrop(e) {
  dragOver.value = false
  if (e.dataTransfer?.files.length) uploadFilesParallel([...e.dataTransfer.files])
}

// 批量删除
const selectedFiles = ref(new Set())
const deleting = ref(false)
// G15：删除确认改成两步内联，不再用浏览器原生弹窗。两个理由都写在判据里：原生弹窗在
// 渲染型测试里根本不出现（那些「删之前必须先确认」的用例等于没验过），而私有化客户机上
// 浏览器策略常把它静默拦掉 —— 拦掉之后那句「要不要删」压根没露过面，一次点击就直接删。
// 这里第一次点击只把目标标成待确认，同一目标第二次点击才发请求；换了目标只会把待确认
// 挪过去，一次错位的点击删不掉没点过的那一行。与产物列表、数据文件删除共用同一枚状态机。
const pendingDelete = ref('')

/** 待确认目标分两个命名空间：单行按文件名、批量按选择集，二者形状不同永不相撞。 */
function rowDeleteKey(filename) {
  return 'row:' + String(filename ?? '')
}

function batchDeleteKey(files) {
  const list = Array.isArray(files) ? files : [...(files || [])]
  return 'batch:' + list.map(String).sort().join('\u0001')
}

// 改选择集就是改「要删哪些」：待确认必须作废，不许拿着上一版的确认去删这一版的选择。
watch(
  () => [...selectedFiles.value].map(String).sort().join('\u0001'),
  () => { pendingDelete.value = '' },
)

/** advanceDelete 三档收口：arm 只记账，execute 才清账放行，idle 什么都不做。 */
function stepDelete(key) {
  const step = advanceDelete(pendingDelete.value, key)
  pendingDelete.value = step === 'arm' ? key : ''
  return step
}

function cancelDelete() {
  pendingDelete.value = ''
}

function toggleSelect(filename) {
  if (!isAdmin.value) return
  if (selectedFiles.value.has(filename)) {
    selectedFiles.value.delete(filename)
  } else {
    selectedFiles.value.add(filename)
  }
}

function toggleAll() {
  if (selectedFiles.value.size === filteredDocs.value.length) {
    selectedFiles.value.clear()
  } else {
    filteredDocs.value.forEach(row => selectedFiles.value.add(row.filename))
  }
}

async function deleteDocuments(files) {
  if (!files.length || deleting.value) return
  deleting.value = true
  try {
    const results = await Promise.allSettled(
      files.map(filename => http.delete(`/documents/${encodeURIComponent(filename)}`))
    )
    const failed = results
      .filter(r => r.status === 'rejected')
      .map(r => errorDetail(r.reason, ''))
      .filter(Boolean)
    selectedFiles.value.clear()
    await loadDocs()
    if (failed.length) raiseNotice('部分文档没能删除', `有 ${failed.length} 个文档未能删除：${failed.join('、')}`, false)
  } catch (err) {
    raiseNotice('删除没有完成', errorDetail(err, '删除失败'), false)
  } finally {
    deleting.value = false
  }
}

/** 批量那一枚的待确认：🔴 这里传的是【值】不是 ref，脚本里不解包就永远比不中。 */
function batchDeleteArmed() {
  return isPendingDelete(pendingDelete.value, batchDeleteKey([...selectedFiles.value]))
}

async function requestDeleteSelected() {
  const files = [...selectedFiles.value]
  if (!files.length || deleting.value) return
  if (stepDelete(batchDeleteKey(files)) !== 'execute') return
  await deleteDocuments(files)
}

async function requestDeleteOne(filename) {
  const target = String(filename ?? '')
  if (!target || deleting.value) return
  if (stepDelete(rowDeleteKey(target)) !== 'execute') return
  await deleteDocuments([target])
}

// ==================== 刚上传那一批的有限轮询（R288 G01） ====================
// 窗口只由「上传回执」这个用户动作打开；落定、离开这一屏、或数满 UPLOAD_POLL_MAX_TICKS
// 次就关。不是常驻定时器，也不在挂载期发任何新请求 —— 读的还是现成那一条
// GET /documents/catalog，行级 parse_status 的唯一事实源，本单一个字都没动后端。
const uploadWatch = ref([])
const uploadPollTicks = ref(0)
const uploadPollFault = ref(false)
// 窗口数满仍未落定的那几个名字：它们画「还没等到结果」，既不画「解析中」也不画「读不到」。
const uploadStalled = ref([])
let uploadPollTimer = null

// 本屏自己那发上传还挂着的那些文件：只有这是界面亲眼看见的在途，才允许画「解析中」。
const inflightUploads = computed(() => uploads.value
  .filter(upload => upload.status === 'uploading')
  .map(upload => upload.name))

// 轮询那一发取数失败时，只把「刚上传那一批」点名为读不到：同屏其它行是上一版真读到的，
// 把它们一起涂成读不到同样是假话。
const unreadableUploads = computed(() => (uploadPollFault.value ? uploadWatch.value : []))

function rowFaceKey(row) {
  return retrievalFace(row, inflightUploads.value, unreadableUploads.value, uploadStalled.value)
}

/** 「还没等到结果」这一格配一枚「再读一次」：出口由人点，不由界面在后台无限续。 */
function rowNeedsRecheck(row) {
  return rowFaceKey(row) === 'stalled'
}

function rowFaceText(row) {
  return retrievalFaceLabel(rowFaceKey(row))
}

/**
 * 收掉窗口。带名字收＝数满次数仍未落定，把它们点名为「还没等到结果」；
 * 不带名字收＝读数已落定或人离开这一屏，一张新脸都不留。
 */
function stopUploadPoll(stalledNames) {
  if (uploadPollTimer !== null) {
    clearTimeout(uploadPollTimer)
    uploadPollTimer = null
  }
  const expired = Array.isArray(stalledNames) ? stalledNames.map(String).filter(Boolean) : []
  uploadStalled.value = expired
  uploadWatch.value = []
  uploadPollTicks.value = 0
  uploadPollFault.value = false
}

function armUploadPoll(names) {
  const incoming = (Array.isArray(names) ? names : [names]).map(String).filter(Boolean)
  if (!incoming.length) return
  // 重新盯就是重新等：上一轮的「还没等到结果」必须作废，否则两句话会同时挂在同一行上。
  uploadStalled.value = uploadStalled.value.filter(name => !incoming.includes(name))
  uploadWatch.value = [...new Set([...uploadWatch.value, ...incoming])]
  uploadPollTicks.value = 0
  uploadPollFault.value = false
  scheduleUploadPoll()
}

function scheduleUploadPoll() {
  if (uploadPollTimer !== null) clearTimeout(uploadPollTimer)
  uploadPollTimer = setTimeout(runUploadPollTick, UPLOAD_POLL_INTERVAL_MS)
}

async function runUploadPollTick() {
  uploadPollTimer = null
  const watched = uploadWatch.value
  if (!watched.length) return
  uploadPollTicks.value += 1
  const read = await loadDocs()
  uploadPollFault.value = !read
  const faces = watched.map(filename => {
    const row = docs.value.find(item => item.filename === filename)
    return row === undefined ? 'unreadable' : rowFaceKey(row)
  })
  if (shouldReadUploadAgain(faces, uploadPollTicks.value, UPLOAD_POLL_MAX_TICKS)) {
    scheduleUploadPoll()
    return
  }
  // 收窗口有两种收法：全部落定就安静收；数满次数还没落定的那几个要留一张「还没等到结果」。
  // 少了这一笔，这一屏就是判据①明令禁止的「静默停在解析中」。
  const expired = uploadPollTicks.value >= UPLOAD_POLL_MAX_TICKS
    ? watched.filter((name, at) => isUnsettledFace(faces[at]))
    : []
  stopUploadPoll(expired)
}

function fileIcon(name) {
  if (name.includes('案例')) return '📋'
  if (name.includes('MYO') || name.includes('MYBI') || name.includes('MYOps')) return '🔧'
  if (name.includes('制度') || name.includes('管理') || name.includes('规范')) return '📜'
  if (name.includes('报告') || name.includes('分析') || name.includes('经营')) return '📊'
  if (name.includes('会议') || name.includes('纪要')) return '📝'
  if (name.includes('法律') || name.includes('合规') || name.includes('安全')) return '🔒'
  if (name.includes('通知') || name.includes('放假') || name.includes('团建') || name.includes('年会')) return '📢'
  if (name.includes('教程') || name.includes('培训') || name.includes('指南') || name.includes('入职')) return '📖'
  return '📄'
}

function clearUploads() {
  uploads.value = uploads.value.filter(u => u.status === 'uploading')
}

// 挂载期这一发列表是 R49 之前就有的既有行为；本单不在 onMounted 里加任何新的自动请求，
// 上传之后的有限轮询只由「刚上传」那个动作打开（见 armUploadPoll）。
onMounted(loadDocs)
onUnmounted(() => {
  uploads.value.forEach(stopProgressTimer)
  stopUploadPoll()
})
// 离开这一屏就关掉窗口：KeepAlive 把面板缓存着，人不在屏上不该继续替它发请求。
onDeactivated(stopUploadPoll)
</script>

<template>
  <div class="doc-panel" data-testid="documents-panel">
    <!-- 面板标题 -->
    <div class="panel-hd">
      <div class="panel-hd-left">
        <span>📁</span>
        <strong>知识库</strong>
        <span class="badge">{{ docs.length }}</span>
      </div>

      <!-- 管理员开关 -->
    </div>

    <!-- 面板级失败提示：可重试，不用原生弹窗 -->
    <UiErrorState
      v-if="notice"
      :title="noticeTitle"
      :description="notice"
      :retryable="false"
      dense
    >
      <template #actions>
        <UiButton v-if="noticeRetry" variant="secondary" size="sm" label="重新加载" data-testid="documents-notice-retry" @click="loadDocs" />
        <UiButton variant="ghost" size="sm" label="关闭" data-testid="documents-notice-close" @click="dismissNotice" />
      </template>
    </UiErrorState>

    <!-- 搜索 -->
    <div class="search-bar">
      <span class="search-icon">🔍</span>
      <input v-model="searchQuery" placeholder="搜索文档..." class="search-input" />
      <span v-if="searchQuery" class="search-result">
        {{ filteredDocs.length }}/{{ docs.length }}
      </span>
    </div>

    <!-- 上传区（紧凑） -->
    <div class="drop-zone" data-testid="document-drop-zone" :class="{ drag: dragOver }"
         @dragover.prevent="dragOver = true"
         @dragleave.prevent="dragOver = false"
         @drop.prevent="onDrop">
      <label class="upload-label">
        <span class="upload-icon">☁️</span>
        <span>拖拽或点击上传 · 支持多选</span>
        <input data-testid="document-upload-input" type="file" hidden multiple accept=".pdf,.docx,.doc,.txt" @change="onFileInput" />
      </label>
    </div>

    <!-- R313 · 格一：上传时终于问一句密级。用原生 <select>（与 ChatPanel 那两枚选择框同一条规矩：
         键盘 / 读屏 / 输入法行为不重新发明，也不新增色值）。默认档就是后端 Form(1) 的那一枚 1，
         不动它 = 今天的行为。🔴 这一屏只有密级、没有部门：部门由服务端按 principal 判（chat.py 写明理由）。 -->
    <div class="classification-bar" data-testid="document-classification-picker">
      <label class="classification-label" for="document-classification-select">这一发的密级</label>
      <select
        id="document-classification-select"
        class="classification-picker"
        data-testid="document-classification-select"
        :value="uploadClassification"
        @change="chooseClassification($event.target.value)"
      >
        <option
          v-for="choice in classificationChoices"
          :key="choice.value"
          :value="choice.value"
        >{{ choice.label }}{{ choice.isDefault ? '（默认）' : '' }}</option>
      </select>
      <span class="classification-note" data-testid="document-classification-note">{{ classificationNote }}</span>
    </div>

    <!-- 上传队列 -->
    <TransitionGroup name="queue">
      <div v-for="item in uploads" :key="item.id" :class="['upload-item', item.status]">
        <span v-if="item.status === 'uploading'" class="sr-only" role="status">正在解析入库</span>
        <svg
          v-if="item.status === 'uploading'"
          class="upload-progress-ring"
          aria-hidden="true"
          viewBox="0 0 24 24"
        >
          <circle
            cx="12"
            cy="12"
            r="9"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-dasharray="42 14"
          />
        </svg>
        <span v-else>{{ item.status === 'done' ? '✅' : item.status === 'skipped' ? '⏭️' : '❌' }}</span>
        <div class="up-body">
          <div class="up-line">
            <span class="up-name">{{ item.name }}</span>
            <span class="up-msg">{{ item.status === 'uploading' ? (item.phase === 'processing' ? '解析入库中...' : '上传中...') : item.msg }}</span>
            <!-- 这一发【实际带出去的】那一档：界面说的与表单发的是同一枚值，不是选择框现在的样子。 -->
            <span class="up-class" data-testid="upload-item-classification">{{ classificationWords(item.classification) }}</span>
          </div>
          <div
            v-if="item.status === 'uploading' || item.status === 'done'"
            class="upload-progress-track"
            role="progressbar"
            aria-label="文件上传进度"
            :aria-valuenow="item.progress"
            aria-valuemin="0"
            aria-valuemax="100"
          >
            <div class="upload-progress-bar" :style="{ width: `${item.progress}%` }"></div>
          </div>
          <div v-if="item.status === 'uploading' || item.status === 'done'" class="upload-progress-meta">
            <span>{{ item.phase === 'done' ? '上传完成' : item.phase === 'processing' ? '解析入库中...' : '上传中...' }}</span>
            <span>{{ item.progress }}%</span>
          </div>
        </div>
      </div>
    </TransitionGroup>

    <UiButton
      v-if="uploads.some(u => u.status !== 'uploading')"
      class="clear-btn"
      variant="ghost"
      size="sm"
      label="清除已完成"
      data-testid="documents-clear-uploads"
      @click="clearUploads"
    />

    <!-- 批量操作栏（管理员可见） -->
    <div v-if="isAdmin && filteredDocs.length > 0" class="batch-bar">
      <label class="batch-toggle" @click.prevent="toggleAll">
        <input type="checkbox" :checked="selectedFiles.size === filteredDocs.length && filteredDocs.length > 0" />
        <span class="batch-text">
          {{ selectedFiles.size ? `已选 ${selectedFiles.size} 个` : '全选' }}
        </span>
      </label>
      <span v-if="selectedFiles.size" class="batch-actions">
        <UiButton
          class="batch-del"
          variant="danger"
          size="sm"
          :loading="deleting"
          :label="deleteButtonLabel({ pending: batchDeleteArmed(), busy: deleting, label: '🗑 删除选中' })"
          data-testid="documents-delete-selected"
          @click="requestDeleteSelected"
        />
        <UiButton
          v-if="batchDeleteArmed()"
          variant="ghost"
          size="sm"
          label="取消"
          data-testid="documents-delete-selected-cancel"
          @click="cancelDelete"
        />
        <!-- 原生弹窗那句「无法恢复」不能因为换成内联确认就丢掉：待确认时把它写在按钮旁边。 -->
        <span
          v-if="batchDeleteArmed()"
          class="batch-note"
          role="status"
          data-testid="documents-delete-warning"
        >删除后无法恢复</span>
      </span>
    </div>

    <!-- 文档列表 -->
    <div class="doc-list" data-testid="document-list">
      <!-- R313 · 格二：「知识库是空的」只在【真的一枚都没有】时才许说出口。
           后端在同一个成功体里另挂了 restricted（app/api/v1/chat.py:4235）=「有，但你看不见」，
           那是与「没有」正相反的一句话，两句不许同时站在这块屏上（与 DataPanel 判据 1④ 同一条）。 -->
      <UiEmptyState v-if="docs.length === 0 && !restrictedNotice" title="知识库是空的" description="上传公司制度、手册或数据开始" />
      <UiEmptyState v-else-if="docs.length > 0 && filteredDocs.length === 0" :title="noMatchTitle" dense />

      <TransitionGroup name="list" tag="div">
        <div v-for="row in filteredDocs" :key="row.filename" data-testid="doc-row"
             :class="['doc-row', { selected: selectedFiles.has(row.filename) }]"
             :data-index-status="indexStatus(row)"
             :data-index-reason="row.index_reason || ''"
             @click="toggleSelect(row.filename)">
          <!-- 选择框（管理员） -->
          <span v-if="isAdmin" class="check-box">
            {{ selectedFiles.has(row.filename) ? '☑' : '☐' }}
          </span>

          <span class="doc-icon">{{ fileIcon(row.filename) }}</span>
          <div class="doc-main">
            <div class="doc-line">
              <span class="doc-name" :title="row.filename">{{ row.filename }}</span>
              <!-- R49②：被排除的那篇要在库里看得见，而且要看得见原因，
                   不许只留一个图标让人猜；也不许拿「这一步上传被跳过」冒充「这篇未索引」。 -->
              <span v-if="isExcluded(row)" class="doc-index-flag" data-testid="doc-index-status"
                    data-index-status="excluded">未索引</span>
              <!-- R288 G01：这一格只说读数说过的话。indexed 才有「已可检索」，excluded 走
                   上面那张未索引的脸（这里返回空串，一行不摆两句话），读不到就画读不到。 -->
              <span
                v-if="rowFaceText(row)"
                class="doc-retrieval"
                data-testid="doc-retrieval"
                :data-retrieval-face="rowFaceKey(row)"
              >{{ rowFaceText(row) }}</span>
              <!-- 盯过一整轮仍没结果：给一次「再读一次」的出口，不许让人只能整页刷新。
                   点它只重开同一个窗口，读的还是那一条 GET /documents/catalog。 -->
              <UiButton
                v-if="rowNeedsRecheck(row)"
                class="doc-recheck-btn"
                variant="ghost"
                size="sm"
                label="再读一次"
                data-testid="doc-retrieval-recheck"
                @click.stop="armUploadPoll([row.filename])"
              />
            </div>
            <p v-if="isExcluded(row)" class="doc-index-reason" data-testid="doc-index-reason"
               :data-index-reason="row.index_reason || ''">{{ indexReasonText(row) }}；文件与目录记录均已保留。</p>
            <!-- R313 · 格三：谁传的 / 多大 / 这一版到哪一步 —— 三句全读这一行已有的字段
                 （public_document_row 的 owner_id、size_bytes、parse_status），不为这一格多发一次请求，
                 也不要求后端加字段。裸值走 data-* 通道给测试与诊断，给人看的那一行只有中文。 -->
            <p class="doc-truth" data-testid="doc-row-truth"
               :data-owner-id="row.owner_id || ''"
               :data-size-bytes="sizeAttr(row)"
               :data-parse-status="row.parse_status || ''">
              {{ ownerTruth(row) }} · {{ sizeTruth(row) }} · {{ stageTruth(row) }}
            </p>
          </div>
          <div class="doc-actions">
            <UiButton
              class="doc-open-btn"
              variant="secondary"
              size="sm"
              label="打开"
              data-testid="document-open"
              @click.stop="openDocument(row.filename)"
            />
            <UiButton
              class="doc-open-btn"
              variant="secondary"
              size="sm"
              label="下载"
              data-testid="document-download"
              @click.stop="downloadDocument(row.filename)"
            />

          <!-- 删除按钮（管理员）：第一次点击只把这一行改成确认文案，第二次才发请求 -->
            <UiButton
              v-if="isAdmin"
              class="del-btn"
              variant="danger"
              size="sm"
              title="删除"
              :loading="deleting"
              :label="deleteButtonLabel({ pending: isPendingDelete(pendingDelete, rowDeleteKey(row.filename)), busy: deleting, label: '删除' })"
              data-testid="document-delete-one"
              @click.stop="requestDeleteOne(row.filename)"
            />
            <UiButton
              v-if="isAdmin && isPendingDelete(pendingDelete, rowDeleteKey(row.filename))"
              variant="ghost"
              size="sm"
              label="取消"
              data-testid="document-delete-one-cancel"
              @click.stop="cancelDelete"
            />
          </div>
        </div>
      </TransitionGroup>

      <!-- R313 · 格二：那一腿服务端已经答了「有 N 份文档存在，但不在当前账号的可见范围内」
           （restricted_summary，形状全站只此一份 —— R200），这一屏必须给它正脸。
           句子用后端那一份原话，界面只补一个「没有列在这里」的标题；不点名任何一份文件 ——
           点名一件对方无权访问的就是泄露，那两份投影里本来也没有名字。
           列表有货时同样要说，所以它站在那条空态链之外单独一枚（同 DataPanel 的 data-files-restricted）。 -->
      <UiErrorState
        v-if="restrictedNotice"
        :title="restrictedNotice.title"
        :description="restrictedNotice.description"
        :retryable="false"
        :data-restricted-count="restrictedNotice.count"
        data-testid="documents-restricted"
        dense
      />
    </div>

    <!-- 底栏统计 -->
    <div v-if="docs.length > 0" class="panel-footer">
      <span>共 {{ docs.length }} 个文档</span>
      <span v-if="excludedDocs.length" class="footer-excluded" data-testid="document-excluded-count">{{ excludedDocs.length }} 个未入索引</span>
      <span v-if="isAdmin" class="footer-hint">点击选择 · 批量删除</span>
    </div>

    <DocumentPreviewModal
      :open="preview.open"
      :filename="preview.filename"
      :kind="preview.kind"
      :text="preview.text"
      :blob-url="preview.blobUrl"
      :loading="preview.loading"
      :error="preview.error"
      :truncated="preview.truncated"
      @close="closeDocumentPreview"
      @download="downloadDocument(preview.filename)"
    />
  </div>
</template>

<style scoped>
.doc-panel {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  padding: 0 14px 10px; user-select: none;
}

/* ===== 面板标题 ===== */
.panel-hd {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 0 10px; border-bottom: 1px solid color-mix(in srgb, var(--legacy-void) 5%, transparent);
  font-size: 14px; gap: 8px;
}
.panel-hd-left { display: flex; align-items: center; gap: 6px; }
.badge { color: var(--legacy-ink-mid); font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 10px; }

/* 管理员开关 */
.admin-toggle { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 11px; }
.admin-label { font-size: 13px; }
.admin-toggle input { display: none; }
.toggle-slider { width: 32px; height: 18px; border-radius: 10px; background: var(--legacy-line); position: relative; transition: all 0.2s; }
.toggle-slider::after { content: ''; position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%; background: var(--legacy-paper); transition: all 0.2s; box-shadow: 0 1px 3px color-mix(in srgb, var(--legacy-void) 15%, transparent); }
.admin-toggle input:checked + .toggle-slider { background: var(--legacy-ep-danger); }
.admin-toggle input:checked + .toggle-slider::after { left: 16px; }

/* ===== 搜索栏 ===== */
.search-bar {
  display: flex; align-items: center; gap: 6px;
  margin: 10px 0; padding: 7px 10px;
  background: color-mix(in srgb, var(--legacy-void) 3%, transparent); border-radius: 8px;
}
.search-icon { font-size: 13px; opacity: 0.5; }
.search-input {
  flex: 1; border: none; background: none; outline: none;
  font-size: 12px; font-family: inherit; color: var(--legacy-ink-strong);
}
.search-input::placeholder { color: var(--legacy-ink-faint); }
.search-result { font-size: 11px; color: var(--legacy-ink-soft); flex-shrink: 0; }

/* ===== 上传区 ===== */
.drop-zone {
  border: 1.5px dashed var(--legacy-line); border-radius: 8px;
 transition: all 0.2s; margin-bottom: 8px;
}
.drop-zone.drag { border-color: var(--legacy-ep-primary); }
.upload-label {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 10px; cursor: pointer; font-size: 12px; color: var(--legacy-ink-mid);
}
.upload-icon { font-size: 16px; }

/* ===== 上传队列 ===== */
.upload-item {
  display: flex; align-items: center; gap: 6px; padding: 6px 10px; margin-bottom: 4px;
  border-radius: 6px; font-size: 11px; background: var(--legacy-paper); border: 1px solid var(--legacy-line-pale);
}
.upload-item.done { background: color-mix(in srgb, var(--legacy-ep-success) 4%, transparent); border-color: var(--legacy-ep-success-line); }
.upload-item.error { background: color-mix(in srgb, var(--legacy-ep-danger) 4%, transparent); border-color: var(--legacy-ep-danger-line); }
.up-body { flex: 1; min-width: 0; }
.up-line { display: flex; align-items: center; gap: 8px; min-width: 0; }
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.upload-progress-ring {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: var(--legacy-ep-primary);
  animation: upload-progress-spin 0.85s linear infinite;
  transform-origin: 50% 50%;
}
.upload-progress-track {
  height: 4px;
  margin-top: 5px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--legacy-fill-mist);
}
.upload-progress-bar {
  height: 100%;
  min-width: 2px;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--legacy-ep-primary), var(--legacy-ep-success));
  transition: width 0.2s ease;
}
.upload-progress-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 3px;
  color: var(--legacy-ink-soft);
  font-size: 10px;
}
.up-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.up-msg { color: var(--legacy-ep-success); flex-shrink: 0; }
.upload-item.error .up-msg { color: var(--legacy-ep-danger); }
.clear-btn {
  display: block; width: 100%; padding: 4px; border: none; background: none;
  color: var(--legacy-ink-soft); cursor: pointer; font-size: 11px; font-family: inherit;
  border-radius: 4px; margin-bottom: 4px;
}
.clear-btn:hover { color: var(--legacy-ink-mid); background: var(--legacy-fill); }

/* ===== 批量操作栏 ===== */
.batch-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 8px; margin-bottom: 4px;
  background: color-mix(in srgb, var(--legacy-ep-danger) 4%, transparent); border-radius: 6px;
}
.batch-toggle { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; color: var(--legacy-ink-mid); }
.batch-toggle input { cursor: pointer; }
.batch-text { user-select: none; }
.batch-del {
  padding: 4px 12px; border: 1px solid var(--legacy-ep-danger-line); border-radius: 4px;
  background: var(--legacy-paper); color: var(--legacy-ep-danger); cursor: pointer; font-size: 12px;
  font-family: inherit; transition: all 0.15s;
}
.batch-del:hover { background: var(--legacy-ep-danger); color: var(--legacy-paper); }

/* ===== 文档列表 ===== */
.doc-list { flex: 1; overflow-y: auto; }
.doc-list::-webkit-scrollbar { width: 3px; }
.doc-list::-webkit-scrollbar-thumb { background: var(--legacy-line); border-radius: 3px; }

/* ===== 文档行 ===== */
.doc-row {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 8px; margin-bottom: 2px;
  border-radius: 6px; font-size: 12px;
  transition: all 0.15s; cursor: pointer;
  border: 1px solid transparent;
}
.doc-row:hover { background: color-mix(in srgb, var(--legacy-ep-primary) 3%, transparent); }
.doc-row.selected { background: color-mix(in srgb, var(--legacy-ep-primary) 6%, transparent); border-color: color-mix(in srgb, var(--legacy-ep-primary) 15%, transparent); }

.check-box { font-size: 14px; flex-shrink: 0; color: var(--legacy-ink-soft); }
.doc-row.selected .check-box { color: var(--legacy-ep-primary); }

.doc-icon { font-size: 13px; flex-shrink: 0; }
.doc-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--legacy-ink-strong); }
.doc-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.doc-open-btn {
  border: 1px solid var(--legacy-line);
  background: var(--legacy-paper);
  color: var(--legacy-ink-mid);
  border-radius: 6px;
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
}

.del-btn {
  background: none; border: none; color: var(--legacy-ink-faint); cursor: pointer;
  padding: 3px 6px; border-radius: 4px; font-size: 12px; flex-shrink: 0;
  opacity: 0; transition: all 0.15s;
}
.doc-row:hover .del-btn { opacity: 1; }
.del-btn:hover { color: var(--legacy-ep-danger); background: color-mix(in srgb, var(--legacy-ep-danger) 8%, transparent); }

/* ===== 底栏 ===== */
.panel-footer {
  display: flex; justify-content: space-between; padding: 8px 0 0;
  border-top: 1px solid color-mix(in srgb, var(--legacy-void) 4%, transparent); font-size: 11px; color: var(--legacy-ink-faint); flex-shrink: 0;
}
.footer-hint { color: var(--legacy-ep-danger); }

/* ===== 动画 ===== */
.list-enter-active { transition: all 0.2s ease; }
.list-leave-active { transition: all 0.15s ease; }
.list-enter-from { opacity: 0; transform: translateX(-8px); }
.list-leave-to { opacity: 0; transform: translateX(8px); }
.list-move { transition: transform 0.2s ease; }
.queue-enter-active { transition: all 0.2s ease; }
.queue-leave-active { transition: all 0.15s ease; }
.queue-enter-from { opacity: 0; transform: translateY(-6px); }
.queue-leave-to { opacity: 0; }

@keyframes upload-progress-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.doc-panel {
  color: var(--text);
  padding: 0 18px 18px;
}

.panel-hd {
  border-bottom-color: var(--line);
  color: var(--text);
}

.badge,
.search-bar,
.upload-item,
.doc-row,
.batch-bar {
  background: color-mix(in srgb, var(--legacy-paper) 3.5%, transparent);
  border-color: var(--line);
}

.badge {
  color: var(--cyan);
  background: color-mix(in srgb, var(--legacy-aqua-bright) 10%, transparent);
}

.search-bar {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--legacy-paper) 2%, transparent);
}

.search-input,
.doc-name,
.up-name,
.panel-hd strong {
  color: var(--text);
}

.search-input::placeholder,
.search-result,
.upload-hint,
.footer-hint,
.up-msg,
.panel-footer {
  color: var(--muted);
}

.drop-zone {
  border-color: color-mix(in srgb, var(--legacy-aqua-bright) 28%, transparent);
  background: color-mix(in srgb, var(--legacy-aqua-bright) 3.5%, transparent);
}

.drop-zone.drag {
  border-color: var(--cyan);
  background: color-mix(in srgb, var(--legacy-aqua-bright) 10%, transparent);
}

.upload-label {
  color: var(--ink-soft);
}

.doc-row:hover,
.doc-row.selected {
  background: color-mix(in srgb, var(--legacy-periwinkle-strong) 10%, transparent);
  border-color: color-mix(in srgb, var(--legacy-periwinkle-strong) 28%, transparent);
}

.doc-open-btn,
.del-btn,
.batch-del,
.clear-btn {
  border-color: var(--line-strong);
  background: color-mix(in srgb, var(--legacy-paper) 4%, transparent);
  color: var(--ink-soft);
}

.doc-open-btn:hover {
  border-color: var(--blue);
  color: var(--legacy-periwinkle-pale);
  background: color-mix(in srgb, var(--legacy-periwinkle-strong) 12%, transparent);
}

.del-btn:hover,
.batch-del:hover {
  border-color: var(--red);
  color: var(--legacy-coral-soft);
  background: color-mix(in srgb, var(--red) 12%, transparent);
}

.panel-footer {
  border-top-color: var(--line);
}

/* ===== 未索引这张脸（R49②） =====
   色值只引 theme.css 里已有的 token，本单不新增、不改值（预算 148 枚告警已顶满）。 */
.doc-main {
  flex: 1; min-width: 0;
}
.doc-line {
  display: flex; align-items: center; gap: 6px; min-width: 0;
}
.doc-index-flag {
  flex-shrink: 0;
  padding: 1px 6px;
  border: 1px solid color-mix(in srgb, var(--amber) 34%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--amber) 12%, transparent);
  color: var(--amber);
  font-size: 11px;
}
.doc-index-reason {
  margin: 2px 0 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.5;
}
.footer-excluded {
  color: var(--amber);
}

/* ===== 检索状态那一格（R288 G01） =====
   色值只借 theme.css 已有的 token，并且刻意绕开 --red / --blue 那两枚名字会撞 stylelint
   关键字正则的：本仓 lint:colors 预算钉死在 148 枚告警，多一枚就是违约（判据①）。
   也不写 background：r151 那条浅色板棘轮只准降，这一格不该给它添数。 */
.doc-retrieval {
  flex-shrink: 0;
  padding: 1px 6px;
  border: 1px solid color-mix(in srgb, var(--muted) 34%, transparent);
  border-radius: 999px;
  color: var(--muted);
  font-size: 11px;
}

.doc-retrieval[data-retrieval-face="retrievable"] {
  border-color: color-mix(in srgb, var(--cyan) 34%, transparent);
  color: var(--cyan);
}

.doc-retrieval[data-retrieval-face="parsing"] {
  border-color: color-mix(in srgb, var(--amber) 34%, transparent);
  color: var(--amber);
}

.doc-retrieval[data-retrieval-face="failed"] {
  border-color: color-mix(in srgb, var(--legacy-ep-danger) 34%, transparent);
  color: var(--legacy-ep-danger);
}

/* 数满窗口仍没落定：还是琥珀色（还没好），但换成虚线边，和「解析中」不是一张脸。 */
.doc-retrieval[data-retrieval-face="stalled"] {
  border-style: dashed;
  border-color: color-mix(in srgb, var(--amber) 34%, transparent);
  color: var(--amber);
}

/* 「再读一次」贴着那一格，尺寸收进行内，不新造控件高度档，也不引新色值。 */
.doc-recheck-btn {
  min-height: 20px;
  padding: 0 6px;
  font-size: 11px;
}

/* 待确认那一档：取消与「无法恢复」并排，句子不给按钮文案让位。 */
.batch-actions { display: flex; align-items: center; gap: 6px; }
.batch-note { color: var(--legacy-ep-danger); font-size: 11px; }

/* ===== 上传密级这一格（R313 格一） =====
   色值只引 theme.css 里已有的 token（--muted / --surface-2 / --line-strong），本单不新增、
   不改值：lint:colors 的 148 枚告警已顶满，多一枚就是违约（判据①）。
   控件形状照 ChatPanel 的 .lane-picker（原生 select 已有先例，不新造一档控件高度）。 */
.classification-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin: 0 0 8px; font-size: 11px;
}
.classification-label { color: var(--muted); }
.classification-picker {
  font-family: inherit;
  font-size: var(--t-xs);
  color: var(--muted);
  background: var(--surface-2);
  border: 1px solid var(--line-strong);
  border-radius: var(--r-sm);
  padding: var(--s-1) 6px;
}
.classification-note { color: var(--muted); }

/* ===== 行内真值那一行（R313 格三） =====
   与 .doc-index-reason 同档（同色同字号），这一格是补白不是主角，不写 background：
   浅色卡片棘轮（r151 的 LIGHT_BG_SITES=18）只准降，本单一枚都不给它添数。 */
.doc-truth {
  margin: 2px 0 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.5;
}
.up-class { flex-shrink: 0; font-size: 11px; }
</style>
