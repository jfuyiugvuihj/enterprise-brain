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