# R495 · 「会话归属今天恰好成立」搬到纸面上：一处显式真源＋可失败的牙（2026-09-29）

- 单号 **R495** ｜ 执行体 `Fermat` ｜ 工作树 `be-r495` ｜ 基点 `438d67d`（detached，HEAD 未动，零 commit／零 push／零建分支）
- 一句话：会话台账按哪套键认人，今天**仍然**是用户名，但它不再是「那句 SELECT 恰好少一列」的副产品——它是一枚声明（`SESSION_OWNER_NAMESPACE`）、只剩一处算式（`session_owner_key()`）、被两枚常驻钉拿真源对账，命名空间一旦被换掉写腿当场抛。
- 写域：`app/common/auth.py`、`app/storage/sessions.py`、`tests/test_r495_*`（两枚新件）、本文。`app/api/v1/chat.py`／`app/api/v1/auth.py`／`frontend/**`／`docs/api/contract-v1.md`／`tests/test_r484_*`／`tests/test_r453_*`／`pyproject.toml`／`scripts/run_gate.py` 逐字节未动（§四格⑤给凭据）。
- 全程离线：`tests/conftest.py` 把 `DATABASE_URL` 钉在保留端口 `127.0.0.1:1`，一发模型都不打、一个端口都不开、一行生产库都不写、容器一个没动；R56 闸门读数 `blocked connect attempts to host model port: 0`。

## 一、现读核对（派工词给的门牌号逐条对实物，本树 09-29 现取）

| 派工词说 | 现读 | 判定 |
| --- | --- | --- |
| `app/common/auth.py` 取用户那句 SELECT 今天约 `:636-647`，只回 `username, role, department` | `get_user` 占 `:636-647`，SELECT 字面在 `:644` | 对得上 |
| `app/storage/sessions.py:85-87` 的归属判定是 `record.owner_id == str(principal.user_id)` | `is_owned_by` 在 `:85-87`，判定式在 `:87` | 对得上 |
| `app/api/v1/chat.py` 里「admin 不豁免」约 `:728-729` | 就在 `:728-729`，且它自己指着 `app/storage/sessions.py:85` | 对得上 |
| 「不含 `id`」这句 SQL 的偶然形状是整条会话归属今天成立的唯一理由 | 🔴 不完全是。真正把两列折成一列的那句在 **`app/agents/contracts.py:34`**：`user_id=str(user.get("id") or user.get("username") or "")`。SELECT 不含 `id` 只是让这枚 `or` 走到第二支 | 派工词漏了翻译点 |

## 二、对派工词的两处纠正（照字面做会撞禁碰件）

1. **翻译点不在 auth，在 `app/agents/contracts.py:34`，而那枚文件不在本单写域。** 所以「principal 上显式的会话归属键」这一种形状做不了（要往 `Principal` 加属性就得动 contracts.py）；本单走派工词给的第二种形状——sessions 侧唯一的派生函数＋一枚命名空间声明。
2. **🔴 「归属键＝用户名」若照字面把读腿换成 `principal.username`，会当场改掉在册件钉死的那格判定**：`tests/test_r484_session_read_leg_owner_filter.py:406` 要求一枚 `user_id="1" / username="admin"` 的主体在按用户名写着的台账上判 `False`，原文写的正是「台账竟然认得 bigint 那套 namespace：本件记的『偶然承重』这格不成立了，结论要重写」；`tests/test_r484_*.py` 是本单禁碰件，把它的牙改红不是「强度只升」。而且不止 R484：`tests/test_session_ownership_guards.py:17`、`tests/test_r159_cross_scope_matrix.py:157`、`tests/test_r172_lane_across_hitl.py:98`、`tests/test_r295_history_scope_readback.py:104` 这些在册夹具本来就按 id 形键绑台账，读写两头同源时归属一直是对的。
   ⇒ 本单做的不是**换尺**，是**把尺的来源写成声明、只留一处算式、换命名空间当场响**。算式仍只一枚（`session_owner_key`），没有长出第二把尺。
