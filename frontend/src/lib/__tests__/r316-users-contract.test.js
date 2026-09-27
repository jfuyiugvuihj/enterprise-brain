/**
 * R316 判据①②③ · 名册的列账本与五张脸（lib 层）
 *
 * 三件事，各自有各自的出处：
 *  ① 列只认后端真发的那五枚键。对账读的是 `git show HEAD:app/common/auth.py`，
 *     不 readFileSync 工作树（lib/errcodes.test.js:26-33 那条教训同样适用于这里：
 *     工作树里的后端文件可能与判据所依据的那一版不同，读它就是「永远绿」的假绿）。
 *  ② 403 / 401 / 503 / 回包读不出行 / 真零行，五张脸两两不等，且 403 那一张永不塌成空态。
 *  ③ 零统计量：视图里没有前端算出来的数，源码里也没有「共 N 人」那一类词。
 *     扫描前先剥注释（剥法沿用 r136-screen-names.test.js 的 withoutComments）：注释里
 *     叙述「不许数人数」不是违规，把注释一起扫只会逼人删掉说明。
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { errorText } from '../../lib/errcodes'
import {
  USER_BACKEND_COLUMNS,
  USER_COLUMNS,
  USER_ROLES,
  USER_ROLE_LABELS,
  USER_ROLE_UNKNOWN,
  USERS_DENIED_TITLE,
  USERS_DENIED_WHERE,
  USERS_EMPTY_DESCRIPTION,
  USERS_EMPTY_TITLE,
  USERS_FACE_DENIED,
  USERS_FACE_EMPTY,
  USERS_FACE_FAILED,
  USERS_FACE_LOADING,
  USERS_FACE_MALFORMED,
  USERS_FACE_READY,
  USERS_FACE_STORAGE,
  USERS_FACE_UNAUTHORIZED,
  USERS_PATH,
  USERS_ROWS_KEY,
  createdAtText,
  departmentText,
  mapUserRow,
  parseUsersPayload,
  userRoleLabel,
  usersBlankView,
  usersErrorView,
  usersFailureFace,
  usersMalformedView,
} from '../users'

const REPO_REF = 'HEAD'

function showAtRef(path) {
  let text
  try {
    text = execFileSync('git', ['show', `${REPO_REF}:${path}`], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
  } catch (cause) {
    throw new Error(`读不到真源 ${REPO_REF}:${path}（git show 失败：${cause.message}）。列账本不许降级，这里必须红，skip 等于回到装饰。`)
  }
  if (!text.trim()) throw new Error(`git show ${REPO_REF}:${path} 返回空内容，无法对账。`)
  return text.replace(/\r\n/g, '\n')
}

/** 剥注释：块注释、行注释、模板注释都不参与「词」的扫描（同 r136 那枚 helper 的口径）。 */
function withoutComments(text) {
  return text
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[\s;:{}])\/\/[^\n]*/g, '$1')
}

const sourceOf = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const libSource = () => withoutComments(sourceOf('../users.js'))
const panelSource = () => withoutComments(sourceOf('../../components/AdminPanel.vue'))

/** 取 list_users 函数体：从 def 那一行到下一枚顶格 def 为止。 */
function listUsersBody(src) {
  const start = src.indexOf('def list_users(')
  if (start < 0) throw new Error('app/common/auth.py 里找不到 def list_users(：后端出口换了形状，列账本要重新取证。')
  const rest = src.slice(start + 1)
  const next = rest.search(/^def /m)
  return next < 0 ? rest : rest.slice(0, next)
}

/** 真源那串 SELECT 的列名，逐字取，不去重不排序 —— 顺序也是账。 */
function selectColumns(body) {
  const match = /SELECT\s+([^)]*?)\s+FROM\s+users/i.exec(body)
  if (!match) throw new Error('list_users 里解析不到 SELECT ... FROM users：后端读法变了，这里的对账必须一起改，不许悄悄放过。')
  return match[1].split(',').map(name => name.trim()).filter(Boolean)
}

/** 内存表那一腿手写的键名清单（后端两条腿必须回同一组键，否则屏上会出现第二条读法）。 */
function memoryStoreKeys(body) {
  const match = /return \[\s*\{([^}]*)\}/.exec(body)
  if (!match) throw new Error('list_users 的内存表那一腿解析不到字典字面量，键名对账落空。')
  return [...match[1].matchAll(/"([^"]+)":/g)].map(item => item[1])
}

