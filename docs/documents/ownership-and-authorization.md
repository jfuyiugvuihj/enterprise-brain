# 文档归属与授权口径（S1）

落地切片：`docs/handoff/2026-09-14-consolidated-fix-plan.md` 的 S1，并入前端需求单 **R4**。
代码事实以分支 `codex/data-file-catalog`（基线 `5db955c`）为准；本文只写这一条链路，不描述全局架构。

## 1. 修的是什么

`record_document_version()` 的签名里没有 principal，`documents` / `document_versions` 两张表也没有 owner 列，
所以 `_document_authorization_decision()` 读到的 `owner_id` 恒为 `None`，每一次文档判定都只能落到部门交集：

- 上传者删除自己的文档 403 `permission_denied`（staff/manager 没有 `resource:delete`）；
- 无部门的管理员删除任何文档 403 `department_scope_denied`（principal_departments 为空集）。

结果是任何人都删不掉文档，删除级联、资源生命周期、TTL、备份清理都无法端到端验证。

## 2. 归属写在哪（三条，缺一不可）

| 路径 | 位置 | 写入方 |
| --- | --- | --- |
| 逻辑文档表 | `documents.owner_id / size_bytes / parse_status` | `app/api/v1/chat.py` `_upsert_document()` |
| 版本表 | `document_versions.owner_id / size_bytes / parse_status` | `app/documents/catalog.py` `record_document_version()` |
| 本地 JSON | `<存储文件同目录>/.document-versions.json` | 同上；PostgreSQL 离线时由 `record_local_document_version()` 单独写 |

- sidecar 按**存储文件所在目录**定位，不按 `DOCUMENTS_DIR`，因此把版本存到别处不会误写进活的文档根目录。
- sidecar 里额外保存 `recorded_path`：上传后的文件名是 resource id，旧的 `名称__vN` 目录扫描看不见它，
  没有这条记录，离线目录就会丢掉这一行以及它的归属。
- `record_document_version()` 先写 sidecar 再写表；两条路径的字段形状由 `_version_metadata()` 单点决定，不会漂移。
- 表里已有一行且 `owner_id` 为 NULL 时，重复登记只会被 `COALESCE` 补齐归属，不会覆盖成空。

`chunk_count` **不在本切片**：片段计数属于 S4（Wave 3）的索引发布链路，0006 迁移里刻意没有这一列，
并在 SQL 注释中写明由谁补。

## 3. 上线顺序

`migrations/0006_document_ownership.sql` 是幂等增量（`ALTER TABLE IF EXISTS ... ADD COLUMN IF NOT EXISTS` +
`CREATE INDEX IF NOT EXISTS`），风格对齐 0003/0004/0005，校验和已并入 `migrations/manifest.json`。

必须先跑迁移再放量上传：列不存在时 `current_documents()` / `list_document_versions()` 的 SELECT 会失败，
按既有策略退回本地扫描并记一条 warning；此时目录里只有带 sidecar 的行，普通员工看不到任何无主行。

离线校验（不连库）：

```powershell
python -c "import sys;sys.path.insert(0,'.');from app.db.migrations import MIGRATIONS,migration_plan;print([m.name for m in MIGRATIONS]);print([m.version for m in migration_plan({})])"
```

## 4. 判定顺序（`app/common/policy.py`）

```
principal 缺失            -> 401 authentication_required
principal 非 active       -> principal_inactive
是 owner 且动作属于所有权  -> 放行 owner_match           （先于角色门）
角色没有该动作             -> permission_denied
resource 缺失             -> permission_granted / resource_scope_missing
无主文档 + 非管理级        -> permission_denied (legacy_ownership)
密级/部门元数据缺失        -> resource_scope_missing      （管理员也不放行）
密级非法                  -> resource_scope_invalid
密级 > clearance          -> clearance_insufficient
管理员                    -> 放行 administrator_scope     （不再要求部门交集）
资源部门为空              -> resource_scope_missing
部门不相交 + 控制类动作    -> permission_denied (department_scope_mismatch)
部门不相交 + 读取类动作    -> department_scope_denied
部门相交                  -> department_scope_match
```