3. 派工词把归属判定写成「`sessions.py:85-87` 一句」。现读它其实吃三处：`:68` 的重绑闸门、`:73` 的写入、`:87` 的读腿比较（改后为 `:131 / :136 / :152`）。三处今天全部收进同一枚函数，这才叫一处。

## 三、改了什么（形状，不是抄来的实现）

| 坐标（09-29 现取行号） | 它是什么 |
| --- | --- |
| `app/storage/sessions.py:30 SESSION_OWNER_NAMESPACE = "username"` | 🔴 台账命名空间的**唯一真源**：全仓只有这里把这句话写成字面（§四格②给 grep） |
| `app/storage/sessions.py:33 OWNER_NAMESPACE_FROM_USER_ID = "user_id"` | 另一套键的名字，只在证词里出现 |
| `app/storage/sessions.py:46 session_owner_key()` | 归属键的**唯一算式**：写腿与读腿都从这一处取键 |
| `app/storage/sessions.py:57 session_owner_namespace()` | 现读一枚主体的键属于哪套；只出证词，不判归属 |
| `app/storage/sessions.py:36 SessionOwnerNamespaceError(PermissionError)` | 命名空间被换掉时的错；它借既有对外码，不新造 |
| `app/storage/sessions.py:120-127`（bind 内） | 写腿 fail-loud：先出证词，漂了就拒写，台账字节一个字都不许多长出一套键 |
| `app/storage/sessions.py:152`（读腿） | `owned = record.owner_id == session_owner_key(principal)`——判归属的比较式只这一枚 |
| `app/storage/sessions.py:167-190 _owner_key_drift()` | 证词本体：principal 的键离开声明的那套命名空间，而台账上还挂着按该主体**用户名**写下的行 ⇒ 同一个人两套键 |
| `app/common/auth.py:645-646 USER_LOOKUP_COLUMNS / USER_LOOKUP_SQL` | 查人交出哪些列：从手抄字面升成声明；`:651 _project_user_row()` 让内存表与 PG 两支共用这一枚列名声明 |
| `app/common/auth.py:664-674 get_user()` | 两支都只吃声明，`str(principal.user_id)` 这类裸读在 sessions.py 归零 |

对外可见行为：**没有变化**。三档会话归属改前改后逐枚相等（§四格①），状态码、响应体字段、台账 JSON 形状（四列，无新键）一枚都没动（§四格①末枚凭据）。

## 四、判据逐条实测读数（全部本回合亲自跑；解释器＝主树 `.venv`，cwd＝本树）

**跑法**（工作树里没有 `.venv`，事故 #93 那一格照派工词办）：

    cd C:\Users\fengx\PycharmProjects\be-r495
    C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -m pytest <件> -o addopts= -p no:cacheprovider -q --tb=line

### ① 行为不变面：三档逐枚相等

夹具是**形状副本**（与 R484 同口径，成员全是 `r495-snap-*` 合成 id）：库里 1020 枚 = admin 336 + evalbot 656 + 五枚孤儿名 28（9/8/6/3/2）；台账 1027 行 = 上述 1020 + 7 枚只落在台账里的 ghost ⇒ **admin 台账 343 对库里 336**，那 7 枚永不进出口；第三档 `r495-staff-finance`（有部门、零会话）应见 0 枚。

三样读数一起对，谁单独漂了都要点名：

