<!--
  R316 · 「账号与角色」屏壳：读服务端名册，并按那四枚早已在树的后端出口写它

  读的是 app/api/v1/auth.py:90 那一枚 GET /users（:106 回 {"users": users}）。
  R316 当年把同文件里的四枚写出口按派工原样留着不接，并在结案时把这笔边界登记在自己的注释里；
  R360 接的就是那一笔：:98 POST /users、:113 DELETE /users/{user_id}、:123 PUT /users/password、
  :139 PUT /users/department。后端零改动——四枚的语义、状态码、请求体一个字符没动，前端也不替
  它们补能力：后端只有「删除」没有「停用」，屏上就只说删除；改密码那一枚要先验现用密码，
  屏上就照它说这一格要知道现由密码，不造一枚假的「一键重置」。四枚各自真会回哪些码，见
  src/lib/__tests__/r360-user-writes.test.js 那张取证表（本单对契约的唯一交代）。

  三条屏壳级纪律：
  ① 不乐观（判据乙）：每一次写之后都重新发那一枚 GET，屏上那几行永远只可能来自后端回包；
     本文件不提供、也不允许任何「本地把那一行改掉」的写法（手法同 lib/notifications.js 的全部已读）。
     回执随后端两次回包对表：名册重新读回来如果不支持「成了」这句话，两句同时摆在屏上。
  ② 失败脸逐枚分开、各有出处（判据丙）：没权限 / 登录失效 / 冲突 / 找不到 / 没收下这一发 / 存储
     没就绪 六张脸，加一张「200 但读不出结论」，判据只在 lib/errcodes.js 那本字典与 HTTP status
     两枚出处上，本文件不判码。存储那一张不挂重试按钮（三条理由逐字抄在 lib/users.js 写层开头，
     出自 lib/errcodes.js:99-107）；写失败一律不挂重试。
  ③ 动作条只在名册真的读回来（ready / empty）那两张脸上出现：没权限 / 登录失效 / 存储没就绪 /
     回包读不出行那几张脸上一个写控件都不画——那些场合后端连名册都没答应过，摆一枚写了删的按钮
     就是假控件。这一屏也不猜权限：GET 与那三枚 manage 出口过的是同一道闸（auth.py:93 / :101 /
     :116 / :155），所以「名册读回来了」是后端的回话说你有这道闸，不是前端自己判了一遍角色。

  零统计量、列只认后端那五枚键、无新色值（屏壳不带样式块，排版只用 theme.css 既有类）、
  零枚裸 <button>、动作全部走 ui 原语且在 script setup 块内 import —— R316 钉过的那一族一字未退，
  反向钉在 src/components/__tests__/r360-admin-panel-writes.test.js。
-->
<script>
export default { name: 'AdminPanel' }
</script>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import {
  USER_COLUMNS,
  USER_CREATE_DEFAULTS,
  USER_CREATABLE_ROLES,
  USER_FORM_FIELDS,
  USER_RULE_HINTS,
  USERS_FACE_EMPTY,
  USERS_FACE_LOADING,
  USERS_FACE_READY,
  USERS_FACE_WRITE_OK,
  USERS_LOADING_TEXT,
  USERS_UNADDRESSABLE_MESSAGE,
  USERS_UNADDRESSABLE_TITLE,
  USER_WRITE_CREATE,
  USER_WRITE_DELETE,
  USER_WRITE_DEPARTMENT,
  USER_WRITE_PASSWORD,
  createBody,
  departmentBody,
  departmentText,
  loadUsers,
  passwordBody,
  submitCreateUser,
  submitDeleteUser,
  submitDepartmentChange,
  submitPasswordChange,
  userDeletePath,
  userFormRuleViolations,
  userRoleLabel,
  userWriteReadback,
  usersBlankView,
  usersFailureFace,
} from '../lib/users'
import { UiButton, UiDialog, UiEmptyState, UiErrorState, UiField, UiLoadingState, UiSelect, UiTable } from './ui'

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
// 动作条的两张许可脸：ready 与 empty 都是「后端真的答了这枚 GET」；剩下几张没答应过。
const canAct = computed(() => view.value.face === USERS_FACE_READY || view.value.face === USERS_FACE_EMPTY)

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

// ── 写：对话框与表单状态 ────────────────────────────────────────────────────
const dlgCreate = ref(false)
const dlgPassword = ref(false)
const dlgDepartment = ref(false)
const dlgDelete = ref(false)
const targetName = ref('')
const busyKind = ref('')
const fieldErrors = ref({})
const receipt = ref(null)

const form = reactive({
  [USER_FORM_FIELDS.username]: '',
  [USER_FORM_FIELDS.password]: '',
  [USER_FORM_FIELDS.role]: '',
  [USER_FORM_FIELDS.department]: '',
  [USER_FORM_FIELDS.oldPassword]: '',
  [USER_FORM_FIELDS.newPassword]: '',
})

