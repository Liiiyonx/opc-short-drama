<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2 class="title">OPC 短剧出海平台</h2>
      <el-form :model="form" label-position="top">
        <el-form-item label="账号">
          <el-input v-model="form.username" placeholder="学生 / 教师 / 企业 统一账号" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="请输入密码"
            @keyup.enter="onLogin"
          />
        </el-form-item>
        <el-button type="primary" :loading="loading" style="width: 100%" @click="onLogin">
          登 录
        </el-button>
      </el-form>
      <p class="tip">AI 赋能 · 一人成军</p>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore, roleHome } from '../stores/user.js'

const router = useRouter()
const userStore = useUserStore()
const form = reactive({ username: '', password: '' })
const loading = ref(false)

async function onLogin() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入账号和密码')
    return
  }
  loading.value = true
  try {
    const user = await userStore.login({ username: form.username, password: form.password })
    router.push(roleHome(user.role))
  } catch (error) {
    ElMessage.error(error.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-card {
  width: 360px;
  max-width: 90vw;
}
.title {
  text-align: center;
  margin: 0 0 16px;
  font-weight: 500;
}
.tip {
  text-align: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 12px 0 0;
}
</style>
