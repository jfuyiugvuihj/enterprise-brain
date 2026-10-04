# R387 · 生产标签从源头到落库的取证，与修法判据（2026-09-27）

> 一句话结论：**部门这条腿今天在真库上没有第二本账可赖 —— `chunk_vectors` 的 1008 枚 `department` 全 `''`、`classification` 全 `1`，而这不是"复制环节写坏了"，是"上传人自己就没有部门"**：真值的第一处丢失在服务端覆盖那一句（`app/api/v1/chat.py:4088`），而它覆盖上去的那枚值来自 `users.department`，生产三枚账号里只有 `dataowner` 有部门、且不走来上传文档的那枚口（`admin` / `evalbot` 都是 SQL NULL）。⇒ 验收 C 那句"越权 0 条"是**空集意义上成立**，本单把它改写成一条今天会红的判据，并留下两枚常驻钉。

本单性质：**取证 + 定案，生产码零写入**。交付三件工具（只读）、两枚钉件（含一枚今天必须红的）、这份文档。

---

## 0. 取证边界与复现口径

| 项 | 口径 |
|---|---|
| 基点 | `be-r387@b498c88`，开工 dirty=0，收工 tracked 零改动（`git diff --numstat b498c88` 空输出） |
| 生产库 | 容器 `enterprise-brain-postgres-1`，库 `enterprise_brain`，会话先压 `SET default_transaction_read_only = on`，并当场验 `SHOW transaction_read_only` = `on`、`CREATE TABLE` 被拒（`cannot execute CREATE TABLE in a read-only transaction`） |
| 遗留引擎 | `/app/chroma_db/chroma.sqlite3` 走 `sqlite3` 的 `file:…?mode=ro` + `PRAGMA query_only`=1；🔴 **不走 `chromadb.PersistentClient`**（它会推进遗留卷的 mtime/WAL，AGENTS.md 明令不得新增 Chroma 写点，本单一条都没造） |
| 沙盒 | `eb_r59_sandbox` 只读量了一遍分布，没写 |
| DSN / 密码 | 一个字都不进本文档、不进回执、不进任何文件；读生产一律走 `docker exec … psql` 的容器内本机认证 |
| 容器手法 | `docker run`（非 `compose run`）+ `--network enterprise-brain_default` + `/app/.venv/bin/python`；挂载走 `C:\Users\fengx\AppData\Local\Temp\r387`（不含中文） |
| 没做的事 | 不起服务、不打大模型、不开评测窗口、不跑全量回归门、不 commit |

现场踩到并已登记的两侧不一致（不属本单缺陷，但会误导下一个取证的人）：

- `docker run` 取 R382 在册的那枚在跑镜像 `256cb9a65fc3` 已经拉不到（`No such image`，它是悬空层）；本机今天能 `run` 的是 `enterprise-brain:local`（`09c204241d9b`）。⇒ 本单的容器读数一律走 `docker exec` 进**正在跑**的那枚容器，避免把镜像账读成运行账。
- `--env-file deploy\.env.server` 传给 `docker run` 时 `DATABASE_URL` 不做 compose 变量替换，直连会 `password authentication failed`。⇒ 要连库就用 `docker exec -i enterprise-brain-postgres-1 psql`，别在 `docker run` 里重造这条腿。

---

## 1. 判据①：血缘链逐跳行号表（按锚点现读派生，不是抄来的字面量）

`kind` 三取一：**真值** = 这一跳确实搬运调用方给的值；**默认值兜底** = 这一跳只是把上游的空值原样接住；**硬编** = 这一跳把上游的值覆盖掉。

🔴 **本表的行号不是手抄的，是派生的**：`scripts/r387_label_lineage.py` 里每一格配一枚锚块（若干行原文，
语义就是 `rg -F`：逐行 strip 后连续固定串匹配，且必须在整个被引文件里**恰枚一枚**命中），表里的数由它在运行时
现读生成 —— 重落地跑 `python scripts/r387_label_lineage.py --emit-doc-cells`，**不许手改这张表**。
`chat.py` 再被并树撑长时，本表跟着走、不需要人回来改；锚块一旦不再唯一（那一格被删、被改名、或被人插了一段
长得像的代码），`tests/test_r387_label_ruler_teeth.py` 会自己红并端出「表里印 X、现读 Y」与差了几格。
本表之下的正文里，一枚行号只有**三种身份**，逐枚当场可判——不留「整片都是历史账」这种可以被人当挡箭牌的口径：
 甲（**当下声称**）＝同一行、或同一表格列的表头，带着「现读」字样且说的是此刻盘上源码的坐标（§3 方案 A 那一格、
   §8.7 凭据那一格、§9.3 最后一列）。这类坐标只许取自 `--emit-doc-cells`／`resolve_site` 的成品串，并且每一格都必须
   有一枚常驻钉拿着它跟现场派生值对账：§1 表＝teeth，§9.3 最后一列＝R492，表外正文的单点声称＝R490。
   🔴 写不出这枚钉，就不许写「现读」两个字。
   R493 收口一笔：无主区段里那种「自称现读、又对不上派生值」的坐标本来逐枚得在册（欠账名单在 `test_r492_live_claim_boundary.py`，
   键＝节号＋文件、不含坐标），那本账今天**清零**——唯一在册的一枚（§9.6 的 `chat_ask_entry` 那一行）已按乙案降回丙类（§9.8）。
   此后每一枚甲类坐标都必须对得上派生值，一处豁免都不剩；名单机制不退役：它仍只许变短、不许变长，账外新长一枚即红。
 乙（**成对叙述**）＝同一句里「旧 ／ 新」两枚标号同时夹着坐标（§8.7 那次重锚留下的账）。
 丙（**历史操作账**）＝记的是当时那一次的读数与动作（§8.7 漂移账、§9.4 与 §9.6 的派工词对照账、已交回的旧读数）。
乙丙两格原样留档、不随并树更新 ⇒ 要今天的坐标看 §1 那张表或 §9.3 最后一列，别拿它们当现读。

| # | 这一跳是什么 | 站点（现读行号） | 载体 | 性质 |
|---|---|---|---|---|
| 1 | 接口收到什么 | `app/api/v1/chat.py:4506-4508` | `upload_document(file, classification=Form(1), department=Form(""))` | 默认值兜底 |
| 2 | **服务端立刻丢掉客户端那一格** | `app/api/v1/chat.py:4524` | `department = str(getattr(principal, "department", "") or "")` | **硬编覆盖** |
| 3 | 主体的部门从哪来 | `app/common/authorization.py:34` → `app/agents/contracts.py:39` | `Principal.department = str(user.get("department") or "")` | 默认值兜底 |
| 4 | **账号的部门又是谁写的** | `app/common/auth.py:434-442`、`:445-464` | `_bootstrap_admin_department() = os.getenv("AUTH_DEPARTMENT", "")` → `INSERT INTO users(…, department)` | 默认值兜底（断点） |
| 5 | `classification` 走的是另一条路 | `app/api/v1/chat.py:4507` → `:4652` / `:4666` / `:4680` / `:4755` | 形参原样下传，**没有被覆盖** | 真值 |
| 6 | 目录行（逻辑文档） | `app/api/v1/chat.py:4080-4164` → `:1124-1159`（`:1142` / `:1153`） | `INSERT INTO documents(filename, classification, department, …)`，`department or None` | 默认值兜底 |
| 7 | 目录行（版本） | `app/documents/catalog.py:626-655`、`:695-769`（`:647` / `:746-748` / `:762`） | `_record_uploaded_version` → `record_document_version` → `INSERT INTO document_versions(…, department, …)` | 默认值兜底 |
| 8 | 索引载体 | `app/api/v1/chat.py:4211-4259` → `app/rag/indexing.py:938-939`、`:990-999` | `DocumentIndexPublication(classification=…, department=…)` → `scope_metadata()` | 默认值兜底 |
| 9 | `chunks` 表（发布账） | `app/rag/indexing.py:1001-1018`、`:1275` | `IndexChunk.metadata = scope_metadata()` | 默认值兜底 |
| 10 | 遗留引擎元数据（今天仍在服务的读路径） | `app/api/v1/chat.py:4648-4654` → `app/rag/retriever.py:1639-1640`、`:1683-1687` | `add_document(…, department` 或 `None)` → `"department": department or ""` | 默认值兜底 |
| 11 | `chunk_vectors.department` 是谁写的那一格 | `app/rag/pg_store.py:305-404`（`:373`）→ `:87-99` | `str(values.get("department") or "")`，`values` = **第 10 跳那份元数据** | 默认值兜底 |
| 12 | 读侧谓词（越权判定的出处） | `app/rag/filters.py:130-145` → `app/rag/pg_store.py:705-790`（`:738-740`） | `{"$and": [classification $in …, department $in …]}` → `sql_scope_filter` | 真值 |

**第一个把真值丢掉的那一跳 = 第 2 跳（`app/api/v1/chat.py` 旧 `:4511`→派生今值 `:4524`，R551 `62c8973` 把这一带顶下 12 行，站点语义一字未动）。** 严格说它丢的是"客户端自报值"，而那本来就该丢（理由在 `app/api/v1/chat.py` 旧 `:4503-4507`→派生今值 `:4516-4520` 的 docstring 与 `frontend/src/components/DocPanel.vue:647-648`：检索按【来问的人】的部门匹配文档，放客户端挑部门等于允许往别人的结果里投稿）。所以这条链上**真正的断点在第 4 跳**：`:4088` 覆盖上去的那枚值，源头是 `users.department`，而那枚列在生产上是 `NULL`。

三格要说清的细节：

- **`department` 与 `classification` 不同命。** `classification` 一路是"真值搬运"（第 5 跳），`department` 一路是"服务端替主体作答"（第 2 跳）。密级今天全 = 1 不是通路坏了 —— `R313` 起前端真的把它发出去（`DocPanel.vue:649-650`）—— 而是**这 1008 枚早于 R313，或出自不带这一格的通路**（`upload_all.py` / `scripts/seed_workspace.py`）。通路是通的，从没被真值喂过。
- **空值在同一趟里换了两种写法**：`chat.py:1153` 落 `None`、`catalog.py:647` 落 `""`、`catalog.py:762` 又落 `None`、`retriever.py:1685` 落 `""`、`pg_store.py:373` 落 `""`。第 11 跳因此只能"跟着空"，不能"救回来"。
- **第 12 跳决定了这件事的严重性**：`filters.py:135-139` 对没有部门的非管理员主体直接 raise；`filters.py:119-128` 对管理员**根本不发部门谓词**（`departments=None`）；`pg_store.py:738-740` 对 `$in` 里出现空串**拒答不猜**。⇒ 生产上部门这条腿今天有三种形态：对管理员无约束、对无部门账号是拒答、对有部门账号是恒空集 —— 三种都**不是**"部门隔离生效"。

---

## 2. 判据②：为什么全空 —— 定量答案（分桶，含"不许只答默认值是空串"那半条）

### 2.1 现读原始数（2026-09-27，只读）

| 账 | 读数 |
|---|---|
| `chunk_vectors`（生产镜像） | rows=**1008**，`department` 非空=**0**，不同部门=**0**，不同密级=**1**，`classification IS NULL`=0，文件=**100** |
| `chunks`（发布账，同一批） | rows=**1008**，`metadata->>'department'` 非空=**0**，非默认密级=**0** |
| `documents`（目录逻辑行） | rows=**105**，`department` 非空=**3**，非默认密级=**0** |
| `document_versions`（目录版本行） | rows=**100**，`department` 非空=**0**，非默认密级=**0**，`owner_id` 为空=**0**（100/100 有主，全是 `admin`） |
| `resource_versions`（`resource_type='document'`） | rows=**129**，带 `department_ids` 的=**3** |
| `users` | rows=**3**，`admin`=SQL NULL、`evalbot`=SQL NULL、`dataowner`=「财务部」⇒ **1/3** |
| 遗留引擎 `enterprise_docs`（`mode=ro` 直读） | embeddings=**1008**，`department` 键在位=1008 枚但值 `''`=**1008**，非空=**0**，`classification`=`1`=**1008**，文件=**100**，`query_only`=1 |
| `/app/documents` 磁盘侧 | 文件=**101**，`32` 位十六进制哈希名=**100**，按内容命名=**1**，非文本=**5** |

那 `3` 枚 `documents.department` 非空，全部是 `r8-scope-0b665a63.txt` / `r8-scope-4f311c41.txt` / `r8-scope-8f193cfe.txt`：部门 `R8甲部`、owner `r8-probe-a`、在 `resource_versions` 里 `status=retired`，且**既没有 `document_versions` 行、也没有任何 `chunk_vectors` 行**。⇒ 它们是 R8 时代探针留下的样本行，**不是**"有部门却丢了"的文档。生产上今天没有任何一枚真实业务文档带着部门。

### 2.2 分桶（口径：`chunk_vectors` 里真在位的 `100` 枚文档 / `1008` 枚 chunk）

| 桶 | 含义 | 文档 | chunk |
|---|---|---|---|
| ① 源头就没有 | 目录账（`documents`）那一格本身就空 | **100** | **1008** |
| ② 源头有但没传下来 | 目录账有部门、`chunk_vectors` 空 | **0** | **0** |
| ③ 传下来了但写错列 | 两处都非空却不相等 | **0** | **0** |
| （对照）传下来且一致 | 两处都非空且相等 | 0 | 0 |

🔴 **这张表是本单最重要的一句话：传播链没有被写坏，桶② 与桶③ 都是 0。**"11 跳复制元数据"那条路（第 11 跳）今天忠实搬运了上游 —— 上游是空的。所以修法不该往 `pg_store.py` 打补丁，也不该新增迁移去"补列"。

### 2.3 但"源头就没有"不等于"信息不存在"（这就是为什么不能只答"默认值是空串"）

签名（默认值 `""`）不是原因。原因要查调用点，两处：

