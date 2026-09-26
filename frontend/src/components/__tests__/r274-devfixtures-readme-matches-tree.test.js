/**
 * R274 · X-4 的反证钉：devFixtures 那张表说的文件集必须与树里的文件集对得上
 *
 * 病灶：README 至今把 dashboard-demo.js 写成「在喂 DashboardPanel 的趋势卡、异常卡」，
 * 而 R267 已经把这枚文件整枚删了。README 自己第 3 条立的规矩就是「除本 README 之外
 * `git grep -n devFixtures -- src` 应当零命中」——表与树对不上，下一个接线的人只会照着
 * 这张表再编一次数据，或者反过来以为总览还挂着 fixture。
 *
 * 本件只钉「表与磁盘闭合」这一件事，不越界改别人的行：insights-demo.js 那一行同样陈旧
 * （W7 起 InsightPanel 已不引用它），那是 X-5，与 R271 的 insight-alerts.test.js 同写域，
 * 所以这里反过来钉住它**原样不动**，等 R271 并树后再由 X-5 收。
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { dirname, join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// 本件在 src/components/__tests__/ 下，src 根要往上两级。
const SRC_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const FIXTURE_DIR = join(SRC_ROOT, 'devFixtures')
const README = join(FIXTURE_DIR, 'README.md')
const readme = readFileSync(README, 'utf8').replace(/\r?\n/g, '\n')

/** 表里的数据文件行：第一列是一个 `xxx.js`。 */
const rows = readme
  .split('\n')
  .filter(line => /^\|\s*`[^`]+\.js`\s*\|/.test(line))
  .map(line => line.replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim()))
  .map(cells => ({
    file: cells[0].replace(/`/g, ''),
    feeds: cells[1],
    waiting: cells[2],
    removed: cells.slice(1).some(cell => cell.includes('已删除')),
  }))

/**
 * 全仓 src 下还有哪些「会被打包进界面」的文件提到这个文件名。
 * 测试件与 README 自己除外——它们提这个名字正是为了钉它不许回来。
 */
function productionReferrers(name) {
  const hits = []
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name)
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules') continue
        walk(full)
        continue
      }
      if (!/\.(js|vue|css)$/.test(entry.name)) continue
      if (/\.test\.js$/.test(entry.name)) continue
      if (full === README) continue
      if (readFileSync(full, 'utf8').includes(name)) hits.push(relative(SRC_ROOT, full).split(sep).join('/'))
    }
  }
  walk(SRC_ROOT)
  return hits
}

describe('R274② · README 的文件集与磁盘上的文件集逐条闭合', () => {
  it('表真的被解析出来了：四行、一个不多一个不少（解析不出来时下面全是空话）', () => {
    expect(rows.map(row => row.file)).toEqual([
      'dashboard-demo.js',
      'insights-demo.js',
      'approval-demo.js',
      'login-demo.js',
    ])
  })

  it('每一行都与磁盘对得上：标了已删除的必须不在树里，没标的必须真在树里', () => {
    for (const row of rows) {
      expect(existsSync(join(FIXTURE_DIR, row.file)), `${row.file} 的在册状态与磁盘不符`).toBe(!row.removed)
    }
  })

  it('目录里不许有表上没登记的私货', () => {
    const listed = new Set(rows.map(row => row.file))
    const onDisk = readdirSync(FIXTURE_DIR).filter(name => name.endsWith('.js')).sort()
    expect(onDisk.length).toBeGreaterThan(0)
    for (const name of onDisk) expect(listed.has(name), `${name} 没进 README 的表`).toBe(true)
  })

  it('dashboard-demo.js 那一行改口成「已删除」，而且全仓再无生产代码引用它', () => {
    const row = rows.find(item => item.file === 'dashboard-demo.js')
    expect(row, '表里必须留着这一行，说清它去哪了').toBeTruthy()
    expect(row.removed, 'README 仍把 dashboard-demo.js 当成在喂面板的活件').toBe(true)
    expect(row.feeds).toContain('不留空壳')
    expect(productionReferrers('dashboard-demo.js')).toEqual([])
  })

  it('面板改读真回执这句话不许只写在表里：DashboardPanel 自己也不许再提 devFixtures', () => {
    const panel = readFileSync(join(SRC_ROOT, 'components', 'DashboardPanel.vue'), 'utf8')
    // 注意别把诚实牌那枚 data-testid="dashboard-demo-flag" 也算成引用：查的是文件名。
    expect(panel).not.toMatch(/devFixtures|dashboard-demo\.js/)
  })

  it('insights-demo.js 那一行原样不动：那是 X-5 的写域，等 R271 并树后收', () => {
    const row = rows.find(item => item.file === 'insights-demo.js')
    expect(row.feeds).toBe('`InsightPanel.vue` → `POST /insights/detect` 的入参')
    expect(row.waiting).toBe('R14：同上')
  })
})
