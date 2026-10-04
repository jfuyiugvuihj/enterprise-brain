# R638｜纸面坐标的尺、棘轮钉与批量转换的派工切法（取证纸）

- 工单：R638 ／ 树 ``be-r638`` ／ 基点 ``473235f``（分支 ``codex/be-r638``）／ 执行层：本席
- 定位：**先止血、再出工单**——只交尺与清单，**正文一枚 .md 都没改**；本纸坐标形状＝0 枚（钉死在册）
- 返工单 **R638-R**（总控 §173.2 退回）：身份去行位＋第三态。三条病因与处置见本纸 §2A，五态亲跑见 §3。
- 交付：``scripts/r638_doc_pointer_ruler.py``（尺）／``tests/test_r638_pointer_ratchet.py``（棘轮钉，
  14 枚用例）／``tests/test_r638_counter_evidence_teeth.py``（反证刀，15 枚用例）／
  ``docs/testing/r638-pointer-baseline.json``（派生基线）／本纸（含批量切法）；
  整册 4,102 枚读数 **不进仓**（R638-R⑤），落点与 sha256 见 §5
- 本纸每一格都出自我亲跑的读数：命令原文逐条附在对应格里。用例枚数、棘轮四格对账、收席五枚
  由生成器在落笔那一刻现取，现取与在册读数不等即抛——不落一张对不上盘的纸。

## 0．判据①｜形状同值：命令原文 → 读数

```text
rg -o -N --glob "docs/**/*.md" "[A-Za-z0-9_./-]+\.py:[0-9]+(-[0-9]+)?" | Measure-Object -Line
rg --files-with-matches -N --glob "docs/**/*.md" 同一形状 | Measure-Object -Line
.\.venv\Scripts\python.exe scripts\r638_doc_pointer_ruler.py            # 尺的派生读数
```

| 读数 | 总控那把宽尺 | 本件的尺 |
| --- | --- | --- |
| 总枚数 | 4,102 | ``total_pointers`` = 4,102 |
| 涉 .md | 123 | ``md_files_with_pointers`` = 123 |
| docs 下 .md 全集 | —— | ``md_files_scanned`` = 178（其余 55 枚零坐标） |
| 行区间那一形 | —— | ``range_pointers`` = 977 |

两把尺**逐字符同形**：``TICKET_SHAPE`` 就是派工词那枚正则原文；钉
``test_the_ruler_counts_what_the_ticket_regex_counts`` 拿它独立再数一遍 docs 全集，与尺的读数比同值。

**差在哪（点名，不含糊）**：执行层 Ptolemy 交回的 110 枚／22 枚 .md 是**窄口径**——只数
``eval_transport_ask_v2.py`` 那一枚把手的行号引用；本席按「任意 ``.py:`` 后接行号（含区间、含裸基名）」
在 ``docs/**/*.md`` 全量取。形状不同、射程不同：110 与 4,102 都是真话，不可互相顶账。

**行号口径**（复现的前提）：枚数与行号一律按 ``\n`` 切行、剥行尾 ``\r``。现取凭据：册内 ``lone_cr`` 最大的一枚是
**docs/handoff/2026-09-15-backend-followup-requests.md**：1,534 枚孤立 ``\r``（``len(re.findall(r"\r(?!\n)", text))``）。若改用 Python 通用换行读，那一枚文件的
「行」会被孤立回车劈开，``所在md:行`` 与 ``rg -n`` 报的号整体错位——抽查就成了假凭据。基线里的正文
digest 只归一 ``\r\n``→``\n``（孤立 ``\r`` 属内容），所以两态（CRLF 脏树／干净检出）读数逐枚相等。

## 1．判据②｜三件判定与现取读数

```text
.\.venv\Scripts\python.exe scripts\r638_doc_pointer_ruler.py --stale
.\.venv\Scripts\python.exe scripts\r638_doc_pointer_ruler.py --stale --limit 10
```

**①被引文件在不在**——三级解析（全路径 → 仓内后缀 → 基名）。档位从册内逐枚 ``resolution`` 现数：
可解析 3,994 枚（exact 2,910／suffix 13／unique 1,071）、
基名歧义 78 枚（``service.py``／``contracts.py``／``artifacts.py`` 那一族，候选逐枚交回、**不猜**）、
依赖引用 8 枚（``chromadb``／``pypdf`` 那一族，不算本仓行号账）、
查无此文件 18 枚、路径已搬走 4 枚——五档相加＝4,102。

**②该行现读与句子声称对不对得上**——走 AST，零 import。分档（11 档相加＝4,102）：

| 档位 | 枚数 |
| --- | --- |
| ``unverified_no_claim`` | 2373 |
| ``symbol_mismatch`` | 739 |
| ``comment_target_line`` | 341 |
| ``claim_matches`` | 305 |
| ``empty_target_line`` | 202 |
| ``ambiguous_path`` | 78 |
| ``unverified_multi_pointer`` | 25 |
| ``file_missing`` | 18 |
| ``line_out_of_range`` | 9 |
| ``external_dependency`` | 8 |
| ``file_moved`` | 4 |

