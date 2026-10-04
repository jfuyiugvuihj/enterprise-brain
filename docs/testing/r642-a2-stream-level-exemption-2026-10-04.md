# R642 · A② 甲案：豁免第④条从轮级比源换成流级比源（2026-10-04）

一句话结论：**判据② 在 `run19` 读 False 是量具失明，不是产品断流。**R215 豁免四条里第④条拿「本轮交回评分器的那份字」当比对对象，而 `approved_ok` 那一族天然两条流（同步流道挂起后被批准），断裂住在挂起轮、交付来自批准腿 —— 两窗 19/19 枚终答都比挂起轮那份字长，那一条件对这一族**恒假**。甲案只换第④条的比对对象：同一条流内不许换源，跨流不许互相比源。🔴 ① ② ③ 一字未动，`prefix_breaks` 一字未动，「豁免只把坏形分家」那枚恒等式一字未动，帧账一行的键集一格未多。

归因不在本纸里重述，凭据＝`docs/perf/r614-uncorrected-break-attribution-2026-10-03.md`；乙案（读数侧分档）已由 R619 并树 `718ab1e`，本席 `git merge-base --is-ancestor 718ab1e HEAD` 现取 rc=0。甲案与乙案是两条腿：乙案在判据侧把这一族单分一档，甲案治量具判定层那一枚恒假的条件，🔴 两枚不许互抄、不许互相顶掉。

本单零容器、零连库、零模型。产物＝这份纸 + `scripts/eval_transport_ask_v2.py` 的改动 + `tests/test_r642_a2_stream_level_exemption.py`。

## 1. 改了什么（判定层只动一处）

`_corrective_readings` 里第④条那一行，从

```
if str(record.get("text") or "") != answer_text:
    continue  # ④ 屏上没真替换成交付的那份字
```

换成调用 `_stream_level_correction(frame_text, answer_text, deliveries, stream)`：

- **轮级那一条原样排第一**：断裂帧逐字等于本轮交回评分器的 `answer` —— 单流轮（同步道全部形状、R215 当年在册用例那一族）读法一字不改。
- **或**流级三条**同时**成立（缺一条不算）：
  - (a) 断裂所在那条流**不是最后一条流** —— 末流那一族只许用轮级那一条判，本条不给它开后门；
  - (b) 断裂帧逐字等于**它所在那一条流自己交付的**那份字（同一条流内不许换源）；
  - (c) 本轮终答以它为前缀 —— 批准腿是接着往下写，不是屏上换了第二份字。

判定用的「每条流交付的那份字」＝`_fold_frames` 折进内存账的 `stream_deliveries`，🔴 与 `break_frames` 同一格纪律：**只活在内存里、只喂第④条、一列都不进账**（见 §4 为什么必须这样）。

## 2. 不变量（动了就是没收工）

- 🔴 原始账一格不漂：`prefix_breaks` 照旧写进帧账，豁免只体现在 `uncorrected_breaks`；`prefix_breaks − 豁免枚数 == 判据②读的那一格` 那枚恒等式两边都成立，`tests/test_r215_recomputing_run6_frames.py` 没改语义、没加豁免。
- 🔴 本腿不吃 `prefix_breaks`：`_frame_verdict` 读的是 `uncorrected_breaks`，这条不许被「顺手统一」。常驻牙用 AST 现读那枚函数里 `readings[...]` 的键用集，不搜散文：`test_the_verdict_leg_still_does_not_read_prefix_breaks`。
- 🔴 宁可少豁免一次，不可多豁免一次：见 §3 那四把刀与主刀反证。
- 历轮可比性：`run6` 那 105 行只读原件的逐位复算（`test_r215_recomputing_run6_frames`）在两态都绿；当年读数一律不重判。

## 3. 判据② · 两把刀 + 四把影子刀（`tests/test_r642_a2_stream_level_exemption.py`，20 枚）

命令原文：

```powershell
cd C:\Users\fengx\PycharmProjects\be-r642
.\.venv\Scripts\python.exe -m pytest -p no:randomly -q tests/test_r642_a2_stream_level_exemption.py
```

影子端一律落 `tmp_path` 副本（R253 纪律），每把刀按唯一锚点动刀，锚点在原件里不唯一就当场红（空响的刀不算刀），跑完现读被跟踪量具 sha256 与 import 那一刻逐字节相同。

