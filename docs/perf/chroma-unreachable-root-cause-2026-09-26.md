# R269 · 现网 Chroma 持久索引缺口的根因（只诊断，不开刀）

日期 2026-09-26 · 工作树 `C:/Users/fengx/PycharmProjects/be-r269` · 分支 `codex/be-r269` · 基点 `af55756`
引擎实取：chromadb **1.5.9**（chroma-rs，Rust 图；Python `local_hnsw.py` 只是参考实现）
判据源：`docs/handoff/2026-09-15-backend-followup-requests.md` §101.9

---

## 0. 结论（四句）

1. **「138 枚自探针取不到自己」不是索引损坏，是近似检索的候选预算被同坐标近重复吃光**（读路径
   的固有近似性 × 写路径攒出的代际堆）。它在**一枚都不删、纯 `add` 出来的健康库**上就能复现
   （本单实测 1,415/12,000 与 23/240），并把同一批向量交给 numpy 精确扫描做对照 ⇒ **0 漏**。
2. **「21/105 题空 top-5」才是持久图状态的缺陷**：截断只会给不满 k 行，给不出 0 行；现网那 21 题
   在 `k=50` 下仍然 0 行（`r2_emptydiag.json`），所以它不可能由 ef 解释。本单在同一形状上
   **复现过一次 889/1000 枚字面 0 行**（且跨进程稳定复测），但**同配方 5 次里只有 1 次出**——
   ⇒ 症状 B 定到「写序/并发相关的持久图状态空洞」这一层，**没有定到具体那一行代码**，不假装。
3. **两条症状同索引、不同因**：prod 侧实测「21 道空表题的精确 top-5 里只有 6/105 枚落进 138
   不可达集合」（`summary.json · chroma_index_forensics.empty_result_attribution`），两簇几乎不相交；
   本单在同一份 41 代库里也量到「889 空表 / 82 非空但问不到自己 / 29 正常」三簇并存 ⇒ 同一堆
   墓碑的两个不同阈值，因不同。
4. **方向题裁定（一句话）**：**更该快切 PG——这病在 Chroma 的读路径上，切读即愈**；切读治不到的
   三处_residuals_见 §5，它们与"要不要在 Chroma 侧单独修"无关，因为 Chroma 正在退役。

---

## 1. 事实基线（现场实取 + 对继承读数的纠正）

| 口径 | 读数 | 来源 |
|---|---|---|
| 两侧条目 | 1008 = 1008，差集 0 | `docs/perf/raw/p3-2026-09-26/summary.json` |
| 向量值 | bit-identical 0 枚，单元素最大差 2.17e-07 | 同上 `vector_value_equality` |
| 105 题 k=5 | mean_overlap 0.7238 / 逐位全等 55 / **空 21** | 同上 `round2_recall_k5` |
| Chroma 自比 | 同源自比 mean_overlap **0.700 而非 1.000** | 同上 `same_source_control` |
| PG 自比 | 1.0000 / 105 / 0 | 同上 `attribution_self_recall` |
| 自探针不可达 | **138/1008**，`dup_suspect=0`，`zero_distance_relabelled=0` | `.../chroma-unreachable-vectors.json` |
| 段字节 | `data_level0.bin 128,232,676` / `length.bin 159,692` / `link_lists.bin 345,604` / pickle 118,132 / sqlite 123,052,032 | `%TEMP%/p3r264/r3b_reach.log`（未入库，见 §7） |

槽数三套口径互证（本单在工作树索引上验证过同一公式，再回代现网 stat）：

```
128,232,676 / (132 + 4*768 + 8 = 3,212) = 39,923.0      data_level0.bin
159,692 / 4                              = 39,923        length.bin
→ 现网图平面里真实存在 39,923 个元素，在册记录 1,008 条 ⇒ 39.6 : 1
工作树 dev 索引同式复算：1,994,652/3,212 = 621 = 2,484/4 = pickle total_elements_added=621 ✔
```

### 1.1 必须点名的三处纠正

