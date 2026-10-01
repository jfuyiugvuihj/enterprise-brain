# run11c · 云端形状窗判读（2026-10-01，主树 `be11e51`）

口径声明：本窗的 backend 与 worker 都挂在显式 opt-in 的云端覆盖件上（`deploy/compose.cloud-eval.yaml` 在册那枚只管 backend；worker 那一腿今天用的是操作员临时件 `%TEMP%\\evalrun11\\compose.cloud-eval-worker.yaml`，**不落仓**，因为 R453 的在册钉明文规定那枚文件只许碰 backend，把它改口需要同册两态数字与单独裁定）。因此：

- 🔴 **本窗只出形状格**。每一行读数都带 `caliber=cloud-shape`，由 `scripts/eval_cloud_window_readout.py --readouts` 机检：今天 **19 行 / 2 段 / 违规 0 条 / 结论 PASS**。
- 🔴 **时延与分数一律不在本窗**（A① p50/p95、A③ 吞吐与改写腿、A④ correctness／evidence／逐类分／unsupported_claim_rate、以及 `answer_chars`／`evidence_n`／usage token 的**数值**）。那些格仍欠一扇关掉覆盖件、GPU 安静下来的本机全量窗。
- 本机窗今天开不了：机上有一枚仓库外的训练任务（`anaconda3\\python.exe train.py --config configs/_local_cl5.yaml --device cuda --resume`，PID 15344，15:50:42 起）占着 GPU。前置闸 `scripts/r530_run10_window_preflight.py` 的 `gpu_apps`／`foreign_python` 两格因此判 FAIL，那种窗里的 p95 只能标「污染·不可采信」。

## 开窗前置与收窗后置（逐条现取）

| 格 | 读数 | 出处 |
| --- | --- | --- |
| 相 1 起止 | 15:55:40 开 → 16:46:32 收，105/105 行，`exit=0` | `docs/perf/raw/run11c-2026-10-01/run11c.out` |
| 相 2 起止 | 16:54:41 开 → 17:05:56 收，12/12 行，`exit=0` | `docs/perf/raw/run11c-2026-10-01/run11c_p2.out` |
| 两相之间 P-18 | 清掉 31 枚 `answer:*`（`dbsize` 118→87），别的键族清前=清后=87 ⇒ 一枚没碰；复扫 0 枚，`verdict: PASS rc=0` | `scripts/eval_window_answer_cache_gate.py`（runbook §2 第 39 行 R461 起唯一入口件） |
| 语料 | 清前 97 枚 / 清后 97 枚，逐路径+SHA256 对比 **差 0** | `corpus_before.csv` / `corpus_after.csv`（两份 sha256 相同：`105E230D0905AE8A…`） |
| 镜像出处 | `MATCH -- image revision equals be11e51`，`provenance gate: PASS rc=0` | `scripts/check_image_provenance.py --expect-container` |
| 收窗后腿 | backend 与 worker 均恢复默认本机腿：`LOCAL_MODEL_NAME=qwen3.5:9b`、`LOCAL_MODEL_BASE_URL=http://ollama:11434/v1`、`LOCAL_MODEL_API_KEY=local` | `docker exec … env` 现取（17:0x） |
| 云端腿 | `LOCAL_MODEL_NAME=qwen-plus`（百炼 compatible-mode），`MODEL_CONTEXT_TOKENS=8192`；密钥只从操作员进程环境注入，一个字节不落盘 | `deploy/compose.cloud-eval.yaml` 抬头判据④ 与 `scripts/eval_cloud_window_readout.py --preflight`（rc=0） |

## A② 的逐帧读数（相 1，n=105，`scripts/eval_frame_caliber_readout.py`）