| 刀 | 摘掉的东西 | 咬住它的用例 |
|---|---|---|
| `ROUND_LEVEL` | 把第④条退回改前的轮级比源 | 正控那一枚必须**改前红／改后绿**（同一份 trace 两棵树各跑一遍） |
| `DROP_PREFIX_GATE` | (c) 前缀闸 | 主刀「屏上换成另一份答案」会被洗成绿 ⇒ 证明 (c) 真的站着 |
| `DROP_DELIVERY_GATE` | (b) 流内交付比对 | 空尾帧那一形：单独摘 (b) 仍拦得住 ⇒ guard 不是空的 |
| `DROP_EMPTY_GUARD` | 空帧 guard | 空尾帧那一形：单独摘 guard 仍拦得住 ⇒ (b) 不是空的；两枚一起摘才放行（双保险互证） |

主刀读数（现取）：`SWITCHED` 那一形（挂起轮换源、批准腿交回**另一份**答案）在改后仍 `corrective_replacements=0 / uncorrected_breaks=1 / criterion_two_holds=False`；同一份喂摘掉 (c) 的影子端 ⇒ 被洗成 `1/0/True`。🔴 把它豁免掉＝刀折断，这一枚折断由常驻牙当场报。

另有三条不落在散文上的形状：一轮两枚坏形仍只豁免一枚（②）、末流坏形不吃流级那一条（(a)）、单条流那族在四枚不同 `answer`（含 `None`／哨兵串／空串）下两棵树逐格全同。

## 4. 判据② · 真材实料复算（run19 那两枚真行）

命令原文（离线，件在 `%TEMP%\r642\a2_real_control.py`；同一份输入喂**改前那份量具**（`git show 2103890:scripts/eval_transport_ask_v2.py`）与**改后这份**）：

```powershell
git show 2103890:scripts/eval_transport_ask_v2.py > $env:TEMP\r642\head_instrument.py
.\.venv\Scripts\python.exe $env:TEMP\r642\a2_real_control.py
```

现取读数：

```
-- report-09  双流·挂起轮换源（终答以挂起轮那份字为前缀且严格更长 startswith=True）
   盘上帧宽 stream0=[20, 40, 60, 636] stream1=[689] ｜ 断裂帧 sha 3d572eff169a＝pre_answer ｜ 终答 sha 9a52943ae2d8
   片帧不是交付文本前缀的证据：等长前缀 sha 与盘上不符的片帧 3/3 枚 [20, 40, 60]
   盘上原文       pb=1 corr=0 unc=1 holds=False first_break_at=[4, 0]
   改前的量具      pb=1 corr=0 unc=1 holds=False first_break_at=[4, 0]
   改后的量具      pb=1 corr=1 unc=0 holds=True first_break_at=[4, 0]
   改前复算 vs 盘上原始账：漂 0 格 （逐格同数）
   改前 vs 改后唯一在动的格：['corrective_replacements', 'uncorrected_breaks', 'criterion_two_holds'] ｜ 恒等式两边 pb=corr+unc：True

-- tool-02  …（同形：stream0=[19,41,62,82,103,123,136,225]，断裂帧 f42f05809da2＝pre_answer，终答 cf1c4c36b875）
   盘上原文 改前 改后 三行读数与 report-09 完全同构：1/0/1/False → 1/0/1/False → 1/1/0/True
   改前复算 vs 盘上原始账：漂 0 格
```

三件事一次交清：① 改前那份量具在真材实料上**复现盘上那枚红**（`pb/corr/unc/holds/first_break_at` 与原件逐格同数，13 格原始账漂 0 格）；② 改后同一份输入读绿；③ 两棵树之间在动的只有「豁免分家」那两格 + 判定那一格。

反证刀同样在真材实料上跑了一遍：把 `report-09` 的批准腿换成**另一题的真答案**（`tool-02` 那份 278 字，`startswith=False`）——

```
   改前的量具      pb=1 corr=0 unc=1 holds=False
   改后的量具      pb=1 corr=0 unc=1 holds=False  🔴 仍判红＝反证刀有牙
```

