/**
 * V6 视觉用例的固定输入（B 叶子线）
 *
 * 这里只放「组件渲染成什么样」的等价 markup，给两处共用：
 *   1. tests/visual/ui-states.spec.js —— setContent 之后在 Chromium 里量像素；
 *   2. src/components/ui/__tests__/states.test.js —— 断言这份 markup 里每一个 ui-* 类名
 *      与 data-testid 都真实存在于组件的 SSR 产物里（防止两份 markup 各漂各的）。
 *
 * 为什么是手抄而不是直接渲染组件：Playwright 不编译 .vue，而这两个原语此刻还没接进任何
 * 面板（接线归 A 线），拿不到真实页面 DOM。手抄 + 上面第 2 条耦合断言，是这里不撒谎的做法；
 * 一旦 A 线接线完成，本文件可以被真实页面选择器取代。
 */

/** 不含任何空格、不可断行的长串：没有 overflow-wrap: anywhere 就会撑破窄面板 */
export const LONG_URL =
  'https://intranet.example.gov.cn/api/v1/documents/2f9c8a71-4b6d-4e12-9a3f-7c05d1e8b244/preview?department=%E8%B4%A2%E5%8A%A1%E9%83%A8&page=1'

/** 一整段无标点中文：CJK 也必须正常折行，而不是把容器顶宽 */
export const LONG_ZH =
  '后端返回的原始原因是一长串没有任何标点符号的可读文本，用来验证状态块在窄面板里会不会把版面顶宽，因此这句话需要足够长，长到一行放不下才会被迫换行，这里再补上一段确保超过测量宽度'

/** 三个状态位的 data-testid，spec 与单测共用同一份，避免两处各写一套 */
export const STATE_TESTIDS = {
  empty: 'ui-empty-state',
  emptyAction: 'ui-empty-action',
  error: 'ui-error-state',
  retry: 'ui-error-retry',
}

/** 失败态：等价于 <UiErrorState title="这一步没有完成" :description="LONG_URL" :code-label="…" /> 的产物 */
export const ERROR_STATE_MARKUP =
  [
    '<div class="ui-error-state" role="alert" data-testid="ui-error-state">',
    '  <span class="ui-error-state__mark" aria-hidden="true">',
    '    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 4.5 3.5 19h17L12 4.5Z" /><path d="M12 10v4" /><path d="M12 16.6h.01" /></svg>',
    '  </span>',
    '  <div class="ui-error-state__body">',
    '    <p class="ui-error-state__title">这一步没有完成</p>',
    '    <p class="ui-error-state__desc">' + LONG_URL + '</p>',
    '    <p class="ui-error-state__code">错误码：weird_code_from_backend</p>',
    '  </div>',
    '  <div class="ui-error-state__actions">',
    '    <button class="ui-button ui-button--secondary ui-button--md" type="button" data-testid="ui-error-retry"><span class="ui-button__label">重试</span></button>',
    '  </div>',
    '</div>',
  ].join('\n')

/** 空态（紧凑档）：等价于 <UiEmptyState :title="LONG_ZH" dense action-label="去登记一条" /> 的产物 */
export const EMPTY_STATE_MARKUP =
  [
    '<div class="ui-empty-state ui-empty-state--dense" role="status" data-testid="ui-empty-state">',
    '  <span class="ui-empty-state__mark" aria-hidden="true">',
    '    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 13.5v3.2a1.8 1.8 0 0 0 1.8 1.8h13.4a1.8 1.8 0 0 0 1.8-1.8v-3.2" /><path d="M6.6 9.4 12 14.8l5.4-5.4" /><path d="M12 14.6V4.4" /></svg>',
    '  </span>',
    '  <div class="ui-empty-state__body">',
    '    <p class="ui-empty-state__title">' + LONG_ZH + '</p>',
    '  </div>',
    '  <div class="ui-empty-state__actions">',
    '    <button class="ui-button ui-button--primary ui-button--sm" type="button" data-testid="ui-empty-action"><span class="ui-button__label">去登记一条</span></button>',
    '  </div>',
    '</div>',
  ].join('\n')

/**
 * 反例对照组：同一条长串，抽掉换行机制（不给 overflow-wrap），外层收进 overflow: hidden。
 * 它必须溢出 —— 用来证明上面「不溢出」是组件机制救的，不是视口够宽、容器够大造成的假绿。
 */
export const CONTROL_MARKUP =
  [
    '<div class="fx-control">',
    '  <p class="fx-control__text">' + LONG_URL + '</p>',
    '</div>',
  ].join('\n')

/** fixture 里用到的全部组件类名（不含 fx-* 测试壳），耦合断言拿它比对真实 SSR 产物 */
export const FIXTURE_CLASSES = [
  'ui-error-state',
  'ui-error-state__mark',
  'ui-error-state__body',
  'ui-error-state__title',
  'ui-error-state__desc',
  'ui-error-state__code',
  'ui-error-state__actions',
  'ui-empty-state',
  'ui-empty-state--dense',
  'ui-empty-state__mark',
  'ui-empty-state__body',
  'ui-empty-state__title',
  'ui-empty-state__actions',
  'ui-button',
  'ui-button--primary',
  'ui-button--secondary',
  'ui-button--md',
  'ui-button--sm',
  'ui-button__label',
]
