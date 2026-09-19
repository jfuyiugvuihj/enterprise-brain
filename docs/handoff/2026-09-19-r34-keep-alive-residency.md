# R34 · `keep_alive` 常驻与空闲回收策略

- 单号：R34（跟进单 `2026-09-15-backend-followup-requests.md` §21 L504，P1「决定能不能用」档）
- 树基线：`9626b7d`（主干已并 R92），工作树 `be-r34b`，分支 `codex/be-r34b`
- 代码落点：`app/common/model_handler.py`（两条腿的请求）、`app/common/model_config.py`（读环境 + 上限与拒绝）
- 取证机器：交付形态单机，RTX 4060 Laptop 8 GiB / 32 GiB RAM，容器网内 `http://ollama:11434`，模型 `qwen3.5:9b`
- 取证时间：2026-09-19（本文件所有秒数都是**同一台机器同一进程链**上的实测，不是估算）

## 1. 一句话结论

冷加载这笔钱（实测 4.4–6.1 s）现在**只在窗口过期后才付**：每发请求向 Ollama 原生端点显式要一个
**有上限的**常驻窗口（`keep_alive`，默认等于服务端自己的 300 s，运维可用 `LOCAL_MODEL_KEEP_ALIVE`
调到最长 1800 s），窗口内连续提问不再重复加载；窗口一到，**服务端自己把 5.3 GB 还回去**，
本单没有任何"永不卸载"的写法能生效（`-1`/`infinite`/`2h` 全部被代码截断）。

## 2. 判据①：连续 5 问不再重复冷加载（before / after 逐次秒数）

两组都走同一台机器、同一个模型、同一条原生腿（`/api/chat`，`think:false`、`num_predict:256`），
提示词固定为"只回复两个字：收到"，让**加载**而不是生成主导耗时；`wall` 是 HTTP 往返墙钟，
B 组的 UNTIL 取自主干码探针打印的 `expires_at`（每发答完都恰好落在"答完时刻 + 5 分钟"，
即服务端自己的默认窗口），A 组的 UNTIL 是 `/api/ps` 直接读到的剩余秒数；
`load` 是服务端自报的 `load_duration`，`UNTIL` 是发完这一发之后 `/api/ps` 里剩下的窗口秒数。
取证件在 `be-r34b` 树外（`%LOCALAPPDATA%\Temp\eb-r34q`），容器 `/app` 一字未改：before 用
主干 `9626b7d` 的 `model_handler.py` 覆盖导入，after 用本单改后的同一份文件覆盖导入。

### before（主干码：请求里根本没有 `keep_alive`，服务端按自己的 5 分钟处理）

| # | 前置状态 | wall (s) | load (s) | 答完后 UNTIL |
|---|---|---|---|---|
| B1 | 冷（`ollama ps` 空） | **6.366** | **6.126** | ≈300 s |
| B2 | 热（间隔 0 s） | 0.628 | 0.001 | ≈300 s |
| B3 | 热（间隔 8 s） | 1.712 | 0.001 | ≈300 s |
| B4 | 热 | 2.785 | 0.001 | ≈300 s |
| B5 | 热 | 1.593 | 0.001 | ≈300 s |
| B6 | **空闲 > 5 min 后首问** | **4.612** | **4.410** | ≈300 s |

B2–B5 说明：5 分钟窗口内本来就不会重复加载（这是 Ollama 的默认行为，不是本单的功劳）。
**B6 才是这单要消的那笔**：一旦问与问之间空过 5 分钟（业务上就是"去开了个会回来再问一句"），
模型已经不在了，第 6 问重新付 4.4 s。跟进单 §21 记的 6.4–6.9 s 与本组 B1 的 6.13 s 同一量级。

### after（本单码：`LOCAL_MODEL_KEEP_ALIVE=15m` → 线上 `keep_alive:"900s"`）

| # | 前置状态 | wall (s) | load (s) | 答完后 UNTIL |
|---|---|---|---|---|
| A1 | 冷（先用 `keep_alive:"0s"` 主动卸载） | **5.090** | **4.951** | **899.6 s** |
| A2 | 热（间隔 6 s） | 0.922 | 0.001 | 899.7 s |
| A3 | 热 | 0.184 | 0.003 | 899.5 s |
| A4 | 热 | 3.028 | 0.003 | 899.4 s |
| A5 | 热 | 2.516 | 0.001 | 899.9 s |
| A6 | 同进程撤掉变量（未重启服务）后的下一发 | 1.439 | 0.003 | **299.4 s** |

判据①成立：A1 一次冷加载 4.951 s，**A2–A5 四发的 `load` 全在 0.001–0.003 s**，即第一次之后
不再付那笔；且每一发都把窗口重新按到 ~900 s（窗口是"答完之后再计时"，不是"从第一问起计时"）。
A6 顺带钉住"改了环境变量下一发就生效，不必重启"：窗口从 900 s 回到 300 s。

