/**
 * R175 判据② —— 「你批过了，那一轮失败了」这一格上屏
 *
 * 要补的病（本树实读，不抄留档）：/approve 的 error 腿与 timeout 腿各发一条 request.failed
 * 之后直接 break，一次都没闭合那一行挂起账。于是审批人点了「同意」而那一轮跑挂了之后：
 *   要么待办屏把同一件事当新待办原样列回来（图还挂在同一个中断上，再点一次就是让同一轮
 *   resume 第二遍），要么下次开屏被复核腿就地判成 stale（「已作废」）。
 * 两处都没有人对他说一句真话：你批过，那一轮失败了。
 *
 * 修法分两头：后端把那一行闭合成 failed 并以 failed_turns 回给这一屏（app/api/v1/chat.py），
 * 本文件只管上屏这一头。四条红线：
 *   ① 这一格【不是】待办：不占 hitl-row 的行位，也不带批准/驳回按钮；
 *   ② 这一格【不许】被说成「已拒绝 / 已驳回」—— 员工点的是同意，那一轮是系统跑挂的；
 *   ③ 这一格【不许】被说成「已完成 / 已放行」—— 什么都没产出，报办完就是伪装；
 *   ④ 这句话只可能来自真响应：后端没这一格（老镜像）或读失败了，屏上一个字都不许多造。
 *
 * 三条腿沿用 r168/r174 的口径：真面板（跑组件自己的 loadPending）、真产物（ssrRender 出整屏
 * HTML）、源码钉（赋值形状与话术红线）。全程离线：http.get 是进程内假实现，不开 socket。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'

vi.mock('../../lib/http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn() }, authedFetch: vi.fn() }
})

import { http } from '../../lib/http'
import { sessions } from '../../lib/sessions'
import HitlPendingPanel, {
  EMPTY_TITLE,
  FAILED_TURN_LEAD,
  FAILED_TURN_MORE,
  FAILED_TURN_TITLE,
  PENDING_PATH,
  decisionView,
  failedTurnLabel,
  failedTurnsOf,
} from '../hitl/HitlPendingPanel.vue'

const source = f => readFileSync(new URL(`../${f}`, import.meta.url), 'utf8').replace(/\r\n/g, '\n')

async function mountBindings(component) {
  let bindings = null
  const Probe = {
    name: 'R175Probe',
    setup(props, ctx) {
      bindings = component.setup({}, ctx)
      return () => null
    },
  }
  await renderToString(h(Probe))
  expect(bindings, '组件应暴露可调用的 setup()').toBeTruthy()
  return bindings
}

const renderState = (component, bindings) => renderToString(h({ ...component, setup: () => bindings }))
const text = html => html.replace(/<!--[\s\S]*?-->/g, ' ').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
const count = (html, testid) => (html.match(new RegExp(`data-testid="${testid}"`, 'g')) || []).length

/** 后端 items 一行的真形状。 */
function todoRow(over) {
  return Object.assign({
    session_id: 'sess-open',
    owner_user_id: 'u-1',
    parked_steps: ['export'],
    labels: ['📋 导出报告'],
    status: 'awaiting',
    created_at: '2026-09-23T09:12:44+08:00',
    expires_at: '2026-09-23T09:42:44+08:00',
    request_id: 'req-open',
    trace_id: 'tr-open',
    task_id: 'tk-open',
  }, over || {})
}

/** 后端 failed_turns 一行的真形状：没有 labels（这一格不许向图复核），字段照 chat.py 抄。 */
function failedRow(over) {
  return Object.assign({
    session_id: 'sess-crash',
    owner_user_id: 'u-1',
    parked_steps: ['chart'],
    status: 'failed',
    created_at: '2026-09-23T08:02:11+08:00',
    expires_at: '2026-09-23T09:42:44+08:00',
    request_id: 'req-crashed',
    trace_id: 'tr-crashed',
    task_id: 'tk-crashed',
  }, over || {})
}

/** GET /hitl/pending 的返回体：两格各说各的，一个都不许多。 */
function page(items, extra) {
  return Object.assign({
    items,
    count: items.length,
    limit: 50,
    offset: 0,
    has_more: false,
    failed_turns: [],
    failed_turns_has_more: false,
  }, extra || {})
}

function route(payload) {
  http.get.mockImplementation(async url => {
    if (url === PENDING_PATH) return { data: typeof payload === 'function' ? payload() : payload }
    if (url === '/sessions') return { data: { sessions: [] } }
    return { data: {} }
  })
}

