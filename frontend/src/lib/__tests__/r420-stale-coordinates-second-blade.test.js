/**
 * R420 · 假坐标第二刀：活坐标必须当场可推，历史坐标必须带锚
 *
 * R416 改口两枚注释、立了在册件，并在账上登记 5 枚「越界未做」的失效坐标。R420 把这 5 枚逐枚改口收口，
 * 又把同族余下的手抄行号一枚枚现读对账。本件钉的是：这些账不许漂回去，也不许靠「删掉引用」躲过去。
 *
 * 两类坐标必须分开钉，混了说出的都是假话：
 *   活坐标 —— 注释指的是**今天**那一行，所以它得能被 finders 在 git HEAD 那份目标文件里当场推导出来；
 *   历史坐标 —— 注释说的是**取证当时**（如缺口清单 §4.2 记下的病灶），它今天往往已不在那一行，于是必须
 *     自带 commit 锚，且锚上那一行真写着锚串。r267-overview-real-status.test.js:4 那种写明锚号的写法，
 *     说的是当时的事实，不是欠账；把锚号删掉才叫造假。本件的判据就把这两类切开。
 *
 * 四组断言，缺一组都不算收口：
 *   甲 四枚同族件（r416 的台账不覆盖它们）里现扫到的每一枚 path:line 都在账上，多一枚少一枚都红 ——
 *      删引用躲检查、手抄一枚新数字，当场撞。frontend/src/lib/dashboard.js 的全覆盖归 r416 甲组管，
 *      本件对它只补一刀（乙组那七条），不另立一张平行尺。
 *   乙 活坐标逐枚对账：注释所写的数字必须等于当场推导，被引那一行本身还得真写着锚串，引用还得在文件里。
 *      其中 dashboard.py 与 alerts.py 那两枚钉的是**调用点**这一口径 —— 注释原话是「都走
 *      _require_alert_management」，定义是另一枚位置，两边各指一处就等于这句注释自己打自己。
 *   丙 历史坐标：注释必须点名锚 commit，锚上那一行必须写着锚串，且 HEAD 上同一枚行号**不许**还写着它 ——
 *      写上了它就是活坐标，得搬去乙组重新对账，不许拿「历史」这块牌把过期账一直挂着。
 *   丁 R416 摘掉的账不许长回来：那本在册件里 debt 登记一枚都不许有，它的 header 自述、甲组那枚棘轮
 *      断言与这五枚改口后的数字必须互相咬住（放宽棘轮等于回到「先记着以后修」）。
 *
 * 真源一律 git show <ref>:<path>（与 r416 同一口径）：工作树可能停在分支点，拿它对账等于永远绿的假绿。
 * 读不到就抛错让测试红，禁止 skip。
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const DASHBOARD = 'frontend/src/lib/dashboard.js'
const SELF_FED = 'frontend/src/components/__tests__/r267-overview-no-self-fed-rows.test.js'
const TECH_NOTE = 'frontend/src/components/__tests__/r267-overview-no-tech-note.test.js'
const ADMIN_ENTRY = 'frontend/src/router/__tests__/r316-admin-entry.test.js'
const USERS_CONTRACT = 'frontend/src/lib/__tests__/r316-users-contract.test.js'
const LEDGER = 'frontend/src/lib/__tests__/r416-comments-cite-live-coordinates.test.js'

/** 甲组只管 r416 台账没覆盖的这四枚文件。 */
const COVERED = [SELF_FED, TECH_NOTE, ADMIN_ENTRY, USERS_CONTRACT]

