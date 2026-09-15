import { defineConfig, devices } from '@playwright/test'

/**
 * V6 视觉回归配置（B 叶子线）
 *
 * 不打真服务器：`tests/visual/support/static-site.js` 用 context.route 从
 * `frontend/dist/` 直接 fulfill 磁盘文件，同时 abort 远程字体域名，
 * 并把 /api/** 一律喂 401（验 F3 的未登录分支）。
 * 因此跑之前必须先 `npm run build`；缺 dist 时用例显式 skip，不假装通过。
 *
 * 基线截图不入库（体积），见 tests/visual/.gitignore；
 * 首次生成：`npx playwright test --update-snapshots`。
 */
export const VIEWPORTS = [
  { name: 'desktop-1440', width: 1440, height: 900 },
  { name: 'desktop-1920', width: 1920, height: 1080 },
  { name: 'ultrawide-3440', width: 3440, height: 1440 },
  { name: 'laptop-1280', width: 1280, height: 720 },
  { name: 'tablet-768', width: 768, height: 1024 },
]

export default defineConfig({
  testDir: './tests/visual',
  testMatch: '**/*.spec.js',
  // 基线一律落在 tests/visual/__snapshots__/<spec>-<project>/ 下，目录整体不入库
  snapshotPathTemplate: '{snapshotDir}/{testFileDir}/__snapshots__/{testFileName}-{projectName}/{arg}{ext}',
  outputDir: './tests/visual/.output',
  timeout: 60000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  expect: {
    toHaveScreenshot: {
      // 关动效截图：动画与 CSS transition 一律冻结，避免同一次运行两张图不一致
      animations: 'disabled',
      caret: 'hide',
      scale: 'css',
      maxDiffPixelRatio: 0.01,
    },
  },
  use: {
    baseURL: 'http://enterprise-brain.test',
    // 客户机常见 1x 屏，deviceScaleFactor 固定 1 以稳定像素比对
    deviceScaleFactor: 1,
    viewport: { width: 1440, height: 900 },
    reducedMotion: 'reduce',
    forcedColors: 'none',
    colorScheme: 'dark',
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    trace: 'off',
    video: 'off',
    screenshot: 'only-on-failure',
  },
  projects: [
    ...VIEWPORTS.map((viewport) => ({
      name: viewport.name,
      metadata: { viewport: `${viewport.width}x${viewport.height}` },
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: viewport.width, height: viewport.height },
        deviceScaleFactor: 1,
        reducedMotion: 'reduce',
      },
    })),
  ],
})