beforeEach(() => {
  http.get.mockReset()
  sessions.value = []
})

describe('R175② · 这句话只可能来自真响应', () => {
  it('failedTurnsOf 只认数组：老镜像没这一格、或后端坏成形状不对，一律空', () => {
    expect(failedTurnsOf(page([], { failed_turns: [failedRow()] }))).toHaveLength(1)
    expect(failedTurnsOf({ items: [] })).toEqual([])
    expect(failedTurnsOf({ items: [], failed_turns: null })).toEqual([])
    expect(failedTurnsOf({ items: [], failed_turns: 'failed' })).toEqual([])
    expect(failedTurnsOf(undefined)).toEqual([])
  })

  it('后端没这一格 = 屏上一句都不造（宁缺不猜）', async () => {
    const legacy = { items: [], count: 0, limit: 50, offset: 0, has_more: false }
    route(legacy)
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    const html = await renderState(HitlPendingPanel, bindings)
    expect(count(html, 'hitl-failed-turns')).toBe(0)
    expect(text(html)).not.toContain(FAILED_TURN_TITLE)
    expect(text(html)).toContain(EMPTY_TITLE)
  })

  it('后端回了这一格，句子才上屏，且带得上「哪一步 / 哪一笔请求」', async () => {
    route(page([], { failed_turns: [failedRow()], failed_turns_has_more: true }))
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    const html = await renderState(HitlPendingPanel, bindings)
    expect(count(html, 'hitl-failed-turn')).toBe(1)
    const said = text(html)
    expect(said).toContain(FAILED_TURN_TITLE)
    expect(said).toContain(FAILED_TURN_LEAD)
    expect(said).toContain('生成图表')
    expect(said).toContain('req-crashed'.slice(0, 8))
    expect(said).toContain(FAILED_TURN_MORE)
  })
})

describe('R175② · 这一格不是待办，也不是拒批', () => {
  it('失败那一行不占待办行位，也不带批准/驳回按钮', async () => {
    route(page([], { failed_turns: [failedRow()] }))
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    const html = await renderState(HitlPendingPanel, bindings)
    expect(count(html, 'hitl-row')).toBe(0)
    expect(count(html, 'hitl-approve')).toBe(0)
    expect(count(html, 'hitl-reject')).toBe(0)
    expect(html).toMatch(/data-testid="hitl-failed-turn"[^>]*data-status="failed"/)
  })

  it('话术红线：不许说成已拒绝/已驳回，也不许说成已完成/已放行/办妥', async () => {
    const said = FAILED_TURN_TITLE + FAILED_TURN_LEAD + FAILED_TURN_MORE
    expect(said).not.toMatch(/已拒绝|已驳回|驳回的|拒绝的/)
    expect(said).not.toMatch(/已完成|已放行|已批准|办妥|成功/)
    expect(said).toContain('失败')
    // 「不会回来等你批第二次」这句话必须有主语：它是待办屏上唯一一处提到这件事的地方。
    expect(FAILED_TURN_LEAD).toMatch('新的待办')
  })

  it('待办与失败轮并存时两句各说各的，谁也不顶谁', async () => {
    route(page([todoRow()], { failed_turns: [failedRow()] }))
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    const html = await renderState(HitlPendingPanel, bindings)
    const said = text(html)
    expect(count(html, 'hitl-row')).toBe(1)
    expect(count(html, 'hitl-failed-turn')).toBe(1)
    expect(said).toContain('等你拍板')
    expect(said).toContain(FAILED_TURN_TITLE)
    expect(said).toContain('导出报告')
    expect(said).toContain('生成图表')
  })

  it('空待办 + 有失败轮：空态那句「没有等你拍板的事」不许顶掉失败那句，反之也一样', async () => {
    route(page([], { failed_turns: [failedRow()] }))
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    const html = await renderState(HitlPendingPanel, bindings)
    const said = text(html)
    expect(bindings.face.value).toBe('empty')
    expect(said).toContain(EMPTY_TITLE)
    expect(said).toContain(FAILED_TURN_TITLE)
  })
})

