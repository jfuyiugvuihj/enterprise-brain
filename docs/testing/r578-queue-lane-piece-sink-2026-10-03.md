# R578 · 队列道「逐字片段」第一次有可注册点＋失败终态与原因码（V2 #8/#22 那半格）

派工词：R578｜代号 Lamark｜基点 `b85c277`｜工作树 `C:\Users\fengx\PycharmProjects\be-r578`。
写域：`deploy/queue_worker.py`（只动 `_drain_report_stream` 及其直接调用签名那一小段）
＋ 新钉 `tests/test_r578_*.py` ＋ 本纸 `docs/testing/r578-*.md`。
`docs/api/contract-v1.md` **未追加**：本单交回的两枚原因码（`internal_error`、`context_limit_exceeded`）
都在 `ErrorEnvelope.code` 的封闭枚举里，且都在契约里已有出处（前者＝兜底，见 `app/agents/contracts.py:638`
的注释「放在 internal_error 之前：兜底码留在最后」；后者＝R30 的 `CONTEXT_LIMIT_CODE`，
`tests/test_error_code_vocabulary.py::RATIFIED` 点名 `app/common/model_budget.py`）。派工词里那句
「要新增码就必须同笔在契约尾追加」这一支**没触发**——没有新码，也没有借一枚听起来像的旧码。

## 0. 盘面（`git -C C:\Users\fengx\PycharmProjects\be-r578 diff --numstat` ＋ 未跟踪清单）

| 文件 | 状态 | 增/删 | 现取 sha256（工作树字节，CRLF） |
| --- | --- | --- | --- |
| `deploy/queue_worker.py` | 修改 | `+11 / -0` | `9a29a5990f240dc366bbf493a5fe81aa614bb592750eaf7caab0f40f80b5bc07` |
| `tests/test_r578_queue_lane_reports_the_failure_terminal.py` | 新钉 | 未跟踪 | `53f2da9a0f7042bf55c98a5272b364e7baf278f89cfd020934329de7053ed924` |
| `tests/test_r578_counter_evidence_teeth.py` | 反证刀 | 未跟踪 | `6d642d066b4ddd0f852fb986f9453dc5b457f899aba1189a27d752781e6178fc` |
| `docs/testing/r578-queue-lane-piece-sink-2026-10-03.md` | 本纸 | 未跟踪 | （自指不落在自己纸上——交给总控落账） |

改后 worker 的 sha256 与 R548 §7.1 台账里那两枚历史指纹（`03be6d53…`＝R548 进门；`905d3a58…`＝R558 现读）**逐字节不同**。
R548 那枚在册钉 `test_z9c_the_worker_bytes_match_the_number_written_on_paper` 拿盘面 sha 对纸——本单动过
`deploy/queue_worker.py`，那枚钉按口径必须补一行 10-03 现读；§5.1 与 §6 里都点破了这一笔连带账的
落法（照 R558 先例：原样留着上一枚历史指纹，只**追加**新的一行，不改写上一行）。
连带账的执行落点：`docs/testing/r548-queue-lane-piece-sink-registration.md` §7.1 表格末尾**加一行**，
上面两行字节数一字不动。这一格在本单写域外，**交总控落笔**，本单不自行动别人的纸；`test_z9c` 在
本单交回时是**未复绿**的一枚（红话与 sha 现取一并交回 §5.2），不谎称它绿。

## 1. 事实源与判据口径

- `docs/handoff/2026-09-30-v2-gap-recheck-3.md` §6 那一行 R545：注册点在 `_drain_report_stream`，
  `stream_piece_sink` 该文件今天已经**有命中**（R548 并树 `5830422` 起了头，R558 又给它 `+121/-5`）——
  与本派工词开头那句「零命中」的**改派前事实**已经漂开；漂开的账本席归 R548/R558 两笔并树，本席只按今天盘面走。
- `R524` 那一格按实交回 `not_applicable` 带凭据；本席不改写、不翻绿（凭 `tests/test_r524_queue_lane_sends_no_second_character.py`
  那枚在册负向钉，sha `8f22e08c7873d105a6b3bd07094d8f7b2902232fe28ebbdf4ef49a250c8f347f` 未动）。
- 台账 `scripts/audit_plan_ticket_ledger.py:283` R37 = `PARTIAL`，本单动的是它「③ 终态原因码」那一半的
  **可重量前置**：改前那一步只在返回三元组里交一句 `stream_error`，改码发生在最外层的
  `report_failure_record()`——本单让**那一步自己**能交出记录，注册点收到的是同一条改码路径的原样产物，
  与最外层调用者事后自己叫一次**逐字节同**（`report_failure_record` 一函数一实现，两半共用同一把尺）。

