/**
 * R195 判据① · 「采纳 / 驳回」的判定、措辞与状态机（纯函数层，node 直接跑）
 *
 * 这一枚钉的四件事：
 *   ① 请求体只可能有两枚键，值只可能是后端认的那两枚；第三枚值（例如「未评价」）当场不组装；
 *   ② 撤回这条路【不存在】——取证 app/api/v1/feedback.py 只有 POST 与 GET 两枚路由，
 *      那张表的写法是累加计数，所以记上之后必须锁死，第二次点击一枚请求都不许发；
 *   ③ 没读到确认回执之前按钮不许亮：sending 与一切失败脸都不许出现「已记录 / 已记下」；
 *   ④ 401 / 422 / 断网 三张脸各长得不一样，且都不谎报入账。
 */
import { describe, expect, it, vi } from 'vitest'

import {
  FEEDBACK_BODY_KEYS,
  FEEDBACK_PATH,
  MAX_FILENAME_CHARS,
  PHASE_FAILED,
  PHASE_IDLE,
  PHASE_RECORDED,
  PHASE_SENDING,
  PHASE_UNCERTAIN,
  SIGNALS,
  canSendSignal,
  feedbackAriaLabel,
  feedbackButtonProps,
  feedbackNotice,
  feedbackRequestBody,
  filenameTooLong,
  initialFeedbackState,
  receiptView,
  requestFeedback,
  rowFeedbackBlocked,
  rowFilename,
  rowMarkable,
  sendDocumentSignal,
  settleFeedback,
  signalFailureView,
  signalLabel,
} from '../feedback'

const NAME = '差旅费报销制度-2026.pdf'
const QUESTION = '上个季度华东区的销售额是多少，同比涨了多少'
const ANSWER = '根据销售明细.csv，上季度华东区销售额为 1280 万元，同比上涨 12%'
const HIT = '第四条 差旅费按职级实报实销，超出部分由本人承担'

/** 后端 200 的原样回执（docs/api/contract-v1.md 那五格）。 */
const okReceipt = (signal, extra = {}) => ({
  status: 'ok',
  filename: NAME,
  signal,
  accepted_count: 4,
  rejected_count: 1,
  ...extra,
})

const errorOf = (status, detail) => ({ response: { status, data: { detail } }, message: 'Request failed' })
const networkDown = () => ({ code: 'ERR_NETWORK', request: {}, message: 'Network Error' })
const timedOut = () => ({ code: 'ECONNABORTED', request: {}, message: 'timeout of 30000ms exceeded' })

const recorded = signal => settleFeedback(requestFeedback(initialFeedbackState(), signal), receiptView(okReceipt(signal), { filename: NAME, signal }))

describe('R195 判据① · 契约形状', () => {
  it('路径、两枚键、两枚值都是后端那一套，一字不多', () => {
    expect(FEEDBACK_PATH).toBe('/feedback/document')
    expect(FEEDBACK_BODY_KEYS).toEqual(['filename', 'signal'])
    expect(SIGNALS).toEqual(['accepted', 'rejected'])
  })

  it('请求体只含两枚键，值原样是文件名与信号', () => {
    const body = feedbackRequestBody('  ' + NAME + '  ', 'accepted')
    expect(Object.keys(body)).toEqual(['filename', 'signal'])
    expect(body).toEqual({ filename: NAME, signal: 'accepted' })
  })

  it('第三枚值一律不组装：未评价 / 中立 / 大写都不发（后端只有两枚枚举值）', () => {
    for (const signal of ['neutral', 'none', 'withdraw', 'retract', 'ACCEPTED', '', 'unrated', null, undefined]) {
      expect(feedbackRequestBody(NAME, signal), String(signal)).toBeNull()
    }
  })

  it('文件名空 / 只有空格 / 带换行 / 超长都不组装（发出去也是白发的 422）', () => {
    expect(feedbackRequestBody('', 'accepted')).toBeNull()
    expect(feedbackRequestBody('   ', 'accepted')).toBeNull()
    expect(feedbackRequestBody(NAME + '\n' + QUESTION, 'accepted')).toBeNull()
    expect(feedbackRequestBody('a\r\nb', 'accepted')).toBeNull()
    const long = '长'.repeat(MAX_FILENAME_CHARS + 1)
    expect(filenameTooLong(long)).toBe(true)
    expect(feedbackRequestBody(long, 'accepted')).toBeNull()
    expect(filenameTooLong('长'.repeat(MAX_FILENAME_CHARS))).toBe(false)
    expect(feedbackRequestBody('长'.repeat(MAX_FILENAME_CHARS), 'accepted')).not.toBeNull()
  })

  it('发出去的是问题原文以外的那一格：整条 JSON 里没有问句、答案与命中句', async () => {
    const post = vi.fn().mockResolvedValue({ data: okReceipt('accepted') })
    await sendDocumentSignal(NAME, 'accepted', { post })
    expect(post).toHaveBeenCalledTimes(1)
    const [path, body] = post.mock.calls[0]
    expect(path).toBe(FEEDBACK_PATH)
    expect(Object.keys(body)).toEqual(['filename', 'signal'])
    const wire = JSON.stringify(body)
    for (const secret of [QUESTION, ANSWER, HIT]) {
      expect(wire.includes(secret), wire).toBe(false)
    }
  })

  it('本地就该拒的形状一次请求都不发（不发一条打歪的账）', async () => {
    const post = vi.fn()
    const empty = await sendDocumentSignal('   ', 'accepted', { post })
    const long = await sendDocumentSignal('名'.repeat(MAX_FILENAME_CHARS + 1), 'rejected', { post })
    const bogus = await sendDocumentSignal(NAME, 'neutral', { post })
    expect(post).not.toHaveBeenCalled()
    for (const view of [empty, long, bogus]) {
      expect(view.kind).toBe('failed')
      expect(view.headline + view.detail).not.toContain('已记录')
    }
    expect(long.face).toBe('too_long')
    expect(empty.face).toBe('no_filename')
  })
})

