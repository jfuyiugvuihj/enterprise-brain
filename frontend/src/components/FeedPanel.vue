<script setup>
/**
 * R136 · 「喂料」屏：文档 + 数据，一屏两标签
 *
 * 计划书 §四 把「上传制度文档」与「上传经营数据」并成一屏 —— 员工做的是同一件事：把料
 * 喂进去。这一枚组件只做两件事，两块面板一字节未改、接口与交互仍归它们自己：
 *   1. 画标签条（复用 ui/UiTabs.vue，不造第二套标签原语）；
 *   2. 把地址里的标签态落成面板。
 *
 * 三条理由写在这里，因为它们只能有一个出处：
 *  - 标签态住在地址（?tab=data）里，不住在组件的 ref 里。这一屏没进 keep-alive 名单
 *    （cachedScreens 只有问一句那一枚），切回来是重新挂载的，态写在组件里就会丢；写在
 *    地址里，刷新与转给同事都还在，老地址 /docs、/data 也才有东西可以重定向过去。
 *  - 标签清单取自 src/router/feed-tabs.js 那张表：面板、标签文案、要不要 user-role 三列
 *    都在那张表上。这里不抄第二份，也不写 if (id 等于 'docs')，加第三枚标签不用改这枚文件。
 *  - 屏名「喂料」由路由 meta.title 一个人说（顶栏与侧栏同源）。所以这一屏【不】画页级
 *    标题：画了就是 §71 点名的「同一屏两个名字」，还是最难发现的那种 —— 两处各自都好看，
 *    改一处忘一处。标签文案「文档 / 数据」说的是这一格装的内容，不是屏名，不算第二处。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import UiTabs from './ui/UiTabs.vue'
import { FEED_SCREEN, FEED_TAB_PARAM, FEED_TABS, resolveFeedTab } from '../router/feed-tabs.js'

const props = defineProps({
  // 「喂料」屏里只有 needsUserRole 那一列要它（今天就是文档面板的管理员开关）。绑给谁由
  // feed-tabs.js 那张表决定，不在这枚组件里点名某一块面板。
  userRole: { type: String, default: 'staff' },
})

const emit = defineEmits(['ask'])

// 深链用例是裸 renderToString(h(组件))，不带路由上下文，所以这两枚取值都要容空。
// 容空不会把「接不上」伪装成「接上了」：接不上时渲染的就是默认那一枚标签，仍是真内容。
const route = useRoute()
const router = useRouter()

/** 当前标签：地址里那一格认不出就回默认那一枚，而不是画一片空白的工作台。 */
const activeTab = computed(() => resolveFeedTab(route?.query?.[FEED_TAB_PARAM]))

/** 标签条的无障碍名跟着 meta.title 走：屏名与它只有一份字，切标签也不换来源。 */
const screenTitle = computed(() => route?.meta?.title || '')

const panelProps = computed(() => (activeTab.value.needsUserRole ? { userRole: props.userRole } : {}))

/**
 * 切标签走 replace 而不是 push：标签是同一屏里的视图，不该在后退键上堆出「喂料→喂料→喂料」。
 * query 整体带走，只改标签那一格，面板自己认得的那些过滤参数不许被抹掉。
 */
function selectTab(id) {
  const next = resolveFeedTab(id)
  if (next.id === activeTab.value.id) return
  router?.replace({ name: FEED_SCREEN, query: { ...route?.query, [FEED_TAB_PARAM]: next.id } })
}

/**
 * 数据面板的「就这个问题去对话」发的是 { query, filename } 一整个对象。原样转发：
 * 这枚组件拆一次字段重组一次，就多一处可能与 App.vue 那份「切屏之后才派发」的账错位。
 */
function forwardAsk(payload) {
  emit('ask', payload)
}
</script>

<template>
  <div class="feed-panel" data-testid="feed-panel">
    <UiTabs :model-value="activeTab.id" :items="FEED_TABS" :aria-label="screenTitle" @change="selectTab">
      <template v-for="tab in FEED_TABS" :key="tab.id" #[`panel-${tab.id}`]="{ active }">
        <component :is="tab.component" v-if="active" v-bind="panelProps" @ask="forwardAsk" />
      </template>
    </UiTabs>
  </div>
</template>

<style scoped>
/* 标签条与面板都不许把工作台撑出横向滚动：UiTabs 自己只管 min-width，这一格管这一屏。 */
.feed-panel {
  min-width: 0;
}
</style>
