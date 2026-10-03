# R582 · 告警处置三写口落审计账（执行层交工纸·2026-10-03）

单号 **R582**｜执行层自报。树 `C:/Users/fengx/PycharmProjects/be-r582`（detached，基点 `1b0534a`）。
🔴 本纸所有数字都是**执行层亲跑**的读数，不是总控复跑；总控并树前请按同一 HEAD 自取一遍。

## 一、盘面（交回那一刻）

- `git rev-parse HEAD` = `1b0534a9a3825f69de833ff4987436f2154127b9`（基点未动，没有新提交、没有分支）
- `git diff --numstat HEAD` = `96      36      app/api/v1/alerts.py`（净 +60 行）
- 未跟踪：`tests/test_r582_alert_disposal_audit_ledger.py`、本纸
- sha256 前 12（`Get-FileHash` 同口径，`.venv` python `hashlib` 算得）：

| 件 | sha256[:12] | CRLF 枚数 | 行数 | BOM |
|---|---|---|---|---|
| `app/api/v1/alerts.py` | `34017ec67a08` | 1243 | 1243 | 无 |
| `tests/test_r582_alert_disposal_audit_ledger.py` | `e8d7406aea0f` | 628 | 628 | 无 |
| `docs/testing/r582-alert-dispose-audit-2026-10-03.md`（本纸） | 落盘后现算，见 §七 | 126 | 126 | 无 |

两枚件都是单形 CRLF、无 BOM、无裸 CR/裸 LF（`count('\r')==count('\n')==count('\r\n')` 现算自证）。

## 二、改了什么（逐处点名）

1. `app/api/v1/alerts.py:375 _audit_alert_denial` —— **只有 docstring 改了话**：原文那句「也只在拒绝这一侧记账」在补上放行侧之后就是假话，改窄成「这一枚通路只管拒绝，读台账/写规则的放行同样不记；处置写成那一侧另走 `_audit_alert_disposal`」。**函数体那一句 `audit_log.record_audit(principal, ACTION_MANAGE_ALERTS, "denied", resource, reason)` 一字未动**（AST 钉着，见判据②）。
2. `app/api/v1/alerts.py:663 ALERT_DISPOSAL_AUDIT_ACTIONS` —— 三枚动作名，`{action: f"{ACTION_MANAGE_ALERTS}:{action}" for action in ALERT_ACTIONS}`：**派生**自两枚在册符号，件里不出现任何写死的 `"alerts:manage:xxx"` 常量（AST 扫全部字符串常量判这一格）。实测三名 = `alerts:manage:ack` / `alerts:manage:close` / `alerts:manage:assign`。
3. `app/api/v1/alerts.py:675 ALERT_DISPOSAL_AUDIT_OUTCOME = "allowed"` / `:676 ALERT_DISPOSAL_AUDIT_REASON = "permission_granted"` —— 两枚都取在册既有词（`app/common/authorization.py::authorize` 的 allowed/denied 成对词；`app/common/policy.py` 对「角色持有 alerts:manage」交回的那句原话，`app/api/v1/observability.py:589` 已在审计侧引用过）。本件不新造第三份码表。
4. `app/api/v1/alerts.py:680 _audit_alert_disposal` —— 新增的写账函数，走**同一枚** `audit_log.record_audit` 通路（同一本 `audit_events`，不自造事件表），`resource` 沿用 `ALERT_DISPOSAL_RESOURCE`（与拒绝那一格同一道口子的两面），载荷六格：`actor / alert_id / action / status / assigned_by / assignee`，全部取**处置之后读回的那一行**，正文/部门值/密级值一概不进。
5. `app/api/v1/alerts.py:721 _dispose_alert` —— 两条腿（无库内存腿 / 有库 PG 腿）收成 `if / else`，合流之后**只有一枚**写账点：`_audit_alert_disposal(principal, action, alert_id, disposal)` 然后 `return disposal`。三格拒绝仍在合流之前就抛了，所以账上的 `allowed` 行只对应真实写成的处置。行为零变化（写的列、值、commit、读回、交回形状都没动），只是出口多落一行账。

## 三、判据五格逐条

### ① 三枚写口各落一行 `audit_events`，动作名互不相同且与 `ACTION_MANAGE_ALERTS` 同源 —— 达标

