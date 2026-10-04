# R632 · 跑分量具自身的三枚缺陷（读数件 / 契约件名 / 档位名派生 0/105）

工单 R632 ｜ 树 `C:\Users\fengx\PycharmProjects\be-r632`（分支 `codex/be-r632`，基点 `4da0bad`）
｜ 日期 2026-10-04 ｜ 性质：**离线量具单**——零服务／零模型／零容器／零连库。

写域：`scripts/eval_lane_readout.py`、`scripts/eval_slo_lane_readout.py`（新落）、
`scripts/eval_transport_ask_v2.py`、`tests/test_r632_*.py`（新落 3 枚）、本纸。
`app/**`、`docs/api/contract-v1.md`、`docs/handoff/**`、`deploy/**`、`.env*`、评测夹具
一律未动（逐条见 §6 交回总控）。

---

## 1. 缺陷一：`scripts/eval_lane_readout.py --help` 当场崩

**命令原文 → 实取读数**

```
PS> .venv\Scripts\python.exe scripts/eval_lane_readout.py --help
rc=0（改后，本席 10-04 现取）

PS> git show HEAD:scripts/eval_lane_readout.py | Select-String '%TEMP%'
L134: ap.add_argument("--dir", default="", help="件所在目录，缺省 %TEMP%\evalrun")
```

改前那一条由总控 16:4x 现取为 `ValueError: unsupported format character 'T' (0x54) at index 10`
（rc=1）；本席在同一枚临时根副本上把 `%%` 退回 `%` 复现同一句（`tests/
test_r632_reader_help_smoke.py::test_the_knife_reverting_the_escape_breaks_the_help_again`）。

**病根**：argparse 的 `HelpFormatter._expand_help` 对每一枚 `help=` 串做 `%` 展开
（`C:\Users\fengx\anaconda3\Lib\argparse.py:640`），而 `--help` 是**唯一**会走到那一格的调用；
正常运行一次都不碰 ⇒ 「量具自己站不起来」这件事，人眼与「跑过一遍判据」都看不见。
本仓不是第一次（R443 抬头就写着「本席补 Windows GBK 控制台下 stdout 强 UTF-8，否则判读件自己
先炸」——同一族病）。

**治**：那一句写成 `缺省 %%TEMP%%\evalrun`（展开后交回原样 `%TEMP%\evalrun`），并补三格牙：
真跑子进程判 rc=0、`--help` 里那枚路径读得回原样、AST 扫两枚读数件的 `help=` 字面串不许留裸 `%`。

---

## 2. 缺陷二：契约点名的读数件**从来没落**（不是改名漂了）

**命令原文 → 实取读数**

```
PS> git log --all --oneline -- scripts/eval_slo_lane_readout.py
（空输出 —— 任何 ref 都没碰过这个路径）

PS> Test-Path scripts/eval_slo_lane_readout.py
开工时 False ｜ 本席落仓之后 True

PS> Select-String docs\testing\r526-slo-caliber-closure.md -Pattern eval_slo_lane_readout
109 / 154 / 158 / 191 / 216 行 —— 上一班已把这三枚件名记成 MISS（在册旧账）

PS> rg -n "_A_READER" app/api/v1/observability.py
1168:_A_READER = "scripts/eval_slo_lane_readout.py"   ← 产品侧也指着这枚不存在的件（写域外，只交证据）
```

**定性**：`git log --all` 空输出 = 这枚件在**任何**分支/tag 上都没出现过，所以不存在
「改名而契约没跟」那一形；契约家族 A 那一格（`docs/api/contract-v1.md:5900`）与家族 E 那一格
（`:5904`）点名的都是这枚件，那句「该件落仓之前这一条跑不起来，跑不起来就是『取不到』」
今天之前是**真话**，本单之后过期——契约文本本席一个字没动，改哪一格交总控裁。

**治**：照契约那一格的口径补出 `scripts/eval_slo_lane_readout.py`（三条纪律见 §3 件内抬头）：
① 档位名只认服务端说了什么（响应头腿优先，`[R42]` 日志腿只补空缺；前缀不唯一／同题两枚档／
闭集外的名字一律判取不到，不挑一枚；夹具那一列 `tier` 是**声明档**，绝不当生效档用）；
② 分位只出自 `app/common/performance.py::PerformanceStats`，本件不写第二套排名，空表不叫尺；
③ 档位名与样本下限 AST 现场派生（`nodes.py` 的 LANE_QA/LANE_ANALYSIS/LANE_REPORT ＋
`observability.py` 的 MIN_SLO_SAMPLES），派生不到就 rc=2，绝不退落成手抄数。
凭据格（路径＋sha256／`caliber=local-full`／抬头四枚开关／`--readouts` rc=0）逐格在件内实现并被牙钉住。

