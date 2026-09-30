# R535 —— 上下文配套闸：两枚窗口读数逐跳坐标、闸本体、归因行、反证刀台账

单号 R535 ·执行层 ·工作树 `C:\Users\fengx\PycharmProjects\be-r535`（detached HEAD
`05bec06b3123130805eebae8a73d97da39b6e32d`，自主树 `codex/data-file-catalog` 自建）·日期 2026-09-30。

读数状态（09-30 换席后现取）：run10 在 32/105 处按污染线中止（外来 CUDA 夜间链占卡），总控解除「只写不跑」
⇒ 本纸点名的三批件**已在本树亲跑**，逐批末行读数见 §8；合跑 `295 passed, 8 warnings in 36.78 s`。
窗内纪律期间只做过静态层自查（`py_compile`/AST/`ruff --select F`/字节读数），那些读数仍在 §8 末段。
允许过的自查只有静态层：`python -m py_compile`、AST 现取、`ruff --isolated --select F`、`rg`/字节读数。

🔴 **一枚缺省值都没改**：`MODEL_CONTEXT_TOKENS` / `MODEL_MIN_ANSWER_TOKENS` / `MODEL_TIER_ANALYSIS_MAX_TOKENS`
三枚在册赋值的数字一格没动（§5 给了 `git diff` 的零删除凭据）；`context_limit_exceeded` 的语义与
「刻意不走兜底文案」原样保留（§3.4、§6 K3 那把刀专门对着这一格）。参数该抬到哪一档属业主侧裁量。

---

## 1. 判据①：两串读数链的逐跳坐标（先取证，后动手）

写代码之前先取的证。两串链各自「谁声明、谁读、谁算、谁拒」全部逐跳落到 `file:line`，行号都是
09-30 在本树现取（不是抄旧纸）。

### 1.1 env 侧（本进程按之计算的那一半）

| 跳 | 坐标 | 现取内容 |
|----|------|----------|
| 声明 | `.env.example:335` | `MODEL_CONTEXT_TOKENS=4096` |
| 声明 | `.env.example:253` | `MODEL_MIN_ANSWER_TOKENS=1536` |
| 声明 | `.env.example:213` | `MODEL_TIER_ANALYSIS_MAX_TOKENS=1536`（本档声明输出顶） |
| 读数 | `app/common/model_budget.py:885` | `def context_limit_tokens()`——env 那一半的唯一读数口 |
| 读数 | `app/common/model_budget.py:442` | `def min_answer_tokens()` |
| 缺省 | `app/common/model_budget.py:275` / `:307` | `DEFAULT_CONTEXT_TOKENS = 4096` / `DEFAULT_MIN_ANSWER_TOKENS = 1536` |
| 装配 | `app/common/model_budget.py:693` | `window_plan(...)`：把窗口、输出顶、地板、钟、队一次读齐 |
| 载体 | `app/common/model_budget.py:473` | `class WindowPlan`（同一族第二处在 `:535 prompt_room_tokens`） |
| 算式 | `app/agents/contracts.py:109` | `def prompt_room(context_limit_tokens, declared_max_tokens)`——减法唯一的家（R463 口径） |
| 消费者 | `app/common/model_budget.py:542`、`:121`、`app/agents/nodes.py:925` 一带 | 全部引用 `prompt_room`，没有第二份减法 |
| 拒发 | `app/common/model_budget.py:1285-1290` | `authorize()`：`context_window_code` 命中 ⇒ 先发一行 `report_budget` 再 `raise`（文案在 `:124-133` 的 `ModelContextLimitExceeded`） |
| 拒发落点 | `app/agents/nodes.py:984-994`（预发）与 `:1013-1031`（服务端拒后翻码） | 两条都由 `tests/test_r30_context_limit_guard.py` 钉住 |

> 纸面订正（**归因本轮已改口，两处旧账一起作废**）：`nodes.py` 预发拒发那一格，基点 `05bec06`
> 现取是 `try` `:875` / `except` `:878` / `raise` `:886`——所以在基点上，在册纸写的 `:875-885`
> **仍然对得上**，既不是「过期 3 行」（前班旧账，作废），也不是「过期 110 行·隔着 R524 并树」
> （本纸上一次的错账，作废）。真正的漂移是**本单自己造成的**：本单在这格之前净插 **106 行**
> （`git diff -U0` 现取五枚 hunk 相加＝1+2+1+6+96），于是基点 `:875` → 本树 `:981`、
> `:878` → `:984`、`:886` → `:992`。⇒ 并树之后 `:984-994` 才是活坐标，而这一格被**在册钉**
> `tests/test_r255_refusal_says_the_parameters_are_small.py:5` 的 docstring 手抄着
> （现取该行逐字：`in app/agents/nodes.py:875-885, and its shape is:`）。它是散文不是断言
> ⇒ 并树不会因此咬红（本树现取：单跑该件 `12 passed in 3.19 s`，随批 2 合跑 `184 passed in 19.03 s`
> ——那枚手抄坐标只是散文、不在断言路径上），但**并树那一刻它就成了过期坐标**，
> 按 R346/R455 那一族的口径应改成符号派生。那枚件不在本单写域（K3 的 victim 本身），
> 本席不动它，坐标交回由总控落。

### 1.2 运行时侧（服务端真正在用的那一半）

这一半的关键事实是：**本仓从不把 `num_ctx` 写进任何请求载荷**，所以服务端用多大的窗口服务一问，
不由客户端的任何一次改动决定。凭据逐跳：

| 跳 | 坐标 | 现取内容 |
|----|------|----------|
| 自述 | `app/agents/contracts.py:161-168` | 写明本产品不发 `num_ctx` |
| 自述 | `app/api/v1/observability.py:1750` | 「全仓 `app/**` 无任何一处把 `num_ctx` 发进请求载荷，命中的全是注释与报错文案」（R135·S1 现场查证） |
| 原生腿 | `app/common/model_handler.py:62` + `:555` | `NATIVE_MAX_TOKENS_FIELD = "num_predict"`；载荷只有 `"options": {NATIVE_MAX_TOKENS_FIELD: budget.max_tokens}` |
| 兼容腿 | `app/agents/nodes.py:925` | `"extra_body": {"max_tokens": sized.max_tokens, ...}`——没有 `num_ctx` |
| 服务端缺省来源 | `deploy/docker-compose.server.yml:28-30` | `ollama:` 那一格只有 `<<: *log-rotation` 与 `restart: always`，**没有 `environment:`**（`:35`、`:41` 那两格是 backend/worker 的） |
| 同上 | `deploy/.env.server.example:36` | 只有 `OLLAMA_IMAGE_TAG=latest`；全仓 `OLLAMA_CONTEXT_LENGTH` 零命中 |
| 可现读通道一 | `docs/perf/raw/rate_all.jsonl:2` | `JSONL {"case":"runtime","ollama":"0.34.0","loaded":[{"name":"qwen3.5:9b","context_length":4096,"size_vram":0}]}` |
| 通道一取法 | `scripts/perf_probe_rate.py:179` | `"loaded": [{"name": m["name"], "context_length": m.get("context_length"), ...}]` |
| 通道一口径 | `docs/handoff/2026-09-15-orchestration-board.md:1013-1015` | 写明 `context_length: 4096` 是 **`/api/ps` 运行时实测值，不是仓库配置项**（`git grep context_length -- .env.example docker-compose.yml` = 0 命中） |
| 可现读通道二 | `docs/perf/raw/rate_prefill.jsonl:8` | 服务端拒发原文：`request (4402 tokens) exceeds the available context size (4096 tokens), try increasing it` |
| 识别片段 | `app/common/model_budget.py:361-370` | `CONTEXT_ERROR_FRAGMENTS` 里已有 `available context size` / `n_ctx` 等枚枚片段——通道二不是新发明的 |

