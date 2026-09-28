# 形状窗读数表（2026-09-28）· 由 `scripts/eval_window_planner.py` 生成

> 本文件是**骨架**，不是读数。判据③：没拿到的格一律写「未验」——不写 0、不写「应该没问题」、不抄上一班。本班零模型、零容器、不起服务，所以下表每一枚格的读数列全部为「未验」，开窗由总控执行。

## 一、输入件（路径与 sha256 前 16 位）

| 件 | 路径 | sha256 前 16 位 | 字节数 | 角色 |
|---|---|---|---|---|
| 题源本体 | `tests/fixtures/business_evaluation_100.jsonl` | `686c564ff2985744` | 41941 | 105 枚在册题，只读，一个字节不许改 |
| 形状子集 | `docs/testing/bank-shape-subset-30.jsonl` | `823ec81ff11b6345` | 13172 | 33 枚分层子集（本体 105 枚在册），逐行字节等值于本体 |
| 批准算料 | `docs/testing/sidecar-run9.jsonl` | `cb972fd93fa915c0` | 56568 | 上一窗逐枚 `approval_rounds`，批准次数由它算 |

- 落盘行尾：本表由 planner 以 **LF** 整张重写（常量 `READOUT_NEWLINE`＝`\n`）。本仓 `core.autocrlf=true` 且无 `.gitattributes`，检出侧会把这行以下的 LF 展成 CRLF——那是 git 的动作，不是人手改。所以「不许手改」按内容比（先把 `\r\n` 归一成 `\n`），并且比之前要求行尾只此一种约定：CRLF/LF 混排＝有人手改，必须红。

## 二、子集逐行比对（判据①的凭据）

- 子集行数：33；与本体**字节级等值**：33/33
- 外来 id（不在本体 105 枚里）：0 枚
- 被改动的行：0 枚
- 比对口径：`splitlines(keepends=True)` 取原始字节行，本体行尾现取 `CRLF`（形态随检出态变化，本仓无 `.gitattributes`），整行含行尾一起比——所以「重序列化加个空格」「行尾被重新烤过」都算改题。
- 行尾形态（现取）：本体 `CRLF`（CRLF 105 枚／裸 LF 0 枚），子集 `CRLF`（CRLF 33 枚／裸 LF 0 枚）。子集是 `--emit-subset` 用 `write_bytes` 逐字节搬运本体那几行，行尾跟着本体走；两枚件都只许一种约定，混排＝有人在盘上动过手。本表自己的落盘行尾见 §一。

## 三、11 族分布（分层账）

| 族 | 本体枚数 | 子集枚数 | 最低配额 |
|---|---|---|---|
| approval | 6 | 3 | 3 |
| chart | 4 | 2 | 2 |
| chat | 12 | 2 | 2 |
| data | 12 | 2 | 2 |
| doc | 19 | 2 | 2 |
| insight | 7 | 2 | 2 |
| metric | 19 | 2 | 2 |
| report | 12 | 12 | 12 |
| scope | 6 | 2 | 2 |
| tool | 4 | 2 | 2 |
| unsupported | 4 | 2 | 2 |
| 合计 | 105 | 33 | — |

- `approval` 族 3 枚、`report` 族 12 枚（判据①要求各至少 3 枚）
- 子集题序（题源顺序）：doc-01、doc-19、chat-01、chat-12、metric-01、metric-19、data-01、data-12、insight-01、insight-07、chart-01、chart-04、approval-01、approval-03、approval-06、scope-01、scope-06、unsupported-01、unsupported-04、tool-01、tool-04、report-01、report-02、report-03、report-04、report-05、report-06、report-07、report-08、report-09、report-10、report-11、report-12

## 四、一扇窗计划（判据②输出）

- 窗数：**1**（`shape-window-1`）。同一批格只允许出现一次开窗，planner 自己不许生成第二扇。
- 相数：2。相的划分来自开关态互斥：`REPORT_LANE_VIA_QUEUE` 一开，报告档整段取回，A② 必被洗成假红（runbook「两相一窗」）。
- 相之间必须复跑 P-18（Redis `answer:*` 归零），否则相 2 命中缓存，D 三格读的是缓存不是队列道。

