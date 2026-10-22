/**
 * R375 · 写路径那颗「重试」按钮改吃字典那一把尺（判据①③④⑤）
 *
 * 病灶（改前取证，本单基点 796540e，行号为改前实测）：R368 只收了读路径那一枚出口
 * （alerts.js:137 failureRetryable + frontend/src/lib/alerts.js:158 readFailureView 的 error 档），同一族的两枚**写点**仍硬编：
 *   alerts.js:584        disposalFailureView 最后一条 return —— 面板 InsightPanel.vue:559-569 拿它画
 *                        UiErrorState，retry-text=「再试这一件」，所以这一枚是真的会多出一颗按钮；
 *   notifications.js:289 writeFailureView —— NotificationBell.vue:181/198 在「标为已读 / 全部标已读」
 *                        的 catch 里喂它（该字段今天只落进 frontend/src/components/NotificationBell.vue:288-290 那句纯文本 note，屏上没画按钮，
 *                        账记在交回里）。
 * 后果：同一类错误读的时候说 false、写的时候说 true —— R368 判据③要消灭的那种分裂。
 *
 * 本件只管三件事，且一件都不越界：
 *  ① 两枚写点的 retryable 一律来自 alerts.js 那一枚 failureRetryable（屏上不许比字典宽，
 *    字典没说话的格子兜底 true，与读路径逐字同形）；
 *  ② 除这两枚 return 之外，两张文件里每一张既有脸、每一格句子一字未动（对基线做 sha 对平）；
 *  ③ 凡改判成 false 的格子，屏幕上那句人话仍然自洽（R368 丙那条全称律）。
 *
 * 手法照仓里规矩：期望值全部从 lib/errcodes.js 现读，本件一枚码名、一格取值、一句文案都不抄；
 * 反证不靠注释，靠三把现改现跑的刀（己组）。
 */
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { ERROR_CODES, LEGACY_ALIASES, PROSE_ALIASES, dictionaryAdjudicatesRetry, errorText, isRetryable } from '../errcodes'
import {
  DISPOSAL_FAILURE_TITLES,
  INVALID_ID_FAILURE,
  SHAPE_FAILURE_DESCRIPTION,
  disposalFailureView,
  failureRetryable,
  readFailureView,
  shapeFailureView,
} from '../alerts'
import { shapeFailureViewOf, writeFailureView } from '../notifications'

const REF = '796540e'
const READ_ARGS = { deniedTitle: '这一格读不到', failedTitle: '这一格坏了' }
/** 「等一会儿它自己会变好」那一族承诺：与 r208/r368 同一枚字面，判 false 的格子不许说它。 */
const RETRY_LATER = /稍后重试|稍后再试|请稍等|稍等|过一会儿|一会儿再|待会儿|回头再/

/** axios 真形状之一：状态码 + 信封/裸串 detail。 */
function httpError(status, detail) {
  return {
    isAxiosError: true,
    response: { status, data: { detail } },
    message: 'Request failed with status code ' + status,
  }
}

/** 三张表里所有「后端一点名字典就判得出 retryable」的 token：名单现读，本件一枚都不抄。 */
const NAMED_TOKENS = [
  ...Object.keys(ERROR_CODES),
  ...Object.keys(LEGACY_ALIASES),
  ...Object.keys(PROSE_ALIASES),
]

/** 字典没为这一枚说话的那一族形状：兜底必须与读路径同形（true），不是收窄成 false。 */
const SILENT_SHAPES = [
  ['500 无错误体', { response: { status: 500 } }],
  ['500 纯文本错误体', { response: { status: 500, data: 'Internal Server Error' }, message: 'x' }],
  ['502 无错误体', { response: { status: 502 } }],
  ['422 校验数组（后端没点名单枚码）', httpError(422, [{ type: 'missing', loc: ['body', 'assignee'], msg: 'Field required' }])],
  ['后端新加的未知码', httpError(500, 'alert_scope_required')],
  ['断网（只有 request）', { request: {}, message: 'Network Error' }],
  ['断网（只有 code）', { code: 'ERR_NETWORK', message: 'Network Error' }],
  ['本地形状不合（InboxShapeError）', Object.assign(new Error('未读清单还没读完就不给行了，这不能当成全部已读。'), { shapeFailure: true })],
]