1. **同一份台账字节交给新旧两把尺**：`git show HEAD:app/storage/sessions.py` 现取基点那份字，用 `importlib` 单独载成一枚私有模块（`sys.modules` 先登记再执行，否则 `@dataclass` 求值注解时找不到宿主模块）⇒ 旧尺 = `record.owner_id == str(principal.user_id)`；新尺 = 今天树上的 `session_owner_key()`。1020 枚库行 × 三档，逐枚 `LEDGER.member_diff` ⇒ **成员全等**。
2. **旧尺 / 新尺 / R484 交回的那枚纯函数内核 `scripts/r484_session_read_leg_ledger.py::visible_ids`** 三方逐枚对账 ⇒ 三档全部相等（不是比总数：`member_diff` 交回 `only_in_a`／`only_in_b`）。
3. **真路由** `GET /api/v1/sessions`（`TestClient`＋真 `SessionRegistry`＋假用户表＋假库行，只换「查人」与「整表捞」两枚缝，闸门一个字不动）⇒ admin 336 枚、evalbot 656 枚、staff 0 枚，成员逐一等于上两样的读数；`orphan_rows == 28` 且 `orphan_seen_by_any_principal == 0`；`ledger_minus_db` 恰 7 枚。

再加两格把「不变」钉到字节上：旧台账文件今天原样读回 1027 枚条目且盘上字节没被读动作改动；同一枚主体改前改后各绑一枚会话，两份 JSON 换掉时间戳后**逐字节同形**，键集仍是 `{session_id, owner_id, status, created_at}`（R495 没给台账长新列——长了旧文件会被 `SessionRecord(**raw)` 拒读，那是假话式退役）。

**这条判据为什么在离线夹具上就能成立**：会话归属那一句判定今天全部住在 `app/storage/sessions.py` 里，它只吃两样东西——台账自己的字节与 principal 自己的两个字段。它不吃库、不吃模型、不吃端口，所以「改前改后逐枚相等」不需要任何在线条件就能测；把同一份字节交给新旧两把尺就是穷尽了它的输入面。反过来也说明这层承重的脆：一旦键的**来源**换了（`Principal.user_id` 翻成 bigint），夹具里看不见任何异常，只有成员清空——这正是本单要堵的形状。

### ② 显式化：唯一真源坐标＋grep

真源坐标（现取）：`app/storage/sessions.py:30`（声明）、`app/storage/sessions.py:46`（算式）、`app/storage/sessions.py:152`（读腿那一枚比较式）。

    rg -n "SESSION_OWNER_NAMESPACE = " app/     ->  app/storage/sessions.py:30        （1 处）
    rg -n "def session_owner_key" app/          ->  app/storage/sessions.py:46        （1 处）
    rg -n "str\(principal\.user_id\)" app/storage/sessions.py  ->  零命中（rc=1）
    rg -n "principal\.user_id" app/storage/sessions.py         ->  :54 一枚（算式自己）+ :7 文档
    rg -n "owner_id" app/storage/sessions.py                   ->  :75 字段声明 / :131 重绑闸门 / :136 写入 / :152 读腿 / :165 证词取键集

第二把尺的搜索面：`app/**` 里判会话归属的比较式只有 `:152`（读腿）与 `:131`（bind 重绑同一枚会话时那道旧闸门），两枚都吃 `session_owner_key()` 的返回值，没有第二处把 principal 变成键；`:165` 那枚 `_owner_keys_on_ledger()` 只把已有键收成列表给证词数数，不参与判定。**口径范围要讲清**：这条 grep 说的是**会话台账**那一本账；`app/storage/artifacts.py:544`、`app/storage/datasets.py:926`、`app/knowledge_graph/service.py:332`、`app/api/v1/chat.py:5044` 各自也在用 `str(principal.user_id)` 当自己的 owner 列——那是另外几本账，R495 的真源只管会话这一本，本单不越界替它们定命名空间。

### ③ fail-loud：刀一那一形下实测到的形状

