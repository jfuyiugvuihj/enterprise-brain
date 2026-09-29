# R515 · 量具同口径分身那半把：摘瞎那一形改读「未量」，不许再摇假零

> 执行层 R515 · 2026-09-29 · 工作树 ``C:\Users\fengx\PycharmProjects\be-r515``，基点 ``85572c1``。
> 开工现取：``git -C be-r515 rev-parse --short HEAD`` = ``85572c1``（与派工词相符），``git status --porcelain`` 为空。
> 本件只治**读数件**（``scripts/eval_frame_caliber_readout.py`` 交回什么），不治产品、不动帧账那一行、
> 不动判定取值、🔴 不重判当年读数。
> 🔴 坐标全部现取（``rg -n``／逐形现跑），派工词里的行号一处不复用；本文全部数字为**执行层自报**，
> 达标与否由总控亲跑复验。

## 1. 一句话

R507 把 ``scripts/eval_transport_ask_v2.py::_cross_stream_repeats`` 治成「帧在而一枚逐帧指纹都拿不到 ⇒
回 ``None``（未量），不许报 0 冒充量过」，它的**同口径分身**留在 ``scripts/eval_frame_caliber_readout.py``
没治（``docs/testing/r507-blind-instrument-returns-none.md`` §4.B 与 §6 第 4 条挂号的那半把）。今天这半把
落了码：**整份账连一枚逐帧指纹都没参与判定 ⇒ ``derived_repeats`` 交回 ``None``**；一旦有指纹参与且确实
没有跨流重合 ⇒ 才交 0 枚。口径逐字取 R507 **并树后**那一份（``_cross_stream_repeats:717-719``），本件
不自创第二套。

## 2. 病灶复核（照总控现读的原话逐字对源码）

改前 ``_repeats_of_records:61``：:70-74 对 ``chars<=0`` 与 ``sha`` 为空两形各自 ``continue``，末尾照样
``return repeats``（此时恒为 0）；``derived_repeats:82`` 只有一道 ``any(row.get("frames"))``（:90），
它挡得住 ``frames`` 整列缺席与枚枚空表，**挡不住**「``frames`` 列在、枚枚有字、无一枚指纹」——那份账照样
交回一张每行都是 0 的表，纸面印成「``cross_stream_repeat_frames`` >0 枚数=0 题号=无」。
⇒ 复核成立，与本单判据同一句病灶。

## 3. 探针：改前哪些形状交 0（逐形现量，改后并排）

一次性量形探针（合成帧直接喂函数本体）。改前＝``git show 85572c1:scripts/eval_frame_caliber_readout.py``
（blob ``5c0b124cffa91f7a6163f8cc267d9842e340ec8c``，10565 字节，LF）；改后＝工作树终态。

### 3.1 行内那一只手 ``_repeats_of_records``

| 形状 | 改前 | 改后 | 定性 |
|---|---|---|---|
| 帧在、枚枚有字、无一枚 ``sha``（摘瞎） | ``0`` | ``None`` | 🔴 假零 → 未量（本单的牙） |
| ``sha`` 键在而是 ``""``／``None`` | ``0`` | ``None`` | 与摘瞎同一张脸 |
| 有指纹、确实无跨流重合 | ``0`` | ``0`` | 量过了且干净 |
| 有指纹、同一条流内末片帧与收尾帧同文 | ``0`` | ``0`` | 总控裁定：不算出现两遍 |
| 有指纹、跨流重发（R464 批准腿病形） | ``1`` | ``1`` | 不许顺手摘聋 |
| 枚数为零（``[]``） | ``0`` | ``0`` | 🔴 本单不越界（§6 第 2 条） |
| 入参不是帧表（``None``） | ``TypeError`` | ``0`` | 与 ``_cross_stream_repeats(None)`` 同脸 |

### 3.2 整份账那一只手 ``derived_repeats``（最后一列＝读的人看到什么）

