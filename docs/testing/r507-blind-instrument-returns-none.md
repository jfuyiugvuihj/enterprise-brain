# R507 · 量具被摘瞎那一窗改读「未量」，不许再读成「量过了且没重合」

> 执行层 R507 · 2026-09-29 · 工作树 ``be-r501``，基点 ``8857a8d``（开工 ``git status --porcelain`` 为空）
> 本件只治**读数件**（尺子交回什么），不治产品、不动帧账那一行、不动判定取值。
> 🔴 坐标全部现取（``rg -n``，2026-09-29 本席亲手）；工单词里的行号一处不复用。

## 1. 一句话

``scripts/eval_transport_ask_v2.py`` 的 ``_cross_stream_repeats``（:683，判定视图里那枚证词叫
``cross_stream_repeat_frames``）此前把「帧在、逐帧一枚 ``sha`` 都拿不到」那一形折成 **0**，与它 docstring
的承论（「派生不出＝这一格今天没量过」）相反。今天起：**一枚指纹都没拿到 ⇒ 回 ``None``（未量）**；
拿到了指纹且确实没有跨流重合 ⇒ 才回 0。两形分开，不许并脸。

## 2. 病（假零，事故 #73 那一族）

落码里 ``if not sha: continue`` 把没指纹的帧逐枚跳过，末尾照样 ``return repeats``（此时恒为 0）。于是
「量具被摘瞎」那一窗（``_count_text_frame`` 瞎了、或某条道根本不写逐帧指纹）在纸面上读成
「量过了且没重合」= 一枚假绿。这与 ``docs/testing/r506-a2-reading-2026-09-29.md`` §5 第 5 条给复算件记的
那一笔是同一枚缺陷的两个分身，也正是 P-18「量具第二次以假零骗过操作员」那一族。

## 3. 两形分开后的语义（写死，不许再并）

| 输入那一形 | 改前（``8857a8d``） | 改后（R507） | 读法 |
|---|---|---|---|
| 帧在、一枚 ``sha`` 都没有（摘瞎窗） | ``0`` | ``None`` | 这一格今天**没量过** |
| 帧在、指纹在位、确实没有跨流重合 | ``0`` | ``0`` | 量过了，本轮没有第二份正文 |
| 跨流重发（R464 批准腿病形） | ``1`` | ``1`` | 不许被本单顺手摘聋 |
| 同一条流内末片帧与收尾帧同文 | ``0`` | ``0`` | 总控裁定：不算出现两遍 |
| 入参不是帧表 / 枚数为零（空读那一形） | ``0`` | ``0`` | 🔴 本单不动，见 §6 第 3 条 |

判定取值一枚不漂：``_frame_verdict``（:791）在 :832-833 拿 ``int(readings.get(CELL,
REPEAT_DELIVERY_UNMEASURED) or 0) == 0`` 读这枚证词，``None`` 与 0 同权 ⇒ 本单改的是**纸面上的可分辨度**
（既不给摘瞎窗追加定罪，也不替它洗白），不是 ``criterion_two_holds`` 的真值。

## 4. 全仓谁读这枚返回值（现取调用点，不是只看签名）

**A. 真调用点（读 ``_cross_stream_repeats`` 的返回值）**
- ``scripts/eval_transport_ask_v2.py:854`` —— ``readings["cross_stream_repeat_frames"] = _cross_stream_repeats(arrivals["frames"])``，
  丙案：只在判定那一刻派生，🔴 **不落成新列**（帧账那四枚「键集是对判」的闸一枚不改）。
- ``scripts/eval_transport_ask_v2.py:832-833``（``_frame_verdict``）—— 仓内唯一消费者，``None``/缺省都折成「不再定罪」；
  折出来的真值写进 ``row["criterion_two_holds"]``（:855）落帧账。``rg -n`` 全文点名：除这两处没有第三枚读者。
- 测试读者：``tests/test_r471_second_copy_of_the_answer_body_is_not_a_pass.py:123``（``_derived`` 包装）、
  ``:277``（尺与复算件逐行对判）、``:380``、``:405``（拿真账复算）、``:449``（``[]`` 那一形在册回 0）。
