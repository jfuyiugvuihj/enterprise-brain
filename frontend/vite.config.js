import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const guideRoot = resolve(fileURLToPath(new URL('.', import.meta.url)), '../docs/user-guide')
function guidePages(directory = guideRoot) {
  return Object.fromEntries(readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const absolute = resolve(directory, entry.name)
    if (entry.isDirectory()) return Object.entries(guidePages(absolute))
    if (!entry.name.endsWith('.md')) return []
    return [[relative(guideRoot, absolute).replaceAll('\\', '/'), readFileSync(absolute, 'utf8')]]
  }))
}

export default defineConfig({
  plugins: [vue()],
  define: { __USER_GUIDE_PAGES__: JSON.stringify(guidePages()) },
  build: {
    cssTarget: 'chrome97',
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true
      },
      '/static': {
        target: 'http://localhost:8001',
        changeOrigin: true
      }
    }
  }
})
