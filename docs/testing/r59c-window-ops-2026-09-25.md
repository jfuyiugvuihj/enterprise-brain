# R59c → 总控排窗操单：§9.3 ①②③ 真机读数窗

- 出单：执行层 Malthus（R59c）｜日期：2026-09-25｜基点：`4e29141`
- 本窗目标：只消 `docs/handoff/2026-09-17-pgvector-adoption-plan.md` §9.3 的 **①②③**。**④⑤⑥不在本窗**（④ 是全量重建、⑤ 要业主拍板、⑥ 是 Chroma 缺陷已由 R211 裁定）。
- 本单（R59c）零容器零服务：下面每一条都是**给总控执行的**，执行层没跑过一发真请求。
- 量具：`C:\Users\fengx\PycharmProjects\be-r59c\scripts\r59c_recall_compare.py`（解释器：`C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`，在树根执行）。

## 0. 一句话摘要

**这窗最短约 70 分钟、推荐排 100 分钟（预算见 §8）**；但**开窗前有一枚硬前置必须先拍**：读后端开关今天翻不动（`INDEX_BACKEND` 是代码字面量，不是 env）—— 见 §1。
今天生产形状 = **A1 chroma-cold**（`HOT_INDEX_ENABLED` 未设 ⇒ 热集关），所以 **A1 臂零改动就能量**，另两臂各需要动一样东西。

## 1. 🔴 硬前置：pgvector 那一臂今天"翻不出来"（先拍这个再排窗）

执行层在零写入条件下实测（`4e29141`）：

```text
把 INDEX_BACKEND=pgvector 塞进进程环境再 import app.rag.indexing
  -> indexing.read_backend()           == 'chroma'
  -> indexing.pgvector_reads_enabled() == False
```

原因：`app/rag/indexing.py:47` 是模块级字面量 `INDEX_BACKEND = INDEX_BACKEND_DEFAULT`（`:45` = `"chroma"`），`read_backend()`（`:2023-2045`）读的就是这枚常量，全仓 `rg 'getenv..INDEX_BACKEND'` **零命中**；`deploy/.env.server` 里也没有 `INDEX_BACKEND` 这一行。
而 `tests/test_r59b_pg_read_switch.py:154` 专门钉着"字面量改掉这条立刻红"（`test_the_switch_defaults_to_the_legacy_engine`）。

⇒ 上面那条取证**在 09-25 之前是真事实、今天是假事实**：R231（并树 `ed9f8b0`）之后，往 `deploy/.env.server` 加一行 `INDEX_BACKEND=pgvector` 再 `--force-recreate`，读路径**会**翻到 pgvector——env 赢常量，`tests/test_r231_*` 钉死，且版本台账 `as_dict() 里的 backend 键` 与 `create_version` 跟着同一个 `read_backend()`，不留半切换。

🔴 但本节这条取证**不能删**，它换了对象：臂身份检查（退出码 3）现在证的不再是「代码没有旋钮」，而是「**这个真在跑的进程**当下确实由它声称的那台引擎答复」。仍会中招的三种做法：① 加了 env 行却只 `docker restart`——env 是容器 **create 时**烘进 `.Config.Env` 的，restart 复用同一份创建配置，照旧由 Chroma 答复；② 只 recreate backend，worker/scheduler 还走旧引擎（三进程共用 `x-runtime` 的 `env_file`，要一起 recreate）；③ 镜像里根本没有 R231 那枚解析器——镜像落后主树时，改 env 等于没改。

### 1.1 三种翻法（总控二选一，按用途分）

