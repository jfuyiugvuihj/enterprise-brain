/**
 * V6 闸门 · 用户可见文案不得夹带裸码名（B-5 ②，单向棘轮）
 *
 * 要防的缺陷：码名被夹在给人看的句子里。业务同学读到「本轮未产出任何结论
 * （no_answer_produced）」等于读到一句读不懂的报错，与 D-2 同族。唯一真相源是
 * lib/errcodes.js 的字典：句子只说人话 + 下一步，码名走 errorCodeOf() 的独立通道
 * （data-code 属性 / 「错误码：xxx」小字 / console.debug）。
 *
 * 三条判据，都可机器验证：
 *   literal    字符串或模板静态正文里同时出现中文与 snake_case 码名。
 *   interp     会进 DOM 的模板字符串把码本身当文案插值输出：${state.errorCode} /
 *              ${rawCode} / ${code} 这类。它不是字面量，只用「中文字符串里含码名」的
 *              正则当场扫不出来，所以单独立一条。插值取的是查表得到的句子
 *              （codes[state.errorCode]）不算 —— 那种码名已在 literal 侧被抓，不重复计数。
 *   mustache   Vue 模板 {{ }} 里直出码名，且所在标签没有开发者诊断区标记。
 * 例外只放过显式诊断区：同一段正文或所在标签里带「错误码」「技术信息」「诊断」字样
 * （formatError / errorCodeLabel 的「错误码：xxx」小字就是这条通道，V5 规格要求保留）。
 *
 * 棘轮语义（与色值 351、design-tokens 的 EXEMPT_MISSING 同一条规矩）：ALLOWLIST 只准缩短
 * 不准新增，且每一条必须至今仍命中；A-4 把 sessions.js 换成查 errcodes.js 之后还赖在名单里
 * 就是红。今天的账恰好 6 条 = 5 literal + 1 interp，全在 lib/sessions.js（A 的写入集，我不碰）。
 */
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')

/** 码名形态：小写开头的 snake_case 且至少一段下划线；纯小写单词（id、api）不算 */
const BARE_CODE = /\b[a-z][a-z0-9]*(_[a-z0-9]+)+/g
const HAS_CJK = /[\u4e00-\u9fff]/
/** 被认可的开发者诊断区标记 */
const DIAGNOSTIC = /错误码|技术信息|诊断/
/** 「插值出去的值就是码本身」：剥掉下标段与 String() 之后以码变量名结尾 */
const CODE_TAIL = /(?:^|[.\s(])(?:errorCode|rawCode|error_code|code)$/

const ALLOWLIST = [
  { file: 'lib/sessions.js', line: 376, rule: 'literal', code: 'no_answer_produced', owedBy: 'A 线 A-4：friendlyErrorText 改吃 errcodes.errorText' },
  { file: 'lib/sessions.js', line: 377, rule: 'literal', code: 'task_timeout', owedBy: 'A 线 A-4' },
  { file: 'lib/sessions.js', line: 378, rule: 'literal', code: 'internal_error', owedBy: 'A 线 A-4' },
  { file: 'lib/sessions.js', line: 379, rule: 'literal', code: 'authorization_unavailable', owedBy: 'A 线 A-4' },
  { file: 'lib/sessions.js', line: 380, rule: 'literal', code: 'authentication_required', owedBy: 'A 线 A-4' },
  { file: 'lib/sessions.js', line: 384, rule: 'interp', code: 'state.errorCode', owedBy: 'A 线 A-4：未知码走 errorCodeOf + 详情折叠区，别拼进 [错误] 前缀直出' },
]

/** 只准降不准升：清掉一条就得同时把这个数改小，逼着有人对账 */
const ALLOWLIST_CEILING = 6

/** 测试断言与夹具不是发给用户的文案，不进扫描范围 */
const isScanTarget = (name) => /\.(js|vue|css)$/.test(name) && !/\.(test|spec)\.js$/.test(name)

const collectFiles = (dir, out = []) => {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === '__tests__' || entry.name === 'node_modules') continue
      collectFiles(full, out)
    } else if (isScanTarget(entry.name)) {
      out.push(full)
    }
  }
  return out
}

const toRel = (full) => relative(SRC_ROOT, full).split(sep).join('/')

/** 一段文本里出现的全部码名 */
const bareCodesIn = (text) => {
  BARE_CODE.lastIndex = 0
  const found = []
  let match = BARE_CODE.exec(text)
  while (match) {
    found.push(match[0])
    match = BARE_CODE.exec(text)
  }
  return found
}

