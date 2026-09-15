/**
 * V6 闸门 · 设计 token 定义完整性棘轮（B 叶子线）
 *
 * 要防的缺陷类别：未定义的 CSS 自定义属性是**静默失效** —— 浏览器不报错、不掉样式块，
 * 就是不渲染，最后表现成「页面白一块 / 控件没样式」。这类缺陷靠人肉对齐 theme.css 必然漏，
 * 所以把它变成会红的闸门：谁引用了没有定义的 token，单测就红。
 *
 * 口径：使用集 − 定义集 − 豁免集 = 空集。
 * 豁免集当前必须是空数组：A 线 e3b57a2 已把此前上报的 41 个缺失 token 全部补进 theme.css，
 * 基线由此钉在 0（把旧的 41 名单留在代码里等于钉住一个已经死了的事实）。
 *
 * 两档强度（都是硬断言，不是打印提醒）：
 *   档 1 components/ui/**（B 独占写入集）：只认 theme.css 的全局定义，不给「文件内自定义局部
 *        变量」留余地 —— 原语必须吃共享 token 层，不许造平行变量。
 *   档 2 src/**（全量，含 A 的面板）：认 theme.css 并上同文件局部定义。面板里确有局部定义，
 *        所以这一档放宽的是「定义来源」，不放宽「必须有定义」。
 */
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const THEME_CSS = join(SRC_ROOT, 'assets', 'theme.css')

/**
 * 豁免名单：引用了但没定义、允许暂不判红的 token。只准缩不准涨（上限见 EXEMPT_CEILING），
 * 且每一项必须「至今仍缺失且至今仍被引用」：A 补进 theme.css 之后还赖在这里，或者代码里
 * 已经不再引用，两种情况都直接判红 —— 这就是「缩完必须清名单」。
 */
const EXEMPT_MISSING = []
const EXEMPT_CEILING = 0

/** 带兜底值的 var(--x, v)：未定义时不判红（浏览器会退到兜底），但必须单独统计出来。 */
const MASKED_CEILING = 0

/**
 * 解析形状（按已提交树实测确定，不是猜的）：
 * - 定义：行首或分号 / 空白之后紧跟 --x: ，且值里不含分号大括号。必须用这个「紧」形状，
 *   因为 .ui-button--primary:hover 这类 BEM 修饰类名会被松匹配误当成定义
 *   （UiButton.css 4 处、UiTabs.css 1 处实测命中）。
 * - 使用：var( 后紧跟 token 名；第二个捕获组非空即代表这一处带兜底值。
 * - 已知盲区：嵌套 var 今天为 0（见对应断言）；一旦大于 0 说明扫描器要升级，而不是放宽断言。
 */