/** 能创建的角色只有后端那三枚（lib 的账对 app/common/auth.py:606 的 CREATABLE_ROLES 闸）；标签仍走 userRoleLabel 这一处。 */
const roleOptions = USER_CREATABLE_ROLES.map(role => ({ value: role, label: userRoleLabel(role) }))
/** 操作对象只从名册那几行里长出来：一行回包一个选项，前端不补名单、也不替后端猜谁存在。 */
const targetOptions = computed(() => rows.value.map(row => ({
  value: row.username,
  label: `${row.username} · ${userRoleLabel(row.role)} · ${departmentText(row.department)}`,
})))
const chosenRow = computed(() => rows.value.find(row => row.username === targetName.value) || null)
const hasTarget = computed(() => Boolean(chosenRow.value))
/** 删除按编号走（app/api/v1/auth.py:131 的路径参数就是编号）；这一行没编号就如实说删不了，不替它猜一个。 */
const deletePath = computed(() => (chosenRow.value ? userDeletePath(chosenRow.value) : ''))
const busy = computed(() => busyKind.value !== '')

function closeDialogs() {
  dlgCreate.value = false
  dlgPassword.value = false
  dlgDepartment.value = false
  dlgDelete.value = false
  fieldErrors.value = {}
}

/**
 * 打开一枚对话框：表单起点全部取后端默认值或后端已记的值（app/api/v1/auth.py:28-29 给 role / department
 * 定的默认就是 staff 与空串），一个字符都不自己加工；预检错误位与上一次的回执一起清空。
 */
function openDialog(kind) {
  closeDialogs()
  receipt.value = null
  busyKind.value = ''
  const row = chosenRow.value
  form[USER_FORM_FIELDS.role] = USER_CREATE_DEFAULTS.role
  form[USER_FORM_FIELDS.password] = ''
  form[USER_FORM_FIELDS.newPassword] = ''
  form[USER_FORM_FIELDS.oldPassword] = ''
  if (kind === USER_WRITE_CREATE) {
    form[USER_FORM_FIELDS.username] = ''
    form[USER_FORM_FIELDS.department] = USER_CREATE_DEFAULTS.department
    dlgCreate.value = true
    return
  }
  form[USER_FORM_FIELDS.username] = row ? row.username : ''
  form[USER_FORM_FIELDS.department] = row && kind === USER_WRITE_DEPARTMENT ? row.department : ''
  if (kind === USER_WRITE_PASSWORD) dlgPassword.value = true
  else if (kind === USER_WRITE_DEPARTMENT) dlgDepartment.value = true
  else dlgDelete.value = true
}

/** 名册换了就清一次：账号不在了就把操作对象收回空，绝不让屏上留一个名册里没有的「选中的人」。 */
watch(rows, (next) => {
  if (targetName.value && !next.some(row => row.username === targetName.value)) targetName.value = ''
})

/**
 * 一次写：预检（只读后端那本账）→ 发那一枚出口 → 🔴 无论如何都重新读一次名册 → 拿两次回包对表。
 * 预检没过时一发都不发：那一句「至少要几位」说的就是后端那一条，发出去只是让后端再拒一次，
 * 而屏上会先闪一帧「正在提交」——那一帧正是乐观更新的雏形，不要。
 */
async function runWrite(kind, body, send) {
  const errors = userFormRuleViolations(kind, form)
  if (Object.keys(errors).length) {
    fieldErrors.value = errors
    receipt.value = null
    return
  }
  if (busyKind.value) return
  fieldErrors.value = {}
  busyKind.value = kind
  const out = await send()
  busyKind.value = ''
  await loadRoster()
  const back = userWriteReadback(out.kind, out.target, view.value, body)
  receipt.value = { ...out, consistent: back.consistent, note: back.note }
  if (out.face === USERS_FACE_WRITE_OK) closeDialogs()
}

/** 四枚出口的四个提交点：每一枚只发自己那一枚，路径与请求体都在 lib 那层定死。 */
function submitCreate() {
  return runWrite(USER_WRITE_CREATE, createBody(form), () => submitCreateUser(form))
}

function submitPassword() {
  return runWrite(USER_WRITE_PASSWORD, passwordBody(form), () => submitPasswordChange(form))
}

function submitDepartment() {
  return runWrite(USER_WRITE_DEPARTMENT, departmentBody(form), () => submitDepartmentChange(form))
}

/** 删除这一枚只有确认后才会被调用：确认步就是那枚对话框本身（判据丁）。 */
function confirmDelete() {
  return runWrite(USER_WRITE_DELETE, {}, () => submitDeleteUser(chosenRow.value))
}

</script>