- 帧数 >1 的题数：`text_frames` **104/105**、`max_stream_frames` **104/105**；空读（0 帧）**0** 枚。
- 前缀断裂 >0：**64** 题；其中未被纠正 >0：**13** 题（`chart-03`、`scope-02`、`scope-05`、`tool-01/02/03` 加 `report-02/04/05/07/09/10/12` 那一族）。
- 缺字 >0：**4** 题 = `chart-01` `chart-02` `chart-04` `insight-07`；多字 >0：同这 4 题。
- 在册合取口径 `criterion_two_holds`：**88/105**；判据②原文那两格（`text 事件数 >1` 且 `逐字比对无缺字`）：**缺字 4 枚** ⇒ A② 今天仍**不翻绿**，形状面只是把「差在哪 4 枚」钉到了题号上。
- 🔴 排除条件照旧不成立：相 1 那 12 枚报告题的队列格键数全为 0、帧账全在位、`text_frames` 10..128 ⇒ 它们走的是同步流式道，A② 范围必须是 105。

## 队列道第一次真走通（相 2，n=12）

`EVAL_DECLARE_LANE_TIER=报告` 补上量具从前不发的 `lane` 之后，12 枚报告题**全部**入队、由 worker 跑完、再从 `/queue/status` 读回：

- kind：`queued_polled` **4** ／ `queued_approved` **8**；零枚 `queued_failed`、零枚哨兵、零枚重试（`attempt` 全 1）。
- 队列可读面层：12/12 逐枚 `queue` 键数 **10**（`polls` `blips` `relogins` `final` `last_status` `wait_ms` `stall_ms` `deadline_ms` `interval_ms` `terminal`）。在册读体器从前那句「键数为 0 ⇒ 这一层没被测过」是 R443 当年的**散文**，今天这份账的逐枚表已把它推翻 —— 那一层第一次有了读数，纸上的旧句子由本件改口。
- 终态形状：12/12 `terminal.schema=queue-terminal-v1`、`state=answered`、`answer_present` 真、`usage_present` 真（六枚槽全在场：`prompt_tokens` `completion_tokens` `total_tokens` `model_calls` `calls_with_token_readout` `calls_missing_token_readout`）；`sources_present` 真 **8/12**，另 4 枚里 3 枚 `evidence_n=0`（`report-03` `report-06` `report-08`）⇒ D 门那句「报告档 100% 可查回」今天**还不能翻绿**，欠的是那 3 枚的出处，不是投递面。
- 帧面：`queued`+`done` 两帧、`text_frames` 0 或 1 —— 那是队列道的**形状**（流在入队口就关了），不是缺字（`missing_chars` >0 = 0 枚）。

## 那 4 枚批准失败说的是格③，不是投递面

相 1 里 `insight-07` `chart-01` `chart-02` `chart-04` 的 `kind=approval_failed`，`approval_http_status` 全是 **200**、`approved` 全是**真**、`approval_rounds` 全是 1，报错原文逐枚相同：

> `approve 200 仍无终答：artifact owner must have a department scope`

批准动作本身成功了，**终答没回来**，原因是产物属主没有部门范围。这正是计划书 §13 格③ 那笔账在现场的样子：生产 `users.department` 空 ⇒ 批准门放行但取不到属主范围 ⇒ 无终答。沙盒那 252 枚合成标签只证行为、不证客户隔离，今天这 4 枚是**同一根缺口的真机读数**，且它是 `hitl` 桶里那 18/105 的一部分。治它的是业主侧 A1（回填 `users.department`）＋ A3（密级标签）＋ H13 裁定，不是新代码——R400/R409 两笔都已在树上。


## 逐格读数（每行都带 `caliber=cloud-shape`，源件 `readouts-cloud-shape.jsonl`）

### 段 `run11c-p1-sync-105`

