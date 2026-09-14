import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  define: {
    'import.meta.env.VITE_API_BASE_URL': JSON.stringify(''),
  },
  server: {
    port: 5298,
    proxy: {
      '/api': 'http://localhost:8298',
    },
  },
})
