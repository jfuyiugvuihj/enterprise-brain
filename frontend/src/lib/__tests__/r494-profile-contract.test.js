/**
 * R494 判据①②③④ · lib/profile.js 这一本账：列名对源码、请求体不带 department、三张失败脸各说各话
 *
 * 这一枚件是「我的账号」屏唯一取数层的看守，四组断言：
 *   甲 列名台账逐段对源码：名册三列取 app/common/auth.py 里 get_user 的那串 SELECT，画像三列取
 *     app/memory/profile.py 里 get_profile 的那串 SELECT，派生那一枚取 GET /profile 现场写出的键名。
 *     行号一律不进本账（锚点现读推导，同 r396/r416 的手法）；后端多一列而这里没跟上、或这里多一列
 *     而后端没有，都当场红。已在册的两段真源走 git show HEAD：工作树可能停在分支点，拿它对账等于
 *     永远绿的假绿；本单新写的那一枚派生键读工作树（HEAD 上还没有它，那是本次要落的码）。
 *   乙 请求体永不出 department（判据④）：后端判据是「出现即整发拒」（它读 data.model_fields_set，
 *     空串也算出现），所以这一条不许靠「我们不会传」的自觉——夹具把那枚键塞进表单，构造器仍不许带它出门。
 *   丙 三张失败脸两两不等（判据③）：403 department_override_denied / 503 storage_unavailable /
 *     500 画像保存失败 各自一张脸、各一句出处，不许塌成一句「保存失败」。夹具形状逐枚照后端真发的
 *     那一枚 detail 抄（FastAPI 的 {code, message} 信封、裸码、裸中文散文三种形状各一枚）。
 *   丁 档位宁缺不猜（判据②）：回执里有正整数才说「第 1–N 级」；缺席 / 0 / 负 / 小数 / 字符串 / 布尔
 *     一律走「这台服务器没把档位告诉我」，那一格不许出现任何数字。
 *
 * 🔴 全程零真实网络：lib/http.js 那枚 axios 实例换成进程内假实现，本屏只有那两条腿。
 */
import { execFileSync, spawnSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), put: vi.fn() } }
})

import { http } from '../http'
import {
  DEPARTMENT_READ_ONLY_NOTE,
  PROFILE_BODY_FORBIDDEN_KEY,
  PROFILE_BODY_KEYS,
  PROFILE_DERIVED_FIELD,
  PROFILE_DEPARTMENT_REFUSED_CODE,
  PROFILE_FACE_DEPARTMENT_REFUSED,
  PROFILE_FACE_FAILED,
  PROFILE_FACE_INVALID,
  PROFILE_FACE_LOADING,
  PROFILE_FACE_MALFORMED,
  PROFILE_FACE_READY,
  PROFILE_FACE_SAVED,
  PROFILE_FACE_SAVE_FAILED,
  PROFILE_FACE_STORAGE,
  PROFILE_FACE_UNAUTHORIZED,
  PROFILE_FACE_DENIED,
  PROFILE_ROSTER_COLUMNS,
  PROFILE_ROWS_KEY,
  PROFILE_READABLE_FIELDS,
  PROFILE_STORE_COLUMNS,
  PROFILE_TITLES,
  PROFILE_WRITE_FACES,
  clearanceLevel,
  clearanceText,
  clearanceView,
  linesToPreferences,
  loadProfile,
  preferenceLines,
  profileBlankView,
  profileCells,
  profileFaceView,
  profileViewFromError,
  profileViewFromResponse,
  profileWriteBody,
  submitProfile,
} from '../profile'

const CLEARANCE_UNKNOWN_TEXT = '这台服务器没把档位告诉我'

/** 后端 PUT /profile 真发过的三枚 detail 形状（app/api/v1/auth.py，逐字对照，不给它们合并的机会）。 */
const BACKEND_DEPARTMENT_REFUSAL = {
  response: {
    status: 403,
    data: {
      detail: {
        code: PROFILE_DEPARTMENT_REFUSED_CODE,
        message: '画像里的 department 是只读派生值，员工自助改不了；'
          + '要挪部门请用 PUT /api/v1/users/department（需要 users:manage）',
      },
    },
  },
}
const BACKEND_STORE_DOWN = { response: { status: 503, data: { detail: 'storage_unavailable' } } }
const BACKEND_NOT_WRITTEN = { response: { status: 500, data: { detail: '画像保存失败' } } }

