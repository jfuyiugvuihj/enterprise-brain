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
import DocumentPreviewModal from '../DocumentPreviewModal.vue'
import ChatPanel from '../ChatPanel.vue'
import { UiEmptyState, UiErrorState, UiLoadingState } from '../ui'

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

  // A-5-3 filesLoading 初值是 false，SSR 拿不到这一支，所以钉分支形状而不是渲染结果：
  // 三张脸的顺序即语义（进行中 -> 失败 -> 空），失败不许被说成「没有文件」，
  // 而旧的手搓 <p class="data-state"> 一支留痕都不许有。
  it('进行态这一支只认 UiLoadingState，且排在失败与空态之前', () => {
    const s = source('DataPanel.vue')
    const loadingAt = s.indexOf('<UiLoadingState v-if="filesLoading"')
    const errorAt = s.indexOf('v-else-if="filesError"')
    const emptyAt = s.indexOf('v-else-if="!dataFiles.length"')
    expect(loadingAt).toBeGreaterThan(-1)
    expect(loadingAt).toBeLessThan(errorAt)
    expect(errorAt).toBeLessThan(emptyAt)
    expect(s).not.toContain('class="data-state"')
    expect(s).toContain('label="正在读取数据文件..."')
  })

  // role="status" 不在面板里手写（写了就是第二套形状），所以链路两截都要实测：
  // ① 那一支用的确实是 UiLoadingState；② 该原语渲染出来确实带 role + aria-busy。
  it('新位的 role=status 由原语发出：链路两截都是真产物', async () => {
    expect(source('DataPanel.vue')).toMatch(/<UiLoadingState v-if="filesLoading" label="正在读取[^"]*" dense/)
    const html = await renderToString(h(UiLoadingState, { label: '正在读取数据文件...', dense: true }))
    expect(html).toMatch(/<div class="ui-loading-state[^"]*" role="status" aria-busy="true"/)
    expect(html).toContain('正在读取数据文件...')
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
    // R151 把最后这一枚裸色也吃掉了（.data-action-btn 的描边 -> var(--legacy-line-mute)），
    // 所以这里的计数从「还剩 1」收到 0：棘轮只准降，任何一枚裸 #d1d5db 复活都会当场红。
    expect(s.match(/#d1d5db/g) || []).toHaveLength(0)
    expect(s).not.toContain('.data-state.error')
    expect(s).not.toContain('.data-state.empty')
    // 摘掉分支后没人用的 .preview-error 也一起清了，不留死样式
    expect(s).not.toMatch(/\.preview-error\s*\{/)
  })
})

describe('InsightPanel · 没权限 / 真失败 / 空列表是三条分支（W7 起这一屏接的是真告警链）', () => {
  // 面板头注释里保留了旧端点与旧文案做历史交代，所以源码级断言一律先看代码体。
  const codeOnly = text => text
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter(line => !/^\s*\/\//.test(line))
    .join('\n')
  const code = () => codeOnly(source('InsightPanel.vue'))

  it('SSR 首屏是加载脸：一次请求都没回来之前，这一屏不许自称「没有告警」', async () => {
    const html = await render(InsightPanel)
    expect(html).toContain('data-testid="ui-loading-state"')
    expect(html).toContain('data-face="loading"')
    expect(html).not.toContain('data-testid="ui-empty-state"')
    expect(html).not.toContain('data-testid="ui-error-state"')
  })

  // 这就是修案的实质：失败与「200 空数组」是两条分支，且失败优先，谁也不许冒充谁。
  it('加载 / 失败 / 空态三条分支各一条路径，失败排在空态前面', () => {
    const s = code()
    expect(s).toMatch(/<UiLoadingState v-if="alertsFace === 'loading'"/)
    expect(s).toMatch(/<UiErrorState\s+v-else-if="alertsFailure"/)
    expect(s).toMatch(/<UiEmptyState\s+v-else-if="alertsFace === 'empty'"/)
    expect(s).toContain(':data-face="alertsFace"')
    expect(s).toContain(':data-face="rulesFace"')
  })

  it('判脸只有一个出口：lib/alerts.js 的 faceOf 与 readFailureView，面板不再自己数 length === 0', () => {
    const s = code()
    expect(s).toContain('faceOf({')
    expect(s).toContain('readFailureView(err,')
    expect(s).not.toMatch(/alerts\.value\.length\s*[=!]==?\s*0/)
    expect(s).not.toMatch(/err\.response\?\.data\?\.detail \|\|/)
    for (const stale of ['暂时没有异常', 'insights.value', 'runDetection']) {
      expect(s).not.toContain(stale)
    }
  })

  it('重试按钮的有无交给 lib 判脸：没权限与登录失效都不给重试，真坏了才给「重新加载」', () => {
    const s = code()
    expect(s).toMatch(/:retryable="alertsFailure\.retryable"/)
    expect(s).toContain('retry-text="重新加载"')
    expect(s).toMatch(/:busy="alertsLoading"/)
    expect(s).not.toMatch(/:retryable="!denied"/)
  })

  it('状态一律走 ui 原语，手搓的 .empty-state / .error-state 不再回来', () => {
    const s = code()
    expect(s).not.toContain('class="empty-state"')
    expect(s).not.toMatch(/\.empty-state\s*\{/)
    expect(s).not.toMatch(/\.error-state\s*\{/)
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
    // A-5-2：进行态改吃 UiLoadingState，断言打在 SSR 真产物上而不是源码字符串
    expect(html).toContain('data-testid="ui-loading-state"')
    expect(html).toMatch(/<div class="ui-loading-state[^"]*" role="status" aria-busy="true"/)
    expect(html).not.toContain('class="panel-state"')
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

describe('DocumentPreviewModal · 预览进行态吃原语（A-5-4）', () => {
  // 这个弹窗的根节点是 <Teleport to="body">：SSR 把内容写进 teleport 缓冲区，
  // renderToString 只留下两枚注释标记。先把这件事本身钉住，免得下一轮有人误以为
  // 「SSR 断言没写是因为漏了」，或者反过来删用例凑绿。
  it('SSR 只留 teleport 标记：这一支的证据只能来自源码形状 + 原语实测', async () => {
    const html = await renderToString(h({
      render: () => h(DocumentPreviewModal, { open: true, loading: true, filename: '制度汇编.pdf', kind: 'pdf' }),
    }))
    expect(html).toContain('<!--teleport start-->')
    expect(html).not.toContain('data-testid="ui-loading-state"')
  })

  it('loading 那一支只认 UiLoadingState：位置、参数、旧裸文本零留痕', () => {
    const s = source('DocumentPreviewModal.vue')
    const loadingAt = s.indexOf('<UiLoadingState v-if="loading"')
    const errorAt = s.indexOf('<div v-else-if="error" class="preview-state')
    expect(loadingAt).toBeGreaterThan(-1)
    expect(loadingAt).toBeLessThan(errorAt)
    expect(s).toContain('label="正在加载预览..."')
    expect(s).toContain('variant="block"')
    expect(s).not.toMatch(/class="preview-state"[^>]*>正在加载预览/)
  })

  // 面板里不手写 role（写了就是第二套形状），所以 role=status 这件事由原语那一侧实测。
  it('block 档真产物带 role=status + aria-busy + 骨架块', async () => {
    const html = await renderToString(h(UiLoadingState, { label: '正在加载预览...', variant: 'block' }))
    expect(html).toContain('data-testid="ui-loading-block"')
    expect(html).toMatch(/<div class="ui-loading-state[^"]*" role="status" aria-busy="true"/)
    expect(html).toContain('正在加载预览...')
  })

  // 本批只换「进行中」这一支：失败脸与空脸仍是手搓 .preview-state（这个弹窗不在 A-3 的
  // 七个面板名单里，接线要另起一批），所以反向钉住它们的定义不许被顺手删掉。
  it('失败与空两支仍用 .preview-state，类定义必须留在文件里', () => {
    const s = source('DocumentPreviewModal.vue')
    expect(s).toMatch(/<div v-else-if="error" class="preview-state preview-error"/)
    expect(s).toMatch(/class="preview-state">暂无数据<\/div>/)
    expect(s).toContain('.preview-state {')
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


describe('ChatPanel · 会话空态 + 一次性失败提示（本面板不适用 R1(c) 判据，理由见注释）', () => {
  // 会话列表来自 lib/sessions.js 的模块级 store + localStorage，全程不发请求，
  // 所以「无权限 / 空列表」这个分叉在这里没有输入：没有 403 可判，也没有权限可缺。
  // SSE 三条腿（/ask、/ask/{id}/cancel、/approve）的鉴权失败由 sessions.js 流层负责，
  // 落到面板已是「这一次没成」的一次性结果，不是一条能重试的面板加载，故 retryable=false。
  it('SSR 首屏：无会话时画原语空态，文案一字不变，手搓的 .session-empty 不再出现', async () => {
    const html = await render(ChatPanel)
    expect(html).toContain('data-testid="ui-empty-state"')
    expect(html).toContain('暂无历史会话')
    expect(html).not.toContain('session-empty')
  })

  it('error 一条经 UiErrorState（role=alert 由原语给），warn/info 仍是原来的行内提示', () => {
    const s = source('ChatPanel.vue')
    expect(s).toMatch(/<UiErrorState v-if="streamNote && noteTone === 'error'" :title="streamNote" :retryable="false" dense \/>/)
    expect(s).toMatch(/<p v-else-if="streamNote"[^>]*role="status" data-testid="chat-note"/)
    expect(s).not.toContain('role="alert"')
  })

  it('被删分支的样式与两处色债一起清掉，warn 仍留在面板内', () => {
    const s = source('ChatPanel.vue')
    expect(s).not.toContain('.session-empty')
    expect(s).not.toContain('.stream-note.error')
    // 这两处字面量在别的规则里还有用，删除量由 lint:colors 棘轮记账，不在这里钉数
    expect(s).toContain('.stream-note.warn { color: #e6a23c; }')
  })

  it('面板不引入第二套取码器，也不把权限判据硬塞进本地态', () => {
    const s = source('ChatPanel.vue')
    expect(s).not.toContain('isPermissionDenied')
    expect(s).not.toMatch(/\berrorCode\b/)
  })
})


describe('ChartViewer · 取图进行态吃原语（A-5-5）', () => {
  // loadState 初值是 idle，SSR 只能拿到「该轮回答没有返回图表」那张脸；进行态要请求打到一半
  // 才出现，node 里没有网络层可打 —— 所以这一支钉源码形状，role 那一截由原语实测。
  it('三张脸顺序为 就绪 -> 进行 -> 失败，进行态只认 UiLoadingState', () => {
    const s = source('ChartViewer.vue')
    const at = (needle) => {
      const i = s.indexOf(needle)
      expect(i, needle).toBeGreaterThan(-1)
      return i
    }
    const ready = at(`v-if="loadState === 'ready'"`)
    const loading = at(`<UiLoadingState v-else-if="loadState === 'loading'"`)
    const failed = at(`v-else-if="loadState === 'error'"`)
    expect(ready).toBeLessThan(loading)
    expect(loading).toBeLessThan(failed)
    expect(s).toContain('label="正在获取图表…"')
    expect(s).toContain('variant="block"')
    // 旧进行态是自转 spinner，视觉文档 §8.4 第 5 条点名要骨架屏而不是转圈
    expect(s).not.toMatch(/class="chart-state-spinner"/)
    expect(s).not.toMatch(/<div v-else-if="loadState === 'loading'"[^>]*role="status"/)
  })

  it('dense 档真产物：role + aria-busy 由原语发，文案一字不差', async () => {
    const html = await renderToString(h(UiLoadingState, { label: '正在获取图表…', variant: 'block', dense: true }))
    expect(html).toMatch(/<div class="ui-loading-state[^"]*" role="status" aria-busy="true"/)
    expect(html).toContain('ui-loading-state--dense')
    expect(html).toContain('正在获取图表…')
  })

  // dense 不是审美选择而是等值：图表卡在 ChatPanel.vue:478 的消息气泡里，旧文案
  // .chart-state-text 是 12px，dense 档文案走 --t-xs(12px)；不带 dense 会变 --t-sm(13px)。
  it('字号等值有据：旧 .chart-state-text 仍是 12px，dense 走 --t-xs(12px)', () => {
    expect(source('ChartViewer.vue')).toMatch(/[.]chart-state-text \{[\s\S]*?font-size: 12px;/)
    expect(source('../assets/theme.css')).toContain('--t-xs: 12px')
    expect(source('../assets/theme.css')).toContain('--t-sm: 13px')
  })
})


describe('死 CSS 收口（A-5-6）：零引用的删掉，仍在用的不许顺手带走', () => {
  // 判据打在「定义还在不在」上，四条零引用规则各钉一条，删没删一眼可判。
  it('进行态换原语后零引用的规则已删：.panel-state / .data-state / spinner / chart-spin', () => {
    expect(source('../assets/theme.css')).not.toMatch(/[.]panel-state/)
    expect(source('DashboardPanel.vue')).not.toMatch(/[.]panel-state/)
    expect(source('DataPanel.vue')).not.toMatch(/[.]data-state/)
    expect(source('ChartViewer.vue')).not.toMatch(/[.]chart-state-spinner/)
    expect(source('ChartViewer.vue')).not.toMatch(/@keyframes chart-spin/)
  })

  // 反面断言：.preview-state 的失败/空两支与 .chart-state 家族都还有引用，
  // 删过头会让剩下的脸变成无样式裸文本。这条防的就是「为了凑棘轮数字乱删」。
  // A-6-2 改的就是这里：面板全部改接 UiEmptyState 之后，全局 `.empty-state` 落到零引用，
  // 于是它从「一条不少」那侧搬到「已删」这侧；参考稿作用域内那条仍在用，留作反证，
  // 免得下一次有人把它当同一条一起删。
  it('仍在服役的规则一条不少', () => {
    const theme = source('../assets/theme.css')
    expect(theme).not.toMatch(/^\.empty-state \{/m)
    expect(theme).toMatch(/[.]reference-dashboard \.empty-state \{/)
    const chart = source('ChartViewer.vue')
    expect(chart).toMatch(/[.]chart-state \{/)
    expect(chart).toMatch(/[.]chart-state-error \{/)
    const preview = source('DocumentPreviewModal.vue')
    expect(preview).toMatch(/[.]preview-state \{/)
    expect(preview).toMatch(/[.]preview-error \{/)
  })

  // 卡片表面那组规则里被摘掉的只有 .panel-state 一个选择器，同伴不许被牵连。
  it('theme.css 卡片组只摘掉 .panel-state 一个选择器，同伴还在原处', () => {
    const theme = source('../assets/theme.css')
    for (const keep of ['.panel-card,', '.hero-card,', '.mini-stat,', '.row-card,', '.insight-item,', '.metric-card,']) {
      expect(theme, keep).toContain(keep)
    }
  })
})