---

## 3. 缺陷三：「档位名派生 0/105」的归因——量具三面缺码，不是产品不落 `lane`

**先推翻前提**（账上写「等 R524 进镜像」）：

```
PS> git merge-base --is-ancestor 05bec06 a2bbf13 ; $LASTEXITCODE
0    ← R524 那笔早已在现网镜像 revision 里

PS> git rev-list --count a2bbf13..HEAD -- app/
1    ← 之后只有 f5d75a7（R616 裸 connect 修复）一枚 app 改动
```

**服务端那条腿今天是通的**：

```
PS> rg -n "x-effective-lane|x-declared-lane|x-lane-source|_lane_readout_headers" app/api/v1/chat.py
1384/1385/1386 三枚头名常量 ｜ 1502 def _lane_readout_headers(...)（读数缺格就少发一枚头，不发假值）
1713 / 2465 / 2672 三处挂上响应（含 StreamingResponse）
在册钉：tests/test_r172_lane_across_hitl.py 逐枚点名 x-effective-lane
```

**量具这一侧今天读不出档位名，三个面都缺**：

```
PS> git show HEAD:scripts/eval_transport_ask_v2.py | Select-String 'x-effective-lane|x-declared-lane|x-lane-source|resp\.headers|getheader'
x-effective-lane=0 x-declared-lane=0 x-lane-source=0 resp.headers=0 getheader=0
（全文只有三行 headers，且全是**请求头**：Content-Type / Authorization / Request(headers=...)）

PS> <对 %TEMP%\evalrun 下 run20k／run21b 逐件数 lane 命中>
run20k-sidecar.jsonl lane_hits=0 ｜ run20k-sidecar-frames.jsonl lane_hits=0 ｜ run20k-answers.jsonl lane_hits=0
run21b-sidecar.jsonl lane_hits=0 ｜ run21b-sidecar-frames.jsonl lane_hits=0 ｜ run21b-answers.jsonl lane_hits=0
（整个 evalrun 目录里也没有任何 [R42] 日志件：r42_hits=0）

PS> Test-Path scripts/eval_slo_lane_readout.py  （开工时）
False —— 契约点名的读数件不存在（见 §2）
```

而声明腿只补一档：`DECLARE_LANE_TIER` 那一枚只对**与它同名的一档**补 `lane`
（`scripts/eval_transport_ask_v2.py` 里 `lane = LANE_BY_TIER.get(tier, "") if DECLARE_LANE_TIER and
tier == DECLARE_LANE_TIER else ""`），其余两档一题都不补。

**结论**：0/105 是**量具**读不回来（没人读响应头／声明腿只覆盖一档／读数件从来没落），
不是 transport 不发（它只在 `EVAL_DECLARE_LANE_TIER` 设了且档位同名时发那一档，其余是「按产品默认判档」
= 设计如此），也不是服务端不落 `[R42] lane=`（那行由 `app/agents/nodes.py:1556` 逐判别写，
`[R42] '<题面前30字>' → lane=... tier=...`；只是没有任何一份件把它抄进盘上产物）。
**服务端那一半不缺码**，所以本单不动 `app/**`。
---

## 4. 量具半张：两枚新开关（默认都关）＋一枚落点旋钮

| 开关 | 腿 | 默认 | 开起来的后果 |
| --- | --- | --- | --- |
| `EVAL_DECLARE_LANE_PER_TIER` | 载荷腿：按**每一行自己的档位**补 `lane` | **关**（关＝逐字节回到 `DECLARE_LANE_TIER` 那一格的老口径） | 🔴 报告档 20 题从此带 `lane=report`；容器侧 `REPORT_LANE_VIA_QUEUE=on` 时它们改走**队列道** ⇒ 时延换代，这一窗的 A① 不许与 run18／run20k 并表 |
| `EVAL_RECORD_LANE_READOUT` | 记账腿：把 `/ask` 响应头三枚读数逐题落进第三份件 | **关**（关＝一件新产物都不落） | 不动载荷、不动时延口径 ⇒ **下一窗只想把 105 题逐题档位名读出来，只开这一枚就够** |
| `EVAL_LANE_LEDGER` | 落点旋钮 | 未设＝跟着 `SIDECAR` 派生 `*-lane.jsonl` | 与 `frame_ledger_path()` 同纪律：**调用期**读表，runbook §8「产物落仓外」绕不掉 |

- 开关取值字面 `{"1","true","yes","on"}` 与产品同源（`app/api/v1/chat.py` 的
  `REPORT_LANE_ON_VALUES`），同源性由牙现读 AST 对判，不靠抄。
