/**
 * R416 · 注释里每一枚 path:line 必须现读对账；「壳层认识角色」也不许只靠一句改口
 *
 * 病有两格，都在注释这一侧，都不改变渲染。R416 已把这两格改口，本件钉的是它不许回去、也不许漂：
 *   ① frontend/src/router/index.js 的 /admin 那一格原来写着「壳层今天还不认识角色」「入口还没接
 *      线」，而同树的 App.vue 早就 import 了 navigationForRole、侧栏那枚 v-for 吃的就是它，
 *      r316-admin-entry.test.js 正是钉这件事的在册用例 —— 注释比实现旧，读它会以为还欠一次接线。
 *   ② 同一格原来引 app/api/v1/auth.py:93 讲 ACTION_MANAGE_USERS 闸，而 93 是一枚空行；
 *      frontend/src/lib/dashboard.js 又原来引 dashboard.py 的 137-139 讲 alerts 键的条件性，
 *      那三行今天是 parse-vs-index 那段 docstring 的尾部。行号是手抄来的，代码一挪就成了假坐标。
 *
 * 四组断言，缺一组都不算收口：
 *   甲 台账全覆盖：两枚文件里现扫到的每一枚 path:line 都在 LEDGER 里有且只有一条对账规则，
 *      多一枚少一枚都红 —— 删引用躲检查、手抄一枚新数字，当场撞。
 *   乙 逐枚现读对账：真位置由 finders 在**目标文件**里当场推导，注释声称的那枚数字必须等于推导
 *      结果，且被引那一行本身必须真写着锚串（contains / notContains）。markdown 里的引用一样数到
 *      行，「落在同一节里」不算对上。LEDGER 里的 numbers 记的是注释「声称」的数字，不是写死的真理：
 *      只把旧数字抄回注释而不动台账，甲组红（账外引用）；注释与台账一起抄回去，乙组红（声称 != 推导）。
 *   丙 「壳层认识角色」的当前真相：禁句族 0 命中；且光把注释改成「已接线」不算过关 —— 必须从
 *      测试文件集合里现读到一枚真在钉这条接线的在册用例，它钉的那句话还得真的印在 App.vue 上，
 *      而 router 那一侧的注释必须点名这枚用例所在文件。
 *   丁 渲染无关性：剥掉注释后的可执行部分与基点逐字节相等，行数也相等 —— 改口不许挪任何人的行号，
 *      后端与 docs 里都有账按行号指着这一族前端文件，丁组钉的就是那些账不许被我的改口挪走。
 *
 * 越界登记（R416 记下 5 枚，R420 逐枚改口收完）：LEDGER 里 debt: true 的 0 枚 —— 台账上每一枚数字今天
 * 都由 finders 在目标文件里当场推导对上；这个枚数由甲组最后一枚用例现读 LEDGER 与这句自述对账，
 * 改一行台账不改这句自述，当场红。同一枚用例从 R420 起是**棘轮**：debt 数必须等于 0 —— 新登记一枚越界
 * 坐标要先经总控批准才许入账，不再允许「先记着以后修」，那等于放一枚假坐标过夜，第二天没人认得它。
 *
 * 真源一律 git show <ref>:<path>，与 r411 丁组、r368 戊组同一口径：工作树可能停在分支点，
 * 拿它对账等于永远绿的假绿。读不到就抛错让测试红，禁止 skip。
 */
