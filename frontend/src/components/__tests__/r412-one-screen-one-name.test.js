/**
 * R412 · 一屏一名：屏名只有 meta.title 一个人说，页内自写的那一句必须逐字跟着它
 *
 * 要治的病（docs/handoff/2026-09-27-v2-gap-recheck-2.md §3「R412 · 喂料屏三名并存」那一格）：
 *   同一屏上并存三个名字 —— 顶栏与侧栏叫「喂料」（frontend/src/router/index.js:70 的 meta.title），标签条
 *   叫「文档」（src/router/feed-tabs.js 里 FEED_TABS[0].label），DocPanel 页内又叫「知识库」
 *   （改前实测：src/components/DocPanel.vue:955 那句 <strong>知识库</strong>）。员工嘴里说的和
 *   屏上写的对不上三次。
 *
 * 三条已收口径，本件沿用、不另起一套：
 *   ① 屏名全站只有 meta.title 一处真源，顶栏与侧栏都是它的派生视图（R136 判据①）；
 *   ② 屏内自写的主标题必须与 meta.title 逐字相等 —— 这是 R136 判据① 的页内腿，也是 R268 丙组对
 *      「问一句」那一屏已经收下的一式（页内硬写一句，钉现读 meta.title 与它对账）；
 *   ③ 标签文案说的是这一格装的内容，不是屏名（R136 判据① 与 FeedPanel 文件头都这么写）。
 *
 * 与 src/router/__tests__/r136-screen-names.test.js 的分工（那一件不在本单写域，一字节未动）：
 *   R136 的页内腿只认一种画法 —— header.panel-head 里的 h3。而全仓「屏内主标题」的画法实测有三式
 *   （见 TITLE_SHAPES）：DocPanel 用的是 div.panel-hd 里的 strong，ChatPanel 用的是
 *   [data-testid=chat-screen-name] 那一格，两式都落在 R136 那枚正则的射程之外 —— 所以第三枚名字
 *   「知识库」R136 根本看不见，这正是它在喂料屏上活了这么久的原因。本件补的就是这一格。
 *
 * 四条腿：
 *   甲 现读对账 —— 遍历 routes 里每一屏，取它自写的主标题与 meta.title 逐字比；同时命中多式就红
 *      （一屏只许有一处主标题）；取不到主标题的屏必须能在路由表派生出的入口表里找到同一格名字，
 *      两路都取不到 ⇒ 红并点名，不静默跳过。甲腿最后一条自扫描：本件代码里一枚屏名都不许出现。
 *   乙 反向作弊 —— feed 这一屏必须仍然【有】一句非空主标题（把屏名删掉同样红），屏名槽里不许混进
 *      标签名或第三枚叫法，且 DocPanel.vue 整件文件里屏名只许出现一枚（不许抄出第二处）。
 *   丙 员工动作 —— 改名的同时不许把「上传 / 找 / 看进度 / 看失败」那几句一起洗掉。
 *   丁 结构不变 —— 屏名那一句仍然长在 div.doc-panel > div.panel-hd > div.panel-hd-left > strong
 *      这一格里：零属性、唯一一段文字，模板的元素 / 文字 / 属性 / 指令 / 注释枚数一字节没多也没
 *      少。改名不许靠加节点、套壳或换标记做到。（在册这一腿钉的是结构；「与基点逐字节相等」的整件
 *      证明需要 K0 影子克隆，不是用例自己拿得到的东西，它记在交回回执里。）
 *
 * 反证（本单实跑，每把进门取 sha、出门按字节复原并复核相等）：
 *   刀一 病灶未治（把那一格改回旧叫法）⇒ 甲腿点名 feed、乙腿三条、丁腿末条一起红；
 *   刀二 只改一处留两处（再补一句 header.panel-head h3）⇒ 甲腿「同时命中多式」红、丁腿枚数红；
 *   刀三 把屏名那一句删空 ⇒ 乙腿第一条当场红（不是靠「没有不一致」蒙过去）；
 *   刀四 把屏名抄进第二处（往计数角标里再抄一枚）⇒ 乙腿「只许出现一枚」红；
 *   刀五 把「拖拽或点击上传 · 支持多选」换成「文件上传队列」⇒ 丙腿第一条红；
 *   刀六 把屏名抄进本件的 it 标题 ⇒ 甲腿自扫描红。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import { parse as parseHtml } from '@vue/compiler-dom'
import { parse as parseSfc } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { administratorNavigation, navigation, routes } from '../../router/index.js'
import { FEED_TABS } from '../../router/feed-tabs.js'
import DocPanel from '../DocPanel.vue'

const EMPTY = ''
const LINE = String.fromCharCode(10)
const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, LINE)
const docPanelSource = read('../DocPanel.vue')

/** 路由表就是清单本身：谁是一屏、谁叫什么、标签叫什么，全部现读，不另抄一份。 */
const screenRoutes = routes.filter(route => route.meta?.screen)
const entryLabels = [...navigation, ...administratorNavigation].map(item => item.label)
const tabLabels = FEED_TABS.map(tab => tab.label)
const titleOf = id => String(routes.find(route => String(route.name) === id).meta.title)

