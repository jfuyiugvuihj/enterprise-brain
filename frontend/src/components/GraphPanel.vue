<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../lib/api'

const form = ref({
  source_entity: '差旅费',
  relation: '属于',
  target: '费用科目',
  source: '差旅费报销制度.pdf',
})
const relations = ref([])
const loading = ref(false)
const error = ref('')

async function loadRelations() {
  const response = await api.get('/knowledge-graph/relations')
  relations.value = response.data.relations || []
}

async function saveRelation() {
  loading.value = true
  error.value = ''
  try {
    await api.post('/knowledge-graph/relations', form.value)
    await loadRelations()
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '关系保存失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadRelations)
</script>

<template>
  <div class="panel-shell" data-testid="graph-panel">
    <header class="panel-head">
      <div>
        <div class="eyebrow">Knowledge Graph</div>
        <h3>知识图谱</h3>
        <p>把制度、指标、部门和责任关系串联起来。</p>
      </div>
    </header>

    <div class="panel-grid">
      <section class="panel-card">
        <div class="section-head"><h4>新增关系</h4></div>
        <div class="form-grid">
          <label><span>主体</span><input v-model="form.source_entity" /></label>
          <label><span>关系</span><input v-model="form.relation" /></label>
          <label><span>客体</span><input v-model="form.target" /></label>
          <label><span>来源</span><input v-model="form.source" /></label>
        </div>
        <div class="actions">
          <button class="primary-btn" data-testid="save-relation" :disabled="loading" @click="saveRelation">
            {{ loading ? '保存中' : '保存关系' }}
          </button>
          <span v-if="error" class="inline-error">{{ error }}</span>
        </div>
      </section>

      <section class="panel-card">
        <div class="section-head"><h4>关系列表</h4></div>
        <div v-if="!relations.length" class="empty-state">暂无关系，先添加一条</div>
        <div v-else class="relation-list">
          <article v-for="item in relations" :key="item.relation_id" class="relation-item">
            <div class="relation-main">
              <strong>{{ item.source_entity }}</strong>
              <span>{{ item.relation }}</span>
              <strong>{{ item.target }}</strong>
            </div>
            <div class="relation-meta">
              <span>{{ item.source }}</span>
              <span :class="['state', item.status]">{{ item.status }}</span>
            </div>
          </article>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.panel-grid {
  display: grid;
  grid-template-columns: .9fr 1.1fr;
  gap: 16px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

label {
  display: grid;
  gap: 6px;
  color: var(--muted);
  font-size: 12px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}

.relation-list {
  display: grid;
  gap: 10px;
}

.relation-item {
  padding: 13px;
}

.relation-main,
.relation-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.relation-main {
  color: var(--cyan);
  font-size: 12px;
}

.relation-main span {
  color: var(--muted);
}

.relation-meta {
  justify-content: space-between;
  margin-top: 8px;
  color: var(--muted);
  font-size: 10px;
}

@media (max-width: 760px) {
  .panel-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