describe('R316① · 列只认后端真发的那五枚键', () => {
  const body = listUsersBody(showAtRef('app/common/auth.py'))

  it('USER_BACKEND_COLUMNS 逐字等于后端 SELECT 的列名（顺序也算账，多一列少一列都红）', () => {
    expect(selectColumns(body)).toEqual(USER_BACKEND_COLUMNS)
  })

  it('内存表那一腿回的键与真库同一组：两条读法不许给出两份列集', () => {
    expect(memoryStoreKeys(body)).toEqual(USER_BACKEND_COLUMNS)
  })

  it('屏上的列定义按 key 与账本一一对应：label 是界面词汇，key 才是契约', () => {
    expect(USER_COLUMNS.map(column => column.key)).toEqual(USER_BACKEND_COLUMNS)
    for (const column of USER_COLUMNS) {
      expect(column.label, `${column.key} 没有给人看的列名`).toBeTruthy()
      expect(typeof column.formatter, `${column.key} 缺人话化这一层`).toBe('function')
    }
  })

  it('后端没给的那些列名，一帧都不许出现在 lib 与屏壳里', () => {
    const forbidden = ['最近登录', '最后登录', 'last_login', 'is_active', '活跃度', '部门人数', '账号总数', '邮箱', '头像']
    for (const invented of forbidden) {
      for (const [label, text] of [['lib', libSource()], ['屏壳', panelSource()]]) {
        expect(text, `${label} 里出现了后端从没给过的「${invented}」`).not.toContain(invented)
      }
    }
  })

  it('mapUserRow 只造那五枚键：回包里多出来的键一概不带上屏', () => {
    const row = mapUserRow({
      id: 7, username: 'baiye', role: 'admin', department: 'finance', created_at: '2026-09-01T10:00:00+08:00',
      last_login: '2026-09-27', status: 'active', email: 'x@y.z',
    })
    expect(Object.keys(row)).toEqual(USER_BACKEND_COLUMNS)
    expect(row).toEqual({ id: '7', username: 'baiye', role: 'admin', department: 'finance', created_at: '2026-09-01T10:00:00+08:00' })
  })

  it('读路径只有 GET /users 一枚：这一屏没有写出口，也没有第二条取数路径', () => {
    expect(USERS_PATH).toBe('/users')
    expect(USERS_ROWS_KEY).toBe('users')
    const text = libSource()
    expect(text).not.toMatch(/client\.post|client\.delete|client\.put|http\.post|http\.delete|http\.put/)
  })
})
describe('R316① · 后端出口与闸口（本屏只用读的那一枚）', () => {
  const api = showAtRef('app/api/v1/auth.py')

  it('GET /users 确实过 ACTION_MANAGE_USERS 这一道闸，所以 staff 拿到的天然是 403', () => {
    const handler = /@router\.get\("\/users"\)[\s\S]*?\n\n\n/.exec(api)
    if (!handler) throw new Error('app/api/v1/auth.py 里解析不到 GET /users 那枚出口：闸口对账落空，改的必须是这里。')
    expect(handler[0]).toContain('authorize_request(request, ACTION_MANAGE_USERS, resource_name="users")')
    // R356 把这一处从裸 `auth.list_users()` 换成显式表态的读法：读不到名册时抛
    // `UserStoreUnavailable`，路由答 503 `storage_unavailable` —— 本文件那张 USERS_FACE_STORAGE
    // 到这一笔才有真的生产者（在此之前「生产环境 + 进程内内存表」那一格回的是 200 空数组，界面
    // 画出来的是「这家公司没有用户」，一句假话）。断言按形状不按字面量（口径同 R351 那把尺子）：
    // 参数表以后再演进不该让这一格假红，但「不表态就把拒答读成空名册」必须红。
    expect(handler[0]).toMatch(/auth\.list_users\([^)]*\bdenial\s*=\s*auth\.DENIAL_RAISES\s*\)/)
    expect(handler[0]).toMatch(
      /except\s+auth\.UserStoreUnavailable[\s\S]*?status_code=503[\s\S]*?"storage_unavailable"/,
    )
    expect(handler[0]).toContain('{"users": users}')
  })

  it('users:manage 只登记在 admin 名下：入口该给谁，读的是后端那张表而不是前端猜', () => {
    const permissions = showAtRef('app/common/permissions.py')
    const roles = [...permissions.matchAll(/^    "([a-z_]+)":/gm)].map(item => item[1])
    expect(roles.sort()).toEqual([...USER_ROLES].sort())
    const lines = permissions.split('\n').filter(line => line.includes('ACTION_MANAGE_USERS'))
    expect(lines.some(line => line.includes('"admin"'))).toBe(true)
    expect(lines.some(line => /"(staff|manager|auditor)"/.test(line))).toBe(false)
  })
})

