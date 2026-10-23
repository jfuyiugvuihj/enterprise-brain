<script setup>
import { nextTick, onMounted, onUnmounted, ref } from 'vue'

const open = ref(false)
const installed = ref(false)
const promptEvent = ref(null)
const installError = ref('')
const closeButton = ref(null)
const triggerButton = ref(null)
const userAgent = typeof navigator === 'undefined' ? '' : navigator.userAgent
const appIcon = '/app-icon-192.png'
const isWeChat = /MicroMessenger/i.test(userAgent)
const isApple = /iPhone|iPad|iPod/i.test(userAgent)

function onInstallPrompt(event) {
  event.preventDefault()
  promptEvent.value = event
}

function onInstalled() {
  installed.value = true
  promptEvent.value = null
  open.value = false
}

onMounted(() => {
  installed.value = window.matchMedia?.('(display-mode: standalone)').matches || navigator.standalone === true
  window.addEventListener('beforeinstallprompt', onInstallPrompt)
  window.addEventListener('appinstalled', onInstalled)
})

onUnmounted(() => {
  window.removeEventListener('beforeinstallprompt', onInstallPrompt)
  window.removeEventListener('appinstalled', onInstalled)
})

async function showGuide() {
  installError.value = ''
  open.value = true
  await nextTick()
  closeButton.value?.focus()
}

async function closeGuide() {
  open.value = false
  await nextTick()
  triggerButton.value?.focus()
}

async function installFromBrowser() {
  const event = promptEvent.value
  if (!event) return
  promptEvent.value = null
  try {
    await event.prompt()
    const choice = await event.userChoice
    if (choice?.outcome === 'accepted') open.value = false
  } catch {
    installError.value = '浏览器未能打开安装提示，请用浏览器菜单添加到桌面。'
  }
}
</script>

<template>
  <button v-if="!installed" ref="triggerButton" class="install-shortcut-trigger" type="button" @click="showGuide">
    添加到手机桌面
  </button>
  <Teleport to="body">
    <div v-if="open" class="install-shortcut-backdrop" @click.self="closeGuide" @keydown.esc="closeGuide">
      <section class="install-shortcut-dialog" role="dialog" aria-modal="true" aria-labelledby="install-shortcut-title">
        <button ref="closeButton" class="install-shortcut-close" type="button" aria-label="关闭" @click="closeGuide">×</button>
        <img :src="appIcon" alt="" width="56" height="56" />
        <h2 id="install-shortcut-title">添加到手机桌面</h2>
        <p>添加后，点桌面上的“企业智脑”图标就能打开这个工作空间。</p>
        <p v-if="isWeChat">请先用右上角菜单选择“在浏览器打开”，再从手机浏览器菜单添加到桌面。</p>
        <p v-else-if="isApple">在 Safari 中点“分享”，选择“添加到主屏幕”，然后点“添加”。</p>
        <p v-else>在手机浏览器菜单中选择“添加到桌面”“添加到主屏幕”或“安装应用”。菜单名称因浏览器而异。</p>
        <p class="install-shortcut-note">图标仍需要连接企业内网才能打开。当前内网 HTTP 地址在部分浏览器中只会创建网页快捷方式；独立应用式打开需要企业配置 HTTPS。</p>
        <p v-if="installError" role="alert">{{ installError }}</p>
        <button v-if="promptEvent" class="install-shortcut-action" type="button" @click="installFromBrowser">安装应用</button>
        <button v-else class="install-shortcut-action" type="button" @click="closeGuide">知道了</button>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.install-shortcut-trigger { min-height: 44px; padding: 0 12px; border: 1px solid #b9c9ef; border-radius: 8px; background: #f3f7ff; color: #225ce8; font: inherit; font-weight: 600; cursor: pointer; }
.install-shortcut-backdrop { position: fixed; z-index: 2000; inset: 0; display: grid; place-items: center; padding: 20px; background: rgba(15, 30, 60, .55); }
.install-shortcut-dialog { position: relative; width: min(100%, 420px); max-height: calc(100dvh - 40px); overflow-y: auto; padding: 24px; border-radius: 16px; background: #fff; color: #142544; box-shadow: 0 24px 64px rgba(0, 0, 0, .2); }
.install-shortcut-dialog img { display: block; margin-bottom: 12px; border-radius: 12px; }
.install-shortcut-dialog h2 { margin: 0 36px 12px 0; font-size: 22px; }
.install-shortcut-dialog p { margin: 10px 0; line-height: 1.6; }
.install-shortcut-note { color: #5b6881; font-size: 13px; }
.install-shortcut-close { position: absolute; top: 12px; right: 12px; width: 44px; height: 44px; border: 0; background: transparent; color: inherit; font: inherit; font-size: 28px; cursor: pointer; }
.install-shortcut-action { width: 100%; min-height: 44px; margin-top: 12px; border: 0; border-radius: 8px; background: #225ce8; color: #fff; font: inherit; font-weight: 600; cursor: pointer; }
.install-shortcut-trigger:focus-visible, .install-shortcut-close:focus-visible, .install-shortcut-action:focus-visible { outline: 2px solid #225ce8; outline-offset: 2px; }
@media (min-width: 761px) { .install-shortcut-trigger { display: none; } }
</style>
