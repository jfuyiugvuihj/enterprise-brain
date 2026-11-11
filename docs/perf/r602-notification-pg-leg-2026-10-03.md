# R602 · 通知中心的 PG 腿：`row_factory` 递不下去那 6 天 22 小时（2026-10-03）

席：Boole（执行层）· 单号 R602（P1）· 事故 #106 · 树 `be-r602`@`292168a` · 交工日期 2026-10-03
判据事实源：`docs/handoff/2026-09-15-backend-followup-requests.md` §160.7（跟进单第 5393-5402 行，按 LF 计数）

---

## 0. 一句话

`app/notifications/states.py::_conn` 从并树那天起就把 `row_factory=dict_row` 递给一枚**不收这一格**的边界
（`connect_with_policy` 全具名关键字、无 `**kwargs`），于是通知中心三条腿里唯一那本"谁读过什么"的账在**任何
真库**上都没有通过过一次：读腿 500、写腿 500。本单把转发那一格补上（`**driver_kwargs`），并补上第一枚
**不 mock `_conn`** 的常驻钉。

## 1. 这枚病从哪一笔开始坏（判据⑥·取证自取，与派工词的线索差一笔）

派工词与 §160.7 的线索写的是 `fa8709c`。现场取证把它劈成两笔：

| 笔 | 时间 | `states.py::_conn` 的样子 | 这条腿通不通 |
| --- | --- | --- | --- |
| `fa8709c`（并树 R299） | 09-26 17:54:47 | `return psycopg.connect(_PG_URL, row_factory=dict_row)` | **通**（裸连本来就收 `row_factory`） |
| `fea3161`（总控落笔收口 R299 那枚新裸连） | 09-26 18:00:55 | `return open_connection_with_policy(settings, row_factory=dict_row)` | **从这里起恒 TypeError** |

- 凭据：`git show fa8709c:app/notifications/states.py` 里 `_conn` 是裸 `psycopg.connect`；
  `git log -S open_connection_with_policy -- app/notifications/states.py` 只点出 `fea3161` 一笔；
  `git rev-list --count fa8709c..fea3161` = **1**（紧挨着的下一笔）。
- `open_connection_with_policy` 本身由 `e5db4a4`（并树 R238，09-25）造出来，从造出来那天起就没有转发格 ——
  它当时的自我定位是"留给后续调用点迁入时用的同形入口"，而 R238 明写"一个调用点都不迁"。
- 🔴 所以账面该记的坏点是 **`fea3161`（09-26 18:00:55）**，不是 `fa8709c`。§160.7 那句"R299 并树那笔
  （`fa8709c`，总控落笔收口）当时就被账本钉逼着改了落点"把两笔合成了一笔：收口是**另一笔**。
- 到本单交工为止的账龄：09-26 18:00:55 → 10-03 16:4x，**6 天 22 小时**（§160.7 写的
  "20 多天"是那条注释的年龄，不是这枚 500 的年龄；本单一手读数只支持 6 天 22 小时这一格，其余按未验）。

## 2. 今天为什么才发现（判据⑥）

1. **在册测试桩全部打在 `states._conn` 上**（`app/notifications/states.py` 那枚收口注释自己就写明了这一点）。
   mock 掉 `_conn` 之后，`row_factory` 那一格从来没有被真签名对过一次，于是"递不下去"在门里是不可见的。
2. **这条腿在生产机器上今天才第一次被真按下去**：V2 #17 那一格今天由总控去取一次端到端读数，撞见的是
   恒 500，才把账从"欠一次读数"改写成"端点本身坏"。
3. 病与库无关、与迁移无关、与 Redis 无关，所以按库里有没有表去试的那几条路都指不到它 —— 它死在**签名**上，
   连一次握手都没发出去（修前那一格根本没走到 `psycopg.connect`）。
4. 🔴 教训同族：这是今天第二例"拿 mock 的绿当真机的绿"（第一例是 `test_r181` 那枚把"此刻盘面"当判据的钉）。
   本单因此把新钉的第一条纪律写成"一枚 `_conn` 桩都不许有"。

