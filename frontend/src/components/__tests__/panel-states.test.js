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
import DashboardPanel from '../DashboardPanel.vue'
import DocPanel from '../DocPanel.vue'
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

  // 总控原要求：GraphPanel 不留第二套错误呈现。写路径以前是裸 <span class="inline-error">。
  it('整个面板只剩 UiErrorState 一条错误出口，没有第二套手搓错误样式', () => {
    const s = source('GraphPanel.vue')
    expect(s).not.toContain('inline-error')
    expect(s.match(/<UiErrorState/g)).toHaveLength(2)
    expect(s).toMatch(/:title="saveDenied \? '没有权限登记关系' : '这条关系没能保存'"/)
    expect(s).toMatch(/:retryable="!saveDenied"/)
    expect(s).toContain('retry-text="再试一次"')
    expect(s).toMatch(/:busy="saving"/)
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

describe('DashboardPanel · 总览的四处状态 + 被吞掉的证据查询失败', () => {
  it('SSR 首屏是加载行；三张空脸与失败脸都还没出现', async () => {
    const html = await render(DashboardPanel)
    expect(html).toContain('正在加载经营数据')
    expect(html).not.toContain('data-testid="ui-error-state"')
    expect(html).not.toContain('data-testid="ui-empty-state"')
    expect(html).not.toContain('class="empty-state"')
    expect(html).not.toContain('class="panel-state error"')
  })

  it('三处「没有内容」全部改吃原语，且原文案一字不改地保留', () => {
    const s = source('DashboardPanel.vue')
    for (const copy of ['当前没有异常线索', '上传制度或业务文档后显示在这里', '查询指标口径后显示证据']) {
      expect(s).toContain(`title="${copy}"`)
    }
    expect(s).not.toContain('class="empty-state"')
    expect(s.match(/<UiEmptyState/g)).toHaveLength(3)
  })

  // D-4 之外的本批要点：证据卡的 catch 原先什么都不做，失败被吞成一句空话。
  it('lookupMetric 不再空吞异常，失败脸排在正文与空态之前', () => {
    const s = source('DashboardPanel.vue')
    expect(s).not.toMatch(/\}\s*catch\s*\{/)
    expect(s).toMatch(/\} catch \(err\) \{[\s\S]*?evidenceError\.value = [\s\S]*?\}/)
    expect(s).toMatch(/v-if="evidenceError"[\s\S]*?v-else-if="metricContext"[\s\S]*?v-else title="查询指标口径后显示证据"/)
  })

  it('无权限与真失败分两张脸，且都不把 detail 原样插值上屏', () => {
    const s = source('DashboardPanel.vue')
    expect(s).not.toMatch(/err\.response\?\.data\?\.detail \|\|/)
    expect(s.match(/isPermissionDenied\(err\)/g)).toHaveLength(2)
    expect(s).toMatch(/:retryable="!denied"/)
    expect(s).toMatch(/:retryable="!evidenceDenied"/)
    expect(s).toContain('retry-text="重新查询"')
  })
})

describe('DocPanel · 一条提示条拆成「哪种事没成」+ 两处空态', () => {
  it('SSR 首屏：空知识库画原语，两句话一字不改，emoji 图标交给原语的内置图标', async () => {
    const html = await render(DocPanel)
    expect(html).toContain('data-testid="ui-empty-state"')
    expect(html).toContain('知识库是空的')
    expect(html).toContain('上传公司制度、手册或数据开始')
    expect(html).not.toContain('class="empty"')
    expect(html).not.toContain('📭')
  })

  // 以前不论上传、下载还是删除失败，按钮永远写着「重新加载」并去重拉列表。
  it('只有列表本身没拿到时才提供「重新加载」，下载/删除失败不提供假补救', () => {
    const s = source('DocPanel.vue')
    expect(s).toContain("raiseNotice('文档列表没加载出来', errorDetail(err, '文档列表加载失败'), true)")
    expect(s).toContain("raiseNotice('文件没能下载', errorDetail(err, '文件下载失败'), false)")
    expect(s).toContain("raiseNotice('删除没有完成', errorDetail(err, '删除失败'), false)")
    expect(s).toContain("raiseNotice('部分文档没能删除'")
    expect(s).toMatch(/<UiButton v-if="noticeRetry"[^>]*label="重新加载"/)
  })

  it('手搓提示条与空态样式（含 4 处色债）随分支一起删除', () => {
    const s = source('DocPanel.vue')
    for (const gone of ['.doc-notice', '.doc-notice-text', '.doc-notice-retry', '.doc-notice-close', '.empty-icon']) {
      expect(s).not.toContain(gone)
    }
    expect(s).not.toContain('rgba(238, 109, 120, .08)')
    expect(s).not.toMatch(/^\.empty \{/m)
    expect(s).not.toMatch(/^\.empty-sub \{/m)
    // 关闭 × 换成带文字的 UiButton，仍可撤下提示
    expect(s).toContain('label="关闭"')
  })

  it('提示条仍走 role="alert"，但由原语负责，不再由面板自己写', () => {
    const s = source('DocPanel.vue')
    expect(s).toMatch(/<UiErrorState\s+v-if="notice"/)
    expect(s).not.toContain('role="alert"')
  })
})