/**
 * R360 判据甲·丙·己·庚 · 四枚写出口的 lib 层：契约取证表 + 六张失败脸 + 那本规则账
 *
 * 本件是本单对 docs/api/contract-v1.md 的唯一交代：那张表（ENDPOINTS 下面那枚数组）逐枚
 * 写着「后端真会回哪些状态码 / 码名 / 出处行号」，而且每一行都是从 `git show HEAD` 读回来的
 * 后端源码当场推导的，不是我抄的一段话：把某枚端点的分支删掉或改码，本件当场红。
 *
 * 三条手法，全部照仓里既有规矩：
 *  ① 对账读 git 对象，绝不 readFileSync 工作树里的 app/**（lib/errcodes.test.js:26-33 与
 *     r316-users-contract.test.js:52-62 同一条教训：工作树那一份可能与判据所依据的版本不同，
 *     读它就是「永远绿」的假绿）。要扫【被测试的前端代码】时才读工作树 —— 那正是被测物本身。
 *  ② 后端零改动：本件一枚码都不新增，也不改任何一枚的语义。四枚出口做不到的事（没有「停用」
 *     只有「删除」；改密码必须先验现由密码，所以管理员没有「一键重置」）一律只报不造，
 *     报的话写在交付回执里，这里只把它们能被机器验证的那一半钉成账本。
 *  ③ 判据丙那五型失败脸逐枚不等，且 403 那一张永远不许说「没有用户」；503 那一档不挂重试，
 *     三条理由逐字出自 lib/errcodes.js:99-107（本件末尾把它们钉成断言，不是钉成注释）。
 *
 * 反证刀（判据辛）里属于本件的三把：② 把 403 画成空名册、④ 发明一条前端自己的密码/角色规则、
 * 以及「后端换了真码而取证表还在说旧话」；每把的跑法与红数记在收工回执里。
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { describe, expect, it, vi } from 'vitest'
import { errorText, isRetryable } from '../errcodes'
import {
  USER_BODY_KEYS,
  USER_CREATE_DEFAULTS,
  USER_CREATE_PATH,
  USER_CREATABLE_ROLES,
  USER_DEPARTMENT_PATH,
  USER_FORM_RULES,
  USER_PASSWORD_PATH,
  USER_ROLES,
  USER_RULE_HINTS,
  USERS_CONFLICT_TITLE,
  USERS_DENIED_TITLE,
  USERS_DENIED_WHERE,
  USERS_EMPTY_DESCRIPTION,
  USERS_EMPTY_TITLE,
  USERS_FACE_CONFLICT,
  USERS_FACE_DENIED,
  USERS_FACE_EMPTY,
  USERS_FACE_FAILED,
  USERS_FACE_INVALID,
  USERS_FACE_MALFORMED,
  USERS_FACE_NOT_FOUND,
  USERS_FACE_READY,
  USERS_FACE_STORAGE,
  USERS_FACE_UNAUTHORIZED,
  USERS_FACE_WRITE_OK,
  USERS_INVALID_TITLE,
  USERS_LOADING_TEXT,
  USERS_NOT_FOUND_TITLE,
  USERS_STORAGE_TITLE,
  USERS_UNADDRESSABLE_TITLE,
  USERS_UNCHANGED_TITLE,
  USERS_UNAUTHORIZED_TITLE,
  USERS_WRITE_FAILED_TITLE,
  USERS_WRITE_MALFORMED_TITLE,
  USER_WRITE_CREATE,
  USER_WRITE_DELETE,
  USER_WRITE_DEPARTMENT,
  USER_WRITE_PASSWORD,
  createBody,
  departmentBody,
  passwordBody,
  submitCreateUser,
  submitDeleteUser,
  submitDepartmentChange,
  submitPasswordChange,
  userDeletePath,
  userFormRuleViolations,
  userWriteErrorView,
  userWriteFaceOf,
  userWriteReadback,
  userWriteReceiptView,
  usersErrorView,
} from '../users'

const REPO_REF = 'HEAD'

function showAtRef(path) {
  let text
  try {
    text = execFileSync('git', ['show', `${REPO_REF}:${path}`], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
  } catch (cause) {
    throw new Error(`读不到真源 ${REPO_REF}:${path}（git show 失败：${cause.message}）。取证表不许降级，这里必须红。`)
  }
  if (!text.trim()) throw new Error(`git show ${REPO_REF}:${path} 返回空内容，无法对账。`)
  return text.replace(/\r\n/g, '\n')
}

const API = showAtRef('app/api/v1/auth.py')
const STORE = showAtRef('app/common/auth.py')
const GUARD = showAtRef('app/common/authorization.py')
const PERMISSIONS = showAtRef('app/common/permissions.py')

/** 取一枚出口处理器的函数体：从它自己的装饰器起，到下一枚顶格装饰器为止。 */
function outletBody(src, decorator) {
  const start = src.indexOf(decorator)
  if (start < 0) throw new Error(`在 ${REPO_REF} 的后端源码里找不到 ${decorator}：出口换了形状，取证表必须重新取，不许悄悄放过。`)
  const rest = src.slice(start + decorator.length)
  const next = rest.search(/^@router\./m)
  return next < 0 ? rest : rest.slice(0, next)
}

const statusCodesOf = body => [...body.matchAll(/status_code=(\d+)/g)].map(item => Number(item[1]))
const sortedUnique = list => [...new Set(list)].sort((a, b) => a - b)