describe('R375 甲 · 判据①：一把尺，两枚写点都从它上面过', () => {
  it('failureRetryable 已导出，且那一行判据与基线是同一行字', () => {
    expect(typeof failureRetryable).toBe('function')
    expect(rulerLine(workText('alerts.js'))).toBe('  return dictionaryAdjudicatesRetry(err) ? isRetryable(err) : true')
    expect(rulerLine(workText('alerts.js'))).toBe(rulerLine(baselineText('alerts.js')))
    expect(failureRetryable(httpError(503, 'storage_unavailable'))).toBe(false)
    expect(failureRetryable({ request: {}, message: 'Network Error' })).toBe(true)
  })

  it('两枚写点的 return 里都不再有硬编 true：只剩被 判据③ 保护的两张结构脸', () => {
    const owners = ['alerts.js', 'notifications.js'].flatMap(name => {
      const text = workText(name)
      return [...text.matchAll(/retryable: true/g)].map(match => ({ name, fn: enclosingFunction(text, match.index) }))
    })
    expect(owners.map(item => item.name + ':' + item.fn).sort()).toEqual(['alerts.js:shapeFailureView', 'notifications.js:shapeFailureViewOf'])
  })

  it('notifications.js 不另造第二把尺：它从 alerts.js 引那一枚，且没新引字典的判定出口', () => {
    const text = workText('notifications.js')
    expect(/import \{[^}]*failureRetryable[^}]*\} from '.\/alerts'/.test(text)).toBe(true)
    expect(codeOnlyText(text).includes('dictionaryAdjudicatesRetry(')).toBe(false)
    expect(codeOnlyText(text).includes('isRetryable(')).toBe(false)
  })

  it('两枚写点各只有一处走尺，且取数层没有第二本错误码账', () => {
    expect(countIn(disposalBody(), 'failureRetryable(err)')).toBe(1)
    expect(countIn(writeBody(), 'failureRetryable(err)')).toBe(1)
    const names = [...new Set([...Object.keys(ERROR_CODES), ...Object.keys(LEGACY_ALIASES)])]
    for (const file of ['alerts.js', 'notifications.js']) {
      const before = names.filter(name => codeOnlyText(baselineText(file)).includes(name)).sort()
      const after = names.filter(name => codeOnlyText(workText(file)).includes(name)).sort()
      expect(after, file + ' 代码体里的码名集合与本单基点不同（那就是另起了一本账）：' + JSON.stringify(after)).toEqual(before)
    }
  })
})