<template>
  <div class="panel-shell" data-testid="admin-panel" :data-face="view.face">
    <header class="panel-head">
      <div>
        <span class="eyebrow">服务端账号名册</span>
        <p>
          这一屏列的是 GET /users 真回包里的行：谁在名册上、各自被登记成什么角色。
          名册读回来之后，下面那块动作条按后端早就在树的四枚出口写它——开通账号、改密码、调部门、删除账号；
          每写完一次这一屏都重新读一次，所以屏上那几行永远是刚刚读回来的结果，不是前端自己改出来的影子。
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

    <!--
      动作条：只在后端真的答了这枚 GET 的那两张脸上出现（ready / empty）。
      剩下四张脸（没权限 / 登录失效 / 存储没就绪 / 回包读不出行）一个写控件都不画。
      改密码、调部门、删除都要作用在一枚具体的账号上：没点到人就不把这三枚摆出来，
      而不是摆三枚点了没反应的按钮（R32 明令禁的假控件）。
    -->
    <section v-if="canAct" class="panel-card" data-testid="admin-user-actions">
      <div class="section-head">
        <span class="eyebrow">账号操作</span>
        <span class="demo-note">后端只有「删除」这一枚出口，没有「停用」；改名与换角色它也没给出口 —— 这里只摆它真给的那四枚。</span>
      </div>

      <div class="section-head">
        <UiSelect
          v-if="!isEmpty"
          v-model="targetName"
          label="操作对象"
          :options="targetOptions"
          placeholder="先从名册里点一枚账号"
          data-testid="pick-target"
        />
        <UiButton
          variant="primary"
          size="sm"
          label="开通账号"
          data-testid="open-create"
          @click="openDialog(USER_WRITE_CREATE)"
        />
      </div>

      <div v-if="hasTarget" class="section-head" data-testid="target-actions">
        <UiButton
          size="sm"
          :loading="busyKind === USER_WRITE_PASSWORD"
          label="改密码"
          data-testid="open-password"
          @click="openDialog(USER_WRITE_PASSWORD)"
        />
        <UiButton
          size="sm"
          :loading="busyKind === USER_WRITE_DEPARTMENT"
          label="调部门"
          data-testid="open-department"
          @click="openDialog(USER_WRITE_DEPARTMENT)"
        />
        <UiButton
          size="sm"
          variant="danger"
          :loading="busyKind === USER_WRITE_DELETE"
          label="删除账号"
          data-testid="open-delete"
          @click="openDialog(USER_WRITE_DELETE)"
        />
      </div>
      <p v-else-if="!isEmpty" class="demo-note">
        改密码、调部门、删除都落在「操作对象」那一枚账号上：还没点到人，这三枚就不摆出来。
      </p>

      <!-- 回执：成功那一支是名册旁边一句话，失败那一支是一张独立的脸（判据丙），都不挂重试。 -->
      <div v-if="receipt && receipt.face !== USERS_FACE_WRITE_OK" data-testid="write-failure">
        <UiErrorState
          :title="receipt.title"
          :description="receipt.description"
          :code-label="receipt.codeLabel"
          :retryable="false"
          dense
        />
      </div>
      <p v-if="receipt && receipt.note" class="demo-note" data-testid="write-readback">{{ receipt.note }}</p>
      <p v-if="receipt && receipt.face === USERS_FACE_WRITE_OK" class="demo-note" data-testid="write-receipt">
        {{ receipt.title }}：{{ receipt.description }}
      </p>
    </section>

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

    <!--
      四枚对话框：每一枚只对应一枚后端出口，提交点各发各的那一发。
      删除那一枚的确认步就是对话框本身（判据丁）：确认句里点名被操作的是谁，不用 window.confirm，
      也不自造遮罩——叠层、焦点循环、Esc 收起都由 UiDialog 那一枚原语负责。
    -->
    <UiDialog
      v-model="dlgCreate"
      title="开通一枚新账号"
      description="这一枚发的是 POST /users。表单里那几条要求逐条抄自后端自己的规则，一条不多一条不少。"
      :busy="busyKind === USER_WRITE_CREATE"
    >
      <div class="panel-shell">
        <UiField
          v-model="form[USER_FORM_FIELDS.username]"
          label="账号名"
          required
          :error="fieldErrors[USER_FORM_FIELDS.username]"
          hint="后端对账号名没有字符集、也没有长度规则，所以这里也不设：填什么就发什么。"
          data-testid="create-username"
        />
        <UiField
          v-model="form[USER_FORM_FIELDS.password]"
          type="password"
          label="初始密码"
          required
          :error="fieldErrors[USER_FORM_FIELDS.password]"
          :hint="USER_RULE_HINTS.passwordTooShort"
          data-testid="create-password"
        />
        <UiSelect
          v-model="form[USER_FORM_FIELDS.role]"
          label="角色"
          :options="roleOptions"
          :error="fieldErrors[USER_FORM_FIELDS.role]"
          data-testid="create-role"
        />
        <p class="demo-note">{{ USER_RULE_HINTS.roleUnknown }}</p>
        <UiField
          v-model="form[USER_FORM_FIELDS.department]"
          label="部门归属"
          :error="fieldErrors[USER_FORM_FIELDS.department]"
          hint="留空就是这一枚账号没有归属部门；后端对部门归属同样没有字符集规则。"
          data-testid="create-department"
        />
      </div>
      <template #footer="{ close }">
        <UiButton variant="ghost" label="取消" data-testid="cancel-create" @click="close" />
        <UiButton
          variant="primary"
          :loading="busyKind === USER_WRITE_CREATE"
          label="提交开通"
          data-testid="submit-create"
          @click="submitCreate"
        />
      </template>
    </UiDialog>

    <UiDialog
      v-model="dlgPassword"
      title="改写密码"
      description="这一枚发的是 PUT /users/password。它先验一遍现由密码才写新密码，所以「不知道现由密码就能重置」这一档后端并没有给 —— 界面上也不摆那种按钮。"
      :busy="busyKind === USER_WRITE_PASSWORD"
    >
      <div class="panel-shell">
        <UiField
          :model-value="form[USER_FORM_FIELDS.username]"
          label="账号名"
          readonly
          hint="这一枚账号来自名册那几行，不是手打的。"
          data-testid="password-username"
        />
        <UiField
          v-model="form[USER_FORM_FIELDS.oldPassword]"
          type="password"
          label="现由密码"
          :hint="USER_RULE_HINTS.passwordTooShort"
          :error="fieldErrors[USER_FORM_FIELDS.oldPassword]"
          data-testid="password-old"
        />
        <UiField
          v-model="form[USER_FORM_FIELDS.newPassword]"
          type="password"
          label="新密码"
          :hint="USER_RULE_HINTS.newPasswordTooShort"
          :error="fieldErrors[USER_FORM_FIELDS.newPassword]"
          data-testid="password-new"
        />
      </div>
      <template #footer="{ close }">
        <UiButton variant="ghost" label="取消" data-testid="cancel-password" @click="close" />
        <UiButton
          variant="primary"
          :loading="busyKind === USER_WRITE_PASSWORD"
          label="提交改写"
          data-testid="submit-password"
          @click="submitPassword"
        />
      </template>
    </UiDialog>

    <UiDialog
      v-model="dlgDepartment"
      title="调整部门归属"
      description="这一枚发的是 PUT /users/department。归属那一格每次都带上：后端把「没带这一格」读成「这轮没说」，一个字都不写；留空才是明确要清空。"
      :busy="busyKind === USER_WRITE_DEPARTMENT"
    >
      <div class="panel-shell">
        <UiField
          :model-value="form[USER_FORM_FIELDS.username]"
          label="账号名"
          readonly
          hint="这一枚账号来自名册那几行，不是手打的。"
          data-testid="department-username"
        />
        <UiField
          v-model="form[USER_FORM_FIELDS.department]"
          label="部门归属"
          :error="fieldErrors[USER_FORM_FIELDS.department]"
          hint="清空是把人关到门外，不是放开边界：非管理员一旦没有归属，后端会直接拒掉他自己的检索与产出物。"
          data-testid="department-value"
        />
      </div>
      <template #footer="{ close }">
        <UiButton variant="ghost" label="取消" data-testid="cancel-department" @click="close" />
        <UiButton
          variant="primary"
          :loading="busyKind === USER_WRITE_DEPARTMENT"
          label="提交调整"
          data-testid="submit-department"
          @click="submitDepartment"
        />
      </template>
    </UiDialog>

    <UiDialog
      v-model="dlgDelete"
      title="删除账号"
      description="后端没有「停用」这一档：这一枚发的是 DELETE，它删掉的就是名册里的那一行，不可逆。"
      :busy="busyKind === USER_WRITE_DELETE"
      size="sm"
    >
      <div class="panel-shell">
        <UiErrorState
          v-if="!deletePath"
          :title="USERS_UNADDRESSABLE_TITLE"
          :description="USERS_UNADDRESSABLE_MESSAGE"
          :retryable="false"
          dense
        />
        <p v-else>
          确认句：我要删除账号
          <strong>{{ chosenRow ? chosenRow.username : '' }}</strong>
          （名册编号 {{ chosenRow ? chosenRow.id : '' }}），并接受这一步不可逆。
        </p>
      </div>
      <template #footer="{ close }">
        <UiButton variant="ghost" label="取消" data-testid="cancel-delete" @click="close" />
        <UiButton
          v-if="deletePath"
          variant="danger"
          :loading="busyKind === USER_WRITE_DELETE"
          label="确认删除"
          data-testid="confirm-delete"
          @click="confirmDelete"
        />
      </template>
    </UiDialog>
  </div>
</template>