| 相 | 开关态 | 题数 | 题序 | 计划批准轮 |
|---|---|---|---|---|
| 相1-流式道 | REPORT_LANE_VIA_QUEUE=off | 33 | doc-01、doc-19、chat-01、chat-12、metric-01、metric-19、data-01、data-12、insight-01、insight-07、chart-01、chart-04、approval-01、approval-03、approval-06、scope-01、scope-06、unsupported-01、unsupported-04、tool-01、tool-04、report-01、report-02、report-03、report-04、report-05、report-06、report-07、report-08、report-09、report-10、report-11、report-12 | 13 |
| 相2-队列道 | REPORT_LANE_VIA_QUEUE=on | 12 | report-01、report-02、report-03、report-04、report-05、report-06、report-07、report-08、report-09、report-10、report-11、report-12 | 8 |

- 总播放次数：45（唯一题号 33 枚）；因相开关不同而重复播放的题号：report-01、report-02、report-03、report-04、report-05、report-06、report-07、report-08、report-09、report-10、report-11、report-12
- **算出来的批准次数：21 轮**（逐相：相1-流式道＝13；相2-队列道＝8）
- 批准次数的算料＝上一窗 sidecar 逐枚 `approval_rounds`，不是按族猜。反例已在本机抓到：`approval` 族 6 枚在 run9 里一枚都没触发批准轮，触发的是 report/chart/tool/insight/scope——按族猜会把批准次数算错。
- 🔴 自动批准只允许打在评测容器＋评测账号那一条路径，生产/演示路径一个字不碰（业主 09-28 授权①的边界）。
- 批准人与批准次数要落进本表：开窗执行时逐相记 `approved_by=评测账号`、`approval_rounds=实际值`，与计划值不一致就是新事实，得写进读数不许改计划掩盖。

## 五、格归属与读数（判据③主体）

| 格 | 名称 | 归属相 | 取数面 | 计划题数 | 读数 |
|---|---|---|---|---|---|
| A2-stream-verbatim | A② 流式逐字无缺 | 相1-流式道 | 帧账 sidecar-frames：text 事件数 >1 且逐字比对无缺字（missing_chars=extra_chars=0） | 33 | 未验 |
| C-overprivilege | C 越权 | 相1-流式道 | sidecar kind/终答 + 跨部门权限题的拒绝形状 | 2 | 未验 |
| C-cache-annotation | C 缓存命中显式标注 | 相1-流式道 | transport 的 cached 位：命中即 raise 停窗（本树现取 scripts/eval_transport_ask_v2.py:818-819） | 33 | 未验 |
| D-report-retrievable | D 报告档可查回 | 相2-队列道 | GET /api/v1/queue/status/{request_id} 的 sources_present（路由 app/api/v1/chat.py:4882；量具折槽 scripts/eval_transport_ask_v2.py:932） | 12 | 未验 |
| D-usage-nonzero | D usage 非零 | 相2-队列道 | GET /api/v1/queue/status/{request_id} 响应体的 usage 六枚槽（量具点名 scripts/eval_transport_ask_v2.py:869、折槽 :935-941） | 12 | 未验 |
| D-sources-in-stream | D sources 事件在流里 | 相2-队列道 | 帧账 events 里的 sources 事件名＋引用载荷形状（`sources: []` 空列表不算可查回） | 12 | 未验 |
| zero-retry-zero-sentry | 零重试零哨兵 | 相1-流式道＋相2-队列道 | sidecar 逐枚 attempt==1 且 sentinel is False | 33 | 未验 |

- 零重试零哨兵：这一格读的是「每一 play」，所以按 45 次播放逐枚判，重复播放的那几枚再判一遍；上表题数列给的是唯一题号 33 枚。


## 六、与 R453 读数名册的接口（两单合起来才算一次开窗）

