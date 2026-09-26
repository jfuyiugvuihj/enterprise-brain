/**
 * R270 判据① + 判据② · 部门这两枚拒绝码必须说得出「这台界面上真做得到的下一步」
 *
 * 立案原文（docs/handoff/2026-09-26-v1-frontend-gap-list.md 的 G19 行与 §7 块表「G 错误话术」行）：
 *   ① department_scope_required 原句「请先选择部门范围，再生成这项结果。」叫用户去按一枚界面上
 *      根本不存在的部门选择器（全站无选择器：rg 部门 src/components 只剩报销自查那一格输入框）。
 *      后端这句话真正在说的是**这个账号自己没登记部门归属**（app/api/v1/data.py:45 的
 *      OWNER_SCOPE_REQUIRED，两条出口 :271 与 :459 的 _require_artifact_scope），
 *      缺的那一格在人身上不在界面上，所以下一步只能是找人补登记或换账号。
 *   ② department_override_denied（app/common/authorization.py:62，verify_department_self_report
 *      以 403 吐出）今天在字典与别名表里 0 命中 ⇒ 被 STATUS_CODES[403] 兜成 permission_denied，
 *      于是每一屏一律画成「没有权限」。本件把它收进别名表真码位，只到字典这一层——
 *      🔴 ApprovalPanel.vue 那一屏（含 r237 丁2 那枚「没有权限做审批预审」的钉）由块 B 复用本出口。
 *
 * 钉法三类，全部打在 lib 的公开出口上（不引组件、不起渲染器）：
 *   正向  新句必须含的语义件：承认没做成 + 说得出是哪一格 + 一条做得到的下一步；
 *   负向  旧句与「叫人选部门」这一律指错方向的写法不许回来（把文案改回旧句即红）；
 *   结构  ② 必须是别名表里的一枚真码位，且不得折回 permission_denied 那一格——
 *        lib/http.js 的 isPermissionDenied 就是「画成没有权限」那一行的判据，
 *        把码位摘掉它立刻恢复 true（摘钉即红，不靠人记着）。
 */
import { describe, expect, it } from 'vitest'

import {
  ERROR_CODES,
  FALLBACK_MESSAGE,
  LEGACY_ALIASES,
  STATUS_CODES,
  normalizeError,
} from '../errcodes'
import { isPermissionDenied } from '../http'

/** 判据① 的病灶原文（本件拿它当反向夹具：这一句回到字典里就必须红）。 */
const SCOPE_BEFORE = '请先选择部门范围，再生成这项结果。'
/** ②不许画成的那一格：permission_denied 的既有句，一字不改（判据③的邻格自证）。 */
const GENERIC_DENIED = '当前账号没有这项权限，请联系管理员开通。'

/** axios 错误的最小形状：这一发只用得到 response.status 与 response.data.detail。 */
function httpError(status, detail) {
  return {
    isAxiosError: true,
    message: `Request failed with status code ${status}`,
    response: { status, data: { detail } },
    config: { url: '/approval/precheck' },
  }
}

describe('甲 · 判据① 部门范围那一格：下一步必须是这台界面做得出来的', () => {
  const message = ERROR_CODES.department_scope_required.message

  it('旧句已经不在字典里，「叫用户选部门」这一律指错方向的写法一并清掉', () => {
    expect(message).not.toBe(SCOPE_BEFORE)
    expect(message).not.toContain('请先选择部门范围')
    expect(message).not.toMatch(/选择部门|部门范围/)
  })

  it('新句承认没做成、说得出缺的是哪一格、并给出做得到的下一步', () => {
    expect(message).not.toBe(FALLBACK_MESSAGE)
    expect(message).toContain('没能生成')
    expect(message).toContain('部门')
    expect(message).toContain('联系管理员')
    // 两条出口都得真做得出来：这条码的因由在人身上，换带部门的账号也是同一台界面上就有的动作
    expect(message).toMatch(/已登记部门的账号|补上你的部门归属/)
    expect(message).not.toMatch(/[a-z][a-z0-9]*(_[a-z0-9]+)+/)
  })

  it('走真实通道拿到的就是字典这一句，retryable 仍为 false：原样重发不会变', () => {
    const result = normalizeError(httpError(403, 'department_scope_required'))
    expect(result.code).toBe('department_scope_required')
    expect(result.rawCode).toBe('')
    expect(result.message).toBe(message)
    expect(result.retryable).toBe(false)
  })
})

describe('乙 · 判据② department_override_denied 收进字典真码位，不再一律画成没有权限', () => {
  it('别名表里确有这一枚（立案时是 0 命中），折叠目标必须是枚举成员', () => {
    expect(Object.keys(LEGACY_ALIASES)).toContain('department_override_denied')
    const entry = LEGACY_ALIASES.department_override_denied
    expect(Object.keys(ERROR_CODES)).toContain(entry.code)
    expect(typeof entry.message).toBe('string')
    expect(entry.retryable).toBe(false)
  })

  it('句子说的是「替别人报部门」这一格，不是缺一项权限', () => {
    const result = normalizeError(httpError(403, 'department_override_denied'))
    expect(result.rawCode).toBe('department_override_denied')
    expect(result.message).not.toBe(FALLBACK_MESSAGE)
    expect(result.message).not.toBe(GENERIC_DENIED)
    expect(result.message).not.toContain('没有权限')
    expect(result.message).toContain('部门')
    // 后端真接受的两条出口（authorization.py:88-90：留空或重复自己的部门），不许发明第三条
    expect(result.message).toMatch(/留空/)
    expect(result.message).toMatch(/你自己的部门/)
    expect(result.message).not.toMatch(/[a-z][a-z0-9]*(_[a-z0-9]+)+/)
  })

  it('isPermissionDenied 回 false：兜底成 permission_denied 的那一天就是这一枚的红', () => {
    expect(STATUS_CODES[403]).toBe('permission_denied')
    expect(isPermissionDenied(httpError(403, 'department_override_denied'))).toBe(false)
    // 对照组：未登记的码仍走状态兜底 ⇒ 判据本身不是恒真
    expect(isPermissionDenied(httpError(403, 'a_code_nobody_registered_yet'))).toBe(true)
  })

  it('不许折进停表与无权限那一格：permission_denied 的既有句子一字未改', () => {
    expect(LEGACY_ALIASES.department_override_denied.code).not.toBe('permission_denied')
    expect(ERROR_CODES.permission_denied.message).toBe(GENERIC_DENIED)
  })
})