- 🔴 **`r3a_pickle.log` 里 `index_metadata.pickle → builtins.dict -> {}` 是假话**（这条会被
  读成"现网 label 表空了"）。原因在 `run3.py:19-30`：它 `getattr(obj, "max_elements" /
  "cur_element" / "label_list" …)` 探的**全是 Python 参考实现的属性名**，而 chroma-rs 的
  pickle 是一枚普通 `dict`，一个属性都没有 ⇒ 探到的字典为空 ⇒ 打印 `{}`。文件本身 118,132 B，
  按 dev 库实测 401 条 = 35,586 B（≈ 88.7 B/条）折算 ≈ **1,332 条**，与 1,008 在册同量级。
  **现网 pickle 不是空的**，谁也不许拿它当"索引状态损坏"的证据。
- ⚠ **「39,923 = 从未回收的 mmap 容量」这句要说准**：它是 `cur_element_count`（header.bin 第 6 枚
  u32 与两枚文件大小三套口径互证，见 §2 钉 ①），是**真实存在的图元素数**，不是预留容量。
- ⚠ **`by_document` 不是"某一档坏得突出"**：126/138 落在 586 块的大档里，但那是分母大。
  按**密度**看才是异常——大档 126/586 = **21.5%**，其余 8 档合计 12/422 = **2.8%**（7.7 倍差），
  而且 138 个 chunk_index 连续段 74 条、最长 7，无 stride / 无 mod 规律 ⇒ **不是批次边界或
  下标算错**，是"最大最同质的那一簇把候选预算吃光"。

---

## 2. 判据① · 逐项排除/坐实（每条都给命令与真实读数）

复算全部打在 `%TEMP%` 的临时目录上，工作树 `chroma_db/` 收尾按 sha256 复比全等（§6）。
所有实验脚本都在 `%TEMP%/r269_*.py`（按单不入库，本单结论已把读数抄进本文）。

| # | 候选机理 | 判定 | 证据（本单实取） |
|---|---|---|---|
| 1 | collection 命名/分片 | **排除** | dev/prod 都只有 1 枚 VECTOR 段；`segments` 表实取 2 行（vector `34022a7d…` + metadata `394336b4…`，prod 为 `0c4b1056…` 单段）；`retriever.py:882` 只可能拿到这一枚名字。今天探针「段数=1」逐档复核。 |
| 2 | metadata `where` 把条目滤空 | **对这两条症状排除**；另立一条无关引擎的隐患 | R264 两条腿都是**无 where 裸检索**：`run2.py:87-88` 与 `scripts/compare_vector_recall.py:499` 都不带过滤 ⇒ 21 空表与 138 不可达都不可能是 where 造成。但 `where` 打在没写过的键上确实 0 行（R162 已证），切读后跟着 PG 走 ⇒ §7 移交。 |
| 3 | HNSW `ef_search`/`ef_construction` 召回截断 | **症状 A 坐实为因**；**症状 B 不成立** | 同形状扫 ef：dim768/12,000 节点 σ=0.05 → miss **20(ef100)/4(ef1000)**，σ=0.10 → **5/2**；dim64/12,000 零删除 → miss **23→22→5**（ef 100/1000/5000）。反证 B 侧：现网 21 题 **k=50 仍 0 行**，而本仓所有 ef 扫（含 ef=8000 > 语料规模）从未打出过一次 0 行 ⇒ 截断给不出 0 行。 |
| 4 | sqlite 与向量段落盘不一致（WAL / 未 flush） | **排除** | 写进程 `os._exit(0)` 硬杀（base+3 代 / base+8 代）后重开：记录平面 1000、槽 4,000 / 9,000、**空表 0**、miss 7-22；`embeddings_queue` 回放把图补回来了，收尾只剩 1 条 purge 标记（`op=3`，`vector=NULL`）。sqlite mtime 与 HNSW mtime 差 8.4 h 是 `sync_threshold=1000` 节流的**表现**，不是丢更新。 |
| 5 | 删档未清索引 | **量级坐实（膨胀来源）**；**不是空表的因** | 钉 ④：删掉 40% 记录后槽仍 1,000；钉 ③：12 代重传 ⇒ `count()=1000` 而槽 **13,000**；反证 ⑦：95% 整档墓碑库（10,000 槽 / 500 在册）500 枚在册探针**空 0 短 0**，探针打在死档自己的坐标上也**空 0**。 |
| 6 | `document_id` 去重把条目折叠 | **排除** | `dup_suspect=0`（现网实取）；id 拼法是 `f"{filename}_{i}"`（`retriever.py:1324`），库里根本没有 `document_id` 这个键——现网回读的 metadata 键集实取为 `hash / classification / filename / department / chunk_index`（`r3b_reach.log`）。 |
| 7 | **（新增）同 id 代际堆 + 近重复** | **症状 A 的放大器，坐实** | 41 代同 id 重传（`delete(ids)` 紧跟 `add(ids)`，逐条照抄 `retriever.py:1357-1374`）⇒ 槽 41,000 / 在册 1,000；自探针缺口在 5 次同配方复跑里是 **201 / 155 / 13 / 268 / 889+82**，符号稳定（每轮都 > 0），量级随并发写序浮动。位相同（jitter=0）的那次是 96 miss / 0 空表。 |
| 8 | **（新增）段字节 level-0 邻接数直读** | **判读模型作废**（这条是排除自己人） | 健康库按 int32 读槽头会读出 `664 / 35,389,980 / 32,760` 这类非法邻接数（41,000 槽里 40,000 枚 > maxM0=32）。所以**旧「零邻接槽 = 受损指纹」不能当证据**；`tests/test_r269_index_state.py` 已把这条按实测改写成别的钉。 |

