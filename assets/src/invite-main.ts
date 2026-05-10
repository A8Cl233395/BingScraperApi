import { createApp } from 'vue'
import './style-base.css'
import { registerFontAwesome } from './utils/fontawesome'
import Invite from './views/Invite.vue'

const app = createApp(Invite)
registerFontAwesome(app)
app.mount('#app')
