# V2 文件解析功能线 —— 交付报告

- 日期：2026-09-28
- 分支：`codex/partner-document-ingestion`
- PR：https://github.com/jfuyiugvuihj/enterprise-brain/pull/1
- 范围：V2 文件解析（统一解析契约 / OCR / 表格 / Excel-CSV 知识库导入）

## 1. 子功能单独提交

| 子功能 | 提交 |
|---|---|
| 统一解析结果契约（含 errors 汇总字段） | `ca66431`、`2866774` |
| OCR 可替换适配层与扫描 PDF 检测 | `4e64ac0` |
| PDF/Word 表格结构化解析 | `227522f` |
| Excel/CSV 知识库最小导入模式 | `d1ef3ac` |
| 统一 `parse_document` 入口（保持旧 loader 兼容） | `8462e9b` |
| 依赖声明 + 解析文档 + 接线契约 | `ab7866c`、`dd032a3` |
| 基线同步（非功能提交） | `d7f02b1` |

## 2. 新增测试覆盖

| 要求 | 覆盖测试 |
|---|---|
| 普通 PDF 回归 | `tests/test_parse_document_integration.py` |
| 扫描 PDF | `tests/test_scanned_pdf_detection.py` |
| OCR 失败 / 低置信度 | `tests/test_ocr_adapter_and_failures.py` |
| 表格保留结构 | `tests/test_table_parser.py` |
| Excel 工作表与来源信息 | `tests/test_excel_csv_kb_import.py` |
| 契约本身 | `tests/test_parser_result_contract.py` |

## 3. 实际修改文件

新增：

- `app/rag/parser_result.py`
- `app/rag/ocr/`（base / registry / engines / detect / pdf_ocr / __init__）
- `app/rag/table_parser.py`
- `app/rag/excel_kb_parser.py`
- `docs/parsing/v2-parser-result-and-wiring-contract.md`
- `tests/` 下 6 个新测试文件

修改：

- `app/rag/loader.py`（仅追加 `parse_document` 等新入口，旧 `load_*` / `load_document` 未改）
- `pyproject.toml`（新增 `pdfplumber>=0.11`）

未触碰：`frontend/`、`app/api/v1/chat.py`、`app/agents/`、`app/rag/retriever.py`、`app/rag/indexing.py`、`migrations/`、数据库、`documents/`、`chroma_db/`。

## 4. 测试结果

- 本功能 6 个测试文件：`48 passed`（在项目 `.venv` 中带仓库 conftest 运行）
- 既有 loader 回归 `tests/test_file_upload_security.py`：`111 passed`

## 5. 未完成项

- 未接入上传 API / 索引 / 白名单 / 前端 / 数据库
- `uv.lock` 未重生成（本机访问清华 PyPI 源 403；见 `v2-parser-result-and-wiring-contract.md` 第 9 节）
- 真实 OCR 引擎未集成；PDF 页光栅化（`render_page`）未实现
- 未跑真实 OCR 模型、真实库与索引链路

## 6. 依赖与部署注意

- 新增运行时依赖仅 `pdfplumber`（离线纯库，无模型下载）
- OCR 引擎可替换、默认不注册、缺失即失败；Tesseract 为可选适配器，文档已写体积/许可证/语言包/离线部署方式
- PDF 光栅化与真实 OCR 引擎属总控接线边界

## 7. 完成度口径

- ✅ 模块实现完成
- ✅ 测试完成
- ❌ 已接入系统入口
- ❌ 真实环境验收完成

本线交付的是 V2 文件解析的模块实现，不等于整条产品链路完成，等待总控复核与集成。