⇒ 本单的闸就照这两串链接：声明那一半**引用** `window_plan`（不重算、不另开口），运行时那一半
走 `/api/ps` 与拒发原文两条既有通道（§3）。

---

## 2. 三处纸面不符（总控要拿去订正对业主的说法）+ 一枚「未验」

1. **(a) 两枚键都不在 `app/common/model_config.py`。** 现取该文件 279 行（改动前）对
   `MODEL_CONTEXT_TOKENS` / `MODEL_MIN_ANSWER_TOKENS` **零命中**；家在读数口
   `app/common/model_budget.py:885` 与 `:442`。本单把闸本体落在 `model_config.py` 是**新增**，
   不是「去它已有的地方补一格」——原派工词的行址描述会误导验收。
2. **(b) 键名是 `MODEL_MIN_ANSWER_TOKENS`（带 W）。** 纸面写成 `MODEL_MIN_ANSWER_TOKEN` 的都在别处；
   而 `.env.example:253`（原 `:141` 那一格的说法）**与此键无关**——`rg` 现取那一行附近三枚候选行
   都不是这枚键。
3. **(c) 「先给答案留 `MODEL_MIN_ANSWER_TOKENS` 才剩 2560」这句归因不成立。** 守卫减的是**本档声明输出顶**
   （analysis = `MODEL_TIER_ANALYSIS_MAX_TOKENS=1536`，见 `.env.example:213-215` 与
   `app/common/model_budget.py:662` 的 `prompt_room = n_ctx - max_tokens`），与地板无关。
   `4096 − 1536 = 2560` 与地板同数是**巧合**。地板是一枚测量值（R255 判据④：它不参与拒发算式，
   调它一个 token 也塞不进去），不是窗口旋钮——本单的归因行明写了这一句。
4. **「A100 80G 仍按 4096 服务」记「未验」。** 仓内出处 `app/common/model_budget.py:494-495` 自己标注
   **业主口径**、零实测；外部 Ollama 文档自 0.15.5 起按显存分档（<24GiB→4k、24–48→32k、≥48→256k）。
   本机 `/api/ps` 那条读数（§1.2）是 `qwen3.5:9b` 在 4096、`size_vram: 0`，**证不了 A100 那一格**。
   ⇒ 本单既不改缺省，也不裁那句，只把它记成未验。

> **采纳记（总控 09-30 换席令，本席落笔）**：上面 (a)(c) 两条采纳。另作废两枚旧账——本单前班把
> 「在册纸面行号过期」记成 **3 行**（作废），本班一度改口成 **110 行·R524 并树所致**（**同样作废**：
> 现取是 **106 行**，且是本单自己的插入造成的，基点上那格与纸面仍对得上；推导与逐枚 hunk 见 §1.1
> 末尾那一条订正）。
> 两枚读数口与两枚缺省常数（`model_budget.py:885`/`:442`/`:275`/`:307`）的家全在
> `app/common/model_budget.py`；派工词把家写成 `model_config.py` 是总控自曝的笔误，本纸全程按现取走，
> 没有沿用那两个错坐标。并树复核：`05bec06..1a23445` 改过 17 枚文件，**本单四枚写域件一枚未碰**；
> §1.2 引的 `orchestration-board.md:1013` 在两枚基线上行号一致（上游那 +68 行落在别处）。

---

## 3. 判据② 的闸本体：两枚读数一次到手，两个方向都判，缺席不洗绿

### 3.1 新增落点（全部在本单写域内）

- `app/agents/contracts.py:288-575`（`:288` 起是 R535 分隔注释，符号从 `:309` 的 `CONTEXT_PAIRING_MARKER` 起；`:575` 是 `context_refusal_attribution` 的 `return line`，`:576-577` 两枚空行之后才是 `:578 class ArtifactRef`）：`CONTEXT_PAIRING_MARKER`、三枚键名常数、四枚判读词
  （`paired` / `env_above_runtime` / `runtime_above_env` / `runtime_unread`）、`PAIRING_ACTIONABLE`、
  `PAIRING_SLACK_RATIO = 2`、frozen dataclass `ContextPairing`、纯函数
  `evaluate_context_pairing(...)`（`:396`）、归因句 builder `context_refusal_attribution(...)`（`:540`）。
- `app/common/model_config.py:257-459`（`:257` 是 R535 分隔注释，`check_context_pairing` 的
  `return` 落在 `:458`，`:459` 起两枚空行之后是既存的 `:461 get_local_model_settings`）：运行时那一半的**读数与缓存**——`/api/ps` 通道
  （`runtime_window_from_ps_payload` `:302`）、拒发原文通道（`runtime_window_from_refusal` `:324`）、
  记录与复位（`:342` / `runtime_context_window_state`）、带 TTL 的探针
  （`observe_runtime_context_window` `:389`，走既有 `_fetch_registry`，**永不抛**）、
  以及闸本体 `check_context_pairing`（`:428`，两半各引用一次，一处都不重算）。
- `app/agents/nodes.py:271-359`：启动把手 `_log_context_pairing`（`:280`，按判决记名，
  同一判决只说一句）、服务端数回收 `_harvest_runtime_window`（`:321`）、拒发归因行
  `_log_context_refusal`（`:336`）。接线点五枚，全是既有边界：`:1281`（`_make_model`，与
  `_log_thinking_mode` / `_log_keep_alive_mode` 同一处）、`:991`（invoke 预发拒发）、
  `:1027-1028`（invoke 服务端拒发）、`:1158`（stream 预发）、`:1183-1184`（stream 服务端拒发）。

### 3.2 形状上的三条硬要求

1. **零重算**：减法仍只在 `contracts.py:109 prompt_room`；`clock/queue` 付得起的最宽窗口仍只在
   `WindowPlan.maximum_coherent_context_tokens`。闸交出的每个数都是从这两处**引用**来的
   （反证刀 K1b 专治「写死成 4096」这种假绿）。