### 2.1 症状 A 的最小可复现机理（零删除、零损坏）

```
60 档 × 200 块 = 12,000 枚，dim=64，每档一团 σ=0.05 的近重复簇，纯 collection.add，一枚不删
  ef_search=100  → 自探针 240 枚里 23 枚问不到自己（9.6%）；空表 0
  ef_search=1000 → 22 枚（9.2%）
  ef_search=5000 →  5 枚（2.1%）
同一批向量交给 numpy 精确扫描 → 0 枚漏
```

对应到现网：`splitter` 是 `chunk_size=500 / chunk_overlap=50`（`retriever.py:889-892`）⇒ 同档相邻
块天生近重复；`深度学习入门…pdf` 586 块是一整本书 ⇒ 全库最大最同质的一簇；`retriever.py:882` 建集
合时**一个 hnsw 参数都不传** ⇒ `ef_search` 永远是默认 100。三者叠加，就是 21.5% : 2.8% 的密度差。

### 2.2 症状 B：复现到"存在这种状态"，没复现到"必然出这种状态"

```
41 代同 id 重传（同坐标 + σ=0.30 漂移），dim=128，槽 41,000 / 在册 1,000，从盘重开：
  在册自探针 k=5  → 空表 889、非空但问不到自己 82、正常 29
  在册自探针 k=50 → 空表 889        ← 与现网「k=5 与 k=50 同为 0 行」同形状
  旧代坐标探针    → 空表 898 / 895
  语料外随机探针  → 空表 177/200
换一个新进程重开同一枚目录：空表仍是 889（不是读的时候抖出来的）
```

同配方（同数据、同写序、同默认参数）复跑 3 次：`201 / 155 / 13` 枚 miss，**空表 0 / 0 / 0**
⇒ 这个"整片在册向量在图里无处可达"的状态**能被写出来、写出来就固化在盘上，但不是每次写都出现**。
所以本单把它定成「写序/并发相关的持久图状态空洞」，症状 B 的代码级归因**留空**（见 §5 未做到 2）。

---

## 3. 现网 21 道空表题的原始读数（从 `%TEMP%/p3r264/r2_emptydiag.json` 抄进本文固化）

`chroma5` 与 `chroma50` 都是 **0 行**，`brute5`（同一份快照、同一批向量、numpy 精确扫描）与
`pg5` **逐条相等**，探针向量本身健康（`len=768 nan=0 inf=0 norm≈21-23`）。这张表就是"排除向量本体、
排除语料缺块、只指向 Chroma 图平面"的证据。

