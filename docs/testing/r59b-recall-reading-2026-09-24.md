# R59b 切读复测读数 — Chroma vs PGVector 逐题召回（2026-09-24）

> 单号 **R59b**（R59 复测＋收口投），基点 `ca2c7d7`。本报告取代 `docs/testing/r59-recall-reading-2026-09-24.md`——那份整作废，作废理由写在那份的正文里。
>
> 一句话结论：**方向支持切读；本轮不翻默认。** PG 腿在 135/135 题上等于它自己的精确解、从不交 0 行、跨 12 遍逐题 0 变化；67 题不一致全部落在「遗留 Chroma 索引腿自己捞不全」这一格上，没有一题归因到 PG 答错。

## 1. 这轮跑在哪、跑的什么

| 项 | 值 |
|---|---|
| 执行位置 | `enterprise-brain-backend-1` 容器内（两侧同时可达：`/app/chroma_db` 是生产卷，`postgres` 是内网 DNS） |
| 量具 | `scripts/r59_recall_compare.py`（前任那枚的改造版，逐块三态见 §2） |
| PG 腿状态 | **`read_live`** —— 真库读；本轮所有产物里没有一处估算腿（numpy 代替真库那一条） |
| 会话 | 连上第一件事 `read_only = True`，实测回读 `True`（原文见 §3） |
| k | 5 |
| 题集 | `tests/fixtures/business_evaluation_30.jsonl` ＋ `tests/fixtures/business_evaluation_100.jsonl` ＝ 135 题（与前任同口径，便于对账） |
| embedding | `nomic-embed-text` @ `LOCAL_MODEL_BASE_URL`（Ollama，逐题串行、不加并发） |
| 距离 | 两侧同为 **l2**：PG 用 `<->`（索引是 `vector_l2_ops`），Chroma 用集合自己的 l2 |
| 语料 | Chroma 1008 枚 / PG 1008 枚，id 集合逐枚相等（`only_in_pg=0 only_in_chroma=0`） |
| 语料稳定性 | 读前读后两侧都各 1008/1008，`stable=True` |

## 2. 接手制：`r59_recall_compare.py` 三态表

前任留的 30 KB 测量件，逐块处置，一行代码都没改的前提下先说清继承了什么：

| 块 | 处置 | 为什么 |
|---|---|---|
| `parse_args`、题集装载、退出码集合 | **继承** | 口径与前任同（135 题、k=5），换腿不换题；`--pg-mode` 默认 `live` 这条 fail-closed 是前任写对的，保留 |
| `read_matrix` / `read_metadatas`（分页读满并对数） | **继承** | 读不满就判前置不满足、而不是少几百行继续算，这个纪律是对的 |
| `pg_live_topk` / `pg_exact_topk`（`SET enable_indexscan=off` 复算） | **继承** | 判据③「HNSW 近似性会不会改名次」只能这么量，拿别的工具替它作证不算 |
| `masked_view` / `array_topk` 的位置 | **改写** | 原先插在 `chroma_array` 赋值之前，掩码腿拿不到矩阵；移到其后，并把谓词判定改成复用生产的 `retriever.metadata_matches`，量具不自造一套匹配规则 |
| `--where-json`（含 `@文件` 读入） | **新增** | 生产读路径恒带权限谓词；不带 where 的读数证明不了要切的那一条 |
| `compare_vector_bodies`（逐位比两侧向量本体） | **继承＋加码** | 原来只在有差集时才看；现在每遍必读，量出 `max_abs_diff` 这条重嵌入噪声底 |
| `pg_engine_facts` 的 `scope_row` | **改写** | 原实现 `dict(row)` 对元组行当场 TypeError，取证格本身是坏的；改成按 `cursor.description` 列名取 |
| 「Chroma 报平方欧氏」这类**断言** | **推翻→实测** | 不再相信继承来的话，改成 `chroma_self`＋`cross_engine` 两组探针真量（§4） |
| 估算腿（numpy 代替真库）当交付物 | **推翻** | 上一份读数的 PG 腿就是它。本轮零使用，最终产物里不出现那条腿的名字也不出现它的值 |
| 「两侧语料对不上、差 607 枚」 | **推翻** | 那是 `%TEMP%\r59chroma` 临时沙盒（401 枚）造的假账；真卷两侧都是 1008 枚且 id 逐枚相等 |
| 「`mean_overlap=1.0`，两侧完全一致」 | **推翻** | 那是 Chroma 与 numpy 自己比自己。真读之后是 68/135 一致、67 题不一致 |

## 3. 两侧口径取证（原文输出，不转述）

