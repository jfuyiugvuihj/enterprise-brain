# R633 —— 「停双写」的前置量具：把 `VECTOR_DUAL_WRITE` 拨到 off 会掉什么（10-04 · 执行层@`be-r633`）

日期 2026-10-04（星期日）。执行层席交工纸，单号 **R633**，独占工作树
`C:\Users\fengx\PycharmProjects\be-r633`，分支 `codex/be-r633`，基点 **`4da0bad`**。
解释器 `.venv\Scripts\python.exe`（Junction → 主树虚拟环境）。

🔴 **本纸所有读数都是本席亲跑（执行层自报）**，不是转述派工词，也不是转述前席；未跑的格子逐枚写在 §11 标「未验」。
🔴 **本席一枚库都没连、一个容器都没动、一个字节都没往任何库里写**：语料面这一格只以注入假件证明算法（§6）。
🔴 本单不产出「可以翻旋钮」的结论；本单产出的是一把能量这一格的尺，加今天这一遍的读数。

---

## 1. 一手盘面（开工那刻现取）

| 步 | 命令原文 | 实取读数 |
| --- | --- | --- |
| ① 开工零改动 | `git -C C:\Users\fengx\PycharmProjects\be-r633 status --porcelain` | **0 行**（交班账记的开工态；本轮接手时同尺现读 = 仅 `?? scripts/r633_dual_write_off_precondition.py` + `?? tests/test_r633_dual_write_off_precondition_teeth.py` 两枚，即前两件交付已在盘上、第三件未落） |
| ② HEAD 与分支 | `git rev-parse HEAD` / `git rev-parse --abbrev-ref HEAD` | `4da0bad9d5512c709d8ee1d75c3ee59fda5b355c` / `codex/be-r633` |
| ③ 基点那笔是什么 | `git log -1 --format='%H|%ad|%s' --date=iso HEAD` | `2026-10-04 14:43:21 +0800` · 「R626 并树（执行层 Bernoulli／树 `be-r626@8c99251`·遗留引擎静默空召回量具 649 行＋牙 23 枚＋取证纸）」 |
| ④ 已改面积 | `git diff --numstat HEAD` | **空**（本单只新增文件，不改在册件） |
| ⑤ 部署声明文件 | `Test-Path -LiteralPath deploy\.env.server` | **False** —— 本树不存在（主树那枚是未跟踪件，本单禁碰主树）⇒ 声明面这一格本席取不到数，见 §11 |

---

## 2. 派工前提的现读裁定（前提错了照旧顶回来）

| 步 | 命令原文 | 实取读数 |
| --- | --- | --- |
| ① 「停双写」这个词在不在册 | `rg -n '停双写' docs/ AGENTS.md` | **0 命中** |
| ② 退役阶段表现在的原文 | `rg -n 'S0|S1|S2|S3|S4|S5' docs/deployment/chroma-retirement-path.md` | `:73` **S0 停写**＝「旋钮拨到 pgvector，新行只落 PG」，状态列写「已完成（本单）」；`:74` **S1 观察窗**（运维）；`:75` S2 最后一次带遗留库的全量归档；`:76` S3 摘备份范围；`:77` S4 目录与卷离场（🔴 业主本人 H4/H5/H8）；`:78` S5 代码退役 |
| ③ 本页自己的口径 | 同上件 `:94` | 「**S1 之后的每一阶段今天都没执行，本页写的是路径，不是完成度。**」 |

⇒ **顶回来一条（不改口径，只改问题）**：在册的 S0→S5 里**没有一格叫「停双写」**。从 S0（停写）到 S5（代码退役），
没有任何一格的动作是「把 `VECTOR_DUAL_WRITE` 拨到 off」；那枚旋钮在在册路径里是**整条 PostgreSQL 腿的总闸**（§5），
拨 off 的语义不是「停掉最后一份写」，而是**把 S0 停写翻回去＋把读路退回遗留引擎**。
因此本量具把这一问句按字面实现成「**把 `VECTOR_DUAL_WRITE` 关掉会掉什么**」，并给出现在能不能这么做的判定（§9）。
派工词若指的是另一件事（例如「停掉双写的补偿」「停掉 Chroma 侧的写」），请总控点名改判据，本席不猜。

---

## 3. 在册冲突：计划书 §15 标题 vs 跟进单 §165.3（两枚原文 + 本席裁断建议）

### 3.1 两边原文（逐字现取，行号按 `rg` 那一层）

| 出处 | 命令原文 | 实取的原文 |
| --- | --- | --- |
| 计划书 §15 标题 | `rg -n 'S0 停写已完成' docs/handoff/2026-09-17-pgvector-adoption-plan.md` | `:559` 「## 15. 10-03 第十二班第十一格·总控落笔：**S0 停写已完成（R60 并树 `9f43a31`）**·本机读腿有窗指纹为凭·剩余阶段只剩 S1-S5」 |
| 跟进单 §165.3 那一句 | `rg -n -A 8 '### 165\.3 🔴' docs/handoff/2026-09-15-backend-followup-requests.md` | `:5535` 「…欠账照旧写明：**④现读取数（PG +1／Chroma +0）必须在当前 HEAD 重取（旧读数属基点 `245315b`）、⑤一键回滚演练还挂着 R587、⑥纸面归本席——🔴 谁都不许据此声称『停写已完成』**」 |
| 同一节的现读凭据 | 同上件 `:5530` | 「`9f43a31`＝**rc=0**（10-03 16:46「并树 R60……写路径唯一化＋回滚演练账本＋S0-S5 退役阶段表」），计划书 §15 标题（`:559`）白纸黑字「S0 停写已完成…」」 |
| R60 块 1 的派工词 | 同上件 `:5522` | 「🔴 **④现读取数（PG +1／Chroma +0）·⑤一键回滚演练·⑥纸面三格本块不交**——前两格要真机与容器…派工词里明写『本块不得声称停写已完成』」 |
| 判据④⑤的定义 | 同上件 `:5307`、`:5308` | ④「写一枚新文档后 **PG `chunk_vectors` 行数 +1 且 Chroma collection 计数 +0**，两枚读数都要现取进纸；只报『代码看起来改了』不收」；⑤「一键回滚演练：回到上一 `index_version` 全量恢复**真跑一次**并留证（可复用 R575 那套件；🔴 备份必须连库级 GUC 一起备，见 R587）」 |

### 3.2 本席为这两句话补的现读凭据

