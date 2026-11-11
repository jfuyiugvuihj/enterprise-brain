/*
 * R291 · 后端原文的渲染出口（判据②到屏 / 判据③越权不显示 / 判据④既有脸不变）
 *
 * 环境仍然是 node + @vue/server-renderer（本仓没有 jsdom，也不许 npm i）：
 * 断言分两截，各管各的事，不假装验过自己验不了的。
 *   甲 数据出口：真跑 lib/artifacts.js 的失败路（只把 lib/http 打成桩），钉后端原文
 *     确实跟着重建的 Error 出了门 —— 那两格过去在这道消费口被丢掉，是 R291 的病因。
 *   乙 渲染出口：把甲那一发的真 Error 原样喂给 UiErrorState，SSR 出真产物，
 *     钉「屏幕上找得到后端原话、且逐字相同」与「没有原文时那张脸一个字节都没变」。
 *   丙 判据③专件：鉴权 / 越权 / 密级那一族，后端原话一个字都不许上屏，
 *     也不许前端编一句「后端没有提供原文」来填空。
 *   丁 口径唯一：详情区的判断只在 error-detail.js 一处，rawMessage 的读点全仓可数。
 *
 * 反证怎么算红（回执里逐把报读数）：
 *   V-1 摘掉 artifacts.js 里那行 attachRawText 调用  ⇒ 甲组第一钉与乙组到屏钉同时红；
 *   V-2 把 error-detail.js 的 REFUSED_CODES/STATUSES 清空 ⇒ 丙组逐码红；
 *   V-3 摘掉「同字不重复」那一条               ⇒ 乙组未知码钉红；
 *   V-4 摘掉 GARBAGE 守卫                       ⇒ 乙组 [object Object] 钉红；
 *   V-5 把模板里的 v-if=\"rawDetail\" 改成常渲染    ⇒ 乙组「今天那张脸逐字节不变」红。
 */
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'

const { httpGet } = vi.hoisted(() => ({ httpGet: vi.fn() }))
vi.mock('../../lib/http', () => ({ http: { get: httpGet } }))

const { fetchArtifactBlob } = await import('../../lib/artifacts.js')
const { normalizeError, errorCodeLabel, ERROR_CODES } = await import('../../lib/errcodes.js')
const UiErrorState = (await import('../ui/UiErrorState.vue')).default
const primitives = await import('../ui')
const { rawDetailOf } = primitives

const SRC_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')

/* ============================ 共同夹具 ============================ */

/** 后端信封里那一格原话：形状 2（ErrorEnvelope），下载与预览的 blob 体用的是 error_code */
const BACKEND_ZH = '工作簿受密码保护，无法读取。'
/** 契约 docs/api/contract-v1.md:157-163 的示例原句：403 的 permission_denied 带的就是这种英文 */
const BACKEND_EN = 'resource access is not permitted'

/** 把一次取图打成失败：body 给字符串，打成 blob 与真链路同形状 */
const failWith = (status, body) => {
  httpGet.mockReset()
  httpGet.mockRejectedValue({
    response: { status, data: body instanceof Blob ? body : new Blob([body], { type: 'application/json' }) },
  })
}
const grabArtifactError = async () => {
  try {
    await fetchArtifactBlob('/static/chart-1.png')
  } catch (err) {
    return err
  }
  throw new Error('这条用例本来就该抛出错误')
}

const render = props => renderToString(h(UiErrorState, props))
const countIn = (hay, needle) => hay.split(needle).length - 1
const DETAIL_BLOCK = 'ui-error-state__detail'
const RAW_ATTR = 'data-testid="ui-error-state-raw"'
const RAW_ELEMENT_RE = /<p class="ui-error-state__detail-text"([^>]*)>([^<]*)<\/p>/

/* ============================ 甲 · 数据出口 ============================ */