- **红**（常驻钉，当场）：`tests/test_r495_session_owner_namespace_is_declared.py::test_the_real_user_lookup_declares_no_id_column` 与 `::test_a_principal_built_by_the_real_lookup_is_username_keyed`。第二枚不是文本比对：它拿**真** `auth.create_user()` → **真** `auth.get_user()` → `Principal.from_user()` 造主体，再走 `session_owner_namespace()`，读到 `'user_id'` 与台账声明的 `'username'` 分叉才红。
- **响**（运行期，异常名）：`app/storage/sessions.py:36 SessionOwnerNamespaceError`，实测在窗内由 `bind()` 抛出，读数 `{'namespace': 'user_id', 'raised': 'SessionOwnerNamespaceError', 'read_back': False, 'testimony': 2}`。对外它落进 `app/api/v1/chat.py` 写腿那格既有的 `except PermissionError` → **403 `permission_denied`**（`issubclass(..., PermissionError)` 被一枚常驻钉 `test_the_refusal_borrows_the_existing_outward_code` 盯着，同时钉着 `app/**` 里没出现 `detail="session_owner_namespace..."` 这类新码字面）。
- **读腿那一半**：仍是 `False`（R484:406 钉死，见 §二.2），但不许无声——同一条路径落 ERROR 证词，实测 2 行，`caplog` 之外另有 `_Recorder` 直接数 `sessions` 模块自己的 logger。证词只在「两套键同时存在」时出声：`_check_foreign_principals_learn_nothing` 那一形（别人的会话）必须一个字都不落，否则「确实没有会话」与「漂了」又会长成同一张脸。
- **不静默的另一半**：拒写之外台账字节必须恒定（`test_the_write_leg_refuses_a_swapped_owner_namespace` 里 `read_bytes() == before`），命名空间不许在同一份台账上混着长。

### ④ 三把刀

见 §五的表。

### ⑤ 强度只升：在册钉一枚没改宽，R484 逐字节不动

    sha256(tests/test_r484_session_read_leg_owner_filter.py)[:16] = cc47117555c052f1
    git rev-parse HEAD:<该件>  ==  git hash-object <该件>          == ef83d21c90…

同一式子也过了一遍其余禁碰面：`app/api/v1/chat.py` `a5d8cd84e9754edf`、`app/agents/contracts.py` `bc1cb49c28238e43`、`docs/api/contract-v1.md` `c44653df89ec9067`、`pyproject.toml` `5bd226175b480755`、`scripts/run_gate.py` `28caae4758dfb281`、`tests/test_r295_history_scope_readback.py` `d13c8ae0ff6cd817`、`tests/test_session_ownership_guards.py` `ecffae32836eef70`、`tests/test_session_route_authorization.py` `2e0f3df21e5005a2`、`tests/test_r179_chat_denials.py` `9131fe9fb628f690`、`tests/test_hitl_pending.py` `41592a6a7230623a`——全部 `gitblob_same=True`。`git status --porcelain` 只报两枚 M（auth / sessions）加本单的未跟踪件。

### ⑥ 硬不变量

- `rg -c classification_blocked app/` → 零命中（rc=1）。
- `rg -in "chroma" app/common/auth.py app/storage/sessions.py` → 零命中（rc=1）：本单两枚 app 文件没引入任何 Chroma 依赖，也没新增 Chroma 写点。跑测时看到的 `PersistentClient` 计数是 conftest 的 R134 闸门把落点改道出工作树（在册既有行为），与本单无关。

### ⑦ 点名件复跑（本回合实际数字）

两枚新件自己：**21 枚全绿**（15 枚契约闸＋6 枚行为不变面）。

派工词点名的同跑组合（`-o addopts= -p no:cacheprovider`，单进程）：

| 跑什么 | 读数 |
| --- | --- |
| `tests/test_r495_*`（两枚）＋ `test_r484_session_read_leg_owner_filter.py` ＋ `test_session_ownership_guards.py` ＋ `test_session_route_authorization.py` ＋ `test_r295_history_scope_readback.py` | **68 passed / 0 failed**（25.03 s）＝ 15＋6＋19＋7＋2＋19 |
| 再加 `test_r179_chat_denials.py` ＋ `test_hitl_pending.py`（8 枚件＝§五的刀测夹具） | **129 passed / 0 failed**（27.00 s） |

