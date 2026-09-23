# R181 · 判据②「`text` 事件数 >1 且逐字比对无缺字」的凭据长什么样

2026-09-23 取于工作树 `be-r181`（分支 `codex/be-r181`，基点 `8e1136d`）。全程离线：所有读数来自
把合成 SSE 字节喂给**真的**采集适配器，零服务、零模型、零容器、零连库。

## 一、这单修的不是产品，是量具

阶段 A 四条验收里，判据② 从来没被验过 —— run2–run5 四轮跑分都没有这一格读数。09-23 实取的成因是
**收端压根没数帧**：

- 功能侧在流。`app/api/v1/chat.py:1861-1863` 每来一枚 `piece` 就发一帧 **cumulative** `text`
  （构造器 `text_sse_frame()` 在 `app/api/v1/chat.py:250-262`），实时收尾在
  `app/api/v1/chat.py:1943` 再发整段终答；累计片与终答不同源时在 `app/api/v1/chat.py:1888`
  大声记 error。批准恢复道在 `app/api/v1/chat.py:2415` 发整段一帧。
- 量具侧没数。`scripts/eval_transport_ask_v2.py` 的旧 `_consume()` 收到 `text` 帧只做
  `out["answer"] = str(content)`（末帧覆盖前帧），既不数帧、也不比前缀单调。旁边那句注释
  「/ask 只发一条整段 text（chat.py:1364）」是失效注释：09-23 实取 `app/api/v1/chat.py:1363`
  是 `_complete_pending_steps` 的 `return completed`，与发帧无关。

🔴 本单只装尺子，**不改评分**：`answer` 的取值口径、`APPROVAL_FAILED_SENTINEL`、`cached`、
`first_token_at`、`steps` 五样一个字没动，run2–run5 的采集形状因此原样保留（见第六节）。

## 二、读数与落盘

一题一行，落在 sidecar **之外**的第二份证据件：
`scripts/eval_transport_ask_v2.py:frame_ledger_path()` —— 默认跟着 `EVAL_SIDECAR` 走（同目录、
同名加 `-frames.jsonl`），要单独指定用 `EVAL_FRAME_LEDGER`。落点必须在写的那一刻现算：钉在
import 期就会绕过窗口事后重绑 `SIDECAR` 的仓外纪律（runbook §8）。join 键 `id`，另带
`kind` / `attempt` / `session_id` 与 sidecar 同一行对得上。

| 读数 | 口径 | 谁判它 |
|---|---|---|
| `text_frames` | 一题收到的 `event: text` 帧计数（缺 `content` 的空帧也算一帧） | 判据② 的「>1」 |
| `max_stream_frames` | 单条流内的最大帧数 | 把「两条单帧流凑 2 帧」与「一条流真在逐片累计」分开 |
| `prefix_breaks` | 相邻两帧里后帧不以先帧为前缀的次数（cumulative 语义）；只在**同一条流内**判 | 「不许吞前缀缩短」 |
| `missing_chars` | 终答相对末帧的缺字数＝末帧里终答没写到的字（`len(末帧) − 共同前缀`） | 逐字比对 |
| `extra_chars` | 终答相对末帧的多字数＝终答里末帧没带出来的字（`len(终答) − 共同前缀`） | 逐字比对 |
| `last_frame_covers_answer` | **covering 语义的一致性**：`末帧.startswith(终答)` 即算一致 | 判据写死：不许退化成严格相等 |
| `last_frame_sha` / `answer_sha` | 两枚正文的 sha256 前 12 位：逐字比对的凭据，又不把客户正文抄进第二份文件 | 复核 |
| `streams` / `per_stream` | 这一题消费了几条流、各流自己的帧数与坏形数 | 定位 |
| `criterion_two_holds` | 上面几枚折成的一格判定 | 收窗直读 |

合格线（写死在 `scripts/eval_transport_ask_v2.py:_frame_verdict`）：

