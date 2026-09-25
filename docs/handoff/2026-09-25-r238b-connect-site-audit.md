# R238b —— 建连站点审计与 `_db_ready` 死码复核（总控补做，零模型调用）

日期 2026-09-25 · 主树 HEAD `e5db4a4` · 执行人 总控 · 依据 单号 **R238** 判据⑤⑥（施工方 Epicurus 于
12:43:59 被上一班换模型打断，这两格"只报不动"的报告没来得及交回，代码面已另行并树）

本文件里的每一个数字都是这一班现取的，且**推翻了两处派工词的说法**（见 §4）。取证脚本只读，
零真握手、零容器操作、零模型调用；三处 `rg` 的形状陷阱记在 §5。

## 1. 全仓 16 枚 `psycopg.connect(...)` 逐枚读数

| 站点 | 所属函数 | 超时形状 | 调用方是否含 async 端点 | 备注 |
|---|---|---|---|---|
| `app/agents/orchestrator.py:167` | `_make_checkpointer` | 显式 `connect_timeout=2` | 否（import 期） | 建连发生在导入期 |
| `app/api/v1/alerts.py:45` | `_conn` | **无** | **是：4 枚端点**（`list_alerts`/`list_rules`/`create_rule`/`delete_rule`） | 🔴 最坏组合 |
| `app/api/v1/chat.py:853` | `_sess_conn` | **无** | **是：1 枚端点**（`get_session`） | 🔴 最坏组合 |
| `app/api/v1/feedback.py:70` | `_connect` | 显式 | 否 | |
| `app/common/auth.py:301` | `_raw_conn` | `**_connect_kwargs()` 注入 | 否（import 探针走它） | 关键字形状数不出超时，见 §5 |
| `app/common/monitoring.py:381` | `_probe_postgres` | 显式 | 否 | |
| `app/db/connection.py:64` | `open_connection` | 无（**有意**） | —— | R238 的边界本身，四枚开关全默认关 |
| `app/documents/catalog.py:334` | `_conn` | 显式 | 否 | |
| `app/memory/long_term.py:55` | `_conn` | **无** | 否 | |
| `app/memory/profile.py:36` | `_conn` | **无** | 否 | |
| `app/rag/indexing.py:1503` | `_connect` | 显式 | 否 | |
| `app/rag/retriever.py:567` | `_read_activity_signal_rows` | **无** | 否 | |
| `app/semantics/registry.py:514` | `_conn` | 显式 | 否 | |
| `app/storage/pending_approvals.py:105` | `_conn` | **无** | 否 | |
| `app/storage/persistence.py:595` | `build_persistence_adapter` | 显式 | 否 | |
| `scripts/audit_vector_mirror_sets.py:428` | `_ensure` | 显式 | 否 | 只读量具，R59c 一族 |

计数（按调用点，不按文本命中行）：**总 16 枚 = `app/**` 15 枚（含边界自身 1 枚）＋ `scripts/**` 1 枚**。
超时形状分布：**显式 8 枚 / 靠 `**_connect_kwargs()` 注入 1 枚 / 真无超时 7 枚**（其中边界外 6 枚，
第 7 枚是边界自己，默认关是 R238 判据①要求的状态）。
事件循环面：**5 枚站点的建连发生在 async 端点里**，全部来自上表两枚红色文件——
`app/api/v1/alerts.py`（4）与 `app/api/v1/chat.py`（1）。这 5 枚恰好都在"真无超时"那一组。

## 2. 这一栏为什么值得单独写

私有化部署一台机器一个服务进程。事件循环里同步建连且不带超时，意味着一次 DNS 抖动或对端 TCP 黑洞
能把**整个后端**钉住，而不是钉住一个请求：与 `MODEL_MAX_CONCURRENCY=1` 那条"第二个用户拿到离线文案"
相比，这一格是"所有人一起停住"。⇒ **R240（把 14 枚站点迁入边界）的判据必须加一条**：
`alerts.py:45` 与 `chat.py:853` 迁入边界之后，仍要单独判"不在事件循环上建连"（`run_in_threadpool`
或把端点改 sync 让 FastAPI 走线程池），不许只换个函数名就当这格过了。

## 3. 判据⑤：`_get_conn` 里那枚死码，以及它牵出的两句假话

