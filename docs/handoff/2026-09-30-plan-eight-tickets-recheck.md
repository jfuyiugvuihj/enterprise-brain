# 计划书 §5.2 八枚零提交单逐枚复评（R521·2026-09-30·只读取证）

本纸是谁写的、能采信到哪一步：R521 执行层单。工作树 `C:\Users\fengx\PycharmProjects\be-r521`，基点 `97724c5`（复取命令与读数见 §6）。
全单零代码改动、零 `git add`、零 commit，未起服务、未动容器、未打模型；唯一产物是本纸。所有数字均标「执行层自报」并附命令。

## 0. 口径与取证方法

三态定义（本纸只用这三个词，不用「应该已经落了」）：

- **已并树（凭 sha）**：判据字面要求的产物在 `97724c5` 上，且能指名哪一枚并树提交。
- **部分落地（差哪几格）**：产物在树，但逐格对判据仍有点名未达的格子；本纸逐格点名并给文件与行。
- **真欠（欠什么·哪个文件·几行）**：树上找不到该格产物。

判据原文坐标（现取，不抄计划书转述）：`docs/handoff/2026-09-15-backend-followup-requests.md` §21 表。
表头在 LF495（四列：单号｜内容与落点｜判据（机器可验）｜禁改边界），八枚行号 = R29 LF501、R31 LF503、R32 LF504、R33 LF505、
R38 LF510、R43 LF514、R46 LF517、R48 LF519。

🔴 **LF 不是文本行**（本单实测，取段前已核验段落标题）：该文件 996 481 B / 584 306 字符，CR 6 124 枚、LF 4 660 枚，
其中 lone CR 1 534 枚、lone LF 70 枚 ⇒ `ReadAllLines` 交回 6 195 行，而按 `\n` 切只有 4 661 段。
后果：`Select-String` 报的行号与 §21 内部自引的 L505/L510/L517 不同源 —— 那些自引是 LF 口径。
本单踩过一次：R33 改写版判据在文本行 T3369-T3373，同一个数字在 LF 口径是别的字（LF3369 讲的是 R265）。

八枚的 sha 全部逐枚现取（`git cat-file -t` = commit，且 `git merge-base --is-ancestor <sha> HEAD` rc=0），
并核对「mentions 该号的提交是否全在 HEAD 上」：`git log --oneline -E --grep` 加号边界，八枚的 on_HEAD 与 on_ALL 逐枚相等
（23/12/8/8/8/9/13/10）⇒ 本波没有「产物活在别的分支上没并回来」的暗账。

引用面复核过一遍（读数在 §6 读数 4）：本纸每一枚 `文件:行号` 都在 `97724c5` 这棵树上按**绝对路径**逐枚读过——带行号或行区间的引用 token 102 枚、
  区间展开去重得 740 枚 `文件:行`，MISSING_FILE＝OUT_OF_RANGE＝0（两枚自计数按交回前最后一次复算；本纸后来再增删文字，读者改完要重算）。同处记了本单踩到的一枚取证陷阱：PowerShell 的 `Set-Location`
  不移动 .NET 进程的 CWD，`[System.IO.File]::ReadAllText(相对路径)` 会读到主树那份（本树 CRLF／主树 LF，LF 枚数相同⇒行号同义，
  但对拍过一次才敢用）。

## 1. 速览（八枚三态）

| 单号 | 三态 | 凭据（并树 sha） | 今天还欠 |
|---|---|---|---|
| R29 | 已并树（结案口径＝判负） | `791568c`；等效半张 `158259f`（R100 兼容腿真关思考） | 0 行码。判据② 未达成那一格＝业主动作（换无思考模型） |
| R31 | 部分落地 | `eef642b`＋`3aba146`（R149 线上多发）＋`8f429b7`（R203 生成腿真流式）＋`fe5b180`（R210）；尺 `97724c5`（R518） | 三格：审批续跑道无 sink、队列道无 sink、腿名 0/105 派生不出 |
| R32 | 已并树 | `8a91f4e`＋`1cbd164`（R141 档位真生效＋前端选择器） | 0 行码。契约每枚数字格仍是「待真机样本」，那格属 R105 乙半 |
| R33 | 已并树 | `9678d21` | 0 |
| R38 | 部分落地 | `2e6abc6` | 1 格：真机抽查读数（欠 0 行码） |
| R43 | 部分落地 | `4586bb4`（R43a）＋`839c344`（R167＝R43b） | 2 格：cached 落库（4 处码）、E3 档读数 |
| R46 | 部分落地 | `eaa9af8`（R152）＋`4c11efb`（R153）＋`484536c`（R195 前端出口终于有人按） | 3 格：「点击」半张零实现、真库真并发强度未证、按人限额待业主裁 |
| R48 | 部分落地 | `0ad3d3e`（路线甲） | 1 格：判据① 首屏 ≤1 s（欠 0 行码，欠的是业主裁口径＋换引擎） |

🔴 这张表**不推翻**计划书 L470 与 L474 那两格勘误（七枚早已在主干、R46 消费侧在 R195 名下），它是把「在主干上」细化成「逐判据格达没达」。
按「产物在树即算清」这一格，八枚全清；按「判据全达才算清」，八枚里有六枚还欠格子 —— 见 §2 逐枚与 §5 没量到的清单。

## 2. 逐枚复评

### R29 思考税：迁原生 `/api/chat` 或派生 `think false` 模型（计划书 L179／判据原文 LF501）

判据原文四格：① `thinking` 字段实测为 0 字；② 生成轮 30.6 s → ≤22 s；③ 前置 R36 质量基线已建立、制度题准确率不得下降；
④ `tool_calls` 报文重做后权限/超时语义全复验。禁：不许只在 `/v1` 加参数就当完成；不许在无线上端点证据前宣布关掉了思考。

三态：**已并树（结案口径＝判负）**，凭 `791568c`。逐格：

- ① **部分落地**：原生腿确实带 `think:false`（`app/common/model_handler.py:554`），日志逐发印 `thinking_chars=`（`:623`）。
  但**生成腿没迁**：它仍走兼容腿 `ChatOpenAI`（`app/agents/nodes.py:1164`），「关掉思考」这一格实际由 R100 用另一条路买到 ——
  `MODEL_THINKING` 默认 `disabled`（`app/common/model_budget.py:780`）＋ 请求体带 `thinking:{type:disabled}`（`thinking_extra_body():870`，
  在 `nodes.py:816` 随 `max_tokens` 同一枚 body 发出去）。⇒ 「0 字」是兼容腿上的字段生效，不是原生腿。
- ② **真欠（且欠的不是码）**：并树提交原话记着「30.6 s→≤22 s 至今一分钱没省下来，思考税按实测改判为模型能力问题」。
  要拿这一格得换无思考模型，而换模型＝换质量基线，归业主（R101 亦已判明答题腿走 compat 是双重既有裁定，非遗漏）。
- ③ **不再拦路**：run9 那 105 题的帧账在册（本单亲自按它跑过只读量具，见 §6 读数 1），前置那一格的事实基础在场。
  本单不替 R36 宣布逐判据结案。
- ④ **结构上无从触发**：原生腿三个调用点全不 `bind_tools`（`app/api/v1/chat.py:1237` 追问改写、`:1695` legacy `/chat`、
  `app/rag/retrieval_pipeline.py:221` 多路改写），所以「`tool_calls` 报文重做后复验」这件事今天没有现场。
  已交的是把那枚陷阱拆开：`NATIVE_PROTOCOL_ABSENT_STATUSES`（`model_handler.py:87`）与 `NATIVE_REQUEST_REJECTED_STATUSES`（`:90`）
  不再混成一类 —— 这是 R147（`70695df`）治掉的 R29 具名上报缺陷；字符串 `arguments` 撞 400 那一形由 `:82-83` 记名钉住。