/**
 * 后端那三枚模型的真字段名（顺序也是账：CreateUserRequest / ChangePasswordRequest / UpdateDepartmentRequest）。
 * 正文取到下一枚顶格 class / 装饰器 / 注释块为止：UpdateDepartmentRequest 带 docstring，
 * 按空行截它会只截到那句 docstring，字段一格都不剩（第一版就是这么错的，红给我看过）。
 */
function modelBlock(name) {
  const head = `class ${name}(BaseModel):`
  const start = API.indexOf(head)
  if (start < 0) throw new Error(`解析不到 ${name}：请求体的键名对账落空。`)
  const rest = API.slice(start + head.length)
  const end = rest.search(/^class |^@router\.|^# /m)
  return end < 0 ? rest : rest.slice(0, end)
}

function modelFields(name) {
  return [...modelBlock(name).matchAll(/^ {4}([a-z_]+):/gm)].map(item => item[1])
}

/**
 * 取 app/common/auth.py 里那一枚函数自己的体：从签名起，到下一枚顶格 def 为止。
 *
 * 不能沿用上面那枚 outletBody —— 它按「下一顶格 @router.」收口，那是路由文件的形状；
 * app/common/auth.py 里一枚 @router. 都没有，于是它量到的是「本函数往后整个文件」，
 * 白名单尺就会把后面某枚函数里的 role 字面量当成本函数的规则读（R360丙 第一版就是这么红的）。
 */
function storeFunctionBody(name) {
  const head = `def ${name}(`
  const start = STORE.indexOf(head)
  if (start < 0) throw new Error(`app/common/auth.py 里找不到 ${head}：后端出口换了形状，本账必须重新取证。`)
  const rest = STORE.slice(start + head.length)
  const next = rest.search(/^def /m)
  return next < 0 ? rest : rest.slice(0, next)
}

/** 剥注释：结构钉量的是真要跑的代码，注释里写了「不许发明规则」不是违规（同 r316 那枚 helper 的口径）。 */
function withoutComments(text) {
  return text
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[\s;:{}])\/\/[^\n]*/g, '$1')
}

/** 取 userFormRuleViolations 的函数体：辛④那把刀量的是这一格里到底有什么，不是它长得多像。 */
function ruleFunctionBody(source) {
  const start = source.indexOf('export function userFormRuleViolations(')
  if (start < 0) throw new Error('lib 里认不出 userFormRuleViolations：那条「不许发明规则」的结构钉落空了。')
  const rest = source.slice(start)
  const end = rest.indexOf('\n}')
  if (end < 0) throw new Error('userFormRuleViolations 的函数体收不到尾，结构钉落空。')
  return rest.slice(0, end)
}

/**
 * 取证表（本单对契约的唯一交代）。四列里 own / gate / absent 三列都由上面的源码当场推导，
 * body 那一列对的是后端模型的真字段名 —— 我要是抄错一行，本件自己就会红。
 * 422 那一档不在 HTTPException 里：它是 FastAPI 对请求体/路径参数自己的校验（后端没有为此
 * 写任何一枚分支），所以表里单列一栏，并在下面用「声明过的形状」钉住它确实不是后端发的码。
 */
const ENDPOINTS = [
  {
    outlet: USER_WRITE_CREATE,
    decorator: '@router.post("/users")',
    verb: 'post',
    path: USER_CREATE_PATH,
    model: 'CreateUserRequest',
    ownCodes: [400],
    gateCodes: [401, 403],
    absentCodes: [404, 409, 503],
    okShape: '{"status": "ok"',
    // :109 那一枚 400 的 detail 就是 auth.create_user 返回的 msg 原样，逐枚出处在 STORE 里
    rejectSentences: ['用户名和密码不能为空', '密码至少 6 位', '非法角色', 'production_user_store_unavailable', '已存在'],
  },
  {
    outlet: USER_WRITE_DELETE,
    decorator: '@router.delete("/users/{user_id}")',
    verb: 'delete',
    path: '/users/',
    model: null,
    ownCodes: [404],
    gateCodes: [401, 403],
    absentCodes: [400, 409, 503],
    okShape: '{"status": "ok"}',
    rejectSentences: ['用户不存在'],
  },
  {
    outlet: USER_WRITE_PASSWORD,
    decorator: '@router.put("/users/password")',
    verb: 'put',
    path: USER_PASSWORD_PATH,
    model: 'ChangePasswordRequest',
    ownCodes: [400],
    // 这一枚的闸不走 authorize_request，而是在 :127-130 手写了一遍：401 与 403 都在这枚出口自己身上
    gateCodes: [401, 403],
    gateOwn: true,
    absentCodes: [404, 409, 503],
    okShape: '{"status": "ok"',
    rejectSentences: ['原密码错误', '新密码至少 6 位', 'production_user_store_unavailable'],
  },
  {
    outlet: USER_WRITE_DEPARTMENT,
    decorator: '@router.put("/users/department")',
    verb: 'put',
    path: USER_DEPARTMENT_PATH,
    model: 'UpdateDepartmentRequest',
    ownCodes: [400, 404],
    gateCodes: [401, 403],
    absentCodes: [409, 503],
    okShape: '"changed"',
    rejectSentences: ['用户不存在', '用户名不能为空'],
  },
]