| qid | chroma5 | chroma50 | norm | brute5 头名（= pg5 头名） |
|---|---|---|---|---|
| doc-09 | 0 | 0 | 22.4450 | 采购管理制度_最新.txt_2 |
| doc-13 | 0 | 0 | 22.1698 | 制度与口径登记表.txt_3 |
| metric-04 | 0 | 0 | 22.4379 | 制度与口径登记表.txt_3 |
| metric-05 | 0 | 0 | 22.4379 | 制度与口径登记表.txt_3 |
| metric-10 | 0 | 0 | 22.6069 | 制度与口径登记表.txt_3 |
| metric-11 | 0 | 0 | 22.6069 | 制度与口径登记表.txt_3 |
| metric-13 | 0 | 0 | 22.2149 | 员工培训与发展管理办法.txt_2 |
| metric-18 | 0 | 0 | 21.1400 | 员工培训与发展管理办法.txt_2 |
| metric-19 | 0 | 0 | 21.0431 | 员工培训与发展管理办法.txt_2 |
| data-08 | 0 | 0 | 22.0185 | browser_acceptance_policy.txt_0 |
| insight-02 | 0 | 0 | 22.3550 | 制度与口径登记表.txt_3 |
| insight-06 | 0 | 0 | 22.2794 | 制度与口径登记表.txt_3 |
| chart-04 | 0 | 0 | 22.0431 | 制度与口径登记表.txt_3 |
| approval-06 | 0 | 0 | 21.8904 | 销售部2026年Q2会议纪要.txt_2 |
| scope-01 | 0 | 0 | 21.9642 | 深度学习入门：基于Python的理论与实现.pdf_286 |
| scope-03 | 0 | 0 | 21.6115 | 知识产权与专利管理制度.txt_0 |
| scope-05 | 0 | 0 | 21.2380 | 知识产权与专利管理制度.txt_0 |
| scope-06 | 0 | 0 | 23.0605 | 制度与口径登记表.txt_3 |
| tool-01 | 0 | 0 | 21.7995 | 市场营销策略_2026版.txt_2 |
| tool-04 | 0 | 0 | 22.0545 | 深度学习入门：基于Python的理论与实现.pdf_286 |
| report-12 | 0 | 0 | 22.2964 | 深度学习入门：基于Python的理论与实现.pdf_52 |
| （对照）doc-01/02/03 | 5 | 50 | 23.18-23.27 | 正常返回 |

✅ 这张表的原始读数**已入库**：`docs/perf/raw/p3-2026-09-26/`（11 件，09-26 由总控收口，含
`r2_emptydiag.json`、`r2c_emptydiag.log`、`p3_harness.py` 与 RUN/RUN2/RUN3 三遍日志）。唯一
故意不入库的是 `qemb.json`（1.67 MB 查询向量表，可由本目录的 `p3_harness.py` 重算）。

---

## 4. 判据② · 代码级归因（文件:行号 → 症状）

| 位置 | 干什么 | 造成/放大哪个症状 | 性质 |
|---|---|---|---|
| `app/rag/retriever.py:1357-1364` + `:1366-1374` | 重传：`collection.delete(stale_ids)` 之后用**同一批 id** `collection.add`（`batch_size = 2000`，586 块的书一次就进 `_write_batch`） | **症状 A 的堆是这里攒出来的**（钉 ③ 实测 12 代 ⇒ 13,000 槽 / 1,000 在册） | 写入拓扑（不是 bug，但它是病态持久状态的制造者） |
| `app/rag/retriever.py:1206-1211` | 全库唯一向量写点 `_write_batch` | 同上，且是唯一可下刀的位置 | 同上 |
| `app/rag/retriever.py:882` | `get_or_create_collection("enterprise_docs")`，**不传任何 hnsw 配置** | 决定症状 A 的量级：`ef_search` 恒为默认 100（现网 schema 实取 `ef_search:100 / ef_construction:100 / max_neighbors:16 / sync_threshold:1000 / resize_factor:1.2`） | **读路径参数缺省**（今天实测：同数据把 ef 抬到 5000，缺口 9.6% → 2.1%） |
| `app/rag/retriever.py:889-892` | `chunk_size=500 / chunk_overlap=50` | 相邻块近重复 ⇒ 同簇内互相淹没候选预算 | 读路径缺省 × 语料形状 |
| `app/rag/retriever.py:1465-1472` | 无 where 时 `kwargs` 只有 `query_embeddings/n_results` | 证明 21 空表与 138 不可达都发生在裸检索上（与 §2 第 2 行配套） | 既不是这两条症状的因，也排除了它们 |
| `app/rag/retriever.py:1490-1492` | `documents=(results.get("documents") or [[]])[0]` ⇒ **0 行被当成合法的"库说没有"**，只有 embedding 挂掉才走 `_keyword_hits` 降级 | **症状 B 的用户可见后果就是这一行放大的**：库给 0 行，用户就拿到空上下文，而不是降级答案 | 读路径缺口（降级策略缺失）——在写域内，但按单"只诊断不开刀"，**不动**，见 §7 |
| `app/rag/retriever.py:1667` `delete_document` / `:1360` | 删除只打标记 | 槽位永不回收 ⇒ 症状 A 长期单调恶化（钉 ④） | 持久状态累积 |
| `app/rag/retriever.py:1302-1303` | `get(where={"filename": filename})` 取 stale_ids | **已核**：删档重传把记录平面收得干净（现网 1008=1008 无孤儿记录），不是"该删没删" | 排除 |
| 引擎侧：chroma-rs 1.5.9 | `rg compact` 只命中一处 docstring ⇒ **没有任何 compaction/defrag** | 上面那堆 39.6:1 的墓碑不会自己消 | 越域，移交 |
| **症状 B 的行号** | — | **本单交不出来**（见 §5 未做到 2）：写域内没有任何分支能把无过滤 query 变成 0 行；`:1473-1484` 上抛的是异常而不是空表 | 诚实留空 |

