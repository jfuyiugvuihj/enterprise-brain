# R599 · 一份合成中文扫描件走在册 OCR 腿一次，逐页读数（2026-10-03）

- 单号：R599（P2）·工作树 `be-r599`@`4aa1126`·执行层席（名号按本仓老规矩：投递端不下发代号，本文只署名号＋树号）
- 判据唯一事实源：`docs/handoff/2026-09-15-backend-followup-requests.md` §160.6 R599 那一节
- 起因：V2 #13「一份真扫描件跑通一次并留读数」长期挂着，因为手上没有扫描件样本；业主 10-03 令**按合成件做**。
  本单**不给 OCR 加功能**，是给在册通道做一次有凭据的体检。
- 全程离线纯本机 CPU：不打模型、不动容器、不起服务、不建索引、不发向量、不落库。所有复跑数字**执行层自报**。

## 0. 结论（逐格对判据）

| 判据 | 结论 | 凭据 |
| --- | --- | --- |
| ① 无文本层中文 PDF，位图里不许有统计数字 | **做到**：4 页 A4，逐页零文本层、逐页挂位图；像素里既没有阿拉伯数字也没有中文数字与指标词，且这一格由常驻钉与发生器两道把手同时守住 | §1、§2、§8 K3 |
| ② 走在册 OCR 腿跑通一次，交回逐页读数 | **跑通**：4/4 页判成扫描页，第 1-3 页出字（`ocr`），第 4 页有图无字（`ocr-empty`），默认路径下**没有任何一页没跑成** | §2、§3、§5 |
| ③ 不许灌进 `documents/**`，只走一次性解析 | **零变化**：`git status` 只有本单四枚新文件，`documents/**`、`data/**`、`chroma_db/**` 逐枚零命中；件落 `docs/testing/fixtures/` | §7 |
| ④ 如实报 R301 那一格：`PdfExtractionReport` 有没有消费方 | **有**（不是挂着）。R301 已于 `a0179b6` 并树、R338 已于 `e0168b7` 把这一格搬上员工屏；本单又用 live 调用把这格的读数原样取回一次 | §6 |
| ⑤ 交工纸＋一枚常驻钉（默认 skip＋env 开关，不靠打模型/打 OCR 做常绿） | **交付**：`tests/test_r599_synthetic_scan.py`；不装开关 `11 passed / 2 skipped`，装开关 `13 passed`；四把反证逐把 sha 可对 | §8、§9 |

🔴 一句话不许越界：**这份件是合成的**。它证明的是「在册 OCR 通道 + 逐页账 + 回执那一格 + 屏上那句话」这条链在一份
无文本层中文件上真跑得通、真出字、真记账；它**不证明**客户手里那种带歪斜、印章、手写、彩色 JPEG 的真扫描件的质量。
后者见 §9「未验的格子」。

## 1. 件本体

| 项 | 读数 |
| --- | --- |
| 路径 | `docs/testing/fixtures/r599-scan-demo.pdf` |
| 字节 | 1,154,944 |
| sha256 | `1c2aacd751601243605e963ed2b59290611cf1791cba70bba2de6e0660f37053`（前 12 位 `1c2aacd75160`） |
| 页数 | 4 |
| 页面尺寸 | 每页 `/MediaBox [0 0 595 842]`（A4 pt） |
| 位图原生 | 1240 x 1754 px（150 DPI 档，与 `tests/fixtures/r298_scanned_pages.pdf` 同档） |
| 文本层 | 4/4 页 `pypdf.extract_text()` 交回空串；页算子里 `BT` 0 枚、`Tj` 0 枚 |
| 图像对象 | 4/4 页 `/Resources /XObject` 里有且仅有 `/Subtype /Image` |

三把尺各测一次「位图里没有统计数字」这条铁规（R148 那笔换图事故订下来的）：

1. **源句尺**（出件前拦）：发生器 `scripts/r599_synthetic_scan.py` 里那 11 枚要印进像素的句子，逐枚过三把禁尺——
   ASCII 数字、中文数字字符（`〇一二三四五六七八九十百千万亿两零`）、指标词（`%` `百分之` `元` `万元` `亿` `倍`
   `同比` `环比` `增长率` `占比` `达成率` `得分` `排名` `均值` `指标` `统计`）。`statistics_offenders()` 交回 `[]`。
   正文因此**连"第一条／第二条"这种序数都不写**，免得"数字"这件事需要人来解释。
