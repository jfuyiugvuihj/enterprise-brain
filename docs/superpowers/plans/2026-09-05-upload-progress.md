# Knowledge Base Upload Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show upload percentage and processing state for knowledge-base files.

**Architecture:** Keep the existing Axios upload endpoint and reactive `uploads` queue. Use `onUploadProgress` for the real upload phase, then show a non-precise processing phase until the synchronous backend response arrives.

**Tech Stack:** Vue 3, Axios, Vite, pytest source-contract tests.

## Global Constraints

- Do not change the backend upload protocol.
- Do not fake an exact percentage during document parsing.
- Preserve JWT injection, batch upload, and existing error messages.
- Use `apply_patch` for manual edits.

## Task 1: Regression Tests

**Files:**
- Modify: `C:\Users\fengx\PycharmProjects\企业智脑\tests\test_frontend_upload_auth.py`

- [x] Add assertions for `progress`, `phase`, `onUploadProgress`, processing state, progress bar, and 100 percent completion.
- [x] Run the focused tests and observe the expected failure before implementation.

## Task 2: Upload Progress UI

**Files:**
- Modify: `C:\Users\fengx\PycharmProjects\企业智脑\frontend\src\components\DocPanel.vue`

- [x] Add `progress` and `phase` to each upload item.
- [x] Map real upload progress to 0-70 percent.
- [x] Switch to processing state after the upload response begins and set successful uploads to 100 percent.
- [x] Render a progress bar, percentage, stage text, and retain the animated indicator.

## Task 3: Verification

**Files:**
- Modify: `C:\Users\fengx\PycharmProjects\企业智脑\findings.md`
- Modify: `C:\Users\fengx\PycharmProjects\企业智脑\progress.md`

- [x] Run focused frontend contract tests.
- [x] Run `npm run build`.
- [x] Run full pytest and `git diff --check`.
- [x] Record actual results and browser verification limitations.
