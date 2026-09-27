<script>
/**
 * NotificationBell —— 顶栏那枚欠回来的铃铛（R333）
 *
 * 这一格的历史（不是新增玩法，是把当年欠的那格接回来）：R278 按判据 G16①② 主动摘掉顶栏两枚
 * 按了没反应的假控件，其中通知那一枚摘在「今天没有一句诚实的条数可摆」（r278-topbar.test.js:14）——
 * 那时 GET /hitl/pending 的 count 只是一页过滤后的长度，dashboard 那一格自己写着「可能高估」。
 * R299 把出口补上了：GET /notifications 按【全集口径】交回未读总数（unread_total），
 * 并在窗口裁过时把 is_exact 落成 false。所以今天这枚徽标有真数字可摆，代价是诚实口径：
 *   · 数字只出自 lib/notifications.js 的全集未读，页内条数在那一层就不往上交（判据①）；
 *   · is_exact=false 说的是「至少」，不是「正好」（判据①的后半）；
 *   · 还没读到 / 读失败时【不画数字】也不说「没有未读」，0 与未知是两张脸（判据③）；
 *   · 一次动作之后的新数字来自再读一次后端，不来自 unread - changed 那种自己算（判据④⑤）。
 *
 * 四张脸互不顶替（判据⑥），顺序即语义：loading 优先于一切，失败排在「空」之前——
 * 把「读不到」画成「没有通知」是这一单最不能犯的错，反证钉专门打这一条。
 *
 * 可达性（判据⑦）：触发件是 components/ui 的 UiButton（真 button，Enter/Space 是原生行为，
 * 不在这里另造一套），带 aria-label 的可读句子（「3 条未读通知」而不是孤零零一个 3）、
 * aria-expanded / aria-controls；Esc 关闭（复用 ui/focus-trap.js 那一枚 shouldCloseOnKey，
 * 不在输入元素里抢「清空输入」的语义），关闭后焦点交回触发件。Tab 可达由原生 button 保证。
 *
 * 判据⑧：搜索那一格仍【没有】接——全站没有一枚诚实的全局检索端点，接了就是回到假控件。
 * 这里只接通知这一枚。
 */
import { errorDetail } from '../lib/http'
import {
  ALL_FILTER,
  INBOX_PAGE_LIMIT,
  bellLabel,
  badgeText,
  collectUnreadIds,
  dismissNotifications,
  isShapeFailure,
  markAllUnread,
  markRead,
  panelSummary,
  readFailureViewOf,
  readInbox,
  shapeFailureViewOf,
  writeFailureView,
} from '../lib/notifications'
import { shouldCloseOnKey } from './ui/focus-trap.js'

export default { name: 'NotificationBell' }

export const PANEL_TITLE = '通知'
/** 空态说的是「后端确实报了没有」，不是「我没读到」：两句话不许互相顶替。 */
export const EMPTY_TITLE = '现在没有要看的通知'
export const EMPTY_DESCRIPTION = '这一格是那三本既有账的投影：挂起待办、异常告警、已入库文档。'
  + '这里为空只说明现在没有可读回来的条目，不等于公司一切正常，也不等于这一格坏了。'

/**
 * 面板画哪一张脸的唯一出口（与 HitlPendingPanel.vue 的 pendingFace 同一形状）：
 * loading 优先，失败次之，只有两者都不在时才轮到「有没有行」。
 */
export function inboxFace({ loading = false, failure = null, rowCount = 0 } = {}) {
  if (loading) return 'loading'
  if (failure) return failure.face
  return Number(rowCount) > 0 ? 'list' : 'empty'
}

/** 一次读失败的成品卡：把错误对象一并留给原语的详情区（后端原文唯一的渲染出口在 error-detail.js）。 */
function readFailureCard(err) {
  const view = isShapeFailure(err) ? shapeFailureViewOf() : readFailureViewOf(err)
  return { ...view, rawError: err, detail: errorDetail(err, view.description) }
}

