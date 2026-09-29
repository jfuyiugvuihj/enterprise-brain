/**
 * R505 判据 C + D · 「审计事件」这一屏真画出来的样子（SSR 真 HTML）
 *
 * 手法逐字照 r505-evaluations-screen.test.js：真 setup + 组件自己的 render，网络层换成进程内假实现。
 *
 * 判据 C 在这一屏只有一句话：截断不许被藏起来。逐格钉：
 *  ① filters / event_count / events_total / recorded_total / truncated / limits 六枚各画各的，
 *     三枚计数在三枚不同的格子里（用三枚互不相同的数字证明它们没被合并成一句「共 N 条」）；
 *  ② order=newest_first 原话印出来，回执没交代就说「没交代」，不由界面猜一种；
 *  ③ 「这一发真用上了哪些条件」只认回执 echo 的那一格：表单里有字而回包 filters 为空，
 *     屏上说的就是「没有收到任何过滤条件」—— 界面不替操作员宣称自己筛过；
 *  ④ 屏侧一枚空条件都不造：表单空着时那一发的查询参数整枚不存在，「清空条件」是一次真重读。
 *
 * 判据 D：五张失败脸（401 / 403 / 503 / 500 / 形状读不出）分开留名，且失败脸上不画任何计数。
 */
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'

vi.mock('../../lib/http', async importOriginal => {
  const actual = await importOriginal()
  return { ...actual, http: { get: vi.fn() } }
})

import { http } from '../../lib/http'
import {
  AUDIT_EMPTY_FILTERED_DESCRIPTION,
  AUDIT_EMPTY_RECORDED_DESCRIPTION,
  AUDIT_EVENTS_PATH,
  AUDIT_FACES,
  AUDIT_FACE_DENIED,
  AUDIT_FACE_EMPTY_FILTERED,
  AUDIT_FACE_EMPTY_RECORDED,
  AUDIT_FACE_FAILED,
  AUDIT_FACE_MALFORMED,
  AUDIT_FACE_STORAGE,
  AUDIT_FACE_UNAUTHORIZED,
  AUDIT_ORDER_NEWEST_FIRST,
  AUDIT_ORDER_TEXT,
  AUDIT_ORDER_UNKNOWN,
  AUDIT_TITLES,
} from '../../lib/auditEvents'
import AuditEventsPanel from '../AuditEventsPanel.vue'
import { countNativeButtons } from './r288-native-button-scan.js'
import { routes } from '../../router/index.js'

const PANEL = '../AuditEventsPanel.vue'
const LIB = '../../lib/auditEvents.js'
const THEME = '../../assets/theme.css'
const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const panelSource = () => read(PANEL)
const auditRoute = routes.find(route => route.name === 'audit-events')

/** 一条事件：键名逐格抄 app/common/audit.py 里那枚 event 字典（对账在契约件里做过）。 */
const event = (over = {}) => ({
  event_id: 'aud-9f2c', timestamp: '2026-09-29T02:03:04.512+00:00', created_at: '2026-09-29T02:03:04+00:00',
  username: 'lishan', role: 'manager', owner_id: 'u-7', auth_source: 'local', actor_clearance: 2,
  actor_departments: ['研发部', '平台组'], action: 'document:upload', resource: 'doc-31',
  outcome: 'denied', reason: 'clearance_insufficient', request_id: 'req-77',
  persisted: true, storage_mode: 'pg', ...over,
})
const report = (over = {}) => ({
  requested_by: { username: 'root', roles: ['admin'], auth_source: 'local' },
  source: 'app.common.audit.get_audit_events', filters: {}, events: [event()],
  event_count: 1, events_total: 1, recorded_total: 12, truncated: false,
  order: AUDIT_ORDER_NEWEST_FIRST,
  limits: { default_limit: 100, max_limit: 200, applied_limit: 100, requested_limit: null, clamped: false },
  ...over,
})
/** 三枚计数故意取三个互不相同的数：合并成一格就立刻露馅。 */
const SPLIT = report({
  events: [event(), event({ event_id: 'aud-3b7d', username: 'chen' })],
  event_count: 2, events_total: 9, recorded_total: 124, truncated: true,
  limits: { default_limit: 100, max_limit: 200, applied_limit: 2, requested_limit: 2, clamped: true },
})
const REFUSALS = {
  unauthorized: { response: { status: 401, data: { detail: { code: 'authentication_required', message: 'A valid principal is required.', details: {} } } } },
  denied: { response: { status: 403, data: { detail: { code: 'permission_denied', message: 'audit:read is not permitted.', details: { reason_code: 'clearance_insufficient' } } } } },
  storage: { response: { status: 503, data: { detail: { code: 'storage_unavailable', message: 'audit trail is not readable', details: {} } } } },
  failed: { response: { status: 500, data: { detail: { code: 'internal_error', message: 'audit read blew up', details: {} } } } },
}

