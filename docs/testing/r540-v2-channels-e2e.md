# R540 · V2 #13/#14/#15 端到端那一格：三条通道各离线跑通一次（10-03 现取）

执行层自报（代号 **Feynman**，工作树 `C:\Users\fengx\PycharmProjects\be-r540`，基点 `a5ba2d7`）。
总控会亲跑，本文所有读数都附**命令原文**，可就地复算。

## 0. 射程与禁域（先划边界，再谈结论）

- 全程**离线**：不打模型（零 11434/8001 请求）、不上传（不碰 `app/api` 与 `chat.py`）、
  不写库（零 PG 连接）、不写 chroma、不动容器、不跑全量门。唯一被调用的产品代码是
  `app/rag/loader.py` 的解析入口（外加纯函数 `app/documents/index_policy.py`，它不碰任何存储）。
- `app/rag/**` 与 `app/common/table_presence.py` **一字节未改**：`git status --porcelain` 见 §8。
  反证三把（§7）确实就地改写过它们，**三把全部逐字节还原**，摘前/摘后/还原 sha 各自闭合。
- 这格今天为什么还算「半」：底本 `docs/handoff/2026-09-30-v2-gap-recheck-3.md` §2.2 #13 裁定
  「码与依赖都在树上，但从没有一份真扫描件走过 上传→OCR→索引里有字」。本单交的是**除上传与落库之外的
  全部三段**：造扫描件 → 过解析入口 → 逐页来源账 → R49 入索引判定。上传与真写库那两段仍**未验**（§9）。

## 1. 样本（`scripts/r540_samples.py`，一律落 `%TEMP%\r540\`，不入仓）

造它的那段代码原文 = `scripts/r540_samples.py`（手搓 1.4 语法 PDF：一页可选一张 DeviceGray 位图
＋可选若干行 Helvetica 文本层＋可选矢量框线；位图由 `PIL` 现渲染，中文走 `msyh.ttc`）。

| 样本 | 形状 | sha256 前 12（本席连造两遍复算） |
| --- | --- | --- |
| `r540_scan.pdf` | 4 页**只有像素、零文本层**（P1 中文 / P2 中英混排 / P3 故意低质量 / P4 有图无字） | `ce2d6b793baf` ＝ 第二遍 `ce2d6b793baf` ✅ |
| `r540_mixed.pdf` | 3 页：纯图页 + 文本层页（带位图）+ 既无文本层也无图像对象的空白页 | `7d3a596069ad` ✅ |
| `r540_control.pdf` | 2 页**带文本层**（165 字）且每页都挂一张位图（判据④ 的对照件） | `06333b5df71a` ✅ |
| `r540_table.pdf` | 2 页：正文页 + 一页 4 列 4 行**矢量框线**表格 | `7a5d310c77c0` ✅ |
| `r540_table.docx` | 两段正文 + 一枚真 Word 表格（中文表头） | ❌ 不可复算（见下） |
| `r540_sales.xlsx` | 2 张 sheet；中文列名 / 空值 / 真日期 / 合并单元格 / 全 None 行 / 全空串行 | ❌ 不可复算 |
| `r540_sales.csv` | utf-8 逗号，同形 4 行 | `c207988f88f5` ✅ |
| `r540_pad.csv` | 递宽数据行（尾随 3 枚空列）+ 中间一枚空行 | `46b918d70f83` ✅ |

🔴 **复算凭据分两族**：PDF/CSV 是手写字节，两遍 sha 逐枚相等；`.xlsx` 与 `.docx` 是 ZIP 容器，
openpyxl / python-docx 把**打包时间戳**写进 zip 条目 ⇒ 同一份代码每造每换 sha（实测两遍：
xlsx `9d728b958bc1` vs `8163afdf3af8`；docx `4d50f774a7fc` vs `b8d717f416e1`）。
这两枚的复算凭据因此只能是**发生器代码 ＋ 通道自己交回的账**（§5/§6 那些数字两遍逐枚相等），
不是文件 sha。谁以后拿 sha 当这两枚的复算凭据，那是一句假话。

命令与读数：

```
python scripts/r540_samples.py --out %TEMP%\r540        → rc=0（8 枚样本，路径账 JSON）
```

扫描件「无文本层」的**跑前自证**（判据① 左半边）：