2. **不开口**：不新开任何对外路由（`tests/test_r535_context_pairing_gate.py::test_the_gate_opens_no_new_public_route`
   逐枚 AST 扫三棵写域件）；`/health/details` 那一格**没接**，见 §7 未达格。
3. **不开旋钮**：`RUNTIME_WINDOW_TTL_SECONDS` 是常数；R535 那几枚函数里 `getenv` 零命中
   （`test_the_gate_mints_no_new_knob` 当场扫源码）。

### 3.3 两个方向的措辞都带证据

- `env_above_runtime`：「不配套：`MODEL_CONTEXT_TOKENS=8192`（来源 env）声明得比运行时给得起的多，
  服务端只到 4096（来源 api/ps），差 4096 枚」——并点明后果是「本该零成本挡下的一问变成一发白烧的往返」。
- `runtime_above_env`：只有服务端宽到**两倍以上**才叫「白留着容量」（凭据是 `.env.example` 上方那对
  实测：同一条 2154-token prompt 在 `num_ctx` 4096 / 8192 下 prefill 66.683 s / 68.849 s）；
  不足两枚只报方向。这一格由反证刀 K8 对着。
- `runtime_unread`：只说「只读到一侧」，**既不当绿灯也不当红灯**（K9 对着把它算成可行动的那一型）。

### 3.4 判据④ 的形界（语义一格没动）

四枚判读词**不在** `ErrorEnvelope.code` 的封闭枚举里（`test_the_verdicts_are_not_public_error_codes`
逐枚 `get_args` 扫），`context_limit_exceeded` 仍是唯一那枚码、仍不可重试、仍**绝不**接进兜底文案；
`app/api/v1/chat.py:2924` 兜底句、`app/agents/evidence.py:314` `ErrorEnvelope.message`、
`app/trace/**`（在途 R523 写域）一格未碰。

---

## 4. 判据③ 的归因行：一发一行、只吃整数、按构造吃不进正文

撞顶那一发旁边多出来的是**独立标记**的一行（`[ContextPairing]`，不是第二枚 `[ModelBudget]`）：

```
[ContextPairing] 本问需要 4353 枚 token 槽位（prompt 2817 + 本档声明输出 1536），当前
MODEL_CONTEXT_TOKENS=4096 只给资料留 2560 枚，还差 257 枚；要调的是 MODEL_CONTEXT_TOKENS 与
服务端 num_ctx 这两枚，两枚必须配套动——单改一头要么没用要么把机器撑爆；改完要 recreate 容器
（env_file 在建容器那一刻才解析，单改文件与 docker restart 都不生效）。MODEL_MIN_ANSWER_TOKENS
不是窗口旋钮：没有一问是因为它被判拒的。 配套自检：<判读句>
```

- 「一发一行」的在册性质保住：`[ModelBudget]` 仍恰一枚（邻件与 `tests/test_r30_context_limit_guard.py:231`、
  `tests/test_r255_refusal_says_the_parameters_are_small.py:162` 原样绿；反证刀 K11/K12 就是对着这一格配的牙）。
- **正文按构造进不来**：`context_refusal_attribution` 的参数只有 `budget` / 一枚整数 / 可选的
  `ContextPairing`，而 `ContextPairing` 每个字段都是整数或键名（`inspect.signature` 那枚格钉着）。
  端到端那格用 2817 槽的 canary 提示词撞顶，逐条 `caplog` 记录 + 异常字符串 + 证据袋 JSON 三处都验
  canary 不出现（canary 数=`机密采购价目表`，现取 2813 字→2817 槽）。
- 服务端拒发那一支同样只摘整数：`_harvest_runtime_window` 把 `4096` 摘进台账后即丢原文，
  且模式**故意不收 `n_ctx=`** 写法——本仓自家那句拒发文案里就有 `n_ctx=4314`，收了就是拿
  引起撞顶的那枚数给「配套」作证（`test_the_servers_json_n_ctx_is_read_but_our_own_claim_is_never_read_back`）。

---

## 5. `.env.example`：只加注释，一数字未动

`git diff --unified=0 .env.example` 现取两枚 hunk：

```
@@ -245,0 +246,7 @@    （MODEL_MIN_ANSWER_TOKENS=1536 上方：地板不是窗口旋钮）
@@ -304,0 +312,23 @@   （MODEL_CONTEXT_TOKENS=4096 上方：配套两枚键、两个方向的后果、
                        [ContextPairing] 启动行、/api/ps context_length + 两本 raw 台账、
                        不 recreate 等于没改）
```

`git diff --numstat` 交回 **`30 0 .env.example`**——删除行 0 枚，这就是「缺省值一枚都没改」的盘面凭据。

---

## 6. 反证刀台账（`tests/test_r535_counter_evidence_teeth.py`，十三把）

机械沿用 R524：影子里摘刀、`exec` 回挂、`monkeypatch` 复原、影子只落 `tmp_path`、
🔴 被跟踪件**摘前摘后各核一次 sha256**、末了总清两枚格（刀与牙的清点 + 指纹与影子件残留）。
本班新踩并治好的一格：**按值导入**（`from X import f`）不会被源模块的影子覆盖，所以 K2/K11
这类刀的 victim 走按值绑定 ⇒ `_cut(..., consumers=(...))` 把影子同时挂回消费件；不带这一格那两把会咬不动。

| 刀 | 摘掉的那一格 | victim（在册钉本身） | 盘上写口 |
|----|--------------|----------------------|----------|
| K1 | `check_context_pairing` 读运行时那一格 → `None` | 判据② 闸本体格（`test_the_gate_reads_both_halves_...`） | 零 |
| K1b | 同一函数读声明那一格 → 写死 4096 | 「跟着 env 变」那一格 | 零 |
| K2 | `evaluate_context_pairing` 的 `if runtime < declared:` → 永真 | 反方向格 + 同宽格（两枚） | 零 |
| K3 | `invoke` 预发拒发的 `raise` → `return self._offline_fallback(...)` | `test_r30...:144` + `test_r255...:199`（🔴 在册钉本身） | 零 |
| K4 | `_log_context_refusal` 不再问闸（`pairing = None`） | 归因带配对话那一格 | 零 |
| K5 | `invoke` 服务端拒发处不摘数 | 台账拒发→闸读数那一格 | 零 |
| K6 | `_make_model` 里的启动把手整行 | 启动一行那一格（+源文侧谓词归零） | 零 |
| K7 | 启动把手 `except` 改成往上抛 | 自检炸了不许塌建图那一格 | 零 |
| K8 | `PAIRING_SLACK_RATIO` 2→1 | 不足两倍那一格 | 零 |
| K9 | `PAIRING_ACTIONABLE` 把 `runtime_unread` 也算可行动 | 缺席不许当绿灯那一格 | 零 |
| K10 | `evidence._ERROR_CODES` 摘掉 `context_limit_exceeded` | `test_r30...:158`（🔴 码不许被降级） | 零（写域外，内存动） |
| K11 | `authorize` 的拒发行打成两行 | `test_r255...:162`（🔴 一发一行） | 零（写域外，内存动） |
| K12 | 归因行标记换成 `[ModelBudget]` | `test_r30...:231`（一发一行） | 零 |

