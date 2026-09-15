# components/ui —— V5 原语（B 叶子线产出）

统一从 `./index.js` 取。样式在同目录 `.css` 里，由组件自己 `import`，全局类名一律 `ui-` 前缀。
本目录不依赖 `element-plus`，不 import `lucide-vue-next`（图标暂用内联 SVG，A 线统一替换）。

| 组件 | 关键 props | slots | emits | 备注 |
| --- | --- | --- | --- | --- |
| `UiButton` | `variant` primary/secondary/ghost/danger · `size` md/sm · `loading` `disabled` `block` `type` `label` | default · `icon` | 原生 `click` | `loading` 时静态细环 + `aria-busy`，不加旋转动画 |
| `UiField` | `modelValue` `label` `hint` `error` `codeLabel` `type` `multiline` `rows` `required` `disabled` `readonly` `size` | `label` `hint` | `update:modelValue` `change` `blur` `focus` | `useId()` 绑 label/aria-describedby，错误位 `role="alert"` |
| `UiSelect` | `modelValue` `options` `label` `placeholder` `emptyText` `error` `codeLabel` `disabled` `size` `block` `expanded` | — | `update:modelValue` `change` `open` `close` | listbox 语义；方向键/Home/End/Enter/Esc 见 `list-nav.js` |
| `UiTable` | `columns` `rows` `sort`(v-model:sort) `rowKey` `emptyText` `loading` `stickyHeader` `zebra` `dense` `ariaLabel` | `cell-<key>` `empty` `footer` | `update:sort` `sort-change` `row-click` | 真 `<table>`；排序在 `table-sort.js`，空行沉底、中文按 zh-CN |
| `UiDialog` | `modelValue`(v-model) `title` `description` `size` `closeOnBackdrop` `closeOnEsc` `busy` `ariaLabel` | default · `description` · `footer({close})` | `update:modelValue` `open` `close` | 焦点锁在弹层内，关闭后焦点归还原元素 |
| `UiToast` | `tone` info/success/warning/danger · `message` `codeLabel` `retryable` `sticky` `dismissible` | default | `close` `retry` | 单条卡片；danger/warning=`role="alert"` |
| `UiToastHost` | `position` br/tr/tc | — | `retry(toast)` | 在 `App.vue` 根挂一次即可，队列在 `toasts.js` |
| `UiTabs` | `modelValue`(v-model) `items` `orientation` `ariaLabel` `emptyText` | `panel-<id>` `label-<id>` · default | `update:modelValue` `change` | roving tabindex；`role="tablist"` 满足 §8.2 |
| `UiUpload` | `label` `hint` `accept` `multiple` `maxSizeMb` `items` `busy` `disabled` `error` `codeLabel` `emptyText` | — | `select(files)` `reject({file,code})` `remove(i)` `retry(i)` | 前端校验只产 errcodes 里的码名，不新增码 |

## 错误展示唯一入口

```js
import { notifyError } from '@/components/ui'      // catch 里一行
notifyError(err)                                    // 内部走 normalizeError：三种错误形状 → { code, message, retryable }
```

`UiToastHost` 负责渲染队列（最多 4 条），`codeLabel` 只在未知码时出现 `错误码：xxx` 小字。

## token 依赖

组件只用 `frontend-visual-quality-2026-09-14.md` §5.1 那张表里的变量名（外加 `--control-h`
`--control-h-sm` `--dialog-w` `--toast-w` `--upload-h` `--select-max-h` 六个尺寸位）。
`theme.css` 目前一个都没有，缺失清单见 B 线回报；这些缺口的补齐属 A 线 V1，本目录不改 `theme.css`。