import { execFileSync } from 'node:child_process'
import { readdirSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/** R416 的基点。谁改这两枚文件的代码，就带着这两枚常量一起改口（总控裁定后换锚）。 */
const BASE = '0f12a17'

const ROUTER = 'frontend/src/router/index.js'
const DASHBOARD = 'frontend/src/lib/dashboard.js'

/** 注释里的写法 -> 仓内真源。没登记在这张表里的引用名，甲组当场红。 */
const TARGETS = {
  'app/api/v1/auth.py': 'app/api/v1/auth.py',
  'app/api/v1/observability.py': 'app/api/v1/observability.py',
  'app/api/v1/dashboard.py': 'app/api/v1/dashboard.py',
  'app/common/policy.py': 'app/common/policy.py',
  'app/common/permissions.py': 'app/common/permissions.py',
  'dashboard.py': 'app/api/v1/dashboard.py',
  'alerts.py': 'app/api/v1/alerts.py',
  'permissions.py': 'app/common/permissions.py',
  'App.vue': 'frontend/src/App.vue',
  'docs/api/contract-v1.md': 'docs/api/contract-v1.md',
  'docs/frontend-plan-2026-09-14.md': 'docs/frontend-plan-2026-09-14.md',
}

const CACHE = new Map()

function showAt(ref, path) {
  const key = ref + ':' + path
  if (CACHE.has(key)) return CACHE.get(key)
  let text
  try {
    text = execFileSync('git', ['show', key], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })
  } catch (cause) {
    throw new Error('读不到真源 ' + key + '（git show 失败：' + cause.message + '）。行号对账不许降级成 skip。')
  }
  if (!String(text).trim()) throw new Error('git show ' + key + ' 返回空内容，无法对账。')
  const lines = String(text).replace(/\r\n/g, '\n').split('\n')
  CACHE.set(key, lines)
  return lines
}

