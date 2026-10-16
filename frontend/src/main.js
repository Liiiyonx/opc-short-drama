import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'element-plus/dist/index.css'

import App from './App.vue'
import { router } from './router'

// Element Plus 组件由 unplugin-vue-components 按需注册（见 vite.config.js）；
// 全局中文 locale 由 App.vue 的 el-config-provider 提供。
createApp(App)
  .use(createPinia())
  .use(router)
  .mount('#app')
