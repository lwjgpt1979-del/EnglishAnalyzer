import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import { loadBranding } from './branding'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')

loadBranding()   // 启动读取项目名（公开接口）
