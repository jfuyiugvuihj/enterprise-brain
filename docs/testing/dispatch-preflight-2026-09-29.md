# 派工词落笔前的机器校尺（`scripts/dispatch_preflight.py`）

> 立单：R491（09-29）。一天四犯同一族病 —— 事故 #82（产物在盘上悬一夜）、#85（派工词引用
> `%TEMP%\evalrun\r428-driver.md`）、#90（引用账面缩写件名）、#91（写了一条不存在的 venv 路径）。
> 每犯一次烧掉一枚 Agent 一轮加一席读账时间。本件把「先机器校一遍」变成能失败的牙。

## 1. 它校什么（三档）

| 档 | 输入 | 读数 | 判死 |
| --- | --- | --- | --- |
| A 件名 | 文本里带目录前缀的 repo-relative 引用（`app/` `docs/` `scripts/` `tests/` `frontend/` `deploy/` `migrations/` `static/` `data/` `documents/`） | `OK` / `MISSING` / `UNTRACKED_BUT_ON_DISK`（盘上有库里没）/ `TRACKED_BUT_OFF_DISK`（库里在册这棵树没 checkout）/ `DIR_OK` / `DIR_MISSING` | 后四枚红 |
| A 库外 | 盘符路径、`%VAR%\…`、反斜杠路径、POSIX 绝对路径 | `NOT_IN_REPO` + `EXISTS`/`ABSENT`；落在本树内的绝对路径先归一成相对件再走 A 档 | 默认只报不判死（`--strict-external` 才把 ABSENT 判红） |
| B 行号 | `件名:NNN`、`:NNN-NNN`、`：NNN`、`#LNNN-LNNN` | `IN_RANGE` / `OUT_OF_RANGE` / `UNVERIFIABLE`（件本身读不到，见 A 档）；行数**现读磁盘**，混换行件附注 `MIXED_EOL（LF 口径 N）` | `OUT_OF_RANGE` 红 |
| C 号账 | 文本里每枚 `R\d{2,3}`（可带一枚小写字母后缀） | `HAS_COMMIT` / `PAPER_ONLY`（零提交、只有 `docs/**` 提及）/ `NEVER_FILED`（两路皆零） | `NEVER_FILED` 红 |

两路证据的取法：`git log --all -F --grep=<号>`（拿到之后还要按号边界复核，防 `R47` 蒙中 `R478`）
与 `docs/**` 全量扫号（件集 = `git ls-files -c -o --exclude-standard docs`，同 `rg -l <号> docs` 口径）。

## 2. 用法与退出码

```powershell
# cwd 用自己要校的那棵工作树；解释器可以是主树的
python scripts/dispatch_preflight.py path\to\dispatch.md
python scripts/dispatch_preflight.py - < dispatch.txt
python scripts/dispatch_preflight.py --text "新钉 tests/test_r387_teeth.py，锚点 app/api/v1/chat.py:999999"
python scripts/dispatch_preflight.py dispatch.md --json        # 机器可读的账
python scripts/dispatch_preflight.py dispatch.md --repo C:\path\to\other-tree
```

`0` 全绿 / `1` 咬到红牙（回执末行 `RESULT=FAIL 红 N 枚`）/ `2` 环境或输入错（读不到 git、空输入 —— 这不是账错，不许混进红）。
回执逐枚给「档 + 引用 + 落在派工词第几行 + 重复枚数」，同一棵树连跑两次逐字节相同。

## 3. 四笔真实历史假账的读数（判据①）

```
!! MISSING                tests/test_r387_teeth.py            · 盘上无 · 库里无      #90
!! MISSING                tests/test_r400_derived.py          · 盘上无 · 库里无      #90
 ~ NOT_IN_REPO            be-r484\.venv\Scripts\python.exe    · 库外路径 ABSENT      #91
 ~ NOT_IN_REPO            %TEMP%\evalrun\r428-driver.md       · 库外路径 ABSENT      #85
!! OUT_OF_RANGE           app/api/v1/chat.py:999999           · 现读行数 5138        #82 同族
   IN_RANGE               app/api/v1/chat.py:1005             · 现读行数 5138        反向必须绿
```
真名 `tests/test_r387_label_ruler_teeth.py`、`tests/test_r400_derived_ledger_shift_and_silence_pins.py`
读 `OK`、零 `MISSING`；号账三档各有活实例：已并树的号读 `HAS_COMMIT`、#88 那族账面号读 `PAPER_ONLY`、
两路皆零的探针号读 `NEVER_FILED`。探针号**只写在测试件里**：本文初稿把它们抄进 `docs/**`，
下一枚测试当场红 —— 账面窗口吃了 docs，探针就自己翻成了 `PAPER_ONLY`（这笔账记在本单第 12 格）。
牙在 `tests/test_r491_dispatch_preflight_names_the_fakes.py`、
`tests/test_r491_line_bounds_are_read_live.py`、`tests/test_r491_ticket_ledger_keeps_three_tiers.py`、
`tests/test_r491_ruler_reads_only_git.py`；三把反证刀在 `tests/test_r491_counter_evidence_blades.py`。

