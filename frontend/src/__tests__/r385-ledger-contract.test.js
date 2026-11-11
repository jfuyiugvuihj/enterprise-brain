/**
 * R385 判据① · 缺席台账的对账钉（常驻）：屏上那几句话，是否对得上后端真的会交出来的那一台台账
 *
 * 这一枚文件是本单第一交付物（台账对账表）的常驻版：派工词不许当事实用，所以三张表的每一枚
 * 取值都从后端真源现读——读法照仓里既有姿势（lib/errcodes.test.js 列 A）：
 * `git show <ref>:<path>` 取 git 对象，绝不 readFileSync 工作树（工作树新旧与对账无关）。
 *
 * 三条不许：
 *   · 不许手抄：LEDGER_LEGS 的键、reason 的词表、投影的五枚键，全部由后端文本反推出来再比；
 *   · 不许空扫：每一组都先断言「扫得出东西」（长度 > 0），扫空了这枚钉就白写（r375 同一条尺）；
 *   · 不许 skip：任何一枚读不到真源一律抛错让测试红。
 */
import { execFileSync } from 'node:child_process'
import { describe, expect, it } from 'vitest'
import {
  LEDGER_ANSWERED,
  LEDGER_CAUSES,
  LEDGER_LEGS,
  absenceCopy,
  ledgerCells,
  ledgerReasonCopy,
  ledgerSums,
  silentCells,
} from '../components/NotificationBell.vue'

/** 真源所在分支：与 errcodes.test.js 同一枚 REF，读的是主干而不是本工作树。 */
const REF = 'codex/data-file-catalog'

function show(repoPath) {
  let text
  try {
    text = execFileSync('git', ['show', REF + ':' + repoPath], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
  } catch (cause) {
    throw new Error('读不到真源 ' + REF + ':' + repoPath + '（' + cause.message + '）：判据①的账不许降级。')
  }
  if (!text || !text.trim()) throw new Error(REF + ':' + repoPath + ' 是空的，无法对账。')
  return text.replace(/\r\n/g, '\n')
}

const contractsPy = show('app/notifications/contracts.py')
const sourcesPy = show('app/notifications/sources.py')
const policyPy = show('app/common/policy.py')
const contractMd = show('docs/api/contract-v1.md')

/** 后端三枚 source_type：先取 SOURCE_* 的赋值，再按 NOTIFICATION_SOURCES 那一枚元组展开。 */
function backendLegs() {
  const named = new Map([...contractsPy.matchAll(/^SOURCE_([A-Z_]+) = '([a-z_]+)'$/gm)].map(m => [m[1], m[2]]))
  const tuple = contractsPy.match(/NOTIFICATION_SOURCES:\s*tuple\[str,\s*\.\.\.\]\s*=\s*\(([^)]*)\)/)
  if (!tuple) throw new Error('contracts.py 里找不到 NOTIFICATION_SOURCES 那枚元组')
  const names = tuple[1].split(',').map(item => item.trim()).filter(Boolean)
  return names.map(name => {
    const key = name.replace(/^SOURCE_/, '')
    if (!named.has(key)) throw new Error('元组里的 ' + name + ' 在 contracts.py 找不到赋值')
    return named.get(key)
  })
}

/**
 * SourceBundle.as_projection 交回的那五枚键，逐枚成对读出来（键名 -> 值取自哪一格表达式）。
 * 刻意不假设「键 == 属性名」：candidates 那一格写的是 len(self.items)，它是数出来的条数，
 * 不是 bundle 上躺着的一枚字段——这一条本身就是判据④要说的那个意思。
 */
function projectionFields() {
  const start = sourcesPy.indexOf('def as_projection')
  if (start < 0) throw new Error('sources.py 里找不到 as_projection')
  const body = sourcesPy.slice(start, sourcesPy.indexOf('def ', start + 20))
  return [...body.matchAll(/'([a-z_]+)':\s*([^,\n]+)/g)].map(m => ({ wire: m[1], expr: m[2].trim() }))
}

