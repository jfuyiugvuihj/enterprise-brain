# V2 波次四 派工计划（09-26 22:06 · 总控线 · 预配，随波次三结案逐枚投出）

- 本文件的每一条都是总控在 `466d8a1`/`18eebbc` 现取的，不是转述。事实源仍是 `docs/version-roadmap-and-next-week-plan-2026-09-22.md` 的 V2 硬要求。
- 派工一律走波次三那条纪律：一个 block 一枚投递、零 model 覆盖、返回 id 当场写 §0 名册、点名件必须逐枚列出（R332 那笔「自述 313 / 实跑 293+26」的教训）。

> 🔴 **本波作废（R408 复算 · 2026-09-28）：§1 那六枚队列逐枚现取，六枚全部早已并树。**
> 这张纸今天咬过人：09-27 夜里总控差点照着下面那行「无主，槽一空就投」（R341，已并树 `acc092e`）
> 把单再派一次 —— 本仓事故 #14 那一族（同单双人，账面记过九次）差一次就复现。
> 逐枚归因与现取凭据在文末 §4。本文所有 `file:line` 坐标都是 09-26 在 `466d8a1`/`18eebbc` 的读数，
> 多处已漂，引用前现取。
## 1. 队列

| 号 | 一句话症状（现取凭据） | 写域 | 关键判据 | 何时可投 | 今天（R408 现取 2026-09-28） |
|---|---|---|---|---|---|
| **R341** | 「数据趋势」那张卡今天说的是假话：`DashboardPanel.vue:300-305` 明写「服务端还没有回传按期间汇总的时间序列，这一格就空着」——而 R332（并树 `ae7dc96`）已经把 `GET /dashboard/trend` 交出来了 | `frontend/src/components/DashboardPanel.vue` + `frontend/src/lib/dashboard.js` + 新钉 | 数字只能来自 `/trend` 的 series，🔴 不许前端自己按时间重算第二遍；照 R332 裁定①写「新增条目数」，不许暗示金额刻度；`alerts` 键整键缺席（staff）那一行必须有自己那张脸；503 与「这一期真的零」两张脸分开；月/周切换照 period 参数走 | 无主，槽一空就投 | **已并树 `acc092e`**（cat-file -t→commit｜HEAD 祖先）｜症状已兑现：`DashboardPanel.vue` 与 `lib/dashboard.js` 都改口了（后者随后由 R411 再收一笔）。 |
| **R337** | `data.py:294-300` 回 `dataset_id/version_id/classification` 独缺 owner，`:305` 那个 preview 出口同病（R310 的尾巴） | `app/api/v1/data.py` + 新钉 | 与 R310 同一把无主口径（`catalog.py` 的 `None`，不是空串）；不为补字段多开一次查询；逐档行数不变 | 🔴 与 R336 同文件 ⇒ 等 `Heisenberg` 并完 | **已并树 `aefa3ce`**（cat-file -t→commit｜HEAD 祖先）｜症状已兑现：两处出口都答 owner。 |
| **R316** | 管理员零管理屏，而登录页早把员工指向「用户管理」：`frontend/src/components/AdminPanel.vue` 不存在（`Test-Path` 现取 False） | `router/index.js` + 新 `AdminPanel.vue` + 三枚导航钉 | 只读既有出口；不碰 `App.vue`；导航钉三处同源，加一枚屏就三处一起改 | 🔴 与 R315 同抢 `router/index.js` ⇒ 二选一或合一枚（合称估 1.5 人日） | **已并树 `d609165`**（cat-file -t→commit｜HEAD 祖先）｜症状已兑现：`AdminPanel.vue` 今天存在，路由 `/admin` 在树。 |
| **R315** | 成果屏没有自己的位置：`ArtifactList.vue` 早在树里，但只作为 `DataPanel.vue:454` 的子件存在，`router/index.js:53-113` 十条路由里没有它 | `router/index.js` + 新屏壳（薄封装）+ 同三枚钉 | 屏壳**一字不改** `ArtifactList.vue`；只做路由与壳 | 同上 | **已并树 `2cb3401`**（cat-file -t→commit｜HEAD 祖先）｜症状已兑现：路由 `/artifacts` 在树，薄壳 `ArtifactsPanel.vue` 在树。 |
| **R340 候选** | `alerts_open` 是当前状态投影到既往期间（上周的告警今天被确认，会让上周那桶变小），不可回放 | `app/api/v1/dashboard.py` | 按 `acknowledged_at` 算真实历史未处置数；口径变更必须同批改契约 | R332 裁定②，波次五排 | **已并树 `dbb8ba4`**（cat-file -t→commit｜HEAD 祖先）｜候选位今天取消：`alerts_open` 已按 `acknowledged_at` 算真实历史。 |
| **R342 候选** | legacy `created_at=''` 会把 `/trend` 整格打死成 503 | `app/api/v1/dashboard.py` | 显式 `undated` 出口：不吞、不填 0、也不让一格 503 拖死整张卡 | R332 裁定③，波次五排 | **已并树 `e9aac2f`**（cat-file -t→commit｜HEAD 祖先）｜候选位今天取消：`undated` 出口在树，503 与真零两张脸分开。 |

## 2. 撞车图（22:06 现取）