describe('甲 · artifacts.js 不再把后端原文丢在重建 Error 的当场（R291 判据②前半）', () => {
  it('信封里的原话与原始码名跟着 Error 出门，人话位仍归字典', async () => {
    failWith(400, JSON.stringify({ detail: { error_code: 'parse_failed', message: BACKEND_ZH, retryable: false } }))
    const err = await grabArtifactError()
    expect(err.rawMessage, '后端原话在这一发被丢掉了').toBe(BACKEND_ZH)
    expect(err.rawCode).toBe('parse_failed')
    // 加法语义：既有四格一字未动，R281 判据①「信封 message 不占人话位」仍然成立
    expect(err.message).toBe(ERROR_CODES.parse_failed.message)
    expect(err.status).toBe(400)
    expect(err.code).toBe('parse_failed')
    expect(err.retryable).toBe(false)
  })

  it('没有信封 message 那一发不硬造一格（形状 1 裸码名 / 传输层 / 取消）', async () => {
    failWith(403, '{"detail":"permission_denied"}')
    const bare = await grabArtifactError()
    expect('rawMessage' in bare).toBe(false)
    expect('rawCode' in bare).toBe(false)

    httpGet.mockReset()
    httpGet.mockRejectedValue({ code: 'ERR_NETWORK', request: {}, message: 'Network Error' })
    const transport = await grabArtifactError()
    expect('rawMessage' in transport).toBe(false)

    httpGet.mockReset()
    httpGet.mockRejectedValue({ name: 'CanceledError', code: 'ERR_CANCELED' })
    const cancelled = await grabArtifactError()
    expect(cancelled.code).toBe('aborted')
    expect('rawMessage' in cancelled).toBe(false)
  })

  it('非 JSON 错误体不产出原文：网关 HTML 仍按状态归类', async () => {
    failWith(502, new Blob(['<html><body>502 Bad Gateway</body></html>'], { type: 'text/html' }))
    const err = await grabArtifactError()
    expect(err.rawMessage).toBeUndefined()
    expect(err.message).not.toContain('502 Bad Gateway')
  })
})

/* ============================ 乙 · 渲染出口 ============================ */

describe('乙 · UiErrorState 详情区让后端原文真的到屏（判据②）', () => {
  it('甲组那一发的真 Error 喂进来，屏幕上逐字找得到后端原话', async () => {
    failWith(400, JSON.stringify({ detail: { error_code: 'parse_failed', message: BACKEND_ZH } }))
    const err = await grabArtifactError()
    const html = await render({ title: '这份文件没能读进来', description: err.message, rawError: err })
    expect(html, '后端原话仍然上不了屏：详情区没有渲染').toContain(BACKEND_ZH)
    expect(html).toContain(DETAIL_BLOCK)
    expect(html).toContain(RAW_ATTR)
    const hit = RAW_ELEMENT_RE.exec(html)
    expect(hit, '承载原文的元素形状不认识').not.toBeNull()
    expect(hit[2], '原文被前端加了前缀或改字，贴给运维就不是逐字了').toBe(BACKEND_ZH)
    expect(hit[1]).toContain('data-testid')
    expect(hit[2]).not.toContain('data-testid')
    // 人话位没有被顶掉：字典那句还在，两句话一处一个位
    expect(html).toContain(ERROR_CODES.parse_failed.message)
  })

  it('没有原文时那张脸逐字节等于今天（不出现空串位）', async () => {
    failWith(403, '{"detail":"permission_denied"}')
    const denied = await grabArtifactError()
    const today = await render({ title: '这张图没能打开', description: denied.message, codeLabel: errorCodeLabel(denied) })
    const wired = await render({ title: '这张图没能打开', description: denied.message, codeLabel: errorCodeLabel(denied), rawError: denied })
    expect(wired).toBe(today)
    expect(wired).not.toContain(DETAIL_BLOCK)
  })

  it('空串 / undefined / [object Object] / 裸字符串都不配上屏', async () => {
    const garbage = [
      null,
      undefined,
      '',
      '   ',
      {},
      [],
      'permission_denied',
      { rawMessage: '' },
      { rawMessage: 'undefined' },
      { rawMessage: '[object Object]' },
      { rawMessage: '(NaN)' },
      { rawMessage: 42 },
      new Error('取图失败'),
    ]
    for (const source of garbage) {
      const html = await render({ description: '这张图没能打开', rawError: source })
      const label = JSON.stringify(source) || String(source)
      expect(html, label + ' 不该长出详情区').not.toContain(DETAIL_BLOCK)
      expect(html).not.toContain('[object Object]')
      expect(html).not.toContain('undefined')
    }
  })

  it('人话与原文同字（未知码那一档）时不画第二遍', async () => {
    const source = { response: { status: 400, data: { detail: { code: 'brand_new_backend_code', message: '导出列名不能为空' } } } }
    const result = normalizeError(source)
    expect(result.message).toBe('导出列名不能为空')
    expect(result.rawMessage).toBe('导出列名不能为空')
    const html = await render({ description: result.message, codeLabel: errorCodeLabel(result), rawError: result })
    expect(html, '同一句话开了两个出口').not.toContain(DETAIL_BLOCK)
    expect(countIn(html, '导出列名不能为空'), '未知码那句后端原文仍该在屏上，只不过只一次').toBe(1)
    expect(html).toContain('错误码：brand_new_backend_code')
  })

  it('详情区不替 rawCode 开第二条出口：在册别名既不出小字也不出原文', async () => {
    const source = { response: { status: 403, data: { detail: { code: 'department_override_denied', message: BACKEND_EN } } } }
    const result = normalizeError(source)
    const html = await render({ description: result.message, codeLabel: errorCodeLabel(result), rawError: result })
    expect(html).not.toContain('错误码：department_override_denied')
    expect(html).not.toContain(BACKEND_EN)
    expect(html).not.toContain(DETAIL_BLOCK)
    expect(errorCodeLabel(result), 'R281 判据①那条小字的口径没被我放宽').toBe('')
  })

  it('只多传一枚 rawError 就接得上：不依赖 description 与 codeLabel', async () => {
    failWith(413, JSON.stringify({ detail: { code: 'upload_too_large', message: '列宽超过 255，无法建档' } }))
    const err = await grabArtifactError()
    const html = await render({ rawError: err })
    expect(html).toContain('列宽超过 255，无法建档')
    expect(html).toContain(DETAIL_BLOCK)
  })
})

