/**
 * R150 · 「三张脸」的措辞与判定（lib/provenance.js 纯函数，零 IO、零 DOM、零网络）
 *
 * 这一层的价值全在【分开说】三个字上：
 *   「另有 N 处命中未展示」与「没检索到」是两句不同的话（判据②，私有化产品最被客户追问的那句）
 *   「实时算／命中缓存／缓存已改版／无从核对」四态不许并成一句「出错了」（判据③）
 *   「未排队／排队中前面 N 人／没能排上队」三态各说各的（判据④）
 * 每条断言钉的都是【另一个 kind 不许出现的那句话】，这样把两态合并成一态的改动当场就红。
 */
import { describe, expect, it } from 'vitest'
import {
  cacheFace,
  classificationLabel,
  formatMoment,
  queueFace,
  queuePollFailedFace,
  queueRejectedFace,
  queueStatsFace,
  revisionsAfter,
  scoreLabel,
  scopeReasonText,
  sourcesFace,
  versionMoment,
} from './provenance.js'
import { errorCodeLabel, normalizeError } from './errcodes.js'

const row = (over = {}) => ({
  filename: '差旅费报销制度-2026.pdf',
  sourceId: 'doc-travel',
  chunkIndex: 4,
  score: 0.412,
  scoreType: 'rerank',
  versionId: '7',
  classification: '2',
  department: '销售部',
  excerpt: '',
  ...over,
})

describe('A · 出处那张脸：四态各说各的', () => {
  it('后端没发 sources 事件 → null，界面这一格留白（留白不等于「没检索到」）', () => {
    expect(sourcesFace(null)).toBe(null)
    expect(sourcesFace(undefined)).toBe(null)
  })

  it('有可见行：headline 报条数，hidden 为 0 时那句「未展示」根本不出现', () => {
    const face = sourcesFace({ rows: [row(), row({ filename: '采购管理办法.docx', sourceId: 'b' })], hitCount: 2, hiddenCount: 0, scopeReasonCode: 'department_scope' })
    expect(face.kind).toBe('visible')
    expect(face.headline).toContain('2')
    expect(face.hiddenLine).toBe('')
    expect(face.headline).not.toContain('未展示')
  })

  it('一条没检到：说的是「没有检索到可用文档」，且不出现「未展示」那句', () => {
    const face = sourcesFace({ rows: [], hitCount: 0, hiddenCount: 0, scopeReasonCode: '' })
    expect(face.kind).toBe('none')
    expect(face.headline).toContain('没有检索到')
    expect(face.hiddenLine).toBe('')
    expect(face.reason).not.toContain('未展示')
  })

  it('全是无权可见：必须说「检索到了但不给你看」，且「没有检索到」那句话一个字都不许出现', () => {
    const face = sourcesFace({ rows: [], hitCount: 0, hiddenCount: 3, scopeReasonCode: 'department_scope' })
    expect(face.kind).toBe('all-hidden')
    expect(face.headline).toContain('3')
    expect(face.hiddenLine).toBe('另有 3 处命中未展示')
    expect(face.headline).not.toContain('没有检索到')
    // 判据②：这两句分属两个字段/两个节点，组件用例再钉它们不共用一个 DOM
    expect(face.headline).not.toBe(face.hiddenLine)
  })

  it('有可见行也有无权行：条数与「未展示」同时在场，两行各说一件事', () => {
    const face = sourcesFace({ rows: [row()], hitCount: 1, hiddenCount: 2, scopeReasonCode: 'administrator_scope' })
    expect(face.kind).toBe('visible')
    expect(face.hiddenLine).toBe('另有 2 处命中未展示')
    expect(face.headline).not.toContain('未展示')
  })

  it('范围理由取不到时后端把错误码塞进同一格：这一态不许画成「没检索到」', () => {
    const face = sourcesFace({ rows: [], hitCount: 0, hiddenCount: 0, scopeReasonCode: 'authorization_unavailable' })
    expect(face.kind).toBe('scope-error')
    expect(face.tone).toBe('danger')
    expect(face.headline).not.toContain('没有检索到')
  })

  it('hit_count 与行数不等 = 线上出了我们没见过的形状：写进诊断，不静默取其一', () => {
    const face = sourcesFace({ rows: [row()], hitCount: 9, hiddenCount: 0, scopeReasonCode: '' })
    expect(face.diagnostics.length).toBe(1)
    expect(face.diagnostics[0]).toContain('9')
    expect(face.diagnostics[0]).toContain('1')
  })

  it('已登记的范围理由各自有一句人话，两句不许同文', () => {
    const admin = sourcesFace({ rows: [row()], hitCount: 1, hiddenCount: 0, scopeReasonCode: 'administrator_scope' })
    expect(scopeReasonText(admin.reasonCode)).toContain('管理级')
    expect(scopeReasonText('department_scope')).not.toBe(scopeReasonText('administrator_scope'))
  })
})

