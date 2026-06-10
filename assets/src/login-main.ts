import { createApp } from 'vue'
import './style-base.css'
import { initTheme } from './utils/theme'
import Login from './views/Login.vue'

initTheme()

const app = createApp(Login)
app.mount('#app')
