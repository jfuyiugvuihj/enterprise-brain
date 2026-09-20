# R36 判据③ 前置：真机 105 题跑分 runbook

> 采集时点：2026-09-17 17:17 +08:00（`Get-Date` 实取）。工作树 `C:\Users\fengx\PycharmProjects\perf-lab`，分支 `codex/perf-lab`，HEAD `6ee2f79`，`git status --porcelain -uall` 开工时 0 行。
> 本文自指一律用「§N = 第 N 节」。派工判据映射：1)→§3、2)→§4、3)→§5、4)→§6、5)→§7+§8、6)→§9、7)→§2、8)→§11。
> 本文只写文档，不改代码。所有行号引用均在本文撰写时点从源码复核；性能/规模数字一律带 `[实测]/[算术]/[推算]/[外部基准]` 标注。

## 1. 结论

- **能跑了**：采集器 `scripts/collect_evaluation_answers.py` 已具备仓内缺失的答案采集链路，真机跑分只差一个 transport 适配器（§3 给了可编译骨架）+ 一次串行执行（§7）。
- **三条硬红线**：① 跑分窗口内不得有任何并行的 Ollama 计时/其他 agent 打模型（§9）；② `RETRIEVAL_TIER=fast` 在 30 题对比跑完前禁入验收与演示，真基线必须跑在 `full`（§2 前置检查 P-4）；③ 每题必须带独立 `session_id`，否则 `/ask` 的全局答案缓存会直接返回旧答案、一次模型都不打（`app/api/v1/chat.py:998`、`:1002-1016`）——那量出来的 P95 是缓存，不是 Ollama。
- **自证假基线的量级**：拿 `--dry-run` 桩（直接抄金标）评分 = **104/105 = correctness 0.9905 / evidence_coverage 1.0000** `[实测]` 2026-09-17 18:21:21 +08:00（同一形状在 16:25:42 也复现过一次），机理 `app/quality/eval.py:63-66`。§10 给 5 条机械拦截，其中 4 条不需要人读报告就能判死。
- **正式落盘物是报告，不是 answers**：answers 落仓外（`--output` 指 `$env:TEMP` 或用采集器默认，默认本身就在 `tempfile.gettempdir()`，`scripts/collect_evaluation_answers.py:45`），报告落 `docs/testing/evaluation-report.json`（与 `scripts/run_quality_evaluation.py:17` 既有默认一致）。
- **`--dry-run` 已经打不到正式路径**：必须 `--allow-sample` + 显式 `--output` 双开关才写，且永远写不到 `DEFAULT_OUTPUT`（`scripts/collect_evaluation_answers.py:302-313`）。
- **先证明容器里就是那棵树**：P-1 只保证工作树干净，不保证被测镜像同源。已实测到的现状是后端镜像比被测 commit 早约 20 h、容器内代码缺 R41/R54/R26b（见 §2 P-8），照现状开跑量到的是旧产品。
- **题数是 105，不是 100**：`tests/fixtures/business_evaluation_100.jsonl` 实测 105 行（文件名是历史名）；`business_evaluation_30.jsonl` 30 行。
- **单题超时上限 300 s，nginx 读超时 900 s** `[实测]` 源码值：`app/api/v1/chat.py:1033`（`CHAT_REQUEST_TIMEOUT` 默认 300）、`deploy/nginx.conf:63`（`proxy_read_timeout 900s`）。整轮 `[推算]` 105 × 41.6 s ≈ 73 min 串行（41.581 s 是旧 trace 历史 `[实测]` 值，见 §11 口径表，本轮未重测）。

## 2. 开工前置检查（一条不过就别开跑）