| 做法 | 动作 | 改到什么 | 还原 | 用途 |
|---|---|---|---|---|
| **甲：容器内临时注入** | `docker cp` 出 `indexing.py` → 把 `INDEX_BACKEND = INDEX_BACKEND_DEFAULT` 改成 `INDEX_BACKEND = PGVECTOR_BACKEND` → `docker cp` 回去 → `docker restart enterprise-brain-backend-1` | 只改**运行中容器的可写层**；仓、镜像、生产 env 一字未动 | `docker compose ... up -d --force-recreate backend`（可写层丢弃，镜像原样回来） | **本窗量读数用这个**：零版本库改动，且下次 recreate 必丢 ⇒ 不可能漂进生产 |
| ✅ **乙：加 env 钩子**（**已落地：R231，并树 `ed9f8b0`，09-25 12:12**） | `read_backend()` 现先读 `INDEX_BACKEND` env，未设/空白仍回常量 `chroma`；拼错回落 shipped 引擎并落一句告警；env 与常量同时给且不一致 ⇒ **env 赢** | `app/rag/indexing.py` + `tests/test_r59b_pg_read_switch.py` + 新 `tests/test_r231_{index_backend_env,no_half_switch}.py` | 删 env 行即回（且必须 `--force-recreate`，restart 不算） | **生产该用的翻法**：私有化部署里"换读引擎"不该要求改代码重打镜像。🔴 旋钮已在位 ≠ 已合闸：默认仍是 chroma，合闸由总控排窗 |
| **丙：直接翻字面量并 commit** | 改 `indexing.py:47` | 版本库 + 那枚"默认不翻"的钉必红，必须连带改测试 | revert commit | ❌ 不建议在补数窗做：它把"补读数"和"合闸"混成一件事 |

做法甲的两条现场细节（本单在 `Dockerfile` 上复核过，省得窗内试错）：

- 镜像里 `/app/app` 的属主**就是运行用户**（`COPY --chown=10001:10001 app ./app` 在 `Dockerfile:84`，`USER 10001:10001` 在 `Dockerfile:97`）⇒ `docker cp` 进去不需要 `-u root`，也不会改出个跑不动的权限。
- backend 的启动命令是 `uvicorn app.main:app --host 0.0.0.0 --port 8001`（`Dockerfile:106`），**没有 `--reload`** ⇒ 改完文件必须 `docker restart enterprise-brain-backend-1` 才生效；`docker restart` 保留可写层（改动活着），`--force-recreate` 才丢弃它（这就是还原键）。
- 注：`docker exec ... python -c` 看的是**磁盘上那份文件**，不等于正在跑的进程；进程态只认 `answered_by`（§6.4 那把）。
**建议**：本窗用**甲**拿 ①②③ 的读数；读数齐了以后，合闸走**乙**（另立单），别用丙。
用甲时必须如实标注：这量的是"被注入的容器"，不是"某个配置态下的生产部署" —— §9.3 ① 那句"服务内端到端在真库上跑过"能因此消掉，但**"运维到底怎么翻"这一格它不消**。

### 1.2 另外两枚真开关（这两枚是 env，可信）

| 开关 | 位置 | 今天 | 要 A2 chroma-hot 就得 |
|---|---|---|---|
| `HOT_INDEX_ENABLED` | `app/rag/hot_index.py:45,151-154`；`{"1","true","yes","on"}` 才算开，其它一律关 | `deploy/.env.server` 里**没有这一行 ⇒ 关**（生产 = chroma-cold） | 加 `HOT_INDEX_ENABLED=on` + recreate |
| `VECTOR_DUAL_WRITE` | `app/rag/pg_store.py`；compose 在 `docker-compose.yml:161` | `on`（双写在开，R130 NUL 缺陷已修，全库 1008 枚在位） | **本窗不许碰**（碰了就是换被测对象） |

`deploy/.env.server` 经 `x-runtime: &runtime` → `env_file`（`docker-compose.yml:15-17`）被 backend / worker / scheduler 共同继承，**加 env 行不必改 compose**。
🔴 该文件在主树且 gitignored，**归总控管，本单零写入**。改前必备份（§7 第 1 步），改完必须逐字节还原并核 sha256。

## 2. 三臂矩阵（缺一臂就少一项，产物里如实写 null）

| 臂 | 读后端 | `HOT_INDEX_ENABLED` | 要动的东西 | 量具实读的凭证 |
|---|---|---|---|---|
| A1 `chroma-cold` | chroma | 未设 | **零改动**（= 今天生产） | `answered_by` 增量只有 `chroma`；`hot_index.enabled=false` |
| A2 `chroma-hot` | chroma | on | 加 1 行 env + recreate | 增量含 `hot_index`；`enabled=true` |
| B `pgvector` | pgvector | 任意（必然让路） | §1.1 做法甲 | 增量含 `pgvector`；`last_bypass_reason=hot_index_read_backend_switched` |