## 3. 修前的一手读数（判据①②，全部本班现取，不采信派工词转述）

### 甲 · 读腿：一发 `GET /api/v1/notifications` 的容器日志栈

命令（宿主，backend 宿主端口 8001＝后端）：先 `POST /api/v1/login` 拿 token，再 `GET /api/v1/notifications`，
再 `docker logs --since <发枪时刻> enterprise-brain-backend-1`。

- `POST /api/v1/login`（用户取 `deploy/.env.server` 的 `AUTH_USERNAME`＋`DEMO_ADMIN_PASSWORD`）→ **200**
- `GET /api/v1/notifications` → **500 `Internal Server Error`**（裸文本，不是 ErrorEnvelope）
- 日志切片 `prefix-container-log.txt`（88 行，sha256 前 12 = `676155A20394`），`MARKER_UTC 2026-10-03T07:33:09Z`
- 栈帧逐枚点名（`/app/...` 是容器内路径）：

```
Traceback (most recent call last):            （日志第 10 行）
  app/api/v1/notifications.py:199   list_notifications      return await build_inbox(...)
  app/notifications/inbox.py:122    build_inbox             read_back = state_store.recipient_states(recipient)
  app/notifications/states.py:177   recipient_states        with _conn() as conn:
  app/notifications/states.py:83    _conn                   return open_connection_with_policy(settings, row_factory=dict_row)
  app/db/connection.py:279          open_connection_with_policy  return connect_with_policy(settings.url, **kwargs)
TypeError: connect_with_policy() got an unexpected keyword argument 'row_factory'   （第 88 行）
```

### 乙 · 未读徽标那一格落到哪张脸（§160.7 点名"必须实测，不许推断"）

`inbox.py:123` 的 `ledger_answered = read_back is not None` 今天**一枚脸都没落到**：`recipient_states` 在第
177 行就抛了，`read_back` 压根没被赋上值，于是整页 500 —— 生产机器落的是**第三张脸（裸 500）**，既不是
`None`（答不上）也不是 `{}`（真没有行）。这条不是推断：栈顶那一帧在 `recipient_states` 里面，`inbox.py` 的
那两句在栈上根本没有对应帧。

### 丙 · 写腿同病（判据②：先造可地址的 notification id，走在册告警链路，零手插库行）

- 造法：`POST /api/v1/alerts/check`（在册巡检，`evaluate_all` → `INSERT INTO alerts`）→ **200**，
  `alerts` 表 id 从 `[1,2,3,4]` 涨到 `[1,5,6,7,8]`，新出 **5/6/7/8** 四枚，`department=财务部`、`status=open`。
  本单没有手插过一枚库行，也没有 `psql` 可用（backend 容器内没有 psql/ps）——全部走的是那四枚在册出口。
- 可地址性自证：`GET /api/v1/alerts/5` → **200**（`can_address` 的告警腿取的就是这枚详情端点，行级归属谓词同源）。
- 逐枚读数（`MARKER_UTC 2026-10-03T07:40:55Z`，日志 `prefix-write2-log.txt`，88→172 行，sha256 前 12 = `E66FAB8EC808`）：

| notification id | `POST /notifications/read` | `POST /notifications/dismiss` | reason / 栈顶 |
| --- | --- | --- | --- |
| `alert:5`（open，可地址） | **500** `Internal Server Error` | **500** `Internal Server Error` | TypeError，`states.py:203 read_state` → `:83 _conn` |
| `alert:6` | **500** | **500** | 同上 |
| `alert:7` | **500** | **500** | 同上 |
| `alert:8` | **500** | **500** | 同上 |
| `alert:1`（closed=终态） | 200 `changed=0` | 200 `changed=0` | `notification_not_addressable`（`can_address` 在 `_conn` 之前挡：终态不可地址） |
| `alert:9999` | 200 | 200 | `notification_not_addressable` |
| `alert-1:2` | 422 | 422 | `validation_error`（id 形状不合） |
| `report:1` | 422 | 422 | `validation_error`（第四枚源不在白名单） |
| `document:nope` | 200 | 200 | `notification_not_addressable`（无 `#v` 版本段） |

