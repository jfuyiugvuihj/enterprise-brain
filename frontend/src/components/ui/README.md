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
| `UiEmptyState` | `title` `description` `actionLabel` `actionVariant` `dense` | `icon` `description` default · `actions` | `action` | 面板级空态；`role="status"`（结果，不打断读屏），一句人话 + 一个主操作（§8.5）。测试位 `ui-empty-state` / `ui-empty-action` |
| `UiErrorState` | `title` `description` `codeLabel` `retryText` `retryable` `busy` `dense` | `icon` `description` default · `actions` | `retry` | 面板级失败态；`role="alert"`，只占 `--danger` 一个色相。测试位 `ui-error-state` / `ui-error-retry` |

## 错误展示唯一入口

```js
import { notifyError } from '@/components/ui'      // catch 里一行
notifyError(err)                                    // 内部走 normalizeError：三种错误形状 → { code, message, retryable }
```

`UiToastHost` 负责渲染队列（最多 4 条），`codeLabel` 只在未知码时出现 `错误码：xxx` 小字。

## 空态与失败态（面板接线用）

面板级「没数据 / 这一步失败了」统一用 `UiEmptyState` / `UiErrorState`，不要在面板里手搓 `empty-state`、
`panel-state error` 两个 div：样式自带，测试位固定（`ui-empty-state` / `ui-error-state` /
`ui-error-retry`），走查脚本与 e2e 直接抓。调用方自己传 `data-testid` 会**顶掉**组件默认值
（Vue 属性透传实测），要保住 `ui-*` 约定就别传。

```vue
<UiErrorState
  title="关系列表加载失败"
  :description="normalizeError(err).message"
  :code-label="errorCodeLabel(err)"
  :retryable="isRetryable(err)"
  retry-text="重新加载"
  :busy="loading"
  @retry="loadRelations"
/>

<UiEmptyState title="知识库里还没有已登记的关系" action-label="去登记一条" @action="focusForm" />
```

失败态的三件套都来自本目录：`errorCodeLabel` / `isRetryable` 全部读 `normalizeError` 的产物，
面板不必自己碰后端原始响应。权限类失败传 `:retryable="false"`，不给用户一个只会再失败一次的按钮。

## token 依赖

组件只用 `frontend-visual-quality-2026-09-14.md` §5.1 那张表里的变量名（外加 `--control-h`
`--control-h-sm` `--dialog-w` `--toast-w` `--upload-h` `--select-max-h` 六个尺寸位，以及
`--z-dropdown` `--z-dialog` `--z-toast` 三个叠层位）。这些变量 A 线 V1（`e3b57a2`）已全部落进
`theme.css`，缺失基线钉在 0：谁引用了没定义的 token，`src/lib/design-tokens.test.js` 直接判红。
本目录不写 `theme.css`。
