# 上传进度图标 Implementation Plan

> **⚠️ 状态（2026-09-15 标注）**：**目标已交付，但交付的是假进度**。`frontend/src/components/DocPanel.vue:36-52` 的 `startProgressTimer()` 用 `setInterval` 自行累加并封顶，数值不来自服务端。
> 后端现已具备真数据源（`parse_status`，即 R4 / B-3，已落地）。真实进度改造归 `docs/frontend-plan-2026-09-14.md` §2 的「喂料」视图，**不要在本计划下另开一轮**。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在知识库上传队列中显示动态进度图标和清晰的上传阶段文案。

**Architecture:** 修改 `DocPanel.vue` 中已有的 `uploads` 状态项。模板根据
`item.status` 渲染 SVG 旋转进度环或终态图标，`uploadFiles` 在请求开始后更新
阶段文案；不新增接口、轮询或共享状态。

**Tech Stack:** Vue 3 `<script setup>`、Axios、scoped CSS、Pytest 源码回归测试。

## Global Constraints

- 保持现有后端 `/api/v1/upload` 接口和响应格式不变。
- 仅在 `status === "uploading"` 时显示动画。
- 终态图标继续覆盖完成、跳过和失败三种状态。
- 不新增第三方依赖。

---

### Task 1: 上传队列进度视觉

**Files:**
- Modify: `frontend/src/components/DocPanel.vue`
- Modify: `tests/test_frontend_upload_auth.py`

**Interfaces:**
- Consumes: 每个上传项的 `{ name, status, msg }`。
- Produces: `uploading` 状态的 SVG 进度环、`解析入库中...` 文案和旋转动画。

- [ ] **Step 1: 写失败测试**

```python
def test_document_upload_shows_an_animated_progress_indicator():
    source = (ROOT / "frontend" / "src" / "components" / "DocPanel.vue").read_text(
        encoding="utf-8"
    )

    assert 'class="upload-progress-ring"' in source
    assert "解析入库中..." in source
    assert "@keyframes upload-progress-spin" in source
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_frontend_upload_auth.py
```

Expected: FAIL，因为进度环标记、阶段文案和动画尚不存在。

- [ ] **Step 3: 实现最小前端改动**

```vue
<span v-if="item.status === 'uploading'" class="upload-progress-ring" role="status">
  <svg viewBox="0 0 20 20" aria-hidden="true">
    <circle class="upload-progress-track" cx="10" cy="10" r="7" />
    <circle class="upload-progress-arc" cx="10" cy="10" r="7" />
  </svg>
</span>
```

在 `axios.post` 发出后将 `item.msg` 更新为 `解析入库中...`，并添加
`upload-progress-spin` CSS 动画。保留现有完成、跳过和失败图标分支。

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_frontend_upload_auth.py
```

Expected: PASS。

- [ ] **Step 5: 构建前端**

Run:

```powershell
cd frontend
npm run build
```

Expected: `built in ...ms` 且退出码为 0。

- [ ] **Step 6: 提交**

```powershell
git add frontend/src/components/DocPanel.vue tests/test_frontend_upload_auth.py
git commit -m "feat: show upload progress indicator"
```