| 步 | 命令原文 | 实取读数 |
| --- | --- | --- |
| ① 账本是哪笔引进的 | `git log -1 --format='%h|%ad|%s' --date=iso -- docs/testing/r60-chroma-writeoff-ledger-2026-10-03.json` | `9f43a31` · 2026-10-03 16:46:49 +0800 —— **§15 标题点的那笔并树就是账本的引入提交**，两句话引用的是同一件东西 |
| ② 账本自己的身份 | `python -c "import json;d=json.load(open('docs/testing/r60-chroma-writeoff-ledger-2026-10-03.json',encoding='utf-8'));print(d['ticket'],d['cell'],d['base_commit'],d['sandbox_db'])"` | `R60` · 「判据⑤ —— 一键回滚演练（真跑一次并留证）」 · `base_commit = 245315b` · `sandbox_db = eb_r575_drill` |
| ③ 判据④那一格的读数 | 同上件，`steps['writeoff-probe']` | `ok: true`、`dual_write: true`、`writes_go_to_pgvector: true`、`pg_count_before/after = 1009 → 1010`、`legacy_count_before/after = 1 → 1`、`legacy_ids_added: []`、`psql_independent_after: "1010 (… docker exec psql 现取)"`；另附 `delete_proof` 两形（只住 PG 的行删得掉：1010→1009；两腿都有的行删得掉且遗留腿 1→0） |
| ④ 基点离今天多远 | `git rev-list --count 245315b..HEAD` | **51** |
| ⑤ R587 到底并了没 | `git merge-base --is-ancestor eecd699 HEAD` | **rc=0**；`git log -1 --date=iso eecd699` ＝ 2026-10-03 **13:40:02**，早于账本自述的落笔时刻 `written_utc = 2026-10-03T14:4x+08:00` |
| ⑥ 那一遍的库是哪一枚 | 账本 `sandbox_db` 与 `chroma_sandbox_dir` | `eb_r575_drill`（演练副本库）＋ 容器内 `/tmp/r60stage/chroma`；`cleanup.steps.databases_after_cleanup` ＝ `['eb_r59_sandbox','enterprise_brain','postgres','template0','template1']` —— **从头到尾没有在生产库 `enterprise_brain` 上跑过判据④** |
| ⑦ 回滚演练里拨的是哪把旋钮 | 账本 `steps['rollback-knob']` | `command` 里是 `-e INDEX_BACKEND=chroma`，且 **`dual_write: true` 全程未动**；读数 `writes_go_to_pgvector: false`、PG `1008 → 1009`、遗留腿 `0 → 1`、note「退路靠开关，不靠改码」 |
| ⑧ 生产面的数在账本里是什么 | 账本 `steps['postflight']` | `production_vector_count_before/after = 1008 / 1008`、四枚 `*_equal: true`、`r60_rows_left_in_production: 0` |

### 3.3 本席的裁断建议（不是结论，是给总控落笔用的形状）

- **两句话各占半真半假，不能整句收也不能整句退**：
  - 计划书 §15 的「已完成」**有真读数撑着**（`:5307` 定义的判据④那一形，账本 `writeoff-probe` 逐字交回 PG +1／Chroma +0，
    并树提交就是它点名的 `9f43a31`）；但它**跑在基点 `245315b`、跑在演练库 `eb_r575_drill`、跑在容器内临时沙盒目录**上，
    距今天 HEAD 差 **51 笔**。⇒ 「已完成」作为**那一时点那一枚盘面**的读数成立，作为「当前 HEAD 已复量」不成立。
  - 跟进单 §165.3 的两个半句**一真一已过期**：
    「④现读取数必须在当前 HEAD 重取」＝**今天仍成立**（本席第④步现取 51 笔差）；
    「⑤一键回滚演练还挂着 R587」＝**已被推翻**（第⑤步 rc=0、时刻早于账本落笔；账本 `reused_suites` 逐字点名 r575＋r587，
    `rollback-knob`／`index-rollback`／`postflight`／`cleanup` 四步 `ok: true`）。
    同节 `:5535` 那句「谁都不许据此声称『停写已完成』」**方向仍然对**，因为它拦的是「拿代码半张当全部判据」这一形。
- **本席不写「停写已完成」**，一次都不写。本纸里凡是引用这五个字的地方都在「」之内，且是别人的原文（§3.1 那三行）。
  本席能给的、且手里有读数的最强措辞是：
  **「写路径唯一化的码与闸门在 HEAD 静态可复证（§4、§5 逐枚点名）；10-03 那一遍真跑读到过 PG +1／遗留腿 +0；
  当前 HEAD 的复量欠着，而那一遍从来是演练库不是生产库。」**
- 措辞口径按在册写：目标态＝PostgreSQL + PGVector，Chroma＝**退役中的遗留件**——它今天**既不是最终架构、也还没有下线**
  （§5 给出它仍在读、且旋钮一关它就重新接行的凭据）。旁证：`python scripts/check_vector_wording.py` → exit 0
  「向量库口径钉：36 枚文档全部通过」。

---

## 4. 面一 · 写点面（借在册名册，绝不抄第二份清单）

| 步 | 命令原文 | 实取读数 |
| --- | --- | --- |
| ① 全量跑一把 | `python scripts\r633_dual_write_off_precondition.py --all` | **exit=1**；`变异写点 6 枚（名册来自 tests/test_r625_chroma_write_sites_are_named_one_by_one.py）`；`roster_findings: []`；`leg_guards: 2 枚`；产物 `C:\Users\fengx\AppData\Local\Temp\r633\r633-precondition-20261004T092058Z.json/.md` |
| ② 在册名册自己数 | `python -c`（`sys.path.insert(0,'tests')` 后装载该件，取 `len(CHROMA_WRITE_ROSTER)`） | **6**（与量具报的 6 枚逐身份相等） |
| ③ 为什么不按字面数 | `rg -c 'collection\.add' app/rag/retriever.py` / `rg -n 'collection\.add' app/rag/retriever.py` | 字面 **4 处**：`:1446`（**docstring 里的一句话**「未来的双写/迁移路径也应当走这里，而不是各自再抄一份 `collection.add`」）、`:1455`、`:1473`、`:1602`。⇒ 字面 4 ≠ 写点 6：名册按**语义身份**点名（含 `_undo_vector_write` 的补偿两支、含不带 `embeddings` 的离线 `_JsonCollection` 那一支）。同族病在册记录见跟进单 `:5536`（一枚 `collection.add >= 2` 的假牙 ⇒ 引出 R625） |

六枚逐名（`--all` 原文的角色列与 off 态列）：

