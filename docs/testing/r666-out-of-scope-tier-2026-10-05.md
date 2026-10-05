# R666 · 账尺加一档 OUT（移出版本代码半径）——口径、牙与三态读数（2026-10-05）

执行层代号 **Boole**／树 `C:/Users/fengx/PycharmProjects/be-r666`（本席自建的工作树，主树一个字节未动）／分支 `codex/r666-out-of-scope-tier`／基点＝建树那一刻主树 HEAD `798dbdf`（现取）。
全程只动本单写域：`scripts/audit_plan_ticket_ledger.py`、`tests/test_r640_ledger_tiers_are_derived.py`、新件
`tests/test_r666_out_of_scope_tier.py`、本纸。主树一个字节未动；未 commit、未建分支于主树、未 push、未动容器／镜像／模型。

## 1. 治的病

判据「V1 计划书代码单清零」按读法乙挂着 **16 号未清**，其中 5 格不是没做完，而是**判据本身不成立**：

- R29 判据②「生成轮 30.6 s → ≤22 s」：真机 A/B 判负，改动落地后一分没省；
- R43 判据②「E3 档实测 `cached_tokens > 0`」：前提是换推理引擎／档位，与 V1「只管理本机 Ollama」对冲；
- R48 判据①「首屏 ≤1 s 有可用结论」：本机地板现读 11.0 s，物理不可达，报档位属发布期；
- R52 判据①「断网可装可跑」：E 行整行属交付／现场阶段，开发机上不能证实也不能证伪；
- R50 判据②「全量重建可中断续跑」：丙案裁定已交（`docs/deployment/offpeak-rebuild-execution-shape-2026-10-05.md`），
  判据②按现读证据达，欠的只是「低峰自动触发」那半句，登记为交付阶段动作。

继续挂 PARTIAL＝逼后人永远欠一笔还不掉的账。本单给尺子加一档 **OUT**，把这 5 格**移出**，同时把「移出」
钉成一件必须留下可核凭据的事——不是一条让账变好看的出路。

## 2. OUT 的口径（`scripts/audit_plan_ticket_ledger.py::VERDICTS`）

🔴 **OUT 绝不等于判达，也不算完成。** 它唯一的语义是：这一格经实测或裁定确认**不在本版代码半径内**。
工单点名的三件事必须同时成立，本席再加两条硬腿（④⑤），缺一枚就当场红：

- ① **出处**：仓内真实存在的**文书**路径＋该文书里的判语关键词。只认 `docs/` 与 `README.md`
  （`scripts/audit_plan_ticket_ledger.py::OUT_DOC_PREFIX`）——拿脚本自己的注释当裁定不算裁定。文件断头、锚点在文书里命中 0 处或命中多枚、
  关键词没落在那一行上、出处指向的不是文书——全走 `scripts/audit_plan_ticket_ledger.py::resolve_out` 现读，红口是 **C19**。
- ② **不可达证据**：一句带数字或带裁定引句的理由。「暂时不做」这种形容词过不去，红口是 **C20**
  （判据形状见 `scripts/audit_plan_ticket_ledger.py::OUT_VAGUE` 与 `scripts/audit_plan_ticket_ledger.py::OUT_NUMBER_RE`）。
- ③ **逐字点名被移出的那一格**：出处之外还得把判据原文从跟进单 §21 切出来挂着，整号一笔抹掉＝红，红口是 **C21**。
- ④ **那枚文书已并树**（本席加）：把文书带进仓库的提交由 `scripts/audit_plan_ticket_ledger.py::Git.first_add` 现取，再由
  `scripts/audit_plan_ticket_ledger.py::Git.is_ancestor` 现判在不在 HEAD 祖先链上。本地便签、或躺在别的 ref 上没进主干的裁定＝**C19** 咬：
  「移出」是账面裁定，裁定得先成为仓内在册事实，才对得起这本账。
