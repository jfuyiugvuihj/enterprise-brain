# R709 · 带表提问被 `document_terms` 否决：`data_filename` 进不了路由，可见集退化成全量

**号**：R709　**性质**：总控亲签承接单（R703 并树后交回的第 1 格，Lagrange 一手取证）　**基点**＝开工那一刻主树 HEAD 现取　**执行时机**：🔴 必须排在 R702 并树之后——写域含 `app/api/v1/chat.py`，该文件此刻归 Schrodinger（R702）。

## 病形现取（R703 凭据纸 §一 与 §六 第 1 格，`docs/testing/r703-2026-10-06.md`）

- `app/api/v1/chat.py::_should_use_data_context` 里「报销」落进 `document_terms`，于是把本轮带来的 `data_filename` 判成不用；连带 `app/api/v1/chat.py::route_main` 的 `has_data` 取数与 `_authorized_dataset_files` 退化成全量可见。
- 后果两格：① 客户带着表问，分析档答「文档里没有数据」（R703 已在 Data 腿补了真话守卫，但**路由那一半还在**）；② 可见集退化＝越权面（C 门「越权 0 条」那格的真实风险，不是账面风险）。

## 判据（每条可失败，缺一枚判负）

1. **先取证后动刀**：交回纸必须现读点名 `document_terms` 里到底哪一枚词命中、命中之后否决发生在哪两行之间（`文件::符号`），并给出「带表 + 问句含制度词」这一形的最小复现（离线夹具，零真模型）。
2. **路由改口**：本轮 `data_filename` 非空时，`has_data` 必须为真且走 Data 腿；`document_terms` 只许影响「要不要额外检索文档」，**不许**否决已经点名的数据集。判据形态＝离线驱动一次 `/chat`，断言终态件里 Data 腿读数在位（不许用「答复里好像有数字」当判据）。
3. **可见集不许退化**：带 `data_filename` 的那一轮，`_authorized_dataset_files` 交回的集合必须是该文件（或其授权子集），不许是全量。🔴 反证牙：把请求换成一枚无权访问的文件名 ⇒ 必须走在册错误码那一支并点名，不许静默放宽。这枚牙是 C 门的牙，摘掉即退回。
4. **不许碰别的格**：`app/agents/**`（R703 刚并）、`app/documents/**`、`app/rag/**`、`frontend/**`、`app/quality/**` 一律不动；`chat.py` 里 claims 出口那一格归 R702，本单不许顺手改（两单混账＝判负）。
5. **卫兵不许坏**：`tests/test_r149_sse_text_pieces.py`／`tests/test_r459_ask_direct_answer_frames.py`／`tests/test_r379_route_tail_branches_are_gated.py`／`tests/test_r64_row_scope_error_codes.py`／`tests/test_r65_two_path_error_codes.py`／`tests/test_r178_dataset_visibility_faces.py` 复跑仍绿，读数逐枚贴进交付；`lint_hand_copied_coordinates --check` rc=0；`tickets_index --verify` rc=0；控制符各 0。
6. **交付**：同名件两态读数（dirty／`git worktree add --detach` 干净检出各一遍，清单逐枚相同，标「执行层自报」）＋`git rev-list --count <基点>..HEAD`＋未跟踪逐枚点名＋凭据纸 `docs/testing/r709-<开工日>.md`。执行层不得 commit。

## 写域（只许这些）

`app/api/v1/chat.py`（只 `_should_use_data_context`／`route_main` 的 `has_data`／`_authorized_dataset_files` 三处及其直接调用点）／新增 `tests/test_r709_*.py`／`docs/tickets/R709-*.md`／`docs/testing/r709-<开工日>.md`

## 禁区

`docs/api/contract-v1.md`（R702 在飞）／`app/agents/**`／`app/documents/**`／`app/rag/**`／`app/quality/**` 与评测夹具／`frontend/**`／`app/trace/spans.py`／夜窗量具／容器·镜像·模型·GPU／主树任何路径。

## 执行层交回（2026-10-06，席位 be-r709，基点 56bcc59）

🔴 本段是文末追加，判据原文一字未改；逐号状态的真源仍是本文件＋结案纸（AGENTS.md 病根处置 ②）。
读数一律**执行层自报**，坐标一律 文件::符号。凭据纸＝docs/testing/r709-2026-10-06.md（取证、两态读数、
残留三格全在那一页，本段只写结案形状）。