2. **语法尺**（出件后独立复量，不借 `app/` 的判断）：`extract_text()` 逐页空串 + 页算子逐页零 `BT`/`Tj`
   ⇒ 位图之外根本没有第二套字可以藏数字。
3. **目视尺**（真打在册 OCR 后复述）：整页 OCR 正文过一遍数字尺，`[0-9]` 零命中、中文数字零命中——
   见 §3 的原文，读者可以自己逐字看：那份正文里没有任何统计量。

**折行这一格是本班自己踩出来的**（如实入账）：首版件（15:52，sha `7f738e8305c0`，已作废）把 44 号字的整句直接画到
1240 px 宽、99 px 左边距的画布上，一句三十四字约 1,496 px，**超出画布的部分被 PIL 静默裁掉**——真打 OCR 读回
「…超标部分」这种半句话。那既不是识别失败，也不是假指标，而是**样本自己缺字**。因此 `fit_lines()` 成为出件硬前置：
句子按可用宽度 1,067 px 折行（拉丁词优先在空格断、中文逐字断），折完仍画不下的行、或行数越过下边距的，一律
`SystemExit` **拒绝出件**。在册四页的几何账（现取）：

| 页 | 字号 | 源句 | 折后视觉行 | 最宽行 / 可用宽 | 最低绘制行 |
| --- | --- | --- | --- | --- | --- |
| 1 | 44 | 4 | 7 | 1056 / 1067 px | 854 px |
| 2 | 44 | 4 | 6 | 1056 / 1067 px | 762 px |
| 3 | 34 | 3 | 3 | 1020 / 1067 px | 423 px |
| 4 | — | 0（有图无字页） | 0 | — | — |

页面形状是照真扫描件的四族挑的：正文页（第 1 页）、中英混排页（第 2 页）、二次复印式低质量页（第 3 页：34 号字 +
高斯模糊 1.6 + 灰度压平 0.8 + 高斯噪点 10）、有图无字页（第 4 页：只画一个空表单框，`ocr-empty` 那一形靠它）。

## 2. 逐页读数（判据② 的三句话，逐页各答一次）

跑法：`python scripts/r599_readout.py --case scan`（工作目录 = 仓库之外，见 §7 那条坑）；DPI = 在册默认 200。
件账：`pages=4 scanned=4/4 scanned_pages=[1, 2, 3, 4] dpi=200 [ocr=3 ocr-empty=1]`，`degradation_sentence=""`。

| 页 | 是不是扫描页 | 判定输入（文本层字数 / 有无位图） | OCR 出没出字（`source`） | 没跑成？（`note` 原文） | 单页耗时 | 栅格 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 是 | 0 字 / 有图 | 出字（`ocr`） | 无 | 4,106.2 ms | 1653x2339 |
| 2 | 是 | 0 字 / 有图 | 出字（`ocr`） | 无 | 2,526.5 ms | 1653x2339 |
| 3 | 是 | 0 字 / 有图 | 出字（`ocr`） | 无 | 2,320.1 ms | 1653x2339 |
| 4 | 是 | 0 字 / 有图 | **没出字，且不是降级**（`ocr-empty`） | 图像页 OCR 未检出文字 | 899.5 ms | 1653x2339 |

- 整件正文 302 字，`nul_in_text=false`（R130 那一刀在本件无 NUL 可削，如实报"未触发"而不是"已验证"）。
- 阈值那一半边：`scanned_page_text_char_threshold()` 现读 **48**（`SCANNED_PAGE_TEXT_CHARS`），四页文本层都是 0 字 ⇒
  AND 的左半边为真；`page_has_image_object` 四页全真 ⇒ 右半边为真。**两半边各量一次，不靠结论倒推**。