- ⑤ **本格必须有产物在树**（本席加）：判 OUT 的号名下至少一枚在树的产物提交。这版压根没动过的号该记
  ZERO／PARTIAL，不叫移出，红口是 **C22**（`scripts/audit_plan_ticket_ledger.py::self_checks` 的 OUT 分支）。
  🔴 没有这条，一枚零产物的号就能借一句形容词出处把自己洗成「不欠」——那是比挂 PARTIAL 更大的假账。

计数口径：`OUT` 进了 `scripts/audit_plan_ticket_ledger.py::CLEARED_TIERS`，所以它**不进读法甲的未清、也不进读法乙的未清**；
但它同时**不进 LANDED 那一列**——报表 §9 把移出格单列成一段，段头与逐格行都写着「不算完成」
（常量 `scripts/audit_plan_ticket_ledger.py::OUT_DISCLAIMER`）。只加不减不报＝假账，这条由
`tests/test_r666_out_of_scope_tier.py::test_the_cli_singles_out_the_moved_cells_with_the_disclaimer` 钉住。

**为什么 OUT 不走派生**：它故意不进 `scripts/audit_plan_ticket_ledger.py::DERIVABLE_TIERS`。CLOSED／FOREIGN／NOTBUILT
能从祖先链、仓内路径、表格行这些事实里读出来；「这格不属于本版代码半径」是一句**裁定**，只能由人执笔。
尺子若能自己派生 OUT，就等于尺子可以决定哪些题不用做——那才是最大的假账。代价是它必须交出处，
所以 C11（新档不许写死）对 OUT 不适用，替代它的是 C19／C20／C21／C22 这四枚出处与产物牙。

## 3. C1 改口与老三档的不变量

- C1 从「判定词只许六档」改成「判定词只许七档」，判定词表多一枚 `OUT`；**拼错的判定词照咬**，
  包括 `OUTT`／小写 `out`／带尾空格的 `OUT `（`tests/test_r666_out_of_scope_tier.py::test_c1_still_bites_any_verdict_word_outside_the_seven` 七枚变体逐枚现咬）。
- LANDED／PARTIAL／ZERO 三档的口径**一字未动**：报表头那两句原文仍逐字在位，由
  `tests/test_r666_out_of_scope_tier.py::test_the_old_three_tiers_wording_survives_the_upgrade` 钉住；
  老三档的位序（VERDICTS 前三枚）也钉了。
- `T()` 只加了一枚带缺省的参数 `out=None`（`scripts/audit_plan_ticket_ledger.py::T`），既有 43 号调用点一枚都没重写。

## 4. 移出的 5 格（逐格点名，全部现读）

| 号 | 移出的那一格（跟进单 §21 判据表原文） | 出处文档 | 判语关键词 | 为什么不可达 |
|---|---|---|---|---|
| R29 | ② 生成轮 30.6 s → ≤22 s | `docs/version-roadmap-and-requirements-2026-10-05.md` | 真机验过（判负） | 真机 A/B 判负，改动落地后一分没省；V1 硬件口径上不会变绿 |
| R43 | ② E3 档实测 `cached_tokens > 0` | `docs/version-roadmap-and-requirements-2026-10-05.md` | 已裁定移出 | 前提是换推理引擎／档位，V1 钉死只管理本机 Ollama＝部署形态不属代码半径 |
| R48 | ① 首屏 ≤1 s 有可用结论 | `docs/version-roadmap-and-requirements-2026-10-05.md` | 已裁定移出 | 本机地板 11.0 s（只吐 1 枚 token 也要 11.0 s），物理不可达；报档位属发布期 |
| R50 | ② 全量重建可中断续跑 | `docs/deployment/offpeak-rebuild-execution-shape-2026-10-05.md` | 移出 V1 门槛 | 丙案裁定：判据②达（凭据 `scripts/rebuild_index.py::run_rebuild` ＋ `tests/test_r50_resumable_rebuild.py` 20 枚 ＋ `tests/test_r50_incremental_index.py` 15 枚），欠的只是「低峰自动触发」半句＝交付阶段动作 |
| R52 | ① 断网可装可跑 | `docs/version-roadmap-and-requirements-2026-10-05.md` | 已裁定移出 | E 行整行移出 V1（上线实施清单）；开发机上不能证实也不能证伪，缺一台干净机演练 |