describe('R175② · 读失败与翻页都不许把这句话留下来', () => {
  it('读账本失败：那一句跟着撤下，不许拿上一次的话冒充这一次', async () => {
    route(page([], { failed_turns: [failedRow()] }))
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    expect(count(await renderState(HitlPendingPanel, bindings), 'hitl-failed-turn')).toBe(1)

    http.get.mockImplementation(async url => {
      if (url === '/sessions') return { data: { sessions: [] } }
      throw { response: { status: 500, data: { detail: 'internal_error' } }, message: 'boom' }
    })
    await bindings.loadPending()
    const html = await renderState(HitlPendingPanel, bindings)
    expect(bindings.failedTurns.value).toEqual([])
    expect(count(html, 'hitl-failed-turn')).toBe(0)
  })

  it('形状不对＝坏了：这一格也不画', async () => {
    route({ items: 'nope' })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    expect(bindings.failedTurns.value).toEqual([])
    expect(count(await renderState(HitlPendingPanel, bindings), 'hitl-failed-turn')).toBe(0)
  })

  it('「看更早的」那一枪不重复列失败轮：那一格说的是最近这些，不跟着翻页走', async () => {
    let reads = 0
    route(() => {
      reads += 1
      return page([], {
        items: [],
        failed_turns: reads === 1 ? [failedRow()] : [],
        failed_turns_has_more: true,
        has_more: true,
        limit: 50,
      })
    })
    const bindings = await mountBindings(HitlPendingPanel)
    await bindings.loadPending()
    await bindings.loadPending({ append: true })
    expect(reads).toBeGreaterThanOrEqual(2)
    expect(bindings.failedTurns).toBeTruthy()
    expect(bindings.failedTurns.value).toHaveLength(1)
  })

  it('源码钉：failedTurns 每次赋值要么空数组，要么本次响应里那一格映射出来的行', () => {
    const code = source('hitl/HitlPendingPanel.vue')
      .split('\n')
      .filter(line => !/^\s*(\/\/|\*|\/\*\*?)/.test(line))
      .join('\n')
    const assigns = code.match(/failedTurns\.value = [^\n]*/g) || []
    expect(assigns).toEqual([
      'failedTurns.value = []',
      'failedTurns.value = []',
      'failedTurns.value = failedTurnsOf(response.data).map(mapPendingRow)',
      'failedTurns.value = []',
    ])
    // 待办那一格一条都不许多：闭合的失败轮永远混不进 rows。
    expect(code.match(/rows\.value = [^\n]*/g)).toHaveLength(3)
  })
})

describe('R175 · 一次决定的那句话不再承诺「留在原地」', () => {
  it('批准失败：仍然倒扣，但不再说这一行会留在原地', () => {
    const view = decisionView({ approved: true, ok: true, status: 200, terminal: 'failed', errorCode: 'internal_error' })
    const said = view.title + view.description
    expect(view.face).toBe('failed')
    expect(said).toMatch('没有生效')
    expect(said).toMatch('重新读取')
    expect(said).toMatch('不等于这一步真跑完了')
    expect(said).not.toMatch(/留在原地/)
    expect(said).not.toMatch(/已完成|已放行|已批准|已办完|办妥了|成功/)
  })

  it('批准失败与驳回失败仍旧两两不同句，且都不许把故障说成驳回', () => {
    const approved = decisionView({ approved: true, ok: true, terminal: 'failed', errorCode: 'internal_error' })
    const rejected = decisionView({ approved: false, ok: true, terminal: 'failed', errorCode: 'task_timeout' })
    const timeout = decisionView({ approved: true, ok: true, terminal: 'failed', errorCode: 'task_timeout' })
    const texts = [approved, rejected, timeout].map(view => view.title + '|' + view.description)
    expect(new Set(texts).size).toBe(3)
    for (const view of [approved, rejected, timeout]) {
      expect(view.face).toBe('failed')
      expect(view.title + view.description).not.toMatch(/已拒绝/)
    }
  })

  it('失败那一格的动作名走的是同一份后端说法，不自己发明第三个', () => {
    // 后端没给这一格的 labels，所以中文名走 HitlPendingRow 那份 STEP_LABELS；长 id 只留前 8 位。
    expect(failedTurnLabel({ steps: ['chart'], labels: [], requestId: 'req-abcdefgh1234' })).toBe(
      '生成图表（请求 #req-abcd）',
    )
    // 什么名都没给时也不许空着一句不给说。
    expect(failedTurnLabel({ steps: ['unknown-step'], labels: [], requestId: '' })).toBe('需要确认的一步')
  })
})
