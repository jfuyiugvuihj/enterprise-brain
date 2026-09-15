# Enterprise Brain Frontend Visual Upgrade Implementation Plan

> **⚠️ 已被取代（2026-09-15 标注）**：本计划整体作废，**不要照此开工**。
> 取代者：`docs/frontend-visual-quality-2026-09-14.md`（视觉规范与令牌）+ `docs/frontend-plan-2026-09-14.md` §5/§6（登录页与实施顺序）。
> 本文件无任何完成度标记，其布局假设已被 7 入口 → 5 主视图 + 1 管理视图的重排推翻。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the broken default-block layout with a coherent responsive enterprise workbench while preserving existing authentication and module behavior.

**Architecture:** Keep `App.vue` responsible for auth state, navigation, and shell composition. Put global tokens, resets, shared controls, shell layout, and responsive rules in `frontend/src/assets/theme.css`; leave business logic inside existing panels and style their public containers through shared selectors.

**Tech Stack:** Vue 3 Composition API, Vite, plain CSS custom properties, Playwright Core with the existing Chrome executable.

## Global Constraints

- Do not change API contracts or business behavior.
- Preserve the existing seven navigation modules.
- Support desktop widths around 1440px and 1024px plus mobile width around 390px.
- Respect `prefers-reduced-motion`.
- Verify with `npm run build` and real browser screenshots.

### Task 1: Rebuild global visual system

**Files:**
- Modify: `frontend/src/assets/theme.css`

- [x] Replace unscoped fallback-like styles with explicit tokens, reset, shell, auth, navigation, card, form, responsive, and reduced-motion rules.
- [x] Keep existing component class names supported so business panels retain behavior.
- [x] Verify with `npm run build`.

### Task 2: Refine app shell copy and structure

**Files:**
- Modify: `frontend/src/App.vue`

- [x] Add accessible labels and stable classes for the login form.
- [x] Add shell status and navigation structure without changing state transitions.
- [x] Keep `script setup` Composition API and existing component contracts.
- [x] Verify with `npm run build`.

### Task 3: Validate rendered UI

**Files:**
- Create: `tests/browser_visual_acceptance.cjs`
- Create: `tests/browser_visual_acceptance.json`
- Create: `tests/browser_visual_login.png`
- Create: `tests/browser_visual_workbench.png`
- Create: `tests/browser_visual_mobile.png`

- [x] Launch the running frontend, inspect login at desktop and mobile sizes.
- [x] Log in through the rendered UI and inspect overview, documents, data, insights, graph, approval, and chat navigation.
- [x] Capture screenshots and fail on page errors or missing shell selectors.