`--arm` 声明与实读不符 ⇒ 量具退出码 3 并**拒绝出对照**。别绕道 `--no-health-probe` 拿它：那等于自废这一格的凭证。
`keyword_scan` 不算凭证（它是向量腿整个下线时的关键词退化，落在哪一臂都不代表"这一臂的引擎答了"）。

## 3. 开窗前一次性的两件事（各 1 分钟）

1. **备份 env**（还原全靠它）：
```powershell
Copy-Item 'C:\Users\fengx\PycharmProjects\企业智脑\deploy\.env.server' 'C:\Users\fengx\PycharmProjects\企业智脑\deploy\.env.server.bak-r59c' -Force
Get-FileHash 'C:\Users\fengx\PycharmProjects\企业智脑\deploy\.env.server' -Algorithm SHA256 | Tee-Object -FilePath 'C:\Users\fengx\PycharmProjects\企业智脑\deploy\.env.server.sha256-r59c.txt'
```
2. **臂身份冒烟**（零模型，不发问答）：
```powershell
Set-Location 'C:\Users\fengx\PycharmProjects\be-r59c'
`$env:R59C_BASE_URL` = 'http://127.0.0.1:8001'          # 端口映射在 docker-compose.yml:172（127.0.0.1:8001 -> 8001）
`$env:R59C_USERNAME` = 'evalbot'                       # 跑分账号；只有这个 principal 看得见那 100 篇语料
`$env:R59C_PASSWORD` = (Select-String 'C:\Users\fengx\PycharmProjects\企业智脑\deploy\.env.server' -Pattern '^EB_EVAL_PASSWORD=').Line.Split('=',2)[1]
& 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe' scripts\r59c_recall_compare.py preflight
& 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe' scripts\r59c_recall_compare.py census --out "$env:TEMP\r59c_census.json"
```
`preflight` 打印 `status` / `problems` / `search_shape.answered_by` / `hot_index`（`enabled` · `hits` · `resident_chunks` · `max_chunks` · `last_bypass_reason` · `roster_fresh`）—— **这两行决定 A2/A1 谁是今天的真形状，别照抄本文，照它抄**。
`census` 交 ③ 的可选性判定：`selectivity_screen`。现库预期 `NOT_MEASURED`（`classification` 全 1、`department` 全空）—— **这不是失败，这一格的本窗结论就是"仍然量不到，须走 §7 沙盒窗"**。

### 3.3 与计划书 §9.4那条纪律针对的是**直连存储**的跑法：宿主 5432 上挂着没有 `vector_scope` 的野 PostgreSQL（会被悄悄降级成 numpy 估算腿）、`%TEMP%` 下那枚 401 枚的临时 Chroma（不是生产 1008 枚）。

R59c 量具**不连库、不拼 DSN、不开 Chroma**，样本只可能是服务进程正在读的那一份，所以那两类取错对象在本件里是结构上不可能的（臂身份 `answered_by` 再兜一层）。⇒ 宿主跑法可接受，代价只是每发多一跳 loopback（**三臂同一跳，不影响差值**）。

要在字面上也守住 §9.4，就搬进容器跑。🔴 但**镜像里没有 `tests/`**（`Dockerfile:81-84` 只 COPY `migrations`/`scripts`/`deploy`/`app`），所以题集必须自己带进去并用 `--fixture` 指过去：

```powershell
docker cp 'C:\Users\fengx\PycharmProjects\be-r59c\scripts\r59c_recall_compare.py' enterprise-brain-backend-1:/tmp/r59c_recall_compare.py
docker cp 'C:\Users\fengx\PycharmProjects\be-r59c\tests\fixtures\business_evaluation_100.jsonl' enterprise-brain-backend-1:/tmp/business_evaluation_100.jsonl
# preflight/census 不吃题集，先通；collect 才要 --fixture（它是**全局参数**，写在子命令前面）
docker exec -e R59C_BASE_URL=http://127.0.0.1:8001 -e R59C_USERNAME=evalbot enterprise-brain-backend-1 python /tmp/r59c_recall_compare.py preflight
docker exec -e R59C_BASE_URL=http://127.0.0.1:8001 -e R59C_USERNAME=evalbot -e R59C_PASSWORD=…窗内注入 enterprise-brain-backend-1 python /tmp/r59c_recall_compare.py --fixture /tmp/business_evaluation_100.jsonl collect --arm chroma-cold --out /tmp/a1.jsonl --top-k 5 --repeats 2 --max-requests 460
```

