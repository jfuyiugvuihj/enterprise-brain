# R678 · 待派池工单（由 R679 从账面派生·判据原文逐字·非总控亲签）

**号**：R678
**基点**：9efff02
**状态**：不由本文携带——跑 `python scripts/tickets_index.py --verify` 现取
**写域**：
- `scripts/eval_transport_ask_v2.py`
- `scripts/r573_caliber_reconciliation.py`
- `tests/test_r678_*.py`
- `docs/tickets/R678-*.md`
- `docs/testing/r678-<今天>.md`

派工时由总控按写集复核上面四格；本行以下不再是机器字段。

## 判据原文（逐字·一个字不许改）

```verbatim source="LINE::docs/handoff/2026-09-15-backend-followup-requests.md::现取 R678"
| 8 | 事故分三本账·编排故障不得用新增针闭合 | **合理·要先补一条分类定义** | 现取事故 max **#122**，其中大头（`at_` 消息 id 污染、投递死、抄错 id、误杀 pytest、429 限流）在说自己的管道，不是产品 | 与在册「编号卫生：写事故号前先 `rg` 取 max」不冲突；但**量具缺陷没家**——现取 R678（`scripts/eval_transport_ask_v2.py::DECLARE_LANE_TIER` 缺省空串 ⇒ 三扇 on 相窗对 D 门是废样本）落在产品与编排之间 ⇒ 建议加第四本「量具／仪表」，仍配测试、不编项目史号 | 降的是**账面噪声**：口径＝三本分账后，「产品缺陷／编排故障／流程违规／量具」各类枚数可分别统计，班与班可比 | 若不定义「量具缺陷算哪本」，它会成为逃避编号的后门（把真缺陷记成编排故障就不配测试了）——反证牙必须咬「记成编排故障但交不出框架改动 diff」这一形 |
```

出处谓词＝`LINE::docs/handoff/2026-09-15-backend-followup-requests.md::现取 R678`。尺会按这枚谓词重读源文件逐字符比对，改一个字就点名「哪一号第几块自第几个字符起不合」。

## 账面点名的落点（派生自上面判据原文里的反引号路径）

- `scripts/eval_transport_ask_v2.py`

## 总控亲签段（派工口径·以上「判据原文」逐字块为准）

## 现取病形（带 1 三扇实测）

- `scripts/eval_transport_ask_v2.py::DECLARE_LANE_TIER` 缺省**空串** ⇒ 传输层从不发 `lane` ⇒ 即使把容器 `REPORT_LANE_VIA_QUEUE` 翻成 on，报告档也**不入队**，只是走了同步腿。
- 后果：带 1 已收的三扇 on 相（run24s2／24s2b／24s2c）里 `scripts/r573_caliber_reconciliation.py::r573-A2` 逐枚 **rc=2**，12 枚报告题正文全在（长 99–2884 字）但 `answer_source` 逐枚是 `eval_transport_ask_v2:transport` ⇒ 三扇相对 D 门**全是废样本**，D 门三格至今未验。

## 判据（每条都可失败，缺一枚判负）

1. 缺省行为**不许静默**：`DECLARE_LANE_TIER` 未设时，量具必须在开跑那一刻**具名报错并退出**（非零 rc），错误句点名「报告档要 on 相必须显式声明 tier」；🔴 不许改成「未设就自己猜一个」——猜出来的样本比废样本更坏。
2. 显式设定时：`lane` 必须逐请求出门，且能在帧账／sidecar 里**现读**到 `answer_source` 不再是 transport 默认值。加一枚离线牙：喂一份「没声明却指望入队」的桩 ⇒ 尺子必须非零并点名那一扇。
3. 反证牙双向：把声明腿摘掉 ⇒ 牙必须红；补回 ⇒ 必须绿。摘牙定义见 `docs/version-roadmap-and-requirements-2026-10-05.md` §1 第 6 条（G1 甲），不许用 `skip`／放宽断言糊过去。
4. **不许动被测物**：评测夹具、`tests/test_evaluation_report.py`、判分器、`deploy/.env.server` 里 `REPORT_LANE_VIA_QUEUE` 的当前值（现读 `off`）一格不许动；容器与镜像动作属禁区，真 on 相由总控在窗后开。
5. 交付含：改前／改后各一遍的同名件两态数字（窗内禁跑 ⇒ 标 `NOT_RUN_IN_WINDOW` 交回由总控窗后补跑）、rc 读数、以及「下一次带 3 该怎么声明」的一步操作句（写进凭据纸，别写进散文台账）。

## 写域（只许这些）

`scripts/eval_transport_ask_v2.py`／`scripts/r573_caliber_reconciliation.py`（仅当 rc=2 的归因句要跟着改口）／新增 `tests/test_r678_*.py`／`docs/tickets/R678-*.md`／新凭据纸 `docs/testing/r678-<今天>.md`

## 禁区（踩线即退回）

`app/**`／`frontend/**`／`docs/handoff/**`／`docs/api/contract-v1.md`／评测夹具与判分器／`scripts/run_gate.py`／`deploy/**`／任何容器与镜像动作／主树任何路径。

## 交付清单

