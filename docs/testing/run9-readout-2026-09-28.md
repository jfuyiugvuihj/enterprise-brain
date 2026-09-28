# run9 相 1（全 105 题串行）· 收窗判读件（看窗子线，只读产物）

## 抬头（测量条件 + P-15 原样计数）
- 完成戳原文：exit=0 at 2026-09-28 11:09:45
- VECTOR_DUAL_WRITE=on / MODEL_MAX_CONCURRENCY=1 / REPORT_LANE_VIA_QUEUE=on（业主侧 deploy/.env.server 常开）/ RETRIEVAL_TIER、INDEX_BACKEND 未设＝代码默认 full/chroma ⇒ 读路径是 Chroma 遗留件 / Docker context desktop-linux ⇒ 推理在本机 CPU / 模型 qwen3.5:9b + nomic-embed-text，LOCAL_MODEL_KEEP_ALIVE=15m
- 树：主树 C:/Users/fengx/PycharmProjects/企业智脑 分支 codex/data-file-catalog HEAD 9f9d452；点火 09:17:43 +08:00；采集 PID 16056/48184（powershell 壳 55268）
- 🔴 P-15 改写腿整窗计数原样：**rewrite_payload_unparseable=14 次 / 题数 105**（runbook :36 字面量 `查询改写失败` 命中 0 次）
- 🔴 context_limit_exceeded 整窗：**ERROR 2 行 / ModelBudget 2 行**；R149 不同源：**5 行**，dropped>0 涉及题号=['data-07', 'metric-04', 'metric-10', 'metric-11', 'report-03']
- 🔴 PromptPack fitted=0 且 dropped>0：**135 行**（按 tier={'analysis': 135}）
- 本件生成时刻：2026-09-28 11:10:32；仓内零写入，产物全在 C:/Users/fengx/AppData/Local/Temp/evalrun

## 0 覆盖自证
- 取数命令：`(Get-Content <件> | Measure-Object -Line).Lines`；join 键 `id`。
- fixture C:\Users\fengx\PycharmProjects\企业智脑\tests\fixtures\business_evaluation_100.jsonl：rows=105 坏行=0
- sidecar：行数=105 唯一 id=105 坏行=0 缺=0 多=0 重复={}
- frames：行数=105 唯一 id=105 坏行=0 缺=0 多=0 重复={}
- answers：行数=105 唯一 id=105 坏行=0 缺=0 多=0 重复={}
- A0 结论：**PASS**（要求 行数=105 且 id 集与 fixture 全集一致）

## A1 时延（只认 sidecar 的 wall_ms）
- 排名口径：最近秩 `rank=max(1,ceil(n*q))`，与 `app/quality/eval.py:348-352` 同规则。
- 🔴 出处=C:\Users\fengx\AppData\Local\Temp\evalrun\sidecar-run9.jsonl 的 `wall_ms`；未使用 answers.latency_ms（R205a 对越界跨度记 null）。
- tier=问答 n=50 p50=31746.1 p95=125225.2 max=300108.2 min=7927.9
- tier=分析 n=35 p50=65434.5 p95=224651.3 max=291578.9 min=27040.9
- tier=报告 n=20 p50=51948.5 p95=140878.8 max=174562.7 min=12008.9
- category=文档问答 n=19 p50=30714.4 p95=50411.4 max=50411.4 min=7927.9 | max=50.4 s
- category=多轮对话 n=12 p50=36293.1 p95=300108.2 max=300108.2 min=9968.9 | max=300.1 s
- category=口径冲突 n=19 p50=45432.8 p95=119577.9 max=119577.9 min=12008.9 | max=119.6 s
- category=Excel计算 n=12 p50=49178.0 p95=109616.9 max=109616.9 min=27040.9 | max=109.6 s
- category=主动洞察 n=7 p50=138734.5 p95=291578.9 max=291578.9 min=37135.8 | max=291.6 s
- category=图表生成 n=4 p50=107985.8 p95=224651.3 max=224651.3 min=28310.7 | max=224.7 s
- category=审批判断 n=6 p50=38917.8 p95=127991.4 max=127991.4 min=11518.8 | max=128.0 s
- category=跨部门权限 n=6 p50=28499.5 p95=125225.2 max=125225.2 min=10291.0 | max=125.2 s
- category=无证据问题 n=4 p50=27762.5 p95=41358.9 max=41358.9 min=22735.0 | max=41.4 s
- category=工具调用 n=4 p50=46025.4 p95=51706.6 max=51706.6 min=30484.5 | max=51.7 s
- category=报告生成 n=12 p50=90768.5 p95=174562.7 max=174562.7 min=45796.2 | max=174.6 s
- 整表（全部 105 题）n=105 p50=45796.2 p95=154509.1 max=300108.2 min=7927.9
- 问答档（tier=问答，口径未定死故与整表并列）n=50 p50=31746.1 p95=125225.2 max=300108.2 min=7927.9
- sidecar 里没有 wall_ms 的题数：0