口令一律**窗内注入**，值不进文档、不进版本库、不进 shell 历史（用 `docker exec -i ... < 文件` 或运维现场敲）。
🔴 两种跑法都改不了的一件事：**产物别落仓**。落 `$env:TEMP` 或容器 `/tmp`，事后按需挑一份进 `docs/testing/` 入档（R59b 那三份就是这么留的）。

## 4. 热机（必做，否则 `~8 s` 模型加载会吃进 ① 的读数）

上一格踩过：backend 容器 recreate 之后 `ollama ps` 是空的，第一发问答要把模型从磁盘搬进显存，那 `~8 s` 会被记进首臂读数。
**热机必须从 backend 容器里对 ollama 服务发**（容器内 DNS 是 `ollama`，宿主口未必通），字段名是 `keep_alive`，**不是** `keepalive`：

```powershell
# 4.1 generate 腿热机（对话模型，keep_alive 与 deploy/.env.server 的 LOCAL_MODEL_KEEP_ALIVE=15m 同量级）
docker exec enterprise-brain-backend-1 python -c "import json,urllib.request;print(urllib.request.urlopen(urllib.request.Request('http://ollama:11434/api/generate',data=json.dumps({'model':'qwen3.5:9b','prompt':'ping','stream':False,'keep_alive':'15m'}).encode(),headers={'Content-Type':'application/json'}),timeout=300).read()[:200])"
# 4.2 embeddings 腿热机（nomic-embed-text，768 维）
docker exec enterprise-brain-backend-1 python -c "import json,urllib.request;print(urllib.request.urlopen(urllib.request.Request('http://ollama:11434/api/embeddings',data=json.dumps({'model':'nomic-embed-text','prompt':'ping','keep_alive':'15m'}).encode(),headers={'Content-Type':'application/json'}),timeout=300).read()[:120])"
# 4.3 核实两枚模型都在位（期望 ollama ps 里 qwen3.5:9b 与 nomic-embed-text 各一行、100% GPU）
docker exec enterprise-brain-ollama-1 ollama ps
```

🔴 **每一次 recreate / restart 之后都要重做 §4.1+§4.2**（换臂各做一次），否则第一个臂的读数被加载时间污染，而那是 ② 的**唯一被测对象**。

## 5. 采集序列（三臂，每臂一遍；产物一律落仓外 `$env:TEMP`）

解释器与题集都在仓里，产物**不要**落 `scripts/`。发数公式：`planned = 题数 × top_k 档数 × repeats`。

```powershell
Set-Location 'C:\Users\fengx\PycharmProjects\be-r59c'
$py = 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe'
$out = "$env:TEMP\r59c"
New-Item -ItemType Directory -Force -Path $out | Out-Null

# 5.0 形状预演（零网络、零凭据；确认题集 105 / 档位 / 将发多少发）
#       dry-run 不写文件（实测产物路径不会创建），但仍指一枚探针路径，免得看着像往正式臂文件里写
& $py scripts\r59c_recall_compare.py collect --arm chroma-cold --out "$out\dry-probe.jsonl" --top-k 5 --repeats 2 --dry-run

# 5.1 A1 chroma-cold —— 今天生产形状，**零改动**，先跑它
& $py scripts\r59c_recall_compare.py collect --arm chroma-cold --out "$out\a1.jsonl" --top-k 5 --repeats 2 --max-requests 460 --attempts 3 --retry-sleep 5 --gap-seconds 1
#   → 然后按 §1.1 翻到 A2（加 HOT_INDEX_ENABLED=on + recreate）、做 §4 热机，再回来跑 5.2、5.3

注：解释器只有主树那一份（be-r59c 里没有 .venv）；题集与服务常数按脚本自己的树解析，所以必须在树根执行。

# 5.2 A2 chroma-hot —— 需要 HOT_INDEX_ENABLED=on + recreate + §4 热机 + §5.4 暖机
& $py scripts\r59c_recall_compare.py collect --arm chroma-hot --out "$out\a2.jsonl" --top-k 5 --repeats 2 --max-requests 460 --attempts 3 --retry-sleep 5 --gap-seconds 1

# 5.3 B pgvector —— 需要 §1.1 做法甲/乙 + recreate/restart + §4 热机
& $py scripts\r59c_recall_compare.py collect --arm pgvector --out "$out\b.jsonl" --top-k 5 --repeats 2 --max-requests 460 --attempts 3 --retry-sleep 5 --gap-seconds 1
```

