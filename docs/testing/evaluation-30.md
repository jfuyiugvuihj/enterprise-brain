# 业务评估集与持续评估

正式评估集位于 `tests/fixtures/business_evaluation_30.jsonl`，共 30 条，覆盖：

- 文档问答、多轮对话、Excel 计算；
- 指标口径冲突、图表生成、主动洞察；
- 审批判断、跨部门权限、无证据问题、工具调用。

将真实运行结果保存为同样以 `id` 对应的 JSONL：

```json
{"id":"doc-01","answer":"住宿费标准为500元/晚","evidence":[{"source_name":"差旅制度.pdf","locator":"第3页"}],"latency_ms":820}
```

执行报告：

```powershell
python scripts/run_quality_evaluation.py `
  --answers artifacts/evaluation-answers.jsonl `
  --output docs/testing/evaluation-report.json
```

报告包含总体正确率、证据覆盖率、无依据结论率、分类指标和 P95 响应时间。
