// 演示数据 —— 上线前必须清空，见 ./README.md
// 这里剩下的三格只是「自查计算器」的初始输入（F4 裁定保留的那台预演计算器），
// 挂起待办那一屏早就改读 GET /hitl/pending 的真账本了，不依赖本文件。
//
// R237（收 R40 判据③）：本文件【不再有 standard】。预审拿去比的那个数从来不是界面
// 能持有的东西 —— 它由服务端从知识库里检索（app/approval/assistant.py 的
// resolve_standard_from_knowledge_base），取不到就如实报「未给出」，而不是由前端塞一枚
// 500 进去把结论算圆。evidence 同时摘掉：auto 口径下服务端用检索出处整条覆盖请求里的
// 证据，留着假文件名只剩一格改了没用的输入框。

export const demoForm = {
  amount: 680,
  department: '市场部',
  expense_type: '住宿费',
}
