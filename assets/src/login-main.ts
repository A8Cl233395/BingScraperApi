import { createApp } from 'vue'
import './style-base.css'
import { registerFontAwesome } from './utils/fontawesome'
import Login from './views/Login.vue'

const app = createApp(Login)
registerFontAwesome(app)
app.mount('#app')
