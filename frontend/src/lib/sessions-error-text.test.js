/**
 * A-4-3 · friendlyErrorText 改吃 errcodes 之后的行为对账
 *
 * 这里逐条钉的是"合并前后各形状的输出"，因为改的是用户会读到的一句话：
 * 语义不许降级（原先五句私有字典都在说清是什么坏了），裸码名不许再上屏。
 * 前缀 [错误] 是线上既成形状（app/api/v1/chat.py:729、:1101 也这么写），一并钉住别被顺手改掉。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { friendlyErrorText } from './sessions.js'

const BARE_CODE = /\b[a-z][a-z0-9]*(_[a-z0-9]+)+\b/
const text = (state, fallback) => friendlyErrorText(state, fallback)

describe('A-4-3 · 私有码表已删除，句子出自唯一字典', () => {
  const s = readFileSync(new URL('./sessions.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n')

  it('G2 那条 TODO 与第二份码表一起没了，只剩一条 formatError 通道', () => {
    expect(s).not.toMatch(/const codes = \{/)
    expect(s).not.toContain('TODO(B 线')
    expect(s.match(/formatError\(\{ detail:/g)).toHaveLength(2)
    expect(s).toContain("import { formatError } from './errcodes'")
  })

  it('未知码不再把码本身当句子直出（老实现第 384 行就是 return `[错误] ${state.errorCode}`）', () => {
    expect(s).not.toMatch(/\[\u9519\u8bef\] \$\{state\.errorCode\}/)
    expect(s).not.toMatch(/\[\u9519\u8bef\] \$\{state\.errorText\}/)
  })

  it('前缀 [错误] 保留，与后端写进气泡的失败行同一形状', () => {
    expect(text({ errorCode: 'internal_error' }).startsWith('[错误] ')).toBe(true)
    expect(text({}).startsWith('[错误] ')).toBe(true)
  })
})

describe('A-4-3 · 五句私有文案的语义逐条对账', () => {
  const cases = [
    ['no_answer_produced', '未产出'],
    ['task_timeout', '耗时过长'],
    ['internal_error', '内部'],
    ['authorization_unavailable', '部门'],
    ['authentication_required', '登录'],
  ]
  it.each(cases)('%s 仍说得出是什么坏了，且句子里没有裸码名', (code, keyword) => {
    const out = text({ errorCode: code })
    expect(out).toContain(keyword)
    expect(out).not.toContain(code)
    expect(BARE_CODE.test(out)).toBe(false)
  })

  it('未知码走兜底句 + 「错误码：xxx」诊断小字（同 UiErrorState 的 codeLabel 通道）', () => {
    const out = text({ errorCode: 'brand_new_code' })
    expect(out).toContain('错误码：brand_new_code')
    expect(out).not.toBe('[错误] brand_new_code')
  })
})

describe('A-4-3 · 后端自由文本不再原样上屏', () => {
  it('句子里夹带的码名会被摘掉，换成字典句', () => {
    const out = text({ errorText: '本轮未产出任何结论（no_answer_produced），请重试或补充数据范围。' })
    expect(BARE_CODE.test(out)).toBe(false)
    expect(out).toContain('未产出')
  })

  it('网关 HTML 不当人话抛给界面', () => {
    const out = text({ errorText: '<html><body>502 Bad Gateway</body></html>' })
    expect(out).not.toContain('502')
    expect(out).not.toContain('<html')
  })

  it('后端说的人话照旧直出，不为了锁码把信息量砍成一句空话', () => {
    expect(text({ errorText: '用户名或密码错误' })).toBe('[错误] 用户名或密码错误')
  })

  it('码与文本同时在场时以码为准（机器字段优先），句子仍是字典那句', () => {
    expect(text({ errorCode: 'task_timeout', errorText: '后端原文' })).toContain('耗时过长')
  })

  it('什么都没有时用调用方给的场景文案', () => {
    expect(text({})).toBe('[错误] 本轮回答未能完成')
    expect(text({}, '待确认动作执行失败')).toBe('[错误] 待确认动作执行失败')
  })
})