describe('B · 卡片上的字段措辞：后端给什么说什么，不给就不编', () => {
  it('密级说级不猜名字（3 级在后端对应两枚名字，猜必错）', () => {
    expect(classificationLabel('3')).toBe('密级 3 级')
    expect(classificationLabel('')).toBe('')
    expect(classificationLabel('内部公开')).toBe('内部公开')
  })

  it('重排分写成重排分，不许伪装成百分比', () => {
    const reranked = scoreLabel(row({ score: 0.412, scoreType: 'rerank' }))
    expect(reranked).toContain('重排分')
    expect(reranked).not.toContain('%')
    expect(scoreLabel(row({ score: null, scoreType: '' }))).toBe('')
  })
})

describe('C · 缓存那张脸：四态不许并成一句', () => {
  it('实时算这一态明写它的证据是「当场没带回读数」，不是「后端报了未命中」', () => {
    const face = cacheFace({ cached: false, generatedAt: '', note: '', observed: true })
    expect(face.kind).toBe('live')
    expect(face.headline).toContain('实时')
    expect(face.detail).toContain('读数')
    expect(face.detail).not.toContain('缓存结果')
  })

  it('没被当场观察过的轮次一律不表态：拿缺席推「当时是实时算的」就是拿没证据当证据', () => {
    expect(cacheFace(null)).toBe(null)
    expect(cacheFace(undefined)).toBe(null)
    // 老消息从 localStorage 复原时可能只留下正文：没有 observed 这一格，界面就别说这一态
    expect(cacheFace({ cached: false, generatedAt: '', note: '' })).toBe(null)
  })

  it('命中缓存、还没核对：说「正在核对」，不许提前宣布有没有改版', () => {
    const face = cacheFace({ cached: true, generatedAt: '2026-09-21T09:00:00Z', note: '' })
    expect(face.kind).toBe('cached')
    expect(face.detail).toContain('核对')
    expect(face.headline).not.toContain('改版')
    // 断言「屏上的时间就是读数换算出来的那个」，不手抄钟点：手抄 18:00 会让这台 +08 的机器
    // 在别的时区里假红，也会把「格式」与「来源」两件事混成一件事。
    expect(face.headline).toContain(formatMoment('2026-09-21T09:00:00Z'))
  })

  it('核对过、确实没改版 → 「没有新版本入库」，不出现「改版」那个断言句', () => {
    const face = cacheFace({ cached: true, generatedAt: '2026-09-21T09:00:00Z', note: '' }, [])
    expect(face.kind).toBe('cached')
    expect(face.detail).toContain('没有新版本')
    expect(face.headline).not.toContain('已改版')
  })

  it('核对过、有改版 → 那句必须带文件名与入库时间，时间只来自版本读数', () => {
    const staleness = [{ filename: '差旅费报销制度-2026.pdf', revisions: [{ version: 8, moment: '2026-09-21T10:00:00Z' }], latestVersion: 8, latestMoment: '2026-09-21T10:00:00Z' }]
    const face = cacheFace({ cached: true, generatedAt: '2026-09-21T09:00:00Z', note: '' }, staleness)
    expect(face.kind).toBe('cached-stale')
    expect(face.headline).toContain('已改版')
    expect(face.detail).toContain('差旅费报销制度-2026.pdf')
    expect(face.detail).toContain(formatMoment('2026-09-21T10:00:00Z'))
  })

  it('无从核对（这一轮没再交来源清单）是第四枚读数，不许并入「没改版」也不许并入「已改版」', () => {
    const face = cacheFace({ cached: true, generatedAt: '2026-09-21T09:00:00Z', note: '' }, null)
    expect(face.kind).toBe('cached-unknown')
    expect(face.detail).toContain('没有再交出来源清单')
    expect(face.detail).not.toContain('没有新版本')
    expect(face.headline).not.toContain('已改版')
  })

  it('答案没带生成时间：缓存那句写「时间未知」，改版核对直接不成立', () => {
    const face = cacheFace({ cached: true, generatedAt: '', note: '' }, [])
    expect(face.headline).toContain('生成时间未知')
    expect(revisionsAfter('', [{ created_at: '2026-09-21T10:00:00Z', version: 2 }])).toBe(null)
  })
})

describe('D · 改版核对：查不动就说查不动，不许顺手当成「没改版」', () => {
  const versions = [
    { version: 3, created_at: '2026-09-21T10:30:00Z' },
    { version: 2, created_at: '2026-09-21T09:30:00Z' },
    { version: 1, created_at: '2026-09-20T08:00:00Z' },
  ]

  it('只把晚于答案生成时间的版本算作改版，等号那一版不算', () => {
    const newer = revisionsAfter('2026-09-21T09:30:00Z', versions)
    expect(newer.map(item => item.version)).toEqual([3])
  })

  it('全在生成时间之前 → 空数组（这才叫「查过了，没改版」）', () => {
    expect(revisionsAfter('2026-09-22T00:00:00Z', versions)).toEqual([])
  })

  it('压根没拿到数组 ≠ 拿到了空数组：前者 null（没查成），后者才是没改版', () => {
    expect(revisionsAfter('2026-09-21T09:30:00Z', undefined)).toBe(null)
    expect(revisionsAfter('2026-09-21T09:30:00Z', {})).toBe(null)
  })

  it('有一版读不出时间就整体作废：跳过它继续算等于把「查不动」说成「没改版」', () => {
    expect(revisionsAfter('2026-09-21T09:30:00Z', [{ version: 4 }, ...versions])).toBe(null)
    expect(versionMoment({ version: 4 })).toBe('')
  })

  it('只认真源那一列 created_at，不替后端发明的时间键一律当读不到', () => {
    expect(versionMoment({ uploaded_at: '2026-09-21T10:00:00Z' })).toBe('')
    expect(formatMoment('不是时间')).toBe('')
    expect(formatMoment('')).toBe('')
  })
})