| 形状 | 改前 | 改后 | 纸面 |
|---|---|---|---|
| S1 ``frames`` 整列缺席 | ``None`` | ``None`` | 派生不出（在册形，一字未改） |
| S2 ``frames`` 枚枚空表 | ``None`` | ``None`` | 派生不出（在册形，一字未改） |
| S3 有字无 ``sha``（摘瞎账） | ``[]`` | ``None`` | 🔴 改前读成「量得出且 0 枚重合」→ 改后读「派生不出」 |
| S3b 摘瞎行＋空表行混 | ``[]`` | ``None`` | 同上（整份账仍无一枚指纹参与） |
| S4 有 ``sha`` 但同一条流 | ``[]`` | ``[]`` | 量得出且 0 枚（干净，不许倒向 ``None``） |
| S5 正常（有指纹无重合） | ``[]`` | ``[]`` | 量得出且 0 枚 |
| S6 病形（跨流重发） | ``[('q1', 1)]`` | ``[('q1', 1)]`` | 量得出且 1 枚 |
| S7 摘瞎行与量过行混合 | ``[]`` | ``[]`` | 量得出，🔴 另起一行点名没参与的那几行（:163-167） |
| S8 ``sha`` 为 ``""``／``None`` | ``[]`` | ``None`` | 🔴 假零 → 未量 |
| S9 空账（零行） | ``None`` | ``None`` | 派生不出 |
| S10 ``frames`` 不是列表 | ``AttributeError`` | ``AttributeError`` | 不当读数（本单不治，见 §8 第 3 条） |

### 3.3 在册四份真账（只读，一个字节未写）

| 账 | 行数 | 有帧行 | 现成逐帧指纹枚数 | 改前 | 改后 |
|---|---|---|---|---|---|
| ``sidecar-run6-frames.jsonl`` | 105 | 0 | 0 | ``None`` | ``None`` |
| ``sidecar-run7-frames.jsonl`` | 105 | 0 | 0 | ``None`` | ``None`` |
| ``sidecar-run8p2-frames.jsonl`` | 20 | 0 | 0 | ``None`` | ``None`` |
| ``sidecar-run9-frames.jsonl`` | 105 | 103 | 2533 | ``[('insight-07',1),('chart-04',1),('tool-04',1)]`` | 同一枚，逐字不漂 |

⇒ 在册真账里今天没有一枚「帧在而无指纹」的行（``unmeasured_rows(run9) == []``），所以本单**不漂一枚当年
读数**；被治的那一形在四份账上一枚都不存在，这既是好消息也是本单的风险面：它只在量具被摘瞎的那一扇窗
才会露头，因此必须靠合成账钉住（§7 刀一）。

## 4. 两形分开后的语义（写死，不许并脸）

| 输入那一形 | 改前 | 改后 | 读法 |
|---|---|---|---|
| 帧在、一枚 ``sha`` 都没参与（整份账） | 一张全零表 | ``None`` | 这一格今天**没量过** |
| 帧在、指纹在位、确实没跨流重合 | ``[]``（0 枚） | ``[]``（0 枚） | 量过了，本轮没有第二份正文 |
| 跨流重发 | ``[(题, n)]`` | ``[(题, n)]`` | 不许被本单顺手摘聋 |
| 同一条流内末片帧与收尾帧同文 | ``[]`` | ``[]`` | 总控裁定：不算出现两遍 |
| ``frames`` 整列缺席／枚枚空表 | ``None`` | ``None`` | 在册形一字未改 |
| 行内枚数为零（``[]``） | ``0`` | ``0`` | 🔴 本单不动（§6 第 2 条） |

## 5. 改动清单（终态坐标，现取）

只动一枚件：``scripts/eval_frame_caliber_readout.py``，``git diff --numstat`` = ``46 10``（+46/−10）。

- ``:61 _repeats_of_records``：签名 ``-> int`` → ``-> int | None``；:75-77 新增那一支，条件与
  ``_cross_stream_repeats:717-719`` 逐字同形（``records and not any(str(record.get("sha") or "") ...)``）；
  循环体 :78-88 一个字未改（三条边界原样）。
- ``:93 account_fingerprints``／``:99 unmeasured_rows``：两枚新 helper，🔴 只数行内现成读数，一枚不另数。
- ``:105 derived_repeats``（原 :82）：:116-117 那道在册闸（整列缺席／枚枚空表）一字未改；:118-121 新增
  「整份账无一枚指纹 ⇒ ``None``」；:122-123 重合名单改按逐行派生值过滤（``None`` 与 0 都不入名单，病形照旧入）。
- ``:153-167 caliber_block`` 纸面层：派生不出那一行的话补上「或量具被摘瞎那一形」（:157-158）；量得出那一支
  多一行「🔴 行内未量 … 题号=…」（:163-167），🔴 **只在真有摘瞎行时印** ⇒ 干净真账的纸面一字不增。
- 新增钉：``tests/test_r515_frame_caliber_blind_instrument_returns_none.py``（293 行，31 枚，含逐形
  parametrize 表、与尺子的同脸对判、纸面层 capsys 三枚、不重判一枚）。
- 在册件只读未改：``tests/test_r471_second_copy_of_the_answer_body_is_not_a_pass.py``（本单一个字未动，
  它 :16 那句「离线复算那一路同样现场派生」今天才真正落到本件头上）。

## 6. 边界（三条，都是故意的）