const atHead = path => showAt('HEAD', path)
const atBase = path => showAt(BASE, path)
const workText = repoPath => readFileSync(new URL('../../../../' + repoPath, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const claimLines = repoPath => workText(repoPath).split('\n')

/* ------------------------------------------------------------------ 现读推导 */

const countMatches = (lines, pattern) => lines.filter(line => new RegExp(pattern).test(line)).length

/** 当场找出写着 pattern 的那一行（1-based）。认不出来就抛：换了形状的账必须红，不许静默放行。 */
function findLine(lines, pattern, label, from = 0) {
  const re = new RegExp(pattern)
  for (let i = from; i < lines.length; i += 1) {
    if (re.test(lines[i])) return i + 1
  }
  throw new Error('现读推导落空：' + label + '（pattern ' + pattern + '，从第 ' + (from + 1) + ' 行数起）')
}

const roleLine = role => '^\\s{4}"' + role + '":\\s*frozenset'

/* ---------------------------------------------------------------------- 台账 */

/**
/**
 * 对账姿势只有一种：逐行。注释写的每一枚数字都必须等于当场推导的那一行，被引那一行本身还必须
 * 真写着锚串（contains / notContains）。markdown 里的引用也一样数到行 —— 「落在同一节里」不算对上。
 * debt: true —— R420 起停用：这一族登记要先经总控批准才许入账，甲组那枚棘轮钉死 LEDGER 里一枚都不许有
 */
const LEDGER = [
  {
    id: '乙-1 「交成果」的屏名出处',
    file: ROUTER,
    cited: 'docs/frontend-plan-2026-09-14.md',
    numbers: [132],
    finders: [{
      label: '工作区映射表里新增「交成果」那一行',
      pattern: '^\\|.*（新增）.*交成果',
      contains: ['交成果', 'B-1 / R2'],
    }],
  },
  {
    id: '乙-2 /admin 读的那道 users:manage 闸',
    file: ROUTER,
    cited: 'app/api/v1/auth.py',
    numbers: [107],  // R494 把 app/api/v1/auth.py 从 296 行拉到 319 行，真闸 authorize_request(..., ACTION_MANAGE_USERS) 跟着从 106 漂到 107。改的是登记名单本身（仍逐行对账），断言强度未动。
    finders: [{
      label: 'list_users 里那一发 authorize_request(..., ACTION_MANAGE_USERS)',
      pattern: 'authorize_request\\(request, ACTION_MANAGE_USERS',
      after: 'async def list_users\\(',
      contains: ['ACTION_MANAGE_USERS'],
    }],
    note: '基点上这里手抄的是 auth.py:93 —— 那一行今天是空行，真闸在 list_users 内部。',
  },
  {
    id: '乙-3 ADMINISTRATOR_ROLE 与它的服务端同族',
    file: ROUTER,
    cited: 'app/common/policy.py',
    numbers: [44, 95],
    finders: [
      { label: '_ADMINISTRATOR_ROLES 的定义', pattern: '^_ADMINISTRATOR_ROLES\\s*=\\s*frozenset', contains: ['_ADMINISTRATOR_ROLES'] },
      { label: '_is_administrator 的返回', pattern: 'return ACTION_MANAGE_USERS in permissions', contains: ['ACTION_MANAGE_USERS', '_ADMINISTRATOR_ROLES'] },
    ],
    extra(lines) {
      expect(countMatches(lines, '^_ADMINISTRATOR_ROLES\\s*='), '后端长出了第二枚 _ADMINISTRATOR_ROLES 定义：注释那句「就只有这一枚」得改口').toBe(1)
    },
  },
  {
    id: '乙-4 侧栏那枚 v-for 的真位置',
    file: ROUTER,
    cited: 'App.vue',
    numbers: [472],
    finders: [{
      label: 'v-for="item in navigationForRole(userRole)"',
      pattern: 'v-for="item in navigationForRole\\(userRole\\)"',
      contains: ['navigationForRole(userRole)'],
    }],
  },
  {
    id: '乙-5 audit:read 登记在谁名下',
    file: ROUTER,
    cited: 'app/common/permissions.py',
    numbers: [15, 16],
    finders: [
      { label: 'ROLE_PERMISSIONS 的 admin 那一行', pattern: roleLine('admin'), contains: ['ACTION_AUDIT'] },
      { label: 'ROLE_PERMISSIONS 的 auditor 那一行', pattern: roleLine('auditor'), contains: ['ACTION_AUDIT'] },
    ],
    extra(lines, entry) {
      const staff = findLine(lines, roleLine('staff'), 'staff 那一行')
      const manager = findLine(lines, roleLine('manager'), 'manager 那一行')
      expect(lines[staff - 1], 'staff 拿到了 ACTION_AUDIT：那一格注释的前提塌了').not.toMatch(/ACTION_AUDIT/)
      expect(lines[manager - 1], 'manager 拿到了 ACTION_AUDIT：那一格注释的前提塌了').not.toMatch(/ACTION_AUDIT/)
      const claim = claimLines(entry.file).find(line => line.includes(entry.cited + ':' + entry.numbers[0]))
      expect(claim, '注释里不再写 staff / manager 的行号：这一格的账要一起改口').toContain(':' + staff)
      expect(claim, 'staff 的真位置漂到 ' + staff + ' 了，注释没跟上').toContain(':' + manager)
    },
  },
  {
    id: '乙-6 replay_path 在后端哪一行',
    file: ROUTER,
    cited: 'app/api/v1/observability.py',
    numbers: [594],
    finders: [{ label: 'replay_path 那一格', pattern: '"replay_path":\\s*f"/api/v1/traces/', contains: ['replay_path'] }],
  },
  {
    id: '乙-7 唯一的系统管理员判定',
    file: ROUTER,
    cited: 'app/common/policy.py',
    numbers: [44],
    finders: [{ label: '_ADMINISTRATOR_ROLES 的定义', pattern: '^_ADMINISTRATOR_ROLES\\s*=\\s*frozenset', contains: ['_ADMINISTRATOR_ROLES', 'admin'] }],
  },
  {
    id: '乙-8 users:manage 只登记在 admin 名下',
    file: ROUTER,
    cited: 'permissions.py',
    numbers: [15],
    finders: [{ label: 'ROLE_PERMISSIONS 的 admin 那一行', pattern: roleLine('admin'), contains: ['ACTION_MANAGE_USERS'] }],
    extra(lines) {
      const rows = ['staff', 'manager', 'admin', 'auditor'].map(role => findLine(lines, roleLine(role), role + ' 那一行'))
      const holders = rows.filter(row => /ACTION_MANAGE_USERS/.test(lines[row - 1]))
      expect(holders, 'users:manage 不止登记在一枚名下：注释那句「只登记在它名下」得改口').toHaveLength(1)
    },
  },
  {
    id: '乙-9 alerts 键的条件性写在后端哪三行',
    file: DASHBOARD,
    cited: 'app/api/v1/dashboard.py',
    numbers: [318, 320],
    finders: [
      { label: 'alerts = _alert_counts(request)', pattern: '^\\s*alerts = _alert_counts\\(request\\)\\s*$', contains: ['_alert_counts'] },
      { label: 'payload["alerts"] = alerts', pattern: '^\\s*payload\\["alerts"\\] = alerts\\s*$', contains: ['payload', 'alerts'] },
    ],
    extra(lines) {
      expect(lines[319 - 1], '中间那行不再是 if 判定：那句「要等一个 if 才补进去」得改口').toMatch(/^\s*if alerts is not None:\s*$/)
    },
    note: 'R416 修的就是这一格：基点上手抄的是 137-139，而那三行今天是 parse-vs-index docstring 的尾部。',
  },
  {
    id: '乙-10 staff 与 auditor 都没有 alerts:manage',
    file: DASHBOARD,
    cited: 'app/common/permissions.py',
    numbers: [13, 16],
    finders: [
      { label: 'ROLE_PERMISSIONS 的 staff 那一行', pattern: roleLine('staff'), notContains: ['ACTION_MANAGE_ALERTS'] },
      { label: 'ROLE_PERMISSIONS 的 auditor 那一行', pattern: roleLine('auditor'), notContains: ['ACTION_MANAGE_ALERTS'] },
    ],
  },
  {
    id: '乙-11 contract-v1 交给 /dashboard/trend 的那一节',
    file: DASHBOARD,
    cited: 'docs/api/contract-v1.md',
    numbers: [2517],
    finders: [{ label: 'R332 · trend 那一节的标题行',
      pattern: '^## The overview page grows a period',
      contains: ['dashboard/trend', 'R332'] }],
    note: 'R416 登记为越界未做，R420 已改口收口：手抄那一枚落在上一节（R310 owner 的 Pins 清单）里，本节标题行由本条 finders 当场推导。',
  },
  {
    id: '乙-12 contract-v1「整键缺席是权限」那一句',
    file: DASHBOARD,
    cited: 'docs/api/contract-v1.md',
    numbers: [2624],
    finders: [{ label: '无告警权就拿不到 alerts 与 alerts_open 那一行',
      pattern: '\\*\\*A caller without alert rights',
      contains: ['the keys are absent', 'alerts_open'] }],
    note: 'R416 登记为越界未做，R420 已改口收口：改口那一枚讲的是 401/403 那条腿；「整键缺席是权限，不是数字」那一句由本条 finders 当场推导。',
  },
  {
    id: '乙-13 contract-v1「序列之和 != 卡片总数」那一句',
    file: DASHBOARD,
    cited: 'docs/api/contract-v1.md',
    numbers: [2608, 2609],
    finders: [
      { label: 'Series totals are not the tile totals 那一行',
        pattern: '\\*\\*Series totals are not the tile totals',
        contains: ['sum(bucket.documents)'] },
      { label: '/summary 数的是全部可见行那一行',
        pattern: 'counts every visible row',
        contains: ['visible row', '/summary'] },
    ],
    note: 'R416 登记为越界未做，R420 已改口收口：改口那一枚讲的是 503／没有部分序列那颗子弹；「序列之和 != 卡片总数」那句话说的事跨两行，所以两端各钉一枚 finder，半句对上不算对上。',
  },
  {
    id: '乙-14 _alert_counts 走的那条告警门',
    file: DASHBOARD,
    cited: 'dashboard.py',
    numbers: [247],
    finders: [{
      label: '_alert_counts 里那一发 _require_alert_management',
      pattern: '_require_alert_management\\(request',
      after: '^def _alert_counts\\(',
      contains: ['alerts_api._require_alert_management(request)'],
    }],
    note: 'R416 登记为越界未做，R420 已改口收口：改口那一枚今天写着 alert_row_scope_sql。注释那句说的是「走那道门」= 调用点，故本条钉 _alert_counts 内部那一发，不钉定义。',
  },
  {
    id: '乙-15 GET /alerts 的那条告警门',
    file: DASHBOARD,
    cited: 'alerts.py',
    numbers: [1085],
    finders: [{
      label: 'GET /alerts 处理函数里那一发 _require_alert_management',
      pattern: '_require_alert_management\\(request',
      after: '^async def list_alerts\\(',
      contains: ['principal = _require_alert_management(request, ALERT_LEDGER_RESOURCE)'],
    }],
    note: 'R416 登记为越界未做，R420 已改口收口：改口那一枚是巡检里的空行。注释那句「都走 _require_alert_management」说的是调用点，本条与乙-14 同一口径钉 GET /alerts 处理函数内那一发——定义是另一枚位置，两边不许各指一处。',
  },
]

/** 现扫：两枚文件里所有 path:line 落点（含 44/:95、15 与 :16、318-320 这三种续写形式）。 */
function scanCitations(file) {
  const hits = []
  const pathRe = /[A-Za-z0-9_./-]+\.(?:py|js|vue|md)(?![A-Za-z0-9_])/g
  claimLines(file).forEach((line, index) => {
    pathRe.lastIndex = 0
    let match = pathRe.exec(line)
    while (match) {
      let at = match.index + match[0].length
      const numbers = []
      for (let guard = 0; guard < 16; guard += 1) {
        const next = /^(?:\s*(?:与|和|、|,|\/)\s*)?:(\d+)(?:-(\d+))?/.exec(line.slice(at))
        if (!next) break
        numbers.push(Number(next[1]))
        if (next[2]) numbers.push(Number(next[2]))
        at += next[0].length
      }
      if (numbers.length) hits.push({ file, line: index + 1, cited: match[0], numbers })
      pathRe.lastIndex = match.index + match[0].length
      match = pathRe.exec(line)
    }
  })
  return hits
}

const keyOf = entry => entry.file + '|' + entry.cited + '|' + entry.numbers.join(',')

/* --------------------------------------------------------------- 剥注释（丁） */

/**
 * 状态机剥注释：认单双引号与模板字面量（含 ${} 嵌套），行注释与块注释各自归位。
 * 这里不许拿正则一刀切 —— `//` 合法地活在字符串里，一刀切会把代码一起剥掉。
 */
function splitComments(text) {
  let code = ''
  let comments = ''
  let i = 0
  const n = text.length
  while (i < n) {
    const ch = text[i]
    const next = text[i + 1]
    if (ch === '/' && next === '/') {
      let j = text.indexOf('\n', i)
      if (j < 0) j = n
      comments += text.slice(i, j)
      i = j
      continue
    }
    if (ch === '/' && next === '*') {
      const j = text.indexOf('*/', i + 2)
      const stop = j < 0 ? n : j + 2
      comments += text.slice(i, stop)
      i = stop
      continue
    }
    if (ch === "'" || ch === '"') {
      let j = i + 1
      while (j < n && text[j] !== ch && text[j] !== '\n') j += text[j] === '\\' ? 2 : 1
      code += text.slice(i, Math.min(j + 1, n))
      i = j + 1
      continue
    }
    if (ch === '`') {
      let j = i + 1
      while (j < n) {
        if (text[j] === '\\') {
          j += 2
          continue
        }
        if (text[j] === '`') break
        if (text[j] === '$' && text[j + 1] === '{') {
          let depth = 1
          j += 2
          while (j < n && depth > 0) {
            if (text[j] === '{') depth += 1
            else if (text[j] === '}') depth -= 1
            j += 1
          }
          continue
        }
        j += 1
      }
      code += text.slice(i, Math.min(j + 1, n))
      i = j + 1
      continue
    }
    code += ch
    i += 1
  }
  return { code, comments }
}

/* ------------------------------------------------------------------------- 钉 */

describe('R416 甲 · 两枚文件里的 path:line 一枚都不许落在账外', () => {
  const scanned = [...scanCitations(ROUTER), ...scanCitations(DASHBOARD)]
  const keys = LEDGER.map(keyOf)

  it('量具不瞎：现扫得到这一族引用，且台账里每一条都还认得到出处', () => {
    expect(scanned.length, '一枚引用都没扫到：文件换了地方，先取证再说').toBeGreaterThanOrEqual(15)
    for (const entry of LEDGER) {
      const hit = scanned.some(item => keyOf(item) === keyOf(entry))
      expect(hit, '台账里那条「' + entry.id + '」在文件里找不到了：引用被删掉了？').toBe(true)
    }
  })

  it('双向对上：账外引用 = 0，重复登记 = 0，未登记真源 = 0', () => {
    expect(keys, '同一枚引用被登记了两次：两把尺量同一格必有一把是摆设').toHaveLength(new Set(keys).size)
    for (const item of scanned) {
      expect(TARGETS[item.cited], '引用名 ' + item.cited + ' 没登记真源，无法对账').toBeTruthy()
      expect(keys, '账外引用：' + item.file + ':' + item.line + ' 引了 ' + item.cited + ':' + item.numbers.join('-')).toContain(keyOf(item))
    }
  })

  it('自述与账对得上：header 那句 debt 枚数必须等于现读 LEDGER 的 debt 条数', () => {
    const own = readFileSync(fileURLToPath(import.meta.url), 'utf8').replace(/\r/g, '')
    const claim = /debt: true 的 (\d+) 枚/.exec(own)
    expect(claim, 'header 里那句 debt 自述被改没了：删 prose 不算把账摘掉').toBeTruthy()
    const debtCount = LEDGER.filter(entry => entry.debt).length
    expect(Number(claim[1]), 'header 自述 debt ' + claim[1] + ' 枚，现读 LEDGER 是 ' + debtCount + ' 枚：改台账就得改这句').toBe(debtCount)
    // R420 收紧成棘轮：越界登记从「先记着以后修」改成「进门先经总控批准」。
    // 要新增一条 debt，先拿到批准再来动这一行；放宽它等于回到 R416 之前的老病 —— 假坐标在册上过夜。
    expect(debtCount, 'LEDGER 里攒了 ' + debtCount + ' 枚 debt 登记：R420 起越界坐标必须先经总控批准才许入账，不再允许先记着以后修').toBe(0)
  })
})

describe('R416 乙 · 每一枚引用当场对目标文件数行，对不上即红', () => {
  for (const entry of LEDGER) {
    it(entry.id + '：' + entry.cited + ':' + entry.numbers.join('-') + '（逐行）', () => {
      const lines = atHead(TARGETS[entry.cited])
      const derived = entry.finders.map(finder => {
        const from = finder.after ? findLine(lines, finder.after, finder.label + ' 的定界') : 0
        return findLine(lines, finder.pattern, finder.label, from)
      })
      if (entry.debt) {
        entry.numbers.forEach((cited, i) => {
          expect(cited === derived[i], '这条 debt 登记已被修好（注释写的 ' + cited + ' 就是当场推导的那一行）：请把登记摘掉').toBe(false)
        })
        return
      }
      entry.numbers.forEach((cited, i) => {
        expect(cited, entry.id + '：注释写 ' + cited + '，现读推导是 ' + derived[i] + ' —— 行号漂了，注释必须跟着改口').toBe(derived[i])
        const text = lines[cited - 1]
        const finder = entry.finders[i]
        for (const token of finder.contains || []) {
          expect(text, '被引那一行没写着 ' + token + '：' + text.trim()).toContain(token)
        }
        for (const token of finder.notContains || []) {
          expect(text, '被引那一行不该出现 ' + token + '：' + text.trim()).not.toContain(token)
        }
      })
      if (entry.extra) entry.extra(lines, entry)
    })
  }
})

const FORBIDDEN = ['还不认识角色', '还没有消费方', '没有消费方', '入口还没接线', '还没接线', '今天还没接', '仍按 navigation 渲染']

describe('R416 丙 · 「壳层认识角色」说的是当前真相，不是一句改口', () => {
  it('禁句族在 router/index.js 里逐字 0 命中', () => {
    const text = workText(ROUTER)
    for (const phrase of FORBIDDEN) {
      expect(text, '这一句又回到了路由表注释里：' + phrase).not.toContain(phrase)
    }
  })

  it('禁句名单本身非空且含判据点名的三枚：摘名单也是一种躲法', () => {
    expect(FORBIDDEN.length).toBeGreaterThanOrEqual(6)
    expect(FORBIDDEN).toContain('还不认识角色')
    expect(FORBIDDEN).toContain('没有消费方')
    expect(FORBIDDEN).toContain('今天还没接')
  })

  it('反向作弊：从测试文件集合现读到一枚真在钉接线的在册用例', () => {
    const self = fileURLToPath(import.meta.url)
    const root = new URL('../../', import.meta.url)
    const files = readdirSync(root, { recursive: true })
      .map(name => String(name))
      .filter(name => name.endsWith('.test.js'))
      .map(name => fileURLToPath(new URL('../../' + name.replace(/\\/g, '/'), import.meta.url)))
      .filter(path => path !== self)
    expect(files.length, '一枚测试文件都没现读到：量具的位置变了，先取证').toBeGreaterThan(50)
    const pins = files.filter(path => {
      const text = readFileSync(path, 'utf8').replace(/\r\n/g, '\n')
      return text.includes('navigationForRole') && text.includes('v-for="item in navigationForRole(userRole)"')
    })
    expect(pins.length, '没有一枚在册用例在钉「壳层按角色派生入口」了：那一格注释不许写成已接线').toBeGreaterThanOrEqual(1)
    const router = workText(ROUTER)
    const named = pins
      .map(path => path.replace(/\\/g, '/').split('/').pop())
      .filter(name => router.includes(name))
    expect(named.length, 'router 注释没点名任何一枚在册用例：改口要连着证据一起交').toBeGreaterThanOrEqual(1)
  })

  it('接线这件事仍然只从一处说：App.vue 认得到 import，侧栏循环恰一枚', () => {
    const app = atHead('frontend/src/App.vue').join('\n')
    expect(app, 'App.vue 不再 import navigationForRole：丙组那一格就成了假话').toMatch(/import \{[^}]*\bnavigationForRole\b[^}]*\} from '\.\/router'/)
    expect(app, '侧栏那枚 v-for 不再吃 navigationForRole(userRole)：接线被摘了').toContain('v-for="item in navigationForRole(userRole)"')
    const loops = app.match(/v-for="item in [^"]*"/g) || []
    expect(loops, '侧栏清单换了画法，量具得先跟着改口').toHaveLength(1)
    expect(loops[0]).toBe('v-for="item in navigationForRole(userRole)"')
    expect(app).not.toContain('nav-admin')
  })
})