**「今天已对不上」= 972 枚**：``symbol_mismatch`` 739／
``empty_target_line`` 202／``file_missing`` 18／
``line_out_of_range`` 9／``file_moved`` 4。
逐枚六栏凭据（前 10 枚，坐标形状在本纸一律改写成「``文件.py`` 行 N」）：

| 所在 md:行 | 被引坐标 | 现读文件 | 现读所属符号(种类) |
| --- | --- | --- | --- |
| docs/api/contract-v1.md:422 | pending_approvals.py 行 102 | ``app/storage/pending_approvals.py`` | ``_conn``(def) |
| docs/api/contract-v1.md:1568 | app/agents/contracts.py 行 69 | ``app/agents/contracts.py`` | ``<module>``(None) |
| docs/api/contract-v1.md:2452 | app/storage/datasets.py 行 121 | ``app/storage/datasets.py`` | ``DatasetRecord``(class) |
| docs/api/contract-v1.md:2461 | app/documents/catalog.py 行 236 | ``app/documents/catalog.py`` | ``public_document_row``(def) |
| docs/api/contract-v1.md:2757 | app/tools/excel.py 行 88 | ``app/tools/excel.py`` | ``<module>``(None) |
| docs/api/contract-v1.md:2877 | app/tools/excel.py 行 87-88 | ``app/tools/excel.py`` | ``<module>``(None) |
| docs/api/contract-v1.md:3116 | app/knowledge_graph/service.py 行 480-520 | ``app/knowledge_graph/service.py`` | ``KnowledgeGraph.record_verification``(def) |
| docs/api/contract-v1.md:3507 | app/common/auth.py 行 581-583 | ``app/common/auth.py`` | ``list_users``(def) |
| docs/api/contract-v1.md:3843 | app/common/auth.py 行 231 | ``app/common/auth.py`` | ``_retry_readiness_probe``(def) |
| docs/api/contract-v1.md:3922 | app/notifications/inbox.py 行 161 | ``app/notifications/inbox.py`` | ``build_inbox``(async def) |

判红最集中的被引文件（前 12 枚；「已对不上」＝该文件在册引用里判红的枚数）：

| 被引文件 | 引用枚数 | 已对不上 |
| --- | --- | --- |
| ``app/api/v1/chat.py`` | 571 | 164 |
| ``app/agents/nodes.py`` | 186 | 48 |
| ``app/agents/orchestrator.py`` | 171 | 44 |
| ``app/rag/retriever.py`` | 153 | 59 |
| ``scripts/eval_transport_ask_v2.py`` | 112 | 40 |
| ``app/api/v1/alerts.py`` | 105 | 25 |
| ``app/rag/retrieval_pipeline.py`` | 105 | 28 |
| ``app/common/model_budget.py`` | 97 | 51 |
| ``app/common/model_handler.py`` | 90 | 29 |
| ``app/agents/tools.py`` | 86 | 21 |
| ``app/rag/indexing.py`` | 83 | 21 |
| ``app/agents/contracts.py`` | 65 | 34 |

大头所在（按 .md 分组前 8 枚）：

| 所在 md | 枚数 | 已对不上 |
| --- | --- | --- |
| ``docs/handoff/2026-09-15-backend-followup-requests.md`` | 679 | 191 |
| ``docs/handoff/2026-09-15-orchestration-board.md`` | 671 | 164 |
| ``docs/api/contract-v1.md`` | 215 | 33 |
| ``docs/handoff/2026-09-25-plan-ticket-closure.md`` | 161 | 28 |
| ``docs/testing/r508-instance-shadow-debt-2026-09-29.md`` | 127 | 31 |
| ``docs/handoff/2026-09-30-plan-eight-tickets-recheck.md`` | 114 | 29 |
| ``docs/handoff/2026-09-20-unblock-map.md`` | 112 | 33 |
| ``docs/handoff/2026-09-15-alert-and-hitl-design.md`` | 95 | 34 |

**不裁漂移的档同样如实占格**（信息不足就是不足，不冒充凭据、也不凑红）：``unverified_no_claim``
2373 枚（句子里挑不出可在该文件核对的符号名，尺只量到「行在界内」——
**这不等于对得上**）、``comment_target_line`` 341 枚（该行现读是注释，
可能在指注释里写着的那件事）、``ambiguous_path`` 78 枚、
``unverified_multi_pointer`` 25 枚（同一枚 md 行里数枚坐标指向
同一文件，声称归谁说不清）、``external_dependency`` 8 枚。
``claim_matches`` 305 枚是「尺不是死尺」的正面读数。

