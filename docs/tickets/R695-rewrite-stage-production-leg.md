# R695 · rewrite 段的生产发点（R51② 缺的第二条腿·送身份＋开段账）

**号**：R695　**基点**＝派工那一刻主树 HEAD 现取（本段落盘之后那一枚；产品码代次由总控在名册行点名——必须在 R677／R676 并树之后，写域含 `app/rag/retrieval_pipeline.py`）
**独占工作树**：由总控预配并告知路径，不许换树、不许碰主树。

## 现取病形（总控 10-06 12:3x 亲读，不是转述）

`CANONICAL_STAGES` 现取＝classify／rewrite／retrieve／generate／reflect（`app/common/stage_timing.py::CANONICAL_STAGES`）。R688 并树 `ecbd525` 之后 classify／generate／reflect 三段有发点，**rewrite 今天既无跨度也无身份**：

- `app/api/v1/chat.py::_rewrite_followup(session_id, user_msg)` 与 `app/rag/retrieval_pipeline.py::QueryRewriter.rewrite(question)` 两枚签名里**都没有 config／principal**；
- 两者最终都走 `app/common/model_handler.py` 的非流式 `chat()`，而 `app/trace/spans.py::stage_account`／`record_stage_event` 在 `model_handler.py` 里零枚（R690 只并了流式那一发的 `stream_options.include_usage`，已于 `c82208c` 并树 ⇒ 写域冲突已消）。
- ⇒ 直接给 rewrite 发一枚 `stage_account` 会撞「无主不记」那条规矩（写零字节＝静默失效，比没有更坏）。

## 判据（每条可失败，缺一枚判负）

1. **身份真送进去**：`_rewrite_followup` 与 `QueryRewriter.rewrite` 各加**可选**形参（`config` 或 `principal`，缺省值必须保持今天的调用形状不破），调用点把本轮 config 传下去。🔴 反证牙：把传参那一行摘掉 ⇒ 判据 2 的钉必须红并点名是哪一段没主。
2. **发点可指认**：`scripts/r636_stage_coverage.py::call_sites_of` 现读必须交回 `rewrite` 段 ≥1 枚 `文件::符号`；`tests/test_r688_stage_accounts_are_landed.py::assert_stage_accounts` 里「没落地的段必须零枚」那一格会当场红并点名——**它红了就说明账要跟着改口径，那时停下交回，不许偷偷改它凑绿**。
3. **同区间只一把尺**：rewrite 这一段今天没有第二把尺（既无 model 跨度记账也无工具跨度归段），所以发 `stage.finished` 不构成双记。🔴 若你在实现中发现同一区间已经存在别的跨度（现读取证），必须停下交回——retrieve 那一族就是这么差点双记的（等长区间进 `unresolved_pairs`，`within_one_percent` 从此永闭）。
4. **不改计时纪律**：五段计时不得阻塞热路径，在册计时钉 `tests/test_r149_sse_text_pieces.py`／`tests/test_r661_trace_journal_hot_path_teeth.py` 必须仍绿，读数逐枚贴进交付。
5. **不许翻绿 R51②**：<1% 那一格由今晚 run32／run33 的 `r631` 读数判；本单交付里明写「R51② 仍待窗」，写成达即退回。
6. **交付**：同名件两态读数（dirty／commit 后各一遍，清单逐枚相同）＋`rev-list --count <基点>..HEAD`＋未跟踪逐枚点名＋控制符各 0 枚＋坐标一律 `文件::符号`＋凭据纸 `docs/testing/r695-<开工日>.md`＋`python scripts/tickets_index.py --verify` rc=0。

## 写域（只许这些）

`app/api/v1/chat.py`／`app/rag/retrieval_pipeline.py`／`app/trace/spans.py`／`app/common/stage_timing.py`／`app/common/model_handler.py`（仅当必须，且须先取证它未被别席持有）／新增 `tests/test_r695_*.py`／`docs/tickets/R695-*.md`／`docs/testing/r695-<开工日>.md`