| 写点身份 | 角色 | off 态 |
| --- | --- | --- |
| `retriever.py::DocumentRetriever._write_batch::add(documents, ids, metadatas)` | offline | `switch_independent` |
| `retriever.py::DocumentRetriever._write_batch::add(documents, embeddings, ids, metadatas)` | primary | **`reopens_when_off`** |
| `retriever.py::DocumentRetriever._undo_vector_write::delete(ids)` | compensation | **`reopens_when_off`** |
| `retriever.py::DocumentRetriever._undo_vector_write::add(documents, embeddings, ids, metadatas)` | compensation | `switch_independent` |
| `retriever.py::DocumentRetriever.add_document::delete(ids)` | primary | `switch_independent` |
| `retriever.py::DocumentRetriever.delete_document::delete(ids)` | primary | `switch_independent` |

（身份前缀统一为 `app/rag/retriever.py::DocumentRetriever.…`，本表为省宽略写；量具产物里是全串。）

---

## 5. 面二 · 开关面：这把旋钮不是「双写开关」，是「整条 PG 腿在不在」

产品码自述（不是本席的推论）：

| 锚点 | 命令原文 | 实取的原文 |
| --- | --- | --- |
| `app/rag/pg_store.py:175-176` | `rg -n 'def dual_write_enabled' -A 1 app/rag/pg_store.py` | `def dual_write_enabled() -> bool:` ／ docstring 首行 `"""Is the PostgreSQL leg on? Off unless an operator says so, in those words.` |
| `app/rag/pg_store.py:19` | `rg -n 'default is OFF' app/rag/pg_store.py` | 「The switch is `VECTOR_DUAL_WRITE` and its default is OFF. With it off this module imports no…」 |
| `app/rag/indexing.py:2106-2109` | `rg -n '不是停写而是零写' -B 3 -A 2 app/rag/indexing.py` | 「它不许诺『什么都不写』。写路径只在**这一笔真的有一条 PG 腿**时才来问它（`app/rag/retriever.py` 的 `_writes_go_to_pgvector`）：`VECTOR_DUAL_WRITE` 关着就没有 PG 腿，**那时把遗留腿一起关掉不是停写而是零写**」 |

判定与拒答的现取行号（全部本席逐枚点名，行号一律现读）：

| 面 | 锚点 | 读数 |
| --- | --- | --- |
| 停写判定 | `app/rag/retriever.py:1496` `def _writes_go_to_pgvector()`；`:1519-1520` | 合取 `pg_store.dual_write_enabled() and indexing_module.pgvector_writes_are_primary()`，顶部 `:1517-1518` 是 `if not self.stores_vectors: return False` 早退 —— 量具 `predicate` 现取 `terms=['pg_store.dual_write_enabled()','indexing_module.pgvector_writes_are_primary()']`、`early_returns=[('not self.stores_vectors','False')]`、`present/conjunction` 均 `true` |
| 读侧开关 | `app/rag/indexing.py:2040` / `:2087` / `:2098` | `read_backend()` / `pgvector_reads_enabled()` / `pgvector_writes_are_primary()`，后者 `:2112` 即 `return read_backend() == PGVECTOR_BACKEND` —— 读路写路同一把旋钮，没有第二把 |
| 拿腿 | `app/rag/pg_store.py:532` `vector_mirror()`；`app/rag/retriever.py:1482`/`:1494` | `_open_vector_mirror()` 直接返回 `pg_store.vector_mirror()`；旋钮 off ⇒ `None` |
| 拒答码 | `app/rag/pg_store.py:684` | `REASON_VECTOR_READ_WITHOUT_DUAL_WRITE = "vector_read_without_dual_write"` |
| 拒答三处 | `app/rag/pg_store.py:899` / `:935` / `:1091` | 逐处 `reason=REASON_VECTOR_READ_WITHOUT_DUAL_WRITE` |
| 开关一关就拒答的腿（5 枚） | 量具现取 | `_document_leg_connection`（def `:1074`）、`document_vector_rows`（`:1095`）、`indexed_document_names`（`:1120`）、`read_corpus`（`:915`）、`read_topk`（`:886`） |
| 补偿一族 | `app/rag/retriever.py:1582` def；调用点 `:1722`、`:2093` | 两枚调用点各自站在 `if mirror is not None`（`:1721`、`:2092`）之内 ⇒ off 态**整支不可达** |
| 删除问句 | `app/rag/retriever.py:1522` `def _document_rows_by_leg`；`:1539-1540` | `if not self._writes_go_to_pgvector(): return legacy_ids, legacy_metadatas, []` ⇒ **PG 那一格恒交回空列表** |

旋钮 off 态的进程内读数（量具现取，非容器）：`python scripts\r633_dual_write_off_precondition.py --env-file deploy/.env.server`
→ exit 1；产物里 `switch.knobs` ＝ `INDEX_BACKEND.raw=""`、`constant="chroma"`、`resolved_by_read_backend="chroma"`、
`reads_enabled=false`、`writes_primary=false`；`VECTOR_DUAL_WRITE.raw=""`、`resolved_by_dual_write_enabled=false`；
`switch.deployment_declaration` ＝ `{source: "deploy\\.env.server", declared: {}, note: "声明文件不在位：这一格未取数"}`。
🔴 这组数是**裸进程**的数（出厂缺省档），不是现网的数。现网那一格本席**没读到**：AGENTS.md 与派工词记「10-03 08:4x 落地 `INDEX_BACKEND=pgvector`、`VECTOR_DUAL_WRITE=on`，三枚容器 `printenv` 现读均为 pgvector」——**这是转述，不是本席现取**（本席不许动 `.env*`、不许动容器、不许进容器）。⇒ 那一格只能由总控带 `--env-file deploy/.env.server` 现取（§10 第 2 步、§11 第二格）；本纸凡引用它都在「若声明如所报」的形状里（§9.1 末段）。

---

## 6. 面三 · 语料面：本席**未取数**（诚实账，不拿注入冒充实数）