/**
 * 焦点落点：组件实例给的是 $el，普通元素给的是自己；拿不到可聚焦目标就什么都不做，
 * 绝不为了「看起来像有焦点」去猜一个别的选择器（本仓没有 DOM 可查）。
 */
export function focusTarget(target) {
  const node = target && target.$el ? target.$el : target
  if (node && typeof node.focus === 'function') node.focus()
  return Boolean(node && typeof node.focus === 'function')
}

/** Esc 之外一律不动作：面板里没有输入框，但将来加了也不该被这一格抢走清空语义（判据⑦）。 */
export function closeKeyAction(event) {
  if (!event || event.defaultPrevented === true) return false
  return shouldCloseOnKey(event.key, event.target && event.target.tagName)
}
</script>

<script setup>
import { computed, nextTick, onMounted, shallowRef } from 'vue'

// 模板要用的原语必须在 <script setup> 里 import：普通 <script> 的绑定进不了 setupState，
// 放在那里模板只会解析不到组件、静默画出一枚不认识的标签（本单实撞过一次，这条不是猜的）。
import UiButton from './ui/UiButton.vue'
import UiEmptyState from './ui/UiEmptyState.vue'
import UiErrorState from './ui/UiErrorState.vue'
import UiLoadingState from './ui/UiLoadingState.vue'

const inbox = shallowRef(null)
const rows = shallowRef([])
// 初值就是在读：一次都没读过的时候，这一格不配替后端宣布「没有通知」（判据③⑥的命门）。
const loading = shallowRef(true)
const failure = shallowRef(null)
const writeFailure = shallowRef(null)
const busy = shallowRef('')
const open = shallowRef(false)

const bellEl = shallowRef(null)
const panelEl = shallowRef(null)

// 徽标与读屏句子的数字出处只有一个：后端全集未读。inbox 为 null 就是「未知」，不是 0。
const unread = computed(() => (inbox.value ? inbox.value.unread : null))
const isExact = computed(() => Boolean(inbox.value && inbox.value.isExact))
const badge = computed(() => badgeText(unread.value, { isExact: isExact.value }))
const ariaLabel = computed(() => bellLabel(unread.value, { isExact: isExact.value, failed: Boolean(failure.value) }))
const summary = computed(() => panelSummary(inbox.value))
const face = computed(() => inboxFace({ loading: loading.value, failure: failure.value, rowCount: rows.value.length }))
const hasUnread = computed(() => unread.value !== null && unread.value > 0)

async function refresh() {
  loading.value = true
  failure.value = null
  try {
    const page = await readInbox({ state: ALL_FILTER, limit: INBOX_PAGE_LIMIT, offset: 0 })
    inbox.value = page
    rows.value = page.rows
  } catch (err) {
    // 读不到就承认读不到：旧数字一律清掉，不许留着上一轮的读数冒充这一次。
    inbox.value = null
    rows.value = []
    failure.value = readFailureCard(err)
  } finally {
    loading.value = false
  }
}

async function openPanel() {
  open.value = true
  writeFailure.value = null
  await nextTick()
  focusTarget(panelEl.value)
  if (!loading.value) await refresh()
}

function closePanel() {
  if (!open.value) return
  open.value = false
  focusTarget(bellEl.value)
}

async function togglePanel() {
  if (open.value) {
    closePanel()
    return
  }
  await openPanel()
}

async function onKeydown(event) {
  if (!open.value || !closeKeyAction(event)) return
  if (typeof event.preventDefault === 'function') event.preventDefault()
  closePanel()
}

/**
 * 一次写的收尾一律是【再读一次后端】：徽标的数字只可能由那一次读决定。
 * changed 为真为假都不在这里做减法（判据④：第 N 次点同一枚时后端回 changed=false，
 * 全集未读没动，重读回来的还是同一个数——用例把这条钉成红/绿两态）。
 */
async function afterWrite() {
  await refresh()
}

async function markOne(row, action) {
  const id = row && row.id ? row.id : ''
  if (!id || busy.value) return null
  busy.value = id
  writeFailure.value = null
  try {
    const receipt = action === 'dismiss' ? await dismissNotifications([id]) : await markRead([id])
    await afterWrite()
    return receipt
  } catch (err) {
    writeFailure.value = writeFailureView(err)
    await afterWrite()
    return null
  } finally {
    busy.value = ''
  }
}