**进门指纹（09-30 本树现取，摘刀前后与总清那一格都读这张表）**：

```
18740eb2b819d2726204aa16f0390bae6e25e36bd0e0cea8739b85268908f999  app/common/model_config.py
2a0867bf9f47fc6cd6649dad8cece49920d23f8fa3bc10fe0bba0fef8ff18f0e  app/agents/contracts.py
4ec795203a0cfc552a5b95ba2059d9cd1455b46d9bf334708c4143c107611e8b  app/agents/nodes.py
b240ffd8379960e9ccd529d4b99dcfe6fe7fc285d8475c78687dfd591341de69  app/common/model_budget.py
a27c8e776bc80b9f7f3d3f46592b23e9f68d834c11d2035bb9d2332e776a3176  app/agents/evidence.py
4c2bba7d121a305f8f4bdead00d8b3dd81d51daf553ec993a953c3c4860b7f95  .env.example
00d267e8e2cc817dfc39c6e9a709803937642ccf658a0076c32a6b163e5987b3  tests/test_r535_context_pairing_gate.py
7f16b5b3e7f521f110dab6a1edbdd917aa8a26a13342fcca09cac868b7c5316d  tests/test_r535_counter_evidence_teeth.py
8bca7f0603a26b31dcfd9c63532874edfca327275ae37f0c4f56c089af096e7e  tests/test_r30_context_limit_guard.py
8d32442ad19c823121e3b51309d9f680f41e0e65e11a09ff87c7c7cb5f42c4e1  tests/test_r255_refusal_says_the_parameters_are_small.py
```

- 十枚全在 `TRACKED` 里 ⇒ K3/K10/K11/K12 用到的**在册钉一字节未改**（`test_z13b` 按 sha 自证）。
- 仓内不落影子件：`_shadow_file` 断言目标不在 `REPO` 之下，总清那一格再扫一遍
  `r535_shadow_*.py`（根目录 / `tests/` / `app/`）。
- 每把刀都先跑正控（`edits=()` 或不摘刀的属性原样），victim 必须先绿一遍才算牙。
- **交回状态（已亲跑）**：`pytest tests/test_r535_counter_evidence_teeth.py -q -p no:randomly` →
`28 passed in 5.82 s`。十三把刀的「正控＋摘刀」成对格全绿，两枚总清格同绿 ⇒ 每把都真摘过、点名的
十五枚在册钉全真咬红、十枚被跟踪件摘前摘后 sha256 一致、仓内无影子件残留（机械自证，比本表快照更硬：
`FINGERPRINT_AT_IMPORT` 是 import 现取的）。对着拒发判决与「一发一行」的六对（K3/K4/K5/K10/K11/K12）
单跑：`12 passed, 16 deselected in 4.34 s`。
K10/K11 依上一席裁定放行（写域外只做内存影子、盘上零写口）；两把的「摘前绿」正控格分别是
`test_k10_positive_control_the_code_reaches_the_client_undegraded`（咬 `test_r30_context_limit_guard.py:158`）
与 `test_k11_positive_control_the_refusal_line_is_still_one_line`（咬
`test_r255_refusal_says_the_parameters_are_small.py:162`）——受害者名字就是那两枚在册钉本身。

🔴 本班踩到并当场治好的一格（禁洗绿的反面：也别把真红记成没红）：`_bite` 原先接 `Exception`，而
「摘掉 raise」那种摘法抛的是 `Failed: DID NOT RAISE`——`Failed` 继承的是 `BaseException`。首跑 8 枚红里
有一枚就是这个形状：K3 明明咬中了 r30 那枚钉（日志里可见 `[ContextPairing]` 归因行与红话原文），却被
机械漏记成「一次都没被摘红」。已改接 `BaseException` 并把理由写进机械 docstring。其余七枚红是邻件
断言取巧（把「还没到『白留着』那一格」这句诚实话当成违规）、假件自调用污染计数、以及拿判决字面量
去归因散文里找——三处都是测试件的错，产品件一字未改。

---

## 7. 未达格逐枚点名（差的是坐标，不是努力）

1. **`app/common/monitoring.py:211-219`（判据②「要能在既有读数出口上读到」那一格）**——闸本体
   `check_context_pairing()` 与 `as_dict()` 已经交回 JSON 形状，但把它挂进 `/health/details` 的
   快照要改这枚文件，而总控按 R524 先例**没给写域**。⇒ 交回函数与日志行，坐标由本席另落。
2. **屏上那一行的接线（`app/api/v1/chat.py:2924` 兜底句 / `app/agents/evidence.py:314`
   `ErrorEnvelope.message`）**——本单只交归因句 builder（只吃整数与键名）与域内那枚独立标记日志行；
   要不要把同一句话送到客户屏幕上、送到哪一格，归总控裁。两枚坐标均未碰。
3. **span 上带配对话**——`app/trace/spans.py:142-146` 的 `span.finish(...)` 只收
   `status` / `error_code` / `summary`，加字段要动 `app/trace/**`（在途 R523 写域）。
   本单没加，也没改那三枚在册标记的性质。
4. **真机读数（`/api/ps` 在活服务上量得到 `context_length`）——仍记未验，但拦着它的前提已换**：
   run10 在 32/105 处按污染线中止（外来 CUDA 夜间链占卡），「窗内不许起 pytest」这一条**不再成立**，
   本单点名的三批已按 §8 在本树亲跑。今天拦着这一格的是本单硬约束里的**禁打模型·禁起容器**：要证
   「通道量得到数」就得往本机 11434 发那一发读取，执行层无权起。仓内凭据只有 §1.2 通道一那枚历史读数
   （`docs/perf/raw/rate_all.jsonl:2`，`context_length: 4096`，ollama 0.34.0）与假 transport 的端到端钉
   （后者证形状、不证真机）。⇒ **未验**；要补就一发 `Invoke-RestMethod -Uri http://127.0.0.1:11434/api/ps -Method Post -Body '{"model":"<在册模型>"}'`
   读 `.loaded[].context_length`，由本席或业主侧在活服务上取。
5. **判据② 第三问「两枚单改一头各会出什么形状」的对外文档口径**——已写进 `.env.example`
   注释与本纸 §3.3；`docs/api/contract-v1.md` 未碰（在途 R523 写域），若总控要契约里也有
   那一节，本席另落。

---

## 8. 代跑清单（命令原文）＋解锁后本席亲跑读数

**本单两枚新件（点名件）**：

```powershell
pytest tests/test_r535_context_pairing_gate.py tests/test_r535_counter_evidence_teeth.py -q -p no:randomly
```

