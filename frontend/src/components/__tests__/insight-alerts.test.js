/**
 * W7 · 洞察页接真告警链（R1 裁定 (c) 的前端半边）+ 审批页定位说清（checklist L111）
 *
 * 环境是 node + @vue/server-renderer（仓库里没有 jsdom / @vue/test-utils，也不许 npm i），
 * 所以判据分三条腿，各管各的事，不假装验过自己验不了的：
 *   ① 真状态：把 lib/http 的 axios 实例换成 mock，直接跑组件自己的 setup() 取回真实绑定，
 *      再喂 401 / 403 / 200空 / 200有数据 四种响应进真的 loadAll()，读回组件自己算出的
 *      alertsFace 与 failure 视图。脸不是在测试里照抄一遍常量。
 *   ② 真产物：SSR 不跑 onMounted，所以 render(InsightPanel) 拿到的就是「还没拿到任何响应」
 *      那一帧；四种状态则用「同一份 setup() 绑定 + 组件自带的 ssrRender」渲染整屏 HTML。
 *      于是「403 被画成空态」这种缺陷会当场红在 HTML 上，而不是只红在正则上。
 *   ③ 源码形状：手填阈值表单、演示常量、审批按钮这类「点一次才看得到」的东西钉在源码上。
 *      注意要剥注释：本仓面板的头注释会如实交代历史缺陷（/insights/detect、待关注），
 *      不剥注释的断言会把「说明了为什么不用」误判成「还在用」。
 *
 * 后端码名（permission_denied 等）在本文件里是「输入」而不是「输出」：判据是喂真码进真
 * errorDetail / errorCodeOf（这两个不 mock），再断言界面拿到的句子已经没有人话之外的码名。
 * __tests__ 目录不在 lib/no-bare-code.test.js 的扫描范围内。
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'

// 只换网络层：errorDetail / errorCodeOf 保持真身，判据才不会被 mock 顺带改掉。
vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }
})

import { errorDetail, http } from '../../lib/http'
import { errorCodeOf } from '../../lib/errcodes'
import {
  ALERTS_EMPTY_DESCRIPTION,
  ALERTS_EMPTY_TITLE,
  ALERTS_FEED_LIMIT,
  ALERTS_LIMIT_NOTE,
  ALERTS_PATH,
  CHECK_PATH,
  PERMISSION_WHERE,
  RULES_EMPTY_DESCRIPTION,
  RULES_EMPTY_TITLE,
  RULES_PATH,
  RULE_OPERATORS,
  SCAN_REASON_MESSAGES,
  SHAPE_FAILURE_DESCRIPTION,
  advanceRuleDelete,
  checkOutcomeView,
  createRule,
  emptyRuleForm,
  faceOf,
  fetchAlerts,
  fetchRules,
  formatStamp,
  listRows,
  mapAlertRow,
  mapRuleRow,
  operatorLabel,
  readFailureView,
  removeRule,
  rulePath,
  ruleRequestBody,
  runCheck,
  shapeFailureView,
  validateRuleForm,
} from '../../lib/alerts'
import ApprovalPanel from '../ApprovalPanel.vue'
import ChatPanel from '../ChatPanel.vue'
import InsightPanel from '../InsightPanel.vue'
import { UiEmptyState, UiErrorState } from '../ui'

const source = name => readFileSync(new URL('../' + name, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const libSource = name => readFileSync(new URL('../../lib/' + name, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const render = component => renderToString(h({ render: () => h(component) }))

/** 后端码名不许出现在给人看的句子里（B-5 ②：码走独立通道，不进正文）。 */
const SNAKE = /[a-z][a-z0-9]*_[a-z0-9_]+/
/** 「把失败说成 0 个异常」的所有已知写法，四张脸一张都不许踩。 */
const ZERO_CLAIM = /0\s*(个|条)?\s*(异常|告警|风险)/