出处行号**不落纸**：尺子在运行时按锚点现取，报表 §9 每格都打出「文件＋行号＋那一行原文」。
这 5 号的产物提交仍逐枚挂在台账上受 C2／C3／C4／C5 管（移出 ≠ 没干过），
由 `tests/test_r666_out_of_scope_tier.py::test_moved_cells_still_carry_their_products_and_name_their_cell` 钉住。

## 5. 尺子的读数（本单一手现取）

改判前（基线＝本树 apply 之前，HEAD 仍是基点 `798dbdf`，与主树同一枚树）：

- 在册 43 号：LANDED=24 · PARTIAL=16 · CLOSED=1 · ZERO=0 · FOREIGN=1 · NOTBUILT=1；读法甲未清 0；读法乙未清 **16**；RESULT=PASS（0 条违规，在册 43 号逐条自证）。

改判后（本树）：

- 在册 43 号：LANDED=24 · PARTIAL=11 · CLOSED=1 · ZERO=0 · FOREIGN=1 · NOTBUILT=1 · OUT=5；
- 读法甲未清 0 号（不变）；读法乙未清 **11 号（PARTIAL 11 ＋ ZERO 0）**——从 16 降到 11，降的 5 格全在 OUT 段里，一枚都没进 LANDED；
- RESULT=PASS（0 条违规，在册 43 号逐条自证）。

留在 PARTIAL 的 11 号（欠账逐字点名，报表 §4／§8 可见，本单未碰）：R25 R26 R27 R28 R31 R35 R37 R38 R44 R47 R51。

## 6. 反证牙的红／绿读数（每把都先跑正控，正控不绿不算咬中）

常驻件：`tests/test_r666_out_of_scope_tier.py`，29 枚用例（执行层亲跑，非自报）；N9～N12 四把是定稿前补的，补的动机见 §9 那条重叠施工。

| 刀 | 摘掉的那条腿 | 咬它的牙 | 红读数（尺子交回的原文，逐枚点名） |
|---|---|---|---|
| N1 | 出处文档换成不存在的纸 | C19 | 🔴 C19 R29：OUT 出处落不实地——OUT 出处 'docs/testing/r666-paper-that-does-not-exist.md' 不在仓内＝断头引用（要的是仓内真实存在的文档路径） |
| N2 | 判语关键词改成出处读不到的一句 | C19 | 🔴 C19 R48：OUT 出处落不实地——OUT 判语关键词「已裁定移出（出处里没这句）」不在 docs/version-roadmap-and-requirements-2026-10-05.md 第 134 行上：｜ R48 ｜① 首屏 ≤1 s 有可用结论 ｜ 已裁定移出 ｜… |
| N3 | 锚点漂移（文档里读不到） | C19 | 🔴 C19 R52：OUT 出处落不实地——OUT 出处 docs/version-roadmap-and-requirements-2026-10-05.md 里读不到锚点「｜ R52 ｜① 断网可跑（锚点漂了） ｜ 已裁定移出」＝判语断头（文档改口了，改判得重新落纸） |
| N4 | 证据句整段改成「暂时不做」 | C20 | 🔴 两枚一起红：C20 R29「证据句里既没有证据数字也没有裁定引句：'暂时做'」＋ C20 R29「证据句里只剩形容词（暂时不做）＝不可达没交代」 |
| N5 | 出处文档里把那一行复制一枚（锚点命中 2 处） | C19 | 🔴 C19 R29：OUT 锚点在 docs/version-roadmap-and-requirements-2026-10-05.md 命中 2 处，要求恰 1 处 |
| N6 | 出处文档从盘上拿走 | C19 | 🔴 四枚一起红：R29／R43／R48／R52 各一枚「不在仓内＝断头引用」；R50 不跟着倒（它的出处在 `docs/deployment/`） |
| N7 | CLI 给没出处的号标 OUT（`--fault R25=OUT@ad85821`） | C19＋C21 | exit=1；🔴 C19 R25：判 OUT 却没挂出处——OUT 必须点名仓内真实文档＋该文档里的判语关键词；🔴 C21 R25：判 OUT 却没逐字点名移出的那一格（整号一笔抹掉＝假账）；RESULT=FAIL（2 条）· 咬到的单号：R25 |
| N8 | 判定词拼错：`PARTIA`／`PARDIAL`／`LANDED `／`OUTT`／`out`／`OUTG`／`DONE` | C1 | 七枚变体逐枚红，形如「C1 R25：判定词「OUTT」不在七档之内」——改口成七档之后 C1 依旧只认这七个词 |
| N9 | 出处换成一枚代码文件（拿脚本自注当裁定） | C19 | 🔴 C19 R43：OUT 出处落不实地——OUT 出处 scripts/audit_plan_ticket_ledger.py 不是仓内文书（只认 `docs/`、`README.md`）＝拿代码注释当裁定 |
| N10 | 出处文书的落盘提交不在 HEAD 祖先链上 | C19 | 🔴 C19 R29：OUT 出处落不实地——出处 docs/version-roadmap-and-requirements-2026-10-05.md 的落盘提交 f79b005 不在 HEAD 祖先链上＝那枚裁定还没进主干 |
| N11 | 出处只是本地便签（读不到把它带进仓库的提交） | C19 | 🔴 五枚一起红：R29／R43／R48／R50／R52 各一枚「读不到把它带进仓库的提交＝本地便签不在册（裁定得先并树才作数）」 |
| N12 | 把 R29 名下在树的产物摘光，只留出处 | C22 | 🔴 C22 R29：判 OUT 却没有一枚在树的产物＝零产物的号不许借 OUT 把「这版没做」挪出半径 |

