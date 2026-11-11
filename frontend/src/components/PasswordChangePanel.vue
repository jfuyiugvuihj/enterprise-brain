<script setup>
import { ref } from 'vue'
import { http, errorDetail } from '../lib/http'
import { UiButton, UiField } from './ui'

const props = defineProps({ username: { type: String, required: true } })
const emit = defineEmits(['changed', 'logout'])
const currentPassword = ref('')
const newPassword = ref('')
const repeatedPassword = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  if (busy.value) return
  error.value = ''
  if (!currentPassword.value || newPassword.value.length < 6) {
    error.value = '请输入临时密码，并设置至少6位的新密码。'
    return
  }
  if (newPassword.value !== repeatedPassword.value) {
    error.value = '两次输入的新密码不一致。'
    return
  }
  if (newPassword.value === currentPassword.value) {
    error.value = '新密码不能与临时密码相同。'
    return
  }
  busy.value = true
  try {
    const response = await http.put('/users/password', { username: props.username,
      old_password: currentPassword.value, new_password: newPassword.value })
    if (response.data?.status !== 'ok') throw new Error('修改结果尚未确认，请重新登录核对。')
    currentPassword.value = newPassword.value = repeatedPassword.value = ''
    emit('changed')
  } catch (reason) {
    error.value = errorDetail(reason, '密码未能更新，请重试。')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="login-v2" data-testid="required-password-change">
    <section class="login-card" style="width:min(100%,420px);margin:24px auto;min-width:0">
      <h1>设置你的新密码</h1>
      <p>账号：{{ username }}</p>
      <p>管理员已重置密码。请先把临时密码改为你自己的密码，再进入工作台。</p>
      <form class="panel-shell" @submit.prevent="submit">
        <UiField v-model="currentPassword" label="临时密码" type="password" autocomplete="current-password" required data-testid="required-current-password" />
        <UiField v-model="newPassword" label="新密码" type="password" autocomplete="new-password" hint="至少6位，与临时密码不同。" required data-testid="required-new-password" />
        <UiField v-model="repeatedPassword" label="再次输入新密码" type="password" autocomplete="new-password" required data-testid="required-repeat-password" />
        <p v-if="error" role="alert">{{ error }}</p>
        <UiButton type="submit" variant="primary" :loading="busy" data-testid="required-password-submit">保存新密码</UiButton>
        <UiButton type="button" variant="ghost" :disabled="busy" @click="emit('logout')">退出并稍后处理</UiButton>
      </form>
    </section>
  </main>
</template>
