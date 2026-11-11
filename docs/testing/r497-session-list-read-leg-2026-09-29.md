# R497 · 会话列表读腿的「整表进 Python ＋ 每行一枚 COUNT」（2026-09-29）

工单：R497（R484 并树时点名要后续单治的第③件）。工作树 `be-r497`，基点 `7126614`，detached。
写域只有三枚：`app/api/v1/chat.py`、`tests/test_r497_session_list_read_leg.py`、本件。

## 1. 这一格今天长什么样（全部本回合现取）

| 门牌号 | 现读取数 | 与本派工词 |
| --- | --- | --- |
| `app/api/v1/chat.py:1005` `def _list_sessions()` | 改前发的是 `SELECT s.*, (SELECT COUNT(*) ...) as msg_count FROM sessions s ORDER BY s.updated_at DESC`，SQL 字面在 `:1018-1022` | 一致 |
| 生产调用者 | 只有 `app/api/v1/chat.py:3892` 一处（`GET /sessions`）；另有 4 枚测试件引用（`tests/test_offline_runtime_fallbacks.py:127`、`:134` 直调，`tests/test_r179_chat_denials.py:122`、`tests/test_session_route_authorization.py:28`、`tests/test_r484_...:177` 是 monkeypatch） | 一致（「全仓仅 1 处」按生产码口径成立；测试侧引用本单没动） |
| `app/storage/sessions.py:85-87` `is_owned_by()` | `record.owner_id == str(principal.user_id)`，不认角色 | 一致 |
| `app/api/v1/chat.py:728-729` | 「admin 在这条口子上不豁免」那句说明 | 一致，位置没漂 |
| `app/main.py:278-283` | 凭证在、人不在 → `_file_anonymous_denial` + 401 | 一致 |
| 台账 `owner_id` 与库列 namespace | 两者都是用户名字符串，成因是 `app/common/auth.py` 那句 SELECT 不含 `id`（R484 记为「偶然承重」，由 R495 治） | 一致 |

🔴 本回合踩过的一处自伤，如实记：我在 `_list_sessions` 的 docstring 里原写了
`sessions.user_id` 这五个字，被 `check_read_leg_uses_no_user_id_column()` 的字面扫描当成「读腿上有
读者」（count 0 → 1），足以让在册牙 `test_the_read_leg_has_no_owner_predicate_in_sql` 假红。
已改写成「库里那枚 owner 列」，现取回 0 命中。教训：**在册那把尺吃的是源码字面，注释也算**。

真库形状（`scripts/r484_session_read_leg_ledger.py` 默认模式，只读，进 pg 容器）：

```
库里 sessions: 1020 行 (唯一 id 1020)   JSON 台账: 1027 条   users: 3 枚=admin,dataowner,evalbot
  档              库里行数     台账在册     实际可见  差
  admin             336        343        336   台账独有 7 枚(库里无此行, 因此永不进出口)
  evalbot           656        656        656   无差
  无部门档          1020        -         992   成员=admin,evalbot | 上界是成员可见并集, 不是整表
孤儿逐枚: browser-e2e-mgr 9 / r8-probe-a 8 / browser-e2e-rv 6 / r8-probe-b 3 / browser-e2e-tester 2 = 28
库里有而台账无 0 枚; 库里 owner 列与台账 owner_id 不等的行 0 枚; 对账: 闭合
锚点自检: 外层 owner/部门谓词命中=无 -> 整表捞=True; 读 sessions.user_id 的代码行 0 枚
```

本回合另取的四格补充（派工词没有的，判据②要用）：`session_messages` 2120 行（其中 role='user' 1022）；
`updated_at` 并列组 **0** 组（1020 枚逐枚不同，所以改前改后的**返回序**可比且不是运气）；
库里 owner 列为 NULL 的行 **0** 枚；零枚 user 消息的会话 **0** 枚；消息侧多出的会话 id（聚合会凭空造行的那一族）**0** 枚。

7 枚幽灵绑定的逐枚 id（台账仍绑 admin、库里已无此行）：
`browser-e2e-rv-1789435802316`、`g3-check-1`、`g3-check-2`、`mu1zvcmbybsd3f`、`r8-admin-1da013`、
`r8-admin-2aad35`、`r82-admin-e0265`。