1. 判据原文逐字进单：`python scripts/tickets_index.py --verify` 必须绿，退出码 0。
2. 同名件两态读数：state① 本树已 apply 未 commit／state② `git archive 9efff02` 干净检出＋只投本单货；清单逐枚相同、总数相同，标「执行层自报」。
3. 凭据纸 `docs/testing/r678-<开工日>.md`：判据实际读数（枚数／字节数／退出码），不许形容词。
4. 反证牙：改掉盘上副本里的一处判据原文 ⇒ 校验非零退出并点名哪一号哪一条被改了字。
5. 坐标一律 `文件::符号`，禁止 `文件:数字` 形态的行号。
6. 收席那一刻现取：`rev-list --count 9efff02..HEAD`、staged 清单、未跟踪逐枚点名、`diff --numstat HEAD`。

## 这一枚为什么存在

待派池的散文账只有一行「R678（…）」，开工的人得重读整本跟进单或看板才能拿到判据原文。
本文件把那一段逐字搬进 `docs/tickets/`，从此逐号状态的唯一真源是工单目录，
每班开工只读 `docs/tickets/index.tsv` 与本文件。


---

## 执行层交付（R678·开工日 2026-10-05·待总控验收并树）

- 树＝C:/Users/fengx/PycharmProjects/be-r678；基点＝d653e41（派工口径；本文件机器字段仍写 9efff02，
  两者只差一枚 index.tsv 重生成账，与本单货无涉）。主树 0 次写入。
- 写集逐枚点名：scripts/eval_transport_ask_v2.py（声明闸＋前置 CLI＋收窗自查那一格）／
  scripts/r573_caliber_reconciliation.py（--expect-lane-phase on 的事后尺，只在 rc=2 归因句那一格改口）／
  新增 tests/test_r678_lane_declaration_gate.py／新增 tests/test_r678_waste_sample_ruler.py／
  本文件文末追加／新凭据纸 docs/testing/r678-2026-10-05.md。
- 五枚判据的读数全在凭据纸里（§1 判据①·§2 判据②·§3 判据③·§4 判据④·§5 判据⑤），本段不复述数字，
  只记三件必须让验收一眼看见的事：
  ① 「未设即致命」没有按字面整本做——它和并树在册钉
  tests/test_r520_declare_lane_env_leg.py::test_an_unset_key_leaves_the_report_tier_on_the_sync_path
  （写域外那枚文件）正面冲突。交付形态＝「未设＋指望入队
  才致命」，同步相那格逐字节照旧，另有 --lane-preflight 那一步与事后尺两道闸。理由与翻字面所需的前置
  动作写在凭据纸 §7 第 2 条。
  ② 判据② 的「现读到 answer_source 不再是 transport 默认值」在这台机上量不出来：answer_source 由
  采集器写死＝args.transport，与走哪条道无关（scripts/collect_evaluation_answers.py::build_answer）。
  交付改用侧车／帧账的 kind 那一列＋第三份件的 sent_lane，并把「拿 answer_source 当 D① 信号会读假绿」
  记进凭据纸 §2 与 §7 第 3 条。
  ③ 自动那一腿的边界：transport 那道门只认量具自己进程环境里与产品同名的开关，不读 deploy/**、
  不问容器（判据④ 的死线）。带 1 那三扇的实况（容器 on／采集进程两样都没有）拦住它的是前置那一步
  与事后尺；要做成「开窗即致命」需要 driver／collector 在开窗那一刻调用 require_lane_declaration，
  两枚文件都在写域外 ⇒ 建议另立一号。
  ④ 一枚编号撞车（本席自己发现并自己处置）：`scripts/eval_transport_ask_v2.py` 有两枚在册注释按编号引用
  「抬头第 14 条」，而那条自并树笔 02ee2e6 起从未落地；本单那段若记 14 号就会把这两枚引用引到一枚内容
  全错的口径上。处置＝本单那段改记 15 号，R642 那两行一字不碰，悬空引用另立一号（凭据纸 §7 第 5 条）。
- 同名件两态：NOT_RUN_IN_WINDOW（夜窗在跑·窗内禁跑测试）。清单与补跑口径见凭据纸 §5 第 2 条。
- 反证牙：三把量具刀＋一把尺子刀，摘腿必红／补回必绿／每把进刀前后各核一次原件 sha256；另有盘上副本改
  判据原文一个字⇒ --verify rc=5 点名到字符。第一轮读数在凭据纸 §3 与 §5 第 4 条，第二轮（改完编号重取）
  四枚探针的逐形读数在 §8：gate 6 形＋7 条判据全过、preflight 12 形 rc 全等预期、r573 5 形 rc＝[0,0,2,0,0]、
  knives 7 条判据全过。
- 🔴 本席在隔离树里跑不动 §6 的第① 步：deploy/.env.server 未被 git 跟踪 ⇒ 工作树里没有那枚件，
  实取 rc=4「问不着」（不是缺陷，是那一格的形状）；带 3 的这一步得由总控在真装着那本 env 的盘上取。
- 真 on 相窗（D 门三格）仍未验：本单一枚模型没打、一台容器没碰。
