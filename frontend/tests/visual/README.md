# V6 视觉回归（B 叶子线）

跑之前只需要一件事：`cd frontend && npm run build`。
用例**不起任何服务器**，由 `support/static-site.js` 用 `context.route` 从 `frontend/dist/`
读磁盘 fulfill；`fonts.googleapis.com` / `fonts.gstatic.com` / CDN 域名一律 abort，
模拟客户内网；`/api/**` 一律喂 401，用来验未登录分支。

```bash
npx playwright test                      # 五档视口 × 全部断言
npx playwright test --project=tablet-768  # 单档
npx playwright test                  # 没有基线时该条显式 skip，不假装通过

# 首次生成本地基线（基线不入库；CLI 的 --update-snapshots 传不进 worker，需要显式开关）
#   PowerShell: $env:EB_MAKE_BASELINES='1'; npx playwright test --update-snapshots
#   bash:       EB_MAKE_BASELINES=1 npx playwright test --update-snapshots
```

- 视口：`1440x900` `1920x1080` `3440x1440` `1280x720` `768x1024`（`playwright.config.js` 的 `VIEWPORTS`）。
- `deviceScaleFactor` 固定 1；`reducedMotion: reduce` + 注入 CSS 关掉 transition/animation 后再截图。
- 缺 `dist` 时用例**显式 skip**，不会静默变绿。
- `__snapshots__/`、`.output/` 已在 `.gitignore` 里，体积不进版本库。
- `unauthenticated-api.spec.js` 里那条 `test.fail()` 是已知缺陷 D-2 的闸门：
  F7 把面板错误位接到 `lib/errcodes.js` + `UiToast` 之后它会「意外通过」，届时删掉注解转为硬闸门。
- `event-contract.spec.js` 的三条 `test.fixme` 等 A 线 V3（router + 登录态）落地再补 body。