```
python scripts/r540_readout.py --out %TEMP%\r540 --case scan   → rc=0
  precondition_zero_text_layer.page_extract_text_chars = {1: 0, 2: 0, 3: 0, 4: 0}
  precondition_zero_text_layer.page_has_image_object   = {1: True, 2: True, 3: True, 4: True}
```
（`pypdf.PdfReader(...).pages[i].extract_text()` 逐页交回空串，位图对象逐页在位——AND 的两半边都真。）

## 2. ① 扫描件（#13）：真 `rapidocr_onnxruntime` 逐页读数

```
python scripts/r540_readout.py --out %TEMP%\r540 --case scan   → rc=0（进程内 4 页合计约 10 s）
```

`report.summary()` 原文：`pages=4 scanned=4/4 scanned_pages=[1, 2, 3, 4] dpi=200 [ocr=2 ocr-empty=2]`
引擎 `rapidocr_onnxruntime`，`ocr_attempted=True`，`ocr_available=True`，栅格逐页 `(1653, 2339)`。

| 页 | 印进像素的内容 | `source` | 耗时 ms（两遍现取） | OCR 回来的文本（前 40 字，空白归一） |
| --- | --- | --- | --- | --- |
| 1 | 三行中文（标题＋两条条款） | `ocr` | 5019 / 4352 | `季度回款分析说明 第一条 华东大区三季度回款同比增长百分之七 第二条单笔金额超过` |
| 2 | **中英混排**（含 `12.5%`、`zhangmin@example.com`、`13800001234`） | `ocr` | 3145 / 2846 | `Q3 revenue grew 12.5% in East China 华东大区` |
| 3 | **故意低质量**（26 px 字 + blur 6.0 + 对比 0.45 + 高斯噪点 26） | `ocr-empty` | 1183 / 1093 | 空串，note=`图像页 OCR 未检出文字` |
| 4 | 只画几何框、一个字没有 | `ocr-empty` | 874 / 906 | 空串，note=`图像页 OCR 未检出文字` |

第 1、2 页整页原文（`--case scan` 的 `ocr_text_full`，dpi=200）：

```
1: 季度回款分析说明\n第一条 华东大区三季度回款同比增长百分之七\n第二条单笔金额超过5000元需总经理审批。
2: Q3 revenue grew 12.5% in East China 华东大区,\nContact 张敏 zhangmin@example.com 13800001234.
```
⇒ 中英混排那一页的百分号、小数点、`@`、11 位数字全部原样读回；`。` 被读成 `,`/丢掉，与
`app/rag/ocr.py:52-64` 当年在册那条「句号那一档会漂」同族（漂的是标点，见 §3 的 DPI 复测）。

置信度：`recognize()`（`app/rag/ocr.py:292`）**只取 `entry[0]`/`entry[1]`，`entry[2]`（逐框置信度）今天被丢掉**
（`app/rag/ocr.py:308`），所以逐页账里没有这一格——本单按禁域不改它，改交**逐页墙钟耗时与栅格尺寸**
（`OcrPageOutcome.elapsed_ms` / `raster_size`，两列都在上面的表里）。这是「交回置信度」那一格的真实缺口，见 §8-S1。

「索引里有字」那半句的可核对形式（不打库，只看纯函数怎么判）：

```
index_gate_with_ocr    = {"eligible": true,  "reason": ""}
index_gate_without_ocr = {"eligible": false, "reason": "no_text_content"}
```
同一份文件、同一个阈值，只差 OCR 这一条腿 ⇒ 这 140 字正文**全部**来自 OCR（零文本层）。

对照件（判据④：有文本层的页一个字都不许再走 OCR）：

```
python scripts/r540_readout.py --out %TEMP%\r540 --case control   → rc=0
  summary = pages=2 scanned=0/2 scanned_pages=[] dpi=200 [text-layer=2]
  ocr_attempted = False | 逐页 ocr_elapsed_ms = 0.0 | text_layer_chars = {1: 165, 2: 165}
```
两页都挂着位图（`has_image_object` 逐页 True），文本层 165 字 ≥ 阈值 48 ⇒ AND 的左半边不成立 ⇒
**非 OCR 腿**。三形之外还钉了第四、第五形（`text-layer` / `blank`）：