1. 🔴 **不重判 ``criterion_two_holds``**：派生那两只手不改行（钉 ``test_c5_...``：``deepcopy`` 前后对判），
   纸面 holds 钉死 ``91/105``（全量）与 ``80/93``（剔报告档）；``RAW_CELLS``（:35）一枚不增（丙案：那格不落账）。
   口径见 ``docs/testing/r471-verdict-caliber-2026-09-29.md``。
2. 🔴 **空读那一形不越界**：行内 ``[]``／非帧表入参照在册现状回 ``0``，与 ``_cross_stream_repeats`` 同脸；
   那一形钉在 ``tests/test_r471_second_copy_of_the_answer_body_is_not_a_pass.py:449``，不在本单写域。
   （副产物：``None`` 入参从 ``TypeError`` 变成同脸的 ``0``，与 R507 的 ``test_a7`` 同一读法。）
3. **既有断言一枚未改弱**：``rg -l "eval_frame_caliber_readout" tests/`` 现取名册只有 R471 那枚件，本单
   未改它；两形分家只往「多交 ``None``」方向走，未放宽任何一格。

## 7. 反证刀（四把，跑完逐字节还原）

| 刀 | 怎么改坏 | 当场红的钉 | 读数 |
|---|---|---|---|
| 刀一（判据点名）摘掉逐帧指纹 | 拿 run9 真账把 2533 枚 ``sha`` 全清（合成账） | 改前纸面 ``枚数=0 题号=无``；改后纸面 ``派生不出``，且 holds 仍 ``91/105``／``80/93`` | 🔴 假零翻成未量，钉 ``test_c1`` 咬住 |
| 刀二·甲（判据点名）把 ``None`` 强改成 0（行内） | 删 ``_repeats_of_records:75-77`` 那一支 | ``test_a1``/``a2``/``a4``/``a8[blind]``/``a8[blank_sha]``/``b2``/``c3``/``d1`` | 8 failed / 23 passed |
| 刀二·乙（同上，账级） | ``if not account_fingerprints(rows):`` → ``if False:`` | ``test_b1[S3_blind_with_text]``/``b1[S3b...]``/``b1[S8_blank_sha]``/``c1`` | 4 failed / 27 passed |
| 刀三 倒打一耙（干净形也回 ``None``） | ``if records and not any(...)`` → ``if records:`` | ``a3``/``a4``/``a5``/``a6``/``a8[witnessed_clean]``/``a8[resend]``/``a8[same_leg]``/``b1[S6...]``/``b2``/``b3``/``c4`` | 11 failed / 20 passed |
| 刀四 抹掉混合账的点名行 | ``blind = unmeasured_rows(rows)`` → ``blind = []`` | ``test_c3`` | 1 failed / 30 passed |

- 还原凭据：终态 ``scripts/eval_frame_caliber_readout.py`` = 13478 字节、sha256[:16] ``de3b786c41be5a97``、
  四把刀跑完 ``restored byte-for-byte: True``（逐次比对同一枚 sha256）。
- 🔴 强度只升不降：四把刀各咬一格，没有一把靠删断言制造红绿；两形（摘瞎／干净）在纸面与函数两层各有一枚钉。

## 8. 没做到的事（照实列）

1. 没跑真机窗、没打模型、没起服务、没动容器、没连库、没 ``commit``/``git add``/push；主树一行未写；
   除 §5 那三枚路径（读数件＋本单新钉＋本读数件）外一枚未碰，``docs/api/contract-v1.md`` 归 R517。
2. **空读形 ``[]`` 未倒向 ``None``**：见 §6 第 2 条。残余分歧照旧在册 —— ``[]`` 在本尺（``_cross_stream_repeats``）
   回 ``0``、在判器（``r239_stream_gap_offline_audit.py:153``）回 ``None``；要并口径须总控同笔改 ``:449`` 那枚钉。
3. **``frames`` 键在但不是列表**（例如一串字）改前改后同样 ``AttributeError``：那一形不冒充读数（它是硬失败，
   不是假绿），且 R507 并树后的尺子对 ``str`` 入参同一形，本单不自创第二套去治它。要一并治请总控放行同笔。
4. **两枚在册纸的坐标随本单漂**（不在本单写域，请总控按尺子自己给的出路重同步）：
   ``docs/testing/r471-verdict-caliber-2026-09-29.md:96`` 与 ``docs/testing/r507-blind-instrument-returns-none.md:49``
   引的 ``derived_repeats`` 坐标 ``:82`` → 现 ``:105``；``r471-verdict-caliber:96`` 那句「``:126/:129`` 明写派生不出」
   → 现 ``:157/:160``；``r507-blind-instrument-returns-none.md:127`` 那句「:61/:82 那半把未治」今天起应改写成
   「行内 ``:61`` 与账级 ``:105`` 均已治」。``_repeats_of_records:61`` 一枚未漂。