**邻件合跑（写域相邻、可能被日志行与码表影响的那几枚）**：

```powershell
pytest tests/test_r30_context_limit_guard.py tests/test_r255_refusal_says_the_parameters_are_small.py `
  tests/test_r204_budget_refusal.py tests/test_r445_pack_priority.py `
  tests/test_r448_deterministic_refusal_no_retry.py tests/test_r463_pack_room_shares_the_guard_source.py `
  tests/test_r102_stream_slot_release.py tests/test_r110_stream_drop_closes_span.py `
  tests/test_error_code_vocabulary.py tests/test_r142_error_code_table_sync.py `
  tests/test_r74_dead_budget_field.py -q -p no:randomly
```

**模型腿与发现腿（本单动了 `model_config.py`，必须复跑）**：

```powershell
pytest tests/test_model_discovery_selection.py tests/test_private_model_routing.py `
  tests/test_compute_wiring.py tests/test_gpu_compute_honesty.py tests/test_offline_runtime_fallbacks.py `
  -q -p no:randomly
```

- **逐批末行读数（09-30 亲跑；树 `be-r535` dirty 态；解释器 `企业智脑\.venv\Scripts\python.exe`
  py3.11.7；`app -> C:\Users\fengx\PycharmProjects\be-r535\app\__init__.py` 已当场核过）**：

| 跑的是哪一组 | 末行读数 |
|--------------|----------|
| 批 1：两枚 r535 新件 | `60 passed in 7.32 s` |
| 批 2：邻件 11 枚 | `184 passed in 19.18 s` |
| 批 3：模型腿与发现腿 5 枚 | `51 passed, 8 warnings in 17.87 s` |
| 三批合跑（同一进程 18 枚件） | `295 passed, 8 warnings in 36.78 s` |
| 判据② 组（闸本体＋两半读数＋两条通道，20 格） | `20 passed, 12 deselected in 2.19 s` |
| 判据③ 组（归因行＋端到端＋构造性排除，3 格） | `3 passed, 29 deselected in 2.83 s` |
| 判据④ 组（不开口·不开旋钮·不进码表·把手一处，7 格） | `7 passed, 25 deselected in 4.37 s` |
| 缺省值未改＋尺子自证（2 格） | `2 passed, 30 deselected in 2.70 s` |
| 反证十三把刀 | `28 passed in 5.82 s` |
| 其中 K3/K4/K5/K10/K11/K12 六对 | `12 passed, 16 deselected in 4.34 s` |

- **`-k` 分组的命令原文（collect 口径必须写死，否则对不上数）**：四组判据一律只点 gate 那一枚
  （现取 collect = **32** 枚），两刀组一律只点 teeth 那一枚（现取 collect = **28** 枚）。

```powershell
pytest tests/test_r535_context_pairing_gate.py -q -p no:randomly -k 'gate_reads or claimed_half or env_wider or reverse_direction or narrower_gap or equal_windows or unobserved or room_subtraction or resident or shipped_pair or absence or widest or unanswerable or throttled or empty_answer or reading_state or servers_own or servers_json or provider_refusal'
pytest tests/test_r535_context_pairing_gate.py -q -p no:randomly -k 'refused_customer_question or carries_the_pairing or takes_nothing_but_counts'
pytest tests/test_r535_context_pairing_gate.py -q -p no:randomly -k 'opens_no_new_public_route or verdicts_are_not_public or mints_no_new_knob or wired_once_at_the_model_factory or once_per_verdict or absent_half_out_loud or broken_probe'
pytest tests/test_r535_context_pairing_gate.py -q -p no:randomly -k 'shipped_defaults_are_untouched or prompt_ruler'
pytest tests/test_r535_counter_evidence_teeth.py -q -p no:randomly
pytest tests/test_r535_counter_evidence_teeth.py -q -p no:randomly -k 'k3 or k4 or k5 or k10 or k11 or k12'
```

- **解锁后本席亲跑（09-30 16:00 前后，run10 已中止；解释器 `企业智脑\.venv\Scripts\python.exe`
  py3.11.7 —— 注意 PATH 上的 `pytest` 指向 `C:\Users\fengx\anaconda3\Scripts\pytest.exe`，
  复跑请用 venv 的 `python.exe -m pytest`，否则读数不可归因）**：

| 组 | collect 口径 | 末行读数（本轮现取） |
|----|--------------|----------------------|
| 批 1：两枚 r535 件 | 32 + 28 = 60 | `60 passed in 6.73 s` |
| 批 2：邻件 11 枚 | — | `184 passed in 19.03 s` |
| 批 3：模型腿与发现腿 5 枚 | — | `51 passed, 8 warnings in 17.59 s` |
| 三批合跑（同一进程 18 枚件） | 60 + 184 + 51 = 295 | `295 passed, 8 warnings in 39.87 s` |
| 判据② 组 | gate-only 32 | `20 passed, 12 deselected in 3.18 s` |
| 判据③ 组 | gate-only 32 | `3 passed, 29 deselected in 2.67 s` |
| 判据④ 组 | gate-only 32 | `7 passed, 25 deselected in 4.88 s` |
| 缺省值未改＋尺子自证 | gate-only 32 | `2 passed, 30 deselected in 3.35 s` |
| 反证十三把刀 | teeth-only 28 | `28 passed in 6.48 s` |
| 其中 K3/K4/K5/K10/K11/K12 六对 | teeth-only 28 | `12 passed, 16 deselected in 4.48 s` |

  上面那一版表与这一版**逐行同数**（只差 elapsed）。同一批 `-k` 表达式若把两枚 r535 件一起点名
  （collect = 60），判据②/④ 会变成 `24 passed` 与 `8 passed`——那是反证件里有同名关键词的用例被
  一起选中，不是回归，也不是洗绿；所以口径按上面的文件目标写死。每批 R56 自证原样：
  `blocked connect attempts to host model port: 0`、`offline discovery stub calls: 0`（批 3 与合跑那
  两枚是 `1`，出自 `test_private_model_routing.py:12` 的 `importlib.reload`，conftest 自记既存）。
- **内联修复后的末批亲跑（09-30 17:01-17:08，同一棵树）**：批 1 `60 passed`、批 2 `184 passed in 9.98 s`、
  批 3 `51 passed, 8 warnings in 15.70 s`——**三批枚数与修复前逐批同数**（60/184/51），合跑仍是
  `295 passed, 8 warnings / exit=0`。⚠️ 批 1 那一枚 elapsed 报 `130.10 s`（同批先前 6.73 s）不是本单变慢：
  另一席 `be-r547` 在 17:03 起了自己的 pytest（现取 `Win32_Process` 见 `-m pytest C:\...\be-r547\tests…`），
  同机争用把 elapsed 拉高；**枚数与 exit 不受影响**，总控复跑时别拿这个数做回归判据。

- **§10 坐标订正（本轮现取）**：流式翻译块止于 `app/agents/nodes.py:1186`（`:1187` 是下一段的
  `from app.trace.spans import error_code_for`，不属于翻译块），原写 `:1184-1188`；本轮 logger 内联修复后再漂 −1，终值 **`:1183-1186`**。

  8 枚 warnings 是既存的 FastAPI `on_event` 弃用与 `jwt` HMAC 键长告警，出自 `test_compute_wiring.py`
  那一腿，与本单无关、未动。每批末尾的 R56 闸门自证：`blocked connect attempts to host model port: 0`、
  `offline discovery stub calls (no socket opened): 0`（批 3 那枚 `1` 出自 `test_private_model_routing.py:12`
  的 `importlib.reload`，conftest 自己写明是既存行为，不是本单引入）。
- 反证件里的 K3/K10/K11/K12 会**直接调用**在册邻件的钉函数 ⇒ 建议按上面的合跑顺序在同一进程里跑，
  别把 `-k` 拆散（拆散不改变结论，只是正控/摘刀两两成对，同文件内自洽）。
- 全量门（`python scripts/run_gate.py`）属总控独占动作，执行层未跑、也不会请求代跑。
- 静态层自查读数（这一层是真取到的）：`py_compile` 四枚产品件 + 两枚新件 rc=0；
  `ruff check --isolated --select F` 对六枚件 rc=0（`nodes.py` 的 `os` 未用与一枚 f-string 是
  HEAD 上就有的既存项，与本单无关，未动）；两枚新件的 victim 名字与参数表 AST 现取全部解析；
  十三把刀的锚点在现盘上各自**恰好命中一次**。

---

## 9. 盘面数字（09-30 交回时现取）

```
$ git status --porcelain
 M .env.example
 M app/agents/contracts.py
 M app/agents/nodes.py
 M app/common/model_config.py
