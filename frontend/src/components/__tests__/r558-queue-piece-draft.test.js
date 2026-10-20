/**
 * R558 · 队列道增量片段的屏侧形状（跟进单 §142 判据⑤）。
 *
 * 为什么这一件是「源码形状」而不是渲染：`ChatPanel.vue` 的轮询腿住在 `<script setup>` 里，
 * 由 `onMounted` 起表；本仓的 vitest 跑的是 node + @vue/server-renderer，SSR 不执行
 * onMounted（同族先例见 `chat-model-status.test.js` 抬头第 ③ 条，它同样把像素让给 tests/visual）。
 * 所以这里钉的是接线本身——游标带没带、草稿与终答谁盖谁、有没有偷偷多长出一条渲染腿。
 * 真「一个字一个字长出来」的像素证据归跑分窗，不许拿本件冒充。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(
  new URL('../ChatPanel.vue', import.meta.url),
  'utf8',
)

function block(name) {
  const start = source.indexOf(`function ${name}(`)
  if (start < 0) return ''
  const next = source.indexOf('\nfunction ', start + 1)
  return source.slice(start, next < 0 ? source.length : next)
}

describe('R558 队列道增量片段的屏侧形状', () => {
  it('轮询必须带上游标，否则每一发都在重拿全篇', () => {
    expect(source).toContain('const queuePieces = ref({})')
    expect(source).toMatch(/\/queue\/status\/\$\{encodeURIComponent\(requestId\)\}\?since=/)
    expect(source).toContain('status.data?.stream_pieces')
  })

  it('草稿只有一个写点，且它写进的是本来那条正文腿', () => {
    const draft = block('applyQueuedPiece')
    expect(draft).not.toBe('')
    expect(draft).toContain('msg.content = text')
    expect(draft).toContain('msg.pieceDraft = true')
    // 收了不画就是假接线：草稿那一支不许只存进台账。
    expect(draft).toContain('syncActive()')
    // 零新组件、零新 class、零裸色值（判据⑤ 的三条硬约束）。
    expect(draft).not.toMatch(/class=/)
    expect(draft).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(draft).not.toMatch(/rgba?\(/)
  })

  it('终答到货整段替换草稿，而不是接着加', () => {
    const settled = block('applyQueuedAnswer')
    expect(settled).toContain('if (msg.content && !msg.pieceDraft) return')
    expect(settled).toContain('msg.pieceSettled = true')
    expect(settled).toContain('msg.content = answer')
    // 每轮一条答案：草稿位被终答认领之后不许再被片段改写。
    expect(block('applyQueuedPiece')).toContain('msg.pieceSettled')
  })

  it('屏侧没有为片段另起一条投递腿', () => {
    expect(source).not.toMatch(/EventSource|new WebSocket/)
    // 模板串那一层反引号要在场：轮询腿写的是 http.get(`/queue/status/...`)。
    const pollLegs = source.match(/http\.get\(\s*`\/queue\/status/g) || []
    expect(pollLegs).toHaveLength(1)
  })
})