| 步 | 命令原文 | 实取读数 |
| --- | --- | --- |
| ① 默认不连库 | `python scripts\r633_dual_write_off_precondition.py --all` | `corpus.gathered = false`，note 原文：「未给 `--database-url` 与 `--chroma-dir`/`--snapshot-from`：语料面这一格未取数，本席没有跑生产库，那一遍由总控开窗」；stdout 末行同义一句 |
| ② 只给库不给卷 | `python scripts\r633_dual_write_off_precondition.py --database-url postgresql://u@h:5432/enterprise_brain` | **exit=2**，stderr 首行「[前置不满足] `--snapshot-from` 与 `--chroma-dir` 必须且只能给一枚：本量具没有『打开默认卷』这一档」 |
| ③ 指现役卷 | `python scripts\r633_dual_write_off_precondition.py --chroma-dir C:\Users\fengx\PycharmProjects\be-r633\chroma_db` | **exit=2**，「[前置不满足] `--chroma-dir` 指向现役卷…现役卷只许当 `--snapshot-from` 的复制源」 |
| ④ 非沙盒库 | `python scripts\r633_dual_write_off_precondition.py --database-url postgresql://u@h:5432/enterprise_brain --chroma-dir %TEMP%\r633_fake_chroma` | **exit=2**，「[前置不满足] 取不到 collection 'enterprise_docs'：Collection [enterprise_docs] does not exist（目录真实也不等于集合在里面）」 |

🔴 第 ④ 步这一格本席要**照实报一个次序**：库名守卫在**连接之前**（`scripts/r633_dual_write_off_precondition.py:717` 判、`:721` 才 `connect_read_only()`），
但在遗留面校验**之后**——那一枚空副本目录先在集合面上被收了，所以 CLI 没能演示到库名守卫。
那一格由牙 `test_a_non_sandbox_database_is_refused_before_anything_is_connected` 证明：注入的连接工厂一旦被调用即抛，跑完没有抛 ⇒ **一次连接都不许发生**。
沙盒名册现读：`SANDBOX_DATABASES = ("eb_r59_sandbox",)`（`:103`）＋形状 `^eb_r\w*_(sandbox|drill)\Z`（`:104`）。

语料面算法（`only_in_pg`／`only_in_chroma`／`wrong_width`／`all_zero_rows`／`index_version_id_null`）**只由注入假件验过形状**：§13 的「语料面算法」1 枚 ＋「连库纪律」5 枚＝6 枚，全部离线。
生产与沙盒的真实差集枚数**本席一个都没量到**（§11 第一格），纸里也不许出现任何一枚这样的数。快照面本席不复制实现：装载在册件
`scripts/r626_legacy_engine_silent_empty_probe.py` 的 `volume_inventory`/`inventories_match`/`chroma_dir_for_run`/`remove_snapshot`
（`:319`/`:334`/`:376`/`:369`）复用，读取前后各点一次卷面清单，不等即按 2 号收（`corpus_face` `:726-729` 现取）。

---

## 7. 十 条 发 现（`--all` 检出的、逐条按 code 归族）

计数现取：`chroma_write_gate_reopens` ×1、`compensation_needs_a_leg_it_wont_have` ×2、`delete_set_blind_to_pg_only_rows` ×2、
`question_rehomes_to_legacy_store` ×3、`read_leg_waits_for_chroma_receipt` ×2 ＝ **10**，与 stdout「发现 10 条」相等。

| # | code | 落点 | 这一格掉了什么（量具原句摘要） |
| --- | --- | --- | --- |
| 1 | `chroma_write_gate_reopens` | `_write_batch::add(documents, embeddings, ids, metadatas)` | 今天被停写判定挡着（现取闸门：必须假 `_writes_go_to_pgvector`）；旋钮一关判定即为假，**遗留目录重新接新行**——所以「停双写」是把 S0 停写**翻回去**，不是停掉最后一份写 |
| 2 | `compensation_needs_a_leg_it_wont_have` | `_undo_vector_write::delete(ids)` | 调用点必须先过 `mirror is not None`；off 就没有那条腿，整支逆序补偿不再被调用——**而同一时刻遗留目录的写闸门是开的**，Chroma 接的新行没有任何东西撤它（回滚面静默失效，不是换成另一套补偿） |
| 3 | `compensation_needs_a_leg_it_wont_have` | `_undo_vector_write::add(...)` | 同上（补偿的两支一起没） |
| 4 | `delete_set_blind_to_pg_only_rows` | `add_document::delete(ids)` | 那一笔先问 `_document_rows_by_leg()` 拿行；off 态走早退，PG 那一格恒空 ⇒ 同名重传时**只住在 PG 的旧行不在删除集合里**，重开双写后上一版会自己活回来 |
| 5 | `delete_set_blind_to_pg_only_rows` | `delete_document::delete(ids)` | 同上——`DocumentRetriever.delete_document()` **不报错、原样 return**（牙现跑咬住）。端点那一层本席**只读码未真跑**：`app/api/v1/chat.py:4936-4947` 只在 `retriever.delete_document(filename)` 抛异常时才判 `index_rollback_failed`，不抛就往下走 ⇒ 这一格翻不成错误，删除被当成成功走完后续步骤 |
| 6 | `question_rehomes_to_legacy_store` | `_document_rows_by_leg` | off 态早退（现取判定 `['not self._writes_go_to_pgvector()']`）：这一句只问遗留目录 |
| 7 | `question_rehomes_to_legacy_store` | `list_documents` | 整句改问遗留目录（现取遗留读调用 `self.collection.get()`）——**名单退回那台要退役的引擎** |
| 8 | `question_rehomes_to_legacy_store` | `document_chunks` | 整句改问遗留目录（现取 `self.collection.get(where={'filename': filename})`） |
| 9 | `read_leg_waits_for_chroma_receipt` | `read_corpus` | `read_corpus()` 在 off 态按 `REASON_VECTOR_READ_WITHOUT_DUAL_WRITE` 拒答，拒答被 `app/rag/pg_store.py::switched_corpus` 吞成「这一腿没答」，答复改由 `app/rag/retrieval_pipeline.py::build_index` 的遗留读给出（现取 `r.collection.get()`） |
| 10 | `read_leg_waits_for_chroma_receipt` | `read_topk` | 同族：吞点在 `app/rag/retriever.py::_pgvector_hits`，改由 `app/rag/retriever.py::search` 的 `self.collection.query(**kwargs)` 给 |

**最贵的一格是第 4/5/6 与第 1 条的合取**：切换之后**只落在 PG 的行在 off 态删不掉、名单里也没有**，
而同一个旋钮又让 Chroma 重新开始长行，且撤它的补偿整支不可达（第 2/3 条）。
这三形不是「性能掉一档」，是**数据面会出现报成功而实际没删、且没人负责回滚**。

---

## 8. 退出码四挡与本席实跑到的形状

语义写死在 `--help` 的 epilog（本席现取原文），优先级 **2 > 1 > 3 > 0**：

