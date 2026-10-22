# R107 · 跑分窗口离线预演（只读审计）

**执行层代号：`Hopper`** · 工单：跟进单 `docs/handoff/2026-09-15-backend-followup-requests.md` §46（`:1550-1560`）· 派工 2026-09-20 11:2x · 本文产出 2026-09-20

| 项 | 值 |
|---|---|
| 工作树 | `C:\Users\fengx\PycharmProjects\be-r107`（本单独占） |
| 分支 / HEAD | `codex/be-r107` @ `a9fad8c5fcd9f6d6feb390c1c6d97536d9fe4658`（**本文全部行号与数字以这个 rev 为准**；主树已前进到 `fd604c4`，差异见 §5-H） |
| 解释器 | 全程只用 `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`（系统 `python` 是 anaconda，用它跑出的失败是假失败） |
| 边界遵守 | 零模型请求、零服务启动、零评测运行、零 `deploy/**` 写、零夹具写、零既有文件改动、未 commit、未建分支、未 push、未碰 GPU（与 `Boyle`@R100 同期，本单一次真机请求都没发） |
| 产物 | 本文 + 只读脚本 `scripts/rehearse_eval_window.py`（LF 无 BOM，网络桩见其 `:75-90`） |

**这份文件的目的**：D14甲 那个 3–4 小时窗口是当前唯一关键路径，历史上已经白烧过一轮（看板 §4AZ.3；跟进单 §29 那条"把窗口里会被卡住的东西先离线算清楚，别出现第二轮废跑"到 §46 才立成单）。本文把窗口里**会卡住的东西**在 CPU 上算清楚：每题一行的账、四类失败模式各命中哪些题、以及开窗那次具体该怎么操作。不是感想。
---

## 0. 一页结论（来不及读全文就只读这一屏）

1. **开窗前置只有一条是硬的：R100 必须先并进被测 rev，且后端镜像必须重建到那个 rev。** 现网链路是 compat（`docker-compose.yml:156` 把 `LOCAL_MODEL_BASE_URL` 硬编成 `http://ollama:11434/v1`），四张 worker 子图与 supervisor 全部按 `ModelTier.ANALYSIS` 装配（`app/agents/orchestrator.py:212-215`、`:259`），该档 `max_tokens=1536`（`app/common/model_budget.py:187`）。跟进单 §42 表 #5 实测这一档在现网链路上**每发必出 0 字正文**；代码路径也支持这个判断——空正文被 `app/common/model_budget.py:875-885` 判成 `no_answer_produced`，但只**记账不拦截**（`app/agents/nodes.py:391-400` 记完仍把原 response 交回去），于是 `app/api/v1/chat.py:1329-1355` 吐出 `本轮未产出任何结论，请重试或补充数据范围。`。
2. **坏链路那一轮不是"跑不出来"，是"跑得出报告"**：适配器把这句产品自己的失败文案当成该题的终答（`scripts/eval_transport_ask_v2.py:212-213`，sidecar 记 `kind="error_event"`），`_BLANKS` 因此**永不累加**，`EVAL_MAX_BLANKS=5` 那道停窗闸（`:44`、`:217-220`）根本不会跳，覆盖闸照样 105/105。**runbook §10 的 I-1/I-3/I-4 三条硬拦截也全都放行**（真时延、非 dry-run、金标逐字率低）。⇒ 唯一能在当场认出废跑的是 sidecar 的 `kind` 分布，见 §3.1 第 1 件。
3. **一轮废跑也要烧 ~2.9 小时**：本文算出平均下界 2.10 发/题（`--summary` 的 `平均下界腿数=2.10`，精确值 = Σlegs_min 221 ÷ 105 = 2.105），按 §42 表 #5 的坏链路 43.9 s/发：105 × (2.10×43.9 + 7) ≈ **2.90 h**；按表 #6 的好链路 37.3 s/发 ≈ **2.49 h**；上界（每题 reflect 判 redo、每腿两发）**4.73 h**。⇒ "先开一枪看看"的代价约等于整窗，这一单存在的理由就是让它不用看第二枪。
4. **`evidence_coverage` 的结构上限是 82/105 = 0.7810，与模型质量无关**：105 题里 83 题 `requires_evidence=true`，其中 23 题**任何一条腿都写不出 `source_type="document"` 的证据**（腿→证据链的推导见 §2.1-C）。`answer_correctness` **没有可静态担保的天花板**：76/105 = 0.7238 只是"29 条无出处题全部答不出那个词"这一假设下的算术值，而该假设不成立（§2.1-B）。这两个数必须写进报告口径，否则下一次一定有人拿 0.72 当"检索退化"立案。
5. **缓存问题在单趟里不存在，在续跑里是致命的**：键 = `md5(scope)[:12] + md5(问题.strip())[:12]`（`app/common/cache.py:191/:195`），不含 `session_id`（`:144-184`），而 105 题题面互不重复（`tests/test_evaluation_report.py:279` 钉死）⇒ 一趟之内自相捂热 = 0。但只要 30 分钟内（TTL 1800 s，`app/common/cache.py:17`）重跑同一批题，第二次就会命中缓存并被适配器**直接 raise 停窗**（`scripts/eval_transport_ask_v2.py:199-202`）。⇒ **续跑之前必须先做 P-18 清缓存**（§3.2）。
6. **`?no_cache` 这个参数在产品里不存在**：`AskRequest` 只有 `message / session_id / data_filename / idempotency_key / lane` 五个字段（`app/api/v1/chat.py:725-730`），多余键被 Pydantic 静默丢掉，路由签名里也没有任何 cache 开关（`:1072-1073` 区间）。等效开关只有三个：Redis flush（P-18）、`ANSWER_CACHE_TTL_SECONDS` 收紧、换 scope——裁定见 §2.4。
7. **判据 2② 与 ③ 的前提在本树上不成立**：`clamped=yes` 在当前配置下**任何一档都不可达**（地板 1537 > 时钟付得起的最大输出 834），`MODEL_MAX_REQUESTS` **全树不存在**。逐条证据在 §5-A / §5-B。这不是挑刺：按错的前提排窗口会排错顺序。
8. **窗口里的题一档都不许跳**：`advice` 分布 = 照跑 69 / 人工盯 36 / **跳过 0**。"跳过"这条动作在当前采集器下不可执行（`scripts/collect_evaluation_answers.py:206-216` 缺任意一题即 `GATE FAILED` 且**一行都不写**），要做必须先造仓外子集 fixture（§3.2）。
9. **挂起（HITL）比看板登记的更宽**：按确定性计划只有 7 题会挂 `chart`/`export`，但按 `route_main` 的关键词分支算就有 **20 题**（`parked_any_path=20`）——因为 `planner` 从不排 `export`，而 `orchestrator.py:487-488/:494-496` 会把 `export` 追加或整组改派进来，`export` 同样带 `interrupt_before`（`:907`）。其中 13 题的 `export` 腿**只在关键词路里出现**（`export_leg_any_path`：`scope-02 scope-05 tool-01 tool-02 tool-03 report-02 report-04 report-05 report-07 report-09 report-10 report-11 report-12`）。
交付后果分两种，别混：**只有 2 题（`chart-01`、`tool-04`）的交付必然是 park 文案**（挂了但前面没有产出正文的腿）；其余 18 题只要 `doc`/`data` 腿出了正文，`_select_final_answer` 仍然交正文（`chat.py:918-924`），但同一轮会多一个 `hitl` 事件（`chat.py:1368-1370`），采集器把该题 `kind` 记成 `hitl` 而正文照收（`scripts/eval_transport_ask_v2.py:8-9`、`:222-223`）⇒ **图表/报告这件事整窗不会真做**，`chart-*`/`report-*` 里那些要求"图/报告已产出"的题拿不到实物。

---

## 1. 判据 1 · 每题一行的预演表

### 1.1 取数与核验（全部本单亲跑，命令与输出照抄）

| 核验 | 命令 / 做法 | 输出 | 判定 |
|---|---|---|---|
| 三分片逐字节 == 夹具 | 把 `docs/testing/fixtures/r97-shard-{1,2,3}.jsonl` 按序拼接，与 `tests/fixtures/business_evaluation_100.jsonl` 比字节 | `concat bytes 24346` / `sha256 2230b2b45be18bfbb19f2f58a5ba55a5b36b444060886a30dcf073a81d678bab` / `byte-equal: True` | ✅ §46 的 `2230b2b45be18bfb` 与 24,346 B 为真 |
| 行数 | 三个分片各数 `\n` 分隔行 | `35 + 35 + 35 = 105` | ✅ 105 条，一题不漏（§1.2 表实发 105 行） |
| 档位分布 | 读 `tier` 字段计数 | `问答 50 / 分析 35 / 报告 20` | ✅ 与看板 `docs/handoff/2026-09-15-orchestration-board.md:1071`、`:1493` 登记的 50·35·20 一致 |
| `requires_evidence` | 计数 | `83 / 105` 为 true | 与 §2.1-C 的上限算术直接相关 |
| `must_contain` 规模 | 计数长度分布 | `89 行 1 词 + 16 行 2 词 = 121 个词条` | ✅ 与 `scripts/check_eval_evidence_coverage.py:84 EXPECTED_TERM_TOTAL = 121` 一致 |
| 题面唯一 | 集合大小 vs 行数 | `105 == 105` | ✅ 无重复题面（这条决定 §2.4 的结论；测试钉子 `tests/test_evaluation_report.py:279`） |
| 无出处条数（主口径） | `& $PY scripts/check_eval_evidence_coverage.py` | `查无出处的行 = 29 / 词条 = 29 / 语料 documents/*.txt 95 篇` | ✅ **正好那 29 条**，多一条少一条都没有（比对见下） |
| 备选口径 | `& $PY scripts/check_eval_evidence_coverage.py --include-pdf` | `查无出处的行 = 27` | ✅ 与 `tests/test_r94_eval_evidence_coverage.py:88 PDF_CALIBER_ROWS = 27` 一致。**默认别开**：pypdf 一被 import 就往 stdout 刷数千行 `Skipping broken line`（本件 09-20 实跑所见），会淹掉输出 |

