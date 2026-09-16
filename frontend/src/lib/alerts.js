/**
 * 异常与告警链路的唯一取数点与「判脸」点（W7 · R1 裁定 (c) 的前端半边）
 *
 * 背景与不变量：
 *  ① 后端零改动。app/api/v1/alerts.py 的五个端点（GET /alerts、GET/POST/DELETE /alerts/rules、
 *     POST /alerts/check）全部过 ACTION_MANAGE_ALERTS 判定，staff 与 auditor 的角色集里
 *     没有这一项（app/common/permissions.py:13/:16），manager 与 admin 有（:14/:15）。
 *     所以员工账号在这一页拿到的是 403，不是空数组。
 *  ② 「无权限」与「空列表」必须是两张脸（看板 §4F.5 裁定 (c)）。空列表是 200 响应，
 *     压根走不到失败判定；403 是失败，永远不许被降级成「当前没有触发中的告警」。
 *     同理，401（登录失效）与 500 / 结构不对（服务坏了）也是各自独立的脸。
 *  ③ 文案只出自 lib/errcodes.js 的字典（resolveCode 的公开通道：normalizeError 与 errorText）。
 *     后端码名不进正文，未知码走 errorCodeLabel 的「错误码：xxx」小字通道。
 *
 * 这里不放任何演示常量：洞察页原先的手填阈值表单加 devFixtures 三行假数据，把「待关注」
 * 说成了真实异常。W7 起这条链路只认服务端回来的行。
 */
import { errorCodeLabel, errorCodeOf, errorText } from './errcodes'
import { errorDetail, http } from './http'

/** 三条固定路径。列表与规则各自只有一条取数路径，不许在面板里再拼一遍。 */
export const ALERTS_PATH = '/alerts'
export const RULES_PATH = '/alerts/rules'
export const CHECK_PATH = '/alerts/check'

/** DELETE /alerts/rules/{rule_id}：后端路径参数是 int，非数字直接不给发请求。 */
export function rulePath(ruleId) {
  const raw = String(ruleId === null || ruleId === undefined ? '' : ruleId).trim()
  if (!/^\d+$/.test(raw)) return ''
  return RULES_PATH + '/' + encodeURIComponent(raw)
}

/**
 * 比较符只列后端 OPS 认得的四个（app/api/v1/alerts.py 的 OPS 字典）。
 * 界面多给一档后端不认的比较方式，POST 就直接 400，所以这里必须是全集。
 */
export const RULE_OPERATORS = [
  { value: 'gt', label: '大于' },
  { value: 'gte', label: '大于等于' },
  { value: 'lt', label: '小于' },
  { value: 'lte', label: '小于等于' },
]

/** 后端回来的比较符 -> 中文。认不下就说认不下，绝不把原串画上屏。 */
export function operatorLabel(op) {
  const key = typeof op === 'string' ? op.trim() : ''
  const found = RULE_OPERATORS.find(item => item.value === key)
  return found ? found.label : '无法识别的比较方式'
}

/** 新增规则的表单初值：四格全空。预填示例值会和真数据混在同一屏里（V7-1 的教训）。 */
export function emptyRuleForm() {
  return { name: '', metric: '', op: 'lt', threshold: '' }
}

/**
 * 阈值格的唯一读法：留空读成 NaN，而不是静悄悄的 0。
 * Number('') 与 Number(' ') 都等于 0，只查 isFinite 会把「操作员没填」变成一条
 * 「小于 0」的真规则写进后端告警表——那是数据造假，不是体验问题。
 */
function thresholdValue(raw) {
  const text = String(raw === null || raw === undefined ? '' : raw).trim()
  return text === '' ? NaN : Number(text)
}

/**
 * 提交前的最小校验。后端 RuleCreate 只校验 op 是否在 OPS 内：阈值写成空串会被
 * pydantic 判 422，规则名留空则直接落一条看不懂的规则——能在这儿拦住的先在这儿拦住。
 * 阈值这一格比后端多拦一道：空串落到 Number() 是 0，放行就是静默写出一条「小于 0」的真规则。
 */
export function validateRuleForm(form) {
  const source = form && typeof form === 'object' ? form : {}
  const errors = {}
  if (!String(source.name || '').trim()) errors.name = '请填写规则名称'
  if (!String(source.metric || '').trim()) errors.metric = '请填写要盯的指标列名'
  if (!Number.isFinite(thresholdValue(source.threshold))) errors.threshold = '阈值必须是一个数字'
  if (!RULE_OPERATORS.some(item => item.value === source.op)) errors.op = '请选择比较方式'
  return { ok: Object.keys(errors).length === 0, errors }
}

