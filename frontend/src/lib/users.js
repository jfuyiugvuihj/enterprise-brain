/**
 * R316 · 「账号与角色」这一屏的唯一取数点与判脸点（只读 GET /users）
 *
 * 这一格只做一件事：把服务端名册里真有的人列出来。开通与停用账号是另一枚单，
 * 本文件不接 POST /users，也不接 DELETE /users/{id}，一行都不接。
 *
 * 后端零改动，口径逐字跟着源码走（取证行号 = 主树 42a4e9e）：
 *   出口  app/api/v1/auth.py:90-95  GET /users 回 {"users": auth.list_users()}；
 *         :93 的 authorize_request(request, ACTION_MANAGE_USERS, "users") 与 :101 / :116
 *         两枚写出口过的是同一道闸 —— 本单只用第一枚。
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