R484 那 19 枚在同跑里逐枚绿；`tests/test_r484_...::test_the_owner_namespace_is_the_username_and_it_is_load_bearing` 也绿——它记的「偶然承重」这格今天仍在（它测的是算式吃什么，本单没换），但它已经不是**唯一**的理由：那句话另有声明、另有对账、另有牙。

## 五、三把反证刀（整轮复跑；每把只动一处，出门逐字节还原）

刀身一律放在 `tests/`：走 R253 影子根（`tests/_temp_edit_overlay.py`），变异只落 `%TEMP%` 副本，被跟踪文件全程只读，出门核对 `restored=True / shadow_clean=True`。跑法：

    $env:R495_KNIFE = "one"    # 或 "two" / "three"
    python -m pytest <§四格⑦那 8 枚件> -p tests.test_r495_session_owner_namespace_is_declared -o addopts= -p no:cacheprovider -q --tb=no

（没设环境变量时那两枚 pytest 钩子一声不响；设了之后本件自己那三枚 `test_counter_evidence_*` 会 skip，因为同一枚文件上影子窗不许嵌套——三枚反证在常驻态另有跑法，见下表末列。）

| 刀 | 只动的那一处 | 红几枚 | 红的是哪几枚 |
| --- | --- | --- | --- |
| 刀一 | `app/common/auth.py:645` 列名声明补 `"id"`（⇒ SQL 与两支投影一起翻） | **2 枚红**／124 passed／3 skipped | `test_r495_..._is_declared.py::test_the_real_user_lookup_declares_no_id_column`、`::test_a_principal_built_by_the_real_lookup_is_username_keyed`。运行期同时**响**：窗内探针 `raised='SessionOwnerNamespaceError'`、`read_back=False`、`testimony=2`，台账字节恒定 |
| 刀二 | `app/storage/sessions.py:152` 的 `owned = record.owner_id == session_owner_key(principal)` 改成 `owned = True` | **31 枚红**／95 passed／3 skipped | 本单 7 枚（A 3＋B 4）；R484 11 枚（`test_the_ledger_not_the_column_…`／三形四列 3 枚／`test_ledger_only_bindings_never_inflate_the_exit`／孤儿 2 枚／`test_the_owner_namespace_…load_bearing`／`test_the_department_ruler_…`／`test_kernel_and_endpoint_agree_…`／`test_today_reported_shape_replays_…`）；`test_session_ownership_guards.py` 2 枚（外来会话那两枚）；`test_session_route_authorization.py` 2 枚；`test_r295_history_scope_readback.py` 1 枚；`test_r179_chat_denials.py` 8 枚（404 那族 2 枚＋owner 端到端 1 枚＋五扇门 3 枚＋留账通路 1 枚＋…） |
| 刀三 | `app/storage/sessions.py` 整片退回 `git show HEAD:` 那份字（显式真源与证词全摘掉，回到「靠 SELECT 形状」） | **5 枚红**／121 passed／3 skipped | 全在本单 A 件：`test_the_owner_namespace_is_declared_in_exactly_one_place`、`test_the_owner_key_formula_is_the_only_one_in_the_repository`、`test_the_granting_comparison_is_one_read_leg_and_one_rebind_gate`、`test_the_write_leg_refuses_a_swapped_owner_namespace`、`test_the_read_leg_stays_a_denial_and_leaves_a_testimony` |

刀三的读法要说白：**行为一格没红**（129 枚里的 121 枚照绿，R484／R179／R295／guards／route_auth 全照绿）——这正是病根本来的样子：显式化被摘掉之后生产行为不变，没人能从出口看出什么坏了。R495 的价值就是把这格从「看不见的承重」变成「五枚点名红的钉」。刀三里本单另加两枚反向约束当钉：`真源SELECT对账` 那一格**必须**绿（刀三只动 sessions.py，牵连它就是刀身越界），`外来主体学不到东西` **必须**绿（摘掉显式化不该顺手把闸门改松）。