/* ---------------------------------------------------------------- 现读真源 */

const CACHE = new Map()
function sourceAtHead(repoPath) {
  if (CACHE.has(repoPath)) return CACHE.get(repoPath)
  const ran = spawnSync('git', ['show', `HEAD:${repoPath}`], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })
  if (ran.status !== 0 || !String(ran.stdout).trim()) {
    throw new Error(`读不到真源 HEAD:${repoPath}（git 退出码 ${ran.status}：${String(ran.stderr).trim()}）。列名对账不许降级成 skip。`)
  }
  const text = String(ran.stdout).replace(/\r\n/g, '\n')
  CACHE.set(repoPath, text)
  return text
}

const workText = repoPath => readFileSync(new URL(`../../../../${repoPath}`, import.meta.url), 'utf8').replace(/\r\n/g, '\n')

/** 取 ``def name(...)`` 到下一枚顶层 def 之间的那一段。认不出来就抛，不静默给一段空文本。 */
function functionBody(text, name) {
  const start = text.search(new RegExp(`^def ${name}\\(`, 'm'))
  if (start < 0) throw new Error(`现读不到函数 ${name}：本件的锚点得先跟着改口`)
  const rest = text.slice(start + 1)
  const next = rest.search(/^def /m)
  return next < 0 ? text.slice(start) : text.slice(start, start + 1 + next)
}

/**
 * 从 ``SELECT a, b FROM x`` 里取列名清单，只在那一枚函数的体内找。
 * 满件扫是不行的：``app/common/auth.py`` 今天有五句写着 FROM users，
 * 一把捞起别人的 SELECT，这本账就退化成一张自证的空表。
 */
/**
 * 模块级那枚声明的右边：`^NAME ... = ...`，直到下一个空行为止。读不出就回 null，由调用方决定抛不抛。
 */
function moduleAssignment(text, name) {
  const pattern = new RegExp(`^${name}\\s*(?::[^=\\n]+)?=\\s*([\\s\\S]*?)(?=\\n\\s*\\n|\\n#|\\n(?=[A-Za-z_@]))`, "m")
  const hit = pattern.exec(text)
  return hit ? hit[1].trim() : null
}

/**
 * 乙形：函数体不再写字面 SELECT，而是引用一枚模块级 `*_SQL`，那句话由 `", ".join(*_COLUMNS)` 拼出来
 * （R495 把 `app/common/auth.py` 改成了这一形：列名从「巧合儿少一列」变成一枚**声明**）。
 * 不同的是这里仍然把 marker 当硬判据：那句拼出来的话必须真含 `FROM users` / `FROM user_profiles`，
 * 否就是把别人的列名抄进这本账。押不中返回 null，由上层抛。
 */