## 3. 判据③：只有原生腿认这个字段（`/v1` 实测无效）

| 探针 | 请求 | 结果 |
|---|---|---|
| 原生腿 | `POST /api/chat`，body 带 `keep_alive:"900s"` | 200，`/api/ps` 的 UNTIL = **899.x s** ⇒ **服务端接受并生效**（A 组） |
| 兼容腿（裸） | `POST /v1/chat/completions`，body 带 `keep_alive:"900s"` | 200，正常吐 2 token，UNTIL = **299.3 s** ⇒ **字段被忽略**，落回服务端默认 5 分钟 |
| 兼容腿（对照） | 同上但不带该字段 | 200，UNTIL ≈ 299.9 s ⇒ 与带参数时同窗，坐实"忽略"而不是"报错" |
| 兼容腿（本单码） | `ModelHandler.chat(stream=True)` 经 SDK `extra_body` 上路 | 请求体确实含 `keep_alive:"900s"`（本地 echo 服务抓到原文），应答正常 2 字符，wall 5.478 s；但 UNTIL 由 227.3 s 被**重置回 299.8 s** |

echo 抓包（零模型调用，客户端侧证据）：

- before：`/api/chat` keys = `[messages, model, options, stream, think]`，`/v1/chat/completions` keys = `[max_tokens, messages, model, stream]`，两处 `keep_alive` 均 **absent**；
- after：同两条腿各多且只多一个 `keep_alive:"900s"`，`think:false` / `options.num_predict:256` / `max_tokens` / `stream` 一字未动。

**两条必须如实写的限制：**

1. 🔴 **遗留答案腿会把窗口缩短**。`/v1` 不认这个字段，但它照样把常驻时钟按自己的默认 5 分钟重排。
   一次问答的真实顺序是"改写（原生腿，要 15 min）→ 答案（`/v1`，把窗口压回 5 min）"，所以
   **端到端的有效窗口 = 最后一次调用落在哪条腿上**。A 组把常驻钉到了改写这一腿；要让答案腿也吃到
   15 min，得让答案走原生 `/api/chat`（那是 `app/agents/nodes.py:_make_model` 的边界 = R29 单，
   本单一字未碰），或把答案口从 `/v1` 迁走。这一条请总控记在 R29/后续单上，别当成 R34 已完成。
2. **嵌入腿未带**（`nomic-embed-text` 走 `app/rag` 的 `OllamaEmbeddings`，不在本单写域）。它只有
   274 MB，冷加载代价与 9B 不在一个量级，本单不动。

跟进单原话「`/v1` 传参无效」**实测成立，未被推翻**。

## 4. 判据②：空闲后的内存回收策略

### 4.1 占多少

| 观测 | 值 | 来源 |
|---|---|---|
| 常驻体积 | **5,327,342,796 B ≈ 5.3 GB**，`PROCESSOR 100% GPU`，`CONTEXT 4096` | `ollama ps` / `/api/ps` 的 `size`、`size_vram` |
| 加载后宿主显存读数 | 已用 5199 MiB / 空闲 2759 MiB（未加载时同机读数 4060 MiB / 3898 MiB） | `nvidia-smi --query-gpu=memory.*` |
| 冷加载耗时 | 4.41–6.13 s（首次最贵） | 服务端 `load_duration` |
| 热加载耗时 | 0.001–0.003 s | 同上 |
| 宿主内存 | 32 GiB 总量，取证时可用 8.2 GiB | `Win32_OperatingSystem` |

⚠️ 宿主 `nvidia-smi` 的读数含桌面合成器噪声，两次相减得到的 1.1 GiB 与 Ollama 自报的 5.3 GB
**对不上账**（WSL2/容器侧显存计量与宿主不是同一本账）。运维判"还能不能再塞一个模型"时按
Ollama 自报的 5.3 GB 记，别按 `nvidia-smi` 的差值记；这一条是**待查项**，不是本单结论。

### 4.2 多久卸载 · 卸载前怎么判断

- **计时规则**：每发请求带 `keep_alive=<窗口>`，服务端在**这一发答完**之后重新计时（实测 A2–A5
  每发都把 UNTIL 按回 ~900 s）。所以会话期间不会掉，只有"连续无请求超过窗口"才掉。
- **谁来卸**：Ollama 自己。窗口到点后模型从 `ollama ps` 里消失，**实测无人工干预**：A6 那发留下
  300 s 窗口，下一次检查 `ollama ps` 已经空了。这就是"不设 `-1`"的实际含义——内存一定会回来。
