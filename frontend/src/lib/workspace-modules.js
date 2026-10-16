export const WORKSPACE_MODULES = [
  { id: 'analysis', title: '资料与分析', screens: ['feed', 'chat'], start: 'feed', action: '准备资料', description: '准备知识库文档或经营数据，提问分析，核对来源与计算范围。', flow: '准备资料 → 提问分析 → 核对依据' },
  { id: 'tasks', title: '异常与待办', screens: ['insights', 'approval'], start: 'insights', action: '查看异常与任务', description: '从异常记录发起核查，处理待确认操作，再返回原任务查看结果。', flow: '查看异常 → 继续核查 → 处理待办' },
  { id: 'delivery', title: '成果交付', screens: ['artifacts'], start: 'artifacts', action: '查看分析成果', description: '找回图表与报告，核对内容、下载交付，或返回原分析继续追问。', flow: '生成成果 → 核对下载 → 返回分析' },
]
