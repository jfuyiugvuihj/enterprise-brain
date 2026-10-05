# R687 · V2「Excel/CSV 知识库模式」：`/upload-excel` 那份表格必须同时成为知识库文档（一条文件两条命）

**性质**：V2 单（不是 V1 欠账）。**基点**：开工时现取主树 HEAD。**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。

## 现取盘面（总控 10-05 亲验，别照旧账写「未做」）

- 知识库上传白名单里 `.xlsx`／`.csv` **已经在**（R306 落的那半：`app/documents/file_security.py` 顶部注释写明它们由 `app/rag/spreadsheets.py` 读，走文档上传口就是知识库文档）。所以计划书 §8 那句「未做」**只对了一半**，交付里必须按下面两格分别判，不许笼统写「已做／未做」。
- 🔴 真缺的是 `/upload-excel` 那一口：`app/api/v1/data.py::upload_excel` 只做 `_safe_data_filename` → 落盘 → `load_excel` → `dataset_registry.register` → 回数据画像与 `dataset_id`／`owner_id`，**一步都不碰知识库**（不建 catalog 行、不切片、不向量入库）。⇒ 客户从数据口传上来的表格，检索腿永远看不见它。
- `.xls` 仍**故意不收**（白名单注释点名 openpyxl 读不了旧二进制、`xlrd` 不是本仓直接依赖）——本单不许顺手加 `.xls`，那是另一枚单的事。

## 判据（每条都可失败，缺一枚判负）

1. **两条命成立**：同一份经 `/upload-excel` 上传成功的表格，必须能在知识库目录里被现取查到（一枚 catalog 行），且其内容能进检索结果；判据用行为证——上传→（离线腿）检索该表里的一个独有串→命中那一枚文档。改前该钉必须当场红。
2. **零复制**：不许把字节抄进第二处目录——知识库与数据集必须指同一份落盘文件（凭 catalog 里的路径字段现取相等）；🔴 也不许为了「进索引」把同一文件写两行 catalog。
3. **数据集语义一格不许变**：`/upload-excel` 现有响应字段（`dataset_id`／`version_id`／`owner_id`／画像）与 409 `dataset_filename_conflict`、400 稳定码＋下一步、403 owner-scope 三道的形状必须逐字段不变；加一枚钉断言「新增知识库那一腿的失败**不许**把已经成功的数据集注册回滚掉」（部分成功必须可归因，不许 500）。
4. **向量腿走生产口径**：入库必须走 PGVector 在册写点，🔴 **不得新增任何 Chroma 依赖或新的 Chroma 写点**（AGENTS.md 技术栈那条是硬规矩）；若某支写点绕不开遗留件，停下写进交付由总控裁。
5. **权限同源**：知识库那一行的可见性必须复用现有 owner／department／classification 判定（不许新写一套权限分支）；C 门那格（生产标签全空）不在本单判达范围内，交付里照抄「未验」。
6. 两态同名件（不是全量门）：本单新钉＋`tests/test_r306_*`／`tests/test_r337_*`／spreadsheets 族在册件；窗内禁跑 ⇒ 标 `NOT_RUN_IN_WINDOW` 交回总控窗后补跑。
7. 契约缺口**只报不改**：本单会让 `/upload-excel` 多一个可观察行为，`docs/api/contract-v1.md` 属禁区——交付里逐枚列出需要补的契约行（原文级），由总控落账（R681 契约生成化之后才谈得上由生成器管）。

## 写域（只许这些）

`app/api/v1/data.py`（`upload_excel` 那一支）／`app/documents/`（catalog 行与同源 helper）／`app/rag/spreadsheets.py`（只读复用，除非确需暴露一个函数）／新增 `tests/test_r687_*.py`／`docs/tickets/R687-*.md`／新凭据纸 `docs/testing/r687-<今天>.md`

## 禁区（踩线即退回）

`docs/api/contract-v1.md`／`app/api/v1/chat.py`／`app/agents/**`／`frontend/**`／`docs/handoff/**`／评测夹具与 `tests/test_evaluation_report.py`／`scripts/run_gate.py`／`pyproject.toml`（不许新增依赖）／`deploy/**`／`chroma_db/**`／容器与镜像动作／主树任何路径。
