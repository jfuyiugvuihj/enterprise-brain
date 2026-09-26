/**
 * R271 · 告警闭环的前后端契约（判据②：「后端几列」与状态机一律现读后端，抄来的数字不算证据）
 *
 * 对账对象是本工作树里的 app/api/v1/alerts.py 与 migrations/*.sql：并树之后工作树就是当前后端，
 * 比它才有意义。这里刻意不钉任何分支名——那条分支哪天被删，这件前端测试会在 main 上无故长红，
 * 而假红与假绿一样是废掉判据。读不到文件、解析不出列集或路由一律当场抛红，禁止 skip。
 *
 * 本件回答三件事：
 *   ① alerts 一行真发几列 —— 自建库 DDL、生产 migrations、无库内存行三条路必须数出同一个集合，
 *      而且必须等于 lib/alerts.js 那本账（ALERT_BACKEND_COLUMNS）。
 *   ② 每一枚处置列是否真的被 mapAlertRow 取到 —— 靠「源码里必须有 source.<列名> 这一读」判，
 *      不靠注释里写了什么。read 是唯一允许不取的一枚，理由单点钉住。
 *   ③ 三枚动作的端点、请求体与状态机是否与后端逐字同集 —— 少一枚、多一枚、拼错一枚都红。
 */
import { readdirSync, readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

import {
  ALERT_ACTIONS,
  ALERT_ACTION_LABELS,
  ALERT_ACTION_RULES,
  ALERT_BACKEND_COLUMNS,
  ALERT_COLUMN_NOT_SHOWN,
  ALERT_DISPOSAL_COLUMNS,
  ALERT_STATUSES,
  alertActionPath,
  alertActionsFor,
  alertStatusKey,
  assignRequestBody,
  disposeAlert,
  mapAlertRow,
} from '../../lib/alerts'

const BACKEND_ALERTS = 'app/api/v1/alerts.py'

/**
 * 仓库根：__tests__ -> components -> src -> frontend -> 根。走 import.meta.url 而不是 `git rev-parse`：
 * vitest 的工作目录是 frontend/，相对路径会指错地方，而调 git 会把这件测试绑在「这棵树得是个仓库」上。
 */
const REPO_ROOT = new URL('../../../../', import.meta.url)

const libSource = name => readFileSync(new URL('../../lib/' + name, import.meta.url), 'utf8').replace(/\r\n/g, '\n')

function readRepo(path) {
  let text
  try {
    text = readFileSync(new URL(path, REPO_ROOT), 'utf8')
  } catch (cause) {
    throw new Error('读不到后端真源 ' + path + '（' + cause.message + '）。列数对账不许降级。')
  }
  if (!text || !text.trim()) throw new Error(path + ' 是空文件，无法对账。')
  // 本仓 core.autocrlf=true：工作树里的 app/** 是 CRLF，而后端解析式（含 \n\n 这类跨行终止符）
  // 按 LF 写。不归一就会把终止符整个错过，把后面几百行当成类体吃进来 —— 那不是对账，是假红。
  return text.replace(/\r\n/g, '\n')
}

function migrationFiles() {
  let names
  try {
    names = readdirSync(new URL('migrations/', REPO_ROOT))
  } catch (cause) {
    throw new Error('读不到 migrations/ 目录：' + cause.message)
  }
  const sql = names.filter(name => /\.sql$/.test(name)).sort()
  if (sql.length < 14) throw new Error('迁移只数到 ' + sql.length + ' 枚 .sql：目录形状变了，对账口径要重定，不许静默少算。')
  return sql
}

/** DDL 里的列名：每行第一个词，约束行（CONSTRAINT/PRIMARY/UNIQUE/CHECK/FOREIGN）不算列。 */
function ddlColumns(body, where) {
  const cols = body
    .split(/\r?\n/)
    .map(line => line.split('--')[0].trim())
    .filter(Boolean)
    .filter(line => !/^(CONSTRAINT|PRIMARY|UNIQUE|CHECK|FOREIGN)\b/i.test(line))
    .map(line => line.split(/[\s,]+/)[0])
    .filter(name => /^[a-z_][a-z0-9_]*$/.test(name))
  if (!cols.length) throw new Error('解析不到 ' + where + ' 的任何列名：DDL 形状变了，要同步改这里的解析，不许让它退化成空对账。')
  return cols
}

function backendAlerts() {
  return readRepo(BACKEND_ALERTS)
}

/** ① 自建库那条腿：_ensure() 里的 CREATE TABLE IF NOT EXISTS alerts。 */
function devDdlColumns() {
  const hit = /CREATE TABLE IF NOT EXISTS alerts \(([\s\S]*?)\n\s*\)\s*"""|CREATE TABLE IF NOT EXISTS alerts \(([\s\S]*?)\n\s*\)\s*\n/.exec(backendAlerts())
  if (!hit) throw new Error('在 ' + BACKEND_ALERTS + ' 里找不到自建库的 alerts 建表语句：那条腿的形状变了。')
  return ddlColumns(hit[1] || hit[2], 'app/api/v1/alerts.py 的自建库 DDL')
}

/** ② 生产那条腿：0003 建表 + 后续迁移给 alerts 幂等补的列。 */
function productionColumns() {
  const files = migrationFiles()
  const base = files
    .map(name => ({ name, text: readRepo('migrations/' + name) }))
    .filter(item => /CREATE TABLE IF NOT EXISTS alerts\b/.test(item.text))
  if (base.length !== 1) throw new Error('建 alerts 表的迁移应当只有一枚，实测 ' + base.length + ' 枚：对账口径要重定。')
  const cols = ddlColumns(/CREATE TABLE IF NOT EXISTS alerts \(([\s\S]*?)\n\);/.exec(base[0].text)[1], base[0].name)
  for (const item of files) {
    const add = readRepo('migrations/' + item)
    for (const hit of add.matchAll(/ALTER TABLE IF EXISTS alerts\s+ADD COLUMN IF NOT EXISTS (\w+)/g)) cols.push(hit[1])
  }
  return cols
}

/** ③ 无库那条腿：evaluate_all 写进内存表的字面键 ＋ alert_ledger_row 永远补齐的处置列。 */
/** alert_ledger_row 永远补齐的那组处置列（后端 ALERT_DISPOSAL_DEFAULTS 的键，现读，零手抄）。 */
function backendDisposalDefaults() {
  const hit = /ALERT_DISPOSAL_DEFAULTS: dict\[str, str\] = \{([\s\S]*?)\n\}/.exec(backendAlerts())
  if (!hit) throw new Error('找不到 ALERT_DISPOSAL_DEFAULTS：alert_ledger_row 补的那组列读不到了。')
  return [...hit[1].matchAll(/"([a-z_]+)":/g)].map(name => name[1])
}

function memoryColumns() {
  const text = backendAlerts()
  const hit = /_MEM_ALERTS\.append\(\s*\{([\s\S]*?)\}\s*\)/.exec(text)
  if (!hit) throw new Error('解析不到 _MEM_ALERTS.append 的那一枚字典：无库那条腿的形状变了。')
  const literal = [...hit[1].matchAll(/"([a-z_]+)":/g)].map(name => name[1])
  if (literal.length < 5) throw new Error('内存行的字面键解析不出（只拿到 ' + literal.length + ' 枚）：这里也禁止退化成空对账。')
  if (new Set(literal).size !== literal.length) throw new Error('内存行的字面键里出现了重复：解析切歪了。')
  return literal.concat(backendDisposalDefaults())
}

/** 后端的三枚状态名 -> 值，以及 ALERT_STATUSES / ALERT_DISPOSAL_RULES / 写列表。 */
function backendVocabulary() {
  const text = backendAlerts()
  const names = {}
  for (const hit of text.matchAll(/ALERT_STATUS_([A-Z]+) = "([^"]+)"/g)) names[hit[1]] = hit[2]
  const statuses = /ALERT_STATUSES: tuple\[str, \.\.\.\] = \(([\s\S]*?)\n\)/.exec(text)
  if (!statuses) throw new Error('读不到后端 ALERT_STATUSES。')
  const statusList = [...statuses[1].matchAll(/ALERT_STATUS_([A-Z]+)/g)].map(hit => names[hit[1]])
  const rulesBlock = /ALERT_DISPOSAL_RULES: dict[\s\S]*?= \{([\s\S]*?)\n\}/.exec(text)
  if (!rulesBlock) throw new Error('读不到后端 ALERT_DISPOSAL_RULES。')
  const rules = {}
  for (const hit of rulesBlock[1].matchAll(/ALERT_ACTION_([A-Z]+): \(\s*frozenset\(\{([^}]*)\}\),\s*(ALERT_STATUS_[A-Z]+|None)/g)) {
    rules[hit[1].toLowerCase()] = {
      from: [...hit[2].matchAll(/ALERT_STATUS_([A-Z]+)/g)].map(name => names[name[1]]),
      to: hit[3] === 'None' ? '' : names[hit[3].replace('ALERT_STATUS_', '')],
    }
  }
  const writesBlock = /ALERT_DISPOSAL_WRITE_COLUMNS: dict[\s\S]*?= \{([\s\S]*?)\n\}/.exec(text)
  if (!writesBlock) throw new Error('读不到后端 ALERT_DISPOSAL_WRITE_COLUMNS。')
  const writes = {}
  for (const hit of writesBlock[1].matchAll(/ALERT_ACTION_([A-Z]+): \(([^)]*)\)/g)) {
    writes[hit[1].toLowerCase()] = [...hit[2].matchAll(/"([a-z_]+)"/g)].map(name => name[1])
  }
  const actions = /ALERT_ACTIONS: tuple\[str, \.\.\.\] = \(([^)]*)\)/.exec(text)
  if (!actions) throw new Error('读不到后端 ALERT_ACTIONS。')
  const actionList = [...actions[1].matchAll(/ALERT_ACTION_([A-Z]+)/g)].map(hit => hit[1].toLowerCase())
  return { names, statuses: statusList, rules, writes, actions: actionList }
}

function backendRoutes() {
  const routes = []
  for (const line of backendAlerts().split(/\r?\n/)) {
    const hit = /^@router\.(get|post|put|patch|delete)\("([^"]+)"\)/.exec(line.trim())
    if (hit) routes.push(hit[1].toUpperCase() + ' ' + hit[2])
  }
  if (!routes.length) throw new Error('解析不到任何 @router 装饰器：后端形状变了，不许让它退化成空对账。')
  return routes
}

/** AlertAssignCreate 的字段全集：转派那一发能带的键只有这些，多一枚就是自造契约。 */
function backendAssignFields() {
  const hit = /class AlertAssignCreate\(BaseModel\):([\s\S]*?)(\n\n|\nclass |\n@)/.exec(backendAlerts())
  if (!hit) throw new Error('读不到 AlertAssignCreate 的字段：转派的请求体形状变了。')
  return [...hit[1].matchAll(/^\s{4}(\w+)\s*:/gm)].map(name => name[1])
}

describe('R271 判据② · 「后端一行几列」现读现数，三条路必须同集', () => {
  it('自建库 DDL / 生产迁移 / 无库内存行 数出的列集完全相同', () => {
    const dev = devDdlColumns()
    const prod = productionColumns()
    const mem = memoryColumns()
    expect(new Set(dev)).toEqual(new Set(prod))
    expect(new Set(prod)).toEqual(new Set(mem))
    expect(new Set(dev).size).toBe(dev.length)
    expect(new Set(mem).size).toBe(mem.length)
  })

  it('实测列数 == 前端账本 ALERT_BACKEND_COLUMNS，且那一枚登记值 13 确实是少数了', () => {
    expect(new Set(ALERT_BACKEND_COLUMNS)).toEqual(new Set(devDdlColumns()))
    expect(ALERT_BACKEND_COLUMNS.length).toBe(devDdlColumns().length)
    // 缺口清单 G05 登记的是 13 列：少的正是这两枚（department 与 assigned_by），本件把它钉成实测值。
    expect(ALERT_BACKEND_COLUMNS).toContain('department')
    expect(ALERT_BACKEND_COLUMNS).toContain('assigned_by')
    expect(ALERT_BACKEND_COLUMNS.length).not.toBe(13)
    expect(ALERT_BACKEND_COLUMNS.length).toBe(15)
  })

  it('注释里写的那个列数必须等于数组真长度（话与账不许各说一套）', () => {
    const code = libSource('alerts.js')
    expect(code).toContain('后端一行实测 **' + ALERT_BACKEND_COLUMNS.length + ' 列**')
    expect(code).not.toMatch(/后端六列/)
  })

  it('除 read 之外每一枚后端列都被 mapAlertRow 真读：源码里没有 source.<列名> 就是漏了一列', () => {
    const code = libSource('alerts.js')
    const read = ALERT_BACKEND_COLUMNS.filter(column => column !== ALERT_COLUMN_NOT_SHOWN)
    for (const column of read) {
      expect(code, '视图模型没有读后端这一列：' + column).toContain('source.' + column)
    }
    expect(code).not.toMatch(/source\.read\b/)
    expect(ALERT_COLUMN_NOT_SHOWN).toBe('read')
  })

  it('处置七列恰好等于视图模型 ledger 的组成，一列不许多、一列不许少', () => {
    // 后端 ALERT_DISPOSAL_DEFAULTS 减去 status 就是那七枚「人与时间」列：现读，不手抄。
    expect(ALERT_DISPOSAL_COLUMNS).toEqual(backendDisposalDefaults().filter(column => column !== 'status'))
    expect(ALERT_DISPOSAL_COLUMNS).toEqual(ALERT_BACKEND_COLUMNS.filter(column => ALERT_DISPOSAL_COLUMNS.indexOf(column) >= 0))
    const vocabulary = backendVocabulary()
    for (const action of vocabulary.actions) {
      const written = vocabulary.writes[action].filter(column => column !== 'status')
      for (const column of written) {
        expect(ALERT_DISPOSAL_COLUMNS, '动作 ' + action + ' 会写这一列，可屏上没有它：' + column).toContain(column)
      }
    }
    // 反向那一半：视图模型里的每一枚处置列，都确实是后端会写或会补的某一枚，不是前端自己造的字段。
    for (const column of ALERT_DISPOSAL_COLUMNS) {
      expect(backendDisposalDefaults(), '前端当处置列上屏的这一枚后端根本不认：' + column).toContain(column)
    }
  })

  it('处置七列逐枚上屏：给一行全处置完的账，ledger 必须把人与时间原样带出来', () => {
    const row = mapAlertRow({
      id: 7,
      rule_id: 3,
      message: '现金余额 3200 小于阈值 50000',
      ai_analysis: '',
      department: '市场部',
      read: false,
      status: 'acknowledged',
      acknowledged_by: 'linan',
      acknowledged_at: '2026-09-26T14:03:07+08:00',
      closed_by: '',
      closed_at: '',
      assignee: 'wangqiang',
      assigned_by: 'linan',
      assigned_at: '2026-09-26T14:05:12+08:00',
      created_at: '2026-09-26T09:40:00+08:00',
    })
    expect(row.status).toBe('acknowledged')
    expect(row.handled).toBe(true)
    expect(row.ledger).toEqual([
      { key: 'ack', label: '确认', who: 'linan', to: '', at: '2026-09-26 14:03', recorded: true },
      { key: 'close', label: '关闭', who: '未记录', to: '', at: '未记录', recorded: false },
      { key: 'assign', label: '指派', who: 'linan', to: 'wangqiang', at: '2026-09-26 14:05', recorded: true },
    ])
  })
})

describe('R271 判据① · 三枚动作的端点、请求体与状态机与后端同集', () => {
  const vocabulary = backendVocabulary()

  it('ack / close / assign 三条 POST 路由在后端真存在，前端拼出来的路径一一对得上', () => {
    const routes = new Set(backendRoutes())
    for (const action of ALERT_ACTIONS) {
      const declared = 'POST /alerts/{alert_id}/' + action
      expect(routes, '后端没有这条路由：' + declared).toContain(declared)
      const built = alertActionPath(41, action)
      expect(built, '路径拼不出来：' + action).toBe('/alerts/41/' + action)
      expect(routes.has(built), '前端拼出的路径在后端找不到同动词路由：' + built).toBe(false)
      expect(backendRoutes().some(item => item === declared)).toBe(true)
    }
    expect(vocabulary.actions).toEqual(ALERT_ACTIONS)
    expect(ALERT_ACTION_LABELS).toEqual({ ack: '确认', close: '关闭', assign: '指派' })
  })

  it('转派的请求体恰好是 AlertAssignCreate 的字段全集，多一枚就是自造契约', () => {
    expect(backendAssignFields()).toEqual(['assignee'])
    expect(assignRequestBody('  wangqiang  ')).toEqual({ assignee: 'wangqiang' })
    expect(Object.keys(assignRequestBody('lin'))).toEqual(backendAssignFields())
  })

  it('状态词表与每一枚动作允许出发的格子，与后端逐字同集', () => {
    expect(ALERT_STATUSES).toEqual(vocabulary.statuses)
    for (const action of ALERT_ACTIONS) {
      expect(ALERT_ACTION_RULES[action], '动作 ' + action + ' 的形状与后端不一致').toEqual(vocabulary.rules[action])
    }
    expect(alertActionsFor('open')).toEqual(['ack', 'close', 'assign'])
    expect(alertActionsFor('acknowledged')).toEqual(['close', 'assign'])
    expect(alertActionsFor('closed')).toEqual([])
  })

  it('缺列与词表外的状态词：一个按后端口径读成 open，一个认不下并且一个动作都不点亮', () => {
    expect(alertStatusKey(undefined)).toBe('open')
    expect(alertStatusKey('')).toBe('open')
    expect(alertStatusKey('open')).toBe('open')
    expect(alertStatusKey('Open')).toBe('')
    expect(alertStatusKey(' open')).toBe('')
    expect(alertActionsFor('snoozed')).toEqual([])
    expect(mapAlertRow({ id: 9, status: 'snoozed' }).statusKnown).toBe(false)
  })
})

describe('R271 disposeAlert · 三种回执与三枚动作的 POST 形状', () => {
  const alerted = overrides => Object.assign({
    id: 7,
    rule_id: 3,
    message: '现金余额 3200 小于阈值 50000',
    ai_analysis: '',
    department: '市场部',
    read: false,
    status: 'acknowledged',
    acknowledged_by: 'linan',
    acknowledged_at: '2026-09-26T14:03:07+08:00',
    closed_by: '',
    closed_at: '',
    assignee: '',
    assigned_by: '',
    assigned_at: '',
    created_at: '2026-09-26T09:40:00+08:00',
  }, overrides || {})

  it('确认与关闭不发请求体；转派只发一枚目标用户名，路径精确到编号', async () => {
    const seen = []
    const client = { post: async (path, body) => { seen.push([path, body]); return { data: { alert: alerted() } } } }
    expect((await disposeAlert(7, 'ack', '', client)).receipt).toBe('done')
    expect((await disposeAlert(7, 'close', '', client)).receipt).toBe('done')
    expect((await disposeAlert(7, 'assign', ' wangqiang ', client)).receipt).toBe('done')
    expect(seen).toEqual([
      ['/alerts/7/ack', undefined],
      ['/alerts/7/close', undefined],
      ['/alerts/7/assign', { assignee: 'wangqiang' }],
    ])
  })

  it('done 的回执交回的是**处置之后**的那一行（后端读回来的形状，不是我以为写成什么样）', async () => {
    const client = { post: async () => ({ data: { alert: alerted() } }) }
    const verdict = await disposeAlert(7, 'ack', '', client)
    expect(verdict.receipt).toBe('done')
    expect(verdict.row.status).toBe('acknowledged')
    expect(verdict.row.ledger[0].who).toBe('linan')
    expect(verdict.row.ledger[0].at).toBe('2026-09-26 14:03')
  })

  it('编号或动作不对＝一个请求都不发；回执里没有那一行＝不装作处置成功', async () => {
    let fired = 0
    const never = { post: async () => { fired += 1; return { data: { alert: alerted() } } } }
    expect((await disposeAlert('7; DROP', 'ack', '', never)).receipt).toBe('invalid')
    expect((await disposeAlert('', 'close', '', never)).receipt).toBe('invalid')
    expect((await disposeAlert(7, 'reopen', '', never)).receipt).toBe('invalid')
    expect((await disposeAlert(null, 'assign', 'lin', never)).receipt).toBe('invalid')
    expect(fired).toBe(0)
    const empty = { post: async () => ({ data: {} }) }
    expect((await disposeAlert(7, 'ack', '', empty)).receipt).toBe('unreadable')
    const list = { post: async () => ({ data: { alert: [] } }) }
    expect((await disposeAlert(7, 'ack', '', list)).receipt).toBe('unreadable')
    const nothing = { post: async () => ({}) }
    expect((await disposeAlert(7, 'ack', '', nothing)).receipt).toBe('unreadable')
  })
})