**总判据**：症状 A = **读路径的近似检索**（参数缺省 + 语料形状 + 写路径攒出的堆），不是持久状态损坏；
症状 B = **持久索引状态**（图平面上存在无处可达的空洞），不是读路径 bug。

---

## 5. 判据③ · 方向题（一句话裁定 + 切读治不到的三处）

> **裁定：更该快切 PG——病在 Chroma 的读路径与它自己的持久图状态上，切读即愈。**

为什么 138 枚不可达**不需要**在 Chroma 侧修：向量本体一枚不缺（`get` 1008/1008 读得回、与 PG
单元素最大差 2.17e-07），它们在 PGVector 侧是 `chunk_vectors` 里 1,008 行 1:1 的在册数据，
**读一旦切过去，这 138 枚就从"被近似检索漏掉"变成"被精确/半精确扫到"**——PG 腿对同一份数据
的自比是 1.0000 / 105 全等 / 0 空表。而在 Chroma 侧"修"它的唯一手段是重建那 1,008 枚索引，
`rebuild_index.py --apply` 在双写仍 `on` 的情况下会**立刻重新长出**一座没有 compaction 会去收的
39.6:1 墓碑堆（本单钉 ③④ 就是这条），代价是动生产卷，收益是零。

切读**治不到**、必须另外盯住的三处（不含糊，也不改上一句裁定）：

1. **`retriever.py:1490-1492` 的"0 行 = 合法空答案"**：这条语义与引擎无关。切读之后 PG 腿交回 0 行
   （权限过滤打空、scope 判定为 `embedding_scope_unknown`）时，用户照样拿到空上下文。
2. **`where` 下推的等价性**：`where` 打在没写过的键上就是 0 行（R162 已证），切读后这条跟着
   PG 走，不是 Chroma 病。R59 的判据里必须有一枚"同 where 两侧行数相等"。
3. **写入拓扑不变**：`delete 同 id → add 同 id` 的堆只在 Chroma 侧长，但只要 `VECTOR_DUAL_WRITE=on`
   还在喂它、且 3 进程共卷还在，回滚开关就立刻复发。归业主/总控处置，不是 R269 的刀。

---

## 6. 判据④ · `scripts/compare_vector_recall.py` 退出码归真

**实取现状**：HEAD（`af55756`）确有 **9 处** `raise SystemExit(字符串)`，与跟进单 §101.9 说的"九处"
逐行对上；本单把它们全部改成 `fail_precondition()` ⇒ `raise SystemExit(2)`，并在 `main()` 外面
加了一枚 `Exception` 兜底（`_compare()`）。

| HEAD 行号 | 现行号 | 前置原因 | HEAD 退出码 | 现在退出码 |
|---|---|---|---|---|
| `:100` | `:125` | 不接受的表名 | 1 | **2** |
| `:135` | `:160` | 连接串不是 PostgreSQL | 1 | **2**（现场注：该调用点实为死码，`app/db/connection.py:45` 先抛 `ValueError`，现在由 `main()` 兜底接住 ⇒ 仍然 2） |
| `:148` | `:173` | 量不到 `vector_scope` | 1 | **2** |
| `:156` | `:181` | `vector_scope` 多行 | 1 | **2** |
| `:166` | `:191` | 列类型不是 `vector(d)` | 1 | **2** |
| `:181` | `:206` | Chroma 目录不存在 | 1 | **2** |
| `:185` | `:210` | chromadb 不可用 | 1 | **2** |
| `:190` | `:215` | 打不开 Chroma 目录 | 1 | **2** |
| `:376` | `:402` | 题集不存在 | 1 | **2** |
| `:430` | `:471` | 距离口径不一致（六条前置里唯一一枚本来就对的那格） | **2** | 2（语义未改） |
| `:445` | `:486` | `return 1 if gap else 0` — 检出语料差集 | 1 | 1（未改） |
| `:478` | `:519` | `return 1 if differing or gap else 0` — 检出逐题差集 | 1 | 1（未改） |
| `:484` | `:541` | `raise SystemExit(main())` | — | 兜底改挂 `_compare()`，量具自身异常 ⇒ 2 |

