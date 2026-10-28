# 企业智脑客户交付指南

本指南从仓库根目录执行。交付工具不会下载资产、启动主控服务或读取客户资料。

## 1. 准备

1. 核对固定版本：`git rev-parse HEAD` 应与交付记录一致。
2. 从 `deploy/.env.server.example` 复制出**仓库外保管秘密值**的
   `deploy/.env.server`，设置首次管理员、PostgreSQL、Redis、CORS、嵌入模型和维度。
3. 准备目标平台为 `linux/amd64` 的离线镜像、Ollama 模型归档和 OCR 资产。
4. 机器需安装 Docker Engine/Compose，并已启动 daemon；本次交付不自动安装这些组件。

## 2. 只读预检

```bash
python scripts/check_host_readiness.py \
  --env-file deploy/.env.server \
  --install-path /opt/enterprise-brain \
  --port 80 --port 8001 \
  --asset-manifest /secure-delivery/assets.json \
  --verify-hashes \
  --json
```

退出码：`0` 全部通过，`1` 含警告或未知项，`2` 明确失败，`64` 调用参数错误。
`unknown` 不是通过。相对资产路径以清单文件目录为基准。输出不包含配置值。

## 3. 交付包

```bash
python scripts/delivery/bundle.py plan \
  --manifest /secure-delivery/assets.json --output /delivery/out

python scripts/delivery/bundle.py apply \
  --manifest /secure-delivery/assets.json --output /delivery/out \
  --verify-hashes --confirm bundle:/delivery/out
```

`apply` 只接受空目标目录。用 `docker save` 导出清单中的镜像，文件资产复制到
`files/`，并写入不含秘密的 `bundle-manifest.json`。不得把 `.env`、密钥、源数据库或
客户数据放进清单。清单完整不代表现场安装成功。

## 4. 隔离安装

先看计划，再执行：

```bash
python scripts/delivery/orchestrate.py plan \
  --project eb-customer --env-file deploy/.env.server \
  --install-path /opt/enterprise-brain --frontend-port 18080 --backend-port 18081 \
  --backend-image enterprise-brain:local \
  --frontend-image enterprise-brain-frontend:local

python scripts/delivery/orchestrate.py apply \
  --project eb-customer --env-file deploy/.env.server \
  --install-path /opt/enterprise-brain --frontend-port 18080 --backend-port 18081 \
  --backend-image enterprise-brain:local \
  --frontend-image enterprise-brain-frontend:local \
  --images-archive /delivery/out/images.tar --confirm eb-customer:apply
```

安装器使用根 `docker-compose.yml` 加
`deploy/delivery/compose.override.yml`，不会复制第二套服务拓扑。不同项目名不等于硬件
隔离；执行前必须确认独立目标不会与主控站点竞争 CPU、GPU、磁盘或模型。

## 5. 升级、重启、回滚

升级前先完成第 7 节备份。然后：

```bash
python scripts/delivery/orchestrate.py upgrade \
  --project eb-customer --env-file deploy/.env.server \
  --install-path /opt/enterprise-brain --frontend-port 18080 --backend-port 18081 \
  --backend-image enterprise-brain:<new> \
  --frontend-image enterprise-brain-frontend:<new> \
  --backup-manifest /secure-evidence/customer-r1/recovery-manifest.json \
  --confirm eb-customer:upgrade
```

镜像回滚只撤运行镜像，不逆转数据库迁移：

```bash
python scripts/delivery/orchestrate.py rollback \
  --project eb-customer --env-file deploy/.env.server \
  --install-path /opt/enterprise-brain --frontend-port 18080 --backend-port 18081 \
  --backend-image enterprise-brain:<previous> \
  --frontend-image enterprise-brain-frontend:<previous> \
  --confirm eb-customer:rollback
```

新旧 schema 不兼容时必须从隔离恢复点恢复数据库和文件，不能把切回镜像称为完整回滚。

## 6. 备份与隔离恢复

```bash
python scripts/delivery/recovery.py plan --project eb-customer \
  --backup-dir /secure-evidence/customer-r1
python scripts/delivery/recovery.py backup \
  --project eb-customer --env-file deploy/.env.server \
  --frontend-port 18080 --backend-port 18081 \
  --directory /secure-evidence/customer-r1 \
  --confirm eb-customer:backup
```

恢复必须在不同目录、数据库和 Compose 项目中进行；`TARGET_DATABASE_URL` 只从受保护环境
提供。Redis 队列字节不作为恢复点，恢复后先隔离待处理任务，再与 PostgreSQL 任务、
检查点和审计对账，禁止误重放已完成或已取消动作。

恢复后核对原文件哈希、当前授权、会话、计算记录和历史 PDF 字节。该流程尚未在独立客户目标
执行时，不得报告安装或恢复通过。

## 7. 诊断

```bash
python scripts/delivery/diagnose.py --project eb-customer \
  --env-file deploy/.env.server --output /secure-evidence/diagnostic.json
```

诊断只输出版本、平台、服务状态和有限错误摘要，不输出环境值、凭据、问题正文、日志原文或
完整容器配置。`unknown` 表示该项不可读。

## 8. 72 小时观察

```bash
python scripts/delivery/longrun.py --state-file /secure-evidence/longrun.json start \
  --project eb-customer --health-url http://127.0.0.1:18080/api/v1/health \
  --version <frozen-version> --hardware <target-hardware> --load <declared-load>

python scripts/delivery/longrun.py --state-file /secure-evidence/longrun.json status
```

`start` 会启动独立本地进程。进程中断后，`status` 报 `interrupted`；只有确认目标恢复后
才执行 `resume`，它会开启新的连续 72 小时窗口并保留中断记录。新会话恢复同一状态文件时
不会重跑已经记录的历史检查。只有连续 72 小时且逐次业务检查成功才记 `passed`。

## 9. 尚未验证的边界

- 本仓库缺少明确指定的独立安装目标时，真实安装、升级、恢复和 72 小时均为“未验”。
- 过去 4 GB VM 借用 Windows GPU 的演练不是 4 GB 全合一部署。
- 真实手机、企业 SSO、真实人员试用、客户真实材料和生产规模不因本指南完成。