```text
$ docker exec enterprise-brain-postgres-1 psql -U enterprise_brain -d enterprise_brain -c 'SELECT count(*) FROM chunk_vectors;'
  psycopg session read_only = True
  chunk_vectors count = 1008
  vector_scope = [[1, "nomic-embed-text", 768, "l2", 16, 100]]
  indexdef = CREATE INDEX chunk_vectors_embedding_idx ON public.chunk_vectors USING hnsw (embedding vector_l2_ops) WITH (m='16', ef_construction='100')
  schema_migrations = 13

$ python: chromadb.PersistentClient('/app/chroma_db').get_collection('enterprise_docs')
  collection.count() = 1008
  collection.metadata = null
  measured distance space = l2  probe = {"source": "measured", "recorded": "", "sampled": 64, "probes": 2, "returned": 12, "matched": ["l2"], "reason": ""}
  ids paged out = 1008
  ids_equal(pg, chroma) = True | only_pg=0 only_chroma=0 intersection=1008

$ sqlite3 'file:/app/chroma_db/chroma.sqlite3?mode=ro'
  embeddings rows        = 1008
  embeddings_queue       = 729 ops (seq 77968..78696)
  queue by operation     = {0: 657, 3: 72}   # 0=put, 3=delete
  max_seq_id per segment = {"7a42b6a9-8a48-4f4a-ad83-61674bed1563": 78696, "0c4b1056-e0c4-44f8-98fa-6b88d22c2a51": 77968}   # 前一个是元数据段，后一个是 HNSW 向量段
  collection space       = l2
  collection hnsw config = {"ef_construction": 100, "max_neighbors": 16, "ef_search": 100, "num_threads": 12, "batch_size": 100, "sync_threshold": 1000, "resize_factor": 1.2}

$ python: pickle.load('/app/chroma_db/0c4b1056-e0c4-44f8-98fa-6b88d22c2a51/index_metadata.pickle')
  total_elements_added = 39195
  id_to_label (live)   = 422
  id_to_seq_id         = 0
```

三处互不引用的证据：`vector_scope.distance_function=l2`（PG 登记）、`chunk_vectors_embedding_idx ... USING hnsw (embedding vector_l2_ops)`（PG 实际索引算符）、Chroma 侧集合 `metadata=null`（没登记）所以只能实测——U1 探针 `matched=["l2"]`，与 sqlite `collections.schema_str` 里声明的 `"space":"l2"` 一致。

## 4. 距离口径对齐是量出来的（判据③）

| 探针 | 次数 | 可核次数 | 开根号后最大差 |
|---|---|---|---|
| `chroma_self` | 111 | 95 | 2.583e-06 |
| `cross_engine` | 95 | 95 | 3.63e-06 |

⇒ 同一枚 query、同一枚命中向量，Chroma 交回的数开根号与 PG 交回的欧氏距离最大差 `3.63e-06`（`chroma_self` 那组 `2.583e-06`）。「Chroma 报平方欧氏」这一层从断言变成实测，口径不是靠两边都写着 l2 就算对齐。

**HNSW 近似性会不会造成名次差？本轮量到的是「不会」，并且是有条件的不会：**

- `pg_index_vs_exact_same_set` = **135/135**：同一条连接、同一批向量，只把 `enable_indexscan` 关掉重算，索引腿与全表精确腿逐题全等——成员和名次一格没动。
- 条件是当时会话 `SHOW hnsw.ef_search` = `40`（pgvector 默认值）。本轮没有扫参、没有为了好看把它调大。
- 边界写清楚：这条只在**这份 1008 枚 / k=5** 上量到。库长到几万枚以后这一格没量过，不替它外推。
- 另一格独立成立：两库各自精确算的 top-k 也 **135/135 全等**。所以两侧向量本体的 float32 重嵌入噪声（`max_abs_diff=2.1679687467468511e-07`、`mean_abs_diff=8.784e-09`、`identical=0/1008`）不改任何名次——它不够大。

## 5. 主读数（135 题 · k=5 · 未过滤 · 遍次 `h2`）

| 指标 | 值 |
|---|---|
| `questions` | 135 |
| `same_set` | 68 |
| `differing_set` | 67 |
| `mean_overlap` | 3.6741 |
| `mean_overlap_ratio` | 0.7348 |
| `mean_jaccard` | 0.6878 |
| `median_jaccard` | 1.0 |
| `questions_full_overlap` | 68 |
| `questions_zero_overlap` | 24 |
| `mean_abs_rank_shift` | 0.3378 |
| `max_abs_rank_shift` | 2 |
| `mean_kendall_tau` | 1.0 |
| `chroma_zero_rows` | 24 |
| `pg_zero_rows` | 0 |
| `chroma_only_zero` | 24 |
| `pg_only_zero` | 0 |
| `pg_index_vs_exact_same_set` | 135 |
| `chroma_index_vs_exact_same_set` | 68 |
| `exact_sides_same_set` | 135 |

逐题明细（每题两侧 top-5 的 id 与距离、重合、位移、τ、四条腿对照）：`docs/testing/r59b-recall-comparison-2026-09-24.json`，未截断。

**归因（先说哪条腿错）**：`chroma_index_vs_exact_same_set` = 68/135 与 `same_set` = 68/135 是**同一批题**，而 PG 腿 135/135 等于它自己的精确解 ⇒ 每一题分歧都落在「Chroma 的 ANN 腿 ≠ Chroma 自己在同一批向量上的精确解」。形态：43 题两侧各交 5 行但成员对称换入换出，24 题 Chroma 整条交 0 行；`mean_kendall_tau` 恒 `1.0`、`max_abs_rank_shift` = `2` ⇒ 共同成员之间的相对次序两侧一致，**分歧全在谁进 top-5**，不是排序翻转。

## 6. 分歧题逐题清单（67 题）

`形态`：`空`＝Chroma 这条腿交回 0 行；`换`＝两侧都交 5 行但成员不同。`τ`＝Kendall tau，`首位`＝第一个名次开始不同的位置（1 起）。