```
python scripts/r540_readout.py --out %TEMP%\r540 --case mixed     → rc=0
  summary = pages=3 scanned=1/3 scanned_pages=[1] dpi=200 [blank=1 ocr=1 text-layer=1]
  第1页 ocr（1755 ms，出字）｜第2页 text-layer（0 ms）｜第3页 blank，note=`该页既无文本层也无图像对象`
```

## 3. ② 降级形状（#13）：两枚可复算造法

`ocr-degraded` 的三条来源（`app/rag/loader.py:289-312`）是**引擎不可用 / 页数触顶 / 栅格化或识别抛错**——
没有一条是「图不够清楚」。所以造降级不能用糊图（糊图落到 `ocr-empty`，见 §8-S1），本单交两枚可复算造法：

**造法甲·页数顶触顶（读数件里的 `degraded-limit` 格）**

```
python scripts/r540_readout.py --out %TEMP%\r540 --case degraded-limit   → rc=0
  env DOCUMENT_OCR_MAX_PAGES=1（同一份 r540_scan.pdf，代码里就一句 os.environ 赋值，finally 还账）
  summary = pages=4 scanned=4/4 [ocr=1 ocr-degraded=3]
  degradation_notes = ["第2页：超出单次 OCR 页数上限 1", "第3页：…", "第4页：…"]
  degradation_sentence = 扫描页 OCR 降级：第2页：超出单次 OCR 页数上限 1；第3页：…；第4页：…
  WARNING 原文 ×3： [OCR] …第2页未识别：超出单次 DOCUMENT_OCR_MAX_PAGES=1 页上限
                    [PDF] OCR 降级: …第2页：超出单次 OCR 页数上限 1
  第 2-4 页 ocr_elapsed_ms = 0.0（根本没跑，不是"跑了没字"）
```

**造法乙·引擎名指歪（= 反证 K1，见 §7）**：`ocr-degraded` ×4 + `本地 OCR 引擎不可用，扫描页未识别文字：…`。

**`ocr-empty` 两枚**（同一份件，零额外成本）：第 3 页（印了字但糊）与第 4 页（本来无字）。

三形齐发的最小可复算件（**假引擎**，门内跑，不打 onnx）在
`tests/test_r540_scan_offline.py`：`ocr` / `ocr-empty` / `ocr-degraded` × 四枚来源 /
`text-layer` / `blank` 各有专件，且「哪几页真的被送进 OCR」是一枚可断言的账（`OcrProbe.pages_sent_to_ocr`）。

**DPI 复测（在册那句话只成立一半）**：同一枚扫描页，五档现取——

```
--case mixed --dpi 72/100/200/300/400  → rc=0
  72  → "…第一条华东大区…百分之七。…"   3301 ms
  100 → "…第一条华东大区…百分之七。…"   3102 ms
  200 → "…第一条 华东大区…百分之七…"    4370 ms（同档第二遍 3415 ms，字面逐字相同）
  300 → "…第一条 华东大区…百分之七…"    4262 ms
  400 → "…第一条 华东大区…百分之七…"    4652 ms
```
⇒ 字面分**两族**：{72,100} 与 {200,300,400}，族内逐字相同、族间**空格与句号位置不同**。
`app/rag/ocr.py:59-64` 在册那句「四档识别出的文字逐字相同」在这枚样本上**不成立**
（当年那四档是 72/200/300/400，跨的正是这两族）：机制与那条注释自己的解释一致——
`max_side_len=2000` 把长边压回同一尺寸，所以 200/300/400 同族；72/100 栅格没到 2000 px，是另一族。
后果要写清：**客户改 `DOCUMENT_OCR_DPI` 跨族 ⇒ 同一页字面变 ⇒ 重算入库时正文 hash 变**，
不是"参数微调用"，是"重刷索引"级别的动作。

## 4. ③ 表格通道（#14）

```
python scripts/r540_readout.py --out %TEMP%\r540 --case table-pdf,table-docx   → rc=0
```

`table_channel` 有没有被走到——不靠转述，读**出口日志原文**与账：

```
table-pdf  [INFO] enterprise_brain: [PDF] 表格接线: …r540_table.pdf | source=pdf tables=1 rows=3
           segments=1 table_chars=125 prose_chars=211 pages=2/2 truncated=- degraded=-
table-docx [INFO] enterprise_brain: [DOCX] 表格接线: …r540_table.docx | source=docx tables=1 rows=3
           segments=1 table_chars=101 prose_chars=67 pages=0/0 truncated=- degraded=-
在册前缀现取（同一件里两枚常量）：TABLE_TRUNCATION_LOG_PREFIX = "[R304] 表格预算触顶"
                              TABLE_CHANNEL_LOG_PREFIX        = "[R304] 表格通道"
```