describe('E · 排队那张脸：三态与失败态各说各的', () => {
  it('没排队这一轮就没有这句话（idle 是空句，不是「未排队」的错误提示）', () => {
    expect(queueFace(null).kind).toBe('idle')
    expect(queueFace(null).headline).toBe('')
  })

  it('位次 3 说的是「前面还有 2 人」，不是「排在你后面」也不是「队列已满」', () => {
    const face = queueFace({ status: 'queued', position: 3 })
    expect(face.kind).toBe('queued')
    expect(face.ahead).toBe(2)
    expect(face.headline).toContain('2')
    expect(face.headline).not.toContain('已满')
  })

  it('位次读不到就明说读不到：不补 0，也不按等待人数编一个位次', () => {
    const face = queueFace({ status: 'queued', position: null })
    expect(face.ahead).toBe(null)
    expect(face.headline).toContain('读不到')
    expect(face.headline).not.toMatch(/[0-9]/)
  })

  it('队列很长也不许界面自己宣布「已满」：今天后端没有队列上限读数', () => {
    const face = queueFace({ status: 'queued', position: 4000 })
    expect(face.headline).toContain('3999')
    expect(face.headline).not.toContain('满')
    expect(face.detail).not.toContain('满')
  })

  it('processing / done / cancelled / expired 四态四句，一句「出错了」都不许复用', () => {
    const heads = [
      queueFace({ status: 'processing' }).headline,
      queueFace({ status: 'done', result: '答案正文' }).headline,
      queueFace({ status: 'cancelled' }).headline,
      queueFace({ status: 'expired' }).headline,
    ]
    expect(new Set(heads).size).toBe(4)
    for (const line of heads) expect(line).not.toBe('出错了')
  })

  it('done 但 result 是空的：单独一态，不许借 done 宣布界面上有答案', () => {
    expect(queueFace({ status: 'done', result: '' }).kind).toBe('done-no-result')
    expect(queueFace({ status: 'done', result: null }).headline).toContain('没带回答案')
    expect(queueFace({ status: 'done', result: '正文' }).headline).toContain('读数')
  })

  it('failed 带尝试次数与归类后的原因，不带一句空泛的失败', () => {
    const face = queueFace({ status: 'failed', failure: { attempts: 3, max_attempts: 3, last_error: 'task_timeout' } })
    expect(face.kind).toBe('failed')
    expect(face.detail).toContain('3/3')
    expect(face.tone).toBe('danger')
  })

  it('过期那句把「worker 没起来」这条下一步说给管理员，不只是让用户重问', () => {
    const face = queueFace({ status: 'expired' })
    expect(face.detail).toContain('管理员')
  })

  it('全局等待人数只补一句现状，读不到就整句不出现', () => {
    expect(queueStatsFace({ queue_length: 2, processing: 1 }).headline).toContain('等待 2')
    expect(queueStatsFace({})).toBe(null)
    expect(queueStatsFace(null)).toBe(null)
  })
})

describe('F · 入队被拒与轮询失败：两句都是人话，且都不叫「排队中」', () => {
  it('归一成品直接进账：错误码小字不因二次归一而静默消失（守卫存在的全部理由）', () => {
    const product = normalizeError({ status: 503, detail: 'brand_new_backend_code' })
    expect(errorCodeLabel(product)).toContain('brand_new_backend_code')
    const face = queueRejectedFace(product)
    expect(face.kind).toBe('rejected')
    expect(face.detail).toBe(product.message)
    expect(face.codeLabel).toBe(errorCodeLabel(product))
    // 反证留档：没有守卫时这里会把 rawCode 洗成空串，小字整条消失 —— 见回执反证 V-4。
    expect(errorCodeLabel(normalizeError(product))).toBe('')
  })

  it('还没归一的原料也吃得：{code,message} 对象不许渲染成 [object Object]', () => {
    const face = queueRejectedFace({ status: 503, detail: { code: 'queue_unavailable', message: '排队系统当前不可用。' } })
    expect(face.detail).not.toContain('[object Object]')
    expect(face.detail).toContain('排队')
    expect(face.kind).toBe('rejected')
  })

  it('轮询失败是「这次没读到」，既不宣布排队中也不宣布失败', () => {
    const face = queuePollFailedFace({ status: 500, detail: 'internal_error' })
    expect(face.kind).toBe('unreadable')
    expect(face.headline).toContain('没读到')
    expect(face.headline).not.toContain('前面还有')
    expect(face.detail).toContain('3 秒')
  })
})
