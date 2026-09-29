# R503 · 成果回读链缺两把键 —— 取证与停手报告（2026-09-29，执行层，基点 `092fb34`）

## 0. 结论一句话

判据②要的「两把键来自**已有落盘事实**」今天不成立：`artifacts` 表里没有 `session_id`／`request_id` 这两列，
`ArtifactRegistry.register()` 也没有这两枚写点，而唯一能装额外事实的 `metadata` JSONB 在读路径上被一枚白名单
逐枚过滤。⇒ **非加列（或非改上游签名 + 白名单 + 在册钉）不可**，按工单自己的口径停手只交取证。

本单生产码零改动：`git status --short` 只交回三枚新件（本文 + 两枚测试件），`app/**` 与 `frontend/src/**` 的
在册件逐字节未动。

## 1. 判据①：三张账的字段全集（全部现取）

### 1.1 `app/api/v1/artifacts.py` 列表行的字段全集 —— 12 枚

写点 `_artifact_row()`，`app/api/v1/artifacts.py:151-165`：`record.public_payload()`（`app/storage/artifacts.py:237-244`
交回 5 枚）+ `row.update({...})`（再补 7 枚）。

| # | 字段 | 落盘出处 | 备注 |
| --- | --- | --- | --- |
| 1 | `artifact_id` | `artifacts.artifact_id` | |
| 2 | `artifact_type` | `metadata->>'artifact_type'` | 白名单内 |
| 3 | `content_url` | 由 `artifact_id` 拼（`:207-209`） | 不是列，是投递地址 |
| 4 | `download_url` | 由 `artifact_id` 拼（`:210-212`） | 同上 |
| 5 | `expires_at` | `artifacts.expires_at` | |
| 6 | `filename` | `metadata->>'filename'`，缺则取 `storage_key` 尾名 | 白名单内 |
| 7 | `owner_id` | `artifacts.owner_id` | |
| 8 | `department_ids` | `metadata->>'department_ids'` | 白名单内 |
| 9 | `classification` | `metadata->>'classification'`，缺省 `internal` | 白名单内 |
| 10 | `visibility` | `metadata->>'visibility'`，缺省 `private` | 白名单内 |
| 11 | `created_at` | `artifacts.created_at` | |
| 12 | `source_version_id` | `artifacts.source_version_id` | **今天两枚生产写点都不喂 ⇒ 恒 null**（见 1.4） |

屏上「哪一次问答／哪一次计算」要的键：**0 枚命中**（`rg -n session_id app/api/v1/artifacts.py` EXIT 1）。

### 1.2 `app/storage/artifacts.py` 落盘行的字段全集 —— 列 12 枚 + metadata 5 枚

| 组 | 清单 | 现取坐标 |
| --- | --- | --- |
| 表列全集 `ARTIFACT_COLUMNS` | `artifact_id`·`owner_id`·`resource_type`·`resource_id`·`source_version_id`·`storage_key`·`content_sha256`·`status`·`expires_at`·`deleted_at`·`created_at`·`metadata` | `app/storage/artifacts.py:63-76`；`_to_row()` 逐枚点名 `:299-321` |
| metadata 白名单 `SCOPE_METADATA_KEYS` | `artifact_type`·`filename`·`department_ids`·`classification`·`visibility` | `:81-87`；写点 `register()` 的字面量 `:554-560` |
| `register()` 的签名（能收什么） | `storage_path, artifact_type, principal, classification, visibility, source_version_id, expires_at` | `:513-523`；模块级 `register_artifact()` 同形 `:648-666` |
| 读路径的白名单过滤 | `for key in SCOPE_METADATA_KEYS:` —— **白名单外的键当场丢弃** | `_coerce_record()` `:424-430` |

⇒ 落盘里能承载 lineage 的只有两种位置：12 枚列（没有这两枚），或 `metadata`（有列，但写点不写、读点不认）。

