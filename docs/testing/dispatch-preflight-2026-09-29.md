# 派工词落笔前的机器校尺（`scripts/dispatch_preflight.py`）

> 立单：R491（09-29）。一天四犯同一族病 —— 事故 #82（产物在盘上悬一夜）、#85（派工词引用
> `%TEMP%\evalrun\r428-driver.md`）、#90（引用账面缩写件名）、#91（写了一条不存在的 venv 路径）。
> 每犯一次烧掉一枚 Agent 一轮加一席读账时间。本件把「先机器校一遍」变成能失败的牙。

## 1. 它校什么（三档）

| 档 | 输入 | 读数 | 判死 |
| --- | --- | --- | --- |
| A 件名 | 文本里带目录前缀的 repo-relative 引用（`app/` `docs/` `scripts/` `tests/` `frontend/` `deploy/` `migrations/` `static/` `data/` `documents/`） | `OK` / `MISSING`（盘上无库里无）/ `UNTRACKED_BUT_ON_DISK`（盘上有库里没）/ `TRACKED_BUT_OFF_DISK`（库里在册这棵树没 checkout）/ **`IGNORED_IN_REPO`（盘上有 · 库里没 · 被 ignore，R498 加的第四档，附 `git check-ignore -v` 的出处）** / `DIR_OK` / `DIR_MISSING` | 红四枚：MISSING / UNTRACKED_BUT_ON_DISK / TRACKED_BUT_OFF_DISK / DIR_MISSING；第四档**只报不判红** |
| A 库外 | 盘符路径、`%VAR%\…`、反斜杠路径、POSIX 绝对路径 | `NOT_IN_REPO` + `EXISTS`/`ABSENT`；落在本树内的绝对路径先归一成相对件再走 A 档 | 默认只报不判死（`--strict-external` 才把 ABSENT 判红） |
| B 行号 | `件名:NNN`、`:NNN-NNN`、`：NNN`、`#LNNN-LNNN` | `IN_RANGE` / `OUT_OF_RANGE` / `UNVERIFIABLE`（件本身读不到，见 A 档）；行数**现读磁盘**，混换行件附注 `MIXED_EOL（LF 口径 N）` | `OUT_OF_RANGE` 红 |
| C 号账 | 文本里每枚 `R\d{2,3}`（可带一枚小写字母后缀） | `HAS_COMMIT`（首行是本号落地形状 + 实改非空且在册 + 与账面写域有交集 + 在本树 HEAD 祖先链上）/ `LANDING_OFF_TRUNK`（声称并树却躺在别的 ref 上）/ `LANDING_CONFLICT`（首行与实改对不上）/ `SUBNUMBER_LANDED`（父号零并树、货在 R26a 一类子号名下）/ `MENTION_ONLY`（只被正文提到）/ `PAPER_ONLY`（只有 `docs/**` 账面）/ `NEVER_FILED`（两路皆零） | `NEVER_FILED` 一枚红，其余六档只报 |

证据取法：提交一路走 `git log --all -F --grep=<号> --format=<SOH/STX/ETX> --name-only`（子串命中，所以每条还要过号边界复核，防 `R26` 一口吃掉 `R260–R269`；merge 的 `--name-only` 天生为空，补一次 `--first-parent`），账面一路走 `docs/**` 扫号（件集 = `git ls-files -c -o --exclude-standard docs`，同 `rg -l <号> docs` 口径）。R498 之前 C 档只有 `HAS_COMMIT`/`PAPER_ONLY`/`NEVER_FILED` 三档，「号在任何分支的提交里出现过」就等于「已并树」——这正是「20 枚零提交」那笔误判的反向病，现在按上面那四枚腿重判。

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
读 `OK`、零 `MISSING`；**被 ignore 的运行期产物**读 `IGNORED_IN_REPO` 且 rc=0（R498 的第四档，见第 6
节），且必须附凭据：`tests/__pycache__/_chroma_sandbox.cpython-311.pyc` → `.gitignore:2:__pycache__/`、
`C:\…\企业智脑\.venv\Scripts\python.exe` → `.gitignore:1:.venv/`、一枚新图 `static/charts/x.png` →
`.gitignore:37:static/*`。**已在册的那些图不归第四档管**：`static/charts/0af44dd7fa39.png` 读 `OK`
（在册层先答复，ignore 规则压不过一枚已入库的件）。
号账七档里今天有活实例的六档（本回合现取，基点树 `7126614`）：`R484`/`R471`/`R491`/`R492`/`R478`/`R231`
读 `HAS_COMMIT`，`R498` 读 `MENTION_ONLY`，`R493`–`R497` 读 `LANDING_OFF_TRUNK`（别的 ref 已落、本树
祖先链读不到；同一批号在主树 `8857a8d` 上读 `HAS_COMMIT`——两棵树的读数本来就该不同），
`R479`/`R93` 读 `LANDING_CONFLICT`，`R26` 读 `SUBNUMBER_LANDED`，两路皆零的探针号读 `NEVER_FILED`。
下一枚测试当场红 —— 账面窗口吃了 docs，探针就自己翻成了 `PAPER_ONLY`（这笔账记在本单第 12 格）。
牙在 `tests/test_r491_dispatch_preflight_names_the_fakes.py`、
`tests/test_r491_line_bounds_are_read_live.py`、`tests/test_r491_ticket_ledger_keeps_three_tiers.py`、
`tests/test_r491_ruler_reads_only_git.py`；三把反证刀在 `tests/test_r491_counter_evidence_blades.py`。

