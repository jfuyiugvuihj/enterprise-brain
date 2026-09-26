# V2 波次四 派工计划（09-26 22:06 · 总控线 · 预配，随波次三结案逐枚投出）

- 本文件的每一条都是总控在 `466d8a1`/`18eebbc` 现取的，不是转述。事实源仍是 `docs/version-roadmap-and-next-week-plan-2026-09-22.md` 的 V2 硬要求。
- 派工一律走波次三那条纪律：一个 block 一枚投递、零 model 覆盖、返回 id 当场写 §0 名册、点名件必须逐枚列出（R332 那笔「自述 313 / 实跑 293+26」的教训）。

## 1. 队列

| 号 | 一句话症状（现取凭据） | 写域 | 关键判据 | 何时可投 |
|---|---|---|---|---|
| **R341** | 「数据趋势」那张卡今天说的是假话：`DashboardPanel.vue:300-305` 明写「服务端还没有回传按期间汇总的时间序列，这一格就空着」——而 R332（并树 `ae7dc96`）已经把 `GET /dashboard/trend` 交出来了 | `frontend/src/components/DashboardPanel.vue` + `frontend/src/lib/dashboard.js` + 新钉 | 数字只能来自 `/trend` 的 series，🔴 不许前端自己按时间重算第二遍；照 R332 裁定①写「新增条目数」，不许暗示金额刻度；`alerts` 键整键缺席（staff）那一行必须有自己那张脸；503 与「这一期真的零」两张脸分开；月/周切换照 period 参数走 | 无主，槽一空就投 |
| **R337** | `data.py:294-300` 回 `dataset_id/version_id/classification` 独缺 owner，`:305` 那个 preview 出口同病（R310 的尾巴） | `app/api/v1/data.py` + 新钉 | 与 R310 同一把无主口径（`catalog.py` 的 `None`，不是空串）；不为补字段多开一次查询；逐档行数不变 | 🔴 与 R336 同文件 ⇒ 等 `Heisenberg` 并完 |
| **R316** | 管理员零管理屏，而登录页早把员工指向「用户管理」：`frontend/src/components/AdminPanel.vue` 不存在（`Test-Path` 现取 False） | `router/index.js` + 新 `AdminPanel.vue` + 三枚导航钉 | 只读既有出口；不碰 `App.vue`；导航钉三处同源，加一枚屏就三处一起改 | 🔴 与 R315 同抢 `router/index.js` ⇒ 二选一或合一枚（合称估 1.5 人日） |
| **R315** | 成果屏没有自己的位置：`ArtifactList.vue` 早在树里，但只作为 `DataPanel.vue:454` 的子件存在，`router/index.js:53-113` 十条路由里没有它 | `router/index.js` + 新屏壳（薄封装）+ 同三枚钉 | 屏壳**一字不改** `ArtifactList.vue`；只做路由与壳 | 同上 |
| **R340 候选** | `alerts_open` 是当前状态投影到既往期间（上周的告警今天被确认，会让上周那桶变小），不可回放 | `app/api/v1/dashboard.py` | 按 `acknowledged_at` 算真实历史未处置数；口径变更必须同批改契约 | R332 裁定②，波次五排 |
| **R342 候选** | legacy `created_at=''` 会把 `/trend` 整格打死成 503 | `app/api/v1/dashboard.py` | 显式 `undated` 出口：不吞、不填 0、也不让一格 503 拖死整张卡 | R332 裁定③，波次五排 |

## 2. 撞车图（22:06 现取）

- `App.vue` → `Huygens`/R333（顶栏挂载点）；`DocPanel.vue` → `Plato`/R338；`DocumentPreviewModal.vue` + `GraphPanel.vue` → `Bohr`/R314；`data.py` + `excel.py` → `Heisenberg`/R336；`chat.py` + `test_file_upload_security.py` → `Rawls`/R306 第二棒；`tests/fixtures/r305_refutation_driver.py` + `spreadsheets.py` 注释 → `Jason`/R339。
- 无主可占：`DashboardPanel.vue`（R341）。

## 3. 门先绿才有 run6

- 🔴 全量门自 R305（`01db964`）起就是红的，红在反证驱动器就地改写被跟踪源文件。**R339 并树之前不跑全量门、不开跑分窗**——否则 run6 跑到一半会被同一枚假红打断。
- 并完波次三全部六枚之后的开窗顺序：`python scripts/run_gate.py` 绿 → 重建两枚镜像 → `check_image_provenance.py` rc=0 → `up -d --no-build` → `powercfg /change standby-timeout-ac 0` → run6 一窗多判据（A①②③④ + C 两格一次拿完）。