### 1.3 `migrations/` 里两张表的列定义

| 表 | 列 | 现取坐标 |
| --- | --- | --- |
| `artifacts` | `artifact_id`·`owner_id`·`resource_type`·`resource_id`·`source_version_id`·`storage_key`·`content_sha256`·`status`·`expires_at`·`deleted_at`·`created_at`·`metadata JSONB` | `migrations/0001_core_resource_versions.sql:36-49` |
| `calculation_runs` | `calculation_run_id`·`owner_id`·`dataset_version_id`·`metric_definition_id`·**`request_id`**·**`task_id`**·`status`·`formula`·`parameters`·`result`·`error_code`·`started_at`·`completed_at`·`created_at` | `migrations/0002_execution_data_lineage.sql:52-67` |
| `agent_runs`（旁边那本已带两把键的账） | `agent_run_id`·`owner_id`·**`request_id` NOT NULL**·`trace_id`·`task_id`·**`session_id`**·`worker`·`status`·`started_at`·`completed_at`·`error_code`·`metadata` | `:89-102` |
| `audit_events`（判据②点名的「删除审计入参那条路径」） | **`request_id NOT NULL DEFAULT ''`**·`actor_username`·`owner_id`·`action`·`resource`·`resource_scope`·`outcome`·`reason_code`·`before_summary`·`after_summary`·`payload`·`created_at` | `migrations/0005_audit_events.sql:5-22` |

`artifacts` 与 `calculation_runs` 之间**没有任何外键或共享列**；`audit_events` 也没有 `session_id` 这一列。

### 1.4 「列已有、码没读」与「列也没有」必须分开写（工单点名不许混）

| 键 | 判定 | 凭据 |
| --- | --- | --- |
| `session_id` | **列也没有**（`artifacts` 无此列；`metadata` 白名单不含；无写点） | 1.2 + 1.3 表 |
| `request_id` | **列也没有**（同上）；`audit_events.request_id` 有列，但记的是**访问/删除那一发**，不是生成那一发 | `app/api/v1/artifacts.py:42-48`（view/download 审计）、`:103-113`（删除审计带 `request_id=principal.request_id`） |
| `source_version_id` | **列已有、码已读**（列表行今天就在交回），但**两枚生产写点都不喂** ⇒ 恒 null | 读点 `app/api/v1/artifacts.py:162`；写点 `app/api/v1/data.py:513-518`、`app/agents/tools.py:260-264` 两处 `register_artifact(` 的实参里都没有 `source_version_id`（`app/agents/tools.py:270` 只是在**读**它） |
| `calculation_run_id` | **列也没有**；而且 `calculation_runs` 整张表在 `app/` 里**零写点**（`rg -n calculation_run app` 命中 0）——「产物→计算」这一腿今天连生产方都没有 | 1.3 表 + 现取 rg 读数（§5 判据①行） |

## 2. 判据②：为什么「非加列不可」（四步证据链，每步都可失败）

1. **值今天不落盘**。生成一张图的那一刻，手上确实有两把键：`Principal` 带 `request_id`，LangGraph
   `configurable` 带 `session_id`／`request_id`／`task_id`（`app/trace/spans.py:44-61` 逐枚点名）。但
   `register()` 的签名不收它们（`:513-523`），`metadata` 字面量只写那五枚 scope 键（`:554-560`）。
   ⇒ 这是**写点缺口**，不是读点缺口：光改 `artifacts.py` 的读路径无键可读。
2. **走 `metadata` jsonb 绕开迁移，今天被三道门挡死**：
   - `_coerce_record()` 逐枚按白名单过滤（`:424-430`）⇒ 后门塞进去的键**静默丢**（本单钉 P4 已实测）；
   - `tests/test_r248_artifact_column_alignment.py:126` 钉 `set(row["metadata"]) == set(SCOPE_METADATA_KEYS)` ⇒ 白名单一扩容就红；
   - 同件 `:80-84` 双向钉 `dataclasses.fields(ArtifactRecord)` == `CREATE TABLE` 列集，`fields - columns` 非空即「假接入」红。
   ⇒ 想不加列必须**同时**改白名单 + 这两枚在册钉，那是改判，不是接线。
