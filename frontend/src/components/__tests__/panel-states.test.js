/**
 * A-3-1 · 面板状态接线单测
 *
 * 环境是 node + @vue/server-renderer（仓库里没有 jsdom / @vue/test-utils，也不许 npm i），
 * 所以断言分两类，各管各的事，不假装验过自己验不了的：
 *   ① SSR 真产物：初始空态能渲染出原语、原语的 role / data-testid 在、手搓的 .empty-state 不再出现。
 *      SSR 不跑 onMounted，所以这里能稳定拿到「还没发过请求」的那张脸。
 *   ② 源码级断言：失败态 / 无权限态要把请求打成失败才能出现，node 里没有网络层可打，
 *      于是钉住「该分支只存在一条路径、且用原语」，与总控在 tests/test_frontend_request_cancel.py
 *      里用的手法一致；像素与点击行为的覆盖归 tests/visual（B 的写集，A 线不代写）。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import GraphPanel from '../GraphPanel.vue'
import DataPanel from '../DataPanel.vue'
import InsightPanel from '../InsightPanel.vue'
import ApprovalPanel from '../ApprovalPanel.vue'
import { UiEmptyState, UiErrorState } from '../ui'

const source = f => readFileSync(new URL(`../${f}`, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const render = component => renderToString(h({ render: () => h(component) }))

describe('GraphPanel · V7-1 不变量 + A-3-1 接线', () => {
  it('SSR 首屏画的是原语空态，不是手搓 div', async () => {
    const html = await render(GraphPanel)
    expect(html).toContain('data-testid="ui-empty-state"')
    expect(html).toContain('知识库里还没有已登记的关系')
    expect(html).not.toContain('class="empty-state"')
  })

  it('空态用 role="status"（查询结果，不该像失败那样打断读屏）', async () => {
    const html = await render(GraphPanel)
    expect(html).toMatch(/<div class="ui-empty-state[^"]*" role="status"/)
  })

  it('关系列表唯一来源是真接口，失败不回落到常量', () => {
    const s = source('GraphPanel.vue')
    expect(s).toContain("api.get('/knowledge-graph/relations')")
    // V7-1：既不许 import 常量，也不许在 catch 里给 relations 塞任何示例值。
    expect(s).not.toMatch(/devFixtures/)
    expect(s).toMatch(/catch \(err\) \{[\s\S]*?relations\.value = \[\][\s\S]*?\}/)
  })

  it('失败态与空态是两条独立分支，且失败态吃 UiErrorState', () => {
    const s = source('GraphPanel.vue')
    expect(s).toMatch(/<UiErrorState[\s\S]*?v-if="loadError"/)
    expect(s).toMatch(/<UiEmptyState[\s\S]*?v-else-if="!relations\.length"/)
    expect(s).toContain('retry-text="重新加载"')
  })

  // R1(c)：无权限画成「可以重试的加载失败」也是撒谎，重试不会把权限试出来。
  it('无权限分支只可能来自 permission_denied，且该分支不给重试', () => {
    const s = source('GraphPanel.vue')
    expect(s).toContain('isPermissionDenied(err)')
    expect(s).toMatch(/:title="loadDenied \? '没有权限查看关系列表' : '关系列表没加载出来'"/)
    expect(s).toMatch(/:retryable="!loadDenied"/)
  })

  it('原语本身带 aria 语义（role 由组件自己长出来，不靠面板补）', async () => {
    const err = await renderToString(h(UiErrorState, { title: '关系列表没加载出来', description: 'x', retryable: false }))
    expect(err).toContain('role="alert"')
    expect(err).toContain('data-testid="ui-error-state"')
    // retryable=false => 整条操作区不渲染
    expect(err).not.toContain('data-testid="ui-error-retry"')
  })
})

describe('DataPanel · 文件列表三张脸 + 色债随接线一起掉', () => {
  it('SSR 首屏：没有数据文件 => 原语空态，且文案一字不少', async () => {
    const html = await render(DataPanel)
    expect(html).toContain('data-testid="ui-empty-state"')
    expect(html).toContain('暂无数据文件')
    expect(html).toContain('上传 Excel 或 CSV 开始分析。')
    expect(html).not.toContain('class="data-state empty"')
  })

  // R1(c) 的顺序即语义：失败必须先于「空」被判掉，否则读不到列表会说成「没有文件」。
  it('失败分支排在空态分支之前，两者互斥', () => {
    const s = source('DataPanel.vue')
    const errAt = s.indexOf('<UiErrorState')
    const emptyAt = s.indexOf('<UiEmptyState')
    expect(errAt).toBeGreaterThan(-1)
    expect(emptyAt).toBeGreaterThan(errAt)
    expect(s).toMatch(/v-else-if="filesError"[\s\S]*?v-else-if="!dataFiles\.length"/)
  })

  it('无权限不给重试；普通失败给「重新加载」并挡住重复点击', () => {
    const s = source('DataPanel.vue')
    expect(s).toContain('isPermissionDenied(err)')
    expect(s).toMatch(/:retryable="!filesDenied"/)
    expect(s).toMatch(/:retryable="!previewDenied"/)
    expect(s).toMatch(/:busy="filesLoading"/)
    expect(s).toContain('retry-text="重新加载"')
  })

  it('预览失败也不许画成空态：别人的数据集是「打不开」不是「没有数据」', () => {
    const s = source('DataPanel.vue')
    expect(s).toContain('这份数据文件不属于你的可见范围，当前账号打不开它。')
    expect(s).toMatch(/@retry="selectDataFile\(dataFile\)"/)
  })

  it('手搓状态样式与它那 3 个裸色值一起消失（棘轮 351 -> 348 的出处）', () => {
    const s = source('DataPanel.vue')
    expect(s).not.toContain('#dc2626')
    expect(s).not.toContain('#fafafa')
    // #d1d5db 还剩 1 处，那是 .data-file-item 的描边，跟状态块无关，属 V1 色债，别混进这次接线。
    expect(s.match(/#d1d5db/g)).toHaveLength(1)
    expect(s).not.toContain('.data-state.error')
    expect(s).not.toContain('.data-state.empty')
    // 摘掉分支后没人用的 .preview-error 也一起清了，不留死样式
    expect(s).not.toMatch(/\.preview-error\s*\{/)
  })
})

describe('InsightPanel · 失败不许说成「暂时没有异常」', () => {
  it('SSR 首屏（还没发过请求）才是空态，文案原样保留', async () => {
    const html = await render(InsightPanel)
    expect(html).toContain('data-testid="ui-empty-state"')
    expect(html).toContain('暂时没有异常')
    expect(html).not.toContain('class="empty-state"')
  })

  // 这就是修案的实质：failed 与 length===0 是两条分支，且失败优先。
  it('失败分支独立于空态分支，且排在它前面', () => {
    const s = source('InsightPanel.vue')
    expect(s).toMatch(/<UiErrorState\s+v-if="failed"/)
    expect(s).toMatch(/<UiEmptyState v-else-if="!insights\.length" title="暂时没有异常"/)
    expect(s).toContain('failed.value = true')
    expect(s).toContain('insights.value = []')
  })

  it('不再把 err.response.data.detail 原样插值到界面上', () => {
    expect(source('InsightPanel.vue')).not.toMatch(/err\.response\?\.data\?\.detail \|\|/)
    expect(source('InsightPanel.vue')).toContain('errorDetail(err,')
  })

  it('无权限 => 没有重试按钮；普通失败 => 重新分析并挡重复点击', () => {
    const s = source('InsightPanel.vue')
    expect(s).toContain('isPermissionDenied(err)')
    expect(s).toMatch(/:title="denied \? '没有权限运行洞察分析' : '洞察分析没有跑完'"/)
    expect(s).toMatch(/:retryable="!denied"/)
    expect(s).toContain('retry-text="重新分析"')
    expect(s).toMatch(/:busy="loading"/)
  })
})

describe('ApprovalPanel · 自动预审失败不许说成「等待分析」', () => {
  it('SSR 首屏渲染原语空态，保留「等待分析」四个字', async () => {
    const html = await render(ApprovalPanel)
    expect(html).toContain('data-testid="ui-empty-state"')
    expect(html).toContain('等待分析')
  })

  it('onMounted 会自己发请求，所以失败必须能被区分出来', () => {
    const s = source('ApprovalPanel.vue')
    expect(s).toContain('onMounted(submitCheck)')
    expect(s).toMatch(/<UiErrorState\s+v-if="failed"/)
    expect(s).toMatch(/<UiEmptyState v-else-if="!result" title="等待分析"/)
    expect(s).toContain('result.value = null')
  })

  it('错误文案走 errorDetail，无权限不给重试', () => {
    const s = source('ApprovalPanel.vue')
    expect(s).not.toMatch(/err\.response\?\.data\?\.detail \|\|/)
    expect(s).toContain('isPermissionDenied(err)')
    expect(s).toMatch(/:retryable="!denied"/)
    expect(s).toContain('retry-text="重新预审"')
  })
})