const count = (html, id) => (html.match(new RegExp('data-testid="' + id + '"', 'g')) || []).length
const countText = (haystack, needle) => haystack.split(needle).length - 1
function cellText(html, id) {
  const open = html.indexOf(`data-testid="${id}"`)
  expect(open, `屏上少了 ${id} 那一格`).toBeGreaterThan(-1)
  const match = />([^<]*)<\//.exec(html.slice(open))
  return match ? match[1] : ''
}
const buttonLabels = source => [...source.matchAll(/<UiButton\b[\s\S]*?\/>/g)].map(match => {
  const label = /label="([^"]*)"/.exec(match[0])
  return label ? label[1] : '(这一枚 UiButton 没有 label 属性)'
})
/** 假 axios 一次 resolve 一号：clearFilters 内部不 await，靠微任务队列排空。 */
const settle = async () => {
  for (let i = 0; i < 12; i += 1) await Promise.resolve()
}

async function renderAfter(step) {
  let bindings = null
  const Capture = defineComponent({
    __name: 'R505AuditPanelCapture',
    setup(_props, ctx) {
      bindings = AuditEventsPanel.setup({}, ctx)
      return () => null
    },
  })
  await renderToString(h(Capture))
  await step(bindings)
  const Probe = defineComponent({ ...AuditEventsPanel, __name: 'R505AuditPanelProbe', setup: () => bindings })
  return { html: await renderToString(h(Probe)), bindings }
}
const renderWith = payload => renderAfter(async bindings => {
  http.get.mockResolvedValue({ data: payload })
  await bindings.loadIntoView()
})
const renderFailure = error => renderAfter(async bindings => {
  http.get.mockRejectedValue(error)
  await bindings.loadIntoView()
})

beforeEach(() => {
  vi.clearAllMocks()
})

