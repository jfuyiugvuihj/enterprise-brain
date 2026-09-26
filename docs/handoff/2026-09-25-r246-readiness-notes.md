# R246 — 就绪承诺与代码同形（改话不改骨）

- 单号 R246 ／ 执行层签名 **Boole** ／ 工作树 `C:\Users\fengx\PycharmProjects\be-r246`（detached，基点 `2ab23697789c2a5c4b1307aed30fc787fa876ae2`）
- 写域三枚：`app/common/auth.py`（改，+19/−20，668 行 → 667 行）、`tests/test_r246_honest_readiness_claims.py`（新建 398 行）、本文件（新建）。此外一枚字节未动。
- 一句话：`_get_conn()` 里那段"首次连接时建表"恒不可达，本单删掉它，并把为它背书的一句注释与一条运维可见的 WARNING 改成实话。**没有新增任何自愈通路。**

## 1 三行证明链复核（与总控现读一致，行号取基点 `2ab2369`）

| 位置 | 原文 | 复核 |
| --- | --- | --- |
| `app/common/auth.py:164` | `return psycopg is None or not _db_ready` | 一致；本行未被本单改动，改后仍是 `:164` |
| `app/common/auth.py:487` | `if _using_memory_store(): return _FakeConn()`（`:486` 是 `global _db_ready`） | 一致，且无条件排在函数第一句 |
| `app/common/auth.py:490` | `if not _db_ready:` → `:492 _create_schema(conn)` / `:493 _db_ready = True` | 一致，**恒不可达** |

论证（为什么运行期从来走不到那一支，也就是"删掉 = 零行为变化"的凭据）：

1. 要执行 `:490`，必须先不返回 `:487` 的 `_FakeConn()` ⇒ 那一刻 `_using_memory_store()` 判假。
2. `:164` 是 `psycopg is None or not _db_ready`，判假 ⇒ `psycopg is not None` **且** `_db_ready` 为真。
3. 于是 `:490` 的 `not _db_ready` 恒假 ⇒ `:492`、`:493` 两枚语句没有任何输入能走到。中间没有 `try/finally`、没有异常通路、没有别的赋值可以插队：`:489` 只是 `conn = _connect_for_request("user store access")`，`_connect_for_request` 只建连、从不碰这枚旗。
4. 那行 `global _db_ready` 只为 `:493` 那一句赋值服务，随之一起删；删后 `_get_conn` 只读不写，不需要 `global`。
5. 改后 AST 实测：`auth.py` 里 `_db_ready` 的写点 4 枚 — `:235`（`global`，属 `_retry_readiness_probe`）、`:267`（置真，同一函数）、`:467`（初值 False）、`:477`（置真，import 期探针）。**运行期唯一置真点仍是 R230 的 `:267`**，本单一枚没加。

`_create_schema` 本体（def 在 `:410`）留在原地未动：建表与播种都靠它，`tests/test_bootstrap_admin.py` 十处以上直接调用它。

## 2 改动清单（auth.py 五处，前两处是判据本体）

1. `:485-496` → `:489-495`：删死码（12 行 → 7 行，含 `global _db_ready`），函数体只剩「先挡内存支，再连一枚」两枚语句；随附 3 行注释写明"请求路径不建表"的口径来源（生产建表归 `migrations/0003`）。
2. `:479` → `:479-483`：那条 WARNING 换成实话。**级别仍是 `logger.warning`，消息末尾仍插 `{exc}`**，没有降级成 info 把问题藏起来。
3. `:472`：注释「真正的补救在请求路径上（`_get_conn` 会重建表）」换成「请求路径不补救（`_get_conn()` 不建表）：生产建表归 migrations/0003、探针只校验 + 播种，红过之后生产侧由 R230 重探再校验，非生产侧不自愈，直到进程重启」。刻意保持**单行替换**，让 `:474`（`_c = _raw_conn()`）不漂移——`tests/test_r238_connect_boundary_policy.py:16` 的散文引的就是这枚行号。
4. `:197-202`（`_retry_readiness_probe` docstring）：删除使原句「`_db_ready` 全仓只有两处置真——import 期探针与 `_get_conn()`」变成新的假话，故一并收成「修前形状」并注明 R246 已删。6 行 → 6 行，保住 `:301` / `:364` 两枚被 `tests/test_r238_bare_connect_ratchet.py:851-852（行号 09-26 现取；R261 起该件改身份记账，这两枚"散文不算站点/真调用要算"的断言原样保留）` 断言的锚点。
5. `:231-233`：读者读数收窄口径（见 §4）。3 行 → 3 行。

## 3 可达性钉与反证钉（新测试件）