describe('R195 判据② · 状态机没有撤回这支', () => {
  it('idle 可点，按下去进 sending，且两枚互斥地一起按住', () => {
    const idle = initialFeedbackState()
    expect(canSendSignal(idle)).toBe(true)
    const sending = requestFeedback(idle, 'accepted')
    expect(sending.phase).toBe(PHASE_SENDING)
    expect(sending.signal).toBe('accepted')
    expect(canSendSignal(sending)).toBe(false)
    for (const signal of SIGNALS) {
      expect(feedbackButtonProps(sending, signal).disabled).toBe(true)
      expect(feedbackButtonProps(sending, signal).pressed).toBe(false)
    }
  })

  it('回执到了才点亮，亮的只有点过的那一枚', () => {
    const state = recorded('accepted')
    expect(state.phase).toBe(PHASE_RECORDED)
    expect(state.acceptedCount).toBe(4)
    expect(state.rejectedCount).toBe(1)
    expect(feedbackButtonProps(state, 'accepted').pressed).toBe(true)
    expect(feedbackButtonProps(state, 'rejected').pressed).toBe(false)
  })

  it('🔴 记上之后再点第二下一枚请求都不发（后端没有撤回出口，也不许发反向信号）', async () => {
    const post = vi.fn().mockResolvedValue({ data: okReceipt('accepted') })
    const state = settleFeedback(requestFeedback(initialFeedbackState(), 'accepted'), await sendDocumentSignal(NAME, 'accepted', { post }))
    expect(post).toHaveBeenCalledTimes(1)
    // 第二下的闸门在状态机这一侧：requestFeedback 直接返回 null，组件拿不到新态就一动不动。
    // （端到端那一枪由 r195-source-feedback.test.js 在真组件上钉：再点一次发不出第二条 POST。）
    expect(requestFeedback(state, 'accepted')).toBeNull()
    expect(requestFeedback(state, 'rejected')).toBeNull()
    expect(feedbackButtonProps(state, 'accepted').disabled).toBe(true)
    expect(feedbackButtonProps(state, 'rejected').disabled).toBe(true)
  })

  it('失败那一次可以补点：那不是第二枚信号，是同一枚补上', () => {
    const failed = settleFeedback(requestFeedback(initialFeedbackState(), 'accepted'), signalFailureView(errorOf(401, 'authentication_required')))
    expect(failed.phase).toBe(PHASE_FAILED)
    expect(canSendSignal(failed)).toBe(true)
    expect(failed.signal).toBe('')
    expect(feedbackButtonProps(failed, 'accepted').pressed).toBe(false)
    expect(feedbackButtonProps(failed, 'rejected').pressed).toBe(false)
    expect(requestFeedback(failed, 'rejected')).not.toBeNull()
  })

  it('没确认的那一笔不许补点：再点可能多记一次，所以只留话不留门', () => {
    const uncertain = settleFeedback(requestFeedback(initialFeedbackState(), 'accepted'), receiptView({ status: 'ok' }, { filename: NAME, signal: 'accepted' }))
    expect(uncertain.phase).toBe(PHASE_UNCERTAIN)
    expect(canSendSignal(uncertain)).toBe(false)
    expect(requestFeedback(uncertain, 'rejected')).toBeNull()
    const notice = feedbackNotice(uncertain)
    expect(notice.headline).toContain('没读到确认回执')
    expect(notice.headline + notice.detail).not.toContain('已记录')
  })

  it('半截态与认不下的结果都不许被读成没发生', () => {
    // 垃圾态：判不了就当没记过（可点），但绝不说已记录
    expect(canSendSignal('')).toBe(true)
    expect(canSendSignal(null)).toBe(true)
    expect(feedbackNotice(null).headline).toBe('')
    // 记上了但信号值认不下：锁住不放行，也不点亮任何一枚
    const half = { phase: PHASE_RECORDED, signal: 'neutral', view: null }
    expect(canSendSignal(half)).toBe(false)
    expect(requestFeedback(half, 'rejected')).toBeNull()
    expect(feedbackButtonProps(half, 'accepted').pressed).toBe(false)
    expect(feedbackNotice(half).headline).toBe('')
    // 认不下的发送结果：折成 failed（有句话要说），绝不折回 idle 或 recorded
    expect(settleFeedback(initialFeedbackState(), { kind: 'noop' }).phase).toBe(PHASE_FAILED)
    expect(settleFeedback(initialFeedbackState(), null).phase).toBe(PHASE_UNCERTAIN)
  })
})