| 格 | 值 | 注 | 出处 |
| --- | --- | --- | --- |
| `frame_shape` | `{"corrective_replacements": 51, "criterion_two_holds": 88, "extra_chars": 4, "last_frame_covers_answer": 101, "max_stream_frames": 104, "missing_chars": 4, "prefix_breaks": 64, "text_frames": 104, "uncorrected_breaks": 13}` | 每格值＝满足该条件的题数（n=105）；>1 那两格取的是帧数大于一的题数 | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c-frames.jsonl` |
| `event_surface` | `{"completed_present": 105, "done_present": 105, "failed_event_present": 4, "headline_present": 49, "hitl_present": 19, "sources_present": 105}` | 每格值＝流内出现过该事件的题数（n=105） | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c-frames.jsonl` |
| `queue_readback` | `{"queue_keys_present": 0, "queue_readable": 0, "queue_status_class": "not-exercised"}` | 相 1 载荷不声明档位，报告题也走同步道：逐枚 queue 键数全为 0 ⇒ 这一层**没被量到**，不是量了不过 | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c-frames.jsonl` |
| `usage_fields_present` | `{"usage_keys": [], "usage_slots_present": 0}` | usage 只住在队列可读面响应体里；同步道不采该载荷 ⇒ 在场枚数 0 属量具口径 | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c-frames.jsonl` |
| `approval_gate_shape` | `{"approval_rounds": {"1": 19}, "approved": 19, "hitl_rounds": 19}` | approval_rounds／approved 取形状；带审批轮的墙钟合计属时延类，不在本段 | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c.jsonl` |
| `escalation_annotation` | `{"cache_annotation_present": 0, "refused_escalation": 0, "scope_class": "not-instrumented"}` | 越权拒答与缓存标注的正解落点在 scope 题的判定，本段只报量具真读到的：帧账里没有 scope_class 列 ⇒ 该格本窗不出数 | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c-frames.jsonl` |
| `retry_sentinel_shape` | `{"attempt": {"1": 105}, "attempt_max": 1, "retry_count": 0, "sentinel": 4}` | attempt 枚数与哨兵触发与否；哨兵那 4 枚全部落在 approval_failed 上，不是重试 | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c.jsonl` |
| `answer_shape` | `{"answer_chars_bucket": {"1-199": 28, "1000-1999": 18, "200-499": 23, "500-999": 34, ">=2000": 2}, "answer_nonempty": 105, "kind": {"approval_failed": 4, "approved_ok": 15, "ok": 86}}` | kind 归类与答案空不空；answer_chars 只按桶报，字符数数值属必须本机那一格 | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c.jsonl` |
| `citation_shape` | `{"citation_class": {"absent": 56, "present": 49}, "citations_present": 49, "sources_shape": "sync-lane"}` | 引用只报在不在（evidence_n>0 的题数）；条数数值另立必须本机的一格 | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c.jsonl` |
| `error_class_shape` | `{"approval_http_status": {"200": 4}, "failure_class": {"owner_has_no_department_scope": 4}}` | 失败归类：4 枚 approval_failed 的原文都是「approve 200 仍无终答：artifact owner must have a department scope」⇒ 这是生产部门标签为空那一格（格③／A1）在现场的落点，HTTP 全 200 | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c.jsonl` |

### 段 `run11c-p2-queue-12`