/* ============================ 丙 · 判据③专件 ============================ */

describe('丙 · 403 / 越权 / 密级那张脸不显示后端原文（判据③）', () => {
  const CASES = [
    ['permission_denied 契约示例原句', 403, { code: 'permission_denied', message: BACKEND_EN }, ERROR_CODES.permission_denied.message],
    ['密级不够', 403, { code: 'clearance_insufficient', message: 'clearance level 3 required for this document' }, '这份资料的安全等级高于你的可见级别，不能打开，请联系管理员。'],
    ['部门维度拒绝', 403, { code: 'department_scope_denied', message: 'department mismatch: finance vs hr' }, '这份资料属于其他部门的数据范围，当前账号看不到，请联系管理员授权。'],
    ['资源没登记部门或密级', 403, { code: 'resource_scope_missing', message: 'resource has no department registered' }, '这份资料没有登记所属部门或密级，系统判断不了你能不能看，请联系管理员补齐登记。'],
    ['替别人报部门被拒（R281 现场那一发）', 403, { code: 'department_override_denied', message: 'requested department does not match principal department' }, '请求里写的部门不是你这个账号所属的部门，这次没有执行。'],
    ['账号停用', 403, { code: 'principal_inactive', message: 'principal is inactive' }, '这个账号已被停用，请联系管理员恢复后再使用。'],
    ['行级全部不可见', 403, { code: 'row_scope_denied', message: 'all 3 rows are outside your scope' }, ERROR_CODES.row_scope_denied.message],
    ['后端刻意不说为什么的那一枚', 403, { code: 'no_visible_rows', message: 'department filter hid everything' }, ERROR_CODES.no_visible_rows.message],
    ['登录失效', 401, { code: 'authentication_required', message: 'token expired' }, ERROR_CODES.authentication_required.message],
    ['403 加一枚字典收不下的码', 403, { code: 'mystery_denial', message: 'denied by policy engine' }, null],
  ]

  CASES.forEach(([label, status, detail, expectedHuman]) => {
    it(label + '：后端原话不再多一条出口，前端也不替它编一句', async () => {
      const source = { response: { status, data: { detail } } }
      const result = normalizeError(source)
      expect(result.rawMessage, '夹具失效：这一发本来就没有原文，测不出拦截').toBeTruthy()
      const plain = await render({ description: result.message, codeLabel: errorCodeLabel(result) })
      const wired = await render({ description: result.message, codeLabel: errorCodeLabel(result), rawError: source })
      expect(wired, '加了 rawError 之后脸变了').toBe(plain)
      expect(wired).not.toContain(DETAIL_BLOCK)
      for (const needle of ['技术信息', '后端原话', '未提供', '没有原文']) {
        expect(wired, needle + '：沉默被填成了前端自己的一句话').not.toContain(needle)
      }
      /**
       * 去重不变量：字典有话说时（expectedHuman 给了句子），后端原话在屏上出现 0 次；
       * 字典收不下那一枚码时（R281 判据③刻意留的那一档），后端那句本来就占着人话位，
       * 屏上出现且仅出现 1 次 —— 详情区绝不把它变成第二条出口。
       */
      const onScreen = expectedHuman === null ? 1 : 0
      expect(countIn(wired, result.rawMessage), '后端原文在这张脸上漏了 ' + result.rawMessage).toBe(onScreen)
      if (expectedHuman !== null) expect(wired).toContain(expectedHuman)
    })
  })

  /**
   * 三条腿各自有牙：只带状态的那一发考 status，只带码名/原因码的那一发考两张名单。
   * 真实世界里有一批失败**压根没有 HTTP 状态可读** —— SSE 的 request.failed 只带 error_code
   * （docs/api/contract-v1.md:1213），面板与 lib 也会把 normalizeError 的成品 result 递进来
   * （lib/sessions.js 走的就是这条），那个形状里没有 status 这一格。名单漏一枚就漏一句原文。
   */
  const STATUS_FREE = [
    ['枚举码 permission_denied', { code: 'permission_denied', message: 'resource access is not permitted' }],
    ['枚举码 authorization_unavailable', { code: 'authorization_unavailable', message: 'scope cannot be resolved' }],
    ['枚举码 account_unavailable', { code: 'account_unavailable', message: 'principal is inactive' }],
    ['枚举码 authentication_required', { code: 'authentication_required', message: 'token could not be verified' }],
    ['枚举码 row_scope_denied', { code: 'row_scope_denied', message: 'all rows are outside visibility' }],
    ['枚举码 no_visible_rows', { code: 'no_visible_rows', message: 'the department dimension hid them' }],
    ['原因码 department_override_denied', { code: 'department_override_denied', message: 'requested department does not match' }],
    ['原因码 clearance_insufficient（密级）', { code: 'clearance_insufficient', message: 'clearance level 3 required' }],
    ['原因码 department_scope_denied', { code: 'department_scope_denied', message: 'department mismatch: finance vs hr' }],
    ['原因码 resource_scope_missing', { code: 'resource_scope_missing', message: 'no department registered on resource' }],
    ['原因码 resource_scope_invalid', { code: 'resource_scope_invalid', message: 'malformed scope entry' }],
    ['原因码 principal_inactive', { code: 'principal_inactive', message: 'principal status is disabled' }],
  ]

  STATUS_FREE.forEach(([label, envelope]) => {
    it(label + '（这一发没有 HTTP 状态可读）：名单这条腿单独也拦得住', async () => {
      const result = normalizeError(envelope)
      expect(result.rawMessage, '夹具失效：这一发本来就没有原文，测不出拦截').toBeTruthy()
      const plain = await render({ description: result.message })
      const wired = await render({ description: result.message, rawError: result })
      expect(wired).toBe(plain)
      expect(wired).not.toContain(DETAIL_BLOCK)
      expect(wired, '后端原文从详情区漏上屏').not.toContain(result.rawMessage)
      expect(wired).toContain(result.message)
    })
  })

  it('只有状态能拦住的那一发：403 加一枚折向非拒绝枚举的码', async () => {
    // 形状：面板把带 status 的成品递进来，code 归到 validation_error（名单外），原话照实带回
    const source = { code: 'validation_error', rawCode: 'brand_new_denial', status: 403, message: ERROR_CODES.validation_error.message, rawMessage: 'denied by the new dimension' }
    expect(rawDetailOf(source)).toBe('', '状态这条腿没拦住，名单之外的新拒绝码会漏原文')
    const html = await render({ description: source.message, rawError: source })
    expect(html).not.toContain(DETAIL_BLOCK)
    expect(html).not.toContain('denied by the new dimension')
  })

  it('同一枚越权原文经 artifacts.js 出门也一样拦住（走的是 Error 上那两格，不是复算）', async () => {
    failWith(403, JSON.stringify({ detail: { code: 'clearance_insufficient', message: 'clearance level 3 required' } }))
    const err = await grabArtifactError()
    expect(err.rawMessage).toBe('clearance level 3 required')
    const html = await render({ description: err.message, rawError: err })
    expect(html).not.toContain(DETAIL_BLOCK)
    expect(html).not.toContain('clearance level 3 required')
  })

  it('后端回在 details 里的内部结构不进详情区：只认信封 message 那一格', async () => {
    const source = {
      response: { status: 400, data: { detail: { code: 'parse_failed', message: '这一页 OCR 没跑成', details: { trace: 'SELECT * FROM secrets', sql: 'DROP TABLE' } } } },
    }
    const result = normalizeError(source)
    const html = await render({ description: result.message, rawError: source })
    expect(html).toContain('这一页 OCR 没跑成')
    expect(html).not.toContain('SELECT')
    expect(html).not.toContain('DROP TABLE')
  })
})