?? docs/testing/r535-context-window-pairing-2026-09-30.md
?? tests/test_r535_context_pairing_gate.py
?? tests/test_r535_counter_evidence_teeth.py

$ git diff --numstat
30	0	.env.example
291	0	app/agents/contracts.py
119	3	app/agents/nodes.py
210	1	app/common/model_config.py
```

- `nodes.py` 的 3 枚删除行全在本单的接线处（导入块两枚 + 注释收尾一枚），无缺省值行。
- 🔴 **并树目标口径（本班现取更正）**：交回时主树已是 `e9f7ee8`（不是换席令里的 `1a23445`——其间已并
  R536 `7e1c221`（动 `chat.py` +24）与 R548 `f312eeb`（动 `queue_worker.py`））。四枚写域件在
  `05bec06` 与 `e9f7ee8` 上 **blob 逐枚全等**（`git rev-parse` 现取四对相同短哈希）；本单补丁在
  `e9f7ee8` 的导出了树上 `git apply --check` 现取 **rc=0**（四枚逐件 `Checking patch …` 通过）；
  三枚新件在 `e9f7ee8` 上零同名（`git cat-file -e` rc=128）⇒ **铺树零交叠、零撞名**。
- 行号漂移的另一笔：本单内联修复（§11）减掉一行，`nodes.py` numstat 由 `120/3` 变 **`119/3`**，
  319 行之后全体坐标 −1（`:985-995`→`:984-994`、`:1013`→`:1012`、`:1282`→`:1281`、
  `:1184-1185`→`:1183-1184`、`:322/:337`→`:321/:336`、`nodes.py:926`→`:925`）——纸里已全部改齐，
  残留旧坐标扫描 14 枚全 0 命中。
- `model_config.py` 的 1 枚删除行是 `from typing import Callable`（换成
  `from typing import TYPE_CHECKING, Callable`，为的是 `check_context_pairing` 的返回类型能被
  静态读到；运行时导入仍留在函数里）。
- 枚数（AST 现取 + `--collect-only` 双口径，09-30 复取）：闸件 `tests/test_r535_context_pairing_gate.py`
  749 行 / **31 枚 `def`＝pytest collect 32 枚**（`test_an_unobserved_server_is_never_printed_as_paired`
  参数化出两格，所以两口径差一枚，不是漏收）；反证件 `tests/test_r535_counter_evidence_teeth.py`
  639 行 / 28 枚 `def`＝collect 28 枚（十三把刀的「正控 + 摘刀」成对格，加两枚总清）；两枚合 collect
  **60 枚**（⇒ §8 里 `-k` 分组一律单枚点名的原因）。本纸的行数不在本纸里写死（写死就漂——本班已为这枚自指数改口三次）：要就读
  `Measure-Object -Line`，交回时以 §9 的 `git diff --numstat` 与盘面为准。
- EOL：**七枚件**（四枚改 + 三枚新）盘上逐字节全 CRLF、零裸 LF（本轮按 `ReadAllBytes` 数出来的，
  `read_text` 会把 CRLF 归一成 LF，别拿它当证据）；四枚在册件 `git ls-files --eol` 一律 `i/lf w/crlf`
  （本机 `core.autocrlf=true` 且无 `.gitattributes`，本班口径：新件也必须 CRLF）。
- 零 commit、零 push、未新建分支；主树未动。


---

## 10. 配套闸的拒绝形状（两种单改一头，各自被谁拦、拦在哪一行、什么码）

两枚键单改一头的后果**不对称**，这是本单唯一要说清「谁拦的」的一张表。坐标全部 `be-r535` 现取。

| 盘面 | 谁先拦下 | 拦在哪一行 | 交回的码 | 闸的判读 | 证它的刀 |
|------|----------|------------|----------|----------|----------|
| **A：只抬 `MODEL_CONTEXT_TOKENS`（如 8192），服务端 `num_ctx` 仍 4096** | 🔴 **本进程守卫不再拦**（它按 8192 算 `prompt_room`=6656，把本该零成本挡下的问放进网络）——真正拦下它的是**模型服务端**：HTTP 400 原文 | 翻译点 `app/agents/nodes.py:1012`（`provider_code = context_error_code(exc)`）→ `:1027-1031`；流式同一形状在 `:1183-1186`。判码片段 `app/common/model_budget.py:361-370` | 仍是 `context_limit_exceeded`（`:1031` 重新抛 `ModelContextLimitExceeded`，与预发同一枚码，R30 口径），**不降级、不并码** | `env_above_runtime`——「不配套：声明 8192、服务端只到 4096，差 4096 枚」，并点名两枚键与「一发白烧的往返」这个代价 | **K1**（摘掉闸读运行时那一格 ⇒ 判据② 那格当场红，缺席冒充不了配套）；**K2**（方向判据钝化 ⇒ 反方向与同宽两格一起红）；**K5**（摘掉从服务端拒发原文里摘数那一格 ⇒ 通道二失明那格红）；**K3**（不许接进兜底文案 ⇒ `test_r30...:144` 与 `test_r255...:199` 两枚在册钉本身红） |
| **B：只调服务端 `num_ctx`（如 8192），`MODEL_CONTEXT_TOKENS` 仍 4096** | 🔴 **本进程守卫在发请求之前拦**：`app/common/model_budget.py:1285`（`context_window_code` 命中）→ `:1290` `raise ModelContextLimitExceeded`；边界落点 `app/agents/nodes.py:984-994`（invoke 预发）与 `:1157-1160`（stream 预发） | 同上；请求**一个字节都没上过网**（`test_a_refused_customer_question_...` 里 `primary.calls == []` 就是这一格） | 同一枚 `context_limit_exceeded`；`evidence` 不降级（`test_r30...:158` 在册钉原样绿） | `runtime_above_env`——「白留着容量：运行时 8192，声明只肯 4096，多出的 4096 一个字都没用」；不足两枚宽只报方向不叫白留着 | **K8**（把两枚门槛钝成 1 ⇒ 「不足两倍」那格红，证明「白留着」是要证据的）；**K9**（把 `runtime_unread` 算成可行动 ⇒ 缺席那格红）；**K1b**（把声明那一半写死 4096 ⇒ 「跟着 env 变」那格红）；**K12**（把归因行并进 `[ModelBudget]` ⇒ `test_r30...:231` 红，证明两枚标记是分开的） |

两枚盘面都保住的三条不变式（各有钉与刀）：

1. **拒发都发生在「码已经确定」之后、兜底之前**：`slot.release()` / `span.finish("failed", error_code=…)` /
   `raise` 三格顺序未动，屏上永远不会出现离线问候语（K3 是唯一被明令禁止的形状，摘了它两枚在册钉就红）。
2. **一发一行**：`[ModelBudget]` 仍恰一枚（`test_r255...:162`、`test_r30...:231` 原样绿），归因行走
   `[ContextPairing]` 独立标记（K11/K12 两把对着这一格）。
3. **正文不进读数**：归因句与判读句的每个字段都是整数或键名（`test_the_attribution_takes_nothing_but_counts_and_names`），
   端到端那格用 2817 槽的 canary 撞顶，逐条日志、异常字符串、证据袋 JSON 三处都验 canary 不出现。

屏上那一行的接线（`chat.py:2924`／`evidence.py:314`）按本席裁定**不在本单**，见 §7 未达格 2；
上面表里「交回的码」那一列说的是 API 终态码，与客户屏幕文案无关。


## 11. 邻件红逐枚归因（并树前的真读数：一枚本单引入·已治，两族基点既存）

本单在 `nodes.py` 319 行之前净插 **106 行**（不是 107：把手那一句后来内联，减掉一行），
于是 319 之后全体行号后移——纸里所有 `nodes.py` 坐标已按现取重取（§1.1 末条、§3.1、§8 订正条、§10），
`git diff --numstat` 现取 `119  3  app/agents/nodes.py`。

- 🔴 **本单引入的一枚红（已治，在册钉一字未动）**：
  `tests/test_r167_answer_prefix_reuse.py::test_no_prompt_byte_sits_after_variable_bytes_in_the_two_files[app/agents/nodes.py]`
  - 基点干净导出树（`git archive 05bec06` 现取）：该件 **29 passed**＝绿的。
  - 本单初版红句：`这些 prompt 组装点把固定指令排到了可变内容之后：[{'line': 312, ...}]`。
  - **红因（读那枚钉的判据现取）**：`is_prompt_statement(text)` 用「语句原文里有没有 `logger.`」判这条串
    进不进模型。我原先把日志行先提成 `line = (f"…" f"…")` **单独一句**——那句里没有 `logger.`，
    却含 `pairing.prompt_room_tokens` 的 `prompt` 字样 ⇒ 被认成 prompt 组装句。该钉的红是一枚
    **真红**（它量的形状确实被我改变了），不是取巧。
  - **治法（只动本单自己的行）**：把那串 f-string 直接写进
    `(logger.warning if pairing.actionable else logger.info)(...)` 的调用里，语句原文含 `logger.` ⇒
    该钉按自己的口径判回「不进模型」。**打印出来的文本一字未变**（原 `f"{line} {sentence}"` ＝
    新末段 `f" min_answer={…} {sentence}"`）。
  - 治后现取：`pytest tests/test_r167_answer_prefix_reuse.py -q -p no:randomly` ⇒ **29 passed, 4 warnings in 7.65 s**
    （与基点同数）；本单两枚件 **60 passed**；三批 18 枚件合跑 **295 passed, 8 warnings / exit=0**。
- **两族既存红，不属本单**（判据不是「我觉得无关」，是名册对拍：本树红集合 − 基点红集合＝**空集**）：
  - `tests/test_r346_line_ledger_is_derived_not_copied.py`——本树 23 failed / 12 passed；基点干净导出
    同样红；🔴 **现 HEAD `e9f7ee8` 上该件 35 passed**（`git archive e9f7ee8` 导出后现取）。红句点名的
    是 `scripts/r525_activity_prior_readout.py::_connect#0`，本单零接触。⇒ 本席基点 `05bec06` 早于
    `96946f8` 那笔账修（`merge-base --is-ancestor 05bec06 96946f8` rc=0），这一族并树后自然消失，
    **不需要本单治，也不该记在本单账上**。
  - `tests/test_r455_gapdoc_coordinates_are_derived.py`——本树 8 failed；🔴 **现 HEAD 上仍 10 failed**
    （导出树无 `.git`，另两枚 git 依赖格另算）。红句逐枚印的是「那一格印 `app/api/v1/chat.py:4470`、
    按符号现读 `:4494`」＝**恰好 R536 给 `chat.py` 的那 +24 行**。`app/api/v1/chat.py`／缺口单／
    `scripts/r455_gapdoc_coordinates.py` 三枚本单零接触（`git diff --name-only --` 现取为空）。
    ⇒ 出路是它红句自己给的那一条：`python scripts/r455_gapdoc_coordinates.py --emit-doc-cells` 重落地，
    属总控写域，本席不动、也不许拿旧数加减行号。