- 名册唯一来源：`scripts/eval_cloud_window_readout.py`（sha256 前 16 位 `1a0c91ffb725feb4`，在册读数格 28 枚，其中云端可读 10 枚、本机专属 18 枚）。本件的格名**全部从这张表 import**，不落第二份清单——两单今天格名交集＝0 那次事故就是这么来的。

| 判据格 | 名称 | 绑到名册里的哪几格 | 那几格实际吃的读数位 | 名册登记的锚 |
|---|---|---|---|---|
| A2-stream-verbatim | A② 流式逐字无缺 | frame_shape | text_frames、max_stream_frames、prefix_breaks、missing_chars、extra_chars、uncorrected_breaks、corrective_replacements、criterion_two_holds、last_frame_covers_answer | docs/testing/sidecar-run9-frames.jsonl · scripts/eval_frame_caliber_readout.py |
| C-overprivilege | C 越权 | escalation_annotation、error_class_shape | refused_escalation、cache_annotation_present、scope_class、failure_class、approval_http_status | docs/testing/run9-readout-2026-09-28.md 跨部门权限 · 跟进单 §128 第二节判据②；docs/testing/sidecar-run9.jsonl approval_error/approval_http_status |
| C-cache-annotation | C 缓存命中显式标注 | escalation_annotation | refused_escalation、cache_annotation_present、scope_class | docs/testing/run9-readout-2026-09-28.md 跨部门权限 · 跟进单 §128 第二节判据② |
| D-report-retrievable | D 报告档可查回 | queue_readback | queue_readable、queue_keys_present、queue_status_class | scripts/eval_transport_ask_v2.py 队列道 |
| D-usage-nonzero | D usage 非零 | usage_fields_present | usage_slots_present、usage_keys | scripts/eval_transport_ask_v2.py:803-831 · docs/testing/run9-readout-2026-09-28.md A2 末段 |
| D-sources-in-stream | D sources 事件在流里 | event_surface、citation_shape | sources_present、headline_present、done_present、hitl_present、failed_event_present、citations_present、citation_class、sources_shape | scripts/eval_frame_caliber_readout.py::event_tally；docs/testing/run9-readout-2026-09-28.md A0/A4 |
| zero-retry-zero-sentry | 零重试零哨兵 | retry_sentinel_shape | attempt、attempt_max、sentinel、retry_count | docs/testing/sidecar-run9.jsonl attempt/sentinel |

- 读数位覆盖（关「在场但为空」那枚假绿）：`D-sources-in-stream` 声明必须同时读到 sources_present←event_surface、sources_shape←citation_shape；供给的名册格 2 枚，缺位＝无，今天准按这一组读数闭格。

- 名册证不了的格：**无**。本班请求的每一枚形状格都能在名册里找到至少一格真能读它（这一位是算出来的：`r453_unproven_shape_cells`，不是态度）。

- 反向覆盖度：云端可读 10 枚里，本窗**一枚判据格都没引用**的有 2 枚——answer_shape、approval_gate_shape。
  - answer_shape（答案形状）：名册记的是「kind 归类与答案空不空可读；answer_chars 的量级只看形状，不拿来判对错」，读数位 kind、answer_nonempty、answer_chars_bucket。本窗不消费它；要在一扇窗里顺手读，就得把它挂到某枚判据格的 r453_cells 上，或另立一枚判据格——不许悄悄读了又不记账。
  - approval_gate_shape（审批门）：名册记的是「裁定（b）：轮次枚数与 hitl 触发与否取的是形状，留云端道；带审批轮的墙钟合计属时延类，另立一格」，读数位 approval_rounds、approved、hitl_rounds。本窗的**批准台账**按名册认领它：读的是 approval_rounds 这一枚算料位（算料，不判格），所以它仍留在未引用清单里——没有任何一枚判据格拿它当证据。

- 名册里本机专属那 18 枚（时延与分数两族）整体不在形状窗：与 §八 拒绝清单同一口径，两侧分家必须一致，`validate_catalog_binding()` 逐枚对表。

## 七、这台机拿不了的格（planner 判的，不是态度）

