/**
 * R423 · 界面文案不许拿「知识库」当对象名：两处冒充同一族的病，各钉一枚
 *
 * 病根（与本仓正在治的那一族同源，Hume/R421 在喂料屏治的就是这个）：句子把「知识库」当成一个
 * 对象来指称，而那一格真正的对象是【这一篇文档能不能被检索到】与【选了问答档会拿到什么】。
 * 客户装上机以后在侧栏里找不到一枚叫「知识库」的屏，这句话就成假话——它既不是屏名，也不是
 * 任何一格的标题，只是文案借来的一块招牌。
 *   · frontend/src/components/DashboardPanel.vue 的 INDEX_STATUS_TEXT.indexed 原来写「已入知识库索引」；
 *   · frontend/src/components/ChatPanel.vue 的 LANE_PROMISES.qa 原来写「只查知识库回答，……」。
 *
 * 三组断言：
 *   甲 禁句族 0 命中：这两枚文件的【文案】里「知识库」三个字一枚都不许出现（改口不许只是换个
 *     说法又留一份）。扫的是文案不是注解：行注解（整行 // 与挂在代码尾巴上的两种）与本件的标题
 *     都还写着那三个字，说的是它为什么禁 —— 拿全文当文案扫等于自己撞自己。
 *   乙 新口径说的是对象本身：indexed 那张脸说「能不能被检索到」，qa 那句说「选了会怎样」，
 *     都不替后端宣布它跑了哪条腿（ChatPanel.vue 里 LANE_PROMISES 上面那行注解立的规矩）。
 *   丙 可达性：这两句确实绑在屏上某一格（模板 + data-testid），不是住在源码里没人画的一张表 ——
 *     真产物级渲染钉在同树的 r267-overview-real-status.test.js:121（doc 行索引那一列）与
 *     r141-lane-picker.test.js:61-71（?lane= 深链下承诺跟着变），本件钉的是绑定关系本身。
 *
 * 反证怎么算红：把 INDEX_STATUS_TEXT.indexed 改回「已入知识库索引」→ 甲1 乙1 丙1 与 r267 两枚、
 * r410 一枚当场红；把 qa 那句改回「只查知识库回答…」→ 甲2 乙2 丙2 与 r141 当场红。
 *
 * 🔴 范围边界：DocPanel.vue 里也有「知识库」那几句（INDEX_REASON_UNKNOWN 与空态标题），那一棵在
 * Hume/R421 写域内，本件一枚都不扫、一字节都不动；errcodes.js 在待派 R422 名下，同样不扫。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = name => readFileSync(new URL(name, import.meta.url), 'utf8').replace(/\r?\n/g, '\n')
const dash = source('../DashboardPanel.vue')
const panel = source('../ChatPanel.vue')

/** 只留下会上屏的东西：整行 // 注解与模板 <!-- --> 注掉的部分都不是文案。 */
// 行注释有两种形状：整行 // 开头的，与挂在代码尾巴上的 ' // '。两种都不是文案。
const copy = text => text.split('\n')
  .filter(line => !line.trim().startsWith('//'))
  .map(line => line.split(' // ')[0])
  .join('\n')
  .replace(/<!--[\s\S]*?-->/g, '')

describe('甲 · 「知识库」不在这两枚文件的文案里冒充对象名', () => {
  it('DashboardPanel.vue 文案零命中：借招牌那句不许改口之后还留一份', () => {
    expect(copy(dash).match(/知识库/g) || [], '总览那一列说的是这一篇文档，不是一枚叫「知识库」的东西').toHaveLength(0)
  })

  it('ChatPanel.vue 文案零命中：档位承诺里也不许出现屏上没有的名字', () => {
    expect(copy(panel).match(/知识库/g) || [], '屏上没有一枚叫「知识库」的格子，承诺句不许拿它当对象').toHaveLength(0)
  })
})

describe('乙 · 改口之后的两句各说各的对象', () => {
  it('indexed 那张脸说的是「能不能被检索到」，且与未索引／未知／未记录三档仍然分明', () => {
    expect(dash).toContain("indexed: '已入检索索引'")
    expect(dash).toContain("excluded: '未索引'")
    expect(dash).toContain("unknown: '索引状态未知'")
    expect(dash).toContain("INDEX_STATUS_UNRECORDED_TEXT = '索引状态未记录'")
  })

  it('qa 那句只写「选了会怎样」：不宣布腿名，也不宣布它跑了哪条腿', () => {
    const table = /const LANE_PROMISES = \{[\s\S]*?\n\}/.exec(panel)
    expect(table, '承诺表整枚不见了：屏上那一格就没有话可说了').not.toBeNull()
    const qa = /qa: '([^']+)'/.exec(table[0])
    expect(qa, 'qa 那一格掉出承诺表了：屏上就什么承诺都不画').not.toBeNull()
    expect(qa[1]).toBe('只用文字回答，不算数、不出图、不产文件')
    expect(qa[1], '承诺句替后端宣布它跑了检索这条腿：那条腿今天不由界面作证').not.toMatch(/知识库|检索|只查|走[\s\S]*腿/)
  })
})

describe('丙 · 两句真的绑在屏上某一格（可达性）', () => {
  it('总览文档行的索引那一列绑的是 indexStatusText，画在 dashboard-doc-index 这一格里', () => {
    expect(dash).toMatch(/function indexStatusText\(row\) \{[\s\S]*?INDEX_STATUS_TEXT\[keyOf\(row\?\.index_status\)\]/)
    expect(dash).toMatch(/<small data-testid="dashboard-doc-index">\{\{ indexStatusText\(item\) \}\}<\/small>/)
  })

  it('档位承诺绑的是 LANE_PROMISES[selectedLane]，画在 chat-lane-promise 这一格里', () => {
    expect(panel).toMatch(/<span class="lane-promise" data-testid="chat-lane-promise">\{\{ LANE_PROMISES\[selectedLane\] \}\}<\/span>/)
  })
})