| # | 检查 | 命令 | 通过条件 |
|---|---|---|---|
| P-1 | 树与 HEAD | `git rev-parse --short HEAD`; `git status --porcelain -uall` | HEAD 是业主认可的被测版本；跑分树必须 CLEAN（脏项会改变被测量） |
| P-2 | 解释器 | `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -c "import sys;print(sys.version.split()[0], sys.executable)"` | 必须是这个 venv。系统 `python` 是 anaconda 且**无 chromadb**，用它跑出的失败是**假失败** |
| P-3 | 题数 | 跑 §11.1 的计数命令，两个 fixture 各自出数 | 105 行；跑分脚本 `--fixture` 必须显式指 `tests/fixtures/business_evaluation_100.jsonl`（`scripts/run_quality_evaluation.py:14` 的默认仍是 30 题集） |
| P-4 | 检索档位 | `docker exec enterprise-brain-backend-1 printenv RETRIEVAL_TIER`；宿主跑法看 `$env:RETRIEVAL_TIER`；**再加** `Select-String -Path deploy/.env.server -Pattern 'RETRIEVAL_TIER'` | 输出为空或 `full` 才算过。**`fast` 未过 30 题对比前禁入验收/演示**（闸门原文 `docs/handoff/2026-09-15-backend-followup-requests.md:625`；档位实现 `app/rag/retrieval_pipeline.py:49`）。不通过 ⇒ 整轮分数作废，不得落基线。🔴 **R94 复核 R93 §4.5：原写法的文件与行号都不成立（属实，2026-09-19 在 `9626b7d` 上实测）**——容器读的是 `deploy/.env.server`（`docker-compose.yml:16-17` 的 `env_file`），`.env.example` 它**根本不读**；那行 `RETRIEVAL_TIER=full` 的行号也漂过两次：`6ee2f79` 上确实是 `:54`、`b4d2026` 上是 `:91`、`9626b7d` 上是 `:110`。更要紧的是 `deploy/.env.server.example` **压根没有 `RETRIEVAL_TIER` 这一行**（实测 0 命中；同文件 `MODEL_MAX_CONCURRENCY=1` 在 `:37`）⇒ 现网恒为代码默认 `full`，本条**恒过**；但照旧写法去核 `.env.example` 等于核了一个容器不读的文件，核到的 `full` 不作数。真要堵"有人往部署 env 里塞 `fast`"，用上面新加的 `Select-String deploy/.env.server`：**无输出 = 没人设过**。🔴 **本轮跑分口径一并写死（总控 09-19 要求）**：检索`**读腿只有一条 = Chroma**`——`RETRIEVAL_TIER` 管的是**查询改写档位**（`fast` / `adaptive` / `full`），**不是**「Chroma vs pgvector」的开关，两回事别混（R93 §4.1）。唯一语义读在 `app/rag/retriever.py:992`（`collection.query`），索引后端是**字面量** `INDEX_BACKEND = "chroma"`（`app/rag/indexing.py:33`，不是 env）；pgvector 只是 `VECTOR_DUAL_WRITE`（`app/rag/pg_store.py:61`，**默认关**，且 `.env.example` / `deploy/.env.server.example` / `docker-compose*.yml` 里一处都没设）背后的**只写镜像**，`app/rag/pg_store.py:12` 原话 "Chroma stays the read path until R59" ⇒ PG 库里 `chunk_vectors = 0` **不影响**本轮基线。反向更要紧：`search_for_principal` 的 **5 个调用点全不传 `tier=`**（`app/agents/tools.py:425`、`app/agents/orchestrator.py:669`、`app/approval/assistant.py:234`、`app/mcp_server.py:48`、`app/rag/debug.py:40`，全链唯一的 `tier=` 实参是 `app/rag/retrieval_pipeline.py:676` 的自透传）⇒ 现网档位只由进程环境决定，没有请求级后门；而谁哪天把读腿切到 pgvector，本轮基线**立刻整体作废**（0 命中 ⇒ 全量拒答，不是掉几个点），那种作废长得像"出处全空、`retrieval_reason` 全 `empty`"，靠 P-13 / P-16 当场认出来 |
| P-5 | 模型并发 | `docker exec enterprise-brain-backend-1 printenv MODEL_MAX_CONCURRENCY` | `1`（`docker-compose.yml:141` 默认，`app/common/model_budget.py:53`、`:101` 实现）。不为 1 ⇒ 计时红线破防，整轮作废 |
| P-6 | 计时窗口独占 | 与其它 agent/对话约定：本窗口内禁止任何并行打模型的行为，包括 perf_probe、看板复测、演示点击 | 窗口内只有这一条链路在跑（`docs/handoff/2026-09-15-backend-followup-requests.md:487`：端到端计时期间禁止 `up/down/restart`） |
| P-7 | 结构预检（零模型） | §7 步骤 A 的 dry-run | 采集器 exit 0、产物在仓外、`collected=105 of 105` ⇒ 环境可用，再去打真机 |
| P-8 | **被测镜像同源**（容器内跑法是硬闸） | 标记级（主判据）：`docker exec enterprise-brain-backend-1 python -c 's=open("/app/app/api/v1/chat.py",encoding="utf-8").read(); print(s.count("_authorized_source_rows"))'`；树内同符号计数：`(Select-String -Path app/api/v1/chat.py -Pattern '_authorized_source_rows' -AllMatches | ForEach-Object { $_.Matches.Count } | Measure-Object -Sum).Sum`。时间级（辅判据）：`docker image inspect enterprise-brain:local --format '{{.Created}}'` 对比 `git log -1 --format=%cI <被测 rev>` | 标记级**必须相等**（本树现值 `2` `[实测]` 2026-09-17 18:21:21 +08:00），不等即判死；时间级要求镜像 `Created` **晚于**被测 commit 的 committer date——注意 `Created` 是 **UTC**（带纳秒），北京时间 = UTC+8，先换算再比，别让人自己猜。反例即本次实测：镜像 `2026-09-16T12:59:16Z` = 北京 `09-16 20:59:16`，被测 `6ee2f79` committer `2026-09-17T16:54:20+08:00`，早约 20 h；容器内 `chat.py` 2294 行 / 标记 `0` 次，树内 2383 行 / `2` 次 ⇒ 不含 R41（16:37）/R54（16:40）/R26b（16:54） |
| P-9 | **语料在位**（09-18 22:0x 那轮废跑的根因，本班补） | `GET /api/v1/documents?page=1&page_size=500`（Bearer + `trust_env=False`）数 `documents[]` 条数，并确认 `制度与口径登记表.txt` 在列 | 篇数 == 预期 **100**（99 篇参考集 + R66 `9f2f869` 强制入库的登记表；`data/报销明细表.csv` 另计），**缺一即停**：语料不在位跑出来的准确率、证据覆盖率、无出处题数**全部作废**。🔴 删除/对账**禁止**拿宿主 `chroma_db` 快照当真相源——那份快照早于 R66，照它删就会删掉真实语料（第二十班前一班就是这么误删的，见看板 §4AZ.3） |
| **P-10** | **数据文件在位**（R93 §5 补；P-9 只管 `documents/`，管不到 `data/`，而 C 桶 5 条全在它身上） | `docker exec enterprise-brain-backend-1 ls -l /app/data`；先按 §4 取 token 存进 `$env:EVAL_TOKEN`，再 `curl.exe -sS --noproxy '*' -H "Authorization: Bearer $env:EVAL_TOKEN" "http://127.0.0.1:8001/api/v1/data-files"` | 上面两处都**必须出现 `报销明细表.csv`**（注册表口径 `app/api/v1/data.py:121`，目录取 `DATA_DIR` 见 `:35`）。🔴 **机理得写死给业主**：`.dockerignore:11` 排 `data`、`:12` 排 `documents`，`docker-compose.yml:40-41` 又用命名卷 `documents:/app/documents`、`appdata:/app/data` 盖住 ⇒ **重建镜像既不会把明细表带进容器，也不会把语料带进来**（同一块持久卷：也**不会清空**已有的，所以每次重建后这两件上传都得重跑，见 P-12）；`app/api/v1/alerts.py:232` 还明写无可用租户 DATA_DIR 时**不回落仓库 `data/`**。不成立 ⇒ **C 桶 5 条（data-07 / data-08 / data-12 / insight-05 / insight-06）全灭**，等于把 R66 的成果从本轮跑分里抹掉，还要再烧一整轮（≥73 min 独占 GPU）才发现。**这是 P-1..P-9 唯一没盖住、又必然被"重建完就直接开跑"踩中的坑** |
| **P-11** 🔴 **本行仓库侧口径已作废**（`glob("*.txt")` 结构性看不见非 txt 文件，见 §15；改跑 `& $py scripts/check_corpus_parity.py`） | **语料在位要按名单比，不能只数条数**（P-9 的加强版） | `curl.exe -sS --noproxy '*' -H "Authorization: Bearer $env:EVAL_TOKEN" "http://127.0.0.1:8001/api/v1/documents?page=1&page_size=500" -o "$env:TEMP\evalrun\docs_live.json"`，再 `& $py -c "import json,pathlib;live=set(json.loads(pathlib.Path(r'$env:TEMP\evalrun\docs_live.json').read_text(encoding='utf-8-sig'))['documents']);repo=sorted(p.name for p in pathlib.Path('documents').glob('*.txt'));print('repo_txt=',len(repo));print('live=',len(live));print('only_in_container=',sorted(live-set(repo)));print('only_in_repo=',sorted(set(repo)-live))"`（`$py` 见 §7） | **两个差集都必须为空**（或只含业主点头的已知差集），"条数相等"不算过。为什么不许只数条数（R93 §3.9）：`97 − 11 = 86`、`89 − 86 = 3` ⇒ 卷里另有 3 篇不在仓内，而 `89 + 11 = 100` 恰好成立 ⇒ **P-9 的条数判据会通过，名单其实是错的**；数数能对上是巧合。`/documents` 路由 `app/api/v1/chat.py:2560`，仓库侧名单口径 = `git -c core.quotepath=false ls-files documents` 里的 `*.txt` |
| **P-12** | **数据属主账号与数据集已备好**（P-10 的前置；总控 09-19 已裁定唯一路线） | 只读核对两条：`curl.exe -sS --noproxy '*' -H "Authorization: Bearer $env:EVAL_TOKEN" "http://127.0.0.1:8001/api/v1/users"`（应能看到那个属主账号，且它的 `department` **非空**）；`curl.exe -sS --noproxy '*' -H "Authorization: Bearer $env:EVAL_TOKEN" "http://127.0.0.1:8001/api/v1/data-files"`（`报销明细表.csv` 在册，口径同 P-10） | 两条都成立才算过，且**必须在开窗之前就位**：开窗前必须已备好「**带部门的数据属主账号 + 它名下的数据集**」。🔴 **裁定路线（总控 09-19，唯一一条）**：经 API 建账号 —— `POST /api/v1/users`（`app/api/v1/auth.py:90`，body 收 `department` 字段，见 `:22` 与 `:98`），再 `POST /api/v1/upload-excel`（`app/api/v1/data.py:166`）把 `报销明细表.csv` 传进去；这条 seed 序列**必须可重跑**（每次重建镜像或换卷之后重跑一次，就能恢复 P-10）。🚫 **两条不许（同一裁定）**：(a) 改 `deploy/.env.server` 的 `AUTH_DEPARTMENT` 再重启，靠它给首任管理员补部门 —— 不走这条（它只是「无部门⇒被拒」的成因：`app/common/auth.py:216` 读该 env，没被点名的账号就没有部门）；(b) `docker cp` 把 CSV 直接塞进卷 —— 那会**绕过部门权限层**，造出一个客户机上复现不出来的假通过，比已知的缺口更坏。为什么不备好后段就白跑：无部门的属主 ⇒ `app/api/v1/data.py:39-43` 直接拒（已实测 `403 {"detail":"department_scope_required"}`，看板 §4BC.3），而日志把它记成"一次拒绝，不是服务端故障"（原注释措辞 a refusal, not a server fault），**不会喊**，只会被当成上传功能坏了；✅ 09-19 本班把这条 seed 序列落成了仓内可跑件：scripts/seed_workspace.py + 清单 deploy/workspace-seed.json（属主与部门、100 篇语料、数据集归属全写在清单里，只走公开 API；密码只经 password_env 取环境变量，永不入仓）。取 --check 只报缺什么、不上传，缺料退出码 2；同一清单第二次跑零上传 = 幂等，重建镜像或换卷之后重跑一次就恢复 P-10。实测：属主 dataowner（财务部）+ 报销明细表.csv 在册 + 11 篇补传 ⇒ P-9 = 100 篇、P-10 在册；另有 4 行语料在服务器上而盘上没有（六级作文模板.docx 与两张 PDF 是 chat-02 / insight-07 的出处，browser_acceptance_policy.txt 是浏览器测试残留），脚本会点名警告；那三篇 PDF/docx 的源字节此刻在仓外隔离目录 企业智脑-debris\2026-09-19（09-19 清理工作树残片时移入，未入 git ⇒ 客户机上复现不出来，要长期靠它们救 chat-02 / insight-07 就必须真入库）。 |
| **P-13** | **向量腿没下线**（退化检索必须为 0） | 开窗前 `curl.exe -sS --noproxy '*' "http://127.0.0.1:8001/api/v1/health/details" -o "$env:TEMP\evalrun\health_before.json"`，收窗后同法取 `health_after.json`；再 `docker logs --since <开窗时刻> enterprise-brain-backend-1 \| Select-String "退化为关键词召回" \| Measure-Object` | `embedding.degraded_searches` 的**开窗前后差值 = 0**，且日志计数 = 0（计数点 `app/rag/retriever.py:131` 与 `:1005`，出口 `:136-141` → `app/common/monitoring.py:236-248` → 路由 `app/api/v1/auth.py:51`）。不成立 ⇒ embedding 一挂，`retriever.py:984` 只 log 一行就返回词法命中：**采集器照样 `collected=105 of 105`、exit 0**，量到的却是关键词召回的分数。P-1..P-9 **一条都盖不住**，且完全静默 |
| **P-14** | **确认打的是 `/ask` 而不是 `/chat`** | `Select-String -Path "$env:TEMP\evalrun\eval_transport_ask.py" -Pattern 'api/v1/ask','api/v1/chat'`；收窗后 `& $py -c "import json,pathlib;rows=[json.loads(l) for l in pathlib.Path(r'$env:TEMP\evalrun\answers-real.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()];print('tool_calls_gt0=',sum(1 for r in rows if (r.get('tool_calls') or 0)>0))"` | transport 里只允许命中 `/api/v1/ask`（`app/api/v1/chat.py:1072`），且 `tool_calls_gt0 > 0`（该字段由采集器带出，`scripts/collect_evaluation_answers.py:51`、`:149`；dry-run 行是 `None`，见 `:246`）。误用旧 `/chat`（`chat.py:850`）⇒ `:864` **直接调 `retriever.search`，绕开整个 RetrievalPipeline**（查询改写、术语扩展、BM25 多路、RRF、Cross-Encoder 重排全不走），整轮量的是旧链路，分数系统性偏低且与任何一轮都不可比 |
| **P-15** | **把"改写腿状态"写进报告抬头** | `docker logs --since <开窗时刻> enterprise-brain-backend-1 \| Select-String "查询改写失败" \| Measure-Object` | 计数出来后与题数对照（0 / 少量 / ≈105 是三回事），并把结论**原样写进报告抬头**（日志点 `app/rag/retrieval_pipeline.py:224`，档位实现 `:49`）。看板 §4AZ.5 已实测现网改写**每次**都失败并返回空串 ⇒ 不标注，R36 判据③ 的 before/after 会被下一个人当成"同一系统"比较，把 R92 的收益记到别的单上；而且每题白烧 ~15 s GPU，**整轮预算不是 73 min** |
| **P-16** | **在盘 ≠ 已索引**：`/documents` 与 `/documents/catalog` 名单必须对得上 | 先按 P-11 取 `docs_live.json`，再 `curl.exe -sS --noproxy '*' -H "Authorization: Bearer $env:EVAL_TOKEN" "http://127.0.0.1:8001/api/v1/documents/catalog?page=1&page_size=500" -o "$env:TEMP\evalrun\docs_catalog.json"`，然后 `& $py -c "import json,pathlib;cat=json.loads(pathlib.Path(r'$env:TEMP\evalrun\docs_catalog.json').read_text(encoding='utf-8-sig'))['documents'];live=set(json.loads(pathlib.Path(r'$env:TEMP\evalrun\docs_live.json').read_text(encoding='utf-8-sig'))['documents']);print('catalog_not_indexed=',sorted(d['filename'] for d in cat if d.get('index_status')!='indexed'));print('live_not_in_catalog=',sorted(live-{d['filename'] for d in cat}))"` | `live_not_in_catalog` **必须为空**；`catalog_not_indexed` 必须等于**已知**的"按策略不入索引"集合（`index_status` 取值见 `app/api/v1/chat.py:2028` 与 `INDEX_STATUS_INDEXED / EXCLUDED / UNKNOWN`；`/documents` 在 `:2560`、`/documents/catalog` 在 `:2573`）。`:2562-2569` 显示 `/documents` 只回**同时**满足"目录可见"且"在向量库里"的名字 ⇒ 一条上传成功但没发布的文件会在 P-9 的计数里**凭空消失**（表现为"篇数不够"），反过来只看 catalog 又会**多算**（表现为"语料在位但检索不到"）。上一班是"被删了还在跑"，这一种是"传了但查不到"，同一个失效面换了入口 |
| **P-17** | **语料基线快照留档（事后可自证的证据链）** | 开窗前 `Get-ChildItem documents -File \| Get-FileHash -Algorithm SHA256 \| Select-Object Path, Hash \| Export-Csv -NoTypeInformation -Encoding UTF8 "$env:TEMP\evalrun\corpus_before.csv"`，收窗后同法出 `corpus_after.csv`，再 `Compare-Object (Import-Csv -Encoding UTF8 "$env:TEMP\evalrun\corpus_before.csv") (Import-Csv -Encoding UTF8 "$env:TEMP\evalrun\corpus_after.csv")` | `Compare-Object` **无输出**（两次名单/哈希逐字节相同），且报告正文引用这两个文件的**绝对路径 + `Get-Date` 时间戳**（时点戳口径同 §7）。落点必须在**仓外**（`$env:TEMP\evalrun\`，§8 产物纪律）。为什么不留一个数：上一轮废跑的根因就是拿宿主 `chroma_db` 快照当语料真相源（看板 §4AZ.3、P-9 的 🔴）。另注意主树 `documents/` 盘上 123 个文件里 **26 个是上传测试产物**（`kb_policy_*__v1.txt`、`browser_upload_test__v*.txt`、`codex-upload-[ab]__v1.txt`、`qa_*__v1.txt`、`安全生产管理制度汇编.zip` 等）⇒ 任何 `_reconcile.py` 型对账**必须**以"窗口前留档的名单"为唯一真相源，否则又会朝污染集合删文件 |
| **P-18** | **开窗前清掉答案缓存**（本班级补；`scripts/eval_transport_ask_v2.py` 的注释里一直引它，但本文 §2 从来没有这一行 —— 2026-09-19 22:1x 实取 `answer:*` 为 0 键才没暴雷） | `docker exec enterprise-brain-redis-1 sh -lc "redis-cli -a \"$REDIS_PASSWORD\" --no-auth-warning --scan --pattern 'answer:*' | wc -l"`（口令取自 `deploy/.env.server` 的 `REDIS_PASSWORD`，**redis 要鉴权**） | 开窗前该数必须为 **0**；不为 0 就 `--scan --pattern 'answer:*' | xargs redis-cli -a <pw> --no-auth-warning DEL`（只删 `answer:*`，别 `FLUSHALL`）。为什么是硬闸：缓存键含用户/部门/密级/角色/权限但**不含 `session_id`**（`app/common/cache.py:195` + `:144`），TTL 1800 s ⇒ 换新 session 关不掉缓存；半路重跑同一个 shard 或先做过单题冒烟，第二次就会拿到约 50 ms 的假时延，而 §10 的 I-3 只在 max<1 s 时才判死 —— 混在一轮里（部分命中）它拦不住。冻结的适配器另有双路识别（`text.cached` 与 status 文案「缓存命中」）并直接 raise 停窗 |

- 判据取哪个符号：任选一个**只存在于被测版本**里的符号即可，本次用的是 `_authorized_source_rows`（R41 引入，`app/api/v1/chat.py:284`）。树内计数命令与容器内计数命令必须指向**同一个文件相对路径**（容器内是 `/app/app/api/v1/chat.py`）。
- **P-8 不过的唯一正解是重建后端镜像，且必须 `docker compose build migrate`**：直接 build `backend` 会**静默空跑**，跑完还以为更新了。重建属**业主侧长任务（已挂 H12）**，Agent 不得代做。
- 这与 §9「跑分窗口内禁部署」不冲突：P-8 要求**开窗前**镜像已到位，§9 要求**开窗后**不许动。宿主直连跑法（§5 的 B′，宿主进程读宿主工作树）可把 P-8 退化为"确认该进程工作树 = 被测 HEAD 且启动时刻晚于该 commit"；容器跑法没有这条退路。

## 3. transport 适配器：写什么、采集器读什么

### 3.1 采集器读取键（逐个从源码取证，非凭印象）

`--transport` 只接受 `module:callable` 形式（`scripts/collect_evaluation_answers.py:252-268`，`load_transport`），callable 收到的是**整条 fixture row 字典**（`scripts/collect_evaluation_answers.py:188`）。它返回的字典按键被读：

| payload 键 | 读取处 | 缺失/非法时 | 建议来源 |
|---|---|---|---|
| `answer` | `:144` `str(payload.get("answer", ""))` | 缺失 ⇒ 空串 ⇒ **被判为缺口**（`:198-202`） | `/ask` 的 `text` 事件 `content`（`app/api/v1/chat.py:1197`） |
| `evidence` | `:94-99`（`:145` 调用） | 缺失 ⇒ `[]`；非 list ⇒ 抛 `CollectionError` | `sources` canonical 事件 `data.sources`（`app/api/v1/chat.py:1236-1251`） |
| `latency_ms` | `:114-121`（`:146` 调用） | **缺失即由采集器用 `time.perf_counter` 实测补齐**（`:186`/`:192`/`:116`）；非数值或负数 ⇒ 抛错 | 建议**不要自报**，让采集器测：服务端 `elapsed_total` 只有 0.1 s 分辨率（`app/api/v1/chat.py:1139`） |
| `first_token_at` | `:125-130`（`:147` 调用） | 缺失 ⇒ `null`；类型非 number/str ⇒ 抛错 | 客户端收到第一个 `text` 事件的本地墙钟（骨架里是 `arrival`）。**别拿 `request.started.timestamp` 冒充**（`app/api/v1/chat.py:229` 那是请求起点，不是首字） |
| `thinking_chars` | `:103-110`（`:148` 调用，`_counter`） | 缺失 ⇒ `null`；bool/非 int/负数 ⇒ 抛错 | HTTP 侧观测不到隐藏思维链 ⇒ 老老实实 `null`（R29 要它，宁缺不假） |
| `tool_calls` | 同上 `_counter`（`:149`） | 同上 | `step` 事件条数（`app/api/v1/chat.py:1142`、`:1332`、`:1347`） |
| `claims` / `confidence` / `confidence_label` | `:154-156` 原样透传 | 不给就没有该键 | 评分端消费见 `app/quality/eval.py:35-51` |
| 返回 str 而非 dict | `:136-137` 自动包成 `{"answer": <str>}` | 返回其它类型 ⇒ `:138-141` 抛错 | 不建议：会丢掉全部 trace 字段 |

另有两条**采集器自己加**的键，transport 不用管：`id`（取自 row，`:143`）与 `answer_source`（取自 `--transport` 字面量，`:324`）。整行四键与三个 trace 键的存在性由 `assert_line_contract`（`:161-172`）硬校验，写完还要过覆盖闸门 `assert_coverage`（`:206-217`）才落盘（`:326` → `:340`）：**缺题 ⇒ exit 1 + 列出缺失 id + 一个字节都不写**。

### 3.2 最小可运行骨架（存到**仓外**，例如 `$env:TEMP\evalrun\eval_transport_ask.py`）

只依赖标准库。原则：**任何异常都往上抛**，让采集器把该题记成缺口——绝不用空串/占位答案冒充实采。
```python
"""R36 真机 105 题采集适配器骨架：POST /api/v1/ask 单题一问，交回采集器要的字典。

跑法（base_url / 账号都走环境变量，代码里没有硬编凭据）：
    $env:EVAL_BASE_URL = "http://127.0.0.1:8001"      # 容器内直连；宿主经 nginx 用 http://localhost
    $env:EVAL_USERNAME = "<业主提供>";  $env:EVAL_PASSWORD = "<业主提供>"
    $env:PYTHONPATH  = "$env:TEMP\evalrun"            # 本文件所在目录
    & "<venv 绝对路径>" scripts/collect_evaluation_answers.py --transport eval_transport_ask:transport
"""
import json
import os
import time
import urllib.request
import uuid

