# 前端并行开工看板（2026-09-15）

**规则**：每条对话 / 每个子 Agent 开工前只读 §1 找自己那一行 + §4 看闸门颜色。**闸门不绿就不许做任何写操作**，只许只读准备。
**翻绿的唯一凭据是 commit**：翻闸人自己提交、自己把 commit 号写进 §4，并在自己 worktree 里 `git merge --ff-only codex/data-file-catalog` 让全树看到。**不靠记忆、不靠默契、不靠"我觉得做完了"。**

---

## 1. 门禁表（各角色看自己一行）

| 角色 | 目录 / 分支 | 开工前置 | 第一件事 | 完成后要翻的闸 |
|---|---|---|---|---|
| **C 后端** | `企业智脑`（主树）/ `codex/data-file-catalog` | 无 | 实现 e2 检索（六条要求见 handoff 跟进单 §6.2），再做 R1 员工告警 | **G3**、**G4** |
| **A 主干** | `fe-trunk` / `codex/fe-trunk` | G0 | Step 1 = 依赖 + script 入口，单独提交 | **G1**，随后每步翻 **G-A-n** |
| **B 叶子** | `fe-prims` / `codex/fe-prims` | **G1** | G1 前只做只读准备；G1 后写 `lib/errcodes.js` + 6 个纯 CSS 原语 | **G2** |
| **D 验收** | `fe-trunk` | **G-A-3 且 G2** | 逐条复测工单 §6 证据 | 验收报告（不改代码） |
| 子 Agent（E 模板） | 由父对话派出 | 父对话已绿自己那一行 | 只写派单里列的文件 | 不翻闸，回报给父对话 |

---

## 2. 闸门定义（可机器验证，别靠感觉）

| 闸 | 绿的条件 | 自证命令（在对应目录跑） |
|---|---|---|
| **G0** | 七面板应用已在版本控制里 | `git log --oneline -1 -- frontend/src/assets/theme.css` 有结果 |
| **G1** | `fe-trunk` 出现含 `chore(deps)` 的提交，且 `package.json` 有 `lint` / `test` / `test:e2e` 三个入口、无 `element-plus` | `npm pkg get scripts dependencies --prefix frontend` |
| **G2** | `components/ui/` ≥ 6 个组件 + `lib/errcodes.js` 存在 + `npx vitest run` 全绿 | `npx vitest run` |
| **G3** | `app/rag/filters.py` 出现 administrator 判据，且**真机** admin 能问出知识库答案 | `git grep -c "administrator" -- app/rag/filters.py` ≥ 1 |
| **G4** | `GET /alerts` 对 staff 返回 200 而非 403 | 用 staff 探针账号打一次，记状态码 |
| **G-A-n** | A 线第 n 步（F1/F2/F3/V1…）的 commit，且工单 §6 对应证据已改 | `git log --oneline -1` + 工单 diff |

**G3 一翻绿，立刻做两件事**：① 撤掉工单 §0.2 与计划 §8.1 的「必须带部门账号」前置；② 让 D 补一条 admin 开箱用例。G4 一翻绿，F5b 从"阻塞"变"可做"。

---

## 3. 放行顺序（就按这个来，别抢跑）

```
现在 ──┬── C：e2 → R1（最长的一条腿，先派）
       └── A：Step 1 deps ──→ G1 绿
                    │
                    ├────→ B 开工（G1 前它只能只读）
                    └────→ A 继续 F1 → F2 → F3 → V1 → V2 …（不等 B）
                                  │
C 的 G3 / G4 ────────────────────┘（改的是后端行为，A 每步开工前 merge 主树即可拿到）

B 交完 G2 ──┐
A 交完 G-A-3 ┴──→ D 开工（复测）
A 走到 V5(接线) 之前必须等到 G2，否则停下等，不要自己造原语
```

唯一会返工的接缝 = **A 到 V5 时 G2 还没绿**。所以 B 的排期要压在 A 的 F1→F2→F3→V1→V2 这段时间内完成。

---

## 4. 状态板（谁翻谁写，一行一证据）

| 闸门 | 状态 | commit / 命令输出 | 时间（实取） | 翻闸人 |
|---|---|---|---|---|
| G0 | 🟢 | `13e808d` | 2026-09-15 | 计划线 |
| G1 | 🟢 | `e000bef`（`fe-trunk`：deps + `lint`/`test`/`test:e2e` 入口，`element-plus` 已摘；`npm run build` 286ms 通过；`fe-prims` 已 ff 到同 commit） | 2026-09-15T12:32:53 | 总控 |
| G2 | ⚪ | | | |
| G3 | 🟡 **代码绿，真机待验** | `719f29c`：`app/rag/filters.py` 复用 `policy.is_administrator`；`git grep -c administrator -- app/rag/filters.py` ≥1；全量 `713 passed / 22 skipped / 0 failed`。**缺口**：运行中的容器是旧镜像，"开箱 admin 问得出答案"必须重建后端镜像才能证（约 28 分钟，待用户点头） | 2026-09-15T12:52:02 | 总控 |
| G4 | ⚪ | | | |
| G-A-1 (F1) | ⚪ | | | |

---

## 5. 冲突仲裁与全局停写

- 需要别人范围内改动：**在 §4 加一行「请求：…」，不代写**。谁的文件谁改。
- 需要用户拍板：写「待决」，不许自己猜（当前待决：**重建后端镜像以证 G3 真机那半**、「停止 = 拒绝挂起动作？」、真机验收探针账号是哪几个、仓库根与 `tests/browser_*` 垃圾要不要 `.gitignore`、`rbac.py` 死代码清理的一次性授权）。
- **全局停写条件**：主树 `app/**` 或任一 worktree `frontend/**` 出现未提交改动（除主树那 2 个刻意保留项）→ 全线停手先归属。本轮真实教训：e2 早在后端线工作树里写完却**未提交**，且 `chat.py` 缺 import 使成功路径抛 `NameError`——差一天就没人知道。
- 一个分支只属于一个工作树：不许 `git checkout` 别人那条线的分支，要开工就换目录。