- 第 4 页这一格是本件最值钱的一枚形状：`ocr-empty`（这页确实没字）与 `ocr-degraded`（这页根本没跑成）在检索面是
  两句不同的话，`loader.py` 的分界在真件上落成读数了。

## 3. OCR 回来的正文原文（逐页，不校对、不修饰）

```
第 1 页
内部管理制度宣贯会纪要
会议明确，差旅住宿标准按照集团现行制度执行，超标
部分须事前书面报批。
会议指出，各所属单位应当如实记录资金使用情况，并
按月报送综合办公室
会议强调，档案管理遵循谁形成、谁整理、谁负责的原
则。

第 2 页
机房出入管理办法
进入机房须佩戴工牌并由值班人员陪同，严禁单独作业
Server room access requires a badge and a
companionat all times.
值班人员应当如实填写交接班记录并留存备查。

第 3 页
库房巡检记录填写说明
巡检人员应当当场填写巡检记录，不得事后补记或者代签。
发现渗漏、异味或设备异响时，立即上报安全管理部门并留存现场。

第 4 页
（空 —— 图像页 OCR 未检出文字）
```

质量读数（与源句逐字对照后才敢写这几句）：

- **汉字正文逐字读回**：11 枚源句的内容全部回到正文，没有一枚字被读成别的字，也**没有多出任何字**（不幻觉）。
- **瑕疵集中在两类**：① 行尾句号丢（第 1 页「按月报送综合办公室」、第 2 页「严禁单独作业」两处的 `。` 没读回来）；
  ② 折行处的空格粘连（第 2 页英文 `companion at all times.` 读成 `companionat all times.`）。
  两类都不改变可检索性，但都是**真实读数**，不许在纸上抹平。
- 反直觉的一格：**第 3 页那枚故意做糊的低质量页反而逐字全对**（含句号）。原因写在 `app/rag/ocr.py` 里——
  `Global.max_side_len=2000` 会把长边压回 2,000 px，34 号字那页本来就没用到 200 DPI 的像素预算，糊与噪点不足以
  破坏检测框。这条读数的意义是：**"模糊＋噪点"不是本档 DPI 下的决定性变量，行尾小标点与折行才是**。
- 整页正文过数字尺：`[0-9]` 零命中、`〇一二三四五六七八九十百千万亿两零` 零命中 ⇒ 位图里确实没被烤进统计数字。

## 4. 耗时读数与先例对照（对照不当结论）

先例读数（跟进单/看板 R298 那一行，Arendt 09-26 实测）：引擎初始化 **0.610 s**；扫描页单页 CPU dpi=200
**min 1.14 / 中位 2.11 / max 2.72 s**。本单现取（同一台机、同一枚 venv，非那一次）：

| 量 | 本单读数 |
| --- | --- |
| 引擎初始化（`get_engine(force_new=True)`，绕开缓存） | 0.681 s（`--case scan`）/ 0.669 s（`--case repeat`） |
| 第一轮逐页（引擎已建、**含首次推理预热**） | 4,106.2 / 2,526.5 / 2,320.1 / 899.5 ms；min 0.900 / 中位 2.423 / max 4.106 s；整件 9.852 s |
| 第二轮逐页（同进程内复跑 = 稳态） | 1,834.7 / 2,484.9 / 1,623.1 / 912.6 ms；min 0.913 / 中位 1.729 / max 2.485 s；整件 6.855 s |

- **稳态那一轮与先例同档**（0.913/1.729/2.485 vs 1.14/2.11/2.72），max 还略低——第 4 页无字，检测框为空，只花 0.9 s。
- 第一轮 max 4.106 s **高于**先例 max 2.72 s。这**不是**"这页更难"：`ocr.py` 的计时是本页总账（栅格化＋预处理＋推理），
  而 onnxruntime 首次推理有一次性成本，落在第一枚页上。所以本单**拒绝**把 4.106 s 当成单页成本报上去，改成两遍账并交
  （先例那一行只交了一遍 min/中位/max，没写明它属于冷的一遍还是稳的一遍 ⇒ 该格记**不可比**，不记矛盾）。