## A2 帧账（判据范围 = 93 枚非报告题；report-01..12 因 REPORT_LANE_VIA_QUEUE=on 走队列道，不计入）
- 出处=C:\Users\fengx\AppData\Local\Temp\evalrun\sidecar-run9-frames.jsonl 的 28 键行
- 范围题数=93（105 - 12）；其中帧账在位=93
- text_frames>1 计数=82 / 93
- prefix_breaks>0 计数=5 题号=['data-07', 'metric-04', 'metric-10', 'metric-11', 'tool-04']
- 逐字缺失 missing_chars>0 题号=无
- 逐字重复/多余 extra_chars>0 题号=[('metric-02', 21), ('scope-02', 21)]
- corrective_replacements 非零题号=[('data-07', 1), ('metric-04', 1), ('metric-10', 1), ('metric-11', 1)]
- uncorrected_breaks 非零题号=[('tool-04', 1)]
- criterion_two_holds=False 题号=['approval-06', 'chart-01', 'chat-03', 'chat-06', 'chat-09', 'chat-10', 'data-09', 'doc-07', 'metric-02', 'metric-16', 'scope-01', 'scope-02', 'tool-04']
- last_frame_covers_answer=False 题号=['metric-02', 'scope-02']
- first_visible_ms 分布：n=93 p50=6642.1 p95=13679.0 max=42932.3 min=4700.6
- 报告档 12 枚（排除理由的凭据，逐枚 (text_frames, max_stream_frames)）：report-01=(47, 47), report-02=(45, 43), report-03=(39, 39), report-04=(28, 27), report-05=(15, 14), report-06=(46, 46), report-07=(18, 17), report-08=(15, 15), report-09=(21, 20), report-10=(30, 29), report-11=(50, 49), report-12=(32, 31)
- 报告档 12 枚里 (1,1) 的枚数=0/12；kind={'ok': 4, 'approved_ok': 8}
- 非报告题 text_frames 分布：n=93 p50=24.0 p95=51.0 max=113.0 min=0.0

## A3 改写腿（已结案项，原样复述来源）
- 结案项原文（看板 C:\Users\fengx\PycharmProjects\企业智脑\docs\handoff\2026-09-15-orchestration-board.md）：`### 4AZ.5 R92（本班新立，Averroes 在改）：查询改写现网 **100% 失效**`；症状行 :2849「每一次提问都刷 `查询改写失败，返回原始问题: Expecting value: line 1 column 1 (char 0)`」；影响面行 :2861「此前所有真机跑分都建立在『改写从来没生效』的系统上」。
- 结案凭据：C:\Users\fengx\PycharmProjects\企业智脑\docs\handoff\2026-09-15-orchestration-board.md :2955「今日结案 4 单：R84 · R91 · R90a · R92」；:4233 记 R92 之后改写腿现值 4.08 s/发。
- P-15 口径出处：C:\Users\fengx\PycharmProjects\企业智脑\docs\handoff\2026-09-17-eval-real-run-runbook.md :36（日志点 app/rag/retrieval_pipeline.py:224，档位实现 :49）
- 本窗改写失败整窗计数（P-15 现读）见「总控现场指派·三族 → 族二」，并已原样写进本件抬头第 4 行。

## A4 逐类 correctness / evidence（对 run7 主轮）
- run9 读数出处=C:\Users\fengx\AppData\Local\Temp\evalrun\evaluation-report-run9.json（评分腿产出，落 %TEMP% 不入树）；run7 基线出处=C:\Users\fengx\PycharmProjects\企业智脑\docs\testing\evaluation-report-run7.json
- 总分：run9 correctness=0.5619 evidence=0.7905 unsupported_claim_rate=0.0 total=105 | run7 total=0.5333 correctness=0.7905 evidence=0.0 ucr=105
- 文档问答 (n=19)：corr 0.6316 → 0.5789 (-0.0527) | evidence 0.9474 → 0.9474 (+0.0000)
- 多轮对话 (n=12)：corr 0.3333 → 0.4167 (+0.0834) | evidence 0.6667 → 0.5833 (-0.0834)
- 口径冲突 (n=19)：corr 0.6842 → 0.5789 (-0.1053) | evidence 0.9474 → 0.8947 (-0.0527)
- Excel计算 (n=12)：corr 0.5833 → 0.6667 (+0.0834) | evidence 0.4167 → 0.4167 (+0.0000)
- 主动洞察 (n=7)：corr 0.7143 → 0.5714 (-0.1429) | evidence 0.2857 → 0.4286 (+0.1429)
- 图表生成 (n=4)：corr 0.75 → 0.75 (+0.0000) | evidence 0.0 → 0.0 (+0.0000)
- 审批判断 (n=6)：corr 0.5 → 0.8333 (+0.3333) | evidence 0.8333 → 0.8333 (+0.0000)
- 跨部门权限 (n=6)：corr 0.0 → 0.1667 (+0.1667) | evidence 0.3333 → 0.1667 (-0.1666)
- 无证据问题 (n=4)：corr 0.0 → 0.25 (+0.2500) | evidence 1.0 → 1.0 (+0.0000)
- 工具调用 (n=4)：corr 0.75 → 0.75 (+0.0000) | evidence 0.25 → 0.25 (+0.0000)
- 报告生成 (n=12)：corr 0.5 → 0.5833 (+0.0833) | evidence 0.8333 → 0.9167 (+0.0834)
- 退化类（corr 或 evidence 任一向下降）：[('文档问答', -0.0527, 0.0), ('多轮对话', 0.0834, -0.0834), ('口径冲突', -0.1053, -0.0527), ('主动洞察', -0.1429, 0.1429), ('跨部门权限', 0.1667, -0.1666)]
- 逐题对照基线=C:\Users\fengx\PycharmProjects\企业智脑\docs\testing\answers-run8p2.jsonl（行数=20）；比较集合=两份都有答案的题号
- 可逐题比对 n=20：对→错（退化）=无 | 错→对=['metric-18', 'report-04', 'report-09', 'report-12', 'tool-01', 'tool-02']
- 本轮逐题复算判错的题号（n=46）：['approval-06', 'chart-01', 'chat-03', 'chat-05', 'chat-06', 'chat-09', 'chat-10', 'chat-11', 'chat-12', 'data-08', 'data-09', 'data-10', 'data-11', 'doc-06', 'doc-08', 'doc-09', 'doc-12', 'doc-14', 'doc-16', 'doc-18', 'doc-19', 'insight-03', 'insight-04', 'insight-07', 'metric-02', 'metric-06', 'metric-07', 'metric-10', 'metric-13', 'metric-15', 'metric-16', 'metric-17', 'report-02', 'report-05', 'report-07', 'report-10', 'report-11', 'scope-01', 'scope-02', 'scope-03', 'scope-04', 'scope-05', 'tool-03', 'unsupported-01', 'unsupported-03', 'unsupported-04']
- 下面逐类给出「我复算 vs 评分件」两把读数（自证评分件不是空跑）
  - 文档问答 我复算=0.5789 评分件=0.5789 差=+0.0000
  - 多轮对话 我复算=0.4167 评分件=0.4167 差=+0.0000
  - 口径冲突 我复算=0.5789 评分件=0.5789 差=+0.0000
  - Excel计算 我复算=0.6667 评分件=0.6667 差=+0.0000
  - 主动洞察 我复算=0.5714 评分件=0.5714 差=+0.0000
  - 图表生成 我复算=0.75 评分件=0.75 差=+0.0000
  - 审批判断 我复算=0.8333 评分件=0.8333 差=+0.0000
  - 跨部门权限 我复算=0.1667 评分件=0.1667 差=+0.0000
  - 无证据问题 我复算=0.25 评分件=0.25 差=+0.0000
  - 工具调用 我复算=0.75 评分件=0.75 差=+0.0000
  - 报告生成 我复算=0.5833 评分件=0.5833 差=+0.0000