写域（`git show --numstat 791568c` 现取，四枚）：`app/agents/nodes.py` +80/−9、`app/common/model_budget.py` +20、
`app/common/model_handler.py` +22/−2、`tests/test_r29_thinking_tax.py` +1079。
三枚热文件冲突：`app/agents/nodes.py` ✔（会撞）、`app/agents/orchestrator.py` ✘、`frontend/src/App.vue` ✘。
前置：无（R25/R27/R28 在它之前，都已在树）；它自己是计划书 L167 那条腿① 串行链上 R31 的字面前置 —— 该前置已满足。

可失败判据草稿（写给「若真要复工 R29」这一枚，不是写给今天）：

1. `git grep -c NATIVE_CHAT_SUFFIX -- app/agents/nodes.py` 现取必须仍为 0；谁把生成腿迁原生，这一格才允许翻成 ≥1，且新用例要点名那一发 transport 为 `ollama-native`。
2. 同一模型同一批 8 问，兼容腿与原生腿各跑一臂、两臂都 warm，交回中位数之比 ≤0.72（对齐 30.6→22）；冷启动那一发剔除并点名题号 —— 否则不许宣布判据② 达。
3. 对新 probe 全行 `rg -n thinking_chars=`：最大值必须为 0，非 0 逐枚点名题号与字节数。
4. 迁腿之后对那一轮 `SELECT input_tokens, output_tokens FROM model_calls` 必须仍拿得到值（今天流式形状带不出 usage，见 R38 那一格）—— 迁腿若把两列打成 NULL，即 R38 倒退，当场红。
5. `python scripts/run_gate.py` 在同一 HEAD 与并树前那次互比，红数 0（门再便宜也全跑，反证钉不分层出门）。

重估人日：**0**（判负结案，码已交）；若业主改口要迁腿，按原估 1.5 人日重开，另计换模型后的评测复跑（不计码）。

### R31 生成轮流式透传＋片段边界规则（计划书 L181／判据原文 LF503）

判据原文四格：① `text` 事件数 >1；② 片段时间戳不重叠、逐字比对无缺字；③ 后端每片 ≥20 字或 100 ms 合并，禁单字碎片；
④ 与 legacy 全量重发共存不冲突。禁：禁改 `frontend/**`；必须排在 R27/R29/R30 之后。

三态：**部分落地**。凭四枚并树 + 一枚量具：`eef642b`（①a 后端半张）、`3aba146`（R149 把合格片发到线上）、
`8f429b7`（R203 图路径生成腿真走流式，治掉当年那枚死道）、`fe5b180`（R210 断流轮不拼屏）、`97724c5`（R518 让量具说清哪一轮确有逐片腿）。逐格：

- 机制四格全在树，且**调用点核过**：唯一 sink 注册点 `app/api/v1/chat.py:2735`（在 `_ask_stream`，`:2689` 起），
  注册进 `configurable` 的是 `app/agents/orchestrator.py:1400`；交片出口 `app/agents/nodes.py:504 publish_stream_pieces`，
  生产调用两枚：`:1053`（逐 chunk 喂 merger）与 `:1117`（末片）。判据③ 那三把尺现读：`nodes.py:327` = 20 字、`:329` = 0.1 s、
  `:332` 空档地板 = 4 字（禁 1，正是「禁单字碎片」那条）。判据② 的不重叠由 `:480-487` 抬起点保证（区间可偏窄不可重叠）。
- 判据①/② 的**真机读数**（本单亲跑在册量具，非抄纸）：②原文全分母 **94/105 绿、红 11 枚**（approval-06 chat-03 chat-06 chat-09 chat-10 data-09 doc-07 metric-02 metric-16 scope-01 scope-02）；
  甲案分腿读 **93/93**（原文两格）、严读 **91/93**，红 = `report-02`、`tool-04`；分母守恒 105 = 93 + 9 + 2 + 1 + 0。原文与命令见 §6 读数 1。
- 🔴 差格三条（都是结构缺口，不是缺码行数）：
  a) **审批续跑道接不到片**：`run_interrupt_stream` 的形参清单现读为 thread_id / approved / user / request_id / trace_id / task_id / cancel_event
     （`app/agents/orchestrator.py:1545-1554`）—— 不收 `stream_piece_sink`。且即使收了也发不出第二枚字：审批腿正文由
     `build_precheck()` / `extract_standard()` 确定性拼出（`app/agents/nodes.py:548-556`；`build_precheck()` 真调用点在 `orchestrator.py:1057`），
     全文零枚模型符号 —— 这一条已被总控 09-29 裁定记成 `not_applicable`（计划书 L486），不算缺陷。
  b) **队列道接不到片**：`queued_response`（`app/api/v1/chat.py:2446`）不注册 sink，与 a) 同一族。
  c) **帧账派生不出腿名**：R518 自己交回「腿名可派生行数 0/105」，要证只能读后端日志里的 `leg=`/`call=`/`dropped=` 或复跑。
- 判据④ 在树：`publish_stream_pieces` 无人注册时直接 return（`nodes.py:518-526`），不建列表、不发事件，graph 级快照形状一字不动。

写域（`git show --numstat eef642b` 现取）：`app/agents/nodes.py` +230/−1、`app/agents/orchestrator.py` +14、
`tests/test_r31_generation_stream_passthrough.py` +281、`tests/test_r31_stream_pieces.py` +323。R149/R203 另各带自己那批（含 `chat.py`）。
三枚热文件冲突：`nodes.py` ✔、`orchestrator.py` ✔（八枚里唯一同时撞这两枚的）、`App.vue` ✘。
前置（**用树上证，不抄计划书 L167**）：R27 已在树（`6a4f02b`；确定性计划命中复读 dispatch、跳过第二发，现读 `orchestrator.py:463-469`）；
R29 已在树（`791568c`，判负结案）；R30 的产物已在树（`git grep -n timeout=30 -- app` 现取 **0 命中**，档位预算与按 prompt 缩放的时钟在
`app/common/model_budget.py:951 model_tier_budget` 与 `nodes.py:782 _budget_kwargs`）。⇒ **R31 今天不再等任何前置**。

可失败判据草稿：

1. `python scripts/r518_a2_lane_attribution.py` 现取：分母守恒式必须 True（105 = 93+9+2+1+0），且 `not_applicable` 那 9 枚必须逐枚点名 —— 并进「过」那一堆即红。
2. 同一命令读 1 的绿数：从 94 涨不到 105 就不许宣布「②原文全绿」；红名单与上一窗对不上时必须点名差在哪几枚。
3. 若给审批续跑道接 sink：`git grep -n stream_piece_sink -- app/agents/orchestrator.py` 现取必须 ≥2 处（两跑道各一）。仍为 1 处＝没接上。
4. 接上之后 `python -m pytest tests/test_r203_sink_reaches_the_leg.py -q` 里那枚「审批道自己注册了出口 ⇒ 这条结论要重写」的负向钉**必须当场红**；改口须连文档同源散文一起走（执行层禁碰 docs，红了交回总控）。
5. 腿名那一格：新键必须在册量具里有消费者。给 `FRAME_READING_KEYS` 加一枚没人消费的键，`tests/test_r181_text_frame_ruler.py` 那枚甲案钉与「用了账里没有的键」那一族钉当场红（R518 判据 3 在册）。

重估人日：机制 **0**（已交）；补 a) b) 两条腿的逐字交付 = **0.5**（原估 1.0 已交掉大半，剩的是续跑道那本 config ＋ 收端 piece 一支）；
两枚断流轮（`tool-04`/`report-02`）属缺陷单，计划书 L488-490 已明写不在 R31 里销账。

### R32 问答／分析／报告三档进契约＋前端选择器（计划书 L182／判据原文 LF504）

判据原文三格：① 契约写出三档 SLO；② 档位不改变权限判定；③ `/ask` 非法档 → 400。禁：不得借分档放宽 scope；legacy 事件名一个不许下线。
另有第五格（选择器）是施工时新加的，总控在并树提交正文里裁定「按假控件禁令**不交**」并拆出 **R141** —— 本单按树现状记：R32 + R141 合起来才是判据字面的那一整张。

