# V2 文件解析：统一结果契约、OCR/表格/Excel 最小导入与接线契约

版本：2026-09-23
分支：`codex/partner-document-ingestion`
范围：`app/rag/loader.py` + `app/rag/parser_result.py` + `app/rag/ocr/` +
`app/rag/table_parser.py` + `app/rag/excel_kb_parser.py` + 对应测试 + 依赖声明。
**本线只交付“模块实现完成 + 测试完成”，未接入上传 API / 索引 / 前端 / 数据库。**

## 1. 为什么要这个契约

旧 `app/rag/loader.py` 的所有函数都返回 `str`，能表达“正文”，但无法表达页码、
工作表、行列关系、OCR 置信度、失败原因。`docs/current-functionality-2026-09-10.md`
§6.2.1 要求先建立统一解析结果模型，再扩展各解析器。本线按此落地：

```text
原始文件 -> parse_document -> DocumentParseResult
  -> ContentBlock（text / table / ocr / data_rows）
  -> SourceLocation（文件/版本/页码/工作表/表格/行列范围）+ ParseError + confidence
  -> plain_text（兼容旧行为） 与 to_index_text（带来源定位的索引表示）
```

## 2. 统一结果结构（`app/rag/parser_result.py`）

| 类型 | 值 | 含义 |
|---|---|---|
| `ParseStatus` | `success` / `partial_success` / `empty` / `failed` | 整份文件的解析状态；`empty` 与 `failed` 不混用 |
| `ParserType` | `pypdf` / `python_docx` / `olefile` / `text_encoding` / `markdown` / `ocr` / `pdf_table` / `docx_table` / `excel_kb` / `csv_kb` | 产出某块的解析器 |
| `BlockType` | `text` / `table` / `ocr` / `data_rows` | 块的语义类型；`table` 与 `data_rows` 保留行列结构 |
| `SourceLocation` | file_path / page / sheet / table_index / row_start..column_end / section_path | 来源定位，字段按解析器已知粒度可选 |
| `ParseError` | code / message / parser / location / retryable | 稳定错误码 + 人类可读原因 + 是否可重试 |
| `ContentBlock` | block_type / parser_type / content(文本) 或 header+rows(结构化) / location / confidence / errors | 单块产物 |
| `DocumentParseResult` | source / extension / status / blocks / parsers / failure_reason / warnings / errors / metadata | 聚合结果；`plain_text` 与 `to_index_text()` 两种输出 |

不变量：

- `plain_text` 只拼接 `text`/`ocr` 块，**绝不把表格拼成散文**。
- `to_index_text()` 对每个块加 `[位置]` 前缀（例如 `[sheet=Sales rows=2-3 cols=1-2]`），
  单元格内的制表符与换行被替换，避免表格内容注入假行列。
- `failed` 必须有 `failure_reason`；OCR 失败/空页/低置信度都保留稳定 `code`，
  不会静默降级为 `empty`。

## 3. 新入口与兼容保证（`app/rag/loader.py`）

- 旧函数 `load_pdf/load_docx/load_doc/load_txt/load_md/load_document` **一字未改**，
  上传 API、预览与既有测试不受影响。
- 新入口 `parse_document(path, *, include_tables=True, include_ocr=False,
  ocr_engine=None, render_page=None, confidence_threshold=None, max_rows_per_sheet=1000)`：
  - `.pdf`：逐页文本块 + 可选表格块 + 可选 OCR 块；
  - `.docx`：段落文本块 + 可选表格块；
  - `.doc/.txt/.md`：单个文本块，`plain_text` 与旧函数一致；
  - `.xlsx/.xls/.csv`：知识库最小导入块；
  - 未知扩展名仍抛 `Unsupported file format: {ext}`。

## 4. OCR 适配层（`app/rag/ocr/`）

- `base.OcrEngine`：`name` + `recognize(image: bytes, page: int) -> OcrPageResult`。
- `registry`：`register_engine / get_engine / available_engines`；**默认不注册任何引擎**，
  未配置时 `get_engine()` 抛 `OcrEngineUnavailable`，防止用假 OCR 文本冒充结果。
- `detect`：只有“无可复制文本且含图片”的页才判定为扫描页；纯空白页不进 OCR。
- `pdf_ocr`：把扫描页渲染字节交给引擎，产出带页码/置信度/错误码的 `OcrRun`；
  引擎异常 -> `ocr_engine_error`，空结果 -> `ocr_empty_page`，低于阈值 ->
  `ocr_low_confidence`（保留文本 + 告警，状态 `partial_success`）。
- 内置引擎：
  - `StubOcrEngine`：确定性离线测试替身，**只用于测试**。
  - `TesseractOcrEngine`：真实引擎适配示例，懒加载 `pytesseract`/`Pillow`，
    缺依赖时抛带部署说明的 `OcrEngineUnavailable`。

### 4.1 OCR 部署与依赖说明