## 2. 五格逐格读数（达·未达·差哪条）

| 判据 | 结论 | 凭据（点名到符号，不抄行号——行号会漂） |
| --- | --- | --- |
| ① 注册点真存在且真被叫 | **达**：`_drain_report_stream` 收 `stream_piece_sink`（R548 已有）；本单新钉 `test_the_piece_sink_receives_pieces_that_line_up_with_the_final_answer_prefix` 走真 `nodes.publish_stream_pieces`＋真 `nodes.StreamPieceMerger`，切分尺**读自** `nodes.STREAM_PIECE_MIN_CHARS`（不写死数字），拿到 `ledger.count > 1`、逐片 `len(piece.text) >= STREAM_PIECE_MIN_CHARS`（除最末）、`ANSWER.startswith(ledger.joined_text())`；`test_a_partial_run_still_aligns_as_a_strict_prefix` 再把「截在半路」那一格钉死成严格前缀。 |
| ② 默认零回归 | **达**（在册邻件两态同名集同数；见 §3）：`report_failure_sink=None` 缺省时，`_drain_report_stream` 的返回值 arity 与内容一格没动（`test_the_failure_sink_default_none_returns_the_same_three_tuple`）；错误分支上仍旧只交三元组、第三值就是那句 `stream_error`（`test_the_failure_sink_default_none_still_hands_the_error_string_back`）；成功分支上 sink 一次也不叫（`test_the_success_path_never_calls_the_failure_sink`）；worker 与 `ENUM_CODES` 交集仍旧 `= {internal_error}`（`test_the_worker_still_hands_over_no_new_stable_code_literal`，尺借自 R548/R81 两枚在册钉）。 |
| ③ 失败有终态与具名原因码 | **达**：`test_the_failure_sink_receives_the_record_when_the_lane_falls_over` 交出 `record["status"] == "failed"` ＋ `record["error"]["code"] == "context_limit_exceeded"` ＋ 那条 `CONTEXT_ERROR_FRAGMENTS` 尺认得出**在册**的片段才交这个码；认不出的那一发（`test_the_failure_sink_falls_back_to_internal_error_when_nothing_matches`）落回 `internal_error`；两枚都在 `ErrorEnvelope.code` 里，`ErrorEnvelope(code=..., message=...)` 直接构造得起来。R448 那一族（`test_the_deterministic_refusal_still_marks_the_record_non_retryable`）：认回白名单 ⇒ 记录里补 `retryable: False`，`is_non_retryable_error(record) is True` 同读。sink 一轮只叫一次（`test_the_drain_hands_one_record_per_failing_round_not_two`），第二枚 error 事件覆盖 `stream_error`（既有语义），注册点仍旧只交最末一发 ⇒ 不出现第二套口径。 |
| ④ 反证 ≥3 把 | **达**（三把，见 §5 台账）：K1 摘交给片段汇那一手 ⇒ 本单纯净新钉红（victim＝`test_the_piece_sink_receives_pieces_that_line_up_with_the_final_answer_prefix`）；K2 把 worker 里 `"internal_error"` 字面量整批换成字典外一枚 ⇒ **在册**交账钉红（victim＝R548 `test_the_worker_still_hands_over_no_new_stable_code` 与 R81 `test_the_reason_token_is_not_a_stable_error_code` 两枚同名集，同一把 `ENUM_CODES` 尺）；K3 把 `_drain_report_stream` 的默认从 `None` 换成"总是建 sink" ⇒ **在册**默认零改钉红（victim＝R548 `test_a_direct_drain_that_hands_over_nothing_adds_not_a_single_key`）。三把都配正控，摘前摘后各核一次 sha256。 |
| ⑤ 诚实边界 | **达**：见 §4 那一节原文。 |

**未达格 = 零枚**。差的那半条不写在本单账上：R545 那一行点名的另一格「队列道逐字片段的真机读数」
**没交**，本单**也不交**——见 §4。

## 3. 邻件点名清单与改前改后两态数