describe('R505 判据 C · 六枚计数逐格说，一枚都不许合并', () => {
  it('三枚计数是三枚不同的数各占一格：把它们并成一格当场就红', async () => {
    const { html } = await renderWith(SPLIT)
    expect(count(html, 'audit-counts')).toBe(1)
    expect(cellText(html, 'audit-event-count')).toBe('2 条')
    expect(cellText(html, 'audit-events-total')).toBe('9 条')
    expect(cellText(html, 'audit-recorded-total')).toBe('124 条')
    expect(html).toContain('这一页装不下：按同一枚条件还能筛出更早的事件，它们没在这份清单里')
  })

  it('上限那一族五格分开说：默认/最多/这次用了/请求里带的/有没有被夹', async () => {
    const { html } = await renderWith(SPLIT)
    expect(html).toContain('100 条 / 200 条')
    expect(cellText(html, 'audit-requested-limit')).toBe('2 条')
    expect(cellText(html, 'audit-clamped')).toBe('被后端夹过')
    const plain = await renderWith(report())
    expect(cellText(plain.html, 'audit-requested-limit')).toBe('这一发没带 limit')
    expect(cellText(plain.html, 'audit-clamped')).toBe('没夹')
    expect(cellText(plain.html, 'audit-truncated')).toBe('这一页就是按这一发条件筛出来的全部事件')
  })

  it('屏上没有第二本账：改回执里的数字，屏面逐格跟着改', async () => {
    const moved = await renderWith(report({ event_count: 5, events_total: 41, recorded_total: 9_007 }))
    expect(cellText(moved.html, 'audit-event-count')).toBe('5 条')
    expect(cellText(moved.html, 'audit-events-total')).toBe('41 条')
    expect(cellText(moved.html, 'audit-recorded-total')).toBe('9007 条')
  })

  it('排序只认回执那一格：newest_first 就说「从最近往回列」，没交代就说没交代', async () => {
    const stated = await renderWith(report())
    expect(cellText(stated.html, 'audit-order')).toBe(AUDIT_ORDER_TEXT)
    const silent = await renderWith(report({ order: null }))
    expect(cellText(silent.html, 'audit-order')).toBe(AUDIT_ORDER_UNKNOWN)
    expect(silent.html).not.toContain(AUDIT_ORDER_TEXT)
  })

  it('首屏一枚查询参数都不带：表单空着就是没筛，屏侧不给自己造空条件', async () => {
    const { html } = await renderWith(report())
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(http.get).toHaveBeenCalledWith(AUDIT_EVENTS_PATH, undefined)
    expect(html).toContain('服务端这一发没有收到任何过滤条件：下面列的是全库最近的那些事件')
  })

  it('填了才发，而且只发非空的那几枚（空着的那两格整枚不出现在查询串里）', async () => {
    await renderAfter(async bindings => {
      http.get.mockResolvedValue({ data: report() })
      bindings.form.username = 'lishan'
      bindings.form.action = ''
      bindings.form.outcome = 'denied'
      bindings.form.limit = '  '
      await bindings.loadIntoView()
    })
    expect(http.get).toHaveBeenCalledWith(AUDIT_EVENTS_PATH, { params: { username: 'lishan', outcome: 'denied' } })
  })

  it('「清空条件」是一次真重读：第二发不带条件，屏上也不留着上一次那份回执', async () => {
    const { html } = await renderAfter(async bindings => {
      http.get.mockResolvedValueOnce({ data: SPLIT })
      await bindings.loadIntoView()
      bindings.form.username = 'lishan'
      http.get.mockResolvedValueOnce({ data: report() })
      bindings.clearFilters()
      await settle()
    })
    expect(http.get).toHaveBeenCalledTimes(2)
    expect(http.get).toHaveBeenLastCalledWith(AUDIT_EVENTS_PATH, undefined)
    expect(cellText(html, 'audit-event-count')).toBe('1 条')
    expect(cellText(html, 'audit-recorded-total')).toBe('12 条')
    expect(html).toContain('服务端这一发没有收到任何过滤条件')
  })

  it('「这次真用上的条件」只认回执 echo：表单里有字而回包 filters 为空，屏上就说没收到的那句', async () => {
    const { html } = await renderAfter(async bindings => {
      http.get.mockResolvedValue({ data: report({ filters: {} }) })
      bindings.form.username = 'ghost'
      await bindings.loadIntoView()
    })
    expect(count(html, 'audit-filter-pair')).toBe(0)
    expect(html).toContain('服务端这一发没有收到任何过滤条件')
    // 操作员打的字不藏（表单里那一格还写着 ghost），但「这一发用上了什么」只按回执 echo 说。
    expect(html).toContain('ghost')
    expect(cellText(html, 'audit-filters-note')).toContain('没有收到任何过滤条件')
  })

  it('回执 echo 了条件就逐枚列出来，那一句话也跟着换口径', async () => {
    const { html } = await renderWith(report({ filters: { username: 'lishan', outcome: 'denied' } }))
    expect(count(html, 'audit-filter-pair')).toBe(2)
    expect(html).toContain('username = lishan')
    expect(html).toContain('outcome = denied')
    expect(html).toContain('上面这几枚条件就是服务端这一发真正用上的过滤')
  })
})

