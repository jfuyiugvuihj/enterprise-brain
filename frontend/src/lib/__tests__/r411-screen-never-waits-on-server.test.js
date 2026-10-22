/**
 * R411 · 这一枚钉买的是「屏不许替服务端说假话」
 *
 * 后端从 R284 起把「其中已解析多少篇」无条件写进 GET /dashboard/summary 的 payload，而
 * lib/dashboard.js 还留着四句 R284 之前的旧口径，其中一句就印在屏上：文档卡那串口径提示由
 * DashboardPanel.vue 的 :title 原样渲染（:349），指针停在卡上就读得到一次对服务端的等待。
 * 这一格是 R341 交回时自己登记、明确写「越界未做」的第一格（并树提交 acc092e 末段：它被
 * 现存夹具按旧形状钉住，越界），R411 收的就是那笔欠账。
 *
 * 判据两头都要守住，所以钉子分四组，缺一组都不算收口：
 *   甲 那四句旧口径在 lib/dashboard.js 里逐字 0 命中 —— 它们只许活在 git 历史里。
 *   乙 屏上五档文本（<em> 副文案 + :title 口径提示）里读不到任何一次等待，逐档给凭据。
 *   丙 🔴 反向作弊必须红：「未记录」这张脸还在、还是它自己那张脸，没被并进「还没有文档」，
 *      也没靠摘掉 documentsReady 那一读来消灭假话。「读不出来」与「确实没有」不共用一张空态。
 *   丁 前端对服务端的那句说法当场对账真源，走 git show HEAD：与 lib/errcodes.test.js:27-29
 *      和 r368-retryable-source.test.js:26-27 同一条教训 —— 工作树里的 app/** 可能停在分支
 *      点，拿它对账等于永远绿的假绿。读不到就抛错让测试红，禁止 skip。
 *
 * 手法沿用 r341-trend-card.test.js：源码扫描用 readFileSync，后端口径用 git 对象；五档读数
 * 全走真解析链（聚合回执 -> parseSummaryPayload -> summaryTiles -> documentsTileView）。
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import {
  COUNT_PLACEHOLDER,
  DOCUMENTS_ALL_READY_NOTE,
  DOCUMENTS_EMPTY_NOTE,
  DOCUMENTS_MISMATCH_NOTE,
  DOCUMENTS_UNRECORDED_NOTE,
  documentsTileView,
  parseSummaryPayload,
  summaryTiles,
} from '../dashboard'

const source = name => readFileSync(new URL(name, import.meta.url), 'utf8').replace(/\r?\n/g, '\n')
const libSource = () => source('../dashboard.js')

/** 判据①点名的四句旧口径：逐字取自基点 9e817e1 的 frontend/src/lib/dashboard.js。 */
const LIES = [
  '（线上今天就是这一张脸）',
  '\u{1F6AB} 后端补上这一数之前',
  '等后端把已解析篇数一起回传',
  '后端今天还没回这一数',
]

/**
 * 屏上文本里不许出现的一次「等待」。逐枚点名，命中即红。
 *
 * 这张名单只管渲染产物，不管注释：lib/dashboard.js 里合法地存在「旧稿曾把自己写成线上今天的
 * 样子」这类回顾性叙述，把它们算成假话就等于不许记录改过什么。管注释的是甲组那四枚逐字串。
 */
const PROMISE_TOKENS = [
  '等后端',
  '后端补',
  '后端还没',
  '后端今天',
  '还没回',
  '还没带',
  '未回传',
  '补上这一数',
  '补出这一数',
  '自己换说法',
  '总有一天',
  '将来才会',
  '以后就会',
]

/**
 * 五档走法（六行：「未记录」那张脸有两个各自独立的触发者，谁也不许顶掉谁）。
 * metrics 是 parseSummaryPayload 折出来的形状，不是响应体 —— 这一张表钉的是视图层那个五岔路口。
 */
const FACES = [
  { name: '一篇都没有', metrics: { documents: 0, documentsReady: 0 }, note: DOCUMENTS_EMPTY_NOTE },
  {
    name: '文档总数读不出来',
    metrics: { documents: null, documentsReady: 5 },
    note: DOCUMENTS_UNRECORDED_NOTE,
  },
  {
    name: '已解析篇数读不出来',
    metrics: { documents: 5, documentsReady: null },
    note: DOCUMENTS_UNRECORDED_NOTE,
  },
  { name: '两数相等', metrics: { documents: 5, documentsReady: 5 }, note: DOCUMENTS_ALL_READY_NOTE },
  { name: '还有没解析完的', metrics: { documents: 5, documentsReady: 3 }, note: '2 篇还没解析完' },
  {
    name: '已解析比总数还大',
    metrics: { documents: 5, documentsReady: 7 },
    note: DOCUMENTS_MISMATCH_NOTE,
  },
]

