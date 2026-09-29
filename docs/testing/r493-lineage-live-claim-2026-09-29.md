# R493 · 血缘纸 §9.6 那枚「拿不到钉的当下声称」怎么收，与两处过期叙述（2026-09-29）

工单：R493 · 执行层 Lorentz · 树 `be-r493` @ 基点 `438d67d`（detached，未建分支）。
被治的纸：`docs/perf/r387-label-lineage-2026-09-27.md`。解释器一律主树 `.venv`（本树没有 `.venv`，事故 #93）。

## 1. 三笔账与落点（门牌号一律本席现读，派工词给的号以实物为准）

| 账 | 派工词给的号 | 本席现读 | 落点 |
|---|---|---|---|
| ① §9.6 那格「当下声称」 | 约 :827 | 并树前第 827 行，恰一枚 `chat_ask_entry` 表格行 | 改写为丙类历史操作账 + 表前加一节级图例 + 新增 §9.8 记理由 |
| ② 过期的「受检只有 §1」 | 说在 §9.5 约 :652 | :652 在 **§8.8** 未做 3（§9.5 从 :756 起，本节没有未做清单）；另一枚在 §9.7 未做 4（:879） | 两格按实物改写，受检面清单只落 §8.8 未做 3 一处 |
| ③ §9.3 那行「46 枚锚里没有它」 | 约 :711 | :711 现读仍在 §9.3，枚数 46 = `len(LINEAGE_SITES)` 派生值 | 走乙案 ⇒ 枚数一字未改；改由新钉 import 真源逐处对账 |
| 三格成对叙述（判据⑤） | 说在「§1 表旁」 | 实在 **§8.7**（并树前 :526 / :527 / :532），§1 表旁一枚都没有 | 三枚逐字节未动，sha256 前 16 位复认见 §4 |

## 2. 甲案（补锚 46→47）为什么走不通

