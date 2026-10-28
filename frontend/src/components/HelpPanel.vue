<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import MarkdownIt from 'markdown-it'

const route = useRoute()
const menuOpen = ref(false)
const pages = __USER_GUIDE_PAGES__
const sections = [
  { title: '开始使用', items: [
    { title: '手册首页', slug: '' },
    { title: '登录与权限', slug: 'getting-started' },
    { title: '认识工作台', slug: 'workspace' },
  ] },
  { title: '资料与分析', items: [
    { title: '从哪里开始', slug: 'analysis' },
    { title: '上传和查询文档', slug: 'analysis/documents' },
    { title: '上传和分析经营表', slug: 'analysis/datasets' },
    { title: '在智能助手提问', slug: 'analysis/assistant' },
  ] },
  { title: '异常与待办', items: [
    { title: '从哪里开始', slug: 'tasks' },
    { title: '查看和处理异常', slug: 'tasks/alerts' },
    { title: '处理待确认操作', slug: 'tasks/approvals' },
    { title: '查看和清理通知', slug: 'tasks/notifications' },
  ] },
  { title: '成果交付', items: [
    { title: '从哪里开始', slug: 'delivery' },
    { title: '打开和下载报告', slug: 'delivery/artifacts' },
  ] },
  { title: '账号与系统管理', items: [
    { title: '从哪里开始', slug: 'administration' },
    { title: '查看和修改我的账号', slug: 'administration/profile' },
    { title: '管理账号与角色', slug: 'administration/accounts' },
    { title: '查看运行与审计记录', slug: 'administration/diagnostics' },
    { title: '查看资料关系', slug: 'administration/graph' },
  ] },
  { title: '遇到问题', items: [{ title: '常见问题', slug: 'troubleshooting' }] },
]

const slug = computed(() => {
  const value = route.params.page
  return Array.isArray(value) ? value.join('/') : String(value || '')
})
const source = computed(() => {
  const key = slug.value ? `${slug.value}.md` : 'README.md'
  if (key in pages) return key
  const index = slug.value ? `${slug.value}/README.md` : 'README.md'
  return index in pages ? index : null
})
const currentSection = computed(() => sections.find(section => section.items.some(item => item.slug === slug.value)))
const currentItem = computed(() => currentSection.value?.items.find(item => item.slug === slug.value))
const guideHref = slug => slug ? `/help/${slug}` : '/help'

