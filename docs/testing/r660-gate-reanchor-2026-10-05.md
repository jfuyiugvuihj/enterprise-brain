# R660 · 全量门 46 枚派生坐标漂移红的重锚凭据（2026-10-05）

> 席位：执行层 **Sadi**（R660）｜基点：`8a52c5c`｜工作树：`C:\Users\fengx\PycharmProjects\be-r660`（主树对本席只读）
> 本文数字一律是「执行层自报」——由本席于 2026-10-05 10:2x–11:4x（Asia/Shanghai）亲跑取回，未代总控签字。
> 先例：主树 `eaac6da`「坐标重锚（总控亲修）」。本单同一口径：**只走各量具自己印在红句里的出路，零手算加减行号、零手抄数字**。

## 0 一句话

46 枚派生坐标漂移红全部重锚回派生源；同名 10 枚件由 `46 failed / 164 passed` 变 `210 passed / 0 failed`，两态（apply 未 commit / 干净检出复跑）同数；`tests/test_r149_sse_text_pieces.py` 那一枚本席一枚没碰，仍归总控单独判。

## 1 差账（判据①）

| 族 | 起点枚数 | 治掉 | 剩 | 红名分布（= 派工词【红清单】逐枚同名） |
| --- | --- | --- | --- | --- |
| r460 | 21 | 21 | 0 | `run9_coordinates_are_derived` 11／`hand_fudged_numbers_and_wrong_layers_both_redden` 9／`a_blank_line_above_the_backed_files_reddens_both_cells` 1 |
| r455 | 11 | 11 | 0 | `gapdoc_coordinates_are_derived` 8／`hand_fudged_numbers_and_wrong_layers_both_redden` 3 |
| r387＋r492＋r400 | 10 | 10 | 0 | `r387_label_ruler_teeth` 7／`r492_s93_column_matches_derived` 2／`r400_derived_ledger_shift_and_silence_pins` 1 |
| r483 | 2 | 2 | 0 | `r483_empty_table_triage_is_derived` 2 |
| r469 | 2 | 2 | 0※ | `r469_readout_is_generated` 2（🔴 根因不是坐标漂移，且绿带复发条件，见 §2.5／§10） |
| **合计** | **46** | **46** | **0** | 无剩余族、无卡前置 |

- 起点 46 枚＝全量门 47 枚红剔掉 `tests/test_r149_sse_text_pieces.py::test_piece_frames_reach_the_wire_while_the_run_is_still_open`（本单不许碰，树态/负载相关，已归总控）。
- 本席**没跑全量门**（禁区），逐件一律 `python -B -m pytest -p no:randomly -q`。

## 2 逐族出路与读数（判据②）

### 2.1 r460 族（21 枚）·纸面 `docs/testing/run9-readout-2026-09-28.md`

- 出路：`python -B scripts/r460_run9_coordinates.py --land` rc=0（锚腐时它自己拒写）
- 复验：`python -B scripts/r460_run9_coordinates.py --check` rc=0｜`--bytes` rc=0 → `{"size": 36650, "crlf": 260, "bare_lf": 0, "lone_cr": 0, "replacement_char": 0}`（收尾现跑复验同数）
- 漂的只有一格：`C1 缓存命中` `scripts/eval_transport_ask_v2.py:1322-1325` → `:1596-1599`（余格由 `--land` 现取逐字节重写，本席未手改任何一格）
- 族件复跑（3 枚件，分段亲跑）：**78 passed / 0 failed / rc=0**

### 2.2 r455 族（11 枚）·纸面 `docs/handoff/2026-09-26-v1-frontend-gap-list.md`

- 出路：`python -B scripts/r455_gapdoc_coordinates.py --emit-doc-cells` rc=0 出成品串，再由量具自带的落地函数机械重写那 5 格（本席零手抄）
- 现读：`upload_form=app/api/v1/chat.py:4647`、`queue_cancel=app/api/v1/chat.py:5456`、`sessions_route=app/api/v1/chat.py:4149`
- 旧→新：`4507→4647`／`4009→4149`／`5316→5456`（历史表里那枚手抄 `chat.py:3933` 属冻结账，未动）
- 复验：`python -B scripts/r455_gapdoc_coordinates.py --check` rc=0 → 「缺口单行内引用逐字节等值 **5／5** 枚」（收尾 state①／state② 两态各现跑一次，均 rc=0）
- 族件复跑（2 枚件，分段亲跑）：**27 passed / 0 failed / rc=0**