1. 上传入口让 `users.department` 成为文档部门的**唯一入口**（`app/api/v1/chat.py` 里"服务端用主体的部门覆盖客户端那一格"的硬编覆盖 —— 现读行号只写在 §1 那张血缘表的第二跳，本节不重抄一份会过期的数）；
2. `app/common/auth.py` 的 `_seed_bootstrap_admin` 只在 `users` 空表时跑一次，`department` 取 `AUTH_DEPARTMENT`（键名那一枚 `getenv` 由 `rg -F` 现读；两枚模板 `.env.example` 与 `deploy/.env.server.example` 零命中，而 `.env` 与 `deploy/.env.server` 在客户机上、**不在本树盘上** ⇒ "都没有这一枚键"是 R387 当时的现读，本单复跑不了，不许当成今天的读数）⇒ `admin` 落 `NULL`，并且**以后补设环境变量也不会回填既有账号**（同一格的现读行号在 §1 表第四跳）。

那"源头到底有没有部门信息"是有数可量的，🔴 而**这一格从今往后由命令给数、不许手抄**：下面那一整块（连它自己的两行标记一起）是渲染产物，复跑命令、数据源路径与条数都印在块里；`--verify-plan-table` 拿现读渲染逐字节比对那一块，`--write-plan-table` 重落地它。姿势与 §9.5 那张解锁梯同法同姿势，两本账吃同一次分桶：块里"可规则回填"那枚 chunk 数就是梯级 S3 挪开的格数，"合计"就是 S3b 的格数，谁也不许另起口径。

数据源是 `chunk_vectors` 的只读导出，今天**收进了树里**：落在 `%TEMP%` 上就等于"只有那一台机器能复跑"，而批准材料要的是谁都能重跑一遍。重导那枚数据源是 §7 里的一条只读 psql，🔴 不是任何人的记忆；它读不出来时本件非零退出并报名字，不会退化成一张旧表。

<!-- R409:BEGIN 本块由 `python scripts/r387_backfill_estimate.py --no-db --names-file <数据源> --emit-plan-table` 渲染，一个字都不许手抄 -->
数据源：`docs/perf/raw/r387-backfill-names-2026-09-27.tsv` —— 只读导出的「显示文件名 → chunk 枚数」，逐行按制表符分列现读，本件不发一条 SQL、不写一行数据。

判定依据：`scripts/r387_label_lineage.py::DEPARTMENT_HINTS`（公开口径：文件名里出现某枚 token 就记一枚命中）。命中唯一 = 可规则回填；命中多枚或零枚 = 必须人工裁决。这一口径量的是「语义上像属于谁」，🔴 **不是权威**，回填前由业主逐格确认；判词一律出自 `classify_arm`，本件不重造判序。

| 量（每一格现读） | 文档 | chunk | 占合计 |
|---|---|---|---|
| 文件名只指向**唯一**一枚部门（可规则回填） | **74** | **923** | 91.6% |
| 文件名指向**多枚**部门（必须人工裁决） | **10** | **28** | 2.8% |
| 文件名**不给任何**部门线索（必须人工裁决） | **16** | **57** | 5.7% |
| 必须人工裁决小计 | 26 | 85 | 8.4% |
| 合计（= 数据源行数 / 枚数） | 100 | 1008 | 100.0% |

规则可达部门 **11** 枚，按 chunk 降序（同数按部门名升序；同一枚数据源两次渲染逐字节相等）：

| 部门 | 文档 | chunk | 占可回填 |
|---|---|---|---|
| `研发` | 17 | 713 | 77.2% |
| `销售` | 16 | 55 | 6.0% |
| `行政` | 6 | 33 | 3.6% |
| `人力资源` | 10 | 28 | 3.0% |
| `信息安全` | 6 | 27 | 2.9% |
| `经营层` | 3 | 18 | 2.0% |
| `市场` | 6 | 17 | 1.8% |
| `财务` | 4 | 13 | 1.4% |
| `采购供应链` | 3 | 11 | 1.2% |
| `法务` | 2 | 6 | 0.7% |
| `审计` | 1 | 2 | 0.2% |

🔴 回填出来的分布并不均衡：最重一格 `研发` = **17 枚文档 / 713 枚 chunk**（占可回填的 77.2%），次重 `销售` = 16 枚文档 / 55 枚 chunk。**「规则可达 11 枚部门」不等于「11 家都覆盖到了」** —— 这句话必须跟着批准材料一起走。

必须人工裁决的多归属清单（按显示文件名升序；「命中部门」就是规则给出的全部线索）：

| 显示文件名 | chunk | 命中部门 |
|---|---|---|
| `2026年度预算方案_摘要.txt` | 3 | 经营层｜财务 |
| `GB-T 22239-2019 信息安全技术等保三级要求.txt` | 5 | 信息安全｜研发 |
| `MYO_安全白皮书_对外版.txt` | 3 | 信息安全｜研发 |
| `团建活动通知_2026春季.txt` | 1 | 人力资源｜行政 |
| `客户数据保护政策_正式稿.txt` | 3 | 信息安全｜销售 |
| `客户数据保护政策_草稿.txt` | 2 | 信息安全｜销售 |
| `案例_明达律师事务所.txt` | 3 | 法务｜销售 |
| `案例_美的集团供应链.txt` | 3 | 采购供应链｜销售 |
| `消防安全管理规定.txt` | 3 | 信息安全｜行政 |
| `销售话术培训_应对话术集.txt` | 2 | 人力资源｜销售 |

零线索的那 16 枚文档 / 57 枚 chunk 不在这里逐枚列（清单在本件 `--json` 输出的 `plan.unhinted` 里，同样是现读）：它们与上面这些一样，规则给不出部门，只能业主点名。

🔴 本块只声明**能回填多少**，不声明回填之后验收 C 判什么：那本账在文档 §9.5 的解锁梯（`--unlock-ladder` 现跑），两处吃的是同一次分桶。渲染不带时间戳 —— 加了就没有逐字节可复现；数由数据源决定，数据源由 §7 那条只读命令重导。
<!-- R409:END -->

上一版这一节的数是抄下来的一次数，其中一格与量具后到的现读不一致（那笔漂移记在 §9.5；本块不重抄旧数——留着它等于又养一本账）。业主批 A3 看的就是这张表，所以它现在只能是渲染产物：影子数据里挪走几枚可回填 chunk，这块的数必须跟着动，动不了就说明有人在源码里写死了一枚数。

还有一句与数无关、却断掉一条捷径的事实：`app/api/v1/chat.py` 落盘走 `build_storage_path(DOCUMENTS_DIR, resource_id, ext)`，生产磁盘上的文件是内容哈希名 —— **显示文件名只活在目录账里**（`documents.filename` / `chunk_vectors.filename`）。任何"按名字认归属"的规则都只能在 catalog 这一侧走，别去 `documents/` 目录里找原名。

🔴 **那一格修好的是"批不批得动"，不是 §13 格③ 的验收状态。** 格③ 今天仍记「未验」：四件可失败判据 (a)(b)(c) 未成立、(d) 只在空集上成立。按这份计划回填只挪开 (b) 的部门半边，密级半边与召回半边一个字都没动（梯级账 S3 → S4 → S5 三行说的就是这件事）；翻绿要等 A1（业主补 `users.department`）之后重测，或者连 A3 一起批下去、再补密级与那一轮真测量。

---

## 3. 判据③：修法（两个候选，排序 + 代价 + 撞车表 + 第二本账论证）

### 方案 A（推荐 · 先配置、后一个入口、再回填）

**A1 业主动作（今天就能做，零代码、零迁移、零新 Chroma 写点）**：把上传账号的部门补上。`AUTH_DEPARTMENT` 对既有账号**无效**（第 4 跳那条 `if count(*) : return`），所以唯一可行写口是 `PUT /api/v1/users/department`（`app/api/v1/auth.py:155`、`:199` → `app/common/auth.py:727-754`，需 `users:manage`；员工自助走不通，`app/api/v1/auth.py:257-275` 明写那一格是只读派生值）。
**A2 代码动作（一枚，等 R384）**：`POST /upload` 在 `principal.department` 为空时**拒收**（422 同族码，`department_scope_required` 已在册，`scripts/seed_workspace.py:4-5` 就是它），而不是静默落 `""`。这一格缺的不是传参，是**拒收**：今天 `chat.py:4078` 把空值一路放行到 `:1365` / `:373`， producing 一库"检索永远命中不到"的文档。
**回填**：**需要** —— 不回填，那 1008 枚永远空。回填 = 写生产数据 = 业主动作，必须先量后批：量具 `scripts/r387_backfill_estimate.py`，读数见 §2.3（`74` 枚文档 / `923` 枚 chunk 可规则回填，`26` 枚 / `85` 枚必须人工裁决）。🔴 本件 `writes_issued=0`，一行都没写。
**新迁移**：**不需要**。列、默认、COMMENT、索引都在 `migrations/0010_pgvector_chunks.sql` 里现成（`:141` 列、`:163-164` 那句 COMMENT、`:374-375` / `:387-388` 两枚 prefilter 索引）。
**动 `app/documents/catalog.py` 吗**：**方案 A 不动**。`department` 早就在参数链上（现读 `:647` / `:762`），A1/A2 都不需要新写口。⚠ 一旦要加"按文档改部门"的写入口（业主若要求"部门随文档而不是随人"），就必须等 **R383（`Boyle`）并完**。

### 方案 B（更对，但更贵 · 文档部门改由资源归属决定，不再寄生在上传人身上）

把第 11 跳的"复制遗留引擎元数据"改成"发布时按 `publication.resource_department_ids` 展开" —— 这条路**已经有一半在树里**：`app/rag/indexing.py:944`（`department_ids` 字段）与 `:969-981`（`resource_department_ids` 属性，含"没列就用自己那一枚，谁都不属于就返回空元组"的口径）；`resource_versions` 今天已有 `3` 行带 `department_ids`，形状对、没人喂。
代价：要动 `indexing.py`（写 `chunks`）+ `pg_store.py` 写侧或 `0010:396-400` 那支 trigger + `chat.py` 传 `scope`（**R384 写域**）+ 多半要动 `catalog.py`（**R383 写域**）；还要处理形状不匹配：`chunk_vectors.department` 是 `TEXT` 单值列（`0010:141`），而 `department_ids` 是数组 ⇒ **一枚 chunk 只能挂一枚部门**，跨部门资源共享要么改成数组、要么按部门复制 chunk。估算 `4–6 人日`（含召回复测）。

### 撞车表（写域与动作边界）

| 动作 | `app/api/v1/chat.py` | `app/documents/catalog.py` | `app/rag/indexing.py` / `pg_store.py` | 新迁移 | 写生产数据 | 人日 |
|---|---|---|---|---|---|---|
| A1 补 `users.department` | 否 | 否 | 否 | 否 | **是**（`users` 一行，业主动作） | 0.5（含重取读数） |
| A2 空部门拒收 | **是** ⇒ 🔴 **必须等 R384（`Descartes`）并完** | 否 | 否 | 否 | 否 | 1 |
| A3 规则回填 + 人工裁决 | 否 | 否 | 否 | 否 | **是**（`1008` 枚 chunk 的 `department`；业主动作，先量后批） | 1.5 + 业主批准 |
| B 部门改由资源归属 | **是**（R384） | **是**（R383） | **是** | 多半要 | 是 | 4–6 |

排序：**A1 → A2 → A3**，B 押后。理由：A1 是今天唯一能让"部门谓词不再是空集"的动作，且零代码；A2 补的是"以后不再静默造不可检索文档"；A3 才让存量可判。B 一次撞两枚在途写域，且要先裁"部门属于文档还是属于人"这个业务问题（本单无权裁）。

### 第二本账风险（照 `0010:163-164` 的标准论证 `department` 为什么可以复制）

今天 `department` 已经存在 `4` 处：`documents`、`document_versions`、`chunk_vectors`（0010 起）、`resource_versions.department_ids`。`:164` 那句 COMMENT 的原则是：**`owner_id` 刻意不复制，因为它是文档级事实、权威在 catalog，多一份就会漂**；而 `department` / `classification` 可以复制，理由是 `"它与检索器手里那一枚 chunk 不可分"` —— 闸门 `pg_store.py:638` 只认 `classification` / `department` 两列，谓词要**就地可读**，逐枚 chunk 去 join 目录账等于把权限判定搬到另一条路上做第二遍。

按同一条标准，`department` 可以复制，但必须钉死三件事，否则它今天这 `4` 份就是四本账：

1. **权威只有一枚**：`documents` / `document_versions` 是权威，`chunk_vectors.department` 与遗留引擎元数据都是**派生副本**；今天 `pg_store.py:373` 把"副本的副本"当来源，这就是 §2.2 那张"桶② 桶③ 都是 0"能成立的机制 —— 它没有独立价值，只会跟着空。
2. **副本不许被单独修**：回填必须走"改权威 → 重发布"，不许 `UPDATE chunk_vectors` 一处了事；否则 `documents` 与 `chunk_vectors` 立刻分叉（现读已经在往这个方向走：`documents` 有 `3` 枚非空、`document_versions` `0` 枚非空，两本目录账对同一件事给出不同答案）。
3. `classification` 与 `department` 同批处理：§2.3 那条回填量完仍然 `未验`（`scripts/r387_backfill_estimate.py` 原话："语料只有一档密级：没有跨密级可选"），因为文件名给不出密级线索。🔴 **只回填部门，验收 C 依然不能打勾。**

---

## 4. 判据④：把"越权 0 条"改写成一条今天能失败的判据

### 4.1 改写后的判据原文（建议照抄，`R387` 只报不改）

> **验收 C（权限过滤）**：一条臂要记 `通过`，必须**同时**满足四件 ——
> (a) 主体侧这一臂真带部门（`principal.department` / `department_ids` 非空，管理员 `departments=None` 那一档不算，它测的是越权上限而不是部门隔离）；
> (b) 语料侧非空 `department` 枚数 `> 0`，且不同部门 `≥ 2`、不同 `classification` `≥ 2`（沙盒口径 `4 × 4` 是够用形状，生产口径至少要 `2 × 2`）；
> (c) 该臂 `召回行数 > 0`；
> (d) 该臂越权命中 `= 0`。
> 🔴 **(a)–(d) 任一不满足 ⇒ 该臂记「未验」，不得记「通过」，也不得记「失败」。** 只有 breaches `> 0` 才记「失败」，且「失败」优先于一切「未验」（安全问题不许被"还没量"盖掉）。
> **2026-09-27 现读**：`chunk_vectors` `1008` 枚中非空 `department` `0` 枚、不同密级 `1` 档 ⇒ 今天的 C 是 **未验**。"越权 0/0"只是 `(b)` 不成立时的空集副产物。