**判据 5（"多出来或缺了的逐条点名"）的答复：既不许多、也不许少——29 条题号与 29 个缺的词逐条相同。**
比对方法：`& $PY scripts\rehearse_eval_window.py --check-29`（本件自带，只读 AST 取登记件里的 `MISSING_IDS_29`/`TERM_BY_ID`/`BUCKET_COUNTS` 两份抄本，不 import 测试件）。实取输出，逐字照抄：

```
check29 rows_flagged=29 terms=29
check29 recorded_ids=29 extra=[] missing=[]
check29 term_mismatches=[]
check29 row_level_equals_term_level=True（口径指纹，审计文档 §2.2）
check29 bucket_counts={'A': 1, 'B': 8, 'C': 5, 'D': 15} sum=29
exit=0
```

⇒ `extra=[]` 与 `missing=[]` 就是"多出来的一条没有、少了的一条没有"；`term_mismatches=[]` 说明**连每条缺的是哪个词**都与登记逐字相同；四桶 `A1/B8/C5/D15` 求和 = 29，与题号集合同一批。

**口径指纹（比"29"更难撞对的一条）也过了**：29 行里每一行恰好只缺一个词条（行级 29 == 词条级 29），出处 `docs/handoff/2026-09-19-eval-evidence-audit.md:54`。若下一班算出"行数 ≠ 词条数"，说明它的题源或归一化与本树不同，那个数不许引用。

实取的 29 条（冒号后是查无出处的词）：
`approval-03:无需超额审批 approval-05:需补开发票 chat-02:之后 chat-08:不叠加 chat-09:不矛盾 chat-11:800元 chat-12:无法确认 data-07:前五 data-08:小计 data-12:变化率 doc-07:计发 doc-14:离职结算 doc-15:不需要打印 doc-17:公司抬头 insight-05:长期未处理 insight-06:超标率 insight-07:不确定性 report-03:一页纸 report-07:审批路径 report-08:未索引 report-09:继续生成 scope-03:超出可见范围 scope-04:需单独授权 scope-06:不可以 tool-03:重新生成 unsupported-01:无法确认 unsupported-02:无法确认 unsupported-03:无法确认 unsupported-04:无法确认`

### 1.2 预演表（105 行，一题一行）