/** 注释里的写法 -> 仓内真源。没登记在这张表里的引用名，甲组当场红。 */
const TARGETS = {
  'app/api/v1/auth.py': 'app/api/v1/auth.py',
  'app/api/v1/dashboard.py': 'app/api/v1/dashboard.py',
  'app/api/v1/alerts.py': 'app/api/v1/alerts.py',
  'app/common/authorization.py': 'app/common/authorization.py',
  'app/common/permissions.py': 'app/common/permissions.py',
  'app/common/policy.py': 'app/common/policy.py',
  'App.vue': 'frontend/src/App.vue',
  'DashboardPanel.vue': 'frontend/src/components/DashboardPanel.vue',
  'alerts.py': 'app/api/v1/alerts.py',
  'dashboard.py': 'app/api/v1/dashboard.py',
  'docs/api/contract-v1.md': 'docs/api/contract-v1.md',
  'lib/errcodes.test.js': 'frontend/src/lib/errcodes.test.js',
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
const workText = repoPath => readFileSync(new URL('../../../../' + repoPath, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const claimLines = repoPath => workText(repoPath).split('\n')

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

/** 两枚端点各钉一枚 finder，半句对上不算对上。 */
const ALERTS_KEY_SPAN = [
  {
    label: 'alerts = _alert_counts(request)',
    pattern: '^\\s*alerts = _alert_counts\\(request\\)\\s*$',
    contains: ['_alert_counts'],
  },
  {
    label: 'payload["alerts"] = alerts',
    pattern: '^\\s*payload\\["alerts"\\] = alerts\\s*$',
    contains: ['payload', 'alerts'],
  },
]

function ifAlertsIsNotNone(lines, entry) {
  expect(lines[319 - 1], entry.id + '：中间那行不再是 if 判定，那句「没返回 None 才写这一键」得改口').toMatch(/^\s*if alerts is not None:\s*$/)
}

/**
 * 注释说「都走 _require_alert_management」= 调用点。指到定义就是这句注释自己打自己。
 * 定义只活在 alerts.py（dashboard.py 那一侧是跨模块调用），所以只在认得到定义的那枚文件里比。
 */
function callSiteNotDefinition(lines, entry) {
  const cited = entry.numbers[0]
  const text = lines[cited - 1]
  expect(text, entry.id + '：被引那一行不再是调用点，注释那句「都走」就成了假话').toMatch(/_require_alert_management\(request/)
  expect(/^def\s+_require_alert_management\(/.test(text), entry.id + '：被引那一行成了定义行：注释说的是「走那道门」，不是「门长在哪一行」').toBe(false)
  const definition = lines.findIndex(line => /^def\s+_require_alert_management\(/.test(line)) + 1
  if (definition) expect(definition, entry.id + '：定义与调用点成了同一枚行号，两边各指一处 = 口径混了').not.toBe(cited)
}

/* ------------------------------------------------------------------- 活坐标账 */

const LIVE = [
  {
    id: 'L-1 无告警读权时整个键被省掉（r267 自备 rows 那枚注释）',
    file: SELF_FED,
    cited: 'app/api/v1/dashboard.py',
    numbers: [318, 320],
    finders: ALERTS_KEY_SPAN,
    extra: ifAlertsIsNotNone,
  },
  {
    id: 'L-2 能不能读只在服务端那道 users:manage 闸上（r316 入口注释）',
    file: ADMIN_ENTRY,
    cited: 'app/api/v1/auth.py',
    numbers: [106],
    finders: [{
      label: 'list_users 里那一发 authorize_request(..., ACTION_MANAGE_USERS)',
      pattern: 'authorize_request\\(request, ACTION_MANAGE_USERS',
      after: 'async def list_users\\(',
      contains: ['ACTION_MANAGE_USERS'],
    }],
  },
  {
    id: 'L-3 那道闸的判定读的两行（r316 入口注释）',
    file: ADMIN_ENTRY,
    cited: 'app/common/policy.py',
    numbers: [44, 95],
    finders: [
      { label: '_ADMINISTRATOR_ROLES 的定义', pattern: '^_ADMINISTRATOR_ROLES\\s*=\\s*frozenset', contains: ['_ADMINISTRATOR_ROLES', 'admin'] },
      { label: '_is_administrator 的返回', pattern: 'return ACTION_MANAGE_USERS in permissions', contains: ['ACTION_MANAGE_USERS', '_ADMINISTRATOR_ROLES'] },
    ],
    extra(lines, entry) {
      expect(countMatches(lines, '^_ADMINISTRATOR_ROLES\\s*='), entry.id + '：后端长出第二枚定义，那一格的账要一起改口').toBe(1)
    },
  },
  {
    id: 'L-4 users:manage 只有 admin 名下有（r316 入口注释）',
    file: ADMIN_ENTRY,
    cited: 'app/common/permissions.py',
    numbers: [15],
    finders: [{ label: 'ROLE_PERMISSIONS 的 admin 那一行', pattern: roleLine('admin'), contains: ['ACTION_MANAGE_USERS'] }],
    extra(lines, entry) {
      const holders = ['staff', 'manager', 'admin', 'auditor']
        .map(role => findLine(lines, roleLine(role), role + ' 那一行'))
        .filter(row => /ACTION_MANAGE_USERS/.test(lines[row - 1]))
      expect(holders, entry.id + '：users:manage 不止登记在一枚名下，那句「只有 admin」得改口').toHaveLength(1)
    },
  },
  {
    id: 'L-5 侧栏接线那两行的真位置（r316 入口注释）',
    file: ADMIN_ENTRY,
    cited: 'App.vue',
    numbers: [4, 472],
    finders: [
      { label: '壳层 import navigationForRole 那一行', pattern: "^import \\{ DEFAULT_SCREEN, FEED_SCREEN, cachedScreens, navigationForRole", contains: ['navigationForRole'] },
      { label: '侧栏那枚 v-for', pattern: 'v-for="item in navigationForRole\\(userRole\\)"', contains: ['navigationForRole(userRole)'] },
    ],
  },
  {
    id: 'L-6 派生入口吃的那枚角色态在哪一行（r316 入口注释）',
    file: ADMIN_ENTRY,
    cited: 'App.vue',
    numbers: [27],
    finders: [{ label: 'userRole 的声明', pattern: '^const userRole = shallowRef\\(', contains: ['userRole'] }],
  },
  {
    id: 'L-7 「不 readFileSync 工作树」那条教训的两端（r316 名册注释）',
    file: USERS_CONTRACT,
    cited: 'lib/errcodes.test.js',
    numbers: [27, 29],
    finders: [
      { label: '那一段的起行', pattern: '^ \\* 为什么不许 readFileSync 工作树', contains: ['readFileSync', '工作树'] },
      { label: '那一段的止行', pattern: '读到什么与工作树新旧无关', contains: ['新旧无关'] },
    ],
  },
  {
    id: 'L-8 后端把 reason code 括进正文的那一发 raise（r316 名册注释）',
    file: USERS_CONTRACT,
    cited: 'app/common/authorization.py',
    numbers: [23],
    finders: [{ label: 'raise PermissionError(f"权限不足: ...")', pattern: 'raise PermissionError\\(f"权限不足', contains: ['decision.reason_code'] }],
  },
  /* ---- R420 从 R416 账上摘下来的那五枚，外加它们同一条注释里的两枚邻居 ---- */
  {
    id: 'L-9 alerts 键的条件性写在后端哪三行（dashboard.js）',
    file: DASHBOARD,
    cited: 'app/api/v1/dashboard.py',
    numbers: [318, 320],
    finders: ALERTS_KEY_SPAN,
    extra: ifAlertsIsNotNone,
  },
  {
    id: 'L-10 _alert_counts 走的那道告警门＝调用点（dashboard.js · R420 改口）',
    file: DASHBOARD,
    cited: 'dashboard.py',
    numbers: [247],
    finders: [{
      label: '_alert_counts 里那一发 _require_alert_management',
      pattern: '_require_alert_management\\(request',
      after: '^def _alert_counts\\(',
      contains: ['alerts_api._require_alert_management(request)'],
    }],
    extra: callSiteNotDefinition,
  },
  {
    id: 'L-11 GET /alerts 走的那道告警门＝调用点（dashboard.js · R420 改口）',
    file: DASHBOARD,
    cited: 'alerts.py',
    numbers: [1085],
    finders: [{
      label: 'list_alerts 里那一发 _require_alert_management',
      pattern: '_require_alert_management\\(request',
      after: '^async def list_alerts\\(',
      contains: ['ALERT_LEDGER_RESOURCE'],
    }],
    extra: callSiteNotDefinition,
  },
  {
    id: 'L-12 staff 与 auditor 都没有 alerts:manage（dashboard.js）',
    file: DASHBOARD,
    cited: 'app/common/permissions.py',
    numbers: [13, 16],
    finders: [
      { label: 'ROLE_PERMISSIONS 的 staff 那一行', pattern: roleLine('staff'), notContains: ['ACTION_MANAGE_ALERTS'] },
      { label: 'ROLE_PERMISSIONS 的 auditor 那一行', pattern: roleLine('auditor'), notContains: ['ACTION_MANAGE_ALERTS'] },
    ],
  },
  {
    id: 'L-13 contract-v1 交给 /dashboard/trend 的那一节（dashboard.js · R420 改口）',
    file: DASHBOARD,
    cited: 'docs/api/contract-v1.md',
    numbers: [2517],
    finders: [{
      label: 'R332 · trend 那一节的标题行',
      pattern: '^## The overview page grows a period',
      contains: ['dashboard/trend', 'R332'],
    }],
  },
  {
    id: 'L-14 整键缺席是权限，不是数字（dashboard.js · R420 改口）',
    file: DASHBOARD,
    cited: 'docs/api/contract-v1.md',
    numbers: [2624],
    finders: [{
      label: '无告警权就拿不到 alerts 与 alerts_open 那一行',
      pattern: '\\*\\*A caller without alert rights',
      contains: ['the keys are absent', 'alerts_open'],
    }],
  },
  {
    id: 'L-15 序列之和 != 卡片总数（dashboard.js · R420 改口，跨两行各钉一枚）',
    file: DASHBOARD,
    cited: 'docs/api/contract-v1.md',
    numbers: [2608, 2609],
    finders: [
      { label: 'Series totals are not the tile totals 那一行', pattern: '\\*\\*Series totals are not the tile totals', contains: ['sum(bucket.documents)'] },
      { label: '/summary 数的是全部可见行那一行', pattern: 'counts every visible row', contains: ['visible row', '/summary'] },
    ],
  },
]

/* ----------------------------------------------------------------- 历史坐标账 */

const HIST = [
  {
    id: 'H-1 缺口清单 §4.2 记下的那句上屏技术注解（r267 反证钉的出处）',
    file: TECH_NOTE,
    cited: 'DashboardPanel.vue',
    numbers: [175],
    sha: '1142c27',
    tokens: ['class="demo-note"', 'src/devFixtures/dashboard-demo.js', 'GET /api/v1/dashboard/summary'],
  },
]

const keyOf = entry => entry.file + '|' + entry.cited + '|' + entry.numbers.join(',')

/** 现扫：一枚文件里所有 path:line 落点（含 44/:95、15 与 :16、318-320 这三种续写形式）。 */
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

function claimText(entry) {
  const head = entry.cited + ':' + entry.numbers[0]
  const line = claimLines(entry.file).find(text => text.includes(head))
  expect(line, entry.id + '：注释里那句 ' + head + ' 不见了 —— 删引用不算把账摘掉，把数字手抄回来更不算').toBeTruthy()
  return line
}

/* --------------------------------------------------------------------------- 钉 */

describe('R420 甲 · 那四枚同族件里的 path:line 一枚都不许落在账外', () => {
  const scanned = COVERED.flatMap(scanCitations)
  const keys = [...LIVE, ...HIST].map(keyOf)

  it('量具不瞎：现扫得到这一族引用，且账上每一条都还认得到出处', () => {
    expect(scanned.length, '一枚引用都没扫到：文件换了地方，先取证再说').toBeGreaterThanOrEqual(9)
    for (const entry of [...LIVE, ...HIST]) {
      const hit = scanCitations(entry.file).some(item => keyOf(item) === keyOf(entry))
      expect(hit, '账上那条「' + entry.id + '」在 ' + entry.file + ' 里找不到了：删掉引用不算把账摘掉').toBe(true)
    }
  })

  it('双向对上：账外引用 = 0，重复登记 = 0，未登记真源 = 0', () => {
    expect(keys, '同一枚引用登记了两次：两把尺量同一格必有一把是摆设').toHaveLength(new Set(keys).size)
    for (const item of scanned) {
      expect(TARGETS[item.cited], '引用名 ' + item.cited + ' 没登记真源，无法对账').toBeTruthy()
      expect(keys, '账外引用：' + item.file + ':' + item.line + ' 引了 ' + item.cited + ':' + item.numbers.join('-')).toContain(keyOf(item))
    }
  })
})

describe('R420 乙 · 活坐标：注释写的数字必须等于当场推导，被引那一行还得真写着锚串', () => {
  it('dashboard.js 那句「都走 _require_alert_management」的两枚门坐标同一口径：都是调用点', () => {
    const pair = LIVE.filter(entry => /_require_alert_management/.test(JSON.stringify(entry.finders)))
    expect(pair.map(entry => entry.cited).sort().join('+'), '两枚门坐标少了一枚：这一条对账就成了摆设').toBe('alerts.py+dashboard.py')
    for (const entry of pair) {
      const text = atHead(TARGETS[entry.cited])[entry.numbers[0] - 1]
      expect(text, entry.id + '：两枚坐标里有一枚不再写着那发调用：各指一处，注释那句就是假话').toContain('_require_alert_management(request')
      expect(/^def\s/.test(text), entry.id + '：一枚指调用点、另一枚指定义：那句话容不下两种读法').toBe(false)
    }
  })

  for (const entry of LIVE) {
    it(entry.id + '：' + entry.cited + ':' + entry.numbers.join('-'), () => {
      claimText(entry)
      const lines = atHead(TARGETS[entry.cited])
      const derived = entry.finders.map(finder => {
        const from = finder.after ? findLine(lines, finder.after, finder.label + ' 的定界') : 0
        return findLine(lines, finder.pattern, finder.label, from)
      })
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

describe('R420 丙 · 历史坐标：带锚才许说当时的事，锚上必须可验', () => {
  for (const entry of HIST) {
    it(entry.id + '：' + entry.cited + ':' + entry.numbers.join('-') + '（锚 ' + entry.sha + '）', () => {
      const line = claimText(entry)
      expect(line, entry.id + '：注释写着 ' + entry.cited + ':' + entry.numbers[0] + ' 却没点锚号 —— 无锚的过期坐标就是假坐标，要么带锚，要么按今天的真行号改口').toContain(entry.sha)
      const at = showAt(entry.sha, TARGETS[entry.cited])
      const cited = entry.numbers[0]
      const then = at[cited - 1] || ''
      for (const token of entry.tokens) {
        expect(then, '锚 ' + entry.sha + ' 的第 ' + cited + ' 行没写着 ' + token + '：这枚历史坐标本身就是抄来的').toContain(token)
      }
      const now = atHead(TARGETS[entry.cited])[cited - 1] || ''
      const stillLive = entry.tokens.every(token => now.includes(token))
      expect(stillLive, 'HEAD 的第 ' + cited + ' 行现在也写着那句锚串：它已是活坐标，搬去乙组按当场推导对账').toBe(false)
    })
  }
})

describe('R420 丁 · R416 摘掉的账不许长回来', () => {
  const text = workText(LEDGER)
  const debtFlags = text.split('\n').filter(line => /^\s{4}debt: true,$/.test(line))

  it('在册件里一枚 debt 都不许有，且它的 header 自述与棘轮读数互相咬住', () => {
    const self = /debt: true 的 (\d+) 枚/.exec(text)
    expect(self, 'header 那句 debt 自述被改没了：删 prose 不算把账摘掉').toBeTruthy()
    expect(Number(self[1]), 'header 自述 ' + self[1] + ' 枚，现读台账是 ' + debtFlags.length + ' 枚：改台账就得改这句').toBe(debtFlags.length)
    expect(debtFlags.length, 'R420 起越界登记要先经总控批准才许入账：不许再走「先记着以后修」').toBe(0)
    expect(/expect\(debtCount[\s\S]{0,240}?\)\.toBeGreaterThan\(0\)/.test(text), '那枚棘轮被改回 toBeGreaterThan(0) 了：这是放松判据，不是修账').toBe(false)
    expect(/expect\(debtCount[\s\S]{0,240}?\)\.toBe\(0\)/.test(text), '那枚棘轮不在了：debt 归零之后它必须钉死为 0').toBe(true)
  })

  it('五枚改口后的数字必须仍在那本台账上（抄回旧数字 = 当场红）', () => {
    for (const [id, value] of [['乙-11', 'numbers: [2517]'], ['乙-12', 'numbers: [2624]'], ['乙-13', 'numbers: [2608, 2609]'], ['乙-14', 'numbers: [247]'], ['乙-15', 'numbers: [1085]']]) {
      expect(text, id + ' 的数字不是一手现读的 ' + value + '：账与注释又各指一处了').toContain(value)
    }
    for (const stale of ['2509', '2616', '2600', '[90]', '[925]']) {
      expect(text, '旧的那枚 ' + stale + ' 又回到台账里了').not.toMatch(new RegExp('numbers: \\[' + stale.replace(/[\[\]]/g, '') + '\\]'))
    }
  })
})

