# 🔴 作废 — R59 召回对比读数（2026-09-24 09:5x 那一遍）

> **这份读数整份作废，不许再被任何文档或结论引用。**
> 替代件：`docs/testing/r59b-recall-reading-2026-09-24.md`（R59b 复测投，同一天 12:4x）。
> 单号：R59 → R59b。执行者：前任 `Ohm`（已死）→ R59b。

## 作废理由：两侧样本都取错了，一条腿都没读到真库

### 1. PG 腿根本没读库，被悄悄降级成 numpy 估算

产物里 `pg_leg.state = estimated_exact_knn`，原因原文：

```text
口径读不出：UndefinedTable 关系 "vector_scope" 不存在
LINE 1: ...mbedding_model, dimension, distance_function FROM vector_sco...
```

真因（总控 11:0x 真机取证）：宿主机 5432 上另有一个**野 PostgreSQL**（pid 8572，用户 `fengx`），
主树 `.env` 里那个 `postgresql://fengx:…@localhost:5432/enterprise_brain` 连的就是它，里面没有
`vector_scope`。真库在容器里（`postgres:5432/enterprise_brain`），R59b 实测它在位：
`schema_version=1`、`nomic-embed-text`、768 维、`distance_function=l2`、`hnsw_m=16`、
`hnsw_ef_construction=100`，`chunk_vectors` 1008 行，迁移 0001–0013 全在 `schema_migrations`。

⇒ 这份读数的「PG 侧」从头到尾是 **numpy 在一份 Chroma 快照上暴力算**，不是 pgvector。
它证明不了 pgvector 的任何性质。

### 2. Chroma 腿取的是临时沙盒，不是生产库

这份读数连的是 `%TEMP%\r59chroma`（401 枚）。生产读路径是 docker 卷
`enterprise-brain_vectordb` → 容器内 `/app/chroma_db`，collection `enterprise_docs`，
R59b 实测 **count = 1008**，与 PG 侧 1008 枚逐枚相等（`only_in_pg=0`、`only_in_chroma=0`、
交集 1008）。主树根那个 7.9 MB 的 `chroma_db/` 目录同样不是生产库。

⇒ 由这个错位派生出来的两句话一起作废：

- 「`chroma_vectors=401` vs 普查 1008，差 607 枚」——**假账**，两侧本来就都是 1008 枚同一批语料；
  前置疑点「两侧语料对不上」不存在。
- 「`same_set=135`、`mean_overlap=1.0`、`mean_jaccard=1.0` ⇒ 两侧 top-k 完全一致」——那是
  **Chroma 与 numpy 自己比自己**（另一条腿没读过库）。真读之后的数是 68/135 一致、67 题不一致。

## 这份文件里曾经写过的「已验证」字样

一律不采信。R59b 的处置是逐块判定，写在替代件的 §2 三态表里（继承／改写／推翻），
这份脚本本身（`scripts/r59_recall_compare.py`）的大部分只读取证逻辑被继承下来了——
作废的是**这一遍的样本与结论**，不是那 30 KB 代码的价值。

## 逐题明细去哪了

同目录那份 177 KB 的 `r59-recall-comparison-2026-09-24.json` 是这份作废读数的产物，
已移出仓外，不在版本库里。要考古就去找 `_quarantine`，正常读者不需要它。