BASE_URL = os.getenv("EVAL_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
TIMEOUT = float(os.getenv("EVAL_HTTP_TIMEOUT", "900"))
PROXIES = {}  # 空 dict = 无视 http_proxy/https_proxy，等价 curl --noproxy "*"（§6）
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler(PROXIES))  # urlopen() 没有 proxies 参数：骨架原文照抄会 TypeError（2026-09-18 实测）
_TOKEN = ""


def _open(path, payload):
    headers = {"Content-Type": "application/json"}
    if _TOKEN:
        headers["Authorization"] = "Bearer " + _TOKEN  # app/common/auth.py:298-302
    request = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
    )
    return _OPENER.open(request, timeout=TIMEOUT)


def login():
    """/api/v1/login 免鉴权（app/common/auth.py:36 PUBLIC_PATHS），响应体取 token 键。"""
    global _TOKEN
    if _TOKEN:
        return _TOKEN
    body = json.loads(_open("/api/v1/login", {
        "username": os.getenv("EVAL_USERNAME", ""),
        "password": os.getenv("EVAL_PASSWORD", ""),
    }).read().decode("utf-8"))
    _TOKEN = body.get("token") or ""  # app/api/v1/auth.py:60-66
    if not _TOKEN:
        raise RuntimeError("login 响应里没有 token 键")
    return _TOKEN