/** 后端口径读 git 对象，绝不读工作树（头注丁组那两条教训）。读不到就红，不许 skip。 */
function backendSummary() {
  let text
  try {
    text = execFileSync('git', ['show', 'HEAD:app/api/v1/dashboard.py'],
      { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
  } catch (cause) {
    throw new Error(`读不到真源 HEAD:app/api/v1/dashboard.py（git show 失败：${cause.message}）。对账不许降级成 skip。`)
  }
  if (!String(text).trim()) throw new Error('git show HEAD:app/api/v1/dashboard.py 返回空内容，无法对账。')
  return String(text).replace(/\r?\n/g, '\n')
}

/** Python 注释换行续行折成一行：后端那句原文横跨两行，逐行拼不出一条完整句子。 */
const flatten = text => text.replace(/\n\s*#+\s*/g, ' ')

/** 取 /summary 里那段 payload 字面量：从 payload: dict = { 起，到与之配平的 } 止（含注释）。 */
function payloadLiteral(text) {
  const at = text.indexOf('payload: dict = {')
  if (at < 0) throw new Error('读不到 payload: dict = { 这一句，后端那段聚合改形状了。')
  let depth = 0
  for (let i = text.indexOf('{', at); i < text.length; i += 1) {
    if (text[i] === '{') depth += 1
    else if (text[i] === '}') {
      depth -= 1
      if (depth === 0) return text.slice(at, i + 1)
    }
  }
  throw new Error('payload 字面量的花括号不配平，无法判断哪一枚键是无条件的。')
}

describe('R411 甲 · 那四句旧口径在 lib/dashboard.js 里逐字 0 命中', () => {
  it('名单本身是四枚：与判据①点名的格数对齐，不许靠删名单蒙过这一组', () => {
    expect(LIES).toHaveLength(4)
  })

  it('逐枚点名，谁抄回前端源码谁红', () => {
    const text = libSource()
    for (const lie of LIES) {
      expect(text, `这一句又回到了前端源码里：${lie}`).not.toContain(lie)
    }
  })

  it('后端那句原文仍然在位（这一格无条件）：它是甲组成立的前提，不是被删掉的那一方', () => {
    expect(flatten(backendSummary())).toContain('this key is never conditional')
  })
})

describe('R411 乙 · 屏上五档文本里读不到任何一次对服务端的等待', () => {
  it('这一张表是六行五档：行数变了就得连带改判据，不许偷偷并档', () => {
    expect(FACES).toHaveLength(6)
  })

  for (const face of FACES) {
    it(`${face.name}：读到的正是点名那一档，且副文案与口径提示都不含等待字样`, () => {
      const view = documentsTileView(face.metrics)
      const onScreen = `${view.delta} ${view.hint}`
      expect(view.delta).toBe(face.note)
      expect(view.hint.length, '口径提示不许缩成一句没有内容的空话').toBeGreaterThan(10)
      for (const token of PROMISE_TOKENS) {
        expect(onScreen, `${face.name} 这一档的屏上文本出现了「${token}」：${onScreen}`).not.toContain(token)
      }
    })
  }

  it('五档都不把后端字段名画上屏（人话闸门，沿用 R274 那一条口径）', () => {
    for (const face of FACES) {
      const view = documentsTileView(face.metrics)
      expect(`${view.delta} ${view.hint}`).not.toMatch(/parse_status|index_status|documents_ready/)
    }
  })
})

describe('R411 丙 · 反向作弊也咬：这张脸必须在，且必须是它自己那张', () => {
  it('五张脸的副文案两两不等：不许并成一句万能空态', () => {
    const notes = [
      DOCUMENTS_EMPTY_NOTE,
      DOCUMENTS_UNRECORDED_NOTE,
      DOCUMENTS_ALL_READY_NOTE,
      '2 篇还没解析完',
      DOCUMENTS_MISMATCH_NOTE,
    ]
    expect(notes).toHaveLength(5)
    expect(new Set(notes).size).toBe(5)
  })

  it('「读不出来」既不是「确实没有」，也不是那枚横杠：三张脸各自独立', () => {
    expect(DOCUMENTS_UNRECORDED_NOTE).not.toBe(DOCUMENTS_EMPTY_NOTE)
    expect(DOCUMENTS_UNRECORDED_NOTE).not.toBe(COUNT_PLACEHOLDER)
    expect(DOCUMENTS_UNRECORDED_NOTE).not.toContain('还没有')
    const unreadable = documentsTileView({ documents: 5, documentsReady: null })
    const empty = documentsTileView({ documents: 0, documentsReady: 0 })
    expect(unreadable.delta).toBe(DOCUMENTS_UNRECORDED_NOTE)
    expect(empty.delta).toBe(DOCUMENTS_EMPTY_NOTE)
    expect(unreadable.hint).not.toBe(empty.hint)
  })

  it('走真解析链：一份缺列的回执仍然读成「未记录」，摘掉这张脸立刻红', () => {
    const body = { generated_for: 'boss', pending_approvals: 3, documents: 5, datasets: 12 }
    const metrics = parseSummaryPayload(body)
    expect(metrics, '这份回执其余三枚数都读得出来，不该整块判失败').toBeTruthy()
    expect(metrics.documentsReady).toBe(null)
    const tile = summaryTiles(metrics).find(item => item.id === 'documents')
    expect(tile.delta).toBe(DOCUMENTS_UNRECORDED_NOTE)
    expect(tile.delta).not.toBe(DOCUMENTS_EMPTY_NOTE)
  })

  it('源码里那一读必须在：不许靠删掉 documentsReady 来消灭假话', () => {
    expect(libSource()).toContain('documentsReady: countOf(payload.documents_ready),')
  })

  it('摘除「未记录」那一支的 return 也要红：这一支仍然在源码里挂着那张脸', () => {
    expect(libSource()).toContain('delta: DOCUMENTS_UNRECORDED_NOTE, hint: DOCUMENTS_UNRECORDED_HINT')
  })
})

describe('R411 丁 · 前端对服务端的那句说法当场对账真源', () => {
  it('"documents_ready": documents_ready 在 payload 字面量里无条件出现', () => {
    const block = payloadLiteral(backendSummary())
    expect(block).toContain('"documents_ready": documents_ready,')
  })

  it('同一张聚合里 alerts 那一键不在字面量内，是 if 之后才补的：两枚键的条件性确有长短', () => {
    const text = backendSummary()
    const block = payloadLiteral(text)
    expect(block).not.toContain('"alerts"')
    expect(text).toContain('payload["alerts"] = alerts')
  })

  it('线上常态形状：带这一数的回执画的是「有数」那几张脸，不是「未记录」', () => {
    const body = {
      generated_for: 'boss',
      pending_approvals: 3,
      documents: 5,
      datasets: 12,
      alerts: { total: 1, unread: 1 },
    }
    for (const [ready, expected] of [[5, DOCUMENTS_ALL_READY_NOTE], [3, '2 篇还没解析完']]) {
      const metrics = parseSummaryPayload({ ...body, documents_ready: ready })
      const tile = summaryTiles(metrics).find(item => item.id === 'documents')
      expect(tile.delta, `documents_ready=${ready} 应当画上「${expected}」`).toBe(expected)
      expect(tile.delta).not.toBe(DOCUMENTS_UNRECORDED_NOTE)
    }
  })

  it('一篇都没有那一档排在读数之前：0 篇文档不借「未记录」装作读到了什么', () => {
    const metrics = parseSummaryPayload({ generated_for: 'boss', pending_approvals: 0, documents: 0, datasets: 0 })
    expect(summaryTiles(metrics).find(item => item.id === 'documents').delta).toBe(DOCUMENTS_EMPTY_NOTE)
  })

})
describe('R411 戊 · 一刀扫尽整枚 lib：任何一枚画上屏的字都不许有一次等待', () => {
  /**
   * 取这个模块里所有可能上屏的字面量：先剥注释（源码里的回顾性叙述合法存在，见 PROMISE_TOKENS
   * 头上那段），再取引号与反引号里的内容，最后只留下带汉字的——没汉字的不是给人读的句子。
   */
  const screenStrings = text => {
    const body = text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^[ \t]*\/\/.*$/gm, '')
    const quoted = [...body.matchAll(/'((?:[^'\\\n]|\\.)*)'/g)].map(m => m[1])
    const braced = [...body.matchAll(/`((?:[^`\\]|\\.)*)`/g)].map(m => m[1])
    return [...quoted, ...braced].filter(s => /\p{Script=Han}/u.test(s))
  }

  it('量具自己要过秤：扫出来必须是一批真句子，不许哪天把扫描器改空了还报绿', () => {
    expect(screenStrings(libSource()).length).toBeGreaterThanOrEqual(60)
  })

  it('整枚 lib 的屏上文本 0 命中：这一刀不只砍文档卡那五档', () => {
    for (const value of screenStrings(libSource())) {
      for (const token of PROMISE_TOKENS) {
        expect(value, `屏上文本出现了「${token}」：${value}`).not.toContain(token)
      }
    }
  })
  // 已知的一处例外在注释里，不是屏上：:347「这一屏就没有任何理由再替服务端说「还没回传」」，
  // 那是 R332/R341 立下的禁令本身。戊组只扫渲染文本，正是为了让那种句子留着。
})