### 2.3 r387＋r492＋r400 族（10 枚）·同一枚血缘纸 `docs/perf/r387-label-lineage-2026-09-27.md`

- 出路：`python -B scripts/r387_label_lineage.py --no-db --emit-doc-cells` rc=0（12 行成品串、零 ABORT；本族不需连库，未走容器那条路）
- 机械重写共 **19 处**＝§1 血缘表 6 格＋表下正文 1 枚＋§9.3 末列 12 枚（现取核过：diff 12 行、逐行数字格 1/1/1/5/4 分落在 715–719）
- §1 现读：`chat.py:4506-4508→4646-4648`／`:4524→:4664`／`:4507→:4647`／`:4080-4164→:4220-4304`／`:4211-4259→:4351-4399`／`:4648-4654→:4788-4794`
- 表下正文：`chat.py:1153→:1268`（配对由 `HOP_DOC_CELLS[6]` 模板反解＋`resolve_site('hop6n')` 取今值）
- §9.3 末列：`:1124-1159→:1239-1274`／`:1142→:1257`／`:1153→:1268`／`:4652→:4792`／`:4666→:4806`／`:4680→:4820`／`:4755→:4895` 等 12 格
- 🔴 收尾复核揪出一枚施工瑕疵：表下正文那一行（第 69 行）落地时留了 192 B 重复尾巴（多复制出 4 枚幻影坐标，`catalog.py:647`／`catalog.py:762`／`retriever.py:1685`／`pg_store.py:373`），已就地剪回单份；那一格的值仍是量具现读的 `chat.py:1268`（本席现核该行＝`department or None,`），零手算
- 族件复跑（3 枚件，分段亲跑）：**68 passed / 0 failed / rc=0**

### 2.4 r483 族（2 枚）·生成物 `docs/testing/r483-empty-tables-2026-09-29.md`

- 出路：`python -B scripts/r483_empty_tables_triage.py --sync` rc=0 → `synced ... bytes=30175 problems=0`；复验 `--check` rc=0 → 「PASS check：八枚表 + 两枚对照 + 现扫写入点全部逐字节复现，problems=0」（收尾两态各现跑一次，均 rc=0）
- 🔴 取数路：该量具的取数口本身就是 `docker exec enterprise-brain-postgres-1 psql`（`scripts/r483_empty_tables_triage.py:123`），从不 host 直连——所以 host 跑 `--sync` 读到的是真库现数，不需要在容器里改仓；容器里缺 `docs/`（`--probe` 落点）与 `tests/`（`SourceIndex` 扫根），现读 247 枚 vs 本树 941 枚，故走 host。
- 族件复跑（1 枚件，分段亲跑）：**22 passed / 0 failed / 134.08 s / rc=0**
- 判据③「只消漂移不改事实」：读数随真库走，旧数原样留在 §6 修订账里。

### 2.5 r469 族（2 枚）·生成物 `docs/testing/r469-sandbox-scope-readout-2026-09-28.md`（🔴 这族不是坐标漂移）

- 红句第一断言（表 vs 证据）本就过；炸的是 `raw == markdown.encode("utf-8")` 与 `b"\r" not in raw`——盘上那份是 CRLF，生成器出的是 LF。
- 根因（现取）：`git config --show-origin core.autocrlf` → `file:C:/Program Files/Git/etc/gitconfig true`；仓内无 `.gitattributes`；`git ls-files --eol` 交 `i/lf w/crlf` ⇒ checkout 把 LF 生成物落成 CRLF，这枚钉结构性红，与 R649／R653／R647 插行无关。
- 出路（走量具唯一出表口）：`python -B scripts/r469_readout_lib.py render --evidence <由 tests/test_r469_sandbox_scope_matrix.py::extract_evidence 现取的证据 JSON> --out docs/testing/r469-sandbox-scope-readout-2026-09-28.md` rc=0
- 复验：`python -B scripts/r469_readout_lib.py validate --readout docs/testing/r469-sandbox-scope-readout-2026-09-28.md` rc=0 → 「[过关] 状态 SANDBOX_MEASURED_PRODUCTION_UNVERIFIED｜有牙格 5 枚｜未过判据 4 条」（收尾 state①／state② 各现跑一次，均 rc=0）
- 落地后盘上那份与 HEAD blob **逐字节同**（`git diff` 零行、`git status` 只报 eol 假脏）⇒ 这 2 枚靠「重新出表＋checkout 侧不再引入差异」收口，货面唯一差是 eol 归一。
- 🔴 未跑 `--mode full`（会覆盖 6 档现读数＝改事实，且本病不在读数层），也没拿 `preflight` 冒充 `full`。
- 🔴 **※复发条件（现取）**：`git check-attr --all -- docs/testing/r469-sandbox-scope-readout-2026-09-28.md` 交空（仓内无 `.gitattributes`），index/HEAD blob＝`i/lf`，本机 `core.autocrlf=true` ⇒ 任何一次干净 checkout 都会把它落成 `w/crlf`，这 2 枚随之回来。本货对它**没有内容差可带**，所以这 2 枚的绿属「盘上那份此刻是 LF」，不计入「并树即绿」的保证——治它只有 §10 那三条。
- 族件复跑（3 枚件，分段亲跑）：**51 passed / 0 failed / rc=0**

