/**
 * R494 · 「我的账号」这一屏唯一的取数点与判脸点
 *
 * 病（改前现场，取证 = 主树 HEAD 5b8d767）：员工在界面上答不出三句最基本的话——我是谁（角色）、
 * 我在哪个部门（而且为什么我自己改不了）、我能读到哪几级文档。路由表里 `/profile` 一屏都没有
 * （缺口清单 docs/handoff/2026-09-26-v1-frontend-gap-list.md 的 G10 记「半」，点名的没脸清单里就有它），
 * 而 `rg -n "profile" frontend/src` 的命中全在 DataPanel 的「数据画像」，与 GET /api/v1/profile 无关。
 *
 * 本层只把后端已经答得出来的两件事交给界面（逐格现读，出处 = 同树的 app/**）：
 *   读  GET /profile 回 {"profile": {...}}：``users`` 现取的 username / role / department，
 *       画像存储真读到的 position / preferences / updated_at，加上 R494 补的那枚只读派生的
 *       clearance（档位真源是 app/common/rbac.py 的 clearance_for；读不到 role 时后端整格不给）。
 *   写  PUT /profile 只交 position 与 preferences。department 这一格员工自助写不了：后端的判据是
 *       「请求里出现这枚键就整发拒」（它看的是 data.model_fields_set，空串也算出现），不是「收下降不写」。
 *
 * 三条纪律，逐条有钉（src/lib/__tests__/r494-profile-contract.test.js）：
 *  ① 🔴 这一发请求体里永远不许出现 department 那枚键：多传一个空串就换来一发 403。所以
 *     profileWriteBody 只从表单里取那两枚键，屏上也不给部门画任何输入框——它是只读的一格。
 *     这一条不靠「我们不会传」的自觉：夹具把 department 塞进表单，构造器也绝不带它出门。
 *  ② 三张失败脸分开留名（后端 R383 起前两张已经与「存储自报就绪却没写成」分开）：403 部门那一格
 *     不归你写 / 503 画像存储还没就绪 / 500 这一发没写成。各一张脸、各一句出处，不许塌成一句「保存失败」。
 *  ③ 档位拿不到就说拿不到：clearance 缺席时屏上明写「这台服务器没把档位告诉我」。不许用文案糊一枚 1
 *     上去——那枚 1 是 clearance_for 给「已知这人是 staff」准备的缺省，不是给「根本没读到」准备的答案。
 *  ④ 不乐观（与 lib/users.js 同一条）：写完由面板重新读一次画像，本层不把表单里的值当已生效的值。
 */
import { errorCodeLabel, errorCodeOf, normalizeError } from './errcodes'
import { API_BASE, errorDetail, http } from './http'
import { USER_DEPARTMENT_PATH, departmentText, userRoleLabel } from './users'

/** 这一屏唯一的一条读写路径（同一枚出口，GET 与 PUT 各一发，没有第二条）。 */
export const PROFILE_PATH = '/profile'
/** 后端 GET 那一发的回执外层键名：{"profile": {...}}。 */
export const PROFILE_ROWS_KEY = 'profile'
/**
 * 屏上那句人话要点名的管理员出口。路径不自己写第二份：API_BASE（lib/http.js）与
 * USER_DEPARTMENT_PATH（lib/users.js）拼出来就是它，与 lib/users.js 那本账同源。
 * 🔴 这一屏对它一发请求都不发：部门归属只能由持 users:manage 的管理员在那一头改。
 */
export const DEPARTMENT_WRITE_EXIT = `${API_BASE}${USER_DEPARTMENT_PATH}`

/**
 * 后端 GET /profile 真发的那几列，分三段记，一段对一枚源码：
 *   名册段 = app/common/auth.py::get_user 那一串 SELECT 的三列；
 *   画像段 = app/memory/profile.py::get_profile 那一串 SELECT 的三列；
 *   派生段 = R494 由出口现算的那一枚，只读，写不进去。
 * 契约钉拿源码逐段对：后端多一列而这里没跟上、或这里多一列而后端没有，都当场红。
 */
