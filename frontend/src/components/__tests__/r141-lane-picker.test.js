/**
 * R141 · 档位选择器与那一轮的真读数（判据③ 的第二半）
 *
 * 环境同 r150：node + @vue/server-renderer（仓库没有 jsdom / @vue/test-utils，也不许 npm i）。
 *   ① SSR 真产物：控件长什么样、四态读数各说什么 —— 这是"上屏了"的实据。
 *   ② 真路由 + watch：地址栏改了，选择框跟着改（"刷新留得住"这一格走的是真产物）。
 *   ③ 源码级：请求体里那一行 lane、@change 的落点。SSR 不跑点击、node 里没有 fetch，
 *      这一段只能钉调用点，跑通归 tests/visual（总控统一跑）。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createMemoryHistory, createRouter } from 'vue-router'
import ChatPanel from '../ChatPanel.vue'
import { activeId, messages } from '../../lib/sessions.js'

const source = f => readFileSync(new URL(`../${f}`, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const panel = source('ChatPanel.vue')

const TURN_PATHS = [
  { path: '/chat', name: 'chat', component: ChatPanel, meta: { screen: true, title: '问一句' } },
]

function makeRouter(entry = '/chat') {
  const router = createRouter({ history: createMemoryHistory(), routes: TURN_PATHS })
  const app = createSSRApp({ render: () => h(ChatPanel) })
  app.use(router)
  return { router, app }
}

async function bare(turns) {
  activeId.value = 'r141-session'
  messages.value = turns
  const { router, app } = makeRouter()
  await router.push('/chat')
  await router.isReady()
  return renderToString(app)
}

function assistantTurn(over = {}) {
  return { role: 'assistant', content: '限额以内据实报销。', steps: [], mid: 't-' + Math.random().toString(36).slice(2), ...over }
}

describe('P1 · 控件上屏（SSR 真产物）', () => {
  it('四枚取值都在下拉里，且默认落在「系统判断」', async () => {
    const html = await bare([assistantTurn()])
    expect(html).toContain('data-testid="chat-lane-picker"')
    for (const value of ['', 'qa', 'analysis', 'report']) {
      expect(html, `档位 ${value} 没进下拉`).toContain(`value="${value}"`)
    }
    expect(html).toContain('按问题内容自动挑一条最省的路')
  })

  it('控件有 label 且绑到同一个 id（读屏要能说出这是什么）', async () => {
    const html = await bare([assistantTurn()])
    expect(html).toMatch(/<label[^>]*for="chat-lane-select"[^>]*>\s*本轮档位/)
    expect(html).toMatch(/<select[^>]*id="chat-lane-select"/)
  })

  it('换档要说得出代价：三档各自的承诺不同句', async () => {
    const promises = {
      qa: '只查知识库回答，不算数、不出图、不产文件',
      analysis: '允许进数据分析与图表，但不产文件',
      report: '一定走导出这一腿（会先请你确认）',
    }
    for (const [lane, copy] of Object.entries(promises)) {
      const html = await bareWithQuery(`/chat?lane=${lane}`)
      expect(html, `${lane} 的承诺没跟着地址变`).toContain(copy)
    }
  })
})

describe('P2 · 地址是真相（刷新与深链留得住）', () => {
  it('?lane=report 进来，选择框就落在报告档', async () => {
    const html = await bareWithQuery('/chat?lane=report')
    // Vue SSR 把 :value 绑到 <select> 上渲染成 value 属性（选项上的 selected 是水合后的事）：
    // 这一格读的就是"地址 -> 组件状态"这条腿真的接上了。
    expect(html).toContain('class="lane-picker" value="report"')
  })

  it('地址里写了一个认不得的档位，落回「系统判断」而不是原样发出去', async () => {
    const html = await bareWithQuery('/chat?lane=REPORT')
    expect(html).toContain('按问题内容自动挑一条最省的路')
    expect(html).toContain('class="lane-picker" value=""')
  })

  it('地址换了（回退/转发后改口），组件跟着改：watch 盯的是 query 不是本地副本', () => {
    expect(panel).toMatch(/watch\(\(\) => route\?\.query\?\.lane/)
    // 反证锚：把这一行删掉，"刷新留得住"就只剩初始值那一条腿
    expect(panel).toMatch(/router\?\.replace\(\{ query: queryWithLane/)
  })
})

async function bareWithQuery(url) {
  activeId.value = 'r141-session'
  messages.value = [assistantTurn()]
  const { router, app } = makeRouter()
  await router.push(url)
  await router.isReady()
  return renderToString(app)
}

describe('P3 · 每一轮画回的是读数，不是选择框（判据③ 的自证半）', () => {
  it('你选的：句子里写着"你选的"，并点名是哪一档', async () => {
    const html = await bare([assistantTurn({ lane: { lane: 'analysis', source: 'explicit', declared: 'analysis' } })])
    expect(html).toContain('data-testid="lane-readout"')
    expect(html).toContain('本轮档位：分析档（你选的）')
  })

  it('系统判的：没人选就要说得出口"没人在选"', async () => {
    const html = await bare([assistantTurn({ lane: { lane: 'qa', source: 'r42', declared: '' } })])
    expect(html).toContain('（系统按问题内容判的，你没选）')
  })

  it('没走图：缓存命中/排队这一轮档位没参与，且把你选过的 say 回来', async () => {
    const html = await bare([assistantTurn({ lane: { lane: '', source: 'not_routed', declared: 'report' } })])
    expect(html).toContain('本轮没有走进分析图')
    expect(html).toContain('「报告档」没参与这一轮的路径')
    // 与"没走图"不同的另一格：批准后续跑，原始声明掉在确认门外
    const resumed = await bare([assistantTurn({ lane: { lane: '', source: 'resumed', declared: '' } })])
    expect(resumed).toContain('确认门')
  })

  it('四态两两不同句，没有并成一句"出错了"', async () => {
    const texts = []
    for (const read of [
      { lane: 'qa', source: 'explicit', declared: 'qa' },
      { lane: 'qa', source: 'r42', declared: '' },
      { lane: '', source: 'not_routed', declared: 'qa' },
      { lane: '', source: 'resumed', declared: '' },
    ]) {
      const html = await bare([assistantTurn({ lane: read })])
      const got = html.match(/data-testid="lane-readout"[^>]*>(.*?)<\/p>/)
      texts.push(got ? got[1] : '')
    }
    expect(new Set(texts).size).toBe(4)
    expect(texts.every(Boolean)).toBe(true)
  })

  it('后端没发读数就整条不画（不拿选择框的值冒充证据）', async () => {
    const html = await bareWithQuery('/chat?lane=report')
    expect(html).not.toContain('data-testid="lane-readout"')
  })
})

describe('P4 · 发出去真的带这一格（源码级：SSR 不跑点击）', () => {
  it('请求体里带着 lane，值就是选择框', () => {
    expect(panel).toMatch(/lane: selectedLane\.value,/)
  })

  it('读数从响应头读，且在本轮消息对象上留一份（刷新后才复原得回来）', () => {
    expect(panel).toMatch(/readLaneHeaders\(turn, aiMsg, response\)/)
    expect(panel).toMatch(/msg\.lane = read/)
    for (const header of ['x-effective-lane', 'x-lane-source', 'x-declared-lane']) {
      expect(panel, `${header} 没对上后端`).toContain(`'${header}'`)
    }
  })

  it('档位取值表只抄一次：面板里没有第二份 qa/analysis/report 字面量清单', () => {
    // 允许 LANE_NAMES / LANE_PROMISES 这类"说人话"的表，但不许再写一份 value 数组
    expect(panel).not.toMatch(/const LANE_VALUES\s*=\s*\[/)
    expect(panel).toContain("from '../router/lane-choice.js'")
  })
})
