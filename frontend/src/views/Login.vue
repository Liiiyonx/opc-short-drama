<template>
  <div class="login-page">
    <!-- 氛围装饰 -->
    <span class="glow glow-a" aria-hidden="true"></span>
    <span class="glow glow-b" aria-hidden="true"></span>

    <!-- 品牌区 -->
    <header class="brand">
      <span class="brand-logo">
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M9 7.5 16.5 12 9 16.5z" fill="#fff" />
        </svg>
      </span>
      <h1 class="brand-name">OPC 短剧出海平台</h1>
      <p class="brand-slogan">AI 赋能 · 一人成军</p>
    </header>

    <!-- 居中玻璃登录卡 -->
    <main class="login-card">
      <h2 class="card-title">欢迎回来</h2>
      <p class="card-hint">学生 / 教师 / 企业 统一账号登录</p>

      <el-form :model="form" label-position="top" size="large" @submit.prevent="onLogin">
        <el-form-item label="账号">
          <el-input v-model="form.username" placeholder="请输入账号" clearable />
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
        <el-button type="primary" size="large" :loading="loading" class="login-btn" @click="onLogin">
          登 录
        </el-button>
      </el-form>

      <!-- 演示账号：由构建期 VITE_DEMO_ACCOUNTS 注入；生产构建无此变量 → 无凭据 -->
      <template v-if="DEMO_ACCOUNTS.length">
        <div class="demo-divider"><span>演示账号 · 点击快速填充</span></div>
        <div class="demo-grid">
          <button
            v-for="acc in DEMO_ACCOUNTS"
            :key="acc.username"
            type="button"
            class="demo-chip"
            :style="{ '--chip-color': acc.color }"
            @click="fillDemo(acc)"
          >
            <span class="chip-icon" v-html="acc.icon"></span>
            <span class="chip-text">
              <b>{{ acc.role }}</b>
              <small>{{ acc.username }}</small>
            </span>
          </button>
        </div>
      </template>
    </main>

    <footer class="page-footer">福州理工学院 · 产教融合创新实践</footer>
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

// P0-04 Demo 模式隔离：演示账号由构建期环境变量注入（VITE_DEMO_ACCOUNTS），
// 生产构建不携带该变量 → 产物中不含任何演示密码（可在 dist 里 grep 验证）。
const CHIP_ICONS = {
  student: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 10 12 5 2 10l10 5 10-5z"/><path d="M6 12v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5"/></svg>',
  teacher: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>',
  enterprise: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>',
  admin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>'
}
const CHIP_COLORS = {
  student: '#409eff',
  teacher: '#67c23a',
  enterprise: '#e6a23c',
  admin: '#f56c6c'
}

function parseDemoAccounts(raw) {
  try {
    const list = JSON.parse(raw || '[]')
    if (!Array.isArray(list)) return []
    return list
      .filter((acc) => acc && acc.username && acc.password)
      .map((acc) => ({ ...acc, icon: CHIP_ICONS[acc.key] || '', color: CHIP_COLORS[acc.key] || '#909399' }))
  } catch {
    return []
  }
}

const DEMO_ACCOUNTS = parseDemoAccounts(import.meta.env.VITE_DEMO_ACCOUNTS)

function fillDemo(acc) {
  form.username = acc.username
  form.password = acc.password
  ElMessage.success(`已填入${acc.role}演示账号，点击「登 录」体验`)
}

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
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  padding: 56px 24px;
  background:
    radial-gradient(1100px 550px at 12% -10%, rgba(64, 158, 255, 0.28), transparent 55%),
    radial-gradient(900px 520px at 105% 115%, rgba(124, 58, 237, 0.3), transparent 55%),
    linear-gradient(165deg, #0d1526 0%, #141d3a 50%, #1b1740 100%);
}

/* 细网格（中心淡出） */
.login-page::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px);
  background-size: 44px 44px;
  -webkit-mask-image: radial-gradient(ellipse 72% 62% at 50% 44%, #000 25%, transparent 74%);
  mask-image: radial-gradient(ellipse 72% 62% at 50% 44%, #000 25%, transparent 74%);
  pointer-events: none;
}

/* 氛围光斑（缓慢漂移） */
.glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);
  opacity: 0.55;
  pointer-events: none;
  animation: drift 14s ease-in-out infinite alternate;
}
.glow-a {
  width: 380px;
  height: 380px;
  background: rgba(64, 158, 255, 0.35);
  top: -100px;
  left: -80px;
}
.glow-b {
  width: 340px;
  height: 340px;
  background: rgba(124, 58, 237, 0.32);
  bottom: -80px;
  right: -60px;
  animation-delay: -7s;
}
@keyframes drift {
  from {
    transform: translate(0, 0) scale(1);
  }
  to {
    transform: translate(50px, 30px) scale(1.12);
  }
}

