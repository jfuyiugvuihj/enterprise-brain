<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { UiButton } from './ui'
import { WORKSPACE_MODULES } from '../lib/workspace-modules'

const route = useRoute()
const router = useRouter()
const guides = {
  overview: { title: '从资料开始，让每次分析有据可循', description: '准备资料，在智能助手中查询或分析，再把结果保存为报告。异常提醒与待办事项可以随时接入处理。', next: 'feed', action: '上传企业资料' },
  feed: { title: '准备本次要使用的资料', description: '知识库用于查制度和原文，经营数据用于统计和分析。上传后先确认处理结果，再选择资料开始任务。', next: 'chat', action: '前往智能助手' },
  chat: { title: '提出问题，查看结果与依据', description: '选择经营数据或说明要查询的资料；核对回答中的来源和计算范围，需要时继续追问或生成报告。', next: 'artifacts', action: '查看已生成成果' },
  insights: { title: '发现异常，继续核查与处理', description: '查看异常记录和触发条件，确认、转派或关闭提醒；需要进一步核查时，结合相关数据继续分析。', next: 'chat', action: '前往智能助手' },
  approval: { title: '处理需要你确认的操作', description: '查看待确认事项的内容与影响，批准或拒绝后返回分析查看结果。这里的操作确认不等同于企业业务审批。', next: 'chat', action: '返回智能助手' },
  artifacts: { title: '找回你的报告与图表', description: '查看和下载有权限访问的成果，核对生成时间与资料依据；打开关联会话可以回到原分析。', next: 'chat', action: '开始新的分析' },
}
const guide = computed(() => guides[route.name])
const currentModule = computed(() => WORKSPACE_MODULES.find(module => module.screens.includes(route.name)))
const stages = [
  { names: ['feed'], name: 'feed', label: '准备资料' },
  { names: ['chat', 'insights', 'approval'], name: 'chat', label: '提问与分析' },
  { names: ['artifacts'], name: 'artifacts', label: '查看成果' },
]
</script>

<template>
  <section v-if="guide && route.name !== 'chat'" class="workspace-guide" aria-label="页面用途与下一步">
    <div class="workspace-guide__copy">
      <p v-if="currentModule" class="workspace-guide__module">{{ currentModule.title }}</p>
      <h2>{{ guide.title }}</h2>
      <p>{{ guide.description }}</p>
      <nav class="workspace-journey" aria-label="使用流程">
        <template v-for="(stage, index) in stages" :key="stage.name">
          <span v-if="index" class="workspace-journey__arrow" aria-hidden="true">→</span>
          <UiButton variant="ghost" size="sm" :class="{ 'is-current': stage.names.includes(route.name) }" :aria-current="stage.names.includes(route.name) ? 'step' : undefined" @click="router.push({ name: stage.name })">{{ stage.label }}</UiButton>
        </template>
      </nav>
    </div>
    <UiButton variant="secondary" size="sm" @click="router.push({ name: guide.next })">{{ guide.action }} <span aria-hidden="true">→</span></UiButton>
  </section>
  <section v-if="route.name === 'overview'" class="workspace-module-grid" aria-label="业务模块" data-testid="workspace-modules">
    <article v-for="module in WORKSPACE_MODULES" :key="module.id" class="workspace-module-card">
      <h3>{{ module.title }}</h3><p>{{ module.description }}</p><small>{{ module.flow }}</small>
      <UiButton variant="secondary" size="sm" :data-testid="`module-start-${module.id}`" @click="router.push({ name: module.start })">{{ module.action }} →</UiButton>
    </article>
  </section>
</template>
