import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    watch: {
      usePolling: process.env.CHOKIDAR_USEPOLLING === 'true',
      interval: 1000,
    },
    // Browser on host hits mapped :5173; HMR must not use the container IP.
    hmr: {
      host: process.env.VITE_HMR_HOST ?? 'localhost',
      port: Number(process.env.VITE_HMR_PORT ?? 5173),
    },
  },
})