- 本单新增：``tests/test_r507_blind_instrument_returns_none.py``（8 枚，``:74``/``:83``/``:94`` 是三形那几行）。

**B. 同名口径的独立分身（各自一套落码，不调用 A，但共享同一枚缺陷）**
- ``scripts/r239_stream_gap_offline_audit.py:138``（离线复算判器，🔴 本单禁碰件）：:153 只对「非列表 / 空列表」
  回 ``None``，:161 ``if not sha: continue`` 跳完之后 :167 ``return repeats`` ⇒ 摘瞎形今天仍读 0。
- ``scripts/eval_frame_caliber_readout.py:61``（``_repeats_of_records``）与 :82（``derived_repeats``）：只有「整份账
  一枚帧都没有」才回 ``None``（:91）；「帧在而无指纹」那形会交回一张每行都是 0 的表，照样是假零。

**C. 判器那枚读数的下游（本单没改它，列出来是为了别把绿灯读成已治）**
- ``scripts/r239_stream_gap_offline_audit.py:188``（``recomputed_ledger`` 的 ``in (None, 0)``）、:269（``judge_row``）、
  :294/:309/:311（``cross_stream_repeat_ids`` 与 ``cross_stream_repeat_unmeasurable``）、:340-341（报表那一行）。
- 在册纸面：``docs/testing/r471-verdict-caliber-2026-09-29.md``、``docs/testing/r506-a2-reading-2026-09-29.md`` §2.D 与 §5 第 5 条。

## 5. 对今晚真机窗的影响（逐枚点名）

- 🔴 **在册四份账一枚读数都不动**：拿 ``8857a8d`` 那把尺与本单终态并排逐行对判四份帧账，``old != new`` 的行数 = **0**。
  原因：摘瞎那一形今天在任何一份账里都不存在 —— 亲扫 ``docs/testing/sidecar-run6-frames.jsonl``、
  ``sidecar-run7-frames.jsonl``、``sidecar-run8p2-frames.jsonl``、``sidecar-run9-frames.jsonl``，「``frames`` 非空且
  一枚 ``sha`` 都没有」= 0 枚（run9 103 行带帧、全带指纹；run6/run7/run8p2 帧列为零枚）。
- run9 里 ``frames`` 为空的两枚 = ``metric-02`` / ``scope-02``：本尺照 §6 第 3 条仍回 ``0``（空读那一形未改），
  复算件那一路对它们本来就回 ``None`` ⇒ 今晚 ``重合量不出=2`` 那个计数一枚不因本单改变，
  ``docs/testing/r506-a2-reading-2026-09-29.md`` §2.D 那句**不必订正**。
- 真机窗里唯一会换脸的是**今晚现场被摘瞎**那一形：一旦某条道不写逐帧指纹，``cross_stream_repeat_frames``
  从此报 ``None``（未量）而不是 0。收窗读数因此要多读一句：**``None`` 的行不许并进「量过且干净」那一档**，
  必须单列成「这一窗这一格没量过」；``docs/testing/sidecar-run*-frames.jsonl`` 那几份帧账本体一个字不回写。
- ⚠️ 今晚仍**不能**拿离线判器的绿灯当证据：``scripts/r239_stream_gap_offline_audit.py`` 那半没治（禁碰），
  它对摘瞎形照样交 0，而 0 与 ``None`` 在 ``recomputed_ledger`` 里都算通过 ⇒ 两枚件今天对摘瞎窗的读数不一致。
  裁一刀之前请把「复算件的 ``cross_stream_repeat_ids`` 为空」读成**未证实**，不是已证实。

## 6. 本单没做的（明写）