判据之家：`scripts/r387_label_lineage.py::classify_arm`（六条守卫、唯一判序、每条一个稳定原因码）。它在同一份生产读数上给出 `未验`，而"只看 `breaches == 0`"的朴素判法给出 `已验` —— 这一对分歧就是 R382 那格假绿的机制。

### 4.2 在哪个库上量

| 库 | 今天能不能量出这条判据 | 现读凭据 |
|---|---|---|
| 生产 `enterprise_brain` | **不能**（`(b)` 挂：`0/1008` 非空、1 档密级） | §2.1 表 |
| 沙盒 `eb_r59_sandbox` | **形状能、真标签不能** —— 语料侧 `1008` 枚 `100%` 带标签（`engineering/finance/hr/sales` 各 `252`；密级 `1/2/3/4` 各 `252`），`classify_arm` 的 `(b)` 满足；但 `users` 表 `0` 行 ⇒ 主体侧靠 `scripts/r59c_sandbox_corpus.py:165` 合成，**部门名与密级都是编的**，所以它验的是"谓词与索引的选择性行为"，不是"我们客户的部门隔离" | 只读复核 `chunk_vectors` 分布 |

⇒ 下一格要做的不是再跑沙盒，而是：**A1（业主补 `users`）+ A3（业主批回填）**之后，在生产上重跑四臂，让 `(c)` 第一次在真标签上非空。

### 4.3 「标签全空 ⇒ 未验而非通过」这一句要写进哪一节（总控写域，本单只报不改）

1. `docs/handoff/2026-09-17-pgvector-adoption-plan.md` §9.3 第 **③** 格（现读 `:379-381`，那句"选择性权限过滤没量：本库 `classification` 全=1、`department` 全=`''`"）—— 把它从"没量"升级成 §4.1 那段四件判据 + `未验` 结论；
2. 同文件 §3 `P4 切读`（现读 `:77-83`）与 §4 阶段表的 `P4 / R59` 行（现读 `:99`，"过判据 ①②③"）—— 把 §4.1 记成 P4 的第 **③** 条过判据，明写"标签全空的 0 越权不算过"；
3. 顺带把 §11 那格 `:442-448` 的 live-PG 表补两行（`department` 非空 = `0/1008`、`classification` 档数 = `1`），否则那张表读起来像"库很健康"。

---

## 5. 判据⑤：常驻钉清单、两把刀红数、进出 sha

### 5.1 新钉枚数

| 文件 | 形状 | 今天读数 |
|---|---|---|
| `tests/test_r387_label_ruler_teeth.py` | 12 枚静态 + `12` 枚血缘跳参数化 + `12` 枚凭据 token 参数化 = **36 枚** | **36 passed** |
| `tests/test_r387_production_label_leg.py` | **5 枚**（1 枚头条 + 3 枚账对照 + 1 枚报数） | **4 passed, 1 failed**（红的就是头条） |

`tests/test_r387_production_label_leg.py::test_acceptance_c_department_leg_passes_on_production` 今天必须红，红话原文（现跑）：

> `验收 C 的部门腿判词是 未验，原因：语料的 department 全为空：部门谓词恒空集，「越权 0 条」只在空集上成立。现读：0/1008 枚带非空部门、0 枚不同部门、1 档密级、1/3 枚账号有部门。把「越权 0 条」写成通过之前，先让这一枚转绿。`

它不是"永远红的观察钉"：回填 + 真测之后它会转绿；而 `test_the_blocker_is_recorded_and_moves_with_the_data` 会在标签一非空时反过来咬一口（判词若还说空集 = 量具坏了）。容器不在位时它 `pytest.skip` 并明写 `"未验：本机读不到生产库（容器不在位或 psql 拒连），本件不假装绿"` —— 🔴 不静默绿。

### 5.2 两把刀红数（变异检验，可复跑）

挂钩是 `R387_LABEL_TOOL`（指到一份摘掉守卫的量具副本），复现：

`Copy-Item scripts/r387_label_lineage.py $env:TEMP/r387/mut.py   # 删掉指定那一行守卫`
`$env:R387_LABEL_TOOL = "$env:TEMP/r387/mut.py"; python -m pytest tests/test_r387_label_ruler_teeth.py -q`

| 变异（摘掉哪条守卫） | 红数 | 变红的钉 |
|---|---|---|
| `corpus_labelled_chunks == 0`（标签全空那格） | **2 failed / 34 passed** | `test_all_empty_labels_with_nonempty_recall_is_unverified_not_passed`、`test_guard_order_is_breach_then_principal_then_labels_then_selectivity_then_recall` |
| `arm.recalled == 0`（召回为空那格） | **2 failed / 34 passed** | `test_zero_recall_arm_is_unverified_even_with_rich_labels`、`test_guard_order_…` |
| 基线（未变异） | 36 passed | — |

第二把刀的形状正是派工词点名的那一发：**"标签全空但召回非空"的假数据 ⇒ 判据必须 `未验`；谁把守卫摘掉，让它退化成"越权 0 ⇒ 通过"，`test_all_empty_labels_…` 与 `test_guard_order_…` 当场两枚红。**

### 5.3 报数钉的现读输出（谁跑都看得到这三个数）

`[R387 生产标签非空率] chunk_vectors labelled=0/1008 = 0.0000 | departments=<ALL EMPTY> | classifications=['1'] | nondefault_classification=0 | files=100 | publishing_ledger_labelled=0/1008 | accounts_with_department=1/3`
`[R387] 账号侧有部门的比例 = 1/3 = 0.33`

### 5.4 交付件与进出 sha

哈希与字节口径现取在本文档 `§7` 那张表里。本文档自己的哈希不写进本文档 —— 一枚文件装不下自己的哈希；总控按 `§7` 那条命令现取一次即可对数。

---

## 6. 没做到的格子（如实列，不销）

1. **没在生产上量出一条 `已验` 的臂**。本单零写入，(a)–(d) 里的 `(b)` 今天就不成立；这条只能在 A1+A3 之后由下一格做。
2. **密级那一格的回填没量**。文件名给不出密级线索（`r387_backfill_estimate.py` 的结论原话是"语料只有一档密级：没有跨密级可选"），要量得先由业主裁"密级的权威是人、是文档模板、还是目录"。
3. **"部门属于上传人还是属于文档"没裁**。方案 A 与方案 B 的分水岭就是这一句，属业务裁，不属取证裁。
4. **没跑 `scripts/run_gate.py` 全量门**。派工词只要求点名件逐枚单跑；本单两枚钉件合计 `41` 枚（`36 + 5`）逐枚带路径跑过。
5. **沙盒 `eb_r59_sandbox` 只读了一遍分布**，没在沙盒上重跑四臂 —— 那是 R382 已经量过的形状（`hr-c1` 12/12 裁空），本单的增量在生产侧。
6. **遗留卷 `chroma.sqlite3` 的 mtime 会随只读进程前进**这一格（计划书 §9.3 第 ⑤ 格）本单同样没消：本件为了量元数据确实打开过它（`mode=ro`）。`query_only=1` 有读数，但 mtime 动了就是动了，如实报。
7. `documents/` 磁盘那 `101` 枚文件与 `chunk_vectors` `100` 枚文件之间那 `1` 枚差额没追（本单口径以库内 `filename` 为准），留给下一格或 P5 停写时一并清。
8. **没回填计划书**（§9.3 / §3 P4 那两处是总控写域，见 §4.3）。

---

## 7. 交付件字节口径与哈希（2026-09-27 现取）

| 交付件 | sha256 | size | CR | LF | 裸 LF | U+FFFD | BOM |
|---|---|---|---|---|---|---|---|
| `scripts/r387_label_lineage.py` | `839860f87a83dbbe00420d5d298fee31396dd6ad37ffcd432305490c5f440b32` | 29237 | 572 | 572 | **0** | **0** | 无 |
| `scripts/r387_backfill_estimate.py` | `63e7516bc210bbd9a30f29e24dc9760270331d45b4a0304e57f79ddac54dafb1` | 7100 | 148 | 148 | **0** | **0** | 无 |
| `tests/test_r387_label_ruler_teeth.py` | `12ae1f85423233b1e20772df9856a6d77fe5dd295e5627b051afdd4ffa4076ba` | 15802 | 306 | 306 | **0** | **0** | 无 |
| `tests/test_r387_production_label_leg.py` | `f1959c62f28d5a6035aeff59feb6a47bae9879b30e6af8578622ba003acfa128` | 10909 | 222 | 222 | **0** | **0** | 无 |
| `docs/perf/r387-label-lineage-2026-09-27.md`（本文档） | 注入本节后再现取，见下 | — | — | — | **0** | **0** | 无 |

CR = LF 且裸 LF = 0 ⇒ 纯 CRLF；无 BOM；U+FFFD = 0。复算命令（宿主机，主树 venv）：

```powershell
$f = @("scripts/r387_label_lineage.py","scripts/r387_backfill_estimate.py",
      "tests/test_r387_label_ruler_teeth.py","tests/test_r387_production_label_leg.py",
      "docs/perf/r387-label-lineage-2026-09-27.md")
foreach ($p in $f) {
  $b = [IO.File]::ReadAllBytes("$PWD\$p"); $s = [Text.Encoding]::UTF8.GetString($b)
  "{0} {1} size={2} CR={3} LF={4} bareLF={5} FFFD={6}" -f $p,
    (Get-FileHash "$PWD\$p" -Algorithm SHA256).Hash.ToLower(), $b.Length,
    ([regex]::Matches($s,"`r")).Count, ([regex]::Matches($s,"`n")).Count,
    ([regex]::Matches($s,"[^`r]`n")).Count, ([regex]::Matches($s,[char]0xFFFD)).Count
}
```

本文档注入完本节之后的哈希（同一枚命令现取，写在收工回执里，避免自指）：见回执 §交付件哈希。

复跑两枚钉件（逐枚点名，带路径参数；🔴 不裸跑全树 pytest）：

```powershell
$py = 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe'
Set-Location 'C:\Users\fengx\PycharmProjects\be-r387'
& $py -m pytest tests/test_r387_label_ruler_teeth.py -q     # 期望 36 passed
& $py -m pytest tests/test_r387_production_label_leg.py -q  # 期望 4 passed, 1 failed（红的就是判据④本体）
& $py -m pytest tests/test_r302_docs_utf8_guard.py -q       # 期望 8 passed（本文档动过 docs/）
```

读数工具复跑（只读，零写入；生产库走容器内认证，宿主机不需要 DSN）：

```powershell
# 生产 + 遗留卷 + 磁盘三侧一次读全，判词当场打印
Get-Content scripts/r387_label_lineage.py -Raw | docker exec -i enterprise-brain-backend-1 `
  /app/.venv/bin/python - --documents-dir /app/documents `
  --chroma-sqlite /app/chroma_db/chroma.sqlite3 --json /tmp/r387-ledger.json

# 回填量：只读 psql 导 (显示文件名 -> chunk 枚数)，再喂给量具。
# stdin 走 .NET 写 UTF-8 字节，不走 PowerShell 管道：中文文件名经控制台编码换一遍，
# 量具就会把同一枚文档读成两枚名字（本单实测用的就是这一条）。
$sql = @"
SET default_transaction_read_only = on;
BEGIN;
SELECT filename || chr(9) || count(*) FROM chunk_vectors GROUP BY filename ORDER BY filename;
COMMIT;
"@
$bytes = [Text.Encoding]::UTF8.GetBytes($sql)
$psi = New-Object Diagnostics.ProcessStartInfo
$psi.FileName = 'docker'
$psi.Arguments = 'exec -i enterprise-brain-postgres-1 psql -U enterprise_brain -d enterprise_brain -tA -f -'
$psi.RedirectStandardInput = $true; $psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true; $psi.UseShellExecute = $false
$proc = [Diagnostics.Process]::Start($psi)
$proc.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length); $proc.StandardInput.Close()
$rows = $proc.StandardOutput.ReadToEnd() -split "`r?`n" | Where-Object { $_ -match "`t" }
$proc.WaitForExit()
[IO.File]::WriteAllLines("$env:TEMP\r387\names.tsv", $rows, (New-Object Text.UTF8Encoding($false)))
& $py scripts/r387_backfill_estimate.py --no-db --names-file "$env:TEMP\r387\names.tsv"