describe('R416 丁 · 改注释不改变渲染：剥掉注释后与基点逐字节相等', () => {
  it('剥注释器自己先过一遍：字符串里的 // 不算注释，注释里的引号不算字符串', () => {
    const probe = "const url = 'https://example.com/a'\nconst keep = 1 // 这是注释\n/* 块注释里有「引号」 */\nconst tail = 2"
    const { code, comments } = splitComments(probe)
    expect(code).toContain("'https://example.com/a'")
    expect(code).toContain('const keep = 1')
    expect(code).toContain('const tail = 2')
    expect(code).not.toContain('这是注释')
    expect(code).not.toContain('块注释')
    expect(comments).toContain('这是注释')
    expect(comments).toContain('块注释里有「引号」')
  })

  for (const file of [ROUTER, DASHBOARD]) {
    it(file + ' 的非注释可执行部分与基点 ' + BASE + ' 逐字节相等', () => {
      const now = splitComments(workText(file)).code
      const base = splitComments(atBase(file).join('\n')).code
      expect(now.length, '代码体长度变了：注释单里动了可执行部分').toBe(base.length)
      expect(now).toBe(base)
    })

    it(file + ' 的行数与基点相等：改口不许挪任何人的行号', () => {
      expect(workText(file).split('\n').length, '行数漂了：后端与文档都按行号指着这一族前端文件').toBe(atBase(file).length)
    })
  }
})
