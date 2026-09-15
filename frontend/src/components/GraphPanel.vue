<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../lib/api'
import { errorDetail } from '../lib/http'

// 表单不再预填示例关系：写死的「差旅费 / 属于 / 费用科目 / 差旅费报销制度.pdf」
// 会和真数据混在同一屏里，老板分不出哪条是库里来的。
function emptyForm() {
  return { source_entity: '', relation: '', target: '', source: '' }
}

const form = ref(emptyForm())
const relations = ref([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const loadError = ref('')

// 关系列表的唯一来源是 GET /api/v1/knowledge-graph/relations；后端按 Principal
// 收窄部门与密级（app/api/v1/intelligence.py:133）。取不到就摆失败态，
// 绝不回落到任何常量——失败态与空态必须是两件事。
async function loadRelations() {
  loading.value = true
  loadError.value = ''
  try {
    const response = await api.get('/knowledge-graph/relations')
    const list = response.data?.relations
    if (!Array.isArray(list)) {
      loadError.value = '关系列表返回的数据结构不对，未能加载。'
      relations.value = []
      return
    }
    relations.value = list
  } catch (err) {
    loadError.value = errorDetail(err, '关系列表加载失败')
    relations.value = []
  } finally {
    loading.value = false
  }
}

async function saveRelation() {
  saving.value = true
  error.value = ''
  try {
    await api.post('/knowledge-graph/relations', form.value)
    form.value = emptyForm()
    await loadRelations()
  } catch (err) {
    error.value = errorDetail(err, '关系保存失败')
  } finally {
    saving.value = false
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
          <button class="primary-btn" data-testid="save-relation" :disabled="saving" @click="saveRelation">
            {{ saving ? '保存中' : '保存关系' }}
          </button>
          <span v-if="error" class="inline-error">{{ error }}</span>
        </div>
      </section>

      <section class="panel-card">
        <div class="section-head">
          <h4>关系列表</h4>
          <button class="ghost-btn" type="button" :disabled="loading" @click="loadRelations">
            {{ loading ? '加载中' : '刷新' }}
          </button>
        </div>
        <div v-if="loadError" class="panel-state error" data-testid="graph-load-error">
          {{ loadError }}
          <button class="ghost-btn" type="button" @click="loadRelations">重新加载</button>
        </div>
        <div v-else-if="!relations.length" class="empty-state" data-testid="graph-empty">知识库里还没有已登记的关系</div>
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
