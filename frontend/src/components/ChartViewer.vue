<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { fetchArtifactBlob, isArtifactRequest } from '../lib/artifacts'
import { UiLoadingState } from './ui'

const props = defineProps({
  src: String,
  caption: String,
  downloadName: String,
})

// props.src is the artifact address (e.g. /api/v1/artifacts/<id>/content). It is never
// bound to an <img>: that request would go out without a Bearer token. The bytes are
// fetched through the shared axios instance and shown from an object URL instead.
const loadState = ref('idle') // idle | loading | ready | error
const objectUrl = ref('')
const errorText = ref('')
const previewOpen = ref(false)
const previewRotate = ref(0)

let loadToken = 0
let activeHandle = null

const displayUrl = computed(() => objectUrl.value)
const downloadUrl = computed(() => objectUrl.value || '')

function releaseBlob() {
  if (activeHandle) activeHandle.revoke()
  activeHandle = null
  objectUrl.value = ''
}

async function load() {
  const token = ++loadToken
  releaseBlob()
  errorText.value = ''
  if (!props.src) {
    loadState.value = 'idle'
    return
  }
  loadState.value = 'loading'
  if (!isArtifactRequest(props.src)) {
    objectUrl.value = props.src
    loadState.value = 'ready'
    return
  }
  try {
    const handle = await fetchArtifactBlob(props.src)
    if (token !== loadToken) {
      handle.revoke()
      return
    }
    activeHandle = handle
    objectUrl.value = handle.objectUrl
    loadState.value = 'ready'
  } catch (err) {
    if (token !== loadToken || err?.code === 'aborted') return
    errorText.value = err?.message || '图表内容获取失败'
    loadState.value = 'error'
  }
}

function rotate() {
  previewRotate.value = (previewRotate.value + 90) % 360
}

function closePreview() {
  previewOpen.value = false
  previewRotate.value = 0
}

watch(() => props.src, load, { immediate: true })
onUnmounted(() => {
  loadToken += 1
  releaseBlob()
})
</script>

<template>
  <div v-if="src" class="chart-card">
    <!-- 标题栏 -->
    <div class="chart-header">
      <span class="chart-caption">{{ caption || '图表' }}</span>
      <div class="chart-actions">
        <button class="chart-btn" title="放大查看" :disabled="loadState !== 'ready'" @click="previewOpen = true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/><path d="M11 8v6M8 11h6"/>
          </svg>
        </button>
        <a v-if="loadState === 'ready'" class="chart-btn" title="下载" :href="downloadUrl" :download="downloadName || 'chart.png'">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
          </svg>
        </a>
      </div>
    </div>

    <!-- 图表图片：只绑定取回后的本地地址 -->
    <div v-if="loadState === 'ready'" class="chart-img-wrap" @click="previewOpen = true">
      <img :src="displayUrl" :alt="caption || '图表'" class="chart-img" />
    </div>

    <UiLoadingState v-else-if="loadState === 'loading'" label="正在获取图表…" variant="block" dense />

    <div v-else-if="loadState === 'error'" class="chart-state chart-state-error" role="status">
      <span class="chart-state-icon" aria-hidden="true">⚠️</span>
      <div class="chart-state-body">
        <strong class="chart-state-title">图表未能显示</strong>
        <span class="chart-state-text">{{ errorText }}</span>
      </div>
      <button class="chart-retry" type="button" @click="load">重新取图</button>
    </div>

    <div v-else class="chart-state">
      <span class="chart-state-text">该轮回答没有返回图表</span>
    </div>

    <!-- 放大预览弹窗 -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="previewOpen && loadState === 'ready'" class="preview-overlay" @click.self="closePreview">
          <div class="preview-container">
            <div class="preview-toolbar">
              <button class="tb-btn" @click="rotate" title="旋转 90°">
                🔄 {{ previewRotate }}°
              </button>
              <a class="tb-btn" :href="downloadUrl" :download="downloadName || 'chart.png'" title="下载">
                ⬇ 下载
              </a>
              <button class="tb-btn tb-close" @click="closePreview" title="关闭">✕</button>
            </div>
            <img :src="displayUrl" :alt="caption || '图表'" class="preview-img"
                 :style="{ transform: `rotate(${previewRotate}deg)` }" />
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
<style scoped>
.chart-card {
  margin: 12px 0;
  background: color-mix(in srgb, var(--legacy-night-2) 92%, transparent);
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--legacy-steel) 16%, transparent);
  overflow: hidden;
  box-shadow: 0 14px 34px color-mix(in srgb, var(--legacy-void) 18%, transparent);
  transition: box-shadow 0.2s;
}