1. **在册互覆闸拦死**：`test_the_anchor_table_and_the_templates_share_one_ledger` 只许「被 `LINEAGE_TEMPLATES`
   的 site/note 或 `HOP_DOC_CELLS` 引用到的锚」存在。影子复跑（`git archive 438d67d` 导出；`git ls-tree -r HEAD --name-only` 现取 1359 枚在册文件，影子实到 1345 枚，
   差额是 `documents/` 里非 ASCII 命名的样例文件在 Windows 上落不下，与本单三枚件无干，
   副本里只往 `LINEAGE_SITES` 顶端加一枚锚、其余字节一字不动）：锚表 47 枚、`LINEAGE_ANCHOR_FAILURES = []、
   token 恰一枚唯一命中、`--emit-doc-cells` rc=0，而 teeth 单跑 = **42 passed / 1 failed**，红句
   「锚块表里有没人引用的死锚：['askentry']」。要让它不红就得动模板——超出本单「只许动 `LINEAGE_SITES`
   一处」，且那枚闸件本身在禁域。
2. **该进的账不是这本账**：那枚 token 是问答主入口（`async def ask` 头上那行装饰器），不在「上传 → 打标签 →
   落库 → 读侧谓词」那 12 跳上；塞进血缘模板就是给血缘表凭空造一跳搬运关系。
3. **46→47 会打翻在册历史账**：§8.8 未做 1「46 枚锚是在 `ANCHOR_BASE_COMMIT` 那一枚基点的内容上挖出来的」与
   §8.5「75 枚锚块唯一命中普查（46 格 × 起/终点）」都是原样留档的账，判据⑤不许顺手清理。

⇒ 走**乙案**：那一格降为丙类历史操作账，只记 R400 在基点 `6a8063a` 上那一次的读数（第 2224 行，
本席在同一枚基点的 blob 上复现同值），并写明此数不再随并树核对。

## 3. 收口（账面清零是两头一起改的）

- `tests/test_r492_live_claim_boundary.py`：`KNOWN_UNPINNED` 由 (("9.6", "app/api/v1/chat.py"),) 收到 **()**；
  §1 表旁那句自守同时补上"名单今天清零、豁免一处不剩"那一笔。只改一处必红（`test_the_ledger_matches_the_gaps_read_from_the_book`）。
- 同件那枚 `test_teeth_d_an_empty_ledger_exposes_the_debt` 重铸：旧形拿「纸上今天恰有一枚欠账」当量具，欠账
  一治好它必红（牙的形状跟着账走）；新形两问各归各——盘上零欠账且名单也空，再在内存里造一枚无主现读坐标，
  名单空着必红、给它记上名必只登记不红。件内 `def test_` 枚数 **10 枚不变**。

## 4. 实测读数（数字全部本回合亲跑）

- 派生闸：`scripts/r387_label_lineage.py --emit-doc-cells` rc=**0**；
  `scripts/r387_backfill_estimate.py --no-db --verify-plan-table` = **MATCH** rc=**0**（渲染 50 行）。
  🔴 派工词把 `--verify-plan-table` 记在 `r387_label_lineage.py` 名下，本席现读该件无此开关（rc=2
  unrecognized arguments），它在 `r387_backfill_estimate.py` 里。
- 三格成对叙述 sha256 前 16 位（现读复认，与在册等值）：f650180e0e9fc769 / 6e00b0634242d39d / a0e2c19d8dc76a29。
- 本文档形态：`docs/perf/r387-label-lineage-2026-09-27.md` 改后 CR=LF=CRLF=947、裸 LF=0、无 BOM、U+FFFD=0。
- 当下声称的病灶实证：那枚 token 在基点 `6a8063a` 的 blob 里第 2224 行，在本树工作区里第 **2431** 行
  （`TOOL.anchor_lines` 现场解出；09-29 现取，属本席那一次的读数，不再核对）。漂了 207 行而门是绿的——
  这就是它当初不该写成「今天现读」的理由。
- 硬不变量：`rg -c classification_blocked app/` = **0 命中**（rc=1）；`git diff --name-only` 只列出
  `docs/perf/r387-label-lineage-2026-09-27.md` 与 `tests/test_r492_live_claim_boundary.py`，`app/**` 零改动；
  `scripts/r387_label_lineage.py` 一字未动（授权未用）。

## 5. 新钉 20 枚（逐枚点名）

`tests/test_r493_s96_ask_entry_is_history_not_live_claim.py`（10 枚）：那一格不再自称现读且行内零坐标主张；
基点 blob 复现同值；今天的行位与历史那格不等且不是任何锚的端点；纸面锚枚数每一处 == `len(LINEAGE_SITES)`；
名单两头一起清零且闸仍在核东西；§9.6 表前图例在场（而 §9.3 的表头必须继续自称现读，防洗白）；
甲案塞锚即被在册闸点名；乙案把当下声称塞回即被边界闸点名；本件不抄坐标；本件不动取档脚本。

`tests/test_r493_checked_scope_narration.py`（10 枚）：两枚过期形状已消失；受检面清单点到每一格都在场；
清单具名点到的件逐枚回盘验存在；已做掉的范围不写成待办；三格成对叙述逐枚按 sha 复认；五处历史账
原样留且 §1 自守形状完好；「看见但没治」那一格的哨与账必须同框；纸面仍是纯 CRLF 无 BOM 无替换字符；
本件不抄坐标；本件不动取档脚本。

## 6. 没做到 / 要总控裁

1. §3 段末那句用「今天」引出的那枚坐标仍是过期的，且两枚闸都看不见它（闸只认「现读」两个字）。要治它得先
   扩 §1 甲类口径——**口径变更**，本单未动，只在 `test_r493_checked_scope_narration.py` 钉了"哨与账必须同框"。
2. 授权动 `LINEAGE_SITES` 那一处没用（乙案不需要）。
3. §9.7 未做 5 那句「两格派工词引用在本仓读不出」按读数不追溯改写原样留，更正另记在 §9.8 第 ⑥ 格。
4. 没跑全量门；没起服务、没连库、没打模型、没动容器；`app/**`、`frontend/**` 与全部禁域件零改动。