export const PROFILE_ROSTER_COLUMNS = ['username', 'role', 'department']
export const PROFILE_STORE_COLUMNS = ['position', 'preferences', 'updated_at']
export const PROFILE_DERIVED_FIELD = 'clearance'
export const PROFILE_READABLE_FIELDS = [...PROFILE_ROSTER_COLUMNS, ...PROFILE_STORE_COLUMNS, PROFILE_DERIVED_FIELD]

/** 请求体只可能有的两枚键：键名逐字等于后端 UpdateProfileRequest 的字段名。 */
export const PROFILE_BODY_KEYS = { position: 'position', preferences: 'preferences' }
/** 这一枚键出现在请求体里就是一发 403，所以它永远不许出现在请求体里。 */
export const PROFILE_BODY_FORBIDDEN_KEY = 'department'
/** 后端那两枚在册码：写腿按它们分脸，句子仍归 lib/errcodes.js 那本字典。 */
export const PROFILE_DEPARTMENT_REFUSED_CODE = 'department_override_denied'
export const PROFILE_STORAGE_CODE = 'storage_unavailable'

/** 读路径的七张脸：401 / 403 / 503 / 回包读不出对象 / 其它，各自一张，不塌成空态。 */
export const PROFILE_FACE_LOADING = 'loading'
export const PROFILE_FACE_READY = 'ready'
export const PROFILE_FACE_UNAUTHORIZED = 'unauthorized'
export const PROFILE_FACE_DENIED = 'denied'
export const PROFILE_FACE_STORAGE = 'storage'
export const PROFILE_FACE_MALFORMED = 'malformed'
export const PROFILE_FACE_FAILED = 'failed'
/** 写路径自己的四张脸：保存成功 / 部门那一格被拒 / 这一发没写成 / 后端按规则拒了这发。 */
export const PROFILE_FACE_SAVED = 'saved'
export const PROFILE_FACE_DEPARTMENT_REFUSED = 'department_refused'
export const PROFILE_FACE_SAVE_FAILED = 'save_failed'
export const PROFILE_FACE_INVALID = 'invalid'

export const PROFILE_READ_FACES = [
  PROFILE_FACE_LOADING, PROFILE_FACE_READY, PROFILE_FACE_UNAUTHORIZED, PROFILE_FACE_DENIED,
  PROFILE_FACE_STORAGE, PROFILE_FACE_MALFORMED, PROFILE_FACE_FAILED,
]
export const PROFILE_WRITE_FACES = [
  PROFILE_FACE_SAVED, PROFILE_FACE_DEPARTMENT_REFUSED, PROFILE_FACE_STORAGE,
  PROFILE_FACE_SAVE_FAILED, PROFILE_FACE_INVALID, PROFILE_FACE_UNAUTHORIZED,
  PROFILE_FACE_DENIED, PROFILE_FACE_FAILED,
]

/** 每张脸的标题：两两不等是判据②，看标题就知道该重新登录、该找管理员、还是该修存储。 */
export const PROFILE_TITLES = {
  [PROFILE_FACE_LOADING]: '正在读取这个账号',
  [PROFILE_FACE_READY]: '',
  [PROFILE_FACE_UNAUTHORIZED]: '登录状态已失效',
  [PROFILE_FACE_DENIED]: '这一格不向你开放',
  [PROFILE_FACE_STORAGE]: '画像存储还没就绪',
  [PROFILE_FACE_MALFORMED]: '这一发回执读不出账号信息',
  [PROFILE_FACE_FAILED]: '账号信息没加载出来',
  [PROFILE_FACE_SAVED]: '已经存好了',
  [PROFILE_FACE_DEPARTMENT_REFUSED]: '部门那一格不归你写',
  [PROFILE_FACE_SAVE_FAILED]: '这一发后端没写成',
  [PROFILE_FACE_INVALID]: '后端没有收下这一发',
}

export const PROFILE_LOADING_TEXT = '正在读取这个账号在这台服务器上的样子'
/** 写成一发之后的回执句：它只说「后端收下了」，不说「值已经是你要的了」——那一句由重读之后的四格来说。 */
export const PROFILE_SAVED_NOTE = '后端已经收下这一发，上面四格是重新读回来的样子。'
/** 部门只读那一句人话：权威出处是后端 PUT /profile 的 R296 注释与 department 自助被拒那一枚码。 */
export const DEPARTMENT_READ_ONLY_NOTE = '部门这一格是只读的：要挪部门请找管理员，走 PUT '
  + `${DEPARTMENT_WRITE_EXIT}，需要 users:manage 这一项权限。`
  + '你自己在这里改不动；把这一格一起发给后端，整发都会被拒。'