describe('R505 判据 C 的另一半 · 三种「空」各自一张脸，谁也不许冒充谁', () => {
  it('条件筛掉了：说的是「按上面那几枚没筛中」，不是「公司没发生过什么」', async () => {
    const { html } = await renderWith(report({ filters: { username: 'nobody' }, events: [], event_count: 0, events_total: 0, recorded_total: 12 }))
    expect(html).toContain('data-face="' + AUDIT_FACE_EMPTY_FILTERED + '"')
    expect(html).toContain(AUDIT_TITLES[AUDIT_FACE_EMPTY_FILTERED])
    expect(html).toContain(AUDIT_EMPTY_FILTERED_DESCRIPTION)
    expect(html).not.toContain(AUDIT_EMPTY_RECORDED_DESCRIPTION)
    expect(count(html, 'audit-counts')).toBe(1)
  })

  it('这台服务一条都没记过：另一句话、另一张脸，且六枚计数照样摆在屏上', async () => {
    const { html } = await renderWith(report({ events: [], event_count: 0, events_total: 0, recorded_total: 0 }))
    expect(html).toContain('data-face="' + AUDIT_FACE_EMPTY_RECORDED + '"')
    expect(html).toContain(AUDIT_EMPTY_RECORDED_DESCRIPTION)
    expect(html).not.toContain(AUDIT_EMPTY_FILTERED_DESCRIPTION)
    expect(count(html, 'audit-events-table')).toBe(0)
    expect(cellText(html, 'audit-recorded-total')).toBe('0 条')
  })

  it('回执自己打脸（全库有记录却没带条件却交回空清单）：走形状脸，不挑一句听着顺耳的说', async () => {
    const { html } = await renderWith(report({ events: [], event_count: 0, events_total: 0, recorded_total: 12 }))
    expect(html).toContain('data-face="' + AUDIT_FACE_MALFORMED + '"')
    expect(html).toContain('这两格互相打脸')
    expect(html).not.toContain(AUDIT_EMPTY_FILTERED_DESCRIPTION)
    expect(html).not.toContain(AUDIT_EMPTY_RECORDED_DESCRIPTION)
  })

  it('有事件就是正常脸：行画出来，处置结果认后端那几个值', async () => {
    const { html } = await renderWith(report())
    expect(count(html, 'audit-events-table')).toBe(1)
    expect(html).toContain('document:upload')
    expect(html).toContain('doc-31')
    expect(html).toContain('req-77')
    expect(html).toContain('被拒了')
    expect(html).not.toContain('未登记的处置结果')
  })
})

describe('R505 判据 D · 五张失败脸分开留名（真 HTML）', () => {
  it('401 / 403 / 503 / 500 各画自己那一句，HTML 两两不等', async () => {
    const faces = [AUDIT_FACE_UNAUTHORIZED, AUDIT_FACE_DENIED, AUDIT_FACE_STORAGE, AUDIT_FACE_FAILED]
    const rendered = []
    for (const face of faces) {
      const { html } = await renderFailure(REFUSALS[face])
      rendered.push(html)
      expect(html, '这一张脸没上屏：' + face).toContain(AUDIT_TITLES[face])
      expect(html).toContain('data-face="' + face + '"')
      expect(count(html, 'audit-failure')).toBe(1)
    }
    for (let a = 0; a < rendered.length; a += 1) {
      for (let b = a + 1; b < rendered.length; b += 1) {
        expect(rendered[a], '两张脸塌成了一张：' + faces[a] + ' / ' + faces[b]).not.toBe(rendered[b])
      }
    }
    for (const face of AUDIT_FACES) {
      expect(AUDIT_TITLES, '脸谱名册里少这一张：' + face).toHaveProperty(face)
    }
  })

  it('401 / 403 / 503 不给「重试」；500 与形状脸给 —— 只有可能自愈的那两张才值得再按一次', async () => {
    for (const face of [AUDIT_FACE_UNAUTHORIZED, AUDIT_FACE_DENIED, AUDIT_FACE_STORAGE]) {
      const { html } = await renderFailure(REFUSALS[face])
      expect(html, face + ' 那张脸长出了重试按钮').not.toContain('ui-error-state__actions')
    }
    const plain = await renderFailure(REFUSALS.failed)
    expect(plain.html).toContain('ui-error-state__actions')
  })

  it('失败脸上一枚计数都不画：读不到就是读不到，不留一份看着像读数的空壳', async () => {
    for (const error of Object.values(REFUSALS)) {
      const { html } = await renderFailure(error)
      expect(count(html, 'audit-counts')).toBe(0)
      expect(count(html, 'audit-events-card')).toBe(0)
      expect(count(html, 'audit-events-table')).toBe(0)
      // 表单还在（它不是读回来的东西），但那一发确实没换成任何读数。
      expect(count(html, 'audit-filters-form')).toBe(1)
    }
  })

  it('200 但形状读不出：走形状脸，不滑成「这台服务一条都没记过」', async () => {
    const { html } = await renderAfter(async bindings => {
      http.get.mockResolvedValue({ data: { order: AUDIT_ORDER_NEWEST_FIRST } })
      await bindings.loadIntoView()
    })
    expect(html).toContain(AUDIT_TITLES[AUDIT_FACE_MALFORMED])
    expect(html).not.toContain(AUDIT_TITLES[AUDIT_FACE_EMPTY_RECORDED])
    expect(html).toContain('ui-error-state__actions')
  })
})

