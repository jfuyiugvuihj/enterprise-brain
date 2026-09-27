/**
 * R316 · 「账号与角色」这一屏的唯一取数点与判脸点；R360 起它也是四枚写出口的唯一接线点
 *
 * 读只做一件事：把服务端名册里真有的人列出来。写只做后端已有的那四枚（开通 / 删除 / 改密码 /
 * 改部门），后端没给的能力这里不造 —— 它只有「删除」没有「停用」，屏上就只说删除。
 *
 * 后端零改动，口径逐字跟着源码走（读路径取证 = 主树 4382443）：
 *   出口  app/api/v1/auth.py:90  GET /users，:106 回 {"users": users}（R356 起名册取不到
 *         时答 503 storage_unavailable，不答 {"users": []}）；authorize_request(request,
 *         ACTION_MANAGE_USERS, resource_name="users") 与 :98 POST / :113 DELETE / :123 PUT
 *         password / :139 PUT department 四枚写出口过的是同一道闸 —— 读写五腿共用一枚判定。
 *   列名  app/common/auth.py:543  SELECT id, username, role, department, created_at；
 *         内存表那一腿（:538-541）回同一组键，created_at 给空串。
 *   闸口  app/common/authorization.py:50-57  无 Principal → 401 authentication_required，
 *         PermissionError → 403，detail 里带 reason code（app/common/policy.py 的
 *         authorization_decision）；staff / manager / auditor 的角色集里没有 users:manage
 *         （app/common/permissions.py:12-17）⇒ 员工在这一屏拿到的是 403，不是空数组。
 *   角色  docs/superpowers/specs/2026-09-08-complete-rbac-abac-design.md §5.1 的定名。
 *
 * 三条不变量，逐条有钉（src/lib/__tests__/r316-users-contract.test.js）：
 *  ① 列只认后端真发的那五枚键。USER_BACKEND_COLUMNS 是与源码对账的账本而不是文档：
 *     「最近登录」「状态」「活跃度」这类后端从没给过的词在这里没有容身之处，多一列当场红。
 *  ② 「不向你开放」是一张脸，不是空列表。403 / 401 / 503 / 回包读不出行 / 真零行，
 *     五张两两不等，任何一张都不许塌成空态那一句（同 lib/alerts.js 的 R1(c) 裁定）。
 *     这里不重做 faceOf 那六张脸：这一屏要分辨的「存储没就绪」与「读不出行」在那六张里
 *     全是同一张 error，所以沿用 lib/dashboard.js::TREND_FACE_* 那一族的写法 ——
 *     同一手法（判定只认 errorCodeOf 与 HTTP status 两枚出处），不是第二套权限判定。
 *  ③ 零统计量：这里不产出任何前端算出来的数。rows 的长度只回答「这一发读回来几行」，
 *     不参与结论，也不冒充全集（R314 / R341 同一条规矩）。
 */
import { errorCodeLabel, errorCodeOf, errorText } from './errcodes'
import { formatStamp, listRows, UNATTRIBUTED_DEPARTMENT, UNRECORDED } from './alerts'
import { errorDetail, http, PERMISSION_DENIED } from './http'

/** 这一屏唯一的一条请求路径。列表只此一条，写路径一枚都不接。 */
export const USERS_PATH = '/users'
/** 后端 auth.py:95 那一格回包里的数组键名。 */
export const USERS_ROWS_KEY = 'users'

/**
 * 后端 list_users() 真发的列名，顺序取 app/common/auth.py:543 那串 SELECT。
 * 这一枚数组不是注释，是账本：契约钉拿 `git show` 读源码里的 SELECT 逐列对，
 * 后端加一列而这里没跟上、或这里多一列而后端没有，都当场红。
 */
export const USER_BACKEND_COLUMNS = ['id', 'username', 'role', 'department', 'created_at']

/** 角色词表：封闭集合，与 app/common/permissions.py:12-17 的 ROLE_PERMISSIONS 键同集。 */
export const USER_ROLES = ['staff', 'manager', 'admin', 'auditor']
/** 定名取 RBAC 设计文档 §5.1 那张表，不在这里重新发明角色名。 */
export const USER_ROLE_LABELS = {
  staff: '普通员工',
  manager: '部门负责人',
  admin: '系统管理员',
  auditor: '审计人员',
}
/** 后端给了词表外的角色：说认不下，绝不照着猜一个（与 alerts::operatorLabel 同一口径）。 */
export const USER_ROLE_UNKNOWN = '无法识别的角色'
/** 五张脸各自的 face 值：面板按它分派，测试按它两两比对。 */
export const USERS_FACE_LOADING = 'loading'
export const USERS_FACE_READY = 'ready'
export const USERS_FACE_EMPTY = 'empty'
export const USERS_FACE_DENIED = 'denied'
export const USERS_FACE_UNAUTHORIZED = 'unauthorized'
export const USERS_FACE_STORAGE = 'storage'
export const USERS_FACE_MALFORMED = 'malformed'
export const USERS_FACE_FAILED = 'failed'