## 3 基线对照（影子端正控·收尾现跑）

- 构造：`git worktree add --detach %TEMP%\eb104\r660\state2b 8a52c5c` 干净检出，再把 5 枚纸面 `git checkout --` 退回 HEAD（porcelain 零行），跑同名 10 枚件。
- 读数：**46 failed / 164 passed / 147.36 s / rc=1**
- 红名逐枚比对 `%TEMP%\eb104\gate-reds-47.txt` 去掉 r149 后的 46 枚：**两集合全等**（symdiff 0），逐文件分布＝r460 21／r455 11／r387 7＋r492 2＋r400 1／r483 2／r469 2，与派工词【红清单】一致。

## 4 两态数字（判据④·收尾现跑）

| 态 | 构造 | 命令 | 读数 |
| --- | --- | --- | --- |
| state① | `be-r660` apply 未 commit（5 枚纸面为工作树改动） | `.venv\Scripts\python.exe -B -m pytest -p no:randomly -q <同名 10 枚件>` | **210 passed / 0 failed / 155.65 s / rc=0** |
| state② | 干净检出 `8a52c5c` ＋ 叠上同一批 5 枚货（投货前 porcelain 零行） | 同一命令、同名 10 枚件 | **210 passed / 0 failed / 158.28 s / rc=0** |

- 红逐枚同名＝空集对空集；总测试数 210 与 §3 基线 46＋164＝210 闭合。
- 构造口径：state② 的影子树是 `git worktree add --detach … 8a52c5c` 干净检出，再把 5 枚货**按字节覆盖**进去（投货前 porcelain 零行）；其中 r469 那枚与 HEAD blob 逐字节同，它的绿取决于覆盖后的 LF，见 §2.5 复发条件——那一格请总控按 §10 治本，别指望这枚货带上它。
- state② 影子树内另核 5 枚量具自检：`r455 --check`／`r460 --check`／`r460 --bytes`／`r483 --check`／`r469 validate --readout` **全 rc=0**，`--bytes` 与 state① 同数。
- 先试 `git archive` 导 `%TEMP%\eb104\r660\state2` 那一版**不可用作 state②**：无 `.git` 导致 16 枚 `fatal: not a git repository` 陪红（归因＝导出面缺 git，非货有病），故改 `git worktree add --detach`。
- 并树自毁面：这 10 枚件只读固定旧号（`2154318`／`49555eb`）与 `git show HEAD:scripts/r387_label_lineage.py`（该脚本本单未动），无一把「此刻盘面脏不脏」当判据；本席树内无一枚盘面探针。
- 🔴 总控并树后请在**真 HEAD** 复跑同名 10 枚件坐实第二遍（本席无权 commit）。

## 5 邻件回归（读这五枚纸面的其余件·收尾现跑）

`rg -l -g tests/*.py -g scripts/*.py <五枚纸名>` 全仓点齐，取其中 14 枚非本族件：
`test_r404_version_history_judges_before_it_lists`／`test_r467_delivery_gate_classification_item`／`test_r387_production_label_leg`／`test_r398_three_guard_ledgers`／`test_r409_plan_table_is_derived`／`test_r414_a_department_free_upload`／`test_r490_live_reads_match_derived`／`test_r493_checked_scope_narration`／`test_r493_s96_ask_entry_is_history_not_live_claim`／`test_r456_single_frame_shape_is_not_a_pass`／`test_r536_retrieval_completed_on_product_lane`／`test_r550_counter_evidence_teeth`／`test_r550_event_hop_climb_is_generic`／`test_r597_verdict_vocabulary_has_one_source`