describe('R505 交付卫生 · 这一屏不自造第二套真源', () => {
  it('零枚裸 <button>：三枚动作全是 ui 原语，且没有一枚写着运行/执行/写入', () => {
    const source = panelSource()
    expect(countNativeButtons(source)).toBe(0)
    expect(buttonLabels(source)).toEqual(['重新读取', '按这些条件读', '清空条件重读'])
    expect(source).not.toMatch(/label="[^"]*(运行|执行|跑一轮|开始|触发|提交|写入|补记)/)
    expect(source).not.toMatch(/<form\b/i)
  })

  it('这一屏只有读腿：壳里零枚写方法，取数也不在壳里', () => {
    const code = panelSource().replace(/<!--[\s\S]*?-->/g, '').replace(/\/\*[\s\S]*?\*\//g, '')
    for (const needle of ['axios', 'fetch(', "from '../lib/http'", '/api/v1/', "'" + AUDIT_EVENTS_PATH + "'"]) {
      expect(code, '屏壳里出现了取数件：' + needle).not.toContain(needle)
    }
    expect(code).toMatch(/from '\.\.\/lib\/auditEvents'/)
    expect(code).not.toMatch(/\b(post|put|patch|delete)\s*\(/)
    const libSource = read(LIB)
    expect(libSource).toContain("AUDIT_EVENTS_PATH = '" + AUDIT_EVENTS_PATH + "'")
    expect(countText(libSource, "'" + AUDIT_EVENTS_PATH + "'"), '出口地址在取数件里也不许出现第二遍').toBe(1)
  })

  it('运行时零外部请求、零位图、零裸色值（色值只归 theme.css）', () => {
    const source = panelSource()
    expect(source).not.toMatch(/https?:\/\/|\bwww\./i)
    expect(source).not.toMatch(/\.(png|jpe?g|gif|svg|webp)\b/i)
    expect(source).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(source).not.toMatch(/rgba?\(/)
    const styleBlock = /<style scoped>([\s\S]*?)<\/style>/.exec(source)
    expect(styleBlock, '样式块读不出来：这一屏的排版声明去哪儿了？').toBeTruthy()
    expect(styleBlock[1]).not.toMatch(/color|background|border|font-/)
    for (const token of styleBlock[1].match(/var\(--[\w-]+\)/g) || []) {
      expect(read(THEME) + source, token + ' 没有定义').toContain(token)
    }
  })

  it('屏上没有页级主标题：屏名只由路由表那一格说一次', () => {
    const source = panelSource()
    expect(source).not.toMatch(/<header\b[^>]*class="[^"]*\bpanel-head\b[^>]*>[\s\S]*?<h3\b/)
    expect(source).not.toMatch(/class="panel-hd"[\s\S]*?<strong>/)
    expect(auditRoute.meta.title).toBe('审计事件')
    expect(source, '这一屏自己起了第二枚页级屏名').not.toContain('chat-screen-name')
  })
})