- 引擎初始化 0.681/0.669 s 与先例 0.610 s 同档，一次性成本由 `get_engine` 缓存承担（本件四页只付一次）。
- 绝对毫秒不当门（R269 收口那笔点名的假红族）：常驻钉里只断言 `ocr_elapsed_ms > 0`，耗时一律打印。

## 5. 「哪几页没跑成」：默认零页，另外两形各复现一次

- **默认路径（dpi=200、上限 80 页、通道开着）**：`ocr_degraded_page_numbers=[]`，`degradation_sentence=""`
  ⇒ 这一份件今天**没有任何一页没跑成**。这是读数，不是设计。
- **形二：本次调用关掉 OCR 通道**（`--case ocr-off`，零引擎成本）：
  `pages=4 scanned=4/4 … [ocr-degraded=4]`，降级句逐页点名原因——
  `扫描页 OCR 降级：第1页：扫描页未送 OCR（本次调用关闭了 OCR 通道）；第2页：…；第3页：…；第4页：…`
  ⇒ 关掉通道的四页**没被说成"这页没字"**，两态分家在真件上成立。
- **形三：页数触顶**（`--case degraded-limit`，`DOCUMENT_OCR_MAX_PAGES=1` 现读 `resolve_max_pages(None)==1`）：
  `[ocr=1 ocr-degraded=3]`，`扫描页 OCR 降级：第2页：超出单次 OCR 页数上限 1；第3页：…；第4页：…`
  ⇒ 第 1 页真出字、第 2-4 页记名为"这轮没跑"，不是"没字"。截断留名这一格在真件上也落成读数。

## 6. R301 那一格：`PdfExtractionReport` **今天有消费方**（判据④）

结论：**有**，那一格不用继续挂着。链路逐层点名（每层都是本树 `4aa1126` 现读）：

1. `app/rag/loader.py:183 class PdfExtractionReport` → `loader.py:591` 一带组装成 `DocumentExtraction(..., pdf=report)`，
   对外由 `extract_document_with_reports()` 交回。
2. `app/api/v1/chat.py:4413 def _pdf_extraction_cell(extraction)`：只搬已有读数（`page_count` / `scanned_pages` /
   `scanned_page_numbers` / `ocr_attempted` / `ocr_available` / `ocr_engine` / `ocr_dpi` / `source_counts` /
   `ocr_degraded_page_numbers` / `degradation_note`），非 PDF 整格 `None`，格里没有绝对路径。
   调用点 `chat.py:4601`，四条返回路径各带同一格（`chat.py:4628 / 4703 / 4734 / 4765`）。
3. 前端 `frontend/src/components/DocPanel.vue:302-312 pdfExtractionLines()` 把它画成人话：
   `本次共 {page_count} 页 · 扫描页 {scanned_pages} 页 · 第 … 页`；`DocPanel.vue:676` 读 `res.data.pdf_extraction`。
   回执为 `null` ⇒ 整格不画（不许画成"0 页扫描"）。
4. 并树账：R301 = `a0179b6`（回执真过 HTTP），R338 = `e0168b7`（这一格上屏）。在册钉：
   `tests/test_r301_upload_readout.py`、`frontend/src/components/__tests__/r338-pdf-readout.test.js`。

本单**没有**为此新造第二套上报，也**没有**改 `app/**` 接新管道（写域禁区）。live 凭据 = 用在册把手把那格原样取回一次
（`python scripts/r599_readout.py --case receipt`，走 `extract_document_with_reports` → `_pdf_extraction_cell`）：

```json
{
  "page_count": 4,
  "scanned_pages": 4,
  "scanned_page_numbers": [1, 2, 3, 4],
  "ocr_attempted": true,
  "ocr_available": true,
  "ocr_engine": "rapidocr_onnxruntime",
  "ocr_dpi": 200,
  "source_counts": {"ocr": 3, "ocr-empty": 1},
  "ocr_degraded_page_numbers": [],
  "degradation_note": ""
}
```

⇒ 屏上那句话就是「本次共 4 页 · 扫描页 4 页」。**注意射程**：这是"这一次上传的读数"，`app/documents/catalog.py` 对
`pdf_extraction` 零命中 ⇒ 不落库、刷新即消失（R338 明写）。历史扫描件能不能回看这一格仍是一枚**等业主的迁移单**，
本单不动它。