正文里表格那几行的**实际形状**（列结构在位，没被拍平）：

```
r540_table.pdf · 第2页 · 表1                      ← 来源锚
| region | orders | amount | owner |              ← 表头
|---|---|---|---|                                 ← 分隔行（拍平过的通道不会有这一行）
| East | 128 | 45600 | zhang |
| South | 77 | 23100 | chen |
| North | 15 | 8900 | li |
每行竖线格数 = [4, 4, 4, 4, 4]（与列数逐枚相等）

r540_table.docx · 表1 · 前文「下表为三大区回款明细，数据口径与财务系统一致。」
| 大区 | 订单数 | 回款金额 | 负责人 |
|---|---|---|---|
| 华东 | 128 | 45600 | 张敏 |
| 华南 | 77 | 23100 | 陈默 |
| 华北 | 15 | 8900 | 李雷 |
```

判据①「同一枚表不许吐两次」在这一枚上是可数的：`text.count("45600") == 1`、
`text.count("zhang") == 1`、`text.count("128") == 1`（PDF 腿：散文腿已被 pdfplumber 扣掉表框）；
每一枚表行 `lines.count(row_line) == 1`。DOCX 腿的锚里带「前文」，PDF 腿的锚里带「第2页」——两枚按格式各自的真话。

两条**不许静默**的退路（`tests/test_r540_table_sheet_offline.py` 常驻钉）：
- 表格通道塌（`extract_document` 抛 RuntimeError）→ `tables.degraded="RuntimeError: …"`、
  `attached=False`、正文退回纯散文（`| region` 不在，`Appendix B` 在），并出
  WARNING `[R304] 表格通道 退回纯正文: …`；
- 表格腿页数触顶（注入 `max_pages=1`）→ `truncated="pages:1of2"`，
  `truncated_notice` 交回「表格抽取被页数上限切断（pages:1of2）：…未走到的页为第 2-2 页」，
  WARNING `[R304] 表格预算触顶` 出声，而**正文一页字都不少**（`45600` 仍在，逐页账回补那一条腿）。

## 5. ④ 电子表格通道（#15）

```
python scripts/r540_readout.py --out %TEMP%\r540 --case xlsx,csv,csv-pad   → rc=0
```
🔴 三格读数全部来自通道自己交回的 `Spreadsheet.stats()` / `SheetReport` / `TableBlock`，
**没有一处用 pandas 重算**（两枚钉里连 `import pandas` 都没有）。

`一月销售` 那张 sheet 的三把尺（不是同一把，别读混）：

```
rows_total=7  rows_read=5  rows_kept=4  columns_total=7  columns_kept=7
blank_rows_dropped=2  empty_columns_dropped=0  spans=1  state=visible  emitted=true
```
- `rows_total` 是 openpyxl **自己声称**的维度（表头 + 4 数据 + 1 全 None 行 + 1 全空串行 = 7）；
- `rows_read=5` 是清掉两枚空行之后（`blank_rows_dropped=2`），`rows_kept=4` 才是交出去的 data 行；
- 合并单元格 `F2:F3` → `spans=1`，且被覆盖那一格取**左上角**：第 2 行 `备注` 读出 `月结`（不是空）。

逐格渲染（`blocks[0].rows`，通道交回的那一份）：

```
["SO-1001","杭州云栖科技有限公司","2026-01-05","120","0.15","月结",""]
["SO-1002","苏州工业园区某某厂","2026-01-06","77","","月结",""]      ← 折扣率 None → 空串；备注取合并左上角
["SO-1003","","2026-01-07","","0.2","现结",""]                       ← 客户名称 None → 空串
["SO-1004","上海临港装备有限公司","2026-01-08","15","0","",""]       ← 0.0 落盘成 0（openpyxl 写入侧 safe_string）
锚：r540_sales.xlsx · Sheet「一月销售」 · 表1 · 合并单元格1处 ｜ 第二枚块：… · Sheet「汇总」 · 表2
```

CSV 腿：`encoding="utf-8"`、`delimiter=","`（`summary()["delimiter"]=="comma"`）、
`rows_total=5 / rows_read=5 / rows_kept=4`、锚 `r540_sales.csv · 表1`。

