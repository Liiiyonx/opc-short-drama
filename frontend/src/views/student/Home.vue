<template>
  <div class="page">
    <div class="home-head">
      <div>
        <h3 class="title">学生工作台</h3>
        <span class="sub">{{ greeting }}</span>
      </div>
      <div class="actions">
        <el-button type="primary" @click="newDialog = true">新建剧集</el-button>
        <el-button text @click="logout">退出登录</el-button>
      </div>
    </div>

    <el-row :gutter="12" class="stat-row">
      <el-col :span="6" v-for="stat in stats" :key="stat.label">
        <el-card shadow="never" class="stat-card">
          <div class="stat-num">{{ stat.value }}</div>
          <div class="stat-label">{{ stat.label }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <template #header>
        <span>我的作品</span>
        <el-button size="small" text type="primary" @click="reload">刷新</el-button>
      </template>
      <el-table :data="works" v-loading="loading" empty-text="还没有作品，点击「新建剧集」开始创作">
        <el-table-column label="标题" prop="title" min-width="160" show-overflow-tooltip />
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ TYPE_LABELS[row.type] || row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ STATUS_LABELS[row.status] || row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="版本" prop="version" width="70" />
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-button size="small" type="primary" text @click="openWorkshop(row.id)">进入工坊</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="newDialog" title="新建剧集" width="420px">
      <el-form label-width="72px">
        <el-form-item label="剧名">
          <el-input v-model="newTitle" placeholder="如：外卖箱里的秘密" maxlength="50" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" :disabled="!newTitle.trim()" @click="createAndEnter">创建并进入工坊</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useUserStore } from '../../stores/user.js'
import { useWorkStore } from '../../stores/work.js'

const TYPE_LABELS = {
  script: '剧本',
  storyboard: '分镜',
  audio: '配音',
  subtitle: '字幕',
  video: '成片'
}

const STATUS_LABELS = {
  draft: '草稿',
  generating: '生成中',
  ready: '已完成',
  failed: '失败'
}

const userStore = useUserStore()
const workStore = useWorkStore()
const router = useRouter()

const newDialog = ref(false)
const newTitle = ref('')

const works = computed(() => workStore.works)
const loading = computed(() => workStore.loading)

const stats = computed(() => {
  const all = workStore.works
  return [
    { label: '剧本', value: all.filter((w) => w.type === 'script').length },
    { label: '分镜', value: all.filter((w) => w.type === 'storyboard').length },
    { label: '配音', value: all.filter((w) => w.type === 'audio').length },
    { label: '成片', value: all.filter((w) => w.type === 'video').length }
  ]
})

const greeting = computed(() => {
  const name = userStore.profile ? userStore.profile.username : ''
  const profile = userStore.profile && userStore.profile.profile
  const major = profile && profile.major ? ` · ${profile.major}` : ''
  return `${name}${major} · 学中做，做中创`
})

function statusType(status) {
  if (status === 'ready') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'generating') return 'warning'
  return 'info'
}

function formatTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 16)
}

function openWorkshop(workId) {
  router.push(`/student/workshop/${workId}`)
}

async function createAndEnter() {
  const title = newTitle.value.trim()
  const work = await workStore.createWork({ title, type: 'script' })
  newDialog.value = false
  newTitle.value = ''
  router.push(`/student/workshop/${work.id}`)
}

function logout() {
  userStore.logout()
  router.push('/login')
}

async function reload() {
  await workStore.loadWorks({ page: 1, page_size: 50 })
}

onMounted(async () => {
  if (!userStore.profile) {
    await userStore.fetchMe()
  }
  await reload()
})
</script>

<style scoped>
.page {
  padding: 20px 24px 40px;
  max-width: 1080px;
  margin: 0 auto;
}
.home-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}
.title {
  margin: 0 0 4px;
  font-weight: 500;
}
.sub {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.stat-row {
  margin-bottom: 16px;
}
.stat-card {
  text-align: center;
}
.stat-num {
  font-size: 24px;
  font-weight: 500;
}
.stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
