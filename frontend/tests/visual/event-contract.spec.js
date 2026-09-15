import { test } from '@playwright/test'

/**
 * V6 清单里的事件契约用例：喂 canonical + legacy + 未知事件，断言不崩、不空白。
 *
 * 现在挂不起来：它需要 V3 的 vue-router 视图与一个已登录会话
 * （`chat-ask` 事件由 ChatPanel/工作区接收，本分支还没有 router/ 与 views/）。
 * 用 test.fixme 显式登记，不伪装成通过；A 线 V3 落地后把 body 补上即可。
 */
test.describe('事件契约（等 V3 路由与登录态）', () => {
  test.fixme('canonical 事件形状不崩', async () => {})
  test.fixme('legacy 字符串 payload 不崩', async () => {})
  test.fixme('未知事件不崩、不空白', async () => {})
})