`deploy/queue_worker.py` 的动法只有一处：`_drain_report_stream` 加一枚 kw-only `report_failure_sink=None`，
函数末尾加一条 `if stream_error and report_failure_sink is not None: report_failure_sink(report_failure_record(stream_error))`。
`run_with_stream` 的关键字集合、`configurable` 的键集、返回三元组的 arity 与内容都一格未动。
邻件口径：凡在源文里扫 `queue_worker.py` 结构、或把 `_drain_report_stream` 直接叫一发的在册件。

| 邻件（相对路径） | 改前（`b85c277` 未叠本单） | 改后（叠本单） |
| --- | --- | --- |
| `tests/test_r548_queue_lane_registers_the_piece_sink.py` | `16 passed / 0 failed` | `16 passed / 0 failed` |
| `tests/test_r548_counter_evidence_teeth.py` | `17 passed / 0 failed` | `16 passed / 1 failed`（`test_z9c_the_worker_bytes_match_the_number_written_on_paper`；见 §5.2 红话与连带账落法） |
| `tests/test_r524_queue_lane_sends_no_second_character.py` | `10 passed / 0 failed` | `10 passed / 0 failed` |
| `tests/test_r524_counter_evidence_teeth.py` | `19 passed / 0 failed` | `19 passed / 0 failed` |
| `tests/test_r524_sink_reaches_both_runways.py` | `5 passed / 0 failed` | `5 passed / 0 failed` |
| `tests/test_r37_report_lane_worker.py` | `23 passed / 0 failed` | `23 passed / 0 failed` |
| `tests/test_r81_queue_terminal_retry.py` | `26 passed / 0 failed` | `26 passed / 0 failed` |
| `tests/test_r448_deterministic_refusal_no_retry.py` | `25 passed / 0 failed` | `25 passed / 0 failed` |
| `tests/test_error_code_vocabulary.py` | `20 passed / 0 failed` | `20 passed / 0 failed` |
| `tests/test_r558_queue_lane_pieces_reach_the_polling_surface.py` | `15 passed / 0 failed` | `15 passed / 0 failed` |
| `tests/test_r227_discard_is_honest.py` | `6 passed / 0 failed` | `6 passed / 0 failed` |
| **合计** | **`202 passed / 0 failed`** | **`201 passed / 1 failed`** |

改前改后各跑一遍的命令（同树、同解释器、同 `--basetemp`）：

```
C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe `
  -m pytest tests/test_r548_queue_lane_registers_the_piece_sink.py `
            tests/test_r548_counter_evidence_teeth.py `
            tests/test_r524_queue_lane_sends_no_second_character.py `
            tests/test_r524_counter_evidence_teeth.py `
            tests/test_r524_sink_reaches_both_runways.py `
            tests/test_r37_report_lane_worker.py `
            tests/test_r81_queue_terminal_retry.py `
            tests/test_r448_deterministic_refusal_no_retry.py `
            tests/test_error_code_vocabulary.py `
            tests/test_r558_queue_lane_pieces_reach_the_polling_surface.py `
            tests/test_r227_discard_is_honest.py `
  -q --basetemp=%TEMP%\r578bt13 --no-header
```

🔴 **不跑全量门**（同机三枚 Agent 在 `be-r573`/`be-r575`/`be-r577`；机器不安静；派工词明令）；
数字口径按派工词那句「同名集同数」，不引看板最新绿票的历史数字当尺。

## 4. 判据⑤：诚实边界（派工词点名原文）

🔴 **本节是原文，不许改写、不许摘要。**

> 本单只交注册点与离线证明，**队列道逐字片段的真机读数仍未取**，A②／D 门不许据此翻绿。

**要翻绿需要哪一扇窗、哪个开关、哪枚在册量具**（逐格点名，不发明第四件）：

- **窗**：run11 或后续同格的一次「安静机器重量」——参照 `docs/handoff/2026-09-30-v2-gap-recheck-3.md`
  §6 R545/R546 两行点名的 D 门窗口条件；同机在飞的 `be-r573`/`be-r575`/`be-r577` 三棵树全部并树之后，
  主树复跑一次 `python scripts/run_gate.py` 出门的最新绿票，才能另开。
- **开关**：`REPORT_LANE_VIA_QUEUE=on`（`deploy/.env.server` 那格；派工词点名）。这一开关走
  `docker-compose.yml` 里 `x-runtime` 那格 `env_file:`，容器创建那一刻才解析 ⇒ 翻默认要的是**容器重建**
  （`docker compose up -d --force-recreate`），不是镜像重建、也不是 `docker restart`。AGENTS.md 向量库
  那一节 P-8 已把这条钉过；本单**不动** `.env.server`，也不起容器、不重建容器、不打模型。