## 2. 改了什么（只此一处形状）

```sql
WITH user_turn_counts AS (
    SELECT session_id, COUNT(*) AS msg_count
    FROM session_messages
    WHERE role = 'user'
    GROUP BY session_id
)
SELECT s.*, COALESCE(m.msg_count, 0) AS msg_count
FROM sessions s
LEFT JOIN user_turn_counts m ON m.session_id = s.id
ORDER BY s.updated_at DESC
```

- 一枚 `GROUP BY` 预聚合替掉「每行一枚相关子查询」；`COALESCE` 补 0 保住零消息会话那一格；
  驱动方向仍是 `sessions`，所以聚合不会造出行（真库今天 0 枚多余 session_id，夹具里 1 枚，两侧都验过）。
- 外层**零谓词**：`FROM sessions s` 之后出现的只有 `LEFT JOIN … / ORDER BY`，
  在册尺子吃的五枚 Token（where/user_id/owner_id/department/principal）一枚都没进外层。
  聚合自己的 `WHERE role = 'user'` 落在 CTE 里，位置在 `FROM sessions` 之前——
  这与改前那句把子查询写在投影列里同一个道理：**那句 where 是数消息条数的，不是拦人的**。
- 表结构、迁移、数据、路由、台账、契约：一个字没动。`git diff --numstat` = `25 3 app/api/v1/chat.py`。

## 3. 判据② · 为什么不前推归属（本单放弃前推的理由，逐枚写清）

派工词给的分支是「先证 SQL 侧与台账侧逐枚等值，证不动就不许前推」。现取结论：

- **今天等值成立，但只成立于数据态**：`库里 owner 与台账 owner_id 不等的行 = 0 枚`、
  `库行未在册 = 0 枚`、台账 1027 条全 active。两侧对每一枚库行作答一致，这是实测，不是推断。
- **结构上无从可证**：`sessions.id` 与台账之间没有 FK、没有约束、`SessionRegistry` 只有
  `bind/get_active/is_owned_by` 三枚口（没有解绑口），删会话只删库行；owner namespace 还是
  「偶然承重」（谁给 `get_user()` 补 `id`，台账侧当场零命中，而 SQL 侧仍按用户名拦——两侧立刻分叉）。
  幽灵绑定 7 枚与孤儿 28 枚就是这两本账会各自漂移的现成证据。
- 因此任何前推都只有两种收场：把「台账说这人所有」的行**吃掉**（收缩，例：owner 列为 NULL 的行被
  `IS NOT NULL` 筛掉——真库今天 0 枚，但列定义 nullable，`ALTER TABLE … ADD COLUMN` 未回填即出现），
  或者与台账**分叉**（库里说 A 所有、台账说 B 所有）。两者都改「谁能看见哪些会话」。
- 还有一格硬约束：在册静态牙 `test_the_read_leg_has_no_owner_predicate_in_sql` 判定的是「`FROM sessions`
  之后出现归属 Token」与「全仓有人读那一列」，判据④要它逐字节不动且照绿 ⇒ 派工词说的「可证保守的预筛」
  今天**没有合规落点**（一枚 WHERE 都过不去那枚牙）。所以本单只保留「零前推 ＋ 台账照旧逐枚终审」。
- 牙在这一格是双向的：`_check_the_whole_table_still_travels`（整表照旧交给终审）与
  `_check_ledger_asks_once_per_row`（台账被问的枚数 == 库行数）合起来钉住「SQL 没替台账作答」；
  刀二实测红了这 4 枚（见 §6）。

## 4. 判据① · 真库侧对账原文（只读，进 pg 容器；宿主 5432 那台野 PG 没碰）

改前那句由 `git show 7126614:app/api/v1/chat.py` 现取（sha256/16 = `5552c25124950455`），
改后那句取自盘上源码（sha256/16 = `0f2c54b9500969b7`），两句各发一趟
`docker exec enterprise-brain-postgres-1 psql -U enterprise_brain -d enterprise_brain -At -v ON_ERROR_STOP=1
-c "SET default_transaction_read_only = on" -c "<SELECT>"`，出口成员按台账逐枚算：

