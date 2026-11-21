<template>
  <header class="app-header">
    <div class="app-header-inner">
      <button class="brand" type="button" @click="goHome">
        <span class="logo">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M9 7.5 16.5 12 9 16.5z" fill="#fff" />
          </svg>
        </span>
        <span class="name">OPC 短剧出海平台</span>
        <el-tag v-if="roleLabel" size="small" effect="plain" round class="role-tag">
          {{ roleLabel }}
        </el-tag>
      </button>

      <div class="right">
        <span class="username">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
          {{ username }}
        </span>
        <button
          class="theme-toggle"
          type="button"
          :title="isDark ? '切换到亮色模式' : '切换到暗色模式'"
          @click="toggleTheme"
        >
          <!-- 太阳（暗色时显示，点击回亮色） -->
          <svg v-if="isDark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <circle cx="12" cy="12" r="5" />
            <line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" />
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
            <line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" />
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
          </svg>
          <!-- 月亮（亮色时显示，点击切暗色） -->
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
          </svg>
        </button>
        <el-button text size="small" @click="logout">退出登录</el-button>
      </div>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import { roleHome, useUserStore } from '../stores/user.js'

const ROLE_LABELS = {
  student: '学生端',
  teacher: '教师端',
  enterprise: '企业端',
  admin: '管理后台'
}

const router = useRouter()
const userStore = useUserStore()

const username = computed(() => (userStore.profile ? userStore.profile.username : ''))
const roleLabel = computed(() => ROLE_LABELS[userStore.role] || '')

function goHome() {
  router.push(roleHome(userStore.role))
}

function logout() {
  userStore.logout()
  router.push('/login')
}

// 暗色模式开关（html.dark + EP dark vars；持久化到 localStorage）
const isDark = computed(() => document.documentElement.classList.contains('dark'))

function toggleTheme() {
  const dark = document.documentElement.classList.toggle('dark')
  localStorage.setItem('opc_theme', dark ? 'dark' : 'light')
}
</script>

<style scoped>
.app-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.app-header-inner {
  max-width: 1080px;
  margin: 0 auto;
  padding: 0 24px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  border: none;
  background: none;
  padding: 0;
  cursor: pointer;
}

.logo {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: var(--opc-gradient);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.logo svg {
  width: 18px;
  height: 18px;
}

.name {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--el-text-color-primary);
}

.role-tag {
  margin-left: 2px;
}

.right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.username {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.username svg {
  width: 14px;
  height: 14px;
  color: var(--el-text-color-secondary);
}

.theme-toggle {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  background: transparent;
  color: var(--el-text-color-regular);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s ease;
}
.theme-toggle:hover {
  background: var(--el-fill-color-light);
}
.theme-toggle svg {
  width: 15px;
  height: 15px;
}

/* 暗色模式：顶栏底色适配（原为半透明白） */
:global(html.dark) .app-header {
  background: rgba(24, 24, 27, 0.92);
  border-bottom-color: var(--el-border-color);
}
:global(html.dark) .brand .name {
  color: #f3f4f6;
}

/* ---------- P0-07 移动端：拆分为品牌行 + 账号行，消除重叠 ---------- */
@media (max-width: 640px) {
  .app-header-inner {
    flex-wrap: wrap;
    height: auto;
    padding: 8px 16px;
    row-gap: 4px;
  }
  .brand {
    flex: 1;
    min-width: 0;
  }
  .name {
    font-size: 14px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 52vw;
  }
  .right {
    width: 100%;
    justify-content: flex-end;
  }
  /* 触控目标 ≥ 40px */
  .theme-toggle {
    width: 38px;
    height: 38px;
  }
  .right :deep(.el-button) {
    min-height: 38px;
  }
}
</style>
