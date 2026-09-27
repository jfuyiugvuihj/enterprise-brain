/**
 * 异常与告警链路的唯一取数点与「判脸」点（W7 · R1 裁定 (c) 的前端半边）
 *
 * 背景与不变量：
 *  ① 后端零改动。app/api/v1/alerts.py 的读与写五枚端点（GET /alerts、GET/POST/DELETE /alerts/rules、
 *     POST /alerts/check）加上 R251 落的处置三枚（POST /alerts/{id}/ack、/close、/assign）与单条详情
 *     （GET /alerts/{id}），全部过 ACTION_MANAGE_ALERTS 判定，staff 与 auditor 的角色集里没有这一项
 *     （app/common/permissions.py:13/:16），manager 与 admin 有（:14/:15）。
 *     所以员工账号在这一页拿到的是 403，不是空数组；处置三枚也一样，403 不会退成「已经点过了」。
 *  ② 「无权限」与「空列表」必须是两张脸（看板 §4F.5 裁定 (c)）。空列表是 200 响应，
 *     压根走不到失败判定；403 是失败，永远不许被降级成「当前没有触发中的告警」。
 *     同理，401（登录失效）与 500 / 结构不对（服务坏了）也是各自独立的脸。
 *  ③ 文案与「重试」那颗按钮的取值都只出自 lib/errcodes.js 的字典（R368 判据①：界面这一侧不许有
 *     第二本错误码账）。字典的公开读数通道：normalizeError / errorText / isRetryable /
 *     dictionaryAdjudicatesRetry —— 屏上那一格要么是字典说过的值，要么是「字典没说过」那一条兜底。
 *     后端码名不进正文，未知码走 errorCodeLabel 的「错误码：xxx」小字通道。
 *
 * 这里不放任何演示常量：洞察页原先的手填阈值表单加 devFixtures 三行假数据，把「待关注」
 * 说成了真实异常。W7 起这条链路只认服务端回来的行。
 */
import { dictionaryAdjudicatesRetry, errorCodeLabel, errorCodeOf, errorText, isRetryable } from './errcodes'
import { errorDetail, http, PERMISSION_DENIED } from './http'

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
export const PERMISSION_WHERE = '查看告警、维护规则、手动巡检与处置告警（确认、关闭、指派）走的是同一项权限，员工账号默认没有这一项。'
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
 * 「重新加载」那颗按钮的唯一生产者（R368 判据①）。
 *
 * 屏上这一格不许自己判码：字典在册的码 ⇒ 用字典为它备好的那一格取值；字典没为这一枚码说话 ⇒ true。
 * 前者修掉的是「storage_unavailable 挂重试」那一处指错路 —— R359 之后 GET /alerts 在生产无库时真的
 * 回 503 storage_unavailable，而那是跑完迁移才会变的部署缺陷，点多少次都是同一枚 503；
 * 后者保住判据②那一族 —— 连不上服务、未知码、没有码、结构不对，再点一次是有意义的，
 * 不许把这枚修复做成「一律 false」的反方向假绿。
 * 这里一个码名都不列：名单在 lib/errcodes.js 的三张表里，取数层再抄一份就是第二本账。
 */
function failureRetryable(err) {
  return dictionaryAdjudicatesRetry(err) ? isRetryable(err) : true
}

/**
 * 读取失败 -> UiErrorState 的入参。三档脸共用一个出口，差别全在字段里：
 *   unauthorized 登录失效：句子出自字典，重试没用（回登录由 lib/http.js 统一处理）
 *   denied      没权限：说清去哪申请，不给重试按钮
 *   error       真坏了：字典在册的码跟着字典决定给不给「重新加载」；字典没说过的那一族（没有码 /
 *               未知码 / 只按 HTTP 状态兜底归类 / 连不上服务）仍然给 —— 再点一次对这一族是有意义的
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
  return { face, title: failedTitle, description: errorDetail(err, failedTitle), codeLabel: label, retryable: failureRetryable(err) }
}

/** 结构不对的失败：没有错误对象可归码，一律按「坏了」给重试，绝不画成空态。 */
export function shapeFailureView(failedTitle) {
  return { face: 'error', title: failedTitle, description: SHAPE_FAILURE_DESCRIPTION, codeLabel: '', retryable: true }
}

