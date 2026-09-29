# R498 · 派工前自检尺：第四档 `IGNORED_IN_REPO` 与「提及≠并树」的落地形状

> 立单：R498（09-29），基点 `7126614`（R491 并树那笔）。只改这把尺子和它自己的钉，
> 产品代码零改动（`git diff --name-only` 里没有一枚 `app/**`）。
> 派工词全文在 `docs/handoff/2026-09-15-backend-followup-requests.md` §136，与本单同源。

## 1. 两格缺陷与治法

| 格 | 病 | 治 | 不许塌的那一头 |
| --- | --- | --- | --- |
| A 件名 | 「库内被 ignore、盘上真在」的运行期产物（`.venv/**`、`__pycache__/**`、`static/**`）被折进 `UNTRACKED_BUT_ON_DISK` 判红 ⇒ 每一枚派工词都必须写明「用主树解释器」（派工树没有 `.venv`＝事故 #93 的正解），天天吃假账噪音 | 新增第四档 `IGNORED_IN_REPO`，凭 `git check-ignore -v` 的出处（如 `.gitignore:1:.venv/`）**只报不判红** | 「盘上无 · 库里无」仍 `MISSING` 红；「盘上有 · 库里没 · 也没被 ignore」仍 `UNTRACKED_BUT_ON_DISK` 红；拿不到 check-ignore 答案（不是一棵 git 树）→ 回 `None` → 照旧红：**降噪必须有凭据** |
| C 号账 | 一枚号只要在任何提交的信息里出现过就记 `HAS_COMMIT`（＝已并树）。本席 16:5x 实测：`R493` 读 `HAS_COMMIT commits=1 首笔 314888b`、`R495` 读 `HAS_COMMIT 首笔 5270c40`、`R496` 读 `HAS_COMMIT 首笔 438d67d`，而这三枚此刻一枚货都没并树——那三枚 sha 分别是看板提交与「并树 R484／并树 R471 丙案」的正文里点了它们的名 | 把「提及」与「并树」分家：`HAS_COMMIT` 要过四枚可失败的腿，另加 `LANDING_OFF_TRUNK`／`LANDING_CONFLICT`／`SUBNUMBER_LANDED`／`MENTION_ONLY` 四档 | 真并树的 `R484`/`R471`/`R491`/`R492`… 仍必须读 `HAS_COMMIT`（首行形状与实改字节互换后判据必须跟着翻，见 §4 的 B1） |

## 2. `HAS_COMMIT` 的四枚腿（为什么「首行含『并树』两个字」不够）

一枚提交要当本号的并树凭据，四枚腿全过：

1. **首行位置**（`subject_shape`）：首行必须**起头**是本号的落地形状，三种形状都认——
   `并树 RNNN[≤24 字限定语]（施工 名字/id，树 be-rNNN@sha）：…`（现仓模板，吃 `438d67d` 的「R471 丙案」）、
   `feat(R26a): …`／`R260b（总控补口…）：…`（拆单之前的施工首行）、`Merge <branch>: RNNN …`（分支并树）。
   号边界 `(?![0-9A-Za-z])` 钉住，`R26` 不吃 `R260`，`R260b` 不并回 `R260`。
   **为什么不够**：形状只证明「有人声称并了树」，正文一句「另立 R495」也含 `R495`，
   而 `5270c40` 的首行形状是 **R484** 的落地，不是 R495 的——所以形状必须**相对这枚号**判，不能相对文本判。
2. **实改非空 + 仍在册**：该提交相对第一父的 `--name-only` 不许为空（merge 天生为空，补一次
   `--first-parent`，`11f9b1f`/`6ee2f79` 就靠这一腿），且实改的文件今天仍能在 `git ls-files` 里查到
   （`-c core.quotePath=false`，否则非 ASCII 件名被转义成 `"data/\346\212\245…"` 必漏）。
   空提交、并完又被撤掉的，都不算把货并了树。