## 4. 纪律

只读：子进程白名单只有 `git log`、`git ls-files`、`git check-ignore`（三枚都是查询；`check-ignore`
是 R498 为第四档新加的，加档那道闸一格没松）。写动词在 `Ruler.git()` 当场拒，非 sha 形状的 rev
也出不了这道闸；闸的有效性由两枚钉互为对照（见第 6 节纪律第 1 条）。
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
8. **号账只核到「这棵树读不读得到货」**：R498 之后 `HAS_COMMIT` 要同时过四枚腿——首行**位置**是本号
   的落地形状、相对第一父实改非空、实改今天仍在 `git ls-files` 在册、与正文点名的写域有交集；另有「在本树
   HEAD 祖先链上」这道**树的边界**（不在 ⇒ `LANDING_OFF_TRUNK`，不在四枚腿里、它换档不判死）。它**不**判断
   「这笔并树的内容对不对本单的判据」，也不核生产环境（翻没翻 `INDEX_BACKEND` 归 `docs/handoff/` 那本
   计划书），更不核两棵树之间的差异——同一枚号在 A 树读 `HAS_COMMIT`、在 B 树完全可能读
   `LANDING_OFF_TRUNK`（回执头一行写着树与 HEAD，落笔前先扫一眼）。
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


## 6. R498 加的两格：第四档与「提及≠并树」

R491 交回时如实报了一格：`check()` 对「库内被 ignore、盘上真在」的产物没有单独归类，被折进
`UNTRACKED_BUT_ON_DISK` 判红。本仓每一枚派工词都必须写明「用主树解释器 `...\.venv\Scripts\python.exe`」
（派工树没有 `.venv`＝事故 #93 的正解），于是 `.venv/**`、`__pycache__/**`、`static/**` 天天被这把尺
喊成 #82 那一族假账。R498 加第四档 `IGNORED_IN_REPO`（凭 `git check-ignore -v` 的出处，只报不判红），
同时把号账 C 档从三档扩到七档，专治「提交信息里提到这个号」被当成「这个号的货并了树」——上一任「20 枚零提交」是同一个病的反面。设计与可失败论证、判据读数、刀表在
`docs/testing/r498-preflight-fourth-tier-and-landing-shape-2026-09-29.md`。

两件纪律上的事一并入册：

1. **加档不许把只读闸变松**：`git check-ignore` 进白名单的同时，
   `tests/test_r491_ruler_reads_only_git.py` 逐枚咬 27 枚写动词（commit/checkout/restore/add/clean/
   reset/gc/apply/worktree……名单里还备着 `stash`、`filter-branch`、`cherry-pick`、`clone`、`fetch`）
   与 `--` 长写法，任一枚递到子进程那道闸就红，且当场一枚子进程都不许起；
   `tests/test_r498_whitelist_gate_keeps_its_teeth.py` 再拿 9 枚核心写动词做**成双对照**：真件拒且
   零子进程，内存里放宽白名单的同一枚动词则放行 ⇒ 那 27 枚「拒」自带反证，不是一枚空转的探针。
2. **探针号只许活在测试件里**：R491 那把并树提交的正文写了「R475 PAPER_ONLY／R900 NEVER_FILED」，
   把 `R900` 自己烧成 `MENTION_ONLY`——写进账面就等于给它立了案。R498 之后 NEVER_FILED 的探针从池里
   **现选**（两路皆零才用），并留一枚 tripwire 指名是谁把哪枚号抄走的。