**刻意留的假阳性面（明写，不装没有）**：``shape_talk`` 259 枚——纸上那一行正在讲
「坐标形状」本身（反例展示、口径说明），尺照判但带旗标；``hard_on_forensic_lines``
180 枚落在取证原文行上。**总控要拿 972 枚当工单量，先剔这两族。**

**③能否安全换成** ``文件::符号``：可按行机械换 2,611 枚；不可直接换 519 枚
（该行现读属模块级无名语句／基名歧义／区间跨符号）；判红的 972 枚**一律不给机械锚**——
先把假坐标定夺，别把它洗成看着体面的假锚点。锚点交回前已过与在册
``tests/test_r630_first_token_pointer_is_derived.py::anchor_resolves`` 同形的那棵 AST 腿。

## 2．判据③④｜棘轮钉与 12 把刀

```text
.\.venv\Scripts\python.exe scripts\r638_doc_pointer_ruler.py --write-baseline docs\testing\r638-pointer-baseline.json
.\.venv\Scripts\python.exe scripts\r638_doc_pointer_ruler.py --check-baseline docs\testing\r638-pointer-baseline.json
```

- 基线件：123 枚 .md／4,102 枚身份串，口径 ``IDENTITY_SCHEME``＝``doc::整行文本哈希::被引坐标串``（``validate_baseline`` 拒收行位口径的旧基线），每枚 .md 另带正文 digest。
  **没有一处手抄数字**——``count`` 恒等于 ``len(pointers)``，总枚数由求和派生。
- 五格读数（🔴 红只由 ``grew``＋``forged`` 决定）：``grew`` 变多＝红并逐枚点名新身份／
  ``shrank`` 变少＝不红而逐枚点名少了谁／``shifted`` 枚数不变而身份变了（账面 splice 改了句子）＝不红而点名／
  ``new_docs`` 新落的 .md 带着坐标＝不红而点名（别的单的正文不由本单定罪）／
  ``forged`` digest 未动而清单与现读不等，或 ``count`` 与清单长度不等＝红。
  落笔那一刻现取对账：``grew`` 0／``shrank`` 0／``shifted`` 0／
  ``new_docs`` 0／``forged`` 0（``offenders`` 空＝exit=0，生成器当场断言）。
- 更新基线只有一条路：上面那枚 ``--write-baseline`` 显式写口（除此之外本件不落任何盘）。
- 🔴 **运营后果（故意做重）**：往后往跟进单或看板**文末追加**一句带行号坐标的新账，下一次全量门就红。
  要么按 ``文件::符号`` 写（先例 R630／R635），要么由总控授权重取基线并在账上点名。
- 🔴 钉不许把「此刻盘面脏不脏」当判据：全程只读盘上文本与尺的读数，零 ``git`` 调用、不比 dirty。
- 反证刀 15 枚用例（12 把刀各配正控，另带自证）：影子根＝``tmp_path/shadow/docs``，正文从主树逐字节复制，
  **基线取在动手之前**，刀只改影子；末一枚复核主树 digest 动手前后逐枚相等。刀三／刀四专治
  「把基线改成手抄字面量」：改 ``count`` 被自证抓，删身份串并改自洽被 digest 现读对出。

## 2A．返工 R638-R｜身份去行位（今天真正补上的一格）

**三条病因 → 处置**（都由总控 §173.2 现取，本席逐条复现）：

| 病因 | 旧口径怎么错 | 现在这枚怎么改 |
| --- | --- | --- |
| ① 身份串含 md 行号与列号 | 账面一次 splice 就移动全部行位：``473235f``→``7fd8d4a`` 看板只净增 25 行、四枚在册坐标出现次数逐枚不变，却被报成 431 枚"新增" | 身份改成 ``doc::整行文本哈希::被引坐标串``（``IDENTITY_SCHEME``），**与行位无关**；带行位那串只留给 ``--stale`` 抽查清单 |
| ② 分类自相矛盾 | 看板 ``before=671``／``after=670``（枚数下降）仍进 ``grew``，``shrank`` 恒空 | 方向只由**同一枚 doc 的身份多重集**定：变多进 ``grew``／变少进 ``shrank`` 并逐枚点名／枚数不变而身份变了进 ``shifted``；``ratchet_diff`` 末段带一格算术自证 |
| ③ 把别人的旧账算成违例 | ``new_docs`` 里那两枚是别单并进来的取证纸，被本单定罪 | ``new_docs`` 降级为只点名不定罪；本单自己那枚纸零坐标另有专牙 |

**身份样本**（尺现取，本纸把坐标形状改写为「``文件.py`` 行 N」）：``docs/api/contract-v1.md::d048b80fd3ba98a6::app/main.py 行 104``。
整行文本哈希走 ``scripts/r638_doc_pointer_ruler.py::line_digest``：折叠行内空白——表格行补一格竖线、
多一个缩进都不算长出一枚坐标，跟进单那 1,534 枚孤立 ``\r`` 也随之归一。