3. **写域交集**：实改清单要与提交信息**自己点名的写域**有交集。点名三种形状都算——
   整条路径或 ≥10 字的段前缀（吃 `scripts/x.py(518 行)` 这种尾巴挂字）、正文里那枚路径是本件的
   前缀（吃 `tests/test_r491_*` 这种 glob／省略写法）、任一祖先目录加 `/**` 或 `/*`（目录级声明，
   吃 `c23e44c` 的 `app/**`）。或者实改里至少一枚**按本单号命名**（本仓产物一律挂号：
   `tests/test_r483_*`／`scripts/r483_*`／`docs/testing/r496-*.md`）。
   正文一枚件名都没点时，这一腿**无法核**——读数里明写「无法核，已点名」，不许静默放行。
   **为什么要它**：腿 1＋2 只能证「有一笔挂着本号的提交真动了在册的货」，动的是不是本单的货要这一腿核；
   零交集时不判死也不放行，另立 `LANDING_CONFLICT` 点名 sha（真历史里 `46ee7ad`·R479、`ebfb1c9`·R93 就是这个形状）。
4. **本树祖先链**：`git log -1 --format=%H HEAD..<sha>` 空＝在这棵树的祖先链上。不在 ⇒ `LANDING_OFF_TRUNK`：
   首行是落地形状、货也不空，但**这棵树读不到它的货**（回执点名 sha）。今天 `R495`/`R496`/`R493`
   在基点树 `7126614` 上就全读这一档，在主树读 `HAS_COMMIT`——两棵树的读数本来就该不同，尺子不替人抹平。

档位序（前档压后档）：`HAS_COMMIT > LANDING_OFF_TRUNK > LANDING_CONFLICT > SUBNUMBER_LANDED >
MENTION_ONLY > PAPER_ONLY > NEVER_FILED`，七档只有最后一枚判红。
`SUBNUMBER_LANDED` 专治 R26 那一族：父号名下零并树、货在 `R26a`/`R26b` 名下 ⇒ 点名子号与 sha，
**绝不自动并号**（账面记 `R26` 结案就必须点分子号）。

## 3. 只读闸随加档一起升级

`ALLOWED_GIT` 从 `("log", "ls-files")` 扩到 `("check-ignore", "log", "ls-files")`，三枚都是查询。
`tests/test_r491_ruler_reads_only_git.py` 同步加钉：白名单逐字点名、27 枚写动词
（commit/checkout/restore/add/clean/reset/gc/apply/worktree/mv/rm/push/fetch/… 与 `--` 长写法）
逐枚在 `Ruler.git()` 那道闸当场拒且**一枚子进程都不许起**；`check-ignore` 只许走 `--stdin`
（argv 里能藏 `--no-index` 那一族岔口）；非 sha 形状的 rev 出不了 `SHA_REV_RE`；
不是一棵 git 树时「盘上有库里没」照旧红，不许靠降噪过关。

闸的有效性另有一枚**成双对照**钉：`tests/test_r498_whitelist_gate_keeps_its_teeth.py`（20 枚）
把 9 枚核心写动词**两头各跑一次**——真件递进去报 `越界子命令` 且一枚子进程都不许起；另一头在
内存里真的把白名单放宽一格（`compile` + `exec` 的影子副本，盘上零写入），同一枚动词就不再抛
且间谍真的收到 argv ⇒ 那 27 枚「拒」若空转，这一头就红。只跑第一头永远不知道它是闸在咬
还是探针在空转；间谍返回一枚带 `returncode`/`stdout` 的桩（不是 `None`），否则放宽件会在
`Ruler.git()` 里撕成 AttributeError，把「放宽后不再抛」这条断言搞反。

## 4. 反证刀（七把，每把只摘一枚牙）

`tests/test_r498_blades_split_mention_from_landing.py`，刀落在内存里的源码影子副本（compile+exec），
盘上那把尺零字节改动；对照 = 真件跑同一套八枚探针，零红。