describe('R375 乙 · 判据①：在册的每一枚，屏上取值 == 字典取值', () => {
  it('在册清单扫得出东西（扫空了这枚钉就白写）', () => {
    expect(NAMED_TOKENS.length).toBeGreaterThan(40)
  })

  it('writeFailureView 跟着字典走：逐枚对，一格都不许自判', () => {
    const gaps = []
    for (const token of NAMED_TOKENS) {
      const err = httpError(503, token)
      expect(dictionaryAdjudicatesRetry(err), token + ' 不该落在兜底那一族').toBe(true)
      if (writeFailureView(err).retryable !== isRetryable(err)) gaps.push(token)
    }
    expect(gaps, '屏上与字典不一致的格子：' + gaps.join(', ')).toEqual([])
  })

  it('disposalFailureView 落在 error 那一档的每一枚跟着字典走（其余档由戊组钉住未动）', () => {
    const gaps = []
    let scanned = 0
    for (const token of NAMED_TOKENS) {
      const err = httpError(503, token)
      if (disposalFailureView(err, 'ack').face !== 'error') continue
      scanned += 1
      if (disposalFailureView(err, 'ack').retryable !== isRetryable(err)) gaps.push(token)
    }
    expect(scanned, '一枚都没扫到：这一组白写').toBeGreaterThan(10)
    expect(gaps, 'error 档与字典不一致的格子：' + gaps.join(', ')).toEqual([])
  })

  it('同一枚错误对象：读路径 / 处置 / 标记已读三处给的 flag 全等（写读同口径）', () => {
    const splits = []
    for (const status of [400, 401, 403, 404, 409, 500, 503]) {
      for (const token of NAMED_TOKENS) {
        const err = httpError(status, token)
        if (!dictionaryAdjudicatesRetry(err)) continue
        const read = readFailureView(err, READ_ARGS).retryable
        const disposal = disposalFailureView(err, 'ack').retryable
        const write = writeFailureView(err).retryable
        if (read === disposal && read === write) continue
        splits.push(status + '/' + token + ' read=' + read + ' disposal=' + disposal + ' write=' + write)
      }
    }
    expect(splits, '同一类错误读与写给了两种口径：\n' + splits.join('\n')).toEqual([])
  })
})

describe('R375 丙 · 判据①反面：字典没说话的那一族仍给重试，兜底与读路径同形', () => {
  it('八枚哑形状 × 三处出口全等且全为 true（这枚修复不是一律 false）', () => {
    for (const [name, err] of SILENT_SHAPES) {
      expect(dictionaryAdjudicatesRetry(err), name + ' 应当是字典没说话那一族').toBe(false)
      const read = readFailureView(err, READ_ARGS).retryable
      const disposal = disposalFailureView(err, 'ack').retryable
      const write = writeFailureView(err).retryable
      expect([read, disposal, write], name + ' ⇒ 兜底不许收窄成 false').toEqual([true, true, true])
    }
  })

  it('被 判据③ 保护的两张结构脸一字未动，且它们本就与尺同值（没有码 ⇒ true）', () => {
    expect(shapeFailureView(READ_ARGS.failedTitle)).toEqual({
      face: 'error', title: READ_ARGS.failedTitle, description: SHAPE_FAILURE_DESCRIPTION, codeLabel: '', retryable: true,
    })
    expect(shapeFailureViewOf()).toEqual({
      face: 'error', title: '通知没能读出来', description: SHAPE_FAILURE_DESCRIPTION, codeLabel: '', retryable: true,
    })
    expect(shapeFailureViewOf().retryable).toBe(failureRetryable(SILENT_SHAPES[5][1]))
  })

  it('转派被拒那一档仍然单独成脸：本单没把它并进 error 档', () => {
    const rejected = disposalFailureView(httpError(422, [{ type: 'missing', loc: ['body', 'assignee'], msg: 'Field required' }]), 'assign')
    expect(rejected.face).toBe('rejected')
    expect(rejected.retryable).toBe(false)
    expect(rejected.reload).toBe(false)
  })
})