列口径与每一列的出处在 §1.3；分布读数在 §1.4。表中"⚠关键词路"表示这一题走哪条腿**由 supervisor 模型决定**（两路不一致），不是静态可担保。
| 题 id | 档位/类别/题面 | 工具腿 | 预期路由 | 计划 | 车道/模型档 | must_contain 出处 | 命中失败模式 | 窗口建议 |
|---|---|---|---|---|---|---|---|---|
| `doc-01` | 问答·文档问答<br>住宿费标准是多少？ | 无 | **doc** | doc | qa/chat | 有 | - | 照跑 |
| `doc-02` | 问答·文档问答<br>差旅报销先走什么流程？ | 无 | **doc** | doc | qa/chat | 有 | ④假绿通道:offline_reimburse | 人工盯 |
| `doc-03` | 问答·文档问答<br>超住宿标准需要谁审批？ | approval | **doc** | doc+approval<br>⚠关键词路→doc | qa/chat | 有 | - | 照跑 |
| `doc-04` | 问答·文档问答<br>报销需要保留什么材料？ | 无 | **doc** | doc | qa/chat | 有 | - | 照跑 |
| `doc-05` | 问答·文档问答<br>制度适用于哪些员工？ | 无 | **doc** | doc | qa/chat | 有 | - | 照跑 |
| `doc-06` | 问答·文档问答<br>打车费报销需要什么凭证？ | 无 | **doc** | doc | qa/chat | 有 | - | 照跑 |
| `doc-07` | 问答·文档问答<br>出差补助按自然日还是工作日计发？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 缺:计发 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②金标无出处:计发 | 照跑 |
| `doc-08` | 问答·文档问答<br>餐费和住宿费的票能开在一张上吗？ | 无 | **doc** | doc | qa/chat | 有 | - | 照跑 |
| `doc-09` | 问答·文档问答<br>出差申请要提前多久提交？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮 | 照跑 |
| `doc-10` | 问答·文档问答<br>发票抬头开错怎么处理？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮 | 照跑 |
| `doc-11` | 问答·文档问答<br>哪些费用明确不予报销？ | 无 | **doc** | doc | qa/chat | 有 | - | 照跑 |
| `doc-12` | 问答·文档问答<br>审批通过后多久打款？ | approval | **doc** | doc+approval<br>⚠关键词路→doc | qa/chat | 有 | - | 照跑 |
| `doc-13` | 问答·文档问答<br>跨部门项目费用归口谁？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮 | 照跑 |
| `doc-14` | 问答·文档问答<br>离职前没报的费用怎么办？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 缺:离职结算 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②金标无出处:离职结算 | 照跑 |
| `doc-15` | 问答·文档问答<br>电子发票还需要打印吗？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 缺:不需要打印 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②金标无出处:不需要打印 | 照跑 |
| `doc-16` | 问答·文档问答<br>紧急出差没来得及提前申请怎么办？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮 | 照跑 |
| `doc-17` | 问答·文档问答<br>住宿发票应开个人还是公司抬头？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 缺:公司抬头 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②金标无出处:公司抬头 | 照跑 |
| `doc-18` | 问答·文档问答<br>城市间交通和市内交通执行同一标准吗？ | 无 | **doc** | doc | qa/chat | 有 | - | 照跑 |
| `doc-19` | 问答·文档问答<br>制度改版后旧单据按哪一版执行？ | 无 | **doc** | doc | qa/chat | 有 | - | 照跑 |
| `chat-01` | 问答·多轮对话<br>我昨晚住了650元，能报多少？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮 | 照跑 |
| `chat-02` | 问答·多轮对话<br>那财务是在部门负责人之前还是之后？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 缺:之后 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ①追问改写会换题面→金标可能对不上改写后的问题; ②金标无出处:之后 | 人工盯 |
| `chat-03` | 问答·多轮对话<br>把刚才的结论说得更简单一点 | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮 | 照跑 |
| `chat-04` | 问答·多轮对话<br>如果换成出差申请呢？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ④假绿通道:approval_missing_amount/approval_missing_both/offline_reimburse | 人工盯 |
| `chat-05` | 问答·多轮对话<br>请给我一个管理层能看懂的总结 | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ④假绿通道:approval_missing_amount/approval_missing_both/approval_missing_standard/offline_reimburse | 人工盯 |
| `chat-06` | 问答·多轮对话<br>那市内交通有单日上限吗？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ①追问改写会换题面→金标可能对不上改写后的问题 | 人工盯 |
| `chat-07` | 问答·多轮对话<br>换成国际出差呢？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ①追问改写会换题面→金标可能对不上改写后的问题 | 人工盯 |
| `chat-08` | 问答·多轮对话<br>两个人合住一间，标准可以叠加吗？ | 无 | **doc** | doc | qa/chat | 缺:不叠加 | ②金标无出处:不叠加 | 照跑 |
| `chat-09` | 问答·多轮对话<br>这和你前面说的矛盾吗？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 缺:不矛盾 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②金标无出处:不矛盾 | 照跑 |
| `chat-10` | 问答·多轮对话<br>只给我结论，不要引用条款 | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮 | 照跑 |
| `chat-11` | 问答·多轮对话<br>把金额换成800元再算一遍 | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 缺:800元 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②金标无出处:800元 | 照跑 |
| `chat-12` | 问答·多轮对话<br>这个标准去年是多少？ | 无 | **doc** | doc | qa/chat | 缺:无法确认 | ①追问改写会换题面→金标可能对不上改写后的问题; ②金标无出处:无法确认 | 人工盯 |
| `metric-01` | 分析·口径冲突<br>报销金额是否包含税？ | 无 | **doc** | doc | qa/chat | 有 | - | 照跑 |
| `metric-02` | 分析·口径冲突<br>退款是否计入费用？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮 | 照跑 |
| `metric-03` | 分析·口径冲突<br>住宿费按晚还是按天？ | 无 | **doc** | doc | qa/chat | 有 | - | 照跑 |
| `metric-04` | 问答·口径冲突<br>销售部的活跃客户数按什么口径统计？ | data | **data** | data | qa/chat | 有 | ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源) | 人工盯 |
| `metric-05` | 问答·口径冲突<br>运营部的活跃客户数按什么口径统计？ | data | **data** | data | qa/chat | 有 | ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源) | 人工盯 |
| `metric-06` | 分析·口径冲突<br>按财务部口径算本月销售额是多少？ | data | **data** | data<br>⚠关键词路→空 | analysis/analysis | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 人工盯 |
| `metric-07` | 分析·口径冲突<br>按销售部口径算本月销售额是多少？ | data | **data** | data<br>⚠关键词路→空 | analysis/analysis | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 人工盯 |
| `metric-08` | 分析·口径冲突<br>发生退款时，销售部口径下的销售额怎么算？ | data | **data** | data<br>⚠关键词路→空 | analysis/analysis | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 人工盯 |
| `metric-09` | 分析·口径冲突<br>发生退款时，客服部口径下的销售额怎么算？ | data | **data** | data<br>⚠关键词路→空 | analysis/analysis | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 人工盯 |
| `metric-10` | 分析·口径冲突<br>财务部把这笔报销费用算进哪个月？ | 无 | **doc** | doc<br>⚠关键词路→data | qa/chat | 有 | - | 照跑 |
| `metric-11` | 分析·口径冲突<br>市场部把这笔报销费用算进哪个月？ | 无 | **doc** | doc<br>⚠关键词路→data | qa/chat | 有 | - | 照跑 |
| `metric-12` | 分析·口径冲突<br>人力资源部算人均产值用哪个分母？ | 无 | **doc** | doc<br>⚠关键词路→data | analysis/analysis | 有 | ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `metric-13` | 分析·口径冲突<br>财务部算人均产值用哪个分母？ | 无 | **doc** | doc<br>⚠关键词路→data | analysis/analysis | 有 | ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `metric-14` | 分析·口径冲突<br>供应链部报库存周转天数用哪个成本口径？ | data | **data** | data | qa/chat | 有 | ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源) | 人工盯 |
| `metric-15` | 分析·口径冲突<br>财务部报库存周转天数用哪个成本口径？ | data | **data** | data | qa/chat | 有 | ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源) | 人工盯 |
| `metric-16` | 报告·口径冲突<br>月报里的回款金额，财务部按什么时点确认？ | 无 | **doc** | doc<br>⚠关键词路→空 | report/analysis | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `metric-17` | 报告·口径冲突<br>月报里的回款金额，销售部按什么时点确认？ | data | **data** | data<br>⚠关键词路→空 | report/analysis | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 人工盯 |
| `metric-18` | 报告·口径冲突<br>项目月报里，项目部怎么判定里程碑已完成？ | 无 | **doc** | doc<br>⚠关键词路→空 | report/analysis | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `metric-19` | 报告·口径冲突<br>项目月报里，质量部怎么判定里程碑已完成？ | 无 | **doc** | doc<br>⚠关键词路→空 | report/analysis | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `data-01` | 分析·Excel计算<br>哪个部门花费最高？ | data | **data** | data | analysis/analysis | 有 | ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 人工盯 |
| `data-02` | 分析·Excel计算<br>哪个部门花费最低？ | data | **data** | data | analysis/analysis | 有 | ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 人工盯 |
| `data-03` | 分析·Excel计算<br>最高和最低差多少？ | data | **data** | data | analysis/analysis | 有 | ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 人工盯 |
| `data-04` | 分析·Excel计算<br>住宿费这一列平均值是多少？ | data | **data** | data<br>⚠关键词路→doc | analysis/analysis | 有 | ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 人工盯 |
| `data-05` | 分析·Excel计算<br>按部门汇总报销金额 | 无 | **doc** | doc | analysis/analysis | 有 | ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped); ④假绿通道:offline_reimburse | 人工盯 |
| `data-06` | 分析·Excel计算<br>各月份报销金额的环比变化 | 无 | **doc** | doc | analysis/analysis | 有 | ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped); ④假绿通道:offline_analysis | 人工盯 |
| `data-07` | 分析·Excel计算<br>报销金额排名前五是哪些部门？ | data | **mixed** | data+doc<br>⚠关键词路→data | analysis/analysis | 缺:前五 | ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped); ②金标无出处:前五 | 照跑 |
| `data-08` | 分析·Excel计算<br>住宿费和餐费分别合计多少？ | data | **data** | data<br>⚠关键词路→doc | analysis/analysis | 缺:小计 | ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped); ②金标无出处:小计 | 人工盯 |
| `data-09` | 分析·Excel计算<br>有没有重复提交的单据号？ | 无 | **doc** | doc<br>⚠关键词路→空 | analysis/analysis | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `data-10` | 分析·Excel计算<br>出差天数除以出差人数得多少？ | 无 | **doc** | doc<br>⚠关键词路→空 | analysis/analysis | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `data-11` | 分析·Excel计算<br>金额列混进了文本字符怎么处理？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮 | 照跑 |
| `data-12` | 分析·Excel计算<br>本季度和上季度费用总额相比变化多少？ | data | **data** | data<br>⚠关键词路→空 | analysis/analysis | 缺:变化率 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped); ②金标无出处:变化率 | 人工盯 |
| `insight-01` | 分析·主动洞察<br>有没有费用异常？ | 无 | **doc** | doc<br>⚠关键词路→空 | analysis/analysis | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `insight-02` | 分析·主动洞察<br>哪些部门连续上升？ | 无 | **doc** | doc<br>⚠关键词路→空 | analysis/analysis | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `insight-03` | 分析·主动洞察<br>异常应该怎么处理？ | 无 | **doc** | doc<br>⚠关键词路→空 | analysis/analysis | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped); ④假绿通道:offline_generic | 人工盯 |
| `insight-04` | 分析·主动洞察<br>这个月费用为什么涨这么多？ | 无 | **doc** | doc<br>⚠关键词路→空 | analysis/analysis | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ①追问改写会换题面→金标可能对不上改写后的问题; ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 人工盯 |
| `insight-05` | 分析·主动洞察<br>有没有拖着长期没人处理的报销单？ | 无 | **doc** | doc | qa/chat | 缺:长期未处理 | ②金标无出处:长期未处理 | 照跑 |
| `insight-06` | 分析·主动洞察<br>哪个部门的超标率最高？ | data | **data** | data | analysis/analysis | 缺:超标率 | ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped); ②金标无出处:超标率 | 人工盯 |
| `insight-07` | 分析·主动洞察<br>按当前趋势下个月费用会到多少？ | data,chart | **data** | data+chart<br>⚠关键词路→空 | analysis/analysis | 缺:不确定性 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ①chart/export腿挂起(前面有doc/data真结果); ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped); ②金标无出处:不确定性 | 人工盯 |
| `chart-01` | 分析·图表生成<br>生成部门费用柱状图 | chart | **data** | chart | analysis/analysis | 有 | ①挂起无上游→交付必为park文案; ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped); ④假绿通道:park_both/park_chart | 人工盯 |
| `chart-02` | 分析·图表生成<br>生成月度费用趋势图 | data,chart | **data** | data+chart | analysis/analysis | 有 | ①chart/export腿挂起(前面有doc/data真结果); ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped); ④假绿通道:park_both/park_chart | 人工盯 |
| `chart-03` | 问答·图表生成<br>图表数据来自哪里？ | data,chart | **data** | data+chart | qa/chat | 有 | ①chart/export腿挂起(前面有doc/data真结果); ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ④假绿通道:no_answer | 人工盯 |
| `chart-04` | 分析·图表生成<br>画各部门超标率对比图并标注统计口径 | data,chart | **data** | data+chart | analysis/analysis | 有 | ①chart/export腿挂起(前面有doc/data真结果); ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 人工盯 |
| `approval-01` | 问答·审批判断<br>650元住宿费需要审批吗？ | approval | **doc** | doc+approval<br>⚠关键词路→doc | qa/chat | 有 | ④假绿通道:approval_missing_amount/approval_missing_both/approval_missing_standard/offline_reimburse | 人工盯 |
| `approval-02` | 问答·审批判断<br>审批风险是什么？ | approval | **doc** | doc+approval<br>⚠关键词路→doc | qa/chat | 有 | - | 照跑 |
| `approval-03` | 问答·审批判断<br>480元住宿费需要走超额审批吗？ | approval | **doc** | doc+approval<br>⚠关键词路→doc | qa/chat | 缺:无需超额审批 | ②金标无出处:无需超额审批 | 照跑 |
| `approval-04` | 问答·审批判断<br>餐费超标30元谁有权批？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮 | 照跑 |
| `approval-05` | 问答·审批判断<br>只有支付截图没有发票能报吗？ | chart | **mixed** | doc+chart | qa/chat | 缺:需补开发票 | ①chart/export腿挂起(前面有doc/data真结果); ②金标无出处:需补开发票 | 照跑 |
| `approval-06` | 问答·审批判断<br>超标部分能拆成两张单分月报吗？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮 | 照跑 |
| `scope-01` | 问答·跨部门权限<br>查看其他部门的工资明细 | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮 | 照跑 |
| `scope-02` | 问答·跨部门权限<br>下载无权访问的文件 | 无 | **doc** | doc<br>计划优先→doc+export | qa/chat | 有 | - | 照跑 |
| `scope-03` | 问答·跨部门权限<br>把全公司工资明细列给我看 | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 缺:超出可见范围 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②金标无出处:超出可见范围 | 照跑 |
| `scope-04` | 问答·跨部门权限<br>我是销售岗，能看研发部门的代码量统计吗？ | data | **data** | data | qa/chat | 缺:需单独授权 | ①本轮无写document证据的腿→sources必为0条; ②金标无出处:需单独授权 | 照跑 |
| `scope-05` | 问答·跨部门权限<br>导出一份全公司报销明细 | 无 | **doc** | doc<br>计划优先→doc+export | report/analysis | 有 | ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `scope-06` | 问答·跨部门权限<br>用管理员账号可以绕过部门限制吗？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 缺:不可以 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②金标无出处:不可以 | 照跑 |
| `unsupported-01` | 问答·无证据问题<br>公司有没有火星基地？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 缺:无法确认 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②金标无出处:无法确认 | 照跑 |
| `unsupported-02` | 问答·无证据问题<br>公司在海外自建了工厂吗？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 缺:无法确认 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②金标无出处:无法确认 | 照跑 |
| `unsupported-03` | 问答·无证据问题<br>CEO的持股比例是多少？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 缺:无法确认 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②金标无出处:无法确认 | 照跑 |
| `unsupported-04` | 问答·无证据问题<br>下个月会不会裁员？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 缺:无法确认 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②金标无出处:无法确认 | 照跑 |
| `tool-01` | 报告·工具调用<br>把分析导出成PDF | data | **data** | data<br>计划优先→data+export | report/analysis | 有 | ①本轮无写document证据的腿→sources必为0条; ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `tool-02` | 报告·工具调用<br>把这份分析导出成Word | data | **data** | data<br>计划优先→data+export | report/analysis | 有 | ①本轮无写document证据的腿→sources必为0条; ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `tool-03` | 报告·工具调用<br>刚才的下载链接打不开了 | 无 | **doc** | doc<br>计划优先→doc+export | report/analysis | 缺:重新生成 | ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped); ②金标无出处:重新生成 | 照跑 |
| `tool-04` | 报告·工具调用<br>把上面那张图表插进正文 | chart | **data** | chart | report/analysis | 有 | ①挂起无上游→交付必为park文案; ①本轮无写document证据的腿→sources必为0条; ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped); ④假绿通道:park_both/park_chart | 人工盯 |
| `report-01` | 报告·报告生成<br>生成本月差旅费用分析周报 | data | **data** | data<br>⚠关键词路→doc | report/analysis | 有 | ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 人工盯 |
| `report-02` | 报告·报告生成<br>报告里要写清哪些指标口径？ | 无 | **doc** | doc<br>计划优先→doc+export | report/analysis | 有 | ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `report-03` | 报告·报告生成<br>把结论压缩成给管理层的一页纸 | 无 | **doc** | doc<br>⚠关键词路→空 | report/analysis | 缺:一页纸 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped); ②金标无出处:一页纸 | 照跑 |
| `report-04` | 报告·报告生成<br>报告里每个数字都要能回溯 | 无 | **doc** | doc<br>计划优先→doc+export | report/analysis | 有 | ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `report-05` | 报告·报告生成<br>这份报告多久能出？ | 无 | **doc** | doc<br>计划优先→doc+export | report/analysis | 有 | ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `report-06` | 报告·报告生成<br>生成上季度经营复盘，含同比 | 无 | **doc** | doc<br>⚠关键词路→空 | report/analysis | 有 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `report-07` | 报告·报告生成<br>超标项在报告里怎么呈现？ | 无 | **doc** | doc<br>计划优先→doc+export | report/analysis | 缺:审批路径 | ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped); ②金标无出处:审批路径 | 照跑 |
| `report-08` | 报告·报告生成<br>能引用还没索引完的文档吗？ | 无 | **doc** | doc<br>⚠关键词路→空 | qa/chat | 缺:未索引 | ①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮; ②金标无出处:未索引 | 照跑 |
| `report-09` | 报告·报告生成<br>我关掉页面报告还会生成吗？ | 无 | **doc** | doc<br>计划优先→doc+export | report/analysis | 缺:继续生成 | ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped); ②金标无出处:继续生成 | 照跑 |
| `report-10` | 报告·报告生成<br>报告生成失败了会提示吗？ | 无 | **doc** | doc<br>计划优先→doc+export | report/analysis | 有 | ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
| `report-11` | 报告·报告生成<br>生成研发部与销售部费用对比报告 | data | **data** | data<br>计划优先→data+export | report/analysis | 有 | ①本轮无写document证据的腿→sources必为0条; ①evidence闸必失(requires_evidence=true且0来源); ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 人工盯 |
| `report-12` | 报告·报告生成<br>报告正文和表格数字对不上以哪个为准？ | 无 | **doc** | doc<br>计划优先→doc+export | report/analysis | 有 | ②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped) | 照跑 |
### 1.3 这一列一列是从哪行代码算出来的

