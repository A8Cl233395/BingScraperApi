import { defineConfig } from 'vite'
import { resolve } from 'path'
import vue from '@vitejs/plugin-vue'
import { compression } from 'vite-plugin-compression2'

export default defineConfig({
  plugins: [
    vue(),
    compression({ algorithms: ['brotliCompress', 'gzip'] }),
  ],
  build: {
    rolldownOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        login: resolve(__dirname, 'login.html'),
        invite: resolve(__dirname, 'invite.html'),
      },
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('vue') || id.includes('vue-router') || id.includes('axios')) {
              return 'vendor';
            }
            if (id.includes('marked') || id.includes('katex') || id.includes('highlight.js')) {
              return 'markdown';
            }
            if (id.includes('@microsoft')) {
              return 'fetch-event-source';
            }
          }
        }
      }
    }
  }
})