/* ---------- 品牌区 ---------- */

.brand {
  position: relative;
  z-index: 1;
  text-align: center;
  margin-bottom: 30px;
}
.brand-logo {
  width: 54px;
  height: 54px;
  border-radius: 15px;
  background: var(--opc-gradient);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 10px 30px rgba(64, 158, 255, 0.4);
}
.brand-logo svg {
  width: 26px;
  height: 26px;
}
.brand-name {
  margin: 14px 0 6px;
  font-size: 27px;
  font-weight: 700;
  letter-spacing: 1.5px;
  color: #fff;
}
.brand-slogan {
  margin: 0;
  font-size: 14px;
  letter-spacing: 3px;
  color: rgba(255, 255, 255, 0.55);
}

/* ---------- 玻璃登录卡（居中） ---------- */

.login-card {
  position: relative;
  z-index: 1;
  width: 420px;
  max-width: 94vw;
  background: rgba(255, 255, 255, 0.07);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 20px;
  padding: 30px 32px 26px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.38);
}
.card-title {
  margin: 0 0 4px;
  font-size: 21px;
  font-weight: 700;
  color: #fff;
}
.card-hint {
  margin: 0 0 20px;
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.5);
}

/* 深色玻璃上的输入框 */
.login-card :deep(.el-form-item__label) {
  color: rgba(255, 255, 255, 0.62);
  font-size: 12.5px;
  padding-bottom: 4px;
}
.login-card :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.07);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.14) inset;
  border-radius: 10px;
}
.login-card :deep(.el-input__wrapper.is-focus) {
  box-shadow:
    0 0 0 1px rgba(110, 168, 255, 0.85) inset,
    0 0 0 3px rgba(110, 168, 255, 0.18);
}
.login-card :deep(.el-input__inner) {
  color: #fff;
}
.login-card :deep(.el-input__inner::placeholder) {
  color: rgba(255, 255, 255, 0.32);
}
.login-card :deep(.el-input__suffix) {
  color: rgba(255, 255, 255, 0.5);
}

.login-btn {
  width: 100%;
  margin-top: 4px;
  background: var(--opc-gradient);
  border: none;
  font-weight: 600;
  letter-spacing: 4px;
}
.login-btn:hover,
.login-btn:focus {
  opacity: 0.92;
}

/* ---------- 演示账号 ---------- */

.demo-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 20px 0 14px;
  color: rgba(255, 255, 255, 0.42);
  font-size: 11.5px;
  letter-spacing: 1px;
  white-space: nowrap;
}
.demo-divider::before,
.demo-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.16));
}
.demo-divider::after {
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.16), transparent);
}

.demo-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.demo-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  cursor: pointer;
  text-align: left;
  transition: background 0.2s ease, transform 0.2s ease, border-color 0.2s ease;
}
.demo-chip:hover {
  background: rgba(255, 255, 255, 0.11);
  border-color: rgba(255, 255, 255, 0.22);
  transform: translateY(-2px);
}
.chip-icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: color-mix(in srgb, var(--chip-color) 20%, transparent);
  color: var(--chip-color);
}
.chip-icon :deep(svg),
.chip-icon svg {
  width: 15px;
  height: 15px;
}
.chip-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.chip-text b {
  font-size: 12.5px;
  font-weight: 600;
  color: #fff;
}
.chip-text small {
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 10.5px;
  color: rgba(255, 255, 255, 0.5);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ---------- 页脚 ---------- */

.page-footer {
  position: absolute;
  bottom: 22px;
  left: 0;
  right: 0;
  text-align: center;
  font-size: 12px;
  letter-spacing: 1px;
  color: rgba(255, 255, 255, 0.32);
  z-index: 1;
}

@media (max-width: 480px) {
  .login-card {
    padding: 24px 22px 20px;
  }
  .demo-grid {
    grid-template-columns: 1fr;
  }
}
</style>