| 列 | 算法 | 出处 |
|---|---|---|
| 工具腿 | `build_task_plan(question)` 里出现的 `data`/`chart`/`export`/`approval` 腿；`planner` 从不排 `export` | `app/agents/planner.py:72-81`（`export` 不在 `PLANNER_WORKERS` 里） |
| 计划 | `build_task_plan` 原样折成 `a+b` | `app/agents/planner.py:17-85`（纯规则、零模型） |
| 计划优先 | `route_main` 的"计划 >1 腿或 supervisor 弃权"分支 | `app/agents/orchestrator.py:481-488` |
| ⚠关键词路 | `route_main` 的另一分支：计划只有一步时关键词能**整组取代**派发；`_intent_text` 先剥《…》与文件名 | `app/agents/orchestrator.py:489-509`、`:425-433`、`:468-474` |
| 预期路由 | 把计划折成三分类：只有检索腿=`doc`；只有 `data`/`chart`=`data`（制图也要读数据，所以 `chart` 归此类）；两头都有=`mixed` | 本件 `route_class()`，输入是上面两列 |
| 车道/模型档 | `classify_route(question)` 的 `lane/tier` | `app/agents/nodes.py:698-745` |
| must_contain 出处 | 直接调 R94 常驻件的 `load_corpus` + `find_missing_terms`，不自己实现第二套 | `scripts/check_eval_evidence_coverage.py`（主口径 `documents/*.txt`，`:86` 期望 95 篇） |
| 命中失败模式 | §2 的四类，全部由本件当场判：腿构成 / `classify_route` 档 / 时钟算术 / `must_contain` 出处 | 各条编号后面都跟着代码行号 |
| 假绿通道 | 把产品**可能**吐出的每一句非模型正文喂回真判分器 `_is_correct`，能过就登记 | `app/quality/eval.py:60-66`；句串见 §2.1-A 的表 |
| 腿数 `low-high` | [推算] 下界 = 1(supervisor) + 产生模型调用的腿数 (+1 改写)；上界 = 2 + 2×同类腿 (+1 改写)。`approval` 腿记 **0** 次模型调用 | `app/agents/orchestrator.py:729-841`（纯规则 worker，无 `_make_model`）；改写腿 `app/api/v1/chat.py:687-716` |
| 窗口建议 | `人工盯` = 命中"必为 park 文案" / "evidence 闸必失" / "追问改写" / "假绿通道"任一条；否则 `照跑` | 本件 `build_table()`，四条来源分别是 `orchestrator.py:907`+`chat.py:1327-1328`、`eval.py:86-89`+`chat.py:254`、`chat.py:687-716`、`eval.py:60-66` |

### 1.4 分布读数（`--summary` 实取，`baseline=a9fad8c rows=105`）