三态：**已并树**，凭 `8a91f4e`（取值闸＋契约散文归真）＋ `1cbd164`（R141：客户端声明的档位第一次真的改派了工作腿）。逐格：

- ③ 现场核过调用点：闸本体 `app/api/v1/chat.py:1349 _require_valid_lane`，被 `/ask` 路由体第一道调用（`:2493`，函数体从 `:2483` 起）；
  非字符串 lane 保持 pydantic 422（并树提交裁第②笔：不退化成 Any 换 400），这一格已被用例钉住。
- ② 钉在 `tests/test_r32_lane_contract.py:447`（三档同一 authorization scope 同一问法）、`:464`（可见命中集就是该 principal 应得的那一份）、
  `:475`（记账面能分辨两枚身份）。
- ① 契约那节 = `docs/api/contract-v1.md` LF1547 起（标题自署 R105 甲半，09-20）：单位／映射／算术／可寻址格已写死，
  🔴 但 LF1555-1556 原话写着「Nothing in this section is measured」并把每一枚数字格填成「待真机样本」。
  ⇒ 字面「写出三档 SLO」达成的是**口径**，数值格属 R105 乙半（压在跑分窗），不记在 R32 名下。
- 选择器（R141 那半张）在树且不碰 `App.vue`：值表在 `frontend/src/router/lane-choice.js`，读点 `frontend/src/components/ChatPanel.vue:295`
  （并跟随 `?lane=` 地址，`:337-341`），后端回读三枚头 `x-effective-lane` / `x-lane-source` / `x-declared-lane`（`ChatPanel.vue:317-319`；
  后端侧常量在 `chat.py:1383` 起）。图内消费点：`app/agents/nodes.py:1537 resolve_turn_lane`，声明经 `orchestrator.py:1401-1405` 进 `configurable`。

写域（`git show --numstat 8a91f4e` 现取）：`app/api/v1/chat.py` +47、`docs/api/contract-v1.md` +13/−5、`tests/test_error_code_vocabulary.py` +7、
`tests/test_r32_lane_contract.py` +626。R141 另带 `nodes.py`／`orchestrator.py`／前端半张。
三枚热文件冲突：**今天全部 ✘**（残余只碰契约与观测面）；注意历史写域里 R141 当年改过 `nodes.py` 与 `orchestrator.py` —— 已在树，不再构成并行障碍。
前置：无。

可失败判据草稿：

1. `python -m pytest tests/test_r32_lane_contract.py -q` 现取 passed 数必须等于同件 `--collect-only -q` 的枚数（不许拿 skip 抵账）。
2. `rg -n 待真机样本 docs/api/contract-v1.md` 命中数：乙半交数值之前恒 ≥1；谁把某格填成秒数而拿不出 `docs/perf/raw/` 凭据 ⇒ 该枚新用例必须当场红（口径：未实测的秒数＝不可承诺）。
3. TestClient 打 `POST /api/v1/ask` 带 lane=foo ⇒ 400，且信封里的错误码逐字等于既有码（不许新造 invalid_lane；`tests/test_error_code_vocabulary.py:47` 已钉这一条理由）。
4. 三档各跑一问，两枚响应头必须能分辨「你选的」与「系统走的」；换成报告档时 `x-lane-source` 不得从 declared 悄悄翻成 inferred。
5. 改任一档的 scope 判定 ⇒ 上面那三枚钉（`:447`/`:464`/`:475`）至少一枚红；不红就说明它们没牙。

重估人日：**0**（数值那一格属 R105 乙半，不在本单重估范围）。

### R33 每发 prompt token 上限＋无模型裁剪（计划书 L183／判据原文 LF505）

🔴 判据原文以**改写版为准**：跟进单文本行 T3369-T3373 明写「§21 L505 原文大半已被 R30/R112/R117/R122 吃掉」，改写版五格 =
① `orchestrator.py` 内 `ModelTier.COMPRESS` 零调用点且钉成 AST 级（grep 不算）；② 新裁剪纯确定性、零 provider 调用；
③ 硬护栏：裁剪后 `where`/`pred` 权限谓词文本与来源定位串一条不少，反例从真源取不许手抄；④ 裁剪后 prompt 估算不得变胖＋保留条数下限写明轮数与理由；⑤ 反证。
另有一条「它自己刚钉的警报必须仍绿」（`tests/test_r118_subgraph_memory.py` 两枚注释钉 ＋ `test_r98_checkpointer_backend.py`）。

三态：**已并树**，凭 `9678d21`。逐格：

- ① 现取：`git grep -n ModelTier.COMPRESS -- app/` 交回 4 行，其中唯一出现在 `orchestrator.py` 的那一行（`:414`）是**注释**；
  生产调用点是 `app/agents/orchestrator.py:416`，写法为 `compress_messages(all_msgs, tier=ModelTier.ANALYSIS)`。
  枚举采「保留」：`app/common/model_budget.py:234` 仍在，由 `tests/test_r30_timeout_budget.py` 继续按它量表 ⇒ 符合判据「枚举保留还是删净由它给理由」。
- ② 结构上不可回退：`app/memory/summarizer.py:153` 的签名已不收旧式 model 实参，传了就抛 `TypeError`（`:163`，字面「R33 起历史裁剪零模型」）。
  这条比 grep 硬 —— 把旧写法接回来会在第一发就炸，不靠用例记性。
- 「每发 prompt token 有硬上限」那半句今天归 R30/R99/R204 家族：`authorize()`（`app/common/model_budget.py:1263`）在 `nodes.py:811` 被调，
  判不可负担即在报文上 wire 之前拒发（R204 `8636ca4` 把它从「只写日志」改成一刀）。**默认值可达性按调用点核**：`_make_model`（`nodes.py:1134`）
  在 `:1150` 必带 `model_tier_budget(tier)`、`:1177` 传进 `_ResilientModel` ⇒ 生产路径上 budget 恒非 None，`:809` 那条 `if self.budget is None` 只有测试直构能走。
- 写域（`git show --numstat 9678d21` 现取）：`app/agents/orchestrator.py` +9/−6、`app/memory/__init__.py` +3/−3、`app/memory/summarizer.py` +158/−34、
  `tests/test_r33_history_guardrails.py` +335、`tests/test_r33_zero_model_compression.py` +237。
  三枚热文件冲突：`orchestrator.py` ✔、`nodes.py` ✘、`App.vue` ✘。前置：R36（同批合并，会改答案内容）—— 已在树，不再拦路。

可失败判据草稿：

1. `python -m pytest tests/test_r33_zero_model_compression.py tests/test_r33_history_guardrails.py -q` 两件合跑 0 failed（同进程合跑，不许只单跑）。
2. 反证一：把 `orchestrator.py:416` 改回带 `_make_model(ModelTier.COMPRESS)` 的旧写法 ⇒ 必须红在 **AST 级那枚钉**上（红在 grep 上不算过）。
3. 反证二：塞一条含权限谓词与来源定位串的历史跑裁剪 ⇒ 两侧文本逐枚相等；反例文本必须从 `app/rag/filters.py` 与 `app/agents/evidence.py` 现取，手抄即红。
4. 同输入两次裁剪交回逐字节相同（不吃时钟、不吃随机序），且裁剪后 prompt 估算不得大于裁剪前。
5. `python -m pytest tests/test_r118_subgraph_memory.py tests/test_r98_checkpointer_backend.py -q` 必须仍绿，且装配那一格与 `checkpointer=` 那几行零改动（R128 的刀，动了就是越界）。

重估人日：**0**。

### R38 核实 usage 真值（计划书 L188／判据原文 LF510）

判据原文：抽查一问，`input_tokens/output_tokens` 非零且与 Ollama 自报一致；禁：不得估算冒充实测 token 数。
落点四枚（判据原文点名）：`migrations/0002:147` 的计量列、`app/trace/spans.py`、`app/trace/store.py:171`、现 `cached_tokens=0`。