**三种空白各归一把尺**（`r540_pad.csv`：表头 7 列、数据行递宽到 10 列、中间一枚空行）：

```
rows_total=4 rows_read=3 rows_kept=2 blank_rows_dropped=1
columns_total=10 columns_kept=7 empty_columns_dropped=3
header 仍是那 7 枚中文列名
```
机制现读：`spreadsheets._normalize_grid`（`app/rag/spreadsheets.py:337`）先砍超宽列、再去空行、
再去全空列，判定式是 `live = [position … if any(row[position] …)]`（`app/rag/spreadsheets.py:365`）——
`row` 含表头那一枚 ⇒ **只有表头有值的列不丢**（列名本身就是可检索的事实），连表头都空的尾随 3 列才丢。
与在册口径一致，实测复现。

一处**在册口径要分清**的：`render_value(0.0)` 交回 `"0.0"`（渲染层不做第二次取整），而 xlsx 那一格里读到 `"0"`
是 **openpyxl 写入侧**把 `0.0` 落盘成 `0`、读回来是 `int` ——两件事，钉分别钉（`test_one_value_gets_one_spelling_in_the_sheet_channel` 钉前者，`test_xlsx_cells_are_rendered_by_the_channels_own_rules` 端到端钉后者）。

接线与出口三格：

```
loader.load_document(xlsx/csv) == spreadsheets.load_spreadsheet_text(...)   → 逐字相等（两枚 True）
display_name 只改锚点第一段：客户上传的一月明细.csv · 表1，其余行逐字不变
loader.extract_document_with_reports(csv).tables.source == ""    ← 表格通道未参与（真话，不是漏账）
                                                   .pdf is None ← 非 PDF 没有逐页来源账
.xls 仍出声拒绝：ValueError（UNSUPPORTED_SUFFIXES = (".xls",)，app/rag/spreadsheets.py:135）
出口 NUL 计数 0（三枚件），R49 入索引判定 eligible=true（三枚件）
```

## 6. ⑤ 常驻钉

| 件 | 枚数 | 命令 | rc |
| --- | --- | --- | --- |
| `tests/test_r540_scan_offline.py` | 17 passed / 1 skipped | `python -m pytest tests/test_r540_scan_offline.py -o addopts= -p no:cacheprovider --basetemp=%TEMP%\r540x -q` | 0（3.8 s） |
| `tests/test_r540_table_sheet_offline.py` | 21 passed | `python -m pytest tests/test_r540_table_sheet_offline.py -o addopts= -p no:cacheprovider --basetemp=%TEMP%\r540x -q` | 0（5.0 s） |
| 两件同跑 | 38 passed / 1 skipped | `…pytest tests/test_r540_scan_offline.py tests/test_r540_table_sheet_offline.py …` | 0（6.0 s） |

钉住的面：#13 五形（`ocr` / `ocr-empty` / `ocr-degraded` ×四枚来源 / `text-layer` / `blank`）＋
判据④「送 OCR 的页码清单」＋NUL 两形（`sanitize_text` 出口与"整页只剩 NUL 不许算 ocr"）＋
引擎身份静态钉；#14 结构形状／每行恰好一次／通道塌了点名／页数触顶出声／0 表逐字退回；
#15 三把空白尺／渲染口径／分派与出口／`.xls` 拒绝／入索引闸门。

🔴 **非常驻的格子（如实列，没硬钉成假绿）**：
1. **真 `rapidocr_onnxruntime` 的耗时腿与识别质量腿**——CPU 单页 0.9–5.0 s（首枚含引擎初始化），
   这台机此刻还有 run17 在飞；绝对毫秒当了门就是 R269 那笔点名的假红。它只在
   `scripts/r540_readout.py` 现取现报（§2/§3），并另有一枚**默认 skip** 的
   `test_real_engine_reads_the_scanned_pages_end_to_end`（`R540_REAL_OCR=1` 才跑，
   本席跑过的形状：逐页 `raster_size=(1653, 2339)`、`ocr_elapsed_ms>0`、关键句在位）。
2. 栅格化像素级 DPI 线性钉（R298 在册件已经逐档钉死，本单不复制第二份）。
3. 表格/电子表格的**上限触顶真件**（5000 行、40 000 字、12 s 时间预算）——本单样本太小，
   只证「触顶会出声」那两枚注入形状，没证触顶本身的尺（R300/R305 在册件射程）。

