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
let documentHandle = null
let observer = null
let loadGeneration = 0
let renderGeneration = 0
let renderedWidth = 0

async function draw() {
  const current = ++renderGeneration
  if (!documentHandle || !root.value) return
  const handle = documentHandle
  const width = Math.max(1, root.value.clientWidth - 16)
  renderedWidth = width
  const ratio = Math.min(window.devicePixelRatio || 1, 2)
  for (let number = 1; number <= handle.numPages; number += 1) {
    if (current !== renderGeneration || handle !== documentHandle) return
    const page = await handle.getPage(number)
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

async function load() {
  const current = ++loadGeneration
  renderGeneration += 1
  pages.value = []
  loading.value = true
  error.value = ''
  if (documentHandle) { await documentHandle.destroy(); documentHandle = null }
  if (!props.src) return
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
    if (!loading.value && documentHandle && Math.abs(width - renderedWidth) > 8) draw().catch(() => { error.value = '页面缩放失败，请重新打开。' })
  })
  if (root.value) observer.observe(root.value)
  load()
})
onBeforeUnmount(() => {
  loadGeneration += 1
  renderGeneration += 1
  observer?.disconnect()
  documentHandle?.destroy()
})
</script>

<template>
  <div ref="root" class="pdf-pages" data-testid="pdf-pages">
    <p v-if="loading" role="status">正在打开 PDF…</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <canvas v-for="number in pages" :key="number" :data-pdf-page="number" :aria-label="`PDF 第 ${number} 页`"></canvas>
  </div>
</template>

<style scoped>
.pdf-pages { width: 100%; min-width: 0; overflow-x: hidden; padding: 8px; background: var(--surface-3); }
.pdf-pages canvas { display: block; max-width: 100%; height: auto; margin: 0 auto 12px; background: white; box-shadow: var(--shadow-1); }
.pdf-pages p { padding: 20px; color: var(--text-2); }
</style>