| 刀 | 摘什么 | 咬红的探针 | 红句原文（节选） |
| --- | --- | --- | --- |
| B1 | `subject_shape` 退回「首行里有这枚号就行」 | `probe_a_prose_mention_is_not_a_landing` | `['HAS_COMMIT', 'HAS_COMMIT']`（应为 `['HAS_COMMIT','MENTION_ONLY']`） |
| B2 | 「实改清单非空」这一腿 | `probe_an_empty_landing_claim_names_the_empty_diff` | `…另 1 枚声称落地被牙拒：实改 0 枚今天一枚都不在 git ls-files 在册` |
| B3 | 「实改仍在册」这一腿 | `probe_landing_whose_products_left_the_ledger_is_refused` | 档位翻成 `HAS_COMMIT`，读数里不再点名在册 |
| B4 | 「写域交集」这一腿 | `probe_write_domain_mismatch_is_a_named_conflict` | `HAS_COMMIT ≠ LANDING_CONFLICT` |
| B5 | 「在本树祖先链上」这一腿 | `probe_landing_off_this_trunk_is_not_landed` | `HAS_COMMIT ≠ LANDING_OFF_TRUNK`，`commits` 由 0 变 1 |
| B6 | 把 `UNTRACKED_BUT_ON_DISK` 整档降成 IGNORED | `probe_a_plain_untracked_product_is_still_dead` | `['IGNORED_IN_REPO'] ≠ ['UNTRACKED_BUT_ON_DISK']` 且 `red=0`（真假账被放宽） |
| B7 | `message_names_token` 退回子串命中 | `probe_a_sibling_number_is_not_attributed_to_its_parent` | 读数里出现 `R260`（应为 `PAPER_ONLY`，mentions=0） |

另有 `tests/test_r491_counter_evidence_blades.py` 那三把老刀（K1/K2/K3）仍各红一枚，
K3 的锚点已随六档版迁移，不再依赖旧的三档 `ticket_status`。

## 5. 实测读数（数字本回合亲自跑）

- **强度只升**：五枚 `tests/test_r491_*` 改前 **67 枚**（现取基线影子树＝`git clone --shared be-r498`、
  HEAD `7126614` 干净工作区：61 passed / **6 failed**——那 6 枚红是 R491 自己的：并树提交正文把
  探针号抄进了账、又把一枚账面号读成已并树，**不是本单引入的回归**）→ 改后同一批件
  **100 枚全绿**；加四枚 `tests/test_r498_*`（17 + 20 + 61 + 11 = 109）共 **209 枚 / 209 passed**。
  函数名册逐族 Counter（HEAD blob 对磁盘字节，跨来源，不是 `git show HEAD:p` 对 `git show :p` 那种
  同源无效对照）：改前 54 → 改后 108，**LOST 全族为 0**；GAINED = `ruler_reads_only_git` +4、
  `ticket_ledger` +3、`r498_ignored` +12、`r498_landing` +26、`r498_blades` +5、`r498_gate` +4。
- **两棵树同数**：`be-r498`（HEAD `7126614`）= **209 passed**；第二棵树＝主树的临时影子副本
  （`git clone --shared` 到 `%TEMP%`，HEAD `8857a8d`，再把我这 10 枚字节铺进去、逐枚 SHA-256 比过等值，
  主树工作区零写入）= **209 passed**。逐件枚数两边相同：6/19/17/38/20 + 11/17/61/20。
  活账在跑动中漂了三次（R495→R496→R493→R497 依次被别的席落到本树祖先链之外），所以钉里**不写死档位**：
  在途那六枚吃的是不变量——读 `HAS_COMMIT` 就必须交得出本树祖先链上的凭据，交不出就必须 `commits=0`；
  加上 `MENTION_SHAS` 那三枚被点名的 sha 在任一棵树里都不许出现在本号的凭据/脱链/被拒堆里。