const DEFINITION_RE = /(?:^|[\s;])(--[A-Za-z0-9-]+)\s*:\s*[^;{}]+?[;\n]/gm
const USAGE_RE = /var\(\s*(--[A-Za-z0-9-]+)(\s*,)?/g
const NESTED_VAR_RE = /var\(\s*--[A-Za-z0-9-]+\s*,\s*var\(/g
/** Vue SFC 编译产物里的哈希变量名，不参与缺失判定。 */
const COMPILER_HASH_RE = /^--[0-9a-f]{6,8}$/i

const collectSourceFiles = (dir, out = []) => {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) collectSourceFiles(full, out)
    else if (/\.(css|vue)$/.test(entry.name)) out.push(full)
  }
  return out
}

const collect = (text, re) => {
  re.lastIndex = 0
  const out = []
  for (let m = re.exec(text); m !== null; m = re.exec(text)) out.push(m)
  return out
}

const FILES = collectSourceFiles(SRC_ROOT).map((file) => ({
  file,
  rel: relative(SRC_ROOT, file).split(sep).join('/'),
  text: readFileSync(file, 'utf8'),
}))
const TEXT_BY_REL = new Map(FILES.map((f) => [f.rel, f.text]))

const THEME_DEFS = new Set(collect(readFileSync(THEME_CSS, 'utf8'), DEFINITION_RE).map((m) => m[1]))

const LOCAL_DEFS = new Map()
const USED = new Map()
const USED_IN_UI = new Set()
const MASKED_SITES = new Map()
let nestedVarSites = 0

for (const { rel, text } of FILES) {
  for (const m of collect(text, DEFINITION_RE)) {
    if (!LOCAL_DEFS.has(m[1])) LOCAL_DEFS.set(m[1], rel)
  }
  for (const m of collect(text, USAGE_RE)) {
    const token = m[1]
    if (COMPILER_HASH_RE.test(token)) continue
    if (!USED.has(token)) USED.set(token, new Set())
    USED.get(token).add(rel)
    if (rel.startsWith('components/ui/')) USED_IN_UI.add(token)
    if (m[2]) {
      if (!MASKED_SITES.has(token)) MASKED_SITES.set(token, new Set())
      MASKED_SITES.get(token).add(rel)
    }
  }
  nestedVarSites += collect(text, NESTED_VAR_RE).length
}

const GLOBAL_DEFS = new Set([...THEME_DEFS, ...LOCAL_DEFS.keys()])
const missingFrom = (tokens, defined) =>
  [...tokens].filter((t) => !defined.has(t) && !EXEMPT_MISSING.includes(t)).sort()

/** 该 token 的每一处引用都带兜底值 —— 这种未定义不会白块，所以走单独统计而不是硬闸。 */
const everyUseMasked = (tokens, defined) =>
  [...tokens]
    .filter((t) => !defined.has(t) && !EXEMPT_MISSING.includes(t))
    .filter((t) => {
      const sites = USED.get(t)
      const masked = MASKED_SITES.get(t)
      return Boolean(masked) && [...sites].every((s) => masked.has(s))
    })
    .sort()

describe('设计 token 完整性棘轮', () => {
  it('扫描器没有空跑（否则「缺失 0」只是因为什么都没扫到）', () => {
    expect(FILES.length).toBeGreaterThanOrEqual(25)
    expect(THEME_DEFS.size).toBeGreaterThanOrEqual(70)
    expect(USED.size).toBeGreaterThanOrEqual(60)
    expect(USED_IN_UI.size).toBeGreaterThanOrEqual(40)
  })

  it('档 1：components/ui 引用的每个 token 必须在 theme.css 有定义', () => {
    const missing = missingFrom(USED_IN_UI, THEME_DEFS)
    expect(missing, '原语引用了 theme.css 里没有的 token：' + missing.join(', ')).toEqual([])
  })

  it('档 2：src 下任何 css/vue 引用的 token 都必须有定义', () => {
    const missing = missingFrom(USED.keys(), GLOBAL_DEFS)
    expect(missing, 'src 下有未定义的 token 正在被使用：' + missing.join(', ')).toEqual([])
  })

  it('豁免名单只准缩不准涨（基线 0 由 A 的 e3b57a2 清完 41 个后钉下）', () => {
    expect(EXEMPT_MISSING.length, '新增豁免项等于给闸门开后门，默认一律拒绝').toBeLessThanOrEqual(EXEMPT_CEILING)
    expect(new Set(EXEMPT_MISSING).size).toBe(EXEMPT_MISSING.length)
  })

  it('豁免名单里的每一项必须至今仍缺失、至今仍被引用', () => {
    for (const token of EXEMPT_MISSING) {
      expect(GLOBAL_DEFS.has(token), token + ' 已经有人补进定义，把它从豁免名单里删掉').toBe(false)
      expect(USED.has(token), token + ' 已经不再被引用，把它从豁免名单里删掉').toBe(true)
    }
    // 名单为空时上面两条是空转，所以补一条真会红的兜底断言：
    // 只要档 1 出现缺失而名单还是空的，这里就是红的（与上一条一起构成双向棘轮）。
    expect(missingFrom(USED_IN_UI, THEME_DEFS)).toEqual([])
  })

  it('带兜底值的引用单独统计，不进硬闸', () => {
    const masked = everyUseMasked(USED.keys(), GLOBAL_DEFS)
    expect(masked.length, '未定义且被兜底值遮蔽的 token：' + masked.join(', ')).toBeLessThanOrEqual(MASKED_CEILING)
    // 兜底解析本身也要证明在工作：今天有 20+ 个 token 是以 var(--x, 兜底) 形状被引用的
    expect(MASKED_SITES.size).toBeGreaterThanOrEqual(20)
    for (const [, sites] of MASKED_SITES) {
      for (const site of sites) expect(TEXT_BY_REL.has(site), site).toBe(true)
    }
  })

  it('已知盲区：不存在扫描器处理不了的嵌套 var', () => {
    expect(nestedVarSites, '出现嵌套 var 说明扫描器要升级，不许放宽断言凑绿').toBe(0)
  })
})
