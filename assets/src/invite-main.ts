import { createApp } from 'vue'
import './style-base.css'
import { initTheme } from './utils/theme'
import Invite from './views/Invite.vue'

initTheme()

const app = createApp(Invite)
app.mount('#app')