## D 三格（队列道可读面）
- queue 格在位的报告题数=0/12；queue 顶层键=[]
- D1 terminal.state 计数={'None': 12, '<no terminal cell>': 12}
- D2 usage.usage_present=0/12；total_tokens 非空计数=0/12（run8p2 旧账 0/20）题号=[]
- D2 逐枚 usage={'report-01': None, 'report-02': None, 'report-03': None, 'report-04': None, 'report-05': None, 'report-06': None, 'report-07': None, 'report-08': None, 'report-09': None, 'report-10': None, 'report-11': None, 'report-12': None}
- D3 terminal.sources_n>0 计数=0/12（run8p2 旧账 0/20）；sidecar evidence_n>0 计数=11/12
- D3 逐枚 (sources_n, terminal.shape, evidence_n)=[('report-01', None, None, 6), ('report-02', None, None, 5), ('report-03', None, None, 5), ('report-04', None, None, 3), ('report-05', None, None, 5), ('report-06', None, None, 4), ('report-07', None, None, 6), ('report-08', None, None, 4), ('report-09', None, None, 3), ('report-10', None, None, 4), ('report-11', None, None, 0), ('report-12', None, None, 4)]
- 出处：终端读数槽 app/quality 之外的量具 scripts/eval_transport_ask_v2.py:827-833；usage 由 app/api/v1/chat.py:1957/:1980 交回

## C 两格
- sidecar kind 计数（全 105 题）：{'ok': 85, 'error_event': 2, 'approved_ok': 18}
- C1 缓存命中：kind 含 cache 的计数=0（应为 0）；判据出处 scripts/eval_transport_ask_v2.py:1106-1109（命中即 raise 停窗，正常读数就是「一份都不存在」）
- C1 旁证：run9.log / run9.err 中『命中答案缓存』字样命中行数见「现读补记」
- C2 unsupported_claim_rate=0.0（评分件 evaluation-report-run9.json 的 unsupported_claim_rate 键；算法 app/quality/eval.py:471-477）
- C2 分数不退化：本轮 correctness=0.5619 evidence=0.7905 vs run7 0.5333 / 0.7905

