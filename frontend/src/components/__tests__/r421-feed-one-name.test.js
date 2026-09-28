/**
 * R421 · 喂料屏不许再长出第二枚屏名：主标题位、源码文案、整屏普查、射程守门、两份清单互查，五组独立腿
 *
 * 要治的病（总控 09-28 派工，接 R412 并树 `4344e6d` 之后剩下的那一格）：
 *   这一屏页内主标题已被 R412 换成 meta.title 那一句，但同一屏上还留着三枚「知识库」，而在册那枚
 *   屏名钉（src/router/__tests__/r136-screen-names.test.js）当年只认一种画法，看不见 DocPanel 用的
 *   那一式 —— 所以「同一屏两个名字」不是再写一句钉就能了结的：得让「主标题位」这个概念本身覆盖到
 *   全仓每一格画法。R421 把 r136 的射程扩到三式（本单主货），本件是那三式之外的四格补枪。
 *
 * 与在册件的分工（各自验各自能验的，谁也不替谁背书）：
 *   r136-screen-names   三式画法逐屏对账 meta.title；一屏命中两式即红；闭合集定长。
 *   r412-one-screen-one-name  这一屏的主标题仍非空、屏名槽里不许夹标签名；整件模板结构枚数快照。
 *   本件甲  主标题【那一段区域】的全部文字字面量里只许有一枚名字 —— 与它用哪个标签无关：换成 <b>、
 *           往同一段里再塞一句、把 emoji 那一格改成名字，都当场红。r136 每式只取第一枚命中，
 *           「同一格里并排两句字」这一族它看不见；r412 丁腿看的是整件枚数快照，不是这一段说了什么。
 *   本件乙  两块面板的【源码】（剥掉注释）与渲染产物里都不许出现被退下的那枚叫法。源码那一腿管的是
 *           压根不上屏的初值与只在某个分支才露脸的兜底句 —— 那两格 SSR 首屏量不到，产物腿代替不了。
 *   本件丙  整屏（外壳加两块面板）的独立文字节点普查：别屏的屏名与被退下的那枚叫法，一枚都不许以
 *           「单独一句字」的形状站在这屏上；本屏屏名整屏只许说一次；数据标签那一格没有屏名位，也不许自己新添一枚。
 *   本件丁  射程守门：r136 画法登记处里三式的标记一枚都不许被摘掉。甲乙丙挡「这屏又长出一枚名字」，
 *           这一腿挡「钉自己缩回一种画法、从此又看不见」—— 那正是 R412 之前真实的失效方式。
 *   本件戊  两份清单互查：r136 与 r412 各抄了一份画法清单（总控裁定②留了「抽成共享词表」这条路并允许
 *           反裁，本单反裁不抽，理由在回执）。不抽的前提是这两份必须一直说的是同一件事，于是这一组钉
 *           三条：每一份都得是三式（不许两份一起缩到零来冒充相等）；两份的标记集与枚数必须相等；两枚
 *           在册件都不许改成从别处 import 画法清单 —— 真要走那条路得回台账重裁，不许顺手做掉。
 *
 * 反证（本单在 K0 影子树上实跑，逐把读数在派工回执）：
 *   刀一 只改 router/index.js 的 meta.title ⇒ 甲与 r136 ③ 一起红（页内那句是派生，不是第二份真源）；
 *   刀二 把旧叫法塞回主标题那一格 ⇒ 甲（多一枚名字字面量）、乙（源码与产物）、丙（散字）、r136 ③ 全红；
 *   刀三 把旧叫法塞回兜底句或未触发的初值 ⇒ 乙的源码腿当场红；
 *   刀四 把 feed 从 r136 的闭合集里摘掉 ⇒ r136 枚数那条红，本件丁第二条跟着红。
 *   刀五 把 r136 的画法登记处缩回两式 ⇒ 本件丁第一条红，本件戊「每一份都得是三式」同时红。
 *   刀六 只改 r412 本地那份清单（摘掉第三式）⇒ 本件戊两条都红；把 r136 改成从共享词表 import ⇒
 *        本件戊第三条红。两枚钉各自绿着而清单已经不是同一件事，就是本案治的「一枚看不见」的复发病。
 */