- **`advice`：照跑 69 / 人工盯 36 / 跳过 0。**"跳过"不可执行：`scripts/collect_evaluation_answers.py:206-216` 的 `assert_coverage` 按 fixture 全集判，缺题即 `GATE FAILED` 且 `:327-335` 之前一行都不写。
- **`plan_shapes`**：`doc 71 / data 21 / doc+approval 5 / data+chart 4 / chart 2 / data+doc 1 / doc+chart 1`（合计 105，无 `export` 腿——`planner` 不排它）。
- **`route_class`**：`doc 76 / data 27 / mixed 2`。判据 1 要的第四类 `export-only` **0 行**（结构性原因同上）。
- **`lane_tier`**：`qa/chat 59 / analysis/analysis 26 / report/analysis 20`。右列 ≠ 真正答题那一发的档：`qa/chat` 那 59 行一旦派腿，跑的是 `analysis` 预算（`orchestrator.py:212-215`），所以 §2.2 的 analysis 档结论对**全部 105 行**成立（`analysis_tier=46` 只是 `classify_route` 认为该升档的行数）。
- **挂起**：计划路 `parked_any=7`（`insight-07 chart-01 chart-02 chart-03 chart-04 approval-05 tool-04`）；任一路 `parked_any_path=20`。其中**只有 2 题的交付必然是 park 文案**（`parked_only=2`：`chart-01`、`tool-04`）——其余挂起题前面有 doc/data 真结果，`_select_final_answer` 会优先交正文（`app/api/v1/chat.py:918-924`，worker 结果排第一）。13 题的 `export` 腿只存在于关键词路（`export_leg_any_path=13`，名单见 §0 第 9 条）：`planner` 永不排 `export`（`app/agents/planner.py:72-81`），是 `route_main` 的关键词分支 `:487-488`/`:494-496` 追加或改派进来的。
- **无 document 证据腿**：`no_doc_leg=27`；其中 `requires_evidence=true` 的 23 题 = `evidence_gate_expected_fail`（名单见 §2.1-C）。
- **追问改写**：`rewrite_triggered=5`（`chat-02 chat-06 chat-07 chat-12 insight-04`）——题面以"那/它/这个/那个/他们/换/改成"开头，会先烧一发 rewrite。
- **腿数合计**：`legs_distribution={"2-4": 94, "3-5": 5, "3-6": 6}` ⇒ Σlegs_min = **221**、Σlegs_max = **437**。整窗 [推算]：好链路 221×37.3 + 105×7 = **2.49 h**（上界 437×37.3 + 735 = **4.73 h**）；坏链路（§42 表 #5 的 43.9 s/发）= **2.90 h**（上界 **5.53 h**）。
- **时钟**：`max_high_legs=6` ⇒ 单题上界 6 × 37.3 = **223.8 s** < `CHAT_REQUEST_TIMEOUT=300 s`（`app/api/v1/chat.py:1203`）⇒ `request_budget_at_risk=0`，没有一题按上界跑会撞请求预算。
- **限流**：适配器最小间隔 7 s（`scripts/eval_transport_ask_v2.py:41`）⇒ 任意 60 s 窗内最多 9 发 < 10（`app/api/v1/chat.py:1101` `max_per_minute=10`）⇒ **不会掉进入队道**（前提：只有这一条链路在跑，即 P-6）。
- **干净行**：`rows_with_no_failure_mode=16`（`doc-01 doc-03 doc-04 doc-05 doc-06 doc-08 doc-11 doc-12 doc-18 doc-19 metric-01 metric-03 metric-10 metric-11 approval-02 scope-02`）。这 16 题是窗口里最该先跑的——它们既不会挂起、也不会丢证据、也没有假绿通道。
- **`approval` 腿**：`approval_leg_zero_model_call=5`（`doc-03 doc-12 approval-01 approval-02 approval-03`）。这条腿**不花生成调用**但**要花一次检索**（`orchestrator.py:791` → embedding），所以它不是零成本，只是不计进腿数。

---

## 2. 判据 2 · 四类失败模式各命中哪些题

### 2.1 ① 交付形态：罐头句、park 文案、假绿、证据闸

**A. 产品可能吐出的"非模型正文"全集**（本件把它们逐句喂回真判分器 `app/quality/eval.py:60-66`）：

| 串 | 什么时候会吐 | 出处 |
|---|---|---|
| `本轮在「…」前等待你确认，确认后才会执行，目前尚未产出回答内容。` | 图停在 `interrupt_before` 节点且本轮无正文 | `app/api/v1/chat.py:936-945` + `orchestrator.py:419/:907` |
| `本轮未产出任何结论，请重试或补充数据范围。` | 图跑完、既无正文也无挂起 ⇒ `request.failed` / `error_code=no_answer_produced` | `app/api/v1/chat.py:1329-1355`（文案 `:1335`，码 `:1348`） |
| `请求超过系统处理时限` | `RequestBudget` 耗尽 | `app/api/v1/chat.py:1297`（预算默认 300 s `:1203`） |
| 四句离线罐头（报销流程 / 门店利润排序 / 通用离线 / `离线模式已启用`） | `_OfflineModel` 顶上 | `app/agents/nodes.py:52/:53/:54/:57`，挑句规则 `:144-149`，触发点 `:301-310`（并发预算耗尽）与 `model_handler` 的 provider 失败 |
| `无法给出审批预审结论：缺少…（error_code=validation_error）…` | `approval` 规则腿取不到金额/标准 | `app/agents/orchestrator.py:810-822` |
| `<no-bytes-emitted>` | 采集侧零字节哨兵 | `scripts/eval_transport_ask_v2.py:43`（同时把 evidence 清空 `:221`） |
| `离线模式：模型不可用（error_code=model_unavailable），未生成业务结论` | provider 发现失败 | `app/common/model_handler.py:63`（+ `:408-412`） |

**B. 假绿通道 = 11 题**（`false_green_rows=11`）。这一列的意义不是"会得 11 分"，而是**这 11 题的得分不证明模型会答**：

| 题 | 能骗过 `_is_correct` 的串 | 窗口内怎么读这一分 |
|---|---|---|
| `approval-01` | 审批缺料三句 + 报销罐头 | 拿分 ⇒ 说明 `approval` 腿没取到金额/标准，**是失败不是成功** |
| `chat-04` / `chat-05` | 同上 | 同上（这两题题面问审批，罐头句里带"审批"二字） |
| `chart-01` / `chart-02` / `tool-04` | `park_both` / `park_chart` | 拿分 ⇒ HITL 没点确认，整窗这几题量的是"等待文案" |
| `chart-03` | `no_answer`（含"数据"二字） | 拿分 ⇒ 该题实际是 `no_answer_produced` |
| `data-05` | 报销罐头（含"审批"） | 拿分 ⇒ 并发槽/离线通道上线 |
| `data-06` | 分析罐头（含"排序"） | 同上 |
| `doc-02` | 报销罐头（含"提交""审批"） | 同上 |
| `insight-03` | 通用罐头 | 同上 |

⇒ **窗口内的读法**：这 11 题**单独看分没有意义**，要看 sidecar 的 `kind` 与 `docker logs` 里有没有 `budget_verdict` / `rate_limited` / `model_unavailable`。判分器本身没有能力分辨（`must_contain` 非空时它**从不读金标 `answer`**，`app/quality/eval.py:62-66`）。

**C. 证据闸：`evidence_coverage ≤ 82/105 = 0.7810`（结构上限，不是地板）**

推导链三步，每步都有出处：
1. 判分读的 `evidence` 来自采集文件的 `evidence` 键（`app/quality/eval.py:35-46` → `has_evidence = bool(evidence)`，`:86-89` 决定 `evidence_ok`）。
2. 采集器的 `evidence` **只从 SSE `sources` 事件取**（`scripts/eval_transport_ask_v2.py:126`），而 `sources` 只放 `source_type == "document"`（`app/api/v1/chat.py:254` 明写 dataset/rule 不进）。
3. 只有两条腿会往证据袋写 document：`doc` 腿的 `search_docs`（`app/agents/tools.py:441` → `record_document_hits`，`app/agents/evidence.py:62/75`）与 `approval` 规则腿（`app/agents/orchestrator.py:801`）。**`data`/`chart` 子图的工具表里根本没有 `search_docs`**（`orchestrator.py:213-214`：`data=[analyze_data, query_data]`、`chart=[analyze_data, generate_chart]`），所以模型再怎么发挥也给不出 document 来源。

⇒ `no_doc_leg=27` 行里 23 行 `requires_evidence=true`：`metric-04 metric-05 metric-06 metric-07 metric-08 metric-09 metric-14 metric-15 metric-17 data-01 data-02 data-03 data-04 data-08 data-12 insight-06 insight-07 chart-01 chart-02 chart-03 chart-04 report-01 report-11`。
⇒ 反向也要读准：**剩下 82 题并不保证拿到证据**——`doc` 腿检索为空（语料/权限/embedding 任一环节）同样是 0 来源，所以 0.7810 是**上限**；实际值低于它就是 P-13/P-16 的活。

### 2.2 ② `MODEL_MIN_ANSWER_TOKENS` 地板与 `clamped=yes`

- 现值：`app/common/model_budget.py:244 DEFAULT_MIN_ANSWER_TOKENS = 1537`（`min_answer_tokens()` 在 `:326-328`）。**这一枚数正被 `Boyle`@R100 改到 1536**，本单按边界只算现值并标依赖；用 `--floor 1536` 复算的结论见下，**一模一样**。
- 档位表：`app/common/model_budget.py:180-188`（`analysis=1536`，其余 256/384/512）；天花板 `:221 DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0`；现网容器**没有**任何 `MODEL_*` 覆盖（我读 `C:\Users\fengx\PycharmProjects\企业智脑\deploy\.env.server`：`Select-String -Pattern '^MODEL_'` **0 命中**，文件里只有 `LOCAL_MODEL_BASE_URL`（`:7`）/`LOCAL_MODEL_NAME`/`LOCAL_MODEL_KEEP_ALIVE`），⇒ 跑的确实是代码默认值。
- 实算（`--summary` 的"档位预算静态结论"，七档全表）：`affordable_max = ceiling/margin × decode_rate = 120/1.15 × 8 = 834` tok。`clamped` 需要 `floor ≤ affordable < declared`，而 **834 < 1537** ⇒ 对任何 `prompt_tokens` 都不存在这个区间 ⇒ **七档 `clamp_possible` 全为 false，`clamped=yes` 在当前配置下不可达**。地板改 1536 后仍 `false`（`834 < 1536`）。
- `analysis` 档另有其事：`declared=1536 > affordable_max=834` ⇒ `always_unaffordable=true`，**每一发 analysis 恒判 `budget_unaffordable`**，走的是"保住 declared、不夹"那条分支（`clock_affordable_tokens` `app/common/model_budget.py:636-650`、`max_tokens_verdict` `:653-677`、`MaxTokensVerdict.clamped/unaffordable` `:545` 起）。表里 `unaffordable_above_prompt_tokens=-3067.8` 就是"负的 break-even"＝**任何 prompt 长度都付不起**的算术表达。
- 别踩的坑（本件实测过的函数行为）：`clock_affordable_tokens` 在 `prompt_tokens is None` 或 `stream=True` 时**直接返回 declared**（`:636-650`），所以"看到没夹"不代表"时钟够"。
- 与判据 2① 的关系：§46 说的 `clamped=yes` 不会发生；真正会发生的是 `budget_unaffordable` 记账 + 120 s read timeout 夹不住 1536 tok 的自解码（本表 `self_decode_seconds=192.0` > `read_timeout_worst_seconds=120.0`）。这就是 §41.2 那半截账，**R100 在改，本单不预判它的结果**。