### 4.1 owner 覆盖全部所有权动作

`_OWNER_CONTROLLED_ACTIONS = {resource:view, resource:download, resource:delete}`，
不再只有 `ACTION_VIEW`。它排在角色门**之前**：否则没有 delete 授权的上传者永远清不掉自己的内容。

所有权**不**包含 `resource:analyze` / `resource:export` / `resource:approve`——那是角色能力，
仍由 `permissions` 与部门/密级决定；也不包含 `audit:read` / `users:manage` / `alerts:manage`，
拥有一份文档不会让任何人变成管理员。

### 4.2 管理员超级语义

`administrator` = 角色 `admin` 或持有 `users:manage`。它跳过部门交集与「资源部门为空」，
使用独立 reason_code **`administrator_scope`**，`matched_rules = ("clearance", "administrator_scope")`。

- 不复用 `department_scope_match`：越权审计里必须能看出这是管理员覆盖而不是普通命中。
- **不**跳过密级：`classification > clearance` 仍然 `clearance_insufficient`（本切片只放开部门）。
- **不**跳过元数据缺失：一张谁都没描述过的行，管理员也不该被放行。

### 4.3 跨部门为什么拆成两种答案

控制类动作（`resource:upload/export/approve/delete`）跨部门返回 `permission_denied`：调用者对该资源根本没有处置权，
把它说成「部门范围问题」正是当初把删除堵死的错标。读取类动作（view/download/analyze）仍返回
`department_scope_denied`，因为「你不能在部门范围之外读」在这里确实是最终、最准确的裁决；
数据文件工具链（`app/agents/tools.py` → `error_code=`）也依赖这个码不变。

## 5. 存量 `owner_id IS NULL` 的处置（主 thread 已定口径，照此实现）

**仅管理级可见可删，普通员工不可见，禁止默认视为公开。**

- 判定条件：资源是文档（`resource_type == "document"`）且 `owner_id` 为 NULL/空串，且调用者不是管理级 →
  `permission_denied`，`matched_rules = ("legacy_ownership",)`。
- **管理级**定义为：角色 `admin`/`manager`，或持有 `users:manage`/`alerts:manage` 任一管理权限。
  这是「具备管理权限者」的字面口径，也是 P2-8 响应卫生测试（同部门 manager 读无主文档）依赖的边界。
- 管理级放行仍要继续通过密级与部门检查（无主不等于降级放行）；只有管理员的 `administrator_scope`
  可以越过「部门为空」。因此部门也为 NULL 的老行实际只有管理员能列出，这正是清理所需的最小权限面。
- 该规则**只作用于 `resource_type == "document"`**：数据集、产物、知识图谱关系等资源的空 owner
  语义不由本切片改变（`alerts` 表的归属列属于 R1，尚未落地）。
- 目录响应为这类行带 `"ownership": "legacy"`（有主为 `"owned"`），前端据此显示「归属未确定」而不是假装是公开文档。
- 消除存量的唯一途径是把归属补齐，**不是**放宽这条规则。当前提供两条诚实路径：管理员删除重传，
  或后续实现一个显式认领操作（需要 `users:manage` 与审计），二者都未改变默认拒绝。

## 6. 解析状态（R4）

`parse_status` 取值 `pending` / `parsing` / `ready` / `failed`（迁移带 CHECK 约束）。

- `ready`：上传成功路径写入（解析 + 入库都完成之后）。
- `failed`：解析失败路径写入，**同时保留存储文件与目录行**，响应仍是 500 `document_parse_failed`。
  删掉文件会让这一行在目录里消失，用户与管理员都无从处置一次失败的上传。
- `pending`：默认值，历史行与只登记未解析的行；未知取值一律降级为 `pending` 并记 warning。
- `parsing` 常量已在 schema 与 catalog 侧就位，但当前上传是同步完成，没有跨进程中间态可写；
  接入队列（Wave 3）时才由 worker 写入，本切片不伪造。

## 7. 删除链路四段

`DELETE /api/v1/documents/{filename}`：授权 → 索引回滚 → 物理清理 → 目录与审计。