三态：**部分落地**，凭 `2e6abc6`。逐格：

- 通路四格全在树，逐格现读：原生腿读两枚计数 `app/common/model_handler.py:611`/`:612`（外加 `:613` 的 cached，那是 R43a 的）→
  `ModelReply` 带出（形参 `:244-245`，赋值 `:255-256`）→ `app/trace/spans.py:329 model_token_counts()` 两种应答形状都读（`:378-390`）→
  投影进台账 `app/trace/projections.py:305-306`（列清单见 `app/trace/schema.py:86` 起的 model_calls 那一组）。
- 缺值语义：认不出就是**不长键**、落库即 NULL；全链无一处减法或外推 —— `spans.py:312-314` 把 §21 那句「不得估算冒充实测 token 数」写成了禁令本体。
- 判据原文那两处坐标今天一条仍准、一条已换对象：`migrations/0002:147` 现读正是 model_calls 的建表语句（**未漂**）；
  🔴 而 `app/trace/store.py:171` 这一路今天不成立 —— 台账写入早已重构进 projections，`store.py` 里 `input_tokens` 现取 **0 命中**。
  计划书 L67 那句「→ `app/trace/store.py:171`」是同一条旧账（已列入 §4 撑歪清单）。
- 🔴 差的那一格：判据要的「抽一问、两列非零且与自报一致」是**真机读数**，本单禁打模型 ⇒ 没量到（见 §5）。
  流式那一形状今天带不出 usage（`spans.py:362-372` 明写：缺键＝流式说不出来，不是没命中）⇒ 真机抽查必须落在非流式那一发上，
  否则量到的 NULL 会被读成缺陷。

写域（`git show --numstat 2e6abc6` 现取）：`app/common/model_handler.py` +22/−2、`app/trace/spans.py` +41/−4、
`docs/api/contract-v1.md` +1、`tests/test_r38_cached_tokens_honesty.py` +86、`tests/test_r38_native_input_tokens.py` +333。
三枚热文件冲突：全部 ✘。前置：无（观测腿）。

可失败判据草稿：

1. 抽一问答完（非流式那一发），对那一枚 `request_id` 查 model_calls 两列非 NULL，且逐枚等于同一发日志行里 `prompt_eval_count=` / `eval_count=` 的读数（对照面在 `model_handler.py:621`）。
2. 改动前就存在的反证用例：喂一枚只带 `eval_count` 的假应答 ⇒ `input_tokens` 必须为 None（填成 0 或反推即红）。
3. 流式形状必须仍交回两枚 None，并且用例里有一句明写「缺键＝流式说不出来」；谁拿估算填这格，该用例红。
4. 任何把 `prompt_eval_count - cached_tokens` 之类减法写进台账的实现 ⇒ 当场红（判据「不得估算冒充实测 token 数」）。

重估人日：**0.25**（原估 0.5 里码那半已交；剩真机抽查＋读数记录，零产码，但要一台能开窗的机器）。

### R43 system prompt 前缀复用、可变内容后置（计划书 L193／判据原文 LF514）

判据原文两格：① 同一前缀字节级稳定（无时间戳／无随机顺序）；② E3 档实测 `cached_tokens > 0`。禁：不许把权限信息塞进可复用前缀。
并树时总控只宣布 **R43a** 结案，并明写「R43b 未单列，本班不替它宣布整单结案」（跟进单 LF2961）—— 本单实测：R43b 后来以 **R167** 落地。

三态：**部分落地**。凭 `4586bb4`（R43a：原生腿 cached 计数接上＋改写 prompt 可变内容后置）＋ `839c344`（R167＝R43b：答案腿前缀账＋尺＋三把反证刀）。逐格：

- ① **已并树（两半都在）**：改写腿 `app/rag/retrieval_pipeline.py:46 REWRITE_PROMPT` 现读为「固定指令全在前、问题本身是整段最后一枚字节」
  （`:40-42` 注释记着改前 `{question}` 夹在两段固定指令**中间**，可复用前缀只有最前那一句）；答案腿 R167 的结论是「段序今天已经是对的，
  本写域可挪字节 = 0」，交回的是账、尺子和反证（`tests/test_r167_answer_prefix_reuse.py` +715）。监督腿同样合规：
  `app/agents/orchestrator.py:455-457` 先取固定 `MAIN_SYSTEM`，只有带记忆时才把可变块 **append 在后面**，不往前插。
- ② **差两格，其中一格今天有码可欠**：
  a) 本机有读数但不是 E3 档：`docs/perf/raw/think_off.jsonl` 本单现取 —— `cached_tokens` **9 枚读数，非零 9 枚**，值全是 257，
     对位 `prompt_tokens` 在 506-510；E3（vLLM）那一档从未测，而 B 行整行 09-24 已移出 V1（计划书 L375-377）。
  b) 🔴 **命中率落不了库**（真欠，欠 4 处）：`git grep -n -i cached -- migrations/` 现取 **0 命中**；`app/trace/schema.py:86` 起的
     model_calls 列清单里没有 cached 那一列；`app/trace/projections.py:297-309` 只把 `input_tokens`/`output_tokens` 两格塞进 values；
     于是 `app/trace/spans.py:391-393` 现场算出来的 `cached_tokens` **在投影这一层被丢弃**。欠的具体东西：一枚新 migration
     （并改 `migrations/manifest.json`）＋ `schema.py` 一行 ＋ `projections.py` 一行 ＋ 用例。`git ls-files migrations` 现读最新是 0017 ⇒ 下一枚号是 0018。
- 另有一格是**在册假话**（只列不改，见 §4 第 1 条）：`app/trace/spans.py:306-310` 与 `:358-361` 至今写着「native 腿的 cached 字段在
  `model_handler.py:394-395` 被丢掉、所以从来没人设它」—— 那是 R38 时代的真话，R43a（09-22）已经把它接上（现读 `:613`＋`:266-267`＋`:631`），
  而 `:394-395` 今天是 `default_model_budget()` 那两行。**纸上说的缺，树上已经不缺了**；判据② 真正的堵点是 b) 那格落库，不是拷贝。

写域：`git show --numstat 4586bb4` 现取 = `app/common/model_handler.py` +24/−5、`app/rag/retrieval_pipeline.py` +9/−3、
`tests/test_r43a_native_cached_tokens.py` +250、`tests/test_r43a_rewrite_prefix_reuse.py` +249；R167 只新增一枚测试件 +715（零产码）。
三枚热文件冲突：全部 ✘。前置：R38（同一枚 `ModelReply` 载体）—— 已在树。

可失败判据草稿：

1. 台账侧先立红钉：对任意 `request_id` 查 model_calls 的 cached 列 —— **今天这枚查询必须因缺列当场失败**，先把红钉在册，不许在补 migration 之前宣布判据② 达。
2. 缺值语义不许被新列改宽：服务端没报 `prompt_eval_cached_count` 那一发，列必须是 NULL 而不是 0（`_reported_count` 现语义 ＋ `tests/test_r38_cached_tokens_honesty.py` 在册）。
3. 前缀稳定：同一固定段连发两发，逐字节公共前缀 ≥ 上一窗读数（R43a 口径：可复用前缀 39.7% → 85.5%）；任何时间戳或随机序进前缀 ⇒ R167 那把 AST 尺当场红。
4. 权限字节：把 `where`/`pred` 谓词或身份挪进可复用前缀 ⇒ 必须红（判据原文「不许把权限信息塞进可复用前缀」；R167 的 `test_no_prompt_byte_sits_after_variable_bytes_in_the_two_files` 是同族牙）。
5. 落库后 E2/E3 各跑一窗：`SELECT … cached_tokens IS NOT NULL` 计数必须 >0，且不许拿它反推 `prompt_eval_count - cached`（判据「不得估算」）。