可达性证明（全部现读，不引用注释）：
- `app/common/auth.py:164` `_using_memory_store()` 返回 `psycopg is None or not _db_ready`；
- `app/common/auth.py:487` `_get_conn()` 开头 `if _using_memory_store(): return _FakeConn()`；
- 要走到 `:490`，必须 `_db_ready` 为 **真**；而 `:490` 是 `if not _db_ready:`，为真的条件恰好相反。
⇒ **`app/common/auth.py:492` 的 `_create_schema(conn)` 与 `:493` 的 `_db_ready = True` 恒不可达**。
`_create_schema` 全仓三处调用：`:255`（`_retry_readiness_probe`，**生产专属**——`:237` 有
`not _is_production_environment()` 直接 `return False`）、`:475`（import 期探针）、`:492`（死码）。

由此两句假话，一句在注释、**一句是运维看得见的日志**：
- `app/common/auth.py:472` "探针失败今天也只记一条 warning，真正的补救在请求路径上（`_get_conn` 会重建表）"
  —— 括号里那半句不成立，`_get_conn` 永远不会重建表；
- `app/common/auth.py:479` `logger.warning("[Auth] Postgres 不可用，将在首次连接时建表: ...")`
  —— 同一句承诺写进了日志。客户第一次装、PG 容器比后端晚起几秒，就会在日志里看到一句不会发生的话。

**后果边界**（说清，不夸大）：非生产环境里没有自愈通路（`_retry_readiness_probe` 生产专属），
`_db_ready` 一旦在 import 期为假就锁定到重启；生产环境有 R230 那条重探，但它只翻就绪旗、
**不建表**——表由 `:255` 那枚 `_create_schema` 建，所以生产真正缺的是"探针失败后建表这件事再没人做"，
而日志承诺了它。⇒ 立单 **R246**：修 `_get_conn` 死码 ＋ 把那两句假话改成实话（写域 `app/common/auth.py`
＋ 新 `tests/test_r246_*`），判据里明令 R229/R230/R233 三族既有钉逐枚 `git diff --exit-code` 零放宽，
且 `_db_ready` 的 6 处读者（`:231` 那句点名 alerts / chat / catalog / profile / registry / pending_approvals）
一枚不许顺手改。

## 4. 推翻的两处派工词说法（记进纪律）

1. **"边界外裸 connect==11"是错的**，真值 14（`app/**` 侧）＋ 1（`scripts/**`）。派工词那张表漏了整棵
   `app/api/v1/`（alerts/chat/feedback 三枚）。Epicurus 顶住派工词按实测把棘轮钉成
   `{"app": 14, "scripts": 1}` 并在件首写明漏了哪一棵——这个处理是对的。同一枚探针今天第三次给出不同数：
   7（旧账）→ 12（上一班订正）→ 15（本班含边界的 app 侧文件数）。
2. **"`:371` 假注释"指错了行**：`connection.py` 里根本没有 `_db_ready`（现读 0 命中），那两处都在
   `app/common/auth.py`，真位置是 `:472` 与 `:492/:493`，另有一枚同族假话在 `:479` 的日志里。

## 5. 三处形状陷阱（下一班照抄，别重踩）

- **`**_connect_kwargs()` 会让"按关键字判断有无超时"漏判**：`auth.py:301` 没有 `connect_timeout=` 关键字，
  但超时由 `**` 展开注入。第一遍按 `kw.arg` 数出"8 枚无超时"，其中一枚就是假阳；本文件按
  显式/展开/三无 三档重列。
- **`rg` 的行数≠站点数**：`app/common/auth.py:364` 的 docstring 里写着 "``psycopg.connect``" 但不带括号，
  带括号的形状每文件恰好一处——今天对得上是运气，计数一律以 AST 调用点为准。
- **跨文件同名 helper 会造出假阳的"async 调用方"**：`_conn` 这种名字在 5 个文件里各有一枚定义。
  第一遍全仓搜调用方，把 `alerts.py` 的 4 枚 async 端点算到了另外 4 个文件头上。第二遍改成
  **只在 helper 所属文件内匹配调用方**，才是上面那张表。
- 另记：一次 `rg ... | Select-Object -First N` 提前掐断上游管道，导致同一命令块里后一条 `rg` 报了
  假的 0 命中——`scripts/audit_vector_mirror_sets.py:428` 其实存在。计数命令不要接 `-First`。