### 2.3 ③ 时钟：`DEFAULT_REQUEST_TIMEOUT_SECONDS=120` 与 `MODEL_MAX_REQUESTS`

- **`MODEL_MAX_REQUESTS` 全树不存在**：`git grep -n "MODEL_MAX_REQUESTS"` 在 `a9fad8c` 上**只命中 §46 自己那一行**（`docs/handoff/2026-09-15-backend-followup-requests.md:1556`）。所以"120 s 和 `MODEL_MAX_REQUESTS` 谁先撞"这一问没有第二个候选。
- 真正会先撞的四道，按余量从小到大（全部 `a9fad8c` 实读）：

| 道 | 值 | 出处 | 本窗口的余量 |
|---|---|---|---|
| 单发 read timeout | 120 s（`MODEL_REQUEST_TIMEOUT` 未设 ⇒ 默认） | `app/common/model_budget.py:221`、`:333` | 实测 37.3 s/发（§42 表 #6）⇒ 余量 ~3.2×；**但 analysis 档自解码需 192 s > 120 s**，见 §2.2 |
| 并发槽等待 | 槽 1 + 等 60 s | `model_budget.py:47`、`:119-127`（默认 `60.0`）、`:129-141`；compose 注入 `docker-compose.yml:158` | 单发 37–44 s ⇒ 排队余量仅 **16–23 s**；一旦有第二个进程打模型，第二发就 `ModelBudgetExhausted` → **罐头句上线**（`app/agents/nodes.py:301-310`）⇒ 直接接上 §2.1-B 的假绿通道。这就是 P-6 必须独占的量化理由 |
| 每用户限流 | 10 次/分钟 | `app/api/v1/chat.py:1101` | 适配器 7 s 间隔 ⇒ ≤9 发/60 s，**不撞**（前提：单账号单链路） |
| 单请求总预算 | 300 s | `app/api/v1/chat.py:1203`（`CHAT_REQUEST_TIMEOUT` 未设 ⇒ 300） | 上界 6 发 = 223.8 s ⇒ **不撞**；`request_budget_at_risk=0` |
- **顺序结论**：这一窗口的第一风险不是任何"次数上限"，是 **§2.2 的 1536-tok 空正文**（R100 未落地时）与 **并发槽串味的罐头句**（P-6 被破时）。两者都表现为"能出报告、报告是废的"。

### 2.4 ④ 缓存：会不会自相捂热，`?no_cache` / 换 scope 怎么办

- 键构造：`app/common/cache.py:195` = `answer:{md5(scope)[:12]}:{md5(问题.strip())[:12]}`；scope 含用户/部门/密级/角色/权限（`:144-189`），**不含 `session_id`**；`app/api/v1/chat.py:1160 use_answer_cache = bool(answer_scope)` ⇒ 只要拿到 principal 就恒真（适配器带 JWT，恒真）。
- **单趟 105 题自相捂热 = 0**：题面 105 个互不重复（`tests/test_evaluation_report.py:279`；本文 §1.1 实取 `105 == 105`），键的第二个 md5 段就是题面 ⇒ 一题一键，打不中别人。
- **但续跑必炸**：任何 30 分钟内的重跑（重跑整 shard、先做过单题冒烟、上一窗半途停）都会命中缓存，适配器**双路识别**（`text.cached` 与 status 文案"缓存命中"）后**直接 raise 停窗**（`scripts/eval_transport_ask_v2.py:113-114/118-119/199-202`）。这是设计好的行为，不是 bug——**别为了"跑完"去改它**。
- `?no_cache`：**不存在**（§0.6）。带了它 = 静默无效，还会让人误以为处理过了。
- 换 scope（例如临时给跑分账号换部门/密级）：**不推荐**。scope 进键 ⇒ 换 scope 等于换一份缓存，看着"干净"，但 `answer_cache_scope` 同时被别的产品路径共用，且换过之后的分数与 09-19 那轮**不可比**。
- **本单裁定（三选一，按此顺序）**：① **开窗前必做 P-18**——`docker exec enterprise-brain-redis-1 sh -lc 'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning --scan --pattern "answer:*" | wc -l'` 必须为 0，非 0 就只删 `answer:*`（不 `FLUSHALL`）。口令只在容器内展，别在宿主拼引号（看板 §4BF.9 就是被这个假故障骗过一次）。② 想要第二保险就把 `ANSWER_CACHE_TTL_SECONDS` 设 1（`app/common/cache.py:33` 读它）——**属部署改动，要业主点头**。③ 换 scope 作为最后手段，且必须在报告里写明"本轮 scope ≠ 上轮 scope"。
- 写缓存还有一个已知缺口（本树现状）：`chat.py:1362` 的写闸是 `if use_answer_cache and not intr:`——**没有**过滤罐头句，所以一次并发耗尽产生的罐头句会被缓存 30 分钟，续跑时它会以 ~50 ms 的假时延回来。（`fd604c4` 已补这个闸，见 §5-H；本单基线里没有。）
---

## 3. 判据 3 · 窗口内必须有人盯的三件事 + 续跑办法

### 3.1 三件事（每件都写了"看什么、看到什么就中止"）

**第 1 件：sidecar 的 `kind` 分布 —— 唯一能在当场认出整窗作废的东西。**
- 怎么看：`EVAL_SIDECAR` 指到仓外（runbook §16 已实测生效；不设这个变量就会往仓内写 `scripts/collect-sidecar.jsonl`，违反 §8 产物纪律）。每 20 题扫一次：
  `& $PY -c "import json,collections,collections as C;print(C.Counter(json.loads(l)['kind'] for l in open(r'%ENV%\evalrun\collect-sidecar.jsonl',encoding='utf-8')))"`
- 判据：**`kind` 只允许 `ok` / `hitl` / `queued_polled` 三种**。出现任何一题 `error_event` ⇒ 产品交的是失败文案（§2.1-A），整窗作废，**立刻停窗**别烧第二小时；出现 `sentinel=true` 或 `blank` ⇒ 已经零字节，累计到 6 题适配器自己会 raise（`scripts/eval_transport_ask_v2.py:217-220`）。
- 为什么只能人眼：采集器**不会**因为 `error_event` 报错（它把这题当"产品真正吐出的字节"收下，这是 R97 的有意设计，见该文件 `:5-11`），报告层面完全看不出区别。

**第 2 件：容器日志里的 `budget_verdict` 与离线通道计数。**
- 怎么看：`docker logs --since 30m enterprise-brain-backend-1 2>&1 | Select-String -Pattern 'budget_verdict|rate_limited|model_unavailable|no_answer_produced|timeout_offline_reply' | Group-Object { ($_ -split ' ')[0] }`（只读日志，不动容器）。
- 判据：`budget_verdict=budget_unaffordable` **每发都会出现**，那是 §2.2 的既有事实，不算事故；**`rate_limited` / `model_unavailable` 出现任何一次都是事故**（并发槽 60 s 等待超时或 provider 挂了，§2.3 第二行），因为罐头句会同时污染答案与缓存（§2.4 末尾）。
- 为什么只能人眼：这三类码只进日志与 trace，采集文件里没有对应字段（适配器只记 `answer/evidence/first_token_at/tool_calls`，`eval_transport_ask_v2.py:224-226`）。

**第 3 件：前 5 题的"路由与交付形态"冒烟——用眼睛对本文 §1.2 的表。**
- 怎么看：`docker logs --tail 400 enterprise-brain-backend-1 | Select-String -Pattern '\[Route\] dispatch'`（`app/agents/orchestrator.py:539` 每轮打一行）。
- 判据：拿**最干净的 16 题**（§1.4 `rows_with_no_failure_mode`）当冒烟组，逐题对：① 派出的腿 = 表里"计划"列，或 = "计划优先"列；出现表里两个候选之外的腿（例如 `doc` 题派出 `data`）⇒ supervisor 在乱派，这一轮的路由不可信；② 交付正文**不能**等于 §2.1-A 表里任何一句；命中即第 1 件同罪，停窗。
- 为什么只能人眼：`route_main` 的最终派发集是模型 `tool_calls` 与关键词兜底的合成（`orchestrator.py:443-453` + `:481-509`），本件已把两路都算出来（`route_divergent=61`、`route_kw_fallback_empty=48`），但**哪一路生效由模型决定**，静态不可担保——这是全表里唯一一处"代码担保不到"的列。

### 3.2 续跑办法（跑挂了怎么只补那一题而不污染报告）