## hitl 格（口径现算，不抄 run5 的 18/105）
- approved=True 计数=18 题号=['chart-01', 'chart-02', 'chart-03', 'chart-04', 'insight-07', 'report-02', 'report-04', 'report-05', 'report-07', 'report-09', 'report-10', 'report-11', 'report-12', 'scope-05', 'tool-01', 'tool-02', 'tool-03', 'tool-04']
- approval_rounds>0 计数=18；approval_http_status 非空计数=18（值分布={'200': 18}）
- pre_kind=hitl（停在闸上的题）计数=18 题号=['chart-01', 'chart-02', 'chart-03', 'chart-04', 'insight-07', 'report-02', 'report-04', 'report-05', 'report-07', 'report-09', 'report-10', 'report-11', 'report-12', 'scope-05', 'tool-01', 'tool-02', 'tool-03', 'tool-04']
- kind=hitl 残留（批准没走完）计数=0 题号=无
- 没答完却占 correctness 分母（分母恒=105，见 app/quality/eval.py:401-402）：sentinel=True 0 题 + kind 属未答完族 2 题 ⇒ 并集 2/105 题号=['metric-02', 'scope-02']
- answers 件里正文为空或含哨兵的题数=0 题号=无
- 甲案旧口径那把尺（pre_approval_ruler，评分件）：{"total": 105, "answer_correctness": 0.5714, "evidence_coverage": 0.7905, "substituted_rows": 18, "basis": "卡闸的题按侧车 pre_answer / pre_evidence_n 计分＝run2..run5 口径；分母不变"}
- 批准账本那把尺（approval_ledger，评分件）：{"hitl_pre_n": 18, "hitl_pre_ids": ["chart-01", "chart-02", "chart-03", "chart-04", "insight-07", "report-02", "report-04", "report-05", "report-07", "report-09", "report-10", "report-11", "report-12", "scope-05", "tool-01", "tool-02", "tool-03", "tool-04"], "approved_final_n": 18, "approved_final_ids": ["chart-01", "chart-02", "chart-03", "chart-04", "insight-07", "report-02", "report-04", "report-05", "report-07", "report-09", "report-10", "report-11", "report-12", "scope-05", "tool-01", "tool-02", "tool-03", "tool-04"], "approval_failed_n": 0, "approval_failed_ids": [], "ledger_rows": 105, 
- 评分件 latency 格：{"count": 105, "average": 64013.64, "p95": 154510.722, "max": 300110.131, "frame_ledger_rows": 105, "one_attempt_envelope_ms": 960000.0, "suspect_n": 0, "basis": "latency_ms 只由每发尝试自己的真实跨度构成：与帧账 wall_ms 相符者按实测进聚合，越界者按帧账逐发跨度替换，无实测而帧账可用者按帧账顶上，拿不出诚实跨度的题排除并逐题列在 suspect"}
- 评分件 suspect 逐题=[]
- sidecar/帧账重复 id（重试落盘）={} / {}
- 判读件生成时刻：2026-09-28 11:10:31；本件由 C:\Users\fengx\AppData\Local\Temp\evalrun\r9_readout.py 只读产出，仓内文件零写入

## 总控现场指派·三族（只读 docker logs；命令原文附在每节首行）
- 日志快照件=C:\Users\fengx\AppData\Local\Temp\evalrun\run9-backend-full.log 行数=5854（整窗一次性落盘，取数命令：`docker logs --since 2026-09-28T09:17:00+08:00 enterprise-brain-backend-1 2>&1 | Set-Content -Encoding UTF8 run9-backend-full.log`；下面每格的等值复跑命令为 `Select-String -Path <该件> -Pattern '<字面量>' | Measure-Object`。日志时间戳为容器本地时间 +08:00，本格一律按 session 前缀/本地时刻对齐，不查 PostgreSQL（PG 存 UTC，按时刻查需换算＝订正三第 3 条）。

### 族一 · `error_code=context_limit_exceeded`
- 命令：`docker logs --since 2026-09-28T09:17:00+08:00 enterprise-brain-backend-1 2>&1 | Select-String "context_limit_exceeded"`
- 计数：执行失败(ERROR)=2 · ModelBudget(WARNING)=2 · 合计行=4
- 时刻与题号配对（用 sidecar 的 ts 就近取 |Δt|<=15 s 的题）：
  - 2026-09-28 09:43:56 → 题号=metric-02 Δt=0.0 s prompt_tokens=2687 kind=error_event
  - 2026-09-28 10:43:19 → 题号=scope-02 Δt=0.0 s prompt_tokens=2769 kind=error_event
- ModelBudget 行的 tier 计数={'analysis': 2}；prompt_tokens 值=[2687, 2769]；required_n_ctx/n_ctx 逐行=[(4223, 4223, 127), (4305, 4305, 209)]
- sidecar 里 kind=error_event 的题（独立第二把量具）：['metric-02', 'scope-02']
- sidecar 里正文=哨兵或 answer_chars<=120 且 evidence_n=0 的题：['approval-06', 'chart-01', 'chart-02', 'chart-03', 'chart-04', 'chat-03', 'chat-06', 'chat-09', 'chat-10', 'chat-11', 'data-01', 'data-02', 'data-03', 'data-09', 'data-10', 'data-11', 'data-12', 'doc-07', 'insight-01', 'insight-02', 'insight-06', 'insight-07', 'metric-02', 'metric-16', 'report-11', 'scope-01', 'scope-02', 'scope-03', 'scope-04', 'scope-05', 'tool-01', 'tool-02', 'tool-04']

### 族一附 · `[PromptPack]` 逐行读数
- 命令：`docker logs --since 2026-09-28T09:17:00+08:00 enterprise-brain-backend-1 2>&1 | Select-String "PromptPack"`
- PromptPack 解析成功行数=322 / 含该字样行数=495（解析不出=形状变了，另报）
- fitted=0 且 dropped>0 计数=135；按 tier 分组={'analysis': 135}；按 (tier,leg) 分组={('analysis', 'doc'): 114, ('analysis', 'data'): 21}
- 全体 PromptPack 行的 leg 计数={'doc': 229, 'data': 93}
- room_total 全体：n=322 范围=[1198, 1198] p50=1198 | fitted=0 子集：n=135 范围=[1198, 1198]
- room_left 全体：n=322 范围=[0, 1198] p50=248 | fitted=0 子集：n=135 范围=[0, 82]
- dropped 分布（全体）：{1: 81, 0: 63, 3: 58, 4: 54, 2: 16, 5: 50}；fitted=0 子集的 dropped 值：[2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5]
- truncated>0 行数=24 stub 值计数={'none': 265, 'kept': 24, 'refused': 33}

### 族二 · P-15 查询改写腿（原样计数，不归一化、不判无害）
- 命令：`docker logs --since 2026-09-28T09:17:00+08:00 enterprise-brain-backend-1 2>&1 | Select-String "rewrite_payload_unparseable" | Measure-Object`，同法再跑 `"查询改写失败"`
- `rewrite_payload_unparseable` 计数=**14**（本窗题数=105，点火 09:17:43，收窗 见完成戳）
- runbook P-15 那条字面量 `查询改写失败` 命中=**0** ⇒ 🔴 现网发的字符串是「查询改写正文解析失败: error_code=rewrite_payload_unparseable」，runbook :36 的原样 pattern 量不到它（同 R393 那一族量具宽度漂移形状）
- reason 计数={'no_json_object': 14}；正文字数序列=[171, 194, 196, 189, 235, 189, 226, 219, 167, 247, 177, 257, 190, 261]
- 时刻列表=['2026-09-28 09:24:30', '2026-09-28 09:25:05', '2026-09-28 09:30:32', '2026-09-28 09:42:22', '2026-09-28 09:44:11', '2026-09-28 09:46:47', '2026-09-28 09:57:45', '2026-09-28 10:19:16', '2026-09-28 10:41:56', '2026-09-28 10:43:13', '2026-09-28 10:49:49', '2026-09-28 10:58:38', '2026-09-28 11:00:17', '2026-09-28 11:04:52']

### 族三 · `[R149] 流式片段与终答不同源`
- 命令：`docker logs --since 2026-09-28T09:17:00+08:00 enterprise-brain-backend-1 2>&1 | Select-String "\[R149\]"`
- 解析成功计数=5 / 含该字样行数=5
- leg 计数={'data': 2, 'doc': 3}；dropped 值=[8, 17, 24, 39, 56]
- final-cumulative 差额：n=5 范围=[262, 1149] 逐值=[262, 455, 487, 791, 1149]
- session 前缀 join 帧账（`session_id` 前 8 位）：
  - 2026-09-28 09:45:31 session=55dd785a leg=data dropped=17 → 题号=['metric-04']
  - 2026-09-28 09:50:54 session=f5ac84b0 leg=doc dropped=39 → 题号=['metric-10']
  - 2026-09-28 09:52:40 session=fe8e4077 leg=doc dropped=8 → 题号=['metric-11']
  - 2026-09-28 10:04:59 session=e7860e75 leg=doc dropped=24 → 题号=['data-07']
  - 2026-09-28 10:54:59 session=dc66e48d leg=data dropped=56 → 题号=['report-03']
- dropped>0 涉及的题号=['data-07', 'metric-04', 'metric-10', 'metric-11', 'report-03']；其中落在 A② 范围（93 枚非报告题）内的=['data-07', 'metric-04', 'metric-10', 'metric-11']
- 🔴 A② 结构性改写（依总控指派）：上述 4 枚题的 A② 记「结构上不成立」，不计入通过；A② 原读数与改后读数逐格对照={'原始 text_frames>1': 82, '剔除 R149 污染后': 78, '结构上不成立题号': ['data-07', 'metric-04', 'metric-10', 'metric-11']}

### 现读补记（缓存命中旁证 · P-18 相关）
- run9.log：行数=5 · 『命中答案缓存』=0 · 『Traceback』=0 · 『零字节题数已超』=0 · 『COLLECT_EXIT』=['COLLECT_EXIT=0']
- run9.err：行数=0 · 『命中答案缓存』=0 · 『Traceback』=0 · 『零字节题数已超』=0 · 『COLLECT_EXIT』=无

## 总控现场指派·第 1 格：kind 直方图（先按语义分家，approved_ok 不是失败）
- 取数件=C:\Users\fengx\AppData\Local\Temp\evalrun\sidecar-run9.jsonl（逐题 join 键 id）。等值复跑命令：`(Get-Content -LiteralPath C:\Users\fengx\AppData\Local\Temp\evalrun\sidecar-run9.jsonl -Encoding UTF8 | ForEach-Object { (`$_ | ConvertFrom-Json).kind }) | Group-Object | Sort-Object Count -Descending`
- kind=ok 计数=85 题号=['approval-01', 'approval-02', 'approval-03', 'approval-04', 'approval-05', 'approval-06', 'chat-01', 'chat-02', 'chat-03', 'chat-04', 'chat-05', 'chat-06', 'chat-07', 'chat-08', 'chat-09', 'chat-10', 'chat-11', 'chat-12', 'data-01', 'data-02', 'data-03', 'data-04', 'data-05', 'data-06', 'data-07', 'data-08', 'data-09', 'data-10', 'data-11', 'data-12', 'doc-01', 'doc-02', 'doc-03', 'doc-04', 'doc-05', 'doc-06', 'doc-07', 'doc-08', 'doc-09', 'doc-10', 'doc-11', 'doc-12', 'doc-13', 'doc-14', 'doc-15', 'doc-16', 'doc-17', 'doc-18', 'doc-19', 'insight-01', 'insight-02', 'insight-03', 'insight-04', 'insight-05', 'insight-06', 'metric-01', 'metric-03', 'metric-04', 'metric-05', 'metric-06', 'metric-07', 'metric-08', 'metric-09', 'metric-10', 'metric-11', 'metric-12', 'metric-13', 'metric-14', 'metric-15', 'metric-16', 'metric-17', 'metric-18', 'metric-19', 'report-01', 'report-03', 'report-06', 'report-08', 'scope-01', 'scope-03', 'scope-04', 'scope-06', 'unsupported-01', 'unsupported-02', 'unsupported-03', 'unsupported-04']
- kind=approved_ok 计数=18 题号=['chart-01', 'chart-02', 'chart-03', 'chart-04', 'insight-07', 'report-02', 'report-04', 'report-05', 'report-07', 'report-09', 'report-10', 'report-11', 'report-12', 'scope-05', 'tool-01', 'tool-02', 'tool-03', 'tool-04']
- kind=error_event 计数=2 题号=['metric-02', 'scope-02']
- 语义分家（正当终态 / 停在闸上 / 零字节）：
  - 正当终态·有真正文 kinds=['ok', 'approved_ok', 'queued_polled'] 计数=103 题号=['approval-01', 'approval-02', 'approval-03', 'approval-04', 'approval-05', 'approval-06', 'chart-01', 'chart-02', 'chart-03', 'chart-04', 'chat-01', 'chat-02', 'chat-03', 'chat-04', 'chat-05', 'chat-06', 'chat-07', 'chat-08', 'chat-09', 'chat-10', 'chat-11', 'chat-12', 'data-01', 'data-02', 'data-03', 'data-04', 'data-05', 'data-06', 'data-07', 'data-08', 'data-09', 'data-10', 'data-11', 'data-12', 'doc-01', 'doc-02', 'doc-03', 'doc-04', 'doc-05', 'doc-06', 'doc-07', 'doc-08', 'doc-09', 'doc-10', 'doc-11', 'doc-12', 'doc-13', 'doc-14', 'doc-15', 'doc-16', 'doc-17', 'doc-18', 'doc-19', 'insight-01', 'insight-02', 'insight-03', 'insight-04', 'insight-05', 'insight-06', 'insight-07', 'metric-01', 'metric-03', 'metric-04', 'metric-05', 'metric-06', 'metric-07', 'metric-08', 'metric-09', 'metric-10', 'metric-11', 'metric-12', 'metric-13', 'metric-14', 'metric-15', 'metric-16', 'metric-17', 'metric-18', 'metric-19', 'report-01', 'report-02', 'report-03', 'report-04', 'report-05', 'report-06', 'report-07', 'report-08', 'report-09', 'report-10', 'report-11', 'report-12', 'scope-01', 'scope-03', 'scope-04', 'scope-05', 'scope-06', 'tool-01', 'tool-02', 'tool-03', 'tool-04', 'unsupported-01', 'unsupported-02', 'unsupported-03', 'unsupported-04']
  - 停在审批闸上 kinds=['hitl', 'queued_awaiting_approval', 'approval_failed'] 计数=0 题号=无
  - 零字节或错误正文 kinds=['blank', 'cancelled', 'error_event', 'queued_dead', 'queued_cancelled', 'queued_done_no_bytes', 'stalled'] 计数=2 题号=['metric-02', 'scope-02']
- sidecar 里根本不存在的题（未落账=丢题）：无
- 🔴 correctness 分母的口径（不靠形容词）：`app/quality/eval.py:468-469` 的 `total=len(rows)`、`answer_correctness=ratio(correct)` 分母恒为全部 105 题，`app/quality/eval.py:401-402` 原话「分母不因为甲案而变：卡闸的题现在拿真终答进分母」⇒ **没有任何一枚 kind 被从分母里剔除**；kind 的差别只在分子上——`FINAL_OK` 那三枚带真正文进 `_is_correct`（eval.py:67-73），`GATED`/`ZERO` 那两族带的是哨兵串或错误串，只能判错不能判对。run2..run5 的 18/105 那一格是「拿批准前那一帧计分」，它在 `pre_approval_ruler`（eval.py:117-148）里，不在主分母上。
- 旧口径那一把尺读数：substituted_rows=18 pre_correctness=0.5714 pre_evidence=0.7905
- `/approve` 那一腿：approved=True 18 枚；approval_rounds>0 18 枚（轮数分布={1: 18}）；approval_http_status 非空 18 枚（值分布={'200': 18}）；approval_error 非空 0 枚；kind=approval_failed 0 枚 题号=无

## 总控现场指派·第 2 格：出处塌方族 / 空壳答族（逐枚点名，metric-02 不并入）
- 基线件：run6=C:\Users\fengx\PycharmProjects\企业智脑\docs\testing\sidecar-run6.jsonl（逐题 evidence_n）run7=C:\Users\fengx\PycharmProjects\企业智脑\docs\testing\answers-run7.jsonl（逐题 len(evidence)）
- 🔴 先扣哨兵：`scripts/eval_transport_ask_v2.py:1139-1140` 在零字节时把 evidence 清空并置 sentinel=true ⇒ 哨兵题的 ev=0 是「没答」不是「出处塌方」，单列。sentinel=True 且 ev=0 的题数=0 题号=无
- 出处塌方（非哨兵且 evidence_n=0）计数=%d；按 category 分组：
  - Excel计算 (n=)：run9 ev=0 7 枚=['data-01', 'data-02', 'data-03', 'data-09', 'data-10', 'data-11', 'data-12'] ｜ 其中 requires_evidence=true 7 枚=['data-01', 'data-02', 'data-03', 'data-09', 'data-10', 'data-11', 'data-12'] ｜ 本不要求出处 0 枚=无 ｜ run6 同集合 ev=0=7 ｜ run7 同集合 ev=0=7
  - 多轮对话 (n=)：run9 ev=0 5 枚=['chat-03', 'chat-06', 'chat-09', 'chat-10', 'chat-11'] ｜ 其中 requires_evidence=true 2 枚=['chat-06', 'chat-11'] ｜ 本不要求出处 3 枚=['chat-03', 'chat-09', 'chat-10'] ｜ run6 同集合 ev=0=4 ｜ run7 同集合 ev=0=4
  - 跨部门权限 (n=)：run9 ev=0 5 枚=['scope-01', 'scope-02', 'scope-03', 'scope-04', 'scope-05'] ｜ 其中 requires_evidence=true 0 枚=无 ｜ 本不要求出处 5 枚=['scope-01', 'scope-02', 'scope-03', 'scope-04', 'scope-05'] ｜ run6 同集合 ev=0=4 ｜ run7 同集合 ev=0=4
  - 主动洞察 (n=)：run9 ev=0 4 枚=['insight-01', 'insight-02', 'insight-06', 'insight-07'] ｜ 其中 requires_evidence=true 4 枚=['insight-01', 'insight-02', 'insight-06', 'insight-07'] ｜ 本不要求出处 0 枚=无 ｜ run6 同集合 ev=0=4 ｜ run7 同集合 ev=0=4
  - 图表生成 (n=)：run9 ev=0 4 枚=['chart-01', 'chart-02', 'chart-03', 'chart-04'] ｜ 其中 requires_evidence=true 4 枚=['chart-01', 'chart-02', 'chart-03', 'chart-04'] ｜ 本不要求出处 0 枚=无 ｜ run6 同集合 ev=0=4 ｜ run7 同集合 ev=0=4
  - 工具调用 (n=)：run9 ev=0 3 枚=['tool-01', 'tool-02', 'tool-04'] ｜ 其中 requires_evidence=true 0 枚=无 ｜ 本不要求出处 3 枚=['tool-01', 'tool-02', 'tool-04'] ｜ run6 同集合 ev=0=3 ｜ run7 同集合 ev=0=3
  - 口径冲突 (n=)：run9 ev=0 2 枚=['metric-02', 'metric-16'] ｜ 其中 requires_evidence=true 2 枚=['metric-02', 'metric-16'] ｜ 本不要求出处 0 枚=无 ｜ run6 同集合 ev=0=1 ｜ run7 同集合 ev=0=0
  - 审批判断 (n=)：run9 ev=0 1 枚=['approval-06'] ｜ 其中 requires_evidence=true 1 枚=['approval-06'] ｜ 本不要求出处 0 枚=无 ｜ run6 同集合 ev=0=0 ｜ run7 同集合 ev=0=1
  - 报告生成 (n=)：run9 ev=0 1 枚=['report-11'] ｜ 其中 requires_evidence=true 1 枚=['report-11'] ｜ 本不要求出处 0 枚=无 ｜ run6 同集合 ev=0=1 ｜ run7 同集合 ev=0=1
  - 文档问答 (n=)：run9 ev=0 1 枚=['doc-07'] ｜ 其中 requires_evidence=true 1 枚=['doc-07'] ｜ 本不要求出处 0 枚=无 ｜ run6 同集合 ev=0=1 ｜ run7 同集合 ev=0=1
- 该族整表对照（同口径 ev=0 枚数，全 105 题）：run9=33（非哨兵）run6=42 run7=32
- 主动洞察族逐枚（run9/run6 evidence_n、run7 len(evidence)）：[('insight-01', 0, 0, 0), ('insight-02', 0, 0, 0), ('insight-03', 4, 7, 7), ('insight-04', 5, 0, 0), ('insight-05', 6, 4, 4), ('insight-06', 0, 0, 0), ('insight-07', 0, 0, 0)]
- 空壳答（非哨兵且 answer_chars<40）计数=4 题号=['chart-01', 'data-09', 'metric-02', 'scope-02']；answer_chars 全窗分布 p50=536 min=15
  - chart-01 [图表生成] kind=approved_ok chars=16 ev=0 wall=132908.6 ms 判分=错 关键词命中=无
      答案原文='【chart Agent 返回】'
      同 session(4fe97053) 日志命中=1 行；前 3 行=['2026-09-28 10:26:57,273 [INFO] enterprise_brain: [ASK] session=4fe97053... 6.1s | steps=1']
      同刻(±5 s，容器本地时间)日志=15 行；样例=["2026-09-28 10:29:00,088 [INFO] httpx: HTTP Request: POST http://ollama:11434/v1/chat/completions \"HTTP/1.1 200 OK\"", "2026-09-28 10:29:00,090 [WARNING] enterprise_brain: [ModelBudget] tier=analysis thinking=disabled prompt_tokens=1054 read_seconds=46.6 budget_verdict=fits declared_max_tokens=1536 max_tokens=1536 affordable_max_tokens=41"]
  - data-09 [Excel计算] kind=ok chars=15 ev=0 wall=108857.0 ms 判分=错 关键词命中=无
      答案原文='【data Agent 返回】'
      同 session(f4b5a391) 日志命中=1 行；前 3 行=['2026-09-28 10:07:37,994 [INFO] enterprise_brain: [ASK] session=f4b5a391... 108.7s | steps=1']
      同刻(±5 s，容器本地时间)日志=10 行；样例=["2026-09-28 10:07:36,257 [INFO] httpx: HTTP Request: POST http://ollama:11434/v1/chat/completions \"HTTP/1.1 200 OK\"", "2026-09-28 10:07:36,258 [INFO] enterprise_brain: [Supervisor] → dispatch(['data'])"]
  - metric-02 [口径冲突] kind=error_event chars=21 ev=0 wall=119577.9 ms 判分=错 关键词命中=无
      答案原文='本轮未产出任何结论，请重试或补充数据范围。'
      同 session(5404bfcf) 日志命中=0 行；前 3 行=无
      同刻(±5 s，容器本地时间)日志=21 行；样例=["2026-09-28 09:43:51,656 [INFO] httpx: HTTP Request: POST http://ollama:11434/api/chat \"HTTP/1.1 200 OK\"", "2026-09-28 09:43:51,656 [INFO] enterprise_brain: [Model] ollama-native 应答: seconds=3.38 load_seconds=0.00 keep_alive=900s done_reason=stop prompt_eval_count=89 eval_count=124 prompt_eval_cached_count=0 content_chars=245 "]
  - scope-02 [跨部门权限] kind=error_event chars=21 ev=0 wall=125225.2 ms 判分=错 关键词命中=无
      答案原文='本轮未产出任何结论，请重试或补充数据范围。'
      同 session(b31a3b04) 日志命中=0 行；前 3 行=无
      同刻(±5 s，容器本地时间)日志=11 行；样例=["2026-09-28 10:43:17,773 [INFO] httpx: HTTP Request: POST http://ollama:11434/api/chat \"HTTP/1.1 200 OK\"", "2026-09-28 10:43:17,773 [INFO] enterprise_brain: [Model] ollama-native 应答: seconds=3.85 load_seconds=0.00 keep_alive=900s done_reason=stop prompt_eval_count=92 eval_count=139 prompt_eval_cached_count=88 content_chars=268"]
- metric-02 归属：本格不并入；它记在「族一 context_limit_exceeded」（kind=error_event，evidence_n=0，answer_chars=21）。

---

## 总控改口（09-28 第十七格·本席亲跑·历史节正文一字未动）

🔴 上面 A2 节抬头那句「判据范围 = 93 枚非报告题；report-01..12 因 `REPORT_LANE_VIA_QUEUE=on` 走队列道，不计入」**是错的，本格作废其范围**。错在它自己 :53-54 的数据就把排除理由否掉了，而它还是按 93 枚出的 A② 数。判读件在 `%TEMP%` 里、不可钉，是本格能出错的根因，不是笔误。

### 凭据（全部由 `python scripts/eval_frame_caliber_readout.py` 现场算出，落仓可复跑，件=本树 `docs/testing/sidecar-run9-frames.jsonl`，105 行/105 唯一题号）

- 报告档 12 枚的**队列格键数全为 0**，`(text_frames, max_stream_frames)` 逐枚=(47,47)(45,43)(39,39)(28,27)(15,14)(46,46)(18,17)(15,15)(21,20)(30,29)(50,49)(32,31) ⇒ **(1,1) 枚数=0/12**。走队列道的形状是「同步流只留一帧回执」，12 枚一枚都不是。
- ⇒ 这一窗 `REPORT_LANE_VIA_QUEUE` **对报告档没生效**（容器侧那个 env 写了 `on`，但请求腿没进队；原因见下条 D 分家与本节最后一行）。
- ⇒ **A② 的判据范围 = 全 105 枚**，不是 93。

### A② 两套范围并列（判据原文=计划书 §6 A 行「`text` 事件数 >1 且逐字比对无缺字」）

| 范围 | n | `text_frames>1` | 空读(=0) | `missing_chars>0`（缺字） | `prefix_breaks>0` | `uncorrected_breaks>0`（真断流） | `criterion_two_holds=True` |
|---|---|---|---|---|---|---|---|
| 全 105（本格正解） | 105 | **94** | 2 | **0 枚** | 7 | **2 枚**：`report-02`、`tool-04` | 91 |
| 剔报告档（上一班实际只给了这套） | 93 | 82 | 2 | 0 枚 | 5 | 1 枚：`tool-04` | 80 |

- 🔴 **口径错误的实际代价（不是纸面瑕疵）**：按 93 枚算，`report-02` 那枚**真断流**（`prefix_breaks` 与 `uncorrected_breaks` 双非零）落在判据范围之外，A② 读出来只剩 `tool-04` 一枚断流。范围一错，坏形就少报一枚，而且少的这枚正好在报告档——D 行要验的那一档。
- 逐字无缺字这一格：**两档都是 0 枚**（全 105 无一枚缺字），这格成立。
- 余下 11 枚 `criterion_two_holds=False` 的单帧/空读题号（全 105 口径共 14 枚 False，扣掉 `report-02`/`metric-02`/`scope-02`）＝`approval-06`、`chart-01`、`chat-03`、`chat-06`、`chat-09`、`chat-10`、`data-09`、`doc-07`、`metric-16`、`scope-01`；其中 `chart-01`、`data-09` 是 R439 那两枚「内部标签当终答」，`metric-02`、`scope-02` 是 `context_limit_exceeded` 的 21 字兜底句（`extra_chars` 各 21），`doc-07`/`metric-04`/`metric-10`/`metric-11` 里除 `doc-07` 外是 R149 装箱污染那族。
- 🔴 **A② 本格判读＝不翻绿**，但**不必再开 run9b**：全 105 的读数已经从现有件算全。挡它的三样按名字点清：① `report-02`＋`tool-04` 两枚真断流；② 11 枚单帧/空读里 `chart-01`/`data-09` 那两枚属 R439；③ R149 装箱那一族（上一班已按总控指派把 4 枚记「结构上不成立」，本格原样保留该改口，不再重复折账）。

### D 行三格分家：「0/12」是查错了层，不是量不到

前一班记「D 三格本窗仍未被量到（`queue` 格 0/12、`usage` 0/12、`sources_n` 0/12）」。分两层重读之后，**只有一格确实没测，另一格其实有真机读数**：

- **流内层**（读帧账的 `events`）：`sources` 事件在流里出现＝**102/105 枚**，报告档 **12/12**；`answer.headline` 72/105（报告档 11/12，缺的那枚=`report-11`）；`request.completed` 102/105、`done` 104/105、`request.failed` 3/105、`hitl` 18/105。⇒ 计划书 §6 D 行那句「`sources` 事件在流里出现」今天**第一次有真机读数**，且报告档一份不缺。
- **队列可读面层**（`GET /queue/{id}` 响应体的 `usage` 六枚槽与 `sources_present`，实现 `scripts/eval_transport_ask_v2.py:803-831`）：12 枚报告题队列格键数全 0 ⇒ 这一层**没被测过**（因为请求压根没入队），不许读成「测了不过」，也不许拿流内那 102 枚去翻它的绿。
- 🔴 `usage` 这格另有一层量具缺陷要说清：帧账的 `events` 只存事件名与时刻、**不存载荷**，所以「流里读不到 usage」是量具不采载荷，**不许读成「模型没报 usage」**（R146 那本账另说）。要量 `usage` 只有队列可读面这一条路 ⇒ 仍是 run9c 的活。

### 本席自纠两条（同一类病，今天我自己也犯过一次）

- 「`sources_n` 0/12」这句是**在错误的层里找一个不存在的键名**：帧账行里既没有 `sources_n` 也没有载荷，正解在 `events` 的事件名。仓规那句「报『某物不存在』前先确认自己在哪一层查、用的是不是这一层的正确名字」对本格同样成立，包括对总控自己。
- 「两套范围都给」这句是**量具声称与量具实现不符**：`r9_readout.py:131/133` 只实现了一套。落仓的 `scripts/eval_frame_caliber_readout.py` 把两套都出，并把排除条件本身做成读数（队列格键数＋(1,1) 枚数⇒现场折成一句判词），范围不再由抬头决定。反证钉另立（跟进单 §123）。

### 时序连带

- `run9b` 那一格（本席上一格按「A② 需换件重算」开的）**作废**，理由见上。
- `run9c` 改名为 **D 三格首验**（12 枚报告题，`EVAL_DECLARE_LANE_TIER=报告` + 队列可读面读数），它同时是「报告档 100% 可查回」那一格的第一次真测——本格已证这一窗**从没测过队列道**，所以那一格连「量了不过」都算不上。