// 演示数据 —— 上线前必须清空，见 ./README.md
// 依据：/dashboard 是算法端点，只算客户端送上来的 rows，不查库（后端 R14 未落地）。
// 因此驾驶舱里的部门金额、异常条数、「审批任务」计数全部由这几个常量推导出来。

export const demoRows = [
  { department: '市场部', metric: '差旅费', value: 18600 },
  { department: '市场部', metric: '差旅费', value: 9200 },
  { department: '财务部', metric: '报销金额', value: 14200 },
  { department: '运营部', metric: '差旅费', value: 7600 },
  { department: '人事部', metric: '培训费', value: 4200 },
  { department: '行政部', metric: '住宿费', value: 5400 },
]

export const demoInsights = [
  { title: '市场部差旅费异常', severity: 'warning', department: '市场部', metric: '差旅费' },
  { title: '财务部报销波动', severity: 'critical', department: '财务部', metric: '报销金额' },
  { title: '行政部住宿费上升', severity: 'warning', department: '行政部', metric: '住宿费' },
]

// 趋势卡只有"形状"是写死的：weights 是相对比例，纵轴高度仍由上面的真实总量缩放。
// scale 标明每条线按哪个量缩放，与原实现里 base / insightBase 的分岔一一对应。
export const demoTrendShape = {
  labels: ['一', '二', '三', '四', '五', '六', '日'],
  series: [
    { label: '文档', color: '#1bcfe6', scale: 'total', weights: [0.30, 0.40, 0.52, 0.46, 0.65, 0.72, 0.88] },
    { label: '数据', color: '#766cff', scale: 'total', weights: [0.15, 0.25, 0.38, 0.30, 0.56, 0.66, 0.76] },
    { label: '洞察', color: '#45d7a2', scale: 'insights', weights: [0.22, 0.28, 0.36, 0.34, 0.48, 0.63, 0.70] },
  ],
}
