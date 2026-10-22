/**
 * R151 · 四块面板的色值台账（DocPanel / DataPanel / DocumentPreviewModal / ChartViewer）
 *
 * 这枚用例要防的缺陷类别：色值债的「账」与「物」对不上，而且对不上时没有任何东西会红 ——
 *   (1) 有人把 var(--x) 换回裸 #hex / rgba()：面板视觉上回到浅色 Element 时代，lint 只给 warning；
 *   (1b) 有人改 theme.css 里 --legacy-* 的值：那等于在「还债」单里偷偷改视觉（判据④明令禁止）；
 *   (3) 有人把已删除的可证死声明抄回来（同选择器 + 同属性 + 同 @media 被后一条覆盖 = 纯死代码）；
 *   (4) 有人新增一枚名字里带 red/blue/green/white/black/gray/teal 的 token 并在色值属性里引用：
 *       .stylelintrc.json 的 `declaration-property-value-disallowed-list` 用 /\b(?:red|blue|...)\b/
 *       匹配整条值，会把 var(--legacy-ep-red) 当成裸关键字，于是「换成 token」反而多挨一枚告警。
 *       本单实测撞过这一枪（前 13 枚 token 命名就是这样回炉的），所以把它钉成断言。
 *
 * 台账怎么来的（不是手抄）：把工作树基线 eef642b 的四份源码与改后源码逐声明比对生成，
 * 每一步都要求「新值在位 + 旧值在该属性上绝迹」双记账通过（PROBLEMS=0）才落成下面的表。
 * 像素与生效值证据（执行层工具，脚本不进库）：r151_check4.mjs 同视口样本板 + r151_pairs2.mjs
 * 逐枚替换 4 底色实测：820 格生效值 0 处变化、四块板 1036 万像素 0 处差异、169 枚替换 432 探针 0 处差异。
 *
 * 口径：LEDGER 的 old/new 是「整条声明的值」，按源码空白折叠成一个空格比较，
 * 所以格式化换行与缩进变化不会误伤；行号一律不进台账（改一行动号就漂，本仓被咬过多次）。
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const FILES = ['DocPanel.vue', 'DataPanel.vue', 'DocumentPreviewModal.vue', 'ChartViewer.vue']

const styleOf = (text) => text.slice(text.indexOf('<style'), text.indexOf('</style>'))
const readStyle = (file) => styleOf(readFileSync(join(SRC, 'components', file), 'utf8'))
const squeeze = (s) => s.replace(/\s+/g, ' ').trim()
/** 某个属性在这份样式表里出现过的全部声明值（同属性可能有多条，逐条比而不是只看第一条） */
const declsOf = (css, prop) => [...css.matchAll(new RegExp('(?<![\\w-])' + prop + '\\s*:\\s*([^;{}]*)', 'g'))].map((m) => squeeze(m[1]))

const COLOR_PROPS = ['color', 'caret-color', 'background', 'background-color',
  'border', 'border-top', 'border-right', 'border-bottom', 'border-left',
  'border-color', 'border-top-color', 'border-right-color', 'border-bottom-color', 'border-left-color',
  'outline-color', 'fill', 'stroke', 'text-shadow', 'box-shadow']
