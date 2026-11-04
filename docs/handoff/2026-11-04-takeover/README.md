# 企业智脑：剩余业务与交付工作交接

2026-11-04，业主要求将本会话剩余任务交给协作者。本目录是接手入口；执行状态仍统一写入 [docs/backlog.md](../../backlog.md)，不另建平行待办。可直接转发 [协作者提示词](prompt.md)；工作顺序见 [剩余任务](remaining.md)。

## 先认清三个版本

仓库：<https://github.com/jfuyiugvuihj/enterprise-brain>。

| 用途 | 分支／精确代码提交 | 含义 |
| --- | --- | --- |
| 本轮主线 | `codex/data-file-catalog`；交接前产品 HEAD `3537a472` | 包含截至10-30已做过具名真模型／浏览器／产物验收的业务修复；本次追加文档提交，不修改产品码。不是全平台合格声明。 |
| 取消边界候选 | `codex/metric-execution-oct28`；`7875c7b206ced94fbd1edfb1a87144bd5dc49d79` | 以3537a472为父提交，仅新增生成文件清理修复及回归用例。组件验证通过，真实浏览器验收超时、回滚未演练，**不能直接认定完成或直接上线**。 |
| 原交付包基线 | `910d7a13f93740aed66b0359c6a10f746dcea399` | 10-28交付工作包的固定基线。已有交付成果和长跑不因本次接手作废；不能直接用其结果证明新组合版本合格。 |

接手先 fetch 并核对提交关系：`git show --stat 3537a472`、`git show --stat 7875c7b2`、`git merge-base --is-ancestor 3537a472 7875c7b2`。主线交接文档提交和候选补丁不是祖孙关系中的同一最新HEAD；请从主线创建新的 `codex/` 分支，审查候选后再决定 cherry-pick，切勿 reset 现有协作者成果。不要按提交日期或模型自称成功判断可交付状态。

## 分工如何变化

本次新增授权是接续本会话负责的1—4项业务、5项业务回归与后续7项研究/必要改进，**不再受旧提示词“协作者不能改app/frontend”的限制**。原10-28提示词中关于第6项交付的具体要求继续有效，旧分工表由本次接手安排替代。主控暂停这些开发，不会同时改同一写集。

这里的编号沿用原七项：1关键阻塞、2可信分析、3重复工作与核查闭环、4质量与使用覆盖、5稳定性与回归、6交付产品化、7持续接入与复杂解析。`remaining.md`的六节是此次接手执行顺序，不是对原七项重新编号；第3项已有版本复算与告警基础，按backlog中的实际缺口继续，不新造平行系统。

若你已有 `codex/customer-delivery` 或 `codex/delivery-preflight` 成果，先保留并列明实际HEAD、脏文件、在跑窗口。交付分支继续冻结原基线完成既定演练；业务使用另一工作树。集成时逐文件审查冲突，另外核验组合版本。不得为了“最新版”打断已有72小时窗口，或把两个版本的验证拼成一个版本的验收。

## 已完成的具名行为：不需要全部重跑

| 行为 | 代码／历史证据 | 不能外推的范围 |
| --- | --- | --- |
| 已核对指标实际参与计算、追问和导出；新统计不沿用旧报告正文 | `57ccbee`、`720e7a1`；10-28指标执行验收 | 不代表通用公式、跨表计算。 |
| 新版按原指标复算；变更／停用／字段单位不一致时拒绝 | `ca987c2`；10-29具名浏览器、PDF和回滚 | 不支持自动识别字段名未变但业务单位偷换。 |
| 四人排队，正确计算并恢复历史，私有计算跨账号拒绝 | `e0853365`；四个合成经理35／350／3500／35000，三人可见排队 | 不是更大容量、长时负载或C18全量结论。 |
| 明确单列聚合不被模型改错；两题含图报告按题计算和配图 | `b061767c`、`3537a472`；1月中位数乘3为1350／450，2月分组均值750／350；合并2页，分题各1页 | 单月或完整日区间、精确实际列名、受限聚合语法；不是任意派生公式。 |
| 上述PDF实际确认、逐页检查、1440／377px预览及下载字节核对 | 10-30多问题报告证据；实际撤回重建能复现旧问题、恢复正确，六份既有PDF字节保持 | 窄屏不是荣耀／微信／iOS实机。 |
| 真模型运行中停用／取消；执行器崩溃重试与VM任务处理中断电恢复 | backlog的10-28限定结果；含真实本地模型、Redis、PG及产物 | 不代表工具内部每个同步边界、GPU宿主机断电或72小时稳定性。 |

账号恢复、停用恢复、资料版本更新、告警固定／跟随版本、普通多问题／份数澄清已有实现及限定验收，不重新列成待开发。不使用旧V1/V2数字证明今天整体质量；本次没有重跑全仓或更新整体分母。

## 本机状态与恢复入口

以下是11-04只读核对，**Docker Desktop Linux daemon当前不可达**；没有为交接启动服务、模型或VM。端口能否登录未重新确认。不要把下面上次镜像记录当作当前运行自证。