退出码返回点实取：HEAD 有 `:113 return 0` / `:430 return 2` / `:445` / `:478` / `:484`；
工作树有 `:471 return EXIT_PRECONDITION` / `:486` / `:519` / `:541`。**"1 = 差异"的两格一个字没动**。

契约同时改写进 docstring：`0` 干净 / `1` **只**表示"跑成了且检出差异" / `2` 前置不满足，
且 `2` 的 **stderr 首行必带 `[前置不满足] `**。

### 6.1 反证钉（空库：目录真、集合名对、`count=0`）

`tests/test_r269_exit_codes.py` 造了一枚真目录 + 真名 `enterprise_docs` + `count=0` 的沙盒，断言：
`rc == 2`、stderr 首行含 `[前置不满足]`、**不得**出现「两边排序天然不同」那句冒领的文案、
且不许产出 `--out` 文件。

### 6.2 摘掉守卫必红（本会话实取）

```
baseline sha256 9d1e21156d18d4274f173ea3c9ac6864f2f3cb4c165276612d26b303659ec281
A 前置码退回 SystemExit(字符串)      | 锚点命中 1 → 12 failed, 6 passed
B 空库文案退回「先核对 0010」        | 锚点命中 1 →  2 failed, 16 passed
C 前置分支冒领 1                     | 锚点命中 1 →  2 failed, 16 passed
三处还原后 sha256 与基线相同: True ×3
```

---

## 7. 判据⑤ · 红线与读数

- **零新增 Chroma 依赖、零新增 Chroma 写点**：本轮 `app/rag/**` **一个字都没改**（`git diff --stat`
  只有 `scripts/compare_vector_recall.py`）；实验脚本只在 `%TEMP%`，且只用 `PersistentClient(tmp)`。
- **所有 Chroma 访问都打在临时目录**：`tests/test_r269_index_state.py` 里 8 枚用例的
  `PersistentClient` 落点全部由 `tmp_path` 提供；conftest 的 R134 闸门实取
  终轮实取「PersistentClient 调用: 31 次，其中落点被改道出工作树: 31 次（**0 个原路径**）」「工作树
  chroma_db 写回告警用例: **0 枚**」；本文件另加一枚 module 级 autouse 夹具按 sha256 复比工作树
  `chroma_db/`。
- **工作树索引全程未被动过**（收尾实取）：

```
基线条目=6 现值条目=6
逐文件 sha256 全等 = True
chroma.sqlite3 6,262,784  0b8cb318a0e0ba18…（与开工基线同一枚）
段目录 34022a7d…/data_level0.bin 1,994,652 bac4ff53eb7fa864…
```

- **生产卷**：`192.168.254.128` 本会话整程不可达（`ssh vm` 超时 2 次、ping 无响应），
  本轮**没有任何一次**连上现网，谈不上读写。
- **定向件全绿（实取）**：

```
tests/test_r269_index_state.py                                  8 passed（单跑 16.2s；同件复跑 2 次均绿）
tests/test_r269_exit_codes.py + test_r269_index_state.py
  + test_r157_u1_measured_distance.py + test_r162_chroma_zero_row_shape.py
  + test_r120_p3_collection_default.py
  终轮实取：                                                    78 passed, 1 warning in 88.53s
  （首轮同集亦 78 passed in 31.60s；差的是机器负载，不是用例集）
```

  唯一 warning 来自 R162 旧件自己（`test_degenerate_query_vectors_still_get_rows_back` 造极端探针时
  numpy 的 `overflow encountered in cast`），与本单改动无关。**没跑全量门**（按单，在途多枚）。