/** 剥掉块注释 / HTML 注释 / 行注释后的代码体：历史说明只许留在注释里，不许留在代码里。 */
function codeOnly(text) {
  return text
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter(line => !/^\s*\/\//.test(line))
    .join('\n')
}

/** 只留屏上真正给人读的正文：剥注释与标签。裸码名判据只能对它用，BEM 类名里的 __ 不是文案。 */
function visibleText(html) {
  return html.replace(/<!--[\s\S]*?-->/g, ' ').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
}

/** 屏上真正给人读的按钮文案：审批页「不许有批准按钮」判据用它，而不是整段 HTML。 */
function buttonLabels(html) {
  return (html.match(/<button[\s\S]*?<\/button>/g) || [])
    .map(tag => visibleText(tag))
    .filter(Boolean)
}

/**
 * 跑真组件的 setup()：借一个最小宿主组件把实例上下文递进去，onMounted 之类挂在真实例上，
 * 不会有「脱离实例调用」的噪声。返回的是编译产物里的原始绑定对象，ref 不解包，一律写 .value。
 */
async function mountBindings(component) {
  let bindings = null
  const Probe = {
    name: 'W7Probe',
    setup(props, ctx) {
      bindings = component.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Probe))
  expect(bindings, '组件应暴露可调用的 setup()').toBeTruthy()
  return bindings
}

/**
 * 把同一份绑定交回组件自己的 ssrRender 渲染整屏。
 * vitest 下 plugin-vue 产出的是 ssrRender（没有 render），所以整体展开组件、只替换 setup。
 */
const renderState = (component, bindings) => renderToString(h({ ...component, setup: () => bindings }))
const insightHtml = bindings => renderState(InsightPanel, bindings)

/** 401 / 403 / 500 的真形状：axios 的 { response: { status, data: { detail } } }。 */
function httpError(status, code) {
  const data = code === undefined ? undefined : { detail: code }
  return { response: { status, data }, message: 'Request failed with status code ' + status }
}

const ok = data => ({ data })
const boom = err => ({ boom: err })

/** GET 装一张「路径 -> 响应/异常」表；没登记的路径直接判错，防打歪的端点蒙混过关。 */
function routeGet(routes) {
  http.get.mockImplementation(async url => {
    if (!Object.prototype.hasOwnProperty.call(routes, url)) throw new Error('未预期的 GET 路径：' + url)
    const hit = routes[url]
    if (hit && hit.boom) throw hit.boom
    return { data: hit.data }
  })
}

function routePost(routes) {
  http.post.mockImplementation(async url => {
    if (!Object.prototype.hasOwnProperty.call(routes, url)) throw new Error('未预期的 POST 路径：' + url)
    const hit = routes[url]
    if (hit && hit.boom) throw hit.boom
    return { data: hit.data }
  })
}

/** 告警行 / 规则行的后端真形状（GET /alerts 六列、alert_rules 六列）。 */
function alertRow(overrides) {
  return Object.assign({
    id: 7,
    rule_id: 3,
    message: '差旅费合计 12800 大于阈值 8000',
    ai_analysis: '集中在 9 月，环比上升明显。',
    created_at: '2026-09-16T09:12:44.123456+08:00',
    read: false,
  }, overrides || {})
}

function ruleRow(overrides) {
  return Object.assign({ id: 3, name: '差旅费上限', metric: '差旅费', op: 'gt', threshold: 8000, enabled: true }, overrides || {})
}

const DENIED_TITLE = '这个账号没有查看告警的权限'
const RULE_DENIED_TITLE = '这个账号没有查看告警规则的权限'
const FAILED_TITLE = '告警列表没能读出来'

/** 喂一次响应，拿回「组件自己算出的状态 + 组件自己渲染出的整屏 HTML」。 */
async function faceFor(alertsSpec, rulesSpec) {
  routeGet({ [ALERTS_PATH]: alertsSpec, [RULES_PATH]: rulesSpec })
  const bindings = await mountBindings(InsightPanel)
  await bindings.loadAll()
  return { bindings, face: bindings.alertsFace.value, html: await insightHtml(bindings) }
}

beforeEach(() => {
  vi.clearAllMocks()
  http.delete.mockResolvedValue({ data: { status: 'ok' } })
})

describe('W7 判据① · 401 / 403 / 200空 / 200有数据 渲染出四种不同结果', () => {
  it('SSR 首屏（还没拿到任何响应）是加载脸，屏上不出现 0 也不出现空态文案', async () => {
    const html = await render(InsightPanel)
    expect(html).toContain('data-testid="alerts-panel"')
    expect(html).toContain('data-face="loading"')
    expect(html).toContain('data-testid="ui-loading-state"')
    expect(html).toContain('正在读取告警列表')
    expect(html).not.toContain(ALERTS_EMPTY_TITLE)
    expect(html).not.toContain('data-testid="ui-empty-state"')
    expect(html).not.toContain('data-testid="ui-error-state"')
    expect(html).not.toMatch(/>0</)
    expect(html).not.toMatch(ZERO_CLAIM)
  })

  it('401 -> 「登录状态已失效」，role=alert，不给重试按钮', async () => {
    const err = httpError(401, 'authentication_required')
    const { bindings, face, html } = await faceFor(boom(err), boom(err))
    expect(face).toBe('unauthorized')
    expect(html).toContain('data-testid="ui-error-state"')
    expect(html).toMatch(/<div class="ui-error-state[^"]*"[^>]*role="alert"/)
    expect(html).toContain('登录状态已失效')
    expect(html).toContain('请重新登录后再试')
    expect(html).not.toContain('data-testid="ui-error-retry"')
    expect(html).not.toContain(ALERTS_EMPTY_TITLE)
    expect(html).not.toMatch(ZERO_CLAIM)
    expect(bindings.summary.value.map(item => item.value)).toEqual(['未登录', '未登录'])
  })

  it('403 -> 「这个账号没有查看告警的权限」+ 去哪申请，且不渲染重试按钮', async () => {
    const err = httpError(403, 'permission_denied')
    const { bindings, face, html } = await faceFor(boom(err), boom(err))
    expect(face).toBe('denied')
    expect(html).toContain('data-testid="ui-error-state"')
    expect(html).toContain(DENIED_TITLE)
    expect(html).toContain('请联系管理员开通')
    expect(html).toContain(PERMISSION_WHERE)
    expect(html).not.toContain('data-testid="ui-error-retry"')
    expect(html).not.toContain(ALERTS_EMPTY_TITLE)
    expect(html).not.toContain(RULES_EMPTY_TITLE)
    expect(html).not.toMatch(ZERO_CLAIM)
    // 计数格在没权限时给的是「没有权限」，不是 0：0 只可能来自真拿到空数组。
    expect(bindings.summary.value.map(item => item.value)).toEqual(['没有权限', '没有权限'])
    expect(bindings.denied.value).toBe(true)
    expect(bindings.canManage.value).toBe(false)
  })

  it('403 时整页的写操作一起失效：巡检与新增规则按钮都 disabled', async () => {
    const err = httpError(403, 'permission_denied')
    const { html } = await faceFor(boom(err), boom(err))
    const buttons = html.match(/<button[\s\S]*?>/g) || []
    for (const testId of ['run-alert-check', 'create-rule', 'reload-alerts', 'reload-rules']) {
      expect(buttons.some(item => item.includes(testId)), testId + ' 应该在屏上').toBe(true)
    }
    expect(buttons.find(item => item.includes('run-alert-check'))).toContain('disabled')
    expect(buttons.find(item => item.includes('create-rule'))).toContain('disabled')
    expect(html).toContain('当前账号点不动它')
  })

  it('200 空数组 -> 「当前没有触发中的告警」，role=status，不是失败卡', async () => {
    const { face, html } = await faceFor(ok({ alerts: [] }), ok({ rules: [] }))
    expect(face).toBe('empty')
    expect(html).toContain('data-testid="ui-empty-state"')
    expect(html).toMatch(/<div class="ui-empty-state[^"]*"[^>]*role="status"/)
    expect(html).toContain(ALERTS_EMPTY_TITLE)
    expect(html).toContain(ALERTS_EMPTY_DESCRIPTION)
    expect(html).not.toContain('data-testid="ui-error-state"')
    expect(html).not.toContain(DENIED_TITLE)
    expect(html).not.toMatch(ZERO_CLAIM)
  })

  it('200 有行 -> 列表，行内是后端原话，状态卡全部让位', async () => {
    const rows = [alertRow(), alertRow({ id: 8, rule_id: 4, message: '库存周转天数 42 大于阈值 30', ai_analysis: '' })]
    const { bindings, face, html } = await faceFor(ok({ alerts: rows }), ok({ rules: [ruleRow()] }))
    expect(face).toBe('list')
    expect(html).toContain('data-testid="alert-rows"')
    expect(html).not.toContain('data-testid="ui-empty-state"')
    expect(html).not.toContain('data-testid="ui-error-state"')
    expect(html.match(/class="record-item"/g)).toHaveLength(2)
    expect(html).toContain('库存周转天数 42 大于阈值 30')
    expect(html).toContain('集中在 9 月，环比上升明显。')
    expect(html).toContain('2026-09-16 09:12')
    expect(html).toContain('规则 #')
    expect(bindings.alerts.value[0].ruleId).toBe('3')
    expect(bindings.rulesFace.value).toBe('list')
    // 后端没有「标记已读」端点，所以这里不放一个点不动的已读控件。
    expect(html).not.toContain('标记已读')
  })

  it('四张脸的 data-face 与整屏 HTML 两两不同（并成一张脸就是本单要修的缺陷）', async () => {
    const err401 = httpError(401, 'authentication_required')
    const err403 = httpError(403, 'permission_denied')
    const scenarios = [
      await faceFor(boom(err401), boom(err401)),
      await faceFor(boom(err403), boom(err403)),
      await faceFor(ok({ alerts: [] }), ok({ rules: [] })),
      await faceFor(ok({ alerts: [alertRow()] }), ok({ rules: [ruleRow()] })),
    ]
    expect(scenarios.map(item => item.face)).toEqual(['unauthorized', 'denied', 'empty', 'list'])
    expect(new Set(scenarios.map(item => item.face)).size).toBe(4)
    expect(new Set(scenarios.map(item => item.html)).size).toBe(4)
    for (const scenario of scenarios.slice(0, 3)) expect(scenario.html).not.toMatch(ZERO_CLAIM)
  })

  it('两条取数路径的 403 各自点名，都归 denied，不会有一条退成空态', async () => {
    const err = httpError(403, 'permission_denied')
    expect(faceOf({ failed: true, code: errorCodeOf(err) })).toBe('denied')
    const pairs = [[ALERTS_PATH, DENIED_TITLE], [RULES_PATH, RULE_DENIED_TITLE]]
    for (const [path, wantTitle] of pairs) {
      const other = path === ALERTS_PATH ? RULES_PATH : ALERTS_PATH
      routeGet({ [path]: boom(err), [other]: ok({ alerts: [], rules: [] }) })
      const bindings = await mountBindings(InsightPanel)
      await bindings.loadAll()
      const failure = path === ALERTS_PATH ? bindings.alertsFailure.value : bindings.rulesFailure.value
      expect(failure.face).toBe('denied')
      expect(failure.title).toBe(wantTitle)
      expect(failure.retryable).toBe(false)
      expect(failure.description).toContain(PERMISSION_WHERE)
    }
  })

  it('200 但 alerts 不是数组 -> 「坏了」脸并给重试，绝不画成空态', async () => {
    const { bindings, face, html } = await faceFor(ok({ alerts: 'not-a-list' }), ok({ rules: [] }))
    expect(face).toBe('error')
    expect(html).toContain('data-testid="ui-error-state"')
    expect(html).toContain(SHAPE_FAILURE_DESCRIPTION)
    expect(html).toContain('data-testid="ui-error-retry"')
    expect(html).not.toContain(ALERTS_EMPTY_TITLE)
    expect(html).not.toMatch(ZERO_CLAIM)
    expect(bindings.summary.value[0].value).toBe('没读到')
  })

  it('403 但响应体丢了也还是没权限脸（按 HTTP 状态归类），不许退成空态', async () => {
    const err = { response: { status: 403 }, message: 'Request failed with status code 403' }
    const { face, html } = await faceFor(boom(err), boom(err))
    expect(face).toBe('denied')
    expect(html).toContain(DENIED_TITLE)
  })

  it('连不上服务（只有 request，没有 response）-> error 脸，不是空态', async () => {
    const err = { request: {}, message: 'Network Error' }
    const { face, html } = await faceFor(boom(err), boom(err))
    expect(face).toBe('error')
    expect(html).toContain('连不上服务，请确认网络或稍后重试。')
    expect(html).toContain('data-testid="ui-error-retry"')
    expect(html).not.toContain(ALERTS_EMPTY_TITLE)
  })

  it('权限脸不许把裸码名印进正文，也不许留旧页的演示说法', async () => {
    const err = httpError(403, 'permission_denied')
    const { html } = await faceFor(boom(err), boom(err))
    expect(visibleText(html)).not.toMatch(SNAKE)
    for (const stale of ['演示数据', '待关注', '暂时没有异常', '输入行数', 'data-demo=']) {
      expect(html).not.toContain(stale)
    }
  })
})

/**
 * 后端路由真源。手法与 lib/errcodes.test.js 的码表对账一致：读 git 对象而不是工作树副本，
 * 因为各 worktree 的 app/** 停在自己的分支点上，拿过期副本对账等于稳定假绿。
 * 取不到 ref 或解析不出装饰器一律抛红，禁止 skip。
 */
const BACKEND_REF = 'codex/data-file-catalog'
const BACKEND_ALERTS = 'app/api/v1/alerts.py'

function backendRoutes() {
  let text
  try {
    text = execFileSync('git', ['show', BACKEND_REF + ':' + BACKEND_ALERTS], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
  } catch (cause) {
    throw new Error('读不到后端真源 ' + BACKEND_REF + ':' + BACKEND_ALERTS + '（git show 失败：' + cause.message + '）。路由对账不许降级。')
  }
  if (!text || !text.trim()) throw new Error('git show ' + BACKEND_REF + ':' + BACKEND_ALERTS + ' 返回空内容，无法对账。')
  const routes = []
  for (const line of text.split(/\r?\n/)) {
    const hit = /^@router\.(get|post|put|patch|delete)\("([^"]+)"\)/.exec(line.trim())
    if (hit) routes.push(hit[1].toUpperCase() + ' ' + hit[2])
  }
  if (!routes.length) throw new Error('解析不到任何 @router 装饰器：后端形状变了，要同步改这里的解析，不许让它退化成空对账。')
  return routes
}

const flush = async () => {
  for (let round = 0; round < 8; round += 1) await new Promise(resolve => { setTimeout(resolve, 0) })
}

describe('W7 判据② · 手填阈值表单与演示常量整块摘掉（只准留在头注释的历史交代里）', () => {
  const code = () => codeOnly(source('InsightPanel.vue'))
  const alertsCode = () => codeOnly(libSource('alerts.js'))

  // 先自证剥注释这一步不是走过场：注释里的旧端点会被摘掉，正文里的中文说明会留下。
  it('判据自证：codeOnly 确实会摘掉注释里的旧端点，不误伤正文', () => {
    const sample = '<!-- 旧页打的是 /insights/detect -->\n/* 待关注 N 条是假的 */\n<template>\n  <p>当前没有触发中的告警</p>\n</template>\n'
    expect(codeOnly(sample)).not.toContain('/insights/detect')
    expect(codeOnly(sample)).not.toContain('待关注')
    expect(codeOnly(sample)).toContain('当前没有触发中的告警')
  })

  it('老页面的标识、老端点、老文案在代码体里一个都不留', () => {
    const stale = ['/insights/detect', 'demoRows', 'runDetection', '暂时没有异常', '待关注', '输入行数',
      '新增一行', 'row-card', 'row-fields', 'insights-panel', 'insights-demo', 'severity']
    for (const word of stale) expect(code(), '代码体里不该再有：' + word).not.toContain(word)
  })

  it('不引用 devFixtures，也不挂演示徽标与 data-demo', () => {
    for (const word of ['devFixtures', 'demo-flag', 'demo-note', 'data-demo', '演示数据', '演示']) {
      expect(code()).not.toContain(word)
      expect(alertsCode()).not.toContain(word)
    }
  })

  it('没有任何写死的阈值/样例数值：阈值只可能是操作者填进规则表单的那一格', () => {
    expect(code()).not.toMatch(/threshold:\s*['"]?[0-9]/)
    expect(code()).not.toMatch(/current:\s*['"]?[0-9]/)
    expect(code()).not.toMatch(/previous:\s*['"]?[0-9]/)
    expect(code()).not.toMatch(/department:\s*['"]/)
    expect(alertsCode()).not.toMatch(/threshold:\s*['"]?[0-9]/)
    // 阈值这一格是「新增规则」表单的一部分，值经 ruleRequestBody 变成 number 再交给 POST。
    expect(code()).toContain('v-model="ruleForm.threshold"')
    expect(code()).toContain('createRule(ruleForm.value)')
    expect(alertsCode()).toContain('threshold: thresholdValue(source.threshold)')
    // 既然阈值只能由操作者填：空着提交必须被拦下，而不是静默取 0。
    expect(validateRuleForm(emptyRuleForm()).errors.threshold).toBeTruthy()
  })

  it('样式只吃 token：本单不动 assets，面板 scoped 里不许新增裸色值', () => {
    const s = source('InsightPanel.vue')
    expect(s).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(s).not.toMatch(/rgba?\(/)
    expect(s).toContain('var(--')
  })

  it('状态一律走 ui 原语，不再手搓 .empty-state / .error-state', () => {
    const s = source('InsightPanel.vue')
    expect(code()).not.toMatch(/class="[^"]*empty-state/)
    expect(code()).not.toMatch(/class="[^"]*error-state/)
    for (const primitive of ['UiEmptyState', 'UiErrorState', 'UiLoadingState']) {
      expect(s).toContain(primitive)
    }
    expect(s).toContain('from ' + "'./ui'")
  })
})

describe('W7 判据② 追加 · 五个端点是后端真存在的路由，且路径只从 lib/alerts.js 出一次', () => {
  const code = () => codeOnly(source('InsightPanel.vue'))
  const alertsCode = () => codeOnly(libSource('alerts.js'))

  it('后端 GET/POST/DELETE 五条路由都在（读 git 对象对账，不照抄工单行号）', () => {
    const routes = backendRoutes()
    for (const want of ['GET /alerts', 'GET /alerts/rules', 'POST /alerts/rules', 'POST /alerts/check']) {
      expect(routes, '后端没有这条路由：' + want).toContain(want)
    }
    expect(routes.some(item => /^DELETE \/alerts\/rules\/\{rule_id\}$/.test(item))).toBe(true)
  })

  it('前端声明的每条路径都能在后端找到同动词路由（反向对账，防自造端点）', () => {
    const routes = new Set(backendRoutes())
    expect(routes.has(ALERTS_PATH)).toBe(false)
    expect(routes.has('GET ' + ALERTS_PATH)).toBe(true)
    expect(routes.has('GET ' + RULES_PATH)).toBe(true)
    expect(routes.has('POST ' + RULES_PATH)).toBe(true)
    expect(routes.has('POST ' + CHECK_PATH)).toBe(true)
    expect(routes.has('DELETE ' + rulePath(41))).toBe(false)
    expect(rulePath(41)).toBe('/alerts/rules/41')
    expect(rulePath('42')).toBe('/alerts/rules/42')
    expect(rulePath('7; DROP TABLE')).toBe('')
    expect(rulePath(null)).toBe('')
  })

  it('取数只走 lib/alerts.js 的五个函数，面板里不再手写路径、不再用旧 api 封装', () => {
    for (const name of ['fetchAlerts(', 'fetchRules(', 'createRule(', 'removeRule(', 'runCheck(']) {
      expect(code(), '面板没接上 ' + name).toContain(name)
    }
    expect(code()).toContain("from '../lib/alerts'")
    expect(code()).not.toMatch(/from '..\/lib\/api'/)
    expect(code()).not.toMatch(/\bapi\.(get|post|put|patch|delete)\(/)
    expect(code()).not.toMatch(/['"]\/alerts|['"]\/insights|['"]\/dashboard/)
    expect(alertsCode()).toContain("export const ALERTS_PATH = '/alerts'")
    expect(alertsCode()).toContain("export const RULES_PATH = '/alerts/rules'")
    expect(alertsCode()).toContain("export const CHECK_PATH = '/alerts/check'")
  })

  it('比较符与后端 OPS 同集：多给一档 POST 就 400', () => {
    expect(RULE_OPERATORS.map(item => item.value)).toEqual(['gt', 'gte', 'lt', 'lte'])
    const src = execFileSync('git', ['show', BACKEND_REF + ':' + BACKEND_ALERTS], { encoding: 'utf8' })
    for (const op of ['gt', 'gte', 'lt', 'lte']) {
      expect(new RegExp('["\']' + op + '["\']').test(src), '后端 OPS 里没有 ' + op).toBe(true)
    }
  })
})

describe('W7 请求编排 · 进页面只读，写操作只认人工点击', () => {
  const emptyRoutes = () => ({ [ALERTS_PATH]: ok({ alerts: [] }), [RULES_PATH]: ok({ rules: [] }) })

  it('loadAll 只发两条 GET：不发巡检，也不发任何 DELETE', async () => {
    routeGet(emptyRoutes())
    routePost({})
    const bindings = await mountBindings(InsightPanel)
    await bindings.loadAll()
    expect(http.get.mock.calls.map(call => call[0])).toEqual([ALERTS_PATH, RULES_PATH])
    expect(http.post.mock.calls).toHaveLength(0)
    expect(http.delete.mock.calls).toHaveLength(0)
  })

  it('手动巡检：POST /alerts/check 之后重读列表，回执按 scan_scope 说真话', async () => {
    routeGet(emptyRoutes())
    routePost({ [CHECK_PATH]: ok({ triggered: [], scan_scope: { evaluated_files: ['费用.xlsx', '库存.csv'] } }) })
    const bindings = await mountBindings(InsightPanel)
    await bindings.loadAll()
    http.get.mockClear()
    await bindings.runManualCheck()
    expect(http.post.mock.calls.map(call => call[0])).toEqual([CHECK_PATH])
    expect(bindings.checkOutcome.value.kind).toBe('clear')
    expect(http.get.mock.calls.map(call => call[0])).toEqual([ALERTS_PATH])
    const html = await insightHtml(bindings)
    expect(html).toContain('data-testid="check-receipt"')
    expect(html).toContain('data-kind="clear"')
    expect(html).toContain('本轮按 2 个数据文件判定')
  })

  it('一个文件都没读到 -> 「本轮巡检没有判定点」，不许说成没有异常', async () => {
    routeGet(emptyRoutes())
    routePost({ [CHECK_PATH]: ok({ triggered: [], scan_scope: { evaluated_files: [], reason: 'no_data_files' } }) })
    const bindings = await mountBindings(InsightPanel)
    await bindings.runManualCheck()
    expect(bindings.checkOutcome.value.kind).toBe('no-target')
    const html = await insightHtml(bindings)
    expect(html).toContain('数据目录里没有可分析的数据文件')
    expect(html).not.toMatch(ZERO_CLAIM)
  })

  it('规则增删失败也要分脸：403 不给重试，普通失败给', async () => {
    routeGet({ [ALERTS_PATH]: ok({ alerts: [] }), [RULES_PATH]: ok({ rules: [] }) })
    routePost({ [RULES_PATH]: boom(httpError(403, 'permission_denied')) })
    const bindings = await mountBindings(InsightPanel)
    await bindings.loadAll()
    bindings.ruleForm.value = { name: '现金余额下限', metric: '现金余额', op: 'lt', threshold: '50000' }
    await bindings.addRule()
    expect(bindings.ruleSaveFailure.value.face).toBe('denied')
    expect(bindings.ruleSaveFailure.value.retryable).toBe(false)
    expect(bindings.rulesFailure.value).toBe(null)
    const html = await insightHtml(bindings)
    expect(html).toContain('这个账号没有新增告警规则的权限')
    expect(visibleText(html)).not.toMatch(SNAKE)
    expect(http.get.mock.calls.map(call => call[0])).toEqual([ALERTS_PATH, RULES_PATH])
  })

  it('新增规则：不过校验一个请求都不发；过了才 POST 并把表单清空', async () => {
    routeGet({ [ALERTS_PATH]: ok({ alerts: [] }), [RULES_PATH]: ok({ rules: [ruleRow()] }) })
    routePost({ [RULES_PATH]: ok({ id: 9 }) })
    const bindings = await mountBindings(InsightPanel)
    await bindings.loadAll()
    bindings.ruleForm.value = { name: '  ', metric: '', op: 'nope', threshold: 'abc' }
    await bindings.addRule()
    expect(http.post.mock.calls).toHaveLength(0)
    expect(Object.keys(bindings.ruleErrors.value).sort()).toEqual(['metric', 'name', 'op', 'threshold'])
    bindings.ruleForm.value = { name: ' 现金余额下限 ', metric: ' 现金余额 ', op: 'lt', threshold: '50000' }
    await bindings.addRule()
    expect(http.post.mock.calls.map(call => call[0])).toEqual([RULES_PATH])
    expect(http.post.mock.calls[0][1]).toEqual({ name: '现金余额下限', metric: '现金余额', op: 'lt', threshold: 50000 })
    expect(bindings.ruleForm.value).toEqual(emptyRuleForm())
    expect(bindings.rules.value).toHaveLength(1)
  })

  it('删除规则两步确认：第一次点击只点亮「确认删除？」，不发请求', async () => {
    routeGet({ [ALERTS_PATH]: ok({ alerts: [] }), [RULES_PATH]: ok({ rules: [ruleRow(), ruleRow({ id: 4, name: '现金余额下限' })] }) })
    const bindings = await mountBindings(InsightPanel)
    await bindings.loadAll()
    const first = bindings.rules.value[0]
    const second = bindings.rules.value[1]
    bindings.askDeleteRule(first)
    expect(http.delete.mock.calls).toHaveLength(0)
    expect(bindings.ruleDeleteLabel(first)).toBe('确认删除？')
    // 待确认只有一行：点亮另一行必须把上一行顶回「删除」，否则一次错位点击能删掉没点过的行。
    bindings.askDeleteRule(second)
    expect(http.delete.mock.calls).toHaveLength(0)
    expect(bindings.ruleDeleteLabel(first)).toBe('删除')
    expect(bindings.ruleDeleteLabel(second)).toBe('确认删除？')
    bindings.askDeleteRule(second)
    await flush()
    expect(http.delete.mock.calls.map(call => call[0])).toEqual([RULES_PATH + '/4'])
    expect(bindings.pendingRuleId.value).toBe('')
  })

  it('第二次点击才真发 DELETE，路径带编号；删完重读列表', async () => {
    routeGet({ [ALERTS_PATH]: ok({ alerts: [] }), [RULES_PATH]: ok({ rules: [ruleRow()] }) })
    const bindings = await mountBindings(InsightPanel)
    await bindings.loadAll()
    const row = bindings.rules.value[0]
    bindings.askDeleteRule(row)
    await bindings.deleteRuleRow(row)
    expect(http.delete.mock.calls.map(call => call[0])).toEqual([RULES_PATH + '/3'])
    expect(http.get.mock.calls.filter(call => call[0] === RULES_PATH).length).toBe(2)
    expect(bindings.ruleDeleteFailure.value).toBe(null)
  })

  it('后端说这条已经不在了 -> 明说并重读，不装作删成功了', async () => {
    routeGet({ [ALERTS_PATH]: ok({ alerts: [] }), [RULES_PATH]: ok({ rules: [ruleRow()] }) })
    http.delete.mockResolvedValue({ data: { status: 'not_found' } })
    const bindings = await mountBindings(InsightPanel)
    await bindings.loadAll()
    await bindings.deleteRuleRow(bindings.rules.value[0])
    expect(bindings.ruleDeleteFailure.value.title).toBe('这条规则已经不在了，列表已重新读取')
    expect(bindings.ruleDeleteFailure.value.face).toBe('error')
  })

  it('编号不是数字时连请求都不发：宁可不动也不发一条打歪的 DELETE', async () => {
    routeGet({ [ALERTS_PATH]: ok({ alerts: [] }), [RULES_PATH]: ok({ rules: [ruleRow({ id: 'not-a-number' })] }) })
    const bindings = await mountBindings(InsightPanel)
    await bindings.loadAll()
    const row = bindings.rules.value[0]
    bindings.askDeleteRule(row)
    await bindings.deleteRuleRow(row)
    expect(http.delete.mock.calls).toHaveLength(0)
    expect(bindings.ruleDeleteFailure.value.title).toBe('这条规则的编号不对，删除没有发出')
  })

  it('取满后端 LIMIT 100 条时要说明「这里不是全部」', async () => {
    const rows = []
    for (let index = 0; index < ALERTS_FEED_LIMIT; index += 1) rows.push(alertRow({ id: index + 1 }))
    routeGet({ [ALERTS_PATH]: ok({ alerts: rows }), [RULES_PATH]: ok({ rules: [] }) })
    const bindings = await mountBindings(InsightPanel)
    await bindings.loadAll()
    expect(bindings.alerts.value).toHaveLength(ALERTS_FEED_LIMIT)
    const html = await insightHtml(bindings)
    expect(html).toContain(ALERTS_LIMIT_NOTE)
  })

  it('后端回来的行缺字段也不崩，并给一句人话而不是 undefined', async () => {
    routeGet({ [ALERTS_PATH]: ok({ alerts: [{ id: 1 }] }), [RULES_PATH]: ok({ rules: [{ id: 2 }] }) })
    const bindings = await mountBindings(InsightPanel)
    await bindings.loadAll()
    expect(bindings.alerts.value[0].message).toBe('这条告警没有留下说明文字。')
    expect(bindings.rules.value[0].name).toBe('未命名规则')
    const html = await insightHtml(bindings)
    expect(html).not.toContain('undefined')
    expect(html).not.toContain('NaN')
  })

  it('告警与规则的脸互不污染：一边没权限不拖累另一边读列表', async () => {
    routeGet({ [ALERTS_PATH]: boom(httpError(403, 'permission_denied')), [RULES_PATH]: ok({ rules: [ruleRow()] }) })
    const bindings = await mountBindings(InsightPanel)
    await bindings.loadAll()
    expect(bindings.alertsFace.value).toBe('denied')
    expect(bindings.rulesFace.value).toBe('list')
    expect(bindings.canManage.value).toBe(false)
    const html = await insightHtml(bindings)
    expect(html).toContain('data-face="denied"')
    expect(html).toContain('data-face="list"')
    expect(html.match(/data-face=/g)).toHaveLength(2)
  })
})


// ==================== 判据③：审批页的定位 ====================

describe('W7 判据③ · 审批页是报销政策自查工具，不是审批', () => {
  const approvalCode = () => codeOnly(source('ApprovalPanel.vue'))

  it('界面自己说清定位：自查工具、不办理审批、不生成工单', () => {
    const s = source('ApprovalPanel.vue')
    for (const phrase of ['报销自查', '它不办理审批', '自查工具，不是审批', '入口在对话页',
      '不会生成工单', '不会记在任何人名下', '不会改变任何单据的状态']) {
      expect(s).toContain(phrase)
    }
    expect(s).toContain('data-testid="approval-scope-note"')
    expect(s).toContain('<h4>自查参数</h4>')
    expect(s).toContain('<h4>自查结论</h4>')
    expect(s).toContain('重新自查')
  })

  it('判据自证：「批准 / 驳回」只许活在解释性注释里，代码体与按钮一个都不留', () => {
    const s = source('ApprovalPanel.vue')
    expect(s).toContain('批准与驳回按钮')
    const code = approvalCode()
    expect(code).not.toMatch(/批准|驳回/)
    expect(code).not.toMatch(/工单列表|待我审批|一键通过/)
  })

  it('整屏只渲染一个按钮，文案是「重新自查」，没有任何审批动作', async () => {
    const html = await render(ApprovalPanel)
    const labels = buttonLabels(html)
    expect(labels).toEqual(['重新自查'])
    expect(labels.join(' / ')).not.toMatch(/批准|驳回|同意|否决|拒绝|通过|不通过/)
  })

  it('屏上不摆「待审批 N 条」这种无处可取的数字，并说明为什么没有待办列表', async () => {
    const text = visibleText(await render(ApprovalPanel))
    expect(text).not.toMatch(/待审批\s*\d+/)
    expect(text).not.toMatch(/审批\s*\d+\s*条/)
    expect(text).toContain('挂起待办')
    expect(text).toContain('自查工具，不是审批')
  })

  it('这一页只发一个请求：预审端点。没有任何工单/告警端点，也不复制洞察页那套判定', () => {
    const code = approvalCode()
    const calls = code.match(/(api|http|axios)\.(get|post|put|patch|delete)\(/g) || []
    expect(calls).toHaveLength(1)
    expect(code).toContain("api.post('/approval/precheck'")
    for (const banned of ['/approval/approve', '/approval/reject', '/approval/pending',
      '/work-orders', '/work_orders', '/tickets', '/alerts', "'/approve'"]) {
      expect(code).not.toContain(banned)
    }
    expect(source('ApprovalPanel.vue')).not.toMatch(/alerts/i)
  })

  it('人工确认的入口全仓只有一个：对话页那张 HITL 卡片', () => {
    const chat = source('ChatPanel.vue')
    expect(chat).toContain('async function approve(')
    expect(chat).toContain('hitl-btn approve')
    expect(chat).toContain('确认执行')
    expect(chat).toContain('拒绝这个动作')
    expect(chat).toContain("'/approve'")
  })
})

// ==================== lib/alerts.js：判脸与归码矩阵 ====================

describe('W7 lib/alerts.js · 判脸与归码矩阵（R1 裁定 (c) 的逻辑全收在这张表里）', () => {
  const failureArgs = { deniedTitle: DENIED_TITLE, failedTitle: FAILED_TITLE }

  it('faceOf：loading 最优先，failed 次之，只有真 200 空数组才是 empty', () => {
    expect(faceOf({ loading: true, rowCount: 5 })).toBe('loading')
    expect(faceOf({ loading: true, failed: true, code: 'permission_denied' })).toBe('loading')
    expect(faceOf({ failed: true, code: 'authentication_required' })).toBe('unauthorized')
    expect(faceOf({ failed: true, code: 'permission_denied' })).toBe('denied')
    expect(faceOf({ failed: true, code: 'internal_error' })).toBe('error')
    expect(faceOf({ failed: true, code: '' })).toBe('error')
    expect(faceOf({ failed: true, code: '', rowCount: 9 })).toBe('error')
    expect(faceOf({ rowCount: 0 })).toBe('empty')
    expect(faceOf({ rowCount: 1 })).toBe('list')
    expect(faceOf({ rowCount: '12' })).toBe('list')
    expect(faceOf({ rowCount: NaN })).toBe('empty')
    expect(faceOf({ rowCount: undefined })).toBe('empty')
    expect(faceOf()).toBe('empty')
  })

  it('readFailureView · 401：登录失效一张脸，不给重试，不留裸码名', () => {
    const view = readFailureView(httpError(401, 'authentication_required'), failureArgs)
    expect(view.face).toBe('unauthorized')
    expect(view.title).toBe('登录状态已失效')
    expect(view.retryable).toBe(false)
    expect(view.codeLabel).toBe('')
    expect(view.description).toContain('请重新登录')
    expect(view.description).not.toMatch(SNAKE)
  })

  it('readFailureView · 403：点名去哪申请，并明说重新登录不会凭空变出权限', () => {
    const view = readFailureView(httpError(403, 'permission_denied'), failureArgs)
    expect(view.face).toBe('denied')
    expect(view.title).toBe(DENIED_TITLE)
    expect(view.retryable).toBe(false)
    expect(view.codeLabel).toBe('')
    expect(view.description).toContain('请联系管理员')
    expect(view.description).toContain(PERMISSION_WHERE)
    expect(view.description).not.toMatch(ZERO_CLAIM)
  })

  it('readFailureView · 403 带一个后端新加的未知码：仍是没权限脸 + 错误码小字，绝不退成空态', () => {
    const view = readFailureView(httpError(403, 'alert_scope_required'), failureArgs)
    expect(view.face).toBe('denied')
    expect(view.title).toBe(DENIED_TITLE)
    expect(view.codeLabel).toBe('错误码：alert_scope_required')
    expect(view.description).toContain('请联系管理员开通')
  })

  it('readFailureView · 500 与连不上服务：都归 error 并给重试', () => {
    const broken = readFailureView(httpError(500, 'internal_error'), failureArgs)
    expect(broken.face).toBe('error')
    expect(broken.title).toBe(FAILED_TITLE)
    expect(broken.retryable).toBe(true)
    expect(broken.description).toContain('系统内部出现异常')
    const offline = readFailureView({ request: {}, message: 'Network Error' }, failureArgs)
    expect(offline.face).toBe('error')
    expect(offline.retryable).toBe(true)
    expect(offline.description).toContain('连不上服务')
  })

  it('readFailureView · 权限范围判不出来不是「没权限」：403 + resource_scope_missing 归 error', () => {
    const missing = readFailureView(httpError(403, 'resource_scope_missing'), failureArgs)
    expect(missing.face).toBe('error')
    expect(missing.retryable).toBe(true)
    expect(missing.description).toContain('判断不了你能不能看')
    expect(missing.codeLabel).toBe('')
    const scoped = readFailureView(httpError(403, 'department_scope_denied'), failureArgs)
    expect(scoped.face).toBe('denied')
    expect(scoped.title).toBe(DENIED_TITLE)
  })

  it('shapeFailureView：结构不对只有「坏了」一张脸，永不与空态共用', () => {
    expect(shapeFailureView(FAILED_TITLE)).toEqual({
      face: 'error', title: FAILED_TITLE, description: SHAPE_FAILURE_DESCRIPTION, codeLabel: '', retryable: true,
    })
    expect(faceOf({ failed: true, code: '', rowCount: 0 })).toBe('error')
  })

  it('常量：LIMIT 100 与「这里不是全部」成对出现；空态文案不许被写成「一切正常」或「你没权限」', () => {
    expect(ALERTS_FEED_LIMIT).toBe(100)
    expect(ALERTS_LIMIT_NOTE).toContain('100')
    expect(ALERTS_EMPTY_TITLE).toBe('当前没有触发中的告警')
    expect(ALERTS_EMPTY_DESCRIPTION).toContain('不等于业务一切正常')
    expect(ALERTS_EMPTY_DESCRIPTION).toContain('也不等于你的账号没有权限')
    expect(RULES_EMPTY_TITLE).toBe('还没有配置任何告警规则')
    expect(RULES_EMPTY_DESCRIPTION).toContain('永远不会产生告警')
    expect(ALERTS_EMPTY_TITLE + ALERTS_EMPTY_DESCRIPTION).not.toMatch(ZERO_CLAIM)
    expect(SHAPE_FAILURE_DESCRIPTION).toContain('结构不对')
  })

  it('listRows 只认键下的数组：字符串、对象、缺键、错键一律判 null', () => {
    expect(listRows({ alerts: [] }, 'alerts')).toEqual([])
    expect(listRows({ alerts: [1] }, 'alerts')).toEqual([1])
    expect(listRows({ alerts: 'not-a-list' }, 'alerts')).toBeNull()
    expect(listRows({ rules: {} }, 'rules')).toBeNull()
    expect(listRows({}, 'alerts')).toBeNull()
    expect(listRows(null, 'alerts')).toBeNull()
    expect(listRows({ alerts: [] }, 'rules')).toBeNull()
  })

  it('formatStamp：真库带 +08 偏移、内存模式是 ISO 串，两种都取到分钟且不做时区换算', () => {
    expect(formatStamp('2026-09-16T09:12:44.123456+08:00')).toBe('2026-09-16 09:12')
    expect(formatStamp('2026-09-16 09:12:44')).toBe('2026-09-16 09:12')
    expect(formatStamp('2026-09-16')).toBe('2026-09-16')
    expect(formatStamp('   ')).toBe('')
    expect(formatStamp(null)).toBe('')
    expect(formatStamp(undefined)).toBe('')
    expect(formatStamp(123)).toBe('')
  })

  it('rulePath：编号必须是纯数字，否则空串——面板据此一个请求都不发', () => {
    expect(rulePath(4)).toBe(RULES_PATH + '/4')
    expect(rulePath('4')).toBe(RULES_PATH + '/4')
    expect(rulePath(' 4 ')).toBe(RULES_PATH + '/4')
    expect(rulePath('4; DROP')).toBe('')
    expect(rulePath('4/../../x')).toBe('')
    expect(rulePath('abc')).toBe('')
    expect(rulePath('')).toBe('')
    expect(rulePath(null)).toBe('')
    expect(rulePath(undefined)).toBe('')
  })

  it('operatorLabel 与后端 OPS 同集：翻成人话，认不下就说认不下', () => {
    expect(RULE_OPERATORS.map(item => item.value).sort()).toEqual(['gt', 'gte', 'lt', 'lte'])
    expect(operatorLabel('gt')).toBe('大于')
    expect(operatorLabel('gte')).toBe('大于等于')
    expect(operatorLabel('lt')).toBe('小于')
    expect(operatorLabel('lte')).toBe('小于等于')
    expect(operatorLabel(' GE ')).toBe('无法识别的比较方式')
    expect(operatorLabel('')).toBe('无法识别的比较方式')
    expect(operatorLabel(undefined)).toBe('无法识别的比较方式')
  })

  it('mapAlertRow：后端六列 -> 视图字段，缺字段给一句人话而不是 undefined', () => {
    const row = mapAlertRow(alertRow())
    expect(row).toEqual({
      id: '7', ruleId: '3', message: alertRow().message,
      analysis: '集中在 9 月，环比上升明显。', createdAt: '2026-09-16 09:12',
    })
    expect(Object.keys(row)).not.toContain('read')
    expect(mapAlertRow({}).message).toBe('这条告警没有留下说明文字。')
    expect(mapAlertRow(alertRow({ message: '   ' })).message).toBe('这条告警没有留下说明文字。')
    expect(mapAlertRow(alertRow({ ai_analysis: null })).analysis).toBe('')
    expect(mapAlertRow(null)).toEqual({ id: '', ruleId: '', message: '这条告警没有留下说明文字。', analysis: '', createdAt: '' })
  })

  it('mapRuleRow：缺阈值/缺指标给「没有登记」而不是 NaN，enabled 缺省按启用', () => {
    const row = mapRuleRow(ruleRow())
    expect(row.thresholdText).toBe('8000')
    expect(row.opLabel).toBe('大于')
    expect(row.enabled).toBe(true)
    const bare = mapRuleRow({ id: 1 })
    expect(bare.name).toBe('未命名规则')
    expect(bare.metricText).toBe('没有登记指标列')
    expect(bare.thresholdText).toBe('没有登记阈值')
    expect(bare.opLabel).toBe('无法识别的比较方式')
    expect(mapRuleRow(ruleRow({ enabled: false })).enabled).toBe(false)
  })

  it('advanceRuleDelete：一次错位的点击删不掉没点过的行', () => {
    expect(advanceRuleDelete('', '7')).toBe('arm')
    expect(advanceRuleDelete('7', '7')).toBe('execute')
    expect(advanceRuleDelete('7', '8')).toBe('arm')
    expect(advanceRuleDelete('7', '')).toBe('idle')
    expect(advanceRuleDelete('7', null)).toBe('idle')
    expect(advanceRuleDelete('7', 7)).toBe('execute')
    expect(advanceRuleDelete(7, '7')).toBe('execute')
  })

  it('checkOutcomeView 四类：命中 / 没有判定点 / 真清白 / 说不清，四句话不许混成「没有异常」', () => {
    const hit = checkOutcomeView({ triggered: [{ id: 1 }, { id: 2 }], scan_scope: { evaluated_files: ['a.csv'] } })
    expect(hit.kind).toBe('hit')
    expect(hit.count).toBe(2)
    expect(hit.title).toBe('本轮巡检新触发 2 条告警')
    const noTarget = checkOutcomeView({ triggered: [], scan_scope: { reason: 'no_data_files' } })
    expect(noTarget.kind).toBe('no-target')
    expect(noTarget.detail).toBe('数据目录里没有可分析的数据文件，本轮巡检没有判定点。')
    expect(noTarget.detail).toBe(SCAN_REASON_MESSAGES.no_data_files)
    const clear = checkOutcomeView({ triggered: [], scan_scope: { evaluated_files: ['a.csv', 'b.csv', ''] } })
    expect(clear.kind).toBe('clear')
    expect(clear.count).toBe(0)
    expect(clear.detail).toBe('本轮按 2 个数据文件判定，没有任何一条规则被触发。')
    expect(checkOutcomeView({}).kind).toBe('unknown')
    expect(checkOutcomeView(null).kind).toBe('unknown')
    expect(checkOutcomeView({ triggered: 'nope' }).kind).toBe('unknown')
  })

  it('checkOutcomeView：除了真命中，其余三张回执一个「0 个异常」都不许说；有命中时 reason 不再抢话', () => {
    const payloads = [{}, { triggered: [], scan_scope: { reason: 'no_data_files' } },
      { triggered: [], scan_scope: { evaluated_files: ['a.csv'] } }]
    for (const payload of payloads) {
      const view = checkOutcomeView(payload)
      expect(view.kind).not.toBe('hit')
      expect(view.title + view.detail).not.toMatch(ZERO_CLAIM)
    }
    expect(checkOutcomeView({ triggered: [{ id: 1 }], scan_scope: { reason: 'no_data_files' } }).kind).toBe('hit')
    expect(Object.keys(SCAN_REASON_MESSAGES).sort()).toEqual(['no_data_files', 'no_permitted_datasets', 'tenant_data_dir_unavailable'])
  })

  it('emptyRuleForm / validateRuleForm：四格全空起步，阈值留空不许静默变成 0', () => {
    expect(emptyRuleForm()).toEqual({ name: '', metric: '', op: 'lt', threshold: '' })
    const blank = validateRuleForm(emptyRuleForm())
    expect(blank.ok).toBe(false)
    expect(Object.keys(blank.errors).sort()).toEqual(['metric', 'name', 'threshold'])
    expect(validateRuleForm({ name: 'n', metric: 'm', op: 'lt', threshold: '0' }).ok).toBe(true)
    expect(validateRuleForm({ name: 'n', metric: 'm', op: 'gt', threshold: -3.5 }).ok).toBe(true)
    expect(validateRuleForm({ name: 'n', metric: 'm', op: 'eq', threshold: 5 }).errors.op).toBeTruthy()
    expect(validateRuleForm({ name: ' ', metric: 'm', op: 'lte', threshold: 5 }).errors.name).toBeTruthy()
    expect(validateRuleForm({ name: 'n', metric: 'm', op: 'gte', threshold: '12abc' }).errors.threshold).toBeTruthy()
    expect(validateRuleForm({ name: 'n', metric: 'm', op: 'gte', threshold: '  ' }).errors.threshold).toBeTruthy()
    expect(validateRuleForm({ name: 'n', metric: 'm', op: 'gte', threshold: null }).errors.threshold).toBeTruthy()
    expect(validateRuleForm(null).ok).toBe(false)
  })

  it('ruleRequestBody：去首尾空格、阈值转数字、比较方式认不下退回 lt、留空是 NaN 不是 0', () => {
    expect(ruleRequestBody({ name: ' 差旅费上限 ', metric: ' 差旅费 ', op: 'gt', threshold: ' 8000 ' }))
      .toEqual({ name: '差旅费上限', metric: '差旅费', op: 'gt', threshold: 8000 })
    expect(ruleRequestBody({ name: 'a', metric: 'b', op: 'eq', threshold: 5 }).op).toBe('lt')
    expect(Number.isNaN(ruleRequestBody({ name: 'a', metric: 'b', op: 'lt', threshold: '' }).threshold)).toBe(true)
    expect(ruleRequestBody(null)).toEqual({ name: '', metric: '', op: 'lt', threshold: NaN })
  })

  it('removeRule 三种回执：invalid 一个请求都不发，not_found 不许装作删成功', async () => {
    const seen = []
    const client = { delete: async path => { seen.push(path); return { data: { status: 'deleted' } } } }
    expect(await removeRule('4', client)).toBe('ok')
    expect(await removeRule(9, { delete: async () => ({ data: { status: 'not_found' } }) })).toBe('not_found')
    expect(await removeRule(7, { delete: async () => ({}) })).toBe('ok')
    expect(await removeRule(7, { delete: async () => ({ data: null }) })).toBe('ok')
    // 后两次调用各用自己的假 client，seen 只记第一次那条：路径必须精确到编号。
    expect(seen).toEqual([RULES_PATH + '/4'])
    let fired = 0
    const never = { delete: async () => { fired += 1; return { data: {} } } }
    expect(await removeRule('drop table', never)).toBe('invalid')
    expect(await removeRule('', never)).toBe('invalid')
    expect(await removeRule(null, never)).toBe('invalid')
    expect(fired).toBe(0)
  })

  it('四个请求函数各打各的路径，且都走 lib/http.js 的那一个实例', async () => {
    http.get.mockResolvedValueOnce(ok({ alerts: [alertRow()] }))
    expect(await fetchAlerts()).toHaveLength(1)
    expect(http.get).toHaveBeenLastCalledWith(ALERTS_PATH)
    http.get.mockResolvedValueOnce(ok({ rules: [ruleRow(), ruleRow()] }))
    expect(await fetchRules()).toHaveLength(2)
    expect(http.get).toHaveBeenLastCalledWith(RULES_PATH)
    http.post.mockResolvedValueOnce(ok({ triggered: [], scan_scope: {} }))
    expect(await runCheck()).toEqual({ triggered: [], scan_scope: {} })
    expect(http.post).toHaveBeenLastCalledWith(CHECK_PATH)
    http.post.mockResolvedValueOnce(ok({ id: 5 }))
    await createRule({ name: 'n', metric: 'm', op: 'lte', threshold: '3' })
    expect(http.post).toHaveBeenLastCalledWith(RULES_PATH, { name: 'n', metric: 'm', op: 'lte', threshold: 3 })
    expect(http.get).toHaveBeenCalledTimes(2)
  })

  it('形状不对时取数函数回 null（面板据此画「坏了」），真空列表回 []（画「没有」）', async () => {
    http.get.mockResolvedValueOnce(ok({ alerts: 'not-a-list' }))
    expect(await fetchAlerts()).toBeNull()
    http.get.mockResolvedValueOnce(ok({}))
    expect(await fetchRules()).toBeNull()
    http.get.mockResolvedValueOnce(ok({ alerts: [] }))
    expect(await fetchAlerts()).toEqual([])
  })
})