| 阶段 | 失败时 | 返回 |
| --- | --- | --- |
| 授权 | 决策已入审计 | 401 `authentication_required` / 403 reason_code |
| 向量索引回滚 `retriever.delete_document` | 不删文件、不删行 | 500 `index_publish_failed`，`details.stage = "index_rollback"`，`retryable: true` |
| 关键词索引重建 `rebuild_bm25` | 同上 | 500 `index_publish_failed`，`details.stage = "keyword_index"` |
| 物理清理 | 保留目录行（可重试） | 500 `internal_error`，`details.stage = "physical_cleanup"` |
| 目录 + sidecar | 回读校验 | `status: "ok"` 或 `"partial"` + `catalog_rows_remaining` |

任何一段失败都不会返回「删除成功」。错误体沿用 `app/agents/contracts.ErrorEnvelope`，
只用契约里已有的稳定 code（`index_publish_failed` / `internal_error`），细分原因放 `details.stage`，
不新增契约码。删除成功与否以删除后**重新读取目录**为准，而不是以调用返回值为准。

## 8. 审计

`record_audit()` 使用 S2 已落地的 keyword-only 参数：`request_id`、`resource_scope`、`policy_version`、
`before_summary`、`after_summary`。

- 每次文档授权判定记一条（`allowed` / `denied`），携带与判定完全相同的 resource scope。
- 删除链路再记一条收尾事件：`before_summary` 是删除前的版本数/密级/部门/归属，`after_summary` 带 `stage` 与剩余行数。
- `outcome` 取值：`allowed`、`denied`、`failed`（阶段没做成）、`partial`（文件清了但行还在）。
- 因此「谁在什么时候把哪份文档删了、依据的是 owner 还是管理员覆盖」可以只靠审计重放还原。

## 9. 本切片明确没做的事

- `policy_version` 仍是 `resource-policy-v2`。语义变了本该升 v3，但 `tests/test_rbac_abac.py`、
  `tests/test_audit_persistence.py`、`tests/test_security_operations.py` 都钉住了这个字符串，
  需要主 thread 一次性协调改版，不由 S1 单边改。
- `POST /upload` 现在只是**记录** principal，并未强制 `resource:upload`，也没校验上传者是否有权声明该密级/部门。
- `/api/v1/*` 中间件在无 token 时返回的 401 body 仍是中文 `请先登录`，不是契约里的 `authentication_required`；
  路由层已经返回稳定码，中间件层归主 thread。
- 没有实现「认领无主文档」的写操作，只保证了无主行不会被普通员工看到、并能被管理员删除。
- 检索实现、Chroma 地位、`chunks` 落库均属 S4；`alerts` 归属列属 R1；本切片一律未触碰。

## 10. 验收映射

| Accept | 测试 |
| --- | --- |
| A owner 删自己文档 200 | `test_owner_deletes_their_own_document_end_to_end` |
| B admin 删任意文档 200 | `test_administrator_without_a_department_deletes_any_document` |
| C 跨部门不是 department_scope_denied | `test_cross_department_delete_is_not_answered_with_a_scope_code`，`test_cross_department_control_is_a_lack_of_authority_not_a_scope_answer` |
| D 匿名 401 | `test_anonymous_document_routes_answer_authentication_required` |
| E 存量 NULL | `test_legacy_unowned_document_is_hidden_from_staff`，`test_legacy_unowned_document_is_only_deletable_by_the_management_level`，`test_unowned_documents_are_visible_only_to_the_management_level` |
| F ready / failed 行 | `test_successful_upload_records_ready_and_the_uploader`，`test_failed_upload_keeps_a_failed_row_that_can_still_be_retired` |
| G 回滚失败不声称成功 | `test_index_rollback_failure_does_not_claim_the_document_was_deleted`，`test_keyword_index_failure_also_blocks_a_success_claim`，`test_stored_file_that_cannot_be_removed_keeps_the_catalog_row` |
| 双持久化 | `test_record_document_version_writes_the_owner_to_both_paths`，`test_local_record_keeps_the_owner_when_postgres_is_offline` |
| 迁移离线断言 | `test_chunk_count_is_left_to_the_index_publication_slice` |