def iter_events(response):
    """逐行解 SSE：yield (事件名, payload, 到达墙钟)。

    服务端每事件写成 event: <name> + data: <单行 JSON> + 空行（app/api/v1/chat.py:208-209），
    所以按空行切块即可；到达墙钟用 time.time()，是给 first_token_at 用的真实观测值。
    """
    name, data, arrival = None, None, None
    for raw in response:
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if line.startswith("event: "):
            name = line[7:].strip()
        elif line.startswith("data: "):
            data, arrival = json.loads(line[6:]), time.time()
        elif not line and name:
            yield name, (data or {}), arrival
            name, data, arrival = None, None, None


def transport(row):
    """采集器对每题调一次：入参是 fixture row，出参是 §3.1 那张表里的 payload。"""
    login()
    session_id = uuid.uuid4().hex  # 每题新会话 ⇒ use_answer_cache=False（chat.py:998）
    answer, evidence, first_token_at, steps = "", [], None, 0
    with _open("/api/v1/ask", {"message": row["question"], "session_id": session_id}) as resp:
        for name, data, arrival in iter_events(resp):
            if name == "queued":  # 被限流转排队，拿不到本轮答案（chat.py:978-992）
                raise RuntimeError("被限流入队，本轮不计：把节奏放慢成严格串行")
            if name == "status" and "缓存命中" in str(data.get("content", "")):
                raise RuntimeError("命中答案缓存（chat.py:1006），时点是假的")  # chat.py:1002-1016
            if name == "step":
                steps += 1  # chat.py:1142 / :1332 / :1347
            if name == "text" and data.get("content"):
                if first_token_at is None:
                    first_token_at = arrival  # 首字到达：客户端实测，不用服务端 elapsed 折算
                answer = data["content"]  # /ask 只发一条整段 text（chat.py:1197）
            if name == "sources":
                # canonical 事件外面还有一层信封（app/api/v1/chat.py:222-232），
                # 所以来源列表在 data["data"]["sources"]，不是 data["sources"]。
                evidence = list((data.get("data") or {}).get("sources", []))  # chat.py:1236-1251
            if name == "hitl":
                raise RuntimeError("触发了 HITL 确认，该题未产出终答（chat.py:1212）")
            if name == "error":
                raise RuntimeError("ask 错误事件：" + str(data.get("content", "")))
    if not answer.strip():
        raise RuntimeError("空答案")  # 采集器 :198-202 同样会判缺口，这里只是早报因
    return {
        "answer": answer,
        "evidence": evidence,
        "first_token_at": first_token_at,
        "thinking_chars": None,  # HTTP 侧看不见隐藏思维链 ⇒ null，禁止估算
        "tool_calls": steps,
        # 故意不自报 latency_ms：交给采集器 perf_counter 实测（:116/:186/:192）
    }