三把刀在常驻态各自还有一枚 `test_counter_evidence_*`，它们不开环境变量、直接在件内开窗跑同一套判据集合，**该红的没红就当场 `pytest.fail`**；件内实测读数（`-s` 现取）：刀一 2 红＋探针那四格、刀二 3 红、刀三 5 红。

**附注（在册顺序依赖，与本单无关，本单不修）**：`tests/test_r397_read_legs_refuse_a_missing_table.py` 先跑会让 `tests/test_r179_chat_denials.py::test_the_ownership_predicate_stays_the_single_source_of_truth` 红（`assert [] == ['r179-session-mine']`——谓词桩没被调用）。不含本单任何文件的三枚组合 `test_hitl_pending.py + test_r397_... + test_r179_...` 实测同样红（1 failed / 91 passed），所以这不是 R495 带的；本单的 129 枚夹具因此不含 `test_r397_...`。这一格与 R496 给的那枚「禁域自护钉把别人家的在册件当自己的越界判据」是同一族结构缺陷，建议并案。

## 六、numstat

| 件 | 增／删 | 字节 |
| --- | --- | --- |
| `app/common/auth.py` | +31 / −4 | 已跟踪，逐字节见 git |
| `app/storage/sessions.py` | +113 / −5 | 已跟踪，逐字节见 git |
| `tests/test_r495_session_owner_namespace_is_declared.py` | 未跟踪，新钉 15 枚 | 33,977 字节／733 行 |
| `tests/test_r495_owner_filter_is_unchanged_before_after.py` | 未跟踪，新钉 6 枚 | 18,032 字节／350 行 |
| `docs/testing/r495-session-namespace-2026-09-29.md` | 未跟踪，本文 | 28,289 字节／186 行 |

未跟踪三枚共 80,298 字节；`git status --porcelain` 到交回为止只有这两枚 `M`（auth / sessions）加这三枚 `??`，禁碰面一枚都没进改动集。

## 七、本节没做的事（不许读成已收）

- 读腿那一半仍然交回 `False`，本单没把它改成 raise。改了就要动 `tests/test_r484_*.py` 那枚禁碰件（`:406`）。所以「绝不允许 200 + `[]`」这一格是靠**三件**堵住的：写腿当场拒、两枚常驻钉当场红、每次误判落一条 ERROR 证词。出口本身今天仍可能是 200 + `[]`——但它不再是无人看守的形状，这一格本单只做到这里，没做到的部分是「出口自己会响」。
- 没迁台账、没加列、没写 migration、没动 `data/.session-metadata.json` 那份真字节（一个字节都没写过）。
- 没动 `app/api/v1/chat.py`：其中 `:5044` 队列归属那格吃的也是同一枚 `principal.user_id`，SELECT 补 `id` 时它同样会翻命名空间（读数落 `QUEUE_OWNER_STALE`，是失效而不是泄漏）。那一本账不在本单写域，只记不修。
- 没动 `app/agents/contracts.py:34`（翻译点本体），因为不在写域；本单只能在 sessions 侧把键的来源写成声明并对账。要真正根治「一枚字段两套身份」，得给 `Principal` 明说哪一列是身份、哪一列是标签——那是下一单的事。
- 没连库、没起服务、没打模型、没动容器、没跑全量门 `scripts/run_gate.py`（同机并跑，事故 #81）。

## 八、契约段（总控并树时逐字节搬进 `docs/api/contract-v1.md`；本席对那本契约一个字都没动）

## R495 · 会话归属键的命名空间是**声明**，不是 SELECT 恰好少一列：一处真源、一枚算式、换命名空间当场拒（`app/storage/sessions.py` ＋ `app/common/auth.py`，2026-09-29）

### 口径

私有化那台机器上，会话归属只认一把尺；而这把尺「今天等于用户名」这件事，写在一处、可 grep、可钉：