- 09-26 那张撞车图里**没有一枚还在途**：R333 已并树 `42a4e9e`、R338 已并树 `e0168b7`、R314 已并树 `40fe97c`、R336 已并树 `fc13df9`、R306 第二棒已并树 `6d00d70`、R339 已并树 `957c7d2`（六枚 `git cat-file -t` 读数同为 `commit`，本轮现取）⇒ 这五行今天不再替任何一枚单占写域。
- 纸面那句「无主可占」今天作废：R341 已并树 `acc092e`（HEAD 祖先），那块屏随后由 R411 并树 `4fcca16` 再收一笔（改的是 `lib/dashboard.js` 那四处假话）；这块屏上最后一枚还在动的单是 R410，**它也在本单施工期间并树** `73dd85f`（本单 09-28 现取：`git cat-file -t 73dd85f` = commit、01:22 落地、标题原文「并树 R410（施工 Fresnel…be-r410，基点 5621e8d）：DashboardPanel.vue 八枚裸 <button> 接进 ui 原语…」；它与本单同一起点，故 `git merge-base --is-ancestor 73dd85f HEAD` 在本树 rc=1 —— 这不是假 sha，只是还没并到本树这条线上，总控代提交时以主树为准）⇒ 这块屏今天三枚单（R341 / R411 / R410）全部有了凭据，纸面那句「无主可占」到此才算被现场读数清空。

## 3. 门先绿才有 run6

- 🔴 全量门自 R305（`01db964`）起就是红的，红在反证驱动器就地改写被跟踪源文件。**这一格今天已解除**：R339 已并树 `957c7d2`（标题原文「🔴 全量门自 R305 并树（01db964）起那枚红点当场由红转绿」）；09-28 现取主树最后一枚已知红由 R418 并树 `b83f812` 收掉。**本单没有跑过门**（全量门归总控），只登记账面位置。
- 并完波次三全部六枚之后的开窗顺序：`python scripts/run_gate.py` 绿 → 重建两枚镜像 → `check_image_provenance.py` rc=0 → `up -d --no-build` → `powercfg /change standby-timeout-ac 0` → run6 一窗多判据（A①②③④ + C 两格一次拿完）。

---

## 4. 🔴 本波作废：逐枚归因（R408 · 2026-09-28 · 凭据全部本轮 `git` 现取）

**结论一句话：§1 那六枚六枚全部早已并树，本波作废，不许再照它投。**

每一枚都跑过一次 `git cat-file -t <sha>`（读数原样抄在栏里）与 `git merge-base --is-ancestor <sha> HEAD`（rc=0）。
本波没有零提交项，所以「零提交 + 空读数」那种写法在这里一枚都没用上；纸面原话逐字留在行内，不改写。

| 单号 | 今天的状态 | `git cat-file -t` | 并树标题（`git log -1 --format=%s` 截取） | 纸面那句症状，09-28 现取的现场 |
|---|---|---|---|---|
| R341 | 已并树 `acc092e`（09-27 10:08） | `commit`，rc=0 | R341 并树（施工 Herschel…@be-r341）：总览那张「数据趋势」卡不再替服务端说假话 | `frontend/src/lib/dashboard.js` 有 `TREND_PATH` 与 `/dashboard/trend` 取数腿；`rg -n R341 frontend/src` 今天 10 枚命中（含 `frontend/src/components/DashboardPanel.vue:55`）⇒ 单已交付，纸面那句「还没做」是假话 |
| R337 | 已并树 `aefa3ce`（09-27 11:03） | `commit`，rc=0 | R337 并树（施工 Harvey…@be-r337）：数据集两处出口第一次都答 owner | `app/api/v1/data.py` 里 owner 出口在树，无主交 `None` |
| R316 | 已并树 `d609165`（09-27 11:47） | `commit`，rc=0 | R316 并树（施工 Sartre…@be-r316）：管理员第一次有一枚能看的名册屏 | `frontend/src/components/AdminPanel.vue` 在 `git ls-files`；纸面那句 `Test-Path False` 是 09-26 读数，已过期 |
| R315 | 已并树 `2cb3401`（09-27 12:25） | `commit`，rc=0 | R315 并树（施工 Noether…@be-r315）：成果屏第一次有自己的位置 | `frontend/src/router/index.js` 有 `/artifacts`，`ArtifactsPanel.vue` 在树 |
| R340 | 已并树 `dbb8ba4`（09-27 13:32） | `commit`，rc=0 | R340 并树（施工 Kepler…@be-r340）：趋势卡「其中当时未闭环」不再回头改自己的历史 | `app/api/v1/dashboard.py` 里 `alerts_open` 走第二把钟（R340 那一族注释在位） |
| R342 | 已并树 `e9aac2f`（09-27 12:15） | `commit`，rc=0 | R342 并树（施工 Galton…@be-r342）：/dashboard/trend 第一次把「一格没记时间」与「一本账读不出来」分成两件事 | `app/api/v1/dashboard.py` 里 `undated` 出口在树（`_TREND_UNDATED`） |

顺带登记两处下游：`lib/dashboard.js` 那四处替服务端说假话已由 R411 并树 `4fcca16` 收掉（HEAD 祖先，`git show --name-only` 点名 `frontend/src/lib/dashboard.js`）；总览那 8 枚裸按钮的债记在 R410 名下，**本单施工期间已并树** `73dd85f`（本单 09-28 现取：`git show --name-only 73dd85f` 点名 `frontend/src/components/DashboardPanel.vue` 与两前 `__tests__/*.test.js`，r288 债表 8⇒0）⇒ 这一格今天不再是活债；它与本波六枚无关，登记只为止血。

§3 那句「门先绿才有 run6」今天的状态：R339 `957c7d2` 与 R418 `b83f812` 已把两枚已知红收掉，剩下的开窗次序（跑门 → 重建两枚镜像 → 溯源 → `up -d --no-build` → run6）**一件没做，那是总控排窗与业主的活**，不在执行层半径内。

> 复算人：R408（执行层）。与 `-wave3-dispatch-plan.md` 同批改口，两纸文末同屏可见「作废」二字。
