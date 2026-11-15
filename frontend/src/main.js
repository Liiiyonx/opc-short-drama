import { createApp } from 'vue'
import { createPinia } from 'pinia'

// 命令式 API 与 v-loading 不经模板编译，样式需手动引入
//（模板组件的样式由 unplugin-vue-components 按需注入，见 vite.config.js）
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/loading/style/css'

// 全局设计基座（品牌变量 / 页面容器 / 卡片表格观感）
import './styles/base.css'
// Element Plus 暗色模式变量（html.dark 时生效；开关在顶栏）
import 'element-plus/theme-chalk/dark/css-vars.css'

// 主题初始化（挂载前设置，避免闪烁）
if (localStorage.getItem('opc_theme') === 'dark') {
  document.documentElement.classList.add('dark')
}

import App from './App.vue'
import { router } from './router'

// Element Plus 组件由 unplugin-vue-components 按需注册（见 vite.config.js）；
// 全局中文 locale 由 App.vue 的 el-config-provider 提供。
createApp(App)
  .use(createPinia())
  .use(router)
  .mount('#app')