async function markEverything() {
  if (busy.value) return null
  busy.value = 'all'
  writeFailure.value = null
  try {
    const receipt = await markAllUnread()
    await afterWrite()
    return receipt
  } catch (err) {
    writeFailure.value = writeFailureView(err)
    await afterWrite()
    return null
  } finally {
    busy.value = ''
  }
}

onMounted(() => {
  // 徽标要在人点开之前就有数，所以挂载读一次——今天读得起，因为 R299 交回的是全集口径而不是页内长度。
  refresh()
})

defineExpose({
  ariaLabel,
  bellEl,
  badge,
  busy,
  closePanel,
  face,
  failure,
  inbox,
  loading,
  markEverything,
  markOne,
  onKeydown,
  open,
  openPanel,
  panelEl,
  refresh,
  rows,
  summary,
  togglePanel,
  unread,
  writeFailure,
})
</script>

<template>
  <div class="notif" data-testid="notification-bell">
    <UiButton
      ref="bellEl"
      class="notif__bell"
      variant="ghost"
      size="sm"
      type="button"
      :aria-label="ariaLabel"
      :title="ariaLabel"
      aria-haspopup="dialog"
      aria-controls="notification-panel"
      :aria-expanded="open ? 'true' : 'false'"
      data-testid="notification-trigger"
      @click="togglePanel"
      @keydown="onKeydown"
    >
      <template #icon>
        <svg class="notif__icon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M6 9a6 6 0 0 1 12 0c0 4 1.4 5.6 2 6.4H4c.6-.8 2-2.4 2-6.4Z" />
          <path d="M10 19a2 2 0 0 0 4 0" />
        </svg>
      </template>
      <span v-if="badge" class="notif__badge" data-testid="notification-badge" aria-hidden="true">{{ badge }}</span>
      <span v-else-if="failure" class="notif__marker" aria-hidden="true">!</span>
    </UiButton>

    <section
      v-if="open"
      id="notification-panel"
      ref="panelEl"
      class="notif__panel"
      role="dialog"
      :aria-label="ariaLabel"
      tabindex="-1"
      data-testid="notification-panel"
      @keydown="onKeydown"
    >
      <header class="notif__head">
        <h2 class="notif__title">{{ PANEL_TITLE }}</h2>
        <p class="notif__summary">{{ summary }}</p>
        <UiButton
          class="notif__close"
          variant="ghost"
          size="sm"
          type="button"
          aria-label="关闭通知"
          data-testid="notification-close"
          @click="closePanel"
        >×</UiButton>
      </header>

      <p v-if="writeFailure" class="notif__note" role="status" data-testid="notification-write-note">
        {{ writeFailure.title }}：{{ writeFailure.description }}
      </p>

      <UiLoadingState
        v-if="face === 'loading'"
        dense
        :rows="3"
        label="正在读取通知"
      />
      <UiErrorState
        v-else-if="failure"
        dense
        :title="failure.title"
        :description="failure.description"
        :code-label="failure.codeLabel"
        :raw-error="failure.rawError"
        :retryable="failure.retryable"
        :busy="loading"
        retry-text="重新加载"
        @retry="refresh"
      />
      <UiEmptyState
        v-else-if="face === 'empty'"
        dense
        :title="EMPTY_TITLE"
        :description="EMPTY_DESCRIPTION"
      />
      <ul v-else class="notif__list" data-testid="notification-list">
        <li v-for="row in rows" :key="row.id" class="notif__row" data-testid="notification-row">
          <p class="notif__row-title">{{ row.title }}</p>
          <p v-if="row.detail" class="notif__row-detail">{{ row.detail }}</p>
          <p class="notif__row-meta">
            <span v-if="row.createdAt">{{ row.createdAt }}</span>
            <span v-if="!row.read" class="notif__row-state">未读</span>
          </p>
          <div class="notif__row-actions">
            <UiButton
              v-if="!row.read"
              variant="secondary"
              size="sm"
              type="button"
              label="标为已读"
              :loading="busy === row.id"
              :disabled="Boolean(busy) && busy !== row.id"
              :aria-label="row.title + '：标为已读'"
              data-testid="notification-mark-read"
              @click="markOne(row, 'read')"
            />
            <UiButton
              variant="ghost"
              size="sm"
              type="button"
              label="划掉"
              :loading="busy === row.id"
              :disabled="Boolean(busy) && busy !== row.id"
              :aria-label="row.title + '：划掉这条通知'"
              data-testid="notification-dismiss"
              @click="markOne(row, 'dismiss')"
            />
          </div>
        </li>
      </ul>

      <footer v-if="face === 'list' || face === 'empty'" class="notif__foot">
        <UiButton
          variant="secondary"
          size="sm"
          type="button"
          label="全部标为已读"
          :loading="busy === 'all'"
          :disabled="!hasUnread"
          data-testid="notification-mark-all"
          @click="markEverything"
        />
      </footer>
    </section>
  </div>