### 5.4 A2 臂特有：暖机不暖=热集白跑（别把冷读当热读）

热集是**惰性暖机**（`_warm_hot_index` 在 `app/rag/retriever.py:1016`：一次读花名册 + 一次带 `embeddings` 的读，把 1008 枚向量搬进进程）。它有两个后果：

1. **头几发必然不是热读**，而花名册 TTL 默认 300 s（`HOT_INDEX_ROSTER_TTL_SECONDS`）—— 跑满 105 题（≈9 分钟）中途必然过期重建几次。这是**真实现状**，不要为了好看去调大 TTL（那等于换被测配置）。
2. 所以 A2 正式采集前先烧 2-3 发暖机，并核 `hot_index.resident_chunks` > 0：

```powershell
& $py scripts\r59c_recall_compare.py --limit 3 collect --arm chroma-hot --out "$out\a2-warm.jsonl" --top-k 5 --repeats 1 --max-requests 3   # 暖机批，不进对照
& $py scripts\r59c_recall_compare.py preflight    # 看 hot_index.resident_chunks / hits / last_bypass_reason
Remove-Item -LiteralPath "$out\a2-warm.jsonl"      # 暖机批不作数，删掉免得被误当一臂
```

🔴 **参数位置**：`--fixture` / `--limit` 是**全局**参数，必须写在子命令**前面**（`... --limit 3 collect ...`）；
写后面 argparse 直接 `unrecognized arguments: --limit 3` 退出码 2。其余（`--arm/--out/--top-k/--repeats/`
`--attempts/--retry-sleep/--gap-seconds/--max-requests/--resume/--dry-run`）都是 `collect` 自己的参数，写在后面。
读 `resident_chunks` 为 0 或 `hits` 不涨 ⇒ A2 臂**没在服务**，这一臂的代价列会全 null；先修配置再采，别硬采。

## 6. 出对照（离线，零模型零网络，可以反复跑）

```powershell
& $py scripts\r59c_recall_compare.py compare "$out\a1.jsonl" "$out\a2.jsonl" "$out\b.jsonl" --base chroma-cold --census "$out\census.json" --jsonl "$out\pairs.jsonl" --csv "$out\pairs.csv" --md "$out\report.md" --summary "$out\summary.json"
"EXIT=$LASTEXITCODE"
```

退出码怎么看（**不许合并语义**）：

| 码 | 含义 | 该怎么动 |
|---|---|---|
| 0 | 各臂身份成立且逐题集合一致 | 罕见；核一下双空题计数 |
| 1 | 身份成立，但**至少一题集合/名次不一致** | **这是正常结论**，交人判读，不是失败 |
| 2 | 前置不满足（题集漂移 / 凭据缺失 / 服务不可达 / 命中身份键不可用 / 连续失败触顶） | 不出任何召回结论，先修前置 |
| 3 | **臂身份未证实**（声明与 `answered_by` 增量不符） | 这份读数只有半张脸：多半是没真翻过去（见 §1）|
| 4 | 有题失败或触预算闸，但仍有可用读数 | `--resume` 续跑补齐再 compare |
| 130 | Ctrl-C | 读数在盘上，`--resume` 接着跑 |

## 7. 还原（倒序做，一步都别跳）

**"改完就忘了"是补数窗最容易留下的账**。本窗结束时生产必须回到 A1 chroma-cold（今天形状）。