N10／N11 两把遮的是 git 的读数（`tests/test_r666_out_of_scope_tier.py::GitMask` 只遮 `first_add`／`is_ancestor` 一枚方法，其余照旧问真仓）：
裁定的事实源仍是真仓，喂假的只有「有没有并树」这一问。N12 不碰影子文件，直接在现取的在册行上摘产物；
C19 的「没挂出处」、C21 的「没点名格子」两把照旧在内存里判。要 CLI 级的反证看 N7 那枚 sha 路数。

绿读数（正控）：一把刀都不摘时 29 枚全过、尺子 RESULT=PASS（本席另用一枚影子脚本逐把打印红口原文，读数即上表）；已改判 OUT 且出处落得地的 5 号不因新牙受冤——
七档判定词不被 C1 咬（`tests/test_r666_out_of_scope_tier.py::test_c1_does_not_bite_the_seventh_tier_itself`），
五枚出处逐枚现读得回文件＋行号＋判语（`tests/test_r666_out_of_scope_tier.py::test_every_out_source_is_a_real_repo_doc_with_the_verdict_on_that_line`）。
全部影子只落 tmp_path，仓内 .md 与产品码零写入
（`tests/test_r666_out_of_scope_tier.py::test_the_knives_never_write_into_the_repo`）。

## 7. 三态数（同名件清单逐枚相同、总数相同）

三枚态跑的**是同一批件**：`scripts/audit_plan_ticket_ledger.py`、`tests/test_r666_out_of_scope_tier.py`、
`tests/test_r640_ledger_tiers_are_derived.py`、`tests/test_r640_counter_evidence_teeth.py`（后两枚是本单动过／必须一起自证的常驻件）。
解释器一律用主树那枚 venv（新建的工作树里没有 `.venv`，anaconda 那枚在 conftest 当场缺 chromadb），cwd 一律指各自那枚树。

- **改前基线**（本树 apply 之前，HEAD＝基点 `798dbdf`，不含本单货）：尺子 RESULT=PASS、读法乙未清 **16**；两件常驻合跑 **31 passed**。
- **state①**（本树已 apply 未 commit）：尺子 RESULT=PASS、OUT=5、读法乙未清 **11**；逐件分跑 **29 ＋ 17 ＋ 15 ＝ 61 passed**
  （三件的清单与枚数见下表；比基线多的那一枚是本单在 `tests/test_r640_ledger_tiers_are_derived.py` 里加的「OUT 是正式档且不许派生」钉）。
  **执行层亲跑读数，非自报转抄。**