- 无库那条腿（真 HTTP 出口 → `_dispose_alert`）：`test_each_disposal_outlet_lands_exactly_one_allowed_line[ack-1|close-3|assign-1]` 三格各 200、各**恰好一行**账，`action` 逐枚等于派生名、`outcome=allowed`、`resource=alert_disposal`、`username` = 处置人，且 `event_id/created_at/expires_at/policy_version` 齐。
- 有库那条腿（替身连接，真 UPDATE 真 commit）：`test_the_durable_leg_lands_the_same_one_line` 三格各 200、`connection.updates` +1、账上各一行，且账上 `status` 与替身库里现在那一版逐字相等。
- 同一本账不是第二套表：`test_the_disposal_line_lands_in_the_one_existing_journal` 从 `GET /api/v1/audit/events`（`source=app.common.audit.get_audit_events`）把 `event_id` 再认一次。
- 同源/不现编：`test_the_three_action_literals_are_distinct_and_derived_from_the_registered_symbol` —— 三名两两不等、逐枚 `== f"{ACTION_MANAGE_ALERTS}:{action}"`、全件 AST 里没有任何字符串常量以 `alerts:manage:` 开头。

### ② 拒绝那一格形状一字不改 —— 达标

- 七格拒绝逐格对 status_code 与 `detail` 原文：staff×3 = `403/permission_denied`，别部门的行 = `404/resource_not_found`，不存在的 id = `404/resource_not_found`，非法跳转 = `409/conflict`，不合格转派 = `400/validation_error`（`test_a_refusal_keeps_its_exact_shape_and_lands_one_denied_line_only`）。每格账上恰好一笔 `denied`、**零笔** `allowed`。
- 唯一通路：`test_denied_still_has_exactly_one_path_and_allowed_one_path` —— AST 现扫全件 `record_audit` 调用点，只许 `{_audit_alert_denial: ["denied"], _audit_alert_disposal: ["allowed"]}` 两处。
- 在册钉点名复跑（总控要求的两枚 + 同族两枚）：`tests/test_r179_chat_denials.py`、`tests/test_r194_queue_denials_and_flat_list.py`、`tests/test_r176_alert_denial_audit.py`、`tests/test_r251_alert_disposal.py` = **122 passed / rc=0**（读数见 §四）。
- 🔴 一笔口径冲突（越出写域，本席不动，交总控裁）：`tests/test_r251_alert_disposal.py:730 test_an_allowed_disposal_adds_no_audit_line` 仍绿——它按 `action == ACTION_MANAGE_ALERTS` 精确匹配取账，而放行侧的名字是派生的 `alerts:manage:<action>`，所以它抓不到新行。它**绿着，但它 docstring 那句「处置成功的那一笔不写安全台账」从今天起是假话**，与本单判据①正面冲突。改它＝改在册件口径（本单明禁），故只上报。

### ③ 转派那一格同时记「谁派的」与「派给谁」 —— 达标

- `test_assign_lands_both_the_assigner_and_the_assignee`：`after_summary.assignee == "r582-target-own"`（派给谁）、`after_summary.assigned_by == "r582-manager-own"`（谁派的）、`actor` 同值，且 `assignee != assigned_by`（写成同一枚就等于只记了前者）；再与 `GET /api/v1/alerts/1` 读回的行对账，两本说得同一句话。
- 对照格：`test_ack_and_close_name_the_actor_in_the_same_shape`（确认/关闭没有接手人，但「谁做的」照样在场）。

### ④ 反证三把 —— 达标（常驻刀 + 现场刀各一套，同一份锚点）

现场刀（在**盘上那枚件**逐把摘、跑 victim 主钉、逐字节还原；锚点直接从常驻钉的 `KNIVES` 导入，不抄第二份）：

| 刀 | 摘前 sha[:12] | 摘后 sha[:12] | victim 主钉（摘后） | rc | 末行 | 还原后 sha |
|---|---|---|---|---|---|---|
| K1 摘掉 `record_audit` 调用 | `34017ec67a08` | `30afc50e0cd8` | `test_each_disposal_outlet_lands_exactly_one_allowed_line` | 1 | `3 failed in 6.40s` | `34017ec67a08` ✅ |
| K2 三枚动作收成同一枚字面量 | `34017ec67a08` | `449c3154f5e6` | `test_the_three_action_literals_are_distinct_and_derived_from_the_registered_symbol` | 1 | `1 failed in 6.97s` | `34017ec67a08` ✅ |
| K3 账上少了 assignee 那一格 | `34017ec67a08` | `f8f3a4b26c95` | `test_assign_lands_both_the_assigner_and_the_assignee` | 1 | `1 failed in 6.28s` | `34017ec67a08` ✅ |