.chart-card:hover {
  box-shadow: 0 18px 42px color-mix(in srgb, var(--legacy-void) 28%, transparent);
}

.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid color-mix(in srgb, var(--legacy-steel) 12%, transparent);
}

.chart-caption {
  font-size: 13px;
  font-weight: 500;
  color: var(--ink);
}

.chart-actions {
  display: flex;
  gap: 4px;
}

.chart-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--legacy-ink-steel);
  text-decoration: none;
  transition: all 0.15s;
}

.chart-btn:hover {
  background: color-mix(in srgb, var(--legacy-periwinkle-strong) 14%, transparent);
  color: var(--legacy-periwinkle);
}

.chart-img-wrap {
  cursor: pointer;
  padding: 12px;
  display: flex;
  justify-content: center;
}

.chart-img {
  max-width: 100%;
  max-height: 360px;
  border-radius: 6px;
  background: var(--legacy-paper);
  transition: transform 0.2s;
}

.chart-img-wrap:hover .chart-img {
  transform: scale(1.02);
}

/* ===== 预览弹窗 ===== */
.preview-overlay {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, var(--legacy-veil) 82%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  backdrop-filter: blur(4px);
}

.preview-container {
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.preview-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.tb-btn {
  padding: 8px 20px;
  border: 1px solid color-mix(in srgb, var(--legacy-paper) 25%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--legacy-paper) 10%, transparent);
  color: var(--ink);
  cursor: pointer;
  font-size: 13px;
  font-family: inherit;
  text-decoration: none;
  transition: all 0.15s;
  backdrop-filter: blur(8px);
}

.tb-btn:hover {
  background: color-mix(in srgb, var(--legacy-paper) 20%, transparent);
}

.tb-close {
  width: 40px;
  padding: 8px;
  text-align: center;
}

.preview-img {
  max-width: 85vw;
  max-height: 75vh;
  border-radius: 8px;
  transition: transform 0.3s ease;
  box-shadow: 0 20px 60px color-mix(in srgb, var(--legacy-void) 30%, transparent);
}

/* ===== 弹窗动画 ===== */
.modal-enter-active, .modal-leave-active {
  transition: opacity 0.2s ease;
}
.modal-enter-active .preview-container, .modal-leave-active .preview-container {
  transition: transform 0.2s ease;
}
.modal-enter-from, .modal-leave-to {
  opacity: 0;
}
.modal-enter-from .preview-container {
  transform: scale(0.92);
}

/* ===== 取图状态：加载 / 失败占位卡 ===== */
.chart-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 26px 16px;
  color: var(--legacy-ink-steel);
}

.chart-state-error {
  justify-content: space-between;
  flex-wrap: wrap;
}

.chart-state-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.chart-state-title {
  font-size: 13px;
  color: var(--ink);
}

.chart-state-text {
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.chart-state-icon {
  font-size: 18px;
}

.chart-retry {
  flex: none;
  padding: 6px 14px;
  border: 1px solid color-mix(in srgb, var(--legacy-periwinkle) 45%, transparent);
  border-radius: 6px;
  background: color-mix(in srgb, var(--legacy-periwinkle-strong) 14%, transparent);
  color: var(--legacy-periwinkle);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.chart-retry:hover {
  background: color-mix(in srgb, var(--legacy-periwinkle-strong) 26%, transparent);
  color: var(--ink);
}

.chart-btn:disabled {
  opacity: .45;
  cursor: not-allowed;
}
</style>
