/**
 * R538 · 前端三枚手抄后端坐标改派生：判据只有一条——注释里的坐标 == 后端现取坐标
 *
 * 病（R534 现取，本单在基点 81784da 复核成立）：注释里抄着一份会过期的后端行号，后端一挪它就撒谎。
 * 三处今天全在撒谎，本单一并改口，并把「改口」钉成派生而不是快照：
 *   notifications.js 第 26 行写的是 notifications.py 的第 171／194／200 行——三条路由今天不在那三行
 *   DocPanel.vue 第 103 行写的是 chat.py 的第 3933 行——那一句 Form 默认值今天不在那一行
 *   DocPanel.vue 第 112 行抄的档位映射少一枚角色——后端那枚 ROLE_CLEARANCE 今天不止三枚
 * 同一处注释里还带着第四枚坐标（DocPanel.vue 第 114 行词表 core 那一行），一并入账、一并现读。
 *
 * 对账姿势与 r416 / r427 同一口径，四组断言缺一组都不算收口：
 *   甲 逐枚等值：注释【声称】的数字从前端工作树现读，后端【真位置】在 git show HEAD: 的真源里按锚串
 *      当场推导——工作树可能停在分支点，拿它对账等于永远绿的假绿。锚串必须唯一命中，多一枚就抛：
 *      那一枚数字在真源里成了歧义，这条账不该绿。
 *   乙 旧值不许抄回来：DEAD 表里那几段历史形状，逐段在它所在的那枚前端件里 0 命中。
 *   丙 注释说的话必须真是后端的事：三枚导出常量的路径逐枚等于后端那三条路由的路径，「三条路由／
 *      一条读，两条写」由装饰器当场数出来；四枚引用本身仍要在位——引用被删＝现读落空＝红，
 *      不许降级成 skip。
 *   丁 本件不许写第二份坐标：除 DEAD 那一段，本件源码里不许出现任何后端 path:数字——把数字写进
 *      断言的钉叫快照，不叫派生钉（判据②）。
 *
 * 反证怎么算红（≥3 把，逐把当场红）：
 *   刀一 任一坐标改回旧值 => 甲组那一枚「声称 == 推导」红，乙组同时红（DEAD 短语回到件里）；
 *   刀二 从注释里删掉那枚角色 => 甲组档位映射红（键集合与每键档位都要逐枚对上），
 *        乙组那条三档历史形状同时红；
 *   刀三 把某枚坐标挪到别的行（同一条路由的下一行也算）=> 甲组该槽位红；
 *   刀四 把引用整句删掉躲检查 => 丙组「四枚引用仍在原位」红，或 claim 现读落空直接抛；
 *   刀五 后端自己挪了行而不改注释 => 甲组红（这正是要的形状：宁可红，不撒谎）。
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const NOTIFICATIONS_JS = 'frontend/src/lib/notifications.js'
const DOC_PANEL = 'frontend/src/components/DocPanel.vue'

/** 注释里的写法 -> 仓内真源。后端只在 git show HEAD: 那一层取数，本件不读它的工作树。 */
const BACKEND = {
  notifications: 'app/api/v1/notifications.py',
  chat: 'app/api/v1/chat.py',
  rbac: 'app/common/rbac.py',
  policy: 'app/common/policy.py',
}

/* DEAD-BEGIN 历史旧值：本件里唯一允许出现后端 path:数字 的一段，用途只有「抄回来就红」这一把刀。 */
const DEAD = [
  { file: NOTIFICATIONS_JS, phrase: 'notifications.py:171' },
  { file: NOTIFICATIONS_JS, phrase: ':194' },
  { file: NOTIFICATIONS_JS, phrase: ':200' },
  { file: DOC_PANEL, phrase: 'chat.py:3933' },
  { file: DOC_PANEL, phrase: '{staff:1, manager:2, admin:3}' },
]
/* DEAD-END */

const workText = repoPath => readFileSync(new URL('../../../../' + repoPath, import.meta.url), 'utf8').replace(/\r\n/g, '\n')

const CACHE = new Map()