- K1 摘的是整枚调用（只摘头几行会留下悬空实参，编译都过不去——那不是刀，是语法错）。
- K2 只把名字收成同一枚，账照落（`[1,1,1]` 行），所以红的就是「互不相同」那一格，不是「有没有落账」。
- K3 只删 `"assignee"` 那一格，其余载荷不动。
- 收尾 `alerts.py` 与摘前逐字节全等（`git diff --numstat` 回到 `96/36`，`git status` 只有本单两枚件）。
- 常驻版（进全量门、可长期复跑）：`test_every_knife_blinds_the_nail_it_targets[K1|K2|K3]` 三格，变异只落 `tests/_temp_edit_overlay.py::isolated_module` 造的**隔离副本**，盘上原件全程只读，每把进出各取一次 sha256 对账（`tests/test_r253_no_test_rewrites_a_tracked_file.py` 的规矩）；每把先在**未变异**的隔离副本上跑正控（K1 `[1,1,1]`、K2 三种名字、K3 `assignee==TARGET`），确认它会咬再落刀。

### ⑤ 判据用词订正：按 resource/action 取数，`audit_events` 没有 `route` 列 —— 达标（并已把这句话钉住）

- 现网只读凭据（`docker exec enterprise-brain-postgres-1 psql -U enterprise_brain -d enterprise_brain -At -c "select column_name from information_schema.columns where table_name='audit_events' order by ordinal_position"`，rc=0）：`event_id / request_id / actor_username / actor_role / owner_id / action / resource / resource_scope / outcome / reason_code / policy_version / before_summary / after_summary / payload / retention_days / expires_at / created_at` = **17 枚，无 `route`**。
- 本件所有取数把手（`_journal` / `_since` / `_snapshot`）只按 `action` + `resource`（外加 `outcome`）寻址，断言里一次都没出现「按 route 计数」。
- 钉住前提：`test_the_ledger_has_no_route_column` 从 `migrations/0005` 的 DDL 现读列名集合（走 `app.db.migrations.MIGRATIONS`，不手抄），`"route" not in columns` 且 `{"action","resource","outcome"} <= columns`；迁移里若长出 `route` 字样，本钉当场红并要重判口径。

## 四、跑过的命令原文 → rc → 末行读数

解释器一律 `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8`，跑法一律 `-o addopts= -p no:cacheprovider --basetemp=... -q`（`--basetemp` 在 `%TEMP%` 下）。

```
pytest tests/test_r582_alert_disposal_audit_ledger.py            → rc=0   25 passed in 10.38s
     （件形状落定后的末次读数；此前同件另跑过 6.20s / 5.57s / 5.71s 三次，同数）
pytest tests/test_r176_alert_denial_audit.py tests/test_r251_alert_disposal.py
     tests/test_r179_chat_denials.py tests/test_r194_queue_denials_and_flat_list.py
                                                                → rc=0   122 passed in 7.96s
pytest tests/test_r359_alerts_refuse_a_store_that_is_not_there.py
     tests/test_r371_the_conversion_is_narrow_and_stays_at_the_exit.py
     tests/test_r371_migrations_first_answers_503_not_500.py tests/test_r340_replayable_alerts_open.py
     tests/test_r188_alert_count_row_scope.py tests/test_alert_route_authorization.py
     tests/test_phase4_alerts.py tests/test_r176_alert_row_scope.py
     tests/test_r184_alerts_department_column.py                → rc=0   342 passed in 10.60s
pytest tests/test_r376_gate_shape_pins.py tests/test_r367_gate_shape_pins.py
     tests/test_r303_notification_pins.py tests/test_r299_notification_inbox.py
     tests/test_r377_migrations_first_family_is_contained_at_the_store_layer.py
     tests/test_alert_scan_scope.py tests/test_dashboard_summary.py
     tests/test_r183_184_migration_pair.py tests/test_r251_alert_disposal_migration.py
                                                                → rc=0   185 passed in 16.59s
pytest tests/test_r253_no_test_rewrites_a_tracked_file.py tests/test_r253_shadow_root_holds_the_mutation.py
     tests/test_r556_window_posture_is_installed_not_executed.py tests/test_r159_cross_scope_matrix.py
     tests/test_r163_matrix_teeth.py tests/test_r366_inbox_keeps_its_legs_when_the_alert_store_refuses.py
     tests/test_r346_line_ledger_is_derived_not_copied.py tests/test_r396_line_numbers_are_derived_not_copied.py
     tests/test_r483_empty_table_triage_is_derived.py tests/test_audit_persistence.py
     tests/test_r199_anonymous_probe_audit.py                   → rc=1   2 failed, 316 passed in 143.50s
     （两枚红 = tests/test_r483_empty_table_triage_is_derived.py，见 §五乙）
pytest <共置一把梭：r582 + r176 + r251 + r199 + audit_persistence + r303 + r366 + r78>
                                                                → rc=0   194 passed in 12.21s
pytest tests/test_r582_alert_disposal_audit_ledger.py tests/test_r253_no_test_rewrites_a_tracked_file.py
     tests/test_r556_window_posture_is_installed_not_executed.py tests/test_r78_unearned_claims.py
     tests/test_r253_shadow_root_holds_the_mutation.py
                                                                → rc=0   66 passed in 65.22s
     （件落定形状后重跑：新钉自己 + 全仓「测试不许改写被跟踪文件」静态扫 + 窗姿势钉 + r78 同进程共置）
```

