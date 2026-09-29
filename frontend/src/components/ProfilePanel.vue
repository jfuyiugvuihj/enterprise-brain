<!--
  R494 · 「我的账号」：员工自查那一屏——我是谁、归哪个部门、能读到第几级

  病（docs/handoff/2026-09-26-v1-frontend-gap-list.md 的 G10 记「半」，点名的没脸清单里就有 /profile）：
  这一屏今天一张脸都没有。`rg -n "profile" frontend/src` 的命中全在 DataPanel 的「数据画像」，
  与 GET /api/v1/profile 无关。于是三句最基本的话在界面上无处可查，而后端本来就算得出来：
  角色与部门取自 users 那一行，档位取自 app/common/rbac.py 的 clearance_for（R494 才补进回执）。

  这一枚壳的边界（判据②③④，钉在 src/components/__tests__/r494-profile-screen.test.js）：
    · 四格逐格来自后端回包：用户名 / 角色 / 部门（只读）/ 可读档位。屏上不许多长一枚演示值，
      档位缺席时也不许糊一枚 1 上去——那一句写的是「这台服务器没把档位告诉我」。
    · 它不判脸：判码、归脸、句子全在 src/lib/profile.js 一处，与 /admin 走 lib/users.js 同一手法。
    · 屏名只写一遍，但这一屏必须自己说：r412 那枚遍历钉要求每一屏「页内报一句主标题，或者由某张派生入口表替它说」，
      两样都没的屏当场红。/admin 与 /traces 靠的是管理员那截导航，而这一屏今天 primary:false、也不在那截里
      ⇒ 它只剩「自报」这一条路：页内那句 <h3> 逐字等于路由表的 meta.title，且全屏只许有这一处主标题。
    · 它不发部门那一发：挪部门归管理员走 PUT /api/v1/users/department（需要 users:manage），
      本屏只把这句话写给人看；这一屏自己的请求腿只有 GET /profile 与 PUT /profile 两条。
    · 写不发 department：请求体一律出自 profileWriteBody，只出 position 与 preferences 两枚键，
      多带那一枚（连空串一起）整发就是 403，所以这条不靠自觉，靠钉。
-->
<script>
export default { name: 'ProfilePanel' }
</script>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import {
  DEPARTMENT_READ_ONLY_NOTE,
  PROFILE_FACE_LOADING,
  PROFILE_FACE_READY,
  PROFILE_FACE_SAVED,
  PROFILE_LOADING_TEXT,
  PROFILE_SAVED_NOTE,
  loadProfile,
  profileBlankView,
  profileCells,
  profileFaceView,
  profileWriteBody,
  submitProfile,
} from '../lib/profile'
import { UiButton, UiErrorState, UiField, UiLoadingState } from './ui'

/**
 * 取数闸门（沿用 AdminPanel 那一枚手法，不发明第二套）：每一次读领一号，
 * 重新读取与离开这一屏都作废旧号——迟到的那一发既不上屏，也不覆盖新读数。
 */
let profileToken = 0

const view = ref(profileBlankView())
const writeView = ref(null)
const busy = ref(false)

const loading = computed(() => view.value.face === PROFILE_FACE_LOADING)
const ready = computed(() => view.value.face === PROFILE_FACE_READY)
// 失败脸与就绪脸互斥：屏上不可能同时出现「没读到」与半截画像。
const readFailure = computed(() => (!loading.value && !ready.value ? profileFaceView(view.value) : null))
const cells = computed(() => profileCells(ready.value ? view.value.row : {}))
// 写腿的脸永远不挂「重试」：重放同一发写就是再来一次副作用，要改就改表单再提交。
const writeFailure = computed(() => (writeView.value && writeView.value.face !== PROFILE_FACE_SAVED
  ? profileFaceView(writeView.value)
  : null))
const savedNote = computed(() => (writeView.value && writeView.value.face === PROFILE_FACE_SAVED ? PROFILE_SAVED_NOTE : ''))

/** 可改的那两格（职位 / 偏好）。部门那一格在这里没有容身之处：它是只读的一格。 */
const form = reactive({ position: '', preferences: '' })

/** 表单起点只跟后端回包：每读回来一次就同步一次，屏上不许留一份比后端新的「我以为的值」。 */
function syncForm(row) {
  const read = profileCells(row)
  form.position = read.position
  form.preferences = read.preferences
}

