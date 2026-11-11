// Original question outlines informed by Tableau Pulse and Qlik dashboard examples.
// https://help.tableau.com/current/online/en-us/pulse_explore_metrics.htm
// https://www.qlik.com/us/dashboard-examples/dashboard-reporting
const scope = '先核对实际字段、可见数据、统计期间和单位。缺少必要字段时说明限制，不编造数值；列明所用文件与计算范围，暂不生成报告。'
export const ANALYSIS_TEMPLATES = [
  { id: 'overview', label: '经营概览', description: '关键指标、结构与主要发现', query: `请做经营概览：选择这份数据中适合汇总的指标，说明总量、分组结构和主要发现；不同单位的数值不要混加。${scope}` },
  { id: 'breakdown', label: '分组对比', description: '部门、项目或产品的差异', query: `请做分组对比：按数据中已有的部门、项目或产品字段比较适用指标，列出主要差异和最高、最低值；数据支持时绘制对比图。${scope}` },
  { id: 'trend', label: '趋势分析', description: '期间变化与可比口径', query: `请分析变化趋势：在有日期和可比指标时，按实际期间统计变化并绘制趋势图；说明比较口径，没有日期字段时不要推断趋势。${scope}` },
  { id: 'budget', label: '费用与预算', description: '实际费用、预算和偏差', query: `请核查费用与预算：在具备费用和预算字段时，比较实际值、预算、差额与偏差率，说明主要差异及待核查项；未提供预算时不要编造预算。${scope}` },
  { id: 'anomaly', label: '异常核查', description: '异常记录与核查建议', query: `请核查异常记录：检查缺失值、重复记录和明显异常的数值，列出判断方法、对应记录和建议核查步骤；可能原因与已证实事实分开写。${scope}` },
  { id: 'quality', label: '数据质量', description: '字段、缺失、重复与可用性', query: `请检查数据质量：统计可见行数、字段数、缺失和重复情况，说明这份资料适合做哪些分析以及哪些问题需先补数据。${scope}` },
]