全量门 `scripts/run_gate.py` **没跑**（总控独占，本单明禁）。

## 五、越出写域的两笔上报（本席一律不动）

**甲｜R251 那枚「放行不记账」钉的口径过期**：见判据②最后一条。它今天靠 `action` 精确匹配仍然绿，但它的 docstring 与本单判据①正面冲突——要么由总控改口到「按 resource + outcome 计数，放行与拒绝同册」，要么明写它只管 `alerts:manage` 这一枚裸动作名。两样都在 `tests/**` 在册件口径一侧，越出本单写域。

**乙｜本席一手引入两枚在册红**（不藏在绿里）：`tests/test_r483_empty_table_triage_is_derived.py::test_the_in_tree_document_is_the_regenerated_one_byte_for_byte` 与 `::test_the_coordinates_printed_in_the_document_are_the_ones_the_scanner_finds_now`。

- 根因：那枚钉把 `docs/testing/r483-empty-tables-2026-09-29.md` 里的**行坐标**与现场扫描逐字节对账。本单在 `alerts.py` 前半净增 56 行 ⇒ `_dispose_alert` 的 SQL 写点由 `app/api/v1/alerts.py:724` 漂到 `:780`、`evaluate_all` 由 `:957` 漂到 `:1017`（基点现读 `git show HEAD:app/api/v1/alerts.py`：文件 1183 行，`_dispose_alert` 的 def 在 669、其 UPDATE 语句在 724、`def evaluate_all` 在 885；本之后 1243 行，四处分别漂到 721（+52）、780（+56）、945，R483 那枚扫到的 `evaluate_all` 写点由 957 漂到 1017（+60））。基点上这两枚是绿的，红是本单造成的，不是 HEAD 自带。
- 两条出路都在本单写域之外：（甲）重跑生成器 `python scripts/r483_empty_tables_triage.py --sync` 把读数刷新——但那会把 09-29 那份**历史空表台账**的行数与坐标一并换成今天的现网读数，属于数据口径变更；（乙）照 R346／R396 的手法把「行坐标」迁成锚点派生。本席按「不改在册件、不重跑别人的量具」的纪律只上报，不动手。

## 六、未验格（照实写，不许当通过）

1. 🔴 **PG 表里真落三行**未验：生产容器仍跑 pre-fix 镜像（`docker ps` 现读 backend 五分钟前重建过，但那是总控翻 `INDEX_BACKEND` 那一次，不含本单代码）。本单的账证在**账本通路**层（`record_audit` → 既有 persistence adapter → `GET /api/v1/audit/events` 读回 + `audit_events` 列形状），真库那一格要么重建镜像、要么在容器里处置一次告警，两件都在本单明禁（容器/生产库写操作、镜像重建）之内。**现网只读旁证（pre-fix）**：`select action, outcome, resource, count(*) from audit_events where action ilike '%alert%' or resource ilike '%alert%' group by 1,2,3` → **0 rows**，而 `select id, status, assignee, assigned_by, closed_by from alerts order by id` → `1|closed|r577-027|r577-011|r577-011`、`2|acknowledged` —— 处置真发生过、账上零行，正是 R577 那一格的复现。
2. **热集性能**未量：本单每枚处置多一次 `record_audit`（纯内存 + 一笔既有 adapter 写）；没在真机量过延迟差，也没有并发下的写账顺序取证（R88 那本跨进程发号的账仍欠着）。
3. **R251 那枚钉在改口之后的形状**未验：本席不碰在册件，所以「按 resource+outcome 计数会不会把 12 格拒绝矩阵撑成两种形状」没量。
4. **前端「处置留痕」文案/接口消费**未验：`frontend/**` 越域，本单没动，也没读过它是否打算消费这三行账。
6. 执行层自报数字未经总控复跑，一律标「执行层自报」。

## 七、本纸落盘后的自证

- 三枚件 sha256 前 12（落盘后 `hashlib` 现算，`Get-FileHash` 同口径）：`app/api/v1/alerts.py` = `34017ec67a08`、
  `tests/test_r582_alert_disposal_audit_ledger.py` = `e8d7406aea0f`、本纸 = 见下一次现算（写自己的 sha 到自己身上做不到）。

- 三枚件之外零写入：`git status --porcelain` 只应列出 `M app/api/v1/alerts.py` + 两枚未跟踪新件。
- 新件形状：单形 CRLF、无 BOM、`count('\r')==count('\n')==count('\r\n')==行数`。