# 上面那条 lineage 命令会在 backend 容器 /tmp 落一枚 ledger（只是计数，无正文无凭据），
# 收工前扫掉自己的垃圾：docker exec enterprise-brain-backend-1 rm -f /tmp/r387-ledger.json
```

---

## 8. 总控退回与本班处置（R390 · 2026-09-27 续班）

R387 交回的五枚质量很高，但**不能原样进主干**，两笔退回缺一不可。本节只登记「为什么退」与
"改成了什么形状"，**不改写 §1–§7 的任何原始读数** —— 那是 R387 现场量出来的账，改掉它等于毁掉
一次可复核的取证。两处今天已过时的读数（§5.1 的 `4 passed, 1 failed`、§7 的三行哈希）按
"在下文另记现读"的方式作废，旧行一个字留。本节由 R390 施工写，验收与并树归总控。

### 8.1 退回①：取证件自带一枚裸连接 ⇒ 改走唯一边界

政策原文写在 `app/notifications/states.py` 上方那段注释里：新模块不许自带裸 `psycopg.connect`，
全仓只供出 `app/db/connection.py` 这一枚边界。尺子是 `tests/test_r238_bare_connect_ratchet.py`（`rglob` 扫 `app` 与 `scripts` 两棵根，基线 15 枚只准降不准升）。§7 那批 `r382_*` 取证脚本
今天正欠着这笔账（主树因此红 14 枚，另有一枚 Agent 在治），R387 若原样入树就是把第 14 枚
r387 身份再加进去 —— 退回来治的是这一格，不是 §1–§7 的任何一条读数。

改法照现成先例，不自创：`scripts/compare_vector_recall.py:49` 那行模块顶 import，加
`:157-165` 那个 `connect_read_only()` 的三步（`parse_database_settings` → `open_connection` →
再压 `connection.read_only = True`）。`read_postgres` 里被换掉的只有取连接那一件事，三格逐格自证：

| 格 | 未变的凭据（本班现读） |
|---|---|
| `expect_database` 闸门 | `attached != expect_database` 与 `raise SystemExit("ABORT…")` 两行一字未动；另由 `tests/test_r390_xfail_strict_and_boundary_pins.py::test_the_read_only_guards_and_the_wrong_database_gate_survive` 按 AST 钉住（不是文案 grep） |
| 只读语义 | 原来是 `SET default_transaction_read_only = on` 一道；现在是 `conn.read_only = True` **加**同一道 SET，两道都在。`SHOW default_transaction_read_only` 的读数仍然进 `readings["read_only_guard"]`，键名与取值都没换 |
| stdout 字节形状 | 同一份 `--no-db` 读数，改前改后各跑一次：stdout 逐字节相等、ledger JSON 逐字节相等（sha 相等）；唯一的差异是我自己传进去的两个 `--json` 路径名 |

`read_only = True` 到底做了什么，按驱动源码记账而不是按名字猜：`psycopg/_connection_base.py:570-571`
把 `b"READ ONLY"` 拼进 begin 语句，所以第一条语句之前压上它，之后每个隐式事务都是 `BEGIN READ ONLY`，
误写当场报错。顺序也真吃得下：在生产库上只读跑 `BEGIN READ ONLY; SET default_transaction_read_only = on;
SHOW default_transaction_read_only` 交回 `on`（不是报错）⇒ 先压会话只读再压 SET 这个顺序在生产上成立。

🔴 **反向门（不许为了变绿去动尺子或基线表）**：改完再跑尺子，它仍然红 14 枚（那是 `r382_*` 欠的账，
不归本单治），但失败清单里 `scripts/r387_label_lineage.py::read_postgres` 已经摘干净。两次读数原文：

- 改前：`AssertionError: 边界之外裸 connect 从 15 枚涨到 29 枚；… scripts/r387_label_lineage.py::read_postgres#0 → scripts/r387_label_lineage.py:358`（该次输出里 r387 命中 5 行）
- 改后：`AssertionError: 边界之外裸 connect 从 15 枚涨到 28 枚；…`（同一枚尺子、同样的 14 failed / 19 passed，r387 命中 0）

### 8.2 退回②：那枚今天必红的判据 ⇒ `xfail(strict=True)`

定案三条，缺一不可（这也是为什么偏偏是这个形状）：

1. **门今天绿**。仓内纪律是"全量门零失败是硬规矩"，而事故 #56 刚立的就是"主干自带红"；再来一枚
   **永久**红，等于亲手把"红 = 有问题"这条信号废掉 —— 往后任何一枚真红都会被人当成"哦那枚 r387"。
2. **不许假绿**。pytest 摘要里它是 `1 xfailed`，**永远不计入 passed**，谁来看都读不到"通过"两个字。
   裸 `skip` 同样能让门绿，但 skip 会被读成"这格过了"，所以出局（上一班拒绝 skip 的理由照收）。
3. **strict 才是报警的那半**。一旦生产真补上标签、这枚一转好，pytest 当场报 `XPASS(strict)` 变红，
   逼接手的人回来销账并按 §4 改判"已验"。现读 `pyproject.toml` 的 `[tool.pytest.ini_options]`
   里**没有** `xfail_strict`，全局默认 `strict=False` ⇒ "必须显式 `strict=True`"是承重的，不是好看，
   所以它单独有一枚钉（摘掉 strict 当场红，见 §8.4 刀 K1）。

只加在该加的那一枚：只有 `test_acceptance_c_department_leg_passes_on_production` 挂这枚标记。
`test_the_blocker_is_recorded_and_moves_with_the_data` **保持真绿** —— 它是"阻塞在案"那本账，
一起 xfail 掉整件就没有主张了；容器不在位那两枚 `pytest.skip(UNAVAILABLE)` 的原语义一字未动
（那是环境缺失，不是判据未成立），并且另起一枚钉把它们锁在原形状上。

今天的读数（本机现跑，主树 `.venv` 解释器逐枚带路径；生产容器 `Up (healthy)` ⇒ 走的是真断言，
不是 skip 分支 —— 这正是本定案要的形状）：

| 件 | 现读 | 对照 §5.1 |
|---|---|---|
| `tests/test_r387_production_label_leg.py` | **4 passed, 1 xfailed**，零 failed | §5.1 那格 `4 passed, 1 failed` 从今天起作废 |
| `tests/test_r387_label_ruler_teeth.py` | **36 passed** | 与 §5.1 相等：一枚未增删，形状未动 |
| `tests/test_r390_xfail_strict_and_boundary_pins.py` | **11 passed**（本班新增） | 新钉**另起一文件**，不挤进那 36 枚的名次 —— 否则"仍 36 passed"这条验收就没有读者 |

### 8.3 🔴 这一格既不等于验收 C 通过，也不等于 R59 切读被阻塞

- **不等于 C 通过。** 台账上它从今天起记「未验」：既不记「通过」，也不记「不通过」。§4.1 那四件
  判据里的 `(b)` 今天仍不成立（`0/1008` 非空、1 档密级），本节没有推翻 §1–§7 的任何一条结论，
  只是把"今天判不了"这件事从**一枚常驻红**换成**一枚会自己报警的 xfailed**。
- **不等于 R59 切读被阻塞。** 挡着翻 `INDEX_BACKEND=pgvector` 的仍是计划书 §9.3 那三格（格②热集
  让路要一台安静机器重量、格③生产 `department`/`classification` 全空、查询期 `hnsw.ef_search` 40 vs
  遗留引擎实测 100）。本单没给那三格增加任何新阻塞，也没替它们消掉任何一格。C 记「未验」这件事，
  是格③那条"已登记·未治"的账在常驻测试里的**显影**，不是新堵点；把标记销掉的那个人的动作应该是
  回到 §4 改判，而不是去翻开关。

### 8.4 六把刀（变异检验；逐把按字节复原并自证进出 sha 相等）

复跑器是临时件（`%TEMP%\r390_knives.py`，不入树）：它只改这三枚交付件的字节，每把刀跑完立刻
用进刀前的字节复原，并比对 sha。六把全部 `restored sha equal: True`（下表"复原自证"列）。
点名件 = 本班的形状钉 + 那枚腿件（刀 K5 另加下牙件与尺子本身）。

| 刀 | 改哪几字节 | 红几枚 | 具名红件全路径 | 复原自证 |
|---|---|---|---|---|
| K1 摘掉 `strict=True` | 那枚标记去掉 `strict` 关键字 | **1** | `tests/test_r390_xfail_strict_and_boundary_pins.py::test_that_xfail_is_strict_true_not_bare_not_false` | sha 相等 |
| K2 `xfail` 整枚换成 `skip` | 同一行 `mark.xfail` → `mark.skip` | **4** | `…::test_the_xfail_lands_on_exactly_the_acceptance_c_leg`、`…::test_that_xfail_is_strict_true_not_bare_not_false`、`…::test_the_reason_is_a_ledger_entry_naming_the_blocker_and_its_source`、`…::test_the_xfailed_leg_is_not_also_silenced_by_a_skip_mark` | sha 相等 |
| K3 把登记阻塞那枚一起 xfail 掉 | `test_the_blocker_is_recorded_…` 上方加一枚 strict xfail | **3** | `…::test_the_xfail_lands_on_exactly_the_acceptance_c_leg`、`…::test_the_blocker_registration_test_stays_unmarked`、`tests/test_r387_production_label_leg.py::test_the_blocker_is_recorded_and_moves_with_the_data` | sha 相等 |
| K4a 换成运行时 `pytest.xfail()` 调用 | 去掉标记，改在函数体首行调 `pytest.xfail(…)` | **4** | `…::test_the_xfail_lands_on_exactly_the_acceptance_c_leg`、`…::test_that_xfail_is_strict_true_not_bare_not_false`、`…::test_the_reason_is_a_ledger_entry_naming_the_blocker_and_its_source`、`…::test_no_runtime_xfail_call_masquerades_as_the_marker` | sha 相等 |
| K4b 把 `xfail` 放进 `if` 里面 | 标记前加 `if True:` 并缩进那一行 | **0 枚断言红 —— 整场收不起来**：`exit code 2`、`1 error`、零枚用例被跑到；报文本 `IndentationError: unexpected unindent`（`tests/test_r387_production_label_leg.py:168`） | 同上（Python 语法本身就不允许装饰器条件化，所以它红在收集，不红在断言 —— 如实记，不当成"没咬到"） | sha 相等 |
| K5 假修复刀：走边界失败但仍能跑 | `read_postgres` 改回 `import psycopg` + `with getattr(psycopg, "connect")(url) as conn:` | **2** | `…::test_read_postgres_opens_its_connection_through_the_boundary`、`…::test_the_boundary_call_is_not_concealed_behind_dynamic_eval_or_strings` | sha 相等 |

三处值得单独记账的读数：

- **K1/K4a 的对照说明这五枚钉不是装饰**：K1 之下腿件自己照样交回 `4 passed + 1 xfailed`，K4a 之下
  它照样交回 `1 xfailed` —— 摘掉 strict、或把标记降级成运行时调用，**在门的摘要里都读不出来**，
  只有形状钉看得见。这正是"永久红"与"哑刀"两种失效各自的解药。
- **K3 是双保险**：今天真绿的那枚登记账被挂上 strict xfail 之后，它自己就以 `XPASS(strict)` 变红，
  所以就算有人绕过本班的形状钉，腿件本身也会红一次。
- **K5 打的是尺子的盲区**：同一把刀下再跑尺子，它交回 `14 failed / 19 passed` 且清单里 r387 命中 `0`
  —— 棘轮的形状表覆盖 `psycopg.connect(...)`、别名、`from psycopg import connect` 与"只引用不调用"，
  但不覆盖 `import psycopg` + `getattr(psycopg, "connect")(url)`。所以 §8.1 那格不能只靠"少一枚"交差，
  本班另钉四条它扫不到的路：动态求值/动态导入、自己 import 驱动、非 docstring 字符串里出现驱动名、
  `getattr/setattr` 按名字取 `connect`。

### 8.5 本班交付件字节口径（R390 现取；对照 §7 同名行 —— 旧行留作历史，不作废不删）

| 交付件 | sha256 | size | CR | LF | 裸 LF | U+FFFD | BOM | 对比 §7 |
|---|---|---|---|---|---|---|---|---|
| `scripts/r387_label_lineage.py` | `b304bf2090f6a6c6fee6b302bc1493395d501497d5dcc0b9df21ca5fa900c2cf` | 45351 | 856 | 856 | **0** | **0** | 无 | 改（8.1 走边界 + 8.8 派生化） |
| `tests/test_r387_production_label_leg.py` | `1033c4fa1fa7290b740128318b36b09596b41b74abe3d8bb58900643e2dbe645` | 12732 | 242 | 242 | **0** | **0** | 无 | 改（8.2） |
| `tests/test_r390_xfail_strict_and_boundary_pins.py` | `f7314e77d30a86692ed594d30da67cb23de6038635154b0ca4da6d223756752d` | 18561 | 389 | 389 | **0** | **0** | 无 | **本班新增** |
| `tests/test_r387_label_ruler_teeth.py` | `c953b063faaf6dcf4c1213e49dc25c5603f5f9b58d0298fc83681d675b3006f0` | 27859 | 511 | 511 | **0** | **0** | 无 | 改（8.8：±6 容差换成派生硬牙；**不再与 §7 比字节**） |
| `scripts/r387_backfill_estimate.py` | `63e7516bc210bbd9a30f29e24dc9760270331d45b4a0304e57f79ddac54dafb1` | 7100 | 148 | 148 | **0** | **0** | 无 | **与 §7 逐字节相等**（本班零改动） |
| `docs/perf/r387-label-lineage-2026-09-27.md`（本文档） | 追加本节后再现取，见下 | — | — | — | **0** | **0** | 无 | 追加一节 |

本文档自己的哈希与尺寸不写进本文档（一枚文件装不下自己的哈希，也量不到自己改完之后的那一寸）：
总控按 §7 那枚复算命令现取一次即可。本班只保证**形状**与 §7 同口径 —— 纯 CRLF、裸 LF = 0、
无 BOM、U+FFFD = 0；追加完 §8 之后的 size / CR / LF / sha 见回执 §交付件哈希，不写成文档里一枚一改就漂的数。

复跑（逐枚点名带路径，🔴 不裸跑全树、不出全量门）：

```powershell
$py = "C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe"
cd C:\Users\fengx\PycharmProjects\be-r390
& $py -m pytest tests/test_r387_label_ruler_teeth.py -q                       # 43 passed
& $py -m pytest tests/test_r387_production_label_leg.py -q -rsx               # 4 passed, 1 xfailed
& $py -m pytest tests/test_r390_xfail_strict_and_boundary_pins.py -q          # 11 passed
& $py -m pytest tests/test_r238_bare_connect_ratchet.py -q                    # 33 passed（基点 64b3f3c 起主树已清红）
& $py -m pytest tests/test_r346_line_ledger_is_derived_not_copied.py -q       # 35 passed
& $py -m pytest tests/test_r302_docs_utf8_guard.py -q                         # 8 passed
```

### 8.6 本班没做到的格子（如实列，不销）

1. **`read_postgres` 那一腿没做真库端到端往返。** 宿主直连生产 PG 仍必 `password authentication failed`
   （本班复现了 R387 记过的那发：换成 `POSTGRES_PASSWORD` 也一样，`enterprise_brain` 与 `postgres` 两个
   用户都试过），而派工词明令读生产一律走 `docker exec -i … psql`、不许动容器 ⇒ 本班没有为了量这一格
   去容器里落文件、传脚本。替这格作证的是另外三件：`--no-db` 全量 A/B 逐字节相等、驱动源码那两行
   begin 语句、以及生产库上 `BEGIN READ ONLY` + `SET` 的真实读数。**真库往返请下一格在授权的容器内
   读法下补一次** —— 它证的是"改完还能跑通并交回同一本账"，本班只证到了"改完字节不变、且尺子看不见它"。
