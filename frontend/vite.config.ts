import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-i18next', 'i18next'],
          markdown: ['react-markdown', 'remark-gfm'],
          motion: ['framer-motion', 'lucide-react'],
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