| 方案 | 体积/依赖 | 许可证 | 是否需要额外模型/数据 | 离线部署方式 |
|---|---|---|---|---|
| Tesseract（推荐先验证） | 系统二进制（Windows/macOS/Linux），加 `pytesseract`、`Pillow` 两个 pip 包 | Apache-2.0（Tesseract）；pytesseract Apache-2.0 | 需要对应语言训练数据（默认英文内置；中文需 `chi_sim.traineddata`，约 10-40MB，可离线放入 tessdata 目录） | 二进制 + 语言包随安装包/镜像预置，识别时不联网 |
| 仓库既有 `langchain-mineru` | 依赖多且重，默认可能触发模型下载 | 以组件许可证为准 | 需要 MinerU 模型权重 | 需预下载权重并配置离线路径；本线未使用，避免测试时联网下载 |
| 其他（PaddleOCR 等） | 体积更大 | 以组件许可证为准 | 需要模型权重 | 同“预下载 + 离线路径” |

**本线测试只使用 `StubOcrEngine`，不下载任何模型。** 生产接入前由总控确定真实引擎
并把引擎/渲染器注入 `parse_document`。

### 4.2 OCR 渲染边界（需要总控接线）

`pdf_ocr.ocr_scanned_pages` 接收 `render_page(page_number) -> bytes`。本线**不实现
PDF 光栅化**（poppler/pypdfium2），避免引入系统级依赖。接线方需提供一个渲染器；
未提供渲染器时 OCR 显式报 `ocr_renderer_missing`，不会静默跳过。

## 5. PDF/Word 表格（`app/rag/table_parser.py`）

- DOCX：`python-docx` 读 `document.tables`，逐表输出 `table` 块，`table_index` 定位。
- PDF：`pdfplumber` 逐页 `extract_tables()`，保留页码 + 表序号。
- 打开失败 -> `failed` + `*_table_open_failed`；单页失败 -> `partial_success` +
  `pdf_table_page_failed`。无表 -> `empty`（正文仍由文本解析处理）。

## 6. Excel/CSV 知识库最小导入（`app/rag/excel_kb_parser.py`）

- **与经营分析链隔离**：不改 `app/tools/excel.py` / `app/api/v1/data.py`。
- 最小导入模式：每个工作表/每个 CSV 一个 `data_rows` 块 = 表头 + 数据行，块内
  `location` 记录 sheet / row_start / row_end / column_start..end / file_path。
- `max_rows_per_sheet`（默认 1000）显式限流；截断时返回 `partial_success` 并把
  `metadata["sheet_rows"]` 记录真实行数，告警写清“导入了 X / Y 行”，**不静默丢行**。
- `.xlsx` 用 `openpyxl(data_only=True, read_only=True)` 取公式缓存结果；`.csv` 用
  标准库 `csv`，编码探测 utf-8/gbk/gb2312；`.xls` 在本线知识库模式明确返回失败
  （openpyxl 不支持旧二进制格式），不做静默降级。

### 6.1 索引文本表示

索引方应逐块/逐行消费，不要整本 dump：

- 文本块：`block.content`。
- 表格/数据行块：`render_block_for_index(block)`，形如
  `[sheet=Sales rows=2-3 cols=1-2]\nheader行\n数据行1\n数据行2`。
- OCR 低置信度块保留文本但携带 `ocr_low_confidence`，索引方应标记为“需复核”。

## 7. 总控接线契约（本线未做，需另派写集）

1. **上传 API（`app/api/v1/chat.py`，禁止本线修改）**
   - 用 `parse_document(...)` 替换 `load_document(...)`，把
     `DocumentParseResult.as_dict()` 存入版本记录，把 `status` 映射到现有
     `parse_status`（`success/partial_success/empty/failed`），并保存
     `warnings`/`errors` 供前端展示。
   - 知识库上传白名单（`app/documents/file_security.py`）如需放行 `.xlsx/.xls/.csv`，
     需总控另派写集，并明确“知识库导入”与“经营数据分析”两种模式选择。
2. **索引（`app/rag/indexing.py` / `retriever.py`，禁止本线修改）**
   - 消费 `blocks` 与 `render_block_for_index`，按块/行切分后再向量化；
   - chunk 元数据写入 `page/sheet/table_index/row_start/row_end` 等定位字段；
   - OCR 低置信度块进入索引但附加“需人工复核”标记。
3. **渲染器注入**：由总控提供 `render_page` 给 `parse_document(include_ocr=True)`。
4. **引擎注册**：启动时 `register_engine(真实引擎, default=True)`，未注册即失败。

## 8. 交付口径

- ✅ 模块实现完成：契约、OCR 适配层、表格解析、Excel/CSV 最小导入、统一入口。
- ✅ 测试完成：`pytest --noconftest` 下 6 个新测试文件共 48 例通过（本机 Python 3.13）。
- ❌ 已接入系统入口：未接入（上传 API / 索引 / 白名单 / 前端均未改）。
- ❌ 真实环境验收：未做（未运行真实 OCR 模型、未跑真实数据库与索引链路）。

## 9. 依赖与锁文件注意

- `pyproject.toml` 已声明 `pdfplumber>=0.11`（离线纯库，无模型下载）。
- `uv.lock` 未随本次改动重新生成：本机访问项目锁定的清华 PyPI 源返回 403，
  为避免把整份锁文件的 registry 从清华源整体改写为 PyPI.org（会造成数千行无关 diff），
  未在本地执行 `uv lock`。集成方在可访问清华源的机器上执行 `uv lock`（或 `uv sync`）
  把 `pdfplumber` 与 `pdfminer-six` 写入锁文件即可；在此之前代码对 `pdfplumber` 为懒加载，
  缺失时会明确报错而非静默降级。
