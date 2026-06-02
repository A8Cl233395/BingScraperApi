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
    reportCompressedSize: false,
    rolldownOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        login: resolve(__dirname, 'login.html'),
        invite: resolve(__dirname, 'invite.html'),
        profile: resolve(__dirname, 'profile.html'),
      },
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('vue')) {
              return 'vendor';
            }
            if (id.includes('axios')) {
              return 'core';
            }
            if (id.includes('@microsoft')) {
              return 'sse';
            }
            if (id.includes('marked') || id.includes('katex') || id.includes('highlight.js') || id.includes('dompurify')) {
              return 'markdown';
            }
            if (id.includes('mermaid')) {
              return 'mermaid';
            }
            if (id.includes('@fortawesome')) {
              return 'icons';
            }
          }
        }
      }
    }
  }
})