/** 表单 -> 请求体。metric 是经营数据里的列名，后端按它对每个数据文件取合计再比较。 */
export function ruleRequestBody(form) {
  const source = form && typeof form === 'object' ? form : {}
  return {
    name: String(source.name || '').trim(),
    metric: String(source.metric || '').trim(),
    op: RULE_OPERATORS.some(item => item.value === source.op) ? source.op : 'lt',
    threshold: thresholdValue(source.threshold),
  }
}

/**
 * 一次读取的结果该画哪张脸，全仓只有这一个出口。
 * failed 必须显式传：连不上服务时归不出码（code 是空串），只看码就会把「服务坏了」
 * 当成「200 空列表」，正是 R1(c) 要拆的那条缝。
 */
export function faceOf({ loading = false, failed = false, code = '', rowCount = 0 } = {}) {
  if (loading) return 'loading'
  if (failed) {
    if (code === 'authentication_required') return 'unauthorized'
    if (code === 'permission_denied') return 'denied'
    return 'error'
  }
  return Number(rowCount) > 0 ? 'list' : 'empty'
}

/** 403 之后必须指出下一步去哪：少了这一句，无权限卡就是一句死路。 */
export const PERMISSION_WHERE = '查看告警、维护规则与手动巡检走的是同一项权限，员工账号默认没有这一项。'
  + '请让企业管理员在账号权限里放开告警管理，再回到这一页重新加载；重新登录本身不会让这项权限出现。'

export const ALERTS_EMPTY_TITLE = '当前没有触发中的告警'
export const ALERTS_EMPTY_DESCRIPTION = '这一屏读的是服务端告警表：规则命中时才会写入一条。'
  + '所以这里为空只说明目前没有命中记录，不等于业务一切正常，也不等于你的账号没有权限。'

export const RULES_EMPTY_TITLE = '还没有配置任何告警规则'
export const RULES_EMPTY_DESCRIPTION = '没有规则时巡检没有任何判定点，也就永远不会产生告警。先在下面加一条。'

export const SHAPE_FAILURE_DESCRIPTION = '服务端回来的数据结构不对，这一屏没能加载。'

/** 后端 GET /alerts 固定 LIMIT 100（app/api/v1/alerts.py）：取满就该说明「这里不是全部」。 */
export const ALERTS_FEED_LIMIT = 100
export const ALERTS_LIMIT_NOTE = '后端只回传最近 100 条告警，更早的记录不在这一屏。'

/**
 * 读取失败 -> UiErrorState 的入参。三档脸共用一个出口，差别全在字段里：
 *   unauthorized 登录失效：句子出自字典，重试没用（回登录由 lib/http.js 统一处理）
 *   denied      没权限：说清去哪申请，不给重试按钮
 *   error       真坏了：给「重新加载」
 */
export function readFailureView(err, { deniedTitle, failedTitle }) {
  const code = errorCodeOf(err)
  const face = faceOf({ failed: true, code })
  const label = errorCodeLabel(err)
  if (face === 'unauthorized') {
    return { face, title: '登录状态已失效', description: errorDetail(err, errorText(code)), codeLabel: '', retryable: false }
  }
  if (face === 'denied') {
    return { face, title: deniedTitle, description: errorDetail(err, errorText(code)) + PERMISSION_WHERE, codeLabel: label, retryable: false }
  }
  return { face, title: failedTitle, description: errorDetail(err, failedTitle), codeLabel: label, retryable: true }
}

/** 结构不对的失败：没有错误对象可归码，一律按「坏了」给重试，绝不画成空态。 */
export function shapeFailureView(failedTitle) {
  return { face: 'error', title: failedTitle, description: SHAPE_FAILURE_DESCRIPTION, codeLabel: '', retryable: true }
}

/** 列表体只认 alerts / rules 两个键下的数组；形状不对返回 null，交给失败态。 */
export function listRows(data, key) {
  const value = data && typeof data === 'object' ? data[key] : undefined
  return Array.isArray(value) ? value : null
}

/** 后端 created_at 是文本列（真库带 +08 偏移，内存模式是 ISO 串）：统一取到分钟，不做时区换算。 */
export function formatStamp(value) {
  const raw = typeof value === 'string' ? value.trim() : ''
  if (!raw) return ''
  const parts = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(raw)
  if (!parts) return raw.replace('T', ' ')
  return parts[1] + '-' + parts[2] + '-' + parts[3] + ' ' + parts[4] + ':' + parts[5]
}

/**
 * alerts 行（后端六列）-> 视图模型。后端字段名只在这一个函数里出现，模板里全是视图字段。
 * read 列刻意不显示：后端没有把它改成已读的端点，界面上放一个点不动的「标记已读」，
 * 或者摆一个永远不变的未读角，都比省略更糟。
 */