四枚单流受控纠正真行（`metric-03`／`metric-11`／`report-06`／`scope-04`）复算：原始账漂格＝无，改前/改后逐格差＝无，盘上原文 `pb=1 corr=1 unc=0 holds=True` 照旧。🔴 这一族本单没碰。

**重建的诚实边界**（不许读成「盘上原文复现」的另一半）：断裂帧＝`pre_answer`、批准腿帧＝终答，这两枚逐字对得上盘上 sha（现算 `3d572eff169a`／`9a52943ae2d8`／`f42f05809da2`／`cf1c4c36b875`）；**片帧的正文当年没落账，只落了 sha**。本件现算并点名「片帧等长前缀的 sha 与盘上不符」（report-09 三枚全不符、tool-02 七枚里四枚不符）⇒ 片帧不是交付那份字的前缀，坏形正是因此成立；所以代表片帧只要求「同长度、逐条互延、且不是交付文本的前缀」这一**形状**，不冒充正文。③ 那枚武装 step 的 payload 盘上同样读不到，按 R614 §2 推定武装（账上紧邻 + 与已被量具自己豁免过的四枚同形），这一条在常驻牙里由 `_arm()` 显式喂入，🔴 不许读成盘上证词。

## 5. 键集一格不多 + 顶回派工词的一条前提

派工词 §一② 与 R614 §4 都写着甲案「落地代价是多带每条流交付文本的指纹」。**这条前提本席现取顶回**：

- `per_stream` 那一格的**元素键集**被在册件逐位钉死 —— `tests/test_r215_recomputing_run6_frames.py` 把 `per_stream` 列进 `RAW_CELLS`，拿 `docs/testing/sidecar-run6-frames.jsonl` 原件逐格**逐位对判**；`tests/test_r181_text_frame_ruler.py` 与 `tests/test_r223_frame_arrival_clock.py` 另有对 `per_stream` 元素形状的断言。往那一格多塞一枚 sha ⇒ 打断 run6 原件复算 ⇒ 正是本单第二节禁的「原始账漂了」。
- 所以判定用的交付文本**只活在内存**，与 `break_frames` 同一格纪律。帧账一行的顶层键集一格未多，`FRAME_ROW_KEYS`／`FRAME_READING_KEYS` 那两枚**对判**闸（多一列红、少一列也红）一字不改 ⇒ **甲案不需要总控补任何键集名单**，也不需要动纸。
- 派工词 §二那条「只许按判据加键」在本单落成**零加键**，并附翻面证明（判据③）：`test_the_frame_row_key_set_did_not_move_and_the_gate_still_flips` —— 把内存那一格冒充成顶层列 promote 进账，同一枚对判当场红；把在册那一格 `prefix_breaks` 摘掉，同样红（证明它是对判、不是子集）。D-3 那一侧同形：新格嵌在 `queue` 里面，见 `docs/testing/r642-d3-post-approval-readback-2026-10-04.md` §6。

## 6. 交回总控的账面项（🔴 本单不落地）

1. 跟进单 §167 二／§172 二 需补记：A② 甲案已落地（量具判定层第④条流级），🔴 **历轮读数不重判** —— `run19` 那两枚在册红字仍是当年读数，甲案只让**下一扇窗**开始读对；要在账面把 A② 翻绿，得拿带本单货的新窗（run22／D 相 2）读数说话。
2. 契约无漂：`docs/api/contract-v1.md` 与本单无关（改的是评测量具内部判据，不涉及任何 HTTP 形状），故本单没有「逐字替换句」交回。
3. `scripts/collect_evaluation_answers.py` 那段把豁免四条抄成口径的抬头文字（R215 抬头），纸面与码现在差一句（第④条多了流级那三支）；🔴 那枚文件不在本单写域，请总控落纸。

## 7. 未验清单

1. 🔴 **下一扇窗的真读数＝未验**：本单证明的是「改前红／改后绿」在真材实料复算上成立，不是「A② 已达标」。达标要 run22 那扇窗里 `approved_ok` 那一族的 `uncorrected_breaks` 真读成 0。
2. **③ 武装那一枚＝推定**，盘上读不到 payload（R614 §5 同一格欠账），本单没假装补上。
3. **全量门＝未跑**（本单不跑）；两态亲跑同名件 32 枚各 `528 passed`，逐枚清单见 D-3 那份纸 §9。