- 判据 1 已现读：命中的制度词＝「报销」一枚（词表由 ast 从 _should_use_data_context 函数体取，不手抄）；
  否决的落点＝app/api/v1/chat.py::ask 里那枚共享守卫与 user_ctx["data_filename"] 那一行之间，
  改前 inspect.getsource(ask) 现取 _should_use_data_context( ＝ 2 枚调用，改后 ＝ 1 枚。
  最小复现＝tests/test_r709_data_filename_not_vetoed.py 的 terminal 那一枚件（离线夹具、零真模型）。
- 判据 2 已改口：新增 app/api/v1/chat.py::_named_dataset_must_travel（只看点没点名），点名文件必进
  configurable；has_data 那一格由**真** route_main 判出（analysis 档＋只含制度词的问句⇒ data 腿在位；
  没点名⇒不在）。document_terms 只剩「要不要额外检索文档」（改写问句那一格）——参数化件钉死。
  🔴 落点交代：判据原文那句「驱动一次 /chat」物理不可达——ChatRequest 没有 data_filename 那一格，
  /chat 也没有工作腿（CHAT_LANE_SUPPORTED＝空元组）。本单把终态件读数打在 /api/v1/ask 上，/chat 一字未动。
- 判据 3 已钉：点名 ⇒ 可见集只算那一枚（改前实测算了 ['销售明细表.csv','报销明细表.csv']）；
  反证牙两枚在位——无权名⇒闸码 department_scope_required（∈ tools._PUBLIC_ERROR_CODES）且证据袋零枚放宽；
  不存在名⇒resource_not_found 同样不放宽。摘牙＝放宽成「读不到就当没点名」，正是改前那一形。
- 判据 4 已守：改动文件清单（git diff --name-only 56bcc59..HEAD 现取）＝app/api/v1/chat.py、
  tests/test_r709_data_filename_not_vetoed.py、本纸、本工单文件。app/agents/**、app/documents/**、
  app/rag/**、app/quality/**、frontend/**、docs/api/contract-v1.md、app/trace/spans.py 一格未动。
- 判据 5 绿：九枚同名件两态逐枚读数（dirty 与干净影子树 add --detach 到本单提交）＝
  10／16／18／13／32／28／16／3／19 全 passed，合跑 155 passed／0 failed／rc=0（两态同一份清单）；
  lint_hand_copied_coordinates --check rc=0（现取 94／预算 94／WITHIN）；tickets_index --verify rc=0；
  控制符（0x00／07／08／0b／0c）枚数＝0。
- 判据 6 交付：码＋测试一笔＝d4dc82a2bf6122bce34c8df1f02ed6ac5fc9833d（state② 那枚干净影子树检出的就是它），其后的 docs 笔逐枚由总控 git log 56bcc59..HEAD 现取；
  git rev-list --count 56bcc59..HEAD 的枚数本文件不抄（写死在它所描述的账上＝下一枚会漂的坐标，病根处置 ③）。
  🔴 本席按 AGENTS.md 病根处置 ⑦（业主 2026-10-05 裁定）在**自己的树**提交，主树零写入；判据 6 那句
  「执行层不得 commit」与 ⑦ 冲突，且它自己要求的 rev-list 与 state② 干净检出没有本树提交就取不到数。
  并树仍请总控验收后代提交，patch 通道已备（见凭据纸 §六、§七）。
- 🔴 本席自报一笔污染（凭据纸 §九）：主树多出一枚 0 字节的 tests\test_r709_data_filename_not_vetoed.py
  （现取 CreationTime＝2026-10-06 21:46:04），根因是把相对路径交给 .NET 的 ReadAllText／WriteAllText
  （PowerShell 的 cd 不改 .NET 进程 cwd）。删除被策略拒、本席在 approval policy＝never 下做不到，
  请总控手动删这一枚——它内容为空、没有任何读数经过它，但留在主树就是给下一班一枚假的「R709 件已存在」。
  事故号本席不编（编号卫生＝先 rg 取 max 再落号，那是总控的账）；这一格按规矩只落到本结案纸与账面。
- 残留三格（不在本单写域）：① 队列道（_enqueue_ask_turn 载荷被 test_r37／test_r32 逐字段钉死）
  仍拿不到点名文件——同一枚病的第二张脸，在场道治好、后台道照旧；② document_terms 与 planner 的
  制度词表两本不同源；③ 无权那一格两路不同名（闸码 department_scope_required／正文沿用 policy 的
  department_scope_denied，后者不在公开码枚举里）——R65 在册形状，本单只记账不改动。