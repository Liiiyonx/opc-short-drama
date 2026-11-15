<template>
  <div class="nf-page">
    <div class="nf-card">
      <p class="nf-code">404</p>
      <p class="nf-text">页面不存在或已被移除</p>
      <el-button type="primary" @click="back">返回工作台</el-button>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

import { roleHome, useUserStore } from '../stores/user.js'

const router = useRouter()
const userStore = useUserStore()

function back() {
  if (userStore.isLoggedIn) {
    router.push(roleHome(userStore.role))
  } else {
    router.push('/login')
  }
}
</script>

<style scoped>
.nf-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(900px 450px at 20% -10%, rgba(64, 158, 255, 0.12), transparent 55%),
    radial-gradient(900px 450px at 110% 110%, rgba(124, 58, 237, 0.12), transparent 55%),
    var(--el-bg-color-page);
}
.nf-card {
  text-align: center;
  padding: 40px 60px;
}
.nf-code {
  margin: 0;
  font-size: 72px;
  font-weight: 800;
  letter-spacing: 4px;
  background: var(--opc-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.nf-text {
  margin: 8px 0 24px;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}
</style>