## 禁区（踩线即追加）

`app/agents/orchestrator.py`／`app/rag/hot_index.py`（若 R677 未结案）／`frontend/**`／`deploy/**` 与任何 `.env*`／评测夹具与判分器／`docs/handoff/**`／`docs/api/contract-v1.md`／`pyproject.toml`／`scripts/run_gate.py`／夜窗量具 `scripts/eval_*`·`r57*`·`r59*`·`r63*`·`r674*`／容器·镜像·模型动作／主树任何路径。

## 交付与交回（执行层席位 `be-r695`／基点 `3a08975`／10-06）

🔴 本节是**文末追加**，上面六条判据与机器字段（号／基点／写域）一字节未改；状态仍 QUEUED，并树与索引重生成归总控（AGENTS ⑨ 的自指后果）。全文读数、两态清单、SHA-256 与逐枚反证牙都在 `docs/testing/r695-2026-10-06.md`，本节只登记落点与必须交回的口径。

**交出去的形状（两枚发点，两路送身份）**

- chat 腿：发点开在 `app/api/v1/chat.py::_rewrite_followup`（外面套 `app/trace/spans.py::stage_account`）；身份由 `app/api/v1/chat.py::ask` 经 `app/trace/spans.py::arm_turn_identity` 挂进执行上下文、`finally` 里 `app/trace/spans.py::reset_turn_identity` 复位。可选形参 `config` 也加了（显式交 config 的调用方一律收）。
  🔴 为什么身份不走第三枚实参：全档现读 31 枚测试替身（27 个文件）按 `(session_id, message)` 两枚元数替换这枚函数，把 config 做成必交实参就红（席外实测：不止判据④ 点名的那枚，见凭据纸 §6e）。形状照 R536 在册正例 `app/rag/retrieval_pipeline.py::arm_retrieval_trace`。
- pipeline 腿：发点开在 `app/rag/retrieval_pipeline.py::RetrievalPipeline.search`（新可选形参 `config`），由 `app/rag/retrieval_pipeline.py::RetrievalPipeline.search_for_principal` 交 `config=retrieval_turn_config(principal)`；`app/rag/retrieval_pipeline.py::retrieval_turn_config` 缺 principal／缺三枚 id 任一枚就交回 `None`（无主不记仍只由 `app/trace/spans.py::ExecutionSpan.active` 一枚闸判，本件不新造第二种判法）。
- `app/common/stage_timing.py::stage_window` 的文档串里那句「rewrite 还没有边界」是过期陈述，已按新事实改写；retrieve 仍留给 R696，本件没顺手"做出"它的发点。

**判据读数（执行层亲跑，两态）**

- 判据②：`scripts/r636_stage_coverage.py::call_sites_of` 现读 `stage_account`＝3 枚（基点 1 枚），`tests/test_r688_stage_accounts_are_landed.py::stage_emit_points` 现读 rewrite＝2 枚 `文件::符号`。
- 判据③：非流式那一发五枚尺符号零命中（AST 现读）；检索腿那一发严格嵌在 `app/agents/tools.py::search_docs` 之内，由在册算术 `app/common/stage_timing.py::aggregate_stage_latency` 剔出加总而保留分布（`ledger_count=0`／`excluded_count=1`／`unresolved_pairs=0`／`within_one_percent=True`）。**没发现第二把尺，也没造出等长区间**，所以判据③ 的「停下交回」那一支没触发。
- 判据④：`tests/test_r149_sse_text_pieces.py` 16 passed；`tests/test_r661_trace_journal_hot_path_teeth.py` 34 passed。同名件 18 枚 state①（dirty）＝1 failed／307 passed／1 skipped／90.17 s，state② 见凭据纸 §6b 就地填数。那 1 枚 skip 是 `tests/test_r51_observation_is_passive.py` 自带的私有写域守卫，基点同形状。
- 判据⑤：🔴 **R51② 仍待窗**（今晚 run32／run33 的 `scripts/r631_stage_sum_delta.py` 读数判；本单只把 rewrite 变成「有账可量」，量到 ≠ 达标）。
- 反证牙：`tests/test_r695_counter_evidence_teeth.py` 七枚（K1 运行期摘挂载 ⇒ 真路由零枚且红句点名 rewrite 没主；K2／K3 摘接线；K4／K5 摘发点；另含双记可指认正控与不动刀正控）。🔴 刀一律不落在这棵席树盘面（在册教训：R677 因席内反证未还原被记账），变异走 monkeypatch 与 `tmp_path` 影子根，每枚刀下刀前现读原文唯一命中。

