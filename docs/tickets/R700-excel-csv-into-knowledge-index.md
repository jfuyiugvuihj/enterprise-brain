# R700 · Excel／CSV 并进知识库索引（V2 表里唯一一枚「未做」，不许再造第二套入库腿）

**号**：R700　**基点**＝派工那一刻主树 HEAD 现取（由派工指针词带）　**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。

## 现取病形（总控 10-06 13:4x 亲读，不是转述）

- `app/documents/file_security.py` 顶部注释自己写着：`POST /api/v1/upload-excel is still a separate route with its own filename, permission and conflict rules, and it does not read this dict`——同一份文件表上另写了一句「these are knowledge-base documents as well as datasets」，于是 Excel 既算知识又算数据集，**入库这条腿却只走数据集那一半**。
- 路由在 `app/api/v1/data.py::upload_excel`；`app/rag/loader.py` 现取只有 R304 那条 PDF／DOCX 表格腿（`from app.rag import tables as table_channel`），没有 xlsx／csv 进知识库的路径。
- `.xls` 是**故意不做**：openpyxl 读不了遗留二进制，`xlrd` 不在本仓依赖里。这一句必须原样保留在交付里，🔴 不许为过判据偷偷加依赖（依赖变动属业主侧）。
- 🔴 顺带纠一笔账面假账（不要照抄路线图）：`docs/version-roadmap-and-requirements-2026-10-05.md` §8 把「PDF/Word 表格解析」记成「半／端到端待接线（R300 `72a9bdc`）」——**这行过期了**：R304 已并树 `9344028`（「R300 那份模块＋契约从今天起端到端生效」），在册件 `tests/test_r300_tables.py`（43 枚）与 r304 专名件（25 枚）都跑过。本单**不许**去补那半格，那是账要改，不是码要写。

## 判据（每条可失败，缺一枚判负）

1. **真进知识库**：`POST /api/v1/upload-excel` 收下的 xlsx／csv，落库后必须能被既有检索腿命中——用一次性夹具造一份两列表（表头＋≥3 行），走路由入库，再用在册检索出口按表头词与某一行的值各查一次，两查都必须交出该文档的块。🔴 入库只许复用既有那条腿；**新代码一律不得新增 Chroma 依赖或新的 Chroma 写点**（AGENTS.md 技术栈定案：生产向量库＝PGVector，Chroma 是退役中的遗留件）。写点若必须落在 `app/rag/retrieval_pipeline.py`，停下回报，不许跨席写。
2. **边界统一**：文件名／权限／冲突三件事并进 `app/documents/file_security.py` 那本字典（就是「does not read this dict」那一句的治法），并进之后 `upload_excel` 的**响应形状与状态码不破**——`frontend/src/components/DataPanel.vue` 现在就在调这一枚，不许改 `frontend/**` 任何文件来迁就后端。
3. **表格通道不复制**：xlsx／csv 的表格→正文必须复用 `app/rag/tables.py` 既有出口（在册 `TableBlock`／`TableSet`／`DocumentTables`），🔴 不许写第二套「平行实现」；若复用做不到，停下交回并写明差在哪一环。
4. **牙**：新增 `tests/test_r700_*.py` 至少四枚——①判据 1 的端到端命中；②同名冲突与越权两形必须红（摘掉边界检查即红）；③「不许新增 Chroma 写点」的棘轮钉（沿用在册 `tests/test_r238_bare_connect_ratchet.py` 那一族的形状，扫本单新文件）；④`.xls` 明确拒绝并给出可读原因码——把 `.xls` 放进允许名册必须让这枚钉红。
5. **零外部请求与零新依赖**：解析全走本仓既有依赖；`pyproject.toml`／`uv.lock` 一字节不许动，交付里自证（`git diff --numstat` 对这两枚交回空）。
6. **交付**：同名件两态读数（dirty／commit 后各一遍，清单逐枚相同）＋`git rev-list --count <基点>..HEAD`＋未跟踪逐枚点名＋控制符 00/07/08/0b/0c 各 0 枚＋坐标一律 `文件::符号`（禁 `文件:数字`）＋凭据纸 `docs/testing/r700-<开工日>.md`＋`python scripts/tickets_index.py --verify` rc=0。
7. 🔴 **这一格翻绿只算 V2**：V1 九格与五道门不由本单变动，交付里不许出现「V1 因此更近一步」这种话；真机检索那一半若要动容器或模型，属总控窗口，本单离线自证即可。

## 写域（只许这些）

`app/api/v1/data.py`／`app/documents/**`／`app/rag/loader.py`（仅当取证证明必须，且不得碰 R304 那条腿的既有语义）／新增 `tests/test_r700_*.py`／`docs/tickets/R700-*.md`／`docs/testing/r700-<开工日>.md`

## 禁区（踩线即退回）

`app/api/v1/chat.py`／`app/trace/spans.py`／`app/rag/retrieval_pipeline.py`／`app/common/model_handler.py`／`app/common/stage_timing.py`（在飞席 R695 写域）／`app/agents/contracts.py`／`app/agents/evidence.py`／`app/agents/nodes.py`（在飞席 R699 写域）／`frontend/**`／`app/quality/**`（判分器）／评测夹具／`docs/handoff/**`／`docs/api/contract-v1.md`／`docs/version-roadmap-and-requirements-2026-10-05.md`／`scripts/run_gate.py`／`pyproject.toml`／`uv.lock`／`docs/tickets/index.tsv`／容器·镜像·模型动作／主树任何路径。

## 这一枚为什么存在

V2 表里「未做」只剩这一格，而它的病形在源码注释里写得很清楚——不是不知道要做啥，是一直被更急的窗挤着没人动。趁今晚窗口在跑之外的空档把它吃掉。