| 项目 | 位置／最后已知状态 |
| --- | --- |
| 主工作区 | `C:\Users\fengx\PycharmProjects\企业智脑`，`codex/data-file-catalog`。含未知脏文件／未跟踪目录，不能 add -A、reset、clean或删目录。 |
| 候选代码树 | `C:\Users\fengx\.codex\worktrees\metric-execution-oct28\企业智脑`，11-04核对HEAD为7875c7b2，工作树干净。 |
| 主站 | `http://127.0.0.1`；最后验收镜像 `mixed-report-20261030c`，产品源3537a472。Compose工作目录 `C:\Users\fengx\PycharmProjects\企业智脑-deploy-20261024`。 |
| 隔离验收站 | `http://127.0.0.1:18080`；Compose工作树 `C:\Users\fengx\.codex\worktrees\partner-stage-0-3-review\企业智脑`，根Compose加 `output/review-compose.yml`。 |
| 验收站最后在用镜像 | `cancel-output-probe-20261030a`，含7875c7b2及**仅用于验收的sitecustomize暂停探针**。主站未部署此候选。恢复时核对实际容器和override，不把探针镜像投入正式使用。 |
| 无探针候选镜像 | `enterprise-brain:cancel-output-20261030a` 及同后缀前端；镜像是否仍存在须接手实查。不能仅凭tag判断源码。 |
| 本机Python | 主树 `.venv\Scripts\python.exe`；Node最后使用 `D:\node.exe`。其它机器按项目依赖安装，不照抄此路径。 |

先核对服务/队列/用户GPU负载，再选择安全窗口。未经业主确认不终止其它程序、训练或游戏，不重启PG/Redis/Ollama，不动VM/Cloudisk。根AGENTS中的 `ssh vm` 不是对共享环境的新增演练授权。

## 上次中断：必须从这里接续

原问题：真实PNG／PDF渲染完成后取消或改部门，登记被拒绝，但各留下一份未登记文件。修复7875c7b2只清理本次新生成且未登记的文件；登记后审计失败必须保留已登记文件，登记库不可读时不盲删。

定点真实渲染＋隔离PG组件组在dirty/clean两态通过。**最后浏览器结果不是通过**：`report-cancel` 的报告已真实渲染，服务端取消返回200及 `cancelled:true`，之后 `page.waitForFunction` 等待输入框可用超时30秒；日志尚未走到文件存在检查、无新增成果检查及下一问。不能把它说成“仅脚本问题”，也不能断言产品已卡死，须读会话/确认状态并定位。`chart-department`尚未执行，候选真实撤回演练、主站更新、独立审查均未完成。

验收脚本有“已提交不重发”的journal保护，禁止删journal后重跑同一副作用请求。先检查原会话及实际成果/文件，写一个只读恢复检查或续接步骤，再决定是否需要新的测试会话。原暂停控制文件 `/app/data/.qa-sync-boundary.json` 的清理步骤在脚本finally中，但中断后的实际存在性仍须查证。验收完移除探针和控制文件，切回无探针镜像并核对源码。

## 证据位置和可公开边界

本机根目录 `output/multichart-live-20261029/`：

- `boundary-before.json`：四组合原始孤儿文件复现；`cleanup-dirty.log`、`cleanup-clean.log`：定点组件结果；`cleanup-audit-red.log`：已登记文件被误删的反例，后来修复。
- `boundary-browser/report-cancel.json`、`report-cancel-approval.sse`、截图：最后超时现场；`sync-boundary-browser.cjs`、`probe_control.py`、`sitecustomize.py`：验收控制器，不是产品功能或发布依赖。
- `final/` 与 `layout-fixed/`：最终PDF、逐页图片、预览下载记录；`rollback.json`：前两笔代码的真实撤回；`checkpoint-inventory.md`：后续同步边界只读盘点。
- `runtime.py`、`probe_runtime.py`：本机路径绑定的构建部署脚本，先读再用；不要在新机器直接运行。

其它历史证据：`output/metric-reuse-20261029/`、`output/concurrency-20261029/`、`output/enterprise-readiness-20261025/`、`output/c18-local-runs/`。这些目录不会随git clone提供；没有原证据的协作者应明确“按历史记录，未独立复验”，针对新改动在自己机器验收，不捏造旧截图或复制全仓测试。

前期五个调研题的本机材料在 `output/enterprise-deep-research-20261028/`：`adoption.md`、`trust-sources.md`、`delivery.md`、`connectors.md`、`complex-documents.md`，综合为 `report.md`。它们未包含在本次公开快照中；其它机器不得假称已读到或已实现其中建议。第7项需用当前代码和业务范围重新核对后提案，不因此阻塞当前缺陷收尾。

合成夹具凭据仅在本机私有目录 `C:\Users\fengx\.codex\artifacts\enterprise-brain-multichart-20261029-private\state.json`。不复制进文档、提示词、终端输出或GitHub。原合成账号、资料和历史报告暂留供续验；验收后只清理此批活跃测试资源，保留审计/计算/版本历史，不泛删业务资料。新机器自行创建受控合成账号与资料。

此次公开交接只上传代码、定点测试和脱敏说明，不上传output、数据库、PDF/截图、日志原文、.env或凭据。详细执行与完成判据见 [剩余任务](remaining.md)。