function headLines(repoPath) {
  if (CACHE.has(repoPath)) return CACHE.get(repoPath)
  let text
  try {
    text = execFileSync('git', ['show', 'HEAD:' + repoPath], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
  } catch (cause) {
    throw new Error('读不到真源 HEAD:' + repoPath + '（git show 失败：' + cause.message + '）。行号对账不许降级成 skip。')
  }
  if (!String(text).trim()) throw new Error('git show HEAD:' + repoPath + ' 返回空内容，无法对账。')
  const lines = String(text).replace(/\r\n/g, '\n').split('\n')
  CACHE.set(repoPath, lines)
  return lines
}

/** 当场推导：锚串在真源里必须唯一命中，返回那一行的 1-based 行号、原文与捕获。找不到或不唯一就抛。 */
function derive(repoPath, pattern, label) {
  const lines = headLines(repoPath)
  const re = new RegExp(pattern)
  const hits = []
  lines.forEach((line, index) => {
    if (re.test(line)) hits.push(index + 1)
  })
  if (hits.length === 0) throw new Error('现读推导落空：' + label + '（HEAD:' + repoPath + ' 找 /' + pattern + '/ 零命中）')
  if (hits.length > 1) {
    throw new Error('现读推导不唯一：' + label + '（HEAD:' + repoPath + ' 里 /' + pattern + '/ 命中第 ' + hits.join('、') + ' 行——注释声称的那一枚数字成了歧义）')
  }
  const text = lines[hits[0] - 1]
  const hit = new RegExp(pattern).exec(text)
  return { line: hits[0], text: text.trim(), groups: hit ? Array.from(hit.slice(1)) : [] }
}

/** 注释声称的坐标：读工作树（这一单要治的就是它）。抠不到就抛——把引用删了不等于把坐标修对。 */
function claim(file, pattern, label) {
  const hit = new RegExp(pattern).exec(workText(file))
  if (!hit) throw new Error('注释里读不到那枚引用：' + label + '（' + file + ' 找 /' + pattern + '/）——删引用躲检查不算修好坐标。')
  return hit
}

/** 档位映射解析：后端的 "staff": 1 与注释里的 staff:1 走同一条式子，不各抄一份。 */
function parseClearance(text) {
  const map = new Map()
  for (const hit of String(text).matchAll(/["']?([A-Za-z_][A-Za-z0-9_]*)["']?\s*:\s*(\d+)/g)) {
    map.set(hit[1], Number(hit[2]))
  }
  if (!map.size) throw new Error('档位映射解析落空（这一段里没有 role:level）：' + text)
  return map
}

/* ------------------------------------------------------------- 现读推导（甲组用） */

const ROUTE_SPECS = [
  { label: '那一条读（get）', pattern: "^@router\\.get\\('([^']+)'\\)$" },
  { label: '第一条写·标已读（post 尾上 read）', pattern: "^@router\\.post\\('([^']+/read)'\\)$" },
  { label: '第二条写·划掉（post 尾上 dismiss）', pattern: "^@router\\.post\\('([^']+/dismiss)'\\)$" },
]
const ROUTES = ROUTE_SPECS.map(spec => {
  const hit = derive(BACKEND.notifications, spec.pattern, spec.label)
  return { label: spec.label, path: hit.groups[0], line: hit.line }
})
const CLAIM_ROUTE_RAW = claim(NOTIFICATIONS_JS, 'notifications\\.py:(\\d+)\\s*/\\s*:(\\d+)\\s*/\\s*:(\\d+)', '三条路由的坐标')
const CLAIM_ROUTES = CLAIM_ROUTE_RAW.slice(1, 4).map(Number)

const CLAIM_FORM = claim(DOC_PANEL, 'classification: int = Form\\((\\d+)\\)（app/api/v1/chat\\.py:(\\d+)）', '后端那一句 Form 默认值')
const DERIVED_FORM = derive(BACKEND.chat, '^\\s*classification: int = Form\\((\\d+)\\),?\\s*$', '上传签名里的 classification Form 默认值')

const CLAIM_RBAC = claim(DOC_PANEL, 'app/common/rbac\\.py:(\\d+)\\s*的\\s*\\*\\s*ROLE_CLEARANCE\\s*=\\s*\\{([^}]*)\\}', 'ROLE_CLEARANCE 的出处与注释里那份抄件')
const DERIVED_RBAC = derive(BACKEND.rbac, '^ROLE_CLEARANCE\\s*=\\s*\\{[^}]*\\}\\s*$', '角色到密级档位的映射')

const CLAIM_CORE = claim(DOC_PANEL, '第 (\\d+) 档（policy\\.py:(\\d+) core）', '词表里 core 那一档的出处')
const DERIVED_CORE = derive(BACKEND.policy, '^\\s*"core":\\s*(\\d+),?\\s*$', '词表里 core 那一行')

/* ------------------------------------------------------------- 路由枚举（丙组用） */

function enumeratedRoutes() {
  const out = []
  headLines(BACKEND.notifications).forEach((line, index) => {
    const hit = /^@router\.(get|post|put|patch|delete)\('([^']+)'\)$/.exec(line)
    if (hit) out.push({ line: index + 1, method: hit[1], path: hit[2] })
  })
  return out
}
const ROUTE_LIST = enumeratedRoutes()

const CONSTANT_NAMES = ['INBOX_PATH', 'READ_ACTION_PATH', 'DISMISS_ACTION_PATH']

function exportedPath(name) {
  const hit = new RegExp('^export const ' + name + " = '([^']+)'", 'm').exec(workText(NOTIFICATIONS_JS))
  if (!hit) throw new Error('前端那枚导出常量读不到了：' + name + '（第 26 行的注释说的就是这三枚路径）')
  return hit[1]
}
const EXPORTED_PATHS = CONSTANT_NAMES.map(exportedPath)

/* ------------------------------------------------------------------- 断言本体 */

describe('R538甲 · 四枚坐标逐枚等值：注释声称的数字必须等于当场推导', () => {
  it('三条路由的坐标逐枚 == 后端装饰器所在的行（' + ROUTES.map(route => route.label + ' 第 ' + route.line + ' 行').join(' / ') + '）', () => {
    expect(CLAIM_ROUTES, '注释里三条路由的坐标抠出来不是三枚：第 26 行那句话的形状变了，本件要一起改口').toHaveLength(3)
    CLAIM_ROUTES.forEach((cited, index) => {
      expect(cited, '注释写 ' + cited + '，后端现读推导是 ' + ROUTES[index].line + '（' + ROUTES[index].label + '）：行号漂了，注释必须跟着改口')
        .toBe(ROUTES[index].line)
    })
  })

  it('chat.py 坐标 == Form 默认值那一行，且注释引的那一句默认值 == 后端真默认值', () => {
    expect(Number(CLAIM_FORM[2]), '注释写 chat.py 第 ' + CLAIM_FORM[2] + ' 行，现读推导是第 ' + DERIVED_FORM.line + ' 行：那一句 Form 默认值今天不在注释说的那一行')
      .toBe(DERIVED_FORM.line)
    expect(CLAIM_FORM[1], '注释引的后端默认值是 ' + CLAIM_FORM[1] + '，后端那一句今天写的是 ' + DERIVED_FORM.groups[0] + '：默认值换了位，这句注释得改口')
      .toBe(DERIVED_FORM.groups[0])
    expect(DERIVED_FORM.text, '推导到的那一行不再是 Form 默认值那一句：' + DERIVED_FORM.text).toContain('classification: int = Form(')
  })

  it('rbac.py 坐标 == ROLE_CLEARANCE 那一行，且注释那份抄件逐枚等于后端那一份（角色一枚不多、一枚不少）', () => {
    expect(Number(CLAIM_RBAC[1]), '注释写 rbac.py 第 ' + CLAIM_RBAC[1] + ' 行，现读推导是第 ' + DERIVED_RBAC.line + ' 行：ROLE_CLEARANCE 换了行，注释没跟上')
      .toBe(DERIVED_RBAC.line)
    const claimed = parseClearance(CLAIM_RBAC[2])
    const truth = parseClearance(DERIVED_RBAC.text)
    expect([...claimed.keys()].sort(), '注释抄的角色名单与后端 ROLE_CLEARANCE 的键集合不等：后端 ' + [...truth.keys()].join('/') + '，注释 ' + [...claimed.keys()].join('/'))
      .toEqual([...truth.keys()].sort())
    for (const [role, level] of truth) {
      expect(claimed.get(role), '后端 ' + role + ' 的档位是 ' + level + '，注释写的是 ' + claimed.get(role) + '：这一档抄错了')
        .toBe(level)
    }
  })

  it('policy.py 坐标 == 词表 core 那一行，且注释说的「第 N 档」的 N == 后端那一行的档位值', () => {
    expect(Number(CLAIM_CORE[2]), '注释写 policy.py 第 ' + CLAIM_CORE[2] + ' 行，现读推导是第 ' + DERIVED_CORE.line + ' 行：词表那一行换了位')
      .toBe(DERIVED_CORE.line)
    expect(Number(CLAIM_CORE[1]), '注释说 core 是第 ' + CLAIM_CORE[1] + ' 档，后端那一行今天写的是 ' + DERIVED_CORE.groups[0] + ' 档').toBe(Number(DERIVED_CORE.groups[0]))
    expect(DERIVED_CORE.text, '推导到的那一行不含 core：' + DERIVED_CORE.text).toContain('"core"')
  })
})

describe('R538乙 · 旧值不许抄回来：DEAD 表逐段 0 命中', () => {
  for (const dead of DEAD) {
    it(dead.file.replace('frontend/src/', '') + ' 里不许再出现 ' + dead.phrase, () => {
      expect(workText(dead.file), dead.file + ' 又写回了 ' + dead.phrase + '：要么是把旧坐标抄回来了，要么后端恰好挪回这一行——两种都得先取证再改口').not.toContain(dead.phrase)
    })
  }
})

describe('R538丙 · 注释说的话必须真是后端的事，引用本身不许删', () => {
  it('后端今天确实只有三条路由，且「一条读，两条写」当场数得出来', () => {
    const face = ROUTE_LIST.map(route => route.method.toUpperCase() + ' ' + route.path).join(' / ')
    expect(ROUTE_LIST, '第 26 行那句「三条路由」对不上后端今天的路由数（' + face + '）：加一条减一条都要先把这句注释改口').toHaveLength(3)
    expect(ROUTE_LIST.map(route => route.line), '枚举出来的三条路由与甲组逐枚推导的行号不一致：' + ROUTE_LIST.map(route => route.line).join('、'))
      .toEqual(ROUTES.map(route => route.line))
    expect(ROUTE_LIST.filter(route => route.method === 'get'), '「一条读」数出来不是 1 条：' + face).toHaveLength(1)
    expect(ROUTE_LIST.filter(route => route.method !== 'get'), '「两条写」数出来不是 2 条：' + face).toHaveLength(2)
  })

  it('第 26 行管着的三枚导出常量，路径逐枚等于后端那三条路由的路径', () => {
    EXPORTED_PATHS.forEach((value, index) => {
      expect(value, '前端 ' + CONSTANT_NAMES[index] + ' 发的是 ' + value + '，后端那一条是 ' + ROUTES[index].path + '：注释里那三枚行号指的路由已经和界面对不上了')
        .toBe(ROUTES[index].path)
    })
  })

  it('四枚引用都还在原位：删掉引用不等于修好坐标', () => {
    const sites = [
      { label: 'notifications.js 三条路由', text: CLAIM_ROUTE_RAW[0], wants: ['notifications.py'] },
      { label: 'DocPanel 的 chat.py 出处', text: CLAIM_FORM[0], wants: ['app/api/v1/chat.py'] },
      { label: 'DocPanel 的 rbac.py 出处', text: CLAIM_RBAC[0], wants: ['app/common/rbac.py', 'ROLE_CLEARANCE'] },
      { label: 'DocPanel 的 policy.py 出处', text: CLAIM_CORE[0], wants: ['policy.py'] },
    ]
    for (const site of sites) {
      expect(site.text, site.label + ' 那处引用抠不出数字：这一单要的是把坐标改对，不是把坐标删掉').toMatch(/:\d+/)
      for (const want of site.wants) {
        expect(site.text, site.label + ' 那处引用不再点名 ' + want + '：出处丢了，行号就成了无主的数字').toContain(want)
      }
    }
  })
})

describe('R538丁 · 本件不许写第二份坐标（写死数字的钉叫快照，不叫派生钉）', () => {
  it('除 DEAD 那一段以外，本件源码里 0 处后端 path:数字', () => {
    const self = readFileSync(fileURLToPath(import.meta.url), 'utf8').replace(/\r\n/g, '\n')
    const start = self.indexOf('/* DEAD-BEGIN')
    const end = self.indexOf('/* DEAD-END')
    expect(start, 'DEAD 段的起手标记不见了：丁组失去锚，先把标记补回来').toBeGreaterThan(-1)
    expect(end, 'DEAD 段的收尾标记不见了：丁组失去锚').toBeGreaterThan(start)
    const outside = []
    for (const hit of self.matchAll(/\.py:\d+/g)) {
      if (hit.index < start || hit.index >= end) outside.push(self.slice(hit.index, hit.index + 28).split('\n')[0].trim())
    }
    expect(outside, '本件在 DEAD 段以外写死了后端坐标（' + outside.join(' ｜ ') + '）：判据②不许——行号与档位必须现读派生').toHaveLength(0)
  })
})