### 6.1 顺手抓到的一枚副作用（与 V2 #13 无关，但值得入账）

`import app.api.v1.chat` 在 **import 期**就按 `./chroma_db` 建 Chroma 持久客户端（默认值在
`app/rag/retriever.py:1018 def __init__(self, chroma_dir: str = "./chroma_db", ...)`——**相对 CWD**），
并顺手建出 `./data`、`./documents` 两个目录。本班 15:49:56 在仓库内试跑一次 import，`chroma_db/chroma.sqlite3`
当场被改脏（同长度、首字节差在 offset 27），已按备份**逐字节还原**（sha `a486e44e…` 对 `loader.py`、
`0b8cb318…` 对 `chroma.sqlite3`，`git status` 复验干净）。`pytest` 下有 R134「工作树 Chroma 写回闸门」改道，
**裸跑脚本没有**这层保护。对策（已落进 `scripts/r599_readout.py`）：`require_cwd_outside_repo()`——CWD 落在仓内
直接拒绝运行并写明原因。🔴 这一格只是**报出**：修法要动 `app/**`（他单在飞），不在本单射程，也未开单。

## 7. 语料零变化凭据（判据③）

- 一次性解析：全程只调 `app/rag/loader.py` 的解析函数 + `chat.py` 那枚在册消费方函数。无写库、无迁移、无建索引、
  无向量、无 embedding 调用、无模型调用（conftest 的 R56 闸门在同一趟里报 `blocked connect attempts to host model port: 0`）。
- 件的落点：`docs/testing/fixtures/r599-scan-demo.pdf`（与在册 `docs/testing/fixtures/r97-shard-*.jsonl` 同目录）。
- 盘面（本单全部产物，四枚新文件，零修改）：

```
?? docs/testing/fixtures/r599-scan-demo.pdf
?? scripts/r599_readout.py
?? scripts/r599_synthetic_scan.py
?? tests/test_r599_synthetic_scan.py
```

- `documents/**` / `data/**` / `chroma_db/**` 里 `r599` 零命中（常驻钉 `test_the_fixture_never_got_copied_into_the_corpus`
  把这格钉成常绿断言）；发生器另有一把 `refuse_forbidden_targets`，`--out` 指到这三棵目录之下当场 `SystemExit`。
- `test_corpus_parity` 那一族只扫 `documents/`（现读 `tests/test_corpus_parity.py:117`），本件在 `docs/` 之下，不参与语料账。

## 8. 常驻钉 `tests/test_r599_synthetic_scan.py`

形状照 `tests/test_r540_scan_offline.py` 的先例：**默认腿离线常绿、真打引擎那腿 env 开关**。

| 趟 | 命令 | rc | 数字 |
| --- | --- | --- | --- |
| 不装开关（常驻形态） | `python -m pytest tests/test_r599_synthetic_scan.py -o addopts= -p no:cacheprovider --basetemp=%TEMP%\r599_bt_final_off -q` | 0 | **11 passed, 2 skipped** in 0.44 s（skip reason 逐枚打印，见下） |
| 装开关 | 同上，前置 `set R599_REAL_OCR=1` | 0 | **13 passed** in 14.22 s |

- 干净 skip 的两枚（不是假 pass，`-rs` 原文）：
  `SKIPPED [1] tests\test_r599_synthetic_scan.py:264: 真打 rapidocr 不是常驻腿：R599_REAL_OCR=1 才跑（CPU 单页 0.9-4.1 s，见件首）`
  `SKIPPED [1] tests\test_r599_synthetic_scan.py:310: 页数触顶那一形同样要真打引擎才能拿到降级账：R599_REAL_OCR=1 才跑`
- 默认腿**不打 OCR、不打模型**：判定的逐页账用 `enable_ocr=False` 跑（零引擎成本，0.4 s），真打的两枚腿全部 gated。
  ⇒ 判据⑤「常驻钉不许靠打 OCR 做常绿」达成。