- **state②**（基点 `798dbdf` 的干净检出＋只投本单这 4 枚货）：尺子输出与 state① **逐行相同**（501 行，逐行比对零差），
  用例合计 **61 passed ＝ 29 ＋ 17 ＋ 15**，与 state① 同名件逐枚同名；投货前逐枚 sha1 核过两态那 4 枚货字节相同。
  检出态现取凭据：`git worktree add --detach ... 798dbdf` 之后 `git status --porcelain` 零条目；投货前逐枚核过
  `git show 798dbdf:scripts/audit_plan_ticket_ledger.py` 与 `git show 798dbdf:tests/test_r640_ledger_tiers_are_derived.py`
  的 blob 与检出内容（LF 归一后）sha1 相等，另两枚在基点根本不存在；投货后 porcelain 只剩这 4 枚（2 枚 M ＋ 2 枚 ??）。
  🔴 说明：`git archive 798dbdf` 解包这条路在本机走不通——Windows 的 tar 啃不动 `data/**`、`documents/**` 里的中文名（Invalid empty pathname），
  所以干净检出改用「同一枚 commit 的 detached 检出」，并用 blob sha1 逐枚证明它与归档同源。

| 件（本单写域，逐枚现取行数） | 基线 | state①／state② |
|---|---|---|
| `scripts/audit_plan_ticket_ledger.py` | 1166 行（六档） | 1319 行（七档＋C19／C20／C21／C22＋§9 段） |
| `tests/test_r640_ledger_tiers_are_derived.py` | 283 行／16 枚 | 292 行／17 枚 |
| `tests/test_r640_counter_evidence_teeth.py` | 368 行／15 枚 | 一字未动，368 行／15 枚 |
| `tests/test_r666_out_of_scope_tier.py` | 不存在 | 418 行／29 枚用例 |
| `docs/testing/r666-out-of-scope-tier-2026-10-05.md` | 不存在 | 本纸 |

逐件分跑的枚数（同一枚 venv 解释器、`-p no:randomly`，state①／state② 各一遍，两态逐枚对齐）：

| 件 | 采集枚数 | state① | state② |
|---|---|---|---|
| `tests/test_r666_out_of_scope_tier.py` | 29 | 29 passed | 29 passed |
| `tests/test_r640_ledger_tiers_are_derived.py` | 17 | 17 passed | 17 passed |
| `tests/test_r640_counter_evidence_teeth.py` | 15 | 15 passed | 15 passed |

复跑命令（账尺只读；pytest 必须用仓内 venv 那枚解释器，anaconda 那枚在 conftest 当场缺 chromadb）：

    python scripts/audit_plan_ticket_ledger.py
    .\.venv\Scripts\python.exe -m pytest -p no:randomly -q tests/test_r666_out_of_scope_tier.py
    .\.venv\Scripts\python.exe -m pytest -p no:randomly -q tests/test_r640_ledger_tiers_are_derived.py tests/test_r640_counter_evidence_teeth.py

本席实跑的取数口径：state①／state② 都是新建的工作树，里面没有 `.venv`，所以两态一律借主树那枚
`C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe` 起 pytest，cwd 与 rootdir 各自指本树；
账尺自己只用 `python scripts/audit_plan_ticket_ledger.py`（stdlib，不碰 venv）。
定稿那两轮与另一枚并行席同机同盘跑过，所以上面只报枚数与结果，**不报秒数当性能凭据**；要拿计时比性能得一台安静机器重量。

## 8. 本单没做的事（留给总控，写域外）

- 计划书与跟进单那两本账上，这 5 号那行的台账词仍是 PARTIAL／待派——`docs/handoff/**` 是总控写域，本单一个字没碰。
  尺子只报「账判成 OUT」，不替人改表。
- `docs/testing/r640-ledger-derivation-2026-10-04.md` 里复制了一份「六档口径」的原文句子，从今天起那一句过期
  （它自己写了「以尺子报告头为准，不复制」，却复制了）。改它属总控写域，本单不动，只点名。
