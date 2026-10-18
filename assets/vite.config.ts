import { defineConfig } from 'vite'
import { resolve } from 'path'
import vue from '@vitejs/plugin-vue'
import { compression } from 'vite-plugin-compression2'

// 多页面应用（无 Vue Router）：每个入口对应一个独立 HTML + 视图，页面间跳转用
// window.location.href，聊天内切换用 hashchange + history.pushState。
// 预压缩产物由 main.py 的 CachedStaticFiles 按 Accept-Encoding 直接返回；
// 后端以 .br 是否存在判断“有预压缩版本”，故 brotli 开关需与后端逻辑同步。
export default defineConfig({
  plugins: [
    vue(),
    // compression({ algorithms: ['brotliCompress', 'gzip'] }),
    compression({ algorithms: ['gzip'] })
  ],
  build: {
    reportCompressedSize: false,
    rolldownOptions: {
      input: {
        webchat: resolve(__dirname, 'webchat.html'),
        login: resolve(__dirname, 'login.html'),
        invite: resolve(__dirname, 'invite.html'),
        profile: resolve(__dirname, 'profile.html'),
      },
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('lucide')) {
              return 'icons';
            }
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
          }
        }
      }
    }
  }
})