export function mapAlertRow(row) {
  const source = row && typeof row === 'object' ? row : {}
  const message = String(source.message || '').trim()
  return {
    id: String(source.id === null || source.id === undefined ? '' : source.id),
    ruleId: String(source.rule_id === null || source.rule_id === undefined ? '' : source.rule_id),
    message: message || '这条告警没有留下说明文字。',
    analysis: String(source.ai_analysis || '').trim(),
    createdAt: formatStamp(source.created_at),
  }
}

/** alert_rules 行 -> 视图模型。阈值缺失时给一句人话而不是 NaN。 */
export function mapRuleRow(row) {
  const source = row && typeof row === 'object' ? row : {}
  const threshold = Number(source.threshold)
  const metric = String(source.metric || '').trim()
  return {
    id: String(source.id === null || source.id === undefined ? '' : source.id),
    name: String(source.name || '').trim() || '未命名规则',
    metric,
    metricText: metric || '没有登记指标列',
    op: String(source.op || '').trim(),
    opLabel: operatorLabel(source.op),
    thresholdText: Number.isFinite(threshold) ? String(threshold) : '没有登记阈值',
    enabled: source.enabled !== false,
  }
}

/**
 * 删除规则的两步确认状态机，与产物列表的删除同一行为口径：一次错位的点击
 * 删不掉没点过的行。只有返回 execute 才真的发 DELETE。
 */
export function advanceRuleDelete(pendingId, targetId) {
  const target = String(targetId === null || targetId === undefined ? '' : targetId)
  if (!target) return 'idle'
  return String(pendingId) === target ? 'execute' : 'arm'
}

/**
 * POST /alerts/check 的回执。后端返回 triggered 数组与 scan_scope，scan_scope 会说明
 * 本轮到底读了几个文件、为什么没读。「读了三个文件都没命中」与「一个文件都没读到」
 * 是两句话，混成「没有异常」就是造假。
 */
export const SCAN_REASON_MESSAGES = {
  tenant_data_dir_unavailable: '服务端还没有配置可用的租户数据目录，本轮巡检没有任何数据可读。',
  no_data_files: '数据目录里没有可分析的数据文件，本轮巡检没有判定点。',
  no_permitted_datasets: '你的账号可见范围内没有可分析的数据文件，本轮巡检没有判定点。',
}

export function checkOutcomeView(data) {
  const source = data && typeof data === 'object' ? data : {}
  const triggered = Array.isArray(source.triggered) ? source.triggered : []
  const scope = source.scan_scope && typeof source.scan_scope === 'object' ? source.scan_scope : {}
  const files = Array.isArray(scope.evaluated_files) ? scope.evaluated_files.filter(Boolean) : []
  const reasonKey = typeof scope.reason === 'string' ? scope.reason.trim() : ''
  const reason = SCAN_REASON_MESSAGES[reasonKey] || ''
  if (triggered.length > 0) {
    return {
      kind: 'hit',
      count: triggered.length,
      title: '本轮巡检新触发 ' + triggered.length + ' 条告警',
      detail: '已经写入告警表，下面列表里的就是它们。',
    }
  }
  if (reason) {
    return { kind: 'no-target', count: 0, title: '本轮巡检没有判定点', detail: reason }
  }
  if (files.length > 0) {
    return {
      kind: 'clear',
      count: 0,
      title: '本轮巡检没有命中任何规则',
      detail: '本轮按 ' + files.length + ' 个数据文件判定，没有任何一条规则被触发。',
    }
  }
  return {
    kind: 'unknown',
    count: 0,
    title: '本轮巡检没有回传可读到的数据文件',
    detail: '后端没有说明本轮的扫描范围，所以这里既不说「有异常」，也不说「一切正常」。',
  }
}

// ==================== 请求：一律走 lib/http.js 那一个 axios 实例 ====================

/** GET /alerts -> 告警行数组；结构不对返回 null，由面板画失败脸。 */
export async function fetchAlerts(client = http) {
  const response = await client.get(ALERTS_PATH)
  return listRows(response && response.data, 'alerts')
}

export async function fetchRules(client = http) {
  const response = await client.get(RULES_PATH)
  return listRows(response && response.data, 'rules')
}

export async function createRule(form, client = http) {
  return client.post(RULES_PATH, ruleRequestBody(form))
}

/**
 * 删除一条规则。三种回执都要如实带回：
 *   invalid    id 不是数字，请求根本没发（宁可不动也不发一条打歪的 DELETE）
 *   not_found  后端说这条已经不在了（别人先删了），面板得重刷而不是装作删成功
 *   ok         真删掉了
 */
export async function removeRule(ruleId, client = http) {
  const path = rulePath(ruleId)
  if (!path) return 'invalid'
  const response = await client.delete(path)
  const body = response && response.data && typeof response.data === 'object' ? response.data : {}
  return String(body.status || '') === 'not_found' ? 'not_found' : 'ok'
}

export async function runCheck(client = http) {
  const response = await client.post(CHECK_PATH)
  return response && response.data
}