async function refresh() {
  const mine = ++profileToken
  const next = await loadProfile()
  if (mine !== profileToken) return
  view.value = next
  if (next.face === PROFILE_FACE_READY) syncForm(next.row)
}

async function loadIntoView() {
  view.value = profileBlankView(PROFILE_FACE_LOADING)
  await refresh()
}

/** 🔴 不乐观：成没成都重读一次，四格永远只可能来自后端回包。 */
async function saveProfile() {
  if (busy.value) return
  busy.value = true
  const out = await submitProfile(profileWriteBody({ position: form.position, preferences: form.preferences }))
  writeView.value = out
  await refresh()
  busy.value = false
}

onMounted(loadIntoView)
onUnmounted(() => { profileToken += 1 })
</script>

<template>
  <div class="panel-shell" data-testid="profile-panel">
    <header class="panel-head">
      <div>
        <span class="eyebrow">这个账号在这台服务器上的样子</span>
        <h3>我的账号</h3>
        <p>
          下面四格读的都是服务端这一发的回执：你是谁、归哪个部门、能读到第几级文档，
          以及你自己动手改得动的那两格。这里不摆演示值，也不替后端猜数。
        </p>
      </div>
      <UiButton label="重新读取" variant="secondary" size="sm" :disabled="busy" @click="loadIntoView" />
    </header>

    <UiLoadingState v-if="loading" :label="PROFILE_LOADING_TEXT" :rows="3" />

    <UiErrorState
      v-else-if="readFailure"
      :title="readFailure.title"
      :description="readFailure.description"
      :code-label="readFailure.codeLabel"
      :retryable="readFailure.retryable"
      :busy="busy"
      @retry="loadIntoView"
    />

    <template v-else>
      <dl class="profile-cells" data-testid="profile-cells">
        <div class="profile-cell" data-testid="cell-username">
          <dt>用户名</dt>
          <dd class="profile-value" data-testid="cell-username-value">{{ cells.username }}</dd>
        </div>
        <div class="profile-cell" data-testid="cell-role">
          <dt>角色</dt>
          <dd class="profile-value" data-testid="cell-role-value">{{ cells.roleText }}</dd>
        </div>
        <div class="profile-cell" data-testid="cell-department">
          <dt>部门（只读）</dt>
          <dd class="profile-value">{{ cells.department }}</dd>
          <dd class="profile-note">{{ DEPARTMENT_READ_ONLY_NOTE }}</dd>
        </div>
        <div class="profile-cell" data-testid="cell-clearance">
          <dt>可读档位</dt>
          <dd class="profile-value" data-testid="cell-clearance-value">{{ cells.clearance.text }}</dd>
          <dd v-if="!cells.clearance.known" class="profile-note">{{ cells.clearance.note }}</dd>
        </div>
      </dl>

      <section class="profile-edit" data-testid="profile-edit">
        <h4>你自己改得动的两格</h4>
        <UiField v-model="form.position" label="职位" hint="这个称谓会拼进对话的画像块，后端只认这一格与你下面的偏好" />
        <UiField v-model="form.preferences" label="偏好" multiline :rows="3" hint="一行一条，空行不保存" />
        <div class="profile-actions">
          <UiButton label="保存" variant="primary" :loading="busy" :disabled="loading" @click="saveProfile" />
          <p v-if="savedNote" class="profile-receipt" data-testid="profile-saved">{{ savedNote }}</p>
        </div>
        <div v-if="writeFailure" class="profile-write-face" data-testid="profile-write-face">
          <UiErrorState
            :title="writeFailure.title"
            :description="writeFailure.description"
            :code-label="writeFailure.codeLabel"
            :retryable="false"
            dense
          />
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.profile-cells {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 0;
}

.profile-cell {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border: 1px solid var(--border-1);
  border-radius: var(--radius-md);
  background: var(--surface-2);
}

.profile-cell dt {
  color: var(--text-3);
  font-size: var(--t-xs);
}

.profile-value {
  margin: 0;
  color: var(--text-1);
  font-size: var(--t-lg);
}

.profile-note {
  margin: 0;
  color: var(--text-2);
  font-size: var(--t-xs);
  line-height: 1.6;
}

.profile-edit {
  display: grid;
  gap: 12px;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--border-2);
}

.profile-edit h4 {
  margin: 0;
  color: var(--text-1);
  font-size: var(--t-md);
}

.profile-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.profile-receipt {
  margin: 0;
  color: var(--text-2);
  font-size: var(--t-sm);
}
</style>