```
rows old=1020 new=1020
returned_order_identical: True
set_diff id old-new: [] new-old: []
msg_count_mismatch_count: 0 {}
msg_count_total_old: 1022 new: 1022
user_id_col_mismatch_count: 0
ledger_total=1027 users=['admin', 'dataowner', 'evalbot']
PRINCIPAL admin      old=336 new=336 ledger_rows=343 db_rows=336 computed_visible=336 差集=[]/[]
PRINCIPAL evalbot    old=656 new=656 ledger_rows=656 db_rows=656 computed_visible=656 差集=[]/[]
PRINCIPAL dataowner  old=0   new=0   ledger_rows=0   db_rows=0   computed_visible=0   差集=[]/[]
   member_ids_equal_vs_ledger_ruler: True（三档逐枚，与 R484 那把尺 ledger_view 同口径）
ORPHAN browser-e2e-mgr      old=9 new=9 差集=[]
ORPHAN r8-probe-a           old=8 new=8 差集=[]
ORPHAN browser-e2e-rv       old=6 new=6 差集=[]
ORPHAN r8-probe-b           old=3 new=3 差集=[]
ORPHAN browser-e2e-tester   old=2 new=2 差集=[]
ghost_bindings(ledger_only)=7  ghost_leak_old=0 ghost_leak_new=0
orphans_db_rows=28 orphan_seen_by_any=0
reconcile_fails: []
```

三档 = `admin` / `evalbot` / 无部门那一档 `dataowner`（`users` 里在册的第三枚，staff/财务部，
台账零绑定 ⇒ 两趟都是空列表，且都是 200，不是降级）。28 枚孤儿逐名点齐、7 枚幽灵绑定逐名列出，
差集一律为空。`dataowner` 出口为 0 是台账里就没有绑在它名下的行，与会话读腿无关。

## 5. 判据② · 代价实测（`EXPLAIN (ANALYZE, BUFFERS)`，只读，各跑三趟）

| 读数 | 改前（每行一枚 COUNT） | 改后（一枚聚合） |
| --- | --- | --- |
| 顶层 Sort | rows=1020 loops=1 | rows=1020 loops=1 |
| Seq Scan on sessions | rows=1020 loops=1，buffers 3315（含子计划） | rows=1020 loops=1，buffers 24 |
| 每行求值那一格 | `SubPlan 1 → Aggregate rows=1 **loops=1020**`，buffers 3291；`Bitmap Heap Scan rows=1 loops=1020`（Rows Removed by Filter: 1，Heap Blocks exact=1251） | `HashAggregate rows=1020 **loops=1**`；`Seq Scan on session_messages rows=1022 loops=1`（Rows Removed by Filter: 1098），buffers 169 |
| 顶层 Buffers | **shared hit=3318** | **shared hit=196** |
| Execution Time | 6.363 / 5.871 / 5.684 ms | 3.323 / 3.699 / 3.789 ms |

- 实测差：buffers 3318 → 196（少 3122，约 16.9 倍）；行内循环 loops 1020 → 1；墙钟 ≈6 ms → ≈3.5 ms（省 2 ms 上下，约四成）。
- 🔴 如实：**1020 行这一档，墙钟差就是几毫秒**，别把它报成吞吐翻倍。收益的形状比数字硬——
  每行一次的索引探测＋堆回读（3291/1020 ≈ 3.23 buffers/行）换成一次全表扫＋一趟哈希聚合。
- 它在什么量级才咬人（下面是算术外推，不是实测）：按 3.23 buffers/行，1 万枚会话 ≈ 3.3 万 buffer hit、
  10 万枚 ≈ 33 万，热缓存下大致线性抬到几十毫秒至数百毫秒；真疼的是**冷缓存**——那时这些 hit 变成 read，
  N+1 会按行数放大 I/O 次数，而聚合那一侧只多扫一遍消息表。并发也按请求数放大：每一次 `GET /sessions`
  都在库里重新逐行探一遍。