const HEX_RE = /#[0-9a-fA-F]{3,8}\b/
const COLOR_FN_RE = /\b(?:rgba?|hsla?)\(/
const KEYWORD_RE = /\b(?:red|blue|green|white|black|gray|grey|silver|navy|teal)\b/
const MASKED_VAR_RE = /var\(\s*--[\w-]+\s*,/

const LEDGER = [["DocPanel.vue", "border-bottom", "1px solid rgba(0,0,0,0.05)", "1px solid color-mix(in srgb, var(--legacy-void) 5%, transparent)"], ["DocPanel.vue", "color", "#606266", "var(--legacy-ink-mid)"], ["DocPanel.vue", "background", "#d0d5dd", "var(--legacy-line)"], ["DocPanel.vue", "background", "#fff", "var(--legacy-paper)"], ["DocPanel.vue", "box-shadow", "0 1px 3px rgba(0,0,0,0.15)", "0 1px 3px color-mix(in srgb, var(--legacy-void) 15%, transparent)"], ["DocPanel.vue", "background", "#f56c6c", "var(--legacy-ep-danger)"], ["DocPanel.vue", "background", "rgba(0,0,0,0.03)", "color-mix(in srgb, var(--legacy-void) 3%, transparent)"], ["DocPanel.vue", "color", "#303133", "var(--legacy-ink-strong)"], ["DocPanel.vue", "color", "#c0c4cc", "var(--legacy-ink-faint)"], ["DocPanel.vue", "color", "#909399", "var(--legacy-ink-soft)"], ["DocPanel.vue", "border", "1.5px dashed #d0d5dd", "1.5px dashed var(--legacy-line)"], ["DocPanel.vue", "border-color", "#409eff", "var(--legacy-ep-primary)"], ["DocPanel.vue", "color", "#606266", "var(--legacy-ink-mid)"], ["DocPanel.vue", "background", "#fff", "var(--legacy-paper)"], ["DocPanel.vue", "border", "1px solid #ebeef5", "1px solid var(--legacy-line-pale)"], ["DocPanel.vue", "background", "rgba(103,194,58,0.04)", "color-mix(in srgb, var(--legacy-ep-success) 4%, transparent)"], ["DocPanel.vue", "border-color", "#b3e19d", "var(--legacy-ep-success-line)"], ["DocPanel.vue", "background", "rgba(245,108,108,0.04)", "color-mix(in srgb, var(--legacy-ep-danger) 4%, transparent)"], ["DocPanel.vue", "border-color", "#fab6b6", "var(--legacy-ep-danger-line)"], ["DocPanel.vue", "color", "#409eff", "var(--legacy-ep-primary)"], ["DocPanel.vue", "background", "#edf2f7", "var(--legacy-fill-mist)"], ["DocPanel.vue", "background", "linear-gradient(90deg, #409eff, #67c23a)", "linear-gradient(90deg, var(--legacy-ep-primary), var(--legacy-ep-success))"], ["DocPanel.vue", "color", "#909399", "var(--legacy-ink-soft)"], ["DocPanel.vue", "color", "#67c23a", "var(--legacy-ep-success)"], ["DocPanel.vue", "color", "#f56c6c", "var(--legacy-ep-danger)"], ["DocPanel.vue", "color", "#909399", "var(--legacy-ink-soft)"], ["DocPanel.vue", "color", "#606266", "var(--legacy-ink-mid)"], ["DocPanel.vue", "background", "#f0f2f5", "var(--legacy-fill)"], ["DocPanel.vue", "background", "rgba(245,108,108,0.04)", "color-mix(in srgb, var(--legacy-ep-danger) 4%, transparent)"], ["DocPanel.vue", "color", "#606266", "var(--legacy-ink-mid)"], ["DocPanel.vue", "border", "1px solid #fab6b6", "1px solid var(--legacy-ep-danger-line)"], ["DocPanel.vue", "background", "#fff", "var(--legacy-paper)"], ["DocPanel.vue", "color", "#f56c6c", "var(--legacy-ep-danger)"], ["DocPanel.vue", "background", "#f56c6c", "var(--legacy-ep-danger)"], ["DocPanel.vue", "color", "#fff", "var(--legacy-paper)"], ["DocPanel.vue", "background", "#d0d5dd", "var(--legacy-line)"], ["DocPanel.vue", "background", "rgba(64,158,255,0.03)", "color-mix(in srgb, var(--legacy-ep-primary) 3%, transparent)"], ["DocPanel.vue", "background", "rgba(64,158,255,0.06)", "color-mix(in srgb, var(--legacy-ep-primary) 6%, transparent)"], ["DocPanel.vue", "border-color", "rgba(64,158,255,0.15)", "color-mix(in srgb, var(--legacy-ep-primary) 15%, transparent)"], ["DocPanel.vue", "color", "#909399", "var(--legacy-ink-soft)"], ["DocPanel.vue", "color", "#409eff", "var(--legacy-ep-primary)"], ["DocPanel.vue", "color", "#303133", "var(--legacy-ink-strong)"], ["DocPanel.vue", "border", "1px solid #d0d5dd", "1px solid var(--legacy-line)"], ["DocPanel.vue", "background", "#fff", "var(--legacy-paper)"], ["DocPanel.vue", "color", "#606266", "var(--legacy-ink-mid)"], ["DocPanel.vue", "color", "#c0c4cc", "var(--legacy-ink-faint)"], ["DocPanel.vue", "color", "#f56c6c", "var(--legacy-ep-danger)"], ["DocPanel.vue", "background", "rgba(245,108,108,0.08)", "color-mix(in srgb, var(--legacy-ep-danger) 8%, transparent)"], ["DocPanel.vue", "border-top", "1px solid rgba(0,0,0,0.04)", "1px solid color-mix(in srgb, var(--legacy-void) 4%, transparent)"], ["DocPanel.vue", "color", "#c0c4cc", "var(--legacy-ink-faint)"], ["DocPanel.vue", "color", "#f56c6c", "var(--legacy-ep-danger)"], ["DocPanel.vue", "background", "rgba(255, 255, 255, .035)", "color-mix(in srgb, var(--legacy-paper) 3.5%, transparent)"], ["DocPanel.vue", "background", "rgba(53, 211, 200, .1)", "color-mix(in srgb, var(--legacy-aqua-bright) 10%, transparent)"], ["DocPanel.vue", "box-shadow", "inset 0 0 0 1px rgba(255, 255, 255, .02)", "inset 0 0 0 1px color-mix(in srgb, var(--legacy-paper) 2%, transparent)"], ["DocPanel.vue", "border-color", "rgba(53, 211, 200, .28)", "color-mix(in srgb, var(--legacy-aqua-bright) 28%, transparent)"], ["DocPanel.vue", "background", "rgba(53, 211, 200, .035)", "color-mix(in srgb, var(--legacy-aqua-bright) 3.5%, transparent)"], ["DocPanel.vue", "background", "rgba(53, 211, 200, .1)", "color-mix(in srgb, var(--legacy-aqua-bright) 10%, transparent)"], ["DocPanel.vue", "background", "rgba(106, 140, 255, .1)", "color-mix(in srgb, var(--legacy-periwinkle-strong) 10%, transparent)"], ["DocPanel.vue", "border-color", "rgba(106, 140, 255, .28)", "color-mix(in srgb, var(--legacy-periwinkle-strong) 28%, transparent)"], ["DocPanel.vue", "background", "rgba(255, 255, 255, .04)", "color-mix(in srgb, var(--legacy-paper) 4%, transparent)"], ["DocPanel.vue", "color", "#b5c4ff", "var(--legacy-periwinkle-pale)"], ["DocPanel.vue", "background", "rgba(106, 140, 255, .12)", "color-mix(in srgb, var(--legacy-periwinkle-strong) 12%, transparent)"], ["DocPanel.vue", "color", "#ffabb2", "var(--legacy-coral-soft)"], ["DocPanel.vue", "background", "rgba(238, 109, 120, .12)", "color-mix(in srgb, var(--red) 12%, transparent)"], ["DataPanel.vue", "border-bottom", "1px solid rgba(0,0,0,0.05)", "1px solid color-mix(in srgb, var(--legacy-void) 5%, transparent)"], ["DataPanel.vue", "box-shadow", "0 4px 12px rgba(16,185,129,0.3)", "0 4px 12px color-mix(in srgb, var(--legacy-emerald) 30%, transparent)"], ["DataPanel.vue", "color", "#909399", "var(--legacy-ink-soft)"], ["DataPanel.vue", "border-bottom", "1px solid rgba(0,0,0,0.05)", "1px solid color-mix(in srgb, var(--legacy-void) 5%, transparent)"], ["DataPanel.vue", "color", "#303133", "var(--legacy-ink-strong)"], ["DataPanel.vue", "background", "rgba(16,185,129,0.12)", "color-mix(in srgb, var(--legacy-emerald) 12%, transparent)"], ["DataPanel.vue", "color", "#047857", "var(--legacy-emerald-deeper)"], ["DataPanel.vue", "border", "1px solid #edf0f2", "1px solid var(--legacy-fill-cool)"], ["DataPanel.vue", "background", "#fff", "var(--legacy-paper)"], ["DataPanel.vue", "color", "#303133", "var(--legacy-ink-strong)"], ["DataPanel.vue", "border-color", "#6ee7b7", "var(--legacy-emerald-300)"], ["DataPanel.vue", "background", "#f0fdf4", "var(--legacy-emerald-pale)"], ["DataPanel.vue", "border-color", "#10b981", "var(--legacy-emerald)"], ["DataPanel.vue", "background", "linear-gradient(135deg, #ecfdf5, #f0fdf4)", "linear-gradient(135deg, var(--legacy-emerald-mist), var(--legacy-emerald-pale))"], ["DataPanel.vue", "box-shadow", "0 2px 8px rgba(16,185,129,0.1)", "0 2px 8px color-mix(in srgb, var(--legacy-emerald) 10%, transparent)"], ["DataPanel.vue", "background", "#dcfce7", "var(--legacy-emerald-100)"], ["DataPanel.vue", "color", "#047857", "var(--legacy-emerald-deeper)"], ["DataPanel.vue", "color", "#374151", "var(--legacy-ink-graphite)"], ["DataPanel.vue", "color", "#9ca3af", "var(--legacy-ink-mute)"], ["DataPanel.vue", "background", "rgba(255,255,255,0.8)", "color-mix(in srgb, var(--legacy-paper) 80%, transparent)"], ["DataPanel.vue", "border", "1px solid rgba(0,0,0,0.04)", "1px solid color-mix(in srgb, var(--legacy-void) 4%, transparent)"], ["DataPanel.vue", "background", "rgba(16,185,129,0.06)", "color-mix(in srgb, var(--legacy-emerald) 6%, transparent)"], ["DataPanel.vue", "border-bottom", "1px solid rgba(0,0,0,0.04)", "1px solid color-mix(in srgb, var(--legacy-void) 4%, transparent)"], ["DataPanel.vue", "color", "#909399", "var(--legacy-ink-soft)"], ["DataPanel.vue", "border", "1px solid #d1d5db", "1px solid var(--legacy-line-mute)"], ["DataPanel.vue", "color", "#4b5563", "var(--legacy-ink-graphite-deep)"], ["DataPanel.vue", "border-bottom", "1px solid #f5f5f5", "1px solid var(--legacy-fill-plain)"], ["DataPanel.vue", "color", "#303133", "var(--legacy-ink-strong)"], ["DataPanel.vue", "color", "#909399", "var(--legacy-ink-soft)"], ["DataPanel.vue", "background", "#f0f2f5", "var(--legacy-fill)"], ["DataPanel.vue", "color", "#e6a23c", "var(--legacy-ep-orange)"], ["DataPanel.vue", "color", "#909399", "var(--legacy-ink-soft)"], ["DataPanel.vue", "color", "#303133", "var(--legacy-ink-strong)"], ["DataPanel.vue", "background", "#fff", "var(--legacy-paper)"], ["DataPanel.vue", "border", "1px solid #e4e7ed", "1px solid var(--legacy-line-hair)"], ["DataPanel.vue", "color", "#303133", "var(--legacy-ink-strong)"], ["DataPanel.vue", "border-color", "#409eff", "var(--legacy-ep-primary)"], ["DataPanel.vue", "color", "#409eff", "var(--legacy-ep-primary)"], ["DataPanel.vue", "background", "rgba(64,158,255,0.03)", "color-mix(in srgb, var(--legacy-ep-primary) 3%, transparent)"], ["DataPanel.vue", "background", "rgba(157, 178, 207, .25)", "color-mix(in srgb, var(--legacy-steel) 25%, transparent)"], ["DataPanel.vue", "background", "linear-gradient(135deg, var(--cyan), #1a9f9a)", "linear-gradient(135deg, var(--cyan), var(--legacy-aqua))"], ["DataPanel.vue", "color", "#061016", "var(--legacy-night)"], ["DataPanel.vue", "box-shadow", "0 10px 24px rgba(53, 211, 200, .14)", "0 10px 24px color-mix(in srgb, var(--legacy-aqua-bright) 14%, transparent)"], ["DataPanel.vue", "background", "rgba(53, 211, 200, .25)", "color-mix(in srgb, var(--legacy-aqua-bright) 25%, transparent)"], ["DataPanel.vue", "background", "rgba(53, 211, 200, .1)", "color-mix(in srgb, var(--legacy-aqua-bright) 10%, transparent)"], ["DataPanel.vue", "background", "rgba(255, 255, 255, .035)", "color-mix(in srgb, var(--legacy-paper) 3.5%, transparent)"], ["DataPanel.vue", "border-color", "rgba(53, 211, 200, .42)", "color-mix(in srgb, var(--legacy-aqua-bright) 42%, transparent)"], ["DataPanel.vue", "background", "rgba(53, 211, 200, .08)", "color-mix(in srgb, var(--legacy-aqua-bright) 8%, transparent)"], ["DataPanel.vue", "background", "rgba(255, 255, 255, .04)", "color-mix(in srgb, var(--legacy-paper) 4%, transparent)"], ["DataPanel.vue", "color", "#b5c4ff", "var(--legacy-periwinkle-pale)"], ["DataPanel.vue", "background", "rgba(101, 212, 154, .1)", "color-mix(in srgb, var(--green) 10%, transparent)"], ["DataPanel.vue", "background", "rgba(228, 162, 74, .1)", "color-mix(in srgb, var(--amber) 10%, transparent)"], ["DataPanel.vue", "color", "#ff9da5", "var(--legacy-coral)"], ["DataPanel.vue", "background", "rgba(238, 109, 120, .1)", "color-mix(in srgb, var(--red) 10%, transparent)"], ["DocumentPreviewModal.vue", "background", "rgba(3, 7, 16, .82)", "color-mix(in srgb, var(--legacy-veil) 82%, transparent)"], ["DocumentPreviewModal.vue", "background", "#111b2c", "var(--legacy-night-2)"], ["DocumentPreviewModal.vue", "border", "1px solid rgba(157, 178, 207, .18)", "1px solid color-mix(in srgb, var(--legacy-steel) 18%, transparent)"], ["DocumentPreviewModal.vue", "box-shadow", "0 24px 80px rgba(0, 0, 0, .42)", "0 24px 80px color-mix(in srgb, var(--legacy-void) 42%, transparent)"], ["DocumentPreviewModal.vue", "border-bottom", "1px solid rgba(157, 178, 207, .16)", "1px solid color-mix(in srgb, var(--legacy-steel) 16%, transparent)"], ["DocumentPreviewModal.vue", "color", "#f0f4fb", "var(--ink)"], ["DocumentPreviewModal.vue", "color", "#9eacc1", "var(--legacy-ink-steel)"], ["DocumentPreviewModal.vue", "border", "1px solid rgba(157, 178, 207, .22)", "1px solid color-mix(in srgb, var(--legacy-steel) 22%, transparent)"], ["DocumentPreviewModal.vue", "background", "rgba(255, 255, 255, .04)", "color-mix(in srgb, var(--legacy-paper) 4%, transparent)"], ["DocumentPreviewModal.vue", "color", "#dbe5f3", "var(--legacy-tint-azure)"], ["DocumentPreviewModal.vue", "border-color", "#6a8cff", "var(--legacy-periwinkle-strong)"], ["DocumentPreviewModal.vue", "color", "#aabdff", "var(--legacy-periwinkle-mid)"], ["DocumentPreviewModal.vue", "background", "rgba(106, 140, 255, .12)", "color-mix(in srgb, var(--legacy-periwinkle-strong) 12%, transparent)"], ["DocumentPreviewModal.vue", "background", "#0b1220", "var(--legacy-night-1)"], ["DocumentPreviewModal.vue", "color", "#9eacc1", "var(--legacy-ink-steel)"], ["DocumentPreviewModal.vue", "color", "#ff9da5", "var(--legacy-coral)"], ["DocumentPreviewModal.vue", "background", "#525659", "var(--legacy-slate-dark)"], ["DocumentPreviewModal.vue", "color", "#e7eef9", "var(--legacy-tint-azure-soft)"], ["DocumentPreviewModal.vue", "background", "#0d1728", "var(--legacy-night-3)"], ["DocumentPreviewModal.vue", "color", "#9eacc1", "var(--legacy-ink-steel)"], ["DocumentPreviewModal.vue", "border", "1px solid rgba(157, 178, 207, .16)", "1px solid color-mix(in srgb, var(--legacy-steel) 16%, transparent)"], ["DocumentPreviewModal.vue", "background", "#142035", "var(--legacy-night-4)"], ["DocumentPreviewModal.vue", "border-right", "1px solid rgba(157, 178, 207, .12)", "1px solid color-mix(in srgb, var(--legacy-steel) 12%, transparent)"], ["DocumentPreviewModal.vue", "border-bottom", "1px solid rgba(157, 178, 207, .12)", "1px solid color-mix(in srgb, var(--legacy-steel) 12%, transparent)"], ["DocumentPreviewModal.vue", "background", "#172a36", "var(--legacy-aqua-night)"], ["DocumentPreviewModal.vue", "color", "#8ce2bf", "var(--legacy-mint)"], ["DocumentPreviewModal.vue", "color", "#dbe5f3", "var(--legacy-tint-azure)"], ["DocumentPreviewModal.vue", "background", "rgba(106, 140, 255, .08)", "color-mix(in srgb, var(--legacy-periwinkle-strong) 8%, transparent)"], ["ChartViewer.vue", "background", "rgba(17, 27, 44, .92)", "color-mix(in srgb, var(--legacy-night-2) 92%, transparent)"], ["ChartViewer.vue", "border", "1px solid rgba(157, 178, 207, .16)", "1px solid color-mix(in srgb, var(--legacy-steel) 16%, transparent)"], ["ChartViewer.vue", "box-shadow", "0 14px 34px rgba(0, 0, 0, .18)", "0 14px 34px color-mix(in srgb, var(--legacy-void) 18%, transparent)"], ["ChartViewer.vue", "box-shadow", "0 18px 42px rgba(0, 0, 0, .28)", "0 18px 42px color-mix(in srgb, var(--legacy-void) 28%, transparent)"], ["ChartViewer.vue", "border-bottom", "1px solid rgba(157, 178, 207, .12)", "1px solid color-mix(in srgb, var(--legacy-steel) 12%, transparent)"], ["ChartViewer.vue", "color", "#f0f4fb", "var(--ink)"], ["ChartViewer.vue", "color", "#9eacc1", "var(--legacy-ink-steel)"], ["ChartViewer.vue", "background", "rgba(106, 140, 255, .14)", "color-mix(in srgb, var(--legacy-periwinkle-strong) 14%, transparent)"], ["ChartViewer.vue", "color", "#8ea8ff", "var(--legacy-periwinkle)"], ["ChartViewer.vue", "background", "#fff", "var(--legacy-paper)"], ["ChartViewer.vue", "background", "rgba(3, 7, 16, .82)", "color-mix(in srgb, var(--legacy-veil) 82%, transparent)"], ["ChartViewer.vue", "border", "1px solid rgba(255,255,255,0.25)", "1px solid color-mix(in srgb, var(--legacy-paper) 25%, transparent)"], ["ChartViewer.vue", "background", "rgba(255,255,255,0.1)", "color-mix(in srgb, var(--legacy-paper) 10%, transparent)"], ["ChartViewer.vue", "color", "#f0f4fb", "var(--ink)"], ["ChartViewer.vue", "background", "rgba(255,255,255,0.2)", "color-mix(in srgb, var(--legacy-paper) 20%, transparent)"], ["ChartViewer.vue", "box-shadow", "0 20px 60px rgba(0,0,0,0.3)", "0 20px 60px color-mix(in srgb, var(--legacy-void) 30%, transparent)"], ["ChartViewer.vue", "color", "#9eacc1", "var(--legacy-ink-steel)"], ["ChartViewer.vue", "color", "#f0f4fb", "var(--ink)"], ["ChartViewer.vue", "border", "1px solid rgba(142, 168, 255, .45)", "1px solid color-mix(in srgb, var(--legacy-periwinkle) 45%, transparent)"], ["ChartViewer.vue", "background", "rgba(106, 140, 255, .14)", "color-mix(in srgb, var(--legacy-periwinkle-strong) 14%, transparent)"], ["ChartViewer.vue", "color", "#8ea8ff", "var(--legacy-periwinkle)"], ["ChartViewer.vue", "background", "rgba(106, 140, 255, .26)", "color-mix(in srgb, var(--legacy-periwinkle-strong) 26%, transparent)"], ["ChartViewer.vue", "color", "#f0f4fb", "var(--ink)"]]
const DELETED = [["DocPanel.vue", "background", "#e8ecf1", ".badge"], ["DocPanel.vue", "background", "rgba(255,255,255,0.4)", ".drop-zone"], ["DocPanel.vue", "background", "rgba(64,158,255,0.04)", ".drop-zone.drag"], ["DocPanel.vue", "background", "#f5f7fa", ".doc-open-btn:hover"], ["DocPanel.vue", "color", "#409eff", ".doc-open-btn:hover"], ["DataPanel.vue", "background", "#d0d5dd", ".data-panel::-webkit-scrollbar-thumb"], ["DataPanel.vue", "background", "linear-gradient(135deg, #10b981, #059669)", ".upload-btn"], ["DataPanel.vue", "color", "#fff", ".upload-btn"], ["DataPanel.vue", "background", "#a7f3d0", ".upload-btn.loading"], ["DataPanel.vue", "background", "#fff", ".data-action-btn"], ["DataPanel.vue", "border-color", "#10b981", ".data-action-btn:hover"], ["DataPanel.vue", "color", "#047857", ".data-action-btn:hover"], ["DataPanel.vue", "color", "#67c23a", ".col-missing.ok"], ["DataPanel.vue", "background", "rgba(103,194,58,0.08)", ".col-missing.ok"], ["DataPanel.vue", "background", "rgba(230,162,60,0.08)", ".col-missing.warn"], ["DataPanel.vue", "color", "#f56c6c", ".col-missing.bad"], ["DataPanel.vue", "background", "rgba(245,108,108,0.08)", ".col-missing.bad"]]
const TOKENS = {"--legacy-void": {"literal": "#000000", "existing": false, "n": 12}, "--legacy-ink-mid": {"literal": "#606266", "existing": false, "n": 5}, "--legacy-line": {"literal": "#d0d5dd", "existing": false, "n": 4}, "--legacy-paper": {"literal": "#ffffff", "existing": false, "n": 18}, "--legacy-ep-danger": {"literal": "#f56c6c", "existing": false, "n": 9}, "--legacy-ink-strong": {"literal": "#303133", "existing": false, "n": 7}, "--legacy-ink-faint": {"literal": "#c0c4cc", "existing": false, "n": 3}, "--legacy-ink-soft": {"literal": "#909399", "existing": false, "n": 8}, "--legacy-ep-primary": {"literal": "#409eff", "existing": false, "n": 10}, "--legacy-line-pale": {"literal": "#ebeef5", "existing": false, "n": 1}, "--legacy-ep-success": {"literal": "#67c23a", "existing": false, "n": 3}, "--legacy-ep-success-line": {"literal": "#b3e19d", "existing": false, "n": 1}, "--legacy-ep-danger-line": {"literal": "#fab6b6", "existing": false, "n": 2}, "--legacy-fill-mist": {"literal": "#edf2f7", "existing": false, "n": 1}, "--legacy-fill": {"literal": "#f0f2f5", "existing": false, "n": 2}, "--legacy-aqua-bright": {"literal": "#35d3c8", "existing": false, "n": 9}, "--legacy-periwinkle-strong": {"literal": "#6a8cff", "existing": false, "n": 9}, "--legacy-periwinkle-pale": {"literal": "#b5c4ff", "existing": false, "n": 2}, "--legacy-coral-soft": {"literal": "#ffabb2", "existing": false, "n": 1}, "--red": {"literal": "#ee6d78", "existing": true, "n": 2}, "--legacy-emerald": {"literal": "#10b981", "existing": false, "n": 5}, "--legacy-emerald-deeper": {"literal": "#047857", "existing": false, "n": 2}, "--legacy-fill-cool": {"literal": "#edf0f2", "existing": false, "n": 1}, "--legacy-emerald-300": {"literal": "#6ee7b7", "existing": false, "n": 1}, "--legacy-emerald-pale": {"literal": "#f0fdf4", "existing": false, "n": 2}, "--legacy-emerald-mist": {"literal": "#ecfdf5", "existing": false, "n": 1}, "--legacy-emerald-100": {"literal": "#dcfce7", "existing": false, "n": 1}, "--legacy-ink-graphite": {"literal": "#374151", "existing": false, "n": 1}, "--legacy-ink-mute": {"literal": "#9ca3af", "existing": false, "n": 1}, "--legacy-line-mute": {"literal": "#d1d5db", "existing": false, "n": 1}, "--legacy-ink-graphite-deep": {"literal": "#4b5563", "existing": false, "n": 1}, "--legacy-fill-plain": {"literal": "#f5f5f5", "existing": false, "n": 1}, "--legacy-ep-orange": {"literal": "#e6a23c", "existing": false, "n": 1}, "--legacy-line-hair": {"literal": "#e4e7ed", "existing": false, "n": 1}, "--legacy-steel": {"literal": "#9db2cf", "existing": false, "n": 9}, "--legacy-aqua": {"literal": "#1a9f9a", "existing": false, "n": 1}, "--legacy-night": {"literal": "#061016", "existing": false, "n": 1}, "--green": {"literal": "#65d49a", "existing": true, "n": 1}, "--amber": {"literal": "#e4a24a", "existing": true, "n": 1}, "--legacy-coral": {"literal": "#ff9da5", "existing": false, "n": 2}, "--legacy-veil": {"literal": "#030710", "existing": false, "n": 2}, "--legacy-night-2": {"literal": "#111b2c", "existing": false, "n": 2}, "--ink": {"literal": "#f0f4fb", "existing": true, "n": 5}, "--legacy-ink-steel": {"literal": "#9eacc1", "existing": false, "n": 5}, "--legacy-tint-azure": {"literal": "#dbe5f3", "existing": false, "n": 2}, "--legacy-periwinkle-mid": {"literal": "#aabdff", "existing": false, "n": 1}, "--legacy-night-1": {"literal": "#0b1220", "existing": false, "n": 1}, "--legacy-slate-dark": {"literal": "#525659", "existing": false, "n": 1}, "--legacy-tint-azure-soft": {"literal": "#e7eef9", "existing": false, "n": 1}, "--legacy-night-3": {"literal": "#0d1728", "existing": false, "n": 1}, "--legacy-night-4": {"literal": "#142035", "existing": false, "n": 1}, "--legacy-aqua-night": {"literal": "#172a36", "existing": false, "n": 1}, "--legacy-mint": {"literal": "#8ce2bf", "existing": false, "n": 1}, "--legacy-periwinkle": {"literal": "#8ea8ff", "existing": false, "n": 3}}
const LIGHT_TOKENS = ["--legacy-paper", "--legacy-line-pale", "--legacy-fill-mist", "--legacy-fill", "--legacy-fill-cool", "--legacy-fill-plain"]
const LIGHT_BG_SITES = 18

const styleByFile = new Map(FILES.map((f) => [f, readStyle(f)]))
/** 色值属性里仍然带颜色的值的形状（用来区分「裸字面量」与「token 名里带色名」这两种告警） */
const keywordShapedDecls = () => {
  const out = []
  for (const [file, css] of styleByFile) {
    for (const prop of COLOR_PROPS) {
      for (const value of declsOf(css, prop)) {
        if (!KEYWORD_RE.test(value)) continue
        out.push([file, prop, value])
      }
    }
  }
  return out.sort()
}

describe('R151 · 色值台账（四块面板）', () => {
  it('台账不是空转：169 枚替换 / 17 枚删除 / 54 枚 token，四份源码都真读到了', () => {
    expect(LEDGER.length).toBe(169)
    expect(DELETED.length).toBe(17)
    expect(Object.keys(TOKENS).length).toBe(54)
    for (const f of FILES) expect(styleByFile.get(f).length, f + ' 的 <style> 没读到').toBeGreaterThan(500)
    expect(new Set(LEDGER.map((r) => r[0])).size).toBe(4)
  })

  it('每一枚替换都有反证：新声明在位，旧字面量在该属性上绝迹', () => {
    for (const [file, prop, old, now] of LEDGER) {
      const vals = declsOf(styleByFile.get(file), prop)
      expect(vals, file + ' 的 ' + prop + ' 里找不到已债后的值：' + now).toContain(now)
      expect(vals, file + ' 的 ' + prop + ' 还留着裸值 ' + old + '（色值债复活）').not.toContain(old)
    }
  })

  it('复用主题的 token 只有 --ink/--red/--green/--amber 四枚，其余全是本单新增的 --legacy-*', () => {
    const reused = Object.entries(TOKENS).filter(([, m]) => m.existing).map(([n]) => n).sort()
    expect(reused).toEqual(['--amber', '--green', '--ink', '--red'])
    for (const [name, meta] of Object.entries(TOKENS)) {
      if (!meta.existing) expect(name, '本单新增 token 必须带 --legacy- 前缀，好让重上色工单一网打尽').toMatch(/^--legacy-/)
    }
  })

  it('新增的 --legacy-* token 值 == 被它替掉的那枚字面量（改值就是改视觉，判据④不许）', () => {
    const theme = readFileSync(join(SRC, 'assets', 'theme.css'), 'utf8')
    for (const [name, meta] of Object.entries(TOKENS)) {
      const at = theme.indexOf(name + ':')
      expect(at, name + ' 不在 theme.css 里').toBeGreaterThan(-1)
      if (meta.existing) continue
      const value = squeeze(theme.slice(at + name.length + 1).split(';')[0].split('/*')[0])
      expect(value.toLowerCase(), name + ' 的值不再是 ' + meta.literal + '：这一改就把面板颜色挪了位')
        .toBe(meta.literal.toLowerCase())
    }
  })

  it('token 名不许撞 stylelint 的裸关键字正则（本单实测：var(--legacy-ep-red) 也挨告警）', () => {
    // 只管本单新增的 --legacy-*：主题既有 token（--red / --green / --blue）的名字不归我改，
    // 它们撞正则的那 7 处正是上面「残余告警」钉住的那批。
    const theme = readFileSync(join(SRC, 'assets', 'theme.css'), 'utf8')
    const legacy = [...theme.matchAll(/(--legacy-[\w-]+)\s*:/g)].map((m) => m[1])
    expect(legacy.length, 'theme.css 里一枚 --legacy-* 都没扫到，这条断言就是空转').toBeGreaterThanOrEqual(50)
    for (const name of legacy) {
      expect(KEYWORD_RE.test(name), name + ' 这个名字里带裸色名，引用它会白挨一枚 disallowed-list 告警').toBe(false)
    }
  })

  it('17 枚可证死声明已删除，且覆盖它们的那条仍然在位（不许抄回来）', () => {
    for (const [file, prop, old, selector] of DELETED) {
      const vals = declsOf(styleByFile.get(file), prop)
      expect(vals, selector + ' 的 ' + prop + ': ' + old + ' 在 ' + file + ' 里复活了').not.toContain(old)
      expect(vals.length, file + ' 的 ' + prop + ' 一条都不剩：覆盖被删死的死的那条也不见了').toBeGreaterThan(0)
    }
  })

  it('四块面板的 <style> 里不许再有任何裸 hex / rgb() / rgba() / hsl() / hsla()', () => {
    for (const [file, css] of styleByFile) {
      expect(HEX_RE.test(css), file + ' 又出现了裸 hex').toBe(false)
      expect(COLOR_FN_RE.test(css), file + ' 又出现了裸 rgb/rgba/hsl/hsla').toBe(false)
      expect(MASKED_VAR_RE.test(css), file + ' 出现了 var(--x, 兜底)：design-tokens 闸门 MASKED_CEILING=0 明确拒绝').toBe(false)
    }
  })

  it('残余告警只准是「token 名里带色名」这一类，且数量只准降（本单收在 7 枚）', () => {
    const shaped = keywordShapedDecls()
    expect(shaped.length, '色值属性里出现了新的裸色值：' + JSON.stringify(shaped)).toBeLessThanOrEqual(7)
    for (const [file, prop, value] of shaped) {
      const bare = value.replace(/var\(\s*--[\w-]+\s*\)/g, '').replace(/color-mix\(in srgb,[^)]*\)/g, '')
      expect(HEX_RE.test(value) || COLOR_FN_RE.test(value), file + ' ' + prop + ' 仍有裸函数/hex：' + value).toBe(false)
      expect(bare.trim(), file + ' ' + prop + ' 里除了 var() 还有别的东西：' + value).toBe('')
    }
  })

  it('浅色卡片棘轮：背景仍是浅色板的面板位只剩 18 处，只准降（判据②的续账口）', () => {
    let n = 0
    for (const [file, css] of styleByFile) {
      for (const prop of ['background', 'background-color']) {
        for (const value of declsOf(css, prop)) {
          if (LIGHT_TOKENS.some((t) => value.includes('var(' + t + ')'))) n += 1
        }
      }
    }
    expect(n).toBeLessThanOrEqual(LIGHT_BG_SITES)
    expect(n, '一处浅色卡片背景都不剩了？那这条棘轮该删掉而不是留着空转').toBeGreaterThan(0)
  })

  it('lint 预算已按实际清债量下调，且不得低于四块面板的残差', () => {
    const pkg = JSON.parse(readFileSync(join(SRC, '..', 'package.json'), 'utf8'))
    const m = /--max-warnings=(\d+)/.exec(pkg.scripts['lint:colors'])
    expect(m, 'package.json 的 lint:colors 里得留着 --max-warnings=N').not.toBeNull()
    const budget = Number(m[1])
    expect(budget, '棘轮只准降：本单从 334 起步').toBeLessThan(334)
    expect(budget).toBeGreaterThanOrEqual(7)
  })
})