---

## 8. 复现命令原文

本机（全部零生产接触，只吃 `%TEMP%` 与工作树 `chroma_db` 的**只读**副本）：

```powershell
cd C:\Users\fengx\PycharmProjects\be-r269
# ①  sqlite 记录平面到底有没有向量列（判据② 的地基）
.venv\Scripts\python.exe $env:TEMP\r269_schema2.py
.venv\Scripts\python.exe $env:TEMP\r269_seg2.py
# ②  三套口径互证槽数 + 工作树索引自探针（健康对照）
.venv\Scripts\python.exe $env:TEMP\r269_localsnap.py
.venv\Scripts\python.exe $env:TEMP\r269_hdrs.py
# ③  症状 A：稠密同簇扫 ef_search
.venv\Scripts\python.exe $env:TEMP\r269_dense.py
.venv\Scripts\python.exe $env:TEMP\r269_x.py
# ④  症状 B：41 代同 id 重传 + 从盘重开；同配方复跑看浮动
.venv\Scripts\python.exe $env:TEMP\r269_e.py
.venv\Scripts\python.exe $env:TEMP\r269_rep.py
# ⑤  排除：硬杀写进程 / 双 client 共卷 / 95% 整档墓碑
.venv\Scripts\python.exe $env:TEMP\r269_f.py
.venv\Scripts\python.exe $env:TEMP\r269_multi2.py
# ⑥  红线复比
.venv\Scripts\python.exe $env:TEMP\r269_verify3.py
# ⑦  定向件
.venv\Scripts\python.exe -m pytest tests\test_r269_exit_codes.py tests\test_r269_index_state.py `
  tests\test_r157_u1_measured_distance.py tests\test_r162_chroma_zero_row_shape.py `
  tests\test_r120_p3_collection_default.py -q -p no:randomly
```

现网（**VM 一起来就该做的只读取证**，逐条只读；生产目录只 `stat` + `cp -a`，绝不打开）：

```bash
DC='docker compose --env-file deploy/.env.server -f docker-compose.yml'
$DC run --rm --no-deps -T -v "$PWD/..:/tree:ro" -v "$SCRATCH:/drv" backend sh /drv/r269_driver.sh
# 驱动内部顺序（全程零写入生产卷）：
#   1) (cd /app && find chroma_db -type f | sort | xargs sha256sum) > /drv/live_before.sha
#   2) cp -a /app/chroma_db /tmp/r269snap
#   3) sha256sum 对账 /tmp/r269snap 与 live_before（快照一致性）
#   4) 只读 python：pickle 六键与长度            ← 本单最缺的一枚数，见 §1.1 纠正
#        python - <<'PY'
#        import pickle,glob
#        p=glob.glob('/tmp/r269snap/*/index_metadata.pickle')[0]
#        d=pickle.load(open(p,'rb'))
#        print({k:(len(v) if hasattr(v,'__len__') else v) for k,v in d.items()})
#        # 期望 total_elements_added 与 §1 推出的 39,923 同量级；
#        # id_to_label 若明显 < total_elements_added ⇒ 差集就是"图里有槽、label 表不认"的那批
#        PY
#   5) 同法只读 python：header.bin 第 6 枚 u32 与 data_level0.bin/length.bin 三套口径互证
#   6) sqlite 只读：SELECT count(*) FROM embeddings; SELECT * FROM max_seq_id;
#                   SELECT count(*),max(seq_id) FROM embeddings_queue
#      （若 embeddings_queue 远大于 1 枚 purge 标记 ⇒ §2 第 4 行的"回放已自愈"要重开）
#   7) 收尾再 sha256 生产目录，与 live_before 全等才算完
```

---

## 9. 未做到 + 为什么（不写"应该/大概/基本"）

1. **没有一个数字是今天从现网取的**。`192.168.254.128` 整程不可达，R264 的 `/tmp/p3snap` 在
   `docker run --rm` 的容器里，随容器一起销毁了。现网证据只到 `docs/perf/raw/p3-2026-09-26/`
   与未入库的 `%TEMP%/p3r264/`。⇒ §2 的 8 条判定里，凡引用现网读数处都标了出处，可复核期已到。