- 日志里 8 枚 `Traceback` 配 8 枚 `TypeError: connect_with_policy() ... 'row_factory'`，与读腿**同一枚错**。
- 🔴 结论：**写侧与读侧同病**，坏点同一格。§160.7 留的那一格（"写腿要先造一枚真能地址的告警才能证"）今天证到了。
- 🔴 顺带纠正一处账面：派工词里 `alert:1` 得 200 `notification_not_addressable` 被记成"`can_address` 在
  `_conn` 之前就挡了"——挡它的那一格具体是 `inbox.py:226` 的**终态判定**（`alerts` 表里 id=1 今天 `status=closed`），
  不是形状也不是"不存在"。所以"能地址"的判据要看 `status`，光把 id 拼对不够。

## 4. 修后的一手读数（判据③的后半：真机、真库、真签名）

容器里跑的是 `enterprise-brain:local` 镜像内的**修前**代码，本单不许动容器、也不许并树，所以"修后的真机读数"
用另一条零副作用的路取：**把改后的 `app/db/connection.py` 从 stdin 送进 backend 容器，只在内存里替换那一格，
容器文件系统一个字节都不动**（零 `docker cp`、零 `--force-recreate`、零 INSERT）。

命令原文：

```powershell
# 收尾时（注释那一格换了代之后）用交工态 connection.py 重跑过一遍，两份命令都在案：
Get-Content -LiteralPath "$env:TEMP\r602\container_probe.py" -Raw | docker exec -i enterprise-brain-backend-1 python -
Get-Content -LiteralPath "$env:TEMP\r602\probe_final2.py"  -Raw | docker exec -i enterprise-brain-backend-1 python -
```

读数·交工态那一版原文（`MARKER_UTC 2026-10-03T08:35:46Z`＝北京 16:35:46；注入的 `connection.py`
逐字节 = `a37e5002462f` / 14328 字节 / 293 CRLF / 零 bareLF，探针自己把这几格打出来了）：

```
MARKER_UTC 2026-10-03T08:35:46Z
embedded connection.py bytes = 14328 crlf = 293 bareLF = 0 sha256[:12] = a37e5002462f
auth._db_ready = True | states._database_available() = True
container connect_with_policy params: ['url', 'policy', 'environ', 'connect', 'transient', 'sleep', 'clock']
PRE-FIX _conn() -> TypeError: connect_with_policy() got an unexpected keyword argument 'row_factory'
injected params: ['url', 'policy', 'environ', 'connect', 'transient', 'sleep', 'clock', 'driver_kwargs']
POST-FIX _conn() -> Connection
to_regclass row: dict -> {'table_name': 'notification_states'}
notification_states rows: {'n': 0}
recipient_states('admin') -> dict {}
read_state('admin','alert:5') -> None
DONE (零写：只有 to_regclass / count(*) / SELECT)
```

同一枚探针、同一个容器，先在**没 import `app.common.auth`** 的裸进程里跑了一遍（`MARKER_UTC
2026-10-03T08:35:12Z`，注入的仍是 `a37e5002462f`），那一遍交回的是另一张脸：

```
injected params: [..., 'clock', 'driver_kwargs']       # 转发那一格同样已生效
POST-FIX _conn() -> Connection                         # 签名那一格同样已通
_database_available() = False
recipient_states('admin') -> NoneType None
[R388] 生产环境存储未就绪，生命周期这一格答不上而不是交回内存空账: code=storage_unavailable
read_state('admin','alert:5') -> NotificationStateStoreMissing (app/notifications/states.py:195)
rc=1
```

逐格怎么说：

- **`0016` 那张表在**（`to_regclass` 交回 `notification_states`），所以这枚 500 与迁移无关，账面里"缺表"那一族
  可以排除。