- 默认腿钉的内容（枚枚可点名）：件字节与 sha256 / 逐页零文本层 + 零 `BT`/`Tj` / 逐页 `/Image` 在位且 A4 /
  11 枚源句过三把禁尺 / 尺本身会响（喂三句假指标必点六枚名，捏一句必 `SystemExit`）/ 折行两把拒绝出件的刀 /
  落点把手拒绝写进语料三棵树 / 语料里今天没有 `r599` 副本 / 4 页全判扫描页**且对照页必不判**/
  回执那格与屏上那句话的在册链路仍在（静态复述，🔴 不 import `chat.py`，理由见 §6.1）。
- gated 腿钉的内容：`ocr_available` 为真、`source_counts == {ocr:3, ocr-empty:1}`、第 1-3 页出字且耗时>0 且栅格
  1653x2339、第 4 页 `ocr-empty` 并点名「图像页 OCR 未检出文字」、整页正文过数字尺零命中、三枚标题句子逐字回读；
  另一枚 gated 钉 `DOCUMENT_OCR_MAX_PAGES=1` 时第 2-4 页必须 `ocr-degraded` 且原因点名"超出上限"。

## 9. 反证（四把，逐把交回 sha）

sha 一律 sha256 全串前 12 位缩写并注明文件；「还原」一律走摘前的**字节备份文件**回写（不是重写一遍），并复验逐字节全等。

| 刀 | 摘什么 | 摘前 sha | 摘后 sha | 还原后 sha | 结果 |
| --- | --- | --- | --- | --- | --- |
| K1 | 摘掉 env 开关（`R599_REAL_OCR` 不设） | `tests/test_r599_synthetic_scan.py` 全程未改：三趟同一个 sha256 `7350f20f038a…` | 同（不改文件） | 同 | **必须 skip 不是 pass**：不装开关 `11 passed / 2 skipped`，两枚 gated 腿以具名 reason 干净 skip（§8 原文）；装开关才 `13 passed` |
| K2 | 把 `app/rag/loader.py` 的扫描页判定**改宽**：`chars < threshold and has_image` → `has_image`（AND 的左半边摘掉） | `a486e44e5766…` | `d78cb7c94f34…` | `a486e44e5766…`（`byte_identical=True`，`git diff --numstat HEAD -- app/rag/loader.py` 空） | **②那本逐页账当场红**：`test_r599_synthetic_scan.py:233` = 「把扫描页判定改宽（只看有没有图）= 本钉当场红」，对照页（有文本层 165 字 + 挂位图）被误判成扫描页；`1 failed, 12 deselected` |
| K3 | 往 `scripts/r599_synthetic_scan.py` 的源句里烤一枚假统计：`会议强调，档案管理遵循…` → `会议强调，回款同比增长百分之七。` | `64469a2c8bd5…` | `c4d073bb1f91…` | `64469a2c8bd5…`（`byte_identical=True`） | **两响**：常驻钉 `test_r599_synthetic_scan.py:131` 红（`1 failed, 10 passed, 2 skipped`）；发生器 `--geometry-only` **拒绝出件** rc=1，原文「🔴 R148 铁规：位图里不许有统计数字或假指标 —— 含中文数字「百」…；含指标词「百分之」…」 |
| K4 | 换掉已入库件的像素：在文件正中翻一枚字节（`XOR 0x55`） | `1c2aacd75160…` | `b323ea51843b…` | `1c2aacd75160…`（`byte_identical=True`；还原后 `--case probe` 复跑 `all_zero_text_layer=true / all_have_image_object=true`） | **两响**：`test_r599_synthetic_scan.py:93`（sha 漂移）+ `:119`（account 与纸面对不上）红，`2 failed, 9 passed, 2 skipped` |

🔴 三处如实标注：① K2 摘的是**禁改文件** `app/rag/loader.py`，摘后立即按备份还原，交回时该文件与 HEAD 逐字节全等；
② K4 首把曾误用 `\xff\xff\xff\xff` 作为靶子（Flate 流里不存在该序列，`apply` 直接 `AssertionError` 退出、件未被动过，
那一趟 `11 passed / 2 skipped` 属**无效反证**，已重跑），这是本单一枚自抓的流程错——不记作成功刀；
③ K1 不改文件，故"摘后 sha"与"摘前 sha"同一个值，它摘的是环境变量。