import { readFileSync } from "node:fs"
import { describe, expect, it } from "vitest"
import { h } from "vue"
import { parse as parseHtml } from "@vue/compiler-dom"
import { parse as parseSfc } from "@vue/compiler-sfc"
import { renderToString } from "@vue/server-renderer"
import { routes } from "../../router/index.js"
import { FEED_TABS } from "../../router/feed-tabs.js"
import DocPanel from "../DocPanel.vue"
import DataPanel from "../DataPanel.vue"

const read = rel => readFileSync(new URL(rel, import.meta.url), "utf8").replace(/\r\n/g, "\n")

/** 被裁定不作这屏名字的那一枚叫法（跟进单 G17；r412 乙腿把同一件事钉在屏名槽里）。 */
const RETIRED_APPELLATION = "知识库"

const screenRoutes = routes.filter(route => route.meta?.screen)
const titleOf = id => String(routes.find(route => String(route.name) === id).meta.title)
const FEED_TITLE = titleOf("feed")
/** 别屏的屏名：它们出现在这一屏上，就是又开了一处名字。 */
const foreignTitles = screenRoutes.map(route => String(route.meta.title)).filter(title => title !== FEED_TITLE)

/**
 * 这一屏有哪两块面板，现读那张标签表，不在本件抄第二份名单：FEED_TABS 的 component 列就是
 * FeedPanel 画进标签条的那两枚面板（同引用，不是相等），所以本件扫的文件就等于这一屏的面板。
 */
const panelFiles = [
  ["../DocPanel.vue", DocPanel],
  ["../DataPanel.vue", DataPanel],
]

it("这一屏的两块面板就是那张表的派生视图：本件扫的名单不是抄来的", () => {
  expect(FEED_TABS.map(tab => tab.component)).toEqual(panelFiles.map(entry => entry[1]))
  expect(new Set(FEED_TABS.map(tab => tab.id)).size).toBe(FEED_TABS.length)
})

// ==================== 甲 · 主标题那一段区域，只许说一枚名字 ====================

const docPanelSource = read("../DocPanel.vue")
const docPanelTemplate = () => parseHtml(parseSfc(docPanelSource, { filename: "DocPanel.vue" }).descriptor.template.content)
const HEAD_TRAIL = ["div.doc-panel", "div.panel-hd"]

const labelOf = node => {
  const classProp = (node.props || []).find(prop => prop.type === 6 && prop.name === "class")
  return node.tag + (classProp && classProp.value ? "." + classProp.value.content.trim().split(/\s+/).join(".") : "")
}

/** 一枚「名字」：至少两个字符，且带中日韩或拉丁字母 —— emoji 与符号那一格不说话。 */
const isName = text => text.trim().length >= 2 && (/[一-鿿A-Za-z]/.test(text))

/** 取 div.panel-hd 那一整棵子树：元素连同它们各自的路径，文字连同 trim 后的那一段。 */
const headRegion = () => {
  const elements = []
  const texts = []
  const step = (children, trail, inside) => {
    for (const node of children || []) {
      if (node.type === 1) {
        const next = trail.concat(labelOf(node))
        const here = inside || (next.length === HEAD_TRAIL.length && next.every((item, index) => item === HEAD_TRAIL[index]))
        if (here) elements.push({ trail: next, node })
        step(node.children, next, here)
      } else if (inside && node.type === 2 && node.content.trim()) {
        texts.push({ trail, text: node.content.trim() })
      }
    }
  }
  step(docPanelTemplate().children, [], false)
  return { elements, texts }
}

describe("R421甲 · 主标题那一段只许说一枚名字（与它用哪个标签无关）", () => {
  it("这一格今天说的话：名字一枚、emoji 一枚，计数走插值不留字面量", () => {
    const literals = headRegion().texts.map(entry => entry.text)
    expect(literals.filter(isName), "主标题那一段里出现了不止一枚名字类字面量：" + JSON.stringify(literals)).toEqual([FEED_TITLE])
    expect(literals.filter(text => !isName(text))).toEqual(["📁"])
  })

  it("那一句逐字等于现读的 meta.title：它说的是屏名，不是又编了一个名字", () => {
    expect(headRegion().texts.filter(entry => isName(entry.text)).map(entry => entry.text)).toEqual([FEED_TITLE])
  })

  it("主标题位仍只有一格在说话：改名不许靠加节点，也不许靠并排第二句", () => {
    const carriers = headRegion().elements
      .filter(entry => (entry.node.children || []).some(child => child.type === 2 && isName(child.content)))
      .map(entry => entry.trail.join(" > "))
    expect(carriers, "主标题那一段里不止一格带着文字：" + JSON.stringify(carriers)).toEqual([
      "div.doc-panel > div.panel-hd > div.panel-hd-left > strong",
    ])
  })
})