```powershell
# 7.1 还原 env：把备份原样贴回去，并核 sha256 与备份时记下的一致
Copy-Item 'C:\Users\fengx\PycharmProjects\企业智脑\deploy\.env.server.bak-r59c' 'C:\Users\fengx\PycharmProjects\企业智脑\deploy\.env.server' -Force
Get-FileHash 'C:\Users\fengx\PycharmProjects\企业智脑\deploy\.env.server' -Algorithm SHA256
Get-Content 'C:\Users\fengx\PycharmProjects\企业智脑\deploy\.env.server.sha256-r59c.txt'
Select-String 'C:\Users\fengx\PycharmProjects\企业智脑\deploy\.env.server' -Pattern 'HOT_INDEX_ENABLED|INDEX_BACKEND'   # 期望：零命中（= 回到未设）

# 7.2 若走过 §1.1 做法甲（容器内注入）：force-recreate 丢可写层；若走过做法乙：删 env 行后同样 recreate
Set-Location 'C:\Users\fengx\PycharmProjects\企业智脑'
docker compose --env-file deploy/.env.server -f docker-compose.yml up -d --force-recreate backend

# 7.3 还原证明（一把看代码态）
docker exec enterprise-brain-backend-1 python -c "from app.rag.indexing import read_backend; print('read_backend =', read_backend())"   # 还原后期望 chroma（默认值未翻）。R231 起这一跳真能读到 env，所以它同时也是「env 到进程」的凭据：设了 env 却读出 chroma，就是 recreate 没做到位

# 7.4 还原证明（另一把看服务态，不发问答）
Set-Location 'C:\Users\fengx\PycharmProjects\be-r59c'
& 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe' scripts\r59c_recall_compare.py preflight
```

`preflight` 还原后应当读到：`hot_index.enabled = false`，且 `last_bypass_reason` 不再是 `hot_index_read_backend_switched`（可以是空或 `hot_index_disabled`）。
再补一发 `collect --arm chroma-cold --limit 1`：答复方增量必须回到 `chroma` —— **它才是"闸真落回去了"的证据**，配置字符串不是。

## 8. 时间与请求预算（按 `planned = 题数 × 档数 × repeats` 算）

| 项 | 数值 | 依据 |
|---|---|---|
| 题数 | 105 | `tests/fixtures/business_evaluation_100.jsonl`（自带四道 StructureDrift 闸） |
| 单臂单档单遍 | 105 发 ≈ **8-10 分钟** | 4.08 s/发查询改写（跟进单 §36.6）+ 每发最多 `MAX_REWRITES=5` 发 embedding + 2 拍 `health/details`；同口径参照：R59b 实测 135 **行** ≈ 9-10 分钟/侧 ⇒ 单行 ≈ 4.4 s（那 135 行里含 30 行重复，见量法文档 §1.5 —— 换算成"每分钟多少枚唯一题"时别把它当 135 枚）|
| 三臂 × k=5 × `--repeats 2` | 每臂 210 发、合计 630 发 ≈ **48-60 分钟** | ② 要噪声地板，`--repeats` 必须 ≥ 2 |
| recreate / restart + 热机 × 2 轮 | + 8-10 分钟 | `ollama ps` 从空到 `100% GPU` 约 8 s/枚，还要等 healthcheck |
| A2 暖机批 + `census` / `preflight` | + 5-8 分钟 | 暖机 3 发；花名册 TTL 300 s 中途还会重建几次 |
| **合计** | **≈ 70-85 分钟**（推荐排 **100 分钟**，留一发重跑余量） | |
| 若要 k=5,10,20 三档 | ≈ 150-190 分钟 | 每档都是**独立重发**、不是截前缀；第一次窗建议只做 k=5 |

预算闸：`--max-requests 460`（= 105 × 2 遍 + 余量）。触顶不是坏事 —— 它退出码 4 并把续跑命令行原样打出来。
**别把三臂写进同一个 JSONL**：文件头记 `arm`，`collect` 撞到别的臂直接拒写（两臂混进一份文件就是假对照）。

## 9. §9.3 六格 ↔ 本窗动作对照（排窗前先看这张）

| 格 | 计划书原文 | R59c 给了什么 | 本窗能不能消 | 消它需要的动作 |
|---|---|---|---|---|
| ① | 服务内端到端没在真库上跑过 | 三臂逐题对照 + 臂身份实读 + 四份产物 | **能**（前提：§1 开关先落地） | §5.1〜§5.3 + §6 |
| ② | 热集让路代价没量 | 三臂 paired 公式 + 噪声地板 + NOT_RESOLVED 判定 | **能**（同上；只给方向不算消） | §5 全三臂 + `--repeats 2` |
| ③ | 选择性权限过滤没量 | 影子越权哨 + 可选性硬闸 + 沙盒语料/判据/批单 | **不能在本窗消**：现库无可选性，要业主批沙盒 | §10 独立沙盒窗 |
| ④ | 双写开满一轮全量重建未确认 | 未碰 | ❌ | 另排重建窗（写路径） |
| ⑤ | 遗留库仍在被写要拍板 | 未碰（只复核了形状） | ❌ 要业主拍板 | 见交回「只报不动的账」 |
| ⑥ | 24 题空答复要不要当基线缺陷 | 未碰 | ❌（计划书 §10 已给题号级定量答案） | 业主裁定 |

