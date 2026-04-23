import { createApp } from 'vue'
import './style-base.css'
import './style-chat.css'
import Chat from './views/Chat.vue'

const app = createApp(Chat)
app.mount('#app')