/** 标题逐枚不同：看标题就知道该开权限、该重新登录、该修存储，还是该重发一次。 */
export const USERS_DENIED_TITLE = '这一屏不向你开放'
export const USERS_UNAUTHORIZED_TITLE = '登录状态已失效'
export const USERS_STORAGE_TITLE = '账号存储还没就绪，名册取不到'
export const USERS_MALFORMED_TITLE = '账号名册的回包读不出行'
export const USERS_FAILED_TITLE = '账号名册没加载出来'
export const USERS_EMPTY_TITLE = '这一发回包里没有行'

export const USERS_LOADING_TEXT = '正在读取账号名册'

/** 403 之后必须指出下一步去哪：少了这一句，无权限卡就是一句死路（同 alerts 的 PERMISSION_WHERE）。 */
export const USERS_DENIED_WHERE = '看名册、开账号、停账号走的是同一项权限，普通员工、部门负责人与审计人员的角色集里都没有这一项。'
  + '请让系统管理员把这一项权限放到你的账号上，再回到这一屏重新加载；重新登录本身不会让这项权限出现。'

const USERS_UNAUTHORIZED_MESSAGE = errorText('authentication_required')
const USERS_STORAGE_MESSAGE = '服务端还没能读出账号表，所以这一屏一行都不画；这里也不拿上一份名册装作读到了。'
const USERS_MALFORMED_MESSAGE = '这一发回来的是 200，但账号列表不是可读的行，已按失败处理 —— 不会把它降成「名册里没有行」。'
const USERS_FAILED_MESSAGE = '账号名册暂时读不到，请重新加载；一直读不到的话请联系系统管理员。'
export const USERS_EMPTY_DESCRIPTION = '这一屏只按服务端这一发的回包说话：它回的是 200，账号列表里一行都没有。'
  + '零行是后端说的一句话，不等于这一屏对你没有开放（那会是另一张脸），也不由前端替它补解释。'

/** 列定义：key 逐字取自 USER_BACKEND_COLUMNS，label 是界面词汇，formatter 只做人话化。 */
export const USER_COLUMNS = [
  { key: 'id', label: '编号', formatter: value => (value === '' ? UNRECORDED : String(value)) },
  { key: 'username', label: '账号', formatter: value => value || UNRECORDED },
  { key: 'role', label: '角色', formatter: value => userRoleLabel(value) },
  { key: 'department', label: '部门', formatter: value => departmentText(value) },
  { key: 'created_at', label: '创建时间', formatter: value => createdAtText(value) },
]