## 4. 纪律

只读：子进程白名单只有 `git log` 与 `git ls-files`（尺内有一道闸，递别的子命令当场拒），
零网络、零写盘、不起服务、不碰模型、不跑测试。不写任何行数/号数常量 —— 行数一律现读，
`tests/test_r491_line_bounds_are_read_live.py` 里那枚 AST 钉咬「把某枚真实行数抄进尺子」。

## 5. 它量不到的格子（别拿「已通过」当边界说明）

1. **语义**：它只校件名在不在、行号越不越界、号有没有账。一句话把判据写歪、把 `IN_RANGE` 说成
   已达标、把两件的事实张冠李戴 —— 它一概读不懂。判据对不对仍归总控逐格对。
2. **写域冲突**：它不知道两枚 Agent 会不会改同一枚入口/同一测试件。派工时的写集切分不归它判。
3. **章节号**：`docs/**` 里的 `§13`、`§9.3`、`## 21.1` 这类章节锚不在范围内，只认 `件名:行号`。
4. **裸文件名**：没有目录前缀的引用（`catalog.py 623-655`、`pyproject.toml`、`AGENTS.md`）一律不校 ——
   宁可漏，也不拿一句散文误伤。带前缀才算账。
5. **被字隔开的行号**：`记录 :44/:69` 这种件名与行号之间有字的写法不认；同一枚件名后第二枚裸
   `:NNN`（如 `x.py:44/:69`）只取头一枚。
6. **占位符与通配**：`app/**` 按目录认（目录在位即绿）；`tests/test_r491_<自定>.py` 会被截成
   `tests/test_r491_` 并读 `MISSING`（附注会点名「尾部像占位符/通配」）—— 落笔前该把占位符换成真名，
   这把尺子不替人猜名字。
7. **库外路径只报不判死**（默认档）：`--strict-external` 才把 `ABSENT` 判红。它也无法证明一枚库外
   解释器「装了能用的依赖」—— #91 那条 venv 路径写得再真，它顶多喊 `ABSENT`。
8. **号账不证明已并树**：一枚号只要在**任何分支**的提交里出现过就记 `HAS_COMMIT`，它不查那笔是否在
   HEAD 祖先链上（那是 `scripts/audit_plan_ticket_ledger.py` 的活），也不看 `docs/**` 之外的自述。
9. **校的是当前这棵树**：件名在 A 树绿、在 B 树可能红。`--repo` 与执行 Agent 实际所在的树不是同一枚，
   就会出现假绿或假红；回执头一行把树与 HEAD 都写着，落笔前先扫一眼。
10. **行号口径偏宽**：混换行件按「CRLF/LF/CR 全展开」这个最大口径数，宁可不喊也不冤喊；要对齐某位
    编辑器里看到的那一行，仍得人眼。
11. **别的引用形态**：短 sha（`a0ec662`）、URL、容器名、模型名、环境变量值 —— 都不在它眼里。
12. **账面样本是活的**：`R475/R476/R486` 是 #88 那族账面号，两路皆零的探针号写在
    `tests/test_r491_ticket_ledger_keeps_three_tiers.py` 里。哪天真给它们立了单、或有人在 `docs/**` 里
    提起那枚探针号，这枚钉会红着要求换号 —— 那是维护动作，不是回归。
13. **本单的钉一律要求「在合并树上同样成立」**：全量门只在主树跑，派工树绿不算货。环境事实只许用
    与仓库位置无关的形状去取（`sys.base_prefix` 里那枚解释器、pytest 的 `tmp_path`），禁拿仓库位置往上
    拼兄弟树名 —— 本单第一次交回就死在这一格（总控退回令 14:2x：那枚探针在主树变成了库内件）。
    牙在 `tests/test_r491_dispatch_preflight_names_the_fakes.py` 末尾那枚静态闸上。