describe('R375 丁 · 判据④：凡改判 false 的格子，屏上那句话仍然自洽', () => {
  it('两枚写点上判 false 的每一格，句子都不承诺「等一会儿再试」', () => {
    const offenders = []
    for (const token of NAMED_TOKENS) {
      for (const status of [400, 401, 403, 404, 409, 500, 503]) {
        const err = httpError(status, token)
        const views = [['write', writeFailureView(err)], ['disposal', disposalFailureView(err, 'ack')], ['disposalAssign', disposalFailureView(err, 'assign')]]
        for (const [where, view] of views) {
          if (!view.retryable && RETRY_LATER.test(view.description)) offenders.push(token + '@' + status + ' ' + where + ' ⇒ ' + view.description)
        }
      }
    }
    expect(offenders, '判 false 却在邀请再试一次：\n' + offenders.join('\n')).toEqual([])
  })

  it('点名改判格：句子逐字等于字典句，flag 逐字等于字典 flag', () => {
    const cells = [
      ['storage_unavailable', 503, false],
      ['internal_error', 500, false],
      ['validation_error', 422, false],
      ['authentication_required', 401, false],
      ['rate_limited', 429, true],
      ['authorization_unavailable', 403, true],
    ]
    for (const [token, status, flag] of cells) {
      const err = httpError(status, token)
      expect(isRetryable(err), token + ' 的字典取值变了，本件的账要重取').toBe(flag)
      expect(writeFailureView(err).retryable, token + ' 写路径没跟字典').toBe(flag)
      expect(writeFailureView(err).description, token + ' 的人话位不是字典那句').toBe(errorText(token))
      expect(disposalFailureView(err, 'ack').retryable, token + ' 处置路径没跟字典').toBe(flag)
    }
  })

  it('改判只动 flag，没动那几格的 title / codeLabel / reload 与六张脸的分工', () => {
    const storage = disposalFailureView(httpError(503, 'storage_unavailable'), 'ack')
    expect(storage.title).toBe(DISPOSAL_FAILURE_TITLES.error)
    expect(storage.face).toBe('error')
    expect(storage.reload).toBe(false)
    expect(storage.codeLabel).toBe('')
    const write = writeFailureView(httpError(503, 'storage_unavailable'))
    expect(write.title).toBe('这次动作没能改成')
    expect(write.codeLabel).toBe('')
  })
})

describe('R375 戊 · 判据③：既有脸一字未动（对基线 sha 对平）', () => {
  it('两枚写函数除了 flag 的来源，其余与基线逐字相等', () => {
    const pairs = [['alerts.js', 'disposalFailureView', disposalBody()], ['notifications.js', 'writeFailureView', writeBody()]]
    for (const [file, name, body] of pairs) {
      const base = bodyOf(baselineText(file), name)
      expect(countIn(base, 'retryable: true'), name + ' 基线里那一枚硬编 true 的位置数变了').toBe(1)
      expect(base.replace(/retryable: true/g, 'retryable: ⟲')).toBe(body.replace(/retryable: failureRetryable\(err\)/g, 'retryable: ⟲'))
    }
  })

  it('除这两枚之外的每一枚导出与基线同 sha：本单没有顺手摸别的脸', () => {
    const touched = new Set(['disposalFailureView', 'writeFailureView'])
    const drifted = []
    for (const file of ['alerts.js', 'notifications.js']) {
      const base = baselineText(file)
      const work = workText(file)
      for (const name of declNames(base)) {
        if (touched.has(name)) continue
        if (sha(unexport(blockOf(base, name))) !== sha(unexport(blockOf(work, name)))) drifted.push(file + ' ' + name)
      }
    }
    expect(drifted, '与基线不逐字相等的未授权函数/常量：' + drifted.join(', ')).toEqual([])
  })

  it('那枚尺子本身只多了 export 一个词：函数体与基线逐字相等', () => {
    const block = blockOf(workText('alerts.js'), 'failureRetryable')
    expect(block).toBe('export ' + blockOf(baselineText('alerts.js'), 'failureRetryable'))
  })

  it('导出面只多出一枚 failureRetryable，一枚都没少', () => {
    for (const file of ['alerts.js', 'notifications.js']) {
      const before = new Set(exportedNames(baselineText(file)))
      const after = new Set(exportedNames(workText(file)))
      const added = [...after].filter(name => !before.has(name))
      const removed = [...before].filter(name => !after.has(name))
      expect(removed, file + ' 有导出名消失了').toEqual([])
      expect(added, file + ' 多出的导出名不止 failureRetryable').toEqual(file === 'alerts.js' ? ['failureRetryable'] : [])
    }
  })

  it('那六张处置脸与 401/403 那几张读脸的具体取值仍然逐字对得上', () => {
    const cases = [
      ['authentication_required', 401, 'unauthorized', false],
      ['permission_denied', 403, 'denied', false],
      ['resource_not_found', 404, 'notFound', false],
      ['conflict', 409, 'conflict', false],
      ['validation_error', 400, 'rejected', false],
    ]
    for (const [token, status, face, flag] of cases) {
      const view = disposalFailureView(httpError(status, token), token === 'validation_error' ? 'assign' : 'ack')
      expect(view.face).toBe(face)
      expect(view.retryable).toBe(flag)
    }
    expect(disposalFailureView(httpError(404, 'resource_not_found'), 'ack').reload).toBe(true)
    expect(disposalFailureView(httpError(409, 'conflict'), 'ack').reload).toBe(true)
    expect(INVALID_ID_FAILURE.retryable).toBe(false)
    expect(INVALID_ID_FAILURE.reload).toBe(true)
  })
})