重估人日：**0.5**（原估 0.5；今天只剩落库那半张 0.25 ＋ E3 读数 0.25，答案腿那一半 R167 已交、不再计）。

### R46 活动信号回填排序（计划书 L196／判据原文 LF517）

判据原文三格：① 有信号后排序变化可测；② **无信号时与现状一致**；③ 隐私：只存计数不存内容。禁：不得把用户问题原文写进新表。
标题里那一路「点击」也在判据字面上（采纳/驳回/点击 → 相关度先验）。

三态：**部分落地**。凭 `eaa9af8`（R152 后端半张）＋ `4c11efb`／`509c1c7`（R153 强度校准：把先验从「值多少分」改成「最多挪几名」）＋ `484536c`（R195 前端出口终于有人按）。逐格：

- 施加面（这是「消费侧在不在树」那一问的正答，按调用点核）：`app/rag/retriever.py:1562 _apply_activity_prior` 被**五条读腿出口**调用 ——
  `:1493`（降级）、`:1496`（热集）、`:1503`（**PGVector 读腿**）、`:1549`（Chroma 语义腿）、`:1560`（关键词兜底）。
  ⇒ 切读 PGVector 不会把这一格丢掉，这一条值得单独记，因为 AGENTS.md 那条「新代码不得新增 Chroma 依赖」正在推进。
- 三格本体：`:586 activity_priors()`（读计数，缺库即空 dict）、`:665 activity_prior_value()`、`:730 rank_hits_by_activity()`；
  写侧 `app/api/v1/feedback.py:48-49 _UPSERT_SQL`、`:157` 执行、`:182 submit_document_feedback`；
  表 `migrations/0011_document_activity_signals.sql:24` 起 —— 列只有 filename ＋ 两枚计数 ＋ 两枚时间戳，`:38`/`:40`/`:43`/`:47` 四条 CHECK
  含「计数非负」「两枚计数之和 >0」「filename 去空且 ≤512」，**没有任何文本列** ⇒ 判据③ 结构成立，不靠自觉。
- 判据② 有硬牙：`rank_hits_by_activity:748-753` 三条返回路径交回的是**同一个列表对象**（开关关着、输入不是列表、为空、没有任何一条命中带先验），
  不是「内容恰好相同的另一份拷贝」⇒「无信号 ⇒ 与现状逐字一致」可证，不依赖浮点比较。位移界在 `:701-727`（相邻交换，每轮至多一名，与腿宽无关）。
- 🔴 差格三条：
  a) **「点击」半张真欠（零实现）**：`app/api/v1/feedback.py:21` 注释明写那一路要前端埋点、等总控另派。我在 `app/`、`migrations/`、`frontend/src`
     三层按 `click`/`clicked`/`点击` 现查：0011 表里没有第三枚计数列，端点里没有那一路，前端没有埋点，**也没有找到认领它的具号单**。
     欠的是：新列（要 migration）＋ 新端点或同端点新枚举 ＋ 前端埋点 ＋ 先验源，不是一行能补完的格子。
  b) **强度只证到离线形状**：真库真并发打点、真库次序未证明 —— R224（计划书结案单 LF350）当年记这格「未证」，本单也没量到（不连库）。
  c) **身份维度**：计数按 filename 聚合、不存是谁打的点 ⇒ 「谁点得多」买不到「谁更相关」的分，但按人限额／冷却属业主闸门（计划书 L339 已明写不在执行层单里）。

写域（`git show --numstat eaa9af8` 现取，九枚）：`app/api/v1/feedback.py` +249、`app/main.py` +2/−1、`app/rag/retriever.py` +279/−9、
`migrations/0011_document_activity_signals.sql` +52、`migrations/manifest.json` +2/−1、四枚**既有**测试件改口（`test_document_catalog_sync.py`、
`test_r120_clean_install_first_boot.py`、`test_r134_chroma_writeback.py`）＋ 新件 `test_r46_activity_signals.py` +1018；R195 另带前端 `feedback.js`/`SourceCard.vue`。
三枚热文件冲突：全部 ✘（不碰 `nodes.py`/`orchestrator.py`/`App.vue`）；但它碰 `frontend/**`，与在途 R519 同域。
前置：R45（pre-filtering）与 R36 —— 按 R224 与计划书 L338 记在树（R45 并树 `0276f78`），本单不替它们宣布逐判据结案。

可失败判据草稿：

1. 夹具里给某篇塞「有信号」，跑同一问两遍 ⇒ 名次必须真变（断言名次与 `places_moved`，不是断言「读到了计数」）；位移 ≤ 界，且 5/12/40 三种腿宽各测一次。
2. 无信号：同一对象同一份输入，开／关两态分值快照逐字相等，且必须断言函数交回的是**同一个对象**（`is` 比较，不是 `==`）。
3. 隐私反证：往反馈端点塞 10 万字自由文本 ⇒ 422 且表里零行；再对 0011 的列清单一枚枚点名「不得有文本列」，混进 TEXT 即红。
4. 切读不倒退：把 `INDEX_BACKEND=pgvector` 摆进子进程 env 跑同一份夹具 ⇒ 走 `:1503` 那一支，先验必须仍生效；只在 Chroma 腿上接了＝这一条红。
5. 没跑 0011 的库：跑一问必须 fail-open（原序、NULL 语义、一行日志），不许 500、不许把「读不到计数」冒充成「没有信号所以本该如此」而不留痕。

重估人日：**1.5**（原估）里今天只剩 0.75（点击半张：端点＋埋点＋先验源）＋ 0.75（真库强度校准，要一台安静机器，不是缺码）；按人限额不计（业主裁）。

### R48 首屏结论卡片＋来源，正文后台补（计划书 L198／判据原文 LF519）

判据原文两格：① 首屏 ≤1 s 有可用结论；② 后台补齐失败有明确标注。禁：不得先渲染结论再「纠正」成不同答案。
定案走的是**路线甲 = 新 canonical 事件 `answer.headline`**（跟进单文本行 T2828 记着裁由：只有它给得出带 sequence＋timestamp 的线上读数）。

三态：**部分落地**，凭 `0ad3d3e`。逐格：

- 发卡本体在树：`app/api/v1/chat.py:451 _answer_headline_frame`（事件名以字面量待在 `canonical_sse_event` 那一格里，`:476`），
  载荷 `:430 _headline_card_data`；发射点 `:3103`，触发条件是本轮第一批**看得见**的来源到手（`:3097`，一轮一枚）。
  无可见行／无权限／命中缓存三条支路一枚都不发（宁缺毋造：那两张脸仍归收尾的 `sources` 事件）。
- 判据② **已交**：`frontend/src/components/AnswerHeadlineCard.vue:70` 那枚 `kind: unfilled`（标题 `:72`「首屏卡片未获补齐」），
  钉在 `frontend/src/components/__tests__/r48-headline-card.test.js:109`（断言 `data-kind=unfilled` 真上屏）。
- 判据① 🔴 **未交，且今天不可交**：卡片 `carries_answer` 恒 false、只带来源清单**不带结论**；发卡时刻挂在第一批来源行之后，
  问答档 run6 中位 27.9 s；本机地板「只吐 1 枚 token 也要 11.0 s」（计划书 L376 记 R48S 取证）⇒ 1 s 那一格在 V1 硬件口径上物理不可达，
  而 B 行 09-24 已整行移出 V1（L375）。并树提交自己就把这条写成第三条铁规：「不宣布『首屏 ≤1 s 达成』」。
- 防假绿那一格（判据字面没写、但裁定要求写死）：**已交两枚** ——
  `tests/test_r48_headline_card_lands_on_the_wire.py`、`tests/test_r48_headline_never_enters_the_text_ledger.py`（后者拿 R181 真尺比「摘卡 vs 留卡」，
  并带总控补的两枚净额格 `corrective_replacements`/`uncorrected_breaks`，堵住卡片借受控纠正把真断流豁免成绿）。