**消 ①② 的最小验收集**（键路径按 `compare` 的真实产物写，别猜）：

- `cells.9.3-1_service_end_to_end.status == SUPPLIED`（逐题对照读数在位）
- `cells.9.3-2_hot_yield_cost.status == SUPPLIED`（**三臂齐**才是 SUPPLIED；两臂只给 `PARTIAL`）
- `per_arm.<每一臂>.arm_ok_all == true`（有一枚读数身份未证实就是 false）
- `hot_yield.verdict == RESOLVED`；出 `NOT_RESOLVED` / `NOISE_FLOOR_MISSING` 都算**这一格没量出代价**，只是有了方向
- `mixed_leg_records == 0`（任何一臂混着两条腿 = 半切态，见 §11）

`9.3-3_selective_permission.status` 在真生产窗里注定仍是 `NOT_MEASURED` —— 那是语料的性质，不是工具坏了。
③ 在真生产窗里**注定仍然** `NOT_MEASURED` —— 那是它的真形状，不是工具坏了。别为了好看把 admin 一档的 `administrator_scope` 当成"选择性过滤已验"。

## 10. 判据 ③ 的独立沙盒窗（与 §5 那三臂**不混窗**）

③ 的账只能在沙盒里量：现库 `classification` 全 = 1、`department` 全 = `''`，谓词只能全命中或全不命中。
🔴 这是**另一枚窗、另一个库**：不许在生产 `enterprise_brain` 上跑下面任何一条 SQL。

```powershell
Set-Location 'C:\Users\fengx\PycharmProjects\be-r59c'
# 10.1 出料（零库访问、零执行；守卫：库名不是 enterprise_brain_r59c 前缀就退出码 3 且不产文件）
& 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe' scripts\r59c_sandbox_corpus.py plan --out "$env:TEMP\r59c_sandbox" --chunks 48 --sandbox-db enterprise_brain_r59c
# 10.2 交业主拍板三件事（见 $env:TEMP\r59c_sandbox\BATCH.md 末节）：建沙盒库 / 建 5 个合成 principal / 承认合成向量只量谓词不量语义
# 10.3 批准后才动手（另窗，执行人：总控或其指定）
#   createdb enterprise_brain_r59c        （独立实例或独立容器；不许指向生产实例）
#   psql -d enterprise_brain_r59c -f sql\01_scope.sql
#   psql -d enterprise_brain_r59c -f sql\02_table.sql
#   psql -d enterprise_brain_r59c -f sql\03_chunks.sql
#   psql -d enterprise_brain_r59c -f sql\04_indexes.sql
#   psql -d enterprise_brain_r59c -f sql\probes.sql > "$env:TEMP\r59c_probe.csv"
# 10.4 出判据（J-1〜J-5；缺读数一律 NOT_MEASURED，不许把空表印成通过）
& 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe' scripts\r59c_sandbox_corpus.py verify --matrix "$env:TEMP\r59c_sandbox\matrix.jsonl" --corpus "$env:TEMP\r59c_sandbox\corpus.json" --run "chroma-cold=$env:TEMP\r59c\a1.jsonl" --run "pgvector=$env:TEMP\r59c_probe.csv" --json "$env:TEMP\r59c_judge.json"
```

🔴 `--run` 左边的臂名必须与 JSONL **产物头/行内自己记的 `arm` 一致**（写 `chroma=` 会被 `read_service_run` 当成"两臂混进一份文件"直接拒判，退出码 2）。