- **在册量具**：`scripts/r561_queue_lane_piece_readout.py`（`docs/testing/` 与 `docs/perf/raw/r561-*`
  两族凭据的**唯一**采集器；它自述"只读"、"量不到不等于干净"、"零新口径"三条纪律，退出码 2 不等于绿）。
  它的判据① 只交到「同进程真路由真载荷」那一半，容器那一遍**至今没跑过**——本单**不改**这句判定。
  配套在册钉：`tests/test_r561_readout_calibre_and_teeth.py` 现取推导那九枚 `stream_pieces` 键、三枚
  state、三枚 reason、五枚终态停表词、kind 名一律与上游同源。本单一次也没叫它。
- **失败原因码那一格**（判据③ 的另一半）：A②／D 门里的「失败→终态→带原因码可查」那一条真读数
  同样**欠一次真跑**，量具在 `scripts/eval_frame_caliber_readout.py` 与 `scripts/r239_stream_gap_offline_audit.py`
  两枚在册件——本单写域外，一枚也没碰。

**因此**：本纸里"注册点在／被叫／离线可测"三格达（§2）；「队列道接上了客户端那条流」那一格按实交回
`not_applicable`——R524 交工纸那一格一字未改，凭据 `tests/test_r524_queue_lane_sends_no_second_character.py::test_a_dead_registration_alone_does_not_read_as_connected_on_the_enqueue_lane`
（sha `8f22e08c7873d105a6b3bd07094d8f7b2902232fe28ebbdf4ef49a250c8f347f`）与 `tests/test_r548_queue_lane_registers_the_piece_sink.py` 同族两枚在册负向钉都在原位。

## 5. 判据④：反证刀三把 ＋ sha256 台账

### 5.1 三把刀的锚、victim、正控

| 刀 | 锚点（现取唯一） | victim（点名的在册或本单纯净新钉） | 正控 |
| --- | --- | --- | --- |
| **K1** | `        stream_piece_sink=stream_piece_sink,\n`（`_drain_report_stream` 里交给编排入口那一手） | `test_the_piece_sink_receives_pieces_that_line_up_with_the_final_answer_prefix`（本单纯净新钉；派工词点名形状①） | `k1_control`：同套机械不摘刀 ⇒ 本单纯净新钉先绿一遍 |
| **K2** | `"internal_error"` × N（`report_failure_record` 兜底字面量，本单整批换成字典外一枚；命中数现取，不写死） | ① R548 `test_the_worker_still_hands_over_no_new_stable_code`；② R81 `test_the_reason_token_is_not_a_stable_error_code`（同一把 `ENUM_CODES` 尺；派工词点名形状② ⇒ "契约对账件的牙"） | `k2_control`：源文不动 ⇒ R548 交账钉先绿一遍 |
| **K3** | `    stream_piece_sink=None,\n`（`_drain_report_stream` 形参默认那枚） | R548 `test_a_direct_drain_that_hands_over_nothing_adds_not_a_single_key`（默认零改在册钉；派工词点名形状③） | `k3_control`：同套机械不摘刀 ⇒ R548 默认零改钉先绿一遍 |

摘刀只作用在内存影子，仓里一字节不动；每一把进刀前后各核一次被跟踪件的 sha256。
`tests/test_r578_counter_evidence_teeth.py` 的 `test_z9`／`test_z9b` 是两枚总清点：三把都真摘过、
点名的 victim 全真咬红、被跟踪件仍是进门那一刻的字节、影子散件不落仓。三把＋两枚总清点＋三枚正控
= **8 用例 / `8 passed / 0 failed`**。

### 5.2 唯一在册件红话（本单一手现取，不谎称绿）

```
FAILED tests/test_r548_counter_evidence_teeth.py::test_z9c_the_worker_bytes_match_the_number_written_on_paper
AssertionError: ('9a29a5990f240dc366bbf493a5fe81aa614bb592750eaf7caab0f40f80b5bc07', '交工纸里没有出现这枚 sha256')
```