**五态 ``--check-baseline`` 逐格读数**（命令原文见 §3 那一格；exit=0＝棘轮不咬）：

| 态 | HEAD | 总枚数 | 涉 .md | grew | shrank | shifted | new_docs | forged | 对账 exit | 本态重生成自对 exit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| state① | ``473235f75122899c2c509bd39571ee5e3c6492fa`` | 4,102 | 123 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| state② | ``473235f75122899c2c509bd39571ee5e3c6492fa`` | 4,102 | 123 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| state③ | ``473235f75122899c2c509bd39571ee5e3c6492fa`` | 4,102 | 123 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| state④ | ``7fd8d4ab727b0d0d10440021361d3ca603e6c10f`` | 4,150 | 125 | 0 | 1 | 0 | 2 | 0 | 0 | 0 |
| state⑤ | ``88ba01e7f11b3035f6d21fc62df080fc68a3fa06`` | 4,150 | 125 | 0 | 1 | 0 | 2 | 0 | 0 | 0 |

🔴 **R638-R③ 的现取**：同一把尺在每一态的 HEAD 上各自 ``--write-baseline`` 重生成一份，再拿那份自对自跑
``--check-baseline`` → exit 全 0（最末一列）；棘轮「只准降不许升」靠**身份集合**成立，不靠快照行位。
生成器当场断言五态重生成那份的六格全为零，不等即抛、不落纸。

看板那枚 .md 在各态的在册枚数：state①＝671／state②＝671／state③＝671／state④＝670／state⑤＝670。

| 态 | 点名（现取） |
| --- | --- |
| state① | 六格皆空（无点名） |
| state② | 六格皆空（无点名） |
| state③ | 六格皆空（无点名） |
| state④ | ``shrank`` docs/handoff/2026-09-15-orchestration-board.md 671→670；``new_docs``（只点名） docs/testing/r545-queue-failure-probe-2026-10-04.md 48 枚／docs/testing/r636-stage-coverage-2026-10-04.md 1 枚 |
| state⑤ | ``shrank`` docs/handoff/2026-09-15-orchestration-board.md 671→670；``new_docs``（只点名） docs/testing/r545-queue-failure-probe-2026-10-04.md 48 枚／docs/testing/r636-stage-coverage-2026-10-04.md 1 枚 |

## 3．判据⑤＋R638-R④｜五态亲跑（同名件逐枚点名）

| 同名件 | collected state① | collected state② | collected state③ | collected state④ | collected state⑤ |
| --- | --- | --- | --- | --- | --- |
| ``tests/test_r638_pointer_ratchet.py`` | 14 | 14 | 14 | 14 | 14 |
| ``tests/test_r638_counter_evidence_teeth.py`` | 15 | 15 | 15 | 15 | 15 |
| ``tests/test_r253_no_test_rewrites_a_tracked_file.py`` | 9 | 9 | 9 | 9 | 9 |
| ``tests/test_r302_docs_utf8_guard.py`` | 8 | 8 | 8 | 8 | 8 |
| ``tests/test_r630_first_token_pointer_is_derived.py`` | 9 | 9 | 9 | 9 | 9 |
| ``tests/test_r630_counter_evidence_teeth.py`` | 13 | 13 | 13 | 13 | 13 |
| ``tests/test_r635_surface_pointers_are_derived.py`` | 12 | 12 | 12 | 12 | 12 |
| ``tests/test_r635_counter_evidence_teeth.py`` | 13 | 13 | 13 | 13 | 13 |
| **合计（逐枚相加）** | **93** | **93** | **93** | **93** | **93** |

