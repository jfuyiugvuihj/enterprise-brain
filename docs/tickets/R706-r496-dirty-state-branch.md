# R706 · r496 那枚自读钉把「此刻盘面脏不脏」当罪证：并树必红一次，`git archive` 树里连收集都过不去

**号**：R706　**性质**：总控亲签（R700 并树时现取：state① 唯一那枚红就是它；AGENTS 明写「常驻钉不许把此刻盘面脏不脏当成判据——要判归因就写态分支＋影子端正控」，这一枚没做到）　**基点**＝派工那一刻主树 HEAD 现取　**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。

## 病形现取（总控 10-06 14:5x，两条都当场复现过）

- 红形一（并树态）：`tests/test_r496_forbidden_pin_scope.py::test_the_real_tree_reads_its_own_construction_fingerprint` 走 `tests/test_r496_forbidden_pin_scope.py::dropped_must_be_identical`，对被闸门放掉的每一枚候选调 `tests/test_r453_cloud_eval_override.py::content_verdict`，判的是「HEAD blob 与盘上字节是否相同」。⇒ 只要工作区相对 HEAD 有真改动（apply 未 commit 的每一分钟），话就变成「闸门放掉了真改动：app/api/v1/data.py（读数 M app/api/v1/data.py）」。R700 的 state① 读数 1 failed／385 passed，唯一那枚红即此；执行层影子树另取一枚证：干净基线 16 passed，只往 `app/api/v1/data.py` **追加一行注释**（本单代码零参与）当场红。
- 红形二（无 `.git` 的检出）：`git archive HEAD` 解出来的树里跑同名件，收集阶段就 ERROR——红句来自 `tests/test_r453_cloud_eval_override.py` 那句 `assert proc.returncode == 0, "取不到被跟踪清单：…"`（`git ls-files` 在无库目录必非零）。整批 13 枚件被它一枚拖停，两态纪律因此没法用 archive 形态走。

## 判据（每条可失败，缺一枚判负）

1. **态分支**：本钉必须先分辨「树在静止态」还是「树在并树中态」（`git diff --cached --name-only` 与 `git status --porcelain` 现取，禁手抄）。静止态判据一字不松（今天这条红该红还得红）；并树中态改成三条腿对账里的另两条——**索引 blob 对盘上字节**，HEAD↔索引那一截差异**逐枚点名登记**、不作罪证。🔴 不许改成「脏就跳过」：跳过＝摘牙。
2. **影子端正控**：并树中态必须当场再跑一次「同一枚 `content_verdict` 在 `git worktree add --detach <HEAD>` 干净影子树里的读数」作对照，并在凭据纸里给出两态数字。影子树用完必须 `git worktree remove`（只许删自己建的那一枚，路径逐枚点名）。
3. **真改动仍要咬得住**：新增反证牙至少三枚——① 在并树中态下把一枚**已被暂存**的文件盘上再改一字节（暂存与盘上不一致）⇒ 钉必须红并点名该文件；② 闸门若放掉一枚索引 blob≠盘上字节的候选 ⇒ 必须红；③ 干净静止树里造一枚真差异（改 `app/api/v1/data.py` 一行后**不 commit**、跑完还原）⇒ 按新口径必须**不再红**，同时点名「这是并树中态」——这一枚是治病的正牙，不许反过来把它做成永真（判据 2 的影子对照就是它的不永真凭据）。
4. **无库检出不许拖停整批**：拿不到被跟踪清单时必须给出**具名 skip**（话里写清「无 .git 的检出，本钉只在真树与影子树里判」），不得让收集阶段 ERROR 带走同批其它件。
5. **卫兵不许坏**：`tests/test_r453_cloud_eval_override.py` 与 `tests/test_r496_forbidden_pin_scope.py` 两本同名件改动前后各跑一遍（dirty／干净影子树两态，清单逐枚相同）；`python scripts/lint_hand_copied_coordinates.py --check` rc=0；`python scripts/tickets_index.py --verify` rc=0；控制符（00/07/08/0b/0c）各 0 枚；坐标一律 `文件::符号`，本单不得新增 `文件:数字`。
6. **交付**：凭据纸 `docs/testing/r706-<开工日>.md`（两态数字＋三枚牙的读数＋影子树清理自证）＋`git rev-list --count <基点>..HEAD`＋未跟踪逐枚点名。

## 写域（只许这些）

`tests/test_r496_forbidden_pin_scope.py`／`tests/test_r453_cloud_eval_override.py`（只许改 `content_verdict` 与被跟踪清单那两道口的形态分支）／新增 `tests/test_r706_*.py`／`docs/tickets/R706-*.md`／`docs/testing/r706-<开工日>.md`

## 禁区（踩线即退回）

`app/**`／`frontend/**`／`docs/handoff/**`／`docs/api/contract-v1.md`／评测夹具与判分器／`scripts/run_gate.py`／`scripts/eval_*`·`r57*`·`r63*`·`r67*`（夜窗量具）／`pyproject.toml`／容器·镜像·模型动作／主树任何路径／**别人的工作树**（`be-r694`／`be-r695`／`be-r703` 在飞）。

## 这一枚为什么存在

今晚还要并 R695／R702／R703 至少三笔，每一笔都要为这枚钉付一次「先红 vs 我造成」的归因税；而它今天已经证明自己在 archive 形态里会拖停整批件。治病根，不是再加一枚针。