要服务层量 ③（含 Chroma 侧真谓词）还多一道前置：**跨部门 principal**。生产读路径的 department 取自 **principal**（`app/api/v1/chat.py:3445` `department = str(getattr(principal, "department", ...))`），上传表单里那个 department 会被覆盖 ⇒ 跨部门语料必须先有跨部门账号，再上传 `documents/*.txt`，再 `POST /api/v1/upload`。合成向量的边界写在 `BATCH.md`：它量谓词算术与选择性预过滤，**不量语义质量**。

## 11. 失败模式与停手线（照抄即可判）

| 现象 | 真因 | 该怎么办 |
|---|---|---|
| `collect` 退出码 3，`arm_reason = answered-by-unexpected:chroma` | 声明 pgvector 但服务仍由 Chroma 答 —— **开关没真翻过去**（§1 那条字面量坑） | 先做 §7.3 那把代码态核对；别改 `--arm` 硬凑 |
| `arm_reason = no-semantic-answer-recorded` | 这一发没走到语义腿（多半是 4xx / scope 报错） | 看 `error` 列；若是 403/401 ⇒ 账号 `evalbot` 口令或权限变了 |
| A2 臂 `hot_index.enabled = false` | env 加了但没 recreate（backend 只在进程启动时读） | 回 §7.2 的 recreate；然后重做 §4 热机 |
| 三臂代价列全 null | 漏了 `--repeats 2`，或某臂整臂没读数 | 补重发；产物里 `NO_NOISE_FLOOR` 就是"只给得出方向"的意思 |
| `mixed_semantic_leg = true` | 一发里两条腿都答过 = **半切态**（比不切更难查） | 停手。这一窗的读数只能证明"没切干净"，不能证明任何一侧的性质 |
| 连续 5 发失败自动停 | 服务或模型掉了 | 先 `preflight`；修好后 `--resume` 续跑，别删文件重来 |
| 触 `--max-requests` 退出码 4 | 预算闸（每发都打模型） | `--resume` 续跑；或把 `--limit` 砍到 40 题先出方向 |

**不许动的三样**：`VECTOR_DUAL_WRITE`、`EMBEDDING_MODEL` / `EMBEDDING_DIMENSION`、评测集本身。动了被测对象就换了一件事。

## 12. 事后清点（本窗留下的账要能点数）

`retrieval/debug` "不发答案"是真的，"零写入"是**不**真的：每一发在服务侧落 1 条 `retrieval.completed` trace + 1 条 `retrieval/debug` allowed 审计（详见 `docs/testing/r59c-method-2026-09-25.md` §6）。本窗所有请求的 `request_id` 都以 `r59c-` 开头，可点清：

```powershell
# 总账（TRACE_STORE_PATH 见 docker-compose.yml:34 = /app/data/traces/events.jsonl）
docker exec enterprise-brain-backend-1 sh -c "grep -c 'r59c-' /app/data/traces/events.jsonl || echo 0"
# 分臂账（臂名自带连字符，所以逐臂点名，别拿 [a-z]* 去截）
foreach ($arm in 'chroma-cold','chroma-hot','pgvector') {
  $n = docker exec enterprise-brain-backend-1 sh -c "grep -c 'r59c-$arm-' /app/data/traces/events.jsonl || echo 0"
  "r59c-$arm- = $n"
}
```

期望数量级：每臂 `题数 × 档数 × repeats`（k=5 × 2 遍 = 210 发/臂，三臂 ≈ 630 条），三个分臂数**彼此相等**才对得上。对不上 = 有臂多跑或漏跑（含 §5.4 那批暖机没删干净），读数先别用。
要真零写入得另立单改服务端（写域不在本单），本窗只做到"可辨认、可清点"。

## 13. 排窗建议（给总控的一句话）

1. **今天**：把 §1 那枚前置拍掉（做法甲 / 做法乙）。这一枚不拍，①② 就只是"量具已就位"，不是"数在路上"。
2. **拍完当天**：开 §5 三臂窗，100 分钟，一次跑完 A1→A2→B，跑完立刻做 §7 还原 + §12 清点。
3. **同窗顺手**：`census` 一发（零模型）留 ③ 的现状证物，然后 ③ 另排 §10 沙盒窗（要业主批单）。
4. **别在本窗顺手做**：全量重建（④）、动遗留库（⑤）、追 24 题空答复（⑥）—— 那是三格各自的窗，混窗会把 ①② 的读数搅脏。