/** 屏上此刻那一本规则账：逐枚对 STORE 的源码，改一个数字就红（判据丙：不许自己发明）。 */
/**
 * 可创建角色那一格的读法（R357 之后）：账只认一本院。
 *
 * R357（`f30ad8d`）把 app/common/auth.py 里那枚字面元组 `if role not in ("staff", ...)` 换成了
 * 引用 `if role not in CREATABLE_ROLES:`，真源挪到 app/common/permissions.py。本账跟着改口，
 * 而且这一改是**收紧**不是放宽：① 引用形式下，值必须当场从 permissions.py 那行 frozenset 字面量
 * 推导，auth.py 里从此一个字都不许留着角色名；② 谁把字面元组抄回 auth.py，而 permissions.py 里
 * 那本真源还在，就是凭空长出第二本账 —— 那种形状在本函数里当场抛，不放行；③ 两种形状都对不上
 * 时照旧抛「规则形状变了」。旧尺只读字面元组，读不到就抛，今天必然红（这条红是尺子在咬，不是账坏）。
 */
function creatableRolesFrom(create) {
  const literal = /if role not in \(([^)]*)\):/.exec(create)
  if (literal) {
    if (/^CREATABLE_ROLES\b/m.test(PERMISSIONS)) {
      throw new Error('可创建角色的真源已是 app/common/permissions.py::CREATABLE_ROLES（R357）：auth.py 退回手抄字面元组就是第二本账，本单不许放行。')
    }
    return literal[1].split(',')
  }
  const byName = /if role not in ([A-Z][A-Z0-9_]*)(?::[^=]*)?:/.exec(create)
  if (!byName) throw new Error('app/common/auth.py 里推导不到那枚角色白名单：规则形状变了，本账必须重新取证。')
  const decl = new RegExp(byName[1] + '\\s*(?::[^=]*)?=\\s*frozenset\\(\\{([^}]*)\\}\\)').exec(PERMISSIONS)
  if (!decl) throw new Error(`auth.py 引用了 ${byName[1]}，但 app/common/permissions.py 里推导不到它的 frozenset 字面量：那本账必须重新取证。`)
  // 拼接后的模式里只有一枚捕获组：那对花括号不捕获（已转义），所以读 decl[1]
  return decl[1].split(',')
}

