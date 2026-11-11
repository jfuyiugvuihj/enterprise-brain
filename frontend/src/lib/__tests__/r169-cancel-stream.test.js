/**
 * R169 · V1 前端主链路验收矩阵 —— 取消这一格的传输层（按了停止之后，内容到底还进不进得来）
 *
 * 既存 659 枚在「取消」上的落点是零：`git grep confirmCancel|requestCancel|abortStream -- '*test.js'`
 * 只命中产物侧的两步删除（那是「删除二次确认」的取消，不是回答流的取消）。
 * lib/r150-event-claims.test.js 把**帧读成事实**那一层钉得很实（含「迟到的 sources 被 sequence
 * 闸门吃掉」），但它喂的是自造 response，没有一枚用例从 `beginStream()` 的 signal 出发。
 * 于是「用户按了停止 → 这一轮不再收内容」这句话今天只有面板侧的文案，没有传输层的证据。
 * 本文件补的就是这一截：真 beginStream / abortStream / consumeSseStream，跑真的。
 *
 * 🔴 一条都不置灰、不挂待办、不放宽任何既存断言；也不打真后端（这里连 socket 都不开）。
 */
import { describe, expect, it, vi } from 'vitest'
import { abortStream, beginStream, consumeSseStream, endStream, isStreaming, loading } from '../sessions.js'

function frame(event, data) {
  return `event: ${event}\ndata: ${JSON.stringify(data || {})}\n\n`
}

/**
 * 一条会「边读边动」的假流：读到第 before 帧之后执行 onChange（用来模拟用户中途按停止），
 * 后面还留着若干帧——它们绝不该再进这一轮。
 */
function streamOf(events, { before = Infinity, onChange = null } = {}) {
  const bytes = events.map(event => new TextEncoder().encode(event))
  let index = 0
  let reads = 0
  return {
    reads: () => reads,
    response: {
      ok: true,
      status: 200,
      headers: { get: () => null },
      clone() { return this },
      async json() { return null },
      body: {
        getReader() {
          return {
            async read() {
              if (index >= bytes.length) return { done: true }
              const value = bytes[index++]
              reads += 1
              if (reads === before && onChange) await onChange()
              return { done: false, value }
            },
            async cancel() {},
          }
        },
      },
    },
  }
}

describe('R169 Q5 · 停止之后这一轮不再进内容（真 beginStream + 真 consumeSseStream）', () => {
  it('开一条流就是 loading：界面据此才知道「停止」这一枚按钮有资格存在', () => {
    const signal = beginStream()
    expect(loading.value).toBe(true)
    expect(isStreaming()).toBe(true)
    expect(signal.aborted).toBe(false)
    endStream()
    expect(loading.value).toBe(false)
    expect(isStreaming()).toBe(false)
  })

  it('中途按下停止：已经收到的正文留着，后面的帧一字节都不再进这一轮', async () => {
    const signal = beginStream()
    const msg = { role: 'assistant', content: '', steps: [] }
    const streamed = []
    const stream = streamOf(
      [frame('text', { content: '第一段。' }), frame('text', { content: '第二段。' }), frame('text', { content: '第三段。' })],
      { before: 1, onChange: async () => { abortStream() } },
    )
    const result = await consumeSseStream(stream.response, msg, { signal, onText: state => streamed.push(state.text) })
    expect(result.ok).toBe(true)
    expect(result.stopped).toBe('aborted')
    expect(msg.content).toBe('第一段。')
    expect(stream.reads()).toBe(1)
    // 掐断动作本身交给 fetch 的 signal（面板把同一枚 signal 传给 authedFetch，见
    // components/__tests__/r169-chat-panel.test.js 那一组）；读流层这一腿只保证一件事：
    // 循环自己停了，不再往里读第二帧。
    expect(signal.aborted).toBe(true)
    endStream()
  })

  it('读帧读到一半连接被掐断：算「已中断」，不算「坏了」，也不许把半截正文洗掉', async () => {
    const signal = beginStream()
    const msg = { role: 'assistant', content: '已有半截。', steps: [] }
    const onFailed = vi.fn()
    let reads = 0
    const response = {
      ok: true,
      status: 200,
      headers: { get: () => null },
      clone() { return this },
      async json() { return null },
      body: {
        getReader() {
          return {
            async read() {
              reads += 1
              abortStream()
              throw Object.assign(new Error('This operation was aborted'), { name: 'AbortError' })
            },
            async cancel() {},
          }
        },
      },
    }
    const result = await consumeSseStream(response, msg, { signal, onFailed })
    expect(reads).toBe(1)
    expect(result.stopped).toBe('aborted')
    expect(onFailed, '中断不该走失败那条回调').not.toHaveBeenCalled()
    expect(msg.content).toBe('已有半截。')
    endStream()
  })

  it('读帧读到一半真的坏了（不是取消）：这一腿要往上抛，由面板说「连接中断」', async () => {
    beginStream()
    const msg = { role: 'assistant', content: '', steps: [] }
    const response = {
      ok: true,
      status: 200,
      headers: { get: () => null },
      clone() { return this },
      async json() { return null },
      body: {
        getReader() {
          return {
            async read() { throw new Error('socket hang up') },
            async cancel() {},
          }
        },
      },
    }
    await expect(consumeSseStream(response, msg, {})).rejects.toThrow('socket hang up')
    endStream()
  })

  it('出发前就已经取消：一帧都不读，也不谎称「本轮没有返回内容」', async () => {
    const signal = beginStream()
    abortStream()
    const msg = { role: 'assistant', content: '', steps: [] }
    const onText = vi.fn()
    const stream = streamOf([frame('text', { content: '不该被读到。' })])
    const result = await consumeSseStream(stream.response, msg, { signal, onText })
    expect(stream.reads()).toBe(0)
    expect(result.stopped).toBe('aborted')
    expect(onText).not.toHaveBeenCalled()
    expect(msg.content).toBe('')
    endStream()
  })

  it('后端自己宣布取消（cancelled 帧）：是这一轮走到了终点，不是客户端掐的', async () => {
    const signal = beginStream()
    const msg = { role: 'assistant', content: '', steps: [] }
    const stream = streamOf([frame('text', { content: '前半段。' }), frame('cancelled', {}), frame('text', { content: '取消之后还来一帧。' })])
    const result = await consumeSseStream(stream.response, msg, { signal })
    expect(result.state.terminal).toBe('cancelled')
    expect(result.stopped).toBe('cancelled')
    expect(msg.content).toBe('前半段。')
    endStream()
  })

  it('这一轮跑完了：stopped 落在 done，正文一格不少（拿它当「取消」的反面对照）', async () => {
    const signal = beginStream()
    const msg = { role: 'assistant', content: '', steps: [] }
    const stream = streamOf([frame('text', { content: '全部三段。' }), frame('text', { content: '第二段。' }), frame('done', {})])
    const result = await consumeSseStream(stream.response, msg, { signal })
    expect(result.stopped).toBe('done')
    expect(result.state.terminal).not.toBe('cancelled')
    expect(msg.content).toContain('第二段。')
    endStream()
  })
})
