/**
 * R141 · 「档位 ↔ 地址」的唯一一张表
 *
 * 为什么住在这里而不是 ChatPanel 的脚本里：档位选择器今天上了屏，它必须满足三件事——
 * 选中项写进地址、刷新留得住、发出去真的带这一格。前两件事都是「地址」这条腿的形状，
 * 与 src/router/index.js 里那张屏名表同族；抽出来才谈得上单点，也才测得动
 * （node 里没有 DOM，组件里的那段逻辑摸不着，而这一枚模块可以直接拿用例逐格比）。
 *
 * 值必须逐字等于后端那三枚档位名：app/agents/nodes.py 的 LANE_QA / LANE_ANALYSIS /
 * LANE_REPORT，与 app/api/v1/chat.py 的 ASK_LANE_VALUES（空串在内）。这里不发明第四种
 * 拼写，也不把空串解释成 "qa"——tests/test_r32_lane_contract.py 钉着那一条。
 */

/** 空串 = 不声明：服务端按 R42 判别器以问题文本自选（nodes.classify_route）。 */
export const LANE_UNDECLARED = ''

/** 选择框的脸：value 是发给后端的字节，label 是说给人看的。 */
export const LANE_CHOICES = [
  { value: LANE_UNDECLARED, label: '系统判断' },
  { value: 'qa', label: '问答档' },
  { value: 'analysis', label: '分析档' },
  { value: 'report', label: '报告档' },
]

export const LANE_VALUES = LANE_CHOICES.map((choice) => choice.value)

/**
 * 地址栏里的档位 → 选择框的值。
 *
 * 认不得的值落回「系统判断」而不是原样留着：那一格会被发去后端，而 /ask 的取值闸对未知值
 * 当场 400（R32）。地址栏是用户手改得了的东西，宁可不认，也不替用户猜心思。
 */
export function laneFromQuery(query) {
  const given = String((query || {}).lane ?? '')
  return LANE_VALUES.includes(given) ? given : LANE_UNDECLARED
}

/**
 * 选择框的值 → 该写回地址栏的 query。
 *
 * 不声明时**删掉**那一格而不是写 ?lane=：地址里留一枚空值参数，等于让"没人选"看起来像
 * 一次选择，转出去的链接还会带上它。其余查询参数原样留着（会话、深链标签都不该被吃掉）。
 */
export function queryWithLane(query, lane) {
  const next = { ...(query || {}) }
  const value = LANE_VALUES.includes(lane) ? lane : LANE_UNDECLARED
  if (value) next.lane = value
  else delete next.lane
  return next
}
