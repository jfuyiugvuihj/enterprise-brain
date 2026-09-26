import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'

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
 *
 * 首跑税：关掉缓存时 transform 每次运行全部重做（vitest 自己提示 "re-done on every
 * run"）。fsModuleCache 把 transform 结果落盘，跨运行复用。
 * 路径必须显式给：默认值 <workspaceRoot>/node_modules/.vitest-cache 会经由本工作树
 * frontend/node_modules 这条 junction 落到主树，被所有工作树共用，于是
 * `vitest --clearCache` 和 lockfile 变更触发的整目录 rm -rf 会跨树互删。
 * 锚在配置文件上的绝对路径 = 每枚工作树各一份；tmp/ 在根 .gitignore 内，不污染 git status。
 * 相对路径不可用：vitest 内部不对它做 resolve，只在 process.cwd() 下拼接。
 */
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'node',
    include: ['src/**/*.test.js'],
    exclude: ['**/node_modules/**', 'tests/visual/**'],
    css: false,
    reporters: ['default'],
    fsModuleCache: true,
    fsModuleCachePath: fileURLToPath(new URL('../tmp/vitest-fs-cache/', import.meta.url)),
  },
})