```text
# state① cwd = C:\Users\fengx\PycharmProjects\be-r638
"C:\Users\fengx\PycharmProjects\be-r638\.venv\Scripts\python.exe" -m pytest tests/test_r638_pointer_ratchet.py tests/test_r638_counter_evidence_teeth.py tests/test_r253_no_test_rewrites_a_tracked_file.py tests/test_r302_docs_utf8_guard.py tests/test_r630_first_token_pointer_is_derived.py tests/test_r630_counter_evidence_teeth.py tests/test_r635_surface_pointers_are_derived.py tests/test_r635_counter_evidence_teeth.py -q -p no:cacheprovider
# state② cwd = C:\Users\fengx\AppData\Local\Temp\r638_r_state2
"C:\Users\fengx\PycharmProjects\be-r638\.venv\Scripts\python.exe" -m pytest tests/test_r638_pointer_ratchet.py tests/test_r638_counter_evidence_teeth.py tests/test_r253_no_test_rewrites_a_tracked_file.py tests/test_r302_docs_utf8_guard.py tests/test_r630_first_token_pointer_is_derived.py tests/test_r630_counter_evidence_teeth.py tests/test_r635_surface_pointers_are_derived.py tests/test_r635_counter_evidence_teeth.py -q -p no:cacheprovider
# state③ cwd = C:\Users\fengx\AppData\Local\Temp\r638_r_state3_spliced
"C:\Users\fengx\PycharmProjects\be-r638\.venv\Scripts\python.exe" -m pytest tests/test_r638_pointer_ratchet.py tests/test_r638_counter_evidence_teeth.py tests/test_r253_no_test_rewrites_a_tracked_file.py tests/test_r302_docs_utf8_guard.py tests/test_r630_first_token_pointer_is_derived.py tests/test_r630_counter_evidence_teeth.py tests/test_r635_surface_pointers_are_derived.py tests/test_r635_counter_evidence_teeth.py -q -p no:cacheprovider
# state④ cwd = C:\Users\fengx\AppData\Local\Temp\r638_r_state4_7fd8d4a
"C:\Users\fengx\PycharmProjects\be-r638\.venv\Scripts\python.exe" -m pytest tests/test_r638_pointer_ratchet.py tests/test_r638_counter_evidence_teeth.py tests/test_r253_no_test_rewrites_a_tracked_file.py tests/test_r302_docs_utf8_guard.py tests/test_r630_first_token_pointer_is_derived.py tests/test_r630_counter_evidence_teeth.py tests/test_r635_surface_pointers_are_derived.py tests/test_r635_counter_evidence_teeth.py -q -p no:cacheprovider
# state⑤ cwd = C:\Users\fengx\AppData\Local\Temp\r638_r_state5_88ba01e
"C:\Users\fengx\PycharmProjects\be-r638\.venv\Scripts\python.exe" -m pytest tests/test_r638_pointer_ratchet.py tests/test_r638_counter_evidence_teeth.py tests/test_r253_no_test_rewrites_a_tracked_file.py tests/test_r302_docs_utf8_guard.py tests/test_r630_first_token_pointer_is_derived.py tests/test_r630_counter_evidence_teeth.py tests/test_r635_surface_pointers_are_derived.py tests/test_r635_counter_evidence_teeth.py -q -p no:cacheprovider
```

| 态 | 姿势 | 读数 |
| --- | --- | --- |
| state① | 本树脏态：tracked 零改动＋本单 5 枚货 untracked（1661 枚 tracked 在位）｜cwd ``C:\Users\fengx\PycharmProjects\be-r638``（HEAD ``473235f``） | **93 passed / 0 failed / 0 skipped / exit=0** |
| state② | ``473235f`` 干净检出（同 1661 枚 tracked）＋只投本单货｜cwd ``C:\Users\fengx\AppData\Local\Temp\r638_r_state2``（HEAD ``473235f``） | **93 passed / 0 failed / 0 skipped / exit=0** |
| state③ | ``473235f`` 干净检出＋本单货＋在 docs/handoff/2026-09-15-orchestration-board.md 最上方插了一行（沿用该文件原有行尾，不掺孤立回车）：枚数不变、身份不变才算这一态过｜cwd ``C:\Users\fengx\AppData\Local\Temp\r638_r_state3_spliced``（HEAD ``473235f``） | **93 passed / 0 failed / 0 skipped / exit=0** |
| state④ | 总控亲跑那枚 HEAD（账面比基点多几行）＋只投本单货＝今天红的那盘面｜cwd ``C:\Users\fengx\AppData\Local\Temp\r638_r_state4_7fd8d4a``（HEAD ``7fd8d4a``） | **93 passed / 0 failed / 0 skipped / exit=0** |
| state⑤ | 主树最新那枚 HEAD（账面又往前推了几笔）＋只投本单货＝收货时真正会碰到的那盘面｜cwd ``C:\Users\fengx\AppData\Local\Temp\r638_r_state5_88ba01e``（HEAD ``88ba01e``） | **93 passed / 0 failed / 0 skipped / exit=0** |

五态**用例枚数相同**：collected 逐枚相等，合计 93。尺的**读数**在 state①②③ 逐枚相等（同一批 docs、同一把尺）：total 4,102／docs 123／hard 972／scanned 178／可锚 2,611／
不可直接换 519／依赖 8——11 枚判定档全等；state④⑤ 的差**只来自账面那几枚新落文档**，逐格见下表。告警 13／13／13／13／13 枚是在册旧噪声
（``scripts/window_keep_awake.py`` 第 5 行那一枚 ``\k`` 转义等），与本单无关、未弄红也未去修。