| 格 | 值 | 注 | 出处 |
| --- | --- | --- | --- |
| `queue_readback` | `{"queue_keys_present": 12, "queue_readable": 12, "queue_status_class": {"answered": 4, "awaiting_approval": 8}}` | 队列道第一次真走通：12/12 都从轮询面读回终态，逐枚 queue 键数 10 | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c-p2-frames.jsonl` |
| `usage_fields_present` | `{"usage_keys": ["authoritative", "calls_missing_token_readout", "calls_with_token_readout", "completion_tokens", "ledger", "model_calls", "prompt_tokens", "token_readout_complete", "total_tokens"], "usage_slots_present": 12}` | 只报六枚槽在不在场；槽里的 token 数属必须本机那一格 | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c-p2-frames.jsonl` |
| `frame_shape` | `{"criterion_two_holds": 0, "extra_chars": 4, "max_stream_frames": 0, "missing_chars": 0, "prefix_breaks": 0, "text_frames": 0, "uncorrected_breaks": 0}` | 报告档入队后同步流只交 queued+done 两帧：text_frames 全 0/1 是队列道的形状，不是缺字 | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c-p2-frames.jsonl` |
| `event_surface` | `{"done_present": 12, "sources_present": 8}` | 队列道流内事件面：挂起审批走轮询面，不在这条 SSE 里 ⇒ hitl_present 0 是形状不是缺事件 | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c-p2-frames.jsonl` |
| `approval_gate_shape` | `{"approval_rounds": {"1": 8}, "approved": 8, "hitl_rounds": 8}` | 12 枚里 8 枚触发审批并批准到货，4 枚免批直接读回 | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c-p2.jsonl` |
| `retry_sentinel_shape` | `{"attempt": {"1": 12}, "attempt_max": 1, "retry_count": 0, "sentinel": 0}` | 零重试零哨兵：attempt 全 1、sentinel 全假 | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c-p2.jsonl` |
| `answer_shape` | `{"answer_chars_bucket": {"1-199": 2, "1000-1999": 6, "200-499": 1, "500-999": 3}, "answer_nonempty": 12, "kind": {"queued_approved": 8, "queued_polled": 4}}` | kind 归类与在不在；字符数数值不在本段 | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c-p2.jsonl` |
| `citation_shape` | `{"citation_class": {"absent": 4, "present": 8}, "citations_present": 1, "sources_shape": "structured-terminal"}` | 终态载荷里的 sources 在不在（3 枚 ev=0 的题从终态读回 sources_present 假，见 note） | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c-p2-frames.jsonl` |
| `error_class_shape` | `{"approval_http_status": {}, "failure_class": {}}` | 本窗没有失败归类：零枚 request.failed、零枚 approval_failed | `docs/perf/raw/run11c-2026-10-01/sidecar-run11c-p2.jsonl` |

## 本窗没量到的（欠账清单，逐项点名）

- A① 时延（整表 p50/p95 与问答档口径）、A③ 吞吐与改写腿耗时 —— 欠一扇安静 GPU 的本机全量窗。
- A④ correctness／evidence／逐类分／`unsupported_claim_rate`／`total_score` —— 同上；`evidence_n` 与 `answer_chars` 的**数值**也在这一族，本窗只报在不在与桶。
- `context_limit_exceeded_count` —— 本窗把 `MODEL_CONTEXT_TOKENS` 抬到 8192，这一格在云端窗里必然不可比（在册表把它列在必须本机那一侧）。
- C 门越权拒答与缓存标注 —— 量具帧账里没有 `scope_class` 这一列，本段如实写「未instrumented」，不拿形状格冒充。
- E 环境矩阵 E1–E6、浏览器九环走查 —— 与本窗无关，仍旧是 0。

## 证据件（逐枚 sha256 现取）


- `answers-run11c-p2.jsonl` ｜ 192828 字节 ｜ `sha256=69e9c7049a57b783`
- `answers-run11c.jsonl` ｜ 932409 字节 ｜ `sha256=e5a947c638fba280`
- `corpus_after.csv` ｜ 15340 字节 ｜ `sha256=105e230d0905ae8a`
- `corpus_before.csv` ｜ 15340 字节 ｜ `sha256=105e230d0905ae8a`
- `fixture-report12.jsonl` ｜ 4019 字节 ｜ `sha256=a9af15ea81c2bcec`
- `readouts-cloud-shape.jsonl` ｜ 7106 字节 ｜ `sha256=330dc4acfaa0a5e1`
- `run11c.out` ｜ 238 字节 ｜ `sha256=b6fab9c77af3a72b`
- `run11c_p2.out` ｜ 209 字节 ｜ `sha256=38f61e9d11afdc3d`
- `sidecar-run11c-frames.jsonl` ｜ 606289 字节 ｜ `sha256=ce0696efca7f2dc5`
- `sidecar-run11c-p2-frames.jsonl` ｜ 33210 字节 ｜ `sha256=9925f9e714f75f60`
- `sidecar-run11c-p2.jsonl` ｜ 4300 字节 ｜ `sha256=e062e19a176c8080`
- `sidecar-run11c.jsonl` ｜ 63359 字节 ｜ `sha256=b2ebefe362f7fb52`