const markdown = new MarkdownIt({ html: false, linkify: true, typographer: true })
markdown.renderer.rules.link_open = (tokens, index, options, env, self) => {
  const token = tokens[index]
  const href = token.attrGet('href') || ''
  if (/\.md(?:#.*)?$/i.test(href)) {
    const resolved = new URL(href, `https://guide.local/${env.source}`)
    const target = decodeURIComponent(resolved.pathname.slice(1))
    const targetSlug = target.replace(/(?:\/)?README\.md$/i, '').replace(/\.md$/i, '')
    if (target in pages) token.attrSet('href', `${guideHref(targetSlug)}${resolved.hash}`)
  }
  return self.renderToken(tokens, index, options)
}
const content = computed(() => source.value ? markdown.render(pages[source.value], { source: source.value }) : '')
watch(slug, () => { menuOpen.value = false })
</script>

<template>
  <div class="help-page">
    <header class="help-header">
      <a class="help-brand" href="/help" aria-label="企业智脑操作手册首页"><span class="help-brand__mark">知</span><span>企业智脑 <small>使用帮助</small></span></a>
      <a class="help-back" href="/">返回企业智脑 <span aria-hidden="true">↗</span></a>
    </header>
    <div class="help-layout">
      <button class="help-menu-toggle" type="button" :aria-expanded="menuOpen" aria-controls="help-navigation" @click="menuOpen = !menuOpen">{{ menuOpen ? '收起目录' : '浏览目录' }} <span aria-hidden="true">{{ menuOpen ? '−' : '+' }}</span></button>
      <nav id="help-navigation" class="help-navigation" :class="{ 'help-navigation--open': menuOpen }" aria-label="操作手册目录">
        <div v-for="section in sections" :key="section.title" class="help-nav-section">
          <h2>{{ section.title }}</h2>
          <a v-for="item in section.items" :key="item.slug" :href="guideHref(item.slug)" :aria-current="slug === item.slug ? 'page' : undefined" @click="menuOpen = false">{{ item.title }}</a>
        </div>
      </nav>
      <main class="help-main" id="main-content">
        <div v-if="source" class="help-article-wrap">
          <p class="help-breadcrumb"><a href="/help">使用帮助</a><span v-if="currentSection"> / {{ currentSection.title }}</span><span v-if="currentItem"> / {{ currentItem.title }}</span></p>
          <article class="help-article" v-html="content"></article>
          <div class="help-article-footer"><a href="/help">返回手册目录</a><a href="/">返回工作台</a></div>
        </div>
        <div v-else class="help-missing"><h1>没有找到这篇指南</h1><p>请从目录选择要查看的操作。</p><a href="/help">返回手册目录</a></div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.help-page { min-height: 100dvh; background: #f5f8fc; color: #172942; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; }
.help-header { height: 72px; padding: 0 max(24px, calc((100vw - 1280px) / 2)); display: flex; align-items: center; justify-content: space-between; gap: 16px; background: #fff; border-bottom: 1px solid #dce6f2; }
.help-brand { display: inline-flex; align-items: center; gap: 12px; color: #172942; font-size: 19px; font-weight: 700; text-decoration: none; white-space: nowrap; }
.help-brand small { margin-left: 8px; color: #647993; font-size: 13px; font-weight: 500; }
.help-brand__mark { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 10px; background: #255eda; color: #fff; font-size: 17px; }
.help-back { color: #2458c7; font-size: 14px; font-weight: 600; text-decoration: none; white-space: nowrap; }
.help-layout { width: min(1280px, 100%); min-height: calc(100dvh - 72px); margin: 0 auto; display: grid; grid-template-columns: 246px minmax(0, 1fr); }
.help-navigation { padding: 28px 16px 48px 24px; border-right: 1px solid #dce6f2; align-self: start; position: sticky; top: 0; max-height: 100dvh; overflow-y: auto; }
.help-nav-section { margin-bottom: 22px; }
.help-nav-section h2 { margin: 0 0 7px; padding: 0 12px; color: #60758d; font-size: 12px; font-weight: 700; letter-spacing: .04em; }
.help-nav-section a { display: block; padding: 9px 12px; border-radius: 8px; color: #314660; font-size: 14px; line-height: 1.45; text-decoration: none; }
.help-nav-section a:hover, .help-nav-section a[aria-current="page"] { background: #e5edfd; color: #1e52bd; }
.help-nav-section a[aria-current="page"] { font-weight: 700; box-shadow: inset 3px 0 #255eda; }
.help-main { min-width: 0; padding: 42px clamp(24px, 5vw, 76px) 80px; }
.help-article-wrap { max-width: 840px; }
.help-breadcrumb { margin: 0 0 28px; color: #60758d; font-size: 13px; }
.help-breadcrumb a, .help-article-footer a, .help-missing a { color: #2458c7; text-decoration: none; }
.help-article { font-size: 16px; line-height: 1.85; overflow-wrap: anywhere; }
.help-article :deep(h1) { margin: 0 0 22px; color: #112b4d; font-size: clamp(28px, 3vw, 38px); line-height: 1.25; }
.help-article :deep(h2) { margin: 36px 0 12px; padding-top: 20px; border-top: 1px solid #dce6f2; color: #173555; font-size: 22px; line-height: 1.35; }
.help-article :deep(h3) { margin: 24px 0 10px; font-size: 18px; }
.help-article :deep(p), .help-article :deep(ul), .help-article :deep(ol) { margin: 12px 0; }
.help-article :deep(li) { margin: 5px 0; }
.help-article :deep(a) { color: #2458c7; text-underline-offset: 3px; }
.help-article :deep(table) { display: block; width: max-content; max-width: 100%; overflow-x: auto; border-collapse: collapse; font-size: 14px; }
.help-article :deep(th), .help-article :deep(td) { padding: 10px 12px; border: 1px solid #dce6f2; text-align: left; vertical-align: top; }
.help-article :deep(th) { background: #eaf1fb; }
.help-article :deep(code) { padding: 2px 5px; border-radius: 4px; background: #eaf1fb; font-size: .9em; }
.help-article-footer { display: flex; justify-content: space-between; gap: 16px; margin-top: 50px; padding-top: 20px; border-top: 1px solid #dce6f2; font-size: 14px; }
.help-menu-toggle { display: none; }
.help-page a:focus-visible, .help-page button:focus-visible { outline: 2px solid #255eda; outline-offset: 3px; }
@media (max-width: 900px) {
  .help-header { height: 60px; padding: 0 16px; }
  .help-brand { gap: 8px; font-size: 16px; }
  .help-brand small { margin-left: 3px; font-size: 12px; }
  .help-brand__mark { width: 30px; height: 30px; font-size: 14px; }
  .help-back { font-size: 12px; }
  .help-layout { display: block; min-height: calc(100dvh - 60px); }
  .help-menu-toggle { width: calc(100% - 32px); min-height: 44px; margin: 16px 16px 0; padding: 0 14px; display: flex; align-items: center; justify-content: space-between; border: 1px solid #dce6f2; border-radius: 8px; background: #fff; color: #173555; font: inherit; font-weight: 600; }
  .help-navigation { display: none; position: static; max-height: 55dvh; margin: 8px 16px 0; padding: 16px 8px; border: 1px solid #dce6f2; border-radius: 8px; background: #fff; }
  .help-navigation--open { display: block; }
  .help-main { padding: 22px 18px 60px; }
  .help-breadcrumb { margin-bottom: 20px; }
  .help-article { font-size: 15px; line-height: 1.75; }
  .help-article :deep(h2) { font-size: 19px; }
}
</style>