**五态读数逐枚相等（尺现取，不是用例数）**：state②③ 与 state① 的 11 枚指标读数逐枚相等（生成器当场断言，不等即抛）。state④ 相对 state① 之差（现取）：total_pointers 4102→4150／md_files_scanned 178→180／md_files_with_pointers 123→125／hard_total 972→978／anchor_safe 2611→2650／anchor_unverifiable 519→522／hard_shape_talk 259→260／判红档 empty_target_line 202→204／判红档 file_missing 18→16／判红档 symbol_mismatch 739→745／判定档 ambiguous_path 78→79／判定档 claim_matches 305→320／判定档 empty_target_line 202→204／判定档 file_missing 18→16／判定档 symbol_mismatch 739→745／判定档 unverified_no_claim 2373→2399；state⑤（账面又往前推了几笔）之差：total_pointers 4102→4150／md_files_scanned 178→183／md_files_with_pointers 123→125／hard_total 972→987／anchor_safe 2611→2640／anchor_unverifiable 519→523／hard_shape_talk 259→264／判红档 empty_target_line 202→209／判红档 file_missing 18→16／判红档 symbol_mismatch 739→749／判定档 ambiguous_path 78→79／判定档 claim_matches 305→316／判定档 comment_target_line 341→343／判定档 empty_target_line 202→209／判定档 file_missing 18→16／判定档 symbol_mismatch 739→749／判定档 unverified_no_claim 2373→2392。两态的差全部来自账面新落的文档，棘轮对它们报的都是 ``grew`` 0 枚——不是把旧账算成违例。

| 态 | HEAD | total | 涉 .md | hard | 可锚 | 依赖档 | 缺文件档 | 本树有 .venv |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| state① | ``473235f`` | 4,102 | 123 | 972 | 2,611 | 8 | 18 | **有** |
| state② | ``473235f`` | 4,102 | 123 | 972 | 2,611 | 8 | 18 | **无** |
| state③ | ``473235f`` | 4,102 | 123 | 972 | 2,611 | 8 | 18 | **无** |
| state④ | ``7fd8d4a`` | 4,150 | 125 | 978 | 2,650 | 8 | 16 | **无** |
| state⑤ | ``88ba01e`` | 4,150 | 125 | 987 | 2,640 | 8 | 16 | **无** |

state②③④⑤ 那四棵影子树的造法（总控可原样复现）：``git -C be-r638 worktree add --detach <临时目录> <基点>``
（state④⑤ 的基点换成总控亲跑的那两枚 HEAD：④＝今天退本单那枚，⑤＝收席时主树最新那枚），再把本单那 5 枚货逐枚复制进去（复制后逐枚比对字节相等），
解释器仍用主树 venv；state③ 再往看板最上方插一行（沿用该文件原有行尾，不掺孤立 ``\r``）；
交回前用 ``git -C be-r638 worktree remove --force <临时目录>`` 收掉，本树与主树都不留痕。
今天这枚病正是被 state①②**同一快照**漏掉的——插行那一态量不到行位漂移，所以判据④点名要第三态。

本单踩过并当场改掉的一格：第一版把「依赖档」绑在 ``repo/.venv`` 存在上，而 ``.venv`` 不被跟踪——
干净检出的树里没有它，于是同一份 docs 在脏树读成 8 枚 ``external_dependency``、在干净检出读成 8 枚 ``file_missing``，**两态差 8 枚**（旧版那笔账；今天这 8 枚现读全在 
``external_dependency`` 档）。这就是〔把此刻盘面当判据〕的同族病（事故 #96／#107 那一族）。
改绑现跑解释器的 ``site-packages``（``sysconfig.get_paths()["purelib"]`` 为主，仓内 ``.venv`` 只作补充）后
两态逐枚相等（现取：state① 有 ``.venv``、state②③④⑤ 没有，11 枚指标读数全等，见上表末列）；取不到依赖的那枚刀改为如实 skip，不假红。

## 4．判据第 3 样｜批量转换的派工切法（写给总控，本席不执行）

```text
.\.venv\Scripts\python.exe scripts\r638_doc_pointer_ruler.py --batches --max-per-batch 250
```

现取分账：可转池 **1,146** 枚（9 批）＋ 取证原文行
**151** 枚（逐枚排除）＋ 排除 **2,805** 枚
（账本 2,590／契约 215）
＝ 4,102。原则：**同一枚 .md 只属一枚写集**（按所在目录归组、按枚数装桶）。

| 批 | 所在目录 | .md | 枚数 | 判红 | 可直接换锚点 | 待人定夺 | 风险旗标 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R638-01-docs | ``docs`` | 5 | 90 | 19 | 67 | 4 | — |
| R638-02-api | ``docs/api`` | 1 | 8 | 5 | 2 | 1 | **过半判红** |
| R638-03-deployment | ``docs/deployment`` | 3 | 18 | 1 | 17 | 0 | — |
| R638-04-perf | ``docs/perf`` | 10 | 248 | 50 | 170 | 28 | — |
| R638-05-perf | ``docs/perf`` | 6 | 20 | 1 | 19 | 0 | 取证纸 1 枚 |
| R638-06-testing | ``docs/testing`` | 2 | 201 | 30 | 169 | 2 | 取证纸 1 枚 |
| R638-07-testing | ``docs/testing`` | 9 | 240 | 48 | 173 | 19 | 取证纸 3 枚 |
| R638-08-testing | ``docs/testing`` | 29 | 250 | 58 | 162 | 30 | 取证纸 5 枚 |
| R638-09-testing | ``docs/testing`` | 23 | 71 | 20 | 42 | 9 | 取证纸 7 枚 |