describe('R375 己 · 判据⑤：三把刀现改现跑', () => {
  it('刀①：退回硬编 true ⇒ 点名红在字典判 false 的每一格', () => {
    const hardTrue = err => ({ ...writeFailureView(err), retryable: true })
    const flagged = NAMED_TOKENS.filter(token => hardTrue(httpError(503, token)).retryable !== isRetryable(httpError(503, token)))
    expect(flagged.length, '硬编 true 都不红，这枚判据就是单向的').toBeGreaterThan(10)
    expect(flagged).toContain('storage_unavailable')
    expect(flagged).toContain('internal_error')
  })

  it('刀②：一律 false ⇒ 必须红（屏上不许比字典宽，也不许比字典窄）', () => {
    const allFalse = err => ({ ...writeFailureView(err), retryable: false })
    const flagged = NAMED_TOKENS.filter(token => allFalse(httpError(503, token)).retryable !== isRetryable(httpError(503, token)))
    expect(flagged.length, '一律 false 都不红，判据②那一族就守不住').toBeGreaterThan(0)
    expect(flagged).toContain('rate_limited')
    expect(SILENT_SHAPES.filter(([, err]) => allFalse(err).retryable !== failureRetryable(err)).length).toBe(SILENT_SHAPES.length)
  })

  it('刀③：把字典某一格翻过来 ⇒ 两枚写点当场跟着翻，复原后当场翻回', () => {
    const row = ERROR_CODES.rate_limited
    const err = httpError(429, 'rate_limited')
    expect(writeFailureView(err).retryable).toBe(true)
    expect(disposalFailureView(err, 'ack').retryable).toBe(true)
    try {
      row.retryable = false
      expect(writeFailureView(err).retryable, '字典翻了屏上没翻：屏上是又一份抄写').toBe(false)
      expect(disposalFailureView(err, 'ack').retryable, '字典翻了处置脸没翻：又一份抄写').toBe(false)
    } finally {
      row.retryable = true
    }
    expect(writeFailureView(err).retryable).toBe(true)
    expect(disposalFailureView(err, 'ack').retryable).toBe(true)
  })
})

/** ===== 取证用的读源工具（本件不写任何文件） ===== */
/**
 * 基线两枚源码在模块作用域各起一枚 git 子进程读一次，全程缓存：放在 test 体内现读会撞
 * vitest 默认 5s 单测超时（全量 105 个文件争 CPU 时实测红过一次），那是量具自己抖、不是判据红。
 * r369-ruler-integrity.test.js 同样把 git show 摆在顶层。
 */
const SOURCE_CACHE = new Map()
function cached(key, read) {
  if (!SOURCE_CACHE.has(key)) SOURCE_CACHE.set(key, read())
  return SOURCE_CACHE.get(key)
}

