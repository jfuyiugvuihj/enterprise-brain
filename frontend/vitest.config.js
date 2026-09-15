import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

/**
 * V5 单元测试配置（B 叶子线）
 *
 * 环境用 node 而不是 jsdom：本仓库 devDependencies 里没有 jsdom / happy-dom /
 * @vue/test-utils，且叶子线不许 npm i、不许改 lockfile。
 * 因此组件断言走 @vue/server-renderer（vue 自带依赖）出真实 HTML，
 * 交互逻辑（键盘导航 / 排序 / 焦点循环 / 上传校验）拆在同目录纯函数里直接单测。
 *
 * include 只收 `*.test.js`：`tests/visual/**.spec.js` 是 Playwright 用例，
 * 归 `npm run test:e2e`，不能被 vitest 收走。
 */
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'node',
    include: ['src/**/*.test.js'],
    exclude: ['**/node_modules/**', 'tests/visual/**'],
    css: false,
    reporters: ['default'],
  },
})
