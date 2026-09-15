import type { CapacitorConfig } from '@capacitor/cli'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// 从同目录 .env 加载环境变量（文件不存在时忽略，可改用外部环境变量注入）
try {
  process.loadEnvFile(join(dirname(fileURLToPath(import.meta.url)), '.env'))
} catch {
  // 无 .env 时仅依赖进程环境变量
}

const serverUrl = process.env.CAP_SERVER_URL
if (!serverUrl) {
  throw new Error('缺少环境变量 CAP_SERVER_URL：请在 android-app/.env 中配置线上地址（参考 .env.example）')
}

// 直接加载线上地址，允许的跳转域名由该地址推导
const config: CapacitorConfig = {
  appId: 'com.ai.chat',
  appName: 'AI Chat',
  webDir: 'www',
  server: {
    url: serverUrl,
    allowNavigation: [new URL(serverUrl).hostname],
    cleartext: false,
  },
}

export default config