3. **拿删除审计那一发的 `request_id` 冒充 = 假绿灯**。那一枚说的是「谁在什么时候删的」，
   而 `_artifact_row(record)` 的签名压根拿不到 principal（`app/api/v1/artifacts.py:151`）。把访问号画上屏，
   同一行在不同账号眼里会长出不同的「来源」——本单钉 P2 与刀②专门盯这一条。
4. **反查 trace 日志属于工单明令禁的「自己造推断」**。`trace_events.payload`／`tool_calls.result_summary`
   里可能有那张图的 URL，但 payload 是无索引 JSONB，列表页每页要反扫整本 journal，且「事件文本里出现过这个 URL」
   ≠「这一行登记过这个键」。

⇒ 唯一干净的路 = 加列（或 §3 那套「白名单扩容 + 上游写点 + 改判在册钉」），两者都要业主批。

## 3. 提案：要批的那一单长什么样（本文不落 `migrations/`，一片都不落）

### 3.1 迁移草案（编号由总控定）

```sql
-- migrations/00XX_artifact_generation_lineage.sql
ALTER TABLE IF EXISTS artifacts
    ADD COLUMN IF NOT EXISTS session_id TEXT,
    ADD COLUMN IF NOT EXISTS request_id TEXT;

CREATE INDEX IF NOT EXISTS artifacts_request_idx ON artifacts (request_id);
```

三条硬口径：

- **两枚都可空**，且**空 = 「这台部署没有登记它是哪一次产生的」**。不许给默认值、不许回填 `created_at` 猜、
  不许用空串——空串会被前端折成「有这一格但没内容」，那是第三种假话。
- **不复用 `source_version_id`**：那一列说的是「哪一版数据集」，不是「哪一次问答」；一列两问就是把
  `dataset_version` 与 `session` 混成一套身份，与 `app/storage/artifacts.py:78-80` 那条「不许造第二套身份概念」对冲。
- **不只加 `request_id` 再去 join `agent_runs`**：`agent_runs` 只在真跑过编排时才有行，直连
  `POST /chart`／`POST /export` 的产物不经过编排 ⇒ 一大票产物 join 不到，而「join 不到」既不等于「没产生过」
  也不等于「没有问答」。自证两列比借别人一本账诚实。

### 3.2 写点（与 3.1 同一单，缺一条就又是假账）

`ArtifactRegistry.register(..., session_id: str | None = None, request_id: str | None = None)` →
进 `ArtifactRecord` → 进 `_to_row()` → 进 `ARTIFACT_COLUMNS`；**同单必须改判**
`tests/test_r248_artifact_column_alignment.py:80-84`（列集/字段集双向）、`:126` 保持不动（lineage 走真列，
不走 metadata 白名单）。两枚生产写点各自把键递进来：`app/api/v1/data.py:513-518` 用路由上的
`principal.request_id`；`app/agents/tools.py:253-274` 用 `span_identity(config)` 的 `request_id` 与会话号。

### 3.3 读点

`_artifact_row()` 交回两枚键时，**沿用 `alerts` 那一枚「缺席 ≠ 0」的规矩**：没有登记就整个键不出现，
不要回 `null` 让前端去折空串。前端判据（本单已钉的三道门，从「不许假接入」翻成「不许假缺席」）：

- 两枚键都在 → 画「来自那一次问答」+ 一条到会话的出口；
- 任意一枚缺席 → 画「这一条没有登记它是哪一次产生的」；
- 画 `0`／「—」／空串冒充 → 当场红（本件刀①②③）。

### 3.4 「产物→计算」那一腿另开单