| # | 题集 | 题号 | 题面 | 重合 | 形态 | 首位 | 平均位移 | 最大 | τ | Chroma 独有 | PG 独有 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 30 | `doc-01` | 住宿费标准是多少？ | 4/5 | 换 | 3 | 0.5 | 1 | 1.0 | 公司年会流程_2025年度.txt_1 | dl.pdf_510 |
| 2 | 30 | `doc-02` | 差旅报销先走什么流程？ | 3/5 | 换 | 1 | 1.6667 | 2 | 1.0 | dl.pdf_200, 销售话术培训_应对话术集.txt_1 | dl.pdf_502, dl.pdf_510 |
| 3 | 30 | `doc-03` | 超住宿标准需要谁审批？ | 4/5 | 换 | 3 | 0.5 | 1 | 1.0 | 公司年会流程_2025年度.txt_1 | dl.pdf_510 |
| 4 | 30 | `doc-05` | 制度适用于哪些员工？ | 3/5 | 换 | 1 | 1.6667 | 2 | 1.0 | dl.pdf_200, dl.pdf_288 | dl.pdf_502, dl.pdf_510 |
| 5 | 30 | `data-01` | 哪个部门花费最高？ | 4/5 | 换 | 2 | 0.75 | 1 | 1.0 | dl.pdf_288 | dl.pdf_510 |
| 6 | 30 | `data-02` | 哪个部门花费最低？ | 3/5 | 换 | 4 | 0.0 | 0 | 1.0 | dl.pdf_215, dl.pdf_286 | dl.pdf_510, dl.pdf_534 |
| 7 | 30 | `data-03` | 最高和最低差多少？ | 4/5 | 换 | 4 | 0.25 | 1 | 1.0 | dl.pdf_550 | dl.pdf_510 |
| 8 | 30 | `metric-02` | 退款是否计入费用？ | 3/5 | 换 | 1 | 1.6667 | 2 | 1.0 | 年度经营报告2026H1.txt_11, dl.pdf_288 | dl.pdf_502, dl.pdf_510 |
| 9 | 30 | `metric-03` | 住宿费按晚还是按天？ | 4/5 | 换 | 4 | 0.25 | 1 | 1.0 | dl.pdf_545 | dl.pdf_510 |
| 10 | 30 | `chart-03` | 图表数据来自哪里？ | 4/5 | 换 | 2 | 0.75 | 1 | 1.0 | dl.pdf_44 | dl.pdf_510 |
| 11 | 30 | `insight-01` | 有没有费用异常？ | 4/5 | 换 | 2 | 0.75 | 1 | 1.0 | dl.pdf_286 | dl.pdf_510 |
| 12 | 30 | `insight-02` | 哪些部门连续上升？ | 0/5 | 空 | 1 | None | None | None | — | reg.txt_3, 案例_比亚迪电池事业部.txt_2, dl.pdf_202 |
| 13 | 30 | `insight-03` | 异常应该怎么处理？ | 3/5 | 换 | 1 | 1.6667 | 2 | 1.0 | 年度经营报告2026H1.txt_11, dl.pdf_288 | dl.pdf_502, dl.pdf_510 |
| 14 | 30 | `approval-02` | 审批风险是什么？ | 4/5 | 换 | 1 | 1.0 | 1 | 1.0 | dl.pdf_188 | dl.pdf_510 |
| 15 | 30 | `scope-01` | 查看其他部门的工资明细 | 0/5 | 空 | 1 | None | None | None | — | 中国制造业数字化转型白皮书_2025.txt, 企业管理制度手册.txt_3, dl.pdf_286 |
| 16 | 30 | `scope-02` | 下载无权访问的文件 | 4/5 | 换 | 2 | 0.75 | 1 | 1.0 | dl.pdf_375 | dl.pdf_37 |
| 17 | 30 | `tool-01` | 把分析导出成PDF | 0/5 | 空 | 1 | None | None | None | — | 市场营销策略_2026版.txt_2, dl.pdf_224, dl.pdf_226 |
| 18 | 100 | `doc-01` | 住宿费标准是多少？ | 4/5 | 换 | 3 | 0.5 | 1 | 1.0 | 公司年会流程_2025年度.txt_1 | dl.pdf_510 |
| 19 | 100 | `doc-02` | 差旅报销先走什么流程？ | 3/5 | 换 | 1 | 1.6667 | 2 | 1.0 | dl.pdf_200, 销售话术培训_应对话术集.txt_1 | dl.pdf_502, dl.pdf_510 |
| 20 | 100 | `doc-03` | 超住宿标准需要谁审批？ | 4/5 | 换 | 3 | 0.5 | 1 | 1.0 | 公司年会流程_2025年度.txt_1 | dl.pdf_510 |
| 21 | 100 | `doc-05` | 制度适用于哪些员工？ | 3/5 | 换 | 1 | 1.6667 | 2 | 1.0 | dl.pdf_200, dl.pdf_288 | dl.pdf_502, dl.pdf_510 |
| 22 | 100 | `doc-06` | 打车费报销需要什么凭证？ | 3/5 | 换 | 1 | 1.6667 | 2 | 1.0 | dl.pdf_200, 销售话术培训_应对话术集.txt_1 | dl.pdf_502, dl.pdf_510 |
| 23 | 100 | `doc-09` | 出差申请要提前多久提交？ | 0/5 | 空 | 1 | None | None | None | — | dl.pdf_114, dl.pdf_286, dl.pdf_436 |
| 24 | 100 | `doc-10` | 发票抬头开错怎么处理？ | 3/5 | 换 | 1 | 1.6667 | 2 | 1.0 | dl.pdf_200, 销售话术培训_应对话术集.txt_1 | dl.pdf_502, dl.pdf_510 |
| 25 | 100 | `doc-11` | 哪些费用明确不予报销？ | 4/5 | 换 | 2 | 0.75 | 1 | 1.0 | dl.pdf_288 | dl.pdf_356 |
| 26 | 100 | `doc-12` | 审批通过后多久打款？ | 3/5 | 换 | 1 | 2.0 | 2 | 1.0 | dl.pdf_288, dl.pdf_48 | dl.pdf_224, dl.pdf_510 |
| 27 | 100 | `doc-13` | 跨部门项目费用归口谁？ | 0/5 | 空 | 1 | None | None | None | — | reg.txt_0, reg.txt_10, reg.txt_2 |
| 28 | 100 | `doc-19` | 制度改版后旧单据按哪一版执行？ | 4/5 | 换 | 4 | 0.25 | 1 | 1.0 | MYO_V5.4_更新日志.txt_1 | dl.pdf_567 |
| 29 | 100 | `chat-08` | 两个人合住一间，标准可以叠加吗？ | 3/5 | 换 | 3 | 0.3333 | 1 | 1.0 | dl.pdf_200, 财务管理制度_V2.0.txt_0 | dl.pdf_451, dl.pdf_510 |
| 30 | 100 | `chat-10` | 只给我结论，不要引用条款 | 3/5 | 换 | 1 | 1.0 | 1 | 1.0 | 公司年会_优秀员工获奖感言.txt_0, dl.pdf_52 | dl.pdf_405, dl.pdf_502 |
| 31 | 100 | `chat-12` | 这个标准去年是多少？ | 4/5 | 换 | 2 | 0.75 | 1 | 1.0 | ISO27001信息安全管理体系_简介.tx | dl.pdf_510 |
| 32 | 100 | `metric-02` | 退款是否计入费用？ | 3/5 | 换 | 1 | 1.6667 | 2 | 1.0 | 年度经营报告2026H1.txt_11, dl.pdf_288 | dl.pdf_502, dl.pdf_510 |
| 33 | 100 | `metric-03` | 住宿费按晚还是按天？ | 4/5 | 换 | 4 | 0.25 | 1 | 1.0 | dl.pdf_545 | dl.pdf_510 |
| 34 | 100 | `metric-04` | 销售部的活跃客户数按什么口径统计… | 0/5 | 空 | 1 | None | None | None | — | reg.txt_0, reg.txt_10, reg.txt_2 |
| 35 | 100 | `metric-05` | 运营部的活跃客户数按什么口径统计… | 0/5 | 空 | 1 | None | None | None | — | reg.txt_0, reg.txt_10, reg.txt_2 |
| 36 | 100 | `metric-10` | 财务部把这笔报销费用算进哪个月？ | 0/5 | 空 | 1 | None | None | None | — | IT安全管理制度V3.1.txt_6, reg.txt_0, reg.txt_3 |
| 37 | 100 | `metric-11` | 市场部把这笔报销费用算进哪个月？ | 0/5 | 空 | 1 | None | None | None | — | IT安全管理制度V3.1.txt_6, reg.txt_0, reg.txt_3 |
| 38 | 100 | `metric-13` | 财务部算人均产值用哪个分母？ | 0/5 | 空 | 1 | None | None | None | — | reg.txt_3, 员工培训与发展管理办法.txt_2, 员工手册_2025正式版.txt_2 |
| 39 | 100 | `metric-18` | 项目月报里，项目部怎么判定里程碑… | 0/5 | 空 | 1 | None | None | None | — | IT安全管理制度V3.1.txt_6, reg.txt_2, reg.txt_3 |
| 40 | 100 | `metric-19` | 项目月报里，质量部怎么判定里程碑… | 0/5 | 空 | 1 | None | None | None | — | IT安全管理制度V3.1.txt_6, reg.txt_3, 员工培训与发展管理办法.txt_2 |
| 41 | 100 | `data-01` | 哪个部门花费最高？ | 4/5 | 换 | 2 | 0.75 | 1 | 1.0 | dl.pdf_288 | dl.pdf_510 |
| 42 | 100 | `data-02` | 哪个部门花费最低？ | 3/5 | 换 | 4 | 0.0 | 0 | 1.0 | dl.pdf_215, dl.pdf_286 | dl.pdf_510, dl.pdf_534 |
| 43 | 100 | `data-03` | 最高和最低差多少？ | 4/5 | 换 | 4 | 0.25 | 1 | 1.0 | dl.pdf_550 | dl.pdf_510 |
| 44 | 100 | `data-08` | 住宿费和餐费分别合计多少？ | 0/5 | 空 | 1 | None | None | None | — | browser_acceptance_pol, 供应商管理制度_含评估表.txt_1, 合同管理办法_法务版.txt_1 |
| 45 | 100 | `data-09` | 有没有重复提交的单据号？ | 4/5 | 换 | 2 | 0.75 | 1 | 1.0 | dl.pdf_286 | dl.pdf_510 |
| 46 | 100 | `insight-01` | 有没有费用异常？ | 4/5 | 换 | 2 | 0.75 | 1 | 1.0 | dl.pdf_286 | dl.pdf_510 |
| 47 | 100 | `insight-02` | 哪些部门连续上升？ | 0/5 | 空 | 1 | None | None | None | — | reg.txt_3, 案例_比亚迪电池事业部.txt_2, dl.pdf_202 |
| 48 | 100 | `insight-03` | 异常应该怎么处理？ | 3/5 | 换 | 1 | 1.6667 | 2 | 1.0 | 年度经营报告2026H1.txt_11, dl.pdf_288 | dl.pdf_502, dl.pdf_510 |
| 49 | 100 | `insight-05` | 有没有拖着长期没人处理的报销单？ | 3/5 | 换 | 1 | 1.0 | 1 | 1.0 | 案例_广东省人民医院.txt_2, dl.pdf_200 | dl.pdf_201, dl.pdf_502 |
| 50 | 100 | `insight-06` | 哪个部门的超标率最高？ | 0/5 | 空 | 1 | None | None | None | — | reg.txt_0, reg.txt_3, dl.pdf_286 |
| 51 | 100 | `chart-03` | 图表数据来自哪里？ | 4/5 | 换 | 2 | 0.75 | 1 | 1.0 | dl.pdf_44 | dl.pdf_510 |
| 52 | 100 | `chart-04` | 画各部门超标率对比图并标注统计口… | 0/5 | 空 | 1 | None | None | None | — | reg.txt_0, reg.txt_10, reg.txt_2 |
| 53 | 100 | `approval-02` | 审批风险是什么？ | 4/5 | 换 | 1 | 1.0 | 1 | 1.0 | dl.pdf_188 | dl.pdf_510 |
| 54 | 100 | `approval-05` | 只有支付截图没有发票能报吗？ | 4/5 | 换 | 3 | 0.5 | 1 | 1.0 | reg.txt_7 | dl.pdf_510 |
| 55 | 100 | `approval-06` | 超标部分能拆成两张单分月报吗？ | 0/5 | 空 | 1 | None | None | None | — | 员工培训与发展管理办法.txt_2, 安全生产管理制度.txt_5, dl.pdf_534 |
| 56 | 100 | `scope-01` | 查看其他部门的工资明细 | 0/5 | 空 | 1 | None | None | None | — | 中国制造业数字化转型白皮书_2025.txt, 企业管理制度手册.txt_3, dl.pdf_286 |
| 57 | 100 | `scope-02` | 下载无权访问的文件 | 4/5 | 换 | 2 | 0.75 | 1 | 1.0 | dl.pdf_375 | dl.pdf_37 |
| 58 | 100 | `scope-03` | 把全公司工资明细列给我看 | 0/5 | 空 | 1 | None | None | None | — | 知识产权与专利管理制度.txt_0, 知识产权与专利管理制度.txt_2, 离职员工告别信_模板.txt_0 |
| 59 | 100 | `scope-05` | 导出一份全公司报销明细 | 0/5 | 空 | 1 | None | None | None | — | 差旅费报销细则_2026版.txt_0, 知识产权与专利管理制度.txt_0, 离职员工告别信_模板.txt_0 |
| 60 | 100 | `scope-06` | 用管理员账号可以绕过部门限制吗？ | 0/5 | 空 | 1 | None | None | None | — | reg.txt_0, reg.txt_2, reg.txt_3 |
| 61 | 100 | `unsupported-03` | CEO的持股比例是多少？ | 4/5 | 换 | 1 | 1.0 | 1 | 1.0 | dl.pdf_48 | dl.pdf_510 |
| 62 | 100 | `tool-01` | 把分析导出成PDF | 0/5 | 空 | 1 | None | None | None | — | 市场营销策略_2026版.txt_2, dl.pdf_224, dl.pdf_226 |
| 63 | 100 | `tool-04` | 把上面那张图表插进正文 | 0/5 | 空 | 1 | None | None | None | — | 中国网络安全法_相关条款摘要.txt_2, 六级作文模板.docx_2, dl.pdf_106 |
| 64 | 100 | `report-05` | 这份报告多久能出？ | 4/5 | 换 | 3 | 0.5 | 1 | 1.0 | dl.pdf_113 | dl.pdf_451 |
| 65 | 100 | `report-07` | 超标项在报告里怎么呈现？ | 4/5 | 换 | 2 | 0.75 | 1 | 1.0 | dl.pdf_419 | dl.pdf_510 |
| 66 | 100 | `report-08` | 能引用还没索引完的文档吗？ | 4/5 | 换 | 4 | 0.25 | 1 | 1.0 | dl.pdf_375 | dl.pdf_37 |
| 67 | 100 | `report-12` | 报告正文和表格数字对不上以哪个为… | 0/5 | 空 | 1 | None | None | None | — | 中国网络安全法_相关条款摘要.txt_2, dl.pdf_202, dl.pdf_375 |