- 第三份件的字段：`id / session_id / ts / sent_lane / effective_lane / server_declared_lane /
  lane_source / headers_readable`。**读数不并进 sidecar 也不并进帧账**——那两本的键集被在册对判
  钉成死对（`tests/test_r181_text_frame_ruler.py`、`tests/test_r223_frame_arrival_clock.py`、
  `tests/test_r259_awaiting_approval_stops_the_watch.py`、`tests/_r259_queue_ruler.py`），
  加一列当场红，所以这一格只能长在第三份件上。
- join 三跳全是精确键：侧车 `id` →（帧账 `id`→`session_id`）→ 档位件 `session_id`；
  重试那一发每次现造新会话，不会与终答那一发撞键。
- 三枚头按产品的纪律读：**读数缺格就少发一枚**（不发空串、不折零）；`headers_readable=False`
  单说一件事——这一枚出口根本没有头可读（假出口/旧件），它**不等于**「服务端说没档位」。

---

## 5. 旧口径不受影响的现证（`tests/test_r632_transport_lane_switches.py`）

| 判据 | 牙 | 实取 |
| --- | --- | --- |
| 两枚新开关都没设 ⇒ 载荷仍只有 `BASE_PAYLOAD_KEYS` 三键、侧车与帧账一字不多、第三份件一件不落 | `test_off_by_default_payloads_are_the_three_keys_and_no_lane_file` | 绿 |
| 只开旧的 `EVAL_DECLARE_LANE_TIER=报告` ⇒ 与 R520 钉的行为逐字相同 | `test_old_single_tier_shape_is_byte_identical_with_the_new_switch_off` | 绿 |
| 新旧同设 ⇒ 旧口径优先，已被补上 `lane` 的题一字节不改 | `test_declaring_per_tier_never_overrides_what_the_old_switch_already_declared` | 绿 |
| 开新腿的代价 = 恰好多一枚 `lane` 键，别的一律不变（逐 row 对判两态载荷） | `test_the_new_leg_costs_exactly_one_key_and_nothing_else` | 绿 |
| 105 行逐行按自己的档位补（不是只有报告档） | `test_the_full_corpus_declares_its_own_tier_for_every_one_of_the_105_rows` | 绿 |
| 开关名/取值字面/头名三处与产品同源 | `test_the_switch_vocabulary_and_header_words_match_the_product` | 绿 |
| 反证四把：K1 摘 per-tier 开关、K2 记账腿恒落盘、K3 读表腿恒真、K4 头名漂走 | `test_k1_* … test_k4_*` | 四把都红在预期的那一格 |

---

## 6. 读数件自己的牙（`tests/test_r632_slo_lane_readout.py`，39 枚）

四组：件名与契约同源（长期钉，只认件名不认行号）／派生不许手抄（含影子根改名与四枚坏下限）／
分位只出自产品那把尺（含「尺对空表回 0」的正控与「不许有第二套排名」的 AST 结构钉）／
join 三跳与三态（撞键不挑一枚、闭集外不认、题面歧义不认、同题两枚档判取不到、
UTF-16 LE BOM 日志读得回而按 utf-8 硬读交零枚、家族 E 那格如实交不出数、
`--emit-readouts` 交出的三行被 `eval_cloud_window_readout.py --readouts` 判 rc=0——
反证：同一批读数换上 `caliber=cloud-shape` 闸当场 rc=2）。

反证三把（只在临时根副本动刀，真树件逐把核 sha256 不变）：
甲 摘掉「空表不叫尺」⇒ 件对空表当场炸（10-04 实取：`min() arg is an empty sequence`）；
乙 摘掉派生闭集 ⇒ 服务端说 `turbo` 也照收；
丙 `return names` 换成手抄三枚字面 ⇒ 影子根那扇窗当场读不出数（正控：真件同一扇窗 rc=0）。

---

## 7. 两态自跑读数

```
PS> .venv\Scripts\python.exe -m pytest <本单 3 枚新牙 + 点名在册 11 枚> -q
278 passed in 13.07s          ← apply 态（货在盘上，未 commit）
  含：tests/test_r632_reader_help_smoke.py（6）
      tests/test_r632_transport_lane_switches.py（29）
      tests/test_r632_slo_lane_readout.py（39）
      test_r520_*（3 枚件）/ test_r518_*（2 枚件）/ test_r259_*（2 枚件）
      test_r181 / test_r222 / test_r223 / test_r123_hitl_approval

PS> .venv\Scripts\python.exe -m pytest tests/test_r632_slo_lane_readout.py -q
39 passed in 3.73s
```

**commit 态那一遍本席跑不了**（硬规禁 `git commit`），按 AGENTS.md 的两态纪律欠总控：并树后在干净树
复跑同名件（尤其 `tests/test_r259_terminal_readout_lands_in_the_book.py` 那一枚行尾钉——它上一遍
正是因为 transport 里混进 3 枚 lone LF 而红过，现已归成一色 CRLF）。