```
text_frames > 1 且 max_stream_frames > 1 且 prefix_breaks == 0 且 extra_chars == 0
```

`extra_chars == 0` 就是「无缺字」的 covering 读法：终答里的每一枚字都由末帧带出来了。
`missing_chars > 0`（末帧比终答长）在这一格算一致，但必须连着 `prefix_breaks` 一起读 ——
末帧长出的那截通常就是同一条流里的坏形（片与终答不同源，`app/api/v1/chat.py:1888` 那枚 error
的收端对称面）。

## 三、凭据长什么样（真实样本行）

下面五枚取自本树 105 题合成重放（形状实取：66 题三帧 cumulative、18 题挂起后批准、10 题整段
一帧、5 题零字节、3 题 error 事件、3 题入队取回；`criterion_two_holds` 为真的正是 66 + 18 = 84 题）：

```json
{"id":"doc-01","kind":"ok","streams":1,"text_frames":3,"max_stream_frames":3,"prefix_breaks":0,
 "missing_chars":0,"extra_chars":0,"last_frame_covers_answer":true,
 "last_frame_sha":"443c1fc8fe16","answer_sha":"443c1fc8fe16","criterion_two_holds":true}

{"id":"insight-07","kind":"approved_ok","streams":2,"text_frames":4,"max_stream_frames":3,
 "prefix_breaks":0,"missing_chars":0,"extra_chars":0,"last_frame_covers_answer":true,
 "last_frame_sha":"5562ece27f0c","answer_sha":"5562ece27f0c","criterion_two_holds":true}

{"id":"chat-03","kind":"queued_polled","streams":1,"text_frames":0,"max_stream_frames":0,
 "prefix_breaks":0,"missing_chars":0,"extra_chars":30,"last_frame_covers_answer":false,
 "last_frame_sha":"e3b0c44298fc","answer_sha":"9ec4e0c0cc1a","criterion_two_holds":false}

{"id":"doc-04","kind":"blank","streams":1,"text_frames":0,"extra_chars":18,
 "last_frame_covers_answer":false,"criterion_two_holds":false}

{"id":"doc-12","kind":"error_event","streams":1,"text_frames":0,"extra_chars":14,
 "last_frame_covers_answer":false,"criterion_two_holds":false}
```

一条能当判据② 凭据的行必须同时具备：帧数、坏形数、末帧与终答的两枚差、covering 布尔、`kind`。
少任何一枚都算「没量」，不算通过。第二行是**挂起后批准**那 18 枚的形状：一题两条流、4 帧、
跨流不比前缀（批准流从零起累计），所以坏形仍读 0。第三、四、五行的 `last_frame_sha`
是空串的指纹（`e3b0c44298fc`）：那三段正文都不是从 `text` 帧来的（入队取回 / 哨兵 / error 事件），
`criterion_two_holds=false` 是「这一格无从比对」，不是「产品丢了字」。

## 四、缓存命中只有一帧时怎么判

命中道只发那一帧：`app/api/v1/chat.py:1638-1660`（`cache_fields` 在 `:1645-1649`），
所以它的形状天然是 `text_frames == 1`、`max_stream_frames == 1`、`missing_chars == extra_chars == 0`、
`last_frame_sha == answer_sha`、`last_frame_covers_answer == true`。

- **不许**拿「`text_frames > 1`」去判命中行 —— 那是把「命中」读成「没流式」的失败。
- 命中行该被读成：**这一题没有实时腿可测**，判据② 对它不适用；`criterion_two_holds` 因此恒为
  `false`，靠 `prefix_breaks == 0` 与两枚 `sha` 相同来确认「末帧＝终答、一个字都没掉」。
- 真机窗口里命中根本到不了落盘：`scripts/eval_transport_ask_v2.py:transport()` 见到
  `cached` 当场 raise（P-18 的开窗纪律），所以命中形状的凭据今天只在离线合成流里有
  （`tests/test_r181_text_frame_ruler.py::test_case_7_a_cache_hit_is_a_single_covering_frame`）。
  同一枚用例的另一半钉住「raise 之前两份证据件都不许出现」。
