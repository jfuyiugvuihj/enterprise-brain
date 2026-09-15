// 演示数据 —— 上线前必须清空，见 ./README.md
// 依据：POST /insights/detect 只对客户端送来的 rows 做阈值/环比判定，不查库（后端 R14 未落地）。
// 这三行是编造的部门与金额，"待关注"条数因此不是真实告警。

export const demoRows = [
  { department: '市场部', metric: '差旅费', current: 12600, previous: 7200, threshold: 10000 },
  { department: '财务部', metric: '报销金额', current: 9800, previous: 6100, threshold: 9000 },
  { department: '运营部', metric: '物料费', current: 4200, previous: 4600, threshold: 5000 },
]
