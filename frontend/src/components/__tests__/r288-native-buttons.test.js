/**
 * R288 守卫钉 · G15 原生对话框归零 + G20 裸按钮接原语
 *
 * 这一件是判据②与判据③的门：它把「现取计数」从一枚没人跑的脚本变成一跑就红的钉。
 * 量具只有两枚，全部与施工脚本共用同一份实现（不许测试一套数法、脚本另一套数法）：
 *   · r288-native-button-scan.js —— 裸 <button> 怎么数（tmp/r288-native-buttons.mjs 同一份）
 *   · r288-native-dialog-scan.js —— 原生对话框调用点怎么数（tmp/r288-native-dialogs.mjs 同一份）
 *
 * 反证怎么算红：
 *   · 往 frontend/src 任何一枚 .vue 里塞回一发 confirm( / alert( / prompt( ⇒ 甲组第一钉红；
 *   · 把六枚文件里任何一枚的裸 <button> 加回来 ⇒ 乙组第一钉红；
 *   · 把六枚文件里任何一枚的 UiButton 拆掉（哪怕顺手把按钮删了）⇒ 乙组第三钉红。
 *
 * 两枚棘轮都只准降不准升：越界的数字不会自动放行，红字会点名要谁去改。
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { countNativeButtons, scanNativeButtons } from './r288-native-button-scan.js'
import { findNativeDialogs, scanNativeDialogs } from './r288-native-dialog-scan.js'

const SRC_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const readSrc = rel => readFileSync(join(SRC_ROOT, rel), 'utf8').replace(/\r\n/g, '\n')

/** R288 判据③点名的六枚文件：本单写域，裸按钮必须一枚不剩。 */
const R288_FILES = [
  'components/ApprovalPanel.vue',
  'components/ChartViewer.vue',
  'components/DataPanel.vue',
  'components/DocPanel.vue',
  'components/DocumentPreviewModal.vue',
  'components/GraphPanel.vue',
]

/**
 * 六枚之外的欠账棘轮（2026-09-26 现取）：DashboardPanel.vue 属排队单 R291／R293 写域，
 * 本单只读不写；App.vue 与 SourceCard.vue 不在本单点名的六枚里。这三处一枚都不许加，
 * 减了就把这个数字改小 —— 改大必须在本单回执里点名说明。
 */
const DEBT_RATCHET = {
  'App.vue': 8,
  'components/DashboardPanel.vue': 9,
  'components/SourceCard.vue': 3,
}
const DEBT_TOTAL_RATCHET = 20

const formatRows = rows => rows.map(row => row.file + '  ' + row.count + ' 枚').join('\n')
const formatDialogs = rows => rows.map(row => row.file + ':' + row.line + '  ' + row.raw).join('\n')

// ==================== 甲 · G15 原生对话框 ====================

describe('甲 · G15：原生对话框调用点在 frontend/src 全域归零', () => {
  it('扫描面不豁免任何目录，命中必须是一枚都没有', () => {
    const rows = scanNativeDialogs(SRC_ROOT)
    expect(rows, '还留着浏览器原生弹窗：\n' + formatDialogs(rows)).toEqual([])
  })

  it('数法本身有牙：三枚真调用点全都抓得到', () => {
    const probe = [
      'if (!confirm("确定删除？")) return',
      'window.alert("好了")',
      'const answer = window.prompt("输入名称")',
    ].join('\n')
    expect(findNativeDialogs(probe).map(hit => hit.text)).toEqual(['confirm(', 'window.alert', 'window.prompt'])
  })

  it('数法不误伤好话：注释里写明「不用原生弹窗」与断言里的字符串都不算调用点', () => {
    const prose = [
      '// 两步内联确认，不用 window.confirm',
      '<!-- 这里曾经用过 confirm(，现在换成内联两步 -->',
      "expect(code).not.toContain('window.confirm')",
      "it('不出现裸 confirm(', () => {})",
      'function renewAlert() {}',
      'dialog.confirm()',
    ].join('\n')
    expect(findNativeDialogs(prose), formatDialogs(findNativeDialogs(prose))).toHaveLength(0)
  })

  it('刻意保留的口径：模板属性 @click="confirm(...)" 算调用点（双引号串不剥就是为了让它现形）', () => {
    const templateHit = '<div @click="confirm(`确定删除？`)"></div>'
    expect(findNativeDialogs(templateHit).map(hit => hit.text)).toEqual(['confirm('])
  })

  it('六枚文件里不许靠「删掉按钮」蒙过归零：删除出口仍在，且走两步内联', () => {
    const docPanel = readSrc(join('components', 'DocPanel.vue'))
    expect(docPanel).toContain('requestDeleteSelected')
    expect(docPanel).toContain('requestDeleteOne')
    expect(docPanel).toContain('advanceDelete')
    expect(docPanel).toContain('删除后无法恢复')
  })
})

// ==================== 乙 · G20 裸按钮接原语 ====================

describe('乙 · G20：判据点名的六枚文件裸按钮归零，且真的接上了原语', () => {
  it.each(R288_FILES)('%s 的裸 <button> 为 0 枚', rel => {
    const count = countNativeButtons(readSrc(rel))
    expect(count, rel + ' 还剩 ' + count + ' 枚裸按钮').toBe(0)
  })

  it('六枚文件都从 ./ui 引了 UiButton，并且真的在模板里用了它', () => {
    for (const rel of R288_FILES) {
      const source = readSrc(rel)
      expect(source, rel + ' 没有从 ./ui 引 UiButton').toMatch(/import\s*\{[^}]*\bUiButton\b[^}]*\}\s*from\s*'\.\/ui'/)
      expect(source, rel + ' 引了 UiButton 却没有用它').toContain('<UiButton')
    }
  })

  it('全仓裸按钮欠账只减不增（六枚之外的三处棘轮）', () => {
    const rows = scanNativeButtons(SRC_ROOT)
    const total = rows.reduce((sum, row) => sum + row.count, 0)
    const found = new Map(rows.map(row => [row.file, row.count]))
    for (const [rel, limit] of Object.entries(DEBT_RATCHET)) {
      const count = found.get(rel) ?? 0
      expect(count, rel + ' 现为 ' + count + ' 枚，棘轮上限 ' + limit + ' 枚').toBeLessThanOrEqual(limit)
    }
    expect(total, '全仓裸按钮现取 ' + total + ' 枚，棘轮上限 ' + DEBT_TOTAL_RATCHET + ' 枚\n' + formatRows(rows))
      .toBeLessThanOrEqual(DEBT_TOTAL_RATCHET)
  })

  it('量具本身有牙：开标签才算，UiButton 与大写前缀都不误伤', () => {
    expect(countNativeButtons('<button type="button">删</button>')).toBe(1)
    expect(countNativeButtons('<button\n  class="x"\n>删</button>')).toBe(1)
    expect(countNativeButtons('<UiButton label="删" />')).toBe(0)
    expect(countNativeButtons('<!-- <button>注释里不画上屏</button> -->')).toBe(0)
  })
})