const asRoleList = raw => raw.map(item => item.trim().replace(/^["']|["']$/g, '')).filter(Boolean).sort()

function scrapedRules() {
  const create = storeFunctionBody('create_user')
  const change = storeFunctionBody('change_password')
  const minLength = /if len\(password\) < (\d+):/.exec(create)
  const newMinLength = /if len\(new_password\) < (\d+):/.exec(change)
  const emptyGuard = /if not username or not password:/.test(create)
  if (!minLength || !newMinLength || !emptyGuard) {
    throw new Error('app/common/auth.py 的规则形状变了：本账必须重新取证，不许留旧数字继续绿。')
  }
  return {
    usernameRequired: emptyGuard,
    passwordRequired: emptyGuard,
    passwordMinLength: Number(minLength[1]),
    newPasswordMinLength: Number(newMinLength[1]),
    // 角色是一枚集合而不是一串顺序：frozenset 的书写次序不是契约，比就比排序后的那一序，
    // 免得谁调换 permissions.py 里的两行就让这本账假红（屏上下拉次序另有一枚钉在 R360丙 之外）。
    creatableRoles: asRoleList(creatableRolesFrom(create)),
  }
}

describe('R360甲 · 四枚出口逐枚接通，且后端一个字没动', () => {
  for (const endpoint of ENDPOINTS) {
    it(`${endpoint.outlet}：路径与动词逐字等于后端那一枚装饰器，成功回包认那一枚形状`, () => {
      const body = outletBody(API, endpoint.decorator)
      const [, verb, route] = /@router\.(get|post|put|delete)\("([^"]+)"\)/.exec(endpoint.decorator)
      expect(verb).toBe(endpoint.verb)
      const ourPath = endpoint.outlet === USER_WRITE_DELETE
        ? USER_CREATE_PATH + '/x'
        : endpoint.path
      expect(ourPath.replace('/x', '')).toBe(route.replace('/{user_id}', ''))
      expect(body).toContain(endpoint.okShape)
    })

    it(`${endpoint.outlet}：后端自己发的状态码就是表里那一组，表外的一枚都不许多画`, () => {
      const body = outletBody(API, endpoint.decorator)
      expect(sortedUnique(statusCodesOf(body))).toEqual(
        endpoint.gateOwn ? [...endpoint.ownCodes, ...endpoint.gateCodes].sort((a, b) => a - b) : endpoint.ownCodes,
      )
      for (const absent of endpoint.absentCodes) {
        expect(body, `后端这枚出口发不出 ${absent}，界面上不许有一张脸声称它会来`).not.toContain(`status_code=${absent}`)
      }
    })

    it(`${endpoint.outlet}：被拒时后端说的是那几句话，界面上不替它编原因`, () => {
      const body = outletBody(API, endpoint.decorator) + storeFunctionBody(endpoint.outlet === USER_WRITE_PASSWORD ? 'change_password' : endpoint.outlet === USER_WRITE_DEPARTMENT ? 'update_department' : endpoint.outlet === USER_WRITE_DELETE ? 'delete_user' : 'create_user')
      for (const sentence of endpoint.rejectSentences) {
        expect(body, `后端源码里再没有「${sentence}」这一说了，取证表要重新取`).toContain(sentence)
      }
    })
  }

  it('闸口那两枚码出自同一处：401 authentication_required / 403 权限不足（三枚 manage 出口共用）', () => {
    expect(GUARD).toContain('raise HTTPException(status_code=401, detail="authentication_required")')
    expect(GUARD).toContain('raise HTTPException(status_code=403, detail=str(exc))')
    for (const outlet of [USER_WRITE_CREATE, USER_WRITE_DELETE, USER_WRITE_DEPARTMENT]) {
      const decorator = ENDPOINTS.find(item => item.outlet === outlet).decorator
      expect(outletBody(API, decorator)).toContain('authorize_request(request, ACTION_MANAGE_USERS, resource_name="users")')
    }
    // 改密码那一枚自己手写闸，并且比另外三枚多一条「本人可以自助」的分支（:129）——这是四枚里唯一的例外
    const password = outletBody(API, '@router.put("/users/password")')
    expect(password).toContain('data.username != principal.username')
    expect(password).not.toContain('authorize_request(')
    // 那一半自助豁免被后端写进了这一枚自己的 docstring（auth.py:146-147），只能按「有没有这一行 if」判
    expect(outletBody(API, '@router.put("/users/department")')).not.toMatch(/if data\.username != principal\.username/)
  })

  it('重名不是 409：后端把它算在 400 那一档（表里 absentCodes 已经钉住这枚出口发不出 409）', () => {
    expect(API).not.toMatch(/status_code=409/)
    expect(storeFunctionBody('create_user')).toContain('psycopg.errors.UniqueViolation')
    expect(outletBody(API, '@router.post("/users")')).toContain('raise HTTPException(status_code=400, detail=msg)')
  })

  it('这四枚出口今天发不出 503：storage_unavailable 那张脸留着是为哪天，不是为今天', () => {
    for (const endpoint of ENDPOINTS) expect(outletBody(API, endpoint.decorator)).not.toContain('status_code=503')
  })

  it('只报不改的两条服务端缺口，钉成账本而不是愿望：没有「停用」出口，也没有删自己/删最后一个 admin 的保护', () => {
    expect(API).not.toMatch(/@router\.(put|patch|post)\("\/users\/(disable|activate|status)/)
    const deleteBody = outletBody(API, '@router.delete("/users/{user_id}")')
    expect(deleteBody).not.toContain('principal')
    expect(storeFunctionBody('delete_user')).not.toMatch(/role|admin/)
  })
})

describe('R360甲 · 请求体键名等于后端模型字段名', () => {
  it('POST 那三枚模型的字段逐字对上我们发出去的键（顺序也算账）', () => {
    expect(modelFields('CreateUserRequest')).toEqual([
      USER_BODY_KEYS.username, USER_BODY_KEYS.password, USER_BODY_KEYS.role, USER_BODY_KEYS.department,
    ])
    expect(modelFields('ChangePasswordRequest')).toEqual([
      USER_BODY_KEYS.username, USER_BODY_KEYS.oldPassword, USER_BODY_KEYS.newPassword,
    ])
    expect(modelFields('UpdateDepartmentRequest')).toEqual([USER_BODY_KEYS.username, USER_BODY_KEYS.department])
  })

  it('三枚 body 构造器发的那几枚键就是模型那几枚，一枚不多一枚不少', () => {
    const form = { username: 'baiye', password: 'secret6', role: 'staff', department: 'finance', oldPassword: 'old666', newPassword: 'fresh99' }
    expect(Object.keys(createBody(form))).toEqual(modelFields('CreateUserRequest'))
    expect(Object.keys(passwordBody(form))).toEqual(modelFields('ChangePasswordRequest'))
    expect(Object.keys(departmentBody(form))).toEqual(modelFields('UpdateDepartmentRequest'))
    expect(createBody(form).password).toBe('secret6')
    expect(passwordBody(form).old_password).toBe('old666')
  })

  it('department 那一枚每次必带：后端把「没带」读成「这轮没说」，一个字都不写（auth.py:171-180）', () => {
    const sent = departmentBody({ username: 'baiye', department: '' })
    expect(Object.keys(sent)).toContain(USER_BODY_KEYS.department)
    expect(sent[USER_BODY_KEYS.department]).toBe('')
    expect(outletBody(API, '@router.put("/users/department")')).toContain('if data.department is None:')
  })

  it('值不做二次加工：后端只对部门 strip（:182），用户名与密码它一个字都不改', () => {
    expect(createBody({ username: ' baiye ' }).username).toBe(' baiye ')
    expect(storeFunctionBody('create_user')).not.toMatch(/username\.strip|password\.strip/)
    expect(outletBody(API, '@router.put("/users/department")')).toContain('data.department.strip()')
  })

  it('删除按编号定位：名册那一行没编号就构造不出路径，前端不替后端猜一个 id', () => {
    expect(userDeletePath({ id: '7', username: 'baiye' })).toBe('/users/7')
    expect(userDeletePath({ id: '', username: 'baiye' })).toBe('')
    expect(userDeletePath(null)).toBe('')
  })

  it('表单默认值等于后端模型默认值（auth.py:22-23），不是界面自己挑的一枚', () => {
    const block = modelBlock('CreateUserRequest')
    const defaultOf = field => {
      const line = new RegExp(`^    ${field}: [^=]+= (.+)$`, 'm').exec(block)
      return line ? line[1].trim().replace(/["']/g, '') : null
    }
    expect(defaultOf('role')).toBe('staff')
    expect(defaultOf('department')).toBe('')
    expect(USER_CREATE_DEFAULTS.role).toBe(defaultOf('role'))
    expect(USER_CREATE_DEFAULTS.department).toBe(defaultOf('department'))
    // 默认角色还必须在后端那枚白名单里：抄错一枚默认值，界面上就开出一枚后端当场拒的账号
    expect(USER_CREATABLE_ROLES).toContain(USER_CREATE_DEFAULTS.role)
  })
})

describe('R360乙 · lib 这一层不产第二本名册', () => {
  /** 一枚只会记账的假 client：谁被动过、被动了几次，全在这张流水里。 */
  function fakeClient(reply = { status: 200, data: { status: 'ok', changed: true } }) {
    const calls = []
    return {
      calls,
      get: async url => { calls.push(['get', url]); return { status: 200, data: { users: [] } } },
      post: async (url, body) => { calls.push(['post', url, body]); return reply },
      put: async (url, body) => { calls.push(['put', url, body]); return reply },
      delete: async url => { calls.push(['delete', url]); return reply },
    }
  }

  const form = { username: 'newbie', password: 'secret6', role: 'staff', department: 'finance', oldPassword: 'old666', newPassword: 'fresh99' }

  it('四枚出口各自只发那一枚：动词、路径、请求体三件都对得上，一枚多余的请求都没有', async () => {
    const runs = [
      [USER_WRITE_CREATE, 'post', USER_CREATE_PATH],
      [USER_WRITE_PASSWORD, 'put', USER_PASSWORD_PATH],
      [USER_WRITE_DEPARTMENT, 'put', USER_DEPARTMENT_PATH],
    ]
    for (const [kind, verb, path] of runs) {
      const client = fakeClient()
      // 发的是哪一枚由 kind 决定：三枚各走自己那一个出口，谁的流水里都只有一笔
      const receipt = await (verb === 'post'
        ? submitCreateUser(form, client)
        : verb === 'put' && path === USER_PASSWORD_PATH
          ? submitPasswordChange(form, client)
          : submitDepartmentChange(form, client))
      expect(client.calls).toHaveLength(1)
      expect(client.calls[0][0]).toBe(verb)
      expect(client.calls[0][1]).toBe(path)
      expect(Object.keys(client.calls[0][2])).toEqual(
        verb === 'post'
          ? modelFields('CreateUserRequest')
          : path === USER_PASSWORD_PATH ? modelFields('ChangePasswordRequest') : modelFields('UpdateDepartmentRequest'),
      )
      expect(receipt.face).toBe(USERS_FACE_WRITE_OK)
      expect(receipt.kind).toBe(kind)
    }
    const del = fakeClient()
    await submitDeleteUser({ id: '7', username: 'baiye' }, del)
    expect(del.calls).toEqual([['delete', '/users/7']])
  })

  it('写回执里没有 rows 这一格：本层不产出名册的影子，屏上那几行只可能来自那一次 GET', async () => {
    const receipt = await submitCreateUser(form, fakeClient())
    expect(Object.keys(receipt).sort()).toEqual(
      ['changed', 'codeLabel', 'description', 'face', 'kind', 'retryable', 'target', 'title'].sort(),
    )
    expect(receipt).not.toHaveProperty('rows')
  })

  it('名册没编号那一行：不发注定 422 的请求，也不假装删掉了', async () => {
    const client = fakeClient()
    const receipt = await submitDeleteUser({ id: '', username: 'baiye' }, client)
    expect(client.calls).toEqual([])
    expect(receipt.face).toBe(USERS_FACE_MALFORMED)
    expect(receipt.title).toBe(USERS_UNADDRESSABLE_TITLE)
  })

  it('200 但读不出结论那一张不是成功：status 不是 ok、回包是数组、回包是 null 都算它', async () => {
    for (const data of [{ status: 'failed' }, {}, [], null, undefined, 'ok']) {
      const receipt = await submitCreateUser(form, fakeClient({ status: 200, data }))
      expect(receipt.face, JSON.stringify(data)).toBe(USERS_FACE_MALFORMED)
      expect(receipt.face).not.toBe(USERS_FACE_WRITE_OK)
      expect(receipt.title).toBe(USERS_WRITE_MALFORMED_TITLE)
    }
  })

  it('部门那一枚的 changed=false 说的是「没改动」，界面不许把它画成「改好了」', async () => {
    const unchanged = await submitDepartmentChange(form, fakeClient({ status: 200, data: { status: 'ok', changed: false, department: 'finance' } }))
    expect(unchanged.changed).toBe(false)
    expect(unchanged.title).toBe(USERS_UNCHANGED_TITLE)
    const changed = await submitDepartmentChange(form, fakeClient({ status: 200, data: { status: 'ok', changed: true, department: 'ops' } }))
    // 那句归属取的是回包给的 department，不是表单里填的那一个：后端会 strip，也会把空串落成「无归属」
    expect(changed.description).toContain('ops')
    const cleared = await submitDepartmentChange(form, fakeClient({ status: 200, data: { status: 'ok', changed: true, department: '' } }))
    expect(cleared.description).toContain('未登记归属部门')
    // changed 缺席/不是布尔：这一发的结论读不出来，不替后端猜一个 true
    const unreadable = await submitDepartmentChange(form, fakeClient({ status: 200, data: { status: 'ok' } }))
    expect(unreadable.face).toBe(USERS_FACE_MALFORMED)
  })
})

describe('R360丙 · 失败脸逐枚分开、各有出处，且不挂重试', () => {
  const http = (code, detail) => ({ response: { status: code, data: { detail } }, status: code })
  const FACE_ERRORS = {
    [USERS_FACE_DENIED]: http(403, 'permission_denied'),
    [USERS_FACE_UNAUTHORIZED]: http(401, 'authentication_required'),
    [USERS_FACE_CONFLICT]: http(409, 'conflict'),
    [USERS_FACE_NOT_FOUND]: http(404, '用户不存在'),
    [USERS_FACE_INVALID]: http(422, [{ loc: ['body', 'username'], msg: 'Field required', type: 'missing' }]),
    [USERS_FACE_STORAGE]: http(503, 'storage_unavailable'),
    [USERS_FACE_FAILED]: new Error('Network Error'),
  }

  it('七张脸各归各的，两两不等；没有一张说的是「名册里没有账号」', () => {
    const views = Object.entries(FACE_ERRORS).map(([face, err]) => {
      const view = userWriteErrorView(err)
      expect(view.face).toBe(face)
      return view
    })
    expect(new Set(views.map(item => item.title)).size).toBe(views.length)
    expect(new Set(views.map(item => `${item.face}|${item.description}`)).size).toBe(views.length)
    for (const view of views) {
      expect(view.face).not.toBe(USERS_FACE_EMPTY)
      expect(view.title).not.toBe(USERS_EMPTY_TITLE)
      expect(view.changed).toBe(null)
    }
  })

  it('403 那张说的是「不向你开放」+ 下一步去哪，句子出自字典，也不给重试入口', () => {
    const view = userWriteErrorView(FACE_ERRORS[USERS_FACE_DENIED])
    expect(view.title).toBe(USERS_DENIED_TITLE)
    expect(view.description).toContain(errorText('permission_denied'))
    expect(view.description).toContain(USERS_DENIED_WHERE)
    // 后端真发的两种散文形状（authorization.py 那句「权限不足: …」带不带 reason code）走同一张脸
    expect(userWriteFaceOf(http(403, '权限不足: users:manage (permission_denied)'))).toBe(USERS_FACE_DENIED)
    expect(userWriteFaceOf(http(403, '权限不足: users:manage'))).toBe(USERS_FACE_DENIED)
  })

  it('503 不挂重试按钮：lib/errcodes.js:99-107 那三条理由逐条钉成断言，不是留在注释里', () => {
    const err = FACE_ERRORS[USERS_FACE_STORAGE]
    const view = userWriteErrorView(err)
    expect(view.title).toBe(USERS_STORAGE_TITLE)
    expect(view.retryable).toBe(false)
    // 理由①：它是部署缺陷，重试同一个请求必然同样失败 —— 字典自己就判 false
    expect(isRetryable(err)).toBe(false)
    // 理由②：后端自己也没把它当可重试错，_RETRIABLE_CODES 那五档刻意没有这一档
    const retriable = /_RETRIABLE_CODES = \{([^}]*)\}/.exec(showAtRef('app/agents/evidence.py'))
    if (!retriable) throw new Error('evidence.py 里认不出 _RETRIABLE_CODES：这条理由必须重新取证。')
    const codes = retriable[1].match(/"[a-z_]+"/g).map(item => item.replace(/"/g, ''))
    expect(codes).toEqual(['model_unavailable', 'retrieval_unavailable', 'task_timeout', 'rate_limited', 'queue_unavailable'])
    expect(codes).not.toContain('storage_unavailable')
    // 理由③：retryable 决定界面挂不挂那颗按钮，所以必须说的是「去找人跑迁移」
    expect(errorText('storage_unavailable')).toContain('迁移')
  })

  it('写这一族没有任何一张脸挂重试：要再来一次走表单那一枚提交钮', () => {
    for (const err of Object.values(FACE_ERRORS)) expect(userWriteErrorView(err).retryable).toBe(false)
    for (const kind of [USER_WRITE_CREATE, USER_WRITE_DELETE, USER_WRITE_PASSWORD, USER_WRITE_DEPARTMENT]) {
      expect(userWriteReceiptView(kind, 'baiye', { status: 'ok' }).retryable).toBe(false)
    }
  })

  it('后端那枚 400 的原话占人话位：重名与「原密码错误」都照它说，界面上不另编原因', () => {
    const dup = userWriteErrorView(http(400, "用户 'baiye' 已存在"))
    expect(dup.face).toBe(USERS_FACE_INVALID)
    expect(dup.title).toBe(USERS_INVALID_TITLE)
    expect(dup.description).toContain("用户 'baiye' 已存在")
    expect(dup.codeLabel).toBe('')
    const wrongOld = userWriteErrorView(http(400, '原密码错误'))
    expect(wrongOld.face).toBe(USERS_FACE_INVALID)
    expect(wrongOld.description).toContain('原密码错误')
    expect(wrongOld.title).toBe(dup.title)
    expect(wrongOld.description).not.toBe(dup.description)
  })

  it('存储坏了却回 400 那一格：码名只走「错误码」小字那一条通道，不冒充没权限也不说成没用户', () => {
    const view = userWriteErrorView(http(400, 'production_user_store_unavailable'))
    expect(view.face).toBe(USERS_FACE_INVALID)
    expect(view.codeLabel).toBe('错误码：production_user_store_unavailable')
    expect(view.title).not.toBe(USERS_DENIED_TITLE)
    expect(view.title).not.toBe(USERS_EMPTY_TITLE)
    // 这枚码名后端确实在发，但既没进 ErrorEnvelope 封闭枚举也没进前端字典：只报不改
    expect(API).not.toContain('production_user_store_unavailable')
    expect(STORE).toContain('production_user_store_unavailable')
  })

  it('人话位一枚裸码名都不许上屏（庚）：每张脸的 description 里都找不到 snake_case', () => {
    for (const err of Object.values(FACE_ERRORS)) {
      const view = userWriteErrorView(err)
      expect(view.description, view.description).not.toMatch(/[a-z][a-z0-9]*_[a-z0-9_]+/)
    }
  })

  it('422 归「没收下这一发」，404 归「找不到这一枚账号」，两张不与前面任何一张同句', () => {
    expect(userWriteFaceOf(http(422, [{ loc: ['body'], msg: 'Field required', type: 'missing' }]))).toBe(USERS_FACE_INVALID)
    expect(userWriteFaceOf(http(404, '用户不存在'))).toBe(USERS_FACE_NOT_FOUND)
    expect(userWriteFaceOf(http(409, 'conflict'))).toBe(USERS_FACE_CONFLICT)
    expect(userWriteErrorView(http(404, '用户不存在')).title).toBe(USERS_NOT_FOUND_TITLE)
    expect(userWriteErrorView(http(409, 'conflict')).title).toBe(USERS_CONFLICT_TITLE)
    // 404 那一句说的是「这一枚账号」，绝不能与「名册里一个账号都没有」共用一句
    expect(userWriteErrorView(http(404, '用户不存在')).description).not.toContain(USERS_EMPTY_DESCRIPTION)
  })
})

describe('R360丙 · 那本规则账等于后端真规则（辛④的正面钉）', () => {
  it('USER_FORM_RULES 四个值逐枚对 app/common/auth.py 当场推导出来的账，改一个数字就红', () => {
    const scraped = scrapedRules()
    expect(USER_FORM_RULES.usernameRequired).toBe(scraped.usernameRequired)
    expect(USER_FORM_RULES.passwordRequired).toBe(scraped.passwordRequired)
    expect(USER_FORM_RULES.passwordMinLength).toBe(scraped.passwordMinLength)
    expect(USER_FORM_RULES.newPasswordMinLength).toBe(scraped.newPasswordMinLength)
    expect(asRoleList(USER_FORM_RULES.creatableRoles)).toEqual(scraped.creatableRoles)
    // R357 之后 auth.py 里一个字都不该再留着角色名：那本账挪走了就得留下「挪走了」的证据。
    // 只看签名之后的函数体 —— 签名上那枚 `role: str = "staff"` 是默认值，属 USER_CREATE_DEFAULTS
    // 那本账（另有钉），不是白名单，把它算进来会把这枚钉做成永久红，等于用假红换掉真红。
    const ownBody = storeFunctionBody('create_user')
    const afterSig = ownBody.slice(ownBody.indexOf(String.fromCharCode(10)) + 1)
    expect(afterSig).not.toMatch(/["'](staff|manager|admin|auditor)["']/)
    expect(afterSig).toMatch(/if role not in CREATABLE_ROLES:/)
  })

  it('后端对账号名与部门没有任何字符集/长度规则：这两格必须记 null，界面也不许长出正则', () => {
    expect(USER_FORM_RULES.usernamePattern).toBe(null)
    expect(USER_FORM_RULES.departmentPattern).toBe(null)
    const code = withoutComments(readFileSync(new URL('../users.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n'))
    const body = ruleFunctionBody(code)
    expect(body).not.toMatch(/RegExp|\.test\(|\/\^/)
    expect(body).not.toMatch(/\d/)
    expect(storeFunctionBody('create_user')).not.toMatch(/len\(username\)|username\.(isalpha|startswith|strip)/)
  })

  it('可创建的角色与可读到的角色同集：auditor 读得到、也开得出（R413，对 permissions.py::CREATABLE_ROLES）', () => {
    expect(USER_ROLES).toContain('auditor')
    expect(USER_CREATABLE_ROLES).toEqual(['staff', 'manager', 'admin', 'auditor'])
    expect([...USER_CREATABLE_ROLES].sort()).toEqual([...USER_ROLES].sort())
    expect(userFormRuleViolations(USER_WRITE_CREATE, { username: 'a', password: 'abcdef', role: 'auditor' }).role).toBeUndefined()
    expect(userFormRuleViolations(USER_WRITE_CREATE, { username: 'a', password: 'abcdef', role: 'superuser' }).role).toBe(USER_RULE_HINTS.roleUnknown)
  })

  it('预检只说后端那几条：六位、非空、白名单，除此之外一枚都不拦', () => {
    expect(userFormRuleViolations(USER_WRITE_CREATE, { username: '', password: 'abcdef', role: 'staff' })).toEqual({
      username: USER_RULE_HINTS.usernameRequired,
    })
    expect(userFormRuleViolations(USER_WRITE_CREATE, { username: 'a', password: '', role: 'staff' })).toEqual({
      password: USER_RULE_HINTS.passwordRequired,
    })
    expect(userFormRuleViolations(USER_WRITE_CREATE, { username: 'a', password: '12345', role: 'staff' })).toEqual({
      password: USER_RULE_HINTS.passwordTooShort,
    })
    // 后端说 6 位就 6 位：不多不少，把这条改成一枚更严的规则，上面那格先红
    expect(userFormRuleViolations(USER_WRITE_CREATE, { username: 'a', password: '123456', role: 'staff' })).toEqual({})
    // 中文账号名、带空格、带 emoji：后端一概不设字符集，所以这里也一概放行
    for (const username of [' 空格 开头 ', '张三', 'a'.repeat(200), '🧠-ops']) {
      expect(userFormRuleViolations(USER_WRITE_CREATE, { username, password: 'abcdef', role: 'staff' }), username).toEqual({})
    }
    // 部门同理：多长、什么字符都原样发
    expect(userFormRuleViolations(USER_WRITE_DEPARTMENT, { username: 'a', department: ' x '.repeat(40) })).toEqual({})
    // 改密码这一枚：后端对 old_password 没有非空规则（它验的是对不对），所以这里也不设 required
    expect(userFormRuleViolations(USER_WRITE_PASSWORD, { username: 'a', oldPassword: '', newPassword: 'abcdef' })).toEqual({})
    expect(userFormRuleViolations(USER_WRITE_PASSWORD, { username: 'a', oldPassword: 'x', newPassword: '12345' })).toEqual({
      newPassword: USER_RULE_HINTS.newPasswordTooShort,
    })
    // 删除这一枚后端没有任何表单规则，预检一枚都不许设
    expect(userFormRuleViolations(USER_WRITE_DELETE, {})).toEqual({})
  })

  it('那几句话里的位数是从账上取的，不是再手抄一遍', () => {
    expect(USER_RULE_HINTS.passwordTooShort).toContain(String(USER_FORM_RULES.passwordMinLength))
    expect(USER_RULE_HINTS.newPasswordTooShort).toContain(String(USER_FORM_RULES.newPasswordMinLength))
  })
})

describe('R360乙 · 写完重读之后那一次对表', () => {
  const roster = (...rows) => ({ face: USERS_FACE_READY, rows, title: '', description: '', codeLabel: '', retryable: false })
  const row = (username, department = 'finance') => ({ id: '7', username, role: 'admin', department, created_at: '' })

  it('后端说 200、重新读回来的名册也支持它：对表只说一句「读过了」，不改任何一行', () => {
    const back = userWriteReadback(USER_WRITE_CREATE, 'newbie', roster(row('baiye'), row('newbie')))
    expect(back.consistent).toBe(true)
    expect(back.note).toContain('重新读过')
    expect(Object.keys(back).sort()).toEqual(['consistent', 'note'])
  })

  it('后端说 200 而名册里没有那一枚：这一句必须同时摆在屏上，不许留下「看着像成功了」的残影', () => {
    const created = userWriteReadback(USER_WRITE_CREATE, 'newbie', roster(row('baiye')))
    expect(created.consistent).toBe(false)
    expect(created.note).toContain('200')
    expect(created.note).toContain('newbie')
    const deleted = userWriteReadback(USER_WRITE_DELETE, 'baiye', roster(row('baiye')))
    expect(deleted.consistent).toBe(false)
    expect(deleted.note).toContain('baiye 还在')
    const gone = userWriteReadback(USER_WRITE_DELETE, 'baiye', roster())
    expect(gone.consistent).toBe(true)
  })

  it('名册压根没读回来：对表说的是「这一次没读回来」，而不是「成功了」也不是「没有用户」', () => {
    const failed = usersErrorView({ response: { status: 503, data: { detail: 'storage_unavailable' } }, status: 503 })
    const back = userWriteReadback(USER_WRITE_PASSWORD, 'baiye', failed)
    expect(back.consistent).toBe(false)
    expect(back.note).toContain('没读回来')
    expect(back.note).not.toContain(USERS_EMPTY_TITLE)
  })

  it('部门那一枚连值都对表：回包说改了、名册读回来的却不是那个值，就说不一致', () => {
    const ok = userWriteReadback(USER_WRITE_DEPARTMENT, 'baiye', roster(row('baiye', 'ops')), { department: 'ops' })
    expect(ok.consistent).toBe(true)
    const drift = userWriteReadback(USER_WRITE_DEPARTMENT, 'baiye', roster(row('baiye', 'finance')), { department: 'ops' })
    expect(drift.consistent).toBe(false)
    expect(drift.note).toContain('不是同一个值')
    const missing = userWriteReadback(USER_WRITE_DEPARTMENT, 'gone', roster(row('baiye', 'finance')), { department: 'finance' })
    expect(missing.consistent).toBe(false)
  })

  it('清空归属读回来是空串那一枚，对表要认得它是「没部门」而不是「读不到」', () => {
    const cleared = userWriteReadback(USER_WRITE_DEPARTMENT, 'baiye', roster(row('baiye', '')), { department: '' })
    expect(cleared.consistent).toBe(true)
  })
})
