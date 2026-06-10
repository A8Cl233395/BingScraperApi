import { createApp } from 'vue'
import './style-base.css'
import './style-chat.css'
import { registerFontAwesome } from './utils/fontawesome'
import { initTheme } from './utils/theme'
import Chat from './views/Chat.vue'

initTheme()

const app = createApp(Chat)
registerFontAwesome(app)
app.mount('#app')