- **真源**：`app/storage/sessions.py::SESSION_OWNER_NAMESPACE = "username"`——全仓唯一一处把「JSON 台账按哪套键认人」写成字面。
- **算式**：`app/storage/sessions.py::session_owner_key(principal)`——全仓唯一一处把一枚 principal 变成台账里的 `owner_id`。写腿（`bind`，含重绑同一枚会话那道旧闸门）与读腿（`is_owned_by`）都只从这一处取键：命名空间要么两头一起换，要么一起不换。
- **声明**：`app/common/auth.py::USER_LOOKUP_COLUMNS` / `USER_LOOKUP_SQL`——查人交出哪些列。`app/agents/contracts.py::Principal.from_user` 取的是 `user["id"] or user["username"]`，所以这枚列名声明一列一列地决定归属键属于哪套命名空间；内存表与 PostgreSQL 两支从此共用同一份投影（`_project_user_row`），库里多出一列不再能悄悄改写主体身份。
- 🔴 **算式仍只一枚**。本单没有把尺子换成 `principal.username`：那会改掉 `is_owned_by` 对 bigint 形主体的判定，而那一格由 `tests/test_r484_session_read_leg_owner_filter.py:406` 钉着（「台账竟然认得 bigint 那套 namespace」＝结论要重写）。R495 做的是把那枚**既有**算式的来源写成声明、只留一处、换掉当场拒。

### 执法点

命名空间被换掉不许静默。两处执法、一处只出证词：

- 写腿 `SessionRegistry.bind()`：这枚 principal 的归属键不在 `SESSION_OWNER_NAMESPACE` 声明的那套里，而台账上已经有一行恰好按该主体的**用户名**写着 `owner_id`（同一个人此刻两套键）⇒ 抛 `SessionOwnerNamespaceError`，台账字节零改动。对外不是新码：`app/api/v1/chat.py` 写腿本来就把 `bind()` 的 `PermissionError` 折成 403 `permission_denied`，本错类是它的子类。
- 读腿 `SessionRegistry.is_owned_by()`：判定仍交回 `False`——不是你的会话要像不存在一样（`GET /api/v1/sessions/{id}` 404 `resource_not_found`、`GET /api/v1/sessions` 不进出口、admin 不豁免，这一格一字未改），但落一条 ERROR 证词，把「命名空间漂了」与「这个人确实没有会话」在日志里分开。
- 证词本体 `SessionRegistry._owner_key_drift()`：只报成因（两套键的名字与行数，不落用户名），不参与归属判定，因此不是第二把尺。

### 对外可见行为

无变化。三档会话归属（admin / evalbot / staff）改前改后逐枚相等：在库里 1020 枚（admin 336＋evalbot 656＋五枚孤儿名 28）、台账 1027 行（admin 343 对库里 336，7 枚 ghost 绑定永不进出口）这份形状副本上，真路由 `GET /api/v1/sessions` 的出口成员逐枚等于在册内核 `scripts/r484_session_read_leg_ledger.py::visible_ids` 的读数；台账 JSON 仍是 `session_id / owner_id / status / created_at` 四列，`created_at` 之外改前改后两份字节同形；`GET /sessions/{id}` 与五扇门（delete／cancel／hitl/pending／approve）的状态码与 detail 一个都没改；**没有新对外码**。

### 凭据（判据②③④；行号一律运行时派生，本段只认函数名与文本锚点）

