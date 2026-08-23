import { createApp } from 'vue'
import './style-base.css'
import { registerLucide } from './utils/lucide'
import { initTheme } from './utils/theme'
import Profile from './views/Profile.vue'

initTheme()

const app = createApp(Profile)
registerLucide(app)
app.mount('#app')