/**
 * 全仓现读的三式「主标题」画法，每一式只取本格【有界】的那一段。两格要紧事：
 *   · 容得下属性：SSR 会给每个标签补 data-v-* 作用域属性。照模板里那个裸标签形状去匹配渲染产物，
 *     本单实测九屏全部取不到 —— 那样写出来的钉会一路绿到底，是这枚钉最容易犯的假绿；
 *   · 只取本格之内：容器开标签到它自己那一个收标签之间。否则正则会一路滑到页面深处，把某一枚小节
 *     标题当成主标题，红得莫名其妙。
 */
const TITLE_SHAPES = [
  {
    shape: 'header.panel-head 里的第一个 h3',
    pick(html) {
      const open = /<header\b[^>]*class="[^"]*\bpanel-head\b[^"]*"[^>]*>/.exec(html)
      if (!open) return EMPTY
      const body = html.slice(open.index + open[0].length)
      const end = body.indexOf('</header>')
      const hit = /<h3\b[^>]*>([^<]*)<\/h3>/.exec(end < 0 ? body : body.slice(0, end))
      return hit ? hit[1].trim() : EMPTY
    },
  },
  {
    shape: 'div.panel-hd 里、本格收口之前的第一个 strong',
    pick(html) {
      const cell = /<div\b[^>]*class="panel-hd"[^>]*>([\s\S]*?)<\/div>/.exec(html)
      if (!cell) return EMPTY
      const hit = /<strong\b[^>]*>([^<]*)<\/strong>/.exec(cell[1])
      return hit ? hit[1].trim() : EMPTY
    },
  },
  {
    shape: '[data-testid=chat-screen-name] 那一格',
    pick(html) {
      const hit = /data-testid="chat-screen-name"[^>]*>([^<]*)</.exec(html)
      return hit ? hit[1].trim() : EMPTY
    },
  },
]

/** 命中几式、各是什么字，全都交回用例判；这里不替它挑一枚「最像的」。 */
const paneTitles = html => TITLE_SHAPES
  .map(entry => ({ shape: entry.shape, text: entry.pick(html) }))
  .filter(hit => hit.text)

const renderDocPanel = () => renderToString(h(DocPanel))

/** 模板 AST：结构账只认它，不认正则 —— 正则会把属性名一起改错，看不出来。 */
const docPanelTemplate = () => parseHtml(parseSfc(docPanelSource, { filename: 'DocPanel.vue' }).descriptor.template.content)

const walkTemplate = (visit) => {
  const step = (children, trail) => {
    for (const node of children || []) {
      if (node.type === 1) {
        const classProp = (node.props || []).find(prop => prop.type === 6 && prop.name === 'class')
        const label = node.tag + (classProp && classProp.value ? '.' + classProp.value.content.trim().replace(/\s+/g, '.') : EMPTY)
        const next = trail.concat(label)
        visit(node, next)
        step(node.children, next)
      } else {
        visit(node, trail)
      }
    }
  }
  step(docPanelTemplate().children, [])
}

