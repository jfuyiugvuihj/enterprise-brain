# 备份与恢复

默认备份范围包括原始文档、数据文件、Chroma、导出报告和日志目录。PostgreSQL
业务数据和 Redis 队列状态不包含在工作区 ZIP 中，生产备份必须单独导出数据库。

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
2. Chroma 可以重新加载或重建；
3. 导出报告和审计日志完整；
4. 服务重启后健康检查和权限校验正常；
5. PostgreSQL 中的用户、资源元数据、审计和任务状态可查询；
6. 每一行的 `owner_id`、部门范围与密级仍然与原库一致（权限关系随行恢复）。

## 已验证的隔离演练

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