```

**证据键名提醒**：`sources` 事件里每行的字段是 `source` / `score` / `worker` / `chunk_index` / …（`app/api/v1/chat.py:251-266`），**不是** `source_name`。评分端只判 `evidence` 真伪与条数（`app/quality/eval.py:36`、`:44`、`:86-89`），所以原样透传就能过 `requires_evidence`；但要给 R38 的溯源链留可读名，建议在 transport 里做一次搬运：`{"source_name": row["source"], "locator": {"chunk_index": row["chunk_index"]}, "score": row["score"], "worker": row["worker"]}`。
## 4. 认证

- 登录：`POST /api/v1/login`，请求体 `{"username": "...", "password": "..."}`（字段定义 `app/api/v1/auth.py:13-15`）。该路径**免鉴权**（`app/common/auth.py:36` 的 `PUBLIC_PATHS`）。
- 取 token：**响应体顶层键 `token`**（`app/api/v1/auth.py:60-66`），同时会回 `username` / `role` / `department` / `expires_in`。`expires_in = token_expire_hours * 3600`（默认 24 h，`app/common/auth.py:34`）——105 题一轮 `[推算]` ≈ 73 min，**一轮内不会过期**，但别把 token 存盘复用到下一天。
- 后续请求带法：请求头 `Authorization: Bearer <token>`（读取处 `app/common/auth.py:298-302`，`startswith("Bearer ")`，**前缀后有一个空格**）。没有 token 调 `/ask` 会 401 `authentication_required`（`app/api/v1/chat.py:914-915`）。
- 探活免登录：`GET /api/v1/health`（`app/api/v1/auth.py:37`、`app/common/auth.py:36`）。用它先确认链路通，再谈跑分。

```bash
# 容器内跑法（§5 情形 A）。注意 --noproxy（§6）
curl -sS --noproxy '*' -X POST http://127.0.0.1:8001/api/v1/health
TOKEN=$(curl -sS --noproxy '*' -X POST http://127.0.0.1:8001/api/v1/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"<业主提供>","password":"<业主提供>"}' | python -c 'import json,sys; print(json.load(sys.stdin)["token"])')
curl -sS --noproxy '*' -X POST http://127.0.0.1:8001/api/v1/ask \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"message":"住宿费标准是多少？","session_id":"probe-0001"}'
```
凭据来源：首个管理员由 `AUTH_USERNAME` / `AUTH_PASSWORD_HASH` 播种（`app/common/auth.py:99-116`；生产环境二者必填，非生产回退 `admin/admin123` 见 `:112-115`）。**业主侧提供，runbook 不记录明文口令**；`/ask` 的检索范围随 Principal 收敛，所以**跑分账号必须用最终验收要用的那个角色/部门**，换账号=换分数口径。

## 5. 端口口径（容器内 :8001 / 宿主经 nginx :80）

| 情形 | 在哪执行 | `EVAL_BASE_URL` / curl 目标 | 依据 |
|---|---|---|---|
| **A 容器内**（推荐，链路最短） | `docker exec -it enterprise-brain-backend-1 bash` | `http://127.0.0.1:8001` | 镜像内 uvicorn 监听 `0.0.0.0:8001`（`Dockerfile:78`、`EXPOSE 8001` `:73`），健康检查就是打 `http://127.0.0.1:8001/api/v1/health`（`Dockerfile:76`） |
| A′ 容器内（同网别的服务） | 任一 compose 服务内 | `http://backend:8001` | nginx 上游即此写法：`set $enterprise_brain_api http://backend:8001;`（`deploy/nginx.conf:38`）；拓扑测试也钉死了它（`tests/test_deployment_topology.py:167`） |
| **B 宿主经 nginx** | Windows 宿主（`curl.exe` / venv 解释器） | `http://localhost`（等价 `http://localhost:80`） | 前端容器发布 `${HTTP_PORT:-80}:80`（`docker-compose.yml:233`），nginx `listen 80`（`deploy/nginx.conf:30`）+ `location /api/ { proxy_pass $enterprise_brain_api; }`（`:50`、`:53`） |
| B′ 宿主直连后端（绕过 nginx） | Windows 宿主 | `http://127.0.0.1:8001` | 后端也发布到宿主：`127.0.0.1:${BACKEND_HOST_PORT:-8001}:8001`（`docker-compose.yml:147`，注释说明容器侧固定 8001、只有宿主侧可移）；`scripts/verify_container_stack.py:223` 同一口径 |

两种跑法的**选择规则**：要"量产品实际付的时延" ⇒ 走 B（经 nginx，含代理开销与 900 s 读超时）；要"排除代理噪声、单测模型腿" ⇒ 走 A。同一轮基线**只允许一种**，并在报告里写明；A/B 混跑得到的 P95 不可比。
经宿主 nginx 时注意：`proxy_read_timeout 900s`（`deploy/nginx.conf:63`）> 单题预算 `CHAT_REQUEST_TIMEOUT=300s`（`app/api/v1/chat.py:1033`），所以**先撞 300 s 应用超时、不会被 nginx 掐** `[算术]`（数值取自源码默认，非实测）。

## 6. Clash 对 localhost 生效：所有 curl 必须 `--noproxy '*'`

- **命令纪律**：`curl -sS --noproxy '*' ...`（Git-Bash / WSL 用引号包 `*`；PowerShell 里 `curl` 是 `Invoke-WebRequest` 别名，请用 `curl.exe --noproxy '*'`，或干脆用 §7 的 venv 解释器跑采集器）。
- **为什么**：本机 Clash 会接管 `localhost`，代理对 `127.0.0.1` 的 CONNECT/转发**不一定回源**，于是"服务明明健康但 curl 打不通"。
- **漏掉的症状（照着对号入座，别去重启服务）**：
  1. 连接层立刻失败：`curl: (7) Failed to connect` / `Curl error 000`，而 `docker exec ... printenv` 一切正常；
  2. 走 SSE 时**首字节之后断流**或整体 502/504（代理吞流、按 HTTP/1.1 缓冲）；
  3. 时延被代理加料：`latency_ms` 莫名抬高且抖动大 —— 对 R36 基线是**污染数据**，比失败更糟；
  4. `python` 侧 `urllib` 同样会被 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量影响 —— 骨架里用 `PROXIES = {}` 显式屏蔽（`_open()`），否则等价于漏写 `--noproxy`。
- **自检**：`curl.exe -sS --noproxy '*' http://127.0.0.1:8001/api/v1/health` 与不带 `--noproxy` 各跑一次，若只有前者通 ⇒ 本机代理确实在拦，后续所有命令必须带 `--noproxy '*'`。
## 7. 执行序列（三步，一条一个退出码）

```powershell
cd C:\Users\fengx\PycharmProjects\perf-lab
$py = 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe'   # 只用这个解释器（P-2）
New-Item -ItemType Directory -Force -Path "$env:TEMP\evalrun" | Out-Null
Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'   # 记录跑分窗口起点（时点戳）

# A. 结构预检：零模型、零凭据，先证明链路和闸门能用（产物只进 TEMP）
& $py scripts/collect_evaluation_answers.py --dry-run --allow-sample `
  --fixture tests/fixtures/business_evaluation_100.jsonl `
  --output "$env:TEMP\evalrun\sample-answers.jsonl"

# B. 真采集：串行 105 题（此时才打模型；--allow-sample 属 dry-run 专用，别带）
$env:PYTHONPATH = "$env:TEMP\evalrun"
& $py scripts/collect_evaluation_answers.py --transport eval_transport_ask:transport `
  --fixture tests/fixtures/business_evaluation_100.jsonl `
  --output "$env:TEMP\evalrun\answers-real.jsonl"

# C. 评分：正式落盘物是报告，进 docs/testing/
& $py scripts/run_quality_evaluation.py `
  --fixture tests/fixtures/business_evaluation_100.jsonl `
  --answers "$env:TEMP\evalrun\answers-real.jsonl" `
  --output docs/testing/evaluation-report.json
Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'   # 窗口终点
```

- **退出码口径**：`0` 成功；`1` = 覆盖闸门/fixture 失败（`scripts/collect_evaluation_answers.py:327-338`，会打 `GATE FAILED: missing N fixture id(s): ...` 且**不写任何字节**）；`2` = 用法被拒（`:302-313` 的 dry-run fail-closed、`:295-301` 的 transport 二选一）。
- **A 步期望输出**：`collected=105 of 105 wrote=<仓外路径>` + `dry-run sample answers: structure only, NOT a quality baseline`。A 步产物**绝不进 C 步**（它就是 §10 要拦的那个假基线）。
- **B 步期望输出**：同样 `collected=105 of 105`。**中途不要 Ctrl+C**：采一半的产物会被闸门判失败（缺 id），已打模型的时点也就废了；确实要中断就整轮重来。
- **C 步期望输出**：`evaluated=105 correctness=... evidence=... p95_ms=...`（`scripts/run_quality_evaluation.py:20-25`）。`evaluated=` 必须是 105，少了就是 fixture 指错（默认值仍指 30 题集，`scripts/run_quality_evaluation.py:14`）。
- **失败重试的正确姿势**：某题因模型超时/报错缺失 ⇒ 修因后**整轮重跑**。不要手工把缺的题补进 answers 文件：`assert_coverage`（`scripts/collect_evaluation_answers.py:206-217`）按 fixture 全集判，补进去的行必须与真机同口径，否则 §10 的时点/延迟检查会露馅。

## 8. 产物落点纪律

| 产物 | 落点 | 是否进 git | 依据 |
|---|---|---|---|
| answers JSONL（含 dry-run 样例） | 仓外：`$env:TEMP\evalrun\*.jsonl`，或采集器默认 `tempfile.gettempdir()\enterprise-brain-evaluation-answers.jsonl` | **不进** | `scripts/collect_evaluation_answers.py:43-45` 的注释就是这条纪律：仓内 `artifacts/` 未被忽略、`.gitignore` 在 H5 结案前冻结 |
| 评测报告 JSON | `docs/testing/evaluation-report.json` | 进（唯一该动的跟踪文件） | `scripts/run_quality_evaluation.py:17` 既有默认 |
| 跑分窗口/环境快照（可选） | 仓外，或写进报告旁边的人读文档时**只贴摘要** | 视情况 | 别把 105 条全文塞进跟踪文档 |
- 跑完自查：`git status --porcelain -uall` 只应出现 ` M docs/testing/evaluation-report.json`（+ 业主批准的文档）。**出现 `artifacts/`、`*.jsonl`、`chroma_db/` 任意一项 = 越界**，先清回仓外再回报。
- 采集器不会自己建 `artifacts/`（默认已在 TEMP），但**别顺手 `--output artifacts/...`**：那会在每个 worktree 长期挂脏，并有被误 `git add` 的风险。

## 9. 计时红线

- **模型是单点**：`n_ctx=4096` 的共享红线 ⇒ 跑分窗口内**只允许这一条链路打 Ollama**。其他 agent 的 perf_probe、看板复测、演示点击、并发的 pytest 模型用例，全部让路（并发即作废，`docs/handoff/2026-09-15-orchestration-board.md:1293`：复测须打 Ollama ⇒ 命中并发红线，只能排队、由用户另开独立对话做）。
- **并发闸门不许动**：`MODEL_MAX_CONCURRENCY` 必须为 `1`（`docker-compose.yml:141` 默认；实现 `app/common/model_budget.py:53`、`:101`）。调高它跑出来的 P95 不是产品时延，是排队时延。另需注意：闸门与 `n_ctx` 都是**镜像里**的配置，改了 `.env` 不重建镜像等于没改（与 §2 P-8 同源）。
- **窗口内禁部署动作**：不得 `docker compose up/down/restart`、不得重建镜像、不得改 `.env` 后重启服务（`docs/handoff/2026-09-15-backend-followup-requests.md:487`）。
- **缓存不算实测**：`/ask` 在无 `session_id` 时会命中全局答案缓存并**一次模型都不打**（`app/api/v1/chat.py:998`、`:1002-1016`）。骨架里靠两条防线拦：每题新 `session_id`（关缓存）+ 见到 `status` 含"缓存命中"就抛错（`:1006`）。
- **限速不算失败重试**：`/ask` 有每用户 10 次/分钟的限制（`app/api/v1/chat.py:936`），超限会**入队**并只回 `event: queued`（`:978-992`），此时既没有 `text` 也没有 `sources`。串行跑 `[推算]` ≈ 1.5 次/分钟（按 41.6 s/题），不会触发；一旦触发说明链路异常快 ⇒ 当轮作废查因。
- **别在跑分窗口内跑仓库测试**：pytest 会把 Chroma 写进沙箱（R53 已钉），但也可能拉起模型用例，与 P95 抢同一个单点。测试与跑分分窗口。
## 10. 真跑分 vs 自证假基线：一眼分辨 + 机械拦截

先给结论：**只看分数无法分辨**。`--dry-run` 桩把 fixture 金标原文当答案回声（`scripts/collect_evaluation_answers.py:227-238` 的 `build_dry_run_transport`），而评分端 `app/quality/eval.py:63-66` 判的是"`must_contain` 全含 / 无则 `row["answer"] in text`" ⇒ 桩必然刷到 **104/105 = 0.9905、evidence 1.0000** `[实测]` 2026-09-17 16:25:42。而 `app/quality/runner.py` 与 `app/quality/eval.py` **都不读 `answer_source`**，所以报告里不会留任何"这是桩"的痕迹。拦截只能靠下面 5 条外部特征。

| # | 拦截 | 判据 | 硬度 |
|---|---|---|---|
| I-1 | transport 标记字段 | answers 每行的 `answer_source`（采集器 `:152` 写入，取值 `:321` 的 `"dry-run"` 或 `:324` 的 `--transport` 字面量）。出现 `dry-run` ⇒ 判死；真跑分应等于你传给 `--transport` 的那个 `module:callable` 串 | 硬，零误判 |
| I-2 | 文件落点 | answers 若落在仓内（`git status --porcelain -uall -- *.jsonl` 非空）⇒ 违规，按 §8 挪出仓外再判 | 硬 |
| I-3 | 时延量级 | `latency_ms` 最大值 < 1000 ms ⇒ 判死（桩 `[实测]` max 0.003 ms（p95 0.001 ms）；真机单题 `[推算]` ~4.2e4 ms，取历史 41.581 s）。阈值取 1 s `[推算]`：宁可错杀一个数量级，也不放缓存命中/桩混进基线 | 硬 |
| I-4 | 金标逐字率 | 答案与 fixture 金标**逐字相等**的行占比 > 50% ⇒ 起疑人工复核（短答案天然容易撞，所以只做软判） | 软 |
| I-5 | trace 覆盖率 | `first_token_at` / `tool_calls` / `thinking_chars` 的**非 null 计数**。全 null 不代表假，但**R29 思考税与 R38 usage 核实对这份文件无据可用**；`thinking_chars` 恒 null 是 HTTP 侧观测不到，不是漏采（见 §3.1） | 可用性判据 |

机械检查（把下面存到**仓外** `$env:TEMP\evalrun\eval_selfcheck.py`，只读、不改任何文件）：

```python
"""eval_selfcheck.py <fixture.jsonl> <answers.jsonl>：非零退出 = 判死或起疑。"""
import json, statistics, sys

rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8-sig") if l.strip()]
got = [json.loads(l) for l in open(sys.argv[2], encoding="utf-8-sig") if l.strip()]
gold = {str(r["id"]): str(r.get("answer", "")).strip() for r in rows}
ids = {str(a.get("id")) for a in got}
flags = []
stubs = sum(1 for a in got if str(a.get("answer_source", "")).startswith("dry-run"))
if stubs:
    flags.append(f"I-1 answer_source=dry-run 共 {stubs} 行（自证桩）")
missing = [str(r["id"]) for r in rows if str(r["id"]) not in ids]
if missing:
    flags.append(f"I-1b 缺题 {len(missing)} 行：{missing[:5]}")
exact = sum(1 for a in got if gold.get(str(a.get("id")), "__no_gold__") == str(a.get("answer", "")).strip())
lat = [float(a["latency_ms"]) for a in got if a.get("latency_ms") is not None]
if not lat:
    flags.append("I-3 latency_ms 全空，P95 无从谈起")
elif max(lat) < 1000.0:
    flags.append(f"I-3 latency_ms 最大 {max(lat):.3f} ms，不可能是真机问答")
sources = sorted({str(a.get("answer_source")) for a in got})
print(json.dumps({
    "rows": len(got), "fixture": len(rows), "missing": len(missing),
    "gold_exact_matches": exact, "gold_exact_ratio": round(exact / len(got), 4) if got else None,
    "latency_ms": {"count": len(lat), "min": min(lat) if lat else None,
                   "median": round(statistics.median(lat), 3) if lat else None, "max": max(lat) if lat else None},
    "first_token_at_non_null": sum(1 for a in got if a.get("first_token_at") is not None),
    "thinking_chars_non_null": sum(1 for a in got if isinstance(a.get("thinking_chars"), int)),
    "tool_calls_non_null": sum(1 for a in got if isinstance(a.get("tool_calls"), int)),
    "answer_sources": sources,
}, ensure_ascii=False, indent=2))
if got and exact / len(got) > 0.5:
    flags.append(f"I-4 金标逐字相等 {exact}/{len(got)}，超过 50%，需人工复核")
for flag in flags:
    print("FLAG " + flag)
sys.exit(1 if flags else 0)
```

- 跑法：`& $py "$env:TEMP\evalrun\eval_selfcheck.py" tests/fixtures/business_evaluation_100.jsonl "$env:TEMP\evalrun\answers-real.jsonl"`；exit 0 才算干净，exit 1 时 stdout 的 `FLAG` 行就是理由。
- 时点戳（人读的一眼分辨）：answers 与报告的写入时刻都应落在 §7 记录的跑分窗口之内；`docs/testing/evaluation-report.json` 必须比 answers **新**（先采集后评分）。桩文件的时间戳与任何跑分窗口无关，这也是它自己的破绽。
## 11. 数字口径与已知 nit 备案

### 11.1 数字口径（每条带标注 + 采集时点）

| 数字 | 标注 | 采集时点 / 依据 |
|---|---|---|
| 105 题 | `[实测]` | 2026-09-17 18:17:54 +08:00 本树计数（文件名里的 100 是历史名，别照文件名写题数）：`& $py -c "import json;print(sum(1 for l in open(r'tests/fixtures/business_evaluation_100.jsonl',encoding='utf-8-sig') if l.strip()))"` → `105`；把路径换成 `business_evaluation_30.jsonl` → `30` |
| 桩分数 correctness **0.9905** / evidence **1.0000** / p95 **0.001 ms** | `[实测]` | 2026-09-17 18:18:05 +08:00，本树跑 §7 的 A 步产物 → 再评分（`--output` 指 TEMP，不进仓）：`evaluated=105 correctness=0.9905 evidence=1.0000 p95_ms=0.001`；同一份桩文件被 §10 的自检脚本判死：`gold_exact_ratio=1.0`、`latency_ms.max=0.003`、`answer_sources=["dry-run"]`、exit 1 |
| 104/105 = 0.9905 | `[算术]` | `round(104/105, 4)`：105 题里只有 `insight-02` 失分（§11.2） |
| 单题 41.581 s | `[实测]` **历史值，本轮未重测** | `docs/handoff/2026-09-15-backend-followup-requests.md:626` 明确"旧 trace 的历史 `[实测]` 值"；`docs/handoff/2026-09-15-orchestration-board.md:925` 同值。**只能当量级参考，不得写成本轮结果** |
| 整轮 ≈ 72.8 min | `[推算]` | 105 × 41.581 s = 4365.99 s ÷ 60，基于上一行历史值 + 严格串行（P-5/P-6） |
| ≈ 1.44 次/分钟 | `[推算]` | 60 ÷ 41.581，用于对照下一条限额 |
| 限额 10 次/分钟 | `[实测]` 源码常量 | `app/api/v1/chat.py:936`（`check_rate_limit(username, max_per_minute=10)`）；超限入队 `:954-992` |
| 单题预算 300 s | `[实测]` 源码默认 | `app/api/v1/chat.py:1033`（`CHAT_REQUEST_TIMEOUT`，未设即 300） |
| nginx 读超时 900 s | `[实测]` 源码值 | `deploy/nginx.conf:63`；`300 < 900` 为 `[算术]` ⇒ 走宿主 nginx 时先撞应用超时，不会被代理掐 |
| 后端镜像 `Created = 2026-09-16T12:59:16Z`（北京 09-16 20:59:16） | `[实测]` | 2026-09-17 18:18:40 +08:00 由总控取证，**只读查看，未启动、未重启任何容器**；被测 `6ee2f79` committer `2026-09-17T16:54:20+08:00`，差约 20 h `[算术]`（UTC+8 换算后相减） |
| 容器内 `chat.py` 2294 行 / `_authorized_source_rows` 0 次 vs 树内 2383 行 / 2 次 | `[实测]` | 容器侧同上取证；树侧本树 `6ee2f79` 复核 2026-09-17 18:21:21 +08:00：行数 2383、标记 2 次 ⇒ 结论：现役容器不含 R41/R54/R26b，**P-8 判死** |
| I-3 判死阈 1000 ms | `[推算]` | 取"真机 `[推算]` 4.2e4 ms"与"桩 `[实测]` 1e-3 ms"之间留一个数量级余量，纯拦截用，不进任何统计 |

### 11.2 已知 nit 备案（**只备案，业主未点头前不得改评测集业务语义**）

- `insight-02`（`tests/fixtures/business_evaluation_100.jsonl`）：`must_contain = ["上升"]`，金标 `answer = "返回趋势异常"` ⇒ 金标自身不含 `must_contain`，任何真跑分**上限 104/105**。取证命令：
  `Select-String -Path tests/fixtures/business_evaluation_100.jsonl -Pattern insight-02 -SimpleMatch` → 第 64 行原样打出 `"answer":"返回趋势异常","must_contain":["上升"]`
- 影响口径：`answer_correctness` 的天花板 0.9905（`[算术]`）。**不许**为了让分数好看去改金标/`must_contain`/判分逻辑；要动得先拿到业主点头。
- 该行缺陷已被既有测试钉死为"已知集合"（`tests/test_evaluation_report.py` 的 `KNOWN_INCONSISTENT_*` 常量），所以修它属于评测集语义变更，不属于跑分动作。

## 12. 交付前自查清单（缺一即视为基线不成立）

- [ ] P-1…P-8 全过，尤其 `RETRIEVAL_TIER` 非 `fast`（P-4）、`MODEL_MAX_CONCURRENCY=1`（P-5）与镜像同源（P-8）。
- [ ] P-8 标记级实测：容器内 `_authorized_source_rows` 计数 = 树内计数（不等就找业主走 `docker compose build migrate` 重建（H12），**Agent 不得代做**，也别在跑分窗口内做）。
- [ ] §7-B 采集 exit 0 且 stdout `collected=105 of 105`；中途无 `GATE FAILED`。
- [ ] §7-C 评分 exit 0 且 stdout 以 `evaluated=105` 开头。
- [ ] `eval_selfcheck.py` 对真 answers  exit 0，`answer_sources` 等于你传的 `--transport` 串，`latency_ms.max` 在秒级（I-1…I-4）。
- [ ] `first_token_at` 非 null 计数 > 0（R29 才有据；全 null 时本单只支持质量基线，不支持思考税结论，须在报告里写明）。
- [ ] `git status --porcelain -uall` 只有 ` M docs/testing/evaluation-report.json`（+ 业主批准写入的文档），**没有** `artifacts/`、`*.jsonl`、`chroma_db/`。
- [ ] 跑分窗口起止时间戳（`Get-Date`）与产物 mtime 自洽，且窗口内无其他 agent 打模型。
- [ ] 基线分数落盘后，才允许解锁 R29 / R33 / R35 的"质量基线已建立"前置（`docs/handoff/2026-09-15-backend-followup-requests.md:546`）。

## 13. P-8 判据升级（09-19 23:0x，总控第二十三班，代码基线 `ce9630f`）

- 🔴 **P-8 的唯一判据改成一条命令**：`python scripts/check_image_provenance.py`，退出码 0 才算过。它读镜像自己的声明（`org.opencontainers.image.revision` 标签 + 容器内 `/app/BUILD_INFO`），不再拿时间戳做算术。§2 表里 P-8 那行的「时间级辅判据」就此作废，留着只为解释 09-17 那次误判是怎么来的。
- **旧标记级判据的字面数已过期**：`_authorized_source_rows` 在主树现值 **4**（`[实测]` 09-19 20:40：主树 4、容器 4；09-17 记的 2 被后续提交推翻）。⇒ 任何「数某个符号出现几次」的判据，今后只比 **容器 == 树**，别把文档里的常数当闸门。
- **重建命令补一条硬约束**：`--env-file deploy/.env.server` **不可省**（compose 要从它插值 `POSTGRES_USER` / `REDIS_PASSWORD` 的 `:?`，缺了就拒不启动），且必须 `build migrate` 而非 `build backend`（§4BC.5 已记两个坑）。重建前先 `$env:GIT_SHA = (git rev-parse --short HEAD)`，忘盖戳的镜像自称 `unknown`，P-8 只能退回逐文件 sha256（脚本会自动这么做）。
- **重建成本已实测，不再是「跨小时」**：改代码后重建 **1.5 s**（全层 CACHED，09-19 20:27）；换 `uv.lock` 才会重造 ~5.8 GB 的依赖层（同机实测 210 s）。镜像虚体积 **18.4 GB → 9.6 GB**。⇒ 「H12 属业主侧长任务」这个前提已经不成立，窗口开窗前总控自己重建即可。
- **同源证据（本班亲取，不采信任何自述）**：容器内 `app/` 101、`scripts/` 19、`migrations/` 10 个文件与主树**逐文件 sha256 相等**；容器闸门 `scripts/verify_container_stack.py --skip-build` **22 passed / 0 failed**（`tmp/container_gate_r98.log`）。

## 14. 冒烟计时实测：本文的 73 min 预算作废（2026-09-19 22:1x，主树 `78b8507` 镜像 + 现役容器）

- **单题实测 262.3 s**（一道**非评测题**，走 `/api/v1/ask` 冻结适配器 v2，468 字 / 5 条证据 / `tool_calls=2` / `first_token_at` 有值）。§1 与 §11 里的 `105 × 41.6 s ≈ 73 min` 用的是 09-17 之前的旧 trace 常数，**就地作废**；按 262 s 排窗口 = **7.6 h**，按 41.6 s 排 = 3.7 h 的余量，差一个量级。
- **但 262 s 不是产品应有的单题时延，是坏链路的时延**：那一题里两发 `tier=analysis` 调用各自精确烧满 `read_seconds=120.0 clamped=yes` 然后 `Request timed out.`，而同一时刻 native 链路 `/api/chat` 用 **4.08 s** 答完 115 token（≈28 tok/s，`ollama ps` = `100% GPU`）。机理与修法见跟进单 **§41.2 = R99**（预算常数停在 CPU-only 标定，天花板 120 s 比档自身最坏值 192 s 还低 ⇒ 自己判自己死刑，超时后拿「离线回复」冒充答案）。
- 🔴 **R99 未并树之前，这一轮的 P95 与 correctness 都没有意义**：`[doc] 完成 status=model_unavailable` 的题会被记成一个能过覆盖闸的答案。开窗前先确认 `git log` 里 R98 / R99 已并树。
- 顺带结案 **H11**：`docker exec enterprise-brain-ollama-1 ollama ps` 实取 `qwen3.5:9b  5.3 GB  100% GPU  CONTEXT 4096`。阶段 A「容器真拿到 GPU」这条验收自此有据（之前只看到「日志无 `inference compute` 行」，那是因为压根没打真实推理）。
- **宿主环境坑（本班新踩，写死给下班）**：业主 09-19 21:2x 把 Docker Desktop 与 Ollama 从 C 盘搬到 `E:\Docker` / `E:\Ollama` ⇒ ① `docker` 立刻从 PATH 上消失（PATH 还指着 `C:\Program Files\Docker\Docker\resources\bin`）；② HKLM `SOFTWARE\Docker Inc.\Docker Desktop` 键丢失 ⇒ `Docker Desktop.exe` 起不动（`%LOCALAPPDATA%\Docker\log\host\Docker Desktop.exe.log` 末行 `getting backend binary path: cannot find registry key`）；③ `com.docker.service` 的 `PathName` 仍是旧路径 ⇒ 起不来。**症状不是「服务没起」而是「CLI 根本找不到 docker」**，先按 §5 的端口口径确认 backend 是不是真的还在跑，别急着重试命令。恢复前所有需要 `docker exec` 的前置（P-4/P-5/P-8/P-10/P-12/P-13）都只能读上次取证快照，不能重取。

## 15. P-11 口径重写：仓库侧改读 git，双向都要有豁免名单（2026-09-19 23:3x，总控第二十四班，主树 `73fb71e`）

**为什么必须重写**：旧 P-11 的仓库侧是 `pathlib.Path('documents').glob('*.txt')`。这个 glob 不是「不够严」，是**结构性失明**——任何非 `.txt` 的语料文件从定义上就进不了比对，所以它永远不可能报告「有个文件被 git 跟踪却从来没被种进库」。本班实测：`git ls-files documents` 里有两个 PDF，其中一个（`refactor_guide.pdf`，859,650 B）**从未出现在 `deploy/workspace-seed.json`**，也就是全新装机永远不会种它、检索永远召不回它，而这条事实 P-11 与 P-16 两条闸门同时看不见。方向反过来也一样：库里 4 篇在仓库里没有对应文件，旧口径同样不知道。

**新闸门（一条命令，取代 P-11 全文，并顺手把 P-16 的两个差集并进来）**：

```powershell
& $py scripts\check_corpus_parity.py        # 过 = exit 0；它自己登录取 live 名单
& $py scripts\check_corpus_parity.py --offline    # 没有服务时可跑，只判仓库侧那一桶
```

仓库侧 = `git -c core.quotepath=false ls-files documents`（**全部后缀**），live 侧 = `/api/v1/documents` + `/api/v1/documents/catalog`。五桶语义（`scripts/check_corpus_parity.py:compare`）：

| 桶 | 含义 | 判定 |
|---|---|---|
| `absent_everywhere` | manifest 点名、盘上没有、库里也没有 | **FAIL**：全新装机会少这一篇 |
| `server_only` | 库里在、盘上没有（manifest 已预见） | **WARN**：卷是它唯一副本，跑分报告必须原样抄这一行 |
| `never_seedable` | git 跟踪、既不在 manifest、也没声明豁免 | **FAIL**：这就是 `refactor_guide.pdf` 藏了两周的那种洞 |
| `unexplained_live` | 库里有、仓库和 manifest 都交代不了 | **FAIL**：来路不明的语料 |
| `non_corpus_still_live` | 声明了非语料却还检索得到 | **FAIL**：豁免与现网不一致 |
| catalog `index_status != indexed` | 在架未索引 | **FAIL**（要豁免就得先在 manifest 里写理由） |

**09-19 23:3x 实测基线（本班亲跑，宿主直连 `:8001`，admin）**：`counts: disk=97 live=100 manifest=100 non_corpus=1 tracked=97`；`never_seedable=[]`、`unexplained_live=[]`、`non_corpus_still_live=[]`、`catalog_not_indexed=[]`，唯一 WARN 是 `server_only` 四条 ⇒ **verdict PASS**。跑分前复跑，这六行应当逐字不变；变了就是语料又漂了，先解释漂移再开窗。

- **D11 落盘（业主裁定「按总控建议」）**：`deploy/workspace-seed.json` 新增顶层 `non_corpus` 段，`refactor_guide.pdf` 连同理由登记在内。`AI-Agent学习路线图.pdf` **不在**豁免名单里——它在 manifest 中，属应当入库的语料，别把它和前者混为一谈。`tests/test_corpus_parity.py` 三枚钉保证豁免名单不许空转：声明的名字必须真在 git 里、必须不在 manifest 里、理由必须长到值得读。
- **`server_only` 那 4 条的身份已查实，别再当新发现**：`/app/documents/.document-versions.json` 里四条全是 `owner_id=admin`、`department=''`、`created_at` 集中在 **2026-09-18 22:00:49 ~ 22:01:04**，即浏览器验收那一批探针（`browser_acceptance_policy.txt` 267 B、`六级作文模板.docx`、`深度学习入门：基于Python的理论与实现.pdf` **11.3 MB**、`深度学习技术栈学习路线.pdf`）。`tests/test_seed_workspace.py:24` 的 `SERVER_ONLY_ROWS` 早就把它们钉成闭合集，所以**不许删条目、不许扩名单**——扩名单等于承认又丢了数据，唯一的修法是让文件回到盘上。
- 🔴 **这条直接改变跑分报告的口径**：一次全新装机只能种出 **96 篇**（manifest 100 条里 4 条无文件），而这台机器答的是 **100 篇**。报告抬头写语料数时必须写「100（其中 4 篇仅存于本机卷，不可由装机重建）」，只写 100 是给客户看的假可复现性。
- PDF 算不算出处这条口径**不因本次改动而变**：主规则仍是 95 txt、`29` 行无出处；把 PDF 也算进去会得到 27，而 `chat-02` / `insight-07` 那两次「被 PDF 救回」在 `docs/handoff/2026-09-19-eval-evidence-audit.md` §3.10 已判为**假有据**。复算出 27 的人是把 PDF 算进去了，不是谁算错。

## 16. 开窗机械预检复跑 + 三个会让窗口即死的坑（2026-09-20 00:0x，总控第二十四班，跑分树 `codex/be-eval95` @ `ede64f2`）

本班把「窗口一开就死」能靠 CPU 排掉的都排掉了，全部亲跑，不引用旧结论：

| 预检 | 实取 | 判定 |
|---|---|---|
| 跑分树快进 + 零脏项 | `git merge --ff-only ede64f2` 后 `status --porcelain -uall` = **0 行** | ✅ 主树永远脏（1 万项），开窗只能用这棵树 |
| 冻结三分片完整性 | `r97-shard-{1,2,3}.jsonl` 拼接 **逐字节等于** `tests/fixtures/business_evaluation_100.jsonl`，sha256 前缀 `2230b2b45be18bfb`，24,346 B | ✅ 与登记一致，题源没被碰过 |
| P-7 采集器 dry-run | `collected=105 of 105`，exit 0，产物落 TEMP | ✅ 采集器与夹具接口仍对接 |
| 适配器导入 + `EVAL_SIDECAR` 生效 | `SIDECAR` 解析到 TEMP（`inside_repo=False`），`transport` 可调用 | ✅ 默认值是 `scripts/collect-sidecar.jsonl`，**不设环境变量就是往仓内写** |
| 认证链路（不打模型） | 经 `eval_transport_ask_v2.login()` 真取到 JWT，`token_len=147`、`prefix=eyJhbG` | ✅ 口令、`/api/v1/login`、顶层 `token` 键、`:8001` 直连四项同时对 |

🔴 **三个坑，都是本班亲踩，写在开窗之前**：

1. **跑分树里没有 `deploy/.env.server`**（它被 gitignore，只存在于主树）。在它里面取口令会得到空串 ⇒ `/api/v1/login` **401**（适配器会抛 `HTTPError`，不会假通过，这点好）。⇒ 一切引用 `deploy/.env.server` 的命令，在跑分树上必须换成主树绝对路径 `C:\Users\fengx\PycharmProjects\企业智脑\deploy\.env.server`；compose 的 `--env-file` 同理。口令现值长度 14（不写值）。
2. **P-7 的 `--dry-run` 不经过冻结适配器**：采集器把 `--dry-run` 与 `--transport` 判为互斥（`error: --dry-run already supplies a fake transport; drop --transport`），所以 dry-run 绿**不能**证明 `eval_transport_ask_v2` 能用。⇒ 上表后两行就是为补这个洞而加的；正式开窗前若要再验一次，跑这两行而不是重跑 dry-run。
3. **冻结适配器里的 `chat.py` 行号引用会随并树偏移**。它现在引 `chat.py:1359-1365 / 1364 / 1379 / 1403-1418 / 1177`，而跟进单 §42.3 排队的那笔缓存闸门改动就在 1362 附近 ⇒ 落地后这些引用整体后移。**适配器是冻结件，不许为了对齐行号去改它**；改动并树时在本节记一行「§42.3 使适配器行号引用偏移 +N，行为不变」即可。

**开窗还差的两件事，都不是机械问题**：① R100 未并树 ⇒ 现网每发 analysis 仍是 0 字正文，开窗只会量到 105 个 `no_answer_produced`（§42 表 #5）；② 计时预算要按 R100 的结果重估，§14 的 7.6 h 与旧 73 min 都已作废，compat 关掉思考是 37 s/发、native 是 1.9 s/发，差 20 倍（§42 结论 2）。
