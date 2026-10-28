import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../http', async importOriginal => {
  const actual = await importOriginal()
  return { ...actual, http: { post: vi.fn() } }
})

import { http } from '../http'
import {
  createRule,
  checkOutcomeView,
  emptyRuleForm,
  mapAlertRow,
  mapRuleRow,
  ruleRequestBody,
  validateRuleForm,
  versionPolicyLabel,
} from '../alerts'

const validRule = overrides => ({
  name: '收入预警', metric: '收入', op: 'gt', threshold: '100',
  versionPolicy: 'fixed', dataFilename: '销售明细.csv', expectedVersionId: 'version-7',
  ...overrides,
})

beforeEach(() => http.post.mockReset())

describe('告警规则的数据版本策略', () => {
  it('负责人失去权限时，未判断回执点名规则而不显示undefined文件名', () => {
    const view = checkOutcomeView({ triggered: [], scan_scope: { evaluation_failures: [
      { rule_id: 17, reason: '规则负责人当前没有告警管理权限，未判断' },
    ] } })
    expect(view.kind).toBe('unknown')
    expect(view.detail).toContain('规则 #17')
    expect(view.detail).not.toContain('undefined')
  })
  it('新建表单默认固定版本；固定策略必须选文件，跟随最新版可留空', () => {
    expect(emptyRuleForm()).toMatchObject({ versionPolicy: 'fixed', dataFilename: '' })
    expect(validateRuleForm(validRule()).ok).toBe(true)
    expect(validateRuleForm(validRule({ dataFilename: '' })).errors.dataFilename).toBeTruthy()
    expect(validateRuleForm(validRule({ versionPolicy: 'follow_latest', dataFilename: '' })).ok).toBe(true)
    expect(validateRuleForm(validRule({ versionPolicy: 'surprise' })).errors.versionPolicy).toBeTruthy()
  })

  it('序列化固定策略时发送页面所见版本；跟随最新发策略但不带 pin', async () => {
    http.post.mockResolvedValue({ data: { id: 1 } })
    await createRule(validRule())
    expect(http.post).toHaveBeenLastCalledWith('/alerts/rules', expect.objectContaining({
      data_filename: '销售明细.csv', version_policy: 'fixed', expected_version_id: 'version-7',
    }))

    await createRule(validRule({ versionPolicy: 'follow_latest', expectedVersionId: 'stale-version' }))
    expect(http.post).toHaveBeenLastCalledWith('/alerts/rules', expect.objectContaining({
      data_filename: '销售明细.csv', version_policy: 'follow_latest',
    }))
    expect(http.post.mock.calls[1][1]).not.toHaveProperty('expected_version_id')
  })

  it('不带新策略的旧请求体保持原形，规则行策略标签按已知与未知值展示', () => {
    expect(ruleRequestBody({ name: '旧规则', metric: '金额', op: 'lt', threshold: '5' }))
      .not.toHaveProperty('version_policy')
    expect(mapRuleRow({ options: { version_policy: 'fixed', version_id: 'v-9' } }).versionPolicyText)
      .toBe('固定版本 · v-9')
    expect(mapRuleRow({ options: { version_policy: 'follow_latest' } }).versionPolicyText).toBe('跟随最新版')
    expect(mapRuleRow({ options: {} }).versionPolicyText).toBe('跟随最新版（已有规则）')
    expect(mapRuleRow({ options: { version_policy: 'future' } }).versionPolicyText).toBe('无法识别的数据版本策略')
    expect(versionPolicyLabel('fixed')).toBe('固定版本 · 未记录版本 ID')
    expect(mapAlertRow({ evidence: { version_policy: 'follow_latest' } }).evidence.versionPolicyText)
      .toBe('跟随最新版')
  })
})