describe('R195 判据③ · 200 回执要认，认不下就不点亮', () => {
  it('五格齐全才叫记下', () => {
    expect(receiptView(okReceipt('rejected'), { filename: NAME, signal: 'rejected' }).kind).toBe('recorded')
  })

  it('status / signal / filename 任一格对不上号都只是 uncertain', () => {
    const cases = [
      [null, '空回执'],
      [{}, '只有空对象'],
      [{ status: 'ok' }, '少了 signal'],
      [{ status: 'queued', signal: 'accepted', filename: NAME }, 'status 不是 ok'],
      [{ status: 'ok', signal: 'rejected', filename: NAME }, '回执里的信号与点的那枚不同'],
      [{ status: 'ok', signal: 'accepted', filename: '别的文件.docx' }, '回执说的是另一份文件'],
    ]
    for (const [payload, label] of cases) {
      const view = receiptView(payload, { filename: NAME, signal: 'accepted' })
      expect(view.kind, label).toBe('uncertain')
      expect(view.face, label).toBe('unconfirmed')
    }
  })

  it('计数读不到就是 null，不补一个 0 上去', () => {
    const view = receiptView({ status: 'ok', signal: 'accepted', filename: NAME }, { filename: NAME, signal: 'accepted' })
    expect(view.kind).toBe('recorded')
    expect(view.acceptedCount).toBeNull()
    expect(view.rejectedCount).toBeNull()
  })
})

describe('R195 判据④ · 三张失败脸各不相同且不谎报', () => {
  const faces = [
    ['unauthorized', errorOf(401, 'authentication_required')],
    ['denied', errorOf(403, 'permission_denied')],
    ['missing', errorOf(404, 'resource_not_found')],
    ['body_refused', errorOf(422, 'validation_error')],
    ['storage', errorOf(503, 'storage_unavailable')],
    ['timeout', timedOut()],
    ['offline', networkDown()],
    ['unknown', errorOf(500, 'internal_error')],
  ]

  it('每一档的 face 与句子都不同：8 档 8 个键、8 句标题', () => {
    const seen = faces.map(([key, err]) => {
      const view = signalFailureView(err)
      expect(view.kind, key).toBe('failed')
      expect(view.face, key).toBe(key)
      expect(view.headline, key).toBeTruthy()
      return view
    })
    expect(new Set(seen.map(item => item.face)).size).toBe(8)
    expect(new Set(seen.map(item => item.headline)).size).toBe(8)
  })

  it('401 / 422 / 断网三张两两不同，且都说什么没做到', () => {
    const unauthorized = signalFailureView(errorOf(401, 'authentication_required'))
    const refused = signalFailureView(errorOf(422, 'validation_error'))
    const offline = signalFailureView(networkDown())
    const trio = [unauthorized, refused, offline]
    expect(new Set(trio.map(item => item.headline)).size).toBe(3)
    expect(new Set(trio.map(item => item.detail)).size).toBe(3)
    for (const item of trio) {
      const prose = item.headline + item.detail
      expect(prose).not.toMatch(/已记录|已记下|记上了|完成/)
      expect(prose).toMatch(/没有记上|没有等到回执|说不准/)
    }
    expect(unauthorized.headline).toContain('登录')
    expect(refused.headline).toContain('提交被服务端挡下')
    expect(offline.headline).toContain('连不上服务端')
  })

  it('每一档失败句子里都不许出现「已记录」，也不许把码名夹进人话', () => {
    for (const [key, err] of faces) {
      const view = signalFailureView(err)
      const prose = view.headline + view.detail
      expect(prose, key).not.toMatch(/已记录|已记下/)
      expect(prose, key).not.toMatch(/[a-z][a-z0-9]*(_[a-z0-9]+)+/)
    }
  })

  it('断网与超时不许按入账记账，但话要说清可能已经到了', () => {
    for (const err of [networkDown(), timedOut()]) {
      const prose = signalFailureView(err)
      expect(prose.retryable).toBe(true)
      expect(prose.detail).toContain('再点一次')
    }
  })
})