| 码 | epilog 原文 | 本席实跑到了吗 |
| --- | --- | --- |
| 0 | 「三面全量到且没有任何发现：S1 停双写现在可翻」 | **没有**。静态两面今天就有 10 条发现，够不着 |
| 1 | 「跑成了，且检出发现：关掉 `VECTOR_DUAL_WRITE` 会掉功能或留下删不掉的行 ⇒ 现在不可翻」 | **有**：`--all` → exit=1、10 条（§4/§6）；`--env-file`（不存在）→ 同样 exit=1，声明面记「未取数」而不改退出码 |
| 2 | 「前置不满足或本量具的读数不可信（名册对不上／只读事务设不上／目录是现役卷／库名不在沙盒又没给开窗责任人／量具自身异常），stderr 首行带『[前置不满足]』」 | **有**，三形（§6 第 ②③④ 步）；名册对不上与只读设不上两形由牙覆盖 |
| 3 | 「静态两面量到且无发现，但语料面未取数 ⇒ 只能说这一遍没量全，不能说可翻」 | **CLI 没够着**（静态面就有发现）；由牙 `test_the_exit_code_meaning_is_fixed` 4 组参数化钉住语义 |

旁证：`python scripts\r633_dual_write_off_precondition.py --help` → **exit=0**，epilog 把 0/1/2/3 与全部 code 名逐枚点名
（牙 `test_the_epilog_states_every_exit_code` 按名字判，不按句子措辞）。

---

## 9. **S1（停双写）现在能不能翻：不能**

判定凭据一句话：本量具在当前 HEAD 现跑 **exit=1**，语义即「现在不可翻」；且三面里只量到两面（语料面未取数）。

### 9.1 必须先绿的格（前置清单）

| 格 | 内容 | 今天 | 谁欠 |
| --- | --- | --- | --- |
| P1 | 量具三面全量到且**零发现**（exit 0） | ❌ exit=1，10 条发现 | 需要**改产品码**才能消（把 off 态的读腿、删除问句、补偿族改成显式报错而不是搬家/静默），本单禁碰 `app/**` |
| P2 | 写点名册与在册件零差 | ✅ `roster_findings: []`，6 枚逐身份等 | — |
| P3 | 停写判定仍是「三条件合取」 | ✅ `predicate.present/conjunction` 真、`terms` 两枚＋`early_returns` 一枚 | — |
| P4 | 判据④在**当前 HEAD** 现取复量（PG +1／Chroma +0） | ❌ 旧读数属 `245315b`，差 **51** 笔 | 总控开窗（容器＋库） |
| P5 | 语料面差集实数（`only_in_pg`／`only_in_chroma`／`wrong_width`／`all_zero_rows`／`index_version_id_null`） | ❌ 未取数 | 总控开窗（本席禁连库） |
| P6 | 声明面现取（`--env-file deploy/.env.server` 里两把旋钮原文） | ❌ 本树无该文件 | 总控（在主树现取） |
| P7 | off 态不许有「读答复由遗留引擎给出」 | ❌ 2 条 waiters | 改产品码，另开工单 |
| P8 | off 态不许「报删除成功而 PG 行仍在」 | ❌ 2 条 | 改产品码，另开工单 |
| P9 | off 态不许「写闸门开着而补偿不可达」 | ❌ 2 条（**回滚安全**，最贵） | 改产品码，另开工单 |
| P10 | S1 观察窗运维账（连续窗口内零次回拨 ＋ `scripts/rebuild_index.py --status` 两腿差只增不减） | 未起算 | 运维 |

**给总控的一句判断**（本席能负责任说的最弱形态）：如果业主真正想要的是「Chroma 不再长新行」，那么**按现网那两把旋钮的声明就已成立**——
`VECTOR_DUAL_WRITE=on` ＋ `INDEX_BACKEND=pgvector` 之下主写闸门是关着的（§7 第 1 条从码里现取的闸门条件：判定为真 ⇒ 遗留 `collection.add` 那一支不走）。
🔴 这两把旋钮的**现网读数出自派工词所引的总控 10-03 落地账，本席没有现读到它**（`deploy/.env.server` 在本树不存在，见 §11 第二格、§5 末段裸进程读数），
所以这一句是「若声明如所报，则……」的形状，不是本席的实测；要把它变成实测，只差 §9.1 的 P6 那一格。
S0 停写的码就在 HEAD 上；下一步在册是 **S1 观察窗与 S2 归档**，不是把这把旋钮拨 off。
把 `VECTOR_DUAL_WRITE` 拨 off 得到的**恰恰相反**：Chroma 重新接行，同时 PG 的读、删、名单、补偿全部下线。

### 9.2 回滚姿势（翻下去之后，缺口区间怎么界定）

🔴 先钉一条：在册的回滚档**不是这把旋钮**。账本 `steps['rollback-knob']` 拨的是 `INDEX_BACKEND=chroma` 且 `dual_write: true`
全程未动（§3.2 第⑦步），语义是「两腿照写、新行回遗留腿」；而 `VECTOR_DUAL_WRITE=off` 是**把 PG 腿整条拆掉**。
拿后者当回滚，等于用一台没演练过的机器演练。

缺口区间只能按**三枚集合的差**界定，且必须在 off 之前先拍一次基线：

- **基线**（开窗第一件事，零发现也算）：`--snapshot-from` ＋ `--database-url` 跑一次，把
  `PG vector_id 集合`／`Chroma vector_id 集合`／`only_in_pg` 名单落进产物（仓外 JSON 里 `corpus.drift` 那一格）。
- **区间左端** = off 那一刻的 `index_version_id`（`corpus.drift.index_version_id_null` 同批取）；**右端** = 重开那一刻再跑一次的同一读数。
- **三类行，三种处理，不许合并**：
  1. `only_in_pg`（S0 之后写、只住 PG）——off 期间**读不到、删不掉、名单里没有**（§7 第 4/5/6/7/8 条）。重开双写**不自动复原其可见性**：
     off 期间对它们发起过的删除是假的（`delete_document()` 不报错，端点 `app/api/v1/chat.py:4937` 那一层只认异常——读码现取，未真跑端点），必须**按文档名点名重建**（`document_chunks` 拿不到 ⇒ 只能按 `filename` 清单重建，
     清单本身来自 off 之前的基线产物）。
  2. `only_in_chroma`（off 期间新长出来的）——重开双写**不会把它们补进 PG**（§7 第 1 条）。处理只有两条路：
     `scripts/rebuild_index.py` 定向重建，或删除后重传。禁止「重开旋钮当作已经同步」。
  3. off 期间**上传失败**留下的孤儿（补偿两支不可达，§7 第 2/3 条）——没有任何在册账本会记它，只能靠 off→on 之后
     一次 `rebuild_index.py --status` 普查把它当两腿差暴露出来。这一格是回滚姿势里唯一**无账可查**的，纸里必须写。