</template>

<style scoped>
.notif {
  position: relative;
}

.notif__bell {
  position: relative;
  width: var(--control-h-sm);
  min-height: var(--control-h-sm);
  padding: 0 var(--s-2);
  color: var(--text-2);
  border-radius: var(--r-sm);
}

.notif__bell:hover {
  color: var(--accent-hover);
}

.notif__icon {
  display: block;
}

.notif__badge {
  position: absolute;
  top: -2px;
  right: -2px;
  min-width: 16px;
  padding: 0 4px;
  color: var(--text-invert);
  background: var(--danger);
  border-radius: var(--r-pill);
  font-size: var(--t-xs);
  font-weight: 700;
  line-height: 16px;
  text-align: center;
}

.notif__marker {
  position: absolute;
  top: -2px;
  right: -2px;
  color: var(--danger);
  font-size: var(--t-xs);
  font-weight: 700;
}

.notif__panel {
  position: absolute;
  top: var(--s-6);
  right: 0;
  z-index: var(--z-dropdown);
  display: grid;
  gap: var(--s-2);
  width: 360px;
  max-width: 90vw;
  padding: var(--s-4);
  background: var(--surface-2);
  border: 1px solid var(--border-2);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-2);
}

.notif__head {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: start;
  gap: var(--s-2);
}

.notif__title {
  margin: 0;
  color: var(--text-1);
  font-size: var(--t-md);
  font-weight: 700;
}

.notif__summary {
  grid-column: 1;
  margin: 0;
  color: var(--text-3);
  font-size: var(--t-xs);
}

.notif__close {
  grid-column: 2;
  grid-row: span 2;
  width: var(--control-h-sm);
  min-height: var(--control-h-sm);
  padding: 0;
  color: var(--text-2);
  font-size: var(--t-lg);
}

.notif__note {
  margin: 0;
  padding: var(--s-2);
  color: var(--text-1);
  background: var(--surface-3);
  border-left: 3px solid var(--warning);
  border-radius: var(--r-sm);
  font-size: var(--t-xs);
}

.notif__list {
  display: grid;
  gap: var(--s-3);
  margin: 0;
  padding: 0;
  list-style: none;
}

.notif__row {
  display: grid;
  gap: var(--s-1);
  padding-bottom: var(--s-3);
  border-bottom: 1px solid var(--border-1);
}

.notif__row:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.notif__row-title {
  margin: 0;
  color: var(--text-1);
  font-size: var(--t-sm);
}

.notif__row-detail {
  margin: 0;
  color: var(--text-2);
  font-size: var(--t-xs);
}

.notif__row-meta {
  display: flex;
  gap: var(--s-2);
  margin: 0;
  color: var(--text-3);
  font-size: var(--t-xs);
}

.notif__row-state {
  color: var(--accent);
}

.notif__row-actions {
  display: flex;
  gap: var(--s-2);
}

.notif__foot {
  display: flex;
  justify-content: flex-end;
  gap: var(--s-2);
}
</style>