## 6. 判据③ · 牙与四把刀（`tests/test_r497_session_list_read_leg.py`，17 枚，全离线）

夹具复现 R484 那四形并逐枚扩到真库的形状：**库里 34 行 / 台账 41 条 / 孤儿 28 枚 / 幽灵绑定 7 枚**，
外加本单需要的三形：owner 列为 NULL 而行由台账认给 admin、零 user 消息的会话、只有消息没有会话行的聚合造人陷阱。
出口成员（改后必须与今天一字不差，实测相等）：

```
档=admin          状态=200 出口=4 枚 ['r497-sess-admin-1','r497-sess-admin-2','r497-column-is-null','r497-no-messages']
档=evalbot        状态=200 出口=2 枚 ['r497-assistant-only','r497-column-says-admin']
档=dataowner      状态=200 出口=0 枚 []
档=r497-outsider  状态=401 出口=0 枚 []      # 查不到人即拒（app/main.py:278-283），与读腿无关
[R497 msg_count] 34 枚逐枚相等，其中报 0 的 2 枚=['r497-assistant-only','r497-no-messages']
[R497 往返] 库里 34 行发了 1 枚语句；3 行发了 1 枚语句
```

改前/改后逐枚相等（同一副夹具、同一枚真闸门，窗内跑改前原文）：

```
[R497 对账] 档=admin          改前=4 枚 改后=4 枚 差集=空 状态=200/200
[R497 对账] 档=evalbot        改前=2 枚 改后=2 枚 差集=空 状态=200/200
[R497 对账] 档=dataowner      改前=0 枚 改后=0 枚 差集=空 状态=200/200
[R497 对账] 档=r497-outsider  改前=0 枚 改后=0 枚 差集=空 状态=401/401
[R497 逐格] 34 行 × 6 格逐枚相等（含 msg_count）
```

四把刀（每把只动一处；变异只落 `tests/_temp_edit_overlay.py` 的影子根，`R466` 的 `install_mutation`
把改动的那枚顶层绑定装进活模块，出门逐枚装回；`盘上 sha256/16 = 314e441b60335ca8` 四扇窗进出一致）：

| 刀 | 红了哪几枚 | 红句原文（摘录） |
| --- | --- | --- |
| 刀一 摘台账终审只信 SQL | **2 枚**：三档出口成员逐枚相等、台账逐枚终审 | `档=admin 谓词=SQL 行交台账终审 \| 出口 4 枚 != 应有 4 枚 \| 少=['r497-column-says-admin'] 多=['r497-column-is-null']`；`库里 34 枚，台账被问 0 枚=[]` |
| 刀二 `WHERE s.user_id IS NOT NULL` 宽筛 | **4 枚**：语句里零归属谓词、整表照旧交给终审、三档出口成员逐枚相等、台账逐枚终审 | `谓词=FROM sessions 之后不许出现归属 Token \| 命中=['where', 'user_id'] \| 外层=from sessions s left join … where s.user_id is not null order by …`；`读腿交回 33 枚，库里 34 枚`；`档=admin … 出口 3 枚 != 应有 4 枚 … 多=['r497-column-is-null']`；`库里 34 枚，台账被问 33 枚 … 没被问=['r497-column-is-null']` |
| 刀三 聚合改回每行 COUNT | **2 枚**（且只有这两枚）：投影零子查询（N+1）、单枚聚合＋一趟往返 | `谓词=最外层投影列不许按行求值 \| 投影里出现 1 枚 SELECT … \| 投影=s.*, (SELECT COUNT(*) FROM session_messages WHERE session_id = s.id AND role = 'user') as msg_count`；`COUNT( 命中 1 枚、GROUP BY 命中 0 枚（要求各 1）` |
| 刀四 LEFT 退化成 JOIN（本单自加） | **4 枚**：整表照旧交给终审、三档出口成员逐枚相等、台账逐枚终审、零消息会话仍在册 | `读腿交回 32 枚，库里 34 枚`；`零消息会话 r497-no-messages 掉出了出口` |

