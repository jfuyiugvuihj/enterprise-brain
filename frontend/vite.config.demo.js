import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Local preview for the existing demo stack:
// latest frontend source on :5173, API proxied to the latest backend on :18082.
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:18082',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://127.0.0.1:18082',
        changeOrigin: true,
      },
    },
  },
})