清单里 `PG 独有` 反复出现的那几枚，就是 §7「不可达」那批向量——精确解里有它、Chroma 捞不出它：

- `深度学习入门：基于Python的理论与实现.pdf_510`：36 题
- `制度与口径登记表.txt_3`：13 题
- `深度学习入门：基于Python的理论与实现.pdf_502`：12 题
- `深度学习入门：基于Python的理论与实现.pdf_286`：10 题
- `制度与口径登记表.txt_0`：8 题
- `制度与口径登记表.txt_2`：6 题

## 7. Chroma 交不全的机制（本轮结掉的部分）

```text
$ sqlite3 'file:/app/chroma_db/chroma.sqlite3?mode=ro'
  embeddings rows        = 1008
  embeddings_queue       = 729 ops (seq 77968..78696)
  queue by operation     = {0: 657, 3: 72}   # 0=put, 3=delete
  max_seq_id per segment = {"7a42b6a9-8a48-4f4a-ad83-61674bed1563": 78696, "0c4b1056-e0c4-44f8-98fa-6b88d22c2a51": 77968}   # 前一个是元数据段，后一个是 HNSW 向量段
  collection space       = l2
  collection hnsw config = {"ef_construction": 100, "max_neighbors": 16, "ef_search": 100, "num_threads": 12, "batch_size": 100, "sync_threshold": 1000, "resize_factor": 1.2}

$ python: pickle.load('/app/chroma_db/0c4b1056-e0c4-44f8-98fa-6b88d22c2a51/index_metadata.pickle')
  total_elements_added = 39195
  id_to_label (live)   = 422
  id_to_seq_id         = 0
```