- 读数：**155 passed / 1 xfailed / 0 failed / rc=0**（施工期现跑 299.41 s；§2.3 瑕疵剪回后本席**同集合复跑＝155 passed / 1 xfailed / 302.65 s / rc=0**，零回归；那枚 xfail 是在册件自身口径，与本单无关）

## 6 r483 旧读数留账（判据③）

| 格子 | 旧数（并树前纸面） | 今数（`--sync` 现读） |
| --- | --- | --- |
| `alerts` | 8 | 12 |
| `retrieval_traces` | 1033 | 1948 |
| `sessions` | 1636 | 2280 |
| `pending_approvals` | 290 | 427 |
| `evaluate_all` | 23 | 97 |
| 写入点坐标 `chat.py` | 2484／3426／2708／3475 | 2599／3556／2823／3605 |
| 写入点坐标 `observability.py` | 528 | 529 |
| 对照表其余行 | 24281／6284／6283／5569／1832／1818／1745／1692／1552 | 32533／8735／8734／7157／2604／2589／2515／2468／2186 |

## 7 交付清单（收尾现取）

| 路径 | 行数 | 字节 | eol | 本单 diff |
| --- | --- | --- | --- | --- |
| `docs/handoff/2026-09-26-v1-frontend-gap-list.md` | 369 | 80971 | CRLF | 5/5 行（5 枚行内坐标） |
| `docs/perf/r387-label-lineage-2026-09-27.md` | 948 | 101269 | CRLF | 12/12 行（19 处数字格） |
| `docs/testing/run9-readout-2026-09-28.md` | 261 | 36650 | CRLF | 1/1 行 |
| `docs/testing/r483-empty-tables-2026-09-29.md` | 301 | 30175 | LF（生成器落盘） | 59/57 行 |
| `docs/testing/r469-sandbox-scope-readout-2026-09-28.md` | 7194 | 237481 | LF（与 HEAD blob 逐字节同） | 内容零差，仅 eol 假脏 |
| `docs/testing/r660-gate-reanchor-2026-10-05.md` | 156 | 18159 | CRLF | 新增凭据纸（本纸） |

## 8 铁规自证

- 零手算／零手抄：所有数字出自 `--land`／`--emit-doc-cells`／`--sync`／`render` 的成品串，本席未在任何纸面上加减行号或誊数。
- 零摘牙：未 skip／xfail／改断言；未动任何一枚钉的判据；未动 `app/**`、生成器本体、`tests/**`、`scripts/run_gate.py`、`pyproject.toml`、`deploy/.env.server`、`chroma_db/**`、`frontend/**`、他席在途件（`tests/test_r633_*`／`app/api/v1/observability.py`／`docs/api/contract-v1.md`／`app/rag/**`）。
- 未碰 `tests/test_r149_sse_text_pieces.py` 与 `tests/test_r269_index_state.py`。
- 未 commit／建分支／push／起服务／重建镜像／打模型／跑全量门。
- 口径钉：`python -B scripts/check_vector_wording.py` rc=0 → 「向量库口径钉：39 枚文档全部通过」（本纸落盘后现跑，Chroma 只以退役中的遗留件身份出现在禁区清单那一行）。
- 交付字节体检：`0x00`／`0x07`／`0x08`／`0x0b`／`0x0c` 枚数＝0，`U+FFFD`＝0（含本纸）。
- 同刻纸面邻件抽查（含本纸在场）：`tests/test_r302_docs_utf8_guard.py`＋`tests/test_r597_verdict_vocabulary_has_one_source.py`＝**30 passed / rc=0**；`scripts/check_vector_wording.py` rc=0；`tests/test_r638_pointer_ratchet.py`＝**3 failed / 11 passed**（棘轮基线待总控重落，见 §11，非 46 枚之内）。
- 盘面自证（收席那一刻现取）：`git rev-list --count 8a52c5c..HEAD` ＝ **0**；staged＝**空**；工作树改动＝§7 那 5 枚纸面＋本纸 1 枚新增。

## 9 需总控复核的一格（禁区与铁规相撞）