/** 插值表达式是否就是码本身：查表 key 与 errorText/fallback 这类人话变量都排除 */
const isCodeExpr = (raw) => {
  let expr = String(raw).trim()
  const wrapped = /^String\(([\s\S]*)\)$/.exec(expr)
  if (wrapped) expr = wrapped[1].trim()
  expr = expr.replace(/\[[^\]]*\]/g, '').trim()
  return CODE_TAIL.test(expr)
}

/**
 * 词法扫描：注释、正则字面量、对象键名一律不参与判定（它们不会渲染给人看）。
 * 解析不出来的形状不判红（宁可漏判也不误伤），但每条判据下面都有 fixture 用例反向证明
 * 它真的会红 —— 免得又造出一个「只有名单、闸门是空的」的失效（看板 §4A.1 的锁色闸门教训）。
 */
function tokenize(text, startMode) {
  const tokens = []
  let mode = startMode
  let i = 0
  let line = 1
  let prev = ''
  let lastTag = ''
  const n = text.length
  const at = (k) => (k < n ? text.charAt(k) : '')
  const startsWith = (needle, k) => text.substr(k, needle.length) === needle
  const countNewlines = (from, to) => {
    for (let k = from; k < to; k += 1) if (text.charAt(k) === '\n') line += 1
  }
  const readQuoted = (k, quote) => {
    let j = k + 1
    let buf = ''
    while (j < n) {
      const d = at(j)
      if (d === '\\') { buf += at(j + 1); j += 2; continue }
      if (d === quote) return { value: buf, end: j }
      if (d === '\n' && quote !== '`') return { value: buf, end: j }
      buf += d
      j += 1
    }
    return { value: buf, end: j }
  }
  const readTemplate = (k) => {
    let j = k + 1
    let buf = ''
    const exprs = []
    while (j < n) {
      const d = at(j)
      if (d === '\\') { buf += at(j + 1); j += 2; continue }
      if (d === '`') return { value: buf, exprs, end: j }
      if (d === '$' && at(j + 1) === '{') {
        let depth = 1
        let q = j + 2
        let inner = ''
        while (q < n && depth > 0) {
          const e = at(q)
          if (e === "'" || e === '"' || e === '`') {
            const stop = readQuoted(q, e)
            inner += text.slice(q, stop.end + 1)
            q = stop.end + 1
            continue
          }
          if (e === '{') depth += 1
          else if (e === '}') { depth -= 1; if (depth === 0) break }
          if (e === '\n') line += 1
          inner += e
          q += 1
        }
        exprs.push(inner)
        j = q + 1
        continue
      }
      if (d === '\n') line += 1
      buf += d
      j += 1
    }
    return { value: buf, exprs, end: j }
  }
  const readRegex = (k) => {
    let j = k + 1
    let inClass = false
    while (j < n) {
      const d = at(j)
      if (d === '\\') { j += 2; continue }
      if (d === '[') inClass = true
      else if (d === ']') inClass = false
      else if (d === '/' && !inClass) {
        j += 1
        while (/[a-z]/.test(at(j))) j += 1
        return j
      } else if (d === '\n') return k
      j += 1
    }
    return j
  }

  while (i < n) {
    const ch = at(i)
    if (ch === '\n') { line += 1; i += 1; continue }
    if (ch === ' ' || ch === '\t' || ch === '\r') { i += 1; continue }
    if (ch === '/' && at(i + 1) === '*') {
      let j = text.indexOf('*/', i + 2)
      if (j < 0) j = n
      countNewlines(i, j + 2)
      i = j + 2
      continue
    }
    if (mode === 'html') {
      if (startsWith('<!--', i)) {
        let j = text.indexOf('-->', i)
        if (j < 0) j = n
        countNewlines(i, j + 3)
        i = j + 3
        continue
      }
      if (startsWith('<script', i) || startsWith('<style', i)) {
        const isScript = startsWith('<script', i)
        let j = text.indexOf('>', i)
        j = j < 0 ? n : j + 1
        countNewlines(i, j)
        i = j
        lastTag = ''
        mode = isScript ? 'js' : 'css'
        continue
      }
      if (ch === '<') {
        let j = i + 1
        while (j < n && at(j) !== '>') {
          if (at(j) === '"' || at(j) === "'") {
            const q = at(j)
            j += 1
            while (j < n && at(j) !== q) j += 1
          }
          j += 1
        }
        const tagText = text.slice(i, Math.min(j + 1, n))
        lastTag = tagText
        tokens.push({ kind: 'tag', text: tagText, line })
        const attrRe = /[\w).:@-]+\s*=\s*"([^"]*)"/g
        let m = attrRe.exec(tagText)
        while (m) {
          tokens.push({ kind: 'string', text: m[1], line })
          m = attrRe.exec(tagText)
        }
        countNewlines(i, j + 1)
        i = j + 1
        continue
      }
      if (ch === '{' && at(i + 1) === '{') {
        let j = text.indexOf('}}', i)
        if (j < 0) j = n
        tokens.push({ kind: 'mustache', expr: text.slice(i + 2, j), tag: lastTag, line })
        i = j + 2
        continue
      }
      let j = i
      while (j < n && at(j) !== '<' && !(at(j) === '{' && at(j + 1) === '{')) j += 1
      const body = text.slice(i, j).replace(/\{\{[\s\S]*?\}\}/g, ' ')
      if (body.trim()) tokens.push({ kind: 'text', text: body, line })
      countNewlines(i, j)
      i = j
      continue
    }
    if (mode === 'js') {
      if (startsWith('</script', i)) {
        let j = text.indexOf('>', i)
        j = j < 0 ? n : j + 1
        countNewlines(i, j)
        i = j
        lastTag = ''
        mode = 'html'
        continue
      }
      if (ch === '/' && at(i + 1) === '/') {
        let j = i
        while (j < n && at(j) !== '\n') j += 1
        i = j
        continue
      }
      if (ch === '"' || ch === "'") {
        const got = readQuoted(i, ch)
        tokens.push({ kind: 'string', text: got.value, line })
        countNewlines(i, got.end + 1)
        i = got.end + 1
        prev = ch
        continue
      }
      if (ch === '`') {
        const got = readTemplate(i)
        tokens.push({ kind: 'template', text: got.value, exprs: got.exprs, line })
        countNewlines(i, got.end + 1)
        i = got.end + 1
        prev = '`'
        continue
      }
      if (ch === '/' && (/[([{,;:=!&|?+\-*%~^]$/.test(prev) || prev === '')) {
        const end = readRegex(i)
        prev = '/'
        // readRegex 返回的是消费完之后的下标；认不下时按普通字符走一格，绝不原地打转
        i = end > i ? end : i + 1
        continue
      }
      prev = ch
      i += 1
      continue
    }
    if (startsWith('</style', i)) {
      let j = text.indexOf('>', i)
      j = j < 0 ? n : j + 1
      countNewlines(i, j)
      i = j
      mode = 'html'
      continue
    }
    if (ch === '"' || ch === "'") {
      const got = readQuoted(i, ch)
      tokens.push({ kind: 'string', text: got.value, line })
      countNewlines(i, got.end + 1)
      i = got.end + 1
      continue
    }
    i += 1
  }
  return tokens
}

/** 一个文件里的全部违规点。rule 四条：literal / interp / mustache / html-text */
function violationsOf(rel, text) {
  const startMode = rel.endsWith('.css') ? 'css' : rel.endsWith('.js') ? 'js' : 'html'
  const lines = text.split('\n')
  const out = []
  const record = (t, rule, code) => out.push({
    file: rel,
    line: t.line,
    rule,
    code,
    excerpt: (lines[t.line - 1] || '').trim().slice(0, 140),
  })
  for (const t of tokenize(text, startMode)) {
    if (t.kind === 'string') {
      if (!HAS_CJK.test(t.text) || DIAGNOSTIC.test(t.text)) continue
      const codes = bareCodesIn(t.text)
      if (codes.length) record(t, 'literal', codes[0])
      continue
    }
    if (t.kind === 'text') {
      if (!HAS_CJK.test(t.text) || DIAGNOSTIC.test(t.text)) continue
      const codes = bareCodesIn(t.text)
      if (codes.length) record(t, 'html-text', codes[0])
      continue
    }
    if (t.kind === 'template') {
      if (!HAS_CJK.test(t.text) || DIAGNOSTIC.test(t.text)) continue
      const codes = bareCodesIn(t.text)
      if (codes.length) {
        record(t, 'literal', codes[0])
        continue
      }
      const hit = (t.exprs || []).filter(isCodeExpr)[0]
      if (hit) record(t, 'interp', hit.trim().slice(0, 60))
      continue
    }
    if (t.kind === 'mustache') {
      if (!isCodeExpr(t.expr)) continue
      if (DIAGNOSTIC.test(t.tag || '') || DIAGNOSTIC.test(t.expr)) continue
      record(t, 'mustache', t.expr.trim().slice(0, 60))
    }
  }
  return out
}

/** 名单匹配用 file+rule+码名，行号只做记账：A 在它上方加行不会误红 */
const keyOf = (v) => [v.file, v.rule, v.code].join('|')

const { files: SHIPPED, found: FOUND } = (() => {
  const list = collectFiles(SRC_ROOT).sort()
  const hits = []
  for (const full of list) hits.push(...violationsOf(toRel(full), readFileSync(full, 'utf8')))
  return { files: list.map(toRel), found: hits }
})()

const FOUND_KEYS = new Set(FOUND.map(keyOf))
const ALLOW_KEYS = new Set(ALLOWLIST.map(keyOf))

describe('裸码名禁令 · 真实树棘轮（只准缩短）', () => {
  it('闸门不是空的：扫描范围覆盖到 A 的面板与 theme.css', () => {
    expect(SHIPPED.length).toBeGreaterThanOrEqual(25)
    for (const must of ['lib/sessions.js', 'lib/http.js', 'assets/theme.css', 'App.vue', 'components/ChatPanel.vue']) {
      expect(SHIPPED.includes(must), must).toBe(true)
    }
    // 扫得出的字符串/模板 token 量级，防止解析器整体失灵导致「零违规 = 绿灯」的假象
    const tokenVolume = SHIPPED.reduce((sum, rel) => sum + tokenize(readFileSync(join(SRC_ROOT, rel), 'utf8'), rel.endsWith('.css') ? 'css' : rel.endsWith('.js') ? 'js' : 'html').length, 0)
    expect(tokenVolume).toBeGreaterThan(1500)
  })

  it('现存违规恰好等于名单，一条不许多、一条不许少', () => {
    expect(FOUND.map((v) => keyOf(v)).sort()).toEqual(ALLOWLIST.map((v) => keyOf(v)).sort())
  })

  it('每条名单都仍指向真实存在的违规：账清了就得同时删掉', () => {
    ALLOWLIST.forEach((entry) => expect(FOUND_KEYS.has(keyOf(entry)), keyOf(entry)).toBe(true))
    expect(ALLOWLIST.length).toBeLessThanOrEqual(ALLOWLIST_CEILING)
  })

  it('正交控制：lib/sessions.js 单独扫恰好 6 条（5 literal + 1 interp）', () => {
    const hits = violationsOf('lib/sessions.js', readFileSync(join(SRC_ROOT, 'lib', 'sessions.js'), 'utf8'))
    expect(hits.length).toBe(6)
    expect(hits.filter((h) => h.rule === 'literal').length).toBe(5)
    expect(hits.filter((h) => h.rule === 'interp').length).toBe(1)
    expect(hits.filter((h) => h.rule === 'interp')[0].line).toBe(384)
  })

  it('B 自己的写入集零违规：components/ui/** 与 errcodes.js 不占名单', () => {
    const mine = FOUND.filter((v) => v.file.startsWith('components/ui/') || v.file === 'lib/errcodes.js')
    expect(mine.map((v) => keyOf(v))).toEqual([])
  })

  it('四条判据在真实树里的分布记账（防某条判据被静默改废）', () => {
    const byRule = FOUND.reduce((acc, v) => {
      acc[v.rule] = (acc[v.rule] || 0) + 1
      return acc
    }, {})
    expect(byRule.literal).toBe(5)
    expect(byRule.interp).toBe(1)
    expect(byRule.mustache || 0).toBe(0)
    expect(byRule['html-text'] || 0).toBe(0)
  })
})
describe('裸码名禁令 · 判红夹具（证明判据本身会红，不只是名单）', () => {
  it('literal：面板脚本里的字典句夹码名会红，且新面孔不在名单里', () => {
    const src = [
      '<script setup>',
      'const codes = {',
      "  no_answer_produced: '本轮未产出任何结论（no_answer_produced），请重试或补充数据范围。',",
      '}',
      '</script>',
      '<template>',
      '  <p>{{ codes.no_answer_produced }}</p>',
      '</template>',
    ].join('\n')
    const hits = violationsOf('components/ChatPanel.vue', src)
    expect(hits.length).toBe(1)
    expect(hits[0].rule).toBe('literal')
    expect(hits[0].code).toBe('no_answer_produced')
    expect(ALLOW_KEYS.has(keyOf(hits[0]))).toBe(false)
  })

  it('interp：模板字符串把码本身当文案输出会红（字面量正则抓不到这一条）', () => {
    const src = 'function pick(state) {\n  if (state.errorCode) return `[错误] ${state.errorCode}`\n  return `[错误] ${state.errorText}`\n}\n'
    const hits = violationsOf('lib/sessions.js', src)
    expect(hits.length).toBe(1)
    expect(hits[0].rule).toBe('interp')
    expect(hits[0].code).toBe('state.errorCode')
    expect(hits[0].line).toBe(2)
  })

  it('interp 反例：插值取的是查表句子就不判红，那头的码名已由 literal 抓到', () => {
    const src = "function pick(state) {\n  const codes = { task_timeout: '请求超时，请重试。' }\n  return `[错误] ${codes[state.errorCode]}`\n}\n"
    expect(violationsOf('lib/sessions.js', src)).toEqual([])
  })

  it('mustache：Vue 模板直出码名会红；带「技术信息」的 <code> 诊断区与 data-code 属性放行', () => {
    const src = [
      '<template>',
      '  <div>',
      '    <span>{{ state.errorCode }}</span>',
      '    <code data-testid="ui-error-code" title="技术信息">{{ errorCode }}</code>',
      '    <p>{{ entry.message }}</p>',
      '    <b :data-code="entry.code">{{ entry.message }}</b>',
      '  </div>',
      '</template>',
    ].join('\n')
    const hits = violationsOf('components/GraphPanel.vue', src)
    expect(hits.length).toBe(1)
    expect(hits[0].rule).toBe('mustache')
    expect(hits[0].line).toBe(3)
  })

  it('html-text：模板文本节点里夹码名会红，{{ }} 里的字段名不误判成正文', () => {
    const src = [
      '<template>',
      '  <p>本轮未产出任何结论（no_answer_produced），请重试。</p>',
      '  <p>{{ col.unique_values }} 个唯一值 · {{ profile.column_count }}</p>',
      '</template>',
    ].join('\n')
    const hits = violationsOf('components/DataPanel.vue', src)
    expect(hits.length).toBe(1)
    expect(hits[0].rule).toBe('html-text')
    expect(hits[0].code).toBe('no_answer_produced')
  })

  it('不参与判定的形状：注释 / 正则字面量 / 对象键名 / 机器字段 / 诊断小字', () => {
    const src = [
      '/** 出处 app/api/v1/chat.py:998 的 error_code=no_answer_produced */',
      '// internal_error 走兜底句',
      'const EMBED = /error_code=([a-z][a-z0-9_]+)|（([a-z][a-z0-9_]+)）/g',
      "const tidy = (t) => t.replace(/([，、；：])[，、；：]+/g, '$1')",
      "const obj = { internal_error: '内部错误，请稍后重试。' }",
      "const label = (raw) => `错误码：${raw}`",
      "const tech = (code) => `技术信息：${code}`",
      "export default { name: 'no_answer_produced' }",
    ].join('\n')
    expect(violationsOf('lib/errcodes.js', src)).toEqual([])
  })

  it('解析器不被 CSS 形状打崩：注释 / @keyframes / 媒体查询 / v-bind()', () => {
    const src = [
      '/* 按 docs/reference/make_plate.py 的 inpaint 路线修补，实测会留矩形残影 */',
      '@keyframes ui-spin { to { transform: rotate(360deg); } }',
      '@media (min-width: 768px) { .ui-card { padding: var(--space-3); } }',
      '.ui-chip { width: v-bind(chipWidthPx); content: "已完成"; }',
      ':root { --radius-md: 8px; }',
    ].join('\n')
    expect(violationsOf('assets/theme.css', src)).toEqual([])
  })

  it('跨段不串味：<script> 里的属性文案算违规，模板里的中文说明不算', () => {
    const src = '<script setup>\nconst tip = \'当前部门范围缺失（department_scope_required），请联系管理员。\'\n</script>\n<template>\n  <p :title="tip">说明文字，没有码名。</p>\n</template>\n'
    const hits = violationsOf('components/InsightPanel.vue', src)
    expect(hits.length).toBe(1)
    expect(hits[0].rule).toBe('literal')
    expect(hits[0].code).toBe('department_scope_required')
  })
})