2. **症状 B（21 题 0 行）没交得出可请求复现的最小复现物，也没交得出文件:行号**。本会话把同一
   配方跑了 6 遍：`889 空表 / 0 / 0 / 0 / 0`（另含 nt=1 那遍也是 0），只有第一次出现；出现后
   跨进程重读仍是 889。⇒ 我能钉的是"这种状态存在、会被写出来、写出来就固化"，不能钉"什么顺序
   必然写出它"。硬杀写进程、双 client 共卷、95% 墓碑、ef 扫四路尝试全部 0 复现。
3. **段字节的图结构没读通**：`data_level0.bin` 的槽头 int32 在带墓碑的健康库上会读出
   `35,389,980` 这类非法邻接数（§2 第 8 行），所以 `link_lists.bin` / level-0 邻接表 / 上层
   可达性的判读模型没建立 ⇒ "空洞在图上的形状"这条只能说存在，说不出邻居指针断在哪。
4. **`max_seq_id` / WAL 与 39,923 槽的对应关系没在现网复核**（工作树 dev 库上是
   `max_seq_id=621 = total_elements_added=621`，prod 未取）。若 prod 这两个数不等，§2 第 4 行
   的排除要重开。
5. **没跑全量回归门**：按单要求（在途多枚，xdist 争用会假红）。
6. **没动 `app/rag/**`**：§4 表里 `:1490-1492`（0 行不降级）落在我写域内，但按"只诊断不开刀"
   不动，转 §10 移交。
7. **门纪律更正（09-26 总控收口时追加）**：本节第 2 条那个“6 遍只出 1 遍”不是巧合，是
   **抖动率 ≈ 1/7**。它原本被写进 `tests/test_r269_index_state.py`：`assert ann_miss >= 1` 把一
   个设计上会浮动的量当了回归门，主树首跑即红。现已改为**门内只留确定性断言**
   （`count==1000` / `by_data==13000` / `len(stored)==1000` / `brute_miss==0`）另加两枚确定性
   守卫（探针每发必回 5 名且查的就是入库读回那一枚向量；槽位:记录恒 13:1），缺口
   量级改 `print` 现取记录。不 skip、不 xfail、不删件。同文件 `:224` 那枚
   `ann_miss >= 1` **保留**：它的语料是固定 seed 的 12,000 枚稠密近重复 + 240 发探针，
   连跑三次均绿（每次 3.5 s），与上面那个 1/7 不同因。

---

## 10. 移交项（本单发现、无权限或未开刀）

1. 🔴 **`app/rag/retriever.py:1490-1492`**：库交回 0 行被当成合法空答案，只有 embedding 挂掉才
   降级到关键词。与引擎无关，切读后同样存在。**建议并入 R59 判据**：切读时给 PG 腿也立一枚
   "0 行必须降级并记 `search_shape`"的钉。写域内但本单未动。
2. 🔴 **`deploy/.env.server:56` `VECTOR_DUAL_WRITE=on`（三进程一致）**：双写还在喂那座 39.6:1 的
   墓碑堆。是业主动作，本单不碰。
3. ⚠ **3 进程共卷**：`docker-compose.yml:167/209/244` + `deploy/queue_worker.py:237/288/514` →
   `app/api/v1/chat.py:89`，backend / queue_worker / scheduler 各持一枚 `DocumentRetriever` 打同一
   个卷。本会话只证到"同一进程内两个 `PersistentClient` 共卷无害"（`r269_multi2`：四个视角读数
   一致），**跨进程那层没证到也没否掉**（VM 不可达）。越域（`app/api`/`deploy`），移交。
4. ⚠ **`app/trace/**` 与评测集**：本单没碰、没有发现（R263 在途）。
5. ⚠ **`frontend/**`**：没碰（R267/R268 在途）。
6. ⚠ **chroma-rs 1.5.9 无任何 compaction/defrag**：任何"重建一次就好"的排期都不成立，
   只要写入拓扑不变，堆就长回来。这条要进 R59 之后的"Chroma 退役"验收，不该进"修 Chroma"的排期。
7. ✅ **`r2_emptydiag.json` 已入库**（09-26 总控裁定）：§3 那张承重表的原始 JSON、其日志、
   驱动脚本与三遍 RUN 一共 **11 件**落进 `docs/perf/raw/p3-2026-09-26/`；`qemb.json`（1.67 MB，可由
   `p3_harness.py` 重算）故意不入库。这张表从此可离线复核，不再依赖临时目录。