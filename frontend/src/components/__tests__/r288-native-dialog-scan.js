/**
 * R288 · G15 量具：原生对话框扫描算法（唯一事实源）
 *
 * 判据原文：frontend/src/** 里 window.confirm / confirm( / alert( / prompt( 命中数必须为 0。
 * 这一枚模块只放着「怎么数」，不放结论；同一份实现被两边消费：
 *   · tmp/r288-native-dialogs.mjs（施工脚本，现取改前改后两个数）；
 *   · r288-native-buttons.test.js（守卫钉，把「0」钉成一跑就红的门）。
 * 量具只有一枚（照 r288-native-button-scan.js 的手法）：改了数法必须同时改脚本与用例。
 *
 * 数法定死四件事：
 *   1 扫描面 = src 目录下所有 .vue 与 .js，**不豁免任何目录**：判据点名的就是整个 src，
 *      这里开一个豁免口，下一单就能多开一个，最后「0」就退化成「没人看的地方不算」。
 *   2 先剥注释：模板注释、块注释、整行注释。本仓既有用例（ArtifactList.vue 第 19 行、
 *      DataPanel.vue 第 70 行）要把「这里不用原生弹窗」写在注释里，那是要留着的好话，
 *      不是欠账。
 *   3 再剥单引号串与反引号串：artifact-list.test.js 与 r268-chat-panel-shell.test.js
 *      靠 not.toContain('window.confirm') 这种断言禁它，测试标题还得把这四个字画在屏上
 *      —— 那些都不是调用点。**双引号串刻意不剥**：.vue 模板里 @click="confirm(...)"
 *      这种双引号包起来的就是要执行的代码，剥了等于在最想查的那一层留一个洞。
 *   4 window.X 一律算（原生对话框的完整写法），裸 X( 才算：前置不许有 . 单词字符或 $，
 *      所以 renewAlert(、dialog.prompt( 这类不误伤。
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative, sep } from 'node:path'

/** 剥掉不执行的文本：注释、单引号串、反引号串。 */
export const stripNonCode = (text) => text
  .replace(/<!--[\s\S]*?-->/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .split('\n')
  .filter(line => !/^\s*\/\//.test(line))
  .join('\n')
  .replace(/'[^']*'/g, "''")
  .replace(/`[^`]*`/g, '``')

/** 原生对话框调用点：window 全写法 + 裸函数写法。 */
export const NATIVE_DIALOG_PATTERN = /(?:window\.(?:confirm|alert|prompt)|(?<![.\w$])(?:confirm|alert|prompt)\s*\()/g

/** 一份源码文本里的命中明细（带行号，红了要能一眼指到那一行）。 */
export function findNativeDialogs(source) {
  const hits = []
  stripNonCode(source).split('\n').forEach((line, index) => {
    for (const match of line.matchAll(NATIVE_DIALOG_PATTERN)) {
      hits.push({ line: index + 1, text: match[0], raw: line.trim() })
    }
  })
  return hits
}

/** 这个相对路径要不要进扫描面：src 下所有 .vue 与 .js，一个目录都不豁免。 */
export const isScanTarget = (relPath) => /\.(vue|js)$/.test(relPath.split(sep).join('/'))

/** 从 src 根扫出全部命中，按文件、行号排序。 */
export function scanNativeDialogs(srcRoot) {
  const out = []
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name)
      const rel = relative(srcRoot, full).split(sep).join('/')
      if (entry.isDirectory()) { walk(full); continue }
      if (!isScanTarget(rel)) continue
      for (const hit of findNativeDialogs(readFileSync(full, 'utf8'))) {
        out.push({ file: rel, ...hit })
      }
    }
  }
  walk(srcRoot)
  return out.sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line)
}