`calculation_runs` 今天零写点。先定「谁在什么时刻落这一行、落进哪一枚 `request_id`」，再谈 `artifacts` 侧要不要
`calculation_run_id` 外键。别把它和 session/request 塞进同一单——那是一整块编排落账的活，不是两枚列。

## 4. 契约段提案（本文不动 `docs/api/contract-v1.md`，请总控搬）

现读：契约里今天只有单条投递的两枚路由（`docs/api/contract-v1.md:753-779`，`GET /artifacts/{id}/content`／
`/download`），**`GET /api/v1/artifacts` 列表路由一整段都没有**；`:781-784` 还留着那句「does not complete
source-version lineage」。所以先补今天形状，再补 lineage 差量：

```markdown
## Artifact Listing: `GET /api/v1/artifacts` (rows published today)

Page through the artifacts this caller may open, newest first. One row is
`app/api/v1/artifacts.py::_artifact_row`: `artifact_id`, `artifact_type`,
`content_url`, `download_url`, `expires_at`, `filename`, `owner_id`,
`department_ids`, `classification`, `visibility`, `created_at`,
`source_version_id`. Membership is `authorization_decision` with
`resource:view`, the same call the content route makes, so a row is listed
exactly when it can be fetched.

**No row names the generation.** There is today no `session_id`, no
`request_id`, no `calculation_run_id` on an Artifact row, and the
`artifacts` table has no such column (`migrations/0001_core_resource_versions.sql:36-49`):
「这张图是哪一次问答、哪一次计算产生的」has no durable answer on this
surface, and the UI must say so rather than draw a placeholder. The only
lineage-shaped key, `source_version_id`, is published but fed by neither
production writer (`app/api/v1/data.py:513-518`, `app/agents/tools.py:260-264`),
so it is `null` for every artifact generated today. `audit_events.request_id`
records the *accessing or deleting* call, never the generating one.
```

lineage 落地时补的差量（同段替换）：

```markdown
`session_id` and `request_id` join the row only when the registry has them.
Both are **absent, never null**, when nothing was recorded: absence means
「本机没有登记这一条是哪一次产生的」, and it is not the same answer as
`0`, as an empty string, or as 「没有问答」. A caller that can see the row can
see these two keys; they open no new authorization judgement.
```

## 5. 判据逐条对照（实测读数）

| 判据 | 结论 | 读数 |
| --- | --- | --- |
| ① 三张账 | **做到** | §1 逐枚清单；`rg -n session_id app/api/v1/artifacts.py` → EXIT 1（零命中）；`rg -n calculation_run app` → 命中 0；`rg -n "INSERT INTO (agent_runs\|tool_calls\|trace_events\|calculation_runs)" app` → EXIT 1（这几本账都走 `app/trace/store.py:839-865` 的投影写，不走裸 INSERT，本行只是把「谁在写」点名到坐标） |
| ② 接两把键 | **停手**（工单给的那条出口） | 理由 = §2 四步；未加列、未加 migration、未改上游、未造推断 |
| ③ 前端那一格 | **未做**（依赖②） | 生产码零改动；已交付「不许假接入」三道门 + 三把刀（`frontend/src/components/__tests__/r503-artifact-lineage-face.test.js`，8 passed） |
| ④ 零外部请求 | **做到** | 新增前端件 `rg -n "https?://"` → 0 命中；未新增任何位图 |
| ⑤ 色值纪律 | **零新增色值** | `frontend/src/assets/theme.css` 一字未动（尾追加 0 行）；`npx stylelint "src/**/*.{css,vue}"` → **`148 problems (0 errors, 148 warnings)`，exit 0** = 与基点同数，`--max-warnings=148` 预算未动、未换用别处；`r151-legacy-colors.test.js` 一枚字未改 |
| ⑥ 在册钉只升不降 | **做到** | 在册件零 diff：`tests/test_artifact_list.py`／`tests/test_r248_*`／`frontend/src/components/__tests__/artifact-list.test.js` 全部未改（`git status --short` 不点名它们）；只新增两枚件。同族复跑：`artifact-list.test.js` 77 passed + 本件 8 passed = **85 passed / 0 failed**；`tests/test_r503_artifact_lineage_keys.py` **9 passed** |
| ⑦ 反证刀 ≥3 | **做到（改日形态）** | 后端三把 + 前端三把，红句见 §6。刀身全在 `tests/` 与 `frontend/src/**/__tests__/`，走**内存源码影子**（`compile`+`exec` / 文本替换），盘上在册件一个字都不改（R491 同族手法，见 `tests/test_r491_counter_evidence_blades.py:1-13`） |
| ⑧ 硬不变量 | **做到** | `rg -c classification_blocked app/` → 0 命中；零新 Chroma 依赖/写点（本单不碰向量库；跑 pytest 时 conftest 的 R134 闸门交回「PersistentClient 调用 1 次，落点被改道出工作树 1 次」＝既有闸门行为，非本单新增写点）；零新错误码 |