2. §4.3 那两处计划书回填仍是总控写域，本班一字未动。
3. 尺子红 14 枚这件事本班不治（R389 在治），也没有为变绿去动那枚尺子或它的基线表。
4. **没跑 `scripts/run_gate.py` 全量门**（派工词明令总控并树后统一出闸）；§5.1/§7 的作废只在本节里
   另记现读，没有回改计划书或功能文档。
5. 刀 K1/K2/K3/K4a/K5 的红数是在**同一份会话**里逐把跑出来的；K4b 之外每把刀都同时跑了形状钉与腿件，
   K4b 只到收集期就停了（语法不允许），所以那一把没拿到"下牙件"的对照读数。

### 8.7 R390 续班：并树前重锚（基点 `b498c88` → `a331d54`）

本班第一次交回的行号是在基点 `b498c88` 上现读的；主树其后并了 R381 / R386 / R389，被引文件里四枚动了形状：
`app/api/v1/chat.py`（+30/−2）、`app/documents/catalog.py`（+87/−1）、`app/rag/pg_store.py`（+97/0）、
`app/api/v1/auth.py`（+20/−6）。⇒ 下牙件 `test_lineage_anchor_token_still_sits_at_the_cited_site` 在新基点上
量出 **4 failed / 32 passed**（第 1 / 2 / 5 / 7 跳读不出凭据）—— 它就该在这时候咬，这一口不是它的假红。
本节把这批行号重锚到新基点：**只动数字与区间描述，12 跳的语义主张一字未改**（第 2 跳仍指服务端覆盖那一格，
第 7 跳仍指 `INSERT INTO document_versions` 那一格）。

- **重锚方式是内容锚定，不是加减偏移**：取旧行原文在新树里唯一定位，再与 difflib 的位置映射交叉核对。
  照偏移算是必错的 —— `chat.py` 同一条链上有两段不同增量（区间起端那一段 +18、更靠后的那一段 +28）。
  🔴 这条自守今天升级为**一律不许手取**：见 §8.8，行号改由锚块派生。
- **未漂移的引用逐枚现读、逐枚同值命中，故一字未改**：`app/common/authorization.py:34`、`app/agents/contracts.py` 旧 `:38`→派生今值 `:39`（那一枚站点语义一字未动，只是 R535 `7c798e4` 在它上方新插一行 import 把它顶下一行）、
  `app/common/auth.py:434-442`/`:445-464`/`:455-456`/`:727-754`、`app/rag/indexing.py:938-939`/`:990-999`/`:1001-1018`/`:1275`/`:944`/`:969-981`、
  `app/rag/retriever.py:1323-1324`/`:1363-1367`/`:1365`、`app/rag/filters.py:119-128`/`:130-145`/`:135-139`、
  `frontend/src/components/DocPanel.vue:647-648`/`:649-650`、`migrations/0010_pgvector_chunks.sql:141`/`:163-164`/`:374-375`/`:387-388`/`:396-400`、
  计划书 `:77-83`/`:99`/`:360`/`:379-381`/`:442-448`（那 19 行新账全加在文件尾部）。`pg_store.py` 只漂了 404 行以后：
  `:87-99`/`:305-404`/`:373`/`:638` 同值未改，`:665-750`→`:705-790`、`:698-700`→`:738-740`。
- **一处区间长度变了（本节唯一一处区间描述）**：`app/documents/catalog.py:626-698` → `:692-766`，旧 73 行 / 新 75 行，
  整窗匹配零命中 = 真改写而不是搬家。窗内只多两行：`:732-733` 那支 `_require_ready_store("version record")` 与它的注释；
  `:769-770` 的 `_schema_needs_migrations` 分支落在终点之外。区间端点仍取同一格 —— 起点 `def record_document_version(`，
  终点 `conn.execute(...)` 的收尾括号（旧 `:698` / 新 `:766`），凭据 `INSERT INTO document_versions` 现读在 `:746`。
- **表与脚本同批**：§1 那张血缘表与 `LINEAGE_HOPS` 的 site 串逐枚等值（脚本 12 跳的 cite 集 ⊆ 文档同行 cite 集；
  文档多出的内层 cite `:1041` / `:1052` / `:644` / `:743-745` / `:759` 按同一张映射表取）。改一头留一头就是给下一班埋第二把假尺。
- **历史读数不随重锚改**：§8.1 那条「改前 `scripts/r387_label_lineage.py:358`」与 §8.4 刀 K4b 那条「leg `:168`」是当时那一次的
  输出原文，按本节开头那条自守（不改写已交回的读数）原样留。
- ~~`tests/test_r387_label_ruler_teeth.py` 本班零改动~~ **本节这条已被 §8.8 作废**：那枚「记法示例」里的
  字面量（旧第 6 跳真身那一串）今天随派生口径一并剥除，本件改成**一枚字面量都不许有**（自扫钉
  `test_the_ruler_and_the_tool_carry_no_literal_line_numbers`）；§8.5 表里「teeth 与 §7 逐字节相等」那一格
  同时换成「派生自证」—— 比的不再是字节，而是这两枚件里读不读得出一枚抄来的行号。
- 另两处随基点变的**自指事实**（不是判据，是「在哪棵基点上量的」这本账）：脚本里那枚
  `ANCHOR_BASE_COMMIT` 今天随锚重挖改指 `64b3f3c`（锚块是在这一枚基点的内容上挖出来的）；§8.5 复跑块里
  那行 `cd` 指 `be-r390`。

---

### 8.8 R390 再续班：行号从「抄来的字面量」换成「派生读数」（锚块基点记在 `ANCHOR_BASE_COMMIT`）

§8.7 那一次重锚交回后，主树又并了 R391：它在 `app/api/v1/chat.py` 里 `+10 -0` ⇒ 那之后的每一枚行号整体 +10，
而下牙件的容差只有 ±6。主树复跑量出 **3 failed / 33 passed**（第 1、2、5 跳；旧件一共 36 枚，那是「±6 容差」钉时代的形状）。这一回不再手取第三次行号 ——
`b498c88 → a331d54 → 64b3f3c` 已经漂两次，第三次照抄是同一枚坑的第三次踩法。

- **病因不是读错，是抄。** 把两次的值机器对机器比一遍（旧值：把同一批锚块拿到 `git cat-file blob` 取回的旧内容上重解，
  不是照偏移换算），漂的一共 12 枚锚、全在 `chat.py`、全在插入点之后：`hop1 4060-4062→4070-4072`、`hop2 4078→4088`、
  `hop2n 4070-4074→4080-4084`、`hop5f 4061→4071`、`hop5g 4206→4216`、`hop5h 4220→4230`、`hop5i 4234→4244`、
  `hop5j 4309→4319`、`hop6 3644-3718→3644-3728`、`hop8 3765-3813→3775-3823`、`hop10 4202-4208→4212-4218`、
  `hop10d 4207→4217`；其余 34 枚同值未变 ⇒ 表上只有 6 行（跳 1/2/5/6/8/10）的第 3 格随派生重落地，
  **语义主张一字未动**：第 2 跳仍指服务端用 `principal.department` 覆盖接口形参那一格、第 7 跳仍指
  `INSERT INTO document_versions` 那一格。
- **行号只能活在一处 = 锚块。** `LINEAGE_SITES` 46 枚锚（`key -> (文件, (偏移, 若干行原文), 终点锚或 None)`），
  `rg -F` 语义：逐行 strip 后连续固定串匹配，不是正则。`LINEAGE_TEMPLATES` 与 `HOP_DOC_CELLS` 里只留 `{hopN}` 占位符，
  运行时由 `resolve_cites()` 渲染成 `LINEAGE_HOPS` / `LINEAGE_DOC_CELLS`。这两枚件里今天读不出任何一枚
  「文件名 + 冒号 + 数字」的字面量 —— 由自扫钉逐行端出「第几行 + 那一行的前 72 字节」，不是文案 grep。
- **不许回落成「取第一次命中」。** 命中 0 枚 = 锚已腐、命中 ≥2 枚 = 不再是唯一锚，两条路都不给出数：`_one_hit` 抛
  `AnchorNotUnique`，`resolve_cites()` 收进 `LINEAGE_ANCHOR_FAILURES`，`main()` 在连库**之前**端出 `ABORT …` 并
  `return 3`（K-b 现场把那枚锚的名字、文件、命中行号一起打了出来）。并树往中间插一段长得像的代码是常事，
  那时候取第一枚等于把整条血缘表指到别人身上 —— 比红更糟。
- **多 site 那一族不再只咬第一格。** 上一班 §5 自陈「后几格实际上没被牙咬住」：跳 5 的后四格、跳 6/7/10/12 的内层格
  当时没有自己的凭据。现在每一格各配一枚锚（`hop5g…hop5j`、`hop6c`/`hop6n`、`hop7c`/`hop7d`/`hop7e`、`hop10d`/`hop10e`、
  `hop12c`/`hop12d`/`hop12e`），三条钉死：同一枚锚在同一格模板里只许出现一次、同一跳各格解出的行号两两不同、
  表里锚数不低于该跳应有的格数（`MIN_TABLE_CELLS = {5: 5, 6: 4, 7: 5, 10: 3, 12: 3}`）。
- **两条硬牙换掉 ±6 容差。** `test_lineage_site_is_derived_and_matches_the_doc_table`：(a) 量具 import 期的缓存 ==
  本件现场重解的值（缓存过期也红）；(b) 表里印的那一格 == 现读渲染出来的那一格，红句直接端出「表里印 X、现读 Y，
  改表只有一处可改」；(c) 这一跳引用的每一枚锚（site + note + 表三处并集）在被引文件里恰一枚命中。另加三枚闸：
  全局锚失效闸、死锚与幽灵锚互覆闸、**表下正文闸** —— 人写的正文里那几枚行号也只许写现读值；这一枚落地当天就咬出
  §1 正文里那枚过期的 `chat.py` 引用（旧值比新值少 10），并顺手把一枚裸引用补上文件名让它受检。
- **重落地那条腿是脚本，不是手。** `python scripts/r387_label_lineage.py --emit-doc-cells` 打印 12 行「序号 TAB 站点格」；
  锚一腐它 `rc=3` 且一行数都不出。表与脚本从此只能同批改。

四把刀（逐把进/出按字节复原并自证 sha 相等；夹具是临时件 `%TEMP%\r392_knives_all.py`，不入树）：

| 刀 | 改哪几字节 | 红几枚 | 具名红件全路径 | 复原自证 |
|---|---|---|---|---|
| K-a 手改表里一枚行号 +1 | §1 表第 9 跳那一格末号 +1 | **1** | `tests/test_r387_label_ruler_teeth.py::test_lineage_site_is_derived_and_matches_the_doc_table[9]`，红句原文端出「表里印 …`:1276`、现读 …`:1275`」 | 本文档字节相等（哈希见回执；一枚文件装不下自己改完之后的那一寸，见 §8.5 末段） |
| K-b 一枚凭据变成两枚命中 | `migrations/0010_pgvector_chunks.sql` 里把 `COMMENT ON COLUMN chunk_vectors.department IS` 那一行再插一份副本（tracked 件，跑完按字节复原） | **3** | `…::test_lineage_site_is_derived_and_matches_the_doc_table[11]`、`…::test_the_prose_under_the_table_quotes_derived_numbers`、`…::test_no_lineage_anchor_is_stale_or_ambiguous`；红句具名到 `hop11n … 命中 2 枚 [163, 164] —— 不再是唯一锚`；`--emit-doc-cells` `rc=3` 并 ABORT | SQL `9bb5993053bb0b1e` 进=出（B=26230） |
| K-c 派生改回取第一次命中 | 量具里摘掉 `if len(hits) > 1: raise AnchorNotUnique(…)` 那三行 | **1** | `…::test_the_deriver_has_no_first_hit_fallback[two-hits]`（`Failed: DID NOT RAISE AnchorNotUnique`） | 脚本 `b304bf2090f6a6c6` 进=出（B=45351） |
| K-d 摘掉多 site 跳的逐格 token | 第 5 跳表模板里 `hop5g`/`hop5h`/`hop5i`/`hop5j` 四格全改回 `{hop5f}`（只咬第一格） | **2** | `…::test_lineage_site_is_derived_and_matches_the_doc_table[5]`（红句端出「表里印 `:4216` / `:4230` / `:4244` / `:4319`、现读四格全是 `:4071`」）、`…::test_multi_site_hops_give_every_site_its_own_anchor` | 脚本 `b304bf2090f6a6c6` 进=出 |

副本列的取证法换过一趟：本班第一次是按旧派工词「临时把六枚拷进主树」跑的，总控随后改口径
（「别把件拷进主树」，两棵树并树会互相踩踏）⇒ 本节交回的读数改用 `git archive` 从主树 HEAD 导出**只读副本**再跑，
本班对主树只发过 `git log` / `git diff` / `git rev-parse` / `git status` / `git archive` 五枚只读命令，主树零写入：

```powershell
git -C C:\Users\fengx\PycharmProjects\企业智脑 archive --format=tar 3337f9a -o %TEMP%\r390_head.tar
# 导出 1211 枚文件到 %TEMP%\r390_head（副本里没有 .git），跑完整个删掉
```

两棵树之间被引文件的真实差（逐枚 sha256 前 8 与行数现取，不是照偏移换算）：

| 被引件 | `64b3f3c`（本班基点） | `3337f9a`（主树现读） | 行数 | 形状 |
|---|---|---|---|---|
| `app/api/v1/chat.py` | `1a4839d7` | `1a4839d7` | 4828 → 4828 | SAME（R391 那 `+10` 已落在本班基点之内）|
| `app/documents/catalog.py` | `f0b84e26` | `4cd0addb` | 906 → 906 | **DIFF**：R394 改写 16 行、行数中性（`:362`/`:371-373`/`:393`/`:396-402`/`:769-771`）|
| 另 12 枚被引件（`common/auth.py`、`api/v1/auth.py`、`common/authorization.py`、`agents/contracts.py`、`rag/{indexing,retriever,filters,pg_store}.py`、`migrations/0010_pgvector_chunks.sql`、`frontend/src/components/DocPanel.vue`） | — | — | 逐枚等值 | 全 SAME |
| `app/memory/profile.py`、`app/memory/long_term.py`（**本班未引用**） | `aadb43e7`/`923ff9ea` | `f491bd7d`/`d6193721` | 245→288 / 218→259 | DIFF（+43/+41 行的活体撑长）|