- **`notification_states` 行数 = 0**：这与 `legitimately_empty` 那句旧话**不矛盾但也没有替它翻绿** —— 表在、
  零行，是因为写腿从来没有成功过一次（同一枚 TypeError）。V2 #17 那一格仍按**未验**记，见 §7。
- 🔴 **R388 那两枚脸在生产机器上是实测分开的**（不是推断）：`{}` = "查过了，确实没有行"，`None` = "答不上
   （存储这一格不供数）"，两遍读数来自同一枚修后的转发格。判据是 `app/notifications/states.py:70-72` 的
   `_database_available()`，它读的是 `sys.modules['app.common.auth']._db_ready` —— 所以**在没 import auth 的
   裸进程里它是 False**，那一带压根走不到 PG 腿。这一格是探针进程的性质，不是这条腿的性质。
   🔴 HTTP 那条路上 `_db_ready` 该为真（应用启动即 import auth，`PRE-FIX` 那一遍正是从容器自带模块读到那枚
   TypeError 的），但**修后的 HTTP 读数本单没取**，这句只算结构账、不算实测，见 §7·1。
- **修前与修后在同一次进程里各量一遍**（`PRE-FIX` 从容器自带模块抛 TypeError、`POST-FIX` 注入后才通）：
   同一进程、同一环境变量，排除了容器重启与环境漂移这一族干扰。注入只活在 `docker exec` 新起的那枚子进程里，
   容器里那个服务进程和它的文件系统一个字节都没被碰（零 `docker cp`、零写、零 `--force-recreate`）。
- **`read_state(...) is None`** 说的是"这一枚没有行 = 未读"，与上面那句不冲突（`read_state` 的 `None` 本来
  就只兼这一格意思，见 `states.py:185-192` 文件头）。
- 🔴 这一串是**内存注入态**的读数，不是"容器已经好了"的读数。真正的 HTTP 端到端（`GET` 交回 200 一页收件箱）
  要等总控并树 + 重建镜像/`--force-recreate`，本单**没做也不该做**，见 §7。

## 5. 修法与边界（照 §160.7 写死的那两条之一）

选了**第一条**：让边界把多余 kwargs 转发进 `connect(...)`。

- `app/db/connection.py`：`connect_with_policy(..., clock=None, **driver_kwargs)`；合并那一格改成
  `kwargs = {**driver_kwargs, **connect_kwargs(plan, url)}`。**策略那两枚排在后面** —— 调用方不许拿同名键
  盖掉操作者拧开的 env（R238 判据③：时延参数只许一处说了算）；env 全关时 `connect_kwargs` 交回空 dict，
  转发格因此逐字节等于调用方给的那几枚，判据①那句"不设 env 就是今天"一个字没动（有钉）。
- 四枚测试缝 `connect` / `transient` / `sleep` / `clock` 一枚没碰，`open_connection` 一个字节没改，
  裸 `psycopg.connect` 一枚都没新长（棘轮现场读数 17 枚 = 摘前，见 §6·乙）。
- `app/notifications/states.py`：只改掉那枚**假话注释**（第 81 行，1 进 1 出，全文件行号一字未动，
  `:83` 仍是那枚调用），代码格零改动。
- 🔴 注释里那两句**过期账**也在本单一并改掉：初版把 `connection.py` 的 docstring 与 `tests/test_r602_*`
  的件头写成「从 `fa8709c` 起」「门绿了 20 多天」——那是照派工词抄的，与本单 §1 的一手取证矛盾。交工态的
  措辞是「从 `fea3161`（09-26 那笔把落点收进边界的收口笔）起在真库里一次都没通过过，而全量门一路绿」。
  这枚病不该在注释里被写成比账上更老。
- 为什么不走第二条（改 `states.py` 去抄 `pg_store::_connect` 的形状）：`pg_store` 那条腿今天**根本没递
  `row_factory`**（它用 `open_connection(settings)` ＋ `_row_value(row, name, idx)` 的位次读法），抄过来等于
  把 `row['notification_id']` 那一族全改写；更要紧的是 §160.7 判据④·甲要求"摘掉 `row_factory` → 新钉必须红"，
  第二条路走下去 `row_factory` 压根不存在，那把刀就无从下手。假话在边界那一格，就在边界那一格治。