/** 判据③：档位拿不到时屏上就是这两句，不许出现任何数字。 */
export const CLEARANCE_UNKNOWN_TEXT = '这台服务器没把档位告诉我'
export const CLEARANCE_UNKNOWN_NOTE = '这不是「你能读到第 1 级」，也不是「你什么都读不到」：'
  + '后端这一发没把档位那一格交出来，通常是账号的角色那一列没填。这一格由管理员补，不由界面猜。'

/** 一行一条：偏好是一个字符串数组，屏上用多行文本承载，换行是唯一的分隔符。 */
export const PREFERENCE_LINE_SEPARATOR = '\n'

/** 屏上四格的读数（值一律来自后端回包，前端不补一个字的默认值）。 */
export function profileCells(row) {
  const source = row && typeof row === 'object' && !Array.isArray(row) ? row : {}
  return {
    username: String(source.username ?? ''),
    role: String(source.role ?? ''),
    roleText: userRoleLabel(source.role ?? ''),
    department: departmentText(source.department ?? ''),
    position: String(source.position ?? ''),
    preferences: preferenceLines(source.preferences).join(PREFERENCE_LINE_SEPARATOR),
    clearance: clearanceView(source),
  }
}

/** 把后端给的偏好读成字符串数组：不是数组就当没有，不替它猜一条。 */
export function preferenceLines(value) {
  return Array.isArray(value) ? value.map(line => String(line ?? '').trim()).filter(Boolean) : []
}

/** 多行文本 → 数组：只按换行切，其余字符一个都不动（动了就是替后端改规则）。 */
export function linesToPreferences(text) {
  return String(text ?? '').split(PREFERENCE_LINE_SEPARATOR).map(line => line.trim()).filter(Boolean)
}

/**
 * 档位那一格：只有后端真给了一个正整数才算「知道」，其余一律走「没告诉我」那张脸。
 *
 * 为什么宁缺毋滥：后端在读不到角色时整格不给（这单的另一半），而 clearance_for 的兜底会替空角色
 * 回 1。界面若在这里写「拿不到就按 1 画」，就是把「不知道」画成「你能读到第 1 级」——假话。
 */
export function clearanceLevel(row) {
  const source = row && typeof row === 'object' && !Array.isArray(row) ? row : null
  const raw = source ? source[PROFILE_DERIVED_FIELD] : null
  // 只认后端真发的那个整数：字符串「2」不是档位，是形状不对，宁缺不猜。
  return typeof raw === 'number' && Number.isInteger(raw) && raw > 0 ? raw : 0
}

export function clearanceText(level) {
  return `你能读到第 1–${level} 级`
}

export function clearanceView(row) {
  const level = clearanceLevel(row)
  if (!level) return { known: false, level: 0, text: CLEARANCE_UNKNOWN_TEXT, note: CLEARANCE_UNKNOWN_NOTE }
  return { known: true, level, text: clearanceText(level), note: '' }
}

/** 空白视图：面板起手与切屏作废都用它，face 是唯一分派位。 */
export function profileBlankView(face = PROFILE_FACE_LOADING) {
  return { face, row: null, message: '', code: '', codeLabel: '' }
}

/** 从 {"profile": {...}} 里取那一枚对象；读不出对象就是 malformed，不当成「没有画像」。 */
export function readProfileRow(payload) {
  const row = (payload && typeof payload === 'object' ? payload : {})[PROFILE_ROWS_KEY]
  return row && typeof row === 'object' && !Array.isArray(row) ? row : null
}

/** 200 那一发：读得出对象才算 ready。 */
export function profileViewFromResponse(response) {
  const row = readProfileRow(response && response.data)
  if (!row) return profileBlankView(PROFILE_FACE_MALFORMED)
  return { face: PROFILE_FACE_READY, row, message: '', code: '', codeLabel: '' }
}