`tests/test_r246_honest_readiness_claims.py`（16 枚，全绿）只读源码、不 `import app.common.auth`——那枚模块 import 期就向 `DATABASE_URL` 发真握手，本单判的四件事全在 AST 上判得完，一次运行都不必发起。

- `test_get_conn_body_has_no_db_ready_write`：`_get_conn` 体内不存在 `_db_ready` 的任何**写**形态（赋值 / 注解赋值 / 增量赋值 / 海象 / `global`），并且不存在 `_create_schema` 调用（钉住"不许把建表挪回请求路径"）。
- `test_counter_evidence_dead_block_reinserted_gets_reported`：把基点那 12 行原文逐字塞回一份 `tmp_path` 副本（判器实测报出 `[(490, 'global'), (497, 'assign')]` + 那枚 DDL 调用），副本落在工作树之外，收尾用 sha256 复核 `auth.py` 与开头一致。另有 6 种写形态的参数化反证与一枚"只读不写不许误报"的噪音门禁。
- `test_the_selection_counts_the_r229_nail_pins_still_hold` / `test_get_conn_still_shields_the_memory_branch_first` / `test_the_dead_branch_would_have_been_a_seventh_reader_line`：正面复算禁改钉各判的那件事，见 §5。

## 4 `:231` 那句"另有 6 处读者"——判**真**，但原句没写口径

AST 现数（范围 `app` + `deploy` + `scripts` 全量 `.py`，`tests/**` 不计；`scripts` / `deploy` 实测 0 枚）：

| # | 读者 | 读点 |
| --- | --- | --- |
| 1 | `app/api/v1/alerts.py:50` | `getattr(auth_module, "_db_ready", False)` |
| 2 | `app/api/v1/chat.py:858` | 同上 |
| 3 | `app/documents/catalog.py:324` | 同上 |
| 4 | `app/memory/profile.py:41` | 同上 |
| 5 | `app/semantics/registry.py:503` | 同上 |
| 6 | `app/storage/pending_approvals.py:99` | 同上 |

本文件之外 **6 处、六枚模块各一枚，名单逐字对得上 ⇒ 数目与名单都是真话**。但"另有"没交代口径：`auth.py` 自己另有 3 枚读者（`:164` `_using_memory_store` / `:169` `user_storage_state` / `:237` `_retry_readiness_probe`；基点是 4 枚，第 4 枚就是被删的 `:490`），全仓运行时读者此刻 9 枚。故 `:231` 收窄为「**本文件之外**另有 6 处读者，各一枚（…）」，并加钉 `test_the_six_reader_claim_matches_ast`：数目、名单、"各一枚"三件一起与 AST 现算对齐，将来多一枚读者而注释没改就判红。差值登记：本单**没有**发现数目或名单对不上，改动只是补口径。

## 5 禁改清单的正面凭据（不是"它们全绿"）

| 禁改钉 | 它判的那件事 | 本单的正面论证 |
| --- | --- | --- |
| `tests/test_r229_connect_retry.py:155` | `_raw_conn` 调用点 2 枚、`_get_conn` 调用点 7 枚 | 新钉独立复算同一段 AST：改后仍是 (2, 7)。本单唯一改动的计数是 `_create_schema` 调用点 3 → 2（死掉那一枚），def 仍在 `:410` |
| `tests/test_r229_connect_retry.py:292` | 未就绪时 `_get_conn()` 返回 `_FakeConn` | 新钉 AST 半边：`_get_conn` 体恰为 `[If, Return]`，`If.test` 仍是 `_using_memory_store()`、`If.body` 仍只有一句 `return _FakeConn()`，`orelse` 为空；尾部 `return _connect_for_request("user store access")` 的 operation 标签逐字未变 |
| `tests/test_r230_db_ready_selfheal.py`（含 `:522`） | `_get_conn` 修前修后都翻不了这枚旗 | 修前靠"恒不可达"翻不了，修后靠"体内零写点"翻不了——同一条断言的两半都成立；该钉的运行时读数（`_FakeConn` + `_db_ready is False`）未受影响 |
| `tests/test_r233_sso_first_login.py` / `tests/test_r233_undefined_root_names.py` | 对 `auth.py` 源码做 AST/文本判定（secrets、hashpw 形状、未绑定根名字） | 本单只动 `:197-202`/`:231-233`/`:472`/`:479`/`:485-496` 五段，且 `:301`、`:364`、`:474` 三枚行号锚点实测未漂移（`:410` def 未漂移）；未新增任何未绑定名字 |

`git diff --exit-code` 对这四枚文件：无输出，`exit=0`（原文见 §6）。

## 6 实测读数