- 与之相对，**批准恢复道**也是单帧（`app/api/v1/chat.py:2415`）：那种行的 `streams` 会是 2，
  读 `max_stream_frames` 就能看出实时腿到底有没有在逐片发。

## 五、为什么读数不落 sidecar 那一行（具名阻塞）

判据原文是「读数随采集器落盘」，本单落在第二份证据件而不是 sidecar 行内，因为并进那一行会
当场打断一枚**不在本单写域**的既有断言：
`tests/test_r123_hitl_approval.py:243` 把 sidecar 除九键之外的键集钉成甲案那七键的子集
（`set(record) - SIDECAR_BASE_KEYS <= APPROVAL_EXTRA_KEYS | {"pre_answer"}`），加任何新键即红；
同一文件 `:205` 又把交回采集器的 payload 钉死为五键，所以读数也不能顺着 answers 行走。
两份产物因此形状不变 —— 这恰好也是「run2–run5 必须还能逐题对齐」要求的那件事。
若总控要读数并回 sidecar 行，需要先授权改那枚测试（一处断言），本单不擅动。

## 六、run2–run5 逐题对齐怎么验

`tests/test_r181_text_frame_ruler.py` 末两枚用例把 105 题喂给**真** `transport()` + **真**采集器，
在确定性假钟下取两份摘要，与开工前（`8e1136d`，没装尺子的那版）同批输入跑出的摘要逐题比对：

- `answers_sha == f50024895fe64778a7cd9cee28a21c6d46bed77e4d045858d2e07bb26a97ac8e`
- `sidecar_nine_sha == 4b58bb839f080c12cfb29b4567982ee97edadc9aed3480dd6864e4bc9c6facf2`

两枚常数是**改前**取的：把 `git show 8e1136d:scripts/eval_transport_ask_v2.py` 落到仓外，与改后版
跑同一批合成流、同一条假钟，两侧 105 行 answers 与 sidecar 九键逐一相同（`ALIGN answers逐题=True
sidecar九键逐题=True`）。改后任何一处漂了字，这两枚摘要就会红。

## 七、两把常驻反证怎么复现

两把都写成了仓库里的用例（`tests/test_r181_text_frame_ruler.py`），在进程内复刻回退形状；
真改文件那把的红色回显与还原 sha 记在交付说明里：

1. `test_counter_evidence_a_ruler_that_stops_counting_turns_the_reading_red` —— 把
   `_count_text_frame` 改回「只留末帧、不计数」⇒ 三帧与零帧读成同一格，`criterion_two_holds`
   永远红。改回真文件：把 `out["text_frames"] += 1` 去掉即可复现。
2. `test_counter_evidence_a_swallowed_prefix_break_turns_the_reading_red` —— 把前缀缩短吞成静默
   （帧照数、坏形不报）⇒ `prefix_breaks` 读 0 而 `text_frames` 仍读 3，红就红在坏形那一格。
   改回真文件：去掉 `if out["text_frames"] and not frame.startswith(...)` 那一支即可复现。

## 八、装好尺子之后，run6 第一件要看的事

`app/api/v1/chat.py:1743-1747` 的具名注释写着：生产图路径上的生成腿今天只被 `invoke`，
`stream_piece_sink` 一次都不会响（R149 案发现场：三档问题各跑一遍，`model_calls` 全是
`stream=0`、`pieces=0`）。⇒ 真机轮大概率读到 `text_frames == 1`、`max_stream_frames == 1`。

那时候要写的结论是**判据② 在真机上不成立**（实时腿今天不流式，整段只有一帧），而不是「量具
没读数了」。要让 `criterion_two_holds` 大面积转真，得先生成腿改走流式 —— 那是生成腿改造单的
硬前置，不在本单范围。