function textOf(value) {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

/** 角色 -> 中文。词表外一律回「无法识别的角色」，不猜、也不把后端原串画上屏。 */
export function userRoleLabel(role) {
  const key = textOf(role)
  return USER_ROLE_LABELS[key] || USER_ROLE_UNKNOWN
}

/** 后端没记部门就是空串（auth.py:565 那一格同一语义）：说「未登记」，不替它编一个部门名。 */
export function departmentText(department) {
  return textOf(department) || UNATTRIBUTED_DEPARTMENT
}

/** created_at 是文本列：内存表回空串，真库回带偏移的时间串。空串读成「没记过」，不是 0，也不是「今天」。 */
export function createdAtText(value) {
  return formatStamp(value) || UNRECORDED
}

/**
 * 服务端的一行 -> 屏上的一行：只按 USER_BACKEND_COLUMNS 造对象，多回来的键一概不带，
 * 缺的键留空串而不是补一个像真的一样的值。「这一屏知道哪些列」因此只有这一处答案。
 */
export function mapUserRow(row) {
  const source = row && typeof row === 'object' ? row : {}
  return {
    id: textOf(source.id),
    username: textOf(source.username),
    role: textOf(source.role),
    department: textOf(source.department),
    created_at: textOf(source.created_at),
  }
}
/** 还没有回包时的起点：每一次重新取数都从这里起步，上一份名册不许挂在屏上冒充这一份的结果。 */
export function usersBlankView(face = USERS_FACE_LOADING) {
  const loading = face === USERS_FACE_LOADING
  return {
    face: loading ? USERS_FACE_LOADING : USERS_FACE_FAILED,
    title: '',
    description: loading ? USERS_LOADING_TEXT : '',
    codeLabel: '',
    rows: [],
    retryable: false,
  }
}

/** 这一张脸是不是「没读到」那五张之一，是就把脸名回给面板，不是就回空串（归脸只这一处）。 */
export function usersFailureFace(view) {
  const face = view && typeof view === 'object' ? view.face : ''
  return [USERS_FACE_DENIED, USERS_FACE_UNAUTHORIZED, USERS_FACE_STORAGE, USERS_FACE_MALFORMED, USERS_FACE_FAILED]
    .includes(face) ? face : ''
}

/**
 * 失败归脸：没权限 / 登录失效 / 存储没就绪 / 就是读不到，四句话四张脸。
 * 句子仍出自 lib/errcodes.js 那本字典（这里只决定标题与「字典没话说时」的场景文案），
 * 判据走 errorCodeOf 那枚独立通道 —— 本模块一枚码都不新增。
 */
export function usersErrorView(err) {
  const code = errorCodeOf(err)
  const status = Number(err?.response?.status ?? err?.status ?? 0) || 0
  const denied = code === PERMISSION_DENIED
  const unauthorized = code === 'authentication_required'
  const storage = !denied && !unauthorized && (code === 'storage_unavailable' || status === 503)
  const face = denied ? USERS_FACE_DENIED : unauthorized ? USERS_FACE_UNAUTHORIZED : storage ? USERS_FACE_STORAGE : USERS_FACE_FAILED
  const fallback = denied
    ? errorText(PERMISSION_DENIED)
    : unauthorized
      ? USERS_UNAUTHORIZED_MESSAGE
      : storage
        ? USERS_STORAGE_MESSAGE
        : USERS_FAILED_MESSAGE
  return {
    face,
    title: denied
      ? USERS_DENIED_TITLE
      : unauthorized
        ? USERS_UNAUTHORIZED_TITLE
        : storage
          ? USERS_STORAGE_TITLE
          : USERS_FAILED_TITLE,
    // 没权限那一张把人话位留给字典那句，再补「下一步去哪」；其余三张只说自己的事。
    description: errorDetail(err, fallback) + (denied ? USERS_DENIED_WHERE : ''),
    // 字典已收编的码不追加「错误码：xxx」小字（errorCodeLabel 自己就知道这一条），
    // 未知码才把它留到小字通道，与全站同一规矩。
    codeLabel: denied || unauthorized || storage ? '' : errorCodeLabel(err),
    rows: [],
    retryable: face === USERS_FACE_FAILED,
  }
}

/** 200 但读不出行：这是一张独立的脸，绝不与「真零行」共用一句文案。 */
export function usersMalformedView() {
  return {
    face: USERS_FACE_MALFORMED,
    title: USERS_MALFORMED_TITLE,
    description: USERS_MALFORMED_MESSAGE,
    codeLabel: '',
    rows: [],
    retryable: true,
  }
}

/** 回包 -> 视图。列表键缺席或不是数组就返回 null，交给 malformed 那张脸，不降成空态。 */
export function parseUsersPayload(payload) {
  const rows = listRows(payload, USERS_ROWS_KEY)
  if (!rows) return null
  const mapped = rows.map(mapUserRow)
  return {
    face: mapped.length ? USERS_FACE_READY : USERS_FACE_EMPTY,
    title: mapped.length ? '' : USERS_EMPTY_TITLE,
    description: mapped.length ? '' : USERS_EMPTY_DESCRIPTION,
    codeLabel: '',
    rows: mapped,
    retryable: false,
  }
}

/**
 * 读一次名册。返回的永远是视图，不抛给面板 —— 这一屏没有第二块内容可以被它拖走。
 * 那一发 GET 本身就是判定的一部分：这一屏不替服务端猜「你有没有权限」，它去问，然后照回话说。
 */
export async function loadUsers(client = http) {
  let response
  try {
    response = await client.get(USERS_PATH)
  } catch (err) {
    return usersErrorView(err)
  }
  const status = Number(response?.status ?? 0) || 0
  if (status !== 200) return usersErrorView({ response, status })
  return parseUsersPayload(response.data) || usersMalformedView()
}

// ============================================================================
// R360 · 四枚写出口：本文件唯一的一次越界，越的是 R316 结案时自己登记的那笔边界
// ============================================================================
/**
 * 上面那半份文件只读（GET /users）。这一半接 app/api/v1/auth.py 里早就在树的四枚写出口，
 * 逐枚对应关系是现取的（取证行号 = 本仓 HEAD 的 app/api/v1/auth.py）：
 *   POST   /users                  :98-110   开通账号，回 {"status":"ok","message":...}
 *   DELETE /users/{user_id}        :113-120  删账号，按编号定位，回 {"status":"ok"}
 *   PUT    /users/password         :123-134  改密码，回 {"status":"ok","message":...}
 *   PUT    /users/department       :139-204  改部门归属，回 status/username/department/changed/message
 *
 * 后端零改动是本单前提：这里不新增第五枚出口、不改任何一枚的语义、状态码或请求体，
 * 后端做不到的事（「停用」这一档它没有；管理员替人重置密码它要 old_password）一律只报不造。
 * 四枚出口各自真会回哪些码，逐条写在 r360-user-writes.test.js 那张取证表里，本文件不重述一遍
 * —— 一处叙述就是两本账，那张表才是唯一说法。
 *
 * 三条纪律：
 *  ① 不乐观（判据乙）：写完一律由面板重新调 loadUsers() 读名册，本层不提供也不许任何人用
 *     「本地把那一行改掉」的第二本账（手法与 lib/notifications.js 的「全部已读」同一套：
 *     写完重读，屏上那几行永远只可能来自后端回包）。
 *  ② 失败脸逐枚分开、各有出处（判据丙）：判据只走 errorCodeOf 与 HTTP status 两枚通道，
 *     本模块一枚码都不新增、一张脸都不新造句子的人话位（句子仍归 lib/errcodes.js 那本字典）。
 *     🔴 503 那一档不挂重试按钮，三条理由逐字出自 lib/errcodes.js:99-107：
 *        ① 它是部署缺陷，前端重试同一个请求必然同样失败，直到有人把迁移跑完；
 *        ② 后端自己也没把它当可重试错 —— app/agents/evidence.py:18 的 _RETRIABLE_CODES 收了
 *           model_unavailable / retrieval_unavailable / task_timeout / rate_limited / queue_unavailable
 *           五档，刻意没有这一档；
 *        ③ isRetryable 决定界面挂不挂「重试」按钮，给一个必须运维介入的故障挂重试只会让人反复点。
 *     本层把这三条推广到全部写失败脸（retryable 恒 false）：要再来一次就走表单本身那一枚提交钮，
 *     不在失败脸上再开第二个入口 —— 写请求重放发的就是同一发写。
 *  ③ 表单侧规则只准等于后端真规则（判据丙）：那本账是 USER_FORM_RULES，四个值逐枚抄自
 *     app/common/auth.py，r360 的契约钉拿 git show 与源码逐格对。后端没有的规则这里一律记 null，
 *     不许长出一枚前端自己的密码强度、角色白名单或部门字符集。
 */

/** 四枚出口的名字：面板按它分派，回执按它说话，测试按它逐枚验。 */
export const USER_WRITE_CREATE = 'create'
export const USER_WRITE_DELETE = 'delete'
export const USER_WRITE_PASSWORD = 'password'
export const USER_WRITE_DEPARTMENT = 'department'

/** 四条路径，与上面那四枚出口一一对号。读路径仍然只有 USERS_PATH 一枚，没有第二条。 */
export const USER_CREATE_PATH = USERS_PATH
export const USER_PASSWORD_PATH = '/users/password'
export const USER_DEPARTMENT_PATH = '/users/department'
/** DELETE 的路径带编号（auth.py:113 声明的是 user_id: int），所以这里是一个构造函数而不是常量。 */
export const USER_DELETE_PATH_PREFIX = `${USERS_PATH}/`

/**
 * 请求体键名逐字取自后端那三枚模型：CreateUserRequest（:39-43）、ChangePasswordRequest（:46-49）、
 * UpdateDepartmentRequest（:52-56）。键名是契约，值不做二次加工：后端对用户名与密码都不做
 * strip（只有部门在 :182 由后端自己 strip），所以前端一个字符都不动 —— 动了就是替后端改了规则。
 */
export const USER_BODY_KEYS = {
  username: 'username',
  password: 'password',
  role: 'role',
  department: 'department',
  oldPassword: 'old_password',
  newPassword: 'new_password',
}

/** 表单里那几格的字段名（前端词汇，与请求体键名刻意不同名，防的是「屏上直出蛇形键」那一族）。 */
export const USER_FORM_FIELDS = {
  username: 'username',
  role: 'role',
  password: 'password',
  department: 'department',
  oldPassword: 'oldPassword',
  newPassword: 'newPassword',
}

/**
 * 表单侧唯一的一本规则账。四个数逐枚对源码，三个 null 逐枚对「后端确实没有这条规则」：
 *   :548-549  用户名或密码为空 -> 拒（所以 required 只有这一枚出处）
 *   :550-551  len(password) < 6 -> 拒
 *   :668-669  len(new_password) < 6 -> 拒
 *   :552-553  role 不在 ("staff", "manager", "admin") -> 拒
 * username / department 的字符集与长度：后端一个字都没写，所以这里记 null，不发明。
 * 老密码没有「不能为空」这一条规则（:666 走的是校验原密码对不对），所以这里也不设 required。
 */
export const USER_FORM_RULES = {
  usernameRequired: true,
  passwordRequired: true,
  passwordMinLength: 6,
  newPasswordMinLength: 6,
  creatableRoles: ['staff', 'manager', 'admin'],
  usernamePattern: null,
  departmentPattern: null,
}

/**
 * 能创建的角色，比能读到的角色少一枚。
 * USER_ROLES 那四枚对的是 app/common/permissions.py 的角色集，而 auth.py:552 的白名单里没有
 * auditor —— 名册里读得到审计人员，界面上却开不出这一枚账号，这一格差别只能照后端说。
 */
export const USER_CREATABLE_ROLES = USER_FORM_RULES.creatableRoles

/** 后端 CreateUserRequest 那两枚默认值（auth.py:22-23：role 默认 staff、department 默认空串）：表单起点照它抄，不自己挑一枚。 */
export const USER_CREATE_DEFAULTS = { role: 'staff', department: '' }

/** 预检没过时的那几句话：说的是本账那几个值，不是第二份判定。 */
export const USER_RULE_HINTS = {
  usernameRequired: '账号名不能是空的。',
  passwordRequired: '密码不能是空的。',
  passwordTooShort: `密码至少要 ${USER_FORM_RULES.passwordMinLength} 位。`,
  newPasswordTooShort: `新密码至少要 ${USER_FORM_RULES.newPasswordMinLength} 位。`,
  roleUnknown: '角色要在后端认得的那几枚里挑。',
}

/** 请求体三枚构造器：纯函数，不碰屏上任何东西，键名逐字等于后端模型字段名。 */
export function createBody(form = {}) {
  return {
    [USER_BODY_KEYS.username]: String(form[USER_FORM_FIELDS.username] ?? ''),
    [USER_BODY_KEYS.password]: String(form[USER_FORM_FIELDS.password] ?? ''),
    [USER_BODY_KEYS.role]: String(form[USER_FORM_FIELDS.role] ?? ''),
    [USER_BODY_KEYS.department]: String(form[USER_FORM_FIELDS.department] ?? ''),
  }
}

export function passwordBody(form = {}) {
  return {
    [USER_BODY_KEYS.username]: String(form[USER_FORM_FIELDS.username] ?? ''),
    [USER_BODY_KEYS.oldPassword]: String(form[USER_FORM_FIELDS.oldPassword] ?? ''),
    [USER_BODY_KEYS.newPassword]: String(form[USER_FORM_FIELDS.newPassword] ?? ''),
  }
}

/**
 * department 这一枚键每次都必须出现：后端把「缺席 / null」读成「这轮没说」（auth.py:171-180 那半条
 * 分支一个字都不写，回 changed: false），显式空串才读成「清空归属」。少发一枚键就是把「没改」
 * 提交成「改过了」——那一格 R290 的注释专门钉过，本层照它的口径整发都带上。
 */
export function departmentBody(form = {}) {
  return {
    [USER_BODY_KEYS.username]: String(form[USER_FORM_FIELDS.username] ?? ''),
    [USER_BODY_KEYS.department]: String(form[USER_FORM_FIELDS.department] ?? ''),
  }
}

/**
 * DELETE 按编号定位（auth.py:113 的路径参数是 user_id）。名册这一行没给编号就构造不出路径：
 * 空串是唯一允许的「不行」，前端不替后端猜一个 id，也不发一枚注定 422 的请求。
 */
export function userDeletePath(row) {
  const id = textOf(row && typeof row === 'object' ? row.id : '')
  return id ? `${USER_DELETE_PATH_PREFIX}${encodeURIComponent(id)}` : ''
}

/** 表单预检：只读 USER_FORM_RULES 那本账。本函数体内不许出现数字字面量、正则或账外的判断。 */
export function userFormRuleViolations(kind, form = {}) {
  const errors = {}
  const username = String(form[USER_FORM_FIELDS.username] ?? '')
  const password = String(form[USER_FORM_FIELDS.password] ?? '')
  const newPassword = String(form[USER_FORM_FIELDS.newPassword] ?? '')
  const role = String(form[USER_FORM_FIELDS.role] ?? '')
  if (kind === USER_WRITE_CREATE) {
    if (USER_FORM_RULES.usernameRequired && !username) errors[USER_FORM_FIELDS.username] = USER_RULE_HINTS.usernameRequired
    if (USER_FORM_RULES.passwordRequired && !password) {
      errors[USER_FORM_FIELDS.password] = USER_RULE_HINTS.passwordRequired
    } else if (password.length < USER_FORM_RULES.passwordMinLength) {
      errors[USER_FORM_FIELDS.password] = USER_RULE_HINTS.passwordTooShort
    }
    if (!USER_FORM_RULES.creatableRoles.includes(role)) {
      errors[USER_FORM_FIELDS.role] = '角色要在后端认得的那几枚里挑。'
    }
  }
  if (kind === USER_WRITE_PASSWORD && newPassword.length < USER_FORM_RULES.newPasswordMinLength) {
    errors[USER_FORM_FIELDS.newPassword] = USER_RULE_HINTS.newPasswordTooShort
  }
  return errors
}

/** 写这一族自己的三张脸（其余四张与读路径同名同句：denied / unauthorized / storage / failed）。 */
export const USERS_FACE_CONFLICT = 'conflict'
export const USERS_FACE_NOT_FOUND = 'not_found'
export const USERS_FACE_INVALID = 'invalid'
/** 后端回了 200 但这一发的结论读不出来：它不是成功，也不是「名册里没有账号」。 */
export const USERS_FACE_WRITE_OK = 'ok'

export const USERS_CONFLICT_TITLE = '这一步和名册现在的样子撞了'
export const USERS_CONFLICT_MESSAGE = '后端说这一发与名册里已有的东西冲突，所以什么都没改。'
export const USERS_NOT_FOUND_TITLE = '名册里找不到这一枚账号'
export const USERS_NOT_FOUND_MESSAGE = '后端回的是「找不到这一枚账号」：它不是说这一屏不向你开放，也不是说名册里一个账号都没有。'
export const USERS_INVALID_TITLE = '后端没有收下这一发'
export const USERS_INVALID_MESSAGE = '这一步没做成，后端按它自己的规则拒了这一次提交，原因就在下面那句里。'
export const USERS_WRITE_FAILED_TITLE = '这一步没成交'
export const USERS_WRITE_FAILED_MESSAGE = '这一发写请求没成，名册上有没有改动以重新读回来的那几行为准。'
/** 200 但没有 status: ok —— 这一张说的是「读不出结论」，绝不当成成功（判据乙的另一半）。 */
export const USERS_WRITE_MALFORMED_TITLE = '后端回了成功状态，但这一发的结论读不出来'
export const USERS_WRITE_MALFORMED_MESSAGE = '这一发的回包里认不出「成了」这句话，所以屏上不说它成功了；'
  + '名册随后重新读过一次，那几行才是此刻的事实。'
/** 这一行没有编号：DELETE /users/{user_id} 没法定位它。 */
export const USERS_UNADDRESSABLE_TITLE = '名册里这一枚账号没有编号'
export const USERS_UNADDRESSABLE_MESSAGE = '删除按编号走（后端那枚出口的路径参数就是编号），这一行没给编号，'
  + '前端不替它猜一个，所以这一枚账号今天删不了。'

/**
 * 一次写失败 -> 一张脸。分派只认 errorCodeOf 与 HTTP status 两枚出处，与 usersErrorView 同一手法；
 * 优先级也与它一致：先认「没权限 / 登录失效」，再认存储，才轮到冲突、找不到、没收下。
 */
export function userWriteFaceOf(err) {
  const code = errorCodeOf(err)
  const status = Number(err && err.response && err.response.status ? err.response.status : (err && err.status) || 0) || 0
  if (code === PERMISSION_DENIED) return USERS_FACE_DENIED
  if (code === 'authentication_required') return USERS_FACE_UNAUTHORIZED
  if (code === 'storage_unavailable' || status === 503) return USERS_FACE_STORAGE
  if (code === 'conflict') return USERS_FACE_CONFLICT
  if (code === 'resource_not_found') return USERS_FACE_NOT_FOUND
  if (code === 'validation_error') return USERS_FACE_INVALID
  return USERS_FACE_FAILED
}

/** 每张写失败脸的标题与人话兜底句：唯一一处映射，面板与测试都读它，不各自再抄一份。 */
const USER_WRITE_FACE_COPY = {
  [USERS_FACE_DENIED]: {
    title: USERS_DENIED_TITLE,
    fallback: errorText(PERMISSION_DENIED),
    where: USERS_DENIED_WHERE,
  },
  [USERS_FACE_UNAUTHORIZED]: { title: USERS_UNAUTHORIZED_TITLE, fallback: USERS_UNAUTHORIZED_MESSAGE, where: '' },
  [USERS_FACE_STORAGE]: { title: USERS_STORAGE_TITLE, fallback: USERS_STORAGE_MESSAGE, where: '' },
  [USERS_FACE_CONFLICT]: { title: USERS_CONFLICT_TITLE, fallback: USERS_CONFLICT_MESSAGE, where: '' },
  [USERS_FACE_NOT_FOUND]: { title: USERS_NOT_FOUND_TITLE, fallback: USERS_NOT_FOUND_MESSAGE, where: '' },
  [USERS_FACE_INVALID]: { title: USERS_INVALID_TITLE, fallback: USERS_INVALID_MESSAGE, where: '' },
  [USERS_FACE_FAILED]: { title: USERS_WRITE_FAILED_TITLE, fallback: USERS_WRITE_FAILED_MESSAGE, where: '' },
}

/**
 * 后端那四枚出口的成功回包共有形状：{"status": "ok"}（auth.py:120），三枚还多带一句 message
 * （:110 / :134 / :198-203）。认「成了」只认这一枚键的这一枚值，别的形状一律走「读不出结论」那张脸。
 */
export const USER_WRITE_OK_KEY = 'status'
export const USER_WRITE_OK_VALUE = 'ok'

export const USERS_UNCHANGED_TITLE = '后端说这一发什么都没改'
export const USERS_UNCHANGED_MESSAGE = '回包是 200，但它明写 changed=false：这一发没有改动任何东西。'
  + '最常见的原因是填进去的值与它原来记的本来就是同一个，或是这一发压根没带上那一格。'

/** 读不出结论那一张：它既不是成功，也不是「名册里没有账号」。 */
export function userWriteMalformedReceipt(kind, target) {
  return {
    face: USERS_FACE_MALFORMED,
    kind,
    target,
    title: USERS_WRITE_MALFORMED_TITLE,
    description: USERS_WRITE_MALFORMED_MESSAGE,
    codeLabel: '',
    retryable: false,
    changed: null,
  }
}

/** 这一行没编号：一张独立的脸，不降级成「删除失败」，也不假装删掉了。 */
export function userUnaddressableView(row) {
  const source = row && typeof row === 'object' ? row : {}
  const target = textOf(source.username) || textOf(source.id)
  return {
    face: USERS_FACE_MALFORMED,
    kind: USER_WRITE_DELETE,
    target,
    title: USERS_UNADDRESSABLE_TITLE,
    description: USERS_UNADDRESSABLE_MESSAGE,
    codeLabel: '',
    retryable: false,
    changed: null,
  }
}

/** 一次写失败 -> 一张脸。句子出处与读路径完全同一本字典，这里只决定标题与兜底场景话。 */
export function userWriteErrorView(err) {
  const face = userWriteFaceOf(err)
  const copy = USER_WRITE_FACE_COPY[face]
  const dictionaryOwn = face === USERS_FACE_DENIED || face === USERS_FACE_UNAUTHORIZED || face === USERS_FACE_STORAGE
  return {
    face,
    title: copy.title,
    description: errorDetail(err, copy.fallback) + copy.where,
    codeLabel: dictionaryOwn ? '' : errorCodeLabel(err),
    // 写失败一律不挂重试（三条理由见本段开头那三条，逐字出自 lib/errcodes.js:99-107）：
    // 要再来一次走表单那一枚提交钮，重放一发的本来就是同一发写。
    retryable: false,
    changed: null,
  }
}

/** 成功回包 -> 回执。target 是这一发点名的人，回执与确认句都靠它，绝不写「确定吗」那种空话。 */
export function userWriteReceiptView(kind, target, payload) {
  const envelope = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : null
  if (!envelope || textOf(envelope[USER_WRITE_OK_KEY]) !== USER_WRITE_OK_VALUE) {
    return userWriteMalformedReceipt(kind, target)
  }
  if (kind === USER_WRITE_DEPARTMENT) {
    if (typeof envelope.changed !== 'boolean') return userWriteMalformedReceipt(kind, target)
    if (!envelope.changed) {
      return {
        face: USERS_FACE_WRITE_OK,
        kind,
        target,
        title: USERS_UNCHANGED_TITLE,
        description: USERS_UNCHANGED_MESSAGE,
        codeLabel: '',
        retryable: false,
        changed: false,
      }
    }
    return {
      face: USERS_FACE_WRITE_OK,
      kind,
      target,
      title: '归属已经改写',
      // 那句归属取的是回包自己给的 department，不是表单里填的那一个：后端会 strip，也会把空串落成「无归属」。
      description: `后端这一发回的是 200：${target} 现在的归属是「${departmentText(envelope.department)}」。`,
      codeLabel: '',
      retryable: false,
      changed: true,
    }
  }
  const COPY = {
    [USER_WRITE_CREATE]: { title: '账号已开通', description: `后端这一发回的是 200：${target} 已按这一发的角色与归属写进名册。` },
    [USER_WRITE_DELETE]: { title: '账号已删除', description: `后端这一发回的是 200：${target} 那一行已删除。这一步不可逆。` },
    [USER_WRITE_PASSWORD]: { title: '密码已改写', description: `后端这一发回的是 200：${target} 的登录密码已按这一发提交的新密码改写。` },
  }
  const copy = COPY[kind] || { title: '这一步已成交', description: `后端这一发回的是 200：${target}。` }
  return {
    face: USERS_FACE_WRITE_OK,
    kind,
    target,
    title: copy.title,
    description: copy.description,
    codeLabel: '',
    retryable: false,
    changed: true,
  }
}

/**
 * 写完重读之后的那一次对表（判据乙的第二半）。
 *
 * 比的两侧都是【后端回包】：一侧是这一发写的回话，另一侧是随后那一次 GET 读回来的名册。
 * 这里不改本地任何一行，也不替后端圆场：后端说了 200 而重新读回的名册不支持它，屏上就必须
 * 同时摆出这两句话 ——「看着像成功了」的残影正是这一格要防的东西。
 */
export function userWriteReadback(kind, target, roster, sent = {}) {
  const NO_ROSTER = '名册这一次没读回来，所以上面那句只说后端对这一发的回话，不代表屏上此刻有几行。'
  const rows = roster && Array.isArray(roster.rows) ? roster.rows : []
  // 空名册是一次【读回来了的】结果（删掉最后一枚账号就该是它），只有真没读回来才对表说不了。
  if (usersFailureFace(roster)) return { consistent: false, note: NO_ROSTER }
  const found = rows.some(row => textOf(row.username) === textOf(target))
  if (kind === USER_WRITE_CREATE && !found) {
    return { consistent: false, note: `后端这一发回的是 200，但重新读回的名册里没有 ${target} 这一枚账号。` }
  }
  if (kind === USER_WRITE_DELETE && found) {
    return { consistent: false, note: `后端这一发回的是 200，但重新读回的名册里 ${target} 还在。` }
  }
  if ((kind === USER_WRITE_PASSWORD || kind === USER_WRITE_DEPARTMENT) && !found) {
    return { consistent: false, note: `后端这一发回的是 200，但重新读回的名册里已经找不到 ${target} 这一枚账号。` }
  }
  if (kind === USER_WRITE_DEPARTMENT && found) {
    const after = textOf(sent[USER_FORM_FIELDS.department])
    const row = rows.find(item => textOf(item.username) === textOf(target))
    if (textOf(row.department) !== after) {
      return { consistent: false, note: '后端这一发回的是 200，但重新读回的名册里这一枚的归属与这一发提交的不是同一个值。' }
    }
  }
  return { consistent: true, note: '名册已按后端回包重新读过，屏上那几行就是这一次读回来的结果。' }
}

/**
 * 四枚出口的调用层：返回的永远是回执（成功脸 / 失败脸 / 读不出结论脸），不抛给面板 ——
 * 与 loadUsers 同一条纪律，这一屏没有第二块内容可以被一次失败拖走。
 */
async function submitWrite(kind, target, send) {
  let response
  try {
    response = await send()
  } catch (err) {
    return { ...userWriteErrorView(err), kind, target }
  }
  const status = Number(response && response.status ? response.status : 0) || 0
  if (status !== 200) return { ...userWriteErrorView({ response, status }), kind, target }
  return userWriteReceiptView(kind, target, response && response.data)
}

export function submitCreateUser(form, client = http) {
  const body = createBody(form)
  return submitWrite(USER_WRITE_CREATE, body[USER_BODY_KEYS.username], () => client.post(USER_CREATE_PATH, body))
}

export function submitPasswordChange(form, client = http) {
  const body = passwordBody(form)
  return submitWrite(USER_WRITE_PASSWORD, body[USER_BODY_KEYS.username], () => client.put(USER_PASSWORD_PATH, body))
}

export function submitDepartmentChange(form, client = http) {
  const body = departmentBody(form)
  return submitWrite(USER_WRITE_DEPARTMENT, body[USER_BODY_KEYS.username], () => client.put(USER_DEPARTMENT_PATH, body))
}

export function submitDeleteUser(row, client = http) {
  const target = textOf(row && typeof row === 'object' ? row.username : '')
  const path = userDeletePath(row)
  if (!path) return Promise.resolve(userUnaddressableView(row))
  return submitWrite(USER_WRITE_DELETE, target, () => client.delete(path))
}
