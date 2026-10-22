# R533 · SLO 桥话改派生（`bridge_note` 不再手写枚数）

- 单号：R533（执行层）｜总控线：本席派工 09-30 10:5x
- 工作树：`C:\Users\fengx\PycharmProjects\be-r533`，基点＝主树 `codex/data-file-catalog` 现取 HEAD
  `05bec06b3123130805eebae8a73d97da39b6e32d`（自建，`git worktree add --detach`）
- 写域：`app/api/v1/observability.py` ＋ 本纸 ＋ 两枚新件；零 commit、零 push
- 🔴 禁改清单一枚字节没碰：`docs/api/contract-v1.md`、`migrations/manifest.json`（在途单 R523 名下）、
  `tests/test_r526_*.py`（只读对拍）、`frontend/**`、评测集、任何 `.env*`
  —— 现取证明：`git -C be-r533 status --porcelain` 只列 `M app/api/v1/observability.py` 与两枚 `??` 新件，
  `docs/api/contract-v1.md` 与 `migrations/manifest.json` 均**未**出现在清单里（逐字节差异见 §8 行尾那笔）

## 1. 症状与根因（基点自带，非 R526 引入）

`app/api/v1/observability.py` 的 `slo_units()["model_budget_tier"]["bridge_note"]` 把一枚**枚数**手写在
散文里：`... and six of the seven budget tiers belong to no lane at all`；`docs/api/contract-v1.md:1582`
同处写 **Five**。现源两名册（`ModelTier` 值面 × `nodes.LANE_TIERS` 值面）的读数是**五枚无对属／七枚总**
⇒ 观测面那句多一。这正是 R526（并树 `efc5c50`）立口径骨架要消灭的那一类「散文里的数字」，也是
`docs/testing/r526-slo-caliber-closure.md` §7.2 本单登记、建议「另立一单改成派生＋补一枚对拍牙」那一格。

## 2. 改动（现取 `git diff --numstat` = `75  7  app/api/v1/observability.py`）

- 新增派生把手 `app/api/v1/observability.py:836 _slo_bridge_note(members, bridge)`：
  共用几档、哪几条例外同档、几档无对属、总共几档，全部由 `members`（`ModelTier` 值面）与
  `bridge`（`LANE_TIERS` 值面）现场算；顺序取名册顺序；道与档同名（`analysis`）时两侧都贴标签。
- `app/api/v1/observability.py:902 slo_units()`：先落两枚局部名册 `budget_members` / `lane_bridge`，
  `members`、`bridge_from_product_lane`、`bridge_note` 三格同源；那一格取值从字面量换成
  `_slo_bridge_note(budget_members, lane_bridge)`。
- 🔴 零新路由、零新对外字段：`slo_units()` 三格键名、预算格键名、`slo_slot_caliber()` 顶格集一字未动
  （牙：`tests/test_r533_bridge_note_is_derived.py::test_the_published_shape_did_not_change`）。
  改的只是一枚已在册键的**值**由抄写变成派生 ⇒ 不构成形状变更，无需停手回报。
- 今日派生读数（逐字，施工期零争用探针现取，不 import 项目包、不起 pytest）：

  ```
  not one-to-one: 1 budget tier of the 7 is shared across lanes: lanes `analysis` and `report` on tier `analysis`; 5 budget tiers of the 7 are named by no lane: `plan`, `compress`, `rewrite`, `code` and `alert`
  ```

  旧那句写 `six`、且把成员名 `ModelTier.ANALYSIS` 手抄进散文；新那句一枚手写枚数、一枚手写成员名都没有。

## 3. 判据① ——句子由名册派生，且不在别处留下手写枚数

件：`tests/test_r533_bridge_note_is_derived.py`（12 枚，319 行）