**禁止项复核**：未跑 `scripts/run_gate.py`；未动容器／未打 Ollama／未连 PG；未碰 `app/**`、
`frontend/**`、`deploy/**`、`.env*`、`docs/api/contract-v1.md`、`docs/handoff/**`、评测夹具。

---

## 8. 交回总控（本席不许动的四格）

1. **契约那一格今天过期**：`docs/api/contract-v1.md:5900`「该件落仓之前这一条跑不起来」——件已落仓
   （`scripts/eval_slo_lane_readout.py`），这句话与「一枚在册读数件」的定语现在才成立；
   `:5904`（家族 E 同一枚件的另一条道）仍交不出数，件里如实 rc=2。改哪一格请总控裁。
2. **产品侧那枚同名常量**：`app/api/v1/observability.py:1168` `_A_READER = "scripts/eval_slo_lane_readout.py"`
   此前指着不存在的件；本单之后指得住了。该文件正由 `Pasteur`/R630 在改，本席一字未动。
3. **110 处行号引用漂了**：在册文档里 `eval_transport_ask_v2.py:<行号>` 形态共 **110 枚**（涉 22 枚 .md）。
   本单给 transport 加了 105 行，`:220`／`:1302` 那一类引用逐枚失效。建议照 R400（`69e0035`）那笔的
   做法把行号改成运行时派生，而不是再抄一遍新行号。
4. **run21b 读不出档位名是预期**：那一窗跑的是旧镜像（`revision=a2bbf13` 里没有本单两枚开关），
   盘上现取 `lane_hits=0`；要 A② 那一格出逐题档位名，下一窗只需 `EVAL_RECORD_LANE_READOUT=on`
   （不动时延口径）。若同时要逐题带 `lane` 声明，必须写明 `EVAL_DECLARE_LANE_PER_TIER=on` 的换代代价。
5. `scripts/__pycache__/` 里留下本单的 `.pyc`（`py_compile` 与测试导入的产物），由 `.gitignore:2`
   管着不入库，`status --porcelain` 不显示。
---

## 9. 现场端到端读数（真树件，非影子根；产物在 `%TEMP%\r632probe`，仓内零写入）

三枚合成件：侧车三题（`wall_ms` 1200/2400/900）× 帧账三枚 session × 档位件三行
（q2 故意写成 `sent_lane=qa` 而服务端读回 `report`）。

```
PS> .venv\Scripts\python.exe scripts/eval_slo_lane_readout.py --window probe --dir %TEMP%\r632probe --emit-readouts %TEMP%\r632probe\readouts.jsonl
- 派生：档位名=qa/analysis/report（出自 app\agents\nodes.py）｜ 样本下限=100（出自 app\api\v1\observability.py 的 MIN_SLO_SAMPLES）
- 档位名读回源：响应头件=3 行 ｜ [R42] 日志=未指定（--r42-log 没给）
- 侧车题数=3 ｜ 档位名读回=3（逐源 {'header': 3}）｜ 取不到=0
| qa | 1 | 100 | 🔴 样本不足（照实报 n，不拿分位当结论） | 1200.0 | 1200.0 | 1200.0 | 0 | {'answered': 1} |
| analysis | 1 | 100 | 🔴 样本不足（照实报 n，不拿分位当结论） | 900.0 | 900.0 | 900.0 | 0 | {'answered': 1} |
| report | 1 | 100 | 🔴 样本不足（照实报 n，不拿分位当结论） | 2400.0 | 2400.0 | 2400.0 | 0 | {'answered': 1} |
- 量具发出去的 lane 与服务端读回的档位名不一致的题数=1 题号=q2
  - q2：sent=qa effective=report server_declared=qa source=override
rc=0

PS> .venv\Scripts\python.exe scripts/eval_cloud_window_readout.py --readouts %TEMP%\r632probe\readouts.jsonl
- 行数=3 ｜ 段数=3 ｜ 格表指纹=19fb5b5ac2ebed02
| qa | local-full | p50_wall_ms,p95_wall_ms | 0 | 本机 |
| analysis | local-full | p50_wall_ms,p95_wall_ms | 0 | 本机 |
| report | local-full | p50_wall_ms,p95_wall_ms | 0 | 本机 |
- 结论：PASS
gate rc=0
```

这三格正是契约家族 A 那一格要的凭据形状：件路径＋sha256、`caliber=local-full`、
抬头四枚开关、`--readouts` 退出码 0。缺的只有**真窗的数**——那要下一扇开了
`EVAL_RECORD_LANE_READOUT=on` 的窗才有，本席不许动容器与模型，交总控排窗。