# 备份与恢复

工作区 ZIP 默认备份原始文档、经营数据、`static`（图表与导出报告）和日志，具体目录以 `app/common/backup.py::DEFAULT_BACKUP_DIRS` 为准。PostgreSQL 业务数据与 PGVector 向量不在这个 ZIP 内，必须另做数据库备份；Redis 队列也不在 ZIP 内。新版备份保留文件修改时间；输出 ZIP 位于备份目录内时，不把该 ZIP 自身重复打包。旧 ZIP 不含修改时间字段时仍可恢复内容，但不能精确还原原修改时间。

PGVector 是当前唯一现役向量库。恢复准备应同时保留工作区文件、PostgreSQL 归档、部署配置与所需本地模型；配置和凭据按企业的保管规则单独保护，不放进公开代码包。旧 Chroma 迁移材料只供历史追溯，不作为现役恢复步骤。

库级恢复演练入口为 `scripts/r575_vector_restore_drill.py`；涉及库级设置时，应成对保存 `.globals.json`／`.globals.sql`，并在恢复校验前重新施加。向量表和数据是否完整，应核对数据库归档目录、恢复后的行数及检索结果。能生成 ZIP、能列出归档目录或单项测试通过，都不能代替完整备份恢复验收；本轮完整目标机恢复仍待实机验证。

```powershell
python scripts/backup_workspace.py --output backups/enterprise-brain.zip
python scripts/restore_workspace.py backups/enterprise-brain.zip --destination restore-check
```

备份包包含 `manifest.json`，恢复时会校验每个文件的 SHA-256。路径穿越条目会被拒绝。

容器内使用同一组脚本，凭据只来自环境变量：

```bash
docker compose run --rm backend python scripts/backup_workspace.py --output /app/data/backups/workspace.zip
```

## 数据库恢复

### PostgreSQL

在服务器上使用与 Compose 相同的环境变量生成 dump；不要把密码写进命令或脚本：

```bash
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc \
  > backups/enterprise-brain.dump
```

项目自带的封装会从 `DATABASE_URL` 解析主机、端口、用户与口令，只把它们放进子进程环境，
`pg_dump` / `pg_restore` 的命令行与输出里都不会出现凭据：

```bash
python scripts/backup_database.py --output backups/enterprise-brain.dump
python scripts/restore_database.py backups/enterprise-brain.dump --list
python scripts/restore_database.py backups/enterprise-brain.dump
```

`--list` 只读取归档目录（TOC），用于在真正恢复前确认归档可用、包含哪些表。

恢复顺序是先恢复工作区文件，再启动 PostgreSQL，最后将 dump 导入空库：

```bash
docker compose up -d postgres
python scripts/restore_database.py backups/enterprise-brain.dump --database-url "$RESTORE_DATABASE_URL"
docker compose up -d
```

`pg_restore` 会修改数据库，只应对隔离的恢复环境执行。生产环境应另外定期生成
PostgreSQL dump，并将 dump 放入受控备份目录。恢复演练至少验证：

1. 文档和数据文件可以读取；
2. PGVector 表、向量维度及同一权限范围内的检索结果正确；
3. 导出报告和审计日志完整；
4. 服务重启后健康检查和权限校验正常；
5. PostgreSQL 中的用户、资源元数据、审计和任务状态可查询；
6. 每一行的 `owner_id`、部门范围与密级仍然与原库一致（权限关系随行恢复）。

## 隔离演练与验证范围

2026-10-27 在一次性 PostgreSQL 16 + PGVector 容器中完成真实归档、恢复到兄弟库及恢复后核对，来源和恢复库均与应用库隔离。具名检查覆盖迁移、权限字段、向量内容、维度、最近邻和约束；日志在 `output/enterprise-readiness-20261025/backup-isolated-pg-final.log`。这一组只覆盖数据库；联合恢复的范围见下段，新机器安装与72小时运行仍未验。

同日另将隔离验收站的文件 ZIP、数据库归档及成对库级设置恢复到独立临时服务，110个文件校验和一致、9份登记图表存在；账号登录、资料列表（含修改时间）、原会话、计算记录及原PDF字节核对通过，1440px／377px浏览器登录和原PDF预览通过。部署配置由受保护环境提供，模型地址断开、没有启动任务执行器。证据为上述产物目录内 `restore-files-pg-proof.json` 与 `restore-browser.log`。临时服务已移除；仅证明本机隔离环境的联合恢复，不证明异机安装、真实手机、模型恢复运行、排队中任务恢复或72小时运行。

`tests/test_postgres_backup_recovery.py` 在隔离集群上真实执行了以下链路，只有显式导出
`EB_PG_ACCEPTANCE_URL` 与 `EB_PG_BIN_DIR` 才会运行，避免误碰生产库：

1. 在验收库写入数据集、AgentRun 与带 `vector` 向量的分块；
2. `scripts/backup_database.py` 生成 custom 格式 dump；
3. `scripts/restore_database.py --list` 校验归档目录；
4. 恢复进同集群的 `*_restore` 兄弟库，绝不覆盖来源库；
5. 比对迁移台账校验和、行数、`vector` 扩展、`<=>` 最近邻结果、
   `owner_id`/密级/部门数组，以及外键约束仍然存在；
6. 删除兄弟库并清理验收行。

日常回归不会连接任何外部服务，这些用例报告为跳过而不是通过。

JWT 轮换：

```powershell
python -c "from app.common.secret_rotation import rotate_jwt_secret; rotate_jwt_secret('.env')"
```

轮换后必须重启服务，使新密钥生效；旧令牌将失效。
