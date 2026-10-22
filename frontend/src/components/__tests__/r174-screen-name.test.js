/**
 * R174 判据③ · 屏名定名：这一屏叫「审批与待办」，不叫「报销自查」
 *
 * 要补的病：这一屏今天挂着真待办（GET /hitl/pending 的账本）与真审批（POST /approve 的
 * 批准 / 驳回），屏名却还写着「报销自查」——名实不符。「报销」是一枚业务专属词，客户一装机
 * 就会以为这台产品只管报销，而它其实管的是「智能体停下来等人拍板」这件事。
 *
 * 三条腿：
 *   ① 定名钉死在 meta.title 上，并钉住「报销」二字不得再作任何一屏的名字。
 *   ② 名实相符：把这一屏与那一行真渲染一遍，屏上确有「待办」那一块、也确有「批准 / 驳回」
 *      那两个动作 —— 名字不是凭空改的，是照着内容改的。
 *   ③ 改名不许顺手把诚实声明洗掉：页内仍然自己说清「自查工具，不是审批」「它不办理审批」。
 *
 * 反证③（本单要求实测红→绿，跑完即还原）：把 meta.title 或页内 h3 任一处回写成「报销自查」
 *   → ①的定名与禁词两枚、②的同源一枚，三处一起红。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { navigation, routes } from '../../router/index.js'
import ApprovalPanel from '../ApprovalPanel.vue'
import HitlPendingRow from '../hitl/HitlPendingRow.vue'

const read = rel => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const source = name => read(`../${name}`)
const byName = new Map(routes.map(route => [String(route.name), route]))
const approval = byName.get('approval')

/** 页级屏名的唯一画法（与 R136 那枚同源用例同一条规则）：panel-head 里的第一个 <h3>。 */
const PAGE_TITLE_RE = /<header\b[^>]*class="[^"]*\bpanel-head\b[^"]*"[^>]*>[\s\S]*?<h3\b[^>]*>([^<]*)<\/h3>/

const BUSINESS_WORD = '报销'
const OLD_TITLE = '报销自查'
const TITLE = '审批与待办'

describe('R174③ · 定名：审批与待办', () => {
  it('meta.title 就是定名，旧名一枚字都不许多留', () => {
    expect(approval.meta.title).toBe(TITLE)
    expect(approval.meta.title).not.toBe(OLD_TITLE)
  })

  it('业务专属词不得充当任何一屏的名字（客户一装机就以为产品只管报销）', () => {
    for (const route of routes.filter(item => item.meta?.screen)) {
      expect(String(route.meta.title), `${String(route.name)} 的屏名里夹了业务专属词`)
        .not.toContain(BUSINESS_WORD)
    }
  })

  it('侧栏文案与顶栏都是这一格派生的，改名只改了一处', () => {
    const item = navigation.find(entry => entry.id === 'approval')
    expect(item.label).toBe(approval.meta.title)
    expect(item.label).toBe(TITLE)
  })
})

describe('R174③ · 名实相符：这个名字撑得住屏上的内容', () => {
  it('页内屏名与 meta.title 逐字相等（两处各写一份迟早漂）', async () => {
    const html = await renderToString(h(ApprovalPanel))
    const match = PAGE_TITLE_RE.exec(html)
    expect(match, '这一屏把页级屏名弄丢了').toBeTruthy()
    expect(match[1].trim()).toBe(approval.meta.title)
  })

  it('「待办」那一块是真的：这一屏挂的是读服务端账本的组件', () => {
    const code = source('ApprovalPanel.vue')
    expect(code).toMatch(/import HitlPendingPanel from '\.\/hitl\/HitlPendingPanel\.vue'/)
    expect(code).toMatch(/<HitlPendingPanel\s*\/>/)
  })

  it('「审批」那一半也是真的：行上确有批准与驳回两个动作', async () => {
    const html = await renderToString(h({
      render: () => h(HitlPendingRow, {
        row: { sessionId: 's-1', requestId: 'req-1', labels: ['📋 导出报告'], steps: ['export'] },
        canOpen: true,
      }),
    }))
    expect(html).toContain('批准执行')
    expect(html).toContain('驳回')
    expect(html).toContain('回到这一轮对话')
  })

  it('改名没把自查那一格的诚实声明一起洗掉：它仍然自己说清不办理审批', () => {
    const code = source('ApprovalPanel.vue')
    for (const phrase of ['自查工具，不是审批', '它不办理审批', '不会生成工单', '演示数据']) {
      expect(code, `改名时把「${phrase}」弄丢了`).toContain(phrase)
    }
  })
})