function columnsFromDeclaration(text, body, marker) {
  for (const [, name] of body.matchAll(/\b([A-Z][A-Z0-9_]{2,})\b/g)) {
    const sql = moduleAssignment(text, name)
    if (!sql || !sql.includes(marker)) continue
    const joined = /join\(\s*([A-Z][A-Z0-9_]+)\s*\)/.exec(sql)
    if (!joined) continue
    const tuple = moduleAssignment(text, joined[1])
    if (!tuple) continue
    const columns = tuple.replace(/[()\[\]]/g, "").split(",")
      .map(cell => cell.trim().replace(/^["']|["']$/g, "").trim())
      .filter(Boolean)
    if (columns.length) return columns
  }
  return null
}

/**
 * 从 `SELECT a, b FROM x` 里取列名清单，只在那枚函数的体内找。
 * 满件扫是不行的：`app/common/auth.py` 今天有五句写着 FROM users，
 * 一把捞起别人的 SELECT，这本账就退化成一张自证的空表。
 * 两形都读不出▶ 抛，不降级、不 skip：那意味着真源又换了写法，得先改量具。
 */
function selectColumnsFromText(text, functionName, marker, label) {
  const body = functionBody(text, functionName)
  const hits = [...body.matchAll(/SELECT\s+([^"\r\n]+?)\s+FROM\s+(\w+)/g)].filter(match => match[0].includes(marker))
  if (hits.length > 1) throw new Error(`${label}：在 ${functionName} 体内读到 ${hits.length} 枚 "${marker}"，无法唯一对账`)
  if (hits.length === 1) return hits[0][1].split(",").map(name => name.trim())
  const declared = columnsFromDeclaration(text, body, marker)
  if (declared) return declared
  throw new Error(`${label}：字面 SELECT 与列名声明两形都读不出 "${marker}"，真源换写法了，本件得先改口`)
}

/** 真源那一串列名：先按函数体里的字面 SELECT 读，读不出再顺列名声明摸（两形都押不中当场抛）。 */
function selectColumns(repoPath, functionName, marker, label) {
  return selectColumnsFromText(sourceAtHead(repoPath), functionName, marker, label)
}

const ROSTER_FROM_SOURCE = () => selectColumns('app/common/auth.py', 'get_user', 'FROM users', 'get_user 的那串 SELECT')
const STORE_FROM_SOURCE = () => selectColumns('app/memory/profile.py', 'get_profile', 'FROM user_profiles', 'get_profile 的那串 SELECT')

/** GET /profile 现场写出的那枚派生键：``profile["clearance"] = clearance_for(role)``，行号不进账。 */
function derivedKeyFromSource() {
  const hits = [...workText('app/api/v1/auth.py').matchAll(/\["(?<key>[\w_]+)"\]\s*=\s*clearance_for\((?<var>\w+)\)/g)]
  if (hits.length !== 1) throw new Error(`现读到的派生赋值有 ${hits.length} 处，判据①要的是恰好一处`)
  return { key: hits[0].groups.key, roleVar: hits[0].groups.var }
}

beforeEach(() => {
  vi.clearAllMocks()
})

/* -------------------------------------------------------------------- 甲组 */

describe('R494 甲 · 列名台账与后端源码逐段对上', () => {
  it('名册那三列 = get_user 现取的三列，一枚不多一枚不少', () => {
    expect(PROFILE_ROSTER_COLUMNS).toEqual(ROSTER_FROM_SOURCE())
    expect(PROFILE_ROSTER_COLUMNS).toEqual(['username', 'role', 'department'])
  })

  it('两形真源都读出同一串三列：甲＝基点那句字面 SELECT，乙＝R495 那枚列名声明', () => {
    const HEAD_FORM = [
      'def get_user(username: str) -> dict | None:',
      '    with _get_conn() as conn:',
      '        row = conn.execute(',
      '            "SELECT username, role, department FROM users WHERE username = %s",',
      '            (username,),',
      '        ).fetchone()',
      '    return dict(row) if row else None',
    ].join("\n")
    // 乙形逐字抄自主树 `8d228be`（R495 并树那一笔）：字段清单从 SQL 句子里搬进了一枚模块级声明，
    // 而那句 SQL 由 ", ".join(那枚声明) 拼出来。本件若只认甲形，并树之后就会把一串没变的列名读成「读不出」。
    const DECLARED_FORM = [
      'USER_LOOKUP_COLUMNS: tuple[str, ...] = ("username", "role", "department")',
      '',
      'USER_LOOKUP_SQL = (',
      '    "SELECT " + ", ".join(USER_LOOKUP_COLUMNS) + " FROM users WHERE username = %s"',
      ')',
      '',
      'def get_user(username: str) -> dict | None:',
      '    return _project_user_row(conn.execute(USER_LOOKUP_SQL, (username,)).fetchone())',
    ].join("\n")

    expect(selectColumnsFromText(HEAD_FORM, 'get_user', 'FROM users', '甲形'), '甲形读出来的列名变了').toEqual(['username', 'role', 'department'])
    expect(selectColumnsFromText(DECLARED_FORM, 'get_user', 'FROM users', '乙形'), '乙形读出来的列名与甲形不是同一串').toEqual(['username', 'role', 'department'])
    expect(selectColumnsFromText(DECLARED_FORM, 'get_user', 'FROM users', '乙形')).toEqual(ROSTER_FROM_SOURCE())
    // 两形都押不中时必须抛，不许退化成一张空账：那枚 marker 指的是别人的表。
    expect(() => selectColumnsFromText(HEAD_FORM, 'get_user', 'FROM sessions', '错表'),
      '读不出列名时本件静默放行，那就是自证的空表').toThrow()
  })

  it('画像那三列 = get_profile 现取的三列（department 早就不在这段里了，R296）', () => {
    expect(PROFILE_STORE_COLUMNS).toEqual(STORE_FROM_SOURCE())
    expect(PROFILE_STORE_COLUMNS).toEqual(['position', 'preferences', 'updated_at'])
    expect(PROFILE_STORE_COLUMNS).not.toContain(PROFILE_BODY_FORBIDDEN_KEY)
  })

  it('派生那一枚 = 出口现场写出的那枚键名，且它的值只能来自 clearance_for(role)', () => {
    const derived = derivedKeyFromSource()
    expect(PROFILE_DERIVED_FIELD).toBe(derived.key)
    expect(derived.roleVar).toBe('role')
  })

  it('这一屏可读的字段全集就是这三段：多一列就是有人在前端凭空造一格', () => {
    expect(PROFILE_READABLE_FIELDS).toEqual([...PROFILE_ROSTER_COLUMNS, ...PROFILE_STORE_COLUMNS, PROFILE_DERIVED_FIELD])
    expect(new Set(PROFILE_READABLE_FIELDS).size).toBe(PROFILE_READABLE_FIELDS.length)
  })

  it('读那一发只发 GET /profile 一条腿；屏上那句人话点名的出口本屏一发都不发', async () => {
    http.get.mockResolvedValue({ data: { [PROFILE_ROWS_KEY]: { username: 'a', role: 'staff', department: '研发部' } } })

    await loadProfile()

    expect(http.get).toHaveBeenCalledTimes(1)
    expect(http.get.mock.calls[0][0]).toBe('/profile')
    expect(http.put).not.toHaveBeenCalled()
    expect(DEPARTMENT_READ_ONLY_NOTE).toContain('/api/v1/users/department')
    expect(DEPARTMENT_READ_ONLY_NOTE).toContain('users:manage')
  })
})

/* -------------------------------------------------------------------- 乙组 */

describe('R494 乙 · 请求体里绝不许出现 department（判据④的钉）', () => {
  it('正常表单：只出 position 与 preferences 两枚键', () => {
    const body = profileWriteBody({ position: '工程师', preferences: '图表优先\n先给结论' })
    expect(Object.keys(body).sort()).toEqual(['position', 'preferences'])
    expect(body).toEqual({ [PROFILE_BODY_KEYS.position]: '工程师', [PROFILE_BODY_KEYS.preferences]: ['图表优先', '先给结论'] })
  })

  it('🔴 夹具把 department 塞进表单，构造器也不许带它出门（后端一见到它就整发拒）', () => {
    const body = profileWriteBody({
      position: '工程师',
      preferences: '',
      [PROFILE_BODY_FORBIDDEN_KEY]: '市场部',
      department_override: '市场部',
    })

    expect(PROFILE_BODY_FORBIDDEN_KEY in body).toBe(false)
    expect(Object.keys(body)).not.toContain(PROFILE_BODY_FORBIDDEN_KEY)
    // 空串也算「出现」：所以这一发里连一枚值为空串的 department 都不许有
    expect(JSON.stringify(body)).not.toContain(`"${PROFILE_BODY_FORBIDDEN_KEY}"`)
  })

  it('空表单也是一枚合法的两键体，而不是「干脆什么都不发」', () => {
    expect(profileWriteBody({})).toEqual({ position: '', preferences: [] })
  })

  it('偏好的分隔符只有换行一枚：其余字符一个都不动，动了就是替后端改规则', () => {
    expect(linesToPreferences('a,,b\n c \n\n')).toEqual(['a,,b', 'c'])
    expect(preferenceLines(['图表优先', '', '  ', '先给结论'])).toEqual(['图表优先', '先给结论'])
    expect(preferenceLines('不是数组')).toEqual([])
  })

  it('写那一发 PUT 走的还是同一条腿，成功后再读一次（不乐观）', async () => {
    http.put.mockResolvedValue({ data: { status: 'ok' } })
    http.get.mockResolvedValue({ data: { [PROFILE_ROWS_KEY]: { username: 'a', role: 'staff', clearance: 2, position: '工程师' } } })

    const out = await submitProfile(profileWriteBody({ position: '工程师', preferences: '' }))

    expect(out.face).toBe(PROFILE_FACE_SAVED)
    expect(http.put).toHaveBeenCalledTimes(1)
    expect(http.put.mock.calls[0][0]).toBe('/profile')
    expect(Object.keys(http.put.mock.calls[0][1])).not.toContain(PROFILE_BODY_FORBIDDEN_KEY)

    const reloaded = await loadProfile()
    expect(reloaded.face).toBe(PROFILE_FACE_READY)
    expect(reloaded.row.position).toBe('工程师')
  })
})

/* -------------------------------------------------------------------- 丙组 */

describe('R494 丙 · 三张失败脸两两不等，句子各自有出处（判据③）', () => {
  const faces = {
    department: profileViewFromError(BACKEND_DEPARTMENT_REFUSAL, 'write'),
    storage: profileViewFromError(BACKEND_STORE_DOWN, 'write'),
    saveFailed: profileViewFromError(BACKEND_NOT_WRITTEN, 'write'),
  }

  it('三张脸各自的 face 值都不同名，且都在写腿那张清单里', () => {
    expect(faces.department.face).toBe(PROFILE_FACE_DEPARTMENT_REFUSED)
    expect(faces.storage.face).toBe(PROFILE_FACE_STORAGE)
    expect(faces.saveFailed.face).toBe(PROFILE_FACE_SAVE_FAILED)
    for (const view of Object.values(faces)) expect(PROFILE_WRITE_FACES).toContain(view.face)
  })

  it('标题两两不等：把任一枚分派摘掉，三张脸就塌成同一句「保存失败」', () => {
    const titles = Object.values(faces).map(view => PROFILE_TITLES[view.face])
    expect(new Set(titles).size).toBe(3)
    for (const title of titles) {
      expect(title).toBeTruthy()
      expect(title).not.toBe('保存失败')
    }
  })

  it('句子逐枚读回后端自己的话：403 说部门、503 说存储没就绪、500 才是那句没写成', () => {
    const departmentText = profileFaceView(faces.department).description
    const storageText = profileFaceView(faces.storage).description
    const failedText = profileFaceView(faces.saveFailed).description

    expect(departmentText).toContain('部门')
    expect(storageText).toContain('数据表')
    // 后端那句裸中文散文原样上屏：R383 之后 500 只剩「存储自报就绪却没写成」这一种含义
    expect(failedText).toBe('画像保存失败')
    expect(new Set([departmentText, storageText, failedText]).size).toBe(3)
  })

  it('写腿的每张失败脸都不挂重试按钮：重放同一发写就是再来一次副作用', () => {
    for (const view of Object.values(faces)) {
      expect(profileFaceView(view).retryable).toBe(false)
    }
  })

  it('503 在读腿是同一张脸（同一条排查路），但它不与「读不出形状」「其它失败」「没登录」「没权限」「422」合并', () => {
    expect(profileViewFromError(BACKEND_STORE_DOWN, 'read').face).toBe(PROFILE_FACE_STORAGE)
    expect(profileViewFromResponse({ data: {} }).face).toBe(PROFILE_FACE_MALFORMED)
    expect(profileViewFromError(new Error('network down'), 'read').face).toBe(PROFILE_FACE_FAILED)
    expect(profileViewFromError({ response: { status: 401, data: { detail: 'authentication_required' } } }, 'read').face).toBe(PROFILE_FACE_UNAUTHORIZED)
    expect(profileViewFromError({ response: { status: 403, data: { detail: 'permission_denied' } } }, 'read').face).toBe(PROFILE_FACE_DENIED)
    expect(profileViewFromError({ response: { status: 422, data: { detail: [{ msg: '字段不对' }] } } }, 'read').face).toBe(PROFILE_FACE_INVALID)
    const seven = [PROFILE_FACE_LOADING, PROFILE_FACE_READY, PROFILE_FACE_UNAUTHORIZED, PROFILE_FACE_DENIED, PROFILE_FACE_STORAGE, PROFILE_FACE_MALFORMED, PROFILE_FACE_FAILED]
    expect(new Set(seven).size).toBe(7)
  })

  it('403 里「部门那一格不归你写」与「这一格不向你开放」是两件事，不许共用一张脸', () => {
    const refused = profileViewFromError(BACKEND_DEPARTMENT_REFUSAL, 'write')
    const plain = profileViewFromError({ response: { status: 403, data: { detail: 'permission_denied' } } }, 'write')
    expect(refused.face).toBe(PROFILE_FACE_DEPARTMENT_REFUSED)
    expect(plain.face).toBe(PROFILE_FACE_DENIED)
    expect(PROFILE_TITLES[refused.face]).not.toBe(PROFILE_TITLES[plain.face])
  })

  it('200 但回包读不出对象 = malformed，不许画成一张空白的「没有画像」', async () => {
    http.get.mockResolvedValue({ data: { unexpected: 1 } })

    const view = await loadProfile()

    expect(view.face).toBe(PROFILE_FACE_MALFORMED)
    expect(profileFaceView(view).title).toBe(PROFILE_TITLES[PROFILE_FACE_MALFORMED])
    expect(view.row).toBeNull()
    expect(profileFaceView(view).retryable).toBe(true)
  })

  it('读回来的那一行只认后端真发的那几列：屏上四格的值全来自回包', () => {
    const view = profileViewFromResponse({
      data: {
        [PROFILE_ROWS_KEY]: {
          username: 'lishan', role: 'manager', department: '研发部', clearance: 2,
          position: '负责人', preferences: ['先给结论'],
        },
      },
    })

    expect(view.face).toBe(PROFILE_FACE_READY)
    const cells = profileCells(view.row)
    expect(cells.username).toBe('lishan')
    expect(cells.roleText).toBe('部门负责人')
    expect(cells.department).toBe('研发部')
    expect(cells.position).toBe('负责人')
    expect(cells.preferences).toBe('先给结论')
    expect(cells.clearance).toEqual({ known: true, level: 2, text: '你能读到第 1–2 级', note: '' })
  })

  it('回包缺列也不替它补一个值：读不到就是空，档位读不到就是那句「没告诉我」', () => {
    const cells = profileCells({ profile: 1 })

    expect(cells).toMatchObject({ username: '', role: '', position: '', preferences: '' })
    expect(cells.clearance.known).toBe(false)
    expect(cells.clearance.text).toBe(CLEARANCE_UNKNOWN_TEXT)
    expect(profileBlankView().face).toBe('loading')
  })
})

/* -------------------------------------------------------------------- 丁组 */

describe('R494 丁 · 档位宁缺不猜（判据②）', () => {
  it('只有正整数才算「知道」：0 / 负 / 小数 / 字符串 / null / 缺席 / 布尔 全部走那句实话', () => {
    expect(clearanceLevel({ clearance: 1 })).toBe(1)
    expect(clearanceLevel({ clearance: 3 })).toBe(3)
    for (const bad of [0, -1, 2.5, '2', '', null, undefined, {}, [], true, false]) {
      expect(clearanceLevel({ clearance: bad }), `档位那一格拿到了 ${JSON.stringify(bad)}`).toBe(0)
    }
    expect(clearanceLevel(null)).toBe(0)
    expect(clearanceLevel({})).toBe(0)
  })

  it('拿不到就整格说「这台服务器没把档位告诉我」，那一格不许出现一枚数字', () => {
    const view = clearanceView({ username: 'a' })

    expect(view.known).toBe(false)
    expect(view.text).toBe(CLEARANCE_UNKNOWN_TEXT)
    expect(view.text).not.toMatch(/\d/)
    expect(view.note).toContain('不是')
    expect(view.note).toContain('角色')
  })

  it('拿得到才说「第 1–N 级」，N 就是后端给的那一枚数，前端不 +1 也不 -1', () => {
    expect(clearanceText(1)).toBe('你能读到第 1–1 级')
    expect(clearanceView({ clearance: 3 }).text).toBe('你能读到第 1–3 级')
    expect(clearanceView({ clearance: 3 }).level).toBe(3)
  })
})