## 10. 未验的格子（逐枚点名，不许含糊）

1. **真客户扫描件**：本件是合成件（业主令已覆盖"按合成件做"这一格，但不覆盖质量结论）。带页边倾斜、印章压字、
   手写签批、彩色 JPEG 原生分辨率、双面重影的真件，**一页都没测**。
2. **端到端 HTTP 上传**：判据④ 的"屏上看得到"是三层证据——后端函数源码在册、`_pdf_extraction_cell` 的 live 读数、
   前端源码里的画法与 R338 的 vitest 在册钉。🔴 **浏览器里真画出来了**那一格本单**未验**（不许动容器/起服务）。
3. **落库与检索面**：本件按判据③ 只做一次性解析。OCR 回来的正文进了哪个 chunk、检索能不能命中、
   与既有语料有无近重复，**一律未测**（也不许测——它会改数据）。
4. **OCR 质量的上界/下界**：只量了一份件的四族。字小于多少读不出、模糊到几读不出、dpi 72 与 600 的实测档
   都没重跑（`ocr.py` 里那几张 dpi 表是 R298 的旧读数，本单未复核）。
5. **长件与页数上限**：`DEFAULT_OCR_MAX_PAGES=80` 只在演示里把上限压到 1。真实 80 页、以及 81 页那一格
   （"这轮没跑"的账会不会漂），**未量**。
6. **并发与多进程**：`get_engine` 的进程内锁（backend/worker/scheduler 三份实例）在真并发下会不会互相踩，**未测**。
7. **扫描页里的表格**：`app/rag/loader.py` 明写今天不支持（无框线、无文本层），本单**未验也没打算验**，记在册边界。
8. **NUL 那一族**：本件正文无 NUL（`nul_in_text=false`），所以 R130 那一刀在本件上是"未触发"，不是"已验证"。
9. **`documents/**` 之外的既有历史窗口可比性**：本件没碰语料，故 P-17 哨兵未跑（不在射程，也不该由本单跑）。
10. **§6.1 那枚 import 期 Chroma 副作用**：只**报出**并加了本单脚本的把手，`app/**` 层面**未修**、**未开单**。

## 11. 复算指令（工作树 `be-r599`，解释器 = 主树 .venv）

```powershell
# 1) 造件/复量（只写 docs/testing/fixtures/；指到 documents|data|chroma_db 之下会当场拒绝）
python -X utf8 scripts\r599_synthetic_scan.py --geometry-only   # 折行与几何账
python -X utf8 scripts\r599_synthetic_scan.py --verify-only     # 语法尺 + sha 账（不落盘）

# 2) 读数（🔴 必须先把工作目录切到仓库之外，理由见 §6.1）
cd %TEMP%\eb103\r599_cwd
python -X utf8 C:\Users\fengx\PycharmProjects\be-r599\scripts\r599_readout.py --case probe
python -X utf8 C:\Users\fengx\PycharmProjects\be-r599\scripts\r599_readout.py --case scan
python -X utf8 C:\Users\fengx\PycharmProjects\be-r599\scripts\r599_readout.py --case repeat,ocr-off,degraded-limit,receipt

# 3) 常驻钉：默认（干净 skip）与装开关（真打）两趟
cd C:\Users\fengx\PycharmProjects\be-r599
python -X utf8 -m pytest tests\test_r599_synthetic_scan.py -o addopts= -p no:cacheprovider --basetemp=%TEMP%\r599_bt -q
set R599_REAL_OCR=1 && python -X utf8 -m pytest tests\test_r599_synthetic_scan.py -o addopts= -p no:cacheprovider --basetemp=%TEMP%\r599_bt -q
```

依赖一律用现读的在册件：`rapidocr_onnxruntime 1.4.4`（`app/rag/ocr.py` 点名的唯一引擎）/ `pypdfium2 5.13.0` /
`pypdf 6.13.2` / `Pillow 12.2.0`；三枚 onnx 模型 `missing_model_files()` 现读 `()`。**本单未装任何新依赖。**