**必须交回总控的六格（执行层没动它们一个字节）**

1. 判据① 字面里「`QueryRewriter.rewrite` 加可选形参」这格没照字面做：R43a 硬门 `tests/test_r43a_rewrite_prefix_reuse.py::test_no_identity_can_reach_the_reusable_prefix` 钉死它的 `parameters == ["question"]`，那是「可复用前缀收不到身份」的结构证据。跨度因此开在调用侧，并反向钉住签名不破（`tests/test_r695_rewrite_stage_accounts.py::test_the_query_rewriter_still_takes_no_identity`）。拆不拆那枚门归总控裁定。
2. 在册钉红 1 枚且不许改它凑绿：`tests/test_r688_stage_accounts_are_landed.py::test_every_emit_point_host_accepts_a_config_argument`（红句点名 `RetrievalPipeline.search`）——它把 `app/agents/nodes.py` 当成发点宿主的唯一表。同件 `LANDED_STAGES`／`UNLANDED_STAGES`（现读仍把 rewrite 记在 UNLANDED）与宿主表要一起改口径。另记一格：`assert_stage_accounts` 的「没落地的段必须零枚」今天仍绿，因为 R688 那一轮走图入口、未挂本轮身份 ⇒ 无主不记，这正证新发点没绕过闸。
3. 基线账面红（非本单造成）：基点影子树上 `python scripts/tickets_index.py --check` rc=2、`--verify` rc=4，都红在索引里 R677 那一格（现算 LANDED＋`152c9ce09ceb`，盘上仍写 QUEUED＋`9efff02`）。`scripts/tickets_index.py` 与 `docs/tickets/index.tsv` 不在本单写域 ⇒ 判据⑥ 的 rc=0 这一格在执行层不可达。
4. 夜窗量具的 rewrite 归因文字已过期：`scripts/r636_stage_coverage.py::classify_missing` 里 `stage == "rewrite"` 那一支仍写着「这条腿没有跨度这回事」，`scripts/r636_stage_coverage.py::nonproducing_lanes` 还带全线 `stages: ["rewrite"]` 那块。该件在禁区（`scripts/r63*`）内，一字未动，交回总控按新事实改口径。另记两把尺的符号拼法分叉（r636 交回 `app/rag/retrieval_pipeline.py::search`，R688 交回 `...::RetrievalPipeline.search`），本件不抹平。5. 🔴 **R51 的私有写域守卫在席位树上误判本单**（state② 第二枚红的归因）：`tests/test_r51_observation_is_passive.py::test_this_ticket_writes_no_dependency_manifest_no_migration_and_no_frontend` 的归属判法 `:: _is_r51_work` 是「分支名以 `codex/be-r51` 开头」或「改动集里出现 `app/common/stage_timing` ·`tests/test_r51_observation_is_passive`」。本席树是 `git worktree add --detach` 的 detached HEAD（`:: _current_branch` 读回 `HEAD`，也不在 `TRUNK_CANDIDATES` 里），而本单合法改了 `app/common/stage_timing.py::stage_window` 的文档串（那句「rewrite 还没边界」已被本单证伪），守卫因此把本单当成 R51 的树，再用 R51 的 `FORBIDDEN_PREFIXES`（含 `app/rag/`、`docs/`）判本单越界。机器取证（直接调守卫自己的函数，零改动）：席位树 `_is_r51_work(scope)`＝True、violations 三枚；**剔掉 R51 自己的产物前缀再问一次 ⇒ False**；主树（`codex/data-file-catalog` 在 `TRUNK_CANDIDATES` 里）scope 为空、violations 为空 ⇒ **并树到主树以后这枚守卫不会红**。口径要改成绑**单据身份**（分支名 \/ 提交词里的单号）或先把别人的单号产物剔出 scope——守卫自己的注释里就写着它把 R92 \/ R50 这类合规单判成越界的风险。本单未动那枚文件一个字节。
6. **state② 已现测并填数**：本席 commit `8538197` 之后干净树复跑同名 18 枚＝**2 failed \/ 307 passed \/ 90.56 s，rc=1**。passed 枚数与 state① 相同，差的只是上面第 5 条那一格 skip→failed；判据④ 点名的两枚计时钉两态都绿（`tests/test_r149_sse_text_pieces.py` 16 passed、`tests/test_r661_trace_journal_hot_path_teeth.py` 34 passed）。另外两件事已落纸：**§6c 席外实弹**（在本席提交的 detached 影子树里删 `config=retrieval_turn_config(principal),` ⇒ 主件 1 failed ＋ 牙件正控与 K3 双红；放回那一行 ⇒ 回到 24 passed；另刀摘 `arm_turn_identity` 挂载 ⇒ chat 两枚钉双红）与 **§6d 并发污染披露**（state② 墙钟与另一席的 `scripts/r694_walkthrough.py` 重叠，按 AGENTS ⑭ 秒数只当样本、判据只认枚数与 rc）。

