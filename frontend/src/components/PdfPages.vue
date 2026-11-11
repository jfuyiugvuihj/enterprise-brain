<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as pdfjs from 'pdfjs-dist/legacy/build/pdf.mjs'
import workerUrl from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?url'

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

const props = defineProps({ src: { type: String, required: true } })
const root = ref(null)
const pages = ref([])
const error = ref('')
const loading = ref(true)
const zoom = ref(1)
let documentHandle = null
let observer = null
let loadGeneration = 0
let renderGeneration = 0
let renderedWidth = 0
let renderTail = Promise.resolve()

async function renderPages(current) {
  if (!documentHandle || !root.value) return
  const handle = documentHandle
  const fitWidth = Math.max(1, root.value.clientWidth - 16)
  const width = fitWidth * zoom.value
  renderedWidth = fitWidth
  const ratio = Math.min(window.devicePixelRatio || 1, 2)
  for (let number = 1; number <= handle.numPages; number += 1) {
    if (current !== renderGeneration || handle !== documentHandle) return
    const page = await handle.getPage(number)
    if (current !== renderGeneration || handle !== documentHandle) return
    const canvas = root.value?.querySelector(`[data-pdf-page="${number}"]`)
    if (!canvas) return
    const base = page.getViewport({ scale: 1 })
    const viewport = page.getViewport({ scale: width / base.width })
    canvas.width = Math.ceil(viewport.width * ratio)
    canvas.height = Math.ceil(viewport.height * ratio)
    canvas.style.width = `${Math.ceil(viewport.width)}px`
    canvas.style.height = `${Math.ceil(viewport.height)}px`
    const context = canvas.getContext('2d')
    await page.render({ canvasContext: context, viewport, transform: [ratio, 0, 0, ratio, 0, 0] }).promise
  }
}

function draw() {
  const current = ++renderGeneration
  const task = renderTail.catch(() => {}).then(() => renderPages(current))
  renderTail = task.catch(() => {})
  return task
}

function drawSafely() {
  const task = draw()
  const current = renderGeneration
  task.catch(() => {
    if (current === renderGeneration) error.value = '页面缩放失败，请重新打开。'
  })
}

function changeZoom(delta) {
  zoom.value = Math.min(3, Math.max(1, Math.round((zoom.value + delta) * 100) / 100))
  drawSafely()
}

function fitWidth() {
  zoom.value = 1
  if (root.value) root.value.scrollLeft = 0
  drawSafely()
}

async function load() {
  const current = ++loadGeneration
  renderGeneration += 1
  zoom.value = 1
  if (root.value) root.value.scrollLeft = 0
  pages.value = []
  loading.value = true
  error.value = ''
  await renderTail.catch(() => {})
  if (current !== loadGeneration) return
  if (documentHandle) { await documentHandle.destroy(); documentHandle = null }
  if (current !== loadGeneration || !props.src) return
  try {
    const response = await fetch(props.src)
    if (!response.ok) throw new Error('文件读取失败')
    const data = new Uint8Array(await response.arrayBuffer())
    const handle = await pdfjs.getDocument({ data }).promise
    if (current !== loadGeneration) { await handle.destroy(); return }
    documentHandle = handle
    pages.value = Array.from({ length: handle.numPages }, (_, index) => index + 1)
    await nextTick()
    await draw()
    if (current === loadGeneration) loading.value = false
  } catch (cause) {
    if (current === loadGeneration) {
      error.value = cause?.message || 'PDF 无法预览，请尝试下载。'
      loading.value = false
    }
  }
}

watch(() => props.src, load)
onMounted(() => {
  observer = new ResizeObserver(() => {
    const width = (root.value?.clientWidth || 0) - 16
    if (!loading.value && documentHandle && Math.abs(width - renderedWidth) > 8) drawSafely()
  })
  if (root.value) observer.observe(root.value)
  load()
})
onBeforeUnmount(() => {
  loadGeneration += 1
  renderGeneration += 1
  observer?.disconnect()
  renderTail.then(() => documentHandle?.destroy()).catch(() => {})
})
</script>

<template>
  <div ref="root" class="pdf-pages" :class="{ 'is-zoomed': zoom > 1 }" data-testid="pdf-pages">
    <div class="pdf-toolbar" role="toolbar" aria-label="PDF 缩放">
      <button type="button" aria-label="缩小" :disabled="zoom <= 1" @click="changeZoom(-0.25)">缩小</button>
      <span class="pdf-zoom-level" aria-live="polite">{{ Math.round(zoom * 100) }}%</span>
      <button type="button" aria-label="放大" :disabled="zoom >= 3" @click="changeZoom(0.25)">放大</button>
      <button type="button" aria-label="适合宽度" @click="fitWidth">适合宽度</button>
    </div>
    <p v-if="loading" role="status">正在打开 PDF…</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <canvas v-for="number in pages" :key="number" :data-pdf-page="number" :aria-label="`PDF 第 ${number} 页`"></canvas>
  </div>
</template>

<style scoped>
.pdf-pages { width: 100%; min-width: 0; overflow: auto; padding: 8px; background: var(--surface-3); }
.pdf-toolbar { position: sticky; top: 0; left: 0; z-index: 2; display: flex; align-items: center; gap: 6px; width: max-content; max-width: 100%; padding: 4px; margin: 0 auto 8px 0; border-radius: 8px; background: var(--surface-1); box-shadow: var(--shadow-1); }
.pdf-toolbar button { min-width: 44px; min-height: 44px; padding: 0 8px; border: 1px solid var(--border-1); border-radius: 6px; background: var(--surface-1); color: var(--text-1); font: inherit; cursor: pointer; touch-action: manipulation; white-space: nowrap; }
.pdf-toolbar button:disabled { opacity: 0.5; cursor: default; }
.pdf-zoom-level { min-width: 42px; text-align: center; font-size: 13px; }
.pdf-pages canvas { display: block; max-width: 100%; height: auto; margin: 0 0 12px; background: white; box-shadow: var(--shadow-1); }
.pdf-pages.is-zoomed canvas { max-width: none; }
.pdf-pages p { padding: 20px; color: var(--text-2); }
</style>