function baselineText(name) {
  return cached('base:' + name, () => {
    const text = execFileSync('git', ['show', REF + ':frontend/src/lib/' + name], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
    if (!text.trim()) throw new Error('git show ' + REF + ' 取不到 frontend/src/lib/' + name)
    return text.replace(/\r\n/g, '\n')
  })
}

function workText(name) {
  return cached('work:' + name, () => readFileSync(new URL('../' + name, import.meta.url), 'utf8').replace(/\r\n/g, '\n'))
}

function codeOnlyText(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').split('\n').filter(line => !/^\s*\/\//.test(line)).join('\n')
}

/** 命中点往前找最近一枚顶格函数声明：用来把「还剩几枚硬编」归到函数名下。 */
function enclosingFunction(text, index) {
  const head = [...text.slice(0, index).matchAll(/^(?:export )?(?:async )?function ([A-Za-z_0-9]+)/gm)].pop()
  return head ? head[1] : '(top)'
}

function declNames(text) {
  return [
    ...[...text.matchAll(/^(?:export )?(?:async )?function ([A-Za-z_0-9]+)/gm)].map(item => item[1]),
    ...[...text.matchAll(/^export const ([A-Z_0-9]+)\s*=/gm)].map(item => item[1]),
  ]
}

function blockOf(text, name) {
  const asFunction = bodyAt(text, new RegExp('^(?:export )?(?:async )?function ' + name + '\\(', 'm'))
  return asFunction || constBlock(text, name)
}

/** 常量块：吃掉缩进续行与顶格的收尾括号，遇到下一枚顶格声明或空行收口。 */
function constBlock(text, name) {
  const lines = text.slice(text.indexOf('export const ' + name)).split('\n')
  const block = [lines[0]]
  for (let i = 1; i < lines.length; i += 1) {
    const line = lines[i]
    if (/^[}\]]/.test(line)) {
      block.push(line)
      break
    }
    if (/^\S/.test(line) || line === '') break
    block.push(line)
  }
  return block.join('\n')
}

/** 顶格导出口的名字：本单只准多出一枚 failureRetryable。 */
function exportedNames(text) {
  return [
    ...[...text.matchAll(/^export (?:async )?function ([A-Za-z_0-9]+)/gm)].map(item => item[1]),
    ...[...text.matchAll(/^export const ([A-Za-z_0-9]+)/gm)].map(item => item[1]),
  ]
}

/** failureRetryable 那一行判据：全文件只准有一枚，多了就是第二把尺。 */
function rulerLine(text) {
  const hits = text.split('\n').filter(line => /dictionaryAdjudicatesRetry\(err\) \? isRetryable\(err\) : true/.test(line))
  if (hits.length !== 1) throw new Error('尺子那一行不是唯一一枚，扫到 ' + hits.length + ' 枚')
  return hits[0]
}

function bodyAt(text, headPattern) {
  const match = headPattern.exec(text)
  if (!match) return null
  const end = text.indexOf('\n}', match.index)
  if (end < 0) throw new Error(headPattern.source + ' 的块收不到尾，量具落空')
  return text.slice(match.index, end + 2)
}

function bodyOf(text, name) {
  const block = blockOf(text, name)
  if (!block) throw new Error('找不到函数 ' + name + '：本件要量的东西不见了')
  return block
}

function disposalBody() {
  return bodyOf(workText('alerts.js'), 'disposalFailureView')
}

function writeBody() {
  return bodyOf(workText('notifications.js'), 'writeFailureView')
}

/** 只差一个 export 关键字不算漂移：那一枚尺子的函数体由上一枚钉单独逐字对平。 */
function unexport(block) {
  return block.replace(/^export /, '')
}

function countIn(text, needle) {
  return text.split(needle).length - 1
}

function sha(text) {
  return createHash('sha256').update(text, 'utf8').digest('hex').slice(0, 16)
}

/** 预热：基线与工作树各读一次（缓存的 const 声明在文件下半段，所以这一段摆在最后）。 */
for (const name of ['alerts.js', 'notifications.js']) {
  baselineText(name)
  workText(name)
}