---

## 12. 「不给摘」那四枚坐标在并树目标上的现值（交回本席，供另立单用）

派工词给的四枚坐标是按**本席基点 `05bec06`** 取的。并树目标是 `e9f7ee8`，两版差一枚：

| 派工词给的坐标 | 基点 `05bec06` 现取 | 并树目标 `e9f7ee8` 现取 | 差 |
|----------------|--------------------|------------------------|----|
| `app/api/v1/chat.py:2924` 兜底句 | `:2924` ＝ `failure_text = "本轮未产出任何结论，请重试或补充数据范围。"` | 🔴 **`:2937`** 才是那句（`:2924` 在现 HEAD 上已落进 R210 那段注释里） | +13（R536） |
| `app/agents/evidence.py:314` `ErrorEnvelope.message` | `:314` ＝ `error = ErrorEnvelope(` | `:314` **逐枚等值** | 0 |
| `app/common/monitoring.py:211`（`/health/details` 模型那一格） | `:211-219` ＝ `return { ... }` | `:211-219` **逐枚等值** | 0 |
| `app/trace/spans.py:142` `span.finish` | `:142` ＝ `def finish(` | `:142` **逐枚等值** | 0 |

`git diff --name-only 05bec06..e9f7ee8 -- app/agents/evidence.py app/common/monitoring.py app/trace/spans.py`
现取为空 ⇒ 后三枚坐标照旧可用；只有 `chat.py` 那一枚要按 `:2937` 走，别照派工词的行号扑空。