| 钉 | 咬的是哪一格 |
|---|---|
| `test_bridge_note_is_a_call_into_the_rosters_not_a_literal` | 源文 AST：那一格必须是 `_slo_bridge_note(budget_members, lane_bridge)` 这一枚 Call，`Constant` 即红 |
| `test_the_derivation_lives_inside_observability_and_adds_no_surface` | 派生函数在 observability.py 内；没给自己开出路由 |
| `test_neither_function_smuggles_a_count_into_prose` | `slo_units` / `_slo_bridge_note` 两枚函数里任何字面量（含 f-string 常量片、docstring）都不许「数词紧跟名册名词」 |
| `test_the_stale_hand_typed_sentence_is_dead_on_the_page` | 旧那句整句与半句（`belong to no lane at all`）在观测面源文里彻底死 |
| `test_the_note_agrees_with_the_rosters_it_is_derived_from` | 句子里每一枚数字都必须等于两名册现取读数之一，且总数格必须真等于 `len(members)`；英文枚数词（two…twelve）一枚不许出现 |
| `test_the_shared_half_names_the_lanes_that_share` / `test_the_unlaned_half_names_every_tier_no_lane_owns` | 共用半句与无对属半句的成员名＝现取名册，一枚不多一枚不少，顺序即名册顺序 |
| `test_the_published_shape_did_not_change` / `test_the_note_is_the_same_object_the_surface_publishes` | 形状锁；`/slo` 回执那格与 `slo_units()` 那格同源，不是第二份抄本 |

枚数一律不写死：所有期望值由 `contracts.ModelTier` 与 `nodes.LANE_TIERS` 现取（`from` 式绑定会被
monkeypatch 绕过，所以件里一律走模块属性现读）。

## 4. 判据② ——名册一动、话就跟着动（影子端注入一档）

| 影子动作 | 句子的读数（施工期零争用刀架现取） |
|---|---|
| 真名册（7 档／3 道） | `… 1 budget tier of the 7 is shared across lanes: lanes `analysis` and `report` on tier `analysis`; 5 budget tiers of the 7 are named by no lane: `plan`, `compress`, `rewrite`, `code` and `alert`` |
| `ModelTier` 注入一档 `shadow_extra`，lane 对属一字不动 | `… 1 budget tier of the **8** …; **6** budget tiers of the **8** are named by no lane: `plan`, `compress`, `rewrite`, `code`, `alert` and `**shadow_extra**`` ⇒ 句子随名册变 |
| 把 `report` 改配到 `plan`（共用消失、无对属少一枚） | `not one-to-one: 4 budget tiers of the 7 are named by no lane: `compress`, `rewrite`, `code` and `alert`` ⇒ 共用半句自己消失 |
| 名册换成一一映射 | `one-to-one: each of the 2 product lanes budgets on its own of the 2 budget tiers` ⇒ 不许再假称「not one-to-one」 |
| 桥为空 / 桥指一名册外的档 | 全 7 枚无对属 / 追加 `the bridge points at `ghostly`, which the budget roster does not have` |

牙：`test_growing_modeltier_with_a_shadow_member_moves_the_sentence`、
`test_repointing_one_lane_moves_the_shared_half`（两枚都用 `monkeypatch.context()`，窗尾断言句子与名册
双双回到原样＝变异不许漏在活模块上，R466 姿势）；`test_the_sentence_is_a_function_of_the_rosters_alone`
钉纯函数面。**在册件里没留下任何新的手写枚数**：本单只改 observability.py 一枚文件，且那两枚函数现在
一枚数都不带（`test_neither_function_smuggles_a_count_into_prose` 就是这一格的牙）。

## 5. 反证刀（`tests/test_r533_counter_evidence_teeth.py`，13 枚，316 行）

影子＝observability.py 源文的内存副本＋`tmp_path` 上的副本回挂（仓里一字节不落）；每把先正控后摘刀；
`_cut` 进刀前后各核一次 `app/api/v1/observability.py` 的 sha256，总清点那三枚用例（`test_z9`／`test_z9b`／
`test_z9c`）查台账：五把刀全真摘过、点名钉全真咬红、八枚被跟踪件（含契约纸与 `migrations/manifest.json`）
指纹仍是进门那些、活模块那两枚把手身份没被换过。锚点在源文段内命中 ≠1 即当场拒（死牙不算牙）。