describe('R412甲 · 一屏一名：每一屏自写的主标题都与 meta.title 逐字相等（遍历路由表，不抄清单）', () => {
  it('屏的名单现读自路由表：这条遍历不会漏屏', () => {
    const fromTable = routes.filter(route => route.meta && route.meta.screen)
    expect(screenRoutes).toHaveLength(fromTable.length)
    expect(new Set(screenRoutes.map(route => String(route.name))).size).toBe(screenRoutes.length)
  })

  for (const route of screenRoutes) {
    const id = String(route.name)
    it('屏 ' + id + '：meta.title 非空，且屏内不许出现第二枚屏名', async () => {
      const title = String(route.meta?.title || '').trim()
      expect(title, '屏 ' + id + ' 的 meta.title 是空的：屏名没有真源了').toBeTruthy()
      const hits = paneTitles(await renderToString(h(route.component)))
      expect(hits.length, '屏 ' + id + ' 用多于一式画了主标题，一屏只许有一处：' + JSON.stringify(hits)).toBeLessThanOrEqual(1)
      for (const hit of hits) {
        expect(hit.text, '屏 ' + id + ' 页内自写的屏名与 meta.title 不是一份字：' + hit.text + ' / ' + title).toBe(title)
      }
      if (!hits.length) {
        expect(entryLabels, '屏 ' + id + ' 既没写页内主标题、也不在任何一枚派生入口表里：这一屏没人说它叫什么').toContain(title)
      }
    })
  }

  it('本件自己不抄屏名：在册屏名一枚都不许以字面量的形式出现在用例代码里', () => {
    const self = read('./r412-one-screen-one-name.test.js')
    const code = self
      .replace(/\/\*[\s\S]*?\*\//g, ' ')
      .replace(/(^|[\s;:{}])\/\/[^\n]*/g, '$1')
    for (const route of screenRoutes) {
      const title = String(route.meta?.title || '').trim()
      if (!title) continue
      expect(code, '这一枚钉把屏名「' + title + '」抄进了代码：改了 meta.title 它就会假绿').not.toContain(title)
    }
  })
})

describe('R412乙 · 反向作弊：屏名不是靠删文案统一掉的', () => {
  const title = titleOf('feed')

  it('feed 这一屏仍然【有】一句非空主标题（把标题删了同样算红）', async () => {
    const hits = paneTitles(await renderDocPanel())
    expect(hits.length, '这一屏把主标题弄丢了：统一名字不许靠删文案做到').toBe(1)
    expect(hits[0].text, '主标题不许是空的一句').toBeTruthy()
  })

  it('那一句与 meta.title 逐字相等（现读路由表，不抄清单）', async () => {
    expect(paneTitles(await renderDocPanel())[0].text).toBe(title)
  })

  it('屏名槽里不许混进标签名，也不许混进被裁定不统一的第三枚叫法', async () => {
    const banned = [...tabLabels, '知识库'].filter(word => word !== title && !title.includes(word))
    const text = paneTitles(await renderDocPanel())[0].text
    for (const word of banned) {
      expect(text, '这一屏的主标题里还夹着一枚「' + word + '」：同一屏上就是两个名字').not.toContain(word)
    }
  })

  it('DocPanel.vue 整件文件里屏名只许出现一枚：抄出第二处就是开第二份真源', async () => {
    const text = paneTitles(await renderDocPanel())[0].text
    expect(text).toBe(title)
    expect(docPanelSource.split(title).length - 1, '屏名在 DocPanel.vue 里不止一枚').toBe(1)
  })
})

describe('R412丙 · 改名没把员工动作那几句话一起洗掉', () => {
  it('上传与找这两格仍说得出动作，不是名词堆叠', async () => {
    const html = await renderDocPanel()
    for (const phrase of ['拖拽或点击上传', '上传公司制度、手册或数据开始', '搜索文档', '这一发的密级', '部门由服务端按你的账号判定']) {
      expect(html, '这一句员工动作不见了：' + phrase).toContain(phrase)
    }
  })

  it('看进度与看失败那几张脸仍在件里：改屏名不许顺手把它们改成名词', () => {
    for (const phrase of ['正在解析入库', '解析入库中', '文件上传进度', '文档列表没加载出来', '文件没能下载']) {
      expect(docPanelSource, '这一句进度/失败话术不见了：' + phrase).toContain(phrase)
    }
  })
})

describe('R412丁 · 屏名那一句长在既有的那一格里，改名没动结构', () => {
  const BASE_TALLY = { elements: 80, texts: 19, attributes: 146, directives: 102, comments: 21 }

  const tallyShape = () => {
    const tally = { elements: 0, texts: 0, attributes: 0, directives: 0, comments: 0 }
    walkTemplate(node => {
      if (node.type === 1) {
        tally.elements += 1
        for (const prop of node.props || []) {
          if (prop.type === 6) tally.attributes += 1
          else if (prop.type === 7) tally.directives += 1
        }
      } else if (node.type === 2) {
        tally.texts += 1
      } else if (node.type === 3) {
        tally.comments += 1
      }
    })
    return tally
  }

  it('模板结构枚数与基点一致：这单只改文案，没加节点也没减节点', () => {
    expect(tallyShape()).toEqual(BASE_TALLY)
  })

  it('屏名那一句仍是 div.doc-panel > div.panel-hd > div.panel-hd-left > strong 里唯一一段文字', () => {
    const strongs = []
    walkTemplate((node, trail) => {
      if (node.type === 1 && node.tag === 'strong') {
        strongs.push({
          trail,
          props: (node.props || []).map(prop => prop.name),
          texts: (node.children || []).filter(child => child.type === 2).map(child => child.content.trim()),
        })
      }
    })
    expect(strongs, 'DocPanel 里 strong 的枚数变了：屏名不该由第二格来说').toHaveLength(1)
    expect(strongs[0].trail).toEqual(['div.doc-panel', 'div.panel-hd', 'div.panel-hd-left', 'strong'])
    expect(strongs[0].props).toEqual([])
    expect(strongs[0].texts).toEqual([titleOf('feed')])
  })
})