- 派工词【不许做】把 `docs/handoff/**` 列为禁区，而【铁规】点名 r455 族的唯一出路是 `--emit-doc-cells` 重落地——那一格正长在 `docs/handoff/2026-09-26-v1-frontend-gap-list.md` 里；两条硬墙互斥。
- 本席取「各量具点名的纸面」这一更具体条（【写域】原文），只重写那 5 枚行内坐标，未动该纸任何别的格子；该纸不在他席写集（R657 走 `docs/api/contract-v1.md`，R658 走 `tests/test_r633_*`），无并发冲突。
- 若总控判它确实是硬墙：回退面＝`git checkout -- docs/handoff/2026-09-26-v1-frontend-gap-list.md`，差账变成「46 → 剩 11（r455 族）」，其余 35 枚不受影响。

## 10 留给下一格

- 总控并树后在真 HEAD 复跑同名 10 枚件（第二遍干净树，AGENTS.md 并树双跑口径）。
- r469 那 2 枚的**病根**不在纸面：本机 `core.autocrlf=true` ＋ 仓内无 `.gitattributes`，会让任何 LF 生成物在 checkout 侧被落成 CRLF。三条出路请总控择一（本席无权动仓配置）：① 主树重跑一次 `render`；② 给生成物加定向 `.gitattributes` `text eol=lf`；③ 把那枚字节钉改成归一化比对（改判据可以、摘牙不行）。
- `docs/testing/r483-empty-tables-2026-09-29.md` 的读数随真库走：下一次并树若再插行，`--sync` 会连数带坐标一起重写，别手改。
- r149 那一枚仍挂总控名下（同 sha 影子树五连绿、主树连红，判据未落）。
- 🔴 r638 指针棘轮的基线件要由总控在并树后一行命令重落，见 §11。
## 11 r638 指针棘轮的连带账（本单货带出的一格，非 46 枚之内）

- 现象：同名 10 枚件转绿之后，`tests/test_r638_pointer_ratchet.py` 反多出 **3 枚红**（`test_the_stored_baseline_matches_the_rulers_own_reading`／`test_no_markdown_file_grew_its_paper_coordinates`／`test_shrink_is_named_not_silently_forgiven`）。
- 归因：那把尺的棘轮基线 `docs/testing/r638-pointer-baseline.json` 登记的是**漂移前**的身份串。重锚把在册纸面的坐标身份整体换掉，其中 `docs/testing/r483-empty-tables-2026-09-29.md` 由 `--sync` 重生后枚数 75 → 77（生成器现扫多写入了两枚写入点，`--check` 逐字节 PASS，非手抄）；枚数一变多就进 `grew`＝红。尺自己的 `--check-baseline` 在这一形还会撞 `scripts/r638_doc_pointer_ruler.py:777` 那条自证 assert（`after-before` 与 `added-removed` 不等，因 17 枚是 1:1 换号、2 枚才是净增）。
- 出路只有一条（尺的唯一写口）：`python -B scripts/r638_doc_pointer_ruler.py --write-baseline docs/testing/r638-pointer-baseline.json`
- 本席实测（跑过一次即回退，交付里不含那件）：`--write-baseline` rc=0 → `written: docs/testing/r638-pointer-baseline.json files=126 total=4157`；随后 `--check-baseline` rc=0 且六格全空（`forged`／`grew`／`new_docs`／`offenders`／`shifted`／`shrank`）；`tests/test_r638_pointer_ratchet.py`＋`tests/test_r638_counter_evidence_teeth.py` **29 passed / rc=0**。
- 🔴 为什么不由执行层落：① 在册口径——`docs/testing/r646-retirement-paper-derived-anchors-2026-10-05.md` 明写那件基线「在总控写域里……留给总控并树时处置」；② 技术理由——基线必须由**并树后的合并树**派生：R657 还在动 `app/api/v1/observability.py`（r483 那张纸正引用 `:529`），本席这份是 `8a52c5c`＋本货的读数，合进去会立刻再次过期，还可能与在飞席位抢同一枚 JSON。
- 回退面（若总控判本单连 r638 那 3 枚也该一起治）：并树后跑上面那一行即可，原件留档 `%TEMP%\eb104\r660\r638-baseline.before.json`。
- 另注：本纸自己带着当日留账坐标（旧→新对照），在棘轮里只算 `new_docs`（点名不定罪）；那些数字属**当天读数**，不是在册活格，下一次重锚不必回头同步它们。