**并树坐标（给总控搬运用，逐枚现取）**

- 基点＝`3a08975`；本席第一笔出货＝`8538197`（之后全是就地填数的账面提交）。🔴 **席树 HEAD 的 sha 不写进本席账面**——那是自指坐标（每补一行就漂一次，本单已自撞一次并就地改掉）。并树坐标请总控现取：`git -C <席树> log --oneline 3a08975..HEAD`、`git rev-list --count 3a08975..HEAD`、`git diff --numstat 3a08975..HEAD`、`git status --porcelain`。本席交还前现读：`git status --porcelain` 空、`git diff --numstat HEAD` 空、无未跟踪件。
- 改动集 8 枚逐枚点名（两枚账面文件只点形状不抄枚数，那两个数字会随本行自己漂）：`app/api/v1/chat.py` 90\/56（state① 为 89\/56，第五笔账面改的是注释，+1 行）、`app/common/stage_timing.py` 8\/7、`app/rag/retrieval_pipeline.py` 39\/2、`app/trace/spans.py` 39\/0（四者是产品码；之后只有 `app/api/v1/chat.py` 里的注释被改过一处数字，**逻辑一字未动**，另三者自始至终未再变）、`tests/test_r695_rewrite_stage_accounts.py` 464\/0（新增）、`tests/test_r695_counter_evidence_teeth.py` 192\/0（新增）、`docs/tickets/R695-rewrite-stage-production-leg.md`（纯文本追加，机器字段与判据原文未动）、`docs/testing/r695-2026-10-06.md`（新增凭据纸）。
- 🔴 本席**不把补丁 SHA-256 抄进账面**：那是自指坐标（每补一行账就漂一次）。正解＝总控在并树那一刻现取 `git -C <席树> diff 3a08975 HEAD --binary` 的字节数与 SHA-256，再与 `git apply` 之后的主树盘面逐枚 SHA-256 对盘（AGENTS ⑤）。六枚代码与测试件的 SHA-256 已逐枚记在凭据纸 §8，本席在提交之间复扫过：前四笔全部相等（无漂移）；第五笔是纯文字订正，让其中**两枚**漂号（`app/api/v1/chat.py` 与 `tests/test_r695_rewrite_stage_accounts.py`，旧值已在 §8 同格登记）。⇒ 总控对盘请用 §8 现取值，不要用 state① 的旧值。
- 席位树的两枚影子工作树（基点取证树与席外实弹树）已由本席 `git worktree remove` 清掉，主树与别席树全程未碰。