| 刀 | 摘掉的那一格 | victim（点名在册钉） | 离线刀架读数 |
|---|---|---|---|
| K1 | `slo_units` 的 `bridge_note` 退回基点那句硬编（写 `six`） | `test_the_note_agrees_with_the_rosters_it_is_derived_from`（＋源文侧 `bridge_note_value_node`/`prose_counts`） | 红＝`AssertionError`；源文侧：那一格不再是 Call、散文扫描命中 `slo_units: 'seven budget tiers'` |
| K1b | 同一格退回「今天派生出来的那串」的硬编（枚数取自现读，不手抄） | `test_growing_modeltier_with_a_shadow_member_moves_the_sentence`、`test_repointing_one_lane_moves_the_shared_half` | 两枚皆红：「注一档进名册而句子一个字都没动：那句还是手抄的」 |
| K2 | 派生里无对属那一支的总数改读桥（`len(members)`→`len(lanes_by_tier)`） | `test_the_note_agrees_with_the_rosters_it_is_derived_from` | 句子变成 `… 5 budget tiers of the **2** …`；枚数对判钉红 |
| K3 | 共用那一支门槛钝掉（`len(lanes) > 1`→`> 2`） | `test_the_shared_half_names_the_lanes_that_share`（红在共用那半句上，派工词点名的形状） | 共用半句整支消失 |
| K4 | 无对属那一支只留数、摘掉成员名 | `test_the_unlaned_half_names_every_tier_no_lane_owns` | 名册名对判钉红（数对而名册丢了也是假话） |

正控：`test_k1_positive_control_…`／`test_k1b_positive_control_…`／`test_k2_positive_control_…`／
`test_k3_positive_control_…`／`test_k4_positive_control_…` 五枚，未摘刀时全部要求在册钉先绿。

## 6. 判据④ —— R526 那两枚在册件合跑仍 40 passed

- 本席改**前**基线（09-30 10:5x，be-r533，主树 venv＋本树 cwd，现取）：
  `python -m pytest tests/test_r526_slot_caliber_closure.py tests/test_r526_counter_evidence_teeth.py -q -p no:randomly`
  → **40 passed in 3.65s**（19＋21，与派工词所给枚数逐字相符）。
- 改**后**合跑：🔴 本单未跑（11:20 起 run10 真机跑分窗，窗内一枚 pytest 都不起；见 §9 代跑清单）。
- 两枚在册件里**没有一枚钉住那句散文**（现取：`git grep -n "bridge_note|one-to-one|belong to no lane" -- tests/test_r526_*.py`
  → 零命中；`test_k9b_the_forgeries_stay_out_of_the_shipped_pages` 只要求伪造串不出现在 observability.py，
  本单没往 observability.py 写任何伪造串）。⇒ 不需要走「取证＋总控裁」那条改口出路。
- 只读对拍、一字未改：`tests/test_r526_slot_caliber_closure.py`、`tests/test_r526_counter_evidence_teeth.py`、
  `tests/test_r105_slo_contract.py`（三者 `git status` 均未列出）。

## 7. 判据③ —— 契约那一格的成段原文（交总控代笔 splice；本单一枚字节没碰契约）

对应代码派生读数＝§2 那句逐字（现取）：`1 budget tier of the 7 is shared across lanes …; 5 budget tiers
of the 7 are named by no lane …`。契约 `docs/api/contract-v1.md:1580` 与 `:1582` 那两枚 bullet 现读为
「`analysis` and `report` share one budget tier」与「Five of the seven budget tiers (`plan` `compress`
`rewrite` `code` `alert`) are named by no lane at all」。建议替换为下面两段（枚数与成员名都不再抄写，
只指向同一枚派生读数）：

```markdown
- Product lanes and budget tiers are not a bijection, and this document does not do the arithmetic:
  how many budget tiers are shared across lanes, which lanes land on them, and how many budget tiers
  are named by no lane (out of how many) are the readout of
  `slo_units()["model_budget_tier"]["bridge_note"]`, which `observability.py::_slo_bridge_note` spells
  out of `members` × `bridge_from_product_lane` on every read. The tiers named by no lane are work
  performed *inside* one lane's request, which is why a budget-tier split and a per-tier SLO can never
  be drawn from the same table.
- The shape is pinned, the number is not retyped: `tests/test_r533_bridge_note_is_derived.py` grows
  `ModelTier` by one shadow member (and separately repoints one lane) and requires that sentence to
  move with the roster. This row used to say *five* while the module said *six* -- two copies of one
  count edited by hand on two surfaces, which is exactly the defect R526's caliber skeleton forbids;
  there is now one source and no count here to disagree with it.
```