读出来是一句话：**Chroma 的持久索引装不下这批语料**。它的元数据段有 1008 行、集合水位已到 seq 78696，而 HNSW 向量段自己的水位只到 seq 77968——中间 729 条日志（657 put / 72 delete）从没回放进索引。段里 `id_to_label` 只剩 422 枚活标签，而 `total_elements_added=39195` 说明这个库历史上被反复重灌过。配置 `sync_threshold=1000` 大于未消费的 729，所以它不会自己追平。

实测后果（与读数**同进程**量的探针：`n_results=count()` 一次要回全库）：只回 **878 枚**，且捞回枚数在 875–882 之间随进程摆 ⇒ 库里约有 130 枚向量**在生产库里有、在它的 ANN 里不可达**。

**没结的部分（不猜）**：24 题交 0 行这一格，与上面「130 枚不可达」在字节层**不是同一件事**。取证过程：加 `where`、加 `ids` 白名单、把 `n_results` 从 1 放到 1008 都仍然交 0 行；把该题的真最近邻向量本身当查询喂回去能交 5 行；该题向量 `isfinite` 全真、norm ≈ 22；与远近无关（交 0 的题最近邻距离跨 12.28–17.79，交 5 行的题最大到 18.81）。**成因没量到**，只量到了形状与「与什么无关」。