/**
 * 「这一格不向你开放」：没有告警读取权时，那一发 GET /alerts 根本不必发出去（R285 · X-2）。
 *
 * 不发 ≠ 沉默。少了这张脸，那一格会顺着 `alertRows = []` 掉回「当前没有异常线索」——
 * 那是把「这一屏不给这个账号看异常」说成「公司没有异常」，正是 R1(c) 同族的那条缝。
 *
 * 它与 403 那张脸同源同句：讲的是同一件事（这个账号不在告警管理的权限里），所以句子照旧走
 * lib/errcodes.js 的字典出口加 PERMISSION_WHERE，组件里不新造裸句子。四张脸仍两两不等：
 * 没权限（这张）／401 登录失效（readFailureView unauthorized）／真读失败（error）／真空列表（面板空态）。
 * codeLabel 留空：这一发从没发生过，没有后端码名可报，编一个是假话。
 * retryable 为 false：再点一次只是把同一发注定被拒的请求再发一遍。
 */
export function alertsNotOpenView({ deniedTitle }) {
  return {
    face: 'denied',
    title: deniedTitle,
    description: errorText(PERMISSION_DENIED) + PERMISSION_WHERE,
    codeLabel: '',
    retryable: false,
  }
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

// ==================== 处置闭环（R271）：状态词表、逐列上屏与三件动作 ====================

/**
 * 后端没记过的处置列一律回空串（ALERT_DISPOSAL_DEFAULTS，app/api/v1/alerts.py:350-359）。
 * 空串说的就是「没记过」这件事本身，既不是 0，也不是猜出来的名字或时间，所以屏上原话是「未记录」。
 */
export const UNRECORDED = '未记录'
/** department 为空串是后端在册的真值：这一条没有登记归属部门（migrations/0012 的 COMMENT 就这么写）。 */
export const UNATTRIBUTED_DEPARTMENT = '未登记归属部门'

/**
 * 后端 alerts 一行真发的 15 枚列名（顺序按自建库 DDL）。这一枚数组不是文档，是对账用的账本：
 * r271-alert-contract.test.js 拿 git 里的 DDL、migrations 与无库那条腿现算同一份列集比，
 * 后端加一列而这里没跟上，或者这里加一列而后端没有，都当场红。
 */
export const ALERT_BACKEND_COLUMNS = [
  'id', 'rule_id', 'message', 'ai_analysis', 'department', 'read', 'status',
  'acknowledged_by', 'acknowledged_at', 'closed_by', 'closed_at',
  'assignee', 'assigned_by', 'assigned_at', 'created_at',
]
/** 唯一刻意不上屏的一列：后端没有「改成已读」的端点，摆上去就是一个点不动的控件。 */
export const ALERT_COLUMN_NOT_SHOWN = 'read'
/** 处置七列（人和时间）：屏上那三行台账就是按这三对拼出来的，一列都不许多、也不许少。 */
export const ALERT_DISPOSAL_COLUMNS = [
  'acknowledged_by', 'acknowledged_at', 'closed_by', 'closed_at',
  'assignee', 'assigned_by', 'assigned_at',
]

/** 处置状态词表：封闭集合，与后端 ALERT_STATUSES 逐枚同集（app/api/v1/alerts.py:306-313）。 */
export const ALERT_STATUSES = ['open', 'acknowledged', 'closed']
export const ALERT_STATUS_LABELS = {
  open: '还没人处理',
  acknowledged: '已确认，待处理',
  closed: '已关闭',
}
/** 后端给了词表外的状态词：说认不下，绝不照着猜一个能点的动作（与 operatorLabel 同一条口径）。 */
export const ALERT_STATUS_UNKNOWN = '无法识别的处置状态'

/** 三件动作，与三条 POST 路径一一对应（后端 :318-321 与 :982 / :993 / :1004）。 */
export const ALERT_ACTIONS = ['ack', 'close', 'assign']
export const ALERT_ACTION_LABELS = { ack: '确认', close: '关闭', assign: '指派' }

/**
 * 每一枚动作能从哪一格状态出发、写成哪一格：抄后端 ALERT_DISPOSAL_RULES（:326-339）。
 * 这张表只决定按钮点不点得动，为的是少打一发必被 409 拒掉的 POST；判定本身仍然只在服务端。
 * assign 的目标是空串：转派刻意不动状态——派出去说的是「现在归谁」，不是「有人决定了」。
 */
export const ALERT_ACTION_RULES = {
  ack: { from: ['open'], to: 'acknowledged' },
  close: { from: ['open', 'acknowledged'], to: 'closed' },
  assign: { from: ['open', 'acknowledged'], to: '' },
}

/** 按钮必须写明后果：这三句是本单「说人话」的判据，不许改成「操作成功」式的空话。 */
export const ALERT_ACTION_NOTES = {
  ack: '确认后这一条仍在账上，只是记下谁看过并认领了它；已确认的不能再确认一次。',
  close: '关闭是终态：关掉之后它不再能被确认、关闭或转派，这一屏也没有重开它的入口。关闭不等于问题已被修好，只表示有人把这笔账销了。',
  assign: '指派只换「现在归谁」，不改处置状态：接手的本人仍要自己确认一次。',
}

/**
 * 状态词 -> 词表内的键。缺列或空串读成 open：那是迁移给存量行填的同一个默认值
 * （与后端 alert_row_status 同一条口径，:418-424），不是新造的第三种状态。
 * 刻意不 trim 也不转小写：后端判的就是那一串字面值，前端多归一一次，就会点亮一个必被拒的动作。
 */
export function alertStatusKey(value) {
  const raw = typeof value === 'string' ? value : ''
  if (!raw) return 'open'
  return ALERT_STATUSES.indexOf(raw) >= 0 ? raw : ''
}

export function alertStatusLabel(value) {
  const key = alertStatusKey(value)
  return key ? ALERT_STATUS_LABELS[key] : ALERT_STATUS_UNKNOWN
}

/** 从这一格状态出发，前端允许点亮哪几枚动作；认不下的状态一个都不点亮。 */
export function alertActionsFor(value) {
  const key = alertStatusKey(value)
  if (!key) return []
  return ALERT_ACTIONS.filter(action => ALERT_ACTION_RULES[action].from.indexOf(key) >= 0)
}

/** 处置列里的人名：空串就是没记过，说「未记录」，不摆空白也不猜一个名字。 */
function personText(value) {
  const raw = String(value === null || value === undefined ? '' : value).trim()
  return raw || UNRECORDED
}

function stampText(value) {
  return formatStamp(value) || UNRECORDED
}

function recorded(...values) {
  return values.some(value => String(value === null || value === undefined ? '' : value).trim() !== '')
}

/**
 * 处置台账三行：确认 / 关闭 / 指派，每行都是「谁、什么时候」。三行永远在场，取不到的那一格写
 * 「未记录」。时间一律取后端那一列的原值：前端不许自己盖时钟，否则「刷新后仍看得见是谁处理的」
 * 就成了一句话只有这台机器能证明的事。
 */
function alertLedger(source) {
  return [
    {
      key: 'ack',
      label: '确认',
      who: personText(source.acknowledged_by),
      to: '',
      at: stampText(source.acknowledged_at),
      recorded: recorded(source.acknowledged_by, source.acknowledged_at),
    },
    {
      key: 'close',
      label: '关闭',
      who: personText(source.closed_by),
      to: '',
      at: stampText(source.closed_at),
      recorded: recorded(source.closed_by, source.closed_at),
    },
    {
      key: 'assign',
      label: '指派',
      who: personText(source.assigned_by),
      to: personText(source.assignee),
      at: stampText(source.assigned_at),
      recorded: recorded(source.assignee, source.assigned_by, source.assigned_at),
    },
  ]
}

function idText(value) {
  return String(value === null || value === undefined ? '' : value)
}

/**
 * alerts 行 -> 视图模型。后端一行实测 **15 列**（2026-09-26 在 commit 70b4f26 逐列数出来的，
 * 不是照抄任何登记值；缺口清单 G05 记的 13 列少数了 department 与 assigned_by 两枚）：
 *   ① 自建库那条腿：_ensure() 的 CREATE TABLE IF NOT EXISTS alerts —— app/api/v1/alerts.py:107-123，
 *      15 枚列名；
 *   ② 生产库那条腿：migrations/0003 建表 6 列（id、rule_id、message、ai_analysis、read、created_at）
 *      ＋ 0012 补 department ＋ 0014 补 8 枚处置列 ＝ 15 列；
 *   ③ 无库那条腿：evaluate_all 写进内存表的 7 枚字面键（:818-827）＋ alert_ledger_row 永远补齐的
 *      8 枚处置列（:427-438）＝ 15 枚键。
 * 三条路交回的列集相同，所以「后端到底发几列」今天有唯一答案。逐列归属：
 * id、rule_id、message、ai_analysis、created_at 进前五键；department -> departmentText；
 * status -> status / statusLabel / statusKnown；acknowledged_by、acknowledged_at、closed_by、
 * closed_at、assignee、assigned_by、assigned_at 七枚 -> ledger 三行；read 是唯一刻意不上屏的一列。
 * 列集一变，components/__tests__/r271-alert-contract.test.js 当场红。
 *
 * read 列刻意不显示：后端没有把它改成已读的端点，界面上放一个点不动的「标记已读」，
 * 或者摆一个永远不变的未读角，都比省略更糟。
 */
export function mapAlertRow(row) {
  const source = row && typeof row === 'object' ? row : {}
  const message = String(source.message || '').trim()
  const status = alertStatusKey(source.status)
  const ledger = alertLedger(source)
  return {
    id: idText(source.id),
    ruleId: idText(source.rule_id),
    message: message || '这条告警没有留下说明文字。',
    analysis: String(source.ai_analysis || '').trim(),
    createdAt: formatStamp(source.created_at),
    departmentText: String(source.department || '').trim() || UNATTRIBUTED_DEPARTMENT,
    status,
    statusLabel: alertStatusLabel(source.status),
    statusKnown: status !== '',
    handled: ledger.some(line => line.recorded),
    actions: alertActionsFor(source.status),
    ledger,
    addressable: /^\d+$/.test(idText(source.id)),
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
 * 两步确认的唯一实现：一次错位的点击不能对没点过的那一行下手。
 * 删除规则（不可逆）与关闭告警（终态）共用这一枚状态机，不再各写一套。
 */
export function advanceTwoStep(pendingKey, targetKey) {
  const target = String(targetKey === null || targetKey === undefined ? '' : targetKey)
  if (!target) return 'idle'
  return String(pendingKey) === target ? 'execute' : 'arm'
}

/** 删除规则的两步确认：只有返回 execute 才真的发 DELETE。 */
export function advanceRuleDelete(pendingId, targetId) {
  return advanceTwoStep(pendingId, targetId)
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
  all_data_files_unreadable: '本轮扫到的数据文件没有一个能读出来，所以本轮没有任何一条规则拿到数据（这不代表没有异常）。',
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

/**
 * POST /alerts/{id}/ack | /close | /assign 三条路径。编号与动作任一认不下就交回空串，
 * 面板据此一个请求都不发（后端三枚路径参数都是 int：:983 / :994 / :1005）。
 */
export function alertActionPath(alertId, action) {
  const raw = String(alertId === null || alertId === undefined ? '' : alertId).trim()
  if (!/^\d+$/.test(raw)) return ''
  if (ALERT_ACTIONS.indexOf(action) < 0) return ''
  return ALERTS_PATH + '/' + encodeURIComponent(raw) + '/' + action
}

/**
 * 转派的请求体只有一枚目标用户名（后端 AlertAssignCreate，app/api/v1/alerts.py:145-146）。
 * 谁派的、什么时候派的服务端自己记，不接受客户端代填；确认与关闭两枚连请求体都没有。
 */
export function assignRequestBody(assignee) {
  return { assignee: String(assignee === null || assignee === undefined ? '' : assignee).trim() }
}

/** 转派目标必填：空着点按钮只会换来一发注定 400 的 POST。 */
export function assigneeError(assignee) {
  return assignRequestBody(assignee).assignee ? '' : '请填写要派给谁：填对方登录用的用户名，不是显示名。'
}

/**
 * 处置一件告警。回执三种，与 removeRule 同一纪律：
 *   invalid      编号或动作对不上，请求根本没发
 *   unreadable   后端没把「处置之后的那一行」交回来：不装作处置成功，也不点名是谁处理的
 *   done         交回的就是库里现在这一版（后端写完再从同一条归属谓词读回，:559-620）
 */
export async function disposeAlert(alertId, action, assignee = '', client = http) {
  const path = alertActionPath(alertId, action)
  if (!path) return { receipt: 'invalid', row: null }
  const response = action === 'assign'
    ? await client.post(path, assignRequestBody(assignee))
    : await client.post(path)
  const body = response && response.data && typeof response.data === 'object' ? response.data.alert : null
  if (!body || typeof body !== 'object' || Array.isArray(body)) return { receipt: 'unreadable', row: null }
  return { receipt: 'done', row: mapAlertRow(body) }
}

/** 处置失败与降级的标题：六张脸各一句，谁也不许顶替谁。 */
export const DISPOSAL_FAILURE_TITLES = {
  unauthorized: '登录状态已失效',
  denied: '这个账号没有处置告警的权限',
  notFound: '这一条已经不在你的告警账上',
  conflict: '这一条刚被别人动过',
  rejected: '转派没有成立',
  error: '这一件没有做完',
  invalidId: '这条告警没有可用的编号，动作没有发出',
}

/**
 * 编号读不出来的那一格：后端要的是数字编号，这一行的编号是空的或不是数字，
 * 所以三枚动作一个都不该点得动——这与「没权限」是三件事，别混成一张脸。
 */
export const INVALID_ID_FAILURE = {
  face: 'invalidId',
  title: DISPOSAL_FAILURE_TITLES.invalidId,
  description: '后端认的是数字编号，这一行交回的编号读不出来，所以确认、关闭与指派一个都没发出去。列表已重新读取。',
  codeLabel: '',
  retryable: false,
  reload: true,
}

/**
 * 处置失败后的读数。归码只认 lib/errcodes.js 那一张表：404 / 409 / 400 在后端是三枚不同出口，
 * 这里就画三张脸，一张都不许退成读列表那三张（没权限 / 空 / 坏了）。
 *   notFound 后端把「这一条不存在」与「这一条不归你读」答成同一句话（:364-368 的 404 同形口径，
 *            一区分就成了一条存在性 oracle），所以屏上只能说它不在你的账上，不猜它去了哪儿
 *   conflict 点这一下之前状态刚被别人改过：处置只认固定的跳转，关闭是终态
 *   rejected 只可能来自转派。目标那四格里有一格没过，后端刻意不说是哪一格（防用户名枚举，:548-556）
 * reload 为真时面板会重读列表：屏上那一版已经不作数了，别拿旧的一格继续点。
 */
export function disposalFailureView(err, action) {
  const code = errorCodeOf(err)
  const label = errorCodeLabel(err)
  if (code === 'authentication_required') {
    return { face: 'unauthorized', title: DISPOSAL_FAILURE_TITLES.unauthorized, description: errorDetail(err, errorText(code)), codeLabel: '', retryable: false, reload: false }
  }
  if (code === 'permission_denied') {
    return { face: 'denied', title: DISPOSAL_FAILURE_TITLES.denied, description: errorDetail(err, errorText(code)) + PERMISSION_WHERE, codeLabel: label, retryable: false, reload: false }
  }
  if (code === 'resource_not_found') {
    return { face: 'notFound', title: DISPOSAL_FAILURE_TITLES.notFound, description: '服务端说这一条读不到了：它可能已经不在这家企业的账上，也可能不在你这个账号的可见范围里——这两件事后端答得一模一样，这里不替它猜。列表已重新读取，处置没有发生。', codeLabel: label, retryable: false, reload: true }
  }
  if (code === 'conflict') {
    return { face: 'conflict', title: DISPOSAL_FAILURE_TITLES.conflict, description: errorDetail(err, errorText(code)) + '确认、关闭与指派各自只认固定的上一格状态，关闭是终态。先重新加载，看这一条现在到哪一格、归谁。', codeLabel: label, retryable: false, reload: true }
  }
  if (code === 'validation_error' && action === 'assign') {
    return { face: 'rejected', title: DISPOSAL_FAILURE_TITLES.rejected, description: '对方得同时满足两件事：自己管得了告警，且这一条在他的可见范围里。查无此人、账号停用、没有这项权限、看不到这一条——后端回的是同一句话，不说是哪一格是刻意的，分开答就成了一条试用户名的口子。请核对登录用户名后再派。', codeLabel: label, retryable: false, reload: false }
  }
  return { face: 'error', title: DISPOSAL_FAILURE_TITLES.error, description: errorDetail(err, DISPOSAL_FAILURE_TITLES.error), codeLabel: label, retryable: true, reload: false }
}

/**
 * 处置写成了、但列表没能重读回来：这仍然是一张「降级」脸。
 * 不许退成成功（读不到就别宣布读得到），也不许退成空列表（这一条明明在账上）。
 */
export const DISPOSED_BUT_UNREADABLE = {
  kind: 'degraded',
  title: '这一件已经写下，但列表没能重读回来',
  detail: '后端收下了处置，也交回了处置之后的那一行；紧接着重读列表失败，所以这一屏停在读失败的脸上。谁处理的、几点处理的，等列表读得回来时以服务端交回的为准，这里不替它填。',
}

/**
 * 处置成功后的回执：把后端交回的那一行里的人与时间原话带回屏上，
 * 而不是写一句「操作成功」。没有可点名的一行时宁可说「读不出来」。
 */
export function disposalOutcomeView(action, row) {
  const label = ALERT_ACTION_LABELS[action] || '处置'
  const lines = row && Array.isArray(row.ledger) ? row.ledger : []
  const line = lines.find(item => item && item.key === action)
  if (!line) {
    return {
      kind: 'degraded',
      title: label + '这一件后端说做完了，但回执读不出来',
      detail: '处置之后的那一行没有按册交回来，所以这里不写是谁、几点做的。列表已按服务端重读一次，读得回来就以读回来的为准。',
    }
  }
  // 后端回的是成功，可重读回来这一格仍然空空如也：那就当作没写成，绝不替它补名字与时间。
  if (!line.recorded) {
    return {
      kind: 'degraded',
      title: label + '没有被记上：这一格处理人与处理时间都还是空的',
      detail: '这一发请求成功了，可重读回来的账上，' + line.label + '这一行既没有人也没有时间。这里不替它补，也不说已经记上；先确认服务端这一条到底写成什么样，再决定要不要点第二次。',
    }
  }
  const who = line.to ? line.who + ' 派给 ' + line.to : line.who
  return {
    kind: 'done',
    title: label + '已经记到台账上',
    detail: '这一行现在写的是：' + who + ' · ' + line.at + '。' + (ALERT_ACTION_NOTES[action] || ''),
  }
}