- 解释器 `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`；`DATABASE_URL` 在每条命令前显式钉 `postgresql://x@127.0.0.1:1?connect_timeout=1`；未跑 `scripts/run_gate.py`、未加 `-n`、未起容器、未打模型、未连真库。
- `pytest tests/test_r246_honest_readiness_claims.py -q -p no:cacheprovider` → `16 passed in 2.59s`
- 交回格式那一条六件合跑 → `107 passed in 39.23s`
- 邻族旁证（`test_auth` / `test_auth_database` / `test_deployment_guards` / `test_r229_auth_semantics` / `test_phase2_rbac` / `test_r98_checkpointer_backend` / `test_dashboard_summary` / `test_r238_bare_connect_ratchet` / `test_r238_connect_boundary_policy`）→ `132 passed, 61 warnings in 33.66s`
- `git status --porcelain=v1` → ` M app/common/auth.py`、`?? tests/test_r246_honest_readiness_claims.py`、`?? docs/handoff/2026-09-25-r246-readiness-notes.md`
- 未 commit、未 add、未 push；`chroma_db/`、`.gitignore`、`frontend/**`、`app/rag/**`、`app/db/**`、契约与计划书、评测集、`scripts/**` 一律未动。

## 7 客户可见症状（总控第 5 问）

场景：客户装完、`docker compose up`，PG 容器比后端晚起几秒。

**日志会说什么。** 改前那一条是运维可见的假话：`[Auth] Postgres 不可用，将在首次连接时建表: <异常>`（WARNING）。运维据此等一次"首次连接时建表"，而 §1 已证它永远不会发生。改后同一条写成：`[Auth] Postgres 探针失败：本进程改用进程内内存表管理员，请求路径不建表也不自愈；生产侧由 `_retry_readiness_probe()`（R230）重探再校验后恢复（建表归 migrations/0003），非生产侧要到进程重启才恢复: <异常>`，级别与异常照旧。

**然后实际会发生什么。** 分两种形态，二者行为本单一枚未改：

- 生产（`APP_ENV` ∈ `_PRODUCTION_ENVIRONMENTS`）：探针失败后 `_load_memory_admin()` 只把凭据读进进程，鉴权一律被 `_memory_store_denied` 挡住——每发登录落一条 ERROR `production user store is not durable; refused …（set DATABASE_URL and run migrations）`，用户看到 401，**内存表绝不是一条放行的路**。PG 起来之后不必重启：下一发撞上探测窗口的登录触发 R230 重探（两次探测至少隔 `_READY_PROBE_INTERVAL_SECONDS = 15.0`，`auth.py:52`），翻真后打 INFO `R230 生产用户库在启动探针失败后重新可用，鉴权不再需要重启进程`。真实症状 = **PG 可达之后最长约 15 s 的登录 401，自愈**。若 `users` 表压根不存在，生产分支不建表而是直接 raise `users table is required in production; run migrations first`（`auth.py:414`）——建表从来轮不到运行时，它是 `migrations/0003_legacy_runtime_tables.sql:5` 的活。
- 非生产（本机 dev / 测试台，`APP_ENV=development`）：**没有任何自愈通路**。`_db_ready` 在 import 期为假就锁到进程重启；这期间鉴权走进程内内存表管理员，§4 那六处读者读到假 ⇒ 各自退回内存支或拒用持久支。真实症状是"登得上，但用户 / 会话 / 审批 / 目录读的不是库里那一份"，`user_storage_state()` 报 `storage_mode=memory, durable=false`。

**运维该怎么办。** 看到新那条 WARNING：先核 PG 可达性、再核 `migrations/0003` 跑过没有（生产缺表就是 raise，不会自愈）。生产等 ≤15 s 重试登录即可，不必重启；非生产重启后端进程是唯一复位手段。两种形态都不要期待后端会在请求路径上替你把表建出来——这句正是本单删掉的那两行假话。

## 8 遗留（本单明令不做，登记备查）

- 非生产侧仍不自愈：`_db_ready` 一旦 import 期为假就锁到重启。补它 = 发明新自愈路径，需要单独开单 + 真机验收。
- 请求路径仍不建表：把 DDL 挪到请求路径是产品行为变更，本单只做减法。
- `tests/test_r230_db_ready_selfheal.py:4` 那句「只有两处置真——import 期探针（`:376`）与 `_get_conn()`（`:392`）」与 `:523` 的"修前事实"是修前快照，行号在基点上就已过期；该族属禁改清单，本单不碰，交由总控决定是否另开一单改成"修前"口径。
- `docs/handoff/2026-09-15-backend-followup-requests.md:3139` 预告的"R240 候选"含本单这两件事（`_get_conn` 死码 + 假注释），已在此收；计划书按禁改清单未动。