写域（`git show --numstat 0ad3d3e` 现取，八枚）：`app/api/v1/chat.py` +107、`docs/api/contract-v1.md` +53/−2、
`frontend/src/components/AnswerHeadlineCard.vue` +173、`frontend/src/components/ChatPanel.vue` +26、`frontend/src/lib/sessions.js` +42、
`frontend/src/components/__tests__/r48-headline-card.test.js` +398、两枚后端测试件 +895。
三枚热文件冲突：`App.vue` ✘（零改动，本单现取 `git grep -c lane frontend/src/App.vue` 亦 0 命中）、`nodes.py` ✘、`orchestrator.py` ✘；
但 `frontend/**` 与在途 R519 同域 ⇒ 本波不许同投。前置：R41（canonical `sources` 事件）—— 已在树（发卡吃的就是那条信封）。

可失败判据草稿：

1. 抽一真问打 `/ask`，取 `answer.headline` 帧时间戳减请求起点，先量出真数再决定判据① 要不要改写 —— 今天量到的量级是几十秒，不许拿「卡片在场」冒充 ≤1 s。
2. 摘掉卡片 ⇒ A② 那把尺的 verdict 一字不动（总控补丁就钉着 `verdict_on == verdict_off`）；若摘卡后 verdict 变了，说明卡片骑上了正文道，红。
3. 卡片载荷闭集：六格里混进任何正文字节 ⇒ 红（`test_b` 那枚钉正文道载荷闭集）。
4. 三条不发卡的路各测一次（无可见行／无权限／命中缓存）⇒ 事件计数必须为 0，不许拿一张假卡去填首屏。
5. 正文最终没到 ⇒ 屏上必须显 unfilled 那张脸（`data-kind=unfilled`），不许静默留一张 pending 卡；后端若把 `carries_answer` 翻成 true，前端只认后端那一格并同步改口。

重估人日：**0**（码已交）；判据① 那一格欠的是业主裁口径＋E2/E3 换引擎，不计在 R48。

## 3. 本波能同投哪几枚（写集相交表）

八枚里 R29/R32/R33 今天不欠码，所以「可投」的不是这八枚本身，而是它们剩下的格子。先把残余列成最小可投单元：

| 代号 | 欠的那一格 | 会写的文件（现取坐标） |
|---|---|---|
| A | R43 判据②：cached 落库 | 新 `migrations/0018_*.sql`、`migrations/manifest.json`、`app/trace/schema.py:86`、`app/trace/projections.py:297-309`、新测试件 |
| B | R31 差格 a/b：审批续跑道＋队列道接 sink | `app/agents/orchestrator.py:1545-1554`、`app/api/v1/chat.py:2446` 与 `_ask_stream` 邻域、`app/agents/nodes.py:564` 那枚 worker 白名单、改 `tests/test_r203_sink_reaches_the_leg.py` |
| C | R46 差格 a：点击／浏览半张 | `app/api/v1/feedback.py:48-49/157/182`、新 `migrations/0019_*.sql`＋`migrations/manifest.json`、`app/rag/retriever.py:586/665`、`frontend/src/lib/feedback.js`、`frontend/src/components/ChatPanel.vue` |
| D | R46 差格 b：真库强度校准 | 只读取证脚本（`scripts/`）＋新测试件；要一台安静机器 |
| E | R38 那一格＋R43 判据②读数 | `scripts/` 一枚取证件；要开窗打模型 |
| F | R29 判据②（若业主改口迁腿） | `app/agents/nodes.py:1134-1181`、`app/common/model_handler.py:537-634`、`app/common/model_budget.py` |
| G | R32 判据① 数值格＝R105 乙半 | `docs/api/contract-v1.md`、`app/api/v1/observability.py` |
| H | R48 判据① 首屏秒数 | 0 行码：欠业主裁口径＋E2/E3 换引擎（不建可投单元） |

两两相交（**同文件即相交**，必须串行）：

- A × C：🔴 相交在 `migrations/manifest.json` ＋「下一枚 00 号」这一枚共享资源（`git ls-files migrations` 现读最新 0017）。同投必须把 0018／0019 两个号**预分配死**，否则两枚都会去改同一行 manifest。
- B × F：相交在 `app/agents/nodes.py`（B 要放开 `ANSWER_LEG_STREAM_WORKERS:564`，F 要换生成腿的传输）。必须串行。
- C × 前端在途：`frontend/**` 与 **be-r519**（R519，队列道屏侧读数，且明令 `sessions.js` 净零行）同域 ⇒ C 排它并树之后，本波不同投。
- B × tests 在途：B 要改 `tests/test_r203_sink_reaches_the_leg.py`；**be-r516** 写域是 `dataset_registry` 一族既有件、**be-r520** 只新增 `tests/test_r520_*.py` ⇒ 现读不相交，但并树前必须逐枚点名两枚在途的 dirty 文件清单再定（别拿功能名称当写集）。
- A × B、A × F、A × G、B × C、B × G、C × G、D × 全部、E × 除 G 外全部：**不相交**。
- D × E × G 抢的是**同一台安静机器的时间窗**，不是文件 ⇒ 按机器串行，不按写集串行。

结论（本波可同投的最大集合）：

- ✅ 可同投三枚：**A ＋ D ＋ G**（A 只碰 trace/migrations，D 只碰 `scripts/` 与自己新件，G 只碰契约与 observability）。
  🔴 但 G 本波只能投**口径半张**：数值只有开窗才取得到，要求填秒数就必然逼人造数 ⇒ 投 G 时判据要写成「只钉口径、不许发布数值」。
- ✅ 也可换成 **A ＋ B**（两枚写集零相交）；一旦 B 落地动了 `nodes.py`，F 就必须排 B 之后。
- ❌ 本波不许同投：C（与 R519 同域）、F（与 B 同文件，且前置在业主手里）、E（打模型＝开窗）。
- 串行序（同文件必须串行，逐条给因）：`F → B`（同 `nodes.py`）；`A → C` 或号先预分配（同 `manifest.json`）；`R519 → C`（同 `frontend/`）；`E → D → G 的数值`（同一台机器一次只干一件）。

## 4. 会被这批新坐标撑歪的在册纸（只列，一枚都不改）

下面每格都是「纸上的行号」与「本纸 §2 现取的行号」已经不等。改口归总控，且改口要连自同步尺一起走（不许手改数字）。

1. 🔴 **`app/trace/spans.py:306-310` 与 `:358-361`**：两处都写着 the missing copy is `app/common/model_handler.py:394-395`。今天 :394-395 是
   `default_model_budget()` 初始化那两行；真正的计数拷贝在 `:611-613`，且 R43a 早已把 cached 那格接上 ⇒ 这两句**不只过期，是与树上代码互相矛盾**
   （同文件 `:349` 那句 `app/agents/nodes.py:370` 与 `:505` 同样错位：:370 今天是空行、:505 今天是 `publish_stream_pieces` 签名的形参行（`def` 在 :504），而那句要指的两发出口
     现读在 `nodes.py:779` 与 `nodes.py:953`（`model_token_counts`，import 在 :777/:951））。
2. `docs/handoff/2026-09-25-plan-ticket-closure.md` LF333-352 那八行的锚点列（R31 写 `nodes.py:302-321,397,598-628,1000-1047`／`orchestrator.py:1199,1235`；
   R32 写 `chat.py:1232,1246-1256,1333`；R33 写 `orchestrator.py:342-350`；R43 写 `model_handler.py:154,168-173,519,537`；R46 写 `retriever.py:676,722-770`；
   R48 写 `chat.py:332-405,2161,2448-2456`）—— 本纸逐枚另给一套，两套同行号不同义。同一文件 LF350 那句 `feedback.py:181-211` 现读应为 `:182` 起。