## 8. 跨进程稳定性（同一枚脚本、同一份输入，反复重跑）

| 遍次 | 谓词 | same_set | 分歧 | Chroma 0 行 | PG 0 行 | pg索引=pg精确 | chroma索引=chroma精确 | 两侧精确相等 | 全库捞回 |
|---|---|---|---|---|---|---|---|---|---|
| `h1` | （无） | 89 | 46 | 24 | 0 | 135/135 | 89/135 | 135/135 | 877 |
| `h2` | （无） | 68 | 67 | 24 | 0 | 135/135 | 68/135 | 135/135 | 878 |
| `h3` | （无） | 68 | 67 | 24 | 0 | 135/135 | 68/135 | 135/135 | 876 |
| `h4` | （无） | 68 | 67 | 24 | 0 | 135/135 | 68/135 | 135/135 | 876 |
| `h5` | （无） | 68 | 67 | 24 | 0 | 135/135 | 68/135 | 135/135 | 881 |
| `p1a` | `{"classification": {"$in": [1, 2, 3]}}` | 68 | 67 | 24 | 0 | 135/135 | 68/135 | 135/135 | 877 |
| `p1b` | `{"classification": {"$in": [1, 2, 3]}}` | 68 | 67 | 24 | 0 | 135/135 | 68/135 | 135/135 | 877 |
| `p2a` | `{"$and": [{"classification": {"$in": [1, 2, 3]}}, {"department": {"$in": [""]}}]}` | 68 | 67 | 24 | 0 | 135/135 | 68/135 | 135/135 | 880 |
| `p2b` | `{"$and": [{"classification": {"$in": [1, 2, 3]}}, {"department": {"$in": [""]}}]}` | 68 | 67 | 24 | 0 | 135/135 | 68/135 | 135/135 | 882 |
| `p2c` | `{"$and": [{"classification": {"$in": [1, 2, 3]}}, {"department": {"$in": [""]}}]}` | 69 | 66 | 24 | 0 | 135/135 | 69/135 | 135/135 | 878 |
| `p3` | `{"$and": [{"classification": {"$in": [1]}}, {"department": {"$in": ["研发中心"]}}]}` | 135 | 0 | 135 | 135 | 135/135 | 135/135 | 135/135 | 875 |
| `p4` | `{"classification": {"$in": [2, 3]}}` | 135 | 0 | 135 | 135 | 135/135 | 135/135 | 135/135 | 880 |

未过滤 5 遍的 `same_set` 分布：`{"h1": 89, "h2": 68, "h3": 68, "h4": 68, "h5": 68}` ⇒ 众数 68，但有一遍落到 89（差 21 题）；带全命中谓词的 5 遍是 68/68/68/68/69。**同一份输入、同一枚脚本，换进程答案集会变**——这是遗留腿的性质，不是量具的性质（下面逐腿对账可证）。

逐腿对账（单位＝多少题的这条腿变了；每一行的基印在标签里）：

| 对照 | `query_sha` | `chroma_ids` | `pg_ids` | `pg_exact_ids` | `chroma_exact_ids` |
|---|---|---|---|---|---|
| 未过滤 vs 未过滤：`h2` vs `h1` | 0 | 36 | 0 | 0 | 0 |
| 未过滤 vs 未过滤：`h2` vs `h3` | 0 | 0 | 0 | 0 | 0 |
| 未过滤 vs 未过滤：`h2` vs `h4` | 0 | 1 | 0 | 0 | 0 |
| 未过滤 vs 未过滤：`h2` vs `h5` | 0 | 0 | 0 | 0 | 0 |
| 全命中谓词(w1) 两遍：`p1a` vs `p1b` | 0 | 0 | 0 | 0 | 0 |
| 全命中 $and 谓词(w2)：`p2a` vs `p2b` | 0 | 1 | 0 | 0 | 0 |
| 全命中 $and 谓词(w2)：`p2a` vs `p2c` | 0 | 3 | 0 | 0 | 0 |
| 未过滤 vs 全命中谓词(w2)：`h2` vs `p2a` | 0 | 1 | 0 | 0 | 0 |