## 13. 第八班续席复核（09-30 17:24–17:37，并树目标已从 `1a23445` 推进到 `b86b9e2`）

令上给的「主树 HEAD `1a23445`」是过期读数。现取 `git -C 企业智脑 rev-parse HEAD` = **`b86b9e2`**，其间已并
R538 `1a23445`／R536 `7e1c221`／R548 `f312eeb`／R523 `b2d82a0`／总控改口 `e9f7ee8`／落账 `b86b9e2`。本节全部按
`b86b9e2` 重取，不沿用上一席对着 `e9f7ee8`／`1a23445` 的对账。

- **写域交集＝零**：`git diff --name-only 05bec06..b86b9e2` 现取 **49 枚**文件，与本单七枚（四枚在册件＋三枚新件）
  **交集为空**。四枚在册件在两枚基线上的 blob 逐枚全等：`.env.example 655a6ad`／`app/agents/contracts.py 3832cc7`／
  `app/agents/nodes.py a15e31d`／`app/common/model_config.py 9fdbe7d`；三枚新件在 `b86b9e2` 上零同名
  （`git cat-file -e b86b9e2:<路径>` rc=128）。补丁 40 262 B 在 `git archive b86b9e2` 导出树上
  `git apply --check -v` = **rc=0**（`Checking patch` 四枚逐件通过）⇒ 并树不会撞 R536 的 `app/api/v1/chat.py`、
  R523 的 `app/storage/persistence.py`／`app/trace/**`／`migrations/**`、R548 的 `deploy/queue_worker.py`。
- **在册钉与量具未漂**：范围内唯一与本单邻接的产品件是 `app/trace/spans.py`（R523，24/9），`def finish(` 仍在
  **`:142`**；两枚在册钉 `tests/test_r30_context_limit_guard.py`／`tests/test_r255_refusal_says_the_parameters_are_small.py`
  与 `app/common/model_budget.py`／`app/agents/evidence.py` 一字未变 ⇒ §6 那十枚 sha 指纹本席 17:31 现取**逐枚等值**，
  十三把刀的 victim 行（`test_r30_context_limit_guard.py:144`／`:158`／`:231`、
  `test_r255_refusal_says_the_parameters_are_small.py:162`／`:199`）现取全部是 `def test_…` 本身。
- 🔴 **一枚 §1.2 坐标在落地目标上漂了**：`app/api/v1/observability.py` 被 R536 改过，那句「全仓 `app/**` 无任何一处把
  `num_ctx` 发进请求载荷」在基点 `05bec06` 是 **`:1750`**，在 `b86b9e2` 是 **`:1818`**（+68）⇒ 并树后引用 `:1750` 会扑空。
  §1.2 其余引用逐枚对过：`app/common/model_handler.py:62`/`:555`、`deploy/docker-compose.server.yml:28-30`、
  `deploy/.env.server.example:36`、`docs/perf/raw/rate_all.jsonl:2`、`docs/perf/raw/rate_prefill.jsonl:8`、
  `scripts/perf_probe_rate.py:179`、`app/common/model_budget.py:361-370`（`CONTEXT_ERROR_FRAGMENTS` 现取九枚片段）
  都不在那 49 枚里，坐标照旧；`docs/handoff/2026-09-15-orchestration-board.md` 虽在范围内，§1.2 引的那三行
  （`context_length: 4096` 属 `/api/ps` 运行时实测值）在 `b86b9e2` 上现取仍是 **`:1013-1015`** ⇒ 不改。
- §1.1「消费者 …`nodes.py:925` 一带引用 `prompt_room`」那一行不精确，本席收紧：`prompt_room(` 的字面消费者只有
  `app/common/model_budget.py:121` 与 `:542` 两处；`app/agents/nodes.py` 这一头走
  **`:920 authorized = authorize(self.budget, prompt_tokens, stream=stream)`**，`:925` 是同一函数体内写 `extra_body`
  载荷那一行，不含 `prompt_room(` 字面。⇒「没有第二份减法」结论不变，坐的仍是 R463 那一处家。
- `.env.example` 三枚键分两版坐标：本树（＝并树后）**`:213`／`:253`／`:335`**；基点 `05bec06` 是 `:213`／`:246`／`:305`。
  本单只往注释格插行——`git diff` 现取**非注释新增行 0 枚、删除行 0 枚** ⇒ 缺省数字一枚没动，但引用 `:246`／`:305`
  的旧纸并树后会扑空。
- **静态层把 `-k` 分组的枚数算平了（不靠跑）**：gate 件现取 31 枚 `def test_`，其中
  `test_an_unobserved_server_is_never_printed_as_paired` 带 `@pytest.mark.parametrize("unread", [None, 0])` ⇒ collect
  **32**；四组关键词命中 def 数＝判据② 19（＋参数化那枚的第二次＝**20**）、判据③ **3**、判据④ **7**、缺省未改＋尺子
  **2**，四组恰好无重无漏地平分那 31 枚 ⇒ 与 §8 执行层自报的 `20 passed, 12 deselected`／`3 passed, 29 deselected`／
  `7 passed, 25 deselected`／`2 passed, 30 deselected` 逐格同数。teeth 件 28 枚 `def test_`＝十三把刀 ×（正控＋摘刀）26
  ＋ `test_z13_the_ledger_names_every_knife_and_every_tooth_bit` ＋
  `test_z13b_the_tracked_files_are_the_ones_we_opened_the_door_with` ⇒ 与 `28 passed` 同数。
- **本席未跑（等门）**：主树 `scripts/run_gate.py` 17:22:09 起（PID 48960，自选 `-n 6 --dist loadfile`）至 17:36 仍在跑；
  同机外来 anaconda CUDA 夜间链在占卡，本机一度紧到 PowerShell 起进程报 `GC heap initialization failed`、Node 报
  「页面文件太小」(os error 1455)。按「门属总控独占、执行层不挤」的口径，本席**一枚 pytest 都没起**，§8 三批原样留作
  代跑清单。
- 顺手摘掉 §8 里一枚 `apply_patch` 压平病残留：原 `:360` 那半句「- **§10 坐标订正（本轮现取）**：流式翻译块止于」（无后文、
  与 `:363` 全文重复）已删，纸面 495 → 493 行；本节写回后现取 **493＋本节行数**，全 CRLF、裸 LF **0**。