- 新增常驻闸 `tests/test_r495_session_owner_namespace_is_declared.py`（15 枚）：命名空间字面声明全仓恰好一处；归属键算式全仓恰好一处且 `app/storage/sessions.py` 里 `str(principal.user_id)` 归零、除算式自己之外零处读 `principal.user_id`；判归属的比较式只两枚（读腿一枚、重绑闸门一枚）；拿**真** `auth.create_user`/`auth.get_user` 造出的主体必须属于声明的那套命名空间（真源对账，不是文本比对）；列名声明与它拼出的 SQL 不得分叉、`get_user` 里不许手写第二句 SELECT；命名空间被换掉时写腿必须抛 `SessionOwnerNamespaceError` 且台账字节恒定；这枚错类必须落进 chat.py 既有的 `except PermissionError` → `permission_denied`，同时 `app/**` 里不许出现新的 `detail=` 字面；读腿保留 `False` 但必须留证词，而「确实没有会话」那一形必须一个字都不落；整套键一致时归属照常成立；外来主体什么都学不到；基点那份台账文件今天仍原样读回、不长新列。
- 新增行为不变面件 `tests/test_r495_owner_filter_is_unchanged_before_after.py`（6 枚）：`git show HEAD:app/storage/sessions.py` 现取的**旧尺**与今天的尺在同一份台账字节上逐枚相等，并与 R484 内核三方对账；真路由出口等于内核读数；三档读数必须 336 / 656 / 0、孤儿 28 枚零外泄、台账超集 7 枚零放大；改前改后写出的台账 JSON 逐字节同形。
- 反证三刀（走 R253 影子根：变异只落 `%TEMP%` 副本，被跟踪文件全程只读，出门核对 `restored=True`／`shadow_clean=True`）：**刀一** 列名声明补 `"id"` ⇒ 8 枚件 129 钉夹具上 **2 枚红**（真源 SELECT 对账、真 principal 形状），运行期同刻**响**：`raised='SessionOwnerNamespaceError'`、`read_back=False`、ERROR 证词 2 行、台账字节恒定。**刀二** 读腿判定改恒真 ⇒ **31 枚红**／95 passed（本单 7＋R484 11＋`test_session_ownership_guards` 2＋`test_session_route_authorization` 2＋R295 1＋R179 8）。**刀三** `app/storage/sessions.py` 整片退回基点那份字 ⇒ **5 枚红**，全在「声明唯一／算式唯一／比较式唯一／写腿拒／读腿证词」这五格，**行为一格没红**（其余 121 枚照绿）——这正是病根本来的形状：显式化被摘掉之后出口一切如常，没人能从不改的行为看出承重墙被拆了。刀三另带两枚反向约束：SELECT 对账那一格必须绿（牵连它就是刀身越界），外来主体那一格必须绿（摘显式化不许顺手把闸门改松）。三把刀在常驻态各有一枚 `test_counter_evidence_*`，不开环境变量也在件内开窗跑同一套判据，该红的没红就当场 `pytest.fail`。

### 本节没做的事（不许读成已收）

- 没把 `is_owned_by` 在漂移时改成报错：那一格 `False` 是别人的在册牙（R484:406），本单不许磨。⇒ 出口今天仍可能 200 + `[]`，只是从此被三件同时看着：写腿拒、两枚常驻钉红、每次误判一条 ERROR。「**出口自己会响**」这一格没做到。
- 没给台账加列、没写迁移、没碰 `data/.session-metadata.json` 一个字节；也没做「把两套键混写过的那份台账搬回一套」的手续——今天写腿只**拒**，不搬。
- 没动 `app/api/v1/chat.py`：队列归属回读那格（`str(claimed_id) != str(live.user_id)`）吃的是同一枚 `principal.user_id`，SELECT 补 id 时它同样翻命名空间，读数落 `QUEUE_OWNER_STALE`（判失效，不是泄漏）。那一本账不在本段口径里。
- 没动 `app/agents/contracts.py:34`——「一枚字段两套身份」的翻译点本体在那里。要根治得让 `Principal` 自己说清哪一列是身份、哪一列是标签；本段只把会话这一侧的后果接住。
- `app/storage/artifacts.py`、`app/storage/datasets.py`、`app/knowledge_graph/service.py` 各自也在用 `str(principal.user_id)` 当 owner 列。那是另外三本账，R495 的真源只管会话台账；本段不替它们定命名空间，也不声称它们已同源。