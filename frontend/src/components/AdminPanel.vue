<!--
  R316 · 「账号与角色」屏壳：只读服务端名册，一屏一件事

  这一屏接的是 app/api/v1/auth.py:90-95 那一枚 GET /users（回 {"users": auth.list_users()}）。
  同一个文件里的 :98 POST /users 与 :113 DELETE /users/{user_id} 一都不接：开通与停用账号是
  另一枚单，边界由总控裁定，所以这里连一个写控件都没有——摆一枚点不动的按钮就是 R32 明令
  禁的假控件，摆一枚真能点的就越了本单的界。

  四张读数的脸 + 一张进行中的脸，判据全在 lib/users.js，本文件只做编排与渲染：
    403 permission_denied -> 「这一屏不向你开放」，句子出自 lib/errcodes.js 那本字典
    401 authentication_required -> 登录失效，另一句
    503 / storage_unavailable -> 存储还没就绪，另一句
    200 但列表读不出行 -> 形状不对，另一句
    200 且真零行 -> 空态，「这一发回包里没有行」
  五张两两不等，任何一张都不许塌成「没有用户」：把 403 画成空列表，等于把「这个账号不在
  名册的管理范围里」说成「这家公司没有账号」，那是比报错更坏的产物（R1(c) 同族）。

  零统计量（判据③）：这里不数「共 N 人」，不算「管理员占比」，也不按行数得任何结论。
  后端没给过的列（最近登录、状态、活跃度）同样不画——列只认 USER_BACKEND_COLUMNS 那五枚键，
  它与源码对账的钉在 src/lib/__tests__/r316-users-contract.test.js。
-->
<script>
export default { name: 'AdminPanel' }
</script>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  USER_COLUMNS,
  USERS_FACE_EMPTY,
  USERS_FACE_LOADING,
  USERS_FACE_READY,
  USERS_LOADING_TEXT,
  loadUsers,
  usersBlankView,
  usersFailureFace,
} from '../lib/users'
import { UiButton, UiEmptyState, UiErrorState, UiLoadingState, UiTable } from './ui'

/**
 * token 闸门：沿用 R314 / R341 那枚手法，不发明第二套。
 * 每一次取数领一枚号；重新加载与离开这一屏都把旧号作废。迟到的那一发既不上屏，
 * 也不会把上一份名册挂在新读数的位置上——那正是「切屏离开再回来还看着上一份」的成因。
 */
let usersToken = 0

const view = ref(usersBlankView())

const loading = computed(() => view.value.face === USERS_FACE_LOADING)
const failure = computed(() => (usersFailureFace(view.value) ? view.value : null))
const isEmpty = computed(() => view.value.face === USERS_FACE_EMPTY)
// 只有 ready 那张脸才把行交给表格：失败与空态一律是空数组，屏上因此不可能同时出现
// 「一句没读到」与「半截名册」。
const rows = computed(() => (view.value.face === USERS_FACE_READY ? view.value.rows : []))

async function loadRoster() {
  const mine = ++usersToken
  view.value = usersBlankView(USERS_FACE_LOADING)
  const next = await loadUsers()
  if (mine !== usersToken) return
  view.value = next
}

function invalidateRoster() {
  usersToken += 1
}

onMounted(loadRoster)
onUnmounted(invalidateRoster)
</script>

<template>
  <div class="panel-shell" data-testid="admin-panel" :data-face="view.face">
    <header class="panel-head">
      <div>
        <span class="eyebrow">服务端账号名册</span>
        <p>
          这一屏列的是 GET /users 真回包里的行：谁在名册上、各自被登记成什么角色。
          这里只读不写——开通账号与停用账号不在这一屏，屏上也不摆还没接上后端的那些控件。
        </p>
      </div>
      <div>
        <UiButton
          size="sm"
          variant="ghost"
          :loading="loading"
          label="重新加载"
          data-testid="reload-users"
          @click="loadRoster"
        />
      </div>
    </header>

    <section class="panel-card" data-testid="admin-users-card" :data-face="view.face">
      <UiLoadingState v-if="loading" :label="USERS_LOADING_TEXT" dense />

      <!-- 这一格的名字挂在包裹层上，不挤掉原语自己的 data-testid：数「屏上有没有一张失败脸」
           与数「失败脸用的是不是 UiErrorState」是两件事，两枚钉子各量各的。 -->
      <div v-else-if="failure" data-testid="admin-users-failure">
        <UiErrorState
          :title="failure.title"
          :description="failure.description"
          :code-label="failure.codeLabel"
          :retryable="failure.retryable"
          retry-text="重新加载"
          dense
          @retry="loadRoster"
        />
      </div>

      <div v-else-if="isEmpty" data-testid="admin-users-empty">
        <UiEmptyState :title="view.title" :description="view.description" dense />
      </div>

      <div v-else data-testid="admin-users-rows">
        <UiTable :columns="USER_COLUMNS" :rows="rows" row-key="id" aria-label="账号名册" dense />
      </div>
    </section>
  </div>
</template>