## 7. ⑥ 反证三把（`scripts/r540_refutation.py`，逐字节还原）

```
python scripts/r540_refutation.py --out %TEMP%\r540 --knife all `
    --python C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe   → rc=0（三把全闭合）
```

| 刀 | 摘什么 | sha 前 12：摘前 → 摘后 → 还原后 | 钉的反应 |
| --- | --- | --- | --- |
| K1 | `app/rag/ocr.py` `OCR_ENGINE_MODULE` 指到不存在的模块 | `6067f2d889f0` → `e0dba4f804bb` → `6067f2d889f0` ✅ | 门 **1 failed / 16 passed / 1 skipped**：`test_the_only_allowed_engine_is_the_local_rapidocr` 红；读数腿同时改口——逐页 `[ocr-degraded ×4]`、`ocr_available=false`、降级句 `本地 OCR 引擎不可用，扫描页未识别文字：第1页：r540_engine_absent_here 未安装（import 找不到模块）；…`，WARNING 两行原文点名 |
| K2 | `app/rag/loader.py` 扫描页判定 AND → OR | `a486e44e5766` → `7301bbcbd84e` → `a486e44e5766` ✅ | 门 **3 failed / 14 passed / 1 skipped**：`test_pages_with_a_text_layer_never_reach_the_ocr_channel`／`test_a_mixed_document_records_a_source_per_page`／`test_blank_page_without_bitmap_or_text_is_named_blank` 红；读数腿 `--case control` 现取 `[ocr=2]`、`ocr_attempted=true`、耗时 5190 + 2524 ms —— 文本层页被整个重跑一遍 OCR（判据④ 点名的双份正文＋白烧 CPU） |
| K3 | `app/rag/spreadsheets.py` `CSV_SUFFIXES` 摘成空元组 | `91d3894d8b89` → `e40b4cf70a00` → `91d3894d8b89` ✅ | 门 **7 failed / 14 passed**（csv 五枚＋`index_gate[csv]`/`[pad_csv]`）；读数腿 rc=1：`ValueError: R305 表格入库不支持该格式: .csv`（`app/rag/spreadsheets.py:695`） |

三把都在还原后**立刻复跑同名件**：K1 `17 passed, 1 skipped` rc=0 ／ K2 同 rc=0 ／ K3 `21 passed` rc=0。
`git status --porcelain` 收尾只剩本单写域里那五枚新件（§8）——`app/` 无 `M`，逐字节还原成立。

## 8. 只报不改：症状与硬证（命令原文 → 读数）

**S1｜「糊到读不出」与「这页本来没字」同形，且整件可以静默归零。**

```
python scripts/r540_readout.py --out %TEMP%\r540 --case lowq-only   → rc=0
  样本 = 一页，印了 "库存周转天数 45 天" / "呆滞物料占比 3.2%"，26 px + blur 6.0 + 对比 0.45 + 噪点 26
  读数 = page_source: "ocr-empty" | page_note: "图像页 OCR 未检出文字"
         text_chars: 0 | degradation_notes: [] | WARNING 行数: 0
         index_gate: {"eligible": false, "reason": "no_text_content"}