describe('R316① · 词表外不猜', () => {
  it('四个在册角色各有一句人话，定名出自 RBAC 设计文档 §5.1', () => {
    expect(USER_ROLES.map(userRoleLabel)).toEqual(['普通员工', '部门负责人', '系统管理员', '审计人员'])
    expect(Object.keys(USER_ROLE_LABELS)).toEqual(USER_ROLES)
  })

  it('后端回了一个词表外的角色：说认不下，不猜一个，也不把原串画上屏', () => {
    expect(userRoleLabel('superuser')).toBe(USER_ROLE_UNKNOWN)
    expect(userRoleLabel('')).toBe(USER_ROLE_UNKNOWN)
    expect(userRoleLabel(undefined)).toBe(USER_ROLE_UNKNOWN)
    expect(userRoleLabel('ADMIN')).toBe(USER_ROLE_UNKNOWN)
  })

  it('部门与创建时间缺席各有自己的说法，不共用一个空串也不补一个像真的值', () => {
    expect(departmentText('')).toBe('未登记归属部门')
    expect(departmentText('finance')).toBe('finance')
    expect(createdAtText('')).toBe('未记录')
    expect(createdAtText('2026-09-01T10:00:00+08:00')).toBe('2026-09-01 10:00')
  })
})

describe('R316② · 五张脸两两不等，任何一张都不许塌成「没有用户」', () => {
  const denied = usersErrorView({ response: { status: 403, data: { detail: 'permission_denied' } } })
  // 后端今天真发的那一句（app/common/authorization.py:23 把 reason code 括在正文里），
  // 归脸必须与裸码名走同一张脸：这一条防的是「换了个形状就认不出来，于是掉进兜底那张」。
  const deniedProse = usersErrorView({ response: { status: 403, data: { detail: '权限不足: users:manage (permission_denied)' } } })
  const unauthorized = usersErrorView({ response: { status: 401, data: { detail: 'authentication_required' } } })
  const storage = usersErrorView({ response: { status: 503, data: { detail: 'storage_unavailable' } } })
  const malformed = usersMalformedView()
  const empty = parseUsersPayload({ users: [] })

  it('没权限那张说的是「不向你开放」，句子出自字典，还带下一步去哪', () => {
    expect(denied.face).toBe(USERS_FACE_DENIED)
    expect(denied.title).toBe(USERS_DENIED_TITLE)
    expect(denied.description).toContain(errorText('permission_denied'))
    expect(denied.description).toContain(USERS_DENIED_WHERE)
    expect(denied.retryable).toBe(false)
    expect(denied.rows).toEqual([])
  })

  it('403 那句散文形状回来的是同一张脸：归脸不因为后端换了写法就退成兜底', () => {
    expect(deniedProse.face).toBe(USERS_FACE_DENIED)
    expect(deniedProse.title).toBe(USERS_DENIED_TITLE)
    expect(deniedProse.description).toContain(errorText('permission_denied'))
  })

  it('五张脸的 face、标题、说明两两互不相等，而且都不是「ready」', () => {
    const faces = [denied, unauthorized, storage, malformed, empty]
    expect(faces.map(item => item.face)).toEqual([
      USERS_FACE_DENIED, USERS_FACE_UNAUTHORIZED, USERS_FACE_STORAGE, USERS_FACE_MALFORMED, USERS_FACE_EMPTY,
    ])
    const triples = faces.map(item => `${item.face}|${item.title}|${item.description}`)
    expect(new Set(triples).size).toBe(faces.length)
    for (const item of faces) expect(item.face).not.toBe(USERS_FACE_READY)
  })

  it('五张里没有任何一张说得出「没有用户」那句空态话；空态那一张也说不出一句权限话', () => {
    for (const item of [denied, unauthorized, storage, malformed]) {
      expect(item.face).not.toBe(USERS_FACE_EMPTY)
      expect(item.title).not.toBe(USERS_EMPTY_TITLE)
      expect(item.description).not.toContain(USERS_EMPTY_DESCRIPTION)
    }
    expect(empty.face).toBe(USERS_FACE_EMPTY)
    expect(empty.title).toBe(USERS_EMPTY_TITLE)
    expect(empty.description).not.toContain(errorText('permission_denied'))
    expect(empty.description).not.toContain(USERS_DENIED_TITLE)
  })

  it('500 / 502 与归不出码的失败共用「没加载出来」那一张，但也只有那一张可以重试', () => {
    for (const err of [
      { response: { status: 500, data: { detail: 'internal_error' } } },
      { response: { status: 502, data: { detail: '网关返回了一段 HTML' } } },
      { code: 'ECONNABORTED', message: 'timeout of 30000ms exceeded' },
    ]) {
      const view = usersErrorView(err)
      expect(view.face).toBe(USERS_FACE_FAILED)
      expect(view.retryable).toBe(true)
      expect(view.face).not.toBe(USERS_FACE_EMPTY)
      expect(view.rows).toEqual([])
    }
  })

  it('usersFailureFace 只认那五张失败脸：ready / empty / loading 一律回空串，面板不会同时画出两张', () => {
    expect(usersFailureFace(denied)).toBe(USERS_FACE_DENIED)
    expect(usersFailureFace(unauthorized)).toBe(USERS_FACE_UNAUTHORIZED)
    expect(usersFailureFace(storage)).toBe(USERS_FACE_STORAGE)
    expect(usersFailureFace(malformed)).toBe(USERS_FACE_MALFORMED)
    expect(usersFailureFace(empty)).toBe('')
    expect(usersFailureFace(parseUsersPayload({ users: [{ id: 1 }] }))).toBe('')
    expect(usersFailureFace(usersBlankView(USERS_FACE_LOADING))).toBe('')
    expect(usersBlankView(USERS_FACE_LOADING).face).toBe(USERS_FACE_LOADING)
  })

  it('回包读不出行是一张独立的脸：列表键缺席、不是数组、整个回包是 null 都算它，不算空态', () => {
    for (const payload of [{}, { users: null }, { users: 'baiye' }, [row()], null, undefined]) {
      expect(parseUsersPayload(payload), `形状 ${JSON.stringify(payload)} 不该被读成回包`).toBe(null)
    }
    expect(malformed.title).toBe('账号名册的回包读不出行')
    expect(malformed.retryable).toBe(true)
  })

  it('200 有行才叫 ready，行逐条过 mapUserRow；5xx 与 401 都不许被降级成空列表', () => {
    const ready = parseUsersPayload({ users: [row(), row({ username: 'manager1', role: 'manager' })] })
    expect(ready.face).toBe(USERS_FACE_READY)
    expect(ready.rows).toHaveLength(2)
    expect(ready.rows.map(item => item.username)).toEqual(['baiye', 'manager1'])
    expect(storage.face).not.toBe(USERS_FACE_EMPTY)
    expect(unauthorized.face).not.toBe(USERS_FACE_EMPTY)
  })
})

describe('R316③ · 零统计量', () => {
  it('视图的格子就那七枚，没有一格装的是前端算出来的数', () => {
    const view = parseUsersPayload({ users: [row(), row(), row()] })
    expect(Object.keys(view).sort()).toEqual(['codeLabel', 'description', 'face', 'retryable', 'rows', 'title'])
    expect(view.face).toBe(USERS_FACE_READY)
  })

  it('lib 与屏壳里都不许长出「共 N 人 / 占比 / 活跃」那一类说法', () => {
    for (const [label, text] of [['lib', libSource()], ['屏壳', panelSource()]]) {
      expect(text, `${label} 里数了人数或占比`).not.toMatch(/共\s*\d*\s*人|账号总数|人数|占比|活跃|在岗/)
    }
  })
})

function row(overrides = {}) {
  return { id: 7, username: 'baiye', role: 'admin', department: 'finance', created_at: '2026-09-01T10:00:00+08:00', ...overrides }
}