| 格 | 名称 | 拿不了的原因 | 读数 |
|---|---|---|---|
| C-overprivilege | C 越权 | 生产 department/classification 现值为空（AGENTS.md pgvector 格③：欠业主侧 A1 users.department 回填＋A3 密级标签回填，H13 未裁）⇒ 本机拿不到「客户数据上的隔离」这一形，沙盒合成标签不在此窗 | 未验 |
| C-cache-annotation | C 缓存命中显式标注 | P-18 要求开窗前 Redis answer:* 计数为 0（runbook 前置第 8 步），命中即 raise 停窗⇒ 本窗按纪律只能拿到「零命中」这一负形，正形需要总控另裁一枚探针臂 | 未验 |

## 八、形状窗范围之外（判据②硬规矩第 2 条）

- 分数与时延类格不在形状窗范围内。下列格被 planner 直接拒绝，不是「暂缓」：

| 格 | 名称 | 为什么不在形状窗 | 只能怎么拿 |
|---|---|---|---|
| A1-end-to-end-p95 | A① 端到端 ≤90 s（p95/时延） | 时延类格：本机全量每冻结点一次，不走子集 | 本机全量 105 枚，每冻结点一次；时延类另需样本 ≥100 |
| A4-category-score | A④ 逐类分数不退化 | 分数类格：与 run6 可比性要求全 105 题同开关态 | 本机全量 105 枚，每冻结点一次；时延类另需样本 ≥100 |
| C-bank-score-no-regression | C 评测集分数不退化 | 分数类格：子集分数与全量分数不同径，不许混报 | 本机全量 105 枚，每冻结点一次；时延类另需样本 ≥100 |
| aggregate-correctness | 整表 correctness/evidence 分数 | 分数类格：子集那几十枚的总分不能当全量 105 枚的总分用 | 本机全量 105 枚，每冻结点一次；时延类另需样本 ≥100 |

## 九、机器可读计划（planner 原样吐出，validate_readout 按它核对）