5. ``scripts/eval_cloud_window_readout.py:78/:83`` 只在纸上点了本件的名字（未调 ``derived_repeats``），本单没动它。
6. 没跑真机新窗，也没替 run10 出任何数（读数只落本文与钉，不改任何在册账）。

## 9. 自验（执行层自报，命令原文照抄）

- 环境：``cd C:\Users\fengx\PycharmProjects\be-r515`` ＋ 主树解释器
  ``C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe``（裸 ``python`` 无 chromadb，会 ImportError）。
- 本单新钉：``...python.exe -m pytest tests/test_r515_frame_caliber_blind_instrument_returns_none.py -q``
  → **31 passed**（0 skipped／0 failed，0.61 s）。
- 读物者点名件（28 枚：``rg -l "eval_frame_caliber_readout|eval_transport_ask_v2|cross_stream" tests/`` 现取名册，
  含 R471/R507/R506/R239 读者与 R181/R215/R218/R223/R259/R361/R447/R453/R456/R459/R464/R48/R496/R123/R203/R210/R222）：
  ``...python.exe -m pytest <28 枚逐枚点名> -q -p no:cacheprovider --tb=line`` → **465 passed / 4 skipped / 0 failed**（72.36 s）。
  两笔都在 dirty 态（已改未 commit，本单不许 commit）跑；文件清单以上面那条 ``rg -l`` 现取名册为准（含 ``tests/_r259_queue_ruler.py`` 这枚读者件，无 ``test_*`` 前缀但同册）。
- 终态复跑（读数件落盘之后再跑一遍同一组 28 枚，同名同参）：**465 passed / 4 skipped / 0 failed**；本单新钉单跑 **31 passed**（两笔之间只多了一份 ``.md``，一个字节未动代码）。
- 全量回归门（``-n 3`` 自控并发，本机同时还有三枚兄弟 Agent 在写主树，不抢 ``-n 6`` 的 12 GB）：
  ``...python.exe scripts/run_gate.py -n 3`` → ``[run_gate] xdist -n 3 --dist loadfile`` ＝
  **5 failed / 9181 passed / 53 skipped / 2 xfailed，exit=1**（664.8 s；并发改成 ``-n 3`` 而不是自选的
  ``-n 6``，是因为本机此刻还有三枚兄弟 Agent 在施工，12 GB 那一档把主机打死过一次）。
  🔴 五枚红**一枚都不归本单**，逐枚点名（凭据现取，不是话术）：
  * ``tests/test_r256_dataset_version_scope.py::test_the_bytes_on_disk_the_manifest_and_the_loader_are_one_document``
    —— 断言原文 ``assert raw.count(b"\r") == 0``，对象是 ``migrations/0015_dataset_version_scope_columns.sql``；
    ``git ls-files --eol`` 现取读数 ``i/lf w/crlf`` ⇒ 这是**工作树 checkout 的 EOL 形状**（``core.autocrlf=true``），
    在任意一棵新树于此基点同红，与本单的帧账读数件无一根毛。
  * ``tests/test_r469_readout_is_generated.py`` 两枚（``test_the_in_tree_readout_is_byte_for_byte_what_the_lib_emits``
    ／``test_the_cli_is_the_only_way_that_produced_this_table``）——同一族：拿 ``read_bytes()`` 与渲染件对
    ``docs/testing/r469-sandbox-scope-readout-2026-09-28.md`` 逐字节判，那枚件不在本单写域。
  * ``tests/test_r508_the_bind_stub_stays_on_the_class.py::test_the_registry_class_and_singletons_are_what_the_audit_measures``
    与 ``tests/test_response_hygiene.py::test_dataset_file_and_preview_are_not_cacheable``——并行序污：这四枚红件
    单独合跑（无 xdist，``-p no:cacheprovider``）＝ **3 failed / 48 passed**，上面这两枚**独跑即绿**，
    红只在 ``-n 3`` 那一带出现（``assert registry is session_storage.session_registry`` 的共享单例被前序用例换掉）。
  * 归零凭据：``rg -l "eval_frame_caliber_readout" tests/`` 在册名册只有 R471 那枚件；上面五枚红件一枚都不在本单
    改动的依赖链上（本件只被 ``scripts/eval_cloud_window_readout.py:78/:83`` 在纸上点过名，且不调这两只手）。
  * 🔴 本席不替总控判定「这五枚该谁治」：前三枚是**树级 EOL 形状**、后两枚是**并行序污**，都不是本单的牙松了。
