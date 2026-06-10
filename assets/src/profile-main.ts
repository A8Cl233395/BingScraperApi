import { createApp } from 'vue'
import './style-base.css'
import { registerFontAwesome } from './utils/fontawesome'
import { initTheme } from './utils/theme'
import Profile from './views/Profile.vue'

initTheme()

const app = createApp(Profile)
registerFontAwesome(app)
app.mount('#app')