/** 那本账答上话时 reason_code 取的缺省值（dataclass 那一格）。 */
function answeredWord() {
  const hit = sourcesPy.match(/reason_code:\s*str\s*=\s*'([a-z_]+)'/)
  if (!hit) throw new Error('sources.py 里找不到 reason_code 的缺省值')
  return hit[1]
}

/** 存储拒答那一枚常量的字面值（本文件唯一一处兜底写的字面量）。 */
function storageWord() {
  const hit = sourcesPy.match(/^STORAGE_UNAVAILABLE\s*=\s*'([a-z_]+)'$/m)
  if (!hit) throw new Error('sources.py 里找不到 STORAGE_UNAVAILABLE 常量')
  return hit[1]
}

/** policy.py 里 authorization_decision 每一枚「拒」的 reason_code：403 那一支交回的就是它。 */
function policyDenialWords() {
  return [...new Set([...policyPy.matchAll(/_decision\(\s*False,\s*"([a-z_]+)"/g)].map(m => m[1]))]
}

/** 契约 R299 那一节 JSON 示例里的 sources 段（三格的样例脸）：按花括号配对切，不数行号。 */
function contractExampleLedger() {
  // 全站有两处 "sources" 示例：chat 那一处交回的是【数组】（检索出处清单），收件箱这一处才是按格索引的
  // 台账。所以先认出「紧跟其后就是 approval 那一格」的这一处，再按花括号配对切整块。
  const hits = [...contractMd.matchAll(/"sources":\s*\{/g)]
  const hit = hits.find(item => contractMd.slice(item.index, item.index + 260).includes('"approval"'))
  if (!hit) throw new Error('contract-v1.md 里找不到收件箱那一处 sources 示例段')
  const open = contractMd.indexOf('{', hit.index)
  let depth = 0
  let at = open
  for (; at < contractMd.length; at += 1) {
    if (contractMd[at] === '{') depth += 1
    else if (contractMd[at] === '}' && (depth -= 1) === 0) break
  }
  return JSON.parse(contractMd.slice(open, at + 1))
}

describe('R385 甲 · 判据①：三格账本的人话名与后端那枚元组不多不少', () => {
  const legs = backendLegs()

  it('后端真源扫得出三格（扫空了下面几枚钉就白写）', () => {
    expect(legs.length, JSON.stringify(legs)).toBeGreaterThan(2)
    expect(new Set(legs).size).toBe(legs.length)
  })

  it('LEDGER_LEGS 的键 == 后端 NOTIFICATION_SOURCES，一枚不多一枚不少', () => {
    expect(Object.keys(LEDGER_LEGS).sort(), '格名集合漂了').toEqual([...legs].sort())
  })

  it('每一格都有人话名，且名字里一枚状态名都没有（判据②）', () => {
    for (const leg of legs) {
      const copy = LEDGER_LEGS[leg]
      expect(typeof copy).toBe('string')
      expect(copy.length, leg + ' 没有人话名').toBeGreaterThan(1)
      expect(copy).not.toMatch(/[A-Za-z]/)
    }
  })

  it('未知那一格（第四枚源哪天来了）说的是笼统话，绝不把后端的键直插人话位', () => {
    const copy = absenceCopy({ sourceType: 'wiki', included: false, reasonCode: 'storage_unavailable' })
    expect(copy).not.toContain('wiki')
    expect(copy).not.toContain('storage_unavailable')
    expect(copy.length).toBeGreaterThan(10)
  })
})

describe('R385 乙 · 判据①：投影那五枚键，前端一格都没漏读', () => {
  const fields = projectionFields()

  it('as_projection 扫得出五枚键，每一枚的值都取自 bundle 自己那一格（没有第三处来源）', () => {
    expect(fields.map(item => item.wire).sort(), JSON.stringify(fields)).toEqual(
      ['candidates', 'included', 'reason_code', 'scanned', 'truncated'],
    )
    for (const item of fields) {
      const direct = item.expr === 'self.' + item.wire
      const counted = /^len\(self\.[a-z_]+\)$/.test(item.expr)
      expect(direct || counted, item.wire + ' 的值不是从 bundle 那一格来的：' + item.expr).toBe(true)
    }
  })

  it('契约正文那一句列出的五枚键与代码逐枚相同（文档 ⇄ 代码 ⇄ 前端三方可查）', () => {
    const start = contractMd.indexOf('The five keys of one')
    if (start < 0) throw new Error('contract-v1.md 里找不到「five keys」那一句')
    const sentence = contractMd.slice(start, contractMd.indexOf('\n\n', start))
    const named = [...new Set([...sentence.matchAll(/`([a-z_]+)`/g)].map(m => m[1]))]
      .filter(word => word !== 'sources' && word !== answeredWord())
    expect(named.sort(), sentence).toEqual(fields.map(item => item.wire).sort())
  })

  it('逐枚反证：只改这一枚 wire 字段，前端读出来的那一格必须跟着变（读漏了就红）', () => {
    const base = { included: true, reason_code: 'ok', candidates: 0, scanned: 0, truncated: false }
    const probes = { included: false, reason_code: 'zzz_no_such', candidates: 7, scanned: 9, truncated: true }
    for (const item of fields) {
      expect(Object.prototype.hasOwnProperty.call(probes, item.wire), item.wire + ' 是新生出来的键？').toBe(true)
      const before = ledgerCells({ sources: { approval: { ...base } } })
      const after = ledgerCells({ sources: { approval: { ...base, [item.wire]: probes[item.wire] } } })
      expect(JSON.stringify(after), item.wire + ' 前端没读它：改了它，读出来的那一格一个字都没动')
        .not.toBe(JSON.stringify(before))
    }
  })

  it('答上了的那一格交回空句：included=true 一格字都不许多（判据②两脸）', () => {
    const payload = { sources: { approval: { included: true, reason_code: 'ok', candidates: 0, scanned: 0, truncated: false } } }
    expect(silentCells(ledgerCells(payload))).toEqual([])
    expect(absenceCopy(ledgerCells(payload)[0])).toBe('')
  })

  it('included 只认严格 true：null / 字符串 / 缺失一律算没答（fail-closed，与 lib 的 isExact 同尺）', () => {
    for (const value of [undefined, null, 'true', 1, 0, false]) {
      const cells = ledgerCells({ sources: { approval: { included: value, reason_code: 'ok' } } })
      expect(silentCells(cells).length, JSON.stringify(value)).toBe(1)
    }
  })
})

describe('R385 丙 · 判据③：reason 词表零自造，也不漏后端今天真会交出来的那几枚', () => {
  const causes = Object.keys(LEDGER_CAUSES)
  const real = new Set([storageWord(), ...policyDenialWords()])

  it('两枚真源都扫得出东西（扫空了就白写）', () => {
    expect(real.size, policyPy.slice(0, 0)).toBeGreaterThan(3)
    expect(causes.length).toBeGreaterThan(1)
  })

  it('表里每一枚键都是后端真会写进 reason_code 的那几枚之一：本件不自造状态名', () => {
    for (const word of causes) expect(real.has(word), word + ' 不是后端交得出来的词').toBe(true)
  })

  it('答上话那一枚不在这张表里：ok 说的是「在答」，不该长出缺席句', () => {
    expect(LEDGER_ANSWERED).toBe(answeredWord())
    expect(causes).not.toContain(answeredWord())
  })

  it('每一枚人话都不含状态名、也不含任何拉丁字母（判据②：后端原话不许占人话位）', () => {
    for (const word of causes) {
      const copy = ledgerReasonCopy(word)
      expect(copy).not.toContain(word)
      expect(copy).not.toMatch(/[A-Za-z]/)
      expect(copy).not.toBe(ledgerReasonCopy('zzz_not_a_real_word'))
    }
  })

  it('表里没登记的原因退到笼统句：既不猜为什么，也不把状态名端出去', () => {
    const fallback = ledgerReasonCopy('clearance_insufficient')
    expect(fallback).not.toContain('clearance_insufficient')
    expect(ledgerReasonCopy('anything_new_next_week')).toBe(fallback)
  })

  it('契约示例里那一格没答的 reason，本件必须说得出专句（不许退笼统句）', () => {
    const example = contractExampleLedger()
    expect(Object.keys(example).sort(), '契约示例的三格与后端元组不同：' + JSON.stringify(example))
      .toEqual(backendLegs().sort())
    const omitted = Object.entries(example).filter(([ , cell ]) => cell.included === false)
    expect(omitted.length, JSON.stringify(example)).toBeGreaterThan(0)
    for (const [ , cell ] of omitted) {
      expect(causes, '契约示例点名的 ' + cell.reason_code + ' 没有专句').toContain(cell.reason_code)
    }
  })

  it('告警腿 403 那一支交回的就是 authorization_decision 的 reason：staff 那一枚在册', () => {
    const staff = 'permission_denied'
    expect(real.has(staff), policyPy).toBe(true)
    expect(causes).toContain(staff)
  })
})

describe('R385 丁 · 判据④：台账的算术只算答上了的那几格', () => {
  it('缺席格的 candidates 不进合计，且这一枚数是算出来的不是写死的', () => {
    const payload = {
      sources: {
        approval: { included: false, reason_code: 'storage_unavailable', candidates: 7, scanned: 11, truncated: false },
        alert: { included: true, reason_code: 'ok', candidates: 3, scanned: 5, truncated: false },
        document: { included: true, reason_code: 'ok', candidates: 13, scanned: 17, truncated: false },
      },
    }
    const cells = ledgerCells(payload)
    const answered = cells.filter(cell => cell.included === true)
    const expectCandidates = answered.reduce((sum, cell) => sum + cell.candidates, 0)
    const expectScanned = answered.reduce((sum, cell) => sum + cell.scanned, 0)
    const all = cells.reduce((sum, cell) => sum + cell.candidates, 0)
    const sums = ledgerSums(cells)
    expect(sums.candidates, '合计把缺席格混进来了').toBe(expectCandidates)
    expect(sums.scanned).toBe(expectScanned)
    expect(sums.candidates).not.toBe(all)
    expect([sums.answeredLegs, sums.silentLegs, sums.exact]).toEqual([2, 1, true])
  })

  it('数不出来的格子把 exact 落成 false：下界不许冒充精确数', () => {
    const sums = ledgerSums(ledgerCells({
      sources: { approval: { included: true, reason_code: 'ok', candidates: '3', scanned: 5, truncated: false } },
    }))
    expect(sums.exact).toBe(false)
    expect(sums.candidates).toBe(0)
  })

  it('sources 整格缺失 / 不是对象 = 读不到台账：交回空表，一句话都不许多', () => {
    for (const payload of [undefined, null, {}, { sources: null }, { sources: [] }, { sources: 'no' }]) {
      expect(ledgerCells(payload), JSON.stringify(payload)).toEqual([])
    }
    expect(ledgerSums(ledgerCells({}))).toEqual({ candidates: 0, scanned: 0, answeredLegs: 0, silentLegs: 0, exact: true })
  })

  it('后端少交一格就是少一格：本件不替它补齐三格（补=自造账本）', () => {
    const cells = ledgerCells({ sources: { alert: { included: false, reason_code: 'permission_denied' } } })
    expect(cells.map(cell => cell.sourceType)).toEqual(['alert'])
    expect(absenceCopy(cells[0])).toContain(LEDGER_LEGS.alert)
  })

  it('格子里躺着一枚非对象：跳过它，不拿它编一句话', () => {
    const cells = ledgerCells({ sources: { approval: null, alert: 'x', document: { included: true, reason_code: 'ok' } } })
    expect(cells.length).toBe(1)
    expect(cells[0].sourceType).toBe('document')
  })
})