1. 🔴 **``scripts/r239_stream_gap_offline_audit.py`` 那半未改**：工单禁令（``不得碰 scripts/r239_*``）与「治落码」
   互相排斥 —— 工单把缺陷坐标写成 ``scripts/eval_transport_ask_v2.py``，而那三枚行号 :153/:161/:167 逐字属于
   ``r239``（本席两头都现取过），禁令优先。给总控的一行补丁（与 ``_cross_stream_repeats`` 终态同形，两枚件才逐字同）：
   在 :153 之后、循环之前插入 ``if records and not any(str(rec.get("sha") or "") for rec in records): return None``
   （``records`` 即 :152 那个 ``row.get("frames")``），:157-167 一个字不动。
2. 🔴 **R506 那枚现状钉未改口**：它不在工单写的 ``tests/test_r506_a2_single_frame_not_green.py``（该文件只有
   ``test_a1``…``test_a6``，与本形无关，本单一个字没动它），实际在
   ``tests/test_r506_a2_ledger_required_keys.py:162::test_b6b_the_blind_instrument_shape_today_reads_zero_not_none``，
   且 :179/:180/:181 三枚断言读的全是禁碰件 ``audit.cross_stream_repeat_frames``。工单同时禁止碰 ``scripts/r239_*@
   并禁止 skip/xfail/包含式 —— 两条同时成立时「把它倒向 ``None``」只能交出一枚**永久红**的钉（判器没修，函数今天就回 0）。
   本席因此不动那枚钉，等总控同笔放行 ``scripts/r239_*`` + 那枚文件再倒向；那才是它自己 docstring 写的「该有的反应」。
3. **空读那一形（入参不是帧表 / 枚数为零）未改成 ``None``**：它钉在
   ``tests/test_r471_second_copy_of_the_answer_body_is_not_a_pass.py:449``（``_cross_stream_repeats([]) == 0``），
   那枚文件不在本单写域。残留后果：``[]`` 在本尺读 0、在复算件读 ``None``，两枚件这一形仍不同脸；
   要并口径请总控同笔改 ``:449`` 与 §6 第 1 条那一行。
4. **``scripts/eval_frame_caliber_readout.py`` 那半未改**：不在写域，见 §4.B。
5. 没跑真机窗、没打模型、没起服务、没碰容器、没连库、没跑 ``scripts/run_gate.py`` 全量门、没 commit/``git add``/push。

## 7. 凭据（执行层自报）

- 改动：``scripts/eval_transport_ask_v2.py`` numstat = ``11 1``（``+11/-1``，只有 ``_cross_stream_repeats`` 一枚函数体＋它自己的 docstring）；
  磁盘字节 sha256[:16] = ``906ad95704e15925``（两把刀跑完逐字节还原，复验 ``same=True``）；
  改前基线一律取 ``git show 8857a8d:``（blob ``43681b3897dc9ae1`` / 工作树 CRLF 字节 ``8a314573b6e05e5d``，``core.autocrlf=true``）。
- 新钉：``tests/test_r507_blind_instrument_returns_none.py`` = 8 枚，``8 passed``。
- 点名件复跑（29 枚读者件 + 本单新钉，改后终态）：``455 passed / 4 skipped / 0 failed``（78.10 s）。
- 反证刀①（把新分支改回旧形：摘瞎回 0）→ 新钉 ``3 failed, 5 passed``：``test_a1`` 原文
  ``AssertionError: assert 0 is None``；``test_a3`` 原文 ``AssertionError: (0, 0) / assert (0 is None)``；
  ``test_a8`` 原文 ``AssertionError: 摘瞎形的 None 分支被摸走了``。
- 反证刀②（把「真没重合」那一形改成回 ``None``，倒打一耙）→ 新钉 ``4 failed, 4 passed``：``test_a2`` 原文
  ``AssertionError: None / assert None == 0``；``test_a3`` 原文 ``AssertionError: (None, None)``；
  ``test_a5`` 原文 ``AssertionError: assert None == 0``；``test_a7`` 原文 ``assert None == 0``。
- 两形各回什么（同一输入并排，``8857a8d`` vs 终态）：摘瞎 ``0`` → ``None``；指纹在位且无重合 ``0`` → ``0``；
  跨流重发 ``1`` → ``1``；同流同文 ``0`` → ``0``；``[]``/``None`` 入参 ``0`` → ``0``。