# R676 · 待派池工单（由 R679 从账面派生·判据原文逐字·非总控亲签）

**号**：R676
**基点**：9efff02
**状态**：不由本文携带——跑 `python scripts/tickets_index.py --verify` 现取
**写域**：
- `tests/test_r676_*.py`
- `docs/testing/r676-<开工日>.md`
- `docs/tickets/R676-synonym-rewrite-no-roundtrip.md`
- `scripts/tickets_index.py`

派工时由总控按写集复核上面四格；本行以下不再是机器字段。

## 判据原文（逐字·一个字不许改）

```verbatim source="S21CELL::docs/handoff/2026-09-15-backend-followup-requests.md::R47::判据（机器可验）"
① 同义词题命中改进；② 改写仍走规则不新增模型往返
```

出处谓词＝`S21CELL::docs/handoff/2026-09-15-backend-followup-requests.md::R47::判据（机器可验）`。尺会按这枚谓词重读源文件逐字符比对，改一个字就点名「哪一号第几块自第几个字符起不合」。

## 账面点名的落点（派生自上面判据原文里的反引号路径）

（本枚判据原文里没有点名的文件路径——落点由总控派工时给。）

## 禁区（踩线即退回）

- `docs/handoff/**`：跟进单与看板只读，一个字节都不许改（在册工具按行读它们）。
- `app/**`／`frontend/**`：本枚判据没点名就不许碰；`chat.py` 那格的写域归 R670，其余单号一律避开。
- `pyproject.toml`／`scripts/run_gate.py`／`deploy/.env.server`／`chroma_db/**`／评测夹具。
- 主树任何路径；commit／建分支／push／起服务／动容器／rebuild 镜像／打真模型／跑全量门。

## 交付清单

1. 判据原文逐字进单：`python scripts/tickets_index.py --verify` 必须绿，退出码 0。
2. 同名件两态读数：state① 本树已 apply 未 commit／state② `git archive 9efff02` 干净检出＋只投本单货；清单逐枚相同、总数相同，标「执行层自报」。
3. 凭据纸 `docs/testing/r676-<开工日>.md`：判据实际读数（枚数／字节数／退出码），不许形容词。
4. 反证牙：改掉盘上副本里的一处判据原文 ⇒ 校验非零退出并点名哪一号哪一条被改了字。
5. 坐标一律 `文件::符号`，禁止 `文件:数字` 形态的行号。
6. 收席那一刻现取：`rev-list --count 9efff02..HEAD`、staged 清单、未跟踪逐枚点名、`diff --numstat HEAD`。

## 这一枚为什么存在

待派池的散文账只有一行「R676（…）」，开工的人得重读整本跟进单或看板才能拿到判据原文。
本文件把那一段逐字搬进 `docs/tickets/`，从此逐号状态的唯一真源是工单目录，
每班开工只读 `docs/tickets/index.tsv` 与本文件。

---

## 总控派工段（10-06 13:1x·基点 `c82208c`·业主已裁**乙案**）

- **裁定原文口径**：R47① 走**乙**＝**不动 105 题评测集**（`tests/fixtures/business_evaluation_100.jsonl` 一字节不许动，它被 `tests/test_evaluation_report.py` 钉着），改的是**口径**：同义词那一族题按「top-5 变化率」判命中改进，不按 `must_contain` 命中判。
- **基点改口**：头部 `9efff02` 过期，派工基点＝主树现取 `c82208c`。工作树＝`C:\Users\fengx\PycharmProjects\be-r676`（总控已备好，独占）。
- **写域追加两格**（原判据四格之外）：新量具 `scripts/r676_synonym_top5_delta.py` ＋ 它的牙 `tests/test_r676_*.py` ＋ 凭据纸 `docs/testing/r676-2026-10-06.md`。🔴 原判据里那格 `scripts/tickets_index.py` **不要动**（名册派生器由总控管）；也不许写整本 `scripts/`。
- **禁区**：`app/**` 一律不碰（本单是量具与账面单，若你判定必须改产品码才能达，**停下写进交付**由总控裁，不许自己动）；评测夹具；`frontend/**`；`docs/handoff/**`；容器／模型／镜像；主树 commit。
- **判据（可失败）**：① 新量具离线可跑（读仓内既有读数件，不发一次模型调用），对同义词那一族题交出逐题 top-5 变化率表；② 一枚反证：把变化率分子分母对调或摘掉同义词腿 ⇒ 某枚牙当场红；③ 判据②「改写仍走规则不新增模型往返」用一枚离线牙钉住（改写路径调用次数＝0 次模型往返）；④ 凭据纸逐枚点名＋两态数字＋未验清单（真机命中改进那格明写「待窗」）。
- **回报**：patch 路径 + SHA-256 + numstat 逐枚点名 + 两态读数。