describe('R195 判据① · 措辞像人话，撤回不做就说明白', () => {
  it('两枚按钮的字：有用 / 没用，认不下的值没有字', () => {
    expect(signalLabel('accepted')).toBe('有用')
    expect(signalLabel('rejected')).toBe('没用')
    expect(signalLabel('neutral')).toBe('')
  })

  it('sending 那句不许提前宣布成功', () => {
    const notice = feedbackNotice({ phase: PHASE_SENDING, signal: 'accepted' })
    expect(notice.headline).toContain('正在')
    expect(notice.headline + notice.detail).not.toMatch(/已记录|已记下|成功|完成/)
  })

  it('记下那一句直说只记一次、改不了，并把原因给到后端没有撤回的门', () => {
    const accepted = feedbackNotice(recorded('accepted'))
    expect(accepted.headline).toBe('这处出处已记下「有用」。')
    expect(accepted.detail).toContain('一处出处只记一次')
    expect(accepted.detail).toContain('改不了')
    expect(accepted.detail).toContain('撤回')
    expect(feedbackNotice(recorded('rejected')).headline).toBe('这处出处已记下「没用」。')
  })

  it('idle 不留一个字：没点过就没有任何一句评价读数', () => {
    const notice = feedbackNotice(initialFeedbackState())
    expect(notice.headline).toBe('')
    expect(notice.detail).toBe('')
  })

  it('aria 全称带上文件名，屏上只读到「有用」也知道在说哪一份', () => {
    expect(feedbackAriaLabel('accepted', NAME)).toBe('把这处出处『' + NAME + '』标记为有用')
    expect(feedbackAriaLabel('neutral', NAME)).toBe('')
  })
})

describe('R195 判据① · 行能不能评价由文件名判，不由文案判', () => {
  it('取文件名只读 filename 那一格，别的一概不算名字', () => {
    expect(rowFilename({ filename: '  ' + NAME + ' ' })).toBe(NAME)
    expect(rowFilename({ excerpt: HIT })).toBe('')
    expect(rowFilename(null)).toBe('')
    expect(rowFilename({ filename: 123 })).toBe('')
  })

  it('没名字、带换行、超上界的名字都不摆按钮，且各有一句为什么', () => {
    expect(rowMarkable({ filename: NAME })).toBe(true)
    expect(rowFeedbackBlocked({ filename: NAME })).toBe(null)
    expect(rowMarkable({ filename: '' })).toBe(false)
    expect(rowMarkable({})).toBe(false)
    expect(rowMarkable({ filename: NAME + '\n' + QUESTION })).toBe(false)
    expect(rowMarkable({ filename: '长'.repeat(MAX_FILENAME_CHARS + 1) })).toBe(false)
    expect(rowFeedbackBlocked({ filename: '' }).headline).toBe('这一行没有可记录的出处名称')
    expect(rowFeedbackBlocked({ filename: NAME + '\n' + QUESTION }).headline).toBe('这份资料的名称里有换行，评价送不出去')
    expect(rowFeedbackBlocked({ filename: '长'.repeat(MAX_FILENAME_CHARS + 1) }).headline).toBe('这份资料的名称太长，评价送不出去')
    for (const bad of [{}, { filename: '' }, { filename: NAME + '\n' + QUESTION }]) {
      const prose = rowFeedbackBlocked(bad).headline + rowFeedbackBlocked(bad).detail
      expect(prose).not.toMatch(/已记录|已记下/)
    }
  })
})