三格并排读数（同一批字节，主树 venv，逐枚带路径）：

| 读数 | `be-r390` @`64b3f3c` | 只读副本 @`3337f9a`（主树零写入） |
|---|---|---|
| **旧字面量版** teeth（上一班那三枚：脚本 `f2b842a9…` + teeth `12ae1f85…` + 文档 `5df47273…`，site 里写死 `chat.py:4060-4062`、`:4078`、`4061 → :4206/:4220/:4234/:4309`） | 在 `a331d54` 上当时刻全绿（36 passed） | 🔴 **3 failed / 33 passed**（红在第 1、2、5 跳） |
| **派生版** teeth（本班交付件 `c953b063…`） | **43 passed · 0 failed** | **43 passed · 0 failed** |
| 75 枚锚块唯一命中普查（46 格 × 起/终点） | 命中 ≠1 的锚 = **0**，`LINEAGE_ANCHOR_FAILURES = []` | 命中 ≠1 的锚 = **0**，`LINEAGE_ANCHOR_FAILURES = []` |
| `--emit-doc-cells` 逐格现读 | rc=0 · 12 行 | rc=0 · 12 行 · **与左列逐字符相等** |

旧字面量版那三行红句原文（副本现跑，逐字）：

```
AssertionError: 第 1 跳（app/api/v1/chat.py:4060-4062）在 ±6 行内读不出凭据 'department: str = Form'：被引文件的形状已改，本单的行号必须重取
AssertionError: 第 2 跳（app/api/v1/chat.py:4078）在 ±6 行内读不出凭据 'department = str\(getattr\(principal,'：被引文件的形状已改，本单的行号必须重取
AssertionError: 第 5 跳（app/api/v1/chat.py:4061 -> :4206 / :4220 / :4234 / :4309）在 ±6 行内读不出凭据 'classification: int = Form'：被引文件的形状已改，本单的行号必须重取
```

其余五枚点名件在同一条副本里的读数：leg `4 passed + 1 xfailed`、nails `11 passed`、棘轮 `33 passed`、
r346 `35 passed`、r302 `8 passed` —— 与本班树逐枚同值。

⇒ 这一格交的是「抄来的行号必被后续并树打红」的**现行**证据：同一棵 `3337f9a`，旧字面量版红 3 枚、
派生版绿 43 枚，两棵树的派生读数逐字符相等。另算第一次吃到「**内容被改写**而不是被搬家」的活体考验：
`app/documents/catalog.py` 被 R394 就地改写了 16 行（改写点落在第 7 跳区间之外、行数不变），
75 枚锚仍逐枚唯一命中 —— 若哪天改写正好落进锚块原文，命中的是「锚已腐 = 0 枚命中」那一格，
它要求下一班**重挖锚块**，不是调容差（本件已无容差这个旋钮）。

派工词与本树现读的差（铁规第 6 条：以现读为准并写明漂移）：

- 派工词写「主树 HEAD `64b3f3c`」，本班现读主树已进到 **`3337f9a`**：其后又并了 `3a5f25f`（改口账）、
  R393 `f509f36`、R394 `ae2fbb4`、R392 `3337f9a` ⇒ **总控派工词该行号已漂移**（漂的是基点指针，不是行号）。
  派工词写「副本里期望 36 passed」，本班现读派生版 **43 枚**（同一枚漂移，见下一条）。
- 派工词期望 teeth「36 passed」，本班现读 **43 枚**：36 是「±6 容差」时期的形状，本班把那 12 枚容差钉换成 12 枚逐跳
  派生钉，另加三枚闸（全局锚失效、死锚互覆、表下正文）与两枚 fallback 参数。枚数涨 7，主张只多不减。
- 派工词贴的红句里那枚具名件 `test_lineage_anchor_token_still_sits_at_the_cited_site` 在本班已**不存在**：它就是被
  换掉的那枚 ±6 容差钉，继任者是上面那 12 枚逐跳派生钉。
- 第 4 跳那两枚 `app/common/auth.py` 的锚（`hop4a`/`hop4b`/`hop4n`）逐枚现读、逐枚命中 1 枚，值未变（不是沿用旧数）。
- 🔴 **别拿本文档的历史块当今天的期望值**：§5.1/§5.2/§5.4 与 §8.2 里那些「36 passed」「仍红 14」是 R387/R390
  当时那一次的读数，按本文档"读数不追溯改写"的自守原样留着；今天的账只有 §8.5 复跑块与本节的两棵树并排读数。
  棘轮从「红 14」到「33 passed」是 R389 并树的功劳，不是本班改出来的 —— 本班碰那枚尺子一次都算事故。

本班没做到的格子（如实列，不销）：

1. **锚块仍是"某一次基点的内容"**：46 枚锚是在 `ANCHOR_BASE_COMMIT` 那一枚基点的内容上挖出来的。若下一枚并树
   **改写**某一格的原文（不是插入、不是搬家），那枚锚就命中 0 枚 ⇒ 表与脚本一起红 —— 这是设计要的报警，不是缺陷，
   但它要求下一班**重挖那一枚锚**而不是调容差：本件已经没有"容差"这个旋钮可调了。
2. `ANCHOR_BASE_COMMIT` 只是出处账，没有任何一枚钉拿它当判据（判据全在现读命中上）。把它钉成"等于 `git rev-parse HEAD`"
   会造出一枚假绿发生器（工作树随时 dirty 就永远不等），故没做。
3. §2–§7 正文里那批**不自称现读**的行号仍是历史账（§1 表旁已写明），本班没逐枚回填。本班当时那句「受检的只有 §1 表 + §1 表下正文」
   到 09-29 已过期，R493 按实物把它改写成这张清单（受检面的唯一事实源，别处只许指过来、不另抄第二本）：§1 表＝teeth 逐跳钉；
   §1 表旁正文＝teeth 正文闸；§9.3 最后一列＝R492 逐格钉；§3 方案 A 与 §8.7 凭据那两格＝R490；§9.5 那块 R409 计划表＝
   `r387_backfill_estimate.py --no-db --verify-plan-table` 逐字节；**其余每一枚带「现读」字样的坐标（无主区段也算）＝R492 边界闸，
   对不上派生值即红，且欠账名单已清零**。不受检的只剩丙类：不带那三个字的历史读数，它们按定义不再声称今天的形状。
   ⚠ 这一族里还有一格 R493 没治：§3 段末那句用「今天」引出的那枚坐标，两枚闸都看不见它（闸只认「现读」两个字），
   详情与哨钉见 §9.8 第 ⑤ 格。
4. `pyproject.toml` 里 `xfail_strict = true` 仍只报不改（全局开关归总控裁，仓里裸 `@pytest.mark.xfail` 得逐枚看）。
5. 真库端到端往返那一格仍未做（§8.6 第 1 格原样挂着，本班一个字节都没碰它）。

---

## 9. R400 接管：第二令的真实落地状态、独立复跑、两把刀、回填账（2026-09-27 三度续班）

写域与基点：`be-r400` @ **`6a8063a`**（开工 `git status --porcelain` 空、`rev-list --count 6a8063a..HEAD` = 0），
解释器主树 `.venv`，逐枚点名件带路径单跑。取证只走 `docker exec -i enterprise-brain-postgres-1 psql`
一条道：全程 `SET default_transaction_read_only = on` + `BEGIN/COMMIT`，零 DDL、零 DML、零写生产库，
一个字节都没碰 `chroma_db/**`，没读 `.env`/`deploy/**`，没取过 DSN。
所有变异打在 `git archive 6a8063a` 导出的临时影子副本（`%TEMP%\r400\*`）与 `tmp_path` 上，盘上树零写入。

### 9.1 先纠一笔账：派工词说"第二令零落地"，实测是"基本已落地"

`be-r390` 那六枚原件的最后落盘时刻（本班现取，不是推断）：

| 件 | mtime | 与派工词"21:19 之后再无写入"的关系 |
|---|---|---|
| `scripts/r387_backfill_estimate.py` | 09-27 18:07 | 早于第二令 |
| `tests/test_r390_xfail_strict_and_boundary_pins.py` | 09-27 18:49 | 早于第二令 |
| `tests/test_r387_production_label_leg.py` | 09-27 19:03 | 早于第二令 |
| `tests/test_r387_label_ruler_teeth.py` | 09-27 **20:41** | 第二令的派生化版（±6 容差已换成逐格锚） |
| `scripts/r387_label_lineage.py` | 09-27 **21:19** | `LINEAGE_SITES` 46 枚锚已在位 |
| `docs/perf/r387-label-lineage-2026-09-27.md` | 09-27 **21:22** | §8.8 整节已写完（含四把刀与两棵树并排读数） |

⇒ 第二令**不是零落地**：行号派生化（本文档 §8.8）与那三枚件的字节都在树上。失联发生在派工词写下来之后、
交接账写下来之前，所以派工词按"最后一次回执"取的状态是旧状态。本班据此把"接管重写"改成
"**逐枚自己重跑重验 + 只补真正没做的三格**"，没有把已到位的 46 枚锚推倒重来（那才是浪费）。
前任草稿一律按非该线自证处理：下面每一枚读数都是本班在 `6a8063a` 上现跑的，没有一条抄自 §7/§8。

### 9.2 六枚草稿的处置（沿用/改写字节 + 本班复跑读数）

| 件 | sha256 前 16 | 处置 | 本班在 `6a8063a` 的复跑读数 |
|---|---|---|---|
| `scripts/r387_label_lineage.py` | `b304bf2090f6a6c6` | **逐字节沿用**（本班零改动） | 46 枚锚逐枚唯一命中，`LINEAGE_ANCHOR_FAILURES = []`；`--emit-doc-cells` rc=0 |
| `scripts/r387_backfill_estimate.py` | 改前 `63e7516bc210bbd9` → 改后见 §9.5 | **改写**（加 `unlock_ladder` / `render_ladder` / `--unlock-ladder` / `--classification-kinds`，判序仍 import 量具那一枚） | 计划账逐格同值（74/923、26/85、11 枚部门），梯级表 S0–S6 rc=0 |
| `tests/test_r387_label_ruler_teeth.py` | `c953b063faaf6dcf` | **逐字节沿用** | **43 passed / 0 failed** |
| `tests/test_r387_production_label_leg.py` | `1033c4fa1fa7290b` | **逐字节沿用** | **4 passed + 1 xfailed**（容器 `Up (healthy)` ⇒ 走真断言，不是 skip 分支） |
| `tests/test_r390_xfail_strict_and_boundary_pins.py` | `f7314e77d30a8669` | **逐字节沿用** | **11 passed** |
| `docs/perf/r387-label-lineage-2026-09-27.md` | 见 §9.5 | **续写本节**（§1–§8 一字未改，含 §2.3 那枚过期数按纪律原样留） | §1 表 12 行与现读逐格等值（由 teeth 逐跳钉） |

三枚点名件合跑：**58 passed / 0 failed / 1 xfailed**（派工词期望的"36 = 18 + 18"两头都不是今天的形状：
36 是「±6 容差」时期的枚数，本班实测 teeth 43 + leg 4(+1 xfail) + nails 11 = 58(+1)）。

### 9.3 三处手抄行号账现在各由哪一枚锚负责

改法与 `00945a9`（R346）同源：行号只在运行时由**唯一锚块**（符号名 + 符号内唯一语句形状，逐行 strip
后的连续固定串）现读；`LINEAGE_TEMPLATES` / `HOP_DOC_CELLS` 里只留 `{hopN}` 占位符；文档表里那格由
`--emit-doc-cells` 重落地。🔴 r346 与 r238 两枚件本班一个字未动。

| 派工词点的病 | 现在的锚（key） | 锚首行 token（唯一命中，逐枚现读） | 本班现读＝左列锚 key 经 `resolve_site` 现场派生（R492 钉逐格对账，漂一枚即红） |
|---|---|---|---|
| 服务端强制覆盖那一格（旧账冻在 `3656..3719`） | `hop2` | `department = str(getattr(principal, "department", "") or "")` | `app/api/v1/chat.py:4524` |
| 同一格的 docstring 理由段 | `hop2n` | `The document scope is decided here rather than accepted from the form: retrieval` | `:4516-4520` |
| 接口形参默认值那一格（旧账冻在 `3644..3719` 起端） | `hop1` | `async def upload_document(file: UploadFile = File(...),` → `department: str = Form(""),` | `:4506-4508` |
| 密级下传那四格（旧账冻在 `1534..1620` 一族） | `hop5f` `hop5g` `hop5h` `hop5i` `hop5j` | `classification: int = Form(1),` / `classification,`+`department or None,` / `if ok:` 起六行块 / `classification=classification,`+两行 / `classification=classification,`+`department=department,`+`scope=…` | `:4507` / `:4652` / `:4666` / `:4680` / `:4755` |
| 目录账区间（旧账冻在 `748..763` 那格） | `hop6` + `hop6b`/`hop6c`/`hop6n` | `async def upload_document…` 区间终点 / `INSERT INTO documents(` / `department or None,` / `_version_metadata` 收尾 | `:4080-4164` → `:1124-1159`（`:1142` / `:1153`） |
| 部门名册那一格（`list_user_departments`） | 🔴 **本单 46 枚锚里没有它** | 全仓 `app/**` 读不出这个符号（见 §9.6 落空账） | — |

同一文件的多个站点**逐格一枚锚**（不共用），并由 `test_multi_site_hops_give_every_site_its_own_anchor`
钉三条：同一枚锚不许在同一格里冒充两格、同跳各格解出的行号两两不同、表里锚数不低于该跳应有的格数。

### 9.4 两把刀（影子副本道，盘上零写入）

被引文件在 `64b3f3c → 6a8063a` 之间的真实差：`git diff --stat 64b3f3c HEAD -- <12 枚被引件>` = **空**
⇒ 表里那批派生读数今天不需要重落地（这是现读，不是照偏移换算）。

**K1 插行**（`app/api/v1/chat.py` 顶端插噪声行，副本按字节复原；副本进出的 `chat.py` sha256 前 16
= `1a4839d70e4a4fb2`、4828 行、B=237292，主树与本树全程未动）：