```
同一份 `r540_scan.pdf` 的第 3 页（印了字）与第 4 页（没印字）交回**同一个** `ocr-empty` +
同一句 `图像页 OCR 未检出文字`，两条腿都没有降级句、没有 WARNING。
机制现读：`recognize()` 在 `app/rag/ocr.py:304` 处 `if not result: return "", elapsed`，
`app/rag/ocr.py:308` 取 `entry[0]/entry[1]` 而**丢 `entry[2]`（逐框置信度）**；`ocr_pages` 在
`app/rag/ocr.py:414` 把「空文本」一律记 `STATUS_EMPTY`，loader 再落成 `ocr-empty`
（`app/rag/loader.py:306-308`）。⇒ 后果：客户上传一份**整本糊**的扫描件，走到的结局是
「正文 0 字 → R49 判 `no_text_content` → 拒入索引」，屏幕上与"这本来就是空白页"无从分辨，
也没有任何一处写着「引擎在位、图看过了、一个字没读出来」。
🔴 本单不改（`app/rag/**` 禁域）。要治的方向只提一句、不开方：`ocr-empty` 内部至少分得出
「检出了框但读空」与「连框都没有」——那是两句话。

**S2｜在册那句「四档逐字相同」今天只成立一半**（详见 §3 的五档复测）。
影响面不是正确性而是**运维口径**：`DOCUMENT_OCR_DPI` 跨族（{72,100} ↔ {200+}）改档 ⇒ 同一页字面变 ⇒
重算时正文 hash 变，属"重刷索引"级别的动作，而 `app/rag/ocr.py:59-64` 现在读起来像"随便调"。

**S3｜`.xlsx`/`.docx` 样本 sha 不可复算（ZIP 时间戳）**，见 §1 表末两行。
对本单无影响（凭据落在发生器代码上），但谁把这两枚的 sha 当复算凭据就是假话——纸上先记。

## 9. 没验的格子（明确空着，不猜）

1. **真上传链路**（`app/api/v1/chat.py` 的白名单／`inspect_upload_header`／落盘命名／
   `display_name` 那处刻意的不对称）——本单一字节没碰 HTTP 层，`chat.py` 也不在写域。
2. **OCR 文本真的进了向量库**——不写库、不动容器，所以「索引里有字」今天只证到
   R49 纯函数判 `eligible=true` 那一格；PGVector 那一腿（`pg_store` 落 1008+ 枚向量后的命中）未测。
3. **检索命中**：没有 embed、没有 retriever 调用，"扫描件里的句子问得出来"仍是**未验**。
4. **扫描件里的表格**：`loader.extract_pdf_with_tables` 的在册边界（整页扫描件无矢量框线 ⇒ 表数为 0）
   今天**没有**被一枚真样本考过——我的表格件是数字 PDF。这一格既没验也没推翻。
5. **规模腿**：80 页 OCR 上限、400 页表格上限、40 000 字预算、12 s 时间预算的**真件**触顶行为；
   600 DPI 的内存峰值（`MAX_OCR_DPI`，`ocr.py:78`）——一台正在跑评测的机器不该造这个。
6. **客户机分布外推**：样本文字是我造的（`msyh.ttc` 渲染、干净背景），不是客户扫描件的噪声／歪斜／
   双面透印分布。§2 那两个 `ocr` 页读得准，**不能**外推成"客户扫描件读得准"。
7. `documents/` 那 12 枚真件的 OCR 通道：本单样本零上传零写库，没去碰那批语料（避免与本单
   「不打模型、不动容器」之外的窗内禁忌混淆），留作总控另裁。

## 10. 交回盘面

```
git -C C:\Users\fengx\PycharmProjects\企业智脑 worktree add -b codex/be-r540 `
    C:\Users\fengx\PycharmProjects\be-r540 a5ba2d7                       → HEAD a5ba2d7
cd C:\Users\fengx\PycharmProjects\be-r540; git status --porcelain         → 五枚 ??，零 M，零 D
git diff --numstat a5ba2d7                                                → 空（未 commit，规矩：执行层不 commit）
```

| 新件 | 行数（CRLF 计） | sha256 前 12 | 行尾自证 |
| --- | --- | --- | --- |
| `scripts/r540_samples.py` | 430 | `afd7ce21548f` | `count(\r)==count(\n)==count(\r\n)`＝430，裸 CR 0，孤立 LF 0，无 BOM |
| `scripts/r540_readout.py` | 534 | `db163383e7a9` | 同上（534/534/534），无 BOM |
| `scripts/r540_refutation.py` | 173 | `9619582ccdd2` | 同上（173/173/173），无 BOM |
| `tests/test_r540_scan_offline.py` | 344 | `e5f7fd5be714` | 同上（344/344/344），无 BOM |
| `tests/test_r540_table_sheet_offline.py` | 335 | `c172593aa67d` | 同上（335/335/335），无 BOM |
| `docs/testing/r540-v2-channels-e2e.md` | 358 | 不自记（改一行就变一枚） | 同上（358/358/358），无 BOM |

写域自检：只新建了 `scripts/r540_*.py` 三枚、`tests/test_r540_*.py` 两枚与本纸；
`app/**`、`frontend/**`、`tests/fixtures/**`（一字节）、`tests/conftest.py`、`docs/handoff/**`、
`deploy/**`、`migrations/**`、`.gitignore`、`chroma_db/**` 全部零改动。
样本与读数 JSON 全在 `%TEMP%\r540\`，仓里没有二进制。