/* ============================ 丁 · 口径唯一 ============================ */

describe('丁 · 判断只有一处，渲染出口只有一条', () => {
  it('rawDetailOf 在 barrel 上，且原语内部用的就是它（同一入参同一读数）', async () => {
    expect(typeof primitives.rawDetailOf).toBe('function')
    const shown = ERROR_CODES.index_publish_failed.message
    const sources = [
      { rawMessage: '索引发布失败：分片 3/7 超时', code: 'index_publish_failed', rawCode: 'index_publish_failed', status: 500 },
      { response: { status: 400, data: { detail: { code: 'parse_failed', message: BACKEND_ZH } } } },
      { response: { status: 403, data: { detail: { code: 'permission_denied', message: BACKEND_EN } } } },
      null,
      'permission_denied',
    ]
    for (const source of sources) {
      const expected = rawDetailOf(source, { shown })
      const html = await render({ description: shown, rawError: source })
      expect(html.includes(DETAIL_BLOCK), '详情区长不长，与 rawDetailOf 的读数必须一致').toBe(Boolean(expected))
      if (!expected) continue
      const hit = RAW_ELEMENT_RE.exec(html)
      expect(hit).not.toBeNull()
      expect(hit[2], '原语画出去的与 rawDetailOf 判的不是同一句').toBe(expected)
    }
  })

  it('全仓读 .rawMessage 的非测试件只有三枚：字典产出、artifacts 搬运、error-detail 裁定', () => {
    const readers = []
    const walk = dir => {
      for (const entry of readdirSync(join(SRC_ROOT, dir), { withFileTypes: true })) {
        const rel = join(dir, entry.name)
        if (entry.isDirectory()) {
          if (entry.name !== '__tests__' && entry.name !== 'node_modules') walk(rel)
          continue
        }
        if (!/\.(js|vue)$/.test(entry.name) || /\.(test|spec)\.js$/.test(entry.name)) continue
        const text = readFileSync(join(SRC_ROOT, rel), 'utf8').replace(/\r\n/g, '\n')
        const hits = text.split('\n').filter(line => /rawMessage/.test(line) && !/^\s*(\/\/|\*|\/\*)/.test(line))
        if (hits.length) readers.push({ file: rel.split(sep).join('/'), count: hits.length })
      }
    }
    walk('.')
    expect(readers.map(row => row.file).sort()).toEqual([
      'components/ui/error-detail.js',
      'lib/artifacts.js',
      'lib/errcodes.js',
    ])
  })

  it('原语的默认脸没被换：不传 rawError 时屏上只有人话与（未知码的）小字', async () => {
    const html = await render({ description: '文件已收到，但没能进入知识库。', codeLabel: '错误码：odd_download_code' })
    expect(html).not.toContain(DETAIL_BLOCK)
    expect(html).toContain('文件已收到，但没能进入知识库。')
    expect(html).toContain('错误码：odd_download_code')
  })
})
