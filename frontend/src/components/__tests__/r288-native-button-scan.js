/**
 * R288 · G20 量具：原生 button 扫描算法（唯一事实源）
 *
 * 这一枚模块只放着「怎么数」，不放结论。同一份实现被两边消费：
 *   · tmp/r288-native-buttons.mjs（施工脚本，node 直接跑，用来现取计数表）；
 *   · r288-native-buttons.test.js（守卫钉，把每文件残值与总数钉成只减不增的棘轮）。
 * 量具只有一枚：改了数法就必须同时改脚本与用例，两边不可能各自漂移 ——
 * 照 R278 的手法，计数表不许「脚本一套算法、用例另一套算法」。
 *
 * 数法定死三件事：
 *   1 扫描面 = src 目录下所有 .vue，排除测试件目录与原语自身（components/ui 整棵：
 *      UiButton 的模板里当然有原生 button，把它算进欠账等于把还债本身记成债）。
 *   2 注释先剥再数：模板注释、块注释、行注释里的 button 没画上屏，不算欠账
 *      （与 r237-r49-index-face.test.js 的 codeOnly 同一条剥法）。
 *   3 只数【开标签】：左尖括号 button 之后必须紧跟空白、斜杠或右尖括号，
 *      所以 UiButton 不会误命中，而一枚跨行书写的开标签仍算一枚。
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative, sep } from 'node:path'

/** 剥掉不画上屏的注释：模板注释与块注释、行注释。 */
export const stripComments = (text) => text
  .replace(/<!--[\s\S]*?-->/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .split('\n')
  .filter(line => !/^\s*\/\//.test(line))
  .join('\n')

/** 一枚 .vue 源文件里的原生 button 开标签数。 */
export const countNativeButtons = (source) => {
  const hits = stripComments(source).match(/<button(?=[\s/>])/gi)
  return hits ? hits.length : 0
}

/** 这个相对路径要不要进扫描面。 */
export const isScanTarget = (relPath) => {
  const normalized = relPath.split(sep).join('/')
  if (!normalized.endsWith('.vue')) return false
  if (normalized.includes('__tests__/')) return false
  if (normalized.startsWith('components/ui/')) return false
  return true
}

/** 从 src 根扫出欠账表，零命中的文件不进表；按命中数降序、同数按路径升序。 */
export function scanNativeButtons(srcRoot) {
  const out = []
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name)
      const rel = relative(srcRoot, full).split(sep).join('/')
      if (entry.isDirectory()) { walk(full); continue }
      if (!isScanTarget(rel)) continue
      const count = countNativeButtons(readFileSync(full, 'utf8'))
      if (count > 0) out.push({ file: rel, count })
    }
  }
  walk(srcRoot)
  return out.sort((a, b) => b.count - a.count || a.file.localeCompare(b.file))
}