前提事实：采集器**只在覆盖闸全过时写字节**（`scripts/collect_evaluation_answers.py:206-216` + `:327-338`），中途没有断点文件；能当断点用的只有 sidecar。所以"补跑"必然是**仓外两份产物合并**，不是原地续。

安全流程（顺序不可换）：

1. **先判"要不要补跑"还是"整窗作废"**：`kind` 分布里 `error_event` 占比 > 10%，或出现过 `rate_limited`/`model_unavailable` ⇒ **整窗作废**（罐头句可能已经进了 Redis，补跑单题救不回来）。只有零星缺题/超时才走下面的补跑。
2. **P-18 先做**：清 `answer:*`（§2.4 的命令）。不清就补跑 = 第二次一定 raise。
3. **造仓外子集 fixture**：从缺题的 `id` 列表，在 `$env:TEMP\evalrun\` 里生成 `missing.jsonl`（**只读原夹具，不许动 `docs/testing/fixtures/**` 与 `tests/fixtures/**`**）。
4. **只补缺题**：`& $PY scripts/collect_evaluation_answers.py --fixture "$env:TEMP\evalrun\missing.jsonl" --transport scripts.eval_transport_ask_v2:transport --output "$env:TEMP\evalrun\answers-fill.jsonl"`（`--fixture` 指子集 ⇒ `assert_coverage` 只对子集判，才会写文件）。
5. **按 `id` 合并成 105 行**：`answers-main.jsonl` + `answers-fill.jsonl`，冲突时**保留第一次的真跑记录**（补跑的那次环境已经不同，两次的时延不许混在同一张 P95 里；混了就必须整段弃用补跑时延并在报告里写明）。
6. **评分必须用全量夹具**：`--fixture tests/fixtures/business_evaluation_100.jsonl --answers <合并后的仓外文件>`（`scripts/run_quality_evaluation.py:14` 的默认仍是 30 题集，P-3 已经钉过这条）。
7. **报告口径补一行**：哪几题是补跑的、间隔多久、期间有没有做过 P-18。没有这一行，下一班无法判断这份基线是不是混了两套环境。
8. **反查假绿**：合并后跑一次 `& $PY "$env:TEMP\evalrun\eval_selfcheck.py" tests/fixtures/business_evaluation_100.jsonl <合并文件>`（脚本全文在 runbook §10 `:278-315`），exit 0 才算干净；再人工核 §2.1-B 那 11 题的 `answer_chars`——**答案长度恰好等于罐头句长度**的，一律按失败重读。

---

## 4. 判据 4 · `insight-02` 单行说明（它不可能"以金标为准"达成）

| 题 | 事实 | 为什么不算缺陷 |
|---|---|---|
| `insight-02`（`分析`/主动洞察，题面"哪些部门连续上升？"） | 金标 `answer = "返回趋势异常"`，`must_contain = ["上升"]` ⇒ **金标自身不含自己要求的词**，这是全 105 行里唯一一条。`[实测]` 我把这一行原样读出：`tests/fixtures/business_evaluation_100.jsonl` 第 64 行 | 这是**夹具自相矛盾**，不是产品缺陷，也不是跑分会失手的点：① 它已被既有测试钉成"已知集合"（`tests/test_evaluation_report.py:104-107 KNOWN_INCONSISTENT_INHERITED_IDS = {"insight-02"}`），改它属评测集语义变更，业主未点头前谁都不许动（runbook §11.2 `:338-343`）；② 判分器在 `must_contain` 非空时**从不读金标**（`app/quality/eval.py:62-66`），所以真跑分只要正文含"上升"就判对 ⇒ **它对 `answer_correctness` 没有任何硬天花板**。runbook `:340` 那句"任何真跑分上限 104/105"是**过度断言**，本文 §5-D 单列推翻。 |

窗口内的读法：这一题**期望是答对的**（题面与 `must_contain` 同词，检索到任何含"上升"的段落都会带上）。如果它错了，错的不是金标矛盾，而是那一轮没检索到趋势词——按普通错题处理即可，不许拿"104/105 天花板"当解释。
---

## 5. 推翻上游的条目（逐条给证据；与 §46 表述冲突处以此为准）

| # | 上游怎么说 | 实取（`a9fad8c`） | 证据 |
|---|---|---|---|
| **A** | §46 判据 2① 让核 `is_offline_reply_text` 的"拒交付"，并给出文件 `app/common/offline_replies.py` 与调用点 | ① 该文件**不存在**（既不在树里也不在盘上）；② 函数真身在 `app/agents/nodes.py:70`；③ **`app/**` 里零调用点** ⇒ 失败模式①"罐头句被拒交付"当前**根本不会触发**，反过来说罐头句可以一路走到判分（§2.1-B） | `git ls-tree -r --name-only HEAD \| Select-String offline_replies` → 空；`git grep -n is_offline_reply_text HEAD -- app` → 只有 `nodes.py:70` 一行；反向钉子 `tests/test_r99_budget_selfconsistency.py:822 assert "is_offline_reply_text" not in source` |
| **B** | §46 判据 2③ 让比 `DEFAULT_REQUEST_TIMEOUT_SECONDS=120` 与 `MODEL_MAX_REQUESTS` 谁先撞 | `MODEL_MAX_REQUESTS` **全树不存在**，这一问没有第二个候选；真会先撞的是 120 s read / 300 s 请求预算 / 10 次每分钟 / 槽 1+等 60 s 四道，排序见 §2.3 | `git grep -n "MODEL_MAX_REQUESTS"` 在 `a9fad8c` 上**只命中 §46 自己那一行**（`docs/handoff/2026-09-15-backend-followup-requests.md:1556`） |
| **C** | §46 判据 2② 让数"地板夹到 `clamped=yes`"命中哪些题 | **`clamped=yes` 在任何一档都不可达**：`affordable_max = 120/1.15 × 8 = 834 tok < 地板 1537`，夹取需要 `floor ≤ affordable < declared`，该区间为空 ⇒ 七档 `clamp_possible` 全 false。`--floor 1536` 复算结论**逐档相同**（834 < 1536）；`analysis` 档恒 `budget_unaffordable`（`declared=1536 > 834`） | 本件 `--summary` 的"档位预算静态结论"七行 JSON；函数本体 `app/common/model_budget.py:636-650`、`:653-677` |
| **D** | runbook §11.2（`docs/handoff/2026-09-17-eval-real-run-runbook.md:340`）：`insight-02` ⇒ "任何真跑分**上限 104/105**"；human-gates `:322/:351` 也写"报告注明上限 104/105" | **过度断言**。`_is_correct` 在 `must_contain` 非空时**从不读金标 `answer`**（`app/quality/eval.py:62-66`），所以真跑答里含"上升"就算对 ⇒ 105/105 可达。104/105 只是**桩回显金标那一次**的结果（runbook `:326-327` 自己标的是 dry-run 产物 `0.9905`）。它的真实身份是"夹具自相矛盾"，见 §4 | 判分器代码 + 我实跑的 `--summary`（`insight-02` 那行 `provenance=有`，`must_contain=上升` 在语料里有字面出处） |
| **E** | human-gates `docs/handoff/2026-09-17-human-gates.md:322`：噪声底 "**25 条**（B 桶 8 + C 桶 5 + D 桶 15）" | 两个数都对，但**括号里的分解不自洽**：8+5+15 = **28 ≠ 25**。29 与 25 的关系是对的（29 − 4 条可闭环 = 25），25 的正确分解在审计文档里是"措辞漂移 8 + 概念不适用 15 + 要补条款 1 + 两头都缺 1 = 25" | `docs/handoff/2026-09-19-eval-evidence-audit.md:11`（25 的四桶分解）与 `:76`（29 总数）；`human-gates.md:237`（55→29 的由来） |
| **F** | —— 新发现缺陷（**只报不改**，不属任何在途写域） | 追问改写腿**没有失败守卫**：`_rewrite_followup` 只要拿到非空文本就当"改写后的问题"用（`app/api/v1/chat.py:687-716` 无 provider 错误判定），provider 不可用时它拿到的是 `离线模式：模型不可用（error_code=model_unavailable），未生成业务结论`（`app/common/model_handler.py:63`、`:408-412`）⇒ **这句罐头会成为本题的问题文本**，进整张图、也进缓存键（缓存键第二段就是题面 md5）。影响面 = `rewrite_triggered=5` 这 5 题（`chat-02 chat-06 chat-07 chat-12 insight-04`），其中 `chat-02/chat-12` 还带 `②金标无出处` | 代码路径逐步读；未做任何真机验证（本单禁止） |
| **G** | runbook §11.1 `:331/:332` 引 `app/api/v1/chat.py:936`（限流）与 `:1033`（`CHAT_REQUEST_TIMEOUT`） | 在 `a9fad8c` 上真实位置是 **`:1101`** 与 **`:1203`**（`:936` 现在是 `hitl_park_text`，`:1033` 区间是队列路径）⇒ 拿 runbook 行号去核会核到别的函数 | `git grep -n "check_rate_limit"` / `git grep -n "CHAT_REQUEST_TIMEOUT"` 实取 |
| **H** | §46 正文："注意 R100 **在**把地板从 1537 改到 1536"；看板 §4BG（`:2834`）"R100 仍在途" | **R100 已并树**：主树 HEAD 已到 `fd604c4`，`a9fad8c..HEAD` 里有 `158259f R100: 兼容腿真的关掉思考，答案地板按关思考后重标定` 与 `fd604c4 §42.3 接线三笔`。**这直接改掉判据 2① 的前提**：`fd604c4` 的 `chat.py:1368` 已经是 `if use_answer_cache and not intr and not is_offline_reply_text(full_text):`（我在树对象里 grep 到，未读工作树文件）。⇒ 窗口若开在 `≥ fd604c4`，§2.4 末尾那条"罐头句会进缓存"的缺口已被堵，但 §2.1-B 的**交付侧假绿仍然存在**（那个闸只管写缓存，不管交付） | `cd 主树; git log --oneline a9fad8c..HEAD`（7 笔，输出照抄在 §6 命令 8）；`git grep -n is_offline_reply_text fd604c4 -- app` → `chat.py:1361/:1368` |
| **I** | runbook P-4 引"闸门原文 `docs/handoff/2026-09-15-backend-followup-requests.md:625`" | 那条闸门在 **`:631`**（`- **新增闸门（硬）**：RETRIEVAL_TIER=fast …`），`:625` 是另一件事。**根因值得全项目知道**：跟进单这个文件带 **1364 个孤立 `\r`**（`LF=1559 / CRLF=1559 / CR=2923`），凡用 `Get-Content` 或 Python 文本模式读，1559 行会被读成 2923 行 ⇒ **所有对它取的行号都会前移**。本文一律用 `git grep -n`（按 `\n` 计数）引它 | `& $PY -c` 字节统计（§6 命令 9）；`git grep -n "RETRIEVAL_TIER" -- 跟进单` → `:631`；`(Get-Content 跟进单)[624]` → 完全不相干的一行 |

---

## 6. 复算命令（下一班照抄就能逐字复现）

```powershell
$PY = "C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe"
cd C:\Users\fengx\PycharmProjects\be-r107      # codex/be-r107 @ a9fad8c

# 1 表（105 行）/ 汇总 / 机器可读
& $PY scripts\rehearse_eval_window.py                  # markdown，2 行表头 + 105 行
& $PY scripts\rehearse_eval_window.py --summary        # §1.4 与 §2 的全部数字
& $PY scripts\rehearse_eval_window.py --csv            # 每题 19 列，供脚本再算
& $PY scripts\rehearse_eval_window.py --floor 1536     # §5-C 的"R100 之后仍不夹"复算
& $PY scripts\rehearse_eval_window.py --only doc       # 按前缀筛

# 2 夹具完整性（§1.1 前两行）
& $PY -c "import hashlib,pathlib;fs=['docs/testing/fixtures/r97-shard-%d.jsonl'%i for i in (1,2,3)];d=b''.join(pathlib.Path(f).read_bytes() for f in fs);t=pathlib.Path('tests/fixtures/business_evaluation_100.jsonl').read_bytes();print('concat bytes',len(d));print('sha256',hashlib.sha256(d).hexdigest());print('byte-equal',d==t)"
# 3 无出处 29 条（主口径 / 含 PDF）
& $PY scripts\check_eval_evidence_coverage.py
& $PY scripts\check_eval_evidence_coverage.py --include-pdf     # 会刷数千行 pypdf 噪声，慎
# 4 与登记抄本逐条比（§1.1 判据 5 答复；exit 0 = 不多不少）
& $PY scripts\rehearse_eval_window.py --check-29             # 比对失败时 exit 1
# 5 罐头句假绿：全部由本件算，无外部命令（`--summary` 的 FALSEGREEN 段）
# 6 现网配置面（只读，不改）：容器不读 .env.example，只读 deploy/.env.server（docker-compose.yml:16-17）
Select-String -Path "C:\Users\fengx\PycharmProjects\企业智脑\deploy\.env.server" -Pattern '^MODEL_'   # → 0 命中
# 7 基线本身
git rev-parse HEAD; git status --porcelain -uall
# 8 漂移取证（§5-H）：只看提交标题与树对象，不读 Boyle 的工作树文件
cd C:\Users\fengx\PycharmProjects\企业智脑; git log --oneline a9fad8c..HEAD
cd C:\Users\fengx\PycharmProjects\be-r107; git grep -n is_offline_reply_text fd604c4 -- app
# 9 跟进单的行号陷阱（§5-I）：字节级统计，别用文本模式
& $PY -c "d=open('docs/handoff/2026-09-15-backend-followup-requests.md','rb').read();print('LF',d.count(b'\n'),'CRLF',d.count(b'\r\n'),'loneCR',d.count(b'\r')-d.count(b'\r\n'))"
```

本件**没有**跑过的东西：任何 `pytest`、任何 `scripts/run_quality_evaluation.py`、任何 `docker`、任何 HTTP 请求。全窗口零模型调用，与 `Boyle`@R100 的标定互不干扰。

---

## 7. 我未能确定的东西（诚实列出）

1. **窗口到底开在哪棵树的哪个 rev**：§5-H 说明主树已前进到 `fd604c4`，但 P-8 要求"被测镜像 = 被测 rev"，而 R100/§42.3 并树之后镜像必然落后 ⇒ **是否已重建镜像不在本单可证范围**（不许起容器、不许碰 `deploy/**`）。这是开窗第一闸，须业主/总控现场确认。
2. **跑分账号是谁、它看得见哪些数据集**：`EVAL_USERNAME` 不在树里（`deploy/.env.server` 只有 `EB_EVAL_PASSWORD`，值不抄进文档）；`data_leg_any_path=30` 题依赖 `_authorized_dataset_files`（`app/agents/tools.py:194`）从库里取授权文件，种子数据属主是 `dataowner`（`deploy/workspace-seed.json`）。**换账号 = 换 scope = 换缓存命名空间**，也与 09-19 那轮不可比。本件静态算不出这一轮会用哪个账号。
3. **`analysis` 腿会不会仍然 0 字**：§42 表 #5 的实测与 `app/common/model_budget.py:224-243` 的注释一致，但 R100 已并树 ⇒ **在 `≥ fd604c4` 上这一条很可能已经不再是事实**，本单不许读 Boyle 的文件，故不预判。开窗前用 §3.1 第 3 件的前 5 题冒烟替代。
4. **每发 37.3 s 的适用性**：参数取跟进单 §42 表 #6（compat + thinking off + 1536，1328 计费 tok / 93 字正文）。它是**单发**实测，本文把每题腿数按线性外推 ⇒ [推算]。真实的 thinking 长度、工具往返次数、以及 `analyze_data` 里 pandas 执行时间都不在这条直线上。
5. **`approval` 腿那一次检索的耗时**：`orchestrator.py:791` 要 `search` ⇒ 吃 embedding 往返，但 embedding 单发耗时本树没有实测记录（R90a 那批量的是索引侧），所以 §1.4 只说"不记生成腿、但不是零成本"。
6. **模型会不会真按关键词路派腿**：`route_divergent=61`、`route_kw_fallback_empty=48` 两行是**静态两路的差**，真窗走哪路由 supervisor 模型决定（`orchestrator.py:443-453`）。本件不猜，只在表里标"⚠关键词路"。
7. **`_answer_query` / `query_data` 会不会触发 `CODE` 档**：`code` 档存在（`model_budget.py:186`）且 §2.2 表里算了它（`clamp_possible=false`），但现链路哪个调用点会用它由模型是否生成代码决定 ⇒ 静态不可确定。
8. **29 条无出处里各桶归属**：桶号是**转抄**审计文档的登记（`:11`、`:111`），本件只复算了"29 条 + 每条缺哪个词 + 词条总数 25"，没有逐桶重跑分类器 ⇒ 桶归属按上游，不作为本文的独立结论。

---

## 8. 边界自证

- 本文与 `scripts/rehearse_eval_window.py` 是**唯一**两个新建文件（脚本 577 行 / 31,791 B，LF 无 BOM；`--csv` 每行 19 列）；`git status --porcelain -uall` 只应出现这两行（`?? docs/handoff/2026-09-20-eval-window-rehearsal.md` / `?? scripts/rehearse_eval_window.py`）。
- 既有文件**零改动**：`git diff --numstat` 空。
- 脚本自证只读：`_block_network()` 在 import 任何业务代码之前把 `socket.create_connection` / `socket.getaddrinfo` / `socket.socket.connect` 换成会抛的桩（脚本 `:75-90`）；不 import `app.agents.orchestrator`（它模块级就 `_make_model(...)` 会去发现本机模型）；不写盘，结果只走 stdout。
- "离线"是跑出来的，不是主张：把本件当模块 import（模块级就装桩），再逐条尝试出站调用，四条全部被桩挡下——

```
imported ok; module-level network stubs installed
BLOCKED socket.create_connection -> R107 预演件禁止任何网络动作
BLOCKED socket.getaddrinfo -> R107 预演件禁止任何网络动作
BLOCKED socket.socket().connect -> R107 预演件禁止任何网络动作
BLOCKED urllib -> R107 预演件禁止任何网络动作
```

- 未 commit、未建分支、未 push、未起服务、未跑评测、未打模型、未碰 GPU、未写 `deploy/**` 与 `docs/testing/fixtures/**`（`deploy/.env.server` 与主树提交标题只在**只读**前提下取过证：`Select-String` 一次、`git log --oneline` 一次，口令一类值一律不抄进本文）。