3. `docs/handoff/2026-09-15-backend-followup-requests.md` **§21 表本体**：LF499（R27 指 `orchestrator.py:201`）、LF502（R30 指 `contracts.py:72` ＋ 三处 `timeout=30`）、
   LF503（R31 指 `nodes.py:174`/`:193`、`orchestrator.py:709`、`stream_mode` 在 `:491`）、LF505（R33 指 `orchestrator.py:158`）、LF517（R46 指 `contracts.py:157 score_type`）。
   现取：`orchestrator.py:201` 是 `_fail_checkpointer_loudly`、`nodes.py:174` 是关键词判定、`orchestrator.py:709` 是空行、graph 级快照在 `:931`、
   `contracts.py:157` 是 `max_tokens`、`score_type` 在 `contracts.py:405`、`ModelTier.COMPRESS` 那条生产裁剪在 `orchestrator.py:416`；
   `timeout=30` 在 `app/` 现取 0 命中（这一格不是撑歪，是判据要的事已经做完而纸面还挂着）。
4. 同一文件文本行 T2013 与 T2824（R38 缺陷锚写 `model_handler.py:360`；R203 那段死道指 `chat.py:2041` 与 `:1921-1924`）：今天 :2041 是
   `request_id=request_id`、:1921 是一枚形参行；那枚死道已由 `8f429b7` 治掉 —— 纸还活着，指的对象已换。
5. `docs/handoff/2026-09-15-orchestration-board.md:950-951`、`:2252`、`:3537`、`:3918`：同一族旧坐标（`nodes.py:174/:193/:304/:370`、`orchestrator.py:201`、
   `contracts.py:72`、`retriever.py:404`、`chat.py` 帧账旧行号）。其中 `retriever.py:404` 现读是**空行**（那句散文今天不在那儿）。
6. `docs/handoff/2026-09-17-perf-architecture-plan.md:47`（HTTP 出口只有 2 处：`nodes.py:174`/`:193`）、`:67`（那串链路末端写 `app/trace/store.py:171`）、
   `:339`（R153 引 `retriever.py:404` 那句散文）、`L486`（引 `app/agents/nodes.py:550-563`：这段今天仍在 `:548-563`，但它内部 `:553` 又引
   `orchestrator.py:856-877`，而 `build_precheck()` 的真调用点现读在 `orchestrator.py:1057`、`extract_standard()` 在 `:1036`）。
7. `docs/handoff/2026-09-19-native-route-audit.md:9-13`（`model_handler.py:41`/`:54`/`:243` 三枚坐标）：端点常量与传输名今天分别在 `:58`/`:71`。
8. `docs/handoff/2026-09-20-unblock-map.md:106`（R38 判据前提过期那句，写的是 `cached_tokens` 在 app 与 migrations 两侧 0 命中）：`app/` 那一侧
   现取已 **23 命中**（`migrations/` 仍 0 命中，那正是 A 单元要补的）⇒ 这行只欠一半改口。
9. **代码内注释**三处：`app/agents/orchestrator.py:299` 与 `:410` 都指 `:201` 说那一发的 prompt 只有 sys_msg ＋ current_user_msg，
   该调用现读在 `:472-473`；`app/agents/nodes.py:559` 写 `run_interrupt_stream`（`orchestrator.py:1341-1350`）不收 sink，
   现读 1341-1350 是 `run_with_stream` 的形参区（`stream_piece_sink` 恰好在 `:1346`），`run_interrupt_stream` 的签名今天在 `:1545-1554`。
10. 门里的自同步件（谁动坐标谁只能走它们给的出路）：`scripts/r460_run9_coordinates.py` ＋ `tests/test_r460_*.py`、
    `tests/test_r483_empty_table_triage_is_derived.py`、`tests/test_r302_docs_utf8_guard.py`。🔴 关于最后一枚：它按 `docs/handoff/*.md` 逐文件**等值**记账，
    本纸是干净新文件（严格 UTF-8、零 NUL、零 U+FFFD、零奇异控制字符），按它 `:99-105` 那枚「不许漏文件」的钉**不需要**进它的账本；
    一旦谁往本纸里写坏编码，那枚钉会先把本纸点名列进红。`tests/test_r276_vector_wording_pin.py` 的名单不含 `docs/handoff`（现取），本纸不在它射程内。

## 5. 没量到的格子（明列，不许被当成已达标）

- R29 判据②（生成轮 30.6→≤22 s）：没量到 —— 本单禁打模型。
- R38 判据（抽一问两列非零且与自报一致）：没量到 —— 同上。
- R43 判据②（E3 档 `cached_tokens > 0`）：没量到。E2／本机侧读数本单**亲取**：`think_off.jsonl` 9 枚全为非零（见 §6 读数 3），但它不是 E3，也不在台账里。
- R46 判据① 的强度：真库、真并发次序没量到（本单不连库）。
- R31 判据①/② 的**当前**真机分布：量具我跑了（§6 读数 1），但那是 run9 那两窗的账；run10 未开 ⇒ 纸上的 94/105 不等于今天的线上数。
- R32 判据① 的数值：契约每枚数字格仍写「待真机样本」（`contract-v1.md` LF1555-1556 原话），没量到。
- 门：本单**没跑全量门**。基点 `97724c5` 上「并树后干净树复跑」那一遍的读数我没现取到（只见到 R518 交回里的八件 116 passed 与看板 §4DZ 那串已过期数），
  所以本纸不引用任何全量枚数当尺 —— 拿不到同 HEAD 的复跑数就别报数。
- 与三枚在途 Agent 的写集相交：我只核了**派工词声明的写域**（`.tmpfix/r516_dispatch.txt`、`r519_dispatch.txt`、`r520_dispatch.txt` 三份原文），
  没去它们的工作树取任何证据（会取到脏中间态）。

## 6. 执行层自报：跑过的命令原文与读数

以下每条都在 `C:\Users\fengx\PycharmProjects\be-r521`（基点 `97724c5`）亲自跑；解释器用主树在册 `.venv`，全程只读，未 commit／未 add／未起服务／未动容器／未打模型。

**读数 0｜树与基点**

```
git rev-parse HEAD            -> 97724c53270a5883a87e538f2098cc394d94ed66
git status --porcelain=v1     -> 空（开工前；写本纸后仅多出一枚未跟踪文件）
```

**读数 1｜A② 在册量具现跑（R518 那把尺，纯读三本账；件内自带 sha256 读前＝读后，自证未改动）**

```
& ..\企业智脑\.venv\Scripts\python.exe scripts/r518_a2_lane_attribution.py
行数=105（重试折叠 0）｜tool_calls 可判行=105｜尺寸闸=20（app/agents/nodes.py）
读 1（②原文全分母）：绿 94/105，红 11 枚：approval-06,chat-03,chat-06,chat-09,chat-10,data-09,doc-07,metric-02,metric-16,scope-01,scope-02
读 2（甲案分腿）：105 = in_scope_has_leg 93 + not_applicable 9 + no_answer 2 + self_added_cell_only 1 + undecidable 0  守恒=True
          甲案原文两格 93/93；甲案严读 91/93，红=report-02,tool-04
          not_applicable/无逐片腿 8 枚；/短过尺寸闸 1 枚（data-09）；/队列道 0 枚；undecidable 0 枚
          腿名可派生行数：0/105
```

同一命令本单跑了两遍（开工一遍、交回前一遍），两遍读数**逐字相同**，且件内自证的三本输入账 sha256 读前＝读后：
`sidecar-run9-frames.jsonl`=`016e9525121c2c6a…`、`sidecar-run9.jsonl`=`cb972fd93fa915c0…`、`answers-run9.jsonl`=`e879075f40833fb1…`；
量具件本身 `scripts/r518_a2_lane_attribution.py` sha256 前缀 `e21961483787f64d`（34 051 B，源码内零写盘调用，`git status` 现取未改动）。

**读数 2｜八枚 sha 与「号是否只活在别的分支上」**