- **同名重传那一形**（§7 第 4/5 条 + 牙已现跑咬住）：off 期间的重传只改遗留腿那一版，PG 留着上一版；
  重开双写之后 PG 交回的是**上一版内容**，而检索答复会安静地用旧答案——**不报错**。
  ⇒ 回滚必须带一份「off 窗口内被重传过的文档名」清单，逐枚点名重建；这份清单只能来自**基线产物的名单面**（off 态拿不到，见第 7/8 条）。
- 最小回滚动作序列（开窗者执行，本席不执行）：重开 `VECTOR_DUAL_WRITE=on` → `docker compose --env-file deploy/.env.server up -d --force-recreate backend worker scheduler`
  （容器重建、**不是**镜像重建；`env_file:` 只在容器创建那一刻解析，`docker restart` 不重读——口径见 `AGENTS.md` 与 `tests/test_r255_env_documents_the_conversion.py`）
  → 现读三枚容器 `printenv` → 重跑本量具同一条命令取**右端** → 按上面三类逐枚处理 → 再跑一次量具确认零发现。

---

## 10. 连库注入姿势与总控开窗的命令序（本席一枚字节都没连）

连接层完全可注入，缺省**一枚都不连**；PG 侧一律 `connect_read_only()` 且本量具自验
`SHOW transaction_read_only`（`:105` 常量、`:697` 探针、`:701` 非 on 即 2 号收），设不上就按前置不满足收，不接受 warn。

| 参 | 语义（`--help` 现取） |
| --- | --- |
| `--database-url` | PG 连接串；**没有默认值**（缺省即不连库，语料面报未取数） |
| `--window-owner` | 开窗责任人；库名不在沙盒名册时**必填**，否则连接之前按 2 号收 |
| `--snapshot-from` | 复制源**可以**是现役卷：量具按字节复制一份到 `<out-dir>/snapshots` 再读副本，并在读前读后各点一次卷面清单 |
| `--chroma-dir` | 已经快照好的副本；指到仓内／容器内现役卷按 2 号收 |
| `--collection` | 遗留集合名，与写入侧同名（生产在写的叫 `enterprise_docs`，`tests/test_r120_p3_collection_default.py:7` 现取） |
| `--vector-table` | 缺省 `chunk_vectors` |
| `--env-file` | 只读它里面两把旋钮的**原文**，不当凭据用 |
| `--out-dir` | 产物落点，**必须在仓外**（牙 `test_products_may_not_land_in_the_repo` 钉） |

**总控开窗那一行**（沙盒库版，安全默认；在主树跑，不在本树）：

```
python scripts/r633_dual_write_off_precondition.py ^
    --database-url postgresql://<user>@<host>:5432/eb_r59_sandbox ^
    --snapshot-from /app/chroma_db --collection enterprise_docs ^
    --env-file deploy/.env.server --out-dir %TEMP%\r633-window
```

命令序（每一枚都必须先于下一枚，缺一枚就停在缺的那枚上报）：

1. 先拍基线：上面那一行跑一次，产物里的 `corpus` 那一格不许为空（`only_in_pg` 名单就是回滚区间的左端）。
2. 现取声明面：`--env-file deploy/.env.server` 交回的 `declared` 里两把旋钮必须逐字读到（本席这边 `declared = {}`）。
3. 现取判据④：按跟进单 `:5307` 的定义在**当前 HEAD** 复量一次 PG +1／Chroma +0，进纸（本单不许动容器，故未做）。
4. 读生产库那一遍（如业主真要）：把库名换成 `enterprise_brain` 时**必须**再加 `--window-owner <谁开的窗>`，
   否则连接前即按 exit 2 拒——这不是本席新造的规矩，是把「谁批准碰生产」写进同一条命令行。
5. 卷面不许直接开 `PersistentClient`：只许 `--snapshot-from` 让量具自己复制副本（复用 `scripts/r626_legacy_engine_silent_empty_probe.py` 那一套），
   读前读后清单不等 ⇒ 2 号收，本轮不产语料结论。

---

## 11. 未验清单（逐枚点名，宁可写未验）

| 格 | 状态 | 差什么 |
| --- | --- | --- |
| 语料面全部实数（PG 枚数、Chroma 枚数、`only_in_pg`／`only_in_chroma`／`wrong_width`／`all_zero_rows`／`index_version_id_null`） | **未验** | 本席禁连库；只以 4 枚注入牙证明算法形状与点名输出 |
| 现网两把旋钮的声明面 | **未验** | `deploy/.env.server` 在本树 `Test-Path=False`；须总控 `--env-file` 现取 |
| 判据④在当前 HEAD 的复量 | **未验** | 要容器＋库；旧读数属 `245315b`（差 51 笔） |
| 「S0 停写已完成」这句在册标题的**当前**成立性 | **未验**（本席既不收也不翻） | 同上两格；见 §3.3 |
| 退出码 3 与 0 的 CLI 形状 | **未验** | 静态面今天必有发现，够不着；由牙参数化钉语义 |
| 端点那一层「删除被报成成功」的**真跑** | **未验** | 要起服务＋真库；本席只读到 `app/api/v1/chat.py:4936-4947` 的判失败条件（§7 第 5 行），离线牙只覆盖到 `DocumentRetriever.delete_document()` 这一层 |
| 非沙盒库守卫的 CLI 演示 | **未验** | 需要一枚含 `enterprise_docs` 集合的合法副本目录才能走到那一行；本席不许造 Chroma 写点，故未造。由牙证明「一次连接都不许发生」 |
| commit 后干净树的同名复跑 | **未验**（且本席无权做） | 硬规禁 commit。本席交的是 §12 的两态差分，并树那一态归总控 |

---

## 12. 复跑数字（执行层自报，全部本席亲跑）