- 🔴 全程零 `try/except` 糊弄：没有把 500 折成 503、没有折成 `{}`、没有折成 `None`。这一条不只写在纸上，
  有反证刀（§6·丁）。

## 6. 反证（判据④：四把，每把三列 sha ＋ 还原逐字节等）

`states.py` 摘前/还原同一枚 sha = `4d970b3a7683`（本件从取证到交工一个字节没再动，见 §5）。
`connection.py` 交工态 sha = `a37e5002462f`（293 行 / 14328 字节）。它在 `292168a` 的基线**分两代账，两代都
对，差别在层**：工作树层（`git checkout --` 落盘，CRLF）= `320b8f327aa0`（279 行 / 13075 字节）；git blob 层
（`git cat-file blob` 的原始字节，LF）= `db89494ced98`（12796 字节）。本仓 `core.autocrlf=true`、无
`.gitattributes`，所以同一内容天然有两枚 sha256。🔴 下面刀表一律按**刀真正落在盘上的那一层**记（=工作树层），
初版在丁那一格混用过 blob 层，已订正。

| 刀 | 摘法 | 靶子 | 摘前 | 摘后 | 还原 |
| --- | --- | --- | --- | --- | --- |
| 甲 | 摘掉 `states.py:83` 的 `row_factory=dict_row` | `tests/test_r602_notification_pg_leg.py` | sha `4d970b3a7683` / rc=0 `7 passed, 1 skipped` | sha `a5c8d7c33602` / **rc=1 `2 failed`**（两枚真签名钉，报"驱动那一层收到 `{}`"） | sha `4d970b3a7683` 等=True / rc=0 全绿 |
| 甲′ | 同一摘法，只点第一枚钉 | `…::test_the_real_states_conn_leg_delivers_row_factory_to_the_driver` | rc=0 `1 passed` | **rc=1 `1 failed`** | rc=0 `1 passed` |
| 乙 | `_conn` 退回裸 `psycopg.connect(settings.url, row_factory=dict_row)` | `tests/test_r238_bare_connect_ratchet.py` ＋ 现场扫描 | `OUTSIDE=17`（`app/**` 14＋`scripts/**` 3）/ states.py 零命中 / rc=1 `14 failed, 19 passed` | `OUTSIDE=18`，新增身份**点名 `app/notifications/states.py::_conn#0`** / rc=1 `14 failed, 19 passed` | `OUTSIDE=17` / states.py 零命中 / rc 同摘前 |
| 丙 | 把"答不上"那一格洗成空账（`return None` → `return {}`） | `tests/test_r388_read_leg_answers_absence.py` | sha `4d970b3a7683` / rc=0 `55 passed, 1 xfailed` | sha `6863961aca92` / **rc=1 `14 failed, 41 passed, 1 xfailed`**（含 `test_the_empty_ledger_and_the_absent_ledger_are_two_different_words`、`test_production_without_a_store_the_read_leg_says_it_cannot_answer`、三枚 `test_counter_evidence_*`） | sha `4d970b3a7683` 等=True / rc=0 全绿 |
| 丁 | 摘掉转发那一格本身：`git checkout -- app/db/connection.py`（回到工作树层基线 `320b8f327aa0`，签名里没有 `**driver_kwargs`） | `tests/test_r602_notification_pg_leg.py` | sha `a37e5002462f` / rc=0 `7 passed, 1 skipped` | sha `320b8f327aa0` / **rc=1 `6 failed, 1 passed, 1 skipped`**，报错原文就是 `TypeError: connect_with_policy() got an unexpected keyword argument 'row_factory'`（`connection.py:279`） | sha `a37e5002462f` 逐字节等=True / rc=0 `7 passed, 1 skipped` |

