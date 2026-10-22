<script setup>
import { computed, ref, watch } from 'vue'
import { WORKSPACE_MODULES } from '../lib/workspace-modules'
import { UiButton } from './ui'

const props = defineProps({ items: { type: Array, default: () => [] }, activeScreen: { type: String, default: '' } })
const emit = defineEmits(['navigate'])
const groups = computed(() => [
  { id: 'overview', title: '', items: props.items.filter(item => item.id === 'overview') },
  ...WORKSPACE_MODULES.map(module => ({ ...module, items: props.items.filter(item => module.screens.includes(item.id)) })),
])
const businessIds = ['overview', ...WORKSPACE_MODULES.flatMap(module => module.screens)]
const systemItems = computed(() => props.items.filter(item => !businessIds.includes(item.id)))
const settingsOpen = ref(false)
watch(() => props.activeScreen, screen => { if (systemItems.value.some(item => item.id === screen)) settingsOpen.value = true }, { immediate: true })
</script>

<template>
  <div class="workspace-navigation">
    <section v-for="group in groups" :key="group.id" class="navigation-module" :data-module="group.id">
      <h2 v-if="group.title" class="navigation-module__title">{{ group.title }}</h2>
      <UiButton v-for="item in group.items" :key="item.id" variant="ghost" :class="['nav-item', { active: activeScreen === item.id }]"
        :data-testid="`nav-${item.id}`" :aria-current="activeScreen === item.id ? 'page' : undefined" :aria-label="item.label" @click="emit('navigate', item.id)">
        <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><path :d="item.icon" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" /></svg>
        <span class="nav-label">{{ item.label }}</span>
      </UiButton>
    </section>
    <section v-if="systemItems.length" class="navigation-module navigation-module--system">
      <UiButton variant="ghost" class="navigation-settings-toggle" data-testid="nav-settings-toggle" :aria-expanded="settingsOpen" aria-controls="system-navigation" @click="settingsOpen = !settingsOpen">账号与系统管理 <span aria-hidden="true">{{ settingsOpen ? '⌃' : '⌄' }}</span></UiButton>
      <div v-if="settingsOpen" id="system-navigation">
        <UiButton v-for="item in systemItems" :key="item.id" variant="ghost" :class="['nav-item', { active: activeScreen === item.id }]"
          :data-testid="`nav-${item.id}`" :aria-current="activeScreen === item.id ? 'page' : undefined" :aria-label="item.label" @click="emit('navigate', item.id)">
          <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><path :d="item.icon" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" /></svg>
          <span class="nav-label">{{ item.label }}</span>
        </UiButton>
      </div>
    </section>
  </div>
</template>

<style scoped>
.nav-item { justify-content: flex-start; width: 100%; }
.nav-item :deep(.ui-button__label) { display: contents; }
.nav-icon { flex: none; }
@media (max-width: 760px) {
  .nav-item { width: auto; }
}
</style>