每批的 .md 名单在机器件 ``batches[i].docs`` 逐枚点名。派法建议：**并发不超过 3～4 枚**（业主 10-04 明令
的服务侧上限）；先派 ``R638-06``／``R638-04``／``R638-07`` 三枚大池；``R638-02-api`` 带「过半判红」旗标
（8 枚里 5 枚已对不上）——先定夺漂移再换锚点。姿势：可机械锚的改 ``文件::符号``；
不可直接换那 519 枚留在原地等人名；判红的 972 枚先定夺。

### 4A．三类必须排除（只出清单，落不落由总控按先例办）

| 排除族 | 范围 | 坐标枚数 | 理由 |
| --- | --- | --- | --- |
| ``docs/handoff/**`` | 31 枚 .md | 2,590 | 跟进单与看板是**只许文末追加**的账本：中间改字会破在册的 pure_append 钉。作废声明走文末追加、不抹原文（先例 R523／R558／R635；坐标改锚点先例 R400／R630／R635） |
| ``docs/api/contract-v1.md`` | 1 枚 .md | 215 | 同一枚文末追加纪律，由 ``tests/test_r523_cached_count_lands.py::contract_is_pure_append`` 挡中间改字 |
| 取证原文行（逐枚） | 44 枚 .md 里的 151 枚 | 151 | 那一枚引用本身就是当时那次读数／那句假话的凭据，改它＝销毁证据。识别形状：行内含「事故 #」／「取证」／「原文」／「逐字」／「作废」／「复现」／「现取」／「实测读数」／「症状」 |

**两格不同底（别当成对不上账）**：全册判红的取证原文行 180 枚（含账本与契约），
排除格逐枚只列**能进写集**那 151 枚取证行——账本与契约整枚排除，其内的
取证行不再逐枚点名（改不了的文件，点名也没处落）。全册取证行合计 703 枚，其中 552 枚
落在被整枚排除的账本/契约里。

账本那 31 枚 .md（本件一字未动，逐枚只列名）：``2026-09-14-consolidated-fix-plan.md``、``2026-09-15-alert-and-hitl-design.md``、``2026-09-15-backend-followup-requests.md``、``2026-09-15-frontend-startup-prompts.md``、``2026-09-15-frontend-work-checklist.md``、``2026-09-15-orchestration-board.md``、``2026-09-17-eval-real-run-runbook.md``、``2026-09-17-human-gates.md``、``2026-09-17-perf-architecture-plan.md``、``2026-09-17-pgvector-adoption-plan.md``、``2026-09-19-eval-evidence-audit.md``、``2026-09-19-native-route-audit.md``、``2026-09-20-eval-window-rehearsal.md``、``2026-09-20-r118-subgraph-memory.md``、``2026-09-20-r120-execution-report.md``、``2026-09-20-unblock-map.md``、``2026-09-21-must-contain-orphans.md``、``2026-09-23-v1-acceptance-record.md``、``2026-09-25-plan-ticket-closure.md``、``2026-09-25-r238b-connect-site-audit.md``、``2026-09-25-r246-readiness-notes.md``、``2026-09-26-frontend-gap-recheck.md``、``2026-09-26-v1-frontend-gap-list.md``、``2026-09-26-v2-wave3-dispatch-plan.md``、``2026-09-26-v2-wave4-dispatch-plan.md``、``2026-09-27-v2-gap-recheck-2.md``、``2026-09-29-v2-gap-recheck-3.md``、``2026-09-30-plan-eight-tickets-recheck.md``、``2026-09-30-v2-gap-recheck-3.md``、``plan-ticket-ledger-2026-09-26.md``、``r591-compat-thinking-lever-2026-10-03.md``

取证原文行的分布（前 15 枚；逐枚清单在机器件 ``batches.forensic_lines``）：

| 所在 md | 枚数 |
| --- | --- |
| ``docs/testing/r573-a2-three-calibres-run1314-2026-10-03.md`` | 17 |
| ``docs/testing/r536-retrieval-trace-emission-2026-09-30.md`` | 16 |
| ``docs/testing/r506-a2-reading-2026-09-29.md`` | 12 |
| ``docs/perf/chroma-unreachable-root-cause-2026-09-26.md`` | 8 |
| ``docs/testing/r495-session-namespace-2026-09-29.md`` | 8 |
| ``docs/testing/r548-queue-lane-piece-sink-registration.md`` | 8 |
| ``docs/testing/r535-context-window-pairing-2026-09-30.md`` | 7 |
| ``docs/perf/a2-single-frame-attribution-2026-09-28.md`` | 6 |
| ``docs/testing/r471-verdict-caliber-2026-09-29.md`` | 6 |
| ``docs/testing/r518-a2-lane-attribution-2026-09-29.md`` | 5 |
| ``docs/perf/r565-a2-denominator-buckets-2026-10-02.md`` | 4 |
| ``docs/testing/r46c-engagement-signals-2026-10-03.md`` | 4 |
| ``docs/testing/r509-artifact-lineage-landed-2026-09-29.md`` | 4 |
| ``docs/testing/r523-prompt-cache-tokens-2026-09-30.md`` | 4 |
| ``docs/testing/r524-stream-piece-sink-two-runways.md`` | 4 |

另有一格旗标 ``risk.forensic_paper_docs``：整篇就是取证纸的命名形状（readout／reading／verdict／caliber／
recheck／closure／窗口…）。这些文档落在批里，上表「风险旗标」列逐批点名了几枚——总控要收口就把它们整枚提入排除。

## 5．写域、禁区分歧与盲区

- 写域（本单只新增这 5 枚）：``scripts/r638_doc_pointer_ruler.py``、
  ``tests/test_r638_pointer_ratchet.py``、``tests/test_r638_counter_evidence_teeth.py``、
  ``docs/testing/r638-pointer-baseline.json``、本纸。
- 整册读数按 R638-R⑤ **留在仓外隔离区**：``C:/Users/fengx/AppData/Local/Temp/eb104/r638-census-quarantine/r638-census-2026-10-04-R.json``／5,314,464 B／
  sha256 ``61fc3ec114f42d69c3069d88a596f50be5b05379c4e28961ad1b730342d4a6ff``＝本席 R 版重取（4,102 枚逐枚判定＋派生读数＋批量切法）。总控 §173.2 在册存档那枚 ``r638-census-2026-10-04.json``／4,853,080 B／sha256 ``aaa3090ab0c92fa91284bc6aa09171986bea94da2041adf1bbaaa49f26e92e9a`` 同目录并存，本纸引用的是上面 R 版那一枚；两枚的字节数与 sha 都由生成器现算，在册那枚另与跟进单 §173.2 原文逐字符核对（不等即抛）。
- 禁区未碰：``app/**``／``frontend/**``／``deploy/**``／``.env*``／``docs/**`` 正文／评测夹具／
  ``scripts/r631_stage_sum_delta.py`` 及在册件／``scripts/run_gate.py``／``pyproject.toml``／锁文件。
- **正文一枚 .md 未改**；未 commit、未建分支、未 push（判据⑥五枚现取见本纸 §6，取于本纸落笔那一刻）。
- 零 import 产品码（解析走 AST）、零容器、零连库、零打模型；反证刀全部落 tmp_path，
  在册 ``test_r253_no_test_rewrites_a_tracked_file`` 的两枚把手（静态扫描＋审计钩子）都未被我绕过。
- 盲区明写：``unverified_no_claim`` 那 2,373 枚只量到「行在界内」；
  ``shape_talk``／取证行两族带旗标不剔除；基名歧义那 78 枚未替总控猜路径。
- 判据歧义未自行扩权：本单**没有**顺手改任何 .md 正文，也没有动写域外的一处。

## 6．收席五枚（现取于本纸落笔那一刻）

```text
$ git -C be-r638 status --porcelain
?? docs/testing/r638-pointer-baseline.json
?? docs/testing/r638-pointer-ruler-2026-10-04.md
?? scripts/r638_doc_pointer_ruler.py
?? tests/test_r638_counter_evidence_teeth.py
?? tests/test_r638_pointer_ratchet.py
```

```text
$ git -C be-r638 diff --numstat HEAD
(空)
```

```text
$ git -C be-r638 ls-files --others --exclude-standard
docs/testing/r638-pointer-baseline.json
docs/testing/r638-pointer-ruler-2026-10-04.md
scripts/r638_doc_pointer_ruler.py
tests/test_r638_counter_evidence_teeth.py
tests/test_r638_pointer_ratchet.py
```

```text
$ git -C be-r638 rev-list --count 473235f..HEAD
0
```

```text
$ git -C be-r638 rev-parse HEAD
473235f75122899c2c509bd39571ee5e3c6492fa
```

逐枚读数（现取）：``status --porcelain`` 列出 5 枚新增件、``diff --numstat HEAD`` 为空＝tracked 正文一枚未改、``ls-files --others`` 同列 5 枚、``rev-list --count 473235f..HEAD`` = 0＝未 commit、``HEAD`` = 基点。写盘之后生成器立刻复跑同五枚并断言逐字节相等（不等即抛）。