🔴 复跑记录：本单在并纸之前又订正过一次**注释**（见 §5 末条），`connection.py` 与新钉的指纹因此换了一代；甲、丁两把刀已在**新指纹**上重跑，上表的数与 sha 就是重跑后的读数（甲：摘前 rc=0 `7 passed, 1 skipped` → 摘后 states.py `a5c8d7c33602` / rc=1 `2 failed` → 还原 `4d970b3a7683` 等=True / rc=0 全绿；丁见上行三列）。

四把各证一句话：

- 甲/甲′：新钉咬的是**转发**，不是形状 —— 摘掉调用方那一枚 kwarg 就红（判据④·甲）。
- 乙：这枚新落点在棘轮面前是**当场涨一枚且被点名**的，所以修法不可能靠"新盖一间裸连的小房子"混过去。
  🔴 必须记清楚：`test_r238_bare_connect_ratchet` 与 `test_r346_line_ledger_is_derived_not_copied`
  **在 `292168a` 基点上就是红的**（`app/rag/retriever.py::_read_engagement_rows#0` ＋
  `scripts/r579_index_crossover_readout.py::Db.open#0` 两枚他单在飞的落点，`14 failed / 23 failed / 1 failed`
  三枚读数在本单**回退到干净基线后复跑逐枚相同**，与本单零关系）。因此乙这一把按**枚数与身份**读，不按绿红读。
- 丙：`None`（答不上）与 `{}`（真没有行）这两枚脸**分得开，且分开是有牙看守的** —— 洗一次就红 14 枚。
- 丁：转发这一格是这枚病的**唯一原因**：把它摘掉，容器里那枚原文报错在测试里逐字节复现。

## 7. 没验的格子（逐枚点名；宁可写未验）

1. 🔴 **V2 #17「通知端到端」= 未验**。本单证到的是"签名那一格修好了、真库上读写两条腿都能发出去了"，
   **没有**证到"客户屏上那页收件箱从此画得对"：容器仍跑修前镜像，`GET /api/v1/notifications` 的**修后 HTTP 读数**
   本单没取到（取它要并树＋重建镜像/`--force-recreate`，那是总控的活）。§160.7 那句"读侧没有「这一格不供数」
   字段"一类的账因此也仍欠。
2. 🔴 **C 门「越权 0 条」= 未验**（照判据⑥原样入账，修好之前一律记未验；本单没有为它取过任何读数）。
3. **写腿真落库 = 未验**。修后我只在真库上跑了 SELECT（`recipient_states` / `read_state` / `to_regclass` /
   `count(*)`），**一次 INSERT 都没发**：那会给客户的 `notification_states` 落下测试行。`apply_state` 的
   `INSERT ... ON CONFLICT` 那一格今天仍是"读了代码、没跑过"。
4. **未读徽标在修后的屏上长什么样 = 未验**（与 1 同因）。
5. **`notification_states` 上 0016 的约束/索引行为 = 未验**（表在、零行；本单没写过一行，所以
   `reader_key` 与 `ON CONFLICT` 那对搭配仍没被真机碰过）。
6. **契约那一格 = 没动**（判据⑤：`docs/api/contract-v1.md` 由总控落笔，本单零追加）。
7. **`alert:2`（acknowledged）能否地址 = 未验**。表上 status 三态只实测了 `open` 通、`closed` 挡，
   `acknowledged` 那一格没取读数，本单不敢替它写结论。
8. **R60 的 Chroma 停写、`app/rag/**` 任何一格 = 没碰**（禁区，`Aquinas`/R60 在飞）。

## 8. 复跑的数（一律标"执行层自报"）

解释器 `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -X utf8`（`be-r602` 树内**没有** `.venv`），
每枚单件都带路径参数，参数 `-o addopts= -p no:cacheprovider --basetemp=$env:TEMP\r602\<独有名> -q`。
**没跑过 `scripts/run_gate.py`**（全量门归总控）。