| 步 | 命令原文 | rc | 读数 |
| --- | --- | --- | --- |
| ① 本单牙（**态一：本纸未落笔，两件交付在盘**） | `python -m pytest tests\test_r633_dual_write_off_precondition_teeth.py -q` | 0 | **35 passed in 35.11 s**（warm；前席同命令自报 108 s 冷跑，本席不复用那个数） |
| ② 同名（**态二：把本纸暂移仓外**，等价于「第三件未落盘」那一枚盘面态） | 同命令，跑前 `Move-Item docs\testing\r633-*.md → %TEMP%`，跑后移回并 `Get-FileHash` 比对 | 0 | **35 passed in 37.39 s**，与 ① 同名同数；移回后 sha256 = `EF50F3A51FA342953B2FAEC35793F93910A91646E2166FF238A4450C271F53F8`，与移走前**逐字节相等**（`equal=True`）⇒ 本单牙不把「盘上有没有这张纸」当判据，也不拿「施工期盘面脏」当永真判据（事故 #96 那一族） |
| ③ 枚数自校 | `python -m pytest tests\test_r633_dual_write_off_precondition_teeth.py --collect-only -q -p no:cacheprovider` | 0 | 35 枚 node id＝摘刀的 **26** ＋正控 **1** ＋正面读数钉 **8**，三堆逐名点名见 §13（本席按 `--collect-only` 逐枚数过，不靠印象） |
| ④ 量具 | `python scripts\r633_dual_write_off_precondition.py --all` | **1** | 10 条发现（§7 逐条点名）；语料面「未取数」 |
| ⑤ 在册名册正控（**只读，不跑全量门**） | `python -m pytest tests\test_r625_chroma_write_sites_are_named_one_by_one.py -q` | 0 | **23 passed in 4.34 s**（本单借它的名册，必须先证明它自己绿）；同跑回显 `PersistentClient 调用: 0 次` ⇒ 这一遍没碰任何卷 |
| ⑥ 措辞闸旁证 | `python scripts\check_vector_wording.py` | 0 | 「向量库口径钉：**36 枚文档全部通过**（目标态 = PostgreSQL + PGVector；Chroma 只许以退役中的遗留件身份出现）」 |
| ⑦ 本单牙（**态三：三件交付全在盘上＝终态**） | 同 ① 的命令 | 0 | **35 passed in 35.91 s** ⇒ 三枚盘面态（本纸未落笔／本纸暂移仓外／三件全在盘）**同名同数 35**，本单牙既不把「盘上有没有这张纸」当判据，也不把「此刻盘面脏不脏」当判据（事故 #96 那一族）；终态同跑量具 `--all` 仍 **exit=1**（读数不随写纸漂移） |

🔴 本席**没有**跑 `scripts/run_gate.py`（硬规），没有动容器，没有打模型，没有连任何库，没有对真实 `chroma_db` 卷开 `PersistentClient`。

---

## 13. 牙：35 枚，补的是谁没覆盖的形

在册那枚 `tests/test_r60_predicate_terms_and_leg_parity.py`（跟进单 `:5535` 点名的「只摘 `stores_vectors` 时在册件 17 枚全绿」那一形的补件）
量的是**行为**：拨开关之后哪条腿接行、两档交给 PG 的语句是否逐字节等。本单的牙不重复它，补它量不到的四层：

| 层 | 刀（测试名摘写） | 咬什么 |
| --- | --- | --- |
| 派生随码走 | `test_dropping_a_conjunct_from_the_predicate_is_named_by_name[dual_write_enabled / pgvector_writes_are_primary]`、`test_dropping_the_stores_vectors_early_return_is_named` | 在**内存源码副本**上摘掉合取里任一枚 ⇒ 量具必须红并**点名少的是哪一枚**（`predicate_term_missing`）。摘 `dual_write_enabled` 那一形正是本派工点的名，与在册件「只摘 `stores_vectors` 且只验行为」不同形 |
| 名册交叉核对 | `test_an_extra_chroma_write_site_is_reported_as_untrustworthy`、`test_a_removed_write_site_is_named_by_identity`、`test_a_count_preserving_identity_swap_still_bites` | 多一枚／少一枚／**枚数不变但身份撞车** 三形都必须走 2 号（`roster_cross_check_failed`），含本量具自己的「同一身份」红，不只借在册件的话 |
| 隐式等回执 | `test_a_refusal_on_another_reason_is_not_a_dual_write_leg`、`test_a_refusal_that_is_not_swallowed_stops_being_a_receipt` | 两把反向刀：换掉 `read_topk` 的拒答码 ⇒ 腿与回执一起从派生里消失（且 `read_corpus` 不误伤）；把 `_pgvector_hits` 的 `except` 改成上抛 ⇒ 腿还在、**回执消失**。这一族就是「关掉双写仍有代码路径隐式等 Chroma 回执」，今天有 2 条（§7 第 9/10 条） |
| off 态运行时行为 | `test_answers_move_back_to_the_legacy_engine_while_the_switch_is_off`、`test_a_row_written_after_the_flip_is_undeletable_and_off_the_list_when_the_switch_is_off`、`test_the_same_delete_works_while_the_switch_is_on`、`test_a_reupload_while_the_switch_is_off_leaves_the_previous_version_behind` | **现跑复用在册装配台**（`test_r59b_pg_read_switch._build_retriever` ＋ `test_r60_write_path_unique_under_pgvector._assemble/LegacyHandle/PgTable/pg_row`），不另造一套平行假腿。第 2 枚是本单最贵的一枚：off 态删一行 PG 独有的行**不报错、原样 return**，行还在、名单里也没有；第 3 枚是同一动作在 dual=on 的正控（删得掉），第 4 枚是 off 期间同名重传留下上一版 |
| 语料面算法 | `test_the_corpus_face_names_the_gap_that_defines_the_rollback`（1 枚，注入假件） | 差集字段逐格点名：`only_in_pg = 1`、`index_version_id_null = 2`、`documents.vanish_if_off = ['new.txt']`、发现恰为两条且 `subject` 恰是 `{only_in_pg, only_in_chroma}`、本量具自造的快照必须自己收走（`fake_probe.removed == [snapshot]`）。🔴 **不给任何真数** |
| 连库纪律 | `test_a_non_sandbox_database_is_refused_before_anything_is_connected`、`test_the_window_owner_token_is_what_opens_the_production_pass`、`test_a_session_that_is_not_read_only_is_refused`、`test_the_live_volume_guard_is_the_registered_one_not_a_second_copy`、`test_no_default_volume_and_no_default_connection_string` | 非沙盒库＝**一次连接都不许发生**；只读设不上即收；现役卷守卫**借在册那枚**而不是抄第二份 |
| 退出码与产物 | `test_the_exit_code_meaning_is_fixed`（4 组参数化）、`test_products_may_not_land_in_the_repo`、`test_the_precondition_prefix_is_the_registered_one`、`test_the_epilog_states_every_exit_code` | 0/1/2/3 语义写死；`[前置不满足]` 前缀与在册同值；产物只落仓外 |
| 不自抄清单 | `test_the_tool_carries_no_second_list_of_write_sites` | 量具源码里不许出现第二份写点清单（本单唯一允许的名册来源是 `tests/test_r625_*`） |
| 正面读数钉（不摘刀，只把今天那一形钉住，明天码变了就红） | `test_the_tool_names_every_write_site_the_registered_roster_knows`、`test_turning_the_switch_off_is_measured_as_a_loss_not_a_green`、`test_the_stop_write_predicate_is_still_a_conjunction_of_the_registered_terms`、`test_the_refusing_legs_and_their_chroma_receipts_are_named_from_the_code`、`test_the_questions_that_move_back_to_the_legacy_directory_are_named`、`test_the_compensation_family_is_reported_as_needing_a_leg_it_wont_have`、`test_the_switch_face_reads_both_knobs_without_opening_anything`、`test_the_deployment_declaration_is_read_as_text_not_as_credentials` | 八枚钉的是本纸 §4～§8 那几张表的**来源**：写点面必须等于在册名册、off 态必须被量成「掉东西」而不是绿、判定必须还是三条件合取、五枚拒答腿与两条回执必须从码里现派生、三枚搬家问句与补偿那一支必须逐名点名、旋钮面读两把而不打开任何东西、声明面按文本读而不按凭据读。🔴 摘刀那一族（上面七行）证「会红」，这一行证「今天读的确实是这一形」 |