- 判据③要的「同总数、不同成员」：夹具里 admin 两枚世界都是 4 枚，成员差两枚——
  `test_counter_evidence_a_totals_only_ruler_lets_the_membership_swap_pass` 让逐枚相等的尺当场红并点名
  `['r497-column-is-null']` / `['r497-column-says-admin']`；刀一就是把它变成活代码的那一把。
- 判据③要的「前推放宽即红」：刀二那 4 枚。
- 刀三「只红 N+1 两枚、语义一枚不红」正是等价性的反向证明：形状确实变了，可见集合没变。
- 每把刀出门都复跑那 8 枚尺（`出窗复跑 8 枚钉全绿`），并核对 `info["restored"] is True` 与盘上 sha 不变。

## 7. fail-closed：没有多开一张 200 + `[]` 的脸

- 表不在（生产）：`_require_sessions_read_schema` 先开口 ⇒ 聚合连一次都没发
  （`probes == ["sessions", "session_messages"] * 2`，两趟读各自过闸；`FROM sessions` 那句 0 命中）；
  具名错 `ChatSchemaNotMigratedError`、出口 503 `storage_unavailable`——改前窗同一张脸。
- 表在、语句自己跑挂：`psycopg.errors.UndefinedTable` 照旧往外抛，路由不接（本单没加 `except`），
  既没被洗成 503，也没有 `200 + []`；改前窗同一张脸。
- 错误码口径沿用仓库既有字典（`storage_unavailable` / `authentication_required` / `resource_not_found` /
  `permission_denied`），本单一个新码都没造。
- 🔴 一格如实报边界：**台账 JSON 不可读时今天仍是 `200 + []`**（`SessionRegistry._load` 吞 OSError）。
  那是 R484 挖出、R495 正在治的形状，`app/storage/sessions.py` 是别人家的在途件，本单没碰、
  也没在会话读腿上新增第二条吞路。

## 8. 判据④–⑥ · 在册钉、合跑、硬不变量

判据④（`tests/test_r484_session_read_leg_owner_filter.py`，19 枚）：

```
HEAD blob len 38071 sha256/16 C38EB56D0BADDB9A     <-- 与本单给的数一字不差
disk    len 38778 sha256/16 CC47117555C052F1
blob==disk bytes: False
blob->CRLF == disk: True / disk->LF == blob: True
git status --porcelain -- <该件>: ''   /  git diff HEAD --name-only -- <该件>: ''
```

🔴 对派工词的一处纠正：本仓 `core.autocrlf=true`，任何一枚在册 `.py` 的 **HEAD blob 都不可能等于磁盘字节**
（blob 是 LF、checkout 是 CRLF，这件差 707 枚 CR）。所以「逐字节不动」的合规对账是本单交回的三件一体：
blob sha == `C38EB56D0BADDB9A` ＋ blob→CRLF == 磁盘字节 ＋ `git status`/`git diff HEAD` 对该内容零命中。
（同源无效对照 `git show HEAD:p` vs `git show :p` 本单没交。）
所有在册钉一枚没改宽：`git diff HEAD --name-only` 全仓只有 `app/api/v1/chat.py` 一处。

判据⑤（五枚件合跑，`-o addopts= -p no:cacheprovider`，解释器=主树、cwd=本树）：

```
tests/test_r497_session_list_read_leg.py            17
tests/test_r484_session_read_leg_owner_filter.py    19
tests/test_session_ownership_guards.py               7
tests/test_session_route_authorization.py            2
tests/test_r295_history_scope_readback.py           19
=> 64 passed / 0 failed（17.04 s）；单独复跑 R497 件 17 passed（14.65 s）
```

判据⑥：`rg -c classification_blocked app/` → **0 命中**（rc=1）；`git diff --name-only` → 仅
`app/api/v1/chat.py`；未跟踪新增仅 `tests/test_r497_session_list_read_leg.py` + 本件；
本单 diff 与新牙件里 `chroma` 零命中、没新增 import、没新增向量库依赖或写点（生产向量库＝PGVector，
Chroma 只作为退役中的遗留件出现在既有导入里，本单一个字没动）。

## 9. 没做到的