- **会动的只有 `chroma_ids` 这一条腿**。`query_sha` 全程 0/135 变化 ⇒ 题向量不抖，抖动不来自 embedding 侧；`chroma_exact_ids`（在 Chroma 自己的向量快照上精确算）0/135 ⇒ 库里的数不抖；`pg_ids` / `pg_exact_ids` 0/135 ⇒ PG 腿跨进程逐题一位不差。
- 全命中谓词相对未过滤动了 1 处 `chroma_ids`、PG 腿 0 处 ⇒ **加不加这份谓词，改的是 Chroma 那条近似腿的遍历终点，不改 PG 的答案**。
- 语料在 12 遍里 `stable=True`：读前读后两侧都是 1008/1008。
- 与前任对照：前任报过 same_set 在 68/99/89/68 之间抖。本轮量到的是同一族现象（众数 68、最高 89、历史极值 92），但**抖的方向对 PG 有利**：抖的只有 Chroma 腿，PG 腿从不参与。

## 9. 权限谓词下推这一格量到了什么、没量到什么

| 谓词（`--where-json`） | 命中 | same_set | PG 腿 | Chroma 腿 | 判读 |
|---|---|---|---|---|---|
| `{"classification":{"$in":[1,2,3]}}` | 1008/1008 | 68 · 68 | 与未过滤逐题全等 | 与未过滤同形 | 下推机制通 |
| `{"$and":[classification, department in ['']]}` | 1008/1008 | 68 · 68 · 69 | 与未过滤逐题全等 | 见 §8 | `$and` 能翻成 SQL 且不改 PG 答案 |
| `{"$and":[classification, department=['研发中心']]}` | **0** | 135 | 135/135 交 0 行 | 135/135 交 0 行 | 两侧一致地空：**PG 侧没有漏放行** |
| `{"classification":{"$in":[2,3]}}` | **0** | 135 | 135/135 交 0 行 | 135/135 交 0 行 | 换一列，仍然两侧对称 |

- SQL 腿用的就是生产要发的同一段（`app/rag/pg_store.py:sql_scope_filter`）。全命中 `$and` 的原文与绑定参：
  `clause = (classification = ANY(%s::integer[]) AND department = ANY(%s::text[]))` / `params = ["[1, 2, 3]", "['']"]`
- 掩码腿复用生产热集在用的 `app/rag/retriever.py:metadata_matches`；`chroma_metadata_rows=1008`、全命中谓词的 `chroma_exact_masked_rows=1008`、零命中谓词的 `=0`（掩码读不满整库就判前置不满足，不用少几行的掩码算「两侧一致」）。
- 🔴 **这一格没量到**：本库 `classification` 全 = 1、`department` 全 = `''`（两侧一致），谓词只能全命中或全不命中。**「有选择性的过滤下两侧召回差多少」在这份语料上量不出来**，本轮不声称量过。要量它得先有一份跨部门/跨密级的语料，且在沙盒库里量。
- 一个取证陷阱记录在案：两份评测集 135 题的 `id` **不唯一**（唯一 id 只有 105 枚）。对账一律按 `(source, 行号, id)`；按 id 对账会把两题并成一题，自己造出假的「两侧一致」。

## 10. 落地的代码（改了实现，**没翻默认**）

| 文件 | 改了什么 |
|---|---|
| `app/rag/indexing.py` | `INDEX_BACKENDS` 认 `chroma`/`pgvector` 两个值（原来写死一个）、新增 `read_backend()` / `pgvector_reads_enabled()`。**默认值一字未动，仍是 `chroma`** |
| `app/rag/pg_store.py` | 读半件：`sql_scope_filter`（Chroma 形状谓词→SQL；翻不出来就拒答，绝不退化成「没有 WHERE」）、`search_vectors`、`read_topk`（双写/算符/表名三道前置＋五枚拒答码）、读腿计数器 |
| `app/rag/retriever.py` | 新增 `RETRIEVAL_SERVER_PGVECTOR` 与 `_pgvector_hits()`，挂在遗留 Chroma 腿之前；开关关着时**一个 SQL 都不发**，遗留腿与切读前逐字一致。`_hot_hits` 在切读态整层让路 |
| `app/rag/hot_index.py` | 加一枚「因读后端切换而让路」的原因码 |
| `tests/test_r59b_pg_read_switch.py` | 24 枚新用例（含反证钉） |

形状契约：`tests/test_r44_hot_index_chroma.py` 钉住的那五个键**一位未动**；既有读数脚本的 JSON 形状也未改——本轮新增的都是 `meta` 下的新键（`chroma_reachability`、`scope_filter`），`questions` / `summary` 的既有键名与含义不变。

反证钉：11 枚变异逐条复验，**11 枚全部能让点名用例变红**（跑完按字节还原，md5 复核一致）。清单：`read_backend` 恒返回 `chroma`、`pgvector_reads_enabled` 恒 True、`_pgvector_hits` 无视开关、摘掉双写前置、摘掉算符映射核对、让 `sql_scope_filter` 在看不懂谓词时返回空 WHERE、摘掉热集让路守卫、把密级 NULL 补成 1 级、`_READ_COLUMNS` 摘掉一列、k<0 不折成 0、以及在 `read_topk` 的 finally 里加一句 commit。

这一轮复验**抓出两枚原本无齿的用例**，不是继承来的现成结论：

