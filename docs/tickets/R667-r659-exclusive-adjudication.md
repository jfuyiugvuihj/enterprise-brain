# R667 · 待派池工单（由 R679 从账面派生·判据原文逐字·非总控亲签）

**号**：R667
**基点**：9efff02
**状态**：不由本文携带——跑 `python scripts/tickets_index.py --verify` 现取
**写域**：
- `tests/test_r667_*.py`
- `docs/testing/r667-<开工日>.md`
- `docs/tickets/R667-r659-exclusive-adjudication.md`
- `scripts/tickets_index.py`

派工时由总控按写集复核上面四格；本行以下不再是机器字段。

## 判据原文（逐字·一个字不许改）

```verbatim source="PAREN::docs/handoff/2026-09-15-backend-followup-requests.md::**R667**"
R659 item②③ 与那七枚在册钉的互斥裁定，形状照 R664
```

出处谓词＝`PAREN::docs/handoff/2026-09-15-backend-followup-requests.md::**R667**`。尺会按这枚谓词重读源文件逐字符比对，改一个字就点名「哪一号第几块自第几个字符起不合」。

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
3. 凭据纸 `docs/testing/r667-<开工日>.md`：判据实际读数（枚数／字节数／退出码），不许形容词。
4. 反证牙：改掉盘上副本里的一处判据原文 ⇒ 校验非零退出并点名哪一号哪一条被改了字。
5. 坐标一律 `文件::符号`，禁止 `文件:数字` 形态的行号。
6. 收席那一刻现取：`rev-list --count 9efff02..HEAD`、staged 清单、未跟踪逐枚点名、`diff --numstat HEAD`。

## 这一枚为什么存在

待派池的散文账只有一行「R667（…）」，开工的人得重读整本跟进单或看板才能拿到判据原文。
本文件把那一段逐字搬进 `docs/tickets/`，从此逐号状态的唯一真源是工单目录，
每班开工只读 `docs/tickets/index.tsv` 与本文件。
