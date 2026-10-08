import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],
    build: {
      outDir: 'dist/w2',
      rollupOptions: {
        input: {
          main: resolve(process.cwd(), 'index.html'),
          documents: resolve(process.cwd(), 'documents.html'),
        },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.js'],
      restoreMocks: true,
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      proxy: {
        '/media': { target: env.BACKEND_URL || 'http://127.0.0.1:8000', changeOrigin: true },
        '/api': {
          target: env.BACKEND_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