收尾订正（注释那一格换了代）之后，下表里的件又复跑了一遍，数逐枚相同：新钉 `7 passed, 1 skipped`；
`test_r238_connect_boundary_policy` 24；`test_r388_read_leg_answers_absence` 55 passed + 1 xfailed；
`test_r299_notification_states` 9；`test_r299_notification_inbox` 35；`test_r303_pg_upsert_leg` 9；
`test_r238_bare_connect_ratchet` `14 failed, 19 passed`；`test_r346_line_ledger_is_derived_not_copied`
`23 failed, 12 passed`；`test_r389_r382_connects_go_through_the_boundary` `1 failed, 31 passed`。
（最后三枚红的仍是 §6·乙 点名的前在红，与本单零关系。）

| 件 | 读数（执行层自报） |
| --- | --- |
| `tests/test_r602_notification_pg_leg.py` | `7 passed, 1 skipped`（skip 那枚 = `R602_REAL_PG` 开关的端到端） |
| `tests/test_r238_connect_boundary_policy.py` | `24 passed` |
| `tests/test_r388_read_leg_answers_absence.py` | `55 passed, 1 xfailed` |
| `tests/test_r299_notification_inbox.py` | `35 passed` |
| `tests/test_r299_notification_states.py` | `9 passed` |
| `tests/test_r303_notification_pins.py` | `15 passed` |
| `tests/test_r303_pg_upsert_leg.py` | `9 passed` |
| `tests/test_r376_gate_shape_pins.py` | `24 passed` |
| `tests/test_r376_notifications_refuse_a_store_that_is_not_there.py` | `30 passed` |
| `tests/test_r381_outlet_answers_the_absent_approval_ledger.py` | `32 passed` |
| `tests/test_r381_outlet_shape_pins.py` | `21 passed` |
| `tests/test_r366_inbox_keeps_its_legs_when_the_alert_store_refuses.py` | `24 passed` |
| `tests/test_r373_the_two_remaining_legs_answer_absence.py` | `39 passed` |
| `tests/test_r390_xfail_strict_and_boundary_pins.py` | `11 passed` |
| `tests/test_r466_mutation_does_not_leak_into_live_module.py` | `20 passed` |
| `tests/test_r469_driver_discipline.py` | `11 passed` |
| `tests/test_r238_bare_connect_ratchet.py` | `14 failed, 19 passed` ＝＝**与干净基线复跑逐字相同**（前在红，非本单） |
| `tests/test_r346_line_ledger_is_derived_not_copied.py` | `23 failed, 12 passed` ＝＝**同上** |
| `tests/test_r389_r382_connects_go_through_the_boundary.py` | `1 failed, 31 passed` ＝＝**同上** |

基线对照的方法（不是嘴上说说）：把本单三件改动逐字节备份到仓库外 → `git checkout --` 两枚 app 文件 ＋ 移掉新钉
→ 盘面回到 `292168a` 干净态（`git status --porcelain=v1` 空）→ 复跑那三枚件 → 数与修后**逐枚相等** → 再把
三件原样放回（放回后 sha 与备份相等）。

## 9. 盘面与指纹（交工态）

```
$ git diff --numstat HEAD
17      3       app/db/connection.py
1       1       app/notifications/states.py

$ git ls-files --others --exclude-standard
docs/perf/r602-notification-pg-leg-2026-10-03.md
tests/test_r602_notification_pg_leg.py
```

逐件指纹（CRLF、无 BOM；行数按 CRLF 切）：

| 件 | sha256[:12] | 行数 | 字节 | crlf | lf | BOM |
| --- | --- | --- | --- | --- | --- | --- |
| `app/db/connection.py` | `a37e5002462f` | 293 | 14328 | 293 | 293 | 无 |
| `app/notifications/states.py` | `4d970b3a7683` | 272 | 16477 | 272 | 272 | 无 |
| `tests/test_r602_notification_pg_leg.py` | `c6926e872bbd` | 245 | 10614 | 245 | 245 | 无 |
| `docs/perf/r602-notification-pg-leg-2026-10-03.md` | 见本单交回盘面读数（本文件自身） | — | — | — | — | 无 |

