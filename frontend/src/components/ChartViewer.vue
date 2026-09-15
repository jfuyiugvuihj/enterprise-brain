<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  src: String,
  caption: String,
  downloadName: String,
})

const previewOpen = ref(false)
const previewRotate = ref(0)

const downloadUrl = computed(() => {
  if (props.src?.startsWith('http')) return props.src
  return `${props.src}`
})

function rotate() {
  previewRotate.value = (previewRotate.value + 90) % 360
}

function closePreview() {
  previewOpen.value = false
  previewRotate.value = 0
}
</script>

<template>
  <div v-if="src" class="chart-card">
    <!-- 标题栏 -->
    <div class="chart-header">
      <span class="chart-caption">{{ caption || '图表' }}</span>
      <div class="chart-actions">
        <button class="chart-btn" title="放大查看" @click="previewOpen = true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/><path d="M11 8v6M8 11h6"/>
          </svg>
        </button>
        <a class="chart-btn" title="下载" :href="downloadUrl" :download="downloadName || 'chart.png'">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
          </svg>
        </a>
      </div>
    </div>

    <!-- 图表图片 -->
    <div class="chart-img-wrap" @click="previewOpen = true">
      <img :src="downloadUrl" :alt="caption" class="chart-img" loading="lazy" />
    </div>

    <!-- 放大预览弹窗 -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="previewOpen" class="preview-overlay" @click.self="closePreview">
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
            <img :src="downloadUrl" :alt="caption" class="preview-img"
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
  background: rgba(17, 27, 44, .92);
  border-radius: 12px;
  border: 1px solid rgba(157, 178, 207, .16);
  overflow: hidden;
  box-shadow: 0 14px 34px rgba(0, 0, 0, .18);
  transition: box-shadow 0.2s;
}

.chart-card:hover {
  box-shadow: 0 18px 42px rgba(0, 0, 0, .28);
}

.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(157, 178, 207, .12);
}

.chart-caption {
  font-size: 13px;
  font-weight: 500;
  color: #f0f4fb;
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
  color: #9eacc1;
  text-decoration: none;
  transition: all 0.15s;
}

.chart-btn:hover {
  background: rgba(106, 140, 255, .14);
  color: #8ea8ff;
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
  background: #fff;
  transition: transform 0.2s;
}

.chart-img-wrap:hover .chart-img {
  transform: scale(1.02);
}

/* ===== 预览弹窗 ===== */
.preview-overlay {
  position: fixed;
  inset: 0;
  background: rgba(3, 7, 16, .82);
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
  border: 1px solid rgba(255,255,255,0.25);
  border-radius: 8px;
  background: rgba(255,255,255,0.1);
  color: #f0f4fb;
  cursor: pointer;
  font-size: 13px;
  font-family: inherit;
  text-decoration: none;
  transition: all 0.15s;
  backdrop-filter: blur(8px);
}

.tb-btn:hover {
  background: rgba(255,255,255,0.2);
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
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
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
</style>