| 口径 | 插 1 行 | 插 500 行 |
|---|---|---|
| 旧「±6 容差 + 手抄行号」版 | 🔴 **静默过关**（漂移 ≤ 6 行全放行，表里那批数已经错着同样多行而门是绿的） | 红（越过容差才终于报） |
| 派生版 teeth（沿用件 `c953b063…`） | 7 failed / 36 passed：跳 **1/2/5/6/8/10** 各红 + 表下正文闸红；每一枚红句同时端出「表里印 `…:4070-4072`、现读 `…:4071-4073`」与那一跳的编号 | 46 枚锚仍逐枚唯一命中；`chat.py` 那些 cite 全体 +500、非 `chat.py` 的一字不变（常驻化在 `tests/test_r400_derived_ledger_shift_and_silence_pins.py`） |
| 派生版 + 一次 `--emit-doc-cells` 重落地 | **6 行表体自动跟上**，重跑 1 failed / 57 passed + 1 xfailed —— 剩那一枚是**人写的正文**（表下正文闸），它当场点名过期引用并给出现读值 | 同左 |
| 全局锚闸 `test_no_lineage_anchor_is_stale_or_ambiguous` | 绿（锚没腐，只是搬家 —— 这正是派生与手抄的分界） | 绿 |

⇒ 这族对照不是回忆，是常驻牙：`test_a_tolerance_ruler_lets_a_small_drift_pass_while_the_table_lies`
拿真锚、真影子跑 drift = 1/3/6/7/10 五档 —— 容差口径前三档**全部放行**（表已在说谎）、后两档才报；
派生口径五档**全部看见**（且锚仍逐枚唯一命中）。

⇒ 与派工词期望的差一格，写清楚：派生版在插行后**不会**"仍全绿"，因为 §1 表里印的是给人读的行号，
表与现读不等就是账不真，这枚牙必须咬。派生化的收益不是"插行永不红"，而是 ① 红只落在真受影响的
那几跳（不跨文件传染、不整表陪红）、② 红句直接端出正确的新数、③ 修表是一条命令而不是 12 次人肉
`rg`（上一班 `b498c88 → a331d54 → 64b3f3c` 已经手取过两次）。"仍全绿"要的是**别让表说谎**，做不到的
那一格今天做不到。

**K2 锚点改名**（把锚住的那行代码改属性名，副本道）：

| 读数 | 结果 |
|---|---|
| `LINEAGE_ANCHOR_FAILURES` | 非空，逐条点名 `hop2：… 命中 0 枚（锚已腐，那一格不在原处）：锚首行 'department = str(getattr(principal, "department", "") or "")'` |
| `resolve_site("hop2", 影子)` | 抛 `AnchorNotUnique`，消息含「命中 0 枚」 |
| `main(["--no-db"])` | **rc=3**，stdout **0 字节**（连库之前 ABORT，不带腐锚出账），stderr 点名 `ABORT` + `hop2` |
| `main(["--emit-doc-cells"])` | rc=3；那一格端 `<锚失效:hop2>`，旧数 `4088` 一个字都不出 |
| teeth 单跑 | 5 failed / 38 passed（跳 2 的逐跳钉 + 全局闸 + 正文闸 + 「文件还在吗」+ 多 site 逐格闸） |

⇒ "静默跳过算假绿"这条路按 AST 钉死：`_one_hit` 的两条件抛（`not hits` / `len(hits) > 1`）摘任何一条
都红（`test_the_no_first_hit_branches_are_both_still_there`）；容差/豁免形状的旋钮在量具与逐跳钉里
读不出来（`test_no_tolerance_or_exemption_knob_survives_in_the_ledger_files`）。
同一批真锚上的 drift 1/3/6/7/10 五档对照另见 §9.4 末段。

### 9.5 回填账：A1 / A2 / A3 今天各能落地多少（派工词 §三）

现读凭据（只读 psql，跑前跑后各量一次 `select count(*) from chunk_vectors` = **1008 / 1008**）：

| 量 | 现读 |
|---|---|
| `chunk_vectors` | 1008 枚 / 非空 `department` **0** 枚 / 不同部门 **0** 枚 / 密级档数 **1** / 文档数 100 |
| `chunks`（发布账） | 1008 枚 / 非空 0 枚 ⇒ 两本账**一致地空**（病灶不在镜像复制那一跳） |
| `documents` | 3/105 枚非空 —— 那 3 枚的部门值 = `R8甲部`（R8 探针遗留名，不是客户部门） |
| `document_versions` | **0**/100 枚非空 |
| `resource_versions`（document） | 3/129 枚带 `department_ids`（同一批探针） |
| `users` | 3 枚账号里 **1** 枚有部门：`dataowner`(staff)=`财务部`；`admin`(admin)、`evalbot`(admin) 均空 |
| 上传账（`documents.owner_id`） | `admin`=**101** 枚、`r8-probe-a`=3、`browser-e2e-rv`=1 ⇒ **唯一带部门的那枚账号上传了 0 枚文档** |
| 磁盘侧 | `/app/documents` 里显示文件名只活在目录账里（`chunk_vectors` 无 `owner_id` 列，0010 那句 COMMENT 的口径） |

规则回填量（`scripts/r387_backfill_estimate.py --no-db --names-file <只读 psql 导出的 100 枚 (显示文件名 -> chunk 枚数)>`）：

| 桶 | 文档 | chunk |
|---|---|---|
| 文件名只指向唯一一枚部门（可规则回填） | **74** | **923** |
| 文件名指向多枚部门（必须人工裁决） | 10 | 28 |
| 文件名不给任何部门线索（必须人工裁决） | 16 | 57 |
| 合计 | 100 | 1008 |
| 规则可达部门 | 11 枚（人力资源/信息安全/审计/市场/法务/研发/经营层/行政/财务/采购供应链/销售） | 最重一格 **研发 17 枚文档 / 713 枚 chunk** |

🔴 更正一笔（不改 §2.3 原文，按"读数不追溯改写"另记现读）：§2.3 写的是「研发 721」，本班同一份
量具现跑 = **713**。这正是"抄来的数"的病：那一格没有锚、也没有牙，抄一次就永久定格。所以本班把
这本账改成可复跑的梯级表（`unlock_ladder()` + `--unlock-ladder`），文档只抄判词，因果由量具现给。

**验收 C 解锁梯**（`--unlock-ladder` 现跑；判词一律出自 `classify_arm`，标「推演/假想」的行不是测量结果）：

| 级 | 动作 | 挪开了什么 | 判词（现跑） |
|---|---|---|---|
| S0 | 今天：零动作 | — | 未验 —— 语料的 department 全为空：部门谓词恒空集，「越权 0 条」只在空集上成立 |
| S1 | **+A1** 业主补 `users.department` | 只影响**以后**的上传：服务端在上传那一跳覆盖，存量 1008 枚一字不动 | 未验 —— **同 S0，逐字不变** |
| S2 | **+A2** 上传时拒收空部门（422 `department_scope_required`） | 止住新增漏标 | 未验 —— **同 S0** |
| S3 | **+A3** 按文件名规则回填部门（923 枚 / 11 部门） | (b) 的部门半边 | 未验 —— 语料只有一档密级：没有跨密级可选 |
| S3b | +A3 之外再把人工裁决那 85 枚也批了 | 覆盖率 923→1008 | 未验 —— **同 S3，判词不动** |
| S4 | +密级也回填（业主逐档定密） | (b) 的密级半边 | 未验 —— 该臂交回 0 行：0 越权与 0 召回是同一个空集，不是隔离 |
| S5 | +在生产真标签上重跑四臂（召回非空、零越权） | (c)(d) | 已验（**假想行：要真测，本单不起服务、不打模型**） |
| S6 | 同 S5 但量出越权 | — | 不通过（有越权）—— 优先级压过一切未验理由 |

三格答案：

1. **A1 今天能落地多少**：账号侧 2/3 枚（`admin`、`evalbot`）待补，写口只有 `PUT /api/v1/users/department`
   （需 `users:manage`，员工自助那条明写是只读派生值），`AUTH_DEPARTMENT` 对既有账号**无效**（第 4 跳那条
   空表才 seed 的分支）。**对验收 C 的推进 = 0 格**：它治的是"以后别再漏"，存量那 1008 枚一个字节都不动（S1 行）。
2. **A2 今天能落地多少**：**0 枚存量**，且它是代码动作（`app/api/v1/chat.py` 那一格的拒收分支）——
   在 R400 的禁域里，需要另派一枚单（与 R384 那一族同树，别和施工中的写域撞）。
3. **A3 今天能落地多少**：**923/1008 枚（91.6%）可规则回填**，85 枚（26 文档）必须人工裁决；
   但**回填本身 = 写生产数据 = 业主动作**，本班 `writes_issued=0`，一行都没写。零新迁移：列、默认、
   COMMENT、两枚 prefilter 索引都在 `migrations/0010_pgvector_chunks.sql` 现成（锚 `hop11n` 那句 COMMENT 现读）。
4. **必须业主本人出手那一格**：① A1（写账号真值，需 `users:manage`）② A3 的批准与执行（UPDATE 走"改权威 →
   重发布"，🔴 不许 `UPDATE chunk_vectors` 一处了事，否则目录账与镜像立刻分叉）③ **密级逐档定密**——
   文件名给不出密级线索，这一格没有任何规则可以代劳。
5. **"只回填部门不回填密级"为什么 C 仍未验**：判据 (b) 要**同时**满足"非空标签 > 0、不同部门 ≥ 2、
   不同密级 ≥ 2"。部门那一半边 S3 就满足了，密级这半边生产今天恒 1 档 ⇒ `(b)` 整体不成立 ⇒ 判**未验**
   （S3 行）。把密级抬到 2 档也只是把堵点前移到 `(c)` 召回（S4 行），不是消掉它。⇒ 四件判据在
   A1+A2+A3 全做完之后**仍然**不会自己变绿：最后一格要在生产真标签上重跑四臂，那是 R59 切读之前
   必须由总控排的一轮真测量（要起服务、要打模型，本单一格都不做）。

### 9.6 派工词引用 vs 本班现读（引用 / 命中 / 落空）

🔴 R493 收口一句：本节整节属**丙类历史操作账**（§1 表旁那条自守的第三格今天已把「§9.6 的派工词对照账」点名列在里面）。
标题与最后一列那三个字是 R400 当时的写法，列值一律是**那一班当时的读数**：不随并树核对，也不许拿去派工。要今天的坐标，
看 §1 那张表、§9.3 最后一列，或 §8.8 未做 3 那张受检清单。本节当年唯一一枚写成当下声称的格子（`chat_ask_entry` 那一行）
已按乙案降回丙类——理由、可复跑反证与收口都在本节末尾的 §9.8。

| 派工词引用 | 命中 | 本班现读 |
|---|---|---|
| 基点 `6a8063a`、`dirty=0`、`rev-list=0` | ✅ 命中 | 开工三条命令原文见回执 §① |
| 前任失联、第二令"零落地" | ⚠ 半真 | 人确实失联；"零落地"**不成立**，§9.1 那张 mtime 表与 §8.8 全文为凭 |
| `read_postgres` 已改走 `app/db/connection.py` 边界 | ✅ 命中 | AST 三枚钉仍绿（nails 11 passed）；尺子 `test_r238` 33 passed |
| `xfail(strict=True)` + 形状钉 18 枚 | ⚠ 部分 | 形状在（strict=True、reason 三个关键字、只挂那一枚）；枚数本班现读 **11 passed**，不是 18 |
| 三枚红 = `tests/test_r387_label_ruler_teeth.py:95/:97/:99` | ❌ 落空 | 今天的 `:95/:97/:99` 是文档字符串行，不是三枚红件；红已在 §8.8 那一班被派生化消掉。本班用**唯一还在的旧字面量版**（`be-r387`：teeth `12ae1f85…` + 脚本 `aece11e3…` + 文档 `36511746…`）在只读副本上复跑 = **4 failed / 32 passed**（第 1/2/5/7 跳，红句仍是"±6 行内读不出凭据…行号必须重取"）——比派工词的 3 枚多一枚，因为它比 §8.7 那次重锚更早 |
| `("server_scope_override", "服务端强制覆盖", 3656, 3719)`、今天真身 `3666..3729` | ❌ 落空 | 全仓（四枚在册草稿 + 主树）读不出 `server_scope_override` 与"服务端强制覆盖"这两个 token；今天那一格由锚 `hop2` 现读 = **4088**（终点由 `hop2n` = 4080-4084 那一段 docstring 佐证）。3656/3666 两族数字本单一格都不抄 |
| `("chat_ask_entry", "@router.post("/ask"", 1534, 1620)` | ❌ 落空 | R400 那一班把 `app/api/v1/chat.py` 的这一格读成第 2224 行（基点 `6a8063a`，当时在 `app` 侧唯一命中）；R493 在**同一枚基点的 blob** 上复现过同值，复现已铸成常驻钉（`tests/test_r493_s96_ask_entry_is_history_not_live_claim.py` 现场拿纸面那个数与复现值比）。🔴 此数属丙类历史操作账，**不再随并树核对**：今天那一枚 token 已经不在这一行——这正是它当初不该写成当下声称的证据。今天的行位本单不复述（复述就是再埋一枚拿不到钉的雷），要它照 §9.8 第 ② 格那条复现形现取。这枚 token 至今不在 46 枚锚里（枚数由 `len(LINEAGE_SITES)` 现取，纸面这一句与 §9.3 那一行都由 R493 钉 import 真源对账），血缘链也不引用它：甲案（补锚 46→47）走不通的三条硬理由与可复跑反证在 §9.8 第 ① 格 |
| `("list_departments", "list_user_departments", 748, 763)` | ❌ 落空 | `app/**` 全仓读不出 `list_user_departments` 这个符号（`rg` 零命中）；本单血缘表里部门名册那一格也不引用它 |
| `64b3f3c` 给 `chat.py` 加 +10 行 | ✅ 命中 | 本班以锚现读复核：`hop1` 4060-4062 → 4070-4072、`hop2` 4078 → 4088、`hop5f` 4061 → 4071 等 12 枚全体 +10（§8.8 那张漂移表与今天现读逐格同值） |
| 期望"36 passed（18+18）" | ⚠ 半真 | 本班现读三枚点名件合跑 **58 passed / 0 failed / 1 xfailed**（teeth 43 + leg 4(+1) + nails 11）。枚数与派工词不符这件事按铁规以现读为准，未拿 36 当达标线 |
| 只读通道 `docker exec … psql -tAX`；禁 `printenv`/禁读 `.env`/`deploy/**`/禁拿 DSN | ✅ 遵守 | 全程一条 psql 管道 + 一次 `docker exec`，未取任何凭据；容器内 `python -` 那一腿**没走**（见 §9.7 第 2 格） |
| `chunk_vectors` 跑前跑后 = 1008 | ✅ 命中 | 1008 / 1008（回执 §⑦ 附原文） |
| 主树门红 13 枚、不去修别人的红 | ✅ 遵守 | 未跑全量门；只单跑点名件 |
| `tests/test_r120_p3_collection_default.py:247` 因本文档不在而红，并树后即绿 | ⚠ 半真 | 缺本文档确实是原因之一；同一枚断言今天还堵着两格**通配路径** `tests/test_r330_*`、`tests/test_r377_*`（在总控写域 `docs/handoff/2026-09-17-pgvector-adoption-plan.md` §8 里，正则读不到 `*` 之后的部分）。本文档落盘后该格红句从三缺变两缺（改前/改后原文见回执 §⑧），另两格请总控改写成具名文件或加进 `OPERATOR_SIDE` |

