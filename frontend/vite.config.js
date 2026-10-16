import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [
    vue(),
    // Element Plus 按需注册组件（模板里的 el-* 自动引入），
    // 样式仍走全量 CSS（main.js 引入）——首屏 JS 从 1.1MB 降至 ~400KB。
    Components({
      resolvers: [ElementPlusResolver({ importStyle: false })],
      dts: false
    })
  ],
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    }
  }
})