🔴 建议**不要**把今天的 1/5/7 抄回契约：那等于把派生读数又手抄一份进散文，下一格名册演进时它就是
新的假话（本单的存在理由）。要留一个可读的今天数，请留在 `docs/testing/` 这面（本纸 §2/§4 就是）。

## 8. 行尾与铺树注意（给总控的 R531 归位器）

- 本树是 `git worktree add --detach` 新建的，本机 `core.autocrlf=true` 且无 `.gitattributes` ⇒ 检出后
  **盘上是 CRLF**，而主树在册那几枚件盘上是 LF：所以 `Get-FileHash` 直接比两棵树会得到 `contract-v1.md`／
  两枚 `test_r526_*` 「不一样」的假读数。真读数以 git 为准：`git -C be-r533 status --porcelain` 未列出这些件
  （逐字节等价 modulo CRLF），本单只改 `observability.py` 一枚。
- 两枚新件与本纸按同目录在册惯例落 **LF、零 CR**（现取 CR=0；两枚件的 sha256 连同本纸一起进反证件
  `FINGERPRINT_AT_IMPORT` 那串台账，摘前摘后各核一次）。
- 被改的 `app/api/v1/observability.py` 在本树盘上是 CRLF（我按盘上行尾原样写回，没顺手统一）；并树时请按
  主树在册惯例铺成 LF，别整片拷贝。

## 9. 待总控代跑（窗内本单不起 pytest；命令原文照抄即可）

```powershell
# 全量门之外，本单点名件（主树 venv，并树后在干净树复跑一遍＝AGENTS 那条两遍数字）
cd C:\Users\fengx\PycharmProjects\be-r533
python -m pytest tests/test_r533_bridge_note_is_derived.py tests/test_r533_counter_evidence_teeth.py -q -p no:randomly
python -m pytest tests/test_r526_slot_caliber_closure.py tests/test_r526_counter_evidence_teeth.py -q -p no:randomly   # 判据④ 要 40 passed
python -m pytest tests/test_r105_slo_contract.py tests/test_r32_lane_contract.py -q -p no:randomly                      # 同面邻件：读过 slo_units/LANE_TIERS 的在册钉
```

本单离线核过的部分（零 import、零 pytest、零写盘）：`py_compile` observability.py 通过；两枚新件 `ast.parse`
通过；派生函数与两枚名册钉在桩名册上 9 枚全绿；五把刀逐枚验过「摘了必红、收刀复绿」。**没核过的**是必须
真 import 项目包的三枚形状钉（`test_the_published_shape_did_not_change`／
`test_the_derivation_lives_inside_observability_and_adds_no_surface`／
`test_the_note_is_the_same_object_the_surface_publishes`）与两枚件在真 pytest 下的合跑枚数——这两格按实交回，
不写成已达。

## 10. 未达格（逐枚点名，没洗绿）

1. 🔴 判据④ 的**改后**合跑读数：本单未取（窗内禁跑）。§6 只有改前基线 40 passed 与「没一枚钉住那句散文」的
   静态取证，代跑件名在 §9。
2. 🔴 判据② 的「读数交句子随名册变」目前是**施工期零争用刀架**读数（桩名册＋从盘上摘出的真派生函数），
   不是真 pytest 在活模块上跑的读数；真读数请由 §9 第一行交出（件里那两枚钉本身就是这条的证据面）。
3. 🔴 判据③ 只交回成段原文，未落契约纸（禁改清单）；splice 与「是否保留一个今天的数」由总控裁。
4. 🟡 在册隐患一枚（**写域外，本单不碰，只登记**）：`tests/test_r105_slo_contract.py:189`
   `assert unlaned == {"plan", "compress", "rewrite", "code", "alert"}` 把成员名手抄进在册件。它今天与
   名册一致，但 `ModelTier` 一演进它就是下一枚「散文里的数字」；本单的牙不覆盖它（它不读 `bridge_note`）。
   另：`app/agents/tools.py:776-777` 的 docstring 逐字引了旧那句 `"analysis and report share
   ModelTier.ANALYSIS"` —— 引用的是已改口的观测面，同样在写域外，登记待裁。
5. 🟡 R526 的交工纸 `docs/testing/r526-slo-caliber-closure.md` §7.2 那条「在册矛盾」登记今天被本单收掉，
   但那本纸在写域外，本单未改它的文字（是否改口由总控裁）。