// ==================== 乙 · 源码里不许留着那枚叫法（含永不上屏的那两格） ====================

/** 剥注释：模板注释、块注释、整行 // —— 注释里叙述旧名是历史，不上屏，也不算文案。 */
const codeOnly = text => text
  .replace(/<!--[\s\S]*?-->/g, " ")
  .replace(/\/\*[\s\S]*?\*\//g, " ")
  .split("\n")
  .filter(line => !/^\s*\/\//.test(line))
  .join("\n")

describe("R421乙 · 两块面板的代码文案里不许留着那枚被退下的叫法", () => {
  for (const [rel] of panelFiles) {
    it(rel + "：剥掉注释的代码里没有那枚叫法（含未触发的初值与只在分支里露脸的兜底句）", () => {
      expect(codeOnly(read(rel)), "这一屏的代码文案里又出现了「" + RETIRED_APPELLATION + "」：它不是这屏的名字").not.toContain(RETIRED_APPELLATION)
    })
  }

  it("两块面板的渲染产物里也没有那枚叫法（SSR 首屏，不依赖任何网络回包）", async () => {
    for (const [, panel] of panelFiles) {
      expect(await renderToString(h(panel))).not.toContain(RETIRED_APPELLATION)
    }
  })

  it("屏名真源那一头同样干净：每一屏的 meta.title 里都不许带着它", () => {
    for (const route of screenRoutes) {
      expect(String(route.meta.title), "路由表里有一枚屏名带着那枚叫法").not.toContain(RETIRED_APPELLATION)
    }
  })
})

// ==================== 丙 · 整屏独立文字节点普查 ====================

/** 一屏上的「单独一句字」：>文字< 之间的整段，剥掉 server-renderer 的分段注释再 trim。 */
const textNodes = html => (html.match(/>([^<]*)</g) || [])
  .map(chunk => chunk.slice(1, -1).replace(/<!--[\s\S]*?-->/g, "").trim())
  .filter(Boolean)

describe("R421丙 · 整屏普查：别屏的名字不许以单独一句字的形状站在这屏上", () => {
  const banned = [...foreignTitles, RETIRED_APPELLATION]

  it("外壳与两块面板：外来屏名与被退下的叫法零命中", async () => {
    const feed = routes.find(route => String(route.name) === "feed")
    const screens = [await renderToString(h(feed.component))]
    for (const [, panel] of panelFiles) screens.push(await renderToString(h(panel)))
    for (const html of screens) {
      const nodes = textNodes(html)
      for (const name of banned) {
        expect(nodes, "这一屏上单独站着一句「" + name + "」：同一屏就是两处名字").not.toContain(name)
      }
    }
  })

  it("本屏的屏名整屏只许说一次：抄第二处就是开第二份真源", async () => {
    expect(textNodes(await renderToString(h(DocPanel))).filter(node => node === FEED_TITLE)).toHaveLength(1)
  })

  it("数据标签不说这屏的屏名：它没有屏名位，加一格就是同一屏长出两张名字", async () => {
    expect(textNodes(await renderToString(h(DataPanel))).filter(node => node === FEED_TITLE)).toHaveLength(0)
  })

  it("标签文案说的是内容：它一枚都不许同时是任何一屏的屏名", () => {
    for (const label of FEED_TABS.map(tab => tab.label)) {
      expect(screenRoutes.map(route => String(route.meta.title)), "标签名「" + label + "」同时也是一枚屏名").not.toContain(label)
    }
  })
})

// ==================== 丁 · 射程守门：那枚钉不许再缩回一种画法 ====================

describe("R421丁 · r136 的画法登记处不许被悄悄缩回一式", () => {
  const names = read("../../router/__tests__/r136-screen-names.test.js")
  const shapeBlock = () => {
    const start = names.indexOf("const PAGE_TITLE_SHAPES = [")
    expect(start, "r136 里 PAGE_TITLE_SHAPES 不在了：画法登记处被拆了").toBeGreaterThan(-1)
    const end = names.indexOf("\n]", start)
    expect(end, "画法登记处收口找不到").toBeGreaterThan(start)
    return names.slice(start, end)
  }

  it("三式的标记一枚都不许从登记处里消失", () => {
    const block = shapeBlock()
    for (const marker of ["panel-head", "panel-hd", "chat-screen-name"]) {
      expect(block, "画法登记处少了 " + marker + " 这一式：它一少，那一格的屏名就又无人管了").toContain(marker)
    }
    expect(block.match(/shape: /g)).toHaveLength(3)
  })

  it("闭合集仍然定长、不重、且这一屏在里面；枚数那条钉跟着名单走", () => {
    const list = /const WITH_PAGE_TITLE = \[([^\]]*)\]/.exec(names)
    expect(list, "WITH_PAGE_TITLE 找不到了：那枚钉的闭合集被拆了").toBeTruthy()
    const ids = list[1].split(",").map(item => item.trim().replace(/^['"]|['"]$/g, "")).filter(Boolean)
    expect(ids).toContain("feed")
    expect(new Set(ids).size).toBe(ids.length)
    expect(names.match(/toHaveLength\(\d+\)/g)).toContain("toHaveLength(" + ids.length + ")")
  })
})

// ==================== 戊 · 两份画法清单必须一直说的是同一件事 ====================

/**
 * 总控裁定②给的「抽成一份共享词表」与「各留一份」是两条互斥的路，本单选后者。既然选了各留一份，
 * 这两份就不许悄悄长成两件事：R412 之前 r136 那枚钉与全仓真实画法脱节，用的正是「一份清单没人对」
 * 这个失效方式。本组把「对得上」本身钉住 —— 一枚改窄，另一枚当场把红叫出来。
 */
describe("R421戊 · 两枚在册件各自那份画法清单同集同枚数，且都是本地那一份", () => {
  /** 本件认的三式标记：两份清单里都得有齐这三枚。 */
  const MARKERS = ["panel-head", "panel-hd", "chat-screen-name"]

  const shapeBlock = (source, opener, who) => {
    const start = source.indexOf(opener)
    expect(start, who + " 里找不到本地那份画法清单（锚串「" + opener + "」）：清单被搬走或拆了").toBeGreaterThan(-1)
    const end = source.indexOf("\n]", start)
    expect(end, who + " 的画法清单收口找不到").toBeGreaterThan(start)
    return source.slice(start, end)
  }

  const inventory = block => ({
    markers: MARKERS.filter(marker => block.includes(marker)),
    shapes: (block.match(/shape:/g) || []).length,
  })

  const R136_FILE = "../../router/__tests__/r136-screen-names.test.js"
  const R412_FILE = "./r412-one-screen-one-name.test.js"
  const r136Source = read(R136_FILE)
  const r412Source = read(R412_FILE)
  const counted = [
    ["r136-screen-names", inventory(shapeBlock(r136Source, "const PAGE_TITLE_SHAPES = [", "r136-screen-names"))],
    ["r412-one-screen-one-name", inventory(shapeBlock(r412Source, "const TITLE_SHAPES = [", "r412-one-screen-one-name"))],
  ]

  it("两份清单每一份都得是三式：不许两份一起缩到零来冒充相等", () => {
    for (const [who, got] of counted) {
      expect(got.markers, who + " 本地那份清单缺式：画法登记的就是这三式").toEqual(MARKERS)
      expect(got.shapes, who + " 本地那份清单的 shape 枚数变了").toBe(3)
    }
  })

  it("两枚在册件各抄一份，只改其中一枚的本地副本会当场红", () => {
    const [first, second] = counted
    expect(second[1], first[0] + " 与 " + second[0] + " 那份画法清单已经不是同一件事：两份独立实现的意义就在这里")
      .toEqual(first[1])
  })

  it("两枚在册件都不许改成从别处 import 画法清单：合并这一步要回台账重裁", () => {
    for (const [who, source] of [["r136-screen-names", r136Source], ["r412-one-screen-one-name", r412Source]]) {
      const importedShapes = source.split("\n").filter(line => /^\s*import\b/.test(line) && /\bSHAPES\b/.test(line))
      expect(importedShapes, who + " 的画法清单改成 import 进来的了：两枚钉从此互相掩盖，不再独立交叉验证")
        .toEqual([])
      expect(source, who + " 引了那份被本单反裁掉的共享词表 screen-names-catalog").not.toContain("screen-names-catalog")
    }
  })
})