### 9.7 本班交付件、没做到的格子、要总控裁定的格子

本班新增/改写的字节（主树 venv 现取，纯 CRLF、无 BOM、U+FFFD=0）：

```powershell
$f = @("scripts/r387_backfill_estimate.py","scripts/r387_label_lineage.py",
       "tests/test_r400_derived_ledger_shift_and_silence_pins.py",
       "tests/test_r400_backfill_ladder_pins.py","docs/perf/r387-label-lineage-2026-09-27.md")
```

| 件 | 处置 | 复跑读数 |
|---|---|---|
| `tests/test_r400_derived_ledger_shift_and_silence_pins.py` | **本班新增**（14 枚：K1 插 500 行仍逐枚唯一命中 / 漂移只落被引那一枚文件且修表是机械的 / 只有真受影响的跳该红 / 容差口径在 1..6 行漂移下放绿而派生口径五档全见（参数化）/ K2 改名 ⇒ ABORT rc=3 且 stdout 零字节 / `<锚失效:key>` 不许退回旧数 / `--emit-doc-cells` 同一棵腐锚影子也 rc=3 / 容差与豁免旋钮按 AST 读不出 / `_one_hit` 两条抛都在 / 全局锚闸） | **14 passed** |
| `tests/test_r400_backfill_ladder_pins.py` | **本班新增**（29 枚：A1 不移动判词 / S0–S2 语料账恒 0 / 判词序列逐格 / 原因码全部取自量具那一本词汇 / 只回填部门仍挂密级、抬密级改挂召回 / 单部门规则先卡部门选择性 / 零召回永不被叫成已验（12 组合参数化）/ 越权压过未验 / 三桶不多不少 / 可达部门 ⊆ `DEPARTMENT_HINTS` / 写语句零命中 / 无连接面 / CLI 复跑整张梯） | **29 passed** |
| `scripts/r387_backfill_estimate.py` | **改写**：`unlock_ladder()` / `render_ladder()` / `_corpus_arm()` + `--unlock-ladder` / `--classification-kinds`（默认 1 = 今天形状，旧读数一字不变） | 计划账同值；梯级表 8 行 rc=0；`writes_issued=0` |
| `docs/perf/r387-label-lineage-2026-09-27.md` | **续写本节**（§1–§8 未改） | §1 表 12 行与现读等值（teeth 逐跳钉）；`test_r120` 那一格 r387 引用已消 |

交付件字节口径（R400 收工现取；纯 CRLF：CR = LF、裸 LF = 0、无 BOM、U+FFFD = 0）：

| 交付件 | sha256 | size | CR | LF | 裸 LF | U+FFFD | BOM |
|---|---|---|---|---|---|---|---|
| `scripts/r387_label_lineage.py` | `b304bf2090f6a6c6fee6b302bc1493395d501497d5dcc0b9df21ca5fa900c2cf` | 45351 | 856 | 856 | **0** | **0** | 无 |
| `scripts/r387_backfill_estimate.py` | `9c0ba08d76ccd3c14f8abad6202d9a15497054d09c4ad5741bb7ee04bd571987` | 12850 | 241 | 241 | **0** | **0** | 无 |
| `tests/test_r387_label_ruler_teeth.py` | `c953b063faaf6dcf4c1213e49dc25c5603f5f9b58d0298fc83681d675b3006f0` | 27859 | 511 | 511 | **0** | **0** | 无 |
| `tests/test_r387_production_label_leg.py` | `1033c4fa1fa7290b740128318b36b09596b41b74abe3d8bb58900643e2dbe645` | 12732 | 242 | 242 | **0** | **0** | 无 |
| `tests/test_r390_xfail_strict_and_boundary_pins.py` | `f7314e77d30a86692ed594d30da67cb23de6038635154b0ca4da6d223756752d` | 18561 | 389 | 389 | **0** | **0** | 无 |
| `tests/test_r400_derived_ledger_shift_and_silence_pins.py` | `ea2bddff80ae0e4a8e1138b2646d85596e33251652a524c2b6f9c540fdef6765` | 17725 | 331 | 331 | **0** | **0** | 无 |
| `tests/test_r400_backfill_ladder_pins.py` | `d86d37a9fd49581d6bc876504033d8c524833b5802aa3eeef3c774c4e9015854` | 12118 | 206 | 206 | **0** | **0** | 无 |
| `docs/perf/r387-label-lineage-2026-09-27.md`（本文档） | 自指：注入本表之后再取，写进本班收工回执 | 85424+ | 815+ | 815+ | **0** | **0** | 无 |

复算命令与 §7 那一枚同形（`Get-FileHash` + `CR/LF/裸LF/U+FFFD` 计数），路径清单换成本表这七枚。

没做到 / 未证（如实列，不销）：

1. **"派生版插行后仍全绿"这一格做不到，本班没假装做到**：见 §9.4 那句 —— 表里给人读的行号与现读不等
   就必须红，这是设计要的。真要"插行零红"，得把文档表改成占位符 + 渲染期注入，那是文书形态的大改，
   归总控裁。
2. **`read_postgres` 那一腿的真库端到端仍没做**（§8.6 第 1 格原样挂着）。本班只在宿主机侧走了
   `docker exec psql`，没往 backend 容器里管道执行脚本 —— 那是"会改变环境"的动作（在别人的运行中
   容器里跑代码、`sys.path` 落在镜像那一份 `app/**` 上），超出本单授权。要销这格，请总控明令一次
   授权（并规定 ledger 只走 stdout、不落容器文件）。
3. §2.3「研发 721」与今天现读 713 这处漂移**没有回改原文**（读数不追溯改写）。要根治的是给 §2.3 那张
   表也配一枚"由 `plan_from_names` 现跑"的牙 —— 本班只把**梯级**那一本账改成可复跑，计划表本身仍是纸账。
4. 文档 §5–§8 里那批**不自称现读**的行号/枚数仍是历史账；R400 当时那句「受检范围仍只有 §1 表 + §1 表下正文」到 09-29 也已过期。
   今天的受检面逐枚点名只写在 §8.8 未做 3 那一格（唯一事实源，本格只指过去、不另抄一遍——两本必漂），
   已做掉的范围没有一处再写成未竟之事，也不许再被下一个人当成挡箭牌。
5. `@router.post("/ask")`、`list_user_departments` 两格派工词引用在本仓读不出，本班**没有**为它们新增锚：
   没有主张要钉的东西，硬造锚就是养闲（死锚比没锚更坏，`test_the_anchor_table_and_the_templates_share_one_ledger`
   就是为这个存在的）。若总控认为这两格该进血缘账，请点名它们要证明哪一条判据。
6. 没跑 `scripts/run_gate.py` 全量门（明令）；没起服务、没打模型、没重建镜像、没碰 `frontend/**`、
   没碰 `app/**`、没碰计划书与看板、没碰 `be-r387`/`be-r390` 两棵树。
### 9.8 R493 收口：一枚「结构上无法核对的当下声称」怎么降回丙类，与两处过期叙述（2026-09-29 四度续班）

写域与基点：`be-r493` @ **`438d67d`**（开工 `git status --porcelain` 空、`rev-list --count 438d67d..HEAD` = 0），解释器用
主树 `.venv`（本树里没有 `.venv`，事故 #93）。零写入 `app/**`、零连库、零起服务、零打模型、零跑全量门；甲案的反证打在
`git archive 438d67d` 导出的临时影子副本上，锚表互覆那一形打在内存副本里，盘上那棵树一个字没动。

**① 为什么走乙案（改写那一格），不走甲案（把 `chat_ask_entry` 补进 `LINEAGE_SITES`，46→47）**——三条硬理由：

1. **死锚闸拦死了「只加锚、不改模板」这条路**。在册闸 `test_the_anchor_table_and_the_templates_share_one_ledger` 拿
   `LINEAGE_TEMPLATES` 的 site/note 与 `HOP_DOC_CELLS` 的引用集同锚表双向互覆，多一枚即红。影子复跑（副本里只往
   `LINEAGE_SITES` 顶端加一枚锚、其余字节一字不动）：锚表 47 枚、`LINEAGE_ANCHOR_FAILURES = []`、那枚 token 恰一枚唯一命中、
   `--emit-doc-cells` rc=0，可 teeth 单跑 = **42 passed / 1 failed**，红句原文「锚块表里有没人引用的死锚：['askentry']」。
   要让它不红就得把占位符写进模板或 §1 那张表——那在本单「只许动 `LINEAGE_SITES` 一处」之外，而那枚闸件本身在禁域里。
2. **解得出来也不该进这本账**。那枚 token 是问答主入口（`async def ask` 头上那行装饰器），不在「上传 → 打标签 → 落库 →
   读侧谓词」那 12 跳上；把它塞进血缘模板等于给血缘表凭空造一跳搬运关系，比留一枚过期行号更坏——§9.7 未做 5 当年就是
   按这条说的（「没有主张要钉的东西，硬造锚就是养闲」）。
3. **46→47 会打翻在册的历史账**。§8.8 未做 1 那句「46 枚锚是在 `ANCHOR_BASE_COMMIT` 那一枚基点的内容上挖出来的」与 §8.5
   那格普查「75 枚锚块唯一命中普查（46 格 × 起/终点）」都是原样留档的账（判据不许顺手清理）；一枚在今天树上重挖的锚
   会让这两格当场变假。

⇒ 甲案要的是「扩写域 + 改甲类口径 + 重写历史账」三件事同时点头，超出本单授权，本单按乙案落。上面第 1 条不是话术：它已铸成
   常驻形——新钉在内存里加同一枚锚、复用同一套互覆算法，当场断言那枚锚落进 dead 集。

**② 那一格今天是什么**：§9.6 的 `chat_ask_entry` 行只剩丙类历史账——基点 `6a8063a` 上 R400 那一次读到的行位，本席在同一枚
基点的 blob 上复现过同值（复现形：`git show 那一枚基点与被引文件`，再按锚块那套逐行 strip 的固定串定位；新钉现场把纸面那个
数与复现值比）。今天的行位**不写进这本纸**：写了就需要一枚拿得住它的钉，而这枚 token 进不了锚表（① 那三条），于是又造出
一枚「结构上无法核对的当下声称」——正是本单要治的病。🔴 可失败形：把当下声称那四个字塞回那一行，
`test_r492_live_claim_boundary.py` 当场红（欠账名单已清零，见 ③），新钉跟着红。

**③ 收口是两头一起改的**：`KNOWN_UNPINNED` 从恰一枚收到零枚，与 §1 表旁那句自守同时改到自洽。只改一处必红——名单先清而纸
没清 ⇒ `test_the_ledger_matches_the_gaps_read_from_the_book` 红（纸上还读得出欠账）；纸先清而名单没清 ⇒ 同一枚红（在册与实际
不符）。名单机制不退役：仍只许变短、不许变长，账外新长一枚即红。

**④ 两处过期叙述**：§8.8 未做 3 与 §9.7 未做 4 原都写「受检的只有 §1 表 + §1 表下正文」，与实物不符；今天按实物改写，受检面
逐枚点名只落在 §8.8 未做 3 那一格（唯一事实源），已做掉的范围没有一处再写成未竟之事。

**⑤ 本席看见但没治的一格（如实报，不销）**：§3 方案 A 段末那句用「今天」引出的那枚坐标，值不是任何一枚锚的派生值，而两枚
闸都看不见它——R490 与 R492 的边界闸都以「现读」那两个字为闸门，「今天」不在甲类口径里。要治它得先扩 §1 的甲类定义（把
「今天」这类字样一并纳入同行标记），那是**口径变更**，归总控裁；本单一字未动 §3，只在
`tests/test_r493_checked_scope_narration.py` 里钉了一枚哨：那一格与本节这一笔必须同时挂在纸上，谁悄悄删掉哨就红。

**⑥ 更正一笔（不改 §9.7 未做 5 原文，按 §9.5 那格同形另记）**：那句「两格派工词引用在本仓读不出」对 `list_user_departments`
仍成立（`rg` 在 `app/**` 零命中），对问答主入口那一枚**不成立**——那枚 token 在 `chat.py` 里唯一命中，只是 R400 写下的那个
符号名在本仓从来不存在。本单的乙案正建立在「token 在、锚进不去」这一对事实上。

**⑦ 本单没做到 / 未证（如实列）**：授权动 `LINEAGE_SITES` 那一处**没用**（走乙案就不需要，该件字节零改动）；⑤ 那格口径没扩、
§3 那一格没治；没跑全量门（明令）；没起服务、没连库、没打模型、没动容器、没碰 `app/**`、没碰 `frontend/**`、没碰计划书与
看板；没给血缘链新增任何 Chroma 依赖或写点（向量库定案＝PGVector，Chroma 只是退役中的遗留件）。