- 没跑全量门 `scripts/run_gate.py`（同机多枚 Agent，令禁）。
- 归属/预筛一格按 §3 放弃前推，只交付「一枚聚合 ＋ 零前推 ＋ 台账逐枚终审」。
- 没打真出口（`--live` 走 HTTP，属禁项），真库侧只交只读 SQL ＋ 只读台账文件读数。
- 契约由总控代搬：`docs/api/contract-v1.md` 本单一个字没碰，全文附在下面。
- 1020 行上的墙钟收益实测只有约 2 ms（§5 如实格），没有把它写成吞吐结论。

## 10. 待搬进契约的段落全文（`GET /api/v1/sessions` 读腿形状，R497）

```markdown
### R497 · `GET /api/v1/sessions` 的读腿换成一枚聚合，归属一个字没前推（2026-09-29）

这一格改的只有「会话列表那一趟读数怎么算」，没有改「谁能看见哪些会话」。

| 项 | 今天（R497 之后） |
| --- | --- |
| 归属判定 | 仍是 `app/storage/sessions.py::SessionRegistry.is_owned_by`：台账 `owner_id` 与 `str(principal.user_id)` 逐枚相等，**不认角色、admin 不豁免**。库里那枚 owner 列在读腿上仍然一根手指都没碰过。 |
| SQL 侧谓词 | 外层 `FROM sessions s` 之后仍然零归属谓词（`where` / `user_id` / `owner_id` / `department` / `principal` 五枚 Token 命中数 = 0）。整表照旧进 Python，再逐枚交台账终审：台账被问的枚数 == 读腿交回的行数。 |
| msg_count | 由「每行一枚相关子查询」换成**一枚** `GROUP BY session_id` 预聚合 + `LEFT JOIN` + `COALESCE(..., 0)`。语义不变：只数 `role = 'user'` 的消息，零枚的行报 0，且该行仍然在册（`LEFT JOIN` 不许退化成 `JOIN`）。 |
| 往返次数 | 一趟。`session_messages` 按会话逐枚探测 1020 次换成全表扫一遍 + 一趟哈希聚合；`EXPLAIN (ANALYZE, BUFFERS)` 顶层 buffers 3318 → 196，子计划 loops 1020 → 1，Execution Time ≈6 ms → ≈3.5 ms。 |
| 响应体 | 一字未变：`{"sessions": [{"id","user_id","title","created_at","updated_at","msg_count"}]}`，仍按 `updated_at DESC`；字段一个不多、一个不少，`user_id` 那格照旧回库里存的那一列（可能是 `null`），归属判定不看它。 |
| 拒答的脸 | 生产缺 `sessions` / `session_messages` 任一枚 → 仍是具名错 `ChatSchemaNotMigratedError` + **503 `storage_unavailable`**，且聚合一枚都不发；语句自己跑挂（含 `UndefinedTable`）→ 错误照旧抛出，**不洗成 503，绝不回 200 + `[]`**。凭证在而查不到人 → 401 `authentication_required`（`app/main.py` 那层）。 |
| 不许前推 | 任何把归属写进 SQL 的筛子（含 `IS NOT NULL` 这类「保守预筛」）都会改变可见集合：台账 1027 条 vs 库里 1020 行（7 枚幽灵绑定）、28 枚孤儿行、owner 列 nullable、两侧之间无 FK 无解绑口、owner namespace 偶然承重（R484 在册记录、R495 在治）。等值今天成立只是数据态，不可证，因此不合规。 |
| 台账不可读那一格 | 今天仍是 200 + `[]`（`SessionRegistry._load` 吞 OSError）。这一格归 R495，本单没碰 `app/storage/sessions.py`，也没在会话读腿上新增第二条吞路。 |

凭据：`tests/test_r497_session_list_read_leg.py`（17 枚，含「同总数、不同成员必须红」与四把反证刀）、
`docs/testing/r497-session-list-read-leg-2026-09-29.md`（真库侧三档 ＋ 28 枚孤儿 ＋ 7 枚幽灵绑定的逐枚差集为空）、
在册钉 `tests/test_r484_session_read_leg_owner_filter.py` 19 枚逐字节不动且照绿。
```