正控：`test_the_registered_write_site_roster_is_green_before_any_knife` ＋ §12 第⑤步——先把在册名册件跑绿，本单的派生才算站在它上面。

---

## 14. 交回盘面

| 步 | 命令原文 | 实取读数 |
| --- | --- | --- |
| ① 三件在位 | `git -C C:\Users\fengx\PycharmProjects\be-r633 status --porcelain` | `?? docs/testing/r633-dual-write-off-precondition-2026-10-04.md` ＋ `?? scripts/r633_dual_write_off_precondition.py` ＋ `?? tests/test_r633_dual_write_off_precondition_teeth.py`（三枚，无第四枚） |
| ② 已改面积 | `git diff --numstat HEAD` | **空**（一枚在册字节未动；`app/**`、`frontend/**`、`deploy/**`、`.env*`、`docs/handoff/**`、`docs/api/**`、评测集、`tests/test_r625_*`、`tests/test_r60_write_path_unique_under_pgvector.py` 全部只读） |
| ③ 未 commit | `git rev-parse HEAD` | 仍是 `4da0bad…`（基点未动，货只留盘上由总控代提交） |

## 15. 编码逐枚自证（本单三枚交付）

| 件 | bytes | CRLF | LF | bare CR | `0x00/07/08/0b/0c` 枚数 | BOM | 反引号枚数 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `scripts/r633_dual_write_off_precondition.py` | 53,956 | 0 | 1,011 | 0 | **0**（`0x00/07/08/0b/0c` 逐枚 0） | False | 150（偶数，成对） |
| `tests/test_r633_dual_write_off_precondition_teeth.py` | 40,892 | 0 | 779 | 0 | **0**（同上逐枚 0） | False | 82（偶数，成对） |
| `docs/testing/r633-dual-write-off-precondition-2026-10-04.md`（本纸） | 见 §16 仓外自证件 | 0 | 见 §16 仓外自证件 | 0 | **0**（同上逐枚 0） | False | 偶数，成对；枚数以 §16 那件为准 |

🔴 行尾这一格本席照实报：仓内既有件是 **CRLF**（`core.autocrlf=true`），而本单前两枚交付落盘是 **LF**（前席写入通道的产物），
本纸与它们保持一致（本席无权改动已在盘上的前两枚——「其余一字节别动」）。对提交无影响：`autocrlf=true` 之下
`git add` 会把行尾归一成 LF 入库。若总控要盘面 CRLF，请在并树后 `git checkout` 一次即可，不必改文件内容。

## 16. 控制字符与反引号现取（含本纸自身的自证件）

本席写完本纸逐枚亲跑（尺＝枚数，不靠眼睛）：

    python -c "<逐枚读三件交付的字节，数 0x00/0x07/0x08/0x0b/0x0c 与反引号枚数>"

| 件 | `0x00` | `0x07` | `0x08` | `0x0b` | `0x0c` | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| 量具 | 0 | 0 | 0 | 0 | 0 | 干净 |
| 牙 | 0 | 0 | 0 | 0 | 0 | 干净 |
| 本纸 | 0 | 0 | 0 | 0 | 0 | 干净 |

反引号枚数：量具 **150**、牙 **82**、本纸**偶数、成对**（三枚全成对＝没有一枚被 PowerShell 双引号啃成 0x0C/0x07/BEL 之类）。
🔴 本纸**不把自己的字节数当判据写死**——一张纸报出自己的长度，写完那一句长度就变了，等于当场作废。
本席现取过一次自证件（仓外，跑一次即可重生成，命令就在下面）：
`%TEMP%\r633\r633-eol-selfproof-20261004T094005Z.json`，那一刻本纸读数＝bytes **41,267**／LF **377**／反引号 **924**／五枚控制字符全 **0**／BOM **False**。
🔴 那一次之后本纸又被补过（§12/§13/§15/§16 四枚 swap），所以那三个长度数**只描述那一刻的本纸，不描述现在的它**；
量具与牙那两枚自 09:40Z 起**一枚字节未动**，它们的 53,956／40,892 与 150／82 至今有效（§15 第一、二行即取自那件）。重取一遍：

    python -c "import pathlib,json,datetime,os;out={};[out.__setitem__(p,{'bytes':len(pathlib.Path(p).read_bytes()),'CRLF':pathlib.Path(p).read_bytes().count(b'\r\n'),'LF':pathlib.Path(p).read_bytes().count(b'\n'),'ctrl':sum(pathlib.Path(p).read_bytes().count(bytes([x])) for x in (0,7,8,11,12)),'backticks':pathlib.Path(p).read_bytes().decode('utf-8').count(chr(96))}) for p in ('scripts/r633_dual_write_off_precondition.py','tests/test_r633_dual_write_off_precondition_teeth.py','docs/testing/r633-dual-write-off-precondition-2026-10-04.md')];print(json.dumps(out,ensure_ascii=False))"

凡含反引号的正文一律走单引号 here-string 或编辑器通道；本纸按此写，§12/§13/§15 的补数走同一通道并逐处 `count==1` 才落盘。