- `test_the_pg_hits_carry_exactly_the_hit_dict_shape` 原来只比键名集合 ⇒ 把 `_READ_COLUMNS` 里的 `classification` 摘掉仍然全绿（缺的键由 `_hit_dicts` 补成 None，键集合一字不变）。已补三行点名列断言（`classification` / `source` / `content` 必须真从 SQL 走回来）。
- `test_k_zero_asks_for_no_rows_instead_of_a_negative_limit` 原来只喂 `k=0` ⇒ `limit = int(k)` 这种写法也能过，负数会原样进 `LIMIT` 变成 PG 语法错误。已补一发 `k=-5`。
- 另一枚不是缺陷：`read_backend` 恒 `chroma` 那一条，第一次复验时点名点到了`test_the_switch_defaults_to_the_legacy_engine`（它断言的正是默认态，改坏了当然还绿）。改点到 `test_switched_reads_answer_from_pgvector_and_are_attributed_to_it` 才红。记在这里是为了别把『我点错了』写成『它无齿』。

## 11. 结论：切读现在能不能翻默认，还差哪几格

**本轮不翻。** 方向支持切：PG 腿 135/135 等于自己的精确解、从不交 0 行、跨 12 遍逐题 0 变化；67 题不一致没有一题归因到 PG 答错，全部归因到遗留索引装不下语料（持久段 422 枚活标签 vs 元数据段 1008 行）。翻默认要满足的格子还缺这几块：

1. **服务内端到端没在真库上跑过**。§10 那条腿今天只在 fake connection 用例下绿过。要量：真库上把 `DocumentRetriever.search` 的完整编排（权限闸门、活动先验、去重、命中字典形状）走通一次。谁量：总控开窗，一次 `/api/v1/chat`。
2. **热集让路的代价没量**。切读态下 `_hot_hits` 整层让路，今天靠热集答的那部分流量改走 SQL。要量：同批题在开关两侧各跑一遍，取延迟与命中分布。
3. **选择性权限过滤没量**（§9 那条 🔴）。本库值域单一，量不出来，得先造一份跨部门/跨密级的小语料进沙盒库。
4. **双写开满一轮重建未确认**。切读的语义前置是 `indexing.py` 的双写先跑满一轮全量重建；本轮只证明**当前**镜像逐枚齐（`only_in_pg=0`、`only_in_chroma=0`、向量本体最大差 2.1679687467468511e-07），没证明重建闭环跑过。
5. **遗留库仍在被写这件事要拍板**。`/app/chroma_db/chroma.sqlite3` 的 mtime 会随**只读**进程前进：静置 128 s 不动（两读同为 12:18:42），每开一遍读动一次（12:20:59 / 12:21:12 / 12:21:27 / 12:21:42 / 12:21:54）。切读后它不再答生产流量，但「读它会把它的索引往前推」得有人决定：顺手做一次全量重建，还是让它冻结在 422 枚活标签上。
6. **Chroma 交 0 行的成因未结**（§7）。它不影响切读判断（切过去就不再问它），但它决定翻默认前那轮回归拿什么当基线——今天的基线里有 24/135 题是空答复。

默认值翻与不翻由总控落笔；本轮 `INDEX_BACKEND` 保持 `chroma`。

## 12. 复现

```bash
docker cp scripts/r59_recall_compare.py enterprise-brain-backend-1:/tmp/r59b/scripts/
docker exec -w /tmp/r59b enterprise-brain-backend-1 \\
  python scripts/r59_recall_compare.py --chroma-dir /app/chroma_db \\
         --collection enterprise_docs --k 5 --out /tmp/r59b/h2.json --md /tmp/r59b/h2.md
# 带谓词：--where-json @/tmp/r59b/p_w2.json   （$in 里的 $ 会被 shell 吃掉，所以支持 @文件）
```

机读产物：`docs/testing/r59b-recall-comparison-2026-09-24.json`（135 题逐题）、`docs/testing/r59b-stability-2026-09-24.json`（12 遍汇总＋跨腿对账＋未量清单）。

---

## 13. 定向验证原文（不跑全量门，这机器今天脏重启过一次）

```text
$ .venv\\Scripts\\python.exe -m pytest tests/test_r59b_pg_read_switch.py -q
24 passed in 0.74s

$ .venv\\Scripts\\python.exe -m pytest tests/test_r59b_pg_read_switch.py \
    tests/test_r44_hot_index_chroma.py tests/test_r44_hot_index_coverage.py \
    tests/test_r44_hot_index_paging.py   tests/test_r44_hot_index_unit.py \
    tests/test_r79_hot_index_defaults.py tests/test_r79_hot_index_observability.py \
    tests/test_r58_pgvector_dual_write.py \
    tests/test_r76_chunk_vectors_join_the_publication.py \
    tests/test_r120_p3_collection_default.py tests/test_r120_dual_write_passthrough.py \
    tests/test_r125_status_vector_census.py \
    tests/test_r145_vector_mirror_set_audit_reads.py \
    tests/test_r145_vector_mirror_set_audit_is_read_only.py \
    tests/test_r157_u1_measured_distance.py tests/test_retrieval_permissions.py \
    tests/test_storage_contract.py -q
316 passed, 20 warnings in 37.95s

$ .venv\\Scripts\\python.exe -m pytest tests/test_r120_p3_collection_default.py \
    tests/test_r120_dual_write_passthrough.py tests/test_r125_status_vector_census.py \
    tests/test_r157_u1_measured_distance.py -q          # 手册追加 §9 之后复跑
68 passed in 1.00s
```

反证钉（11 枚变异）逐条输出：11 枚全部 RED，跑完 4 枚被改文件 md5 复核一致（还原干净）。
明细与两枚「原本无齿」用例的补强见 §10。

全量回归门（`scripts/run_gate.py`）**未跑**：本单硬边界禁止，且同机另有两枚 Agent 在跑测试。