- `states.py` 改的是注释那一格，**行数不变（272）**、`:83` 那枚调用位置不变 —— 全仓那几处引用
  `states.py:177 / :203 / :231 / :83` 的账面（含 §160.7 与 `states.py:112-114` 自己那句"坐标按树取"）
  因此一格都不用跟着漂。
- 禁区零触碰：`app/rag/**`、`app/common/model_handler.py`·`model_budget.py`、`app/agents/nodes.py`·`contracts.py`、
  评测集与三片 jsonl、`tests/test_evaluation_report.py`·`test_r94_*`、`scripts/backup_database.py`·
  `restore_database.py`、`Dockerfile`、`tests/test_r283_*`、`retrieval_pipeline.py`、`r577*`/`r536*`、
  `tests/_temp_edit_overlay.py`·`test_r516_*`、`docs/handoff/**`、`frontend/**`、`migrations/**`、`chroma_db/**`。
- 零 commit / 零分支 / 零 push / 零 `.gitignore` 改动。

## 10. 新钉那一格怎么读（判据③的形状）

`tests/test_r602_notification_pg_leg.py`（8 枚，1 枚默认 skip）：

1. `test_the_real_states_conn_leg_delivers_row_factory_to_the_driver` —— 真 `states._conn()` 一路走到**驱动**那一层，
   断言收到的就是 `dict_row`。桩只打在 `psycopg.connect`（R238 同一族做法），`_conn` /
   `open_connection_with_policy` / `connect_with_policy` 全程原样跑。
2. `test_the_recipient_read_reaches_the_driver_with_row_factory` —— 把调用方也拖进来（`recipient_states` →
   `_require_table` 读 `row["table_name"]`），因为驱动收不到 `row_factory` 时死法会换一格。
3. `test_forwarding_leaves_the_bare_call_shape_alone_when_the_caller_says_nothing` —— 判据①：调用方不多给一枚时，
   发出去的调用逐字节还是 `connect(url)`，`driver.calls == [((URL,), {})]`。
4. `test_a_forwarded_kwarg_and_a_policy_kwarg_travel_in_the_same_call` —— 转发与策略同发一程。
5. `test_the_policy_wins_over_a_caller_supplied_latency_kwarg` —— 合并次序钉死：策略在后面。
6. `test_the_retry_seams_still_bite_next_to_a_forwarded_kwarg` —— 四枚测试缝一枚没撞坏，且重试三发同形。
7. `test_a_failure_on_the_way_to_the_driver_is_not_washed_into_an_empty_ledger` —— 反 try/except：驱动抛的错
   原样上抛，不许折成 `{}` / `None`（就是 §160.7 与 `states.py:65-66` 那条纪律的牙）。
8. `test_the_real_pg_leg_answers_with_mapping_rows` —— **默认 skip**，`R602_REAL_PG=1` 才碰真库，
   照 `tests/test_r540_scan_offline.py:44` 那枚 `R540_REAL_OCR` 的先例；常驻门一次真握手都不发。

## 11. 给总控的四句（不落笔，只点名）

1. §160.7 里"从 R299（`fa8709c`）起恒 500"该订正成**从 `fea3161`（09-26 18:00:55，R299 的收口笔）起恒 500**；
   `fa8709c` 那一笔落的是裸 `psycopg.connect(..., row_factory=dict_row)`，那条腿当时是**通的**。
2. "门绿了 20 多天"这句该按"这条腿从坏到被发现活了 6 天 22 小时"改口径（一手读数只支持这个数）。
3. 契约 `docs/api/contract-v1.md` 的 R602 一节由总控落笔（判据⑤）；V2 #17 与 C 门"越权 0 条"两格在本单
   并树＋容器重建**并取到修后 HTTP 读数**之前，继续记**未验**。
4. 本仓 `core.autocrlf=true` 且无 `.gitattributes` ⇒ 同一内容天然有两枚 sha256（blob 层 LF / 工作树层
   CRLF）。并树时若拿 `git show`／`git cat-file` 的字节去对 §6·§9 的指纹会对不上——那不是本单写错，按层
   对即可（两层的数本单都点名了，见 §6 表头）。