- **判断该不该卸**（运维读这三条就够）：
  1. 距上一次问答超过窗口 → 一定卸了，下一问要重付 4.4–6.1 s；
  2. 冷加载时间在本机被观测到明显变长（日志 `[Model] ollama-native 应答: ... load_seconds=` 就是
     这个数，见 §5）→ 显存/内存被别的东西挤了，**该调小窗口**而不是调大；
  3. 这台机器还跑别的东西（前端构建、Postgres、embedding 服务、客户的桌面会话）→ 按 §4.3 的下限选值。
- **主动卸载通道（三种，都实测过第一种）**：
  - 请求里 `keep_alive:"0s"`：答完立即还内存。实测一发 1 token 的调用 wall 1.002 s，`/api/ps` 随后为
    空 —— 这是"每问完就还回去"的极端档（`LOCAL_MODEL_KEEP_ALIVE=0`）；
  - `ollama stop qwen3.5:9b`（宿主机 CLI，等价动作）；
  - 把 `LOCAL_MODEL_KEEP_ALIVE` 调小，下一发就按新值计时（A6），不需要重启服务。

### 4.3 取值建议（代码允许 0–1800 s，超出即截断）

| 场景 | `LOCAL_MODEL_KEEP_ALIVE` | 效果 |
|---|---|---|
| 与客户共用这台机器、显存紧张、或夜里必须干净 | `0` 或 `60s` | 几乎不常驻，代价是每问都可能重付 4–6 s |
| 交付默认（本单未配置时的行为） | 不设 = 300 s | 与今天一致，只是现在能调了 |
| 分析员连续作业、问与问之间 5–15 min | **`15m`（推荐）** | 实测 A 组：窗口内四发全部 0.001–0.003 s 加载 |
| 会议/审批打断后还要接得上 | `30m` | 代码硬顶就是 `30m`；再大只会得到 `1800s` + 一条带"超过上限"的日志 |

**红线**：`-1`、`infinite`、`never`、`2h` 一律换不来"永不卸载"。`app/common/model_config.py` 的
`resolve_keep_alive()` 把它们截到 `KEEP_ALIVE_CEILING_SECONDS = 1800`，日志里带原因，答案照常
返回。要改这个上限必须改代码并过总控，**不能靠环境变量绕过**——这是"客户机内存有限"那条红线的
机器形态。

## 5. 运维怎么自查（30 秒）

```bash
# 现在谁在常驻、还剩多久
docker exec enterprise-brain-ollama-1 ollama ps
# 本进程要的是多长窗口、冷加载花了多少（后端日志，一发一行）
docker logs --since 10m enterprise-brain-backend-1 2>&1 | grep -E "keep_alive=|load_seconds="
```

日志字段：`[Model] ollama-native 应答: seconds=… load_seconds=… keep_alive=900s done_reason=…`；
被截断时同一条里会跟原因，例如
`keep_alive=1800s (LOCAL_MODEL_KEEP_ALIVE='2h' 超过上限，按 1800s 截断)`。

## 6. 本单未做 / 需要总控裁定的

1. **默认值仍是 300 s（等于现状），没有开箱把窗口调大。** 简报写明"不许新增强制打开的默认值"，
   同时红线是"客户机内存有限"，所以本单把**机制**放进码、把**值**留给部署。要交付即得 15 min，
   二选一，请总控点一个：(a) 改 `app/common/model_config.py:DEFAULT_KEEP_ALIVE_SECONDS` 一处；
   (b) 在 `docker-compose.yml` 的 ollama 客户端服务环境里加 `LOCAL_MODEL_KEEP_ALIVE: 15m`
   ——(b) 落在本单禁改区，我没动。
2. 答案腿（`/v1`）缩短窗口的结构性问题需要 R29/后续单解（§3 限制 1）。
3. 启动预热（`docs/perf/latency-budget-2026-09-16.md:438` 提的"服务起来后先发一发 1-token 预热"）
   要挂 `app/main.py` 的 lifespan，不在本单写域，未做；`keep_alive` 已经把它的必要条件铺好了。
4. 嵌入腿未带 `keep_alive`（§3 限制 2）。
5. `nvidia-smi` 与 Ollama 自报体积对不上账（§4.1 ⚠️），留作待查。

## 7. 验证

- 离线用例：`tests/test_r34_keep_alive_residency.py`（46 条，`LOCAL_MODEL_NAME=__eb_test_disabled__`
  下全绿，一条真 socket 都不开，R56 账本为空）。
- 实机取证：16 次模型调用（本文件 §2、§3 全部数字），未重启/未重建任何容器，容器 `/app` 未覆盖。
- 全量基线：见本单回报（2286 passed / 36 skipped / 0 failed 起算，只增不减）。