```json
{
  "profile": "local-shape-window",
  "subset_size": 33,
  "cells": [
    "A2-stream-verbatim",
    "C-overprivilege",
    "C-cache-annotation",
    "D-report-retrievable",
    "D-usage-nonzero",
    "D-sources-in-stream",
    "zero-retry-zero-sentry"
  ],
  "cell_labels": {
    "A2-stream-verbatim": "A② 流式逐字无缺",
    "C-overprivilege": "C 越权",
    "C-cache-annotation": "C 缓存命中显式标注",
    "D-report-retrievable": "D 报告档可查回",
    "D-usage-nonzero": "D usage 非零",
    "D-sources-in-stream": "D sources 事件在流里",
    "zero-retry-zero-sentry": "零重试零哨兵"
  },
  "windows": [
    {
      "window_id": "shape-window-1",
      "bank_sha16": "686c564ff2985744",
      "subset_sha16": "823ec81ff11b6345",
      "evidence_sha16": "cb972fd93fa915c0",
      "phases": [
        {
          "phase": "相1-流式道",
          "switches": {
            "REPORT_LANE_VIA_QUEUE": "off"
          },
          "cells": [
            "A2-stream-verbatim",
            "C-overprivilege",
            "C-cache-annotation",
            "zero-retry-zero-sentry"
          ],
          "question_ids": [
            "doc-01",
            "doc-19",
            "chat-01",
            "chat-12",
            "metric-01",
            "metric-19",
            "data-01",
            "data-12",
            "insight-01",
            "insight-07",
            "chart-01",
            "chart-04",
            "approval-01",
            "approval-03",
            "approval-06",
            "scope-01",
            "scope-06",
            "unsupported-01",
            "unsupported-04",
            "tool-01",
            "tool-04",
            "report-01",
            "report-02",
            "report-03",
            "report-04",
            "report-05",
            "report-06",
            "report-07",
            "report-08",
            "report-09",
            "report-10",
            "report-11",
            "report-12"
          ],
          "approval_rounds_planned": 13,
          "approval_question_ids": [
            "insight-07",
            "chart-01",
            "chart-04",
            "tool-01",
            "tool-04",
            "report-02",
            "report-04",
            "report-05",
            "report-07",
            "report-09",
            "report-10",
            "report-11",
            "report-12"
          ]
        },
        {
          "phase": "相2-队列道",
          "switches": {
            "REPORT_LANE_VIA_QUEUE": "on"
          },
          "cells": [
            "D-report-retrievable",
            "D-usage-nonzero",
            "D-sources-in-stream",
            "zero-retry-zero-sentry"
          ],
          "question_ids": [
            "report-01",
            "report-02",
            "report-03",
            "report-04",
            "report-05",
            "report-06",
            "report-07",
            "report-08",
            "report-09",
            "report-10",
            "report-11",
            "report-12"
          ],
          "approval_rounds_planned": 8,
          "approval_question_ids": [
            "report-02",
            "report-04",
            "report-05",
            "report-07",
            "report-09",
            "report-10",
            "report-11",
            "report-12"
          ]
        }
      ],
      "question_plays": 45,
      "unique_questions": 33,
      "replayed_question_ids": [
        "report-01",
        "report-02",
        "report-03",
        "report-04",
        "report-05",
        "report-06",
        "report-07",
        "report-08",
        "report-09",
        "report-10",
        "report-11",
        "report-12"
      ],
      "approvals_planned_total": 21,
      "approvals_per_phase": {
        "相1-流式道": 13,
        "相2-队列道": 8
      }
    }
  ],
  "cell_phases": {
    "A2-stream-verbatim": [
      "相1-流式道"
    ],
    "C-overprivilege": [
      "相1-流式道"
    ],
    "C-cache-annotation": [
      "相1-流式道"
    ],
    "D-report-retrievable": [
      "相2-队列道"
    ],
    "D-usage-nonzero": [
      "相2-队列道"
    ],
    "D-sources-in-stream": [
      "相2-队列道"
    ],
    "zero-retry-zero-sentry": [
      "相1-流式道",
      "相2-队列道"
    ]
  },
  "cell_question_ids": {
    "A2-stream-verbatim": [
      "doc-01",
      "doc-19",
      "chat-01",
      "chat-12",
      "metric-01",
      "metric-19",
      "data-01",
      "data-12",
      "insight-01",
      "insight-07",
      "chart-01",
      "chart-04",
      "approval-01",
      "approval-03",
      "approval-06",
      "scope-01",
      "scope-06",
      "unsupported-01",
      "unsupported-04",
      "tool-01",
      "tool-04",
      "report-01",
      "report-02",
      "report-03",
      "report-04",
      "report-05",
      "report-06",
      "report-07",
      "report-08",
      "report-09",
      "report-10",
      "report-11",
      "report-12"
    ],
    "C-overprivilege": [
      "scope-01",
      "scope-06"
    ],
    "C-cache-annotation": [
      "doc-01",
      "doc-19",
      "chat-01",
      "chat-12",
      "metric-01",
      "metric-19",
      "data-01",
      "data-12",
      "insight-01",
      "insight-07",
      "chart-01",
      "chart-04",
      "approval-01",
      "approval-03",
      "approval-06",
      "scope-01",
      "scope-06",
      "unsupported-01",
      "unsupported-04",
      "tool-01",
      "tool-04",
      "report-01",
      "report-02",
      "report-03",
      "report-04",
      "report-05",
      "report-06",
      "report-07",
      "report-08",
      "report-09",
      "report-10",
      "report-11",
      "report-12"
    ],
    "D-report-retrievable": [
      "report-01",
      "report-02",
      "report-03",
      "report-04",
      "report-05",
      "report-06",
      "report-07",
      "report-08",
      "report-09",
      "report-10",
      "report-11",
      "report-12"
    ],
    "D-usage-nonzero": [
      "report-01",
      "report-02",
      "report-03",
      "report-04",
      "report-05",
      "report-06",
      "report-07",
      "report-08",
      "report-09",
      "report-10",
      "report-11",
      "report-12"
    ],
    "D-sources-in-stream": [
      "report-01",
      "report-02",
      "report-03",
      "report-04",
      "report-05",
      "report-06",
      "report-07",
      "report-08",
      "report-09",
      "report-10",
      "report-11",
      "report-12"
    ],
    "zero-retry-zero-sentry": [
      "doc-01",
      "doc-19",
      "chat-01",
      "chat-12",
      "metric-01",
      "metric-19",
      "data-01",
      "data-12",
      "insight-01",
      "insight-07",
      "chart-01",
      "chart-04",
      "approval-01",
      "approval-03",
      "approval-06",
      "scope-01",
      "scope-06",
      "unsupported-01",
      "unsupported-04",
      "tool-01",
      "tool-04",
      "report-01",
      "report-02",
      "report-03",
      "report-04",
      "report-05",
      "report-06",
      "report-07",
      "report-08",
      "report-09",
      "report-10",
      "report-11",
      "report-12"
    ]
  },
  "r453_binding": {
    "A2-stream-verbatim": [
      "frame_shape"
    ],
    "C-overprivilege": [
      "escalation_annotation",
      "error_class_shape"
    ],
    "C-cache-annotation": [
      "escalation_annotation"
    ],
    "D-report-retrievable": [
      "queue_readback"
    ],
    "D-usage-nonzero": [
      "usage_fields_present"
    ],
    "D-sources-in-stream": [
      "event_surface",
      "citation_shape"
    ],
    "zero-retry-zero-sentry": [
      "retry_sentinel_shape"
    ]
  },
  "r453_payload_coverage": {
    "D-sources-in-stream": {
      "fields": [
        "sources_present",
        "sources_shape"
      ],
      "suppliers": {
        "sources_present": [
          "event_surface"
        ],
        "sources_shape": [
          "citation_shape"
        ]
      },
      "missing": [],
      "owner_count": 2,
      "closable": true
    }
  },
  "r453_roster_snapshot": {
    "path": "scripts/eval_cloud_window_readout.py",
    "sha16": "1a0c91ffb725feb4",
    "cells_total": 28,
    "cloud_readable": 10,
    "local_only": 18
  },
  "r453_cloud_unreferenced": [
    "answer_shape",
    "approval_gate_shape"
  ],
  "r453_local_only_out_of_scope": [
    "answer_char_count",
    "citation_count_value",
    "context_limit_exceeded_count",
    "correctness",
    "evidence_score",
    "first_visible_ms",
    "latency_ms",
    "max_wall_ms",
    "min_wall_ms",
    "p50_wall_ms",
    "p95_wall_ms",
    "per_category_score",
    "rewrite_leg_seconds",
    "throughput_tokens_per_second",
    "total_score",
    "unsupported_claim_rate",
    "usage_token_values",
    "wall_ms"
  ],
  "r453_unproven_shape_cells": [],
  "r453_ledger_binding": {
    "approval_rounds": "approval_gate_shape"
  },
  "unattainable_here": {
    "C-overprivilege": "生产 department/classification 现值为空（AGENTS.md pgvector 格③：欠业主侧 A1 users.department 回填＋A3 密级标签回填，H13 未裁）⇒ 本机拿不到「客户数据上的隔离」这一形，沙盒合成标签不在此窗",
    "C-cache-annotation": "P-18 要求开窗前 Redis answer:* 计数为 0（runbook 前置第 8 步），命中即 raise 停窗⇒ 本窗按纪律只能拿到「零命中」这一负形，正形需要总控另裁一枚探针臂"
  },
  "out_of_scope_statement": "分数与时延类格不在形状窗范围内",
  "out_of_scope_cells": [
    "A1-end-to-end-p95",
    "A4-category-score",
    "C-bank-score-no-regression",
    "aggregate-correctness"
  ],
  "auto_approve_boundary": "自动批准只允许打在评测容器＋评测账号那一条路径，生产/演示路径一个字不碰"
}
```

