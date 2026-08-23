import { createApp } from 'vue'
import './style-base.css'
import './style-chat.css'
import { registerLucide } from './utils/lucide'
import { initTheme } from './utils/theme'
import Chat from './views/Chat.vue'

initTheme()

const app = createApp(Chat)
registerLucide(app)
app.mount('#app')