- 计划书 `docs/version-roadmap-and-requirements-2026-10-05.md` 的「『判据全达才算清』未清」那一行仍写 **16 号**，从今天起尺子交回的是「未清 11 ＋ 移出 5」；
  那本纸不是本单写域，OUT 那几行的档位建议也还挂着「待业主点头」，改名册属总控（跟进单 §158 末尾那句
  「五格的档位一律仍 PARTIAL／ZERO——改判要新单」同样等着改名册——本单正是那张新单，但 `docs/handoff/**` 本席一个字没碰）。
- 全量门（`python scripts/run_gate.py`）本单没跑：派工词禁止；门再便宜也要全跑，枚数由 `run_gate.py` 自选，留给总控并树后复跑。
- 读法乙那个 16→11 只是分母结算，**不是进度**：还剩 11 号欠的是代码或一次重量，OUT 那 5 号欠的是「不属这版」，两者不许相加汇报。

## 9. 边界、重叠施工与没做的取舍

- 🔴 **重叠施工（现读取证，不是推测）**：`C:/Users/fengx/wt-r666` 里躺着 **R666 第一席留下的另一批货**，基点 `1af37c5`
  ＝本席基点 `798dbdf` 的父提交（现取 `git rev-list --count 1af37c5..798dbdf` = 1、`merge-base --is-ancestor` rc=0）。
  那棵改的文件与本单写域重叠三枚，另一枚本棵没有、本棵那枚新纸那棵没有：

| 件 | `wt-r666`（第一席） | 本棵 `be-r666` |
|---|---|---|
| `scripts/audit_plan_ticket_ledger.py` | 1300 行 | 1319 行 |
| `tests/test_r640_ledger_tiers_are_derived.py` | 284 行 | 292 行 |
| `tests/test_r666_out_of_scope_tier.py` | 249 行 | 418 行 |
| `tests/test_r666_counter_evidence_knives.py` | 300 行 | 没有这枚（刀全在同一枚新件里） |
| `docs/testing/r666-out-of-scope-tier-2026-10-05.md` | 没有这枚 | 本纸 |

  两批**语义撞、字面不撞**：都把六档改成七档、都加 C19～C22、都点名同一批 5 号，
  计数口径一致（LANDED=24／PARTIAL=11／OUT=5、读法乙未清 11），影子件的类名与刀名不同。
  本席那两条硬腿（④已并树、⑤必须有产物）与「出处只认 `docs/`＋`README.md`」「`OUT` 不入派生档」，
  是在读过那批的设计之后补齐的，不是巧合——写在纸上交总控裁定。
  🔴 两批不许同并：同一枚在册号挂两份凭据，C2／C8／C9／C17 当场互斥。本席交的是
  `C:/Users/fengx/PycharmProjects/be-r666`（基点 `798dbdf`），另一批请整棵归档或只挑本棵缺的那枚刀件，由总控择一。
- 基点与主树：本纸定稿时主树 HEAD 现读 `git -C C:/Users/fengx/PycharmProjects/企业智脑 rev-list --count 798dbdf..HEAD` = 2
  （基点之后主树又并了两笔）。上面所有数都在基点树上量，总控并树后必须在**新 HEAD** 复跑同名件再落账。
- 未跑全量门 `scripts/run_gate.py`（本单禁区），未动容器／镜像／模型／服务；只跑过账尺本身、r640 那两件常驻件与本单新件。
- `git archive <基点>` 解包这条路在本机走不通——Windows 的 tar 啃不动 `data/**`、`documents/**` 里的中文名（Invalid empty pathname），
  所以 state② 用「同一枚 commit 的 detached 检出」`C:/Users/fengx/PycharmProjects/be-r666-state2`，并用 blob sha1 逐枚证明它与归档同源；
  这棵检出交付后请 `git worktree remove` 或 prune。
- 计时不作凭据：定稿那两轮与另一枚并行席同机同盘跑过，本纸只报枚数与结果，不报秒数当性能读数。
- 状态：本席未 commit、未 push、未建分支于主树，主树一个字节未动。