```
逐枚（791568c eef642b 8a91f4e 9678d21 2e6abc6 4586bb4 0ad3d3e eaa9af8 484536c 509c1c7 4c11efb 8f429b7 3aba146 1cbd164 839c344 6a4f02b 70695df 8636ca4 158259f fe5b180）：
  git cat-file -t <sha>                      -> commit
  git merge-base --is-ancestor <sha> HEAD    -> rc=0
逐枚两口径对账（git log --oneline -E --grep=\b<号>\b 分别跑 HEAD 与 --all）：
  on_HEAD / on_ALL -> R29 23/23、R31 12/12、R32 8/8、R33 8/8、R38 8/8、R43 9/9、R46 13/13、R48 10/10
git show --numstat <并树 sha>                -> §2 每枚「写域」那一段的数字
```

**读数 3｜零命中／命中数（每条都是本单自己跑的，不引用旧纸）**

```
git grep -n timeout=30 -- app                                  -> 0 命中
git grep -n -i cached -- migrations/                           -> 0 命中
git grep -n cached_tokens -- app/trace/store.py                -> 0 命中
git grep -n input_tokens  -- app/trace/store.py                -> 0 命中（写入早已迁到 projections.py:305-306）
git grep -n cached_tokens -- app                               -> 23 命中
git grep -n ModelTier.COMPRESS -- app/                         -> 4 命中（唯一出现在 orchestrator.py 的那一行 :414 是注释）
git grep -n stream_piece_sink -- app/agents/orchestrator.py    -> 注册点一枚（:1400）；全仓唯一注入方 app/api/v1/chat.py:2735
git grep -n _apply_activity_prior -- app/rag/                  -> 5 处调用（:1493/:1496/:1503/:1549/:1560）＋ 定义 :1562
git ls-files migrations                                        -> 最新 0017；manifest.json 尾三行含 0015/0016/0017 逐文件 sha256
docs/perf/raw/think_off.jsonl 全行取数                          -> cached_tokens 读数 9 枚、非零 9 枚，值全为 257；对位 prompt_tokens 落在 506-510
跟进单行制普查                                                 -> bytes 996 481 / chars 584 306 / CR 6 124 / LF 4 660 / lone CR 1 534 / lone LF 70；ReadAllLines 6 195 行 vs 按 LF 切 4 661 段
```

**读数 4｜引用面复核（本纸每一枚「文件:行号」都在 `97724c5` 这棵树上逐枚现读）**

```
起因（本单一手踩到的取证陷阱，如实记）：本会话早前若干次 `[System.IO.File]::ReadAllText(相对路径)`／`ReadAllLines(相对路径)`
  实际落在**主树**而不是 be-r521 —— PowerShell 的 `Set-Location` 不移动 .NET 进程的 CWD（`git grep`／`Select-String -Path`／`Get-Content`
  都正确命中本树）。⇒ 凡涉及 .NET 读取的引用一律改绝对路径重取，并对那 4 枚文件做了一次下面的两树对拍。
4 枚文件与主树字节对拍（每枚各算一次原样 SHA256、一次去掉 0x0D 之后的 SHA256）：
  app/trace/schema.py                         bytes 5898/5708   CR 190/0    noCR_same=True
  migrations/0002_execution_data_lineage.sql  bytes 8885/8624   CR 261/0    noCR_same=True
  tests/test_r167_answer_prefix_reuse.py      bytes 35320/34606 CR 714/0    noCR_same=True
  tests/test_r32_lane_contract.py             bytes 36016/36001 CR 696/681  noCR_same=True
  ⇒ 差异**只是行尾**（本树 CRLF／主树那份 LF），LF 枚数两侧恒等 ⇒ 本纸的行号在两树同义。
正则扫本纸的引用面（`*.py`|`*.sql`|`*.md`|`*.vue`|`*.js`|`*.json`|`*.toml` 紧随其后的行号与行区间）：带行号或行区间的引用 token **102 枚**，
  区间展开并去重得 **740 枚 `文件:行`**，逐枚按绝对路径读该行 —— MISSING_FILE=0、OUT_OF_RANGE=0。带路径者全部命中；
  裸文件名（`nodes.py:` 这一类）只出现在 §4「纸上的旧坐标」语境与本节那张简写清单里，
  §2 的 live 断言另逐枚补了一次全路径复核（nodes.py:327/332/480-487/504-526/553/782/811/816/1053/1117、
  orchestrator.py:201/410/463-469/472-473/709/931/1057/1346/1400/1545-1554、chat.py:1383/2041/2446/2689/2735、
  model_handler.py:58/71/87/90/360/394-395/611-613/621/631、spans.py:306-310/349/358-361/391-393、
  app/agents/contracts.py:157/405、feedback.py:181-182、retriever.py:404/586/1493-1562、ChatPanel.vue:317-319/337-341）。
  本节对文件用简写，映射是唯一的：`nodes.py`/`orchestrator.py`/`contracts.py`＝`app/agents/`，`chat.py`/`feedback.py`＝`app/api/v1/`，
  `model_handler.py`＝`app/common/`，`spans.py`/`schema.py`/`projections.py`/`store.py`＝`app/trace/`，`retriever.py`＝`app/rag/`，
  `ChatPanel.vue`＝`frontend/src/components/`。上面逐枚复核按的就是这套全路径。
docs/perf/raw/think_off.jsonl 取数方法（一处易踩的坑，如实记）：11 行非空，2 行是 `# probe_start`/`# probe_end` 注释，
  另 9 行以字面量 `JSONL ` 开头 ⇒ 直接 JSON.parse 会 11 枚全失败，从而假称「cached_tokens 0 枚读数」；
  本纸按正则从原文取，得 cached_tokens **9 枚**（值全 257、非零 9）＋对位 prompt_tokens 9 枚（506/508/509/510）。
跟进单行制普查复跑（绝对路径，be-r521）-> bytes 996481 / chars 584306 / CR 6124（含 CRLF 4590）/ lone CR 1534 /
  LF 4660 / lone LF 70；按 .NET 分隔符切 6195 段 vs 按 LF 切 4661 段 ⇒ §2 一律点名用的是 LF 口径。
```

**自验**（写完后现取，读数交在交付说明里）：本文件纯 CRLF、无 BOM —— CR 数与 LF 数必须恒等，首字节必须不是 EF BB BF；
且不含 U+FFFD、NUL、以及制表／换行／回车之外的控制字符（对 `tests/test_r302_docs_utf8_guard.py` 那三格体检负责）。

## 7. 交回清单（三态逐枚点名）

- R29：**已并树**（凭 `791568c`，结案口径＝判负）。残余 0 行码；判据② 那一格欠业主动作。
- R31：**部分落地**（凭 `eef642b`＋`3aba146`＋`8f429b7`＋`fe5b180`＋尺 `97724c5`）。差三格：审批续跑道无 sink、队列道无 sink、腿名 0/105 派生不出。
- R32：**已并树**（凭 `8a91f4e`＋`1cbd164`）。差 0 行码；契约数值格属 R105 乙半。
- R33：**已并树**（凭 `9678d21`）。差 0。
- R38：**部分落地**（凭 `2e6abc6`）。差一格：真机抽查读数（欠 0 行码）。
- R43：**部分落地**（凭 `4586bb4`＋`839c344`）。差两格：cached 落库（真欠，四处文件：新 migration ＋ `migrations/manifest.json` ＋ `app/trace/schema.py` ＋ `app/trace/projections.py`）、E3 档读数。
- R46：**部分落地**（凭 `eaa9af8`＋`4c11efb`＋`484536c`）。差三格：「点击」半张（真欠，零实现且无具号认领单）、真库强度、按人限额（业主裁）。
- R48：**部分落地**（凭 `0ad3d3e`）。差一格：判据① 首屏 ≤1 s（欠 0 行码，欠业主裁口径＋换引擎）。
- 本波可同投：**A ＋ D ＋ G**（或 A ＋ B）；C／F／E 本波不许同投。写集相交表见 §3。