/**
 * 失败腿：判据只走 errorCodeOf 与 HTTP status 两枚通道（与 lib/users.js 同一手法），
 * 本模块一枚码都不新增，句子仍归 lib/errcodes.js 那本字典。
 *
 * @param {unknown} err axios 错误形状（也接受 { response: { status, data } } 夹具）
 * @param {'read' | 'write'} [leg] 读写两腿对同一状态码要说的话不同：500 在写腿才是「没写成」
 */
export function profileViewFromError(err, leg = 'read') {
  const status = Number(err && err.response ? err.response.status : err && err.status) || 0
  const code = errorCodeOf(err)
  // 后端自己那枚码走 rawCode 这一道在册通道（与 ApprovalPanel 认 department_override_denied 同一手法）：
  // errorCodeOf 已经把它折进 validation_error，那本字典管句子，本层拿它判脸就会认错人。
  const rawCode = normalizeError(err).rawCode
  const message = errorDetail(err, '')
  // 码名只走 errcodes 那一枚诊断小字的通道（errorCodeLabel 自己判这枚码登记没登记过），本层不拼第二份
  const base = { face: PROFILE_FACE_FAILED, row: null, message, code, codeLabel: errorCodeLabel(err) }

  if (status === 401) return { ...base, face: PROFILE_FACE_UNAUTHORIZED }
  if (status === 403) {
    // 部门那一格被自助写拒，与「这一格不向你开放」是两件事：前者要改请求，后者要改权限。
    const isDepartmentClaim = rawCode === PROFILE_DEPARTMENT_REFUSED_CODE
    return { ...base, face: isDepartmentClaim ? PROFILE_FACE_DEPARTMENT_REFUSED : PROFILE_FACE_DENIED }
  }
  if (status === 422) return { ...base, face: PROFILE_FACE_INVALID }
  if (status === 503 || code === PROFILE_STORAGE_CODE) return { ...base, face: PROFILE_FACE_STORAGE }
  if (leg === 'write' && status === 500) {
    // R383 之后只剩这一种可能：存储自报就绪，这一发却真没写成。只有它配得上「没写成」这句话。
    return { ...base, face: PROFILE_FACE_SAVE_FAILED }
  }
  return base
}

/**
 * 请求体构造器：只出 position 与 preferences 两枚键。
 *
 * 🔴 表单里就算躺着 department（比如面板以后复用同一份 reactive），它也绝不会出门：这一格不是
 * 「传了也白传」，传了整发就 403。判据由 r494 的夹具盯着，不靠自觉。
 */
export function profileWriteBody(form = {}) {
  return {
    [PROFILE_BODY_KEYS.position]: String(form[PROFILE_BODY_KEYS.position] ?? ''),
    [PROFILE_BODY_KEYS.preferences]: linesToPreferences(form[PROFILE_BODY_KEYS.preferences]),
  }
}

/** 读那一发 GET。失败不抛：面板只认 face。 */
export async function loadProfile() {
  try {
    return profileViewFromResponse(await http.get(PROFILE_PATH))
  } catch (err) {
    return profileViewFromError(err, 'read')
  }
}

/** 写那一发 PUT：请求体由调用方给（一律出自 profileWriteBody），本层不碰表单。 */
export async function submitProfile(body) {
  try {
    await http.put(PROFILE_PATH, body)
    return { face: PROFILE_FACE_SAVED, row: null, message: '', code: '', codeLabel: '' }
  } catch (err) {
    return profileViewFromError(err, 'write')
  }
}
/** 读腿里只有这两张脸值得再来一次：其余失败脸要么改请求、要么改权限、要么修存储。 */
export const PROFILE_RETRYABLE_READ_FACES = [PROFILE_FACE_FAILED, PROFILE_FACE_MALFORMED]

/**
 * 失败脸的屏上读数：标题出自 PROFILE_TITLES，句子出自字典（view.message），
 * 码名只走 codeLabel 那一枚诊断小字。面板拿到什么就画什么，不再自己判脸。
 */
export function profileFaceView(view) {
  const face = view && view.face
  return {
    face,
    title: PROFILE_TITLES[face] || PROFILE_TITLES[PROFILE_FACE_FAILED],
    description: (view && view.message) || '',
    codeLabel: (view && view.codeLabel) || '',
    retryable: PROFILE_RETRYABLE_READ_FACES.includes(face),
  }
}