## 6. 三把刀的红句原文

后端（`tests/test_r503_artifact_lineage_keys.py`，对照 = 真模块三枚探针全绿）：

```text
K1-RED: 列表行丢了字段，屏上再也说不出这一条的来源：['source_version_id']
K2-ROW-KEYS: [..., 'request_id', ...]（13 枚，多出的一枚就是假接入）
K2-RED: 列表行回显了表里不存在的生成键：['request_id']；artifacts 无此列、register() 无此写点，这就是拿访问者那一发冒充「哪一次问答」
K3-METADATA-KEYS: ['artifact_type','classification','department_ids','filename','request_id','session_id','visibility']
K3-RED: 白名单外的 metadata 键读回来了：['request_id','session_id']
```

前端（`r503-artifact-lineage-face.test.js`，`CONTROL: 真源码全绿`）：

```text
K1-RED: 那一格时间位里出现了冒充来源的残字："— 本次会话"
K2-RED: 视图模型字段全集漂了：["artifactId","contentUrl","createdAt","downloadUrl","expiryText","filename","sourceText","typeLabel","typeRaw"]
K3-RED: 没有落盘来源的生成键或会话出口进了组件代码
```

## 7. 没做到（明写，不许读成已收）

- **判据②/③没做**：两把键没接到列表行、前端没画、没做「点得回那一次问答」。不是偷懒——是 §2 那条链：
  加列要批，改上游写点要批，改 R248 那两枚在册钉要批。本单一行生产码都没动，就是为了不给总控添一笔来路不明的并树。
- **判据⑦按字面少一把**：「把两把键之一从列表行摘掉 ⇒ 必红」今天无物可摘（键不在行上），跑的是它的同族
  K1（摘掉行上今天真在的那枚来源形字段）。键一旦落地，这一把要在同一枚钉上补回真身。
- **判据③要的「拼到既有会话出口」今天拼不出**：`GET /sessions/{id}` 那一侧的契约在读（`docs/api/contract-v1.md:1996`
  按 owner 过滤），但产物行里没有会话号可拼，硬拼就是刀③那根假链接。§3.3 已把两枚键的落地口径写好。
- **`calculation_runs` 那半条链没碰**：见 §3.4，它欠的是生产方，不是列。

## 8. 卫生与不变量（本单实际执行过的）

- 未 commit／未 push／未建分支（`git rev-parse --abbrev-ref HEAD` = `HEAD`，detached @`092fb34`）；
- 未 `npm install`／`npm ci`／未碰 `node_modules`（Junction 原样）；未起 dev server／未 build／未碰 docker／未打模型／未连库写；
- 未跑全量门（同窗有别的 Agent，明令）；只点名跑了 1 枚 pytest 新件与 2 枚 vitest 件；
- 工作树写域之外零写入：`git status --short` 只点名本文 + 两枚新测试件（清单见总控侧复跑）。