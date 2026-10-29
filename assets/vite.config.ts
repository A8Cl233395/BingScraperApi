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
      // 注意：不要用 manualChunks 手动分包。rolldown 下它会把 axios 等库切到独立
      // chunk，而 CJS 互操作辅助函数（var 赋值、不提升）落到共享 chunk（含 api/store，
      // 又反向 import 库 chunk），形成 chunk 循环依赖：库 chunk 顶层先求值时拿到的
      // 辅助函数还是 undefined，报 "TypeError: undefined is not a function"。
      // dev 无 chunk 切分故不复现。交由 rolldown 自动分包即可（循环模块会同 chunk）。
    }
  }
})