- **第四档实读**（全部只用 `--repo` 与临时树，**主树工作区零写入**）：本树
  `tests/__pycache__/_chroma_sandbox.cpython-311.pyc` → `IGNORED_IN_REPO（.gitignore:2:__pycache__/`
  ）`，整单 `RESULT=CLEAN 红 0 · 警 1 rc=0`；`--repo` 指主树取
  `C:\…\企业智脑\.venv\Scripts\python.exe` → `IGNORED_IN_REPO（.gitignore:1:.venv/）` 且同单里
  一枚在册件照旧 `OK`；一枚**盘上新图** `static/charts/r498-probe.png`（临时树里造、用完即删）→
  `.gitignore:37:static/*`，而**已在册的** `static/charts/0af44dd7fa39.png` 读 `OK`（在册层先答复）。
  真假账两格一格没宽：`scripts/nope_missing.py`、`tests/test_r387_teeth.py`、
  `tests/test_r400_derived.py` 三枚仍 `MISSING` 红 3 rc=1；一枚「盘上有 · 库里没 · 没被 ignore」
  的 `docs/r498-untracked-probe.md`（同样只在临时树里造）仍 `UNTRACKED_BUT_ON_DISK` 判红。
- **号界实读**：`git log --all -F --grep=R26` 交回 **57** 枚（它是**子串**命中，一把捞回
  整个 R26x 家族），号边界复核只留 **9** 枚提及；尺子把被剔的兄弟号当场点名（本回合现取：
  `R260 R260b R261 R262 R262b R263 R264 R265 R266 R267 R268 R269 R26a R26b`，列表由钉现算、不抄常量）。
  `R26` 读 `SUBNUMBER_LANDED`：`commits=0` ——这不是「查不到痕迹」，货挂在子号名下：
  `R26a` 读 `HAS_COMMIT`（并树 `11f9b1f`、施工 `118801e`）、`R26b` 读 `HAS_COMMIT`
  （并树 `6ee2f79`、施工 `af027ce`）；两者都只点名、**不自动并回父号**。派工词给的凭据是
  `scripts/audit_plan_ticket_ledger.py` 现读 `R26 = PARTIAL`（本单不改那枚审计器）。
- **硬不变量**：`rg -c classification_blocked app/` 现取**零命中**（rc=1）；`git diff --name-only`
  只有尺子与它自己的钉，`app/**` 零枚。
- **字节卫生**（口径＝**磁盘原始字节现取**，不走 `io.open` 文本模式——那会把 `\r\n` 与孤 `\r` 折成
  `\n`、产出一枚假零）：十枚产物全部 CRLF 纯一、**孤 CR=0、纯 LF=0、无 BOM**；CRLF 行数依次为
  尺子 842、三枚改钉 194/204/213、四枚新钉 226/398/298/105、两枚文档本行为 118 与本文自己（自指，
  交回回执里给的那个数才是现值；改一行就变一次，所以把它写死在纸上等于写一句陈年话）。

## 6. 它量不到的格子（别拿「已通过」当边界说明）

1. **裸相对写法仍不在词表**：`.venv/Scripts/python.exe`、`__pycache__/x.pyc` 这种**不带在册目录前缀**
   的写法，A 档根本抽不到（词表只认 `SCOPE_DIRS` 打头）；派工词要吃到第四档，得写成
   `tests/__pycache__/…`、`static/charts/…` 或用绝对路径归一。词表本身归另一单。
2. **写域交集在「正文一件名都没点」时只能标无法核**：`R26a`/`R26b` 那两枚 merge 就是这个形状，
   读数里明写，不给它编一个交集。
3. **落地形状依赖模板纪律**：将来若并树信息既不点件名、产物又不挂号，腿 3 会退化；本单没有把
   「模板」变硬（硬要模板齐备会把 `ed9f8b0`·R231 那类旧变体判红）。
4. **两枚真历史读数是 `LANDING_CONFLICT`**（`46ee7ad`·R479、`ebfb1c9`·R93）：首行是落地形状、
   实改也在册、与正文点名的写域零交集。本单按「人工定性」交给总控，既没判它已并树也没推翻账面。
5. **C 档不读仓外证据**：生产环境是否真在用那笔货、`INDEX_BACKEND` 翻没翻，都不归它。
6. **探针号只许活在测试件里**：`NEVER_FILED` 的探针从池里现选，本文与 `docs/testing/**` 一律
   不抄那些号——抄进账面就等于给它立案（R491 那一班就栽在这一格）。
7. **衄弟树的相对写法会拿本树根去解**：`be-r491\__pycache__\conftest…pyc` 这样的路径确实存在于
   `C:…\be-r491\` 那棵树，但 A 档把它当库外路径、拿 **当前这棵树的根** 拼过去，于是读
   `NOT_IN_REPO · ABSENT`（只报不判红，但这条读数本身不说真话）。派工词要引别的棵树，
   写**绝对路径**并配 `--repo` 指到那棵树（本单取主树 `.venv` 就是这么自证的）。