这一格红的是**纸盘不一**：R548 §7.1 台账里 `deploy/queue_worker.py` 的现读那一枚还是 R558 时的
`905d3a58b6a15aec…`，本席给这枚件加了 `+11/-0` ⇒ 盘面 sha 变 `9a29a5990f240dc366bbf493a5fe81aa614bb592750eaf7caab0f40f80b5bc07` 前 12
（`9a29a5990f240dc366bbf493a5fe81aa614bb592750eaf7caab0f40f80b5bc07`）。按 R558 先例的正解：在 R548 §7.1 表格**加一行**"10-03 R578 之后的现读"，
上面两行字节数一字不动。R548 交工纸不在本单写域 ⇒ **交总控落笔**，本单不自行动别人的纸。
除此之外 `test_r548_counter_evidence_teeth.py` 其余 16 枚（含 10 把在册反证刀与 `test_z9`／`z9b`）全绿。

## 6. 台账（**现取**，进门指纹）

| 件（相对路径） | 字节 | 行 | CRLF | 单 LF | 现取 sha256 |
| --- | ---: | ---: | ---: | ---: | --- |
| `deploy/queue_worker.py` | 62023 | 1212 | 1212 | 0 | `9a29a5990f240dc366bbf493a5fe81aa614bb592750eaf7caab0f40f80b5bc07` |
| `tests/test_r578_queue_lane_reports_the_failure_terminal.py` | 13597 | 286 | 286 | 0 | `53f2da9a0f7042bf55c98a5272b364e7baf278f89cfd020934329de7053ed924` |
| `tests/test_r578_counter_evidence_teeth.py` | 15155 | 297 | 297 | 0 | `6d642d066b4ddd0f852fb986f9453dc5b457f899aba1189a27d752781e6178fc` |
| `tests/test_r548_queue_lane_registers_the_piece_sink.py`（本单**未碰**） | 26732 | 535 | 535 | 0 | `483cdd9269f0dd2f7a8bf7d96e7732e25eb4a30d186ddef1e613f5db77ca3c03` |
| `tests/test_r548_counter_evidence_teeth.py`（本单**未碰**） | 23583 | 434 | 434 | 0 | `3d6697ae3c5c480a5b24f2f900389e689316997c88a932fb099ab629e0e6ed39` |
| `tests/test_r524_queue_lane_sends_no_second_character.py`（本单**未碰**） | 20598 | 396 | 396 | 0 | `8f22e08c7873d105a6b3bd07094d8f7b2902232fe28ebbdf4ef49a250c8f347f` |
| `app/agents/nodes.py`（本单**未碰**） | 119332 | 2281 | 2281 | 0 | `4ec795203a0cfc552a5b95ba2059d9cd1455b46d9bf334708c4143c107611e8b` |
| `app/agents/orchestrator.py`（本单**未碰**） | 77792 | 1661 | 1661 | 0 | `36def47b87a9d2e67269e863e6f3b1c5cd197b9c9ff0675fdc4f0004d1dde822` |
| `app/api/v1/chat.py`（本单**未碰**） | 270099 | 5310 | 5310 | 0 | `8969a64ebc249a0758a85f59ee43bd26fb4c4056e251838148826496219babd6` |

`py_compile`（离线，产物写进 %TEMP% 不落仓）：两枚新件均过。解释器口径：`C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`（R56 宿主模型端口闸门在测试期间拦到 0 枚对 11434 的连接尝试；R134 工作树 Chroma 写回告警 0 枚）。

## 7. 未做与风险

- **投递面**：R548 那一半没做，本单也没做。入队那条 SSE 仍旧在两枚帧之后关，客户端读不到字；
  `queue_lane=not_applicable` 那一格一字未改。
- **真机读数**：见 §4 原文。三件（`REPORT_LANE_VIA_QUEUE=on`＋安静机器＋`scripts/r561_queue_lane_piece_readout.py`）
  本单一件都没起、没开、没叫。
- **R548 交工纸 §7.1 sha 台账**：`test_z9c` 因此**未复绿**（红话见 §5.2）。连带账的落法在本纸 §0/§5.2 明写；
  执行落在 `docs/testing/r548-*.md` §7.1 的表格**追加一行**——R548 交工纸不在本单写域，**交总控**落笔，
  本单**未**代笔别人的纸。
- **契约尾追加**：本单**未做**，因为没新码（§0 已点名两枚在册出处）。若总控判"队列道失败汇"这一形状
  该独立入契约，那是 R523 写域（`docs/api/contract-v1.md`）之外的另议，不属本单。
- **全量门**：**未跑**（同机三枚在飞；机器不安静；派工词明令"不许跑全量门"）。§3 那张 202/201 的
  两态表是本单唯一交回的回归读数，按派工词口径「